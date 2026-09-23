"""Integration tests: fake bottom daemon + local BusinessServer.

The fake daemon implements the middle<->bottom wire protocol (token + JSON +
STX/NAK/RS) without Virtuoso, so Skill routing can be verified end to end.
"""

from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import ExecutionStatus
from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests

STX = "\x02"
NAK = "\x15"
RS = "\x1e"


class FakeDaemon:
    def __init__(self, token, port=0):
        self.token = token
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", port))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
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
                if req.get("token") != self.token:
                    conn.sendall((NAK + json.dumps({"error": "invalid token", "log": ""}) + RS).encode())
                    conn.close()
                    continue
                value = "2" if "1+1" in req.get("skill", "") else "3"
                log = "\\o VB-BEGIN\n\\e fake-error-line\n\\o VB-END\n"
                if req.get("log_level") == "off":
                    log = ""
                conn.sendall((STX + json.dumps({"value": value, "log": log}) + RS).encode())
                conn.close()
            except Exception:
                conn.close()

    def close(self):
        self._sock.close()


class TestIntegration(unittest.TestCase):
    def test_skill_end_to_end_fake_daemon(self):
        wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        fake = FakeDaemon(token="tok-1")
        try:
            reg = load_registry(registry_path())
            entry = UserEntry(token="tok-1", mode="local")
            entry.roles.daemon.local_port = fake.port
            entry.roles.daemon.daemon_port = fake.port
            reg.register("alice", entry)

            server = BusinessServer(wd)
            r = server.execute_skill("1+1", token="tok-1")
            self.assertTrue(r.ok)
            self.assertEqual(r.output, "2")
            self.assertIn("fake-error-line", r.log)

            r2 = server.execute_skill("1+1", token="wrong")
            self.assertEqual(r2.status, ExecutionStatus.ERROR)
            self.assertIn("invalid token", r2.errors[0])
        finally:
            fake.close()

    def test_thread_capacity(self):
        import os
        wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="local")
        entry.runtime.thread_pool_size = 1
        reg.register("alice", entry)

        server = BusinessServer(wd)
        slow = f'"{sys.executable}" -c "import time; time.sleep(0.5)"'
        holder = threading.Thread(target=lambda: server.run_command(slow, token="tok-1"))
        holder.start()
        time.sleep(0.1)  # let the holder take the only slot
        r = server.run_command("echo x", token="tok-1")
        self.assertIn("thread pool exceeded", r.stderr)
        holder.join()

    def test_parallel_local(self):
        wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="local")
        entry.runtime.thread_pool_size = 4
        reg.register("alice", entry)

        server = BusinessServer(wd)
        results = {}
        cmd = f'"{sys.executable}" -c "import time; time.sleep(0.5)"'

        def run(i):
            results[i] = server.run_command(cmd, token="tok-1", parallel=True).returncode

        # Same-machine serial baseline: a hard-coded "< 1s" is flaky on a loaded
        # CI box, while the *overlap* contract (two parallel calls take
        # materially less than two serial ones) is stable.
        serial_start = time.time()
        for _ in range(2):
            server.run_command(cmd, token="tok-1")
        serial = time.time() - serial_start

        start = time.time()
        threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start
        self.assertLess(
            elapsed, serial - 0.3,
            f"parallel={elapsed:.3f}s serial={serial:.3f}s: calls did not overlap",
        )
        self.assertEqual(set(results.values()), {0})


if __name__ == "__main__":
    unittest.main()
