# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:06
# 依赖: 无
# =======================================================================
"""P-123 红钉（离线）：业务面必须在大 body 之前给出结构化 4xx（与注册面同口径）。

回归判据（P-123 已修）：`src/server/api_server.py::_read_json` 对
`Content-Length` 有与控制面一致的 16 MiB 上限。本用例声明 17 MiB 长度
但只发一小段 body：服务端必须在读取前给出结构化 413，客户端很快读到响应。

第 1 步（环境检查）：离线用例，`build_server` 起 127.0.0.1:0 回环 + 空 middle。
"""
from __future__ import annotations

import http.client
import json
import socket
import sys
import threading
import unittest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from server import api_server

_OVER_LIMIT = 17 * 1024 * 1024
_READ_TIMEOUT = 6.0


class TestBusinessFaceBodyLimit(unittest.TestCase):
    def setUp(self):
        self.server = api_server.build_server("127.0.0.1", 0, object(), max_inflight=4)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def test_small_request_still_gets_structured_response(self):
        """控制组：正常体积请求不受影响（现在就是绿的）。"""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(
            "POST", "/api/operation",
            json.dumps({"operation": "vb.nonexistent"}),
            {"Content-Type": "application/json"},
        )
        resp = conn.getresponse()
        self.assertTrue(400 <= resp.status < 500, f"unexpected status {resp.status}")
        conn.close()

    def test_oversized_content_length_rejected_before_body_read(self):
        conn = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        try:
            conn.sendall(
                b"POST /api/operation HTTP/1.1\r\n"
                b"Host: 127.0.0.1\r\n"
                b"Content-Type: application/json\r\n"
                b"Content-Length: " + str(_OVER_LIMIT).encode("ascii") + b"\r\n"
                b"Connection: close\r\n\r\n"
                + b'{"operation":"basic.skill.execute","token":"vb-offline"'
            )
            conn.settimeout(_READ_TIMEOUT)
            try:
                head = conn.recv(128)
            except socket.timeout:
                self.fail(
                    f"{_READ_TIMEOUT:g}s 内无响应：服务端在按声明的 "
                    f"{_OVER_LIMIT} 字节等 body（业务面无上限）"
                )
            self.assertTrue(head.startswith(b"HTTP/1."), f"响应头异常: {head[:80]!r}")
            status = int(head.split(b" ", 2)[1])
            self.assertEqual(
                status, 413,
                "期望在读取前给出结构化 413（与控制面同口径）",
            )
        finally:
            conn.close()
