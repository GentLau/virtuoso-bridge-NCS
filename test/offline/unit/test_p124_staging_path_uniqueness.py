# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:06
# 依赖: 无
# =======================================================================
"""P-124 回归（离线）：不同远端路径的本地暂存不得同名同目录。

背景：`verilog.py`/`veriloga.py` 的 `_cache_dir()` 固定为
`artifact_dir()/verilog|veriloga`，本地文件名只取 `Path(remote).name`
（主文件名恒为 `verilog.v`/`veriloga.va`）→ 同进程并发请求读写同一文件，
后写覆盖先写，可能把 A cell 的内容上传给 B。

判据（修复无关）：对两个**不同远端路径**的读暂存，本地路径必须互不相同。

2026-10-08 已修：verilog/veriloga 本地暂存名按完整远端路径哈希唯一化；
skillref 改为按工作线程槽位的请求级暂存目录（新请求只替换本线程旧槽位，
不再 rmtree 共享目录）。skillref 行为级 TB 由测试侧后续补（见 P-124 卡尾）。

第 1 步（环境检查）：离线用例，fake middle 记录/落盘，不连真机。
"""
from __future__ import annotations

import sys
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pyapi.models import CommandResult
from pyapi.packages import verilog as verilog_mod
from pyapi.packages import veriloga as veriloga_mod


class _RecordingMiddle:
    """只记录/落盘，不连真机：download_file 写本地文件，upload_file 记录。"""

    def __init__(self) -> None:
        self.downloads: list[tuple[str, str]] = []
        self.uploads: list[tuple[str, str]] = []
        #: 下载落盘后调用的钩子（remote, target），用于编排确定性并发
        self.on_download = None

    def download_file(self, remote, local, timeout=None, token=None, recursive=False):
        target = Path(local)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(f"content:{remote}\n", encoding="utf-8")
        self.downloads.append((str(remote), str(target)))
        if self.on_download is not None:
            self.on_download(str(remote), str(target))
        return CommandResult(returncode=0, stdout="", stderr="")

    def upload_file(self, local, remote, timeout=None, token=None, recursive=False):
        self.uploads.append((str(local), str(remote)))
        return CommandResult(returncode=0, stdout="", stderr="")


def _request() -> SimpleNamespace:
    return SimpleNamespace(token="vb-offline", timeout=30)


class TestStagingPathUniqueness(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        root = Path(self._tmp.name)
        # _cache_dir 走 common.paths.artifact_dir；按模块打桩，避免动全局 work root
        self._patch = pytest.MonkeyPatch()
        self._patch.setattr(verilog_mod, "artifact_dir", lambda: root)
        self._patch.setattr(veriloga_mod, "artifact_dir", lambda: root)
        self.middle = _RecordingMiddle()

    def tearDown(self):
        self._patch.undo()

    def test_verilog_two_remotes_use_different_local_paths(self):
        pkg = verilog_mod.Package(self.middle)
        req = _request()
        pkg._read_remote("/srv/a/cellA/verilog/verilog.v", req)
        pkg._read_remote("/srv/a/cellB/verilog/verilog.v", req)
        first = self.middle.downloads[-2][1]
        second = self.middle.downloads[-1][1]
        self.assertNotEqual(
            first, second,
            "两个 cell 的 verilog.v 暂存到同一个本地文件（并发互踩）",
        )

    def test_veriloga_two_remotes_use_different_local_paths(self):
        pkg = veriloga_mod.Package(self.middle)
        req = _request()
        pkg._read_remote("/srv/a/cellA/veriloga/veriloga.va", req)
        pkg._read_remote("/srv/a/cellB/veriloga/veriloga.va", req)
        first = self.middle.downloads[-2][1]
        second = self.middle.downloads[-1][1]
        self.assertNotEqual(
            first, second,
            "两个 cell 的 veriloga.va 暂存到同一个本地文件（并发互踩）",
        )

    def test_concurrent_reads_do_not_cross_contaminate(self):
        """比"路径相同"更进一步：证明内容真的会串台。

        A 下载完自己的暂存后被卡住；B 完成并覆盖同名文件；A 随后读本地
        文件 → 若拿到 B 的内容，即跨请求内容串台（可能把 A 的源码读成 B 的）。
        """
        import threading

        pkg = verilog_mod.Package(self.middle)
        req = _request()
        remote_a = "/srv/a/cellA/verilog/verilog.v"
        remote_b = "/srv/a/cellB/verilog/verilog.v"
        started = threading.Event()
        release = threading.Event()
        holder: dict = {}

        def hook(remote: str, _target: str) -> None:
            if remote == remote_a:
                started.set()
                release.wait(timeout=10)

        self.middle.on_download = hook

        def read_a() -> None:
            holder["a"] = pkg._read_remote(remote_a, req)

        thread = threading.Thread(target=read_a, daemon=True)
        thread.start()
        try:
            self.assertTrue(started.wait(timeout=10), "A 未进入下载钩子")
            pkg._read_remote(remote_b, req)  # B 完成并覆盖同名暂存
        finally:
            release.set()
            thread.join(timeout=10)
        self.assertFalse(thread.is_alive(), "A 未返回")
        self.assertIn(
            "cellA",
            holder["a"],
            f"A 读到了别的 cell 的内容（跨请求串台）: {holder['a']!r}",
        )
