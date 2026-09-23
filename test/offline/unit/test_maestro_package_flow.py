"""L0 flow contracts for ``pyapi.packages.maestro`` with a scripted middle.

真机 TB 只覆盖主流程；本文件用假 middle 覆盖读配置/写/历史/结果/导出的
失败分支与参数分支，把 maestro 的离线覆盖率抬上来（不需要 Virtuoso）。
"""
from __future__ import annotations

import tempfile
import unittest
import shutil
from pathlib import Path
from typing import Any

from common.paths import override_work_dir_for_tests
from pyapi.models import (
    CommandResult,
    ExecutionStatus,
    QueryResult,
    RoleQuery,
    VirtuosoResult,
)
from pyapi.packages import maestro as M


def ok(output: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=output)


def fail(*errors: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=list(errors))


class FakeMiddle:
    """按子串匹配返回预置结果；不匹配时返回默认值。"""

    def __init__(self) -> None:
        self.skill_script: list[tuple[str, Any]] = []
        self.command_script: list[Any] = []
        self.gui_script: list[Any] = []
        self.upload_rc = 0
        self.download_rc = 0
        self.download_body = "1.0 0.5\n2.0 1.5\n"
        self.calls: list[tuple[str, str]] = []
        self.default_skill = ok('"ok"')
        self.default_command = CommandResult(0, "", "")
        self.default_gui = CommandResult(0, "", "")

    def query(self, *, token: str, role=None, name=None) -> QueryResult:
        self.calls.append(("query", token))
        return QueryResult(
            status=ExecutionStatus.SUCCESS,
            roles={
                "command": RoleQuery(root="/role/command"),
                "daemon": RoleQuery(root="/role/daemon"),
                "file": RoleQuery(root="/role/file"),
                "gui": RoleQuery(root="/role/gui"),
            },
        )

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append(("skill", skill_code))
        for index, (sub, result) in enumerate(self.skill_script):
            if sub in skill_code:
                self.skill_script.pop(index)
                return result if isinstance(result, VirtuosoResult) else ok(result)
        return self.default_skill

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        self.calls.append(("command", cmd))
        if self.command_script:
            return self.command_script.pop(0)
        return self.default_command

    def upload_file(self, local_path, remote_path, timeout=None, *, token,
                    recursive=False):
        self.calls.append(("upload", str(local_path)))
        return CommandResult(self.upload_rc, "", "upload boom" if self.upload_rc else "")

    def download_file(self, remote_path, local_path, timeout=None, *, token,
                      recursive=False):
        self.calls.append(("download", str(remote_path)))
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.download_rc == 0:
            target.write_text(self.download_body, encoding="utf-8")
        return CommandResult(
            self.download_rc, "",
            "download boom" if self.download_rc else "",
        )

    def run_gui_command(self, cmd, timeout=None, *, token):
        self.calls.append(("gui", cmd))
        if self.gui_script:
            return self.gui_script.pop(0)
        return self.default_gui


def base_fields() -> dict[str, str]:
    return {"token": "t", "library": "L", "cell": "C", "view": "maestro"}


class TestReadConfigFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")
        override_work_dir_for_tests(cls._wd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def test_open_failure_is_structured(self):
        middle = FakeMiddle()
        middle.skill_script = [("maeOpenSetup", "nil")]
        result = M.Package(middle).read_config(M.ReadConfigRequest(**base_fields()))
        self.assertFalse(result.ok)
        self.assertIn("maeOpenSetup failed", result.error)

    def test_malformed_setup_is_reported(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("maeGetSetup", "(1 2)"),          # 长度不足 6 → 解析失败分支
        ]
        result = M.Package(middle).read_config(M.ReadConfigRequest(**base_fields()))
        self.assertFalse(result.ok)
        self.assertIn("could not parse maeGetSetup", result.error)

    def test_minimal_success_closes_created_session(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("maeGetSetup", '(nil nil nil nil "batch" "local")'),
            ("cadr(axlGetVars(", "nil"),
            ("axlGetParameters(", "nil"),
        ]
        result = M.Package(middle).read_config(M.ReadConfigRequest(**base_fields()))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["tests"], [])
        self.assertEqual(result.value["corners"], [])
        self.assertTrue(any("maeCloseSession" in code
                            for kind, code in middle.calls if kind == "skill"))


class TestWriteFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")
        override_work_dir_for_tests(cls._wd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def test_write_applies_and_closes_created_session(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("hiGetWindowList", "nil"),       # 后台 session：无需 makeEditable
        ]
        result = M.Package(middle).write(M.WriteRequest(
            **base_fields(),
            commands=[{"op": "set_var", "name": "v", "value": "1.0"}],
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["applied"], 1)
        self.assertTrue(any("maeCloseSession" in code
                            for kind, code in middle.calls if kind == "skill"))

    def test_invalid_command_is_reported_with_index(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("hiGetWindowList", "nil"),
        ]
        result = M.Package(middle).write(M.WriteRequest(
            **base_fields(), commands=[{"op": "bogus"}],
        ))
        self.assertFalse(result.ok)
        self.assertIn("command 0 invalid", result.error)

    def test_command_skill_failure_stops(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("hiGetWindowList", "nil"),
            ("maeSetVar", fail("boom")),
        ]
        result = M.Package(middle).write(M.WriteRequest(
            **base_fields(),
            commands=[{"op": "set_var", "name": "v", "value": "1.0"}],
        ))
        self.assertFalse(result.ok)
        self.assertIn("boom", result.error)

    def test_load_corners_upload_failure(self):
        middle = FakeMiddle()
        middle.upload_rc = 1
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("hiGetWindowList", "nil"),
        ]
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            csv_path = Path(tmp) / "corners.csv"
            csv_path.write_text("x\n", encoding="utf-8")
        result = M.Package(middle).write(M.WriteRequest(
            **base_fields(),
            commands=[{"op": "load_corners", "local_path": str(csv_path)}],
        ))
        self.assertFalse(result.ok)
        self.assertIn("upload boom", result.error)


class TestHistoryFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")
        override_work_dir_for_tests(cls._wd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def test_write_history_rename_success(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("hiGetWindowList", "nil"),
            ("maeGetHistoryLockFlag", "0"),
            ("axlSetHistoryName", "t"),
            ("maeSaveSetup", "t"),
            ("cadr(axlGetHistory(", '("h2")'),
        ]
        result = M.Package(middle).write_history(M.WriteHistoryRequest(
            **base_fields(),
            commands=[{"op": "rename", "history": "h1", "new_name": "h2"}],
        ))
        self.assertTrue(result.ok, result.error)

    def test_write_history_invalid_op(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("hiGetWindowList", "nil"),
        ]
        result = M.Package(middle).write_history(M.WriteHistoryRequest(
            **base_fields(), commands=[{"op": "bogus", "history": "h1"}],
        ))
        self.assertFalse(result.ok)


class TestReadHistoryFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")
        override_work_dir_for_tests(cls._wd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def test_minimal_history_list(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("cadr(axlGetHistory(", "nil"),
            ("axlGetCurrentHistory", "nil"),
        ]
        result = M.Package(middle).read_history(M.ReadHistoryRequest(
            **base_fields()))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["histories"], [])


class TestReadResultsFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")
        override_work_dir_for_tests(cls._wd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def test_no_history_is_reported(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("cadr(axlGetHistory(", "nil"),
            ("axlGetCurrentHistory", "nil"),
        ]
        result = M.Package(middle).read_results(M.ReadResultsRequest(
            **base_fields()))
        self.assertFalse(result.ok)
        self.assertIn("no Maestro history", result.error)

    def test_detail_success_parses_csv(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("maeExportOutputView", "t"),
            ("maeGetOverallYield", "nil"),
        ]
        result = M.Package(middle).read_results(M.ReadResultsRequest(
            **base_fields(), history="h1",
        ))
        self.assertTrue(result.ok, result.error)
        self.assertIn("tests", result.value)

    def test_waveform_missing_psf_is_reported(self):
        middle = FakeMiddle()
        middle.command_script = [CommandResult(0, "", "")]  # find logFile 无结果
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("axlGetResultsLocation", '"/res"'),
        ]
        result = M.Package(middle).read_results(M.ReadResultsRequest(
            **base_fields(), history="h1", waveform="vout",
            analysis="ac",
        ))
        self.assertFalse(result.ok)
        self.assertIn("no PSF logFile", result.error)


class TestExportFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")
        override_work_dir_for_tests(cls._wd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def test_unknown_kind_is_rejected(self):
        with self.assertRaises(ValueError):
            M.Package(FakeMiddle()).export(M.ExportRequest(
                **base_fields(), kind="bogus"))

    def test_screenshot_window_not_found(self):
        middle = FakeMiddle()
        middle.skill_script = [("hiGetWindowList", fail("window not found"))]
        result = M.Package(middle).export(M.ExportRequest(
            **base_fields(), kind="screenshot",
        ))
        self.assertFalse(result.ok)

    def test_screenshot_capture_failure(self):
        middle = FakeMiddle()
        middle.skill_script = [("hiWindowSaveImage", ok('"capture-failed"'))]
        result = M.Package(middle).export(M.ExportRequest(
            **base_fields(), kind="screenshot",
        ))
        self.assertFalse(result.ok)
        self.assertIn("capture-failed", result.error)

    def test_non_screenshot_export_open_failure(self):
        middle = FakeMiddle()
        middle.skill_script = [("maeOpenSetup", "nil")]
        result = M.Package(middle).export(M.ExportRequest(
            **base_fields(), kind="netlist",
        ))
        self.assertFalse(result.ok)
        self.assertIn("maeOpenSetup failed", result.error)


class TestRunFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")
        override_work_dir_for_tests(cls._wd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def _editing_window(self) -> str:
        return ('(("fnxSession9" 12 '
                '"Virtuoso ADE Assembler Editing: L C maestro"))')

    def test_nonblocking_run_starts(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("hiGetWindowList", self._editing_window()),
            ("hiGetWindowList", self._editing_window()),
            ("maeSetJobControlMode", "t"),
            ("maeRunSimulation", '"h1"'),
        ]
        result = M.Package(middle).run(M.RunRequest(
            **base_fields(), blocking=False, poll_interval=0.01,
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["history"], "h1")
        self.assertEqual(result.value["status"], "started")

    def test_run_start_failure_diagnoses_and_retries(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("hiGetWindowList", self._editing_window()),
            ("hiGetWindowList", self._editing_window()),
            ("maeSetJobControlMode", "t"),
            ("maeRunSimulation", fail("run boom")),
            ("hiGetCurrentForm", "nil"),
            ("maeRunSimulation", fail("run boom again")),
        ]
        result = M.Package(middle).run(M.RunRequest(
            **base_fields(), blocking=False, poll_interval=0.01,
        ))
        self.assertFalse(result.ok)
        self.assertIn("maeRunSimulation", result.error)


class TestGuiFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")
        override_work_dir_for_tests(cls._wd)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def test_open_gui_reports_open_failure(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("hiGetWindowList", "nil"),
            ("hiGetWindowList", "nil"),
            ("deOpenCellView", "nil"),
        ]
        result = M.Package(middle).open_gui(M.OpenGuiRequest(
            **base_fields()))
        self.assertFalse(result.ok)
        self.assertIn("deOpenCellView failed", result.error)

    def test_close_gui_without_window_is_clean_noop(self):
        middle = FakeMiddle()
        middle.skill_script = [("hiGetWindowList", "nil")]
        result = M.Package(middle).close_gui(M.CloseGuiRequest(
            **base_fields()))
        self.assertTrue(result.ok, result.error)
        self.assertFalse(result.value["closed"])


if __name__ == "__main__":
    unittest.main()
