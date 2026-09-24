"""`_maestro_util` 的**边界分支**契约（第六轮补测）。

覆盖率口径（`cov-main`）：该模块分支 76.8%，未覆盖的全是"读回/写回"里
**少见但真实**的输入形态——多点 Detail CSV（含 `Parameters:` 行与数字 Point 行）、
非数字 OCEAN 文本、`skill_alist` 的字符串/非法类型、`history_name_for_file` 的
空名与 `.log` 后缀、以及 `parse_overall_yield` 的数值强转兜底。

这些形态都来自真实 maestro 导出的文本，不是实现细节：
写错就会让"读回结果为空/参数丢失"这种静默错误回到生产路径。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.packages import _maestro_util as util


class TestSkillLiteralEdges(unittest.TestCase):
    def test_skill_value_never_silently_emits_a_wrong_literal(self):
        """JSON 表达不出来的类型（set/bytes/自定义对象）必须**报错**而不是产出垃圾字面量。

        现状：走到 `return q(value)` 时会从 `q()` 里冒 AttributeError/TypeError
        （q 期待 str）——已登记为 P-066（建议改成明确的 TypeError）。本断言只钉
        "不许静默出错字面量"，三种异常都放行，缺陷修好也不必改断言。
        """
        for bad in ({1, 2}, b"bytes", object()):
            with self.assertRaises((AttributeError, TypeError, ValueError)):
                util.skill_value(bad)

    def test_skill_alist_accepts_preformatted_string_and_rejects_blank(self):
        self.assertEqual(util.skill_alist("  (\"a\" 1)  "), '("a" 1)')
        self.assertIsNone(util.skill_alist("   "))

    def test_skill_alist_rejects_wrong_shape_and_unknown_type(self):
        with self.assertRaises(ValueError) as ctx:
            util.skill_alist([["a"]], name="opts")
        self.assertIn("opts[0]", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx2:
            util.skill_alist(5, name="opts")
        self.assertIn("alist string, mapping, or list of pairs", str(ctx2.exception))


class TestPairsAndHistoryEdges(unittest.TestCase):
    def test_pairs_to_dict_ignores_non_list_and_junk(self):
        self.assertEqual(util.pairs_to_dict("not-a-list"), {})
        self.assertEqual(util.pairs_to_dict(None), {})
        self.assertEqual(
            util.pairs_to_dict([["a", 1, 2], "junk", ["b"], ("c", 3)]),
            {"a": 1, "c": 3},
        )

    def test_history_name_for_file_edges(self):
        self.assertIsNone(util.history_name_for_file(""))
        self.assertIsNone(util.history_name_for_file("   "))
        self.assertEqual(util.history_name_for_file("run.log"), "run")
        self.assertEqual(util.history_name_for_file("run.msg.db"), "run")
        self.assertEqual(util.history_name_for_file("run7.rdb"), "run7")
        self.assertEqual(util.history_name_for_file("Interactive.3"), "Interactive.3")
        self.assertIsNone(util.history_name_for_file("junk.txt"))


class TestDetailCsvMultiPoint(unittest.TestCase):
    def test_parameters_rows_and_numeric_points_are_parsed(self):
        # 真实导出形态：每个扫描点一行 `Parameters:` + 紧随其后的数字 Point 行。
        text = (
            "Point,Test,Output,Nominal,Spec,Weight,Pass/Fail\n"
            "\"Parameters: temp=27, vdd=1.2, broken\",,,,,,\n"
            "1,ac,gain,10,\"0:20\",1,yes\n"
            "\"Parameters: temp=85, vdd=1.2\",,,,,,\n"
            "2,ac,gain,11,\"0:20\",1,no\n"
        )
        value = util.parse_detail_csv(text, history="multi")
        self.assertEqual(value["history"], "multi")
        points = value["points"]
        self.assertEqual(len(points), 2, "每个 Parameters 行开启一个新 point")
        self.assertEqual(points[0]["parameters"], {"temp": "27", "vdd": "1.2"})
        self.assertEqual(points[1]["parameters"], {"temp": "85", "vdd": "1.2"})
        self.assertEqual(points[0]["outputs"]["gain"]["value"], "10")
        self.assertEqual(points[1]["outputs"]["gain"]["pass_fail"], "no")
        self.assertEqual(value["tests"], ["ac"])
        self.assertEqual(len(value["outputs"]), 2)
        self.assertEqual([item["value"] for item in value["outputs"]], ["10", "11"])

    def test_unquoted_parameters_row_parses_all_parameters(self):
        """P-067：未加引号的 `Parameters: temp=27, vdd=1.2` 也要全解析。"""
        text = (
            "Point,Test,Output,Nominal,Spec,Weight,Pass/Fail\n"
            "Parameters: temp=27, vdd=1.2\n"
            "1,ac,gain,10,\"0:20\",1,yes\n"
        )
        params = util.parse_detail_csv(text, history="x")["points"][0]["parameters"]
        self.assertEqual(params, {"temp": "27", "vdd": "1.2"})

    def test_point_header_switches_back_to_multi_point_layout(self):
        text = (
            "Test,Output,Nominal,Spec,Weight,Pass/Fail\n"
            "ac,e2e_out,1.2,\"1.0:2.0\",1,yes\n"
            "Point,Test,Output,Nominal,Spec,Weight,Pass/Fail\n"
            "1,dc,vout,0.6,\"0.5:0.7\",1,yes\n"
        )
        value = util.parse_detail_csv(text)
        names = [item["name"] for item in value["outputs"]]
        self.assertIn("e2e_out", names)
        self.assertIn("vout", names)
        self.assertEqual(value["tests"], ["ac", "dc"])


class TestOceanAndYieldEdges(unittest.TestCase):
    def test_ocn_text_skips_non_numeric_columns(self):
        text = (
            "0 1.0 2.0\n"
            "x 1 2\n"                 # 第 1 列非数字 → 跳过
            "1 abc 2\n"               # 第 2/3 列非数字 → 退化成只有实数 y
            "2 3.5\n"
        )
        self.assertEqual(
            util.parse_ocn_text(text),
            [{"x": 0.0, "y": complex(1.0, 2.0)},
             {"x": 2.0, "y": 3.5}],
        )

    def test_parse_overall_yield_coerces_numeric_strings(self):
        value = util.parse_overall_yield("(yield \"100\" mean 3.5 sigma 1e-3 flag alnum)")
        self.assertEqual(value["yield"], 100)
        self.assertEqual(value["mean"], 3.5)
        self.assertEqual(value["sigma"], 0.001)
        self.assertEqual(value["flag"], "alnum")


if __name__ == "__main__":
    unittest.main()
