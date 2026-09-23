"""calibre 包单元测试：deck 改写、作业状态判据、报告解析、三件套启动与结果读取。

用假 Middle（不碰真机），覆盖 spec ``12-calibre.md`` §3/§4 的主要分支。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.paths import override_work_dir_for_tests
from pyapi.models import CommandResult, ExecutionStatus, QueryResult, RoleQuery
from pyapi.packages import _calibre_util as cu
from pyapi.packages import calibre as cal
from pyapi.packages.calibre import (
    CheckEnvRequest,
    ExportRequest,
    OPERATIONS,
    Package,
    ReadResultsRequest,
    RunRequest,
    StatusRequest,
)

TOKEN = "vb-vblog"
ROOT = "/home/Gent/.virtuoso-bridge/vblog"
ROOM = f"{ROOT}/calibre"
DECK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre/drc/calibre.drc"

DECK_TEXT = 'LAYOUT PATH "GDSFILENAME"\nLAYOUT PRIMARY "TOPCELLNAME"\nLAYOUT SYSTEM GDSII\n'
DRC_REPORT = """*******************************************************************
TOTAL RULECHECKS EXECUTED = 1737
TOTAL RESULTS GENERATED = 36 (36)
RESULT M1.S.1 12
RESULT PO.S.5 24
*******************************************************************
"""
LVS_REPORT = """Cell ctle
LVS completed. INCORRECT. See report file: lvs.rep
                    Total Initial Nets      = 7
                    Total Initial Instances = 8
"""
PEX_LOG = """xRC Warnings  =  8
xRC Errors  =  0
PEX NETLIST FILE = net.dist
"""


class FakeMiddle:
    def __init__(self, *, kind: str = "drc", completed: bool = True,
                 with_calibre_group: bool = True) -> None:
        self.kind = kind
        self.completed = completed
        self.with_calibre_group = with_calibre_group
        self.calibre_bin = "/opt/eda/mentor/CALIBRE2025/bin/calibre"
        self.commands: list[str] = []
        self.uploads: list[tuple[str, str]] = []
        self.downloads: list[str] = []
        self.tail_text = "log tail line 1\nlog tail line 2\n"

    # -- 中层接口 -----------------------------------------------------------
    def query(self, *, token: str) -> QueryResult:
        if token != TOKEN:
            return QueryResult(status=ExecutionStatus.ERROR, errors=["invalid token"])
        role = RoleQuery(root=ROOT)
        if self.with_calibre_group:
            # per-role 用户组（spec 中层配置文档 §2.3）：role.command.calibre = {bin, version}
            role = RoleQuery(root=ROOT, calibre={"bin": self.calibre_bin,
                                                 "version": "v2025.1_16.10"})
        return QueryResult(status=ExecutionStatus.SUCCESS,
                           roles={"command": role})

    def run_command(self, cmd, timeout=None, *, token, parallel=False) -> CommandResult:
        self.commands.append(cmd)
        text = cmd
        if "###PATH" in text:  # check_env
            stdout = "###PATH\n/opt/eda/mentor/CALIBRE2025/bin/calibre\n###VERSION\nCalibre v2025.1_16.10\n###DECK\ndeck_file_ok\ndfm_ok\n"
        elif "test -f" in text:
            stdout = "yes\n"
        elif "cd" in text and "job.json" in text and "###JOB" in text:  # status snapshot
            marker = "CALIBRE::DRC-H COMPLETED" if self.completed else "FATAL ERROR: license"
            stdout = (
                "###JOB\n{\"kind\": \"drc\", \"job_id\": \"drc_inv2\"}\n"
                "###PID\n4242\n"
                "###ALIVE\n" + ("" if self.completed else "4242\n") +
                f"###LOGS\n== {self.kind}.log\nSOME LOG\n{marker}\n"
                "###FILES\nDRC.rep\nDRC_RES.db\njob.json\n"
            )
        elif "chmod +x launch.sh" in text:
            stdout = "###PID\n4242\n###PROC\n4242\n"
        elif "tail -n" in text:
            stdout = self.tail_text
        elif "TOTAL RULECHECKS EXECUTED" in text:  # 计数 grep
            stdout = ("--- TOTAL RULECHECKS EXECUTED = 1737\n"
                      "--- TOTAL RESULTS GENERATED = 36 (36)\n")
        elif "ls -1" in text:
            stdout = "DRC.rep\nDRC_RES.db\njob.json\n"
        elif "if [ -f lvs.rep ]" in text:
            stdout = "lvs\n"
        else:
            stdout = ""
        return CommandResult(returncode=0, stdout=stdout, stderr="", kind="command")

    def download_file(self, remote_path, local_path, timeout=None, *, token,
                      recursive=False) -> CommandResult:
        self.downloads.append(str(remote_path))
        target = Path(local_path)
        if recursive and target.suffix == "":
            target.mkdir(parents=True, exist_ok=True)
            (target / "probe.txt").write_text("dir", encoding="utf-8")
            return CommandResult(0, "", "", "command")
        target.parent.mkdir(parents=True, exist_ok=True)
        if remote_path.endswith(".drc") or "calibre.lvs" in remote_path:
            content = DECK_TEXT
        elif remote_path.endswith("DRC.rep"):
            content = DRC_REPORT
        elif remote_path.endswith("lvs.rep"):
            content = LVS_REPORT
        elif remote_path.endswith(("pex.stage2.log", "pex.stage3.log")):
            content = PEX_LOG
        else:
            content = "x\n"
        target.write_text(content, encoding="utf-8")
        return CommandResult(0, "", "", "command")

    def upload_file(self, local_path, remote_path, timeout=None, *, token,
                    recursive=False) -> CommandResult:
        self.uploads.append((str(local_path), str(remote_path)))
        assert Path(local_path).is_file(), f"upload source missing: {local_path}"
        return CommandResult(0, "", "", "command")


class UtilTests(unittest.TestCase):
    def test_deck_rewrite_whitelist(self):
        text, changes = cu.deck_rewrite(DECK_TEXT, gds="/x/lay.gds", top="lay_e2e")
        self.assertIn('"/x/lay.gds"', text)
        self.assertIn('"lay_e2e"', text)
        self.assertEqual(len(changes), 2)

    def test_deck_rewrite_lvs_placeholders(self):
        text = 'LAYOUT PATH "lvs_top.gds"\nSOURCE PATH "lvs_top.cdl"\nLAYOUT PRIMARY "lvs_top"\n'
        out, _ = cu.deck_rewrite(text, gds="/x/ctle.gds", top="ctle", cdl="/x/ctle.cdl")
        self.assertIn('"/x/ctle.gds"', out)
        self.assertIn('"/x/ctle.cdl"', out)
        self.assertIn('"ctle"', out)

    def test_job_state_completed(self):
        state = cu.job_state("drc", process_alive=False,
                             log_tail="CALIBRE::DRC-H COMPLETED", artifacts=["DRC.rep"])
        self.assertEqual(state.status, "completed")

    def test_job_state_failed_license(self):
        state = cu.job_state("drc", process_alive=False,
                             log_tail="FATAL ERROR: cannot checkout calibre license",
                             artifacts=[])
        self.assertEqual(state.status, "failed")
        self.assertEqual(state.failure_kind, "license")

    def test_job_state_running_and_unknown(self):
        running = cu.job_state("lvs", process_alive=True, log_tail="Running netlist", artifacts=[])
        self.assertEqual(running.status, "running")
        unknown = cu.job_state("lvs", process_alive=False, log_tail="", artifacts=[])
        self.assertEqual(unknown.status, "unknown")

    def test_parse_drc_report(self):
        parsed = cu.parse_drc_report(DRC_REPORT)
        self.assertEqual(parsed["rules_checked"], 1737)
        self.assertEqual(parsed["total_results"], 36)
        self.assertEqual(parsed["by_rule"]["M1.S.1"], 12)

    def test_parse_lvs_report(self):
        parsed = cu.parse_lvs_report(LVS_REPORT)
        self.assertEqual(parsed["status"], "incorrect")
        self.assertEqual(parsed["counts"]["total_initial_nets"], 7)

    def test_parse_pex_log(self):
        parsed = cu.parse_pex_log(PEX_LOG)
        self.assertEqual(parsed["errors"], 0)
        self.assertEqual(parsed["warnings"], 8)
        self.assertEqual(parsed["netlist_files"], ["net.dist"])

    def test_launcher_backgrounds_and_marks_stages(self):
        script = cu.build_launcher(kind="pex", run_dir="/r", argv=None,
                                   stages=[["calibre", "-xrc", "-phdb"], ["calibre", "-xrc", "-pdb"]],
                                   job_meta={"kind": "pex"})
        self.assertIn("ulimit -n 65536", script)
        self.assertIn("echo $! > job.pid", script)
        self.assertIn("stage1_failed", script)
        self.assertIn("echo COMPLETED >> pex.log", script)


class PackageTests(unittest.TestCase):
    def setUp(self):
        self._wd = Path(tempfile.mkdtemp(prefix="vb-calibre-wd-"))
        override_work_dir_for_tests(self._wd)

    def test_operations_registered(self):
        self.assertEqual({op[0] for op in OPERATIONS}, set(cal.OPERATION_NAMES))
        self.assertIn("calibre.drc", cal.OPERATION_NAMES)
        self.assertIn("calibre.read_results", cal.OPERATION_NAMES)

    def test_check_env(self):
        middle = FakeMiddle()
        result = Package(middle).check_env(CheckEnvRequest(token=TOKEN, deck=DECK))
        self.assertTrue(result.ok, result.error)
        self.assertTrue(result.value["calibre_path"].endswith("calibre"))
        self.assertTrue(result.value["deck_ok"])

    def test_missing_calibre_facts_fails_without_fallback(self):
        """注册表没给 role.command.calibre.bin 时：明确失败，不回退 PATH。"""
        middle = FakeMiddle(with_calibre_group=False)
        result = Package(middle).check_env(CheckEnvRequest(token=TOKEN, deck=DECK))
        self.assertFalse(result.ok)
        self.assertIn("role.command.calibre", result.error or "")
        result2 = Package(middle).drc(RunRequest(
            token=TOKEN, gds="/x/lay_e2e.gds", top="lay_e2e", deck=DECK,
        ))
        self.assertFalse(result2.ok)
        self.assertIn("role.command.calibre", result2.error or "")

    def test_request_override_wins(self):
        """请求显式给 calibre_bin 时优先，且不读注册表。"""
        middle = FakeMiddle(with_calibre_group=False)
        result = Package(middle).check_env(CheckEnvRequest(
            token=TOKEN, calibre_bin="/custom/bin/calibre", deck=DECK,
        ))
        self.assertTrue(result.ok, result.error)

    def test_drc_start_nonblocking(self):
        middle = FakeMiddle()
        result = Package(middle).drc(RunRequest(
            token=TOKEN, gds="/x/lay_e2e.gds", top="lay_e2e", deck=DECK,
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["run_dir"], f"{ROOM}/drc_lay_e2e")
        self.assertIn("stage-deck", [step["name"] for step in result.steps])
        self.assertIn("rewrite-deck", [step["name"] for step in result.steps])
        self.assertIn("upload-deck", [step["name"] for step in result.steps])
        self.assertTrue(any(remote.endswith("run_drc.cal") for _, remote in middle.uploads))
        self.assertTrue(any(remote.endswith("launch.sh") for _, remote in middle.uploads))

    def test_drc_blocking_completes(self):
        middle = FakeMiddle(completed=True)
        result = Package(middle).drc(RunRequest(
            token=TOKEN, gds="/x/lay_e2e.gds", top="lay_e2e", deck=DECK,
            blocking=True, poll_interval=0.01, timeout=20,
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["status"], "completed")

    def test_lvs_requires_cdl(self):
        middle = FakeMiddle()
        result = Package(middle).lvs(RunRequest(
            token=TOKEN, gds="/x/ctle.gds", top="ctle", deck="/x/calibre.lvs",
        ))
        self.assertFalse(result.ok)
        self.assertIn("cdl", result.error or "")

    def test_status_completed(self):
        middle = FakeMiddle(completed=True)
        result = Package(middle).status(StatusRequest(
            token=TOKEN, job_id="drc_lay_e2e", kind="drc",
        ))
        self.assertTrue(result.ok)
        self.assertEqual(result.value["status"], "completed")

    def test_read_results_drc(self):
        middle = FakeMiddle()
        result = Package(middle).read_results(ReadResultsRequest(
            token=TOKEN, job_id="drc_lay_e2e", kind="drc",
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["summary"]["rules_checked"], 1737)
        self.assertEqual(result.value["report_used"], "DRC.rep")

    def test_read_results_pex(self):
        middle = FakeMiddle()
        result = Package(middle).read_results(ReadResultsRequest(
            token=TOKEN, job_id="pex_ctle", kind="pex",
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["summary"]["warnings"], 8)

    def test_read_results_pex_stage_failure_is_reported(self):
        middle = FakeMiddle()
        middle.tail_text = "pex.stage3.log\nstage3_failed\n"
        result = Package(middle).read_results(ReadResultsRequest(
            token=TOKEN, job_id="pex_ctle", kind="pex",
        ))
        self.assertFalse(result.ok)
        self.assertIn("stage failed", result.error)

    def test_export_summary(self):
        middle = FakeMiddle()
        with tempfile.TemporaryDirectory(prefix="vb-cal-") as tmp:
            result = Package(middle).export(ExportRequest(
                token=TOKEN, job_id="drc_lay_e2e", kind="drc",
                items=("summary",), local_dir=str(Path(tmp) / "out"),
            ))
            self.assertTrue(result.ok, result.error)
            self.assertTrue(result.value["downloaded"])
            local = Path(result.value["downloaded"][0]["local"])
            self.assertTrue(local.is_file())

    def test_validation(self):
        with self.assertRaises(ValueError):
            RunRequest(token=TOKEN, gds="g", top="t", deck="d", turbo=0)
        with self.assertRaises(ValueError):
            StatusRequest(token=TOKEN)
        with self.assertRaises(ValueError):
            ExportRequest(token=TOKEN, job_id="j", items=("bogus",))
        with self.assertRaises(ValueError):
            ReadResultsRequest(token=TOKEN, job_id="j", limit=0)


if __name__ == "__main__":
    unittest.main()
