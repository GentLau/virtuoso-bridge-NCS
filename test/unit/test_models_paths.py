"""Small-module unit coverage: models, paths, SkillClient."""

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, SimulationResult, VirtuosoResult
from common import paths as runtime_paths
from common import remote_paths
from common.registry import load_registry
from common.paths import registry_path, override_work_dir_for_tests
from common.skill_client import STX, NAK, RS, SkillClient


class TestResultModels(unittest.TestCase):
    def test_virtuoso_result_properties_and_save(self):
        r = VirtuosoResult(status=ExecutionStatus.SUCCESS, output="3")
        self.assertTrue(r.ok)
        self.assertFalse(r.is_nil)
        r2 = VirtuosoResult(status=ExecutionStatus.SUCCESS, output="nil")
        self.assertTrue(r2.is_nil)
        path = Path(tempfile.mkdtemp()) / "r.json"
        r.save_json(path)
        self.assertTrue(path.is_file())
        self.assertIn("output", path.read_text(encoding="utf-8"))

    def test_simulation_result_save(self):
        sim = SimulationResult(status=ExecutionStatus.ERROR, errors=["x"])
        path = Path(tempfile.mkdtemp()) / "s.json"
        sim.save_json(path)
        self.assertIn("error", path.read_text(encoding="utf-8"))

    def test_command_result_namedtuple(self):
        c = CommandResult(0, "out", "err")
        self.assertEqual((c.returncode, c.stdout, c.stderr), (0, "out", "err"))


class TestRuntimePaths(unittest.TestCase):
    def test_explicit_working_dir(self):
        wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.assertEqual(runtime_paths.work_root(), wd)
        self.assertEqual(registry_path(), wd / "registry.json")
        self.assertTrue(runtime_paths.temp_dir().is_dir())
        self.assertTrue(runtime_paths.log_dir().is_dir())
        self.assertTrue(runtime_paths.artifact_dir().is_dir())
        self.assertEqual(runtime_paths.command_log_file(), wd / "log" / "commands.log")

    def test_windows_appdata_default(self):
        with mock.patch.object(runtime_paths.os, "name", "nt"), \
             mock.patch.object(runtime_paths.os, "environ", {"APPDATA": "C:/Users/u/AppData/Roaming"}):
            result = runtime_paths.default_work_dir()
        self.assertEqual(str(result).replace("\\", "/"), "C:/Users/u/AppData/Roaming/virtuoso_bridge")

    @unittest.skipIf(sys.platform == "win32", "POSIX path defaults require a POSIX host")
    def test_posix_platform_defaults(self):
        import os
        with mock.patch.object(runtime_paths.os, "name", "posix"), \
             mock.patch.object(runtime_paths.sys, "platform", "darwin"), \
             mock.patch.object(runtime_paths.Path, "home", return_value=Path("/Users/u")):
            self.assertEqual(runtime_paths.default_work_dir(), Path("/Users/u/Library/Application Support/virtuoso_bridge"))
        with mock.patch.object(runtime_paths.os, "name", "posix"), \
             mock.patch.object(runtime_paths.sys, "platform", "linux"), \
             mock.patch.object(runtime_paths.Path, "home", return_value=Path("/home/u")), \
             mock.patch.object(runtime_paths.os, "environ", {"XDG_CONFIG_HOME": "/etc/xdg"}):
            self.assertEqual(runtime_paths.default_work_dir(), Path("/etc/xdg/virtuoso_bridge"))


class TestRemotePaths(unittest.TestCase):
    def test_scratch_expansion(self):
        home = Path.home()
        self.assertEqual(remote_paths.scratch_root("~/.vb").replace("\\", "/"),
                         str(home / ".vb").replace("\\", "/"))
        self.assertEqual(remote_paths.scratch_root("/tmp/x/"), "/tmp/x")

    def test_path_tree(self):
        # scratch_root is now the single per-user work directory
        self.assertEqual(remote_paths.user_dir("alice", "/root/alice"), "/root/alice")
        self.assertIn("/root/alice/ramic", remote_paths.ramic_dir("alice", "/root/alice"))
        self.assertIn("ramic_bridge_daemon_27.py", remote_paths.daemon_path("alice", 2, "/root/alice"))
        self.assertIn("virtuoso_setup.il", remote_paths.setup_il_path("alice", "/root/alice"))
        self.assertIn("daemon_identity.txt", remote_paths.identity_path("alice", "/root/alice"))


class TestSkillClientSocketPaths(unittest.TestCase):
    def test_connection_refused_error(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        client = SkillClient(host="127.0.0.1", port=port, timeout=1.0)
        r = client.execute_skill("1+1")
        self.assertEqual(r.status, ExecutionStatus.ERROR)

    def test_success_roundtrip_with_fake_server(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]

        def serve():
            conn, _ = server.accept()
            data = b""
            while True:
                chunk = conn.recv(65536)
                if not chunk:
                    break
                data += chunk
            self.assertIn(b"token", data)
            conn.sendall((STX + json.dumps({"value": "2", "log": "ok"}) + RS).encode())
            conn.close()
            server.close()

        import threading
        t = threading.Thread(target=serve)
        t.start()
        client = SkillClient(host="127.0.0.1", port=port, timeout=5, token="tok")
        r = client.execute_skill("1+1")
        t.join(timeout=3)
        self.assertTrue(r.ok)
        self.assertEqual(r.output, "2")
        self.assertEqual(r.log, "ok")

    def test_parse_malformed_json_marker(self):
        r = SkillClient._parse_response(STX + "not-json" + RS, 0.1)
        self.assertEqual(r.status, ExecutionStatus.ERROR)
        self.assertIn("Malformed", r.errors[0])

    def test_parse_empty(self):
        r = SkillClient._parse_response("", 0.1)
        self.assertEqual(r.status, ExecutionStatus.ERROR)


class TestSmallEdgeCoverage(unittest.TestCase):
    def test_server_package_does_not_import_registration(self):
        import server
        with self.assertRaises(AttributeError):
            _ = server.main


if __name__ == "__main__":
    unittest.main()
