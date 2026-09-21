"""Registration HTTP server smoke tests (local mode, no real daemon).

Verifies the page and the six-step API shape; step 5 is expected to fail
without a running daemon, which must NOT commit anything to the registry.
"""

import http.client
import json
import socket
import sys
import tempfile
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from register.server import RegistrationServer, _ADMIN_TOKEN_HASH
from common.registry import UserEntry, load_registry
from common.paths import registry_path, override_work_dir_for_tests


# 内置管理员 token 的明文（验收/测试用；服务端只存 SHA-256 哈希）
_ADMIN_TOKEN = "V-9-ZM32KpykwpNXyMnmSTUTFB2o_jJVfG0-D_Vd_JA"


def _admin_auth():
    return {"Authorization": "Bearer " + _ADMIN_TOKEN}


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class _ServerThread:
    def __init__(self, registry, process_manager=None):
        self.server = RegistrationServer(
            ("127.0.0.1", 0), registry, process_manager
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
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
        return resp.status, raw

    def request_raw(self, method, path, raw: bytes, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        merged = dict(headers or {})
        merged.setdefault("Content-Type", "application/json")
        conn.request(method, path, raw, merged)
        resp = conn.getresponse()
        body = resp.read().decode("utf-8")
        conn.close()
        return resp.status, body


class _StubManager:
    """Duck-typed process manager used by the control-plane endpoint tests."""

    def __init__(self, *, same_process=False, reload_error=None, restart_error=None):
        self.same_process = same_process
        self.reload_error = reload_error
        self.restart_error = restart_error
        self.calls: list[str] = []

    def status(self):
        return {
            "same_process": self.same_process,
            "state": "ready",
            "pid": 4242,
            "port": 8127,
            "work_dir": "/tmp/w",
            "startup_args": ["-m", "server.api_server", "--port", "8127"],
            "last_error": None,
        }

    def reload(self):
        self.calls.append("reload")
        if self.reload_error is not None:
            raise self.reload_error
        return self.status()

    def restart(self):
        self.calls.append("restart")
        if self.restart_error is not None:
            raise self.restart_error
        return self.status()

    def shutdown(self):
        self.calls.append("shutdown")


class TestProcessEndpoints(unittest.TestCase):
    """顶层补充 v27 §3：/api/process/*（管理员，target=business）。"""

    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.registry = load_registry(registry_path())
        self.manager = _StubManager()
        self.srv = _ServerThread(self.registry, self.manager)

    def tearDown(self):
        self.srv.close()

    def test_admin_required(self):
        for method, path, body in (
            ("GET", "/api/process/status", None),
            ("POST", "/api/process/reload", {"target": "business"}),
            ("POST", "/api/process/restart", {"target": "business"}),
        ):
            with self.subTest(path=path):
                status, _raw = self.srv.request(method, path, body)
                self.assertEqual(status, 401)

    def test_status_reports_manager_state(self):
        status, raw = self.srv.request(
            "GET", "/api/process/status", None, _admin_auth()
        )
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertEqual(payload["state"], "ready")
        self.assertFalse(payload["same_process"])
        self.assertEqual(payload["port"], 8127)

    def test_reload_and_restart_call_manager_and_audit(self):
        for action in ("reload", "restart"):
            status, raw = self.srv.request(
                "POST", f"/api/process/{action}", {"target": "business"},
                _admin_auth(),
            )
            self.assertEqual(status, 200, raw)
        self.assertEqual(self.manager.calls, ["reload", "restart"])
        audit = Path(self.wd) / "log" / "audit.log"
        self.assertTrue(audit.exists())
        lines = [json.loads(line) for line in audit.read_text(encoding="utf-8").splitlines()]
        self.assertEqual([line["action"] for line in lines], ["reload", "restart"])
        self.assertTrue(all(line["ok"] for line in lines))
        self.assertNotIn(_ADMIN_TOKEN, audit.read_text(encoding="utf-8"))

    def test_invalid_target_is_400(self):
        status, raw = self.srv.request(
            "POST", "/api/process/reload", {"target": "control"}, _admin_auth()
        )
        self.assertEqual(status, 400, raw)
        self.assertEqual(self.manager.calls, [])

    def test_malformed_content_length_is_400_and_does_not_reload(self):
        """畸形长度不能按空 body 走默认 target，更不能触发真实 reload。"""
        body = b'{"target":"business"}'
        request = (
            b"POST /api/process/reload HTTP/1.1\r\nHost: x\r\n"
            + f"Authorization: Bearer {_ADMIN_TOKEN}\r\n".encode("ascii")
            + b"Content-Type: application/json\r\nContent-Length: abc\r\n\r\n"
            + body
        )
        sock = socket.create_connection(("127.0.0.1", self.srv.port), timeout=5)
        sock.sendall(request)
        data = b""
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                data += chunk
        except OSError:
            pass
        sock.close()
        self.assertIn(b" 400 ", data.split(b"\r\n", 1)[0], data[:200])
        self.assertEqual(self.manager.calls, [])

    def test_malformed_json_is_400_and_does_not_reload(self):
        """畸形 JSON 也不能退化为默认 target 并触发真实 reload。"""
        for body in (b"{bad", b"[]"):
            with self.subTest(body=body):
                status, raw = self.srv.request_raw(
                    "POST", "/api/process/reload", body, _admin_auth()
                )
                self.assertEqual(status, 400, raw)
                self.assertEqual(self.manager.calls, [])

    def test_unmanaged_returns_409(self):
        server = _ServerThread(self.registry, None)
        try:
            status, raw = server.request(
                "GET", "/api/process/status", None, _admin_auth()
            )
            self.assertEqual(status, 409, raw)
            status, raw = server.request(
                "POST", "/api/process/reload", {"target": "business"},
                _admin_auth(),
            )
            self.assertEqual(status, 409, raw)
        finally:
            server.close()

    def test_same_process_restart_is_501(self):
        manager = _StubManager(same_process=True, restart_error=NotImplementedError())
        server = _ServerThread(self.registry, manager)
        try:
            status, raw = server.request(
                "POST", "/api/process/restart", {"target": "business"},
                _admin_auth(),
            )
            self.assertEqual(status, 501, raw)
            status, raw = server.request(
                "POST", "/api/process/reload", {"target": "business"},
                _admin_auth(),
            )
            self.assertEqual(status, 200, raw)  # same-process reload is allowed
        finally:
            server.close()


class TestRegistrationServer(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.registry = load_registry(registry_path())
        self.srv = _ServerThread(self.registry)

    def tearDown(self):
        self.srv.close()

    def _apply(self, user, **fields):
        status, raw = self.srv.request("POST", "/api/register", {
            "user": user,
            "action": "apply",
            **fields,
        })
        data = json.loads(raw)
        self.assertEqual(status, 200, raw)
        return data

    def _step(self, user, action, token):
        status, raw = self.srv.request("POST", "/api/register", {
            "user": user,
            "action": action,
            "token": token,
        })
        return status, json.loads(raw)

    def _to_deploy(self, user, **fields):
        data = self._apply(user, **fields)
        for action in ("validate", "probe", "deploy"):
            status, data = self._step(user, action, data["token"])
            self.assertEqual(status, 200, data)
        self.assertEqual(data["stage"], "deployed")
        return data

    def test_page_served(self):
        status, raw = self.srv.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("注册", raw)

    def test_local_six_step_reaches_deployed(self):
        port = _free_port()
        data = self._to_deploy(
            "alice",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        self.assertEqual(data["stage"], "deployed")
        self.assertTrue(data["token"])
        self.assertTrue(data["setup_path"].endswith("virtuoso_setup.il"))

    def test_duplicate_user_rejected_before_probe(self):
        # seed a committed entry; the step-2 check reads only the registry
        self.registry.register("alice", UserEntry(token="tok-exists", mode="local"))
        port = _free_port()
        data = self._apply(
            "alice",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        status, data = self._step("alice", "validate", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(data["stage"], "failed")
        self.assertTrue(any("already registered" in e for e in data["errors"]))

    def test_granular_six_steps(self):
        port = _free_port()
        data = self._apply(
            "bob",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        self.assertEqual((data["stage"], data["step"]), ("applied", 1))
        self.assertTrue(data["token"])

        status, data = self._step("bob", "validate", data["token"])
        self.assertEqual((data["stage"], data["step"]), ("validated", 2))

        status, data = self._step("bob", "probe", data["token"])
        self.assertEqual((data["stage"], data["step"]), ("probed", 3))

        status, data = self._step("bob", "deploy", data["token"])
        self.assertEqual((data["stage"], data["step"]), ("deployed", 4))
        self.assertTrue(data["setup_path"].endswith("virtuoso_setup.il"))

        # no daemon running: step 5 must fail and must NOT commit
        status, data = self._step("bob", "verify", data["token"])
        self.assertEqual(data["stage"], "failed")
        self.assertEqual(data["step"], 5)
        self.assertIsNone(self.registry.get("bob"))

    def test_cancel_releases_session_and_does_not_write_registry(self):
        port = _free_port()
        data = self._apply(
            "cancelme",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        status, data = self._step("cancelme", "cancel", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(data["stage"], "cancelled")
        self.assertIsNone(self.registry.get("cancelme"))
        status, repeated = self._step("cancelme", "cancel", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(repeated["stage"], "cancelled")
        status, _ = self.srv.request(
            "GET", f"/api/register/cancelme?token={data['token']}"
        )
        self.assertEqual(status, 404)

    def test_failed_registration_requires_cancel_before_apply(self):
        self.registry.register("retry", UserEntry(token="retry-existing", mode="local"))
        port = _free_port()
        data = self._apply(
            "retry",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        status, failed = self._step("retry", "validate", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(failed["stage"], "failed")
        status, raw_current = self.srv.request(
            "GET", f"/api/register/retry?token={data['token']}"
        )
        self.assertEqual(status, 200)
        current = json.loads(raw_current)
        self.assertEqual(current["stage"], "failed")

        # Same-step retry is allowed; changing parameters is not.
        status, retried = self._step("retry", "validate", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(retried["stage"], "failed")
        status, raw = self.srv.request("POST", "/api/register", {
            "user": "retry",
            "action": "apply",
            "mode": "local",
            "roles": {
                "daemon": {"daemon_port": _free_port()},
                "spectre": {"bin": sys.executable},
            },
        })
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(raw)["expected"], "cancel")

        status, cancelled = self._step("retry", "cancel", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(cancelled["stage"], "cancelled")
        restarted = self._apply(
            "retry",
            mode="local",
            roles={
                "daemon": {"daemon_port": _free_port()},
                "spectre": {"bin": sys.executable},
            },
        )
        self.assertEqual(restarted["stage"], "applied")

    def test_legacy_step_endpoint_removed(self):
        status, raw = self.srv.request("POST", "/api/register/ghost/validate", None)
        self.assertEqual(status, 404)

    def test_state_endpoint_unknown_user(self):
        status, raw = self.srv.request("GET", "/api/register/ghost")
        self.assertEqual(status, 404)

    def test_state_endpoint_requires_session_token(self):
        data = self._apply("nina", mode="local")
        status, raw = self.srv.request("GET", "/api/register/nina?token=wrong")
        self.assertEqual(status, 400, raw)
        self.assertIn("invalid token", raw)
        status, raw = self.srv.request(
            "GET", f"/api/register/nina?token={data['token']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["stage"], "applied")

    def test_action_with_wrong_session_token_does_not_change_state(self):
        data = self._apply("olga", mode="local")
        status, raw = self.srv.request(
            "POST", "/api/register",
            {"user": "olga", "action": "validate", "token": "wrong"},
        )
        self.assertEqual(status, 400, raw)
        status, raw = self.srv.request(
            "GET", f"/api/register/olga?token={data['token']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["stage"], "applied")

    def test_cancel_is_idempotent_and_session_disappears(self):
        data = self._apply("pam", mode="local")
        status, payload = self._step("pam", "cancel", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(payload["stage"], "cancelled")
        status, payload = self._step("pam", "cancel", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(payload["stage"], "cancelled")
        status, raw = self.srv.request(
            "GET", f"/api/register/pam?token={data['token']}"
        )
        self.assertEqual(status, 404, raw)
        self.assertIsNone(self.registry.get("pam"))

    def test_verify_endpoint_unknown_user(self):
        status, raw = self.srv.request("POST", "/api/register", {
            "user": "ghost",
            "action": "verify",
            "token": "missing",
        })
        self.assertEqual(status, 404)

    def test_invalid_json_body(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.port, timeout=10)
        conn.request("POST", "/api/register", "{not json", {"Content-Type": "application/json"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 400)
        resp.read()
        conn.close()

    def test_invalid_request_fields(self):
        status, raw = self.srv.request("POST", "/api/register", {})
        self.assertEqual(status, 400)
        self.assertIn("invalid request", json.loads(raw)["error"])

    def test_remote_without_ssh_user_is_400(self):
        status, raw = self.srv.request("POST", "/api/register", {
            "user": "alice", "action": "apply", "mode": "remote",
            "ssh": {"default": {"host": "server-a"}},
        })
        self.assertEqual(status, 400)
        self.assertIn("invalid request", json.loads(raw)["error"])

    def test_unknown_post_route(self):
        status, raw = self.srv.request("POST", "/nope", {})
        self.assertEqual(status, 404)

    def test_help_lists_all_routes(self):
        status, raw = self.srv.request("GET", "/help")
        self.assertEqual(status, 200)
        endpoints = json.loads(raw)["endpoints"]
        for expected in (
            "POST /api/bug",
            "POST /api/register",
            "GET /api/user/<user>",
            "POST /api/user/<user>/update",
            "DELETE /api/user/<user>",
            "PUT /api/config",
        ):
            self.assertIn(expected, endpoints)

    # -- POST /api/bug（控制面 v22 §3） --------------------------------------
    def _bug_report_files(self):
        reports = Path(self.wd) / "log" / "bug_reports"
        return sorted(reports.glob("*.json")) if reports.is_dir() else []

    def test_bug_report_requires_valid_personal_token(self):
        self.registry.register("carol", UserEntry(token="tok-bug", mode="local"))
        for body in (
            b'{"report": "no token here"}',
            b"not json at all",
            b'{"token": "wrong", "report": "bad token"}',
            b'{"token": "", "report": "empty token"}',
        ):
            with self.subTest(body=body):
                status, raw = self.srv.request_raw("POST", "/api/bug", body)
                self.assertEqual(status, 400, raw)
                self.assertIn("invalid token", raw)
                self.assertEqual(self._bug_report_files(), [], "must not record")

    def test_bug_report_records_entry_with_user_and_masked_token(self):
        self.registry.register("carol", UserEntry(token="tok-bug", mode="local"))
        body = json.dumps(
            {"token": "tok-bug", "error": "boom", "trace": ["line1", "line2"]}
        ).encode("utf-8")
        status, raw = self.srv.request_raw("POST", "/api/bug", body, {
            "Content-Type": "application/json",
        })
        self.assertEqual(status, 200, raw)
        receipt = json.loads(raw)
        self.assertTrue(receipt["ok"])
        self.assertTrue(receipt["id"])

        files = self._bug_report_files()
        self.assertEqual(len(files), 1, files)
        entry = json.loads(files[0].read_text(encoding="utf-8"))
        self.assertEqual(entry["user"], "carol")
        self.assertTrue(entry["id"].startswith("bug-"))
        self.assertTrue(entry["received_at"])
        self.assertIn("boom", entry["raw_body"])
        self.assertIn("line1", entry["raw_body"])
        self.assertNotIn("tok-bug", entry["raw_body"], "credential must be masked")
        self.assertIn("status", entry)
        self.assertIn("users", entry["status"])
        self.assertIn("logs", entry)

    def test_bug_report_does_not_touch_registry_or_config(self):
        self.registry.register("carol", UserEntry(token="tok-bug", mode="local"))
        before = self.registry.get("carol").model_dump()
        self.srv.request_raw(
            "POST", "/api/bug",
            json.dumps({"token": "tok-bug", "error": "x"}).encode(),
        )
        self.assertEqual(self.registry.get("carol").model_dump(), before)

    def test_bug_report_strips_credentials(self):
        """控制面 v28：记录前先剥离 token/Authorization 等凭据。"""
        self.registry.register("carol", UserEntry(token="tok-bug", mode="local"))
        body = json.dumps({
            "token": "tok-bug",
            "authorization": "Bearer super-secret",
            "password": "hunter2",
            "secret": "s3cr3t",
            "error": "boom",
        }).encode("utf-8")
        status, raw = self.srv.request_raw("POST", "/api/bug", body)
        self.assertEqual(status, 200, raw)
        entry = json.loads(self._bug_report_files()[0].read_text(encoding="utf-8"))
        recorded = entry["raw_body"]
        for leaked in ("tok-bug", "super-secret", "hunter2", "s3cr3t"):
            self.assertNotIn(leaked, recorded)
        self.assertIn("boom", recorded)

    def test_malformed_content_length_returns_4xx(self):
        """BUG-4: 畸形 Content-Length 不得静默断连，必须给 4xx JSON。"""
        import socket as _socket
        for value in ("abc", "-7"):
            with self.subTest(value=value):
                sock = _socket.create_connection(
                    ("127.0.0.1", self.srv.port), timeout=5
                )
                body = b'{"user":"a","action":"apply","mode":"local"}'
                sock.sendall(
                    b"POST /api/register HTTP/1.1\r\nHost: x\r\n"
                    + f"Content-Length: {value}\r\n\r\n".encode("ascii")
                    + body
                )
                data = b""
                try:
                    while True:
                        chunk = sock.recv(65536)
                        if not chunk:
                            break
                        data += chunk
                except OSError:
                    pass
                sock.close()
                self.assertTrue(data, "no HTTP response for malformed Content-Length")
                self.assertIn(b"400", data.split(b"\r\n", 1)[0], data[:200])

    def test_json_parser_limits_return_400(self):
        """超长整数字面量/超深嵌套必须回 JSON 400，不得静默断连。"""
        long_int = b'{"user":"nobody","action":"cancel","token":"x","n":' + b"9" * 5000 + b"}"
        deep = (
            b'{"user":"nobody","action":"cancel","token":"x","n":'
            + b"[" * 5000 + b"]" * 5000 + b"}"
        )
        for label, body in (("long-int", long_int), ("deep", deep)):
            with self.subTest(label=label):
                status, raw = self.srv.request_raw(
                    "POST", "/api/register", body
                )
                self.assertEqual(status, 400, raw)
                self.assertIn("invalid JSON body", raw)

    def test_string_port_is_rejected(self):
        """配置字段必须严格按声明类型接收，不能把 "65203" 静默转成 int。"""
        status, raw = self.srv.request(
            "POST",
            "/api/register",
            {
                "user": "strictport",
                "action": "apply",
                "mode": "local",
                "roles": {"daemon": {"local_port": "65203"}},
            },
        )
        self.assertEqual(status, 400, raw)
        self.assertIn("invalid request", raw)
        status, _raw = self.srv.request("GET", "/api/register/strictport?token=x")
        self.assertEqual(status, 404)

    def test_get_user_known_and_unknown(self):
        self.registry.register("zoe", UserEntry(token="tok-zoe", mode="local"))
        status, raw = self.srv.request(
            "GET", "/api/user/zoe", None, _admin_auth()
        )
        self.assertEqual(status, 200)
        payload = json.loads(raw)
        self.assertEqual(payload["user"], "zoe")
        self.assertNotIn("token", payload["entry"])
        status, raw = self.srv.request(
            "GET", "/api/user/ghost", None, _admin_auth()
        )
        self.assertEqual(status, 404)

    def test_unsupported_methods_return_json_405(self):
        for method in ("PATCH", "OPTIONS", "TRACE"):
            with self.subTest(method=method):
                status, raw = self.srv.request(method, "/api/register")
                self.assertEqual(status, 405, raw)
                self.assertIn("method", raw.lower())

    def test_unknown_routes_are_404(self):
        for method in ("GET", "POST", "DELETE", "PUT"):
            with self.subTest(method=method):
                status, _raw = self.srv.request(method, "/nope", None, _admin_auth())
                self.assertEqual(status, 404)

    def test_register_command_rejects_bad_bodies_and_actions(self):
        status, _raw = self.srv.request(
            "POST", "/api/register", {"user": "a", "action": "explode"}
        )
        self.assertEqual(status, 400)
        status, _raw = self.srv.request("POST", "/api/register", ["not", "an", "object"])
        self.assertEqual(status, 400)
        status, _raw = self.srv.request(
            "POST", "/api/register", {"action": "apply", "mode": "local"}
        )
        self.assertEqual(status, 400)

    def test_non_apply_action_rejects_parameter_changes(self):
        data = self._apply("quinn", mode="local")
        status, raw = self.srv.request("POST", "/api/register", {
            "user": "quinn", "action": "validate", "token": data["token"],
            "mode": "remote",
        })
        self.assertEqual(status, 400)
        self.assertIn("cancel", raw)

    def test_out_of_order_action_is_400_and_state_unchanged(self):
        data = self._apply("ruth", mode="local")
        status, payload = self._step("ruth", "probe", data["token"])
        self.assertEqual(status, 400)
        self.assertIn("step order violation", json.dumps(payload))
        status, raw = self.srv.request(
            "GET", f"/api/register/ruth?token={data['token']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["stage"], "applied")

    def test_verify_without_daemon_does_not_commit(self):
        port = _free_port()
        data = self._to_deploy(
            "alice",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        status, data = self._step("alice", "verify", data["token"])
        self.assertEqual(status, 200)
        self.assertEqual(data["stage"], "failed")
        self.assertIn("report", data)
        self.assertFalse(self.registry.get("alice"))


    def test_entry_payload_in_state(self):
        port = _free_port()
        data = self._to_deploy(
            "carol",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        self.assertEqual(data["stage"], "deployed")
        self.assertIn("entry", data)
        self.assertNotIn("token", data["entry"])
        self.assertEqual(data["entry"]["mode"]["default"], "local")

    def test_delete_user(self):
        self.registry.register("carol", UserEntry(token="tok-del", mode="local"))
        status, raw = self.srv.request("DELETE", "/api/user/carol", None, _admin_auth())
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["removed"])
        self.assertIsNone(self.registry.get("carol"))

    def test_update_user(self):
        self._register_full_local("carol", "tok-upd")
        status, raw = self.srv.request(
            "POST", "/api/user/carol/update",
            {"cdslog": {"log_level": "error"}, "runtime": {"thread_pool_size": 16}},
            _admin_auth(),
        )
        self.assertEqual(status, 200)
        entry = self.registry.get("carol")
        self.assertEqual(entry.cdslog.log_level, "error")
        self.assertEqual(entry.runtime.thread_pool_size, 16)
        self.assertNotIn("token", json.loads(raw)["entry"])

    def test_update_nested_three_segment_path(self):
        self._register_full_local("dave", "tok-dave")
        status, raw = self.srv.request(
            "POST", "/api/user/dave/update",
            {
                "root": {"default": "/work/dave"},
                "roles": {"spectre": {
                    "mode": "remote", "host": "spectre-a", "user": "alice",
                    "bin": "/opt/spectre",
                }},
            },
            _admin_auth(),
        )
        self.assertEqual(status, 200, raw)
        entry = self.registry.get("dave")
        self.assertEqual(entry.roles.spectre.host, "spectre-a")
        self.assertEqual(entry.roles.spectre.bin, "/opt/spectre")
        self.assertEqual(entry.root.default, "/work/dave")

    def test_update_invalid_value_keeps_old_entry(self):
        self._register_full_local("erin", "tok-erin")
        before = self.registry.get("erin").model_dump()
        status, raw = self.srv.request(
            "POST", "/api/user/erin/update",
            {"cdslog": {"log_level": "bogus"}}, _admin_auth(),
        )
        self.assertEqual(status, 400)
        self.assertEqual(self.registry.get("erin").model_dump(), before)

    # -- spec r2: per-role overrides, port scope, reservation -----------------

    def test_apply_accepts_per_role_overrides(self):
        """role.<name>.mode / root 可通过 HTTP 提交（spec 配置一览 §2.3）。"""
        port = _free_port()
        local_port = _free_port()
        data = self._to_deploy(
            "dave",
            mode="local",
            roles={
                "daemon": {"daemon_port": port},
                "spectre": {"bin": sys.executable},
                "file": {"root": "/tmp/vb-dave-file"},
                "command": {"mode": "local"},
            },
        )
        self.assertEqual(data["stage"], "deployed")
        roles = data["entry"]["roles"]
        # 注册会把本地 root 回写成展开后的绝对路径（spec：注册后存绝对路径）
        self.assertTrue(roles["file"]["root"].endswith("vb-dave-file"), roles["file"]["root"])
        self.assertEqual(roles["command"]["mode"], "local")
        del local_port

    def test_per_role_local_rejects_connection_fields(self):
        """mode=local 的 role 提交 host/user 必须是参数错误（拒绝注册）。"""
        port = _free_port()
        status, raw = self.srv.request("POST", "/api/register", {
            "user": "erin", "action": "apply", "mode": "remote",
            "ssh": {"default": {"host": "server-a", "user": "alice"}},
            "roles": {"daemon": {"daemon_port": port}, "command": {"mode": "local", "host": "server-a"}},
        })
        self.assertEqual(status, 400)
        self.assertIn("invalid request", json.loads(raw)["error"])

    def test_daemon_port_conflict_is_scoped_to_host(self):
        """同主机同端口冲突；不同主机同号允许（配置一览 §6.4）。"""
        port = _free_port()
        # 直接走本地校验：同主机同端口必须报冲突，不同主机同号必须放行
        from register.flow import validate_local
        from register.models import RegistrationRequest
        from common.registry import UserEntry

        entry = UserEntry(token="tok-a", mode="remote")
        entry.roles.daemon.host = "host-a"
        entry.roles.daemon.daemon_port = port
        self.registry.register("gina", entry)

        same_host = RegistrationRequest(
            mode="remote", user="henry", token="tok-b",
            ssh={"default": {"host": "host-a", "user": "u"}},
            roles={"daemon": {"daemon_port": port}},
        )
        self.assertTrue(any("daemon port" in e for e in validate_local(self.registry, same_host)))

        other_host = same_host.model_copy(deep=True)
        other_host.user = "iris"
        other_host.token = "tok-c"
        other_host.ssh.default.host = "host-b"
        self.assertEqual(
            [e for e in validate_local(self.registry, other_host) if "daemon port" in e], []
        )

    def test_duplicate_token_rejected(self):
        port = _free_port()
        entry = UserEntry(token="dup-token", mode="local")
        entry.roles.daemon.daemon_port = port
        self.registry.register("judy", entry)
        status, raw = self.srv.request("POST", "/api/register", {
            "user": "karl", "action": "apply", "mode": "local", "token": "dup-token",
            "roles": {"daemon": {"daemon_port": _free_port()}, "spectre": {"bin": sys.executable}},
        })
        data = json.loads(raw)
        self.assertEqual(status, 200, data)
        status, data = self._step("karl", "validate", data["token"])
        self.assertTrue(status == 400 or data.get("stage") == "failed", (status, data))
        self.assertIn("token", json.dumps(data))

    def test_second_registration_with_same_daemon_port_fails_before_probe(self):
        """同 daemon 主机同端口：第二个注册在第二步就必须失败（配置一览 §6.4）。"""
        port = _free_port()
        first_data = self._to_deploy(
            "laura",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        self.assertEqual(first_data["stage"], "deployed")

        second_data = self._apply(
            "mike",
            mode="local",
            roles={"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        )
        status, data = self._step("mike", "validate", second_data["token"])
        self.assertEqual(data["stage"], "failed", data)
        self.assertTrue(any("daemon port" in e for e in data.get("errors", [])), data)
        self.assertIsNone(self.registry.get("mike"), "失败注册不得落盘")

    def test_delete_unknown_user(self):
        status, raw = self.srv.request("DELETE", "/api/user/ghost", None, _admin_auth())
        self.assertEqual(status, 404)

    # -- 管理权限与脱敏（技术支持验收 4 条） -------------------------------

    def test_personal_token_rejected_on_admin_endpoint(self):
        self.registry.register("carol", UserEntry(token="tok-personal", mode="local"))
        status, raw = self.srv.request(
            "GET", "/api/users", None,
            {"Authorization": "Bearer tok-personal"},
        )
        self.assertEqual(status, 401)

    def test_users_response_redacts_token(self):
        self.registry.register("carol", UserEntry(token="tok-redact", mode="local"))
        status, raw = self.srv.request("GET", "/api/users", None, _admin_auth())
        self.assertEqual(status, 200)
        self.assertNotIn("tok-redact", raw)
        self.assertNotIn('"token"', raw)

    def test_update_body_with_token_field_rejected(self):
        self.registry.register("carol", UserEntry(token="tok-upd2", mode="local"))
        status, raw = self.srv.request(
            "POST", "/api/user/carol/update",
            {"token": "tok-upd2", "log_level": "error"},
            _admin_auth(),
        )
        self.assertEqual(status, 400)

    def test_credentials_never_logged(self):
        import contextlib
        import io as _io
        buf = _io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.srv.request("GET", "/api/users", None,
                             {"Authorization": "Bearer " + _ADMIN_TOKEN})
            self.srv.request("GET", "/api/users", None,
                             {"Authorization": "Bearer wrong"})
        logged = buf.getvalue()
        self.assertNotIn(_ADMIN_TOKEN, logged)

    def test_config_admin_only(self):
        status, raw = self.srv.request("GET", "/api/config")
        self.assertEqual(status, 401)
        status, raw = self.srv.request("PUT", "/api/config",
                                       {"business_thread_pool_size": 8},
                                       _admin_auth())
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(raw)["business_thread_pool_size"], 8)

    def test_config_persisted_and_loaded_once(self):
        # 写入后 config.json 原子落盘
        self.srv.request("PUT", "/api/config",
                         {"business_thread_pool_size": 8}, _admin_auth())
        cfg_path = Path(registry_path()).parent / "config.json"
        self.assertTrue(cfg_path.exists())
        self.assertEqual(json.loads(cfg_path.read_text(encoding="utf-8"))["business_thread_pool_size"], 8)
        # 启动导入一次：新 server 直接从文件读到 8
        second = _ServerThread(self.registry)
        try:
            status, raw = second.request("GET", "/api/config", None, _admin_auth())
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(raw)["business_thread_pool_size"], 8)
        finally:
            second.close()

    def test_config_unknown_key_rejected(self):
        status, raw = self.srv.request("PUT", "/api/config",
                                       {"bogus": 1}, _admin_auth())
        self.assertEqual(status, 400)

    def test_config_invalid_value_rejected(self):
        """非法配置直接拒绝（顶层补充 §5）。"""
        status, raw = self.srv.request(
            "PUT", "/api/config", {"business_thread_pool_size": "abc"}, _admin_auth()
        )
        self.assertEqual(status, 400)
        self.assertEqual(
            self.srv.server.config["business_thread_pool_size"],
            self.srv.server.config.get("business_thread_pool_size"),
        )

    def test_config_malformed_json_is_4xx(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.srv.port, timeout=10)
        conn.request(
            "PUT", "/api/config", "{bad",
            {**_admin_auth(), "Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        conn.close()
        self.assertEqual(resp.status, 400, raw)

    def test_config_persist_failure_keeps_memory_snapshot(self):
        from unittest import mock
        before = dict(self.srv.server.config)
        with mock.patch.object(
            RegistrationServer, "save_config", side_effect=OSError("disk full")
        ):
            status, raw = self.srv.request(
                "PUT", "/api/config",
                {"business_thread_pool_size": 9}, _admin_auth(),
            )
        self.assertEqual(status, 500, raw)
        self.assertEqual(self.srv.server.config, before)

    def test_concurrent_apply_creates_exactly_one_session(self):
        """§3: apply 的合法前提是“无同名进行中会话”；并发 apply 只能有一个成功。"""
        from unittest import mock
        import register.server as server_mod

        barrier = threading.Barrier(2)
        original_start = server_mod.RegistrationFlow.start

        def blocked_start(self, request):
            try:
                barrier.wait(timeout=0.5)
            except threading.BrokenBarrierError:
                pass
            return original_start(self, request)

        results = []

        def apply():
            status, _raw = self.srv.request(
                "POST", "/api/register",
                {"user": "race", "action": "apply", "mode": "local"},
            )
            results.append(status)

        with mock.patch.object(server_mod.RegistrationFlow, "start", blocked_start):
            threads = [threading.Thread(target=apply) for _ in range(2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)
        self.assertEqual(sorted(results), [200, 400])

    # -- update semantics (D3/D4/D6) -----------------------------------------
    def _register_full_remote(self, user="alice", token="tok-upd"):
        entry = UserEntry(token=token, mode="remote")
        entry.ssh.default.host = "server-a"
        entry.ssh.default.user = "alice"
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, name)
            role.root = f"/home/alice/.virtuoso-bridge/{user}/{name}"
            role.expected_fingerprint = "SHA256:test"
        entry.roles.daemon.daemon_port = 65081
        entry.roles.daemon.local_port = 65082
        entry.roles.daemon.python = "/usr/bin/python3"
        entry.roles.daemon.expected_hostname = "server-a"
        entry.roles.daemon.expected_user = "alice"
        entry.roles.spectre.bin = "/opt/spectre"
        entry.registered_at = 1700000000
        self.registry.register(user, entry)
        return entry

    def _register_full_local(self, user="carol", token="tok-upd"):
        """A complete post-registration local entry (absolute roots, ports, python)."""
        entry = UserEntry(token=token, mode="local")
        base = Path(self.wd) / "roots" / user
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = getattr(entry.roles, name)
            role.root = str(base / name)
        port = _free_port()
        entry.roles.daemon.daemon_port = port
        entry.roles.daemon.local_port = port
        entry.roles.daemon.python = sys.executable
        entry.registered_at = 1700000000
        self.registry.register(user, entry)
        return entry

    def test_update_rejects_entry_with_unresolvable_remote_role(self):
        """§5“整体校验”：update 不能写出运行期不可用的条目。"""
        import copy
        self._register_full_remote()
        before = copy.deepcopy(self.registry.get("alice").model_dump())
        status, raw = self.srv.request(
            "POST", "/api/user/alice/update",
            {"ssh": {"default": {"host": None, "user": None}},
             "roles": {"gui": {"host": None, "user": None}}},
            _admin_auth(),
        )
        self.assertEqual(status, 400, raw)
        self.assertEqual(self.registry.get("alice").model_dump(), before)

    def test_update_rejects_registered_at_and_flat_aliases(self):
        """v31: token/registered_at/未声明字段与扁平别名一律拒绝。"""
        self._register_full_remote()
        status, raw = self.srv.request(
            "POST", "/api/user/alice/update", {"registered_at": 123}, _admin_auth()
        )
        self.assertEqual(status, 400, raw)
        status, raw = self.srv.request(
            "POST", "/api/user/alice/update", {"log_level": "error"}, _admin_auth()
        )
        self.assertEqual(status, 400, raw)

    def test_concurrent_updates_do_not_lose_fields(self):
        """§5: 文件锁 + 读改写原子替换，不丢更新。"""
        from unittest import mock
        import common.registry as registry_mod

        self._register_full_remote()
        barrier = threading.Barrier(2)
        original_get = registry_mod.Registry.get
        counter = {"n": 0}
        count_lock = threading.Lock()

        def blocked_get(self, user):
            with count_lock:
                counter["n"] += 1
                wait = counter["n"] <= 2
            if wait:
                try:
                    barrier.wait(timeout=1.0)
                except threading.BrokenBarrierError:
                    pass
            return original_get(self, user)

        results = []

        def patch(body):
            status, _raw = self.srv.request(
                "POST", "/api/user/alice/update", body, _admin_auth()
            )
            results.append(status)

        with mock.patch.object(registry_mod.Registry, "get", blocked_get):
            threads = [
                threading.Thread(target=patch, args=({"runtime": {"thread_pool_size": 8}},)),
                threading.Thread(target=patch, args=({"cdslog": {"log_level": "error"}},)),
            ]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=15)

        self.assertEqual(results, [200, 200])
        entry = self.registry.get("alice")
        self.assertEqual(entry.runtime.thread_pool_size, 8)
        self.assertEqual(entry.cdslog.log_level, "error")


if __name__ == "__main__":
    unittest.main()
