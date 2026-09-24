"""calibre **LVS 结论归一化在两条解析路径上必须一致**（第六轮补测，钉 P-071）。

背景（2026-09-24 真机验证发现）：`calibre.read_results` 的 LVS 结论可能来自两条路径——

* **报告路径**：`_calibre_util.parse_lvs_report()`（读 `lvs.rep`）→ `"not_compared"`（下划线，已归一）；
* **日志路径**：`_calibre_util.parse_log_counters()` 抓 `LVS completed. NOT COMPARED.` 后
  `.lower()` → `"not compared"`（**空格**，未归一）；

而 `calibre.py:468-469` 在 LVS 上**优先用日志路径**覆盖报告结论 ⇒ 真机 `read_results`
实际返回 `"not compared"`，与离线契约/spec 的枚举不一致，调用方无法用统一枚举判断。

本文件把"两条路径必须给出同一个枚举值"钉死（现在会红 = P-071）；修好后自动转绿。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.packages import _calibre_util as util

ROOT = Path(__file__).resolve().parents[3]
LVS_REPORT = (ROOT / "test" / "shared" / "fixtures" / "calibre_lvs_rep_sample.txt").read_text(
    encoding="utf-8")
LVS_LOG = "LVS completed. NOT COMPARED.\n"


class TestLvsVerdictConsistency(unittest.TestCase):
    def test_report_path_normalises_to_underscore_enum(self):
        self.assertEqual(util.parse_lvs_report(LVS_REPORT)["status"], "not_compared")

    def test_log_path_must_use_the_same_enum(self):
        """P-071：日志路径也要归一成 `not_compared`（而不是 `not compared`）。"""
        counters = util.parse_log_counters(LVS_LOG)
        self.assertEqual(
            counters.get("lvs_status"), "not_compared",
            "日志路径的 LVS 结论必须与报告路径同一枚举（not_compared）")

    def test_both_paths_agree_on_correct_and_incorrect_too(self):
        for raw, expected in (("CORRECT", "correct"), ("INCORRECT", "incorrect"),
                              ("NOT COMPARED", "not_compared")):
            with self.subTest(raw=raw):
                self.assertEqual(
                    util.parse_log_counters(f"LVS completed. {raw}.\n").get("lvs_status"),
                    expected)


if __name__ == "__main__":
    unittest.main()
