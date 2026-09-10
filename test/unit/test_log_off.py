import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from bridge.resources.ramic_bridge_daemon_3 import filter_delta


class TestLogOff(unittest.TestCase):
    def test_off(self):
        raw = "\\e err\n\\w warn\n\\o out\nVB-BEGIN\nVB-END\n"
        text, trunc = filter_delta(raw, "off", 65536)
        self.assertEqual(text, "")
        self.assertFalse(trunc)


if __name__ == "__main__":
    unittest.main()
