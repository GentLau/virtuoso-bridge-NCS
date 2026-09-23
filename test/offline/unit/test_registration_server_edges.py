"""Registration control plane: negative paths and write-failure edges.

Complements ``test_registration_server.py`` with the branches a reviewer can
otherwise only find unused: unauthenticated admin routes, oversized bodies,
broken Content-Length drains, bug-report write failures, active-flow deletion
and ``main()`` lifecycle.  All of it is local-only (127.0.0.1:0 + temp work
dir).
"""

from __future__ import annotations

import hashlib
import http.client
import json
import socket
import sys
import tempfile
import threading
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import register.server as register_server
from register.server import RegistrationHandler, RegistrationServer
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests

#: Same throwaway credential as ``test_registration_server.py``; the module
#: hash is swapped per-test (never at import) so neither file clobbers the
#: other when the whole suite imports both.
_ADMIN_TOKEN = "test-admin-token"


def _admin_auth():
    return {"Authorization": "Bearer " + _ADMIN_TOKEN}


class _ServerThread:
    def __init__(self, registry, process_manager=None):
        self.server = RegistrationServer(
            ("127.0.0.1", 0), registry, process_manager
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever, daemon=True
        )
        self.thread.start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        payload = None if body is None else json.dumps(body)
        merged = dict(headers or {})
        if payload is not None and "Content-Type" not in merged:
            merged["Content-Type"] = "application/json"
        conn.request(method, path, payload, merged)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        conn.close()
        return resp.status, raw, resp

    def request_raw(self, method, path, raw: bytes, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        merged = dict(headers or {})
        merged.setdefault("Content-Type", "application/json")
        conn.request(method, path, raw, merged)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        return resp.status, body

    def raw_socket(self, request: bytes) -> bytes:
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


class _FakeState:
    def __init__(self, *, stage="applied", step=1, token="tok-sess", user="victim"):
        self.user = user
        self.stage = stage
        self.step = step
        self.token = token
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.setup_path = None
        self.entry = None
        self.report = None


class _FakeFlow:
    def __init__(self, state):
        self.state = state
        self.cancelled = False

    def cancel(self):
        self.cancelled = True
        self.state.stage = "cancelled"
        return self.state


class _StubManager:
    def __init__(self, *, status_error=None, reload_error=None):
        self.status_error = status_error
        self.reload_error = reload_error
        self.calls: list[str] = []

    def status(self):
        if self.status_error is not None:
            raise self.status_error
        return {"same_process": False, "state": "ready", "pid": 1, "port": 1}

    def reload(self):
        self.calls.append("reload")
        if self.reload_error is not None:
            raise self.reload_error
        return self.status()

    def restart(self):
        self.calls.append("restart")
        return self.status()


class _EdgeBase(unittest.TestCase):
    def setUp(self):
        self._saved_admin_hash = register_server._ADMIN_TOKEN_HASH
        register_server._ADMIN_TOKEN_HASH = hashlib.sha256(
            _ADMIN_TOKEN.encode("utf-8")
        ).hexdigest()
        self.wd = override_work_dir_for_tests(
            Path(tempfile.mkdtemp(prefix="vb-"))
        )
        self.registry = load_registry(registry_path())
        self._servers: list[_ServerThread] = []

    def tearDown(self):
        for srv in self._servers:
            srv.close()
        register_server._ADMIN_TOKEN_HASH = self._saved_admin_hash

    def start(self, manager=None):
        srv = _ServerThread(self.registry, manager)
        self._servers.append(srv)
        return srv

    @staticmethod
    def _status_line(data: bytes) -> bytes:
        return data.split(b"\r\n", 1)[0]


class TestRouteEdges(_EdgeBase):
    def test_health_and_help_are_public(self):
        srv = self.start()
        status, raw, _resp = srv.request("GET", "/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw), {"status": "ok"})
        status, raw, _resp = srv.request("GET", "/help")
        self.assertEqual(status, 200)
        self.assertIn("POST /api/register", raw)

    def test_admin_routes_refuse_anonymous_readers(self):
        srv = self.start()
        for method, path in (
            ("GET", "/api/config"),
            ("GET", "/api/users"),
            ("GET", "/api/user/ghost"),
            ("GET", "/api/process/status"),
            ("POST", "/api/process/reload"),
            ("POST", "/api/process/restart"),
            ("DELETE", "/api/user/ghost"),
            ("POST", "/api/user/ghost/update"),
            ("PUT", "/api/config"),
        ):
            with self.subTest(method=method, path=path):
                status, raw, _resp = srv.request(method, path, {} if method == "POST" else None)
                self.assertEqual(status, 401, raw)

    def test_head_is_405_without_body(self):
        srv = self.start()
        status, _raw, resp = srv.request("HEAD", "/api/config")
        self.assertEqual(status, 405)
        self.assertEqual(resp.getheader("Allow"), "GET, POST, PUT, DELETE")
        self.assertEqual(resp.getheader("Connection"), "close")

    def test_connect_is_405(self):
        srv = self.start()
        data = srv.raw_socket(
            b"CONNECT /api/config HTTP/1.1\r\nHost: x\r\nContent-Length: 0\r\n\r\n"
        )
        self.assertIn(b" 405 ", self._status_line(data), data[:200])

    def test_unserializable_config_is_structured_500(self):
        srv = self.start()
        srv.server.config = {"business_thread_pool_size": object()}
        status, raw, _resp = srv.request(
            "GET", "/api/config", None, _admin_auth()
        )
        self.assertEqual(status, 500, raw)
        payload = json.loads(raw)
        self.assertEqual(payload["error"], "invalid response payload")


class TestProcessEndpoints(_EdgeBase):
    def test_status_failure_is_structured_500(self):
        manager = _StubManager(status_error=RuntimeError("no status"))
        srv = self.start(manager)
        status, raw, _resp = srv.request(
            "GET", "/api/process/status", None, _admin_auth()
        )
        self.assertEqual(status, 500, raw)
        self.assertIn("status failed", raw)

    def test_reload_failure_is_500_and_audited(self):
        manager = _StubManager(reload_error=RuntimeError("boom"))
        srv = self.start(manager)
        status, raw, _resp = srv.request(
            "POST", "/api/process/reload", {}, _admin_auth()
        )
        self.assertEqual(status, 500, raw)
        self.assertIn("reload failed", raw)
        audit = (Path(self.wd) / "log" / "audit.log").read_text(encoding="utf-8")
        self.assertIn('"ok": false', audit)
        self.assertIn("boom", audit)

    def test_audit_write_failure_is_swallowed(self):
        manager = _StubManager()
        srv = self.start(manager)
        with mock.patch.object(
            register_server, "log_dir", return_value=Path("R:/no/such/dir")
        ):
            status, raw, _resp = srv.request(
                "POST", "/api/process/reload", {}, _admin_auth()
            )
        self.assertEqual(status, 200, raw)

    def test_process_body_over_limit_is_413_without_reading_body(self):
        srv = self.start(_StubManager())
        header = (
            b"POST /api/process/reload HTTP/1.1\r\nHost: x\r\n"
            + _admin_auth()["Authorization"].encode()
            + b"\r\n"
        )
        request = (
            b"POST /api/process/reload HTTP/1.1\r\nHost: x\r\n"
            b"Authorization: Bearer " + _ADMIN_TOKEN.encode() + b"\r\n"
            b"Content-Length: " + str(16 * 1024 * 1024 + 1).encode() + b"\r\n\r\n"
        )
        data = srv.raw_socket(request)
        self.assertIn(b" 413 ", self._status_line(data), data[:300])
        del header


class TestUpdateAndDeleteEdges(_EdgeBase):
    def _local_entry(self, user, token="tok-edge"):
        entry = UserEntry(token=token, mode="local")
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, name)
            role.root = str(Path(self.wd) / "roots" / user / name)
        entry.roles.daemon.daemon_port = 65431
        self.registry.register(user, entry)
        return entry

    def test_update_unknown_user_is_404(self):
        srv = self.start()
        status, raw, _resp = srv.request(
            "POST", "/api/user/ghost/update", {}, _admin_auth()
        )
        self.assertEqual(status, 404, raw)

    def test_update_rejects_oversized_and_malformed_bodies(self):
        self._local_entry("edge1")
        srv = self.start()
        oversized = (
            b"POST /api/user/edge1/update HTTP/1.1\r\nHost: x\r\n"
            b"Authorization: Bearer " + _ADMIN_TOKEN.encode() + b"\r\n"
            b"Content-Length: " + str(16 * 1024 * 1024 + 1).encode() + b"\r\n\r\n"
        )
        data = srv.raw_socket(oversized)
        self.assertIn(b" 413 ", self._status_line(data), data[:300])

        status, raw = srv.request_raw(
            "POST", "/api/user/edge1/update", b"{not json", _admin_auth()
        )
        self.assertEqual(status, 400, raw)
        self.assertIn("invalid JSON body", raw)

        status, raw = srv.request_raw(
            "POST", "/api/user/edge1/update", b"[1, 2]", _admin_auth()
        )
        self.assertEqual(status, 400, raw)
        self.assertIn("must be an object", raw)

    def test_update_keyerror_maps_to_404(self):
        self._local_entry("edge2")
        srv = self.start()
        with mock.patch.object(
            srv.server.registry, "update", side_effect=KeyError("edge2")
        ):
            status, raw, _resp = srv.request(
                "POST", "/api/user/edge2/update", {"runtime": {}}, _admin_auth()
            )
        self.assertEqual(status, 404, raw)

    def test_delete_cancels_active_flow_and_clears_it(self):
        self._local_entry("edge3")
        srv = self.start()
        flow = _FakeFlow(_FakeState(user="edge3"))
        with srv.server.flow_lock:
            srv.server.flows["edge3"] = flow
        status, raw, _resp = srv.request(
            "DELETE", "/api/user/edge3", None, _admin_auth()
        )
        self.assertEqual(status, 200, raw)
        self.assertTrue(flow.cancelled)
        self.assertNotIn("edge3", srv.server.flows)
        self.assertIsNone(self.registry.get("edge3"))

    def test_delete_reports_business_reload_failure(self):
        self._local_entry("edge4")
        manager = _StubManager(reload_error=RuntimeError("child busy"))
        srv = self.start(manager)
        status, raw, _resp = srv.request(
            "DELETE", "/api/user/edge4", None, _admin_auth()
        )
        self.assertEqual(status, 500, raw)
        self.assertIn("business reload failed", raw)
        self.assertIsNone(self.registry.get("edge4"))


class TestConfigEdges(_EdgeBase):
    def test_put_config_oversized_and_non_object(self):
        srv = self.start()
        oversized = (
            b"PUT /api/config HTTP/1.1\r\nHost: x\r\n"
            b"Authorization: Bearer " + _ADMIN_TOKEN.encode() + b"\r\n"
            b"Content-Length: " + str(16 * 1024 * 1024 + 1).encode() + b"\r\n\r\n"
        )
        data = srv.raw_socket(oversized)
        self.assertIn(b" 413 ", self._status_line(data), data[:300])

        status, raw = srv.request_raw(
            "PUT", "/api/config", b'"just a string"', _admin_auth()
        )
        self.assertEqual(status, 400, raw)
        self.assertIn("invalid config body", raw)

    def test_save_config_cleans_temp_file_on_failure(self):
        srv = self.start()
        with self.assertRaises(TypeError):
            srv.server.save_config({"business_thread_pool_size": object()})
        self.assertEqual(list(Path(self.wd).glob("config-*.tmp")), [])

    def test_save_config_cleanup_failure_still_raises(self):
        srv = self.start()
        with mock.patch.object(
            register_server.os, "unlink", side_effect=OSError("locked")
        ):
            with self.assertRaises(TypeError):
                srv.server.save_config({"business_thread_pool_size": object()})


class TestRegisterCommandEdges(_EdgeBase):
    def _register_holder(self, token="holder-tok"):
        self.registry.register("holder", UserEntry(token=token, mode="local"))
        return token

    def _apply_local(self, srv, user="enhanced-user", **extra):
        body = {"user": user, "action": "apply", "mode": "local"}
        body.update(extra)
        return srv.request("POST", "/api/register", body)

    def test_apply_accepts_enhanced_token_from_holder_or_admin(self):
        """r22: enhanced_token 可选；提供了就用（任一已登记 holder token 或管理员 token）。"""
        holder = self._register_holder()
        srv = self.start()
        for label, token in (("holder", holder), ("admin", _ADMIN_TOKEN)):
            with self.subTest(kind=label):
                status, raw, _resp = self._apply_local(
                    srv, user=f"user-{label}", enhanced_token=token
                )
                self.assertEqual(status, 200, raw)
                self.assertEqual(json.loads(raw)["stage"], "applied")

    def test_apply_rejects_unknown_enhanced_token(self):
        srv = self.start()
        status, raw, _resp = self._apply_local(
            srv, enhanced_token="not-a-known-token"
        )
        self.assertEqual(status, 401, raw)
        self.assertIn("invalid enhanced_token", raw)
        self.assertNotIn("enhanced-user", srv.server.flows)

    def test_apply_without_enhanced_token_keeps_legacy_path(self):
        srv = self.start()
        status, raw, _resp = self._apply_local(srv)
        self.assertEqual(status, 200, raw)
        self.assertEqual(json.loads(raw)["stage"], "applied")

    def test_enhanced_token_is_not_echoed_in_state(self):
        holder = self._register_holder()
        srv = self.start()
        status, raw, _resp = self._apply_local(srv, enhanced_token=holder)
        self.assertEqual(status, 200, raw)
        session_token = json.loads(raw)["token"]
        status, state_raw, _resp = srv.request(
            "GET", f"/api/register/enhanced-user?token={session_token}"
        )
        self.assertEqual(status, 200, state_raw)
        self.assertNotIn(holder, state_raw)
        self.assertNotIn("enhanced_token", state_raw)

    def test_bug_report_masks_enhanced_token_key(self):
        holder = self._register_holder()
        srv = self.start()
        body = json.dumps({
            "token": holder,
            "enhanced_token": "top-secret-enhanced-value",
        }).encode("utf-8")
        status, raw = srv.request_raw("POST", "/api/bug", body)
        self.assertEqual(status, 200, raw)
        saved = (Path(self.wd) / json.loads(raw)["path"]).read_text(
            encoding="utf-8"
        )
        self.assertNotIn("top-secret-enhanced-value", saved)
        self.assertIn("***", saved)

    def test_apply_on_committed_flow_is_rejected(self):
        srv = self.start()
        with srv.server.flow_lock:
            srv.server.flows["done"] = _FakeFlow(
                _FakeState(stage="committed", user="done")
            )
        status, raw, _resp = srv.request("POST", "/api/register", {
            "user": "done", "action": "apply", "mode": "local",
        })
        self.assertEqual(status, 400, raw)
        self.assertIn("already registered", raw)

    def test_apply_on_active_flow_requires_cancel(self):
        srv = self.start()
        with srv.server.flow_lock:
            srv.server.flows["busy"] = _FakeFlow(
                _FakeState(stage="applied", user="busy")
            )
        status, raw, _resp = srv.request("POST", "/api/register", {
            "user": "busy", "action": "apply", "mode": "local",
        })
        self.assertEqual(status, 400, raw)
        self.assertIn("step order violation", raw)

    def test_session_token_is_required_and_checked(self):
        srv = self.start()
        with srv.server.flow_lock:
            srv.server.flows["sess"] = _FakeFlow(
                _FakeState(stage="applied", token="tok-sess", user="sess")
            )
        for body in (
            {"user": "sess", "action": "validate"},
            {"user": "sess", "action": "validate", "token": ""},
            {"user": "sess", "action": "validate", "token": "wrong"},
        ):
            with self.subTest(body=body):
                status, raw, _resp = srv.request("POST", "/api/register", body)
                self.assertEqual(status, 400, raw)
                self.assertIn("invalid token", raw)

    def test_cancel_committed_flow_is_rejected(self):
        srv = self.start()
        with srv.server.flow_lock:
            srv.server.flows["done2"] = _FakeFlow(
                _FakeState(stage="committed", token="tok-sess", user="done2")
            )
        status, raw, _resp = srv.request("POST", "/api/register", {
            "user": "done2", "action": "cancel", "token": "tok-sess",
        })
        self.assertEqual(status, 400, raw)
        self.assertIn("step order violation", raw)

    def test_bug_status_summary_skips_unstarted_and_cancelled(self):
        srv = self.start()
        never = types.SimpleNamespace(state=None)
        cancelled = _FakeFlow(_FakeState(stage="cancelled", user="old"))
        live = _FakeFlow(_FakeState(stage="probed", step=3, user="live"))
        with srv.server.flow_lock:
            srv.server.flows.update(
                {"never": never, "old": cancelled, "live": live}
            )

        class _Handler:
            server = srv.server

        summary = RegistrationHandler._bug_status_summary(_Handler())
        self.assertEqual(
            summary["registrations_in_progress"],
            [{"user": "live", "stage": "probed", "step": 3}],
        )


class TestBugReportEdges(_EdgeBase):
    def setUp(self):
        super().setUp()
        self.registry.register("bugger", UserEntry(token="tok-bug-edge", mode="local"))

    def test_bug_report_invalid_content_length_is_not_a_crash(self):
        srv = self.start()
        data = srv.raw_socket(
            b"POST /api/bug HTTP/1.1\r\nHost: x\r\n"
            b"Content-Length: abc\r\n\r\n"
        )
        self.assertIn(b" 400 ", self._status_line(data), data[:300])

    def test_bug_report_masks_bare_token_occurrences(self):
        srv = self.start()
        body = json.dumps({
            "token": "tok-bug-edge",
            "note": "repeated tok-bug-edge in a value",
        }).encode("utf-8")
        status, raw = srv.request_raw("POST", "/api/bug", body)
        self.assertEqual(status, 200, raw)
        report_path = Path(self.wd) / json.loads(raw)["path"]
        saved = report_path.read_text(encoding="utf-8")
        self.assertNotIn("tok-bug-edge", saved)
        self.assertIn("***", saved)

    def test_bug_report_survives_chmod_failure(self):
        srv = self.start()
        body = json.dumps({"token": "tok-bug-edge", "error": "x"}).encode()
        with mock.patch.object(register_server.os, "chmod", side_effect=OSError("denied")):
            status, raw = srv.request_raw("POST", "/api/bug", body)
        self.assertEqual(status, 200, raw)

    def test_bug_report_write_failure_is_500_and_leaves_no_temp(self):
        srv = self.start()
        body = json.dumps({"token": "tok-bug-edge", "error": "x"}).encode()
        with mock.patch.object(
            register_server.os, "replace", side_effect=OSError("disk full")
        ):
            status, raw = srv.request_raw("POST", "/api/bug", body)
        self.assertEqual(status, 500, raw)
        self.assertIn("failed to record bug report", raw)
        leftovers = list((Path(self.wd) / "log" / "bug_reports").glob("*.tmp"))
        self.assertEqual(leftovers, [])

    def test_bug_report_cleanup_failure_still_returns_500(self):
        srv = self.start()
        body = json.dumps({"token": "tok-bug-edge", "error": "x"}).encode()
        with mock.patch.object(
            register_server.os, "replace", side_effect=OSError("disk full")
        ), mock.patch.object(
            register_server.os, "unlink", side_effect=OSError("locked")
        ):
            status, raw = srv.request_raw("POST", "/api/bug", body)
        self.assertEqual(status, 500, raw)
        self.assertIn("failed to record bug report", raw)

    def test_recent_logs_tail_is_bounded(self):
        log = Path(self.wd) / "log"
        log.mkdir(parents=True, exist_ok=True)
        (log / "big.log").write_bytes(b"x" * (200_001))
        (log / "many.log").write_text(
            "\n".join(f"line-{i}" for i in range(600)) + "\n", encoding="utf-8"
        )
        (log / "subdir").mkdir(exist_ok=True)
        entries = {
            entry["name"]: entry for entry in RegistrationHandler._bug_recent_logs()
        }
        self.assertNotIn("subdir", entries)
        self.assertTrue(entries["big.log"]["truncated"])
        self.assertTrue(entries["many.log"]["truncated"])
        self.assertEqual(len(entries["many.log"]["tail"].splitlines()), 500)

    def test_recent_logs_glob_failure_returns_empty(self):
        with mock.patch.object(
            register_server, "log_dir", side_effect=OSError("gone")
        ):
            self.assertEqual(RegistrationHandler._bug_recent_logs(), [])

    def test_recent_logs_skips_unreadable_entries(self):
        class _Path:
            def __init__(self, name, *, is_file=True, stat_error=False):
                self.name = name
                self._is_file = is_file
                self._stat_error = stat_error

            def is_file(self):
                return self._is_file

            def __lt__(self, other):
                return self.name < other.name

            def stat(self):
                if self._stat_error:
                    raise OSError("unreadable")
                return types.SimpleNamespace(st_size=3)

        class _Dir:
            def glob(self, _pattern):
                return [
                    _Path("skipped", is_file=False),
                    _Path("broken", stat_error=True),
                ]

        with mock.patch.object(register_server, "log_dir", return_value=_Dir()):
            self.assertEqual(RegistrationHandler._bug_recent_logs(), [])


class TestDrainEdges(_EdgeBase):
    def test_malformed_content_length_drain_returns(self):
        srv = self.start()
        data = srv.raw_socket(
            b"PATCH /api/config HTTP/1.1\r\nHost: x\r\n"
            b"Content-Length: nan\r\n\r\nbody"
        )
        self.assertIn(b" 405 ", self._status_line(data), data[:300])

    def test_drain_stops_when_peer_sends_short_body(self):
        srv = self.start()
        data = srv.raw_socket(
            b"PATCH /api/config HTTP/1.1\r\nHost: x\r\n"
            b"Content-Length: 100\r\n\r\nxx"
        )
        self.assertIn(b" 405 ", self._status_line(data), data[:300])


class TestMain(_EdgeBase):
    def test_main_serves_and_survives_keyboard_interrupt(self):
        fake = mock.Mock()
        fake.serve_forever.side_effect = KeyboardInterrupt
        with mock.patch.object(register_server, "init_work_dir"), \
                mock.patch.object(register_server, "load_registry",
                                  return_value=mock.Mock(path=Path("r.json"))), \
                mock.patch.object(register_server, "RegistrationServer",
                                  return_value=fake), \
                mock.patch("common.ssh.configure_command_log"), \
                mock.patch("common.paths.command_log_file",
                           return_value=Path("commands.log")):
            register_server.main(["--port", "18124"])
        fake.serve_forever.assert_called_once()
        fake.server_close.assert_called_once()

    def test_main_closes_on_normal_exit(self):
        fake = mock.Mock()
        with mock.patch.object(register_server, "init_work_dir"), \
                mock.patch.object(register_server, "load_registry",
                                  return_value=mock.Mock(path=Path("r.json"))), \
                mock.patch.object(register_server, "RegistrationServer",
                                  return_value=fake), \
                mock.patch("common.ssh.configure_command_log"), \
                mock.patch("common.paths.command_log_file",
                           return_value=Path("commands.log")):
            register_server.main([])
        fake.server_close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
