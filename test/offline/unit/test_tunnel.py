"""RemoteClient / SSHRunner integration tests.

These guard the full-transport wiring restored from the legacy code:
OpenSSH + Paramiko backends, role runners, the parallel channel, and the
tunnel signature (local_port -> remote_port keyword).
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult
from common.registry import UserEntry
from transport.remote_roles import resolve
from common.paths import override_work_dir_for_tests
from transport.tunnel import RemoteClient


class FakeRunner:
    instances: list["FakeRunner"] = []

    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.host = kwargs.get("host")
        self.calls: list[tuple] = []
        FakeRunner.instances.append(self)

    @property
    def is_tunnel_alive(self) -> bool:
        return False

    def start_port_forward(self, *args, **kwargs):
        self.calls.append(("start_port_forward", args, kwargs))

    def stop_port_forward(self):
        self.calls.append(("stop_port_forward", (), {}))

    def close(self):
        self.calls.append(("close", (), {}))

    def run_command(self, *args, **kwargs) -> CommandResult:
        self.calls.append(("run_command", args, kwargs))
        return CommandResult(0, "", "")

    def upload_text(self, *args, **kwargs) -> CommandResult:
        self.calls.append(("upload_text", args, kwargs))
        return CommandResult(0, "", "")

    def upload(self, *args, **kwargs) -> CommandResult:
        self.calls.append(("upload", args, kwargs))
        return CommandResult(0, "", "")

    def download(self, *args, **kwargs) -> CommandResult:
        self.calls.append(("download", args, kwargs))
        return CommandResult(0, "", "")


def make_entry(*, skill_host="daemon-a", command_host="daemon-a", file_host="daemon-a") -> UserEntry:
    entry = UserEntry(token="tok-1", mode="remote")
    entry.ssh.default.host = skill_host
    entry.ssh.default.user = "alice"
    entry.roles.daemon.host = skill_host
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    entry.roles.command.host = command_host
    entry.roles.command.user = None
    entry.roles.file.host = file_host
    entry.roles.daemon.expected_user = "alice"
    entry.roles.daemon.python = "python3"
    entry.roles.daemon.root = "/home/alice/.virtuoso-bridge"
    return entry


class TestRemoteClientTunnel(unittest.TestCase):
    def setUp(self) -> None:
        override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        FakeRunner.instances.clear()

    def test_ensure_tunnel_passes_remote_port_kwarg(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry()
            rc = RemoteClient(entry, resolve(entry), "alice")
            rc.ensure_tunnel()
        skill = FakeRunner.instances[0]
        self.assertEqual(skill.host, "daemon-a")
        calls = [c for c in skill.calls if c[0] == "start_port_forward"]
        self.assertEqual(len(calls), 1)
        _, args, kwargs = calls[0]
        self.assertEqual(args, (65082,))
        self.assertEqual(kwargs.get("remote_port"), 65081)
        self.assertIn("deadline", kwargs)

    def test_single_host_reuses_one_runner(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry()
            rc = RemoteClient(entry, resolve(entry), "alice")
            a, b, c = rc.skill_runner, rc.command_runner, rc.file_runner
        self.assertIs(a, b)
        self.assertIs(a, c)
        self.assertEqual(len(FakeRunner.instances), 1)

    def test_split_host_gets_separate_runners(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry(skill_host="d", command_host="c", file_host="f")
            rc = RemoteClient(entry, resolve(entry), "alice")
            s, cmd, f = rc.skill_runner, rc.command_runner, rc.file_runner
        self.assertIsNot(s, cmd)
        self.assertIsNot(cmd, f)
        self.assertIsNot(s, f)
        self.assertEqual(len(FakeRunner.instances), 3)

    def test_parallel_openssh_uses_fresh_nonpersistent_runner(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry()
            entry.ssh.backend = "openssh"   # covers the non-multiplexed path
            rc = RemoteClient(entry, resolve(entry), "alice")
            serial = rc.command_runner
            parallel = rc._one_shot_runner(rc.targets.command)
        self.assertIsNot(serial, parallel)
        self.assertFalse(parallel.kwargs["persistent_shell"])
        self.assertEqual(parallel.host, "daemon-a")

    def test_parallel_paramiko_reuses_session_backend(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry()
            entry.ssh.backend = "paramiko"
            rc = RemoteClient(entry, resolve(entry), "alice")
            serial = rc.command_runner
            parallel = rc._one_shot_runner(rc.targets.command)
        self.assertIs(serial, parallel)

    def test_local_deploy_uses_no_ssh(self) -> None:
        entry = UserEntry(token="tok-1", mode="local")
        entry.roles.daemon.daemon_port = 65432
        entry.roles.daemon.local_port = 65432
        entry.roles.daemon.python = "python3"
        root = Path(tempfile.mkdtemp(prefix="vb-"))
        entry.roles.daemon.root = str(root)
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            rc = RemoteClient(entry, resolve(entry), "alice")
            setup = rc.deploy(python_major=3)
        self.assertEqual(FakeRunner.instances, [])
        self.assertTrue(Path(setup).is_file())
        self.assertTrue((root / "ramic" / "ramic_bridge_daemon_3.py").is_file())
        self.assertTrue((root / "ramic" / "ramic_bridge_daemon_27.py").is_file())
        self.assertTrue((root / "ramic" / "ramic_bridge.il").is_file())


class TestSSHRunnerParamikoBackend(unittest.TestCase):
    def setUp(self) -> None:
        override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))

    def test_paramiko_backend_constructs(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.skipTest("paramiko not installed")
        from common.ssh import SSHRunner

        runner = SSHRunner("127.0.0.1", user="u", backend="paramiko", connect_timeout=5)
        try:
            self.assertEqual(runner.backend, "paramiko")
            self.assertIsNotNone(runner._paramiko_backend)
        finally:
            runner.close()

    def test_unsupported_backend_rejected(self) -> None:
        from common.ssh import SSHRunner

        with self.assertRaises(ValueError):
            SSHRunner("127.0.0.1", backend="bogus")


if __name__ == "__main__":
    unittest.main()
