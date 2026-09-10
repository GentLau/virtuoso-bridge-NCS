"""SSHRunner unit tests: pure helpers, option construction, and one-shot
command execution with subprocess mocked out (no real SSH)."""

import os
import subprocess
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult
from transport import ssh as ssh_mod
from transport.ssh import (
    SSHRunner,
    _as_text,
    _derive_tool,
    _short_control_path,
    _TimeoutBudget,
)


class TestPureHelpers(unittest.TestCase):
    def test_as_text(self):
        self.assertEqual(_as_text(None), "")
        self.assertEqual(_as_text("str"), "str")
        self.assertEqual(_as_text(b"a\xff"), "a\ufffd")

    def test_derive_tool_exe_sibling(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "ssh.exe"
            scp = Path(d) / "scp.exe"
            exe.write_bytes(b"")
            scp.write_bytes(b"")
            self.assertEqual(_derive_tool(str(exe), "ssh", "scp"), str(scp))

    def test_derive_tool_fallback(self):
        result = _derive_tool("/no/such/ssh", "ssh", "scp").lower()
        self.assertTrue(result.endswith("scp") or result.endswith("scp.exe"), result)

    def test_short_control_path_stable(self):
        a = _short_control_path("server", "alice", "jump")
        b = _short_control_path("server", "alice", "jump")
        c = _short_control_path("server2", "alice", "jump")
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)
        self.assertIn("vb_ssh_", a)

    def test_timeout_budget(self):
        b = _TimeoutBudget.start(5, 10)
        self.assertEqual(b.timeout, 5.0)
        self.assertGreater(b.remaining("cmd"), 0)
        expired = _TimeoutBudget.start(0, 10)
        self.assertEqual(expired.available(), 0.0)
        with self.assertRaises(subprocess.TimeoutExpired):
            expired.remaining("cmd")


class TestSSHRunnerConstruction(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    def test_defaults(self):
        r = SSHRunner("server-a")
        self.assertEqual(r.backend, "openssh")
        self.assertEqual(r.max_sessions, 10)
        self.assertEqual(r.host, "server-a")
        self.assertIsNone(r.user)

    def test_env_variables_are_ignored(self):
        old = {k: os.environ.get(k) for k in ("VB_SSH_BACKEND", "VB_SSH_PROXY", "VB_SSH_MAX_SESSIONS")}
        os.environ["VB_SSH_BACKEND"] = "paramiko"
        os.environ["VB_SSH_PROXY"] = "socks5://127.0.0.1:1080"
        os.environ["VB_SSH_MAX_SESSIONS"] = "99"
        try:
            r = SSHRunner("server-a")
            self.assertEqual(r.backend, "openssh")
            self.assertEqual(r.max_sessions, 10)
            self.assertIsNone(r._proxy_url)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_invalid_backend_raises(self):
        with self.assertRaises(ValueError):
            SSHRunner("server-a", backend="bogus")

    def test_invalid_max_sessions_raises(self):
        with self.assertRaises(ValueError):
            SSHRunner("server-a", max_sessions=0)

    def test_paramiko_backend_constructs(self):
        r = SSHRunner("server-a", user="u", backend="paramiko", connect_timeout=5)
        try:
            self.assertIsNotNone(r._paramiko_backend)
            self.assertFalse(r.persistent_shell_enabled)
        finally:
            r.close()


class TestSSHOptionConstruction(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    def test_common_options_disable_cm(self):
        r = SSHRunner("server", user="u", connect_timeout=7, control_master="disable")
        opts = r._common_ssh_options()
        self.assertIn("-o", opts)
        self.assertIn("BatchMode=yes", opts)
        self.assertIn("ConnectTimeout=7", opts)
        self.assertIn("GSSAPIAuthentication=no", opts)
        self.assertNotIn("ControlMaster=auto", opts)

    def test_common_options_force_cm_and_jump_and_files(self):
        cfg = Path(tempfile.mkdtemp()) / "config"
        key = Path(tempfile.mkdtemp()) / "id_ed25519"
        r = SSHRunner(
            "server", user="u", jump_host="jump", jump_user="ju",
            ssh_config_path=cfg, ssh_key_path=key, control_master="force",
        )
        opts = r._common_ssh_options()
        self.assertIn("ControlMaster=auto", opts)
        self.assertIn("ControlPath=" + r._control_path, opts)
        self.assertIn("-F", opts)
        self.assertIn("-i", opts)
        self.assertIn("-J", opts)
        self.assertIn("ju@jump", opts)

    def test_build_ssh_base(self):
        r = SSHRunner("server", user="u")
        base = r._build_ssh_base()
        self.assertEqual(base[-1], "u@server")

    def test_remote_scp_target(self):
        r = SSHRunner("server", user="u")
        self.assertEqual(r._remote_scp_target("/tmp/a b.txt"), r"u@server:/tmp/a\ b.txt")
        with self.assertRaises(ValueError):
            r._remote_scp_target("/tmp/bad\nname")

    def test_decode_b64_text(self):
        import base64
        payload = base64.b64encode("你好".encode("utf-8")).decode("ascii")
        self.assertEqual(SSHRunner._decode_b64_text(payload), "你好")
        self.assertEqual(SSHRunner._decode_b64_text(None), "")
        self.assertEqual(SSHRunner._decode_b64_text(""), "")
        with self.assertRaises(RuntimeError):
            SSHRunner._decode_b64_text("!!!not base64!!!")

    def test_error_classifiers(self):
        self.assertTrue(SSHRunner._is_transient_ssh_error(255, "connection reset by peer"))
        self.assertFalse(SSHRunner._is_transient_ssh_error(255, "Permission denied"))
        self.assertTrue(SSHRunner._is_cm_failure(255, "getsockname failed: Not a socket"))
        self.assertFalse(SSHRunner._is_cm_failure(255, "Permission denied"))
        self.assertFalse(SSHRunner._is_cm_failure(0, ""))

    def test_summarize_transport_errors(self):
        r = SSHRunner("server")
        self.assertIn("host lookup failed", r._summarize_ssh_transport_error("could not resolve hostname"))
        self.assertIn("authentication failed", r._summarize_ssh_transport_error("Permission denied"))
        self.assertIn("timed out", r._summarize_ssh_transport_error("connection timed out"))
        self.assertIn("refused", r._summarize_ssh_transport_error("Connection refused on port 22"))
        self.assertIn("closed before login", r._summarize_ssh_transport_error("kex_exchange_identification"))
        self.assertIn("failed", r._summarize_ssh_transport_error(None))
        self.assertEqual("some error", r._summarize_ssh_transport_error("some error"))


class TestOneShotRunCommand(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    def test_success(self):
        r = SSHRunner("server", user="u", persistent_shell=False, control_master="disable")
        with mock.patch.object(ssh_mod.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=b"out\n", stderr=b"")
            res = r.run_command("echo hi")
        self.assertEqual(res, CommandResult(0, "out\n", ""))
        self.assertTrue(run.called)

    def test_timeout_raises(self):
        r = SSHRunner("server", user="u", persistent_shell=False, control_master="disable")
        with mock.patch.object(ssh_mod.subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                r.run_command("echo hi", timeout=2)


class TestPortForwardLifecycle(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    @mock.patch.object(SSHRunner, "can_reach_port", return_value=True)
    def test_start_port_forward_builds_command(self, _reach):
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 4242
        with mock.patch.object(ssh_mod.subprocess, "Popen", return_value=proc) as popen:
            r = SSHRunner("server", user="u")
            out = r.start_port_forward(65082, settle=0.1, remote_port=65081)
        self.assertIs(out, proc)
        cmd = popen.call_args[0][0]
        self.assertIn("-L", cmd)
        self.assertIn("65082:127.0.0.1:65081", cmd)
        self.assertTrue(r.is_tunnel_alive)
        r.stop_port_forward()
        self.assertFalse(r.is_tunnel_alive)

    def test_tunnel_pid_setter_marks_external(self):
        r = SSHRunner("server")
        self.assertFalse(r.is_tunnel_alive)
        r.tunnel_pid = 12345
        self.assertEqual(r.tunnel_pid, 12345)


class TestRetryAndFallback(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    def test_cm_fallback_disables_and_retries(self):
        r = SSHRunner("server", control_master="auto")
        calls = []

        def attempt():
            calls.append(1)
            if len(calls) == 1:
                return 255, b"", b"mux_client_request_session failed"
            return 0, b"ok", b""

        budget = _TimeoutBudget.start(10, 10)
        rc, out, err = r._attempt_with_cm_fallback(attempt, budget=budget, command="cmd")
        self.assertEqual(rc, 0)
        self.assertEqual(len(calls), 2)
        self.assertFalse(r._use_control_master)

    def test_transient_retry_then_success(self):
        r = SSHRunner("server")
        calls = iter([
            (255, b"", b"connection reset by peer"),
            (0, b"ok", b""),
        ])
        budget = _TimeoutBudget.start(10, 10)
        rc, _, _ = r._attempt_with_cm_fallback(lambda: next(calls), budget=budget, command="cmd")
        self.assertEqual(rc, 0)

    def test_non_retryable_breaks_immediately(self):
        r = SSHRunner("server")
        budget = _TimeoutBudget.start(10, 10)
        rc, _, err = r._attempt_with_cm_fallback(
            lambda: (255, b"", b"Permission denied"),
            budget=budget, command="cmd",
        )
        self.assertEqual(rc, 255)
        self.assertIn(b"Permission denied", err)

    def test_describe_failure(self):
        r = SSHRunner("server")
        text = r.describe_ssh_command_failure("upload", CommandResult(255, "", "Permission denied"))
        self.assertIn("authentication failed", text)
        text2 = r.describe_ssh_command_failure("upload", CommandResult(1, "", ""))
        self.assertIn("Failed to upload", text2)


class TestRunRemoteTask(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    def test_missing_local_file(self):
        runner = mock.Mock()
        res = ssh_mod.run_remote_task(
            runner, work_dir_base="/tmp", run_id="r1",
            uploads=[(Path(self.wd) / "missing.txt", "x")], command="echo hi",
        )
        self.assertFalse(res.success)
        self.assertIn("not found", res.error)

    def test_upload_failure(self):
        runner = mock.Mock()
        runner.upload_batch.return_value = CommandResult(1, "", "upload boom")
        local = Path(self.wd) / "a.txt"
        local.write_text("x", encoding="utf-8")
        res = ssh_mod.run_remote_task(
            runner, work_dir_base="/tmp", run_id="r1", uploads=[(local, "a.txt")], command="echo hi",
        )
        self.assertFalse(res.success)
        self.assertIn("upload boom", res.error)

    def test_success(self):
        runner = mock.Mock()
        runner.upload_batch.return_value = CommandResult(0, "", "")
        runner.run_command.return_value = CommandResult(0, "done", "")
        local = Path(self.wd) / "a.txt"
        local.write_text("x", encoding="utf-8")
        res = ssh_mod.run_remote_task(
            runner, work_dir_base="/tmp", run_id="r1", uploads=[(local, "a.txt")], command="echo hi",
        )
        self.assertTrue(res.success)
        self.assertEqual(res.stdout, "done")
        self.assertEqual(res.remote_dir, "/tmp/r1")

    def test_command_timeout(self):
        runner = mock.Mock()
        runner.upload_batch.return_value = CommandResult(0, "", "")
        runner.run_command.side_effect = subprocess.TimeoutExpired("ssh", 1)
        local = Path(self.wd) / "a.txt"
        local.write_text("x", encoding="utf-8")
        res = ssh_mod.run_remote_task(
            runner, work_dir_base="/tmp", run_id="r1", uploads=[(local, "a.txt")], command="echo hi",
        )
        self.assertFalse(res.success)
        self.assertIn("timed out", res.error)


class TestPersistentShellMechanics(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    def test_pump_shell_output(self):
        import queue
        stream = iter([b"line1\n", b"line2"])
        out = queue.Queue()
        SSHRunner._pump_shell_output(stream, out)
        self.assertEqual(out.get(), "line1\n")
        self.assertEqual(out.get(), "line2")
        self.assertIsNone(out.get())

    def _runner_with_shell(self):
        r = SSHRunner("server", user="u")
        r._shell_proc = mock.Mock()
        r._shell_proc.poll.return_value = None
        r._shell_proc.stdin = mock.Mock()
        r._shell_queue = __import__("queue").Queue()
        return r

    def test_run_via_shell_protocol(self):
        r = self._runner_with_shell()
        # capture script markers then feed the shell protocol back
        import base64
        import re
        def write(script):
            text = script.decode()
            tok = re.search(r"__vb_STDOUT_B64_BEGIN_([0-9a-f]+)__", text).group(1)
            self.begin = f"__vb_STDOUT_B64_BEGIN_{tok}__"
            self.stderr_marker = f"__vb_STDERR_B64_BEGIN_{tok}__"
            self.rc = f"__vb_RC_{tok}__"
        r._shell_proc.stdin.write = mock.Mock(side_effect=write)
        q = r._shell_queue
        def feed():
            for _ in range(200):
                if hasattr(self, "begin"):
                    break
                time.sleep(0.01)
            q.put(self.begin)
            q.put(base64.b64encode(b"hello").decode())
            q.put(self.stderr_marker)
            q.put(base64.b64encode(b"err").decode())
            q.put(self.rc + "0")
        import threading
        threading.Thread(target=feed, daemon=True).start()
        res = r._run_command_via_persistent_shell_locked("echo hi", timeout=5)
        self.assertEqual(res.returncode, 0)
        self.assertEqual(res.stdout, "hello")
        self.assertEqual(res.stderr, "err")

    def test_shell_not_running_raises(self):
        r = SSHRunner("server", user="u")
        r._shell_proc = None
        with self.assertRaises(RuntimeError):
            r._run_command_via_persistent_shell_locked("echo hi")

    def test_shell_exited_raises(self):
        r = self._runner_with_shell()
        r._shell_queue.put(None)
        with self.assertRaises(RuntimeError):
            r._run_command_via_persistent_shell_locked("echo hi", timeout=5)

    def test_shell_timeout(self):
        r = self._runner_with_shell()
        budget = _TimeoutBudget.start(0, 0)
        with self.assertRaises(__import__("subprocess").TimeoutExpired):
            r._run_command_via_persistent_shell_locked("echo hi", _budget=budget)

    def test_unexpected_protocol_line(self):
        r = self._runner_with_shell()
        r._shell_proc.stdin.write = lambda b: None
        with mock.patch.object(ssh_mod.uuid, "uuid4") as uuid4:
            uuid4.return_value = mock.Mock(hex="tok")
            r._shell_queue.put("__vb_STDOUT_B64_BEGIN_tok__")
            r._shell_queue.put("aGVsbG8=")
            r._shell_queue.put("SURPRISE")
            with self.assertRaises(RuntimeError):
                r._run_command_via_persistent_shell_locked("echo hi", timeout=5)

    def test_ensure_persistent_shell_disabled(self):
        r = SSHRunner("server", user="u", persistent_shell=False)
        r.ensure_persistent_shell()
        self.assertIsNone(r._shell_proc)


class TestEnsurePersistentShell(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    def test_start_success(self):
        r = SSHRunner("server", user="u")
        r._persistent_shell_enabled = True
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.stdin = mock.Mock()
        proc.stdout = mock.Mock()
        with mock.patch.object(ssh_mod.subprocess, "Popen", return_value=proc), \
             mock.patch.object(r, "_run_command_via_persistent_shell_locked", return_value=CommandResult(0, "", "")), \
             mock.patch.object(ssh_mod.threading, "Thread"):
            r.ensure_persistent_shell(timeout=5)
        self.assertIs(r._shell_proc, proc)

    def test_start_probe_failure_raises(self):
        r = SSHRunner("server", user="u")
        r._persistent_shell_enabled = True
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.stdin = mock.Mock()
        proc.stdout = mock.Mock()
        with mock.patch.object(ssh_mod.subprocess, "Popen", return_value=proc), \
             mock.patch.object(r, "_run_command_via_persistent_shell_locked", return_value=CommandResult(1, "", "bad shell")), \
             mock.patch.object(ssh_mod.threading, "Thread"):
            with self.assertRaises(RuntimeError):
                r.ensure_persistent_shell(timeout=5)


class TestCloseTearsDownControlMaster(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from transport.runtime_paths import set_working_dir
        set_working_dir(self.wd)

    def test_openssh_close_stops_master(self):
        r = SSHRunner("server", user="u", control_master="force")
        with mock.patch.object(ssh_mod.subprocess, "run") as run:
            r.close()
        self.assertTrue(run.called)
        cmd = run.call_args[0][0]
        self.assertIn("-O", cmd)
        self.assertIn("exit", cmd)
        self.assertIn(f"ControlPath={r._control_path}", cmd)
        self.assertTrue(cmd[-1].endswith("@server"))

    def test_cm_disabled_skips_master_stop(self):
        r = SSHRunner("server", user="u", control_master="disable")
        with mock.patch.object(ssh_mod.subprocess, "run") as run:
            r.close()
        run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
