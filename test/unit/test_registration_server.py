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

from server.registration_server import RegistrationServer
from transport.registry import UserEntry, load_registry
from transport.runtime_paths import registry_path, set_working_dir


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

    def request(self, method, path, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        payload = None if body is None else json.dumps(body)
        headers = {} if payload is None else {"Content-Type": "application/json"}
        conn.request(method, path, payload, headers)
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        conn.close()
        return resp.status, raw


class TestRegistrationServer(unittest.TestCase):
    def setUp(self):
        self.wd = set_working_dir(Path(tempfile.mkdtemp()))
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
        status, raw = self.srv.request("DELETE", "/api/user/carol", None)
        self.assertEqual(status, 200)
        self.assertTrue(json.loads(raw)["removed"])
        self.assertIsNone(self.registry.get("carol"))

    def test_update_user(self):
        self.registry.register("carol", UserEntry(token="tok-upd", mode="local"))
        status, raw = self.srv.request("POST", "/api/user/carol/update", {"log_level": "error", "thread_pool_size": 16})
        self.assertEqual(status, 200)
        entry = self.registry.get("carol")
        self.assertEqual(entry.cdslog.log_level, "error")
        self.assertEqual(entry.runtime.thread_pool_size, 16)

    def test_update_nested_three_segment_path(self):
        self.registry.register("dave", UserEntry(token="tok-dave", mode="local"))
        status, raw = self.srv.request(
            "POST", "/api/user/dave/update",
            {"spectre_host": "spectre-a", "spectre_bin": "/opt/spectre", "root_default": "/work/dave"},
        )
        self.assertEqual(status, 200, raw)
        entry = self.registry.get("dave")
        self.assertEqual(entry.roles.spectre.host, "spectre-a")
        self.assertEqual(entry.roles.spectre.bin, "/opt/spectre")
        self.assertEqual(entry.root.default, "/work/dave")

    def test_update_invalid_value_keeps_old_entry(self):
        self.registry.register("erin", UserEntry(token="tok-erin", mode="local"))
        before = self.registry.get("erin").model_dump()
        status, raw = self.srv.request("POST", "/api/user/erin/update", {"log_level": "bogus"})
        self.assertEqual(status, 400)
        self.assertEqual(self.registry.get("erin").model_dump(), before)

    def test_delete_unknown_user(self):
        status, raw = self.srv.request("DELETE", "/api/user/ghost", None)
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
