"""SKILL text utilities (``pyapi.packages.basic``) 的契约测试。

这些工具被 cellview/gui 等业务包共用：转义、tokenize、S 表达式解析、
字符串列表解析、单列表判定。全部不依赖中层/SSH。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pyapi.packages.basic import (
    escape_skill_string,
    is_single_complete_skill_list,
    parse_sexpr,
    parse_skill_str_list,
    q,
    scan_top_groups,
    tokenize_top_level,
)


class TestEscapeAndQuote(unittest.TestCase):
    def test_escape_backslash_and_quote(self):
        self.assertEqual(escape_skill_string("a\\b"), "a\\\\b")
        self.assertEqual(escape_skill_string('a"b'), 'a\\"b')
        self.assertEqual(escape_skill_string("plain"), "plain")

    def test_q_wraps_in_quotes(self):
        self.assertEqual(q("abc"), '"abc"')
        self.assertEqual(q('a"b'), '"a\\"b"')
        self.assertEqual(q("a\\b"), '"a\\\\b"')


class TestTokenizeTopLevel(unittest.TestCase):
    def test_defaults_include_groups_only(self):
        # 默认 include_groups=True，strings/atoms 为 False
        self.assertEqual(tokenize_top_level('a (b c) "d e"'), ["(b c)"])

    def test_atoms_groups_strings(self):
        tokens = tokenize_top_level(
            'a (b c) "d e" f',
            include_atoms=True, include_groups=True, include_strings=True,
        )
        self.assertEqual(tokens, ["a", "(b c)", '"d e"', "f"])

    def test_group_with_string_parens_is_one_token(self):
        tokens = tokenize_top_level('(x "(y)" z)', include_groups=True)
        self.assertEqual(tokens, ['(x "(y)" z)'])

    def test_escaped_quote_does_not_end_string(self):
        tokens = tokenize_top_level('"a\\"b" c', include_strings=True, include_atoms=True)
        self.assertEqual(tokens, ['"a\\"b"', "c"])

    def test_max_tokens_stops_early(self):
        tokens = tokenize_top_level("a b c d", include_atoms=True, max_tokens=2)
        self.assertEqual(tokens, ["a", "b"])

    def test_unterminated_string_takes_rest(self):
        tokens = tokenize_top_level('"unterminated', include_strings=True)
        self.assertEqual(tokens, ['"unterminated'])

    def test_unterminated_group_takes_rest(self):
        tokens = tokenize_top_level("(a (b)", include_groups=True)
        self.assertEqual(tokens, ["(a (b)"])


class TestScanTopGroups(unittest.TestCase):
    def test_only_groups(self):
        self.assertEqual(scan_top_groups('a (b) c (d (e))'), ["(b)", "(d (e))"])

    def test_no_groups(self):
        self.assertEqual(scan_top_groups("a b c"), [])


class TestParseSexpr(unittest.TestCase):
    def test_scalars(self):
        self.assertIsNone(parse_sexpr("nil"))
        self.assertIsNone(parse_sexpr(""))
        self.assertIs(parse_sexpr("t"), True)
        self.assertEqual(parse_sexpr("123"), "123")
        self.assertEqual(parse_sexpr("sym"), "sym")

    def test_string_escapes(self):
        self.assertEqual(parse_sexpr('"a\\nb"'), "a\nb")
        self.assertEqual(parse_sexpr('"a\\tb"'), "a\tb")
        self.assertEqual(parse_sexpr('"a\\rb"'), "a\rb")
        self.assertEqual(parse_sexpr('"a\\"b"'), 'a"b')
        self.assertEqual(parse_sexpr('"a\\\\b"'), "a\\b")
        self.assertEqual(parse_sexpr('"a\\qb"'), "a\\qb")   # 未知转义原样保留

    def test_nested_list(self):
        self.assertEqual(parse_sexpr('(1 nil (t "x"))'), ["1", None, [True, "x"]])

    def test_empty_list(self):
        self.assertEqual(parse_sexpr("()"), [])


class TestParseSkillStrList(unittest.TestCase):
    def test_list_of_strings(self):
        self.assertEqual(parse_skill_str_list('("a" "b" nil)'), ["a", "b"])

    def test_bare_top_level_strings(self):
        self.assertEqual(parse_skill_str_list('"a" "b"'), ["a", "b"])

    def test_nil_and_empty(self):
        self.assertEqual(parse_skill_str_list("nil"), [])
        self.assertEqual(parse_skill_str_list(""), [])

    def test_nested_strings_are_flattened(self):
        self.assertEqual(parse_skill_str_list('(("a") ("b" "c"))'), ["a", "b", "c"])

    def test_no_strings(self):
        # 原子不是字符串：不得作为字符串返回
        self.assertEqual(parse_skill_str_list("(1 2 3)"), [])

    def test_symbols_are_not_strings(self):
        self.assertEqual(parse_skill_str_list('(lib cell "real")'), ["real"])


class TestSingleCompleteSkillList(unittest.TestCase):
    def test_balanced_single_list(self):
        self.assertTrue(is_single_complete_skill_list("(a (b c))"))
        self.assertTrue(is_single_complete_skill_list("  (a)  "))

    def test_not_single_list(self):
        self.assertFalse(is_single_complete_skill_list("a"))
        self.assertFalse(is_single_complete_skill_list("(a) (b)"))
        self.assertFalse(is_single_complete_skill_list("(a"))
        self.assertFalse(is_single_complete_skill_list("(a))"))
        self.assertFalse(is_single_complete_skill_list("()" .replace("()", "(()")))

    def test_string_parens_ignored(self):
        self.assertTrue(is_single_complete_skill_list('(a "(" b)'))

    def test_escaped_quote_in_string(self):
        self.assertTrue(is_single_complete_skill_list('(a "x\\"(" b)'))


if __name__ == "__main__":
    unittest.main()
