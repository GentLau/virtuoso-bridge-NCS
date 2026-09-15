"""底层 daemon 的日志契约单元测试（分级 / 限长降级 / 区间读取 / 只读）。"""

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / "src" / "bridge" / "resources" / "ramic_bridge_daemon_3.py"


def load_daemon(name="daemon_under_test"):
    spec = importlib.util.spec_from_file_location(name, DAEMON)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)   # starts no server (only start_server() does)
    return mod


class DaemonLogContractBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = load_daemon()


class TestLevelClassification(DaemonLogContractBase):
    def test_classify(self):
        d = self.d
        self.assertEqual(d.classify_level("\\o normal line"), "info")
        self.assertEqual(d.classify_level("\\w warning line"), "warning")
        self.assertEqual(d.classify_level("\\e error line"), "error")
        self.assertEqual(d.classify_level("plain output"), "info")

    def test_keep_matrix(self):
        d = self.d
        err = "\\e boom"
        warn = "\\w careful"
        info = "\\o fine"
        self.assertTrue(d._keep("all", err))
        self.assertTrue(d._keep("all", warn))
        self.assertTrue(d._keep("all", info))
        self.assertTrue(d._keep("warn", err))
        self.assertTrue(d._keep("warn", warn))
        self.assertFalse(d._keep("warn", info))
        self.assertTrue(d._keep("error", err))
        self.assertFalse(d._keep("error", warn))
        self.assertFalse(d._keep("off", err))


class TestFilterDelta(DaemonLogContractBase):
    def test_all_returns_full_text(self):
        raw = "\\o one\n\\w two\n\\e three\n"
        text, degraded = self.d.filter_delta(raw, "all", 65536)
        self.assertFalse(degraded)
        self.assertIn("one", text)
        self.assertIn("two", text)
        self.assertIn("three", text)

    def test_error_level_keeps_only_errors(self):
        raw = "\\o one\n\\w two\n\\e three\n"
        text, degraded = self.d.filter_delta(raw, "error", 65536)
        self.assertIn("three", text)
        self.assertNotIn("one", text)
        self.assertFalse(degraded)

    def test_off_returns_empty(self):
        text, degraded = self.d.filter_delta("\\e boom\n", "off", 65536)
        self.assertEqual(text, "")

    def test_degrade_to_errors_when_over_limit(self):
        raw = "\\o " + "x" * 200 + "\n\\e kept\n"
        text, degraded = self.d.filter_delta(raw, "all", 40)
        self.assertTrue(degraded)
        self.assertIn("kept", text)
        self.assertIn("auto-degraded", text)

    def test_truncate_when_even_errors_are_too_long(self):
        raw = "\\e " + "y" * 500 + "\n\\o small\n"
        text, degraded = self.d.filter_delta(raw, "all", 30)
        self.assertTrue(degraded)
        self.assertIn("truncated", text)
        self.assertLessEqual(len(text.encode("utf-8")), 30 + 200)  # 提示语不受限，正文受限


class TestRangeReader(DaemonLogContractBase):
    def test_reads_exact_interval(self):
        f = Path(tempfile.mkdtemp()) / "CDS.log"
        f.write_bytes(b"0123456789")
        text, warn = self.d._read_range(str(f), 2, 6)
        self.assertEqual(text, "2345")
        self.assertIsNone(warn)

    def test_rotated_file_reads_from_zero(self):
        f = Path(tempfile.mkdtemp()) / "CDS.log"
        f.write_bytes(b"abc")
        text, warn = self.d._read_range(str(f), 100, 103)
        self.assertEqual(text, "abc")
        self.assertIsNone(warn)

    def test_missing_file_and_empty_path(self):
        self.assertEqual(self.d._read_range("", 0, 10), ("", "CDS.log path unavailable"))
        missing = Path(tempfile.mkdtemp()) / "nope.log"
        text, warn = self.d._read_range(str(missing), 0, 10)
        self.assertEqual(text, "")
        self.assertEqual(warn, "CDS.log unreadable")

    def test_reader_seam_is_used(self):
        """_read_range 必须经 _READER（BUG-3 之后的接缝，便于未来 split-host 替换）。"""
        calls = []

        class Spy:
            def read(self, path, start, end):
                calls.append((path, start, end))
                return "spy", None

        original = self.d._READER
        try:
            self.d._READER = Spy()
            self.assertEqual(self.d._read_range("p", 1, 2), ("spy", None))
        finally:
            self.d._READER = original
        self.assertEqual(calls, [("p", 1, 2)])


class TestNoInjection(unittest.TestCase):
    def test_daemon_never_writes_markers_into_cds_log(self):
        src = DAEMON.read_text(encoding="utf-8")
        self.assertNotIn("hiPrintToLogFile", src)
        for marker in ("VB-BEGIN", "VB-END", "STDOUT_B64_BEGIN"):
            self.assertNotIn(f'hiPrintToLogFile("{marker}', src)


if __name__ == "__main__":
    unittest.main()
