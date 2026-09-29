"""L0 flow contracts for ``pyapi.packages.maestro`` with a scripted middle.

真机 TB 只覆盖主流程；本文件用假 middle 覆盖读配置/写/历史/结果/导出的
失败分支与参数分支，把 maestro 的离线覆盖率抬上来（不需要 Virtuoso）。
六步流程（test/docs/写TB规范.md §1）——离线用例：
① 环境检查**不适用**：纯函数 / 假 middle，不连真机；②③ 前置构建/校验**不适用**：无持久对象；
④⑤ = Arrange→Act→Assert；⑥ 无现场可留（不落盘、不起服务、不占端口）。
"""
from __future__ import annotations

import tempfile
import unittest
import shutil
from pathlib import Path
from typing import Any

from common.paths import init_work_dir
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
        self.default_command = CommandResult(
            returncode=0, stdout="", stderr="")
        self.default_gui = CommandResult(
            returncode=0, stdout="", stderr="")

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
        return CommandResult(
            returncode=self.upload_rc, stdout="",
            stderr="upload boom" if self.upload_rc else "")

    def download_file(self, remote_path, local_path, timeout=None, *, token,
                      recursive=False):
        self.calls.append(("download", str(remote_path)))
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        if self.download_rc == 0:
            target.write_text(self.download_body, encoding="utf-8")
        return CommandResult(
            returncode=self.download_rc, stdout="",
            stderr="download boom" if self.download_rc else "",
        )

    def run_gui_command(self, cmd, timeout=None, *, token):
        self.calls.append(("gui", cmd))
        if self.gui_script:
            return self.gui_script.pop(0)
        return self.default_gui


def base_fields() -> dict[str, str]:
    return {"token": "t", "library": "L", "cell": "C", "view": "maestro"}


MC_YIELD_CSV = """\
Test,Name,Yield,Min,Target,Max,Mean,Std Dev,Cpk,Errors
Yield Estimate: 0 %(0 passed/2 pts)     Confidence Level: <not set>   Filter: <not set>,,,,,,,,,
opamp_ac,,,,,,,,,
,gain_db(summary),0% (0/2),0,> 19,0,0,0,,2
,gain_db_vdd_high,0% (0/2),0,> 19,0,0,0,,2
"""


class TestReadConfigFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")

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
        self.assertEqual(result.value["tests"], {})
        self.assertEqual(result.value["corners"], {})
        self.assertTrue(any("maeCloseSession" in code
                            for kind, code in middle.calls if kind == "skill"))

    def test_read_config_includes_monte_carlo_run_options(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("maeGetSetup",
             '(nil nil nil nil "Monte Carlo Sampling" "local")'),
            ("cadr(axlGetVars(", "nil"),
            ("axlGetParameters(", "nil"),
            ("axlGetRunOption",
             '(("mcmethod" "mismatch") ("mcnumpoints" "8") '
             '("dutsummary" "ac%ICTLE%tb_ctle/schematic%#"))'),
        ]
        result = M.Package(middle).read_config(
            M.ReadConfigRequest(**base_fields()))
        self.assertTrue(result.ok, result.error)
        run_options = result.value["run_options"]["Monte Carlo Sampling"]
        self.assertEqual(run_options["mcmethod"], "mismatch")
        self.assertEqual(run_options["mcnumpoints"], "8")
        self.assertEqual(
            run_options["dutsummary"], "ac%ICTLE%tb_ctle/schematic")
        self.assertIsNone(run_options["samplingmode"])


class TestWriteFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")

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

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls._wd, ignore_errors=True)

    def test_minimal_history_list(self):
        middle = FakeMiddle()
        middle.skill_script = [
            # P-104 之后读路径先做 ddGetObj 存在性探测（不建对象）
            ("ddGetObj", "t"),
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

    def test_monte_carlo_history_adds_yield_view(self):
        middle = FakeMiddle()
        middle.download_body = MC_YIELD_CSV
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ('?view "Detail"', "t"),
            ("maeGetOverallYield",
             "(nil Yield 0 PassedPoints 0 ErrorPoints 2)"),
            ('?view "Yield"', "t"),
            ("maeGetSetup", '("_default" "vdd_high")'),
        ]
        result = M.Package(middle).read_results(M.ReadResultsRequest(
            **base_fields(), history="MonteCarlo.0",
        ))
        self.assertTrue(result.ok, result.error)
        mc = result.value["monte_carlo"]
        self.assertEqual(mc["overall"]["yield"], 0)
        self.assertEqual(mc["overall"]["error_points"], 2)
        self.assertEqual(len(mc["outputs"]), 2)
        self.assertTrue(mc["outputs"][0]["summary"])
        self.assertEqual(mc["outputs"][1]["corner"], "vdd_high")


    def test_waveform_missing_psf_is_reported(self):
        middle = FakeMiddle()
        middle.command_script = [
            CommandResult(returncode=0, stdout="", stderr="")
        ]  # find logFile 无结果
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

    def test_open_waveform_failure_closes_created_session(self):
        """R4 回归：新建了只读 session 后流程失败，必须把 session 关掉。"""
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("maeOpenSetup", '"fnxSession1"'),
            ("axlGetResultsLocation", '"/res/other"'),
        ]
        result = M.Package(middle).open_waveform_gui(M.OpenWaveformRequest(
            **base_fields(), history="h1", signals=["vout"],
        ))
        self.assertFalse(result.ok)
        self.assertIn("no PSF logFile", result.error)
        self.assertTrue(any("maeCloseSession" in code
                            for _kind, code in middle.calls if _kind == "skill"),
                        "created session must be closed on failure")


class TestExportFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")

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

    def test_mc_preflight_blocks_no_plot_outputs(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("hiGetWindowList", self._editing_window()),
            ("hiGetWindowList", self._editing_window()),
            ("maeGetCurrentRunMode", '"Monte Carlo Sampling"'),
            ("maeGetTestOutputs", "nil"),
        ]
        result = M.Package(middle).run(M.RunRequest(
            **base_fields(), blocking=False, poll_interval=0.01,
        ))
        self.assertFalse(result.ok)
        self.assertEqual(result.value["reason"], "mc_no_plot_outputs")

    def test_mc_preflight_blocks_sweeps_without_reference_point(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("hiGetWindowList", self._editing_window()),
            ("hiGetWindowList", self._editing_window()),
            ("maeGetCurrentRunMode", '"Monte Carlo Sampling"'),
            ("maeGetTestOutputs", "t"),
            ("axlGetAllSweepsEnabled", '(t "0")'),
        ]
        result = M.Package(middle).run(M.RunRequest(
            **base_fields(), blocking=False, poll_interval=0.01,
        ))
        self.assertFalse(result.ok)
        self.assertEqual(result.value["reason"], "mc_sweeps_conflict")

    def test_mc_preflight_passes_when_clean(self):
        middle = FakeMiddle()
        middle.skill_script = [
            ("maeGetSessions", "nil"),
            ("hiGetWindowList", self._editing_window()),
            ("hiGetWindowList", self._editing_window()),
            ("maeGetCurrentRunMode", '"Monte Carlo Sampling"'),
            ("maeGetTestOutputs", "t"),
            ("axlGetAllSweepsEnabled", "(nil nil)"),
            ("maeSetJobControlMode", "t"),
            ("maeRunSimulation", '"MonteCarlo.0"'),
        ]
        result = M.Package(middle).run(M.RunRequest(
            **base_fields(), blocking=False, poll_interval=0.01,
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["history"], "MonteCarlo.0")
        run_calls = [
            code for kind, code in middle.calls
            if kind == "skill" and "maeRunSimulation" in code
        ]
        self.assertTrue(
            any('?runMode "Monte Carlo Sampling"' in code
                for code in run_calls),
            f"run 未显式透传当前 MC mode: {run_calls}")


class TestGuiFlow(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._wd = tempfile.mkdtemp(prefix="vb-maestro-flow-")

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
