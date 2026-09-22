"""Contract tests for ``pyapi.packages._maestro_util``.

The SKILL text utilities must be a single implementation: the maestro module
re-exports ``basic``'s functions instead of maintaining private copies.  These
tests lock that identity and cover the maestro-only parsing helpers the old
unit suite never exercised.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.packages import _maestro_util as util
from pyapi.packages import basic
from pyapi.packages import maestro


class TestNoDualImplementation(unittest.TestCase):
    def test_maestro_uses_basic_objects(self):
        # 相同语义：maestro 生产路径直接复用 basic 的实现对象
        self.assertIs(maestro.parse_sexpr, basic.parse_sexpr)
        self.assertIs(maestro.q, basic.q)

    def test_util_no_longer_exports_basic_parse_skill_str_list(self):
        # 语义不同：旧的同名实现已改名，不允许再出现双实现
        self.assertFalse(hasattr(util, "parse_skill_str_list"))


class TestQuoteAndUnquote(unittest.TestCase):
    def test_unquote_and_decode(self):
        self.assertEqual(util.unquote('"abc"'), "abc")
        self.assertEqual(util.unquote('"a\\"b\\\\c"'), 'a"b\\c')
        self.assertEqual(util.decode_skill_text('"line1\\nline2\\tend"'),
                         "line1\nline2\tend")

    def test_parse_bool(self):
        self.assertIs(util.parse_bool("t"), True)
        self.assertIs(util.parse_bool("nil"), False)
        self.assertIs(util.parse_bool("x"), None)


class TestSkillLiterals(unittest.TestCase):
    def test_skill_value(self):
        self.assertEqual(util.skill_value("a b"), '"a b"')
        self.assertEqual(util.skill_value(True), "t")
        self.assertEqual(util.skill_value(None), "nil")
        self.assertEqual(util.skill_value(2.5), "2.5")
        self.assertEqual(util.skill_value(["x", "y"]), '("x" "y")')
        self.assertEqual(util.skill_value({"a": "b"}), '(("a" "b"))')

    def test_skill_alist(self):
        self.assertEqual(util.skill_alist({"a": "b"}), '(("a" "b"))')
        self.assertEqual(util.skill_alist([["a", "b"], ["c", 1]]),
                         '(("a" "b") ("c" 1))')
        self.assertIsNone(util.skill_alist(None))
        with self.assertRaises(ValueError):
            util.skill_alist(["a", "b"])

    def test_skill_string_list(self):
        self.assertEqual(util.skill_string_list(["ac", "tran"]), '("ac" "tran")')


class TestProductionParsers(unittest.TestCase):
    def test_parse_sexpr_readback(self):
        self.assertEqual(
            util.parse_sexpr('(("name" "g") ("direction" "inputOutput") '
                             '("width" 1))'),
            [["name", "g"], ["direction", "inputOutput"], ["width", "1"]],
        )

    def test_parse_skill_str_leaves_sessions(self):
        self.assertEqual(util.parse_skill_str_leaves('("fnxSession28")'),
                         ["fnxSession28"])
        self.assertEqual(util.parse_skill_str_leaves('("ac" "tran")'),
                         ["ac", "tran"])
        self.assertEqual(util.parse_skill_str_leaves("nil"), [])

    def test_skill_str_leaves_keeps_symbols_while_basic_drops_them(self):
        self.assertEqual(util.parse_skill_str_leaves('(a "b")'), ["a", "b"])
        self.assertEqual(basic.parse_skill_str_list('(a "b")'), ["b"])

    def test_pairs_to_dict(self):
        self.assertEqual(
            util.pairs_to_dict([["name", "g"], ["direction", "inputOutput"]]),
            {"name": "g", "direction": "inputOutput"},
        )

    def test_overall_yield(self):
        value = util.parse_overall_yield(
            '(yield 100.0 mean 3.5 sigma 1.25)')
        self.assertEqual(value, {"yield": 100.0, "mean": 3.5, "sigma": 1.25})

    def test_ocn_points(self):
        self.assertEqual(
            util.parse_ocn_text("0 1.0 2.0\n1 3 4\n"),
            [{"x": 0.0, "y": complex(1.0, 2.0)},
             {"x": 1.0, "y": complex(3.0, 4.0)}],
        )

    def test_history_names_natural_sort(self):
        self.assertEqual(
            util.natural_sort_histories(
                ["Interactive.10", "Interactive.2", "run2.rdb", "run10.rdb"]),
            ["Interactive.2", "Interactive.10", "run2", "run10"],
        )

    def test_detail_csv_single_point_layout(self):
        text = (
            "Test,Output,Nominal,Spec,Weight,Pass/Fail\n"
            "ac,e2e_out,1.2,\"1.0:2.0\",1,yes\n"
        )
        value = util.parse_detail_csv(text, history="h1")
        self.assertEqual(value["history"], "h1")
        self.assertEqual(value["tests"], ["ac"])
        self.assertEqual(value["outputs"][0]["name"], "e2e_out")

    def test_skill_value_expr_numeric_and_bool(self):
        # 曾经因 skill_value 未导入而 NameError 的写入路径
        self.assertEqual(maestro._skill_value_expr(1.2), "1.2")
        self.assertEqual(maestro._skill_value_expr(True), "t")
        self.assertEqual(maestro._skill_value_expr([1, "a"]), '(1 "a")')


if __name__ == "__main__":
    unittest.main()
