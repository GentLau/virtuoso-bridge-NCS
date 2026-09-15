"""local-mode 文件接口必须展开 ~（不得创建字面 ~ 目录）。"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from transport.middle import BusinessServer


class TestLocalTildeExpansion(unittest.TestCase):
    def test_upload_expands_tilde(self):
        home = Path(tempfile.mkdtemp())
        src = Path(tempfile.mkdtemp()) / "f.bin"
        src.write_bytes(b"payload")
        expand = lambda p: str(home) + p[1:] if str(p).startswith("~") else p
        with mock.patch("os.path.expanduser", side_effect=expand):
            r = BusinessServer._local_upload(src, "~/vb-test/f.bin", recursive=False, root=None)
        self.assertEqual(r.returncode, 0, r)
        self.assertTrue((home / "vb-test" / "f.bin").exists())

    def test_download_expands_tilde(self):
        home = Path(tempfile.mkdtemp())
        (home / "vb-test").mkdir(parents=True, exist_ok=True)
        (home / "vb-test" / "f.bin").write_bytes(b"payload")
        dst = Path(tempfile.mkdtemp()) / "out.bin"
        expand = lambda p: str(home) + p[1:] if str(p).startswith("~") else p
        with mock.patch("os.path.expanduser", side_effect=expand):
            r = BusinessServer._local_download("~/vb-test/f.bin", dst, recursive=False, root=None)
        self.assertEqual(r.returncode, 0, r)
        self.assertEqual(dst.read_bytes(), b"payload")


if __name__ == "__main__":
    unittest.main()
