"""local-mode 文件接口必须展开 ~（不得创建字面 ~ 目录）。"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from transport.middle import BusinessServer


class TestLocalTildeExpansion(unittest.TestCase):
    @staticmethod
    def _fake_home(home: Path):
        """Patch ``Path.expanduser`` portably (its 3.9 impl bypasses os.path)."""

        def expand(self):
            text = str(self)
            if text.startswith("~"):
                return Path(str(home) + text[1:])
            return self

        return expand

    def test_upload_expands_tilde(self):
        home = Path(tempfile.mkdtemp(prefix="vb-"))
        src = Path(tempfile.mkdtemp(prefix="vb-")) / "f.bin"
        src.write_bytes(b"payload")
        with mock.patch.object(Path, "expanduser", self._fake_home(home)):
            r = BusinessServer._local_upload(src, "~/vb-test/f.bin", recursive=False, root=None)
        self.assertEqual(r.returncode, 0, r)
        self.assertTrue((home / "vb-test" / "f.bin").exists())

    def test_download_expands_tilde(self):
        home = Path(tempfile.mkdtemp(prefix="vb-"))
        (home / "vb-test").mkdir(parents=True, exist_ok=True)
        (home / "vb-test" / "f.bin").write_bytes(b"payload")
        dst = Path(tempfile.mkdtemp(prefix="vb-")) / "out.bin"
        with mock.patch.object(Path, "expanduser", self._fake_home(home)):
            r = BusinessServer._local_download("~/vb-test/f.bin", dst, recursive=False, root=None)
        self.assertEqual(r.returncode, 0, r)
        self.assertEqual(dst.read_bytes(), b"payload")


if __name__ == "__main__":
    unittest.main()
