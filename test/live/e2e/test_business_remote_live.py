"""Live business simulation in remote mode against real Virtuoso daemons.

Requires ``VB_E2E=1`` and running bridge daemons on ``wsl-gent`` (the
multi-Virtuoso pilot creates them).  Every skill uses ``RBDToken`` so the
response must come from the daemon that owns the token — an automatic
routing check on real daemons, not protocol fakes.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from transport.middle import BusinessServer
from register.probe import allocate_local_port
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests

HOST = "wsl-gent"
USER = "Gent"
SCRATCH = "/home/Gent/.virtuoso-bridge"


def _ssh(cmd: str, timeout: int = 60) -> str:
    return subprocess.run(
        ["ssh", HOST, cmd], capture_output=True, text=True, timeout=timeout
    ).stdout


def discover_daemons(limit: int | None = None) -> list[tuple[str, str, int]]:
    """Return (username, token, port) for every token-bearing daemon."""
    out = _ssh('pgrep -fa "ramic_bridge_daemon_(3|27)\\.py"')
    found: list[tuple[str, str, int]] = []
    for line in out.splitlines():
        if "bash -c" in line or "pgrep" in line:
            continue
        parts = line.split()
        py_idx = next((i for i, part in enumerate(parts) if part.endswith(".py")), None)
        if py_idx is None:
            continue
        tail = parts[py_idx + 1:]
        if len(tail) < 3:
            continue
        try:
            port = int(tail[1])
        except ValueError:
            continue
        token = tail[2]
        marker = ".virtuoso-bridge/"
        if marker not in parts[py_idx]:
            continue
        username = parts[py_idx].split(marker, 1)[1].split("/", 1)[0]
        prefix = os.environ.get("VB_E2E_PREFIX", "vb")
        if prefix and not username.startswith(prefix):
            continue
        found.append((username, token, port))
    # one entry per user/token (a reload can briefly show two daemon lines)
    seen_users: set[str] = set()
    deduped: list[tuple[str, str, int]] = []
    for username, token, port in sorted(found, key=lambda item: item[2]):
        if username in seen_users:
            continue
        seen_users.add(username)
        deduped.append((username, token, port))
    return deduped[:limit] if limit else deduped


class TestBusinessRemoteLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("VB_E2E") != "1":
            raise unittest.SkipTest("set VB_E2E=1 to run live tests")
        daemons = discover_daemons()
        if not daemons:
            raise unittest.SkipTest("no live bridge daemons found")
        limit = int(os.environ.get("VB_E2E_USERS") or len(daemons))
        cls.daemons = daemons[:limit]
        cls.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        registry = load_registry(registry_path())
        reserved: set[int] = set()
        for username, token, port in cls.daemons:
            local_port = allocate_local_port(reserved=reserved, tries=200)
            if local_port is None:
                raise RuntimeError("no free local tunnel ports")
            reserved.add(local_port)
            entry = UserEntry(token=token, mode="remote")
            # ``roles.resolve`` resolves all five roles eagerly, so the
            # one-host fallback must be present even though this test only
            # drives skill/command/file: without it every operation dies with
            # "role gui is remote but host/user is unresolved" (the temp
            # work-dir has no VB_REMOTE_HOST to fall back to).
            entry.ssh.default.host = HOST
            entry.ssh.default.user = USER
            entry.roles.daemon.host = HOST
            entry.roles.daemon.user = USER
            entry.roles.daemon.daemon_port = port
            entry.roles.daemon.local_port = local_port
            entry.roles.command.host = HOST
            entry.roles.command.user = USER
            entry.roles.file.host = HOST
            entry.roles.file.user = USER
            entry.roles.gui.host = HOST
            entry.roles.gui.user = USER
            entry.roles.spectre.host = HOST
            entry.roles.spectre.user = USER
            entry.roles.daemon.root = f"{SCRATCH}/{username}"
            entry.roles.daemon.expected_user = USER
            entry.ssh.backend = "paramiko"
            entry.ssh.control_master = "disable"
            entry.runtime.channel_budget = 12
            registry.register(username, entry)
        cls.server = BusinessServer(cls.wd)

    @classmethod
    def tearDownClass(cls) -> None:
        clients = list(getattr(cls, "server", None) and cls.server._clients.values() or [])
        for client in clients:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass

    def test_skill_routes_to_own_daemon_for_every_user(self):
        bad = []
        for username, token, port in self.daemons:
            r = self.server.execute_skill("RBDToken", timeout=60, token=token)
            got = (r.output or "").strip().strip('"')
            if not r.ok or got != token:
                bad.append((username, token, port, r.status, got, r.errors))
        self.assertEqual(bad, [])

    def test_business_surface_on_sample_users(self):
        for username, token, port in self.daemons[: min(5, len(self.daemons))]:
            r = self.server.execute_skill("1+1", token=token)
            self.assertTrue(r.ok, str(r))
            self.assertEqual(r.output.strip().strip('"'), "2")

            c = self.server.run_command("echo vb-ok", token=token)
            self.assertEqual((c.returncode, c.stdout.strip()), (0, "vb-ok"))

            payload = (username.encode() * 1000)
            src = Path(self.wd) / f"{username}.bin"
            src.write_bytes(payload)
            remote = f"{SCRATCH}/{username}/files/e2e.bin"
            u = self.server.upload_file(src, remote, token=token)
            self.assertEqual(u.returncode, 0, u.stderr)
            back = Path(self.wd) / f"{username}-back.bin"
            d = self.server.download_file(remote, back, token=token)
            self.assertEqual(d.returncode, 0, d.stderr)
            self.assertEqual(back.read_bytes(), payload)

    def test_parallel_commands_overlap(self):
        username, token, _port = self.daemons[0]
        results: dict[int, tuple[float, float]] = {}

        def run(i: int) -> None:
            cmd = (
                "s=$(date +%s.%N); sleep 2; e=$(date +%s.%N); "
                "printf '%s %s' \"$s\" \"$e\""
            )
            r = self.server.run_command(cmd, token=token, parallel=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            parts = r.stdout.strip().split()
            results[i] = (float(parts[0]), float(parts[1]))

        ts = [threading.Thread(target=run, args=(i,)) for i in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        (s0, e0), (s1, e1) = results[0], results[1]
        self.assertGreater(min(e0, e1) - max(s0, s1), 0.5)

    def test_mixed_concurrency_retries_until_all_succeed(self):
        tokens = [token for _username, token, _port in self.daemons]
        roots = [f"{SCRATCH}/{username}" for username, _token, _port in self.daemons]
        errors: list[str] = []
        lock = threading.Lock()

        def skill(i: int) -> None:
            tok = tokens[i % len(tokens)]
            try:
                r = self.server.execute_skill("RBDToken", timeout=60, token=tok)
                retry_deadline = time.monotonic() + 180
                while (not r.ok
                       and time.monotonic() < retry_deadline
                       and any(k in str(r.errors).lower()
                               for k in ("exceeded", "tunnel", "banner", "closed", "reset"))):
                    time.sleep(0.2)
                    r = self.server.execute_skill("RBDToken", timeout=60, token=tok)
                got = (r.output or "").strip().strip('"')
                if not r.ok or got != tok:
                    with lock:
                        errors.append(f"skill {tok} -> {r.status} {got} {r.errors}")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"skill {tok}: {exc}")

        def command(i: int) -> None:
            tok = tokens[i % len(tokens)]
            try:
                c = self.server.run_command(f"echo vb-{i}", token=tok, parallel=True)
                while c.returncode == 1 and "exceeded" in c.stderr:
                    time.sleep(0.02)
                    c = self.server.run_command(f"echo vb-{i}", token=tok, parallel=True)
                if c.returncode != 0 or c.stdout.strip() != f"vb-{i}":
                    with lock:
                        errors.append(f"command {tok} rc={c.returncode} out={c.stdout!r} err={c.stderr!r}")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"command {tok}: {exc}")

        def upload(i: int) -> None:
            tok = tokens[i % len(tokens)]
            root = roots[i % len(roots)]
            try:
                src = Path(tempfile.mkdtemp(prefix="vb-")) / "f.bin"
                src.write_bytes(tok.encode())
                remote = f"{root}/files/e2e-conc-{i}.bin"
                u = self.server.upload_file(src, remote, token=tok)
                while u.returncode == 1 and "exceeded" in u.stderr:
                    time.sleep(0.02)
                    u = self.server.upload_file(src, remote, token=tok)
                if u.returncode != 0:
                    with lock:
                        errors.append(f"upload {tok}: {u.stderr}")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"upload {tok}: {exc}")

        def download(i: int) -> None:
            tok = tokens[i % len(tokens)]
            root = roots[i % len(roots)]
            try:
                remote = f"{root}/files/e2e-conc-{i}.bin"
                dst = Path(tempfile.mkdtemp(prefix="vb-")) / "g.bin"
                d = self.server.download_file(remote, dst, token=tok)
                while d.returncode == 1 and "exceeded" in d.stderr:
                    time.sleep(0.02)
                    d = self.server.download_file(remote, dst, token=tok)
                if d.returncode != 0 or dst.read_bytes() != tok.encode():
                    with lock:
                        errors.append(f"download {tok} rc={d.returncode} {d.stderr}")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"download {tok}: {exc}")

        with ThreadPoolExecutor(max_workers=64) as pool:
            list(pool.map(skill, range(len(tokens) * 2)))
        with ThreadPoolExecutor(max_workers=64) as pool:
            list(pool.map(command, range(len(tokens) * 2)))
        with ThreadPoolExecutor(max_workers=32) as pool:
            list(pool.map(upload, range(len(tokens))))
        with ThreadPoolExecutor(max_workers=32) as pool:
            list(pool.map(download, range(len(tokens))))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
