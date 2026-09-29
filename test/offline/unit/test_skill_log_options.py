# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 15:45
# 依赖: 无
# =======================================================================
"""C2 契约：Skill 调用的 `log_level` / `log_max_bytes` 原样透传中层。

范围：只覆盖 `middle.execute_skill`。`run_command` / 文件 / GUI / Spectre
命令不在本 TB 的断言范围内。

六步流程（test/docs/写TB规范.md §1）——离线用例：
① 环境检查不适用：纯函数 / 假 middle，不连真机；
②③ 前置构建/校验不适用：无持久对象；
④⑤ = Arrange→Act→Assert；⑥ 无现场可留（不落盘、不起服务、不占端口）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import (
    basic,
    calibre,
    cellview,
    layout,
    maestro,
    schematic,
    symbol,
    verilog,
    veriloga,
)
from server import dispatch


def _registered_request(module, method_name: str):
    for _operation, method, request_model, _result in module.OPERATIONS:
        if method == method_name:
            return request_model
    raise AssertionError(f"{module.__name__} has no operation method {method_name}")


class RecordingMiddle:
    def __init__(self) -> None:
        self.skill_calls: list[dict] = []

    def execute_skill(self, skill_code, timeout=None, *, token, **kwargs):
        self.skill_calls.append({
            "skill_code": skill_code,
            "timeout": timeout,
            "token": token,
            **kwargs,
        })
        # cellview.lib_list 的 _run_skill 需要一个 `("ok" ...)` 形状。
        return VirtuosoResult(status=ExecutionStatus.SUCCESS,
                              output='("ok" ("lib1"))')


class TestSkillLogOptionsPassThrough(unittest.TestCase):
    def test_registered_skill_request_models_expose_both_fields(self):
        modules = (
            basic, calibre, cellview, layout, maestro,
            schematic, symbol, verilog, veriloga,
        )
        only = {
            basic.__name__: {"execute_skill"},
            calibre.__name__: {"export_cdl"},
        }
        checked = 0
        for module in modules:
            allowed = only.get(module.__name__)
            for operation, method, request_model, _result in module.OPERATIONS:
                if allowed is not None and method not in allowed:
                    continue
                fields = getattr(request_model, "__dataclass_fields__", {})
                with self.subTest(operation=operation):
                    self.assertIn("log_level", fields)
                    self.assertIn("log_max_bytes", fields)
                checked += 1
        self.assertGreater(checked, 40)

    def test_non_skill_operations_do_not_gain_log_fields(self):
        cases = [
            (basic, "run_command"),
            (calibre, "drc"),
        ]
        for module, method in cases:
            with self.subTest(module=module.__name__, method=method):
                request_model = _registered_request(module, method)
                fields = getattr(request_model, "__dataclass_fields__", {})
                self.assertNotIn("log_level", fields)
                self.assertNotIn("log_max_bytes", fields)

    def test_basic_skill_request_accepts_and_passes_both_fields(self):
        request_model = _registered_request(basic, "execute_skill")
        middle = RecordingMiddle()
        request = request_model(
            token="t", skill_code="1+1",
            log_level="warn", log_max_bytes=1234,
        )
        result = basic.Package(middle).execute_skill(request)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(middle.skill_calls[0]["log_level"], "warn")
        self.assertEqual(middle.skill_calls[0]["log_max_bytes"], 1234)

    def test_absent_log_options_are_not_passed(self):
        request_model = _registered_request(basic, "execute_skill")
        middle = RecordingMiddle()
        request = request_model(token="t", skill_code="1+1")
        result = basic.Package(middle).execute_skill(request)
        self.assertTrue(result.ok, result.error)
        self.assertNotIn("log_level", middle.skill_calls[0])
        self.assertNotIn("log_max_bytes", middle.skill_calls[0])

    def test_each_option_can_be_provided_independently(self):
        request_model = _registered_request(basic, "execute_skill")
        cases = [
            ({"log_level": "error"}, "log_level", "error"),
            ({"log_max_bytes": 4096}, "log_max_bytes", 4096),
        ]
        for fields, key, expected in cases:
            with self.subTest(fields=fields):
                middle = RecordingMiddle()
                request = request_model(token="t", skill_code="1+1", **fields)
                result = basic.Package(middle).execute_skill(request)
                self.assertTrue(result.ok, result.error)
                self.assertEqual(middle.skill_calls[0][key], expected)
                other = "log_max_bytes" if key == "log_level" else "log_level"
                self.assertNotIn(other, middle.skill_calls[0])

    def test_domain_skill_operation_passes_the_same_fields(self):
        request_model = _registered_request(cellview, "lib_list")
        middle = RecordingMiddle()
        request = request_model(
            token="t", log_level="all", log_max_bytes=65536,
        )
        result = cellview.Package(middle).lib_list(request)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(middle.skill_calls[0]["log_level"], "all")
        self.assertEqual(middle.skill_calls[0]["log_max_bytes"], 65536)

    def test_top_level_request_build_accepts_log_fields(self):
        request_model = _registered_request(basic, "execute_skill")
        spec = dispatch.OperationSpec(
            basic.Package, "execute_skill", request_model,
        )
        request = dispatch.build_request(
            spec,
            {"skill_code": "1+1", "log_level": "off", "log_max_bytes": 16},
            "t",
        )
        self.assertEqual(request.log_level, "off")
        self.assertEqual(request.log_max_bytes, 16)


if __name__ == "__main__":
    unittest.main()
