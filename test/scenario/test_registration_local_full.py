"""Scenario: full local six-step registration through a fake bottom daemon."""

import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer
from transport.register import RegistrationFlow, RegistrationRequest
from transport.registry import load_registry
from transport.runtime_paths import registry_path, set_working_dir


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
                    conn.sendall(b"\x15" + json.dumps({"error": "invalid token", "log": ""}).encode() + b"\x1e")
                else:
                    value = "2" if "1+1" in req.get("skill", "") else "3"
                    conn.sendall(b"\x02" + json.dumps({"value": value, "log": ""}).encode() + b"\x1e")
                conn.close()
            except Exception:
                conn.close()

    def close(self):
        self._sock.close()


class TestLocalRegistrationScenario(unittest.TestCase):
    def test_six_step_registration_then_business_use(self):
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        root = Path(tempfile.mkdtemp())
        daemon = FakeDaemon(token="tok-local")
        try:
            registry = load_registry(registry_path())
            flow = RegistrationFlow(registry)
            state = flow.apply(RegistrationRequest(
                user="alice", token="tok-local", local=True,
                daemon_port=daemon.port, scratch_root=str(root),
            ))
            self.assertEqual(state.stage, "deployed", str(state.errors))
            setup = Path(state.setup_path)
            self.assertTrue(setup.is_file())

            state = flow.verify()
            self.assertEqual(state.stage, "committed", str(state.errors) + str(state.report))
            self.assertTrue(state.report.command_ok)
            self.assertTrue(state.report.skill_ok)
            self.assertTrue(state.report.token_ok)

            server = BusinessServer(wd)
            r = server.execute_skill("1+1", token="tok-local")
            self.assertTrue(r.ok)
            self.assertEqual(r.output, "2")
            # wrong token must fail with unknown token before touching the daemon
            bad = server.execute_skill("1+1", token="tok-other")
            self.assertFalse(bad.ok)
        finally:
            daemon.close()


if __name__ == "__main__":
    unittest.main()
