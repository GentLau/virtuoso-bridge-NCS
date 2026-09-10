"""Small-module unit coverage: models, paths, legacy adapters, SkillClient."""

import json
import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, SimulationResult, VirtuosoResult
from transport import remote_paths, runtime_paths
from transport.legacy_env import import_user, load_legacy_env
from transport.registry import load_registry
from transport.runtime_paths import registry_path, set_working_dir
from transport.skill_client import STX, NAK, RS, SkillClient


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
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        self.assertEqual(runtime_paths.working_dir(), wd)
        self.assertEqual(registry_path(), wd / "registry.json")
        self.assertTrue(runtime_paths.temp_dir().is_dir())
        self.assertTrue(runtime_paths.log_dir().is_dir())
        self.assertTrue(runtime_paths.artifact_dir().is_dir())
        self.assertEqual(runtime_paths.command_log_file(), wd / "log" / "commands.log")

    def test_windows_appdata_default(self):
        with mock.patch.object(runtime_paths.os, "name", "nt"), \
             mock.patch.object(runtime_paths.os, "environ", {"APPDATA": "C:/Users/u/AppData/Roaming"}):
            result = runtime_paths.default_working_dir()
        self.assertEqual(str(result).replace("\\", "/"), "C:/Users/u/AppData/Roaming/virtuoso_bridge")

    @unittest.skipIf(sys.platform == "win32", "POSIX path defaults require a POSIX host")
    def test_posix_platform_defaults(self):
        import os
        with mock.patch.object(runtime_paths.os, "name", "posix"), \
             mock.patch.object(runtime_paths.sys, "platform", "darwin"), \
             mock.patch.object(runtime_paths.Path, "home", return_value=Path("/Users/u")):
            self.assertEqual(runtime_paths.default_working_dir(), Path("/Users/u/Library/Application Support/virtuoso_bridge"))
        with mock.patch.object(runtime_paths.os, "name", "posix"), \
             mock.patch.object(runtime_paths.sys, "platform", "linux"), \
             mock.patch.object(runtime_paths.Path, "home", return_value=Path("/home/u")), \
             mock.patch.object(runtime_paths.os, "environ", {"XDG_CONFIG_HOME": "/etc/xdg"}):
            self.assertEqual(runtime_paths.default_working_dir(), Path("/etc/xdg/virtuoso_bridge"))


class TestRemotePaths(unittest.TestCase):
    def test_scratch_expansion(self):
        home = Path.home()
        self.assertEqual(remote_paths.scratch_root("~/.vb").replace("\\", "/"),
                         str(home / ".vb").replace("\\", "/"))
        self.assertEqual(remote_paths.scratch_root("/tmp/x/"), "/tmp/x")

    def test_path_tree(self):
        self.assertEqual(remote_paths.token_dir("tok", "/root"), "/root/tok")
        self.assertIn("/tok/ramic", remote_paths.ramic_dir("tok", "/root"))
        self.assertIn("ramic_bridge_daemon_27.py", remote_paths.daemon_path("tok", 2, "/root"))
        self.assertIn("virtuoso_setup.il", remote_paths.setup_il_path("tok", "/root"))
        self.assertIn("daemon_identity.txt", remote_paths.identity_path("tok", "/root"))


class TestLegacyAdapters(unittest.TestCase):
    def setUp(self):
        import transport.legacy_env as le
        le._cache = None

    def test_load_env_cache_and_ignore_comments(self):
        p = Path(tempfile.mkdtemp()) / ".env"
        p.write_text("# c\nVB_REMOTE_HOST=server\nVB_X = bad", encoding="utf-8")
        env = load_legacy_env(p)
        self.assertEqual(env["VB_REMOTE_HOST"], "server")
        self.assertIs(load_legacy_env(p), env)  # cached

    def test_import_requires_host(self):
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        reg = load_registry(registry_path())
        p = Path(tempfile.mkdtemp()) / ".env"
        p.write_text("VB_REMOTE_USER=alice\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            import_user(reg, user="alice", token="t", env_path=p)

    def test_import_profile_suffix(self):
        wd = set_working_dir(Path(tempfile.mkdtemp()))
        reg = load_registry(registry_path())
        p = Path(tempfile.mkdtemp()) / ".env"
        p.write_text("VB_REMOTE_HOST_gpu1=server-b\nVB_REMOTE_USER_gpu1=bob\n", encoding="utf-8")
        entry = import_user(reg, user="bob", token="t", env_path=p, profile="gpu1")
        self.assertEqual(entry.route.skill.daemon_host, "server-b")
        self.assertEqual(entry.expected.daemon_user, "bob")


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
    def test_legacy_profile_from_env(self):
        import os
        from transport.legacy_profile import resolve_legacy_profile
        old = os.environ.get("VB_PROFILE")
        os.environ["VB_PROFILE"] = "gpu1"
        try:
            self.assertEqual(resolve_legacy_profile(None), "gpu1")
            self.assertEqual(resolve_legacy_profile("explicit"), "explicit")
        finally:
            if old is None:
                os.environ.pop("VB_PROFILE", None)
            else:
                os.environ["VB_PROFILE"] = old

    def test_server_lazy_main_and_unknown_attr(self):
        import server
        self.assertTrue(callable(server.main))
        with self.assertRaises(AttributeError):
            _ = server.no_such_thing


if __name__ == "__main__":
    unittest.main()
