"""契约：daemon 模块必须能在"stdin 不是真实文件"的环境里被**导入**。

为什么要有这条（2026-09-23 第三轮实测）：
pytest 会把 `sys.stdin` 换成伪文件（`DontReadFromInput`），它的 `fileno()` 抛
`io.UnsupportedOperation: redirected stdin is pseudofile, has no fileno()`。
而两个 daemon 都在**模块级**做 `sys.stdin.fileno()` + `fcntl(F_SETFL, O_NONBLOCK)`（仅 POSIX）：

    src/bridge/resources/ramic_bridge_daemon_3.py:87-89
    src/bridge/resources/ramic_bridge_daemon_27.py:97-99

后果：Linux 上 `pytest`（CI 口径）在**采集期**就报 6 个 collection error，整批离线用例跑不起来；
Windows 上因为 `_fcntl is None` 走不到这段，所以"Windows 3.9 全绿"掩盖了这个问题。

真实运行时 stdin 是 `ipcBeginProcess` 管道（有 fileno），所以这不是运行时缺陷，
而是**可导入性契约**：库模块在导入期不得依赖"stdin 是真文件"。
"""
from __future__ import annotations

import importlib.util
import io
import pathlib
import sys
import unittest
from unittest import mock

SRC = pathlib.Path(__file__).resolve().parents[3] / "src"
DAEMONS = ("ramic_bridge_daemon_3.py", "ramic_bridge_daemon_27.py")


class _PseudoStdin(io.StringIO):
    """模拟 pytest 捕获用的伪 stdin：没有可用的 fileno()。"""

    def fileno(self) -> int:  # noqa: D102
        raise io.UnsupportedOperation(
            "redirected stdin is pseudofile, has no fileno()"
        )


@unittest.skipIf(sys.platform == "win32",
                 "fcntl 分支仅在 POSIX 上执行（Windows 下 _fcntl is None，测不到该路径）")
class TestDaemonImportContract(unittest.TestCase):
    def test_import_survives_pseudofile_stdin(self) -> None:
        for name in DAEMONS:
            path = SRC / "bridge" / "resources" / name
            self.assertTrue(path.exists(), f"daemon 源文件缺失: {path}")
            spec = importlib.util.spec_from_file_location(f"fresh_{path.stem}", path)
            module = importlib.util.module_from_spec(spec)
            with mock.patch.object(sys, "stdin", _PseudoStdin()):
                try:
                    spec.loader.exec_module(module)  # type: ignore[union-attr]
                except Exception as exc:  # noqa: BLE001
                    self.fail(
                        f"{name}: 在伪 stdin 下导入失败 -> "
                        f"{type(exc).__name__}: {exc}（模块级不得调用 sys.stdin.fileno()）"
                    )


if __name__ == "__main__":
    unittest.main()
