"""spec §5.8：`timeout` 是**全部业务操作**的通用参数（模型级逐 op 断言）。

口径（第八轮"每个可传参数"）：`timeout` 不是某个 op 的专属字段，而是 79 个
业务操作请求模型的通用可选字段（默认 None = 用接口默认预算 30s）。因此：

* **参数面**：本文件逐 op 断言其 Request 模型暴露 `timeout` 且默认 None（79/79）；
* **语义面**：由接口级用例钉住 —— `test/offline/core/semantics_tb.py`
  （skill/command/upload/download 的预算不被忽略）、
  `test/semi/transport/ssh_backend_semi_tb.py`（命令 timeout=1 触发 TimeoutExpired）、
  `test/live/packages/infra_e2e_tests.py` BASIC-05（真机 `sleep 5` + timeout=1 →
  kind=timeout / rc=124）、`test/live/e2e/test_e2e_live.py`（SKILL 超时）。
"""
from __future__ import annotations

import dataclasses
import importlib
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from server.api_server import PACKAGES  # noqa: E402


class TestAllOpsTimeoutField(unittest.TestCase):
    def test_every_operation_model_exposes_timeout(self) -> None:
        total = 0
        missing: list[str] = []
        bad_default: list[str] = []
        for module_name, class_name, ops_name in PACKAGES:
            module = importlib.import_module(module_name)
            self.assertTrue(hasattr(module, class_name), module_name)
            for entry in getattr(module, ops_name):
                op, model = entry[0], entry[2]
                total += 1
                fields = {f.name: f for f in dataclasses.fields(model)}
                if "timeout" not in fields:
                    missing.append(f"{op} -> {model.__name__}")
                    continue
                default = fields["timeout"].default
                if default is not dataclasses.MISSING and default is not None:
                    bad_default.append(f"{op} default={default!r}")
        self.assertEqual(total, 79, f"OPERATIONS 总数变了：{total}")
        self.assertEqual(missing, [], f"缺 timeout 的 op：{missing}")
        self.assertEqual(bad_default, [], f"timeout 默认值不是 None：{bad_default}")


if __name__ == "__main__":
    unittest.main()
