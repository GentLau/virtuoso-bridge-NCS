"""L0 contracts for ``pyapi.packages.verilog`` (log parsers + request guards)."""
from __future__ import annotations

import unittest
from pathlib import Path

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import verilog as V


class FakeMiddle:
    def __init__(self, *results: VirtuosoResult) -> None:
        self.calls: list[tuple[str, str]] = []
        self.queue = list(results)

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append((token, skill_code))
        return self.queue.pop(0) if self.queue else VirtuosoResult(
            status=ExecutionStatus.SUCCESS, output='"ok"')


def ok(output: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=output)


class TestValidators(unittest.TestCase):
    def test_require_text(self):
        self.assertEqual(V._require_text("x", "n"), "x")
        for bad in ("", None, 3):
            with self.assertRaises(ValueError) as ctx:
                V._require_text(bad, "n")
            self.assertIn("n", str(ctx.exception))

    def test_require_timeout_and_bool(self):
        V._require_timeout(None)
        V._require_timeout(3)
        for bad in (0, -1, "3"):
            with self.assertRaises(ValueError):
                V._require_timeout(bad)
        self.assertTrue(V._require_bool(True, "b"))
        for bad in (1, "yes", None):
            with self.assertRaises(ValueError) as ctx:
                V._require_bool(bad, "b")
            self.assertIn("b", str(ctx.exception))

    def test_safe_name(self):
        self.assertEqual(V._safe_name("a/b c"), "a_b_c")
        self.assertEqual(V._safe_name(""), "cell")
        self.assertEqual(V._safe_name("///", "fallback"), "fallback")


class TestLogParsers(unittest.TestCase):
    LOG = "\n".join([
        "INFO: Reading ahdl lib",
        "Checked-in schematic counter8 -- ok",
        "Checked-in symbol counter8, ok",
        "Checked-in functional view counter8; ok",
        "Checked-in schematic counter8 -- again",        # duplicate must be dropped
        "Checked-in something else ignored",
        "WARNING (VERILOGIN-19): something odd",
        "WARNING (VERILOGIN-127): another odd thing",
        "WARNING (VERILOGIN-999): not tracked",
    ])

    def test_imported_cells_dedupes_and_strips_punctuation(self):
        self.assertEqual(V._imported_cells("nothing here"), [])
        self.assertEqual(V._imported_cells(self.LOG), ["counter8"])

    def test_imported_cells_should_dedupe_cleaned_names(self):
        """红灯：同一 cell 被多个视图 check-in（正常情况）时应只出现一次。"""
        self.assertEqual(V._imported_cells(self.LOG), ["counter8"])

    def test_unverified_log_shape_is_flagged(self):
        """仓库内没有真实 VERILOGIN 日志样本：正则接受 "Checked-in schematic <cell>"，
        但 "Checked-in schematic view <cell>" 这种更常见的写法会解析错（拿到 "view"）。
        已记入 audit 观察项；等真实 import 日志到手后按实际格式定稿。
        """
        self.assertNotEqual(
            V._imported_cells("Checked-in schematic view counter8 -- ok"), ["counter8"])

    def test_import_warnings_filters_and_caps(self):
        warnings = V._import_warnings(self.LOG)
        self.assertEqual(len(warnings), 2)
        self.assertIn("VERILOGIN-19", warnings[0])
        self.assertNotIn("VERILOGIN-999", " ".join(warnings))
        many = "\n".join(f"WARNING (VERILOGIN-19): w{i}" for i in range(30))
        self.assertEqual(len(V._import_warnings(many)), 20)


class TestPackageGuards(unittest.TestCase):
    def _pkg(self, *results):
        return V.Package(FakeMiddle(*results))

    def test_read_requires_exactly_one_source(self):
        pkg = self._pkg()
        with self.assertRaises(ValueError) as ctx:
            pkg.read(V.ReadRequest(token="t"))
        self.assertIn("not both/none", str(ctx.exception))
        with self.assertRaises(ValueError):
            pkg.read(V.ReadRequest(token="t", library="L", cell="C", file_path="/tmp/x.v"))

    def test_read_rejects_bad_focus(self):
        pkg = self._pkg()
        with self.assertRaises(ValueError) as ctx:
            pkg.read(V.ReadRequest(token="t", library="L", cell="C", focus=[]))
        self.assertIn("focus", str(ctx.exception))
        with self.assertRaises(ValueError):
            pkg.read(V.ReadRequest(token="t", library="L", cell="C", focus=["nope"]))

    def test_read_text_mode_reports_missing_file(self):
        pkg = self._pkg()
        result = pkg.read(V.ReadRequest(
            token="t", file_path="definitely-missing-file.v", file_is_local=True))
        self.assertFalse(result.ok)
        self.assertIn("file not found", result.error)

    def test_read_text_mode_reads_local_file(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            path = Path(tmp) / "counter.v"
            path.write_text("module counter; endmodule\n", encoding="utf-8")
            result = self._pkg().read(V.ReadRequest(
                token="t", file_path=str(path), file_is_local=True))
        self.assertTrue(result.ok, result.error)
        self.assertIn("module counter", result.value["source"]["text"])
        self.assertEqual(result.value["source"]["size"], 26)
        self.assertEqual(result.value["views"], [])
        self.assertEqual(result.value["diagnostics"], {})
        self.assertEqual(len(result.value["source"]["sha256"]), 64)

    def test_write_rejects_empty_and_bad_commands(self):
        with self.assertRaises(ValueError):
            self._pkg().write(V.WriteRequest(token="t", library="L", cell="C", commands=[]))
        bad = self._pkg().write(V.WriteRequest(
            token="t", library="L", cell="C", commands=[{"nope": 1}]))
        self.assertFalse(bad.ok)
        self.assertIn("valid op", bad.error)


class WriteMiddle:
    """verilog.write 的假 middle：视图目录探测 / 锁检查 / 读写远端文件 / 刷新。"""

    def __init__(self, *, lock: bool = False, current_source: str = "module old; endmodule\n",
                 delete_returns: str = "t") -> None:
        self.lock = lock
        self.current_source = current_source
        self.delete_returns = delete_returns
        self.uploads: dict[str, str] = {}
        self.commands: list[str] = []

    def execute_skill(self, code, timeout=None, *, token):
        from pyapi.models import ExecutionStatus, VirtuosoResult
        if "ddGetObjReadPath(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"/home/u/LIB"')
        if "ddDeleteObj" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.delete_returns)
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
        from pathlib import Path as _Path
        from pyapi.models import CommandResult
        target = _Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.current_source, encoding="utf-8")
        return CommandResult(0, str(target), "")


class TestVerilogWriteOrchestration(unittest.TestCase):
    def _write(self, middle, tmp_root: str, commands, **fields):
        fields.setdefault("token", "t")
        fields.setdefault("library", "LIB")
        fields.setdefault("cell", "CELL")
        import tempfile
        from pathlib import Path as _Path
        from unittest import mock
        with mock.patch.object(V, "artifact_dir", lambda: _Path(tmp_root) / "artifact"):
            return V.Package(middle).write(V.WriteRequest(commands=commands, **fields))

    def test_invalid_commands_are_rejected_before_any_call(self):
        with self.assertRaises(ValueError):
            V.Package(WriteMiddle()).write(V.WriteRequest(
                token="t", library="LIB", cell="CELL", commands=[]))
        bad = V.Package(WriteMiddle()).write(V.WriteRequest(
            token="t", library="LIB", cell="CELL", commands=[{"op": "explode"}]))
        self.assertFalse(bad.ok)
        self.assertIn("must have a valid op", bad.error)

    def test_locked_view_is_refused(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._write(WriteMiddle(lock=True), tmp,
                                 [{"op": "delete_view"}])
        self.assertFalse(result.ok)
        self.assertIn("locked by an open editor", result.error)

    def test_ensure_view_writes_template_and_refreshes(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = WriteMiddle()
            result = self._write(middle, tmp, [{"op": "ensure_view"}])
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value, {"applied": 1})
        self.assertEqual([step["name"] for step in result.steps],
                         ["ensure_view", "ddUpdateLibList"])
        written = {k.split("/")[-1]: v for k, v in middle.uploads.items()}
        self.assertIn("master.tag", written)
        self.assertEqual(written["master.tag"], V.MASTER_TAG + V.MAIN_FILE + "\n")
        self.assertIn("module CELL;", written[V.MAIN_FILE])

    def test_set_source_writes_text(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = WriteMiddle()
            result = self._write(middle, tmp,
                                 [{"op": "set_source", "text": "module new; endmodule\n"}])
        self.assertTrue(result.ok, result.error)
        self.assertEqual(list(middle.uploads.values()),
                         ["module new; endmodule\n"])

    def test_set_source_sha_guard_blocks_write(self):
        import hashlib
        import tempfile
        payload = "module v1; endmodule\n"
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()

        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            matching = WriteMiddle(current_source=payload)
            ok = self._write(matching, tmp, [{"op": "set_source", "text": "module v2; endmodule\n",
                                              "expected_sha256": digest}])
        self.assertTrue(ok.ok, ok.error)
        self.assertEqual(len(matching.uploads), 1)

        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            mismatch = WriteMiddle(current_source="different\n")
            bad = self._write(mismatch, tmp, [{"op": "set_source", "text": "x",
                                               "expected_sha256": digest}])
        self.assertFalse(bad.ok)
        self.assertIn("sha256 mismatch", bad.error)
        self.assertEqual(mismatch.uploads, {})

    def test_patch_source_old_text_paths(self):
        import tempfile
        source = "line one\nline two\nline two\n"
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = WriteMiddle(current_source=source)
            ok = self._write(middle, tmp, [{
                "op": "patch_source",
                # all 是**命令级**开关（源码：command.get("all")），不是 edit 级
                "edits": [{"old_text": "line two", "new_text": "line TWO"}],
                "all": True,
            }])
        self.assertTrue(ok.ok, ok.error)
        self.assertEqual(list(middle.uploads.values())[0],
                         "line one\nline TWO\nline TWO\n")

        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            ambiguous = WriteMiddle(current_source=source)
            bad = self._write(ambiguous, tmp, [{
                "op": "patch_source",
                "edits": [{"old_text": "line two", "new_text": "x"}],
            }])
        self.assertFalse(bad.ok)
        self.assertIn("matches 2 places, all=false", bad.error)

        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            missing = WriteMiddle(current_source=source)
            gone = self._write(missing, tmp, [{
                "op": "patch_source",
                "edits": [{"old_text": "absent", "new_text": "x"}],
            }])
        self.assertFalse(gone.ok)
        self.assertIn("old_text not found", gone.error)

    def test_patch_source_line_range_edits(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = WriteMiddle(current_source="a\nb\nc\n")
            ok = self._write(middle, tmp, [{
                "op": "patch_source",
                "edits": [{"start_line": 2, "end_line": 2, "new_text": "B"}],
            }])
            self.assertTrue(ok.ok, ok.error)
            self.assertEqual(list(middle.uploads.values())[0], "a\nB\nc\n")

            bad_range = WriteMiddle(current_source="a\nb\nc\n")
            out = self._write(bad_range, tmp, [{
                "op": "patch_source",
                "edits": [{"start_line": 0, "end_line": 9, "new_text": "x"}],
            }])
        self.assertFalse(out.ok)
        self.assertIn("invalid line range", out.error)

    def test_delete_view_requires_true_and_failure_shows_applied_prefix(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            not_true = WriteMiddle(delete_returns="nil")
            bad = self._write(not_true, tmp, [{"op": "delete_view"}])
        self.assertFalse(bad.ok)
        self.assertIn("ddDeleteObj returned", bad.error)
        self.assertIn("commands applied: 0/1", bad.error)

        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            good = WriteMiddle()
            ok = self._write(good, tmp, [{"op": "delete_view"}])
        self.assertTrue(ok.ok, ok.error)
        self.assertEqual(ok.value, {"applied": 1})


class CellModeMiddle(WriteMiddle):
    """verilog.read(cell 模式) 与 import 的假 middle。"""

    VIEWS = '(("verilog" ("verilog" "text.v" nil "CELL.v")))'
    CHECKIN = '(("views" (("verilog" 3 4 5 ((0 0) (1 1)))))'

    def __init__(self, *, lib_exists: str = "t", source: str = "module CELL; endmodule\n",
                 views: str | None = None, diag_log: str | None = None,
                 batch_log: str | None = None, ihdl_rc: int = 0,
                 xmvlog: str = "") -> None:
        super().__init__()
        self.lib_exists = lib_exists
        self.source = source
        self.views = views if views is not None else self.VIEWS
        self.diag_log = diag_log
        self.batch_log = batch_log
        self.ihdl_rc = ihdl_rc
        self.xmvlog = xmvlog

    def execute_skill(self, code, timeout=None, *, token):
        from pyapi.models import ExecutionStatus, VirtuosoResult
        if "ddGetObjReadPath(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"/home/u/LIB"')
        if "ddGetObjFiles(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.views)
        if "getWorkingDir()" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"/home/u/work"')
        if "dbOpenCellViewByType(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.CHECKIN)
        if "if(ddGetObj(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.lib_exists)
        if "ddUpdateLibList" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        from pyapi.models import CommandResult
        remote = str(remote_path)
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if remote.endswith("verilogIn.batch.log"):
            payload = self.batch_log if self.batch_log is not None else self.diag_log
            if payload is None:
                return CommandResult(1, "", "missing", "path")
            target.write_text(payload, encoding="utf-8")
            return CommandResult(0, str(target), "")
        if remote.endswith(".vb_verilog/verilogIn.batch.log"):
            return CommandResult(1, "", "missing", "path")
        if remote.endswith("xmvlog.log"):
            if not self.xmvlog:
                return CommandResult(1, "", "missing", "path")
            target.write_text(self.xmvlog, encoding="utf-8")
            return CommandResult(0, str(target), "")
        if "verilogIn.batch.log" in remote:
            if self.diag_log is None:
                return CommandResult(1, "", "missing", "path")
            target.write_text(self.diag_log, encoding="utf-8")
            return CommandResult(0, str(target), "")
        target.write_text(self.source, encoding="utf-8")
        return CommandResult(0, str(target), "")

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        from pyapi.models import CommandResult
        self.commands.append(cmd)
        if "*.cdslck" in cmd:
            return CommandResult(0, "OK\n", "")
        if "ihdl" in cmd:
            return CommandResult(self.ihdl_rc, "", "" if self.ihdl_rc == 0 else "ihdl boom")
        return CommandResult(0, "", "")


class TestVerilogReadCellMode(unittest.TestCase):
    def _read(self, middle, tmp_root: str, **fields):
        from unittest import mock
        fields.setdefault("token", "t")
        fields.setdefault("library", "LIB")
        fields.setdefault("cell", "CELL")
        with mock.patch.object(V, "artifact_dir", lambda: Path(tmp_root) / "artifact"):
            return V.Package(middle).read(V.ReadRequest(**fields))

    def test_happy_path_returns_source_views_and_diagnostics(self):
        import tempfile
        diag = "ERROR (VERILOGIN-19): something odd\nall good otherwise\n"
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._read(CellModeMiddle(diag_log=diag), tmp)
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertIn("module CELL", value["source"]["text"])
        self.assertEqual(value["views"][0]["view"], "verilog")
        self.assertEqual(value["views"][0]["file"], "CELL.v")
        self.assertEqual(value["diagnostics"]["status"], "failed")
        self.assertEqual(value["diagnostics"]["error_count"], 1)
        # 注意：verilog.read 的 value **不含** library/cell/view 身份字段
        # （symbol/layout 的 read 会回填）——已在报告 §3.1 记为跨包一致性观察项
        self.assertNotIn("library", value)
        self.assertEqual(sorted(value), ["diagnostics", "source", "views"])

    def test_missing_diagnostics_is_reported_as_none(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._read(CellModeMiddle(), tmp)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["diagnostics"]["status"], "none")

    def test_focus_limits_sections(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._read(CellModeMiddle(), tmp, focus=["source"])
        self.assertTrue(result.ok, result.error)
        self.assertEqual(sorted(k for k in result.value if k not in
                                ("library", "cell", "view", "view_type")), ["source"])

    def test_short_view_entry_is_skipped(self):
        """守卫改为 len>=4 后，3 元素畸形条目应被跳过而不是 IndexError。"""
        import tempfile
        views = '(("verilog" ("verilog" nil nil)))'
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._read(CellModeMiddle(views=views), tmp)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value.get("views"), [])


class TestVerilogImport(unittest.TestCase):
    # `_imported_cells` 的正则只认 "Checked-in <schematic|symbol|functional view> <cell>"
    BATCH_OK = ("Checked-in functional view counter8 -- ok\n"
                "WARNING (VERILOGIN-19): something odd\n"
                "End of Logfile.\n")

    def _import(self, middle, tmp_root: str, **fields):
        from unittest import mock
        fields.setdefault("token", "t")
        fields.setdefault("library", "LIB")
        fields.setdefault("cell", "CELL")
        design = Path(tmp_root) / "design.v"
        design.write_text("module CELL; endmodule\n", encoding="utf-8")
        fields.setdefault("file_path", str(design))
        with mock.patch.object(V, "artifact_dir", lambda: Path(tmp_root) / "artifact"):
            return V.Package(middle).import_verilog(V.ImportRequest(**fields))

    def test_happy_import_reports_cells_and_warnings(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._import(CellModeMiddle(batch_log=self.BATCH_OK), tmp)
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["reason"], "completed")
        self.assertEqual(value["cells"], ["counter8"])
        self.assertEqual(len(value["warnings"]), 1)
        self.assertTrue(value["log_path"].endswith("verilogIn.batch.log"))
        names = [step["name"] for step in result.steps]
        self.assertIn("library:LIB", names)
        self.assertIn("ihdl", names)

    def test_missing_library_and_ref_lib(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            missing = self._import(CellModeMiddle(lib_exists="nil"), tmp)
            self.assertFalse(missing.ok)
            self.assertIn("target_lib_missing: LIB", missing.error)

            ref_missing = self._import(CellModeMiddle(batch_log=self.BATCH_OK), tmp,
                                       ref_libs=["REF"])
            # REF 默认也存在（lib_exists="t"），这里只验证先查主库再查 ref
            self.assertTrue(ref_missing.ok, ref_missing.error)
            names = [s["name"] for s in ref_missing.steps]
            self.assertIn("library:REF", names)

    def test_parse_failure_and_incomplete_log(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            parse_bad = self._import(CellModeMiddle(
                batch_log="ERROR (VERILOGIN-547): bad\nEnd of Logfile.\n",
                xmvlog="xmvlog: *E,SNYERR syntax error\n"), tmp)
            self.assertFalse(parse_bad.ok)
            self.assertEqual(parse_bad.error, "parse_failed")
            self.assertEqual(parse_bad.value["reason"], "parse_failed")
            self.assertEqual(parse_bad.value["diagnostics"],
                             ["xmvlog: *E,SNYERR syntax error"])

            incomplete = self._import(CellModeMiddle(batch_log="Checked-in verilog view a\n"), tmp)
            self.assertFalse(incomplete.ok)
            self.assertEqual(incomplete.error, "incomplete_log")

    def test_ihdl_nonzero_exit_and_validation(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            # ihdl 非 0 → 原样回显 stderr，不再伪装成 incomplete_log（P-047）
            failed = self._import(CellModeMiddle(ihdl_rc=2), tmp)
            self.assertFalse(failed.ok)
            self.assertEqual(failed.error, "ihdl boom")
            self.assertEqual(failed.value["reason"], "ihdl_failed")

            with self.assertRaises(ValueError):
                V.Package(CellModeMiddle()).import_verilog(V.ImportRequest(
                    token="t", library="LIB", cell="CELL", file_path="x.v",
                    structural_views=9))


if __name__ == "__main__":
    unittest.main()
