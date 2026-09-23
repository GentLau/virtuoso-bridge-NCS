"""L0 contracts for ``pyapi.packages.veriloga`` (validators + DPL parsing + read guards)."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import veriloga as V


class FakeMiddle:
    def __init__(self, *results: VirtuosoResult) -> None:
        self.calls: list[tuple[str, str]] = []
        self.queue = list(results)

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append((token, skill_code))
        return self.queue.pop(0) if self.queue else VirtuosoResult(
            status=ExecutionStatus.SUCCESS, output='("ok")')


class TestValidators(unittest.TestCase):
    def test_require_text_rejects_blank(self):
        self.assertEqual(V._require_text("mod", "n"), "mod")
        # 与 schematic/symbol 不同：veriloga 用 strip() 判空，空白串也拒绝。
        for bad in ("", "   ", None, 3):
            with self.assertRaises(ValueError) as ctx:
                V._require_text(bad, "library")
            self.assertIn("library", str(ctx.exception))

    def test_require_timeout(self):
        V._require_timeout(None)
        V._require_timeout(1)
        for bad in (0, -2, "1"):
            with self.assertRaises(ValueError):
                V._require_timeout(bad)

    def test_require_bool(self):
        self.assertFalse(V._require_bool(False, "b"))
        self.assertTrue(V._require_bool(True, "b"))
        for bad in (0, 1, "true", None):
            with self.assertRaises(ValueError) as ctx:
                V._require_bool(bad, "b")
            self.assertIn("b", str(ctx.exception))

    def test_safe_name(self):
        self.assertEqual(V._safe_name("a/b c"), "a_b_c")
        self.assertEqual(V._safe_name(""), "cell")
        self.assertEqual(V._safe_name("///", "fb"), "fb")


class TestDplHelpers(unittest.TestCase):
    #: DPL 是**扁平 alist**（可带 nil 头，键值成对）；`_parse_pin_list` 在顶层
    #: 搜索字面量 "ports"，所以样本必须是扁平形态而不是嵌套的子表。
    ENTRY_A = [None, "name", "A", "direction", "input", "width", "1"]
    ENTRY_Y = [None, "name", "Y", "direction", "output", "width", "8"]
    PARSED = [
        None, "status", True,
        "moduleName", "inv_va",
        "ports", [ENTRY_A, ENTRY_Y, "junk"],
        "pinList", [ENTRY_A],
        "pinOrder", ["A", "Y"],
        "paramList", [["name", "gain", "type", "real", "default", "1.0"]],
    ]
    #: 同一份内容的 SKILL 文本形态（给 _parse_pin_list 用）
    DPL_TEXT = (
        '(nil "status" t "moduleName" "inv_va" '
        '"ports" ((nil "name" "A" "direction" "input" "width" "1")'
        ' (nil "name" "Y" "direction" "output" "width" "8")) '
        '"pinOrder" ("A" "Y"))'
    )

    def test_dpl_pairs(self):
        self.assertEqual(V._dpl_pairs(self.ENTRY_A, ("name", "direction", "width")),
                         {"name": "A", "direction": "input", "width": "1"})
        self.assertEqual(V._dpl_pairs([], ("name",)), {})
        self.assertEqual(V._dpl_pairs(["name"], ("name",)), {})   # 末尾键没有值

    def test_dpl_value_status_module(self):
        self.assertEqual(V._dpl_value(self.PARSED, "moduleName"), "inv_va")
        self.assertIsNone(V._dpl_value(self.PARSED, "missing"))
        self.assertTrue(V._dpl_status(self.PARSED))
        self.assertFalse(V._dpl_status(["status", False]))
        self.assertFalse(V._dpl_status(["nothing"]))
        self.assertEqual(V._dpl_module(self.PARSED), "inv_va")
        self.assertEqual(V._dpl_module(["nothing"]), "")

    def test_parse_pin_list(self):
        pins = V._parse_pin_list(self.DPL_TEXT)
        self.assertEqual([p["name"] for p in pins], ["A", "Y"])
        self.assertEqual(pins[0]["direction"], "input")
        self.assertEqual(pins[1]["width"], "8")
        self.assertEqual(V._parse_pin_list("nil"), [])
        self.assertEqual(V._parse_pin_list('("no-ports-here")'), [])

    def test_dpl_fields(self):
        pins, order, params = V._dpl_fields(self.PARSED)
        self.assertEqual([p["name"] for p in pins], ["A"])
        self.assertEqual(order, ["A", "Y"])
        self.assertEqual(params, [{"name": "gain", "type": "real", "default": "1.0"}])
        empty = V._dpl_fields(["nothing"])
        self.assertEqual(empty, ([], [], []))


class TestReadFlow(unittest.TestCase):
    def _pkg(self, *results):
        return V.Package(FakeMiddle(*results))

    def test_requires_exactly_one_target(self):
        """只给 library+cell 时不抛（正确分支）；下面两条 xfail 钉住死守卫。"""
        pkg = self._pkg()
        result = pkg.read(V.ReadRequest(token="t", library="L", cell="C"))
        self.assertIsInstance(result.ok, bool)

    def test_neither_target_should_raise(self):
        """缺陷：`cell_target = request.library and request.cell`（str/None）与
        `file_target = bool(...)`（bool）永远不相等 → 这条守卫是死代码
        （verilog.py:203 同名守卫写了 `bool(...)`）。修复后本用例转绿。"""
        with self.assertRaises(ValueError):
            self._pkg().read(V.ReadRequest(token="t"))

    def test_both_targets_should_raise(self):
        with self.assertRaises(ValueError):
            self._pkg().read(V.ReadRequest(
                token="t", library="L", cell="C", file_path="/tmp/x.va"))

    def test_rejects_unknown_focus(self):
        pkg = self._pkg()
        with self.assertRaises(ValueError) as ctx:
            pkg.read(V.ReadRequest(token="t", library="L", cell="C", focus=[]))
        self.assertIn("focus", str(ctx.exception))
        with self.assertRaises(ValueError):
            pkg.read(V.ReadRequest(token="t", library="L", cell="C", focus=["ports", "zzz"]))

    def test_local_file_read_builds_source_block(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "m.va"
            path.write_text("module m(a); endmodule\n", encoding="utf-8")
            result = self._pkg().read(V.ReadRequest(
                token="t", file_path=str(path), file_is_local=True))
        self.assertTrue(result.ok, result.error)
        self.assertIn("module m", result.value["source"]["text"])
        self.assertEqual(result.value["source"]["size"], 23)
        self.assertEqual(result.value["ports"], [])
        self.assertEqual(result.value["diagnostics"], {})

    def test_local_file_missing_is_reported(self):
        result = self._pkg().read(V.ReadRequest(
            token="t", file_path="no-such-file.va", file_is_local=True))
        self.assertFalse(result.ok)
        self.assertIn("file not found", result.error)

    def test_focus_limits_returned_sections(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "m.va"
            path.write_text("module m; endmodule\n", encoding="utf-8")
            result = self._pkg().read(V.ReadRequest(
                token="t", file_path=str(path), file_is_local=True, focus=["ports"]))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(list(result.value.keys()), ["ports"])

    def test_write_rejects_empty_commands(self):
        with self.assertRaises(ValueError):
            self._pkg().write(V.WriteRequest(token="t", library="L", cell="C", commands=[]))

    def test_check_and_save_validates_arguments(self):
        pkg = self._pkg()
        with self.assertRaises(ValueError):
            pkg.check_and_save(V.CheckSaveRequest(token="", library="L", cell="C"))
        with self.assertRaises(ValueError):
            pkg.check_and_save(V.CheckSaveRequest(token="t", library="L", cell="C", timeout=0))


class VaMiddle:
    """veriloga.write / check_and_save 的假 middle。

    与 verilog 同形的部分（视图目录探测 / 锁检查 / 远端读写 / 刷新）复用同一套约定；
    额外支持 AHDL 上下文探测、VerAParseModule 的 DPL 返回与 ahdlUpdateViewInfo。
    """

    # 注意：`_parse_pin_list` 读 "ports"，而 `_dpl_fields` 读 "pinList"——真机 DPL 两者都在
    DPL_OK = ('("status" t "moduleName" "m_va" '
              '"ports" (("name" "A" "direction" "input" "width" "1")) '
              '"pinList" (("name" "A" "direction" "input" "width" "1")) '
              '"pinOrder" ("A") '
              '"paramList" (("name" "g" "type" "real" "default" "1")))')
    DPL_FAIL = '("status" nil "moduleName" "m_va")'

    def __init__(self, *, context_loaded: bool = True, lock: bool = False,
                 current_source: str = "module old; endmodule\n",
                 dpl: str | None = None, parse_ok: bool = True,
                 refresh_output: str = "t", err_log: str = "") -> None:
        self.context_loaded = context_loaded
        self.lock = lock
        self.current_source = current_source
        self.dpl = dpl if dpl is not None else self.DPL_OK
        self.parse_ok = parse_ok
        self.refresh_output = refresh_output
        self.err_log = err_log
        self.skills: list[str] = []
        self.commands: list[str] = []
        self.uploads: dict[str, str] = {}

    def query(self, *, token, role=None, name=None):
        class _Status:
            value = "success"

        class _Role:
            root = "/role/daemon"

        class _Facts:
            status = _Status()
            roles = {"daemon": _Role()}

        return _Facts()

    def execute_skill(self, code, timeout=None, *, token):
        from pyapi.models import ExecutionStatus, VirtuosoResult
        self.skills.append(code)
        if "getd('VerAParseModule)" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS,
                                  output="t" if self.context_loaded else "nil")
        if "loadContext(" in code:
            self.context_loaded = True
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")
        if "ddGetObjReadPath(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"/home/u/LIB"')
        if "VerAParseModule(" in code:
            if not self.parse_ok:
                return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=["parse boom"])
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.dpl)
        if "ahdlUpdateViewInfo(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.refresh_output)
        if "ddDeleteObj" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")
        if "ddUpdateLibList" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        from pyapi.models import CommandResult
        self.commands.append(cmd)
        if "*.cdslck" in cmd:
            return CommandResult(0, "LOCK\n" if self.lock else "OK\n", "")
        return CommandResult(0, "", "")

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        from pathlib import Path as _Path
        from pyapi.models import CommandResult
        self.uploads[str(remote_path)] = _Path(local_path).read_text(encoding="utf-8")
        return CommandResult(0, str(remote_path), "")

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        from pyapi.models import CommandResult
        if str(remote_path).endswith(".log") or "veriloga_err" in str(remote_path):
            if not self.err_log:
                return CommandResult(1, "", "missing err log", "path")
            target = Path(local_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(self.err_log, encoding="utf-8")
            return CommandResult(0, str(target), "")
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.current_source, encoding="utf-8")
        return CommandResult(0, str(target), "")


class TestVerilogaWriteOrchestration(unittest.TestCase):
    def _write(self, middle, tmp_root: str, commands):
        from unittest import mock
        with mock.patch.object(V, "artifact_dir", lambda: Path(tmp_root) / "artifact"):
            return V.Package(middle).write(V.WriteRequest(
                token="t", library="LIB", cell="CELL", commands=commands))

    def test_validation_and_lock(self):
        with self.assertRaises(ValueError):
            V.Package(VaMiddle()).write(V.WriteRequest(
                token="t", library="LIB", cell="CELL", commands=[]))
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            bad = self._write(VaMiddle(), tmp, [{"op": "explode"}])
            self.assertFalse(bad.ok)
            self.assertIn("must have a valid op", bad.error)

            locked = self._write(VaMiddle(lock=True), tmp, [{"op": "delete_view"}])
            self.assertFalse(locked.ok)
            self.assertIn("locked by an open editor", locked.error)

    def test_ensure_view_and_refresh(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = VaMiddle()
            result = self._write(middle, tmp, [{"op": "ensure_view"}])
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value, {"applied": 1})
        self.assertEqual([step["name"] for step in result.steps],
                         ["ensure_view", "ddUpdateLibList"])
        self.assertTrue(any(p.endswith("master.tag") for p in middle.uploads))

    def test_set_source_and_patch(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = VaMiddle()
            ok = self._write(middle, tmp, [{"op": "set_source", "text": "module new;\n"}])
            self.assertTrue(ok.ok, ok.error)
            self.assertEqual(list(middle.uploads.values()), ["module new;\n"])

            patched = VaMiddle(current_source="a\nb\n")
            out = self._write(patched, tmp, [{
                "op": "patch_source",
                "edits": [{"old_text": "b", "new_text": "B"}]}])
            self.assertTrue(out.ok, out.error)
            self.assertEqual(list(patched.uploads.values())[0], "a\nB\n")


class TestVerilogaCheckAndSave(unittest.TestCase):
    def _check(self, middle, tmp_root: str | None = None, **fields):
        fields.setdefault("token", "t")
        fields.setdefault("library", "LIB")
        fields.setdefault("cell", "CELL")
        if tmp_root is None:
            return V.Package(middle).check_and_save(V.CheckSaveRequest(**fields))
        from unittest import mock
        with mock.patch.object(V, "artifact_dir", lambda: Path(tmp_root) / "artifact"):
            return V.Package(middle).check_and_save(V.CheckSaveRequest(**fields))

    def _check_in_tmp(self, middle, **fields):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            return self._check(middle, tmp_root=tmp, **fields)

    def test_happy_path_returns_ports_and_params(self):
        result = self._check_in_tmp(VaMiddle())
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["module_name"], "m_va")
        self.assertEqual(value["ports"], [{"name": "A", "direction": "input", "width": "1"}])
        self.assertEqual(value["pin_order"], ["A"])
        self.assertEqual(value["param_list"],
                         [{"name": "g", "type": "real", "default": "1"}])
        self.assertTrue(value["err_log"].endswith("LIB__CELL.log"))
        self.assertEqual([step["name"] for step in result.steps],
                         ["context", "VerAParseModule", "ahdlUpdateViewInfo"])

    def test_context_is_loaded_when_missing(self):
        middle = VaMiddle(context_loaded=False)
        result = self._check_in_tmp(middle)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(any("loadContext(" in code for code in middle.skills))

    def test_parse_failure_paths(self):
        skill_failed = self._check_in_tmp(VaMiddle(parse_ok=False))
        self.assertFalse(skill_failed.ok)
        self.assertIn("parse boom", skill_failed.error)

        status_nil = self._check_in_tmp(VaMiddle(dpl=VaMiddle.DPL_FAIL))
        self.assertFalse(status_nil.ok)
        # 没有 err log 时给出可归因的兜底文案（不是空消息）
        self.assertIn("no err log available", status_nil.error)
        self.assertEqual([s["name"] for s in status_nil.steps],
                         ["context", "VerAParseModule", "parse"])

    def test_parse_failure_surfaces_err_log_lines(self):
        middle = VaMiddle(dpl=VaMiddle.DPL_FAIL,
                          err_log="VACOMP-1234: bad port\nother line\n")
        result = self._check_in_tmp(middle)
        self.assertFalse(result.ok)
        self.assertIn("VACOMP-1234", result.error)
        self.assertEqual(result.data if hasattr(result, "data") else result.value["errors"],
                         ["VACOMP-1234: bad port"])

    def test_refresh_failure_is_reported(self):
        result = self._check_in_tmp(VaMiddle(refresh_output="nope"))
        self.assertFalse(result.ok)
        self.assertIn("ahdlUpdateViewInfo failed", result.error)


if __name__ == "__main__":
    unittest.main()
