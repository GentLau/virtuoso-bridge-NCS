"""spec《顶层》§3：**已定义路径**的非支持方法必须返回 405（且带 ``Allow``）。

原文：`"已定义路径的非支持方法 → 405（含 Allow）；未定义路径维持 404/501。"`

现状（第五轮真机 + 本节用例复现）：**业务面**只对 PUT/DELETE/OPTIONS/TRACE/
PATCH/CONNECT 与未知方法走 405，``do_GET``/``do_POST`` 落到"路径不匹配"时
直接回 **404 not found**，于是：

* ``GET /api/operation`` → 404（应为 405，路径已定义）
* ``POST /health`` / ``POST /help`` → 404（应为 405，路径已定义）

对照组：控制面的同类规则是**已实现且有用例**的
（``test_registration_server.py::test_405_carries_allow_and_closes`` 断言
``PATCH /api/register`` → 405 + ``Allow: GET, POST, PUT, DELETE``）。

本文件按 spec 断言，因此在修复前**是红的**（本轮"先钉住缺陷"口径，见
``test/reports/round5-*.md``）；修复后应自动转绿，不需要改本文件。

真机侧证据：``test/artifacts/evidence/round5-live-api/business-port-surface.json``
（8127 业务面实测 ``GET /api/operation`` → 404、无 ``Allow``）。
"""
from __future__ import annotations

import http.client
import json
import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from server import api_server


class TestBusinessFaceMethodNotAllowed(unittest.TestCase):
    """127.0.0.1:0 回环起业务面；只打路由分支，不触达中层。"""

    def setUp(self):
        self.server = api_server.build_server("127.0.0.1", 0, object(), max_inflight=4)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def _request(self, method: str, path: str, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        payload = None if body is None else json.dumps(body)
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        conn.request(method, path, payload, headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp, data

    def _assert_405(self, method: str, path: str, must_allow: str, body=None):
        resp, data = self._request(method, path, body)
        text = data.decode("utf-8", "replace")
        self.assertEqual(
            resp.status, 405,
            f"{method} {path} 是已定义路径的非支持方法，spec 顶层 §3 要求 405；"
            f"实际 {resp.status} {text[:120]!r}",
        )
        allow = resp.getheader("Allow") or ""
        self.assertIn(
            must_allow, allow,
            f"405 必须带 Allow（spec §3）；{method} {path} 的 Allow={allow!r}，"
            f"应包含 {must_allow!r}",
        )
        self.assertIn("method not allowed", text.lower(), text)

    # -- 应返 405 的四种（当前为红：实现回 404） -------------------------------------

    def test_get_on_operation_is_405(self):
        self._assert_405("GET", "/api/operation", "POST")

    def test_post_on_health_is_405(self):
        self._assert_405("POST", "/health", "GET")

    def test_post_on_help_is_405(self):
        self._assert_405("POST", "/help", "GET")

    def test_unknown_method_on_defined_path_is_405(self):
        self._assert_405("FOO", "/api/operation", "POST")

    # -- 已经正确、作为回归护栏 ---------------------------------------------------

    def test_put_on_operation_is_already_405(self):
        self._assert_405("PUT", "/api/operation", "POST")

    def test_undefined_paths_stay_404(self):
        for method, path in (("GET", "/no-such-path"), ("POST", "/no-such-path")):
            with self.subTest(method=method, path=path):
                resp, data = self._request(method, path)
                self.assertEqual(resp.status, 404, data)
                self.assertIn("not found", data.decode("utf-8", "replace"))


if __name__ == "__main__":
    unittest.main()
