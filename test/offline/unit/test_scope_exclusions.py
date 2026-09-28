# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 00:32
# 依赖: 无
# =======================================================================
"""`add-本版范围与明确不支持.md` 的"明确不做"契约（补红队 REVIEW-B #6 点名的 3 项）。

为什么要有它：该文档不在 `extract_spec_clauses.py` 的 13 份 NORMATIVE 输入里，矩阵没有它的行；
红队要求"要么补低成本离线契约，要么逐条登记 na"。本文件把 3 项**可机器验证的缺席**钉成契约：

1. **旧入口不存在**：CLI 不接受 `--profile`/`--env`/`--migrate` 之类的旧迁移入口（只认 host/port/work-dir）；
2. **顶层任务等待池不存在**：`server.dispatch`/`server.api_server` 不暴露 `task_pool`/`wait_pool` 等公共入口；
3. **非对称签名/HMAC 不存在**：`pyapi.models`/`register.models` 的数据类里没有任何 `signature`/`hmac`/`signed`
   类字段（本版只有 token 鉴权）。

判据是"这些名字真的不存在"。一旦有人加了它们，本文件会红——这是**有意的**：spec 声明本版不做，
要加必须先改 spec 与本契约。

六步流程（test/docs/写TB规范.md §1）——离线契约用例：
① 环境检查**不适用**（纯静态/反射，不连真机）；②③ 前置构建**不适用**；④ = 反射/源码解析；
⑤ = 缺席断言（不是 ok/rc）；⑥ 无现场可留。
"""
from __future__ import annotations

import importlib
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


class TestLegacyEntryPointsAbsent(unittest.TestCase):
    def test_cli_has_no_legacy_migration_flags(self):
        """spec：旧 `profile`/`VB_*`/`.env` 迁移入口不存在。"""
        from register import server as register_server

        source = Path(register_server.__file__).read_text(encoding="utf-8")
        options = set(re.findall(r'add_argument\(\s*"(--[A-Za-z0-9\-]+)"', source))
        self.assertIn("--host", options)
        self.assertIn("--port", options)
        self.assertIn("--work-dir", options)
        for forbidden in ("--profile", "--env", "--migrate", "--vb-env"):
            self.assertNotIn(forbidden, options, f"旧迁移入口 {forbidden} 不应存在（spec 明确不做）")

    def test_no_profile_module(self):
        for name in ("pyapi.profile", "server.profile", "register.profile", "common.profile"):
            with self.assertRaises(ModuleNotFoundError, msg=f"{name} 不应存在（旧入口已废）"):
                importlib.import_module(name)


class TestNoTaskWaitingPool(unittest.TestCase):
    def test_no_public_task_or_wait_pool(self):
        """spec：顶层不提供"任务等待池"这类公共入口。"""
        from server import api_server, dispatch

        for module in (dispatch, api_server):
            public = {n for n in dir(module) if not n.startswith("_")}
            for forbidden in ("task_pool", "wait_pool", "job_pool", "wait_for_task", "TaskPool"):
                self.assertNotIn(forbidden, public, f"{module.__name__} 不应暴露 {forbidden}")


class TestNoSignatureAuth(unittest.TestCase):
    def test_request_models_have_no_signature_fields(self):
        """spec：本版只有 token 鉴权，没有非对称签名/HMAC 字段。"""
        modules = (importlib.import_module("pyapi.models"),
                   importlib.import_module("register.models"))
        banned = ("signature", "hmac", "signed", "pubkey", "private_key")
        for module in modules:
            for name in dir(module):
                fields = getattr(getattr(module, name), "__dataclass_fields__", None)
                if not fields:
                    continue
                lowered = {str(f).lower() for f in fields}
                for bad in banned:
                    self.assertFalse(
                        any(bad in f for f in lowered),
                        f"{module.__name__}.{name} 含签名类字段 {bad}（spec 明确不做）",
                    )


if __name__ == "__main__":
    unittest.main()
