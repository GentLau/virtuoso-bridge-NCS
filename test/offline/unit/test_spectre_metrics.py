"""Contract tests for the spectre metric helpers (pure logic).
六步流程（test/docs/写TB规范.md §1）——离线用例：
① 环境检查**不适用**：纯函数 / 假 middle，不连真机；②③ 前置构建/校验**不适用**：无持久对象；
④⑤ = Arrange→Act→Assert；⑥ 无现场可留（不落盘、不起服务、不占端口）。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.packages._spectre_util import compute_metric


class TestAcMagnitude(unittest.TestCase):
    def test_db_scale_zero_magnitude_is_structured_error(self):
        result = compute_metric(
            {"freq": [1.0, 2.0], "vout": [0.0, 0.0]},
            {"type": "ac_magnitude", "signal": "vout", "x": "freq",
             "frequency": 1.0, "scale": "db"},
        )
        self.assertFalse(result["ok"])
        self.assertIsNone(result["value"])
        self.assertIn("detail", result)

    def test_db_scale_positive_magnitude(self):
        result = compute_metric(
            {"freq": [1.0], "vout": {"re": [10.0], "im": [0.0]}},
            {"type": "ac_magnitude", "signal": "vout", "x": "freq",
             "frequency": 1.0, "scale": "db"},
        )
        self.assertTrue(result["ok"])
        self.assertAlmostEqual(result["value"], 20.0)
        self.assertEqual(result["unit"], "dB")

    def test_linear_scale_zero_magnitude_is_valid(self):
        result = compute_metric(
            {"freq": [1.0], "vout": [0.0]},
            {"type": "ac_magnitude", "signal": "vout", "x": "freq",
             "frequency": 1.0, "scale": "linear"},
        )
        self.assertTrue(result["ok"])
        self.assertEqual(result["value"], 0.0)


if __name__ == "__main__":
    unittest.main()
