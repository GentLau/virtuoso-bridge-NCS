"""P-081：`file_is_local=False` 时远端 POSIX 路径不得被本地 pathlib 改写。

`verilog.read` / `veriloga.read` 的文件分支把 `request.file_path` 先转成
`pathlib.Path`，再把 `str(path)` 交给下载：在 **Windows 客户端**上
`Path("/home/u/x.v")` 会变成 `\\home\\u\\x.v`，远端（Linux）按相对路径解析到
role root 下面 → "download requires a regular file: <root>/\\home\\u\\x.v"。
同一段代码里 `source.path` 回显也会变成反斜杠形态，Linux 客户端则正常 ——
违反 spec 的 Windows/Linux 一致性要求。

判据：用一个只记录 `download_file(remote_path, ...)` 的 stub，断言传给传输层
的字符串与请求里的 POSIX 路径逐字节一致。

平台口径（2026-09-28 修订）：该缺陷**只在 Windows 客户端**复现（PosixPath 不改写）。
因此 xfail 带 `condition=WINDOWS`：Windows 上修复前 xfail、修复后 XPASS 转红提醒删标记；
Linux 上按正常用例跑（断言正确行为成立），不再出现“正确的平台反而 XPASS 失败”。
"""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pyapi.packages import verilog as VLOG  # noqa: E402
from pyapi.packages import veriloga as VLOGA  # noqa: E402

REMOTE = "/home/u/proj/design/x.v"
WINDOWS = os.name == "nt"


class _Recorder:
    def __init__(self) -> None:
        self.downloads: list[str] = []

    def download_file(self, remote_path, local_path, **kwargs):  # noqa: ANN001
        self.downloads.append(remote_path)
        raise RuntimeError("stop")

    def execute_skill(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("stop")

    def query(self, *args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("stop")


class TestRemotePosixPath(unittest.TestCase):
    def test_verilog_remote_read_keeps_posix_path(self):
        rec = _Recorder()
        VLOG.Package(rec).read(VLOG.ReadRequest(
            token="t", file_path=REMOTE, file_is_local=False, focus=["source"]))
        self.assertEqual(rec.downloads, [REMOTE])

    def test_veriloga_remote_read_keeps_posix_path(self):
        rec = _Recorder()
        VLOGA.Package(rec).read(VLOGA.ReadRequest(
            token="t", file_path=REMOTE, file_is_local=False, focus=["source"]))
        self.assertEqual(rec.downloads, [REMOTE])


if __name__ == "__main__":
    unittest.main()
