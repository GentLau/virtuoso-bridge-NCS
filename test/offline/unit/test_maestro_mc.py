# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 14:59
# 依赖: 无
# =======================================================================
"""Offline contracts for Monte Carlo run options and Yield-view parsing.

六步流程（test/docs/写TB规范.md §1）——离线用例：
① 环境检查不适用：纯函数，不连真机；
②③ 前置构建/校验不适用：输入是调研留下的真实 Yield CSV 文本；
④⑤ = Arrange→Act→Assert；⑥ 无现场可留（不落盘、不起服务、不占端口）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.packages import _maestro_util as util


# 2026-09-28 真机 /tmp/mc_dump/yield.csv（opamp_probe，2 点全 error）。
YIELD_SAMPLE = """\
Test,Name,Yield,Min,Target,Max,Mean,Std Dev,Cpk,Errors
Yield Estimate: 0 %(0 passed/2 pts)     Confidence Level: <not set>   Filter: <not set>,,,,,,,,,
opamp_ac,,,,,,,,,
,gain_db(summary),0% (0/2),0,> 19,0,0,0,,2
,gain_db,0% (0/2),0,> 19,0,0,0,,2
,gain_db_vdd_high,0% (0/2),0,> 19,0,0,0,,2
,ugbw_hz(summary),0% (0/2),0,> 8e5,0,0,0,,2
,ugbw_hz,0% (0/2),0,> 8e5,0,0,0,,2
,ugbw_hz_vdd_high,0% (0/2),0,> 8e5,0,0,0,,2
opamp_dc,,,,,,,,,
opamp_tran,,,,,,,,,
,vout_final(summary),0% (0/2),0,> 1.05,0,0,0,,2
,vout_final,0% (0/2),0,> 1.05,0,0,0,,2
,vout_final_vdd_high,0% (0/2),0,> 1.05,0,0,0,,2
,vout_max(summary),0% (0/2),0,< 1.2,0,0,0,,2
,vout_max,0% (0/2),0,< 1.2,0,0,0,,2
,vout_max_vdd_high,0% (0/2),0,< 1.2,0,0,0,,2
"""


class TestRunOptionNormalization(unittest.TestCase):
    def test_all_17_options_accept_one_valid_value(self):
        values = {
            "mcmethod": "mismatch",
            "mcnumpoints": 8,
            "mcnumbins": 10,
            "samplingmode": "lhs",
            "montecarloseed": 12345,
            "mcstartingrunnumber": 1,
            "dutsummary": "ac%I0%lib/cell/schematic%nch#",
            "ignoreflag": 1,
            "mcreferencepoint": 0,
            "donominal": True,
            "saveprocess": 1,
            "savemismatch": 1,
            "saveallplots": False,
            "mcStopEarly": True,
            "mcStopMethod": "Yield Verification",
            "mcYieldTarget": 99.73,
            "mcYieldAlphaLimit": 95,
        }
        self.assertEqual(set(values), set(util.MC_RUN_OPTIONS))
        for name, value in values.items():
            with self.subTest(name=name):
                normalized = util.normalize_run_option(name, value)
                self.assertIsInstance(normalized, str)
                self.assertTrue(normalized)

    def test_invalid_types_and_ranges_are_rejected(self):
        cases = [
            ("mcmethod", "typo"),
            ("samplingmode", "typo"),
            ("mcnumpoints", 0),
            ("mcnumpoints", 1.5),
            ("mcnumbins", -1),
            ("montecarloseed", -1),
            ("mcstartingrunnumber", 0),
            ("ignoreflag", 2),
            ("mcStopEarly", "maybe"),
            ("mcYieldTarget", 0),
            ("mcYieldAlphaLimit", 100),
            ("dutsummary", 3),
            ("no_such_option", "x"),
        ]
        for name, value in cases:
            with self.subTest(name=name, value=value):
                with self.assertRaises(ValueError):
                    util.normalize_run_option(name, value)

    def test_switch_and_bool_aliases_normalize(self):
        self.assertEqual(util.normalize_run_option("mcStopEarly", False), "nil")
        self.assertEqual(util.normalize_run_option("mcStopEarly", "t"), "t")
        self.assertEqual(util.normalize_run_option("donominal", "false"), "0")
        self.assertEqual(util.normalize_run_option("donominal", "yes"), "1")
        self.assertEqual(util.normalize_run_option("mcnumbins", ""), "")


class TestYieldCsvParser(unittest.TestCase):
    def test_live_yield_sample_is_parsed_by_test_summary_and_corner(self):
        parsed = util.parse_yield_csv(
            YIELD_SAMPLE,
            history="MonteCarlo.0",
            corners=["_default", "vdd_high"],
        )
        self.assertEqual(parsed["history"], "MonteCarlo.0")
        self.assertEqual(parsed["tests"], ["opamp_ac", "opamp_dc", "opamp_tran"])
        self.assertEqual(parsed["corners"], ["_default", "vdd_high"])
        self.assertEqual(parsed["overall"]["yield"], 0.0)
        self.assertEqual(parsed["overall"]["passed_points"], 0)
        self.assertEqual(parsed["overall"]["total_points"], 2)
        self.assertEqual(parsed["overall"]["error_points"], 2)
        self.assertIsNone(parsed["overall"]["confidence_level"])
        self.assertIsNone(parsed["overall"]["filter"])

        outputs = parsed["outputs"]
        self.assertEqual(len(outputs), 12)
        summary = outputs[0]
        self.assertEqual(summary["test"], "opamp_ac")
        self.assertEqual(summary["name"], "gain_db")
        self.assertTrue(summary["summary"])
        self.assertIsNone(summary["corner"])
        self.assertEqual(summary["yield"], 0.0)
        self.assertEqual(summary["min"], 0)
        self.assertEqual(summary["target"], "> 19")
        self.assertEqual(summary["target_value"], 19.0)
        self.assertEqual(summary["errors"], 2)
        self.assertIsNone(summary["cpk"])

        corner = next(
            item for item in outputs
            if item["name"] == "gain_db" and item["corner"] == "vdd_high"
        )
        self.assertFalse(corner["summary"])
        self.assertEqual(corner["raw_name"], "gain_db_vdd_high")

    def test_empty_text_is_an_empty_result(self):
        parsed = util.parse_yield_csv("", history="h")
        self.assertEqual(parsed["outputs"], [])
        self.assertEqual(parsed["overall"], {})

    def test_all_pass_overall_derives_zero_error_points(self):
        text = (
            "Test,Name,Yield,Min,Target,Max,Mean,Std Dev,Cpk,Errors\n"
            "Yield Estimate: 100 %(1 passed/1 pts)     "
            "Confidence Level: <not set>   Filter: <not set>,,,,,,,,,\n"
            "ac\n"
            ",out,100% (1/1),0.1,> 0,0.2,0.15,0.01,1.5,0\n"
        )
        parsed = util.parse_yield_csv(text, history="h")
        self.assertEqual(parsed["overall"]["passed_points"], 1)
        self.assertEqual(parsed["overall"]["total_points"], 1)
        self.assertEqual(parsed["overall"]["error_points"], 0)

    def test_target_numbers_are_extracted_but_raw_target_is_kept(self):
        text = (
            "Test,Name,Yield,Min,Target,Max,Mean,Std Dev,Cpk,Errors\n"
            "ac,,,,,,,,,\n"
            ",out,100% (2/2),0.1,maximize 0.05,0.2,0.15,0.01,1.5,0\n"
        )
        parsed = util.parse_yield_csv(text, history="h")
        self.assertEqual(parsed["outputs"][0]["target"], "maximize 0.05")
        self.assertEqual(parsed["outputs"][0]["target_value"], 0.05)


if __name__ == "__main__":
    unittest.main()
