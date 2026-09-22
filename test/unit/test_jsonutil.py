"""Direct tests for the strict JSON parser used by the HTTP faces."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.jsonutil import loads_strict


class TestStrictJson(unittest.TestCase):
    def test_standard_document(self):
        self.assertEqual(
            loads_strict('{"a": [1, 2.5, true, false, null], "b": "x"}'),
            {"a": [1, 2.5, True, False, None], "b": "x"},
        )

    def test_rejects_non_finite_floats(self):
        for text in ("NaN", "Infinity", "-Infinity", "1e999", "-1e999"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    loads_strict(text)

    def test_rejects_js_constants(self):
        for text in ("NaN", "Infinity", "undefined"):
            with self.subTest(text=text):
                with self.assertRaises(ValueError):
                    loads_strict(text)

    def test_rejects_oversized_integer(self):
        big = "1" * 5000
        with self.assertRaises(ValueError):
            loads_strict(big)
        with self.assertRaises(ValueError):
            loads_strict("-" + big)
        self.assertEqual(loads_strict("9" * 4300),
                         int("9" * 4300))

    def test_rejects_malformed(self):
        for text in ("{", "[1,", '{"a":}', '"unterminated'):
            with self.subTest(text=text):
                with self.assertRaises(json.JSONDecodeError):
                    loads_strict(text)

    def test_escapes_and_unicode(self):
        self.assertEqual(loads_strict(r'{"k": "\u4e2d\n\t"}')["k"], "\u4e2d\n\t")


if __name__ == "__main__":
    unittest.main()
