"""SSHRunner unit tests: pure helpers, option construction, and one-shot
command execution with subprocess mocked out (no real SSH)."""

import os
import io
import subprocess
import sys
import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.models import CommandResult
from common import ssh as ssh_mod
from common.ssh import (
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


@unittest.skipUnless(os.name == "nt", "Windows process flags")
class TestWindowsProcessFlags(unittest.TestCase):
    def test_tunnel_hidden_console_instead_of_no_window(self):
        kwargs = ssh_mod._windows_no_window_kwargs(
            hidden_console=True, new_process_group=True
        )
        flags = kwargs["creationflags"]
        self.assertTrue(flags & getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10))
        self.assertFalse(flags & subprocess.CREATE_NO_WINDOW)
        self.assertFalse(flags & subprocess.DETACHED_PROCESS)
        self.assertEqual(kwargs["startupinfo"].wShowWindow, 0)

    def test_default_still_uses_no_window(self):
        kwargs = ssh_mod._windows_no_window_kwargs(detached=True)
        flags = kwargs["creationflags"]
        self.assertTrue(flags & subprocess.CREATE_NO_WINDOW)
        self.assertFalse(flags & getattr(subprocess, "CREATE_NEW_CONSOLE", 0x10))


class TestSSHRunnerConstruction(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

    def test_defaults(self):
        r = SSHRunner("server-a")
        self.assertEqual(r.backend, "paramiko")   # project default
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
            self.assertEqual(r.backend, "paramiko")
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
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

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
            "server", user="u", backend="openssh", jump_host="jump", jump_user="ju",
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
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

    def test_success(self):
        r = SSHRunner("server", user="u", backend="openssh", persistent_shell=False, control_master="disable")
        with mock.patch.object(ssh_mod.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=b"out\n", stderr=b"")
            res = r.run_command("echo hi")
        self.assertEqual(res, CommandResult(0, "out\n", "", kind="command"))
        self.assertTrue(run.called)

    def test_timeout_raises(self):
        r = SSHRunner("server", user="u", backend="openssh", persistent_shell=False, control_master="disable")
        with mock.patch.object(ssh_mod.subprocess, "run", side_effect=subprocess.TimeoutExpired("ssh", 1)):
            with self.assertRaises(subprocess.TimeoutExpired):
                r.run_command("echo hi", timeout=2)


class _FakePipelineProc:
    """Minimal Popen stub for the ssh | tar download pipeline."""

    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        self.returncode = returncode
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(stderr)
        self.returncode_value = returncode

    def communicate(self, timeout=None):
        return b"", b""

    def wait(self, timeout=None):
        return self.returncode

    def poll(self):
        return self.returncode

    def kill(self):
        self.returncode = -9


class _FakeTarProc(_FakePipelineProc):
    """Popen stub for the local tar side of the upload pipeline."""

    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        super().__init__(returncode, stderr)
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(stderr)


class _FakeSshProc(_FakePipelineProc):
    """Popen stub for the ssh side of the upload pipeline."""

    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        super().__init__(returncode, stderr)
        self.stdout = io.BytesIO(b"")
        self.stderr = io.BytesIO(stderr)
        self.returncode = returncode

    def communicate(self, timeout=None):
        return b"", self.stderr.getvalue()


class TestRecursiveUploadPipeline(unittest.TestCase):
    """ssh | tar 上传流水线的失败分类与 ControlMaster 降级（§4/§4.5）。"""

    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from common.paths import override_work_dir_for_tests

        override_work_dir_for_tests(self.wd)
        self.local_file = self.wd / "f.txt"
        self.local_file.write_text("payload", encoding="utf-8")

    def _plan(self, runner):
        (plan,) = ssh_mod.build_tar_upload_plans(
            "tar", [(self.local_file, "/remote/f.txt")]
        )
        return plan

    def test_upload_pipeline_degrades_from_broken_controlmaster(self):
        runner = SSHRunner(
            "server-a", user="u", backend="openssh", control_master="auto",
        )
        plan = self._plan(runner)
        calls: list[str] = []

        def fake_popen(cmd, **kwargs):
            argv = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
            if argv and argv[0] == runner._ssh_cmd:
                if any("ControlPath=" in part for part in argv):
                    calls.append("ssh-cm")
                    return _FakeSshProc(
                        255, b"mux_client_request_session: session failed\n"
                    )
                calls.append("ssh-direct")
                return _FakeSshProc(0)
            calls.append("tar")
            return _FakeTarProc(0)

        with mock.patch.object(ssh_mod.subprocess, "Popen", side_effect=fake_popen):
            result = runner._execute_openssh_upload_plan(
                plan, _TimeoutBudget.start(30, 30)
            )
        self.assertEqual(result.returncode, 0, result)
        self.assertEqual(calls.count("ssh-cm"), 1)
        self.assertIn("ssh-direct", calls)

    def test_local_tar_failure_is_reported_with_tar_stderr(self):
        runner = SSHRunner(
            "server-a", user="u", backend="openssh", control_master="disable",
        )
        plan = self._plan(runner)

        def fake_popen(cmd, **kwargs):
            argv = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
            if argv and argv[0] == runner._ssh_cmd:
                return _FakeSshProc(0)
            return _FakeTarProc(2, b"tar: Cannot open: No such file or directory\n")

        with mock.patch.object(ssh_mod.subprocess, "Popen", side_effect=fake_popen):
            result = runner._execute_openssh_upload_plan(
                plan, _TimeoutBudget.start(30, 30)
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("Cannot open", result.stderr)


class TestRunnerBackendDispatch(unittest.TestCase):
    """openssh / paramiko 后端分派与连接测试（无真实网络）。"""

    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from common.paths import override_work_dir_for_tests

        override_work_dir_for_tests(self.wd)

    def test_connection_success_and_failures(self):
        runner = SSHRunner("server-a", user="u", backend="openssh")
        with mock.patch.object(
            ssh_mod.subprocess, "run",
            return_value=mock.Mock(returncode=0, stderr=""),
        ):
            self.assertTrue(runner.test_connection(timeout=3))
        with mock.patch.object(
            ssh_mod.subprocess, "run",
            return_value=mock.Mock(
                returncode=255, stderr="ssh: connect to host server-a: refused"
            ),
        ):
            self.assertFalse(runner.test_connection(timeout=3))
        with mock.patch.object(
            ssh_mod.subprocess, "run",
            side_effect=subprocess.TimeoutExpired("ssh", 3),
        ):
            self.assertFalse(runner.test_connection(timeout=3))
        with mock.patch.object(
            ssh_mod.subprocess, "run", side_effect=FileNotFoundError("ssh")
        ):
            self.assertFalse(runner.test_connection(timeout=3))

    def test_paramiko_run_command_uses_backend_result(self):
        runner = SSHRunner("server-a", user="u", backend="paramiko")
        fake_backend = mock.Mock()
        fake_backend.run_command.return_value = (7, "out", "err")
        runner._paramiko_backend = fake_backend
        result = runner.run_command("echo hi", timeout=5)
        self.assertEqual((result.returncode, result.stdout, result.stderr),
                         (7, "out", "err"))
        self.assertEqual(result.kind, "command")

    def test_paramiko_recursive_download_dispatches_to_backend(self):
        runner = SSHRunner("server-a", user="u", backend="paramiko")
        fake_backend = mock.Mock()
        fake_backend.download_tar.return_value = (0, "", "")
        runner._paramiko_backend = fake_backend
        plan = ssh_mod.build_tar_download_plan(
            "tar", "/remote/dir", self.wd / "out"
        )
        result = runner._download_via_tar(
            "/remote/dir", self.wd / "out", timeout=5
        )
        self.assertEqual(result.returncode, 0)
        fake_backend.download_tar.assert_called_once()

    def test_openssh_upload_text_uses_ssh_stdin(self):
        runner = SSHRunner(
            "server-a", user="u", backend="openssh", persistent_shell=False,
            control_master="disable",
        )
        with mock.patch.object(ssh_mod.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"")
            result = runner.upload_text("hello", "/remote/x.txt", timeout=5)
        self.assertEqual(result.returncode, 0)
        self.assertTrue(run.called)
        payload = run.call_args.kwargs.get("input")
        if payload is None:
            payload = run.call_args[1]["input"]
        self.assertIn(b"hello", payload)

    def test_close_is_idempotent(self):
        runner = SSHRunner("server-a", user="u", backend="openssh")
        runner.close()
        runner.close()


class TestPortForwardLifecycle(unittest.TestCase):
    def test_recursive_download_degrades_from_broken_controlmaster(self):
        """并发设计 §4: ControlMaster 故障必须自动降级直连（≤3 次总尝试）。
        当前只有 upload 走了降级路径，递归下载是单次尝试（评审新发现）。"""
        wd = Path(tempfile.mkdtemp())
        from common.paths import override_work_dir_for_tests

        override_work_dir_for_tests(wd)
        runner = SSHRunner(
            "server-a", user="u", backend="openssh", control_master="auto",
        )
        plan = ssh_mod.build_tar_download_plan("tar", "/remote/dir", wd / "out")
        calls: list[str] = []

        def fake_popen(cmd, **kwargs):
            argv = list(cmd) if isinstance(cmd, (list, tuple)) else [str(cmd)]
            if argv and argv[0] == runner._ssh_cmd:
                if any("ControlPath=" in part for part in argv):
                    calls.append("ssh-cm")
                    return _FakePipelineProc(
                        255,
                        b"mux_client_request_session: session request failed\n",
                    )
                calls.append("ssh-direct")
                return _FakePipelineProc(0)
            calls.append("tar")
            plan.staged_item.mkdir(parents=True, exist_ok=True)
            return _FakePipelineProc(0)

        with mock.patch.object(ssh_mod.subprocess, "Popen", side_effect=fake_popen):
            result = runner._execute_openssh_download_plan(
                plan, _TimeoutBudget.start(30, 30)
            )
        self.assertEqual(result.returncode, 0, result)
        self.assertIn("ssh-direct", calls)
        self.assertEqual(calls.count("ssh-cm"), 1)
        self.assertTrue((wd / "out").is_dir())

    def test_proxy_is_never_silently_ignored(self):
        """O7: OpenSSH 承载路径不支持 proxy 时必须明确报错，不得直连。"""
        with self.assertRaises(ValueError):
            SSHRunner(
                "server-a", user="u", backend="openssh",
                proxy_url="socks5://proxy:1080",
            )

    def test_skill_tunnel_rejects_proxy(self):
        runner = SSHRunner(
            "server-a", user="u", backend="paramiko",
            proxy_url="socks5://proxy:1080",
        )
        with mock.patch.object(ssh_mod.subprocess, "Popen") as popen:
            with self.assertRaises(RuntimeError):
                runner._start_port_forward_locked(65099, settle=1.0)
        popen.assert_not_called()

    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

    @mock.patch.object(SSHRunner, "can_reach_port", return_value=True)
    def test_start_port_forward_builds_command(self, _reach):
        proc = mock.Mock()
        proc.poll.return_value = None
        proc.pid = 4242
        with mock.patch.object(ssh_mod.subprocess, "Popen", return_value=proc) as popen:
            r = SSHRunner("server", user="u", backend="openssh")
            out = r.start_port_forward(65082, settle=0.1, remote_port=65081)
        self.assertIs(out, proc)
        cmd = popen.call_args[0][0]
        self.assertIn("-L", cmd)
        self.assertIn("65082:127.0.0.1:65081", cmd)
        self.assertTrue(r.is_tunnel_alive)
        r.stop_port_forward()
        self.assertFalse(r.is_tunnel_alive)

    def test_start_port_forward_past_deadline_raises(self):
        r = SSHRunner("server", user="u")
        import time as _t
        with mock.patch.object(ssh_mod.subprocess, "Popen") as popen:
            with self.assertRaises(subprocess.TimeoutExpired):
                r.start_port_forward(65082, deadline=_t.monotonic() - 1)
        popen.assert_not_called()

    def test_tunnel_pid_setter_marks_external(self):
        r = SSHRunner("server")
        self.assertFalse(r.is_tunnel_alive)
        r.tunnel_pid = 12345
        self.assertEqual(r.tunnel_pid, 12345)


class TestRetryAndFallback(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

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

    def test_remote_command_rc255_stays_command_kind(self):
        r = SSHRunner("server", control_master="disable")
        completed = mock.Mock(returncode=255, stdout=b"remote-output", stderr=b"")
        with mock.patch.object(ssh_mod.subprocess, "run", return_value=completed):
            result = r._run_command_once("exit 255")
        self.assertEqual(result.kind, "command")
        self.assertEqual(result.returncode, 255)

    def test_ssh_transport_diagnostic_rc255_is_transport_kind(self):
        r = SSHRunner("server", control_master="disable")
        completed = mock.Mock(
            returncode=255,
            stdout=b"",
            stderr=b"ssh: connect to host server port 22: Connection refused",
        )
        with mock.patch.object(ssh_mod.subprocess, "run", return_value=completed):
            result = r._run_command_once("echo hi")
        self.assertEqual(result.kind, "transport")
        self.assertEqual(result.returncode, 255)

    def test_remote_rc_marker_wins_over_stderr_heuristics(self):
        """O1: 远端 shell 已回传真实 rc 时，哪怕 stderr 出现类 ssh 文本，
        也必须保持 kind=command 与真实返回码（§4.5）。"""
        r = SSHRunner("server", control_master="disable")
        completed = mock.Mock(
            returncode=0,
            stdout=b"remote-output",
            stderr=(
                b"ssh: connect to host elsewhere port 22: Connection refused\n"
                b"\n__VB_REMOTE_RC__:255\n"
            ),
        )
        with mock.patch.object(ssh_mod.subprocess, "run", return_value=completed):
            result = r._run_command_once("some-command")
        self.assertEqual(result.kind, "command")
        self.assertEqual(result.returncode, 255)
        self.assertNotIn("__VB_REMOTE_RC__", result.stderr)
        self.assertIn("ssh: connect to host elsewhere", result.stderr)

    def test_wrapped_script_reports_rc_marker(self):
        """一次执行必须自己回传 rc：ssh 的 rc 只用于传输层判定。"""
        r = SSHRunner("server", control_master="disable")
        with mock.patch.object(ssh_mod.subprocess, "run") as run:
            run.return_value = mock.Mock(returncode=0, stdout=b"", stderr=b"")
            r._run_command_once("exit 7")
        payload = run.call_args.kwargs.get("input")
        if payload is None:
            payload = run.call_args[1]["input"]
        text = payload.decode("utf-8")
        self.assertIn("exit 7", text)
        self.assertIn("__VB_REMOTE_RC__", text)

    def test_connect_timeout_rendered_as_integer_for_cli(self):
        """OpenSSH 的 ConnectTimeout 只接受整数秒；浮点子预算不得直接
        写进命令行（否则 ssh 报 ‘invalid time value’，隧道直接失败）。"""
        r = SSHRunner(
            "server", user="u", backend="paramiko", connect_timeout=0.5
        )
        opts = r._common_ssh_options()
        rendered = [o for o in opts if o.startswith("ConnectTimeout=")]
        self.assertEqual(len(rendered), 1)
        self.assertEqual(rendered[0], "ConnectTimeout=1")

    def test_openssh_one_shot_maps_missing_file_to_path(self):
        """§4.5/§4.6: no-such-file 诊断必须是 kind=path，且后端切换
        （openssh/paramiko）不得改变结果语义。"""
        r = SSHRunner(
            "server", user="u", backend="openssh",
            persistent_shell=False, control_master="disable",
        )
        completed = mock.Mock(
            returncode=1, stdout=b"",
            stderr=b"sha256sum: /remote/missing.bin: No such file or directory\n",
        )
        with mock.patch.object(ssh_mod.subprocess, "run", return_value=completed):
            res = r.run_one_shot("sha256sum -- /remote/missing.bin", timeout=5)
        self.assertEqual(res.kind, "path")
        self.assertEqual(res.returncode, 1)

    def test_ambiguous_mid_session_reset_is_not_retried(self):
        """并发设计 §4: 无法证明命令未投递时不得重发。

        “Connection reset by peer” 可能发生在命令已经执行之后；它不属于
        明确的建连阶段失败，必须按结果未知/传输错误返回，绝不能重跑。
        """
        r = SSHRunner(
            "server", user="u", backend="openssh",
            persistent_shell=False, control_master="disable",
        )
        completed = mock.Mock(
            returncode=255, stdout=b"", stderr=b"Connection reset by peer\n"
        )
        with mock.patch.object(
            ssh_mod.subprocess, "run", return_value=completed
        ) as run:
            result = r._run_command_once("do-once")
        self.assertEqual(run.call_count, 1, "ambiguous reset must not resend")
        self.assertEqual(result.kind, "transport")

    def test_describe_failure(self):
        r = SSHRunner("server")
        text = r.describe_ssh_command_failure("upload", CommandResult(255, "", "Permission denied"))
        self.assertIn("authentication failed", text)
        text2 = r.describe_ssh_command_failure("upload", CommandResult(1, "", ""))
        self.assertIn("Failed to upload", text2)


class TestRunRemoteTask(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp())
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

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
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

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
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

    def test_start_success(self):
        r = SSHRunner("server", user="u", backend="openssh")
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
        r = SSHRunner("server", user="u", backend="openssh")
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
        from common.paths import override_work_dir_for_tests
        override_work_dir_for_tests(self.wd)

    def test_openssh_close_stops_master(self):
        r = SSHRunner("server", user="u", backend="openssh", control_master="force")
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
