"""Live business simulation in LOCAL mode on the Virtuoso host (wsl-gent).

Run ON the Linux host after deploying ``src/`` there::

    VB_E2E_LOCAL=1 python -m unittest discover -s test/e2e -p "test_business_local_live.py" -v

The test registers local accounts through the six-step flow, launches one real
Virtuoso per account whose ``.cdsinit`` loads the generated local setup, then
drives all three business interfaces (skill / command / file) with concurrency.
No SSH is involved: the middle layer runs on the same host as Virtuoso.
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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer
from transport.register import RegistrationFlow, RegistrationRequest
from transport.registry import load_registry
from transport.runtime_paths import registry_path, set_working_dir

DISPLAY = os.environ.get("VB_LOCAL_DISPLAY", ":10")
PROJECT_ROOT = Path(os.environ.get("VB_LOCAL_PROJECT_ROOT", "/home/Gent/project"))


def _port_open(port: int, timeout: float = 0.5) -> bool:
    s = socket.socket()
    s.settimeout(timeout)
    try:
        return s.connect_ex(("127.0.0.1", port)) == 0
    finally:
        s.close()


class TestBusinessLocalLive(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("VB_E2E_LOCAL") != "1":
            raise unittest.SkipTest("set VB_E2E_LOCAL=1 to run local live tests")
        if os.name == "nt":
            raise unittest.SkipTest("local live tests must run on the Virtuoso host")
        cls.users_n = int(os.environ.get("VB_LOCAL_USERS", "4"))
        port_base = int(os.environ.get("VB_LOCAL_PORT_BASE", "65401"))
        cls.wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-local-")))
        registry = load_registry(registry_path())

        cls.users: list[tuple[str, str, int]] = []
        cls.flows: dict[str, RegistrationFlow] = {}
        cls.project_dirs: list[Path] = []
        for i in range(cls.users_n):
            user = f"l{i:02d}"
            token = f"l-{user}"
            port = port_base + i
            flow = RegistrationFlow(registry)
            state = flow.apply(RegistrationRequest(
                user=user, token=token, local=True, daemon_port=port,
            ))
            if state.stage != "deployed":
                raise RuntimeError(f"{user} deploy failed: {state.errors}")

            project_dir = PROJECT_ROOT / user
            project_dir.mkdir(parents=True, exist_ok=True)
            (project_dir / ".cdsinit").write_text(
                f'load("{state.setup_path}")\n', encoding="utf-8"
            )
            cls.project_dirs.append(project_dir)
            cls.users.append((user, token, port))
            cls.flows[user] = flow

        for user, _token, port in cls.users:
            cls._start_virtuoso(user)
            deadline = time.monotonic() + 240
            while time.monotonic() < deadline and not _port_open(port):
                time.sleep(2)
            if not _port_open(port):
                raise RuntimeError(f"daemon for {user} never bound port {port}")
            time.sleep(1)

        # step 5-6: connectivity test + single registry commit per user
        for user, _token, _port in cls.users:
            state = cls.flows[user].verify()
            if state.stage != "committed":
                raise RuntimeError(f"{user} verify failed: {state.errors}")

        cls.server = BusinessServer(cls.wd)

    @staticmethod
    def _start_virtuoso(user: str) -> None:
        project_dir = PROJECT_ROOT / user
        cmd = (
            f"cd {project_dir} && DISPLAY={DISPLAY} nohup bash -lc "
            f"'source ~/.bashrc; virtuoso -log {project_dir}/CDS.log' "
            f"> {project_dir}/start.log 2>&1 < /dev/null &"
        )
        subprocess.run(["bash", "-lc", cmd], check=True, timeout=30)

    @classmethod
    def tearDownClass(cls) -> None:
        clients = list(getattr(cls, "server", None) and cls.server._clients.values() or [])
        for client in clients:
            try:
                client.close()
            except Exception:  # noqa: BLE001
                pass
        for _user, _token, _port in cls.users:
            pass
        for project_dir in cls.project_dirs:
            subprocess.run(
                ["pkill", "-f", f"project/{project_dir.name}/CDS.log"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

    # -- helpers -------------------------------------------------------------

    def token_of(self, i: int) -> str:
        return self.users[i][1]

    # -- tests ---------------------------------------------------------------

    def test_skill_routes_to_own_daemon(self):
        bad = []
        for user, token, port in self.users:
            r = self.server.execute_skill("RBDToken", timeout=30, token=token)
            got = (r.output or "").strip().strip('"')
            if not r.ok or got != token:
                bad.append((user, token, port, r.status, got, r.errors))
        self.assertEqual(bad, [])

    def test_business_surface(self):
        for user, token, _port in self.users:
            r = self.server.execute_skill("1+1", token=token)
            self.assertTrue(r.ok, str(r))
            self.assertEqual(r.output.strip().strip('"'), "2")

            c = self.server.run_command("echo vb-ok", token=token)
            self.assertEqual((c.returncode, c.stdout.strip()), (0, "vb-ok"))

            payload = user.encode() * 1000
            src = Path(self.wd) / f"{user}.bin"
            src.write_bytes(payload)
            remote = f"{self.wd}/{user}/files/e2e.bin"
            u = self.server.upload_file(src, remote, token=token)
            self.assertEqual(u.returncode, 0, u.stderr)
            back = Path(self.wd) / f"{user}-back.bin"
            d = self.server.download_file(remote, back, token=token)
            self.assertEqual(d.returncode, 0, d.stderr)
            self.assertEqual(back.read_bytes(), payload)

    def test_parallel_commands_overlap(self):
        _user, token, _port = self.users[0]
        results: dict[int, tuple[float, float]] = {}

        def run(i: int) -> None:
            cmd = (
                "s=$(date +%s.%N); sleep 1; e=$(date +%s.%N); "
                "printf '%s %s' \"$s\" \"$e\""
            )
            c = self.server.run_command(cmd, token=token, parallel=True)
            self.assertEqual(c.returncode, 0, c.stderr)
            parts = c.stdout.strip().split()
            results[i] = (float(parts[0]), float(parts[1]))

        ts = [threading.Thread(target=run, args=(i,)) for i in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        (s0, e0), (s1, e1) = results[0], results[1]
        self.assertGreater(min(e0, e1) - max(s0, s1), 0.3)

    def test_mixed_concurrency_retries_until_all_succeed(self):
        users = [u for u, _t, _p in self.users]
        tokens = [t for _u, t, _p in self.users]
        errors: list[str] = []
        lock = threading.Lock()

        def skill(i: int) -> None:
            tok = tokens[i % len(tokens)]
            try:
                r = self.server.execute_skill("RBDToken", timeout=30, token=tok)
                while not r.ok and "exceeded" in str(r.errors):
                    time.sleep(0.02)
                    r = self.server.execute_skill("RBDToken", timeout=30, token=tok)
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
                c = self.server.run_command(f"echo vb-{i}", token=tok)
                if c.returncode != 0 or c.stdout.strip() != f"vb-{i}":
                    with lock:
                        errors.append(f"command {tok} rc={c.returncode} {c.stdout!r} {c.stderr!r}")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"command {tok}: {exc}")

        def upload(i: int) -> None:
            tok = tokens[i % len(tokens)]
            user = users[i % len(users)]
            try:
                src = Path(tempfile.mkdtemp()) / "f.bin"
                src.write_bytes(tok.encode())
                remote = f"{self.wd}/{user}/files/conc-{i}.bin"
                u = self.server.upload_file(src, remote, token=tok)
                if u.returncode != 0:
                    with lock:
                        errors.append(f"upload {tok}: {u.stderr}")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"upload {tok}: {exc}")

        def download(i: int) -> None:
            tok = tokens[i % len(tokens)]
            user = users[i % len(users)]
            try:
                remote = f"{self.wd}/{user}/files/conc-{i}.bin"
                dst = Path(tempfile.mkdtemp()) / "g.bin"
                d = self.server.download_file(remote, dst, token=tok)
                if d.returncode != 0 or dst.read_bytes() != tok.encode():
                    with lock:
                        errors.append(f"download {tok} rc={d.returncode} {d.stderr}")
            except Exception as exc:  # noqa: BLE001
                with lock:
                    errors.append(f"download {tok}: {exc}")

        with ThreadPoolExecutor(max_workers=32) as pool:
            list(pool.map(skill, range(len(tokens) * 8)))
        with ThreadPoolExecutor(max_workers=32) as pool:
            list(pool.map(command, range(len(tokens) * 6)))
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(upload, range(len(tokens) * 2)))
        with ThreadPoolExecutor(max_workers=16) as pool:
            list(pool.map(download, range(len(tokens) * 2)))
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
