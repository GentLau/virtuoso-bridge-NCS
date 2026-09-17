"""五接口错误契约（spec 三层架构 §4.4）——用假 RemoteClient 覆盖映射分支。"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, VirtuosoResult, ExecutionStatus
from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.remote_paths import RemotePathError
from common.paths import registry_path, override_work_dir_for_tests
from common.ssh import UnknownEffectError


class FakeRemote:
    """只暴露 BusinessServer 用到的那几个入口。"""

    def __init__(self):
        self.error = None
        self.parallel_seen = None

    def _raise(self):
        if self.error is not None:
            raise self.error
        return None

    def ensure_tunnel(self, deadline=None):
        self._raise()

    def run_command(self, cmd, timeout=None, parallel=False):
        self.parallel_seen = parallel
        self._raise()
        return CommandResult(0, "ok", "")

    def run_one_shot(self, role_name, cmd, timeout=None):
        self._raise()
        return CommandResult(0, role_name, "")

    def upload_file(self, local, remote, timeout=None, recursive=False):
        self._raise()
        return CommandResult(0, "", "")

    def download_file(self, remote, local, timeout=None, recursive=False):
        self._raise()
        return CommandResult(0, "", "")

    def close(self):
        return None


def remote_entry():
    entry = UserEntry(token="tok-c", mode="remote")
    entry.ssh.default.host = "daemon-a"
    entry.ssh.default.user = "alice"
    for name in ("gui", "daemon", "command", "file", "spectre"):
        role = getattr(entry.roles, name)
        role.host = "server-a"
        role.user = "alice"
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    return entry


class MiddleContractBase(unittest.TestCase):
    def setUp(self):
        wd = Path(tempfile.mkdtemp())
        override_work_dir_for_tests(wd)
        registry = load_registry(registry_path())
        registry.register("alice", remote_entry())
        self.server = BusinessServer(wd)
        self.fake = FakeRemote()
        fakes = {"tok-c": self.fake}
        self._patched = mock.patch.object(
            BusinessServer, "_remote", lambda server, token: fakes[token]
        )
        self.fakes = fakes
        self._patched.start()
        self.addCleanup(self._patched.stop)
        self.addCleanup(self.server.close)

    def assert_kind(self, result, kind, rc=None):
        self.assertEqual(result.kind, kind, result)
        if rc is not None:
            self.assertEqual(result.returncode, rc)


class TestCommandContracts(MiddleContractBase):
    def test_transport_error_maps_to_kind_transport(self):
        self.fake.error = RuntimeError("ssh blew up")
        r = self.server.run_command("echo hi", token="tok-c")
        self.assert_kind(r, "transport", 255)
        self.assertIn("VB-TRANSPORT:", r.stderr)

    def test_timeout_maps_to_124(self):
        self.fake.error = subprocess.TimeoutExpired("cmd", 30)
        r = self.server.run_command("sleep 99", token="tok-c")
        self.assert_kind(r, "timeout", 124)

    def test_unknown_effect_is_not_replayed(self):
        self.fake.error = UnknownEffectError("shell died mid-command")
        r = self.server.run_command("do-once", token="tok-c")
        self.assert_kind(r, "unknown-effect", 255)
        self.assertIn("VB-UNKNOWN-EFFECT:", r.stderr)

    def test_path_error_prefix(self):
        self.fake.error = RemotePathError("cannot resolve remote $HOME")
        r = self.server.run_command("echo hi", token="tok-c")
        self.assert_kind(r, "path", 1)
        self.assertIn("VB-PATH-NOT-VISIBLE:", r.stderr)

    def test_invalid_token(self):
        r = self.server.run_command("echo hi", token="nope")
        self.assert_kind(r, "invalid-token", 1)
        self.assertEqual(r.stderr, "invalid token")

    def test_parallel_flag_is_forwarded(self):
        r = self.server.run_command("echo hi", token="tok-c", parallel=True)
        self.assertEqual(r.returncode, 0)
        self.assertTrue(self.fake.parallel_seen)


class TestFileAndRoleContracts(MiddleContractBase):
    def test_upload_transport_error(self):
        self.fake.error = RuntimeError("scp failed")
        src = Path(tempfile.mkdtemp()) / "f.bin"
        src.write_bytes(b"x")
        r = self.server.upload_file(src, "f.bin", token="tok-c")
        self.assert_kind(r, "transport", 255)

    def test_download_path_error(self):
        self.fake.error = RemotePathError("no such file")
        dst = Path(tempfile.mkdtemp()) / "out.bin"
        r = self.server.download_file("missing.bin", dst, token="tok-c")
        self.assert_kind(r, "path", 1)

    def test_gui_and_spectre_one_shot(self):
        r1 = self.server.run_gui_command("xdotool key Escape", token="tok-c")
        r2 = self.server.run_spectre_command("spectre -v", token="tok-c")
        self.assertEqual((r1.kind, r2.kind), ("command", "command"))
        self.assertEqual(r1.stdout, "gui")
        self.assertEqual(r2.stdout, "spectre")

    def test_gui_transport_error(self):
        self.fake.error = RuntimeError("no ssh")
        r = self.server.run_gui_command("xdotool key Escape", token="tok-c")
        self.assert_kind(r, "transport", 255)


class TestSkillContracts(MiddleContractBase):
    def test_skill_transport_error_reports_daemon_connection(self):
        self.fake.error = RuntimeError("tunnel failed")
        r = self.server.execute_skill("1+1", token="tok-c")
        self.assertEqual(r.status, ExecutionStatus.ERROR)
        self.assertTrue(any("Daemon connection failed" in e for e in r.errors), r.errors)

    def test_skill_path_error(self):
        self.fake.error = RemotePathError("bad root")
        r = self.server.execute_skill("1+1", token="tok-c")
        self.assertTrue(any("VB-PATH-NOT-VISIBLE" in e for e in r.errors), r.errors)

    def test_skill_invalid_token(self):
        r = self.server.execute_skill("1+1", token="nope")
        self.assertEqual(r.errors, ["invalid token"])


if __name__ == "__main__":
    unittest.main()
