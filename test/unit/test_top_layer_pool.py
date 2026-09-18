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


if __name__ == "__main__":
    unittest.main()
