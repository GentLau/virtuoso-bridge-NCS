"""Supervisor internals: lifecycle branches, control channel, kill fallbacks.

Spec: 顶层补充 v27 §1/§1.1/§3.  These cases drive ``BusinessProcess`` and
``SameProcessManager`` **in process** with fake pipes/jobs, so every failure
branch (ready timeout, closed control channel, taskkill fallback, drain
timeout) is deterministic and needs neither Virtuoso nor real children.
The real-subprocess counterpart lives in
``test/offline/integration/test_supervisor_process.py``.
"""

from __future__ import annotations

import io
import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from server import supervisor as sup


class _Pipe:
    """Stream stand-in: yields queued lines, then blocks until closed.

    A real child's stdout must not EOF while the process is alive, otherwise
    ``_read_stdout`` would mark it exited; a ``StringIO`` would EOF instantly.
    """

    def __init__(self, lines=()):
        self._q: queue.Queue = queue.Queue()
        for line in lines:
            self._q.put(line)
        self._closed = threading.Event()
        self.written: list[str] = []

    def feed(self, line: str) -> None:
        self._q.put(line)

    def __iter__(self):
        while True:
            try:
                item = self._q.get(timeout=0.02)
            except queue.Empty:
                if self._closed.is_set():
                    return
                continue
            yield item

    def write(self, text: str) -> int:
        self.written.append(text)
        return len(text)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        self._closed.set()


class _CloseFailsPipe(_Pipe):
    def close(self) -> None:
        raise OSError("already closed")


_UNSET = object()


class _FakePopen:
    """Minimal ``subprocess.Popen[str]`` double used by ``BusinessProcess``."""

    def __init__(self, *, pid=4242, stdout=None, stderr=None, stdin=_UNSET,
                 rc=None, wait_timeout=False):
        self.pid = pid
        self.stdout = stdout
        self.stderr = stderr
        self.stdin = _Pipe() if stdin is _UNSET else stdin
        self._rc = rc
        self._wait_timeout = wait_timeout
        self.killed = False

    def poll(self):
        return self._rc

    def wait(self, timeout=None):
        if self._rc is not None:
            return self._rc
        if self._wait_timeout:
            raise subprocess.TimeoutExpired(cmd="fake-business", timeout=timeout)
        self._rc = 0
        return 0

    def kill(self):
        self.killed = True
        self._rc = -9


class _FakeJob:
    def __init__(self, *, assign=True, resume=True):
        self._assign = assign
        self._resume = resume
        self.closed = False
        self.assigned: list = []
        self.resumed: list = []

    def assign(self, proc):
        self.assigned.append(proc)
        return self._assign

    def resume(self, proc, timeout=2.0):
        self.resumed.append(proc)
        return self._resume

    def close(self):
        self.closed = True


def _ready_line(port=65001):
    return (
        sup.EVENT_PREFIX
        + json.dumps({"event": "ready", "pid": 4242, "port": port})
        + "\n"
    )


def _process(**kwargs):
    kwargs.setdefault("host", "127.0.0.1")
    kwargs.setdefault("port", 65001)
    kwargs.setdefault("work_dir", "C:/vb-work" if os.name == "nt" else "/tmp/vb-work")
    return sup.BusinessProcess(**kwargs)


class TestRedactArgs(unittest.TestCase):
    def test_redacts_both_token_forms_and_keeps_others(self):
        args = ["--host", "h", "--token", "secret", "--token=also", "--port", "1"]
        self.assertEqual(
            sup._redact_args(args),
            ["--host", "h", "--token", "***", "--token=***", "--port", "1"],
        )

    def test_token_at_end_masks_nothing_else(self):
        self.assertEqual(sup._redact_args(["--token"]), ["--token"])
        self.assertEqual(sup._redact_args([]), [])


class TestStart(unittest.TestCase):
    def _patch(self, popen, job):
        return (
            mock.patch.object(sup.subprocess, "Popen", return_value=popen),
            mock.patch.object(sup, "ProcessJob", return_value=job),
        )

    def test_default_python_is_interpreter_and_args_shape(self):
        proc = _process()
        self.assertEqual(proc.args[0], sys.executable)
        self.assertIn("--supervised", proc.args)
        self.assertEqual(proc.state, "crashed")

    def test_start_success_sets_ready_and_bound_port(self):
        stdout = _Pipe([_ready_line(65002)])
        popen = _FakePopen(stdout=stdout, stderr=_Pipe(), stdin=_Pipe())
        job = _FakeJob()
        p_popen, p_job = self._patch(popen, job)
        with p_popen, p_job:
            proc = _process()
            proc.start(timeout=5)
        self.assertEqual(proc.state, "ready")
        self.assertEqual(proc.bound_port, 65002)
        self.assertEqual(proc.pid, 4242)
        self.assertTrue(proc._job_bound)

    def test_start_restarts_over_existing_child(self):
        """A second ``start`` disposes the previous child before spawning."""
        stdout1 = _Pipe([_ready_line(65003)])
        popen1 = _FakePopen(pid=11, stdout=stdout1, stderr=_Pipe())
        stdout2 = _Pipe([_ready_line(65004)])
        popen2 = _FakePopen(pid=12, stdout=stdout2, stderr=_Pipe())
        p_popen, p_job = self._patch(popen1, _FakeJob())
        with p_popen, p_job:
            proc = _process()
            proc.start(timeout=5)
            with mock.patch.object(sup.subprocess, "Popen", return_value=popen2):
                proc.start(timeout=5)
        self.assertEqual(proc.pid, 12)
        self.assertEqual(proc.bound_port, 65004)

    def test_start_ready_timeout_reports_stderr_tail(self):
        popen = _FakePopen(
            stdout=_Pipe(), stderr=_Pipe(["boom: import failed\n"])
        )
        job = _FakeJob()
        p_popen, p_job = self._patch(popen, job)
        with p_popen, p_job:
            proc = _process()
            with self.assertRaises(RuntimeError) as ctx:
                proc.start(timeout=0.3)
        self.assertIn("did not become ready", str(ctx.exception))
        self.assertIn("boom: import failed", str(ctx.exception))
        self.assertEqual(proc.state, "crashed")
        self.assertIsNone(proc._proc)

    def test_start_popen_failure_closes_job_and_raises(self):
        job = _FakeJob()
        with mock.patch.object(
            sup.subprocess, "Popen", side_effect=OSError("cannot spawn")
        ), mock.patch.object(sup, "ProcessJob", return_value=job):
            proc = _process()
            with self.assertRaises(OSError):
                proc.start(timeout=1)
        self.assertTrue(job.closed)
        self.assertIsNone(proc._job)

    def test_start_keeps_existing_pythonpath_without_duplicating_src(self):
        """src 已在 PYTHONPATH 时不再重复前置（重启不膨胀环境变量）。"""
        src = str(Path(sup.__file__).resolve().parents[1])
        stdout = _Pipe([_ready_line(65006)])
        popen = _FakePopen(stdout=stdout, stderr=_Pipe())
        captured = {}

        def fake_popen(args, **kwargs):
            captured.update(kwargs)
            return popen

        with mock.patch.dict(os.environ, {"PYTHONPATH": src + os.pathsep + "x"}):
            with mock.patch.object(sup.subprocess, "Popen", fake_popen), \
                    mock.patch.object(sup, "ProcessJob", return_value=_FakeJob()):
                _process().start(timeout=5)
        self.assertEqual(captured["env"]["PYTHONPATH"], src + os.pathsep + "x")

    @unittest.skipUnless(os.name == "nt", "Windows Job Object binding")
    def test_start_job_bind_failure_refuses_degraded_cleanup(self):
        popen = _FakePopen(stdout=_Pipe(), stderr=_Pipe())
        job = _FakeJob(assign=False)
        p_popen, p_job = self._patch(popen, job)
        with p_popen, p_job:
            proc = _process()
            with self.assertRaises(RuntimeError) as ctx:
                proc.start(timeout=1)
        self.assertIn("could not bind", str(ctx.exception))
        self.assertTrue(job.closed)
        self.assertIsNone(proc._proc)

    @unittest.skipIf(os.name == "nt", "POSIX session leader branch")
    def test_start_posix_uses_new_session(self):
        stdout = _Pipe([_ready_line(65005)])
        popen = _FakePopen(stdout=stdout, stderr=_Pipe())
        captured = {}

        def fake_popen(args, **kwargs):
            captured.update(kwargs)
            return popen

        with mock.patch.object(sup.subprocess, "Popen", fake_popen), \
                mock.patch.object(sup, "ProcessJob", return_value=_FakeJob()):
            proc = _process()
            proc.start(timeout=5)
        self.assertTrue(captured.get("start_new_session"))
        self.assertEqual(proc._posix_group_pid, popen.pid)


class TestStreamReaders(unittest.TestCase):
    def test_read_stdout_filters_noise_and_bad_json(self):
        stdout = _Pipe([
            "plain log line\n",
            sup.EVENT_PREFIX + "{not json}\n",
            sup.EVENT_PREFIX + '{"event":"ready","port":1}\n',
        ])
        stdout.close()  # EOF: the child has exited
        proc = _process()
        proc._proc = _FakePopen(stdout=stdout)
        proc._read_stdout()
        self.assertEqual(proc._events, [{"event": "ready", "port": 1}])
        self.assertEqual(proc.state, "crashed")

    def test_read_stdout_without_stdout_returns(self):
        proc = _process()
        proc._proc = None
        proc._read_stdout()  # no proc: early return
        proc._proc = _FakePopen(stdout=None)
        proc._read_stdout()  # no pipe: early return

    def test_read_stdout_eof_marks_stopped_while_shutting_down(self):
        stdout = _Pipe()
        stdout.close()
        proc = _process()
        proc._shutting_down = True
        job = _FakeJob()
        proc._job = job
        proc._proc = _FakePopen(stdout=stdout)
        proc._read_stdout()
        self.assertEqual(proc.state, "stopped")
        self.assertTrue(job.closed)

    def test_mark_exit_ignores_stale_reader(self):
        """restart 期间旧读取线程收尾时，不得改动新子进程的状态/job。"""
        current = _FakePopen(pid=2)
        stale = _FakePopen(pid=1)
        job = _FakeJob()
        proc = _process()
        proc._proc = current
        proc._job = job
        proc.state = "ready"
        proc._mark_exit(stale)
        self.assertEqual(proc.state, "ready")
        self.assertFalse(job.closed)
        self.assertIs(proc._job, job)

    def test_read_stderr_keeps_only_tail_window(self):
        stream = _Pipe([f"line-{i}\n" for i in range(60)])
        stream.close()
        proc = _process()
        proc._proc = _FakePopen(stderr=stream)
        proc._read_stderr()
        self.assertEqual(len(proc._stderr_tail), 50)
        self.assertEqual(proc._stderr_tail[0], "line-10")
        self.assertEqual(proc._stderr_tail[-1], "line-59")

    def test_read_stderr_without_stream_returns(self):
        proc = _process()
        proc._proc = None
        proc._read_stderr()
        proc._proc = _FakePopen(stderr=None)
        proc._read_stderr()


class TestControlChannel(unittest.TestCase):
    def test_send_refuses_when_no_process(self):
        proc = _process()
        self.assertFalse(proc._send("reload"))

    def test_send_refuses_without_stdin_and_after_exit(self):
        proc = _process()
        proc._proc = _FakePopen(stdin=None)
        self.assertFalse(proc._send("reload"))
        proc._proc = _FakePopen(rc=3)
        self.assertFalse(proc._send("reload"))

    def test_send_writes_json_line(self):
        stdin = _Pipe()
        proc = _process()
        proc._proc = _FakePopen(stdin=stdin)
        self.assertTrue(proc._send("drain"))
        self.assertEqual(json.loads(stdin.written[0]), {"cmd": "drain"})

    def test_send_returns_false_on_broken_pipe(self):
        class _Broken(_Pipe):
            def write(self, text):
                raise OSError("broken pipe")

        proc = _process()
        proc._proc = _FakePopen(stdin=_Broken())
        self.assertFalse(proc._send("reload"))

    def test_wait_event_returns_then_times_out(self):
        proc = _process()
        proc._events.append({"event": "ready", "port": 7})
        self.assertEqual(proc.wait_event("ready", 0.5)["port"], 7)
        self.assertIsNone(proc.wait_event("ready", 0.01))
        # the matched event is consumed, never delivered twice
        self.assertEqual(proc._events, [])

    def test_wait_exit_without_proc_is_true(self):
        self.assertTrue(_process()._wait_exit(0.1))

    def test_wait_exit_reports_timeout(self):
        proc = _process()
        proc._proc = _FakePopen(wait_timeout=True)
        self.assertFalse(proc._wait_exit(0.01))


class TestDisposeChild(unittest.TestCase):
    def test_dispose_without_proc_or_job_is_a_noop(self):
        proc = _process()
        proc._dispose_child(0.1)
        self.assertIsNone(proc._proc)

    def test_dispose_without_proc_closes_pending_job(self):
        proc = _process()
        job = _FakeJob()
        proc._job = job
        proc._dispose_child(0.1)
        self.assertTrue(job.closed)

    def test_dispose_skips_kill_when_child_already_exited(self):
        popen = _FakePopen(rc=0, stdout=_Pipe(), stderr=_Pipe())
        proc = _process()
        proc._proc = popen
        proc._dispose_child(0.1)
        self.assertFalse(popen.killed)
        self.assertIsNone(proc._proc)

    def test_dispose_force_kills_when_wait_times_out(self):
        popen = _FakePopen(wait_timeout=True)
        proc = _process()
        proc._proc = popen
        proc._job = _FakeJob()
        proc._job_bound = True
        killed = []
        with mock.patch.object(
            sup.BusinessProcess,
            "_force_kill_tree",
            staticmethod(lambda p, *, job_bound: killed.append(job_bound)),
        ):
            proc._dispose_child(0.01)
        self.assertEqual(killed, [True])
        self.assertIsNone(proc._proc)

    def test_dispose_ignores_stream_close_errors(self):
        popen = _FakePopen(
            stdout=_CloseFailsPipe(), stderr=_CloseFailsPipe(), stdin=_CloseFailsPipe()
        )
        job = _FakeJob()
        proc = _process()
        proc._proc = popen
        proc._job = job
        proc._dispose_child(0.1)
        self.assertTrue(job.closed)
        self.assertIsNone(proc._proc)


class TestForceKillTree(unittest.TestCase):
    def test_signal_process_group_swallows_oserror(self):
        with mock.patch.object(
            os, "killpg", side_effect=OSError("gone"), create=True
        ):
            sup.BusinessProcess._signal_process_group(123, 15)

    def test_signal_process_group_calls_killpg(self):
        with mock.patch.object(os, "killpg", create=True) as killpg:
            sup.BusinessProcess._signal_process_group(123, 15)
        killpg.assert_called_once_with(123, 15)

    @unittest.skipUnless(os.name == "nt", "taskkill fallback is Windows-only")
    def test_taskkill_success_returns_without_kill(self):
        popen = _FakePopen(rc=None)
        with mock.patch.object(
            sup.subprocess, "run",
            return_value=subprocess.CompletedProcess(["taskkill"], 0),
        ):
            sup.BusinessProcess._force_kill_tree(popen, job_bound=True)
        self.assertFalse(popen.killed)

    @unittest.skipUnless(os.name == "nt", "taskkill fallback is Windows-only")
    def test_taskkill_failure_without_job_kills_directly(self):
        popen = _FakePopen(rc=None)
        with mock.patch.object(
            sup.subprocess, "run",
            return_value=subprocess.CompletedProcess(["taskkill"], 128),
        ):
            sup.BusinessProcess._force_kill_tree(popen, job_bound=False)
        self.assertTrue(popen.killed)

    @unittest.skipUnless(os.name == "nt", "taskkill fallback is Windows-only")
    def test_taskkill_error_with_job_bound_defers_to_job(self):
        for error in (OSError("no taskkill"), subprocess.TimeoutExpired("taskkill", 10)):
            with self.subTest(error=type(error).__name__):
                popen = _FakePopen(rc=None)
                with mock.patch.object(sup.subprocess, "run", side_effect=error):
                    sup.BusinessProcess._force_kill_tree(popen, job_bound=True)
                self.assertFalse(popen.killed)

    @unittest.skipUnless(os.name == "nt", "direct kill fallback is Windows-only")
    def test_direct_kill_error_is_swallowed(self):
        popen = _FakePopen(rc=None)
        popen.kill = mock.Mock(side_effect=OSError("access denied"))
        with mock.patch.object(
            sup.subprocess, "run",
            return_value=subprocess.CompletedProcess(["taskkill"], 128),
        ):
            sup.BusinessProcess._force_kill_tree(popen, job_bound=False)
        popen.kill.assert_called_once()

    @unittest.skipIf(os.name == "nt", "POSIX process-group kill path")
    def test_posix_group_sigterm_success_returns(self):
        popen = _FakePopen(rc=None)
        with mock.patch.object(sup.BusinessProcess, "_signal_process_group") as sig:
            sup.BusinessProcess._force_kill_tree(popen, job_bound=False)
        sig.assert_called_once_with(popen.pid, signal.SIGTERM)
        self.assertFalse(popen.killed)

    @unittest.skipIf(os.name == "nt", "POSIX process-group kill path")
    def test_posix_group_sigkills_after_sigterm_timeout(self):
        popen = _FakePopen(rc=None, wait_timeout=True)
        with mock.patch.object(sup.BusinessProcess, "_signal_process_group") as sig:
            sup.BusinessProcess._force_kill_tree(popen, job_bound=False)
        self.assertEqual(
            [call.args[1] for call in sig.call_args_list],
            [signal.SIGTERM, signal.SIGKILL],
        )


class TestManagementApi(unittest.TestCase):
    def test_status_redacts_token_and_reports_port(self):
        proc = _process(port=65010)
        proc.args = ["python", "-m", "server.api_server", "--token", "s3cret"]
        payload = proc.status()
        self.assertEqual(payload["state"], "crashed")
        self.assertEqual(payload["port"], 65010)
        self.assertIn("***", payload["startup_args"])
        self.assertNotIn("s3cret", payload["startup_args"])

    def test_reload_requires_ready_state(self):
        proc = _process()
        proc.state = "crashed"
        with self.assertRaises(RuntimeError) as ctx:
            proc.reload(timeout=0.1)
        self.assertIn("not ready", str(ctx.exception))

    def test_reload_reports_closed_channel(self):
        proc = _process()
        proc.state = "ready"
        proc._send = lambda command: False
        with self.assertRaises(RuntimeError) as ctx:
            proc.reload(timeout=0.1)
        self.assertIn("closed", str(ctx.exception))

    def test_reload_reports_timeout(self):
        proc = _process()
        proc.state = "ready"
        proc._send = lambda command: True
        proc.wait_event = lambda name, timeout: None
        with self.assertRaises(RuntimeError) as ctx:
            proc.reload(timeout=0.1)
        self.assertIn("timed out", str(ctx.exception))

    def test_reload_reports_child_error(self):
        proc = _process()
        proc.state = "ready"
        proc._send = lambda command: True
        proc.wait_event = lambda name, timeout: {"event": "reload_done", "ok": False,
                                                 "error": "BadRegistry"}
        with self.assertRaises(RuntimeError) as ctx:
            proc.reload(timeout=0.1)
        self.assertIn("BadRegistry", str(ctx.exception))

    def test_reload_success_returns_status(self):
        proc = _process()
        proc.state = "ready"
        sent = []
        proc._send = lambda command: sent.append(command) or True
        proc.wait_event = lambda name, timeout: {"event": "reload_done", "ok": True}
        payload = proc.reload(timeout=0.1)
        self.assertEqual(sent, ["reload"])
        self.assertEqual(payload["state"], "ready")

    def test_restart_without_proc_starts_fresh_child(self):
        proc = _process()
        started = []
        proc.start = lambda timeout=None: started.append(timeout)
        proc.restart(timeout=0.5)
        self.assertEqual(started, [0.5])

    def test_restart_running_child_drains_then_starts(self):
        proc = _process()
        proc._proc = _FakePopen(rc=None)
        sent = []
        proc._send = lambda command: sent.append(command) or True
        proc.wait_event = lambda name, timeout: {"event": "drain_done"}
        proc._wait_exit = lambda timeout: True
        started = []
        proc.start = lambda timeout=None: started.append(timeout)
        with mock.patch.object(proc, "_dispose_child") as dispose:
            proc.restart(timeout=0.5)
        self.assertEqual(sent, ["drain"])
        dispose.assert_called_once()
        self.assertEqual(started, [0.5])
        self.assertFalse(proc._shutting_down)

    def test_restart_kills_child_when_drain_times_out(self):
        proc = _process()
        popen = _FakePopen(rc=None)
        proc._proc = popen
        proc._send = lambda command: True
        proc.wait_event = lambda name, timeout: None
        proc._wait_exit = lambda timeout: False
        proc.start = lambda timeout=None: None
        with mock.patch.object(proc, "_dispose_child"):
            proc.restart(timeout=0.1)
        self.assertTrue(popen.killed)

    def test_shutdown_without_proc_disposes_and_returns(self):
        proc = _process()
        with mock.patch.object(proc, "_dispose_child") as dispose:
            proc.shutdown(timeout=0.1)
        dispose.assert_called_once_with(5.0)

    def test_shutdown_running_child_drains(self):
        proc = _process()
        popen = _FakePopen(rc=None)
        proc._proc = popen
        sent = []
        proc._send = lambda command: sent.append(command) or True
        proc.wait_event = lambda name, timeout: {"event": "drain_done"}
        proc._wait_exit = lambda timeout: True
        with mock.patch.object(proc, "_dispose_child") as dispose:
            proc.shutdown(timeout=0.1)
        self.assertEqual(sent, ["drain"])
        self.assertTrue(proc._shutting_down)
        dispose.assert_called_once_with(5.0)

    def test_shutdown_kills_child_when_drain_times_out(self):
        proc = _process()
        popen = _FakePopen(rc=None)
        proc._proc = popen
        proc._send = lambda command: True
        proc.wait_event = lambda name, timeout: None
        proc._wait_exit = lambda timeout: False
        with mock.patch.object(proc, "_dispose_child") as dispose:
            proc.shutdown(timeout=0.1)
        self.assertTrue(popen.killed)
        dispose.assert_called_once_with(5.0)


class _FakeBusinessServerForSameProcess:
    def __init__(self, *, draining=False, port=8127):
        self.draining = draining
        self.server_address = ("127.0.0.1", port)


class TestSameProcessManager(unittest.TestCase):
    def _manager(self, *, draining=False):
        middle = mock.Mock()
        server = _FakeBusinessServerForSameProcess(draining=draining)
        return sup.SameProcessManager(middle, server), middle, server

    def test_same_process_flag(self):
        self.assertTrue(sup.SameProcessManager.same_process)

    def test_status_ready_and_draining(self):
        with mock.patch.object(sup, "work_root", return_value=Path("/vb-work")):
            manager, _middle, _server = self._manager()
            self.assertEqual(manager.status()["state"], "ready")
            manager, _middle, _server = self._manager(draining=True)
            self.assertEqual(manager.status()["state"], "draining")

    def test_reload_success_and_failure(self):
        with mock.patch.object(sup, "work_root", return_value=Path("/vb-work")):
            manager, middle, server = self._manager()
            with mock.patch(
                "server.api_server.reload_business_state",
                return_value=(True, None),
            ) as reload_state:
                payload = manager.reload()
            reload_state.assert_called_once_with(server, middle)
            self.assertEqual(payload["state"], "ready")

            manager, _middle, _server = self._manager()
            with mock.patch(
                "server.api_server.reload_business_state",
                return_value=(False, "BadRegistry"),
            ):
                with self.assertRaises(RuntimeError) as ctx:
                    manager.reload()
            self.assertIn("BadRegistry", str(ctx.exception))

    def test_restart_is_refused_and_shutdown_is_noop(self):
        manager, _middle, _server = self._manager()
        with self.assertRaises(NotImplementedError):
            manager.restart()
        self.assertIsNone(manager.shutdown())


class TestBuildBusiness(unittest.TestCase):
    def test_build_wires_middle_and_pool_size(self):
        middle = object()
        server = object()
        with mock.patch("transport.middle.BusinessServer", return_value=middle) as _bs, \
                mock.patch("server.api_server.pool_size_from_snapshot",
                           return_value=7) as pool, \
                mock.patch("server.api_server.build_server",
                           return_value=server) as build, \
                mock.patch.object(sup, "init_work_dir") as init, \
                mock.patch.object(sup.config_base, "reload_config") as reload_cfg, \
                mock.patch.object(sup, "config_path", return_value="cfg.json"):
            got_middle, got_server = sup._build_business(
                "127.0.0.1", 8127, "workdir", single_process=True
            )
        self.assertIs(got_middle, middle)
        self.assertIs(got_server, server)
        init.assert_called_once_with("workdir")
        reload_cfg.assert_called_once_with("cfg.json")
        pool.assert_called_once()
        build.assert_called_once_with("127.0.0.1", 8127, middle, max_inflight=7)


class _FakeControlServer:
    def __init__(self, address, registry, manager):
        self.address = address
        self.registry = registry
        self.manager = manager
        self.closed = False
        self.serve_calls = 0

    def serve_forever(self):
        self.serve_calls += 1

    def server_close(self):
        self.closed = True


class _FakeBusinessHttpServer:
    def __init__(self):
        self.shutdown_called = False
        self.closed = False

    def serve_forever(self):
        return None

    def shutdown(self):
        self.shutdown_called = True

    def server_close(self):
        self.closed = True


class TestMain(unittest.TestCase):
    def test_single_process_serves_and_closes_everything(self):
        middle = mock.Mock()
        business_server = _FakeBusinessHttpServer()
        manager = mock.Mock()
        manager.shutdown = mock.Mock()
        captured = {}

        def fake_control(address, registry, mgr):
            captured["control"] = _FakeControlServer(address, registry, mgr)
            return captured["control"]

        with mock.patch.object(sup, "init_work_dir"), \
                mock.patch.object(sup, "work_root", return_value=Path("/vb-work")), \
                mock.patch.object(sup, "load_registry", return_value=object()), \
                mock.patch.object(sup, "registry_path", return_value="r.json"), \
                mock.patch.object(sup, "command_log_file", return_value="c.log"), \
                mock.patch("common.ssh.configure_command_log"), \
                mock.patch.object(sup, "_build_business",
                                  return_value=(middle, business_server)), \
                mock.patch.object(sup, "SameProcessManager", return_value=manager), \
                mock.patch.object(sup, "RegistrationServer", side_effect=fake_control):
            sup.main(["--single-process"])

        control = captured["control"]
        self.assertEqual(control.serve_calls, 1)
        self.assertTrue(control.closed)
        manager.shutdown.assert_called_once()
        self.assertTrue(business_server.shutdown_called)
        self.assertTrue(business_server.closed)
        middle.close.assert_called_once()

    def test_standard_mode_reports_child_start_failure_and_closes(self):
        manager = mock.Mock()
        manager.start.side_effect = RuntimeError("no child")
        manager.shutdown = mock.Mock()
        control = _FakeControlServer(None, None, None)
        stderr = io.StringIO()
        with mock.patch.object(sup, "init_work_dir"), \
                mock.patch.object(sup, "work_root", return_value=Path("/vb-work")), \
                mock.patch.object(sup, "load_registry", return_value=object()), \
                mock.patch.object(sup, "registry_path", return_value="r.json"), \
                mock.patch.object(sup, "command_log_file", return_value="c.log"), \
                mock.patch("common.ssh.configure_command_log"), \
                mock.patch.object(sup, "BusinessProcess", return_value=manager), \
                mock.patch.object(sup, "RegistrationServer", return_value=control), \
                mock.patch.object(sys, "stderr", stderr):
            sup.main([])
        self.assertIn("business child failed to start", stderr.getvalue())
        self.assertTrue(control.closed)
        manager.shutdown.assert_called_once()

    def test_keyboard_interrupt_still_closes_control_face(self):
        control = _FakeControlServer(None, None, None)
        control.serve_forever = mock.Mock(side_effect=KeyboardInterrupt)
        manager = mock.Mock()
        with mock.patch.object(sup, "init_work_dir"), \
                mock.patch.object(sup, "work_root", return_value=Path("/vb-work")), \
                mock.patch.object(sup, "load_registry", return_value=object()), \
                mock.patch.object(sup, "registry_path", return_value="r.json"), \
                mock.patch.object(sup, "command_log_file", return_value="c.log"), \
                mock.patch("common.ssh.configure_command_log"), \
                mock.patch.object(sup, "BusinessProcess", return_value=manager), \
                mock.patch.object(sup, "RegistrationServer", return_value=control):
            sup.main([])
        self.assertTrue(control.closed)
        manager.shutdown.assert_called_once()

    def test_shutdown_failure_is_swallowed_on_exit(self):
        control = _FakeControlServer(None, None, None)
        manager = mock.Mock()
        manager.shutdown.side_effect = RuntimeError("already gone")
        with mock.patch.object(sup, "init_work_dir"), \
                mock.patch.object(sup, "work_root", return_value=Path("/vb-work")), \
                mock.patch.object(sup, "load_registry", return_value=object()), \
                mock.patch.object(sup, "registry_path", return_value="r.json"), \
                mock.patch.object(sup, "command_log_file", return_value="c.log"), \
                mock.patch("common.ssh.configure_command_log"), \
                mock.patch.object(sup, "BusinessProcess", return_value=manager), \
                mock.patch.object(sup, "RegistrationServer", return_value=control):
            sup.main([])
        self.assertTrue(control.closed)


if __name__ == "__main__":
    unittest.main()
