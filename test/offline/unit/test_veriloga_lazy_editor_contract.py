# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 22:14
# 依赖: 无
# =======================================================================
"""veriloga「惰性编辑器」契约的**生成式缺席断言**（spec 11-veriloga.md:97/136/145）。

为什么单独一份：矩阵里 spec 条款 `11-veriloga.md:97/136`（**不用** `ahdlCheckModule` /
`ahdlSaveFile` / `ahdlEdit`）此前只有"读回产物"类证据，没有对**生成的 SKILL 文本**做缺席断言，
本轮把它补成可机器复核的契约。

六步流程（test/docs/写TB规范.md §1）——离线契约用例：
① 环境检查**不适用**（纯假 middle，不连真机，注释说明即可）；②③ 前置构建/校验**不适用**；
④⑤ = Arrange→Act→Assert（断言在**生成的 SKILL 文本**上，不是只断言 ok/rc）；⑥ 无现场可留。
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from pyapi.models import CommandResult, ExecutionStatus, VirtuosoResult  # noqa: E402
from pyapi.packages import veriloga as V  # noqa: E402


#: spec 11-veriloga.md:97 明确禁止的编辑器 GUI 包装函数（错误或缺 symbol 会弹模态阻塞 CIW）。
FORBIDDEN_CALLS = ("ahdlCheckModule", "ahdlSaveFile", "ahdlEdit")

DPL_OK = (
    '("status" t "moduleName" "m_va" '
    '"ports" (("name" "A" "direction" "input" "width" "1")) '
    '"pinList" (("name" "A" "direction" "input" "width" "1")) '
    '"pinOrder" ("A") '
    '"paramList" (("name" "g" "type" "real" "default" "1")))'
)


class RecordingMiddle:
    """最小假 middle：只回答 veriloga 包需要的 SKILL 探针，并记录全部调用文本。"""

    def __init__(self, *, context_loaded: bool = True) -> None:
        self.context_loaded = context_loaded
        self.skills: list[str] = []
        self.commands: list[str] = []
        self.uploads: dict[str, str] = {}

    def execute_skill(self, code, timeout=None, *, token):
        self.skills.append(code)
        if "getd('VerAParseModule)" in code:
            return VirtuosoResult(
                status=ExecutionStatus.SUCCESS,
                output="t" if self.context_loaded else "nil",
            )
        if "loadContext(" in code:
            self.context_loaded = True
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")
        if "ddGetObjReadPath(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"/home/u/LIB"')
        if "VerAParseModule(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=DPL_OK)
        if "ahdlUpdateViewInfo(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")
        if "ddUpdateLibList" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")

    def query(self, *, token, role=None, name=None):
        """veriloga 包用 daemon role 的 root 拼 err_log 路径（spec:55 诊断落盘位置）。"""
        class _Status:
            value = "success"

        class _Role:
            root = "/home/u/.virtuoso-bridge/u"

        class _Facts:
            status = _Status()
            errors: list[str] = []
            roles = {"daemon": _Role()}

        return _Facts()

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        self.commands.append(cmd)
        if "*.cdslck" in cmd:
            return CommandResult(returncode=0, stdout="OK\n", stderr="")
        return CommandResult(returncode=0, stdout="", stderr="")

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        self.uploads[str(remote_path)] = Path(local_path).read_text(encoding="utf-8")
        return CommandResult(returncode=0, stdout=str(remote_path), stderr="")

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("module old; endmodule\n", encoding="utf-8")
        return CommandResult(returncode=0, stdout=str(target), stderr="")


class TestNoEditorGuiCalls(unittest.TestCase):
    def _run(self, tmp_root: str, middle: RecordingMiddle, callable_):
        with mock.patch.object(V, "artifact_dir", lambda: Path(tmp_root) / "artifact"):
            return callable_(V.Package(middle))

    def _check_save(self, tmp_root: str, middle: RecordingMiddle):
        return self._run(tmp_root, middle, lambda pkg: pkg.check_and_save(V.CheckSaveRequest(
            token="t", library="LIB", cell="CELL", view="veriloga", view_type="veriloga",
        )))

    def test_check_and_save_sequence_and_absence(self):
        """① 检查用 `VerAParseModule` → ② 保存/刷新用 `ahdlUpdateViewInfo`，且全程无禁止函数。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            middle = RecordingMiddle()
            result = self._check_save(tmp, middle)
            self.assertTrue(result.ok, f"check_and_save 应成功：{result.error}")

            parse_at = next(
                i for i, code in enumerate(middle.skills) if "VerAParseModule(" in code
            )
            refresh_at = next(
                i for i, code in enumerate(middle.skills) if "ahdlUpdateViewInfo(" in code
            )
            self.assertLess(parse_at, refresh_at, "必须先检查后保存/刷新")

            joined = "\n".join(middle.skills)
            for forbidden in FORBIDDEN_CALLS:
                self.assertNotIn(forbidden, joined, f"禁止调用 {forbidden}（spec:97/136）")

    def test_cold_context_uses_full_path_load_context(self):
        """spec:145#3：AHDL 上下文冷加载必须走 `loadContext` 全路径（getInstallPath + /etc/context/64bit）。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            middle = RecordingMiddle(context_loaded=False)
            result = self._check_save(tmp, middle)
            self.assertTrue(result.ok, f"冷加载后应成功：{result.error}")
            load_code = next(code for code in middle.skills if "loadContext(" in code)
            self.assertIn("getInstallPath()", load_code)
            self.assertIn("/etc/context/64bit/", load_code)

    def test_write_ops_do_not_touch_view_info(self):
        """spec:81#3：`write` 只落文件 —— 不调 `ahdlUpdateViewInfo`，也不跑解析器。"""
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            middle = RecordingMiddle()
            result = self._run(tmp, middle, lambda pkg: pkg.write(V.WriteRequest(
                token="t", library="LIB", cell="CELL", view="veriloga",
                view_type="veriloga",
                commands=[{"op": "ensure_view"},
                          {"op": "set_source", "text": "module m_va; endmodule\n"}],
            )))
            self.assertTrue(result.ok, f"write 应成功：{result.error}")
            self.assertIn("/home/u/LIB/CELL/veriloga/veriloga.va", middle.uploads)
            self.assertIn("/home/u/LIB/CELL/veriloga/master.tag", middle.uploads)

            joined = "\n".join(middle.skills)
            self.assertNotIn("ahdlUpdateViewInfo", joined, "write 不得刷新 CDF")
            self.assertNotIn("VerAParseModule", joined, "write 不得跑解析")
            for forbidden in FORBIDDEN_CALLS:
                self.assertNotIn(forbidden, joined, f"禁止调用 {forbidden}")


if __name__ == "__main__":
    unittest.main()
