"""契约：`layout.gds` 的"remote→remote 发布"必须**自建目标目录**。

2026-09-23 第三轮实测（A/B 对照，见 `test/artifacts/evidence/round3-gds-publish-red.json`）：

* A（目标目录已存在）：`virtuoso.layout.gds --file_is_local=false` → ok，publish_log/publish_gds 全过；
* B（目标目录不存在）：同一个调用 → `publication_error: cp: cannot create regular file
  '.../gds-publish-missing/sub/out.gds.xstream.log': No such file or directory`，
  且在 `publish_log` 就中止（GDS 本身都没发布）。S11 工程链的 gds 阶段就是被这条卡住。

根因：同一个包里三条发布路径行为不一致 ——

* `_publish_remote`（下载到本机）：`local.parent.mkdir(parents=True, exist_ok=True)` ✓
* 截图：`mkdir -p $(dirname <remote_png>)` ✓
* `_publish_remote_copy`（远端→远端，`file_is_local=false` 走这条）：直接 `cp`，**不建目录** ✗

本用例只依赖假 middle，无需真机；修复前 `test_publish_remote_copy_creates_destination_dir` 为红。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from pyapi.models import CommandResult  # noqa: E402
from pyapi.packages import layout as L  # noqa: E402


class RecordingMiddle:
    """只记录 run_command / download_file 的假 middle。"""

    def __init__(self, returncode: int = 0, stderr: str = "") -> None:
        self.commands: list[str] = []
        self.returncode = returncode
        self.stderr = stderr

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        self.commands.append(cmd)
        return CommandResult(self.returncode, "", self.stderr, "command")

    def download_file(self, remote, local, timeout=None, *, token, recursive=False):
        Path(local).parent.mkdir(parents=True, exist_ok=True)
        Path(local).write_text("gds", encoding="utf-8")
        return CommandResult(0, "", "", "command")


def request(**overrides) -> L.GdsRequest:
    values = dict(token="t", action="export", library="LIB", cell="CELL", view="layout")
    values.update(overrides)
    return L.GdsRequest(**values)


class TestRemotePublishContract(unittest.TestCase):
    DEST = "/home/u/publish/sub/out.gds"

    def test_publish_remote_copy_creates_destination_dir(self) -> None:
        middle = RecordingMiddle()
        package = L.Package(middle)
        error = package._publish_remote_copy("/role/xstream/out.gds", self.DEST,
                                             request(file_is_local=False))
        self.assertIsNone(error, error)
        joined = " && ".join(middle.commands)
        self.assertIn("mkdir -p", joined,
                      f"发布前必须先建目标目录（当前命令：{middle.commands}）")
        self.assertIn(f"/home/u/publish/sub", joined,
                      "mkdir 的目标应是 dest 的目录部分")
        self.assertIn("cp ", joined, "仍必须执行拷贝")

    def test_publish_remote_copy_reports_failure(self) -> None:
        middle = RecordingMiddle(returncode=1, stderr="boom")
        error = L.Package(middle)._publish_remote_copy("/r/a.gds", self.DEST,
                                                       request(file_is_local=False))
        self.assertIn("boom", error or "")

    def test_relative_destination_is_rejected(self) -> None:
        error = L.Package(RecordingMiddle())._publish_remote_copy(
            "/r/a.gds", "relative/out.gds", request(file_is_local=False))
        self.assertIn("absolute", error or "")

    def test_download_publish_creates_local_parent(self) -> None:
        """对照：下载路径（file_is_local=true）本来就建父目录 —— 说明包里另外两条路径是漏的。"""
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            target = Path(tmp) / "deep" / "nested" / "out.gds"
            error = L.Package(RecordingMiddle())._publish_remote(
                "/role/xstream/out.gds", target, request())
            self.assertIsNone(error, error)
            self.assertTrue(target.is_file(), "下载路径应自建父目录并落盘")


if __name__ == "__main__":
    unittest.main()
