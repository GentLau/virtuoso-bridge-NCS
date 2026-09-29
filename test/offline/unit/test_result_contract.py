# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 16:54
# 依赖: 无
# =======================================================================
"""C1 上层契约：公共 Result 的 steps 出现条件与 JSON 序列化边界。

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
from pyapi.packages import basic, cellview


class RecordingMiddle:
    def __init__(self, *, ok: bool = True) -> None:
        self.ok = ok

    def execute_skill(self, skill_code, timeout=None, *, token, **kwargs):
        if self.ok:
            return VirtuosoResult(
                status=ExecutionStatus.SUCCESS,
                output="2",
                execution_time=0.32900000002700835,
                log="\\e hello",
            )
        return VirtuosoResult(
            status=ExecutionStatus.ERROR,
            errors=["boom"],
            execution_time=0.5,
            log="\\e failure",
        )


class CellviewMiddle(RecordingMiddle):
    def execute_skill(self, skill_code, timeout=None, *, token, **kwargs):
        return VirtuosoResult(
            status=ExecutionStatus.SUCCESS,
            output='("ok" ("lib1"))',
            execution_time=0.125,
        )


def _json(result) -> dict:
    # import here so the test also documents the actual top-level serializer entry
    from server.dispatch import jsonable
    return jsonable(result)


class TestResultContract(unittest.TestCase):
    def test_success_omits_steps_by_default(self):
        request = basic.SkillRequest(
            token="t", skill_code="1+1",
        )
        result = basic.Package(RecordingMiddle()).execute_skill(request)
        body = _json(result)
        self.assertEqual(body["ok"], True)
        self.assertIsNone(body["error"])
        self.assertNotIn("steps", body)
        self.assertIn("result", body)
        self.assertNotIn("metadata", body["result"])
        self.assertNotIn("log", body["result"])
        self.assertIn("CDSlog", body["result"])
        self.assertEqual(body["result"]["execution_time"], 0.329)

    def test_step_details_true_keeps_steps(self):
        request = basic.SkillRequest(
            token="t", skill_code="1+1", step_details=True,
        )
        result = basic.Package(RecordingMiddle()).execute_skill(request)
        body = _json(result)
        self.assertIn("steps", body)
        self.assertEqual(len(body["steps"]), 1)
        self.assertEqual(body["steps"][0]["name"], "skill")
        self.assertIn("CDSlog", body["steps"][0]["detail"])

    def test_failure_keeps_steps_even_without_step_details(self):
        request = basic.SkillRequest(token="t", skill_code="1+1")
        result = basic.Package(RecordingMiddle(ok=False)).execute_skill(request)
        body = _json(result)
        self.assertEqual(body["ok"], False)
        self.assertIn("steps", body)
        self.assertFalse(body["steps"][0]["ok"])
        self.assertIn("failure", body["steps"][0]["detail"]["CDSlog"])

    def test_domain_result_obeys_same_rule(self):
        request = cellview.LibListRequest(token="t")
        middle = CellviewMiddle()
        plain = cellview.Package(middle).lib_list(request)
        self.assertNotIn("steps", _json(plain))
        detailed = cellview.Package(CellviewMiddle()).lib_list(
            cellview.LibListRequest(token="t", step_details=True)
        )
        self.assertIn("steps", _json(detailed))


if __name__ == "__main__":
    unittest.main()
