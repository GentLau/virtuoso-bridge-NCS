"""Top-layer business face pool contract (顶层补充 §5 / §4).

The overall business thread pool must refuse over-limit requests immediately
with 429 + Retry-After instead of queueing, so callers can retry.
"""

import http.client
import json
import sys
import threading
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pydantic import BaseModel

from server import dispatch as dispatch_module
from server.api_server import BUSY_ERROR, build_server


class _PoolRequest(BaseModel):
    token: str


class _PoolPackage:
    def __init__(self, middle):
        self.middle = middle

    def slow(self, request):
        time.sleep(0.6)
        return {"ok": True, "value": "done"}


class TestBusinessFacePool(unittest.TestCase):
    OPERATION = "tb.pool.slow"

    def setUp(self):
        dispatch_module.register_operation(
            self.OPERATION, _PoolPackage, "slow", _PoolRequest, replace=True
        )
        self.server = build_server("127.0.0.1", 0, object(), max_inflight=1)
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

    def _post(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(
            "POST",
            "/api/operation",
            json.dumps({"operation": self.OPERATION, "token": "tok"}),
            {"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        raw = resp.read().decode("utf-8")
        retry_after = resp.getheader("Retry-After")
        conn.close()
        return resp.status, raw, retry_after

    def _post_raw(self, body: bytes):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(
                "POST", "/api/operation", body,
                {"Content-Type": "application/json"},
            )
            resp = conn.getresponse()
            return resp.status, resp.read().decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - failure diagnostic
            return None, f"{type(exc).__name__}: {exc}"
        finally:
            conn.close()

    def test_json_parser_limits_return_400(self):
        """超长整数字面量/超深嵌套必须回 JSON 400，不得静默断连。"""
        long_int = (
            b'{"operation":"tb.pool.slow","token":"t","value":'
            + b"9" * 5000 + b"}"
        )
        deep = (
            b'{"operation":"tb.pool.slow","token":"t","value":'
            + b"[" * 5000 + b"]" * 5000 + b"}"
        )
        for label, body in (("long-int", long_int), ("deep", deep)):
            with self.subTest(label=label):
                status, raw = self._post_raw(body)
                self.assertEqual(status, 400, raw)
                self.assertIn("invalid JSON body", raw)

    def test_long_int_rejected_without_interpreter_limit(self):
        if not hasattr(sys, "set_int_max_str_digits"):
            self.skipTest("interpreter has no int_max_str_digits switch")
        previous = sys.get_int_max_str_digits()
        try:
            sys.set_int_max_str_digits(0)
            body = (
                b'{"operation":"tb.pool.slow","token":"t","value":'
                + b"9" * 5000 + b"}"
            )
            status, raw = self._post_raw(body)
        finally:
            sys.set_int_max_str_digits(previous)
        self.assertEqual(status, 400, raw)
        self.assertIn("invalid JSON body", raw)

    def test_non_finite_json_literals_are_400(self):
        for literal in (b"NaN", b"Infinity", b"-Infinity", b"1e400"):
            with self.subTest(literal=literal):
                body = (
                    b'{"operation":"tb.pool.slow","token":"t","timeout":'
                    + literal + b"}"
                )
                status, raw = self._post_raw(body)
                self.assertEqual(status, 400, raw)
                self.assertIn("invalid JSON body", raw)

    def test_unsupported_methods_return_json_405(self):
        for method in ("PUT", "DELETE", "OPTIONS", "TRACE", "PATCH"):
            with self.subTest(method=method):
                conn = http.client.HTTPConnection(
                    "127.0.0.1", self.port, timeout=10
                )
                conn.request(
                    method, "/api/operation", "{}",
                    {"Content-Type": "application/json"},
                )
                resp = conn.getresponse()
                raw = resp.read().decode("utf-8")
                conn.close()
                self.assertEqual(resp.status, 405, raw)
                self.assertEqual(resp.getheader("Allow"), "GET, POST")
                self.assertEqual(resp.getheader("Connection"), "close")
                self.assertEqual(json.loads(raw)["ok"], False)
                self.assertIn("method", raw.lower())

    def test_head_returns_405_without_body(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("HEAD", "/api/operation")
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        self.assertEqual(resp.status, 405)
        self.assertEqual(resp.getheader("Allow"), "GET, POST")
        self.assertEqual(body, b"")

    def test_405_with_body_closes_connection(self):
        import socket

        body = b'{"x":"yy"}'
        request = (
            b"PUT /api/operation HTTP/1.1\r\nHost: x\r\n"
            + f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
            + body
        )
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
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
        self.assertIn(b" 405 ", data.split(b"\r\n", 1)[0], data[:200])
        self.assertIn(b"Connection: close", data)
        self.assertNotIn(b"501", data)

    def test_malformed_content_length_with_body_closes(self):
        import socket

        body = b'{"operation":"tb.pool.slow","token":"t"}'
        request = (
            b"POST /api/operation HTTP/1.1\r\nHost: x\r\n"
            + f"Content-Length: abc\r\n\r\n".encode("ascii")
            + body
        )
        sock = socket.create_connection(("127.0.0.1", self.port), timeout=5)
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
        self.assertIn(b"Connection: close", data)
        self.assertIn(b"invalid JSON body", data)

    def test_over_limit_is_refused_with_429_and_retry_after(self):
        results = []

        def first():
            results.append(self._post())

        worker = threading.Thread(target=first)
        worker.start()
        time.sleep(0.2)  # the first request is now holding the only slot
        second_status, second_raw, retry_after = self._post()
        worker.join(timeout=10)

        self.assertEqual(second_status, 429, second_raw)
        self.assertIn("please retry", json.loads(second_raw)["error"])
        self.assertEqual(
            json.loads(second_raw)["error"], BUSY_ERROR.format(limit=1)
        )
        self.assertIsNotNone(retry_after)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0][0], 200, results[0][1])

    def test_health_reports_pool_state(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/health")
        resp = conn.getresponse()
        body = json.loads(resp.read().decode("utf-8"))
        conn.close()
        self.assertEqual(resp.status, 200)
        self.assertEqual(body["data"]["max_inflight"], 1)
        self.assertEqual(body["data"]["in_flight"], 0)

    def test_hot_resize_admits_more_requests(self):
        """v27: reload 热生效 business_thread_pool_size（可变准入上限）。"""
        first = []
        worker = threading.Thread(target=lambda: first.append(self._post()))
        worker.start()
        time.sleep(0.2)
        self.assertEqual(self._post()[0], 429, "limit=1 must refuse a second call")

        self.server.set_max_inflight(2)
        status, raw, _retry = self._post()
        self.assertEqual(status, 200, raw)
        worker.join(timeout=10)
        self.assertEqual(first[0][0], 200, first[0][1])

    def test_draining_refuses_new_requests_with_503(self):
        self.server.draining = True
        status, raw, retry_after = self._post()
        self.assertEqual(status, 503, raw)
        self.assertIn("restarting", json.loads(raw)["error"])
        self.assertIsNotNone(retry_after)

    def test_wait_idle_times_out_then_completes(self):
        worker = threading.Thread(target=self._post)
        worker.start()
        time.sleep(0.2)
        self.assertFalse(self.server.wait_idle(0.1))
        worker.join(timeout=10)
        self.assertTrue(self.server.wait_idle(2.0))


if __name__ == "__main__":
    unittest.main()
