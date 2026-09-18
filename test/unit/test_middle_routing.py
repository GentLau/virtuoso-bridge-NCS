"""BusinessServer routing tests with RemoteClient/SkillClient mocked."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult
from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests


def make_remote_entry(token="tok-1"):
    entry = UserEntry(token=token, mode="remote")
    entry.ssh.default.host = "daemon-a"
    entry.ssh.default.user = "alice"
    entry.roles.daemon.host = "daemon-a"
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    entry.roles.command.host = "daemon-a"
    entry.roles.command.user = "alice"
    entry.roles.daemon.expected_user = "alice"
    entry.roles.daemon.root = "/home/alice/.virtuoso-bridge"
    return entry


class FakeRemoteClient:
    instances = {}

    def __init__(self, entry, targets, user="alice"):
        self.entry = entry
        self.targets = targets
        self.user = user
        FakeRemoteClient.instances[entry.token] = self

    def ensure_tunnel(self, deadline=None):
        self.ensure_tunnel_called = True
        self.ensure_tunnel_deadline = deadline

    def run_command(self, cmd, timeout=None, parallel=False):
        return CommandResult(0, f"remote:{cmd}:{parallel}", "")

    def upload_file(self, local_path, remote_path, timeout=None, recursive=False):
        return CommandResult(0, str(local_path), "")

    def download_file(self, remote_path, local_path, timeout=None, recursive=False):
        return CommandResult(0, str(local_path), "")


class FakeSkillClient:
    instances = {}

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        FakeSkillClient.instances[kwargs["token"]] = self

    def execute_skill(
        self,
        skill_code,
        timeout=None,
        *,
        log_level=None,
        log_max_bytes=None,
    ):
        self.last_call = {
            "log_level": log_level,
            "log_max_bytes": log_max_bytes,
        }
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="2")


class TestBusinessServerRouting(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.reg = load_registry(registry_path())
        FakeRemoteClient.instances.clear()
        FakeSkillClient.instances.clear()

    def _server(self):
        return BusinessServer(self.wd)

    def test_execute_skill_remote_routes_and_tunnels(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient), \
             mock.patch("transport.middle.SkillClient", FakeSkillClient):
            r = server.execute_skill("1+1", token="tok-1")
        self.assertTrue(r.ok)
        self.assertEqual(r.output, "2")
        self.assertTrue(FakeRemoteClient.instances["tok-1"].ensure_tunnel_called)
        self.assertEqual(FakeSkillClient.instances["tok-1"].kwargs["log_level"], "all")

    def test_execute_skill_log_params_override_registry(self):
        entry = make_remote_entry()
        entry.cdslog.log_level = "error"
        entry.cdslog.log_max_bytes = 1024
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient), \
             mock.patch("transport.middle.SkillClient", FakeSkillClient):
            result = server.execute_skill(
                "1+1",
                token="tok-1",
                log_level="warning",
            )
        self.assertTrue(result.ok)
        client = FakeSkillClient.instances["tok-1"]
        self.assertEqual(
            client.last_call,
            {"log_level": "warning", "log_max_bytes": None},
        )
        self.assertEqual(client.kwargs["log_max_bytes"], 1024)

    def test_execute_skill_log_max_bytes_override(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient), \
             mock.patch("transport.middle.SkillClient", FakeSkillClient):
            result = server.execute_skill(
                "1+1",
                token="tok-1",
                log_max_bytes=2048,
            )
        self.assertTrue(result.ok)
        client = FakeSkillClient.instances["tok-1"]
        self.assertEqual(
            client.last_call,
            {"log_level": None, "log_max_bytes": 2048},
        )

    def test_execute_skill_unknown_token(self):
        server = self._server()
        r = server.execute_skill("1+1", token="nope")
        self.assertEqual(r.status, ExecutionStatus.ERROR)
        self.assertIn("invalid token", r.errors[0])

    def test_run_command_remote_passes_parallel(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient):
            serial = server.run_command("echo a", token="tok-1")
            parallel = server.run_command("echo b", token="tok-1", parallel=True)
        self.assertEqual(serial.stdout, "remote:echo a:False")
        self.assertEqual(parallel.stdout, "remote:echo b:True")

    def test_upload_download_remote(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient):
            up = server.upload_file(Path("a.txt"), "/remote/a.txt", token="tok-1")
            down = server.download_file("/remote/a.txt", Path("b.txt"), token="tok-1")
        self.assertEqual(up.returncode, 0)
        self.assertEqual(down.returncode, 0)

    def test_remote_clients_cached_per_token(self):
        entry = make_remote_entry()
        self.reg.register("alice", entry)
        server = self._server()
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient):
            server.run_command("echo a", token="tok-1")
            server.run_command("echo b", token="tok-1")
        self.assertEqual(len(FakeRemoteClient.instances), 1)

    def test_thread_pool_exceeded_for_remote(self):
        entry = make_remote_entry()
        entry.runtime.thread_pool_size = 1
        self.reg.register("alice", entry)
        server = self._server()
        server._capacity["tok-1"] = mock.Mock()
        server._capacity["tok-1"].acquire.return_value = False
        with mock.patch("transport.middle.RemoteClient", FakeRemoteClient):
            r = server.run_command("echo x", token="tok-1")
        self.assertEqual(r.returncode, 1)
        self.assertIn("thread pool exceeded", r.stderr)


class TestMiddleErrorAndLocalPaths(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.server = BusinessServer(self.wd)

    def test_run_command_unknown_token(self):
        r = self.server.run_command("echo x", token="ghost")
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid token", r.stderr)

    def test_upload_unknown_token(self):
        r = self.server.upload_file(Path("a.txt"), "/x/a.txt", token="ghost")
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid token", r.stderr)

    def test_download_unknown_token(self):
        r = self.server.download_file("/x/a.txt", Path("b.txt"), token="ghost")
        self.assertEqual(r.returncode, 1)
        self.assertIn("invalid token", r.stderr)

    def test_local_command_timeout(self):
        r = self.server._local_command('"{}" -c "import time; time.sleep(5)"'.format(sys.executable), 0.1)
        self.assertEqual(r.returncode, 124)
        self.assertIn("timed out", r.stderr)

    def test_local_upload_missing_source(self):
        r = self.server._local_upload(Path("missing.txt"), str(Path(self.wd) / "dst.txt"), recursive=False)
        self.assertEqual(r.returncode, 1)

    def test_local_download_missing_source(self):
        r = self.server._local_download(str(Path(self.wd) / "missing"), Path(self.wd) / "out.txt", recursive=False)
        self.assertEqual(r.returncode, 1)

    def test_local_upload_directory_requires_recursive(self):
        src = Path(self.wd) / "tree"
        src.mkdir()
        r = self.server._local_upload(src, str(Path(self.wd) / "dst"), recursive=False)
        self.assertEqual(r.returncode, 1)
        self.assertIn("recursive=True", r.stderr)

    def test_local_upload_recursive(self):
        src = Path(self.wd) / "tree"
        (src / "sub").mkdir(parents=True)
        (src / "sub" / "f.txt").write_text("x", encoding="utf-8")
        dst = Path(self.wd) / "copy"
        r = self.server._local_upload(src, str(dst), recursive=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual((dst / "sub" / "f.txt").read_text(encoding="utf-8"), "x")

    def test_local_download_recursive(self):
        src = Path(self.wd) / "tree"
        (src / "sub").mkdir(parents=True)
        (src / "sub" / "f.txt").write_text("x", encoding="utf-8")
        dst = Path(self.wd) / "copy"
        r = self.server._local_download(str(src), dst, recursive=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual((dst / "sub" / "f.txt").read_text(encoding="utf-8"), "x")


if __name__ == "__main__":
    unittest.main()
