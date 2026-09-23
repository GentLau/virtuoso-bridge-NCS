"""RemoteClient transport tests with a configurable fake SSHRunner."""

import hashlib
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult
from common.registry import UserEntry
from common.remote_paths import RemotePathError
from transport.remote_roles import resolve
from common.paths import override_work_dir_for_tests
from transport.tunnel import RemoteClient


class FakeRunner:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = []
        self.command_results = {}
        self.upload_result = CommandResult(0, "", "")
        self.download_result = CommandResult(0, "", "")
        self.sha256_value = None
        self.download_payload = None
        self.remote_kind = "missing"
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

    def run_one_shot(self, cmd, timeout=None):
        self.calls.append(("run_one_shot", (cmd, timeout), {}))
        return self.run_command(cmd, timeout=timeout)

    def run_command(self, cmd, timeout=None):
        self.calls.append(("run_command", (cmd, timeout), {}))
        if cmd in self.command_results:
            return self.command_results[cmd]
        if "$HOME" in cmd:
            return CommandResult(0, "/home/alice", "")
        if cmd.startswith("sha256sum"):
            path = cmd.split()[-1].strip("'")
            digest = self.sha256_value or hashlib.sha256(path.encode()).hexdigest()
            return CommandResult(0, f"{digest}  {path}", "")
        if cmd.startswith("if [ -d"):
            return CommandResult(0, self.remote_kind, "")
        return self.command_results.get(cmd, CommandResult(0, "", ""))

    def upload_text(self, *a, **k):
        self.calls.append(("upload_text", a, k))
        return CommandResult(0, "", "")

    def upload(self, *a, **k):
        self.calls.append(("upload", a, k))
        return self.upload_result

    def download(self, *a, **k):
        self.calls.append(("download", a, k))
        if (
            self.download_result.returncode == 0
            and self.download_payload is not None
            and len(a) >= 2
        ):
            local = Path(a[1])
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(self.download_payload)
        return self.download_result


def make_entry(**kwargs):
    entry = UserEntry(token="tok-1", mode="remote")
    entry.ssh.default.host = kwargs.get("skill_host", "daemon-a")
    entry.ssh.default.user = "alice"
    entry.roles.daemon.host = kwargs.get("skill_host", "daemon-a")
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65082
    entry.roles.command.host = kwargs.get("command_host", "daemon-a")
    entry.roles.file.host = kwargs.get("file_host", "daemon-a")
    entry.roles.daemon.expected_user = "alice"
    entry.roles.daemon.python = "python3"
    entry.roles.daemon.root = "/home/alice/.virtuoso-bridge"
    entry.runtime.channel_budget = kwargs.get("channel_budget", 10)
    return entry


class TestRemoteClientTransport(unittest.TestCase):
    def setUp(self):
        override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        FakeRunner.instances.clear()

    def test_serial_command_uses_command_runner(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            res = client.run_command("echo hi")
            runner = client.command_runner
        self.assertEqual(res.returncode, 0)
        self.assertTrue(any(c[0] == "run_command" and c[1][0] == "echo hi" for c in runner.calls))

    def test_nul_remote_path_is_rejected(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            with self.assertRaises(RemotePathError):
                client.resolve_remote_path(
                    client.targets.file, "misc\x00nul.txt"
                )

    def test_upload_success_verifies_sha(self):
        entry = make_entry()
        from unittest import mock
        local = Path(tempfile.mkdtemp(prefix="vb-")) / "p.bin"
        local.write_bytes(b"payload")
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            digest = hashlib.sha256(local.read_bytes()).hexdigest()
            client.file_runner.sha256_value = digest
            res = client.upload_file(local, "/remote/p.bin")
            runner = client.file_runner
        self.assertEqual(res.returncode, 0)
        calls = [c for c in runner.calls if c[0] == "run_command"]
        self.assertTrue(any(c[1][0].startswith("sha256sum") for c in calls))
        self.assertTrue(any(c[1][0].startswith("if [ -d") for c in calls))

    def test_upload_failure_propagates(self):
        entry = make_entry()
        from unittest import mock
        local = Path(tempfile.mkdtemp(prefix="vb-")) / "p.bin"
        local.write_bytes(b"x")
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.file_runner.upload_result = CommandResult(1, "", "upload boom")
            res = client.upload_file(local, "/remote/p.bin")
        self.assertEqual(res.returncode, 1)
        self.assertIn("boom", res.stderr)

    def test_upload_checksum_mismatch_does_not_move_stage(self):
        entry = make_entry()
        from unittest import mock
        local = Path(tempfile.mkdtemp(prefix="vb-")) / "p.bin"
        local.write_bytes(b"payload")
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._one_shot_runner = client._runner
            client.file_runner.sha256_value = "deadbeef"
            res = client.upload_file(local, "/remote/p.bin")
            runner = client.file_runner
        self.assertEqual(res.kind, "checksum")
        self.assertFalse(
            any(c[0] == "run_command" and c[1][0].startswith("if [ -d")
                for c in runner.calls)
        )

    def test_download_recursive_skips_digest(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.file_runner.remote_kind = "directory"
            res = client.download_file("/remote/dir", Path(tempfile.mkdtemp(prefix="vb-")) / "out", recursive=True)
            runner = client.file_runner
        self.assertEqual(res.returncode, 0)
        self.assertTrue(any(c[0] == "download" and c[2].get("recursive") for c in runner.calls))

    def test_channel_budget_exceeded(self):
        entry = make_entry(channel_budget=1)
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            lease = client.budgets.try_acquire_channel(
                endpoint_key="file", role_name="file", role_max_sessions=1
            )  # exhaust the token-wide budget
            res = client.run_command("echo hi", parallel=True)
            lease.release()
        self.assertEqual(res.returncode, 1)
        self.assertIn("channel budget exceeded", res.stderr)

    def test_close_stops_and_closes_runners(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.ensure_tunnel()
            client.run_command("echo hi")
            client.close()
        for runner in FakeRunner.instances:
            self.assertTrue(any(c[0] == "stop_port_forward" for c in runner.calls))


class TestRemoteClientEdges(unittest.TestCase):
    def setUp(self):
        override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        FakeRunner.instances.clear()

    def test_jump_suppressed_when_target_is_jump_host(self):
        entry = make_entry()
        entry.ssh.default.jump_host = "daemon-a"
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            runner = client.command_runner
        self.assertIsNone(runner.kwargs["jump_host"])

    def test_ensure_tunnel_local_is_noop(self):
        entry = make_entry()
        entry.ssh.default.host = None
        entry.ssh.default.user = None
        for role_name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, role_name)
            role.host = None
            role.user = None
            role.jump_host = None
            role.jump_user = None
            role.proxy = None
        entry.mode = "local"
        entry.roles.daemon.local_port = entry.roles.daemon.daemon_port
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.ensure_tunnel()
        self.assertEqual(FakeRunner.instances, [])

    def test_deploy_mkdir_failure_raises(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.skill_runner.command_results = {}
            client.skill_runner.run_command = lambda *a, **k: CommandResult(1, "", "mkdir boom")
            with self.assertRaises(RuntimeError):
                client.deploy(python_major=3)

    def test_deploy_upload_failure_raises(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.skill_runner.upload_text = lambda *a, **k: CommandResult(1, "", "upload boom")
            with self.assertRaises(RuntimeError):
                client.deploy(python_major=3)

    def test_upload_budget_exceeded(self):
        entry = make_entry(channel_budget=1)
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            lease = client.budgets.try_acquire_channel(
                endpoint_key="file", role_name="file", role_max_sessions=1
            )
            res = client.upload_file(Path(tempfile.mkdtemp(prefix="vb-")) / "p.bin", "/remote/p.bin")
            lease.release()
        self.assertIn("channel budget exceeded", res.stderr)

    def test_download_budget_exceeded(self):
        entry = make_entry(channel_budget=1)
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            lease = client.budgets.try_acquire_channel(
                endpoint_key="file", role_name="file", role_max_sessions=1
            )
            res = client.download_file("/remote/p.bin", Path(tempfile.mkdtemp(prefix="vb-")) / "p.bin")
            lease.release()
        self.assertIn("channel budget exceeded", res.stderr)

    def test_download_failure_propagates(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.file_runner.remote_kind = "file"  # 源是常规文件（§4.6）
            client.file_runner.download_result = CommandResult(1, "", "download boom")
            res = client.download_file("/remote/p.bin", Path(tempfile.mkdtemp(prefix="vb-")) / "p.bin")
        self.assertIn("download boom", res.stderr)

    def test_download_checksum_mismatch_keeps_existing_target(self):
        entry = make_entry()
        from unittest import mock
        target = Path(tempfile.mkdtemp(prefix="vb-")) / "p.bin"
        target.write_bytes(b"old")
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._one_shot_runner = client._runner
            client.file_runner.remote_kind = "file"  # 源是常规文件（§4.6）
            client.file_runner.sha256_value = hashlib.sha256(b"remote").hexdigest()
            client.file_runner.download_payload = b"new"
            res = client.download_file("/remote/p.bin", target)
        self.assertEqual(res.kind, "checksum")
        self.assertEqual(target.read_bytes(), b"old")

    def test_verify_command_failure_propagates(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.file_runner.run_one_shot = lambda *a, **k: CommandResult(1, "", "sha boom")
            res = client._verify("/remote/p.bin", b"abc")
        self.assertIn("sha boom", res.stderr)

    def test_verify_mismatch(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            client.file_runner.run_one_shot = lambda *a, **k: CommandResult(0, "deadbeef  /remote/p.bin", "")
            res = client._verify("/remote/p.bin", b"abc")
        self.assertEqual(res.returncode, 1)
        self.assertIn("sha256 mismatch", res.stderr)


class TestRemoteClientRecursiveUpload(unittest.TestCase):
    def setUp(self):
        override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-")))
        FakeRunner.instances.clear()

    def test_directory_without_recursive_is_rejected(self):
        entry = make_entry()
        from unittest import mock
        d = Path(tempfile.mkdtemp(prefix="vb-"))
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            res = client.upload_file(d, "/remote/dir")
        self.assertEqual(res.returncode, 1)
        self.assertIn("recursive=True", res.stderr)

    def test_recursive_upload_skips_digest(self):
        entry = make_entry()
        from unittest import mock
        d = Path(tempfile.mkdtemp(prefix="vb-"))
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            res = client.upload_file(d, "/remote/dir", recursive=True)
            runner = client.file_runner
        self.assertEqual(res.returncode, 0)
        uploads = [c for c in runner.calls if c[0] == "upload"]
        self.assertTrue(uploads and uploads[-1][2].get("recursive"))
        self.assertFalse(any(c[0] == "run_command" and c[1][0].startswith("sha256sum") for c in runner.calls))

    def test_recursive_with_file_is_rejected(self):
        entry = make_entry()
        from unittest import mock
        f = Path(tempfile.mkdtemp(prefix="vb-")) / "f.txt"
        f.write_text("x", encoding="utf-8")
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            # one-shot channels (digest check) reuse the role runner here
            client._one_shot_runner = client._runner
            res = client.upload_file(f, "/remote/f.txt", recursive=True)
        self.assertEqual(res.returncode, 1)
        self.assertIn("recursive upload requires a directory", res.stderr)

    def test_recursive_upload_rejects_file_target(self):
        entry = make_entry()
        from unittest import mock
        source = Path(tempfile.mkdtemp(prefix="vb-"))
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._one_shot_runner = client._runner
            client.file_runner.remote_kind = "file"
            res = client.upload_file(source, "/remote/not-a-dir", recursive=True)
        self.assertEqual(res.kind, "path")

    def test_recursive_download_rejects_file_source(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._one_shot_runner = client._runner
            client.file_runner.remote_kind = "file"
            res = client.download_file(
                "/remote/not-a-dir",
                Path(tempfile.mkdtemp(prefix="vb-")) / "out",
                recursive=True,
            )
        self.assertEqual(res.kind, "path")

    def test_non_recursive_download_of_directory_is_path_kind(self):
        """§4.6: 对象类型与 recursive 不符 → kind=path（不能把 sha 报错当命令失败）。"""
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._one_shot_runner = client._runner
            runner = client.file_runner
            runner.remote_kind = "directory"
            original = runner.run_command

            def run_command(cmd, timeout=None):
                if cmd.startswith("sha256sum"):
                    # real ``sha256sum <dir>`` fails exactly like this
                    return CommandResult(
                        1, "", "sha256sum: /remote/dir: Is a directory"
                    )
                return original(cmd, timeout=timeout)

            runner.run_command = run_command
            res = client.download_file(
                "/remote/dir", Path(tempfile.mkdtemp(prefix="vb-")) / "out"
            )
        self.assertEqual(res.kind, "path")
        self.assertEqual(res.returncode, 1)

    def test_connect_timeout_keeps_fractional_seconds(self):
        """§2.2: connect_timeout 是浮点秒；不得被 int() 截断成 0。"""
        entry = make_entry()
        entry.runtime.connect_timeout = 0.5
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
        self.assertEqual(client._runner_kwargs["connect_timeout"], 0.5)

    def test_local_sha256_honours_call_deadline(self):
        """O3/§5.8: 本地摘要计算属于文件调用预算，超时必须中止。"""
        path = Path(tempfile.mkdtemp(prefix="vb-")) / "big.bin"
        path.write_bytes(b"x" * 4096)
        with self.assertRaises(subprocess.TimeoutExpired):
            RemoteClient._sha256_local(path, deadline=time.monotonic() - 1.0)

    def test_runtime_tilde_path_is_rejected(self):
        """O4/§4.2: 注册后 root 为绝对路径，运行期不再解析 ~。"""
        entry = make_entry()
        from unittest import mock
        from common.remote_paths import RemotePathError
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
        with self.assertRaises(RemotePathError):
            client.resolve_remote_path(client.targets.file, "~/x.txt")

    def test_download_replace_failure_reports_path_kind(self):
        """§4.6: 目标不可替换（如目标目录）→ kind=path，且清理 stage。"""
        entry = make_entry()
        from unittest import mock
        target_dir = Path(tempfile.mkdtemp(prefix="vb-")) / "target"
        target_dir.mkdir()
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._one_shot_runner = client._runner
            runner = client.file_runner
            runner.remote_kind = "file"
            payload = b"payload-bytes"
            runner.download_payload = payload
            runner.sha256_value = hashlib.sha256(payload).hexdigest()
            res = client.download_file("/remote/p.bin", target_dir)
        self.assertEqual(res.kind, "path")
        self.assertIn("VB-PATH-NOT-VISIBLE", res.stderr)
        leftovers = [p.name for p in target_dir.parent.iterdir()
                     if p.name.startswith(".vbtmp-")]
        self.assertEqual(leftovers, [])

    def test_serial_slot_wait_timeout_is_timeout_kind(self):
        """默认串行命令：等不到串行位时必须返回 kind=timeout（§4.5）。"""
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._one_shot_runner = client._runner
            client._serial_lock.acquire()
            try:
                res = client.run_command("echo hi", timeout=0.1)
            finally:
                client._serial_lock.release()
        self.assertEqual(res.kind, "timeout")
        self.assertEqual(res.returncode, 124)
        self.assertIn("serial command slot", res.stderr)

    def test_one_shot_role_dispatch_uses_role_runner(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            res = client.run_one_shot("gui", "xdotool key Escape", timeout=5)
            runner = client._runner(client.targets.gui)
        self.assertEqual(res.returncode, 0)
        self.assertTrue(any(
            call[0] == "run_one_shot" and call[1][0] == "xdotool key Escape"
            for call in runner.calls
        ))

    def test_remote_sha256_missing_digest_is_transport_error(self):
        entry = make_entry()
        from unittest import mock
        with mock.patch("transport.tunnel.SSHRunner", FakeRunner):
            client = RemoteClient(entry, resolve(entry), "alice")
            client._one_shot_runner = client._runner
            runner = client.file_runner
            runner.run_command = lambda cmd, timeout=None: CommandResult(0, "", "")
            error, digest = client._remote_sha256(
                client.targets.file, "/remote/p.bin", 5
            )
        self.assertIsNotNone(error)
        self.assertEqual(error.kind, "transport")
        self.assertEqual(digest, "")


if __name__ == "__main__":
    unittest.main()
