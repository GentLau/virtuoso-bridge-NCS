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

    def test_root_is_default_dir_not_a_sandbox(self):
        """总览#215：role `root` 只是**默认工作目录约定**，不是沙箱。

        * 相对路径 → 拼到 root 下（默认目录约定的作用）；
        * **绝对路径**（即使落在 root 之外）→ 原样使用，不被拦截；
        * `..` → 按 OS 语义处理，可以落到 root 之外。

        条款后半段"同账号不同 user 不承诺跨目录隔离、安全边界由 OS 权限提供"是**不承诺**语义，
        没有可断言的正面行为，故不在本用例里伪造判据。
        """
        tmp = Path(tempfile.mkdtemp(prefix="vb-"))
        src = tmp / "f.bin"
        src.write_bytes(b"payload")
        root = tmp / "rootdir"
        root.mkdir()
        outside = tmp / "outside"
        outside.mkdir()

        rel = BusinessServer._local_upload(src, "rel/f.bin", recursive=False, root=str(root))
        self.assertEqual(rel.returncode, 0, rel)
        self.assertTrue((root / "rel" / "f.bin").is_file())

        target = outside / "abs.bin"
        absolute = BusinessServer._local_upload(
            src, str(target), recursive=False, root=str(root))
        self.assertEqual(absolute.returncode, 0, absolute)
        self.assertTrue(target.is_file(), "绝对路径（在 root 之外）被拦截了——root 不是沙箱")

        dotted = BusinessServer._local_upload(
            src, str(root / "sub" / ".." / "up.bin"), recursive=False, root=str(root))
        self.assertEqual(dotted.returncode, 0, dotted)
        self.assertTrue((root / "up.bin").is_file())


if __name__ == "__main__":
    unittest.main()
