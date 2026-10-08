# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:06
# 依赖: 无
# =======================================================================
"""P-122 红钉（离线）：本地命令会话 shell 中途退出必须报「结果未知」。

合同（`pyapi/models.py::CommandResult` 文档串 + 四层整体架构 §4.4）：只有
`kind == "command"` 才代表 returncode 是真实命令退出码；本地 shell 死亡时
既未收到 rc marker 也未收到结束标记，必须给出 `kind != "command"`。

回归判据（P-122 已修）：`src/transport/middle.py::_LocalCommandSession.execute`
的 eof 分支必须给出 `kind=unknown-effect`、returncode=255、
stderr 带 `VB-UNKNOWN-EFFECT:` 前缀，不得把 proc_rc 当真实退出码。

第 1 步（环境检查）：离线用例，本地 shell 由被测代码自己拉起，无需真机。
第 3 步（构建前置）：启动会话后让命令真正阻塞住，再 kill 掉 shell 进程。
"""
from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import unittest

from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from transport.middle import _LocalCommandSession


@unittest.skipUnless(
    os.name == "nt",
    "本地 shell 会话分平台；Windows 客户端为主靶机（Linux 等价用例待补）",
)
class TestLocalShellEofIsUnknownEffect(unittest.TestCase):
    def test_shell_death_mid_command_reports_unknown_effect(self):
        with TemporaryDirectory() as tmp:
            session = _LocalCommandSession(err_dir=Path(tmp))
            holder: dict = {}

            def run() -> None:
                # 必须是"阻塞且不读 stdin"的命令：pause 会立刻吃掉排队
                # 在 stdin 里的 echo/rc 行，命令提前正常返回，测不到 shell
                # 死亡路径（2026-10-08 实测）。ping 只阻塞、不碰 stdin。
                holder["result"] = session.execute(
                    "ping -n 20 127.0.0.1 >nul", timeout=60)

            try:
                thread = threading.Thread(target=run, daemon=True)
                thread.start()
                time.sleep(1.0)  # 让 ping 真正阻塞住
                self.assertIsNotNone(session._proc, "本地 shell 未启动")
                # 杀整棵树：只杀 cmd.exe 时外部子进程仍攥着 stdout 管道，
                # 读取线程等不到 EOF（实测 execute 20s 不返回）。
                killed = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(session._proc.pid)],
                    capture_output=True, text=True,
                )
                self.assertEqual(killed.returncode, 0,
                                 f"taskkill 失败: {killed.stderr.strip()}")
                thread.join(timeout=20)
                self.assertFalse(thread.is_alive(), "shell 死亡后 execute 未返回")
                result = holder["result"]
                self.assertEqual(
                    result.kind, "unknown-effect",
                    f"shell 死亡应报结果未知（rc={result.returncode}）："
                    "不能把 proc_rc 当真实退出码",
                )
                self.assertEqual(result.returncode, 255)
                self.assertIn("VB-UNKNOWN-EFFECT:", result.stderr)
            finally:
                session.close()
