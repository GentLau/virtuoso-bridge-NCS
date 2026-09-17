"""Unit coverage for the HTTP stress wrapper around the middle layer."""

import base64
import hashlib
import json
import socket
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests
from server.stress_server import StressServer


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
                    conn.sendall(b"\x15" + json.dumps({"error": "invalid token", "log": ""}).encode() + b"\x1e")
                else:
                    value = "2" if "1+1" in req.get("skill", "") else "3"
                    conn.sendall(b"\x02" + json.dumps({"value": value, "log": ""}).encode() + b"\x1e")
                conn.close()
            except Exception:
                conn.close()

    def close(self):
        self._sock.close()


class TestStressServer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        daemon = FakeDaemon("tok-1")
        registry = load_registry(registry_path())
        entry = UserEntry(token="tok-1", mode="local")
        entry.roles.daemon.local_port = daemon.port
        entry.roles.daemon.daemon_port = daemon.port
        registry.register("u1", entry)
        middle = BusinessServer(cls.wd)
        cls.server = StressServer(("127.0.0.1", 0), middle)
        cls.port = cls.server.server_address[1]
        cls.daemon = daemon
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.daemon.close()

    def post(self, path, payload):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))

    def test_skill_command_and_404(self):
        status, body = self.post("/api/skill", {"token": "tok-1", "skill": "1+1"})
        self.assertEqual(status, 200)
        self.assertEqual(body["output"], "2")

        status, body = self.post("/api/command", {"token": "tok-1", "cmd": "echo ok"})
        self.assertEqual(status, 200)
        self.assertEqual(body["stdout"].strip(), "ok")

        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/nope", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=30)
        self.assertEqual(ctx.exception.code, 404)

    def test_upload_download_roundtrip(self):
        payload = b"stress-server-payload" * 32
        b64 = base64.b64encode(payload).decode()
        status, body = self.post(
            "/api/upload",
            {"token": "tok-1", "remote_path": f"{self.wd}/files/p.bin", "content_b64": b64},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["returncode"], 0)
        status, body = self.post(
            "/api/download",
            {"token": "tok-1", "remote_path": f"{self.wd}/files/p.bin"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(body["sha256"], hashlib.sha256(payload).hexdigest())

    def test_token_required(self):
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/skill", data=b"{}",
            headers={"Content-Type": "application/json"}, method="POST")
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            urllib.request.urlopen(req, timeout=30)
        self.assertEqual(ctx.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
