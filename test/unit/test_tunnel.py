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

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult
from transport.registry import UserEntry
from transport.remote_roles import resolve
from transport.runtime_paths import set_working_dir
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
    entry.route.skill.daemon_host = skill_host
    entry.route.skill.daemon_port = 65081
    entry.route.skill.local_port = 65082
    entry.route.command.host = command_host
    entry.route.command.user = None
    entry.route.file.host = file_host
    entry.expected.daemon_user = "alice"
    entry.expected.remote_python = "python3"
    entry.deploy.scratch_root = "/home/alice/.virtuoso-bridge"
    return entry


class TestRemoteClientTunnel(unittest.TestCase):
    def setUp(self) -> None:
        set_working_dir(Path(tempfile.mkdtemp()))
        FakeRunner.instances.clear()

    def test_ensure_tunnel_passes_remote_port_kwarg(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry()
            rc = RemoteClient(entry, resolve(entry))
            rc.ensure_tunnel()
        skill = FakeRunner.instances[0]
        self.assertEqual(skill.host, "daemon-a")
        calls = [c for c in skill.calls if c[0] == "start_port_forward"]
        self.assertEqual(len(calls), 1)
        _, args, kwargs = calls[0]
        self.assertEqual(args, (65082,))
        self.assertEqual(kwargs, {"remote_port": 65081})

    def test_single_host_reuses_one_runner(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry()
            rc = RemoteClient(entry, resolve(entry))
            a, b, c = rc.skill_runner, rc.command_runner, rc.file_runner
        self.assertIs(a, b)
        self.assertIs(a, c)
        self.assertEqual(len(FakeRunner.instances), 1)

    def test_split_host_gets_separate_runners(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry(skill_host="d", command_host="c", file_host="f")
            rc = RemoteClient(entry, resolve(entry))
            s, cmd, f = rc.skill_runner, rc.command_runner, rc.file_runner
        self.assertIsNot(s, cmd)
        self.assertIsNot(cmd, f)
        self.assertIsNot(s, f)
        self.assertEqual(len(FakeRunner.instances), 3)

    def test_parallel_openssh_uses_fresh_nonpersistent_runner(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry()
            rc = RemoteClient(entry, resolve(entry))
            serial = rc.command_runner
            parallel = rc._parallel_command_runner()
        self.assertIsNot(serial, parallel)
        self.assertFalse(parallel.kwargs["persistent_shell"])
        self.assertEqual(parallel.host, "daemon-a")

    def test_parallel_paramiko_reuses_session_backend(self) -> None:
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            entry = make_entry()
            entry.ssh.backend = "paramiko"
            rc = RemoteClient(entry, resolve(entry))
            serial = rc.command_runner
            parallel = rc._parallel_command_runner()
        self.assertIs(serial, parallel)

    def test_local_deploy_uses_no_ssh(self) -> None:
        entry = UserEntry(token="tok-1", mode="local")
        entry.route.skill.daemon_port = 65432
        entry.route.skill.local_port = 65432
        entry.expected.remote_python = "python3"
        root = Path(tempfile.mkdtemp())
        entry.deploy.scratch_root = str(root)
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            rc = RemoteClient(entry, resolve(entry))
            setup = rc.deploy(python_major=3)
        self.assertEqual(FakeRunner.instances, [])
        self.assertTrue(Path(setup).is_file())
        self.assertTrue((root / "tok-1" / "ramic" / "ramic_bridge_daemon_3.py").is_file())
        self.assertTrue((root / "tok-1" / "ramic" / "ramic_bridge.il").is_file())


class TestSSHRunnerParamikoBackend(unittest.TestCase):
    def setUp(self) -> None:
        set_working_dir(Path(tempfile.mkdtemp()))

    def test_paramiko_backend_constructs(self) -> None:
        try:
            import paramiko  # noqa: F401
        except ImportError:
            self.skipTest("paramiko not installed")
        from transport.ssh import SSHRunner

        runner = SSHRunner("127.0.0.1", user="u", backend="paramiko", connect_timeout=5)
        try:
            self.assertEqual(runner.backend, "paramiko")
            self.assertIsNotNone(runner._paramiko_backend)
        finally:
            runner.close()

    def test_unsupported_backend_rejected(self) -> None:
        from transport.ssh import SSHRunner

        with self.assertRaises(ValueError):
            SSHRunner("127.0.0.1", backend="bogus")


if __name__ == "__main__":
    unittest.main()
