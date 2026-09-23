"""Top-layer assembly and supervised control loop (离线).

Spec: 顶层补充 v27 §1.1/§3 — the business child speaks a stdin-command /
stdout-event protocol with the supervisor.  Subprocess TBs exercise it for
real (``test/offline/integration/test_business_child_supervision.py``); this
file drives the same loop in-process so the branches are actually *measured*
and the negative cases are one-liners.
"""

from __future__ import annotations

import io
import http.client
import json
import socket
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pydantic import BaseModel

from server import api_server
from server import dispatch as dispatch_module


class _FakeHttpServer:
    def __init__(self, *, port=8127, drain=True):
        self.server_address = ("127.0.0.1", port)
        self.draining = False
        self.drain_result = drain
        self.wait_idle_calls: list[float] = []
        self.shutdown_called = 0
        self.closed = 0

    def wait_idle(self, timeout):
        self.wait_idle_calls.append(timeout)
        return self.drain_result

    def shutdown(self):
        self.shutdown_called += 1

    def server_close(self):
        self.closed += 1


class TestPoolSizeHelpers(unittest.TestCase):
    def test_pool_size_from_snapshot_rejects_invalid_values(self):
        self.assertEqual(api_server.pool_size_from_snapshot({}), 1024)
        for value in (True, False, "64", 0, -3, None, 1.5):
            with self.subTest(value=value):
                self.assertEqual(
                    api_server.pool_size_from_snapshot(
                        {"business_thread_pool_size": value}
                    ),
                    1024,
                )
        self.assertEqual(
            api_server.pool_size_from_snapshot(
                {"business_thread_pool_size": 3}
            ),
            3,
        )
        self.assertEqual(
            api_server.pool_size_from_snapshot({}, default=8), 8
        )

    def test_load_business_thread_pool_size_reads_config_file(self):
        with mock.patch.object(
            api_server.config_base,
            "load_config_file",
            return_value={"business_thread_pool_size": 12},
        ):
            self.assertEqual(
                api_server.load_business_thread_pool_size(Path("config.json")),
                12,
            )


class TestRegisterPackages(unittest.TestCase):
    def test_broken_package_is_isolated_and_good_one_registers(self):
        calls = []
        rows = (
            ("definitely.not.a.module", "Package", "OPERATIONS"),
            ("pyapi.packages.basic", "Package", "OPERATIONS"),
        )
        errors_seen = {}
        with mock.patch.object(api_server, "PACKAGES", rows), \
                mock.patch.object(
                    dispatch_module, "register_operation",
                    side_effect=lambda *a, **kw: calls.append(a),
                ), \
                mock.patch.dict(
                    dispatch_module.PACKAGE_LOAD_ERRORS, errors_seen, clear=True
                ):
            errors = api_server.register_packages()
            seen = dict(dispatch_module.PACKAGE_LOAD_ERRORS)
        self.assertIn("definitely.not.a.module", errors)
        self.assertIn(
            "ModuleNotFoundError", errors["definitely.not.a.module"]
        )
        self.assertEqual(
            seen["definitely.not.a.module"],
            errors["definitely.not.a.module"],
        )
        self.assertNotIn("pyapi.packages.basic", errors)
        self.assertTrue(calls, "the healthy package must still register")


class TestBuildMiddle(unittest.TestCase):
    def test_build_middle_initializes_paths_then_wires_business_server(self):
        middle = object()
        with mock.patch("transport.middle.BusinessServer",
                        return_value=middle) as business, \
                mock.patch.object(api_server, "init_work_dir") as init, \
                mock.patch.object(api_server.config_base, "reload_config") as reload_cfg, \
                mock.patch.object(api_server, "config_path",
                                  return_value="cfg.json"):
            got = api_server.build_middle("work")
        self.assertIs(got, middle)
        init.assert_called_once_with("work")
        reload_cfg.assert_called_once_with("cfg.json")
        business.assert_called_once()


class TestEmitAndDrain(unittest.TestCase):
    def test_emit_event_writes_one_prefixed_line(self):
        out = io.StringIO()
        with mock.patch.object(sys, "stdout", out):
            api_server._emit_event(event="ready", port=1)
        line = out.getvalue()
        self.assertTrue(line.startswith(api_server.EVENT_PREFIX))
        self.assertEqual(json.loads(line[len(api_server.EVENT_PREFIX):]),
                         {"event": "ready", "port": 1})

    def test_emit_event_swallows_broken_stdout(self):
        class _Broken:
            def write(self, _text):
                raise OSError("closed")

            def flush(self):
                raise OSError("closed")

        with mock.patch.object(sys, "stdout", _Broken()):
            api_server._emit_event(event="ready")  # must not raise

    def test_drain_and_stop_closes_everything(self):
        server = _FakeHttpServer(drain=False)
        middle = mock.Mock()
        idle = api_server.drain_and_stop(server, middle, timeout=0.5)
        self.assertFalse(idle)
        self.assertTrue(server.draining)
        self.assertEqual(server.wait_idle_calls, [0.5])
        self.assertEqual(server.shutdown_called, 1)
        self.assertEqual(server.closed, 1)
        middle.close.assert_called_once()

    def test_drain_and_stop_closes_even_when_shutdown_raises(self):
        server = _FakeHttpServer()
        server.shutdown = mock.Mock(side_effect=RuntimeError("boom"))
        middle = mock.Mock()
        with self.assertRaises(RuntimeError):
            api_server.drain_and_stop(server, middle, timeout=0.1)
        self.assertEqual(server.closed, 1)
        middle.close.assert_called_once()


class TestSupervisedLoop(unittest.TestCase):
    def _run(self, commands: str, *, server=None, middle=None, reload_result=None):
        server = server or _FakeHttpServer()
        middle = middle or mock.Mock()
        out = io.StringIO()
        patches = [
            mock.patch.object(sys, "stdin", io.StringIO(commands)),
            mock.patch.object(sys, "stdout", out),
            mock.patch.object(api_server, "work_root", return_value=Path("w")),
        ]
        if reload_result is not None:
            patches.append(mock.patch.object(
                api_server, "reload_business_state", return_value=reload_result
            ))
        for p in patches:
            p.start()
        try:
            api_server._supervised_loop(server, middle)
        finally:
            for p in reversed(patches):
                p.stop()
        events = [
            json.loads(line[len(api_server.EVENT_PREFIX):])
            for line in out.getvalue().splitlines()
            if line.startswith(api_server.EVENT_PREFIX)
        ]
        return events, server, middle

    def test_ready_event_announces_port_and_work_dir(self):
        events, server, middle = self._run("")
        self.assertEqual(events[0]["event"], "ready")
        self.assertEqual(events[0]["port"], 8127)
        # stdin EOF is the parent-exit path: drain silently, no event stream
        self.assertEqual([e["event"] for e in events], ["ready"])
        self.assertEqual(server.shutdown_called, 1)
        middle.close.assert_called_once()

    def test_invalid_and_unknown_commands_report_errors(self):
        commands = "\n".join([
            "{not json",
            "[1, 2]",
            json.dumps({"cmd": "nonsense"}),
            "",
        ])
        events, _server, _middle = self._run(commands)
        errors = [e for e in events if e["event"] == "error"]
        self.assertEqual(len(errors), 3)
        self.assertEqual(errors[0]["error"], "invalid control command")
        self.assertEqual(errors[1]["error"], "invalid control command")
        self.assertIn("unknown command", errors[2]["error"])

    def test_reload_reports_result_from_business_state(self):
        events, _server, _middle = self._run(
            json.dumps({"cmd": "reload"}) + "\n",
            reload_result=(False, "BadRegistry"),
        )
        done = [e for e in events if e["event"] == "reload_done"]
        self.assertEqual(done, [{"event": "reload_done", "ok": False,
                                 "error": "BadRegistry"}])

    def test_shutdown_command_drains_then_returns(self):
        events, server, middle = self._run(
            json.dumps({"cmd": "shutdown"}) + "\n"
        )
        self.assertEqual(
            [e["event"] for e in events],
            ["ready", "drain_started", "drain_done"],
        )
        self.assertTrue(events[-1]["ok"])
        self.assertEqual(server.shutdown_called, 1)
        middle.close.assert_called_once()

    def test_eof_drains_without_sending_drain_events(self):
        events, server, middle = self._run("")
        self.assertEqual([e["event"] for e in events], ["ready"])
        self.assertEqual(server.shutdown_called, 1)
        middle.close.assert_called_once()


class _FakeThread:
    created: list[dict] = []

    def __init__(self, **kwargs):
        _FakeThread.created.append(kwargs)
        self.kwargs = kwargs

    def start(self):
        return None

    def join(self, timeout=None):
        return None


class TestMain(unittest.TestCase):
    def _run_main(self, argv, *, serve_error=None, stderr=None):
        server = mock.Mock()
        if serve_error is not None:
            server.serve_forever.side_effect = serve_error
        middle = mock.Mock()
        _FakeThread.created = []
        patches = [
            mock.patch.object(api_server, "register_packages",
                              return_value={"bogus": "ModuleNotFoundError"}),
            mock.patch("transport.middle.BusinessServer", return_value=middle),
            mock.patch.object(api_server, "init_work_dir"),
            mock.patch.object(api_server.config_base, "init_config"),
            mock.patch.object(api_server.config_base, "snapshot",
                              return_value={"business_thread_pool_size": 2}),
            mock.patch.object(api_server, "config_path", return_value="cfg.json"),
            mock.patch.object(api_server, "build_server", return_value=server),
            mock.patch.object(api_server.threading, "Thread", _FakeThread),
        ]
        if stderr is not None:
            patches.append(mock.patch.object(sys, "stderr", stderr))
        for p in patches:
            p.start()
        try:
            api_server.main(argv)
        finally:
            for p in reversed(patches):
                p.stop()
        return server, middle

    def test_supervised_mode_starts_control_loop_and_uses_stderr_banner(self):
        stderr = io.StringIO()
        server, middle = self._run_main(
            ["--supervised", "--port", "0"], stderr=stderr
        )
        self.assertTrue(_FakeThread.created)
        self.assertIs(
            _FakeThread.created[0]["target"], api_server._supervised_loop
        )
        self.assertIn("API (business)", stderr.getvalue())
        server.server_close.assert_called_once()
        middle.close.assert_called_once()

    def test_plain_mode_prints_banner_and_closes_on_interrupt(self):
        server, middle = self._run_main(
            ["--port", "0"], serve_error=KeyboardInterrupt
        )
        self.assertEqual(_FakeThread.created, [])
        server.server_close.assert_called_once()
        middle.close.assert_called_once()


class _OpRequest(BaseModel):
    token: str = "tok"


class _OpPackage:
    def __init__(self, middle):
        self.middle = middle

    def nan(self, request):
        return float("nan")


class TestHttpSurface(unittest.TestCase):
    """Route-level branches of the business face (loopback, 127.0.0.1:0)."""

    OPERATION = "tb.api.nan"

    def setUp(self):
        dispatch_module.register_operation(
            self.OPERATION, _OpPackage, "nan", _OpRequest, replace=True
        )
        self.server = api_server.build_server(
            "127.0.0.1", 0, object(), max_inflight=4
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        dispatch_module.PACKAGES.pop(self.OPERATION, None)

    def _request(self, method, path, body=None, raw=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        payload = raw if raw is not None else (
            None if body is None else json.dumps(body)
        )
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, path, payload, headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def _raw_socket(self, request: bytes) -> bytes:
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
        try:
            sock.sendall(request)
            sock.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            return b"".join(chunks)
        finally:
            sock.close()

    def test_help_and_unknown_paths(self):
        resp, data = self._request("GET", "/help")
        self.assertEqual(resp.status, 200, data)
        self.assertIn("POST /api/operation", data.decode("utf-8"))

        resp, data = self._request("GET", "/no-such-path")
        self.assertEqual(resp.status, 404, data)

        resp, data = self._request("POST", "/no-such-path", {})
        self.assertEqual(resp.status, 404, data)

    def test_connect_is_405(self):
        data = self._raw_socket(
            b"CONNECT /api/operation HTTP/1.1\r\nHost: x\r\n"
            b"Content-Length: 0\r\n\r\n"
        )
        self.assertIn(b" 405 ", data.split(b"\r\n", 1)[0], data[:200])

    def test_bad_content_lengths_and_undecodable_body_are_400(self):
        for label, request in (
            ("negative", b"POST /api/operation HTTP/1.1\r\nHost: x\r\n"
                         b"Content-Length: -1\r\n\r\n"),
            ("empty", b"POST /api/operation HTTP/1.1\r\nHost: x\r\n"
                      b"Content-Length: 0\r\n\r\n"),
            ("undecodable", b"POST /api/operation HTTP/1.1\r\nHost: x\r\n"
                            b"Content-Length: 2\r\n\r\n\xff\xfe"),
        ):
            with self.subTest(label=label):
                data = self._raw_socket(request)
                self.assertIn(b" 400 ", data.split(b"\r\n", 1)[0], data[:300])
                self.assertIn(b"invalid JSON body", data)

    def test_drain_stops_when_peer_sends_short_body(self):
        data = self._raw_socket(
            b"PATCH /api/operation HTTP/1.1\r\nHost: x\r\n"
            b"Content-Length: 100\r\n\r\nxx"
        )
        self.assertIn(b" 405 ", data.split(b"\r\n", 1)[0], data[:300])

    def test_drain_ignores_unparsable_content_length(self):
        data = self._raw_socket(
            b"PATCH /api/operation HTTP/1.1\r\nHost: x\r\n"
            b"Content-Length: abc\r\n\r\nbody"
        )
        self.assertIn(b" 405 ", data.split(b"\r\n", 1)[0], data[:300])

    def test_unserializable_result_is_structured_500(self):
        resp, data = self._request(
            "POST", "/api/operation",
            {"operation": self.OPERATION, "token": "tok"},
        )
        self.assertEqual(resp.status, 500, data)
        self.assertIn("invalid response payload", data.decode("utf-8"))

    def test_server_refuses_non_positive_pool(self):
        with self.assertRaises(ValueError):
            api_server.build_server("127.0.0.1", 0, object(), max_inflight=0)


class TestReloadBusinessState(unittest.TestCase):
    def test_reload_applies_registry_and_pool_size(self):
        server = mock.Mock()
        middle = mock.Mock()
        with mock.patch.object(api_server.config_base, "reload_config"), \
                mock.patch.object(api_server, "config_path",
                                  return_value="cfg.json"), \
                mock.patch.object(api_server.config_base, "snapshot",
                                  return_value={"business_thread_pool_size": 5}):
            ok, error = api_server.reload_business_state(server, middle)
        self.assertTrue(ok)
        self.assertIsNone(error)
        middle.reload_registry.assert_called_once()
        server.set_max_inflight.assert_called_once_with(5)

    def test_reload_failure_is_reported_not_raised(self):
        server = mock.Mock()
        middle = mock.Mock()
        middle.reload_registry.side_effect = RuntimeError("bad registry")
        ok, error = api_server.reload_business_state(server, middle)
        self.assertFalse(ok)
        self.assertIn("RuntimeError", error)
        self.assertIn("bad registry", error)
        server.set_max_inflight.assert_not_called()


if __name__ == "__main__":
    unittest.main()
