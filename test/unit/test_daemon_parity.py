"""Parity tests: the Python 3 and Python 2.7 daemons share one fixture set."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from bridge.resources import ramic_bridge_daemon_3 as d3
from bridge.resources import ramic_bridge_daemon_27 as d27

MODULES = [("daemon_3", d3), ("daemon_27", d27)]


class TestDaemonParity(unittest.TestCase):
    def _classify(self, mod, line):
        return mod.classify_level(line)

    def test_classify_parity(self):
        for name, mod in MODULES:
            self.assertEqual(mod.classify_level("\\e x"), "error", name)
            self.assertEqual(mod.classify_level("\\w x"), "warning", name)
            self.assertEqual(mod.classify_level("\\o x"), "info", name)
            self.assertEqual(mod.classify_level("plain"), "info", name)

    def test_filter_levels_parity(self):
        raw = "\\o out\n\\w warn\n\\e error\nVB-BEGIN\nVB-END\nplain\n"
        for name, mod in MODULES:
            text, _ = mod.filter_delta(raw, "off", 1000)
            self.assertEqual(text, "", name)
            text, _ = mod.filter_delta(raw, "warn", 1000)
            self.assertIn("warn", text, name)
            self.assertIn("error", text, name)
            self.assertNotIn("out", text, name)
            self.assertNotIn("plain", text, name)  # unclassified = info, dropped by warn
            text, _ = mod.filter_delta(raw, "error", 1000)
            self.assertIn("error", text, name)
            self.assertNotIn("warn", text, name)

    def test_truncation_degrade_parity(self):
        raw = "\\e " + ("x" * 200) + "\n" + ("\\o y\n" * 100)
        for name, mod in MODULES:
            text, truncated = mod.filter_delta(raw, "all", 50)
            self.assertTrue(truncated, name)
            self.assertIn("error-only", text, name)
            self.assertNotIn("\\o y", text, name)

    def test_parse_meta_parity(self):
        for name, mod in MODULES:
            self.assertEqual(mod._parse_meta(b"/tmp/CDS.log\x1f42"), ("/tmp/CDS.log", 42))
            self.assertEqual(mod._parse_meta(b"no-separator"), (None, 0))
            self.assertEqual(mod._parse_meta(b"/p\x1fabc"), ("/p", 0))

    def test_read_delta_increment_and_clamp(self):
        for name, mod in MODULES:
            mod._cursor_path = None
            mod._cursor_offset = 0
            f = Path(tempfile.mkdtemp()) / "CDS.log"
            f.write_bytes(b"abc")
            self.assertEqual(mod._read_delta(str(f), 2), "ab", name)
            self.assertEqual(mod._read_delta(str(f), 3), "c", name)
            # path switch resets
            f2 = Path(tempfile.mkdtemp()) / "other.log"
            f2.write_bytes(b"xy")
            self.assertEqual(mod._read_delta(str(f2), 2), "xy", name)
            # truncation / end < cursor must not raise
            # truncated/rotated file resets the cursor and rereads from 0
            mod._cursor_path = str(f2)
            mod._cursor_offset = 100
            self.assertEqual(mod._read_delta(str(f2), 50), "xy", name)


if __name__ == "__main__":
    unittest.main()
