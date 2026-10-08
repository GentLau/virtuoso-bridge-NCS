# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:06
# 依赖: 无
# =======================================================================
"""P-126 红钉（离线）：daemon `busy` 必须归类 `not_delivered`（确定未执行）。

回归判据（P-126 已修）：daemon 在读请求后直接 NAK busy、未碰 Virtuoso
（`src/bridge/resources/ramic_bridge_daemon_3.py:438-448`），属可安全重试的
not_delivered；`src/common/skill_client.py` 必须把 busy 单列为 not_delivered，
而真「结果未知」的 timeout 仍保持 delivered_unknown（负向守卫）。

第 1 步（环境检查）：离线用例，起本地假 daemon（只回一帧 busy），不连真机。
"""
from __future__ import annotations

import json
import socket
import sys
import threading
import unittest

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from common.skill_client import NAK, RS, SkillClient


class _StubDaemon(threading.Thread):
    """只回一帧指定 status 的 NAK，然后关闭连接（模拟 daemon 的确定状态机）。"""

    def __init__(self, status: str) -> None:
        super().__init__(daemon=True)
        self.status = status
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.bind(("127.0.0.1", 0))
        self._sock.listen(1)
        self.port = self._sock.getsockname()[1]

    def run(self) -> None:
        try:
            conn, _ = self._sock.accept()
        except OSError:
            return
        with conn:
            while conn.recv(65536):
                pass  # 读完整请求（客户端 shutdown(SHUT_WR) 后 EOF）
            payload = {
                "status": self.status,
                "code": f"skill_{self.status}",
                "error": f"SKILL channel {self.status}",
                "log": "",
            }
            conn.sendall(
                NAK.encode("utf-8")
                + json.dumps(payload).encode("utf-8")
                + RS.encode("utf-8")
            )

    def close(self) -> None:
        self._sock.close()


class TestBusyIsNotDelivered(unittest.TestCase):
    def test_busy_maps_to_not_delivered(self):
        daemon = _StubDaemon("busy")
        daemon.start()
        try:
            client = SkillClient(
                host="127.0.0.1", port=daemon.port, timeout=10, token="vb-offline",
            )
            result, delivery = client.execute_skill_checked("1+1")
            self.assertEqual(
                delivery,
                "not_delivered",
                f"busy 应属确定未执行；实际 delivery={delivery!r}"
                "（会把 token 误标 dirty，后续请求先走 probe 等待）",
            )
            self.assertFalse(result.ok, "busy 不应返回成功结果")
        finally:
            daemon.close()

    def test_timeout_stays_delivered_unknown(self):
        """负向守卫：真「结果未知」的 timeout 必须保持 delivered_unknown（防过度修复）。"""
        daemon = _StubDaemon("timeout")
        daemon.start()
        try:
            client = SkillClient(
                host="127.0.0.1", port=daemon.port, timeout=10, token="vb-offline",
            )
            _result, delivery = client.execute_skill_checked("1+1")
            self.assertEqual(delivery, "delivered_unknown")
        finally:
            daemon.close()
