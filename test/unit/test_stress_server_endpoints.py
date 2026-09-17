"""stress_server 的 HTTP 端点契约（upload/download/composite/shutdown）。"""

import base64
import hashlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult
from server.stress_server import StressServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests


class FakeMiddle:
    def __init__(self, registry):
        self.registry = registry
        self.closed = 0

    def execute_skill(self, skill, timeout=None, *, token):
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=token)

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        return CommandResult(0, "out", "")

    def upload_file(self, local, remote, timeout=None, *, token, recursive=False):
        Path(remote).parent.mkdir(parents=True, exist_ok=True)
        Path(remote).write_bytes(Path(local).read_bytes())
        return CommandResult(0, str(remote), "")

    def download_file(self, remote, local, timeout=None, *, token, recursive=False):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        data = Path(remote).read_bytes() if Path(remote).exists() else b""
        Path(local).write_bytes(data)
        return CommandResult(0, str(local), "")

    def close(self):
        self.closed += 1


class TestStressServerEndpoints(unittest.TestCase):
    def setUp(self):
        wd = Path(tempfile.mkdtemp())
        override_work_dir_for_tests(wd)
        self.registry = load_registry(registry_path())
        entry = UserEntry(token="tok-s", mode="remote")
        entry.roles.daemon.host = "server-a"
        entry.roles.daemon.user = "u"
        entry.roles.daemon.root = str(wd / "root")
        self.registry.register("alice", entry)
        self.middle = FakeMiddle(self.registry)
        self.server = StressServer(("127.0.0.1", 0), self.middle)   # type: ignore[arg-type]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post(self, path, payload):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())

    def test_upload_and_download_round_trip(self):
        payload = b"hello-stress"
        st, body = self.post("/api/upload", {
            "token": "tok-s", "remote_path": str(Path(self.registry.entries()[0][1].roles.daemon.root) / "f.bin"),
            "content_b64": base64.b64encode(payload).decode(),
        })
        self.assertEqual((st, body["returncode"]), (200, 0))
        st, body = self.post("/api/download", {
            "token": "tok-s", "remote_path": str(Path(self.registry.entries()[0][1].roles.daemon.root) / "f.bin"),
        })
        self.assertEqual(st, 200)
        self.assertEqual(body["sha256"], hashlib.sha256(payload).hexdigest())

    def test_composite_chain(self):
        wd_root = Path(self.registry.entries()[0][1].roles.daemon.root)
        wd_root.mkdir(parents=True, exist_ok=True)
        st, body = self.post("/api/composite", {"token": "tok-s", "seq": "1", "delay_ms": 0})
        self.assertEqual(st, 200)
        self.assertTrue(body["ok"], body)

    def test_command_and_skill(self):
        st, body = self.post("/api/command", {"token": "tok-s", "cmd": "echo hi"})
        self.assertEqual((st, body["returncode"]), (200, 0))
        st, body = self.post("/api/skill", {"token": "tok-s", "skill": "1+1"})
        self.assertEqual((st, body["ok"]), (200, True))

    def test_shutdown_releases_middle(self):
        st, body = self.post("/api/shutdown", {})
        self.assertEqual((st, body["ok"]), (200, True))
        self.assertEqual(self.middle.closed, 1)


if __name__ == "__main__":
    unittest.main()
