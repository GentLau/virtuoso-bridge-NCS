import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from bridge.resources.ramic_bridge_daemon_27 import _parse_meta, filter_delta


class TestDaemon27(unittest.TestCase):
    def test_parse_meta(self):
        self.assertEqual(_parse_meta(b"/tmp/CDS.log\x1f42"), ("/tmp/CDS.log", 42))

    def test_filter_off(self):
        text, trunc = filter_delta("\\e err\n\\w warn\nVB-BEGIN\n", "off", 100)
        self.assertEqual(text, "")
        self.assertFalse(trunc)


if __name__ == "__main__":
    unittest.main()
