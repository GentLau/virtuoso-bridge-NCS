"""RemoteClient transport tests with a configurable fake SSHRunner."""

import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult
from transport.registry import UserEntry
from transport.remote_roles import resolve
from transport.runtime_paths import set_working_dir
from transport.tunnel import RemoteClient


class FakeRunner:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.command_results = {}
        self.upload_result = CommandResult(0, "", "")
        self.download_result = CommandResult(0, "", "")
        FakeRunner.instances.append(self)

    @property
    def is_tunnel_alive(self):
        return False

    def start_port_forward(self, *a, **k):
        self.calls.append(("start_port_forward", a, k))

    def stop_port_forward(self):
        self.calls.append(("stop_port_forward", (), {}))

    def close(self):
        self.calls.append(("close", (), {}))

    def run_command(self, cmd, timeout=None):
        self.calls.append(("run_command", (cmd, timeout), {}))
        if cmd in self.command_results:
            return self.command_results[cmd]
        if cmd.startswith("sha256sum"):
            path = cmd.split()[-1].strip("'")
            digest = hashlib.sha256(path.encode()).hexdigest()
            return CommandResult(0, f"{digest}  {path}", "")
        return self.command_results.get(cmd, CommandResult(0, "", ""))

    def upload_text(self, *a, **k):
        self.calls.append(("upload_text", a, k))
        return CommandResult(0, "", "")

    def upload(self, *a, **k):
        self.calls.append(("upload", a, k))
        return self.upload_result

    def download(self, *a, **k):
        self.calls.append(("download", a, k))
        return self.download_result


def make_entry(**kwargs):
    entry = UserEntry(token="tok-1", mode="remote")
    entry.route.skill.daemon_host = kwargs.get("skill_host", "daemon-a")
    entry.route.skill.daemon_port = 65081
    entry.route.skill.local_port = 65082
    entry.route.command.host = kwargs.get("command_host", "daemon-a")
    entry.route.file.host = kwargs.get("file_host", "daemon-a")
    entry.expected.daemon_user = "alice"
    entry.expected.remote_python = "python3"
    entry.deploy.scratch_root = "/home/alice/.virtuoso-bridge"
    entry.runtime.channel_budget = kwargs.get("channel_budget", 10)
    return entry


class TestRemoteClientTransport(unittest.TestCase):
    def setUp(self):
        set_working_dir(Path(tempfile.mkdtemp()))
        FakeRunner.instances.clear()

    def test_serial_command_uses_command_runner(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            res = client.run_command("echo hi")
            runner = client.command_runner
        self.assertEqual(res.returncode, 0)
        self.assertTrue(any(c[0] == "run_command" and c[1][0] == "echo hi" for c in runner.calls))

    def test_upload_success_verifies_sha(self):
        entry = make_entry()
        from unittest import mock
        local = Path(tempfile.mkdtemp()) / "p.bin"
        local.write_bytes(b"payload")
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            digest = hashlib.sha256(local.read_bytes()).hexdigest()
            client.file_runner.command_results[f"sha256sum /remote/p.bin"] = CommandResult(
                0, f"{digest}  /remote/p.bin", ""
            )
            res = client.upload_file(local, "/remote/p.bin")
            runner = client.file_runner
        self.assertEqual(res.returncode, 0)
        calls = [c for c in runner.calls if c[0] == "run_command"]
        self.assertTrue(any(c[1][0].startswith("sha256sum") for c in calls))

    def test_upload_failure_propagates(self):
        entry = make_entry()
        from unittest import mock
        local = Path(tempfile.mkdtemp()) / "p.bin"
        local.write_bytes(b"x")
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client.file_runner.upload_result = CommandResult(1, "", "upload boom")
            res = client.upload_file(local, "/remote/p.bin")
        self.assertEqual(res.returncode, 1)
        self.assertIn("boom", res.stderr)

    def test_download_recursive_skips_digest(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            res = client.download_file("/remote/dir", Path(tempfile.mkdtemp()) / "out", recursive=True)
            runner = client.file_runner
        self.assertEqual(res.returncode, 0)
        self.assertTrue(any(c[0] == "download" and c[2].get("recursive") for c in runner.calls))

    def test_channel_budget_exceeded(self):
        entry = make_entry(channel_budget=1)
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._channel_sem.acquire()  # exhaust the budget
            res = client.run_command("echo hi", parallel=True)
            client._channel_sem.release()
        self.assertEqual(res.returncode, 1)
        self.assertIn("channel budget exceeded", res.stderr)

    def test_close_stops_and_closes_runners(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client.ensure_tunnel()
            client.run_command("echo hi")
            client.close()
        for runner in FakeRunner.instances:
            self.assertTrue(any(c[0] == "stop_port_forward" for c in runner.calls))


class TestRemoteClientEdges(unittest.TestCase):
    def setUp(self):
        set_working_dir(Path(tempfile.mkdtemp()))
        FakeRunner.instances.clear()

    def test_jump_suppressed_when_target_is_jump_host(self):
        entry = make_entry()
        entry.route.jump.host = "daemon-a"
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            runner = client.command_runner
        self.assertIsNone(runner.kwargs["jump_host"])

    def test_ensure_tunnel_local_is_noop(self):
        entry = make_entry()
        entry.mode = "local"
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client.ensure_tunnel()
        self.assertEqual(FakeRunner.instances, [])

    def test_deploy_mkdir_failure_raises(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client.skill_runner.command_results = {}
            client.skill_runner.run_command = lambda *a, **k: CommandResult(1, "", "mkdir boom")
            with self.assertRaises(RuntimeError):
                client.deploy(python_major=3)

    def test_deploy_upload_failure_raises(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client.skill_runner.upload_text = lambda *a, **k: CommandResult(1, "", "upload boom")
            with self.assertRaises(RuntimeError):
                client.deploy(python_major=3)

    def test_upload_budget_exceeded(self):
        entry = make_entry(channel_budget=1)
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._channel_sem.acquire()
            res = client.upload_file(Path(tempfile.mkdtemp()) / "p.bin", "/remote/p.bin")
            client._channel_sem.release()
        self.assertIn("channel budget exceeded", res.stderr)

    def test_download_budget_exceeded(self):
        entry = make_entry(channel_budget=1)
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._channel_sem.acquire()
            res = client.download_file("/remote/p.bin", Path(tempfile.mkdtemp()) / "p.bin")
            client._channel_sem.release()
        self.assertIn("channel budget exceeded", res.stderr)

    def test_download_failure_propagates(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client.file_runner.download_result = CommandResult(1, "", "download boom")
            res = client.download_file("/remote/p.bin", Path(tempfile.mkdtemp()) / "p.bin")
        self.assertIn("download boom", res.stderr)

    def test_verify_command_failure_propagates(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client.file_runner.run_command = lambda *a, **k: CommandResult(1, "", "sha boom")
            res = client._verify("/remote/p.bin", b"abc")
        self.assertIn("sha boom", res.stderr)

    def test_verify_mismatch(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client.file_runner.run_command = lambda *a, **k: CommandResult(0, "deadbeef  /remote/p.bin", "")
            res = client._verify("/remote/p.bin", b"abc")
        self.assertEqual(res.returncode, 1)
        self.assertIn("sha256 mismatch", res.stderr)


class TestRemoteClientRecursiveUpload(unittest.TestCase):
    def setUp(self):
        set_working_dir(Path(tempfile.mkdtemp()))
        FakeRunner.instances.clear()

    def test_directory_without_recursive_is_rejected(self):
        entry = make_entry()
        from unittest import mock
        d = Path(tempfile.mkdtemp())
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            res = client.upload_file(d, "/remote/dir")
        self.assertEqual(res.returncode, 1)
        self.assertIn("recursive=True", res.stderr)

    def test_recursive_upload_skips_digest(self):
        entry = make_entry()
        from unittest import mock
        d = Path(tempfile.mkdtemp())
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            res = client.upload_file(d, "/remote/dir", recursive=True)
            runner = client.file_runner
        self.assertEqual(res.returncode, 0)
        uploads = [c for c in runner.calls if c[0] == "upload"]
        self.assertTrue(uploads and uploads[-1][2].get("recursive"))
        self.assertFalse(any(c[0] == "run_command" and c[1][0].startswith("sha256sum") for c in runner.calls))

    def test_recursive_with_file_is_rejected(self):
        entry = make_entry()
        from unittest import mock
        f = Path(tempfile.mkdtemp()) / "f.txt"
        f.write_text("x", encoding="utf-8")
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            res = client.upload_file(f, "/remote/f.txt", recursive=True)
        self.assertEqual(res.returncode, 1)
        self.assertIn("recursive upload requires a directory", res.stderr)


if __name__ == "__main__":
    unittest.main()
