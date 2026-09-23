"""SSH runner edges: helpers, transfer fallbacks and persistent-shell recovery.

The main ``test_ssh*.py`` files cover the happy paths of each primitive; this
file drives the branches a reviewer would otherwise find unused: log-handler
fallbacks, pipeline teardown, scp/tar failure handling, ControlMaster wedging
and the persistent-shell retry/cleanup matrix.  Everything is in-process with
fake processes; the semi-real counterpart is
``test/semi/transport/ssh_backend_semi_tb.py``.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import queue
import re
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common import ssh as ssh_mod
from common.ssh import (
    SSHRunner,
    UnknownEffectError,
    _TimeoutBudget,
    _drain_binary_stream,
    _stop_pipeline,
)
from common.transfer import (
    FileDownloadPlan,
    TarDownloadPlan,
    TarUploadPlan,
    build_file_download_plan,
    build_tar_download_plan,
)
from pyapi.models import CommandResult


def _runner(**kwargs) -> SSHRunner:
    kwargs.setdefault("backend", "openssh")
    kwargs.setdefault("persistent_shell", False)
    return SSHRunner("server-a", user="u", **kwargs)


class TestModuleHelpers(unittest.TestCase):
    def test_drain_binary_stream_collects_and_reports(self):
        class _Stream:
            def __init__(self, chunks):
                self._chunks = list(chunks)
                self._fail = False

            def read(self, _n):
                if not self._chunks:
                    if self._fail:
                        raise OSError("boom")
                    return b""
                return self._chunks.pop(0)

        chunks: list[bytes] = []
        failures: queue.Queue = queue.Queue()
        _drain_binary_stream(_Stream([b"a", b"b"]), chunks, failures)
        self.assertEqual(chunks, [b"a", b"b"])
        self.assertTrue(failures.empty())

        stream = _Stream([])
        stream._fail = True
        _drain_binary_stream(stream, [], failures)
        self.assertIsInstance(failures.get_nowait(), OSError)

    def test_stop_pipeline_swallows_every_cleanup_error(self):
        class _Process:
            def kill(self):
                raise OSError("kill failed")

            def wait(self, timeout=None):
                raise subprocess.TimeoutExpired("x", timeout)

        class _Stream:
            def close(self):
                raise OSError("close failed")

        class _Worker:
            def __init__(self):
                self.joined = False

            def join(self, timeout=None):
                self.joined = True

        worker = _Worker()
        _stop_pipeline([_Process()], [_Stream()], [worker])
        self.assertTrue(worker.joined)

    def test_command_log_is_idempotent_and_cleans_up(self):
        root = logging.getLogger()
        before = list(root.handlers)
        work = Path(tempfile.mkdtemp(prefix="vb-"))
        try:
            ssh_mod.configure_command_log(work / "log" / "commands.log")
            first = [h for h in root.handlers if getattr(h, "_vb_cmd_log", False)]
            self.assertEqual(len(first), 1)
            ssh_mod.configure_command_log(work / "log" / "commands.log")
            second = [h for h in root.handlers if getattr(h, "_vb_cmd_log", False)]
            self.assertEqual(len(second), 1, "second call must be a no-op")
        finally:
            for handler in list(root.handlers):
                if handler not in before:
                    root.removeHandler(handler)
                    handler.close()

    def test_command_log_disables_itself_when_the_file_cannot_open(self):
        root = logging.getLogger()
        before = list(root.handlers)
        with mock.patch.object(
            logging.handlers, "RotatingFileHandler",
            side_effect=OSError("no permission"),
        ):
            ssh_mod.configure_command_log(Path("R:/nope/commands.log"))
        added = [h for h in root.handlers if h not in before]
        self.assertEqual(added, [])

    def test_interpreter_shutdown_marker_is_sticky(self):
        previous = ssh_mod._INTERPRETER_SHUTTING_DOWN
        try:
            ssh_mod._mark_interpreter_shutdown()
            self.assertTrue(ssh_mod._INTERPRETER_SHUTTING_DOWN)
        finally:
            ssh_mod._INTERPRETER_SHUTTING_DOWN = previous


class TestResultKinds(unittest.TestCase):
    def test_kind_inference_matrix(self):
        cases = {
            "VB-TRANSPORT: broken": "transport",
            "VB-PATH-NOT-VISIBLE: /x": "path",
            "VB-UNKNOWN-EFFECT: maybe": "unknown-effect",
            "cache sha256 mismatch for /x": "checksum",
            "cp: cannot stat '/x'": "path",
            "plain failure": "command",
        }
        for stderr, expected in cases.items():
            with self.subTest(stderr=stderr):
                result = SSHRunner._result_from_rc(3, "out", stderr)
                self.assertEqual(result.kind, expected)
                self.assertEqual(result.returncode, 3)
                self.assertEqual(result.stdout, "out")

    def test_result_coerces_bytes_and_none(self):
        result = SSHRunner._result_from_rc(0, None, None)
        self.assertEqual((result.stdout, result.stderr), ("", ""))


class TestRemoteRcExtraction(unittest.TestCase):
    MARKER = "__vb_RC_tok__"

    def test_marker_with_blank_line_is_removed(self):
        stderr = f"warning\n\n{self.MARKER} 5\n"
        rc, seen, cleaned = SSHRunner._extract_remote_rc(stderr, self.MARKER, 255)
        self.assertEqual((rc, seen), (5, True))
        self.assertEqual(cleaned.strip(), "warning")

    def test_marker_without_blank_line_is_removed(self):
        rc, seen, cleaned = SSHRunner._extract_remote_rc(
            f"warning\n{self.MARKER} 7\n", self.MARKER, 255
        )
        self.assertEqual((rc, seen), (7, True))
        self.assertEqual(cleaned.strip(), "warning")

    def test_unparsable_marker_falls_back_to_ssh_rc(self):
        stderr = f"{self.MARKER} not-a-number\n"
        rc, seen, cleaned = SSHRunner._extract_remote_rc(stderr, self.MARKER, 255)
        self.assertEqual((rc, seen), (255, False))
        self.assertEqual(cleaned, stderr)

    def test_absent_marker_falls_back(self):
        rc, seen, cleaned = SSHRunner._extract_remote_rc("nothing", self.MARKER, 9)
        self.assertEqual((rc, seen, cleaned), (9, False, "nothing"))


class TestRunnerDelegation(unittest.TestCase):
    def test_run_command_and_one_shot_use_paramiko_backend(self):
        backend = mock.Mock()
        backend.run_command.return_value = (0, "ok", "")
        runner = _runner()
        runner._paramiko_backend = backend
        self.assertEqual(runner.run_command("echo ok").stdout, "ok")
        self.assertEqual(runner.run_one_shot("echo ok").stdout, "ok")
        self.assertEqual(backend.run_command.call_count, 2)

    def test_upload_text_delegates_to_paramiko(self):
        backend = mock.Mock()
        backend.upload_text.return_value = (3, "", "VB-TRANSPORT: no")
        runner = _runner()
        runner._paramiko_backend = backend
        result = runner.upload_text("payload", "/remote/file")
        self.assertEqual(result.returncode, 3)
        self.assertEqual(result.kind, "transport")
        self.assertEqual(backend.upload_text.call_args[0][1], b"payload")

    def test_download_delegates_to_paramiko(self):
        backend = mock.Mock()
        backend.download_file.return_value = (0, "", "")
        runner = _runner()
        runner._paramiko_backend = backend
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.download("/remote/file", Path(tmp) / "local")
        self.assertEqual(result.returncode, 0)
        backend.download_file.assert_called_once()

    def test_download_recursive_delegates_to_paramiko_tar(self):
        backend = mock.Mock()
        backend.download_tar.return_value = (0, "", "")
        runner = _runner()
        runner._paramiko_backend = backend
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.download("/remote/dir", Path(tmp) / "local", recursive=True)
        self.assertEqual(result.returncode, 0)
        backend.download_tar.assert_called_once()

    def test_upload_and_batch_validate_local_paths(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.bin"
            with self.assertRaises(FileNotFoundError):
                runner.upload(missing, "/remote/x")
            directory = Path(tmp) / "dir"
            directory.mkdir()
            with self.assertRaises(IsADirectoryError):
                runner.upload(directory, "/remote/x")
        empty = runner.upload_batch([])
        self.assertEqual(empty.returncode, 0)

    def test_upload_uses_tar_plans_and_logs_failure(self):
        runner = _runner()
        plan = TarUploadPlan(("tar",), "remote", "/r", 1)
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "f.bin"
            local.write_bytes(b"x")
            with mock.patch.object(
                ssh_mod, "build_tar_upload_plans", return_value=(plan,)
            ) as builder, mock.patch.object(
                runner, "_execute_tar_upload_plans",
                return_value=CommandResult(1, "", "tar failed"),
            ):
                result = runner.upload(local, "/remote/f.bin")
        self.assertEqual(result.returncode, 1)
        builder.assert_called_once()

    def test_tar_upload_plans_stop_at_first_failure(self):
        runner = _runner()
        good = TarUploadPlan(("tar",), "a", "/r", 1)
        bad = TarUploadPlan(("tar",), "b", "/r", 1)
        results = [
            CommandResult(0, "", ""),
            CommandResult(2, "", "boom"),
            CommandResult(0, "", ""),
        ]
        with mock.patch.object(
            runner, "_execute_openssh_upload_plan", side_effect=results
        ) as attempt:
            result = runner._execute_tar_upload_plans(
                (good, bad, good), _TimeoutBudget.start(10, 10)
            )
        self.assertEqual(result.returncode, 2)
        self.assertEqual(attempt.call_count, 2, "third plan must not run")

    def test_tar_upload_plans_delegate_to_paramiko(self):
        backend = mock.Mock()
        backend.upload_tar.return_value = (0, "", "")
        runner = _runner()
        runner._paramiko_backend = backend
        plan = TarUploadPlan(("tar",), "a", "/r", 1)
        result = runner._execute_tar_upload_plans(
            (plan,), _TimeoutBudget.start(10, 10)
        )
        self.assertEqual(result.returncode, 0)
        backend.upload_tar.assert_called_once()


class _FakePipe(io.BytesIO):
    """BytesIO that also accepts the Popen pipe keyword usage."""

    def close(self):  # noqa: D401 - allow repeated closes
        if not self.closed:
            super().close()


class _FakeProc:
    def __init__(self, *, returncode=0, out=b"", err=b"", wait_error=None):
        self.returncode = returncode
        self.stdout = _FakePipe(out)
        self.stderr = _FakePipe(err)
        self._wait_error = wait_error
        self.stdin = None
        self.terminated = False
        self.killed = False

    def communicate(self, timeout=None):
        return self.stdout.read(), self.stderr.read()

    def wait(self, timeout=None):
        if self._wait_error is not None:
            raise self._wait_error
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True


class TestOpensshUploadPlan(unittest.TestCase):
    def test_success_returns_ssh_rc(self):
        runner = _runner()
        runner._use_control_master = False
        plan = TarUploadPlan(("tar",), "remote", "/r", 1)
        tar_proc = _FakeProc(returncode=0)
        ssh_proc = _FakeProc(returncode=0)
        with mock.patch.object(
            subprocess, "Popen", side_effect=[tar_proc, ssh_proc]
        ):
            result = runner._execute_openssh_upload_plan(
                plan, _TimeoutBudget.start(30, 30)
            )
        self.assertEqual(result.returncode, 0)

    def test_local_tar_failure_is_reported_when_ssh_succeeds(self):
        runner = _runner()
        runner._use_control_master = False
        plan = TarUploadPlan(("tar",), "remote", "/r", 1)
        tar_proc = _FakeProc(returncode=2, err=b"tar exploded")
        ssh_proc = _FakeProc(returncode=0)
        with mock.patch.object(
            subprocess, "Popen", side_effect=[tar_proc, ssh_proc]
        ):
            result = runner._execute_openssh_upload_plan(
                plan, _TimeoutBudget.start(30, 30)
            )
        self.assertEqual(result.returncode, 2)
        self.assertIn("tar exploded", result.stderr)

    def test_spawn_failure_propagates_and_stops_pipeline(self):
        runner = _runner()
        runner._use_control_master = False
        plan = TarUploadPlan(("tar",), "remote", "/r", 1)
        with mock.patch.object(
            subprocess, "Popen", side_effect=OSError("no tar")
        ), mock.patch.object(ssh_mod, "_stop_pipeline") as stop:
            with self.assertRaises(OSError):
                runner._execute_openssh_upload_plan(
                    plan, _TimeoutBudget.start(30, 30)
                )
        stop.assert_called_once()


class TestDownloadEdges(unittest.TestCase):
    def test_scp_failure_discards_stage_and_reports_path_kind(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "out.bin"
            plan = build_file_download_plan("/remote/missing.bin", local)
            with mock.patch.object(
                runner, "_attempt_with_cm_fallback",
                return_value=(1, b"", b"scp: /remote/missing.bin: No such file or directory"),
            ):
                result = runner.download("/remote/missing.bin", local)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.kind, "path")
            self.assertFalse(plan.stage_path.exists())
            self.assertFalse(local.exists())

    def test_scp_success_installs_staged_file(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "out.bin"
            plan = build_file_download_plan("/remote/file.bin", local)

            def fake_attempt():
                plan.stage_path.mkdir(parents=True, exist_ok=True)
                plan.staged_item.write_bytes(b"payload")
                return 0, b"", b""

            with mock.patch.object(
                ssh_mod, "build_file_download_plan", return_value=plan
            ), mock.patch.object(
                runner, "_attempt_with_cm_fallback",
                side_effect=lambda *a, **k: fake_attempt(),
            ):
                result = runner.download("/remote/file.bin", local)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(local.read_bytes(), b"payload")

    def test_scp_attempt_exception_discards_stage(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "out.bin"
            plan = build_file_download_plan("/remote/file.bin", local)
            with mock.patch.object(
                runner, "_attempt_with_cm_fallback",
                side_effect=RuntimeError("scp died"),
            ):
                with self.assertRaises(RuntimeError):
                    runner.download("/remote/file.bin", local)
            self.assertFalse(plan.stage_path.exists())

    def test_recursive_download_reports_invalid_remote_path(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            result = runner.download("/", Path(tmp) / "x", recursive=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Invalid remote directory path", result.stderr)

    def test_recursive_download_failure_maps_to_path_kind(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            plan = build_tar_download_plan("tar", "/remote/dir", Path(tmp) / "dir")
            with mock.patch.object(
                runner, "_run_openssh_download_attempt",
                return_value=CommandResult(
                    1, "", "tar: /remote/dir: Cannot open: No such file or directory"
                ),
            ):
                result = runner._execute_openssh_download_plan(
                    plan, _TimeoutBudget.start(30, 30)
                )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.kind, "path")


class TestOpensshDownloadAttempt(unittest.TestCase):
    def _plan(self, tmp: Path) -> TarDownloadPlan:
        return build_tar_download_plan("tar", "/remote/dir", tmp / "dir")

    def test_success_installs_staged_directory(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(Path(tmp))
            ssh_proc = _FakeProc(returncode=0)
            tar_proc = _FakeProc(returncode=0)

            def fake_popen(args, **kwargs):
                if args[0] == "tar":
                    plan.staged_item.mkdir(parents=True, exist_ok=True)
                    return tar_proc
                return ssh_proc

            with mock.patch.object(subprocess, "Popen", side_effect=fake_popen):
                result = runner._run_openssh_download_attempt(
                    plan, _TimeoutBudget.start(30, 30)
                )
            self.assertEqual(result.returncode, 0)
            self.assertTrue(plan.local_path.exists())

    def test_failure_reports_combined_stderr_and_discards_stage(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(Path(tmp))
            ssh_proc = _FakeProc(returncode=1, err=b"ssh: connection lost")
            tar_proc = _FakeProc(returncode=2, err=b"tar: broken archive")
            with mock.patch.object(
                subprocess, "Popen", side_effect=[ssh_proc, tar_proc]
            ):
                result = runner._run_openssh_download_attempt(
                    plan, _TimeoutBudget.start(30, 30)
                )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("connection lost", result.stderr)
            self.assertFalse(plan.stage_path.exists())

    def test_missing_expected_directory_is_reported(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(Path(tmp))
            ssh_proc = _FakeProc(returncode=0)
            tar_proc = _FakeProc(returncode=0)

            def fake_popen(args, **kwargs):
                if args[0] == "tar":
                    return tar_proc
                return ssh_proc

            with mock.patch.object(
                subprocess, "Popen", side_effect=fake_popen
            ):
                result = runner._run_openssh_download_attempt(
                    plan, _TimeoutBudget.start(30, 30)
                )
            self.assertEqual(result.returncode, 1)
            self.assertIn("did not contain expected directory", result.stderr)

    def test_tar_spawn_failure_discards_stage(self):
        runner = _runner()
        with tempfile.TemporaryDirectory() as tmp:
            plan = self._plan(Path(tmp))
            ssh_proc = _FakeProc(returncode=0)

            def fake_popen(args, **kwargs):
                if args[0] == "tar":
                    raise OSError("tar missing")
                return ssh_proc

            with mock.patch.object(
                subprocess, "Popen", side_effect=fake_popen,
            ):
                with self.assertRaises(OSError):
                    runner._run_openssh_download_attempt(
                        plan, _TimeoutBudget.start(30, 30)
                    )
            self.assertFalse(plan.stage_path.exists())


_UNSET = object()


class _FakeShellProc:
    def __init__(self, *, rc=None, stdin=_UNSET, stdout=None, wait_error=None):
        self._rc = rc
        self.stdin = mock.Mock() if stdin is _UNSET else stdin
        self.stdout = io.BytesIO(b"") if stdout is None else stdout
        self.terminated = False
        self.killed = False
        self._wait_error = wait_error

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = -15

    def kill(self):
        self.killed = True
        self._rc = -9

    def wait(self, timeout=None):
        if self._wait_error is not None:
            raise self._wait_error
        return self._rc


class TestPersistentShellLifecycle(unittest.TestCase):
    def test_ensure_is_a_noop_when_disabled(self):
        runner = _runner(persistent_shell=False)
        runner.ensure_persistent_shell()
        self.assertIsNone(runner._shell_proc)

    def test_ensure_reuses_a_live_shell(self):
        runner = _runner(persistent_shell=True, control_master="disable")
        proc = _FakeShellProc(rc=None)
        runner._shell_proc = proc
        runner.ensure_persistent_shell()
        self.assertIs(runner._shell_proc, proc)

    def test_openssh_shell_without_pipes_is_rejected(self):
        runner = _runner(persistent_shell=True, control_master="disable")
        proc = _FakeShellProc(rc=None, stdin=None, stdout=None)
        with mock.patch.object(subprocess, "Popen", return_value=proc):
            with self.assertRaises(RuntimeError) as ctx:
                runner.ensure_persistent_shell()
        self.assertIn("Failed to allocate pipes", str(ctx.exception))
        self.assertTrue(proc.terminated)

    def test_paramiko_shell_probe_failure_closes_shell(self):
        runner = _runner(persistent_shell=True, control_master="disable")
        backend = mock.Mock()
        backend.open_shell.return_value = _FakeShellProc(rc=None)
        runner._paramiko_backend = backend
        with mock.patch.object(
            runner, "_run_command_via_persistent_shell_locked",
            return_value=CommandResult(1, "", "probe failed"),
        ), mock.patch.object(
            runner, "_close_persistent_shell_locked"
        ) as closer:
            with self.assertRaises(RuntimeError) as ctx:
                runner.ensure_persistent_shell()
        self.assertIn("probe failed", str(ctx.exception))
        closer.assert_called()

    def test_paramiko_shell_probe_exception_closes_shell(self):
        runner = _runner(persistent_shell=True, control_master="disable")
        backend = mock.Mock()
        backend.open_shell.return_value = _FakeShellProc(rc=None)
        runner._paramiko_backend = backend
        with mock.patch.object(
            runner, "_run_command_via_persistent_shell_locked",
            side_effect=RuntimeError("boom"),
        ), mock.patch.object(
            runner, "_close_persistent_shell_locked"
        ) as closer:
            with self.assertRaises(RuntimeError):
                runner.ensure_persistent_shell()
        closer.assert_called()


class TestControlMasterHelpers(unittest.TestCase):
    def test_stop_control_master_swallows_errors(self):
        runner = _runner(control_master="force")
        for error in (OSError("no ssh"), subprocess.TimeoutExpired("ssh", 5)):
            with self.subTest(error=type(error).__name__):
                with mock.patch.object(subprocess, "run", side_effect=error):
                    runner._stop_control_master()  # must not raise

    def test_stop_control_master_skipped_when_not_multiplexing(self):
        runner = _runner(control_master="disable")
        with mock.patch.object(subprocess, "run") as run:
            runner._stop_control_master()
        run.assert_not_called()

    def test_mux_probe_detects_timeout_and_ignores_missing_socket(self):
        runner = _runner(control_master="force")
        with mock.patch.object(
            subprocess, "run",
            side_effect=subprocess.TimeoutExpired("ssh", 3),
        ):
            self.assertTrue(runner._mux_master_wedged())
        with mock.patch.object(subprocess, "run", side_effect=OSError("no socket")):
            self.assertFalse(runner._mux_master_wedged())

    def test_mux_probe_skipped_without_multiplexing(self):
        runner = _runner(control_master="disable")
        self.assertFalse(runner._mux_master_wedged())

    def test_recover_from_wedged_mux_disables_cm_and_unlinks_socket(self):
        runner = _runner(control_master="force")
        with mock.patch.object(
            ssh_mod.os, "unlink", side_effect=OSError("already gone")
        ) as unlink:
            runner._recover_from_wedged_mux()
        unlink.assert_called_once()
        self.assertFalse(runner._use_control_master)

    def test_common_ssh_options_falls_back_for_bad_connect_timeout(self):
        runner = _runner()
        runner._connect_timeout = "not-a-number"
        options = runner._common_ssh_options()
        self.assertIn("ConnectTimeout=30", options)


class TestSummariesAndRetryPredicates(unittest.TestCase):
    def test_describe_failure_uses_summary_then_rc(self):
        runner = _runner()
        summarized = runner.describe_ssh_command_failure(
            "upload", CommandResult(255, "", "Permission denied (publickey)")
        )
        self.assertIn("Failed to upload", summarized)
        self.assertIn("authentication failed", summarized)

        # the rc-based fallback only triggers when no summary is produced
        with mock.patch.object(
            runner, "_summarize_ssh_transport_error", return_value=""
        ):
            generic = runner.describe_ssh_command_failure(
                "upload", CommandResult(17, "", "")
            )
        self.assertIn("code 17", generic)

    def test_transport_error_summaries(self):
        runner = _runner()
        for fragment, expected in (
            ("Could not resolve hostname server-a", "host lookup failed"),
            ("ssh: connect to host server-a port 22: Connection refused",
             "refused the connection"),
            ("banner exchange timeout", "banner exchange timeout"),
        ):
            with self.subTest(fragment=fragment):
                text = runner._summarize_ssh_transport_error(fragment)
                self.assertIn(expected, text)

    def test_retryable_predicate_matrix(self):
        self.assertFalse(SSHRunner._is_retryable_persistent_shell_error(
            UnknownEffectError("Unexpected persistent shell protocol line: 'x'")
        ))
        self.assertTrue(SSHRunner._is_retryable_persistent_shell_error(
            RuntimeError("failed to write to persistent ssh shell")
        ))
        self.assertFalse(SSHRunner._is_retryable_persistent_shell_error(
            RuntimeError("something else")
        ))

    def test_shell_fallback_logging_switches_on_shutdown(self):
        runner = _runner()
        previous = ssh_mod._INTERPRETER_SHUTTING_DOWN
        try:
            ssh_mod._INTERPRETER_SHUTTING_DOWN = True
            with self.assertLogs("common.ssh", level="DEBUG") as captured:
                runner._log_persistent_shell_fallback(
                    "Persistent shell failed", RuntimeError("x")
                )
            self.assertTrue(any("DEBUG" in line for line in captured.output))
        finally:
            ssh_mod._INTERPRETER_SHUTTING_DOWN = previous


class TestPersistentShellRetry(unittest.TestCase):
    def _runner_with_shell(self):
        runner = _runner(persistent_shell=True)
        runner._shell_proc = _FakeShellProc(rc=None)
        runner._shell_queue = queue.Queue()
        return runner

    def test_success_returns_first_result(self):
        runner = self._runner_with_shell()
        with mock.patch.object(runner, "ensure_persistent_shell"), \
                mock.patch.object(
                    runner, "_run_command_via_persistent_shell_locked",
                    return_value=CommandResult(0, "ok", ""),
                ):
            result = runner._run_via_persistent_shell_with_retry("echo ok")
        self.assertEqual(result.stdout, "ok")

    def test_retryable_failure_rebuilds_shell_once(self):
        runner = self._runner_with_shell()
        attempts = [
            RuntimeError("persistent ssh shell exited unexpectedly"),
            CommandResult(0, "second", ""),
        ]

        def run(*_args, **_kwargs):
            outcome = attempts.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with mock.patch.object(runner, "ensure_persistent_shell"), \
                mock.patch.object(
                    runner, "_run_command_via_persistent_shell_locked",
                    side_effect=run,
                ), mock.patch.object(
                    runner, "_close_persistent_shell_locked"
                ) as closer:
            result = runner._run_via_persistent_shell_with_retry("echo ok")
        self.assertEqual(result.stdout, "second")
        self.assertEqual(closer.call_count, 1)

    def test_non_retryable_failure_is_raised_after_one_close(self):
        runner = self._runner_with_shell()
        with mock.patch.object(runner, "ensure_persistent_shell"), \
                mock.patch.object(
                    runner, "_run_command_via_persistent_shell_locked",
                    side_effect=RuntimeError("fatal"),
                ), mock.patch.object(
                    runner, "_close_persistent_shell_locked"
                ) as closer:
            with self.assertRaises(RuntimeError):
                runner._run_via_persistent_shell_with_retry("boom")
        self.assertEqual(closer.call_count, 1)

    def test_unknown_effect_closes_shell_and_is_never_retried(self):
        runner = self._runner_with_shell()
        with mock.patch.object(runner, "ensure_persistent_shell"), \
                mock.patch.object(
                    runner, "_run_command_via_persistent_shell_locked",
                    side_effect=UnknownEffectError("maybe executed"),
                ) as run, mock.patch.object(
                    runner, "_close_persistent_shell_locked"
                ) as closer:
            with self.assertRaises(UnknownEffectError):
                runner._run_via_persistent_shell_with_retry("dangerous")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(closer.call_count, 1)

    def test_timeout_is_not_retried_or_closed_here(self):
        runner = self._runner_with_shell()
        with mock.patch.object(runner, "ensure_persistent_shell"), \
                mock.patch.object(
                    runner, "_run_command_via_persistent_shell_locked",
                    side_effect=subprocess.TimeoutExpired("cmd", 1),
                ) as run, mock.patch.object(
                    runner, "_close_persistent_shell_locked"
                ) as closer:
            with self.assertRaises(subprocess.TimeoutExpired):
                runner._run_via_persistent_shell_with_retry("sleep 10")
        self.assertEqual(run.call_count, 1)
        self.assertEqual(closer.call_count, 0)


class TestPersistentShellLockedBranches(unittest.TestCase):
    def _runner_with_queue(self, **kwargs):
        runner = _runner(persistent_shell=True, **kwargs)
        runner._shell_proc = _FakeShellProc(rc=None, stdin=io.BytesIO())
        runner._shell_queue = queue.Queue()
        return runner

    @staticmethod
    def _await_marker(runner, timeout: float = 5.0) -> str:
        """Wait until the script has been written, then return its token."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            payload = runner._shell_proc.stdin.getvalue().decode("utf-8", "ignore")
            match = re.search(r"__vb_RC_([0-9a-f]+)__", payload)
            if match:
                return match.group(1)
            time.sleep(0.005)
        raise AssertionError("persistent-shell script was never written")

    def test_write_failure_is_unknown_effect(self):
        runner = self._runner_with_queue()

        class _FailingStdin:
            def write(self, _data):
                raise OSError("broken pipe")

            def flush(self):
                return None

        runner._shell_proc.stdin = _FailingStdin()
        with self.assertRaises(UnknownEffectError) as ctx:
            runner._run_command_via_persistent_shell_locked("echo x")
        self.assertIn("failed to write", str(ctx.exception))

    def test_empty_queue_times_out_and_closes_shell(self):
        runner = self._runner_with_queue()
        budget = _TimeoutBudget.start(0.05, 0.05)
        with mock.patch.object(
            runner, "_close_persistent_shell_locked"
        ) as closer:
            with self.assertRaises(subprocess.TimeoutExpired):
                runner._run_command_via_persistent_shell_locked(
                    "echo x", _budget=budget
                )
        closer.assert_called_once()

    def test_exhausted_budget_times_out_before_reading(self):
        runner = self._runner_with_queue()
        # one preamble line arrives in time; the loop then notices the deadline
        # has passed before it can consume the next line
        budget = _TimeoutBudget(timeout=5, deadline=time.monotonic() + 0.05)
        runner._shell_queue.put("preamble\n")
        with mock.patch.object(
            runner, "_close_persistent_shell_locked"
        ) as closer:
            with self.assertRaises(subprocess.TimeoutExpired):
                runner._run_command_via_persistent_shell_locked(
                    "echo x", _budget=budget
                )
        closer.assert_called_once()

    def test_shell_eof_reports_unknown_effect_or_runtime_error(self):
        runner = self._runner_with_queue()
        runner._shell_queue.put(None)
        with self.assertRaises(UnknownEffectError):
            runner._run_command_via_persistent_shell_locked("echo x")

        runner = self._runner_with_queue()
        runner._shell_queue.put(None)
        with self.assertRaises(RuntimeError):
            runner._run_command_via_persistent_shell_locked(
                "echo x", _unknown_effect_on_exit=False
            )

    def test_blank_protocol_lines_are_tolerated(self):
        runner = self._runner_with_queue()

        def producer():
            marker = self._await_marker(runner)
            runner._shell_queue.put(f"__vb_STDOUT_B64_BEGIN_{marker}__\n")
            runner._shell_queue.put(base64.b64encode(b"hi").decode() + "\n")
            runner._shell_queue.put("\n")
            runner._shell_queue.put(f"__vb_STDERR_B64_BEGIN_{marker}__\n")
            runner._shell_queue.put(base64.b64encode(b"warn").decode() + "\n")
            runner._shell_queue.put("\n")
            runner._shell_queue.put(f"__vb_RC_{marker}__0\n")

        worker = threading.Thread(target=producer, daemon=True)
        worker.start()
        result = runner._run_command_via_persistent_shell_locked(
            "echo hi", _budget=_TimeoutBudget.start(5, 5)
        )
        worker.join(timeout=2)
        self.assertEqual((result.stdout, result.stderr), ("hi", "warn"))

    def test_verbose_preamble_summary_is_printed(self):
        runner = self._runner_with_queue()
        runner._verbose = True

        def producer():
            marker = self._await_marker(runner)
            runner._shell_queue.put(f"__vb_STDOUT_B64_BEGIN_{marker}__\n")
            runner._shell_queue.put(base64.b64encode(b"").decode() + "\n")
            runner._shell_queue.put(f"__vb_STDERR_B64_BEGIN_{marker}__\n")
            runner._shell_queue.put(base64.b64encode(b"").decode() + "\n")
            runner._shell_queue.put(f"__vb_RC_{marker}__0\n")

        worker = threading.Thread(target=producer, daemon=True)
        worker.start()
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            runner._run_command_via_persistent_shell_locked(
                "mkdir -p /tmp/x\ncat > /tmp/y <<'EOF'\nbody\nEOF",
                _budget=_TimeoutBudget.start(5, 5),
            )
        worker.join(timeout=2)
        self.assertIn("[cmd] server-a: cat > /tmp/y", out.getvalue())

    def test_verbose_probe_only_command_prints_nothing(self):
        runner = self._runner_with_queue()
        runner._verbose = True

        def producer():
            marker = self._await_marker(runner)
            runner._shell_queue.put(f"__vb_STDOUT_B64_BEGIN_{marker}__\n")
            runner._shell_queue.put(base64.b64encode(b"").decode() + "\n")
            runner._shell_queue.put(f"__vb_STDERR_B64_BEGIN_{marker}__\n")
            runner._shell_queue.put(base64.b64encode(b"").decode() + "\n")
            runner._shell_queue.put(f"__vb_RC_{marker}__0\n")

        worker = threading.Thread(target=producer, daemon=True)
        worker.start()
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            runner._run_command_via_persistent_shell_locked(
                "mkdir -p /tmp/x\n:\n{\n}",
                _budget=_TimeoutBudget.start(5, 5),
            )
        worker.join(timeout=2)
        self.assertEqual(out.getvalue(), "")

    def test_loop_notices_exhausted_budget_after_a_preamble_line(self):
        runner = self._runner_with_queue()

        class _Budget:
            timeout = 5.0

            def __init__(self):
                self._available = [5.0, 0.0]

            def available(self):
                return self._available.pop(0) if self._available else 0.0

            def remaining(self, _command):
                return 5.0

        runner._shell_queue.put("preamble\n")
        with mock.patch.object(
            runner, "_close_persistent_shell_locked"
        ) as closer:
            with self.assertRaises(subprocess.TimeoutExpired):
                runner._run_command_via_persistent_shell_locked(
                    "echo x", _budget=_Budget()
                )
        closer.assert_called_once()


class _TunnelProc:
    def __init__(self, *, rc=None, pid=4321, stderr_text=b""):
        self._rc = rc
        self.pid = pid
        self._stderr_text = stderr_text
        self.terminated = False
        self.killed = False

    def poll(self):
        return self._rc

    def terminate(self):
        self.terminated = True
        self._rc = -15

    def kill(self):
        self.killed = True
        self._rc = -9

    def wait(self, timeout=None):
        return self._rc


class TestTunnelBranches(unittest.TestCase):
    def test_discard_tunnel_stderr_swallows_oserror(self):
        runner = _runner()
        runner._tunnel_stderr_path = Path("R:/nope/tunnel.log")
        with mock.patch.object(Path, "unlink", side_effect=OSError("locked")):
            runner._discard_tunnel_stderr()
        self.assertIsNone(runner._tunnel_stderr_path)

    def test_note_tunnel_ready_records_external_and_owned(self):
        runner = _runner()
        runner._note_tunnel_ready(1234)
        self.assertTrue(runner._tunnel_using_external)
        self.assertEqual(runner._tunnel_local_port, 1234)

        proc = _TunnelProc(rc=None)
        runner._note_tunnel_ready(4321, proc)
        self.assertFalse(runner._tunnel_using_external)
        self.assertIs(runner._tunnel_proc, proc)
        self.assertEqual(runner._tunnel_pid, proc.pid)

    def test_note_tunnel_failure_backs_off_up_to_30s(self):
        runner = _runner()
        runner._tunnel_next_try_at = 0.0
        for _ in range(6):
            runner._note_tunnel_failure()
        delay = runner._tunnel_next_try_at - time.monotonic()
        self.assertLessEqual(delay, 30.0)
        self.assertGreater(delay, 0)

    def test_paramiko_forward_reuses_reachable_port(self):
        runner = _runner()
        runner._paramiko_backend = mock.Mock()
        with mock.patch.object(runner, "can_reach_port", return_value=True):
            self.assertIsNone(runner._start_port_forward_locked(6500, 0.1))
        self.assertTrue(runner._tunnel_using_external)

    def test_paramiko_forward_opens_and_records_process(self):
        runner = _runner()
        backend = mock.Mock()
        proc = _TunnelProc(rc=None)
        backend.open_port_forward.return_value = proc
        runner._paramiko_backend = backend
        with mock.patch.object(runner, "can_reach_port", return_value=False):
            opened = runner._start_port_forward_locked(6501, 0.1)
        self.assertIs(opened, proc)
        backend.open_port_forward.assert_called_once()

    def test_paramiko_forward_failure_enters_backoff(self):
        runner = _runner()
        backend = mock.Mock()
        backend.open_port_forward.side_effect = OSError("no forward")
        runner._paramiko_backend = backend
        with mock.patch.object(runner, "can_reach_port", return_value=False):
            with self.assertRaises(OSError):
                runner._start_port_forward_locked(6502, 0.1)
        self.assertGreaterEqual(runner._tunnel_failures, 1)
        with self.assertRaises(RuntimeError) as ctx:
            runner._start_port_forward_locked(6502, 0.1)
        self.assertIn("backoff", str(ctx.exception))

    def test_openssh_forward_without_user_targets_bare_host(self):
        runner = SSHRunner("server-a", user=None, backend="openssh",
                           control_master="disable")
        captured = {}

        def fake_popen(args, **kwargs):
            captured["args"] = args
            raise OSError("ssh missing")

        with mock.patch.object(runner, "can_reach_port", return_value=False), \
                mock.patch.object(subprocess, "Popen", side_effect=fake_popen):
            with self.assertRaises(OSError):
                runner._start_port_forward_locked(6503, 0.1)
        self.assertEqual(captured["args"][-1], "server-a")
        self.assertIsNone(runner._tunnel_stderr_path)

    def test_windows_forward_retries_transient_drop(self):
        runner = _runner(control_master="disable")
        attempts = {"count": 0}

        def fake_popen(args, **kwargs):
            attempts["count"] += 1
            if attempts["count"] > 1:
                raise OSError("ssh vanished")
            stream = kwargs.get("stderr")
            if hasattr(stream, "write"):
                stream.write(b"banner exchange timeout\n")
            return _TunnelProc(rc=1)

        with mock.patch.object(runner, "can_reach_port", return_value=False), \
                mock.patch.object(subprocess, "Popen", side_effect=fake_popen), \
                mock.patch.object(ssh_mod.time, "sleep", return_value=None):
            with self.assertRaises(OSError):
                runner._start_port_forward_locked(6504, 0.1)
        self.assertEqual(attempts["count"], 2, "transient drop must be retried")

    def test_windows_forward_reports_failure_after_three_attempts(self):
        runner = _runner(control_master="disable")

        def fake_popen(args, **kwargs):
            stream = kwargs.get("stderr")
            if hasattr(stream, "write"):
                stream.write(b"banner exchange timeout\n")
            return _TunnelProc(rc=1)

        with mock.patch.object(runner, "can_reach_port", return_value=False), \
                mock.patch.object(subprocess, "Popen", side_effect=fake_popen), \
                mock.patch.object(ssh_mod.time, "sleep", return_value=None):
            with self.assertRaises(RuntimeError) as ctx:
                runner._start_port_forward_locked(6505, 0.1)
        self.assertIn("failed to start on Windows", str(ctx.exception))
        self.assertGreaterEqual(runner._tunnel_failures, 1)

    def test_windows_forward_reuses_external_listener(self):
        runner = _runner(control_master="disable")
        proc = _TunnelProc(rc=None)
        real_monotonic = ssh_mod.time.monotonic
        base = real_monotonic()
        calls = {"n": 0}

        def clock():
            calls["n"] += 1
            if calls["n"] > 3:
                return base + 1000.0
            return base

        with mock.patch.object(
                runner, "can_reach_port", side_effect=[False, True]), \
                mock.patch.object(subprocess, "Popen", return_value=proc), \
                mock.patch.object(ssh_mod.time, "monotonic", side_effect=clock):
            result = runner._start_port_forward_locked(6506, 0.1)
        self.assertIsNone(result)
        self.assertTrue(runner._tunnel_using_external)

    def test_stop_port_forward_swallows_errors(self):
        runner = _runner()
        proc = _TunnelProc(rc=None)
        proc.terminate = mock.Mock(side_effect=OSError("already dead"))
        proc.wait = mock.Mock(side_effect=OSError("already dead"))
        runner._tunnel_proc = proc
        runner.stop_port_forward()
        self.assertIsNone(runner._tunnel_proc)

        runner._tunnel_pid = 9999
        with mock.patch.object(
            ssh_mod.os, "kill", side_effect=PermissionError("denied")
        ):
            runner.stop_port_forward()
        self.assertIsNone(runner._tunnel_pid)

    def test_stop_port_forward_closes_tunnel_stderr_pipe(self):
        """C2: 成功建立的隧道 stderr=PIPE 必须在 stop 时关闭，不能等 Popen GC。"""
        runner = _runner()
        proc = _TunnelProc(rc=None)
        proc.stderr = mock.Mock()
        runner._tunnel_proc = proc
        runner.stop_port_forward()
        proc.stderr.close.assert_called_once()

        runner._tunnel_proc = proc
        proc.stderr.close.side_effect = OSError("already closed")
        runner.stop_port_forward()  # 失败也要吞掉

    def test_is_tunnel_alive_and_pid_property(self):
        runner = _runner()
        runner._tunnel_local_port = 6507
        with mock.patch.object(runner, "can_reach_port", return_value=False):
            self.assertFalse(runner.is_tunnel_alive)

        proc = _TunnelProc(rc=None, pid=777)
        runner._tunnel_proc = proc
        runner._tunnel_local_port = None
        self.assertTrue(runner.is_tunnel_alive)
        self.assertEqual(runner.tunnel_pid, 777)

        runner._tunnel_proc = None
        runner._tunnel_using_external = True
        runner._tunnel_pid = 888
        with mock.patch.object(ssh_mod.os, "kill", return_value=None):
            self.assertTrue(runner.is_tunnel_alive)
        with mock.patch.object(
            ssh_mod.os, "kill", side_effect=ProcessLookupError("gone")
        ):
            self.assertFalse(runner.is_tunnel_alive)

    def test_can_reach_port_handles_refused_and_open(self):
        fake = mock.Mock()
        with mock.patch.object(
            ssh_mod.socket, "create_connection", return_value=fake
        ):
            self.assertTrue(SSHRunner.can_reach_port(6508))
        fake.close.assert_called_once()
        with mock.patch.object(
            ssh_mod.socket, "create_connection",
            side_effect=ConnectionRefusedError("closed"),
        ):
            self.assertFalse(SSHRunner.can_reach_port(6509))


class TestClosePersistentShell(unittest.TestCase):
    def test_close_swallows_every_error_and_kills_on_wait_timeout(self):
        runner = _runner(persistent_shell=True)
        proc = _FakeShellProc(
            rc=None,
            wait_error=subprocess.TimeoutExpired("shell", 5),
        )
        proc.stdin = mock.Mock()
        proc.stdin.close.side_effect = OSError("stdin closed")
        proc.stdout = mock.Mock()
        proc.stdout.close.side_effect = OSError("stdout closed")
        proc.close = mock.Mock(side_effect=RuntimeError("already gone"))
        reader = mock.Mock()
        reader.is_alive.return_value = True
        runner._shell_proc = proc
        runner._shell_queue = queue.Queue()
        runner._shell_reader = reader

        runner._close_persistent_shell_locked()
        self.assertTrue(proc.killed)
        reader.join.assert_called_once()
        self.assertIsNone(runner._shell_proc)
        self.assertIsNone(runner._shell_queue)
        self.assertIsNone(runner._shell_reader)

    def test_close_with_exhausted_budget_kills_without_waiting(self):
        runner = _runner(persistent_shell=True)
        proc = _FakeShellProc(rc=None)
        runner._shell_proc = proc
        budget = _TimeoutBudget(timeout=1, deadline=0.0)
        runner._close_persistent_shell_locked(_budget=budget)
        self.assertTrue(proc.killed)


class TestRunRemoteTask(unittest.TestCase):
    def test_missing_local_file_fails_before_upload(self):
        runner = mock.Mock()
        result = ssh_mod.run_remote_task(
            runner,
            work_dir_base="/tmp/work",
            run_id="r1",
            uploads=[(Path("no-such-local-file.bin"), "/remote/f.bin")],
            command="true",
        )
        self.assertFalse(result.success)
        self.assertIn("Local file not found", result.error)
        runner.upload_batch.assert_not_called()

    def test_upload_failure_short_circuits(self):
        runner = mock.Mock()
        runner.upload_batch.return_value = CommandResult(1, "", "upload boom")
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "f.bin"
            local.write_bytes(b"x")
            result = ssh_mod.run_remote_task(
                runner,
                work_dir_base="/tmp/work",
                run_id="r2",
                uploads=[(local, "/remote/f.bin")],
                command="true",
            )
        self.assertFalse(result.success)
        self.assertIn("Failed to upload", result.error)
        runner.run_command.assert_not_called()

    def test_timeout_and_oserror_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "f.bin"
            local.write_bytes(b"x")
            for error, expected in (
                (subprocess.TimeoutExpired("cmd", 600), "timed out"),
                (FileNotFoundError("ssh missing"), "SSH execution error"),
                (OSError("broken pipe"), "SSH execution error"),
            ):
                with self.subTest(error=type(error).__name__):
                    runner = mock.Mock()
                    runner.upload_batch.return_value = CommandResult(0, "", "")
                    runner.run_command.side_effect = error
                    result = ssh_mod.run_remote_task(
                        runner,
                        work_dir_base="/tmp/work",
                        run_id="r3",
                        uploads=[(local, "/remote/f.bin")],
                        command="run",
                    )
                    self.assertFalse(result.success)
                    self.assertIn(expected, result.error)

    def test_success_returns_command_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            local = Path(tmp) / "f.bin"
            local.write_bytes(b"x")
            runner = mock.Mock()
            runner.upload_batch.return_value = CommandResult(0, "", "")
            runner.run_command.return_value = CommandResult(0, "ok", "")
            result = ssh_mod.run_remote_task(
                runner,
                work_dir_base="/tmp/work",
                run_id="r4",
                uploads=[(local, "/remote/f.bin")],
                command="run",
            )
        self.assertTrue(result.success)
        self.assertEqual(result.stdout, "ok")
        self.assertIn("upload_total", result.timings)
        self.assertIn("remote_exec", result.timings)


if __name__ == "__main__":
    unittest.main()
