"""Top-layer dispatch contract: explicit registry + response shell.

Spec: 顶层 §2/§3 — structural errors 4xx, business failure 2xx with ok=false,
unexpected exceptions 5xx, token required, unknown operation 404.
"""

import dataclasses
import enum
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pydantic import BaseModel

from server import dispatch as dispatch_module
from server.dispatch import DispatchError, dispatch, jsonable


class _EchoRequest(BaseModel):
    token: str
    value: int = 0


class _EchoPackage:
    def __init__(self, middle):
        self.middle = middle

    def echo(self, request):
        return {"ok": True, "value": request.value}

    def reject(self, request):
        raise ValueError("domain rejected")

    def boom(self, request):
        raise RuntimeError("kaboom")


class _Color(enum.Enum):
    RED = "red"


@dataclasses.dataclass
class _Thing:
    path: Path
    color: _Color


class TestDispatchShell(unittest.TestCase):
    def setUp(self):
        dispatch_module.register_operation(
            "tb.echo", _EchoPackage, "echo", _EchoRequest, replace=True
        )
        dispatch_module.register_operation(
            "tb.reject", _EchoPackage, "reject", _EchoRequest, replace=True
        )
        dispatch_module.register_operation(
            "tb.boom", _EchoPackage, "boom", _EchoRequest, replace=True
        )

    def tearDown(self):
        for name in ("tb.echo", "tb.reject", "tb.boom"):
            dispatch_module.PACKAGES.pop(name, None)

    def test_success_shell(self):
        status, body = dispatch(
            None, {"operation": "tb.echo", "token": "tok", "value": 7}
        )
        self.assertEqual(status, 200)
        self.assertEqual(
            body,
            {"ok": True, "data": {"ok": True, "value": 7}, "error": None},
        )

    def test_missing_or_bad_token_is_4xx(self):
        for payload in (
            {"operation": "tb.echo"},
            {"operation": "tb.echo", "token": ""},
            {"operation": "tb.echo", "token": 123},
        ):
            with self.subTest(payload=payload):
                status, body = dispatch(None, payload)
                self.assertEqual(status, 400)
                self.assertFalse(body["ok"])
                self.assertIsNone(body["data"])

    def test_unknown_operation_is_404(self):
        status, body = dispatch(None, {"operation": "nope", "token": "t"})
        self.assertEqual(status, 404)
        self.assertIn("unknown operation", body["error"])

    def test_invalid_request_fields_are_400(self):
        status, body = dispatch(
            None, {"operation": "tb.echo", "token": "t", "value": "not-an-int"}
        )
        self.assertEqual(status, 400)
        self.assertIn("invalid request", body["error"])

    def test_domain_validation_failure_is_400(self):
        status, body = dispatch(None, {"operation": "tb.reject", "token": "t"})
        self.assertEqual(status, 400)
        self.assertIn("domain rejected", body["error"])
        self.assertIsNone(body["data"])

    def test_unexpected_exception_is_5xx_without_traceback(self):
        status, body = dispatch(None, {"operation": "tb.boom", "token": "t"})
        self.assertEqual(status, 500)
        self.assertIn("kaboom", body["error"])
        self.assertIsNone(body["data"])

    def test_non_object_payload_is_400(self):
        status, body = dispatch(None, ["not", "a", "mapping"])
        self.assertEqual(status, 400)
        self.assertIn("object", body["error"])

    def test_duplicate_operation_is_startup_error(self):
        with self.assertRaises(ValueError):
            dispatch_module.register_operation(
                "tb.echo", _EchoPackage, "echo", _EchoRequest
            )

    def test_jsonable_converts_pydantic_dataclass_enum_and_path(self):
        self.assertEqual(jsonable(_EchoRequest(token="t", value=1)), {"token": "t", "value": 1})
        self.assertEqual(
            jsonable(_Thing(path=Path("/tmp/x"), color=_Color.RED)),
            {"path": str(Path("/tmp/x")), "color": "red"},
        )
        self.assertEqual(jsonable(ValueError("bad")), "bad")

    def test_build_request_requires_token(self):
        spec = dispatch_module.PACKAGES["tb.echo"]
        request = dispatch_module.build_request(spec, {"value": 3}, "tok-1")
        self.assertEqual((request.token, request.value), ("tok-1", 3))
        with self.assertRaises(DispatchError):
            dispatch_module.build_request(spec, {"value": "x"}, "tok-1")


if __name__ == "__main__":
    unittest.main()
