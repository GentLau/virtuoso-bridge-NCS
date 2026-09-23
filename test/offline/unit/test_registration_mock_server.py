"""Tests for the front-end-only registration mock testbench."""

import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "offline" / "frontend"))

from registration_mock_server import RegistrationMockServer


class _MockServerThread:
    def __init__(self, scenario="happy"):
        self.server = RegistrationMockServer(
            ("127.0.0.1", 0),
            scenario=scenario,
            delay_ms=0,
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        payload = None if body is None else json.dumps(body)
        headers = {} if payload is None else {"Content-Type": "application/json"}
        connection.request(method, path, payload, headers)
        response = connection.getresponse()
        raw = response.read().decode("utf-8")
        connection.close()
        content_type = response.getheader("Content-Type", "")
        data = json.loads(raw) if raw and "application/json" in content_type else raw
        return response.status, data


class TestRegistrationMockServer(unittest.TestCase):
    def setUp(self):
        self.srv = _MockServerThread()

    def tearDown(self):
        self.srv.close()

    def set_scenario(self, scenario):
        status, data = self.srv.request("POST", "/__mock__/config", {
            "scenario": scenario,
            "delay_ms": 0,
            "reset": True,
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["scenario"], scenario)
        self.assertTrue(data["safe"])

    def apply(self, user="alice"):
        status, data = self.srv.request("POST", "/api/register", {
            "user": user,
            "action": "apply",
            "mode": "local",
        })
        self.assertEqual(status, 200)
        self.assertEqual((data["stage"], data["step"]), ("applied", 1))
        self.assertTrue(data["token"].startswith("mock-"))
        return data

    def step(self, user, action, expected_status=200):
        flow = self.srv.server.flows.get(user)
        token = flow.token if flow is not None else ""
        status, data = self.srv.request(
            "POST", "/api/register",
            {"user": user, "action": action, "token": token},
        )
        self.assertEqual(status, expected_status)
        return data

    def deploy_ready(self, user="alice"):
        self.apply(user)
        self.assertEqual(self.step(user, "validate")["stage"], "validated")
        self.assertEqual(self.step(user, "probe")["stage"], "probed")
        data = self.step(user, "deploy")
        self.assertEqual(data["stage"], "deployed")
        self.assertIn("entry", data)
        self.assertNotIn("resolved", data)
        self.assertTrue(data["entry"]["roles"]["daemon"]["python"])
        self.assertTrue(data["entry"]["roles"]["file"]["root"])
        self.assertNotIn("token", data["entry"])
        return data

    def test_page_is_production_ui_with_mock_controller(self):
        status, page = self.srv.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("配置用户接入信息", page)
        self.assertIn("Front-end Mock TB", page)
        self.assertIn("MOCK TB · 无真实副作用", page)
        self.assertIn("[Mock TB] Virtuoso Bridge", page)
        self.assertIn('id="configSummaryCard"', page)
        self.assertIn('id="statusCard"', page)
        self.assertIn('id="flowGuide"', page)
        self.assertIn('id="enhanced_token"', page)
        self.assertIn("配置值 / 探测回填值", page)

    def test_production_page_payload_shape_is_accepted(self):
        port = 65432
        status, data = self.srv.request("POST", "/api/register", {
            "user": "shape-user",
            "action": "apply",
            "mode": {"default": "local"},
            "ssh": {"default": {}},
            "root": {},
            "roles": {
                "gui": {},
                "daemon": {"daemon_port": port},
                "command": {},
                "file": {},
                "spectre": {},
            },
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["stage"], "applied")
        self.step("shape-user", "validate")
        self.step("shape-user", "probe")
        self.step("shape-user", "deploy")
        status, state = self.srv.request(
            "GET", f"/api/register/shape-user?token={data['token']}"
        )
        self.assertEqual(status, 200)
        self.assertIn("roles", state["entry"])
        self.assertNotIn("route", state["entry"])

    def test_cancel_requires_session_token(self):
        applied = self.apply("cancel-user")
        status, data = self.srv.request("POST", "/api/register", {
            "user": "cancel-user",
            "action": "cancel",
        })
        self.assertEqual(status, 400)
        self.assertEqual(data["error"], "invalid token")

        status, data = self.srv.request("POST", "/api/register", {
            "user": "cancel-user",
            "action": "cancel",
            "token": applied["token"],
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["stage"], "cancelled")
        status, repeated = self.srv.request("POST", "/api/register", {
            "user": "cancel-user",
            "action": "cancel",
            "token": applied["token"],
        })
        self.assertEqual(status, 200)
        self.assertEqual(repeated["stage"], "cancelled")
        status, _ = self.srv.request(
            "GET", f"/api/register/cancel-user?token={applied['token']}"
        )
        self.assertEqual(status, 404)

    def test_failed_step_retries_in_place_and_reapply_requires_cancel(self):
        self.set_scenario("probe_fail")
        applied = self.apply("retry-policy")
        self.step("retry-policy", "validate")
        failed = self.step("retry-policy", "probe")
        self.assertEqual(failed["stage"], "failed")
        status, current = self.srv.request(
            "GET", f"/api/register/retry-policy?token={applied['token']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(current["stage"], "failed")

        retried = self.step("retry-policy", "probe")
        self.assertEqual(retried["stage"], "failed")
        status, body = self.srv.request("POST", "/api/register", {
            "user": "retry-policy",
            "action": "apply",
            "mode": "local",
        })
        self.assertEqual(status, 400)
        self.assertEqual(body["error"], "step order violation")

        cancelled = self.step("retry-policy", "cancel")
        self.assertEqual(cancelled["stage"], "cancelled")
        restarted = self.apply("retry-policy")
        self.assertEqual(restarted["stage"], "applied")

    def test_happy_path_reaches_committed_without_registry(self):
        deployed = self.deploy_ready()
        self.assertEqual(
            deployed["setup_path"],
            "/mock/virtuoso-bridge/alice/setup/virtuoso_setup.il",
        )
        verified = self.step("alice", "verify")
        self.assertEqual((verified["stage"], verified["step"]), ("verified", 5))
        committed = self.step("alice", "commit")
        self.assertEqual((committed["stage"], committed["step"]), ("committed", 6))
        self.assertTrue(committed["report"]["command_ok"])
        self.assertTrue(committed["report"]["skill_ok"])
        self.assertFalse(hasattr(self.srv.server, "registry"))

    def test_step_failure_scenarios(self):
        cases = [
            ("validate_fail", ["validate"], 2),
            ("probe_fail", ["validate", "probe"], 3),
            ("deploy_fail", ["validate", "probe", "deploy"], 4),
            ("commit_fail", ["validate", "probe", "deploy", "verify", "commit"], 6),
        ]
        for index, (scenario, actions, failed_step) in enumerate(cases):
            with self.subTest(scenario=scenario):
                self.set_scenario(scenario)
                user = f"failure-{index}"
                self.apply(user)
                data = None
                for action in actions:
                    data = self.step(user, action)
                self.assertIsNotNone(data)
                self.assertEqual(data["stage"], "failed")
                self.assertEqual(data["step"], failed_step)
                self.assertTrue(data["errors"])
                if failed_step == 3:
                    self.assertNotIn("entry", data)
                    self.assertNotIn("resolved", data)

    def test_verify_failure_is_retryable_and_second_attempt_succeeds(self):
        self.set_scenario("verify_fail_once")
        self.deploy_ready("retry-user")
        failed = self.step("retry-user", "verify")
        self.assertEqual((failed["stage"], failed["step"]), ("failed", 5))
        self.assertFalse(failed["report"]["skill_ok"])

        verified = self.step("retry-user", "verify")
        self.assertEqual((verified["stage"], verified["step"]), ("verified", 5))
        self.assertTrue(verified["report"]["skill_ok"])
        committed = self.step("retry-user", "commit")
        self.assertEqual((committed["stage"], committed["step"]), ("committed", 6))

    def test_session_lost_and_transient_error_are_recoverable(self):
        self.set_scenario("session_lost")
        self.apply("lost-user")
        lost = self.step("lost-user", "validate", expected_status=404)
        self.assertEqual(lost["error"], "no registration in progress")

        self.set_scenario("transient_500")
        self.apply("transient-user")
        self.step("transient-user", "validate")
        error = self.step("transient-user", "probe", expected_status=500)
        self.assertIn("temporarily unavailable", error["error"])

        flow = self.srv.server.flows["transient-user"]
        status, state = self.srv.request(
            "GET", f"/api/register/transient-user?token={flow.token}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(state["stage"], "validated")
        self.assertEqual(self.step("transient-user", "probe")["stage"], "probed")

    def test_direct_preview_seed(self):
        status, seeded = self.srv.request("POST", "/__mock__/seed", {
            "state": "deployed"
        })
        self.assertEqual(status, 200)
        user = seeded["user"]
        self.assertTrue(user.startswith("mock-preview-"))

        token = seeded["payload"]["token"]
        status, state = self.srv.request(
            "GET", f"/api/register/{user}?token={token}"
        )
        self.assertEqual(status, 200)
        self.assertEqual((state["stage"], state["step"]), ("deployed", 4))
        self.assertIn("setup_path", state)

        status, cleared = self.srv.request("POST", "/__mock__/seed", {"state": "form"})
        self.assertEqual(status, 200)
        self.assertIsNone(cleared["user"])
        self.assertEqual(
            self.srv.request("GET", f"/api/register/{user}?token={token}")[0],
            404,
        )

    def test_invalid_mock_config_is_rejected(self):
        status, data = self.srv.request("POST", "/__mock__/config", {
            "scenario": "does-not-exist"
        })
        self.assertEqual(status, 400)
        self.assertIn("unknown mock scenario", data["error"])

    def test_local_apply_payload_carries_enhanced_token_without_echo(self):
        """spec r18–r22: 本机模式以 enhanced_token 提交加强凭据；不回显、不落盘。"""
        status, data = self.srv.request("POST", "/api/register", {
            "user": "local-cred",
            "action": "apply",
            "mode": {"default": "local"},
            "ssh": {"default": {}},
            "root": {},
            "roles": {
                "gui": {},
                "daemon": {"daemon_port": 65432},
                "command": {},
                "file": {},
                "spectre": {},
            },
            "enhanced_token": "admin-token-abc",
        })
        self.assertEqual(status, 200)
        self.assertEqual(data["stage"], "applied")
        self.assertNotIn("admin-token-abc", json.dumps(data))
        flow = self.srv.server.flows["local-cred"]
        self.assertNotIn("enhanced_token", flow.request)

    def test_remote_apply_payload_carries_per_role_credentials(self):
        """remote role 必须能解析出 key_dir/key；role 覆盖要原样到达服务端。"""
        status, data = self.srv.request("POST", "/api/register", {
            "user": "remote-cred",
            "action": "apply",
            "mode": {"default": "remote"},
            "ssh": {"default": {
                "host": "compute-a",
                "user": "alice",
                "key_dir": "~/.ssh",
                "key": "id_ed25519",
            }},
            "root": {},
            "roles": {
                "gui": {},
                "daemon": {"daemon_port": 65432},
                "command": {"key_dir": "~/.ssh-ops", "key": "ops_ed25519"},
                "file": {},
                "spectre": {},
            },
        })
        self.assertEqual(status, 200)
        flow = self.srv.server.flows["remote-cred"]
        self.assertEqual(flow.request["ssh"]["default"]["key_dir"], "~/.ssh")
        self.assertEqual(flow.request["ssh"]["default"]["key"], "id_ed25519")
        self.assertEqual(flow.request["roles"]["command"]["key_dir"], "~/.ssh-ops")
        self.assertEqual(flow.request["roles"]["command"]["key"], "ops_ed25519")


if __name__ == "__main__":
    unittest.main()
