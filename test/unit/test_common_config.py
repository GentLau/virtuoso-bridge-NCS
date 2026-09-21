"""Contract tests for the process-level read-only config data."""

import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import MappingProxyType

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common import config


class TestConfigSnapshot(unittest.TestCase):
    def test_missing_invalid_and_non_object_file_mean_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            self.assertEqual(config.load_config_file(path), {})
            path.write_text("{bad", encoding="utf-8")
            self.assertEqual(config.load_config_file(path), {})
            path.write_text("[]", encoding="utf-8")
            self.assertEqual(config.load_config_file(path), {})

    def test_reload_snapshot_is_frozen_and_reports_arbitrary_sections(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(
                json.dumps({
                    "future_section": {"x": 1},
                    "skillref": {"source": "remote"},
                }),
                encoding="utf-8",
            )
            snapshot = config.reload_config(path)
            self.assertIsInstance(snapshot, MappingProxyType)
            with self.assertRaises(TypeError):
                snapshot["future_section"]["x"] = 2
            self.assertEqual(
                config.snapshot_dict()["future_section"], {"x": 1}
            )
            self.assertEqual(
                dict(config.section("skillref") or {}), {"source": "remote"}
            )

    def test_value_and_section_read_without_interpreting(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "config.json"
            path.write_text(
                json.dumps({"business_thread_pool_size": 8}),
                encoding="utf-8",
            )
            config.reload_config(path)
            self.assertEqual(config.value("business_thread_pool_size"), 8)
            self.assertIsNone(config.section("unknown"))


if __name__ == "__main__":
    unittest.main()
