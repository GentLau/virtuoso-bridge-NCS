"""Contract tests for the spectre metric helpers (pure logic)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

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
