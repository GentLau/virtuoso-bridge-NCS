"""HTTP response serialization never drops the connection on bad JSON values."""

import io
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from server.api_server import ApiHandler
from register.server import RegistrationHandler


class _DummyHandler:
    def __init__(self):
        self.wfile = io.BytesIO()
        self.close_connection = False
        self.status = None

    def send_response(self, status):
        self.status = status

    def send_header(self, *_args):
        return None

    def end_headers(self):
        return None


class _DummyApi(_DummyHandler, ApiHandler):
    pass


class _DummyRegister(_DummyHandler, RegistrationHandler):
    pass


class TestHttpJsonSafety(unittest.TestCase):
    def test_lone_surrogate_is_escaped_not_dropped(self):
        handler = _DummyApi()
        ApiHandler._send(handler, 200, {"ok": True, "data": "\ud800", "error": None})
        body = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertEqual(handler.status, 200)
        self.assertEqual(body["data"], "\ud800")

    def test_non_finite_number_becomes_structured_500(self):
        handler = _DummyApi()
        ApiHandler._send(
            handler,
            200,
            {"ok": True, "data": {"value": float("-inf")}, "error": None},
        )
        body = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertEqual(handler.status, 500)
        self.assertFalse(body["ok"])
        self.assertIn("invalid response payload", body["error"])

    def test_register_lone_surrogate_is_escaped_not_dropped(self):
        handler = _DummyRegister()
        RegistrationHandler._send_json(
            handler, 400, {"error": "invalid", "user": "\udfff"},
        )
        body = json.loads(handler.wfile.getvalue().decode("utf-8"))
        self.assertEqual(handler.status, 400)
        self.assertEqual(body["user"], "\udfff")


if __name__ == "__main__":
    unittest.main()
