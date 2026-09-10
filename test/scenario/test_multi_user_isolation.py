"""Scenario: two registered users are isolated by token at the business layer."""

import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.runtime_paths import registry_path, set_working_dir


class FakeDaemon:
    def __init__(self, token):
        self.token = token
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(5)
        self.port = self._sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

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
                    conn.sendall(b"\x15invalid token\x1e")
                else:
                    conn.sendall(b"\x02" + json.dumps({"value": self.token, "log": ""}).encode() + b"\x1e")
                conn.close()
            except Exception:
                conn.close()

    def close(self):
        self._sock.close()


class TestMultiUserIsolation(unittest.TestCase):
    def test_two_users_route_to_their_own_daemons(self):
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        da = FakeDaemon("tok-a")
        db = FakeDaemon("tok-b")
        try:
            reg = load_registry(registry_path())
            a = UserEntry(token="tok-a", mode="local")
            a.route.skill.local_port = da.port
            a.route.skill.daemon_port = da.port
            b = UserEntry(token="tok-b", mode="local")
            b.route.skill.local_port = db.port
            b.route.skill.daemon_port = db.port
            reg.register("alice", a)
            reg.register("bob", b)

            server = BusinessServer(wd)
            ra = server.execute_skill("hello", token="tok-a")
            rb = server.execute_skill("hello", token="tok-b")
            self.assertTrue(ra.ok)
            self.assertTrue(rb.ok)
            self.assertEqual(ra.output, "tok-a")
            self.assertEqual(rb.output, "tok-b")

            # each token has its own SkillClient
            self.assertIsNot(server._skill("tok-a"), server._skill("tok-b"))
        finally:
            da.close()
            db.close()

    def test_two_users_parallel_local_commands(self):
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        reg = load_registry(registry_path())
        reg.register("alice", UserEntry(token="tok-a", mode="local"))
        reg.register("bob", UserEntry(token="tok-b", mode="local"))
        server = BusinessServer(wd)

        results = {}
        def run(token, i):
            results[(token, i)] = server.run_command(
                f'"{sys.executable}" -c "import time; time.sleep(0.4)"', token=token
            ).returncode
        import time
        t0 = time.time()
        threads = [
            threading.Thread(target=run, args=("tok-a", 1)),
            threading.Thread(target=run, args=("tok-b", 2)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # different tokens each have their own pool; both run concurrently
        self.assertLess(time.time() - t0, 0.9)
        self.assertEqual(set(results.values()), {0})


if __name__ == "__main__":
    unittest.main()
