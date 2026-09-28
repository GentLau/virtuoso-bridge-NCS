# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 20:25
# 依赖: 无
# =======================================================================
"""第八轮 spec 条款逐条核账暴露的未闭合缺口（g1/g2/g3 的 partial 项）。

每一条都对应一份 spec 文档里的规范性条款，此前只有"代码事实"没有防回归断言：

  * 注册#073  未知字段必须被拒绝（`extra=forbid` 在任何模型层都要生效）
  * 注册#018  未知 role 名（如 `banana`）必须与未知字段一样被拒绝
  * 注册#108  显式 `daemon_port != local_port` 必须拒绝或告警，不得静默归一化
              （P-079：当前实现静默取 local_port —— 本用例修复前是**红灯**）
  * 客户端#011 注册服务默认只绑 `127.0.0.1`
  * 日志#077  IL 必须把 value / log-meta 两帧合并成**一次** `ipcWriteProcess`
  * 注册#036  步内 deadline 不因 deploy 等待而重置（StepBudget 口径）
  * 路由#037  同一 token 内混合 local/remote 必须原样保留（daemon=local + command=remote）

第 1 步（环境检查）：离线用例，不需要真机环境检查。
第 3 步（构建前置）：每条用例自己造 registry / 请求对象，见 setUp。
"""

from __future__ import annotations

import hashlib
import http.client
import json
import sys
import threading
import unittest

import pytest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

import register.flow as register_flow
import register.server as register_server
from common.paths import registry_path
from common.registry import UserEntry, load_registry
from register.server import RegistrationServer
from transport.roles import resolve

_ADMIN_TOKEN = "test-admin-token"
ROOT = Path(__file__).resolve().parents[3]


class _ServerThread:
    def __init__(self, registry):
        self.server = RegistrationServer(("127.0.0.1", 0), registry, None)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def request(self, method, path, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            payload = None if body is None else json.dumps(body).encode("utf-8")
            conn.request(method, path, body=payload, headers=headers or {})
            response = conn.getresponse()
            raw = response.read()
            return response.status, response.getheader("Content-Type"), raw
        finally:
            conn.close()

    def json(self, method, path, body=None, headers=None):
        status, _ctype, raw = self.request(method, path, body, headers)
        return status, json.loads(raw.decode("utf-8"))


class _RegisterGapBase(unittest.TestCase):
    """共用：替换 admin token 哈希 + 起一个真实注册服务实例（127.0.0.1:0）。"""

    def setUp(self):
        self._saved_admin_hash = register_server._ADMIN_TOKEN_HASH
        register_server._ADMIN_TOKEN_HASH = hashlib.sha256(
            _ADMIN_TOKEN.encode("utf-8")
        ).hexdigest()
        self.registry = load_registry(registry_path())
        self._servers: list[_ServerThread] = []

    def tearDown(self):
        for srv in self._servers:
            srv.close()
        register_server._ADMIN_TOKEN_HASH = self._saved_admin_hash

    def start(self):
        srv = _ServerThread(self.registry)
        self._servers.append(srv)
        return srv


_REMOTE_APPLY = {
    "action": "apply",
    "mode": {"default": "remote"},
    "roles": {
        "daemon": {"host": "daemon-host", "user": "someone"},
        "command": {"host": "cmd-host", "user": "someone"},
        "file": {"host": "cmd-host", "user": "someone"},
    },
}


class TestUnknownFieldRejected(_RegisterGapBase):
    """注册#073：未知字段一律 4xx，且不得改变会话状态。"""

    def test_unknown_top_level_field_is_rejected(self):
        srv = self.start()
        payload = dict(_REMOTE_APPLY, user="ngap-unknown-field", surprise=1)
        status, body = srv.json("POST", "/api/register", payload)
        self.assertEqual(400, status, body)
        self.assertEqual("invalid request", body.get("error"), body)
        state_status, state = srv.json("GET", "/api/register/ngap-unknown-field")
        self.assertIn(state_status, (404, 400), state)

    def test_unknown_role_key_is_rejected(self):
        """注册#018：未知 role 名（`banana`）与未知字段同罪。"""
        srv = self.start()
        payload = {
            "user": "ngap-unknown-role",
            "action": "apply",
            "mode": {"default": "remote"},
            "roles": {"banana": {"host": "h", "user": "u"}},
        }
        status, body = srv.json("POST", "/api/register", payload)
        self.assertEqual(400, status, body)
        self.assertEqual("invalid request", body.get("error"), body)


class TestLocalJointPortNotCoerced(unittest.TestCase):
    """注册#108 / P-079：显式 daemon_port≠local_port 必须拒绝（当前红）。"""

    @pytest.mark.xfail(strict=True,
                       reason="P-079: local 显式双端口不等被静默归一化，待设计定口径")
    def test_explicit_mismatched_ports_are_not_silently_coerced(self):
        request = register_flow.RegistrationRequest(
            mode="local",
            user="ngap-joint-port",
            token="tok-ngap",
            roles={"daemon": {"daemon_port": 65091, "local_port": 65092}},
        )
        registry = load_registry(registry_path())
        try:
            flow = register_flow.RegistrationFlow(registry)
            flow.start(request)
            state = flow.validate()
        except Exception as exc:  # 直接拒绝也是合规的（spec：显式双值必须相等）
            self.assertIn("port", str(exc).lower(), str(exc))
            return
        self.assertTrue(
            state.errors or state.stage != "validated",
            "显式 daemon_port=65091 / local_port=65092 不一致：必须拒绝或报错，"
            f"实测 stage={state.stage} errors={state.errors}；"
            "P-079（flow.py:1180-1185 静默取 local_port 覆写两值）",
        )


class TestRegistrationBindsLoopback(unittest.TestCase):
    """客户端#011：`register.server` 默认 --host=127.0.0.1（不对外暴露）。"""

    def test_default_host_is_loopback(self):
        import ast

        tree = ast.parse((ROOT / "src" / "register" / "server.py").read_text(
            encoding="utf-8", errors="replace"))
        defaults: dict[str, object] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Attribute) and func.attr == "add_argument"):
                continue
            if not node.args or not isinstance(node.args[0], ast.Constant):
                continue
            if node.args[0].value != "--host":
                continue
            for kw in node.keywords:
                if kw.arg == "default" and isinstance(kw.value, ast.Constant):
                    defaults["--host"] = kw.value.value
        self.assertEqual("127.0.0.1", defaults.get("--host"),
                         f"注册面默认绑定地址必须回环，实测 {defaults}")


class TestIlSingleIpcWrite(unittest.TestCase):
    """日志#077：value 帧 + log-meta 帧必须一次 ipcWriteProcess 写出。"""

    def setUp(self):
        self.il = (ROOT / "src" / "bridge" / "resources" / "ramic_bridge.il").read_text(
            encoding="utf-8", errors="replace"
        )

    def test_exactly_one_write_call(self):
        calls = self.il.count("ipcWriteProcess(")
        self.assertEqual(
            1, calls,
            f"回包路径必须只有一次 ipcWriteProcess（实测 {calls} 次）——"
            "拆成两次写入会让 CIW 缓冲重排 value/meta 两帧",
        )

    def test_log_meta_frame_is_appended_to_same_buffer(self):
        self.assertIn("frames = strcat(frames", self.il,
                      "log-meta 帧必须 strcat 进同一个 frames 缓冲，再一次性写出")


class TestStepBudgetDoesNotReset(unittest.TestCase):
    """注册#036：步内相位共享同一条 deadline，deploy 等待不重置窗口。"""

    def test_budget_is_single_window(self):
        clock = {"t": 1000.0}
        with mock.patch("register.flow.time.monotonic", lambda: clock["t"]):
            budget = register_flow.StepBudget("probe", 30.0)
            clock["t"] += 12.0  # 模拟 deploy 等待
            self.assertAlmostEqual(18.0, budget.remaining(), places=6)
            self.assertFalse(budget.expired())
            clock["t"] += 19.0
            self.assertTrue(budget.expired())
            with self.assertRaises(register_flow.RegistrationProbeError):
                budget.remaining()

    def test_remaining_never_exceeds_step_seconds(self):
        budget = register_flow.StepBudget("verify", 30.0)
        self.assertLessEqual(budget.remaining(), 30.0)


class TestMixedModeSingleToken(unittest.TestCase):
    """路由#037：同一 token 内 daemon=local + command/file=remote 原样保留。"""

    def test_mixed_modes_are_preserved(self):
        entry = UserEntry(token="tok-mixed", mode="remote")
        entry.ssh.default.host = "daemon-host"
        entry.ssh.default.user = "alice"
        entry.roles.command.host = "cmd-host"
        entry.roles.command.user = "alice"
        entry.roles.file.host = "cmd-host"
        entry.roles.file.user = "alice"
        entry.roles.daemon.mode = "local"
        targets = resolve(entry, "alice")
        self.assertEqual("local", targets.daemon.mode)
        self.assertIsNone(targets.daemon.host, "local role 不得解析出 SSH 目标")
        self.assertEqual("remote", targets.command.mode)
        self.assertEqual("cmd-host", targets.command.host)
        self.assertEqual("remote", targets.file.mode)


if __name__ == "__main__":
    unittest.main()
