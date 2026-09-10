"""Remote probe helpers: python detection and port allocation."""

import socket
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult
from transport.register.probe import allocate_remote_port, detect_remote_python, port_free_on_remote
from transport.runtime_paths import set_working_dir


class FakeRunner:
    def __init__(self, responses: list[CommandResult]):
        self.responses = list(responses)
        self.commands: list[str] = []

    def run_command(self, cmd: str, timeout=None) -> CommandResult:
        self.commands.append(cmd)
        if self.responses:
            return self.responses.pop(0)
        return CommandResult(0, "", "")


class TestProbeHelpers(unittest.TestCase):
    def setUp(self) -> None:
        set_working_dir(Path(tempfile.mkdtemp()))

    def test_local_helpers(self) -> None:
        from transport.register import probe as probes
        self.assertTrue(probes.local_hostname())
        self.assertTrue(probes.local_user())
        cmd, major = probes.local_python()
        self.assertTrue(cmd)
        self.assertIn(major, (2, 3))
        s = socket.socket()
        s.bind(("0.0.0.0", 0))
        port = s.getsockname()[1]
        self.assertFalse(probes.local_port_free(port))
        s.close()
        root = Path(tempfile.mkdtemp())
        self.assertTrue(probes.local_path_writable(root))
        file_path = root / "not_a_dir"
        file_path.write_text("x", encoding="utf-8")
        self.assertFalse(probes.local_path_writable(file_path))

    def test_remote_probes_with_fake_runner(self) -> None:
        from transport.register import probe as probes
        runner = FakeRunner([
            CommandResult(0, "host-a.example.com\n", ""),   # hostname -f
            CommandResult(0, "alice\n", ""),               # whoami
            CommandResult(0, "uid=1000(alice)\n", ""),     # id alice
            CommandResult(0, "", ""),                       # mkdir + test -w
        ])
        self.assertEqual(probes.remote_hostname(runner), "host-a.example.com")
        self.assertEqual(probes.remote_user(runner), "alice")
        self.assertTrue(probes.remote_user_exists(runner, "alice"))
        self.assertTrue(probes.remote_path_writable(runner, "/home/alice/.vb"))
        self.assertEqual(probes.remote_user_exists(runner, "alice"), True)

    def test_host_key_fingerprint_uses_known_hosts(self) -> None:
        from transport.register import probe as probes
        with mock.patch.object(probes.subprocess, "run", side_effect=[
            mock.Mock(stdout="hostname server-a\n", returncode=0),          # ssh -G
            mock.Mock(stdout="# Host server-a found: line 1\nserver-a ssh-ed25519 AAAAB3NzaC1yc2EAAAADAQABAAAB\n", returncode=0),  # ssh-keygen -F
            mock.Mock(stdout="256 SHA256:abcdef server-a (ED25519)\n", returncode=0),  # ssh-keygen -lf
        ]) as run:
            fp = probes.host_key_fingerprint("server-a")
        self.assertEqual(fp, "SHA256:abcdef")
        self.assertEqual(run.call_count, 3)
        self.assertFalse(Path("keys.tmp").exists())

    def test_detect_cadence_python3(self) -> None:
        runner = FakeRunner([CommandResult(0, "CMD:/opt/x/python3 Python 3.9.5\n", "")])
        self.assertEqual(detect_remote_python(runner), ("/opt/x/python3", 3))

    def test_detect_python27(self) -> None:
        runner = FakeRunner([CommandResult(0, "CMD:/opt/x/python2.7 Python 2.7.18\n", "")])
        self.assertEqual(detect_remote_python(runner), ("/opt/x/python2.7", 2))

    def test_detect_falls_back_to_path(self) -> None:
        runner = FakeRunner([
            CommandResult(0, "", ""),                 # one-shot found nothing
            CommandResult(1, "", "no python3"),       # python3 missing
            CommandResult(0, "Python 2.7.18", ""),    # python works
        ])
        self.assertEqual(detect_remote_python(runner), ("python", 2))

    def test_allocate_port_batch(self) -> None:
        runner = FakeRunner([CommandResult(0, "65083\n", "")])
        self.assertEqual(allocate_remote_port(runner, "python3"), 65083)

    def test_allocate_port_falls_back_to_single_checks(self) -> None:
        runner = FakeRunner([
            CommandResult(1, "", "no ports"),   # batch probe failed
            CommandResult(0, "", ""),           # first single check succeeds
        ])
        self.assertEqual(allocate_remote_port(runner, "python3"), 65081)


if __name__ == "__main__":
    unittest.main()
