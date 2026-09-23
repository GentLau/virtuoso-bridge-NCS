"""Static contracts: log=off must not fetch the log at any layer."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

RES = Path(__file__).resolve().parents[3] / "src" / "bridge" / "resources"


class TestLogOffNoFetch(unittest.TestCase):
    def test_il_has_no_marker_injection(self):
        il = (RES / "ramic_bridge.il").read_text(encoding="utf-8")
        self.assertNotIn('hiPrintToLogFile("VB-BEGIN")', il)
        self.assertNotIn('hiPrintToLogFile("VB-END")', il)
        # every flush/fileLength/meta-frame send is gated by log_on
        # (log_on is parsed from the per-request "RBDLogOn=t" directive)
        self.assertIn("when(log_on", il)
        self.assertIn("hiFlushLogFile()", il)

    def test_daemons_gate_meta_frame_on_log_on(self):
        for name in ("ramic_bridge_daemon_3.py", "ramic_bridge_daemon_27.py"):
            src = (RES / name).read_text(encoding="utf-8")
            self.assertIn("log_on = log_level != \"off\"", src, name)
            self.assertIn("if log_on:", src, name)
            self.assertNotIn("_cursor_path", src, name)
            self.assertNotIn("VB-BEGIN", src, name)
            self.assertNotIn("VB-END", src, name)

    def test_off_level_maps_to_empty_log(self):
        sys.path.insert(0, str(RES.parent.parent))
        from bridge.resources.ramic_bridge_daemon_3 import filter_delta
        text, truncated = filter_delta("\\e err\n\\w warn\n", "off", 65536)
        self.assertEqual(text, "")
        self.assertFalse(truncated)


if __name__ == "__main__":
    unittest.main()
