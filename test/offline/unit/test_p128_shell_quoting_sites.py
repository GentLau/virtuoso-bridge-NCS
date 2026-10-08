# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-10-08 15:06
# 依赖: 无
# =======================================================================
"""P-128 回归（离线）：用户可控字符串进入 shell 命令时不得裸拼（3 个可离线站点）。

站点：
  1. `gui.send_key`：window_id 直接进双引号 + 裸插值（`$(...)` 会被求值）；
  2. `verilog.import_verilog`：`re.escape(cell)` 放进单引号 grep 模式，
     `re.escape` 不处理 `'`，单引号逃出引用；
  3. `maestro._find_psf_dir`：`find {history_dir} ...` 完全未引用。

判据（修复无关）：命中站点的命令要么在调用点结构化拒绝（ValueError），
要么让特殊字符在命令中保持字面量（POSIX 解析后仍是同一个 token）。
2026-10-08 已修：gui 走 window_id 白名单 + shlex.quote；verilog 整段 pattern
shlex.quote；maestro find 路径 shlex.quote。schematic 站点（screenshot 的
mkdir/rm 文件名）随修复补验（`shlex.quote` 直引，见 schematic.py）。

第 1 步（环境检查）：离线用例，fake middle 记录命令；不连真机。
"""
from __future__ import annotations

import shlex
import sys
import unittest

from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult
from pyapi.packages import gui as gui_mod
from pyapi.packages import maestro as maestro_mod
from pyapi.packages import verilog as verilog_mod


class _RecordingMiddle:
    def __init__(self) -> None:
        self.commands: list[str] = []
        self._ddgetobj_calls = 0

    def run_command(self, cmd, timeout=None, token=None):
        self.commands.append(cmd)
        return CommandResult(returncode=0, stdout="", stderr="")

    def run_gui_command(self, cmd, timeout=None, token=None):
        self.commands.append(cmd)
        return CommandResult(returncode=0, stdout="", stderr="")

    def upload_file(self, local, remote, timeout=None, token=None, recursive=False):
        return CommandResult(returncode=0, stdout="", stderr="")

    def execute_skill(self, expr, timeout=None, token=None, **kwargs):
        if "getWorkingDir" in expr:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"work"')
        if "ddGetObj" in expr:
            self._ddgetobj_calls += 1
            return VirtuosoResult(
                status=ExecutionStatus.SUCCESS,
                output="t" if self._ddgetobj_calls == 1 else "nil",
            )
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="nil")


class TestShellQuotingSites(unittest.TestCase):
    def setUp(self):
        self.middle = _RecordingMiddle()
        patcher = mock.patch.object(
            gui_mod.Package, "_gui_display", return_value=(":0", None),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_gui_send_key_quotes_window_id(self):
        window_id = "$(echo PWNED)"
        pkg = gui_mod.Package(self.middle)
        request = gui_mod.SendKeyRequest(
            token="vb-offline", window_id=window_id, key="enter",
        )
        try:
            pkg.send_key(request)
        except ValueError:
            return  # 结构化拒绝同样合格
        if not self.middle.commands:
            return  # 未发命令 = 前置校验已拦下
        hits = [cmd for cmd in self.middle.commands if window_id in cmd]
        self.assertTrue(hits, f"window_id 未出现在任何命令中: {self.middle.commands!r}")
        for cmd in hits:  # send 与 xwininfo 校验两条命令都要过关
            self.assertIn(
                shlex.quote(window_id),
                cmd,
                f"window_id 未按字面量引用: {cmd[:160]!r}",
            )

    def test_verilog_import_module_probe_quotes_cell(self):
        cell = "bad'name"
        pkg = verilog_mod.Package(self.middle)
        request = verilog_mod.ImportRequest(
            token="vb-offline", library="libx", cell=cell,
            file_path="design.v", file_is_local=True,
        )
        try:
            pkg.import_verilog(request)
        except ValueError:
            return  # 结构化拒绝同样合格
        probes = [c for c in self.middle.commands if "grep -cE" in c]
        self.assertTrue(probes, f"未捕获到模块名探测命令: {self.middle.commands!r}")
        cmd = probes[0]
        try:
            tokens = shlex.split(cmd)
        except ValueError as exc:
            self.fail(f"cell 名单引号逃出引用、无法按 POSIX 解析: {exc}: {cmd!r}")
        self.assertTrue(
            any(cell in token for token in tokens),
            f"cell 名未以字面量出现在解析结果中: {tokens!r}",
        )

    def test_maestro_find_psf_dir_quotes_history_dir(self):
        history_dir = "/tmp/vb p128; touch PWNED"
        pkg = maestro_mod.Package(self.middle)
        pkg._find_psf_dir(history_dir, None, None, "vb-offline", 10)
        self.assertTrue(self.middle.commands, "未捕获到 find 命令")
        cmd = self.middle.commands[0]
        try:
            tokens = shlex.split(cmd)
        except ValueError as exc:
            self.fail(f"find 命令无法按 POSIX 解析: {exc}: {cmd!r}")
        self.assertIn(
            history_dir,
            tokens,
            f"history_dir 未以字面量作为单个 token: {tokens!r}",
        )
