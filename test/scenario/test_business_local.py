"""Scenario: complete business simulation over the three middle interfaces.

Local mode against protocol-accurate fake bottom daemons.  Covers the full
business surface without requiring a live Virtuoso: skill value/error/
timeout/log, command rc/stdout/stderr/timeout, parallel command overlap,
upload/download roundtrip + recursion + error branches, multi-user token
routing and per-token thread-pool rejection.
"""

from __future__ import annotations

import hashlib
import json
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
from transport.registry import UserEntry, load_registry
from transport.runtime_paths import registry_path, set_working_dir

STX = "\x02"
NAK = "\x15"
RS = "\x1e"


class FakeDaemon:
    """Protocol-accurate bottom endpoint, one token, serial handler."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.requests = 0
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(128)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _reply(self, conn: socket.socket, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        conn.sendall(STX.encode() + body + RS.encode())

    def _serve(self) -> None:
        while True:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            try:
                data = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk:
                        break
                    data += chunk
                req = json.loads(data.decode("utf-8"))
                self.requests += 1
                if req.get("token") != self.token:
                    conn.sendall(NAK.encode() + json.dumps(
                        {"error": "invalid token", "log": ""}).encode() + RS.encode())
                    conn.close()
                    continue
                skill = req.get("skill", "")
                if skill == "boom":
                    conn.sendall(NAK.encode() + json.dumps(
                        {"error": "boom-error", "log": ""}).encode() + RS.encode())
                elif skill == "slow":
                    time.sleep(1.0)
                    self._reply(conn, {"value": "ok", "log": "\\o VB-END"})
                elif skill == "whoami":
                    self._reply(conn, {"value": self.token, "log": "\\o VB-END"})
                else:
                    value = "2" if "1+1" in skill else "3"
                    self._reply(conn, {"value": value, "log": f"\\o VB-BEGIN\\n{skill}\\n\\o VB-END"})
            except Exception:
                pass
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def close(self) -> None:
        try:
            self._sock.close()
        except OSError:
            pass


def _entry(token: str, daemon: FakeDaemon) -> UserEntry:
    entry = UserEntry(token=token, mode="local")
    entry.route.skill.daemon_port = daemon.port
    entry.route.skill.local_port = daemon.port
    entry.runtime.thread_pool_size = 4  # small pool to exercise rejection
    return entry


class TestBusinessLocal(unittest.TestCase):
    def setUp(self) -> None:
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.daemon = FakeDaemon("tok-a")
        self.registry = load_registry(registry_path())
        self.registry.register("alice", _entry("tok-a", self.daemon))
        self.server = BusinessServer(self.wd)
        self.root = Path(tempfile.mkdtemp())

    def tearDown(self) -> None:
        self.daemon.close()

    # -- skill -------------------------------------------------------------

    def test_skill_value_log_and_whoami(self):
        r = self.server.execute_skill("1+1", token="tok-a")
        self.assertTrue(r.ok, str(r))
        self.assertEqual(r.output.strip().strip('"'), "2")
        self.assertIn("VB-BEGIN", r.log)
        self.assertEqual(self.server.execute_skill("whoami", token="tok-a").output, "tok-a")

    def test_skill_error_surfaces(self):
        r = self.server.execute_skill("boom", token="tok-a")
        self.assertFalse(r.ok)
        self.assertIn("boom-error", r.errors[0])

    def test_skill_timeout(self):
        r = self.server.execute_skill("slow", timeout=0.3, token="tok-a")
        self.assertFalse(r.ok)
        self.assertTrue(any("timed out" in (e or "") for e in r.errors))

    def test_unknown_token_rejected_before_daemon(self):
        r = self.server.execute_skill("1+1", token="nope")
        self.assertFalse(r.ok)
        self.assertIn("unknown token", str(r.errors).lower())
        self.assertEqual(self.daemon.requests, 0)

    # -- command -------------------------------------------------------------

    def test_command_rc_stdout_stderr(self):
        c = self.server.run_command("echo hello", token="tok-a")
        self.assertEqual((c.returncode, c.stdout.strip()), (0, "hello"))
        py = sys.executable
        c = self.server.run_command(
            f'"{py}" -c "import sys; print(chr(111)+chr(111)+chr(112)+chr(115), file=sys.stderr); sys.exit(3)"',
            token="tok-a",
        )
        self.assertEqual((c.returncode, c.stderr.strip()), (3, "oops"))

    def test_command_timeout(self):
        py = sys.executable
        c = self.server.run_command(
            f'"{py}" -c "import time; time.sleep(2)"', timeout=0.3, token="tok-a"
        )
        self.assertEqual(c.returncode, 124)
        self.assertIn("timed out", c.stderr)

    def test_local_default_serial_and_explicit_parallel(self):
        py = sys.executable
        cmd = f'"{py}" -c "import time; time.sleep(0.4)"'

        def run(parallel: bool, out: dict, key: str) -> None:
            out[key] = self.server.run_command(cmd, token="tok-a", parallel=parallel).returncode

        serial = {}
        t0 = time.time()
        ts = [threading.Thread(target=run, args=(False, serial, 1)),
              threading.Thread(target=run, args=(False, serial, 2))]
        for th in ts:
            th.start()
        for th in ts:
            th.join()
        serial_elapsed = time.time() - t0
        self.assertEqual(set(serial.values()), {0})
        # default parallel=False must hold the per-token serial lock
        self.assertGreaterEqual(serial_elapsed, 0.8)

        parallel = {}
        t0 = time.time()
        ts = [threading.Thread(target=run, args=(True, parallel, 1)),
              threading.Thread(target=run, args=(True, parallel, 2))]
        for th in ts:
            th.start()
        for th in ts:
            th.join()
        self.assertEqual(set(parallel.values()), {0})
        self.assertLess(time.time() - t0, 0.7)

    def test_parallel_commands_overlap(self):
        py = sys.executable
        results: dict[int, tuple[float, float]] = {}

        def run(i: int) -> None:
            cmd = (
                f'"{py}" -c "import time; s=time.time(); time.sleep(0.5); e=time.time(); '
                f'print(s, e)"'
            )
            c = self.server.run_command(cmd, token="tok-a", parallel=True)
            self.assertEqual(c.returncode, 0, c.stderr)
            s, e = c.stdout.split()
            results[i] = (float(s), float(e))

        ts = [threading.Thread(target=run, args=(i,)) for i in range(2)]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        (s0, e0), (s1, e1) = results[0], results[1]
        self.assertGreater(min(e0, e1) - max(s0, s1), 0.1)

    # -- file ----------------------------------------------------------------

    def test_upload_download_roundtrip(self):
        payload = bytes(range(256)) * 16
        src = self.root / "payload.bin"
        src.write_bytes(payload)
        remote = str(self.root / "remote" / "payload.bin")
        u = self.server.upload_file(src, remote, token="tok-a")
        self.assertEqual(u.returncode, 0, u.stderr)
        back = self.root / "back.bin"
        d = self.server.download_file(remote, back, token="tok-a")
        self.assertEqual(d.returncode, 0, d.stderr)
        self.assertEqual(back.read_bytes(), payload)
        self.assertEqual(hashlib.sha256(back.read_bytes()).hexdigest(),
                         hashlib.sha256(payload).hexdigest())

    def test_recursive_upload_download(self):
        tree = self.root / "tree"
        (tree / "sub").mkdir(parents=True)
        (tree / "a.txt").write_text("a", encoding="utf-8")
        (tree / "sub" / "b.txt").write_text("b", encoding="utf-8")
        remote = str(self.root / "remote-tree")
        u = self.server.upload_file(tree, remote, token="tok-a", recursive=True)
        self.assertEqual(u.returncode, 0, u.stderr)
        back = self.root / "back-tree"
        d = self.server.download_file(remote, back, token="tok-a", recursive=True)
        self.assertEqual(d.returncode, 0, d.stderr)
        self.assertEqual((back / "a.txt").read_text(encoding="utf-8"), "a")
        self.assertEqual((back / "sub" / "b.txt").read_text(encoding="utf-8"), "b")

    def test_file_error_branches(self):
        tree = self.root / "dir2"
        tree.mkdir()
        self.assertNotEqual(
            self.server.upload_file(tree, str(self.root / "x"), token="tok-a").returncode, 0
        )
        self.assertNotEqual(
            self.server.download_file(str(self.root / "missing"), self.root / "m",
                                      token="tok-a").returncode,
            0,
        )


class TestBusinessMultiUserLocal(unittest.TestCase):
    """Concurrency + isolation across many local users."""

    def test_mixed_concurrency_retries_until_all_succeed(self):
        users = 20
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        registry = load_registry(registry_path())
        daemons = []
        try:
            for i in range(users):
                token = f"tok-{i:02d}"
                d = FakeDaemon(token)
                daemons.append(d)
                entry = _entry(token, d)
                entry.runtime.thread_pool_size = 8
                registry.register(f"u{i:02d}", entry)
            server = BusinessServer(wd)

            errors: list[str] = []
            lock = threading.Lock()
            tokens = [f"tok-{i:02d}" for i in range(users)]

            def skill_or_command(i: int) -> None:
                tok = tokens[i % users]
                try:
                    if i % 2 == 0:
                        r = server.execute_skill("whoami", token=tok)
                        while not r.ok and "exceeded" in str(r.errors):
                            time.sleep(0.01)
                            r = server.execute_skill("whoami", token=tok)
                        if r.output != tok:
                            with lock:
                                errors.append(f"route {tok}->{r.output}")
                    else:
                        c = server.run_command("echo ok", token=tok)
                        if c.returncode != 0:
                            with lock:
                                errors.append(f"cmd {tok} rc={c.returncode}")
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(f"{tok}: {exc}")

            def upload(i: int) -> None:
                tok = tokens[i % users]
                try:
                    src = Path(tempfile.mkdtemp()) / "f.bin"
                    src.write_bytes(tok.encode())
                    remote = f"{wd}/users/{tok}/f.bin"
                    u = server.upload_file(src, remote, token=tok)
                    if u.returncode != 0:
                        with lock:
                            errors.append(f"upload {tok}: {u.stderr}")
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(f"upload {tok}: {exc}")

            def download(i: int) -> None:
                tok = tokens[i % users]
                try:
                    remote = f"{wd}/users/{tok}/f.bin"
                    dst = Path(tempfile.mkdtemp()) / "g.bin"
                    d = server.download_file(remote, dst, token=tok)
                    if d.returncode != 0 or dst.read_bytes() != tok.encode():
                        with lock:
                            errors.append(f"download {tok}: rc={d.returncode} {d.stderr}")
                except Exception as exc:  # noqa: BLE001
                    with lock:
                        errors.append(f"download {tok}: {exc}")

            with ThreadPoolExecutor(max_workers=64) as pool:
                list(pool.map(skill_or_command, range(users * 6)))
            with ThreadPoolExecutor(max_workers=32) as pool:
                list(pool.map(upload, range(users)))
            with ThreadPoolExecutor(max_workers=32) as pool:
                list(pool.map(download, range(users)))
            self.assertEqual(errors, [])
        finally:
            for d in daemons:
                d.close()


if __name__ == "__main__":
    unittest.main()
