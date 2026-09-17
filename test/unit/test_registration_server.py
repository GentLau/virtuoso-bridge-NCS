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
    def __init__(self, registry):
        self.server = RegistrationServer(("127.0.0.1", 0), registry)
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


class TestRegistrationServer(unittest.TestCase):
    def setUp(self):
        self.wd = override_work_dir_for_tests(Path(tempfile.mkdtemp()))
        self.registry = load_registry(registry_path())
        self.srv = _ServerThread(self.registry)

    def tearDown(self):
        self.srv.close()

    def test_page_served(self):
        status, raw = self.srv.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("注册", raw)

    def test_local_apply_reaches_deployed(self):
        port = _free_port()
        status, raw = self.srv.request("POST", "/api/register", {
            "user": "alice", "mode": "local", "roles": {"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        })
        self.assertEqual(status, 200)
        data = json.loads(raw)
        self.assertEqual(data["stage"], "deployed")
        self.assertTrue(data["token"])
        self.assertTrue(data["setup_path"].endswith("virtuoso_setup.il"))

    def test_duplicate_user_rejected_before_probe(self):
        # seed a committed entry; the step-2 check reads only the registry
        self.registry.register("alice", UserEntry(token="tok-exists", mode="local"))
        port = _free_port()
        status, raw = self.srv.request("POST", "/api/register", {"user": "alice", "mode": "local", "roles": {"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}}})
        data = json.loads(raw)
        self.assertEqual(status, 200)
        self.assertEqual(data["stage"], "failed")
        self.assertTrue(any("already registered" in e for e in data["errors"]))

    def test_granular_six_steps(self):
        port = _free_port()
        status, raw = self.srv.request("POST", "/api/register/apply", {"user": "bob", "mode": "local", "roles": {"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}}})
        self.assertEqual(status, 200)
        data = json.loads(raw)
        self.assertEqual((data["stage"], data["step"]), ("applied", 1))
        self.assertTrue(data["token"])

        status, raw = self.srv.request("POST", "/api/register/bob/validate", None)
        data = json.loads(raw)
        self.assertEqual((data["stage"], data["step"]), ("validated", 2))

        status, raw = self.srv.request("POST", "/api/register/bob/probe", None)
        data = json.loads(raw)
        self.assertEqual((data["stage"], data["step"]), ("probed", 3))

        status, raw = self.srv.request("POST", "/api/register/bob/deploy", None)
        data = json.loads(raw)
        self.assertEqual((data["stage"], data["step"]), ("deployed", 4))
        self.assertTrue(data["setup_path"].endswith("virtuoso_setup.il"))

        # no daemon running: step 5 must fail and must NOT commit
        status, raw = self.srv.request("POST", "/api/register/bob/verify", None)
        data = json.loads(raw)
        self.assertEqual(data["stage"], "failed")
        self.assertEqual(data["step"], 5)
        self.assertIsNone(self.registry.get("bob"))

    def test_step_endpoint_unknown_user(self):
        status, raw = self.srv.request("POST", "/api/register/ghost/validate", None)
        self.assertEqual(status, 404)

    def test_state_endpoint_unknown_user(self):
        status, raw = self.srv.request("GET", "/api/register/ghost")
        self.assertEqual(status, 404)

    def test_verify_endpoint_unknown_user(self):
        status, raw = self.srv.request("POST", "/api/register/ghost/verify", None)
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
        status, raw = self.srv.request("POST", "/api/register", {"user": "alice", "mode": "remote", "ssh": {"default": {"host": "server-a"}}})
        self.assertEqual(status, 400)
        self.assertIn("invalid request", json.loads(raw)["error"])

    def test_unknown_post_route(self):
        status, raw = self.srv.request("POST", "/nope", {})
        self.assertEqual(status, 404)

    def test_verify_without_daemon_does_not_commit(self):
        port = _free_port()
        self.srv.request("POST", "/api/register", {"user": "alice", "mode": "local", "roles": {"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}}})
        status, raw = self.srv.request("POST", "/api/register/alice/verify", None)
        self.assertEqual(status, 200)
        data = json.loads(raw)
        self.assertEqual(data["stage"], "failed")
        self.assertIn("report", data)
        self.assertFalse(self.registry.get("alice"))


    def test_entry_payload_in_state(self):
        port = _free_port()
        status, raw = self.srv.request("POST", "/api/register", {"user": "carol", "mode": "local", "roles": {"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}}})
        data = json.loads(raw)
        self.assertEqual(data["stage"], "deployed")
        self.assertIn("entry", data)
        self.assertEqual(data["entry"]["token"], data["token"])
        self.assertEqual(data["entry"]["mode"]["default"], "local")

    def test_delete_user(self):
        self.registry.register("carol", UserEntry(token="tok-del", mode="local"))
        status, raw = self.srv.request("DELETE", "/api/user/carol", None, _admin_auth())
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["removed"])
        self.assertIsNone(self.registry.get("carol"))

    def test_update_user(self):
        self.registry.register("carol", UserEntry(token="tok-upd", mode="local"))
        status, raw = self.srv.request("POST", "/api/user/carol/update", {"log_level": "error", "thread_pool_size": 16}, _admin_auth())
        self.assertEqual(status, 200)
        entry = self.registry.get("carol")
        self.assertEqual(entry.cdslog.log_level, "error")
        self.assertEqual(entry.runtime.thread_pool_size, 16)

    def test_update_nested_three_segment_path(self):
        self.registry.register("dave", UserEntry(token="tok-dave", mode="local"))
        status, raw = self.srv.request(
            "POST", "/api/user/dave/update",
            {
                "spectre_host": "spectre-a",
                "spectre_bin": "/opt/spectre",
                "root_default": "/work/dave",
                "roles": {"spectre": {"mode": "remote"}},
            },
            _admin_auth(),
        )
        self.assertEqual(status, 200, raw)
        entry = self.registry.get("dave")
        self.assertEqual(entry.roles.spectre.host, "spectre-a")
        self.assertEqual(entry.roles.spectre.bin, "/opt/spectre")
        self.assertEqual(entry.root.default, "/work/dave")

    def test_update_invalid_value_keeps_old_entry(self):
        self.registry.register("erin", UserEntry(token="tok-erin", mode="local"))
        before = self.registry.get("erin").model_dump()
        status, raw = self.srv.request("POST", "/api/user/erin/update", {"log_level": "bogus"}, _admin_auth())
        self.assertEqual(status, 400)
        self.assertEqual(self.registry.get("erin").model_dump(), before)

    # -- spec r2: per-role overrides, port scope, reservation -----------------

    def test_apply_accepts_per_role_overrides(self):
        """role.<name>.mode / root 可通过 HTTP 提交（spec 配置一览 §2.3）。"""
        port = _free_port()
        local_port = _free_port()
        status, raw = self.srv.request("POST", "/api/register", {
            "user": "dave", "mode": "local",
            "roles": {
                "daemon": {"daemon_port": port},
                "spectre": {"bin": sys.executable},
                "file": {"root": "/tmp/vb-dave-file"},
                "command": {"mode": "local"},
            },
        })
        self.assertEqual(status, 200)
        data = json.loads(raw)
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
            "user": "erin", "mode": "remote",
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
            "user": "karl", "mode": "local", "token": "dup-token",
            "roles": {"daemon": {"daemon_port": _free_port()}, "spectre": {"bin": sys.executable}},
        })
        data = json.loads(raw)
        self.assertTrue(status == 400 or data.get("stage") == "failed", (status, data))
        self.assertIn("token", json.dumps(data))

    def test_second_registration_with_same_daemon_port_fails_before_probe(self):
        """同 daemon 主机同端口：第二个注册在第二步就必须失败（配置一览 §6.4）。"""
        port = _free_port()
        first = self.srv.request("POST", "/api/register", {
            "user": "laura", "mode": "local",
            "roles": {"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        })
        self.assertEqual(json.loads(first[1])["stage"], "deployed")

        second = self.srv.request("POST", "/api/register", {
            "user": "mike", "mode": "local",
            "roles": {"daemon": {"daemon_port": port}, "spectre": {"bin": sys.executable}},
        })
        data = json.loads(second[1])
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
        # 写入后 server.json 原子落盘
        self.srv.request("PUT", "/api/config",
                         {"business_thread_pool_size": 8}, _admin_auth())
        cfg_path = Path(registry_path()).parent / "server.json"
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


if __name__ == "__main__":
    unittest.main()
