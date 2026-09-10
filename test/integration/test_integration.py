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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import ExecutionStatus
from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.runtime_paths import registry_path, set_working_dir

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
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        fake = FakeDaemon(token="tok-1")
        try:
            reg = load_registry(registry_path())
            entry = UserEntry(token="tok-1", mode="local")
            entry.route.skill.local_port = fake.port
            entry.route.skill.daemon_port = fake.port
            reg.register("alice", entry)

            server = BusinessServer(wd)
            r = server.execute_skill("1+1", token="tok-1")
            self.assertTrue(r.ok)
            self.assertEqual(r.output, "2")
            self.assertIn("fake-error-line", r.log)

            r2 = server.execute_skill("1+1", token="wrong")
            self.assertEqual(r2.status, ExecutionStatus.ERROR)
            self.assertIn("unknown token", r2.errors[0])
        finally:
            fake.close()

    def test_thread_capacity(self):
        import os
        wd = set_working_dir(Path(tempfile.mkdtemp()))
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
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        reg = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="local")
        entry.runtime.thread_pool_size = 4
        reg.register("alice", entry)

        server = BusinessServer(wd)
        results = {}

        def run(i):
            cmd = f'"{sys.executable}" -c "import time; time.sleep(0.5)"'
            results[i] = server.run_command(cmd, token="tok-1", parallel=True).returncode

        start = time.time()
        threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start
        # parallel calls must overlap (each ~0.5s, both finish in < 1s)
        self.assertLess(elapsed, 1.0)
        self.assertEqual(set(results.values()), {0})


if __name__ == "__main__":
    unittest.main()
