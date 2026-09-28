"""spec《四层整体架构与接口》§4.5：真实命令的 124/255 必须保持 ``kind=command``。

原文：**"真实命令返回码即使等于 124/255 也保持 `kind=command`，桥保留码只在
`kind != command` 时解释。"**

为什么单列：既有离线用例（``test_middle_contracts`` / ``fault_injection_tb``）
只钉住了"桥自己产生 124/255"（timeout / transport），没有反过来钉住
"**真实命令**恰好返回 124/255 时不得被改判"。这条一旦回归，调用方会把一条
正常退出码 255 的命令当成传输失败去重试，或把 124 当成超时。

本文件**不打桩**：直接跑真实 subprocess（``BusinessServer._local_command``）
与真实常驻本地 shell 路径（local 模式的 ``run_command``），再给出"桥超时"的
对照用例，证明两者可区分。
"""
from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.paths import init_work_dir, registry_path
from common.registry import UserEntry, load_registry
from pyapi.models import CommandResult
from transport.middle import BusinessServer

RESERVED = (124, 255)


def _exit_cmd(code: int) -> str:
    """一条**真实**命令：子进程退出码 = code，且不会杀掉常驻 shell 本身。"""
    if os.name == "nt":
        return f"cmd /c exit {code}"
    return f"sh -c 'exit {code}'"


def _sleep_cmd() -> str:
    return "ping -n 10 127.0.0.1 > nul" if os.name == "nt" else "sleep 5"


def _local_entry(work: Path) -> UserEntry:
    entry = UserEntry(token="tok-rc", mode="local")
    for name in ("gui", "daemon", "command", "file", "spectre"):
        getattr(entry.roles, name).root = str(work / name)
    entry.roles.daemon.daemon_port = 65081
    entry.roles.daemon.local_port = 65081
    entry.roles.daemon.python = sys.executable
    return entry


class TestReservedCodesStayCommand(unittest.TestCase):
    def setUp(self):
        self.wd = Path(tempfile.mkdtemp(prefix="vb-"))
        registry = load_registry(registry_path())
        registry.register("alice", _local_entry(self.wd))
        self.server = BusinessServer()
        self.addCleanup(self.server.close)

    def test_one_shot_local_command_rc_124_255_stay_command(self):
        """真实 subprocess：rc=124/255 属"命令自己的退出码"，kind 必须是 command。"""
        for rc in RESERVED:
            with self.subTest(returncode=rc):
                r = BusinessServer._local_command(_exit_cmd(rc), 30, cwd=str(self.wd))
                self.assertIsInstance(r, CommandResult)
                self.assertEqual(r.kind, "command", r)
                self.assertEqual(r.returncode, rc, r)

    def test_serial_local_mode_session_rc_stays_command(self):
        """走 local 模式的完整路径（常驻 shell + 串行位），仍然必须是 command。"""
        for rc in RESERVED:
            with self.subTest(returncode=rc):
                r = self.server.run_command(_exit_cmd(rc), 30, token="tok-rc")
                self.assertEqual(r.kind, "command", r)
                self.assertEqual(r.returncode, rc, r)

    def test_parallel_local_mode_rc_stays_command(self):
        for rc in RESERVED:
            with self.subTest(returncode=rc):
                r = self.server.run_command(_exit_cmd(rc), 30, token="tok-rc", parallel=True)
                self.assertEqual(r.kind, "command", r)
                self.assertEqual(r.returncode, rc, r)

    def test_bridge_timeout_is_still_kind_timeout(self):
        """对照：桥自己的超时用 124 + kind=timeout —— 与"命令 rc=124"可区分。"""
        r = BusinessServer._local_command(_sleep_cmd(), 0.5, cwd=str(self.wd))
        self.assertEqual(r.kind, "timeout", r)
        self.assertEqual(r.returncode, 124, r)

    def test_zero_and_max_exit_codes_are_untouched(self):
        """边界：0 与 255 都要原样返回（255 最容易被实现顺手改判成 transport）。"""
        for rc in (0, 1, 255):
            with self.subTest(returncode=rc):
                r = BusinessServer._local_command(_exit_cmd(rc), 30, cwd=str(self.wd))
                self.assertEqual((r.kind, r.returncode), ("command", rc), r)


if __name__ == "__main__":
    unittest.main()
