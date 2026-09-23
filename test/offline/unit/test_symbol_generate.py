"""Contract tests for ``pyapi.packages._symbol_generate`` and the symbol generate path.

P-016 补测：``_symbol_generate`` 与 ``pyapi.packages.symbol`` 此前在离线三层
（``test/offline/unit`` + ``test/offline/integration`` + ``test/offline/scenario``）零引用。本文件只锁定
**进程内可判定**的契约——生成出的 SKILL 文本结构、失败信封、回读解析、参数校验，
都不需要真机；真机 TSG 流程仍由 ``test/live/packages/symbol_e2e_tests.py`` 负责。

关键交叉契约：``generate_skill`` 写出的结果信封必须与 ``parse_generation_output``
认识的形状一致（``("generated" action terms order)`` / ``("failed" body cleanup)``），
两侧一旦各自漂移就是一个静默缺陷，故在此双向锁定。
"""
from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import _symbol_generate as util
from pyapi.packages import basic
from pyapi.packages import symbol as symbol_mod
from pyapi.packages.symbol import GenerateRequest, Package


class FakeMiddle:
    """Records ``execute_skill`` calls; the generate path touches nothing else."""

    def __init__(self, output: str = "", *, ok: bool = True, errors=()):
        self.calls: list[tuple[str, object, str]] = []
        self.output = output
        self.status = ExecutionStatus.SUCCESS if ok else ExecutionStatus.FAILURE
        self.errors = list(errors)

    def execute_skill(self, expr, timeout=None, *, token):
        self.calls.append((expr, timeout, token))
        return VirtuosoResult(
            status=self.status, output=self.output, errors=list(self.errors)
        )


def _generate(
    middle: FakeMiddle,
    *,
    library: str = "work",
    cell: str = "inv",
    schematic_view: str = "schematic",
    symbol_view: str = "symbol",
    sort_pins: str | None = None,
    overwrite: bool = False,
    timeout: int | None = 30,
):
    request = GenerateRequest(
        token="tok",
        library=library,
        cell=cell,
        schematic_view=schematic_view,
        symbol_view=symbol_view,
        sort_pins=sort_pins,
        overwrite=overwrite,
        timeout=timeout,
    )
    return Package(middle).generate(request)


class TestGenerateSkillText(unittest.TestCase):
    def test_default_views_are_schematic_and_symbol(self):
        skill = util.generate_skill("work", "inv")
        self.assertIn('dbOpenCellViewByType("work" "inv" "schematic" "schematic" "r")', skill)
        self.assertIn('"symbol"', skill)

    def test_views_must_differ(self):
        with self.assertRaises(ValueError) as ctx:
            util.generate_skill("work", "inv", schematic_view="x", symbol_view="x")
        self.assertIn("must differ", str(ctx.exception))

    def test_identifiers_are_escaped_for_skill_literals(self):
        lib = 'Li"b\\x'
        skill = util.generate_skill(lib, "cell")
        # 转义后的字面量在，原始未转义的字面量不在
        self.assertIn(f'"{basic.escape_skill_string(lib)}"', skill)
        self.assertNotIn(f'"{lib}"', skill)

    def test_overwrite_flag_is_rendered_as_skill_boolean(self):
        self.assertIn("vbReplacing && !nil", util.generate_skill("w", "c"))
        self.assertIn(
            "vbReplacing && !t", util.generate_skill("w", "c", overwrite=True)
        )

    def test_temp_and_backup_views_are_unique_per_call(self):
        first = util.generate_skill("w", "c")
        second = util.generate_skill("w", "c")
        temp = re.findall(r'"(__vb_symbol_[0-9a-f]{32})"', first)
        backup = re.findall(r'"(__vb_symbol_backup_[0-9a-f]{32})"', first)
        # 同一次生成里只引用一个临时/备份视图；不同次生成之间不复用名字
        self.assertGreaterEqual(len(temp), 1, "temp view missing")
        self.assertEqual(len(set(temp)), 1, f"temp view not unique: {set(temp)}")
        self.assertEqual(len(set(backup)), 1, f"backup view not unique: {set(backup)}")
        self.assertNotIn(temp[0], second)
        self.assertNotIn(backup[0], second)

    def test_stale_scratch_views_are_deleted_before_reuse(self):
        skill = util.generate_skill("w", "c")
        self.assertIn('error("temporary symbol delete failed")', skill)
        self.assertIn('error("symbol backup delete failed")', skill)

    def test_every_assigned_scratch_variable_is_declared_in_the_let_list(self):
        # SKILL 里未在 let 列表声明的赋值会落到全局/上一轮残留值上，是真机上极难
        # 复现的静默缺陷；这里按"赋值集合 ⊆ 声明集合"逐档锁定。
        for kwargs in ({}, {"sort_pins": "geometric"}, {"overwrite": True},
                       {"sort_pins": "alphanumeric", "overwrite": True}):
            with self.subTest(**kwargs):
                skill = util.generate_skill("w", "c", **kwargs)
                split = skill.index("vbTargetObj =")
                header, body = skill[:split], skill[split:]
                self.assertTrue(header.startswith("let((vb"), header[:40])
                declared = set(re.findall(r"\bvb[A-Za-z_]\w*", header))
                assigned = set(re.findall(r"\b(vb[A-Za-z_]\w*)\s*=", body))
                self.assertGreater(len(declared), 20)
                self.assertEqual(sorted(assigned - declared), [])

    def test_result_envelope_matches_parser_success_shape(self):
        skill = util.generate_skill("w", "c")
        self.assertIn('list("generated" vbAction vbFinalTerms vbFinalOrder)', skill)
        # 解析侧认得的成功信封
        action, terms, order = util.parse_generation_output(
            '("generated" "created" (("a" "input" 2)) ("a"))'
        )
        self.assertEqual(action, "created")
        self.assertEqual(terms, {"a": ("input", 2)})
        self.assertEqual(order, ("a",))

    def test_result_envelope_matches_parser_failure_shape(self):
        skill = util.generate_skill("w", "c")
        self.assertIn('"failed" if(vbBodyResult nil vbBodyFailure)', skill)
        # 解析侧认得的失败信封
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output('("failed" "structural failure" nil)')
        self.assertEqual(str(ctx.exception), "symbol generation failed: structural failure")

    def test_rollback_path_keeps_backup_and_reports_failure(self):
        skill = util.generate_skill("w", "c", overwrite=True)
        self.assertIn("target symbol rollback failed; backup retained as", skill)
        self.assertIn("target symbol rollback failed; backup unavailable", skill)

    def test_cleanup_failure_text_is_escaped(self):
        text = util._cleanup_close_skill("vbCv", 'close "failed"')
        self.assertIn('cons("close \\"failed\\"" vbCleanupFailures)', text)
        self.assertIn("errset(dbClose(vbCv) nil)", text)


class TestSortPinsRendering(unittest.TestCase):
    def test_none_leaves_schematic_environment_untouched(self):
        skill = util.generate_skill("w", "c")
        self.assertNotIn("ssgSortPins", skill)

    def test_supported_modes_are_rendered_and_restored(self):
        for mode in ("alphanumeric", "geometric"):
            with self.subTest(mode=mode):
                skill = util.generate_skill("w", "c", sort_pins=mode)
                self.assertIn(f'schSetEnv("ssgSortPins" "{mode}")', skill)
                self.assertIn('schSetEnv("ssgSortPins" vbOldSort)', skill)

    def test_unsupported_mode_is_rejected_before_any_skill_is_built(self):
        for bad in ("bogus", "ALPHANUMERIC", ""):
            with self.subTest(mode=bad):
                with self.assertRaises(ValueError) as ctx:
                    util.generate_skill("w", "c", sort_pins=bad)
                self.assertIn("sort_pins must be one of: alphanumeric, geometric",
                              str(ctx.exception))


class TestParseGenerationOutputSuccess(unittest.TestCase):
    def test_empty_terminal_set_is_accepted(self):
        self.assertEqual(
            util.parse_generation_output('("generated" "replaced" nil nil)'),
            ("replaced", {}, ()),
        )

    def test_pin_order_is_preserved_not_sorted(self):
        _, terms, order = util.parse_generation_output(
            '("generated" "created" (("z" "input" 1) ("a" "output" 8)) ("z" "a"))'
        )
        self.assertEqual(list(terms), ["z", "a"])
        self.assertEqual(order, ("z", "a"))

    def test_width_read_back_as_skill_string_is_coerced(self):
        _, terms, _ = util.parse_generation_output(
            '("generated" "created" (("bus" "input" "4")) ("bus"))'
        )
        self.assertEqual(terms, {"bus": ("input", 4)})

    def test_escaped_pin_names_survive_the_round_trip(self):
        name = 'a"b\\c'
        payload = (
            f'("generated" "created" (({basic.q(name)} {basic.q("input")} 1)) '
            f'({basic.q(name)}))'
        )
        _, terms, order = util.parse_generation_output(payload)
        self.assertEqual(terms, {name: ("input", 1)})
        self.assertEqual(order, (name,))


class TestParseGenerationOutputFailures(unittest.TestCase):
    def test_output_must_be_one_complete_skill_list(self):
        for bad in ("", "   ", "(", "(a) (b)", "nonsense", '("generated" "created") x'):
            with self.subTest(output=bad):
                with self.assertRaises(RuntimeError) as ctx:
                    util.parse_generation_output(bad)
                self.assertIn("must be a single complete SKILL list", str(ctx.exception))

    def test_body_failure_is_reported_with_its_message(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output('("failed" "source schematic not found" nil)')
        self.assertEqual(
            str(ctx.exception), "symbol generation failed: source schematic not found"
        )

    def test_cleanup_only_failure_is_reported_as_cleanup(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output(
                '("failed" nil ("temporary symbol cleanup failed"))'
            )
        self.assertEqual(
            str(ctx.exception),
            "symbol generation cleanup failed: temporary symbol cleanup failed",
        )

    def test_body_and_cleanup_failures_are_both_reported(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output(
                '("failed" "target symbol copy failed" ("created symbol rollback failed"))'
            )
        text = str(ctx.exception)
        self.assertIn("symbol generation failed: target symbol copy failed", text)
        self.assertIn("cleanup failed: created symbol rollback failed", text)

    def test_bare_failure_without_details_is_still_an_error(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output('("failed" nil nil)')
        self.assertIn("failed without details", str(ctx.exception))

    def test_unexpected_action_is_rejected(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output('("generated" "weird" nil nil)')
        self.assertIn("unexpected symbol generation action: weird", str(ctx.exception))

    def test_terminal_record_must_be_a_triple(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output('("generated" "created" (("a" "input")) ("a"))')
        self.assertIn("unexpected final terminal record", str(ctx.exception))

    def test_duplicate_terminal_is_rejected(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output(
                '("generated" "created" (("a" "input" 1) ("a" "input" 1)) ("a"))'
            )
        self.assertIn("duplicate final terminal: a", str(ctx.exception))

    def test_non_positive_width_is_rejected(self):
        for width in ("0", "-1"):
            with self.subTest(width=width):
                with self.assertRaises(RuntimeError) as ctx:
                    util.parse_generation_output(
                        f'("generated" "created" (("a" "input" {width})) ("a"))'
                    )
                self.assertIn("invalid final terminal width", str(ctx.exception))

    def test_non_numeric_width_is_rejected(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output(
                '("generated" "created" (("a" "input" wide)) ("a"))'
            )
        self.assertIn("invalid final terminal width", str(ctx.exception))

    def test_missing_pin_order_is_rejected(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output('("generated" "created" nil)')
        self.assertIn("missing", str(ctx.exception))

    def test_non_list_pin_order_is_rejected(self):
        with self.assertRaises(RuntimeError) as ctx:
            util.parse_generation_output('("generated" "created" nil "abc")')
        self.assertIn("unexpected final pin order payload", str(ctx.exception))


class TestPackageGenerate(unittest.TestCase):
    def test_created_symbol_is_reported_with_terminals_and_order(self):
        middle = FakeMiddle('("generated" "created" (("in" "input" 1) ("out" "output" 1)) '
                            '("out" "in"))')
        result = _generate(middle)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["action"], "created")
        self.assertEqual(result.value["terminal_names"], ["in", "out"])
        self.assertEqual(result.value["pin_order"], ["out", "in"])
        self.assertEqual(result.value["library"], "work")
        self.assertEqual(result.value["cell"], "inv")

    def test_replaced_symbol_reports_replaced_action(self):
        middle = FakeMiddle('("generated" "replaced" (("a" "input" 1)) ("a"))')
        result = _generate(middle, overwrite=True)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["action"], "replaced")

    def test_token_and_timeout_are_forwarded_to_the_middle(self):
        middle = FakeMiddle('("generated" "created" nil nil)')
        _generate(middle, timeout=45)
        expr, timeout, token = middle.calls[0]
        self.assertEqual((timeout, token), (45, "tok"))
        self.assertIn('ddGetObj("work" "inv" "symbol")', expr)

    def test_middle_failure_is_returned_with_its_errors(self):
        middle = FakeMiddle(ok=False, errors=["syntax error"])
        result = _generate(middle)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "syntax error")
        self.assertEqual([step["name"] for step in result.steps], ["generate"])
        self.assertFalse(result.steps[0]["ok"])

    def test_unparsable_output_becomes_a_typed_error(self):
        middle = FakeMiddle("(syntax error)")
        result = _generate(middle)
        self.assertFalse(result.ok)
        self.assertTrue(result.error.startswith("RuntimeError: "), result.error)

    def test_terminal_order_mismatch_is_rejected(self):
        middle = FakeMiddle('("generated" "created" (("a" "input" 1)) ("b"))')
        result = _generate(middle)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "generated symbol pin order mismatch")

    def test_request_validation_happens_before_any_skill_round_trip(self):
        cases = {
            "token": {"token": ""},
            "library": {"library": ""},
            "cell": {"cell": ""},
            "schematic_view": {"schematic_view": ""},
            "symbol_view": {"symbol_view": ""},
        }
        for name, override in cases.items():
            with self.subTest(field=name):
                middle = FakeMiddle()
                fields = {"token": "tok", "library": "work", "cell": "inv"}
                fields.update(override)
                request = GenerateRequest(**fields)
                with self.assertRaises(ValueError) as ctx:
                    Package(middle).generate(request)
                self.assertIn(name, str(ctx.exception))
                self.assertEqual(middle.calls, [])

    def test_identical_views_are_rejected(self):
        middle = FakeMiddle()
        with self.assertRaises(ValueError) as ctx:
            _generate(middle, schematic_view="v", symbol_view="v")
        self.assertIn("must differ", str(ctx.exception))
        self.assertEqual(middle.calls, [])

    def test_unsupported_sort_mode_is_rejected(self):
        middle = FakeMiddle()
        with self.assertRaises(ValueError) as ctx:
            _generate(middle, sort_pins="bogus")
        self.assertIn("alphanumeric/geometric/None", str(ctx.exception))
        self.assertEqual(middle.calls, [])

    def test_non_boolean_overwrite_is_rejected(self):
        middle = FakeMiddle()
        request = GenerateRequest(
            token="tok", library="work", cell="inv", overwrite="yes"
        )
        with self.assertRaises(ValueError) as ctx:
            Package(middle).generate(request)
        self.assertIn("overwrite must be a boolean", str(ctx.exception))
        self.assertEqual(middle.calls, [])

    def test_non_positive_timeout_is_rejected(self):
        for bad in (0, -1):
            with self.subTest(timeout=bad):
                middle = FakeMiddle()
                with self.assertRaises(ValueError) as ctx:
                    _generate(middle, timeout=bad)
                self.assertIn("timeout must be a positive number", str(ctx.exception))
                self.assertEqual(middle.calls, [])

    def test_skill_side_failure_envelope_surfaces_as_result_error(self):
        # SKILL 侧的结构化失败信封（回滚/清理路径）必须变成 Result.error，不抛给调用方
        middle = FakeMiddle('("failed" "target symbol exists" nil)')
        result = _generate(middle)
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "RuntimeError: symbol generation failed: target symbol exists")


class TestSymbolPackageExports(unittest.TestCase):
    def test_util_all_matches_public_names(self):
        self.assertEqual(
            set(util.__all__),
            {
                "SymbolGenerationAction",
                "SymbolGenerationResult",
                "SymbolPinSort",
                "generate_skill",
                "parse_generation_output",
            },
        )

    def test_package_uses_the_util_functions(self):
        self.assertIs(symbol_mod.generate_skill, util.generate_skill)
        self.assertIs(symbol_mod.parse_generation_output, util.parse_generation_output)

    def test_generation_result_dataclass_is_frozen(self):
        result = util.SymbolGenerationResult(
            lib="work",
            cell="inv",
            schematic_view="schematic",
            symbol_view="symbol",
            action="created",
            terminal_names=("a",),
            pin_order=("a",),
        )
        with self.assertRaises(Exception):
            result.lib = "other"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
