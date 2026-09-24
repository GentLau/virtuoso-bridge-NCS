"""calibre 包单元测试：deck 改写、作业状态判据、报告解析、三件套启动与结果读取。

用假 Middle（不碰真机），覆盖 spec ``12-calibre.md`` §3/§4 的主要分支。
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))

from common.paths import init_work_dir
from pyapi.models import (CommandResult, ExecutionStatus, QueryResult, RoleQuery,
                          VirtuosoResult)
from pyapi.packages import _calibre_util as cu
from pyapi.packages import calibre as cal
from pyapi.packages.calibre import (
    CheckEnvRequest,
    ExportCdlRequest,
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

#: 一份**真实形态**的 Calibre Interactive LVS set（SMIC 40LLRF 现场文件的结构，
#: 内容换成我们环境里存在的路径）——用来钉住"把 set 直接喂进来"的语义。
REAL_LVS_RUNSET = "\n".join([
    "*lvsRulesFile: /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre/lvs/calibre.lvs",
    "*lvsRunDir: /r/lvs",
    "*lvsLayoutPrimary: inv2",
    "*lvsLayoutPaths: inv2.gds",
    "*lvsLayoutLibrary: bonn_controlled_lib",
    "*lvsLayoutView: layout",
    "*lvsLayoutGetFromViewer: 1",
    "*lvsSourcePath: inv2.src.net",
    "*lvsSourcePrimary: inv2",
    "*lvsSourceLibrary: bonn_controlled_lib",
    "*lvsSourceView: schematic",
    "*lvsSourceGetFromViewer: 1",
    "*lvsSpiceFile: inv2.sp",
    "*lvsUseHCells: 1",
    "*lvsHCellsFile: /pdk/hcelllist",
    "*lvsPowerNames: avdd avs33",
    "*lvsGroundNames: avss",
    "*lvsRecognizeGates: NONE",
    "*lvsERCDatabase: inv2.erc.results",
    "*lvsERCSummaryFile: inv2.erc.summary",
    "*lvsIncludeCmdsType: SVRF",
    "*lvsSVRFCmds: {LVS FILTER C(CP) OPEN} {}",
    "*lvsReportFile: inv2.lvs.report",
    "*lvsReportMaximumCount: 1000",
    "*lvsReportOptions: FX",
    "*lvsAbortOnSupplyError: 0",
    "*lvsSVDBxcal: 1",
    "*lvsMaskDBFile: metal_c.maskdb",
    "*cmnWarnLayoutOverwrite: 0",
    "*cmnPromptSaveRunset: 0",
    "*cmnRunMT: 1",
    "*cmnSlaveHosts: {use {}} {hostName {}}",
    "*cmnFDILayoutLibrary: bonn_controlled_lib",
    "*cmnFDILayoutView: layout",
    "*cmnFDIDEFLayoutPath: inv2.def",
    "*cmnConfigureLVSBox: 1",
    "",
])
REAL_LVS_DECK = "\n".join([
    'LAYOUT PRIMARY "lvs_top"',
    'LAYOUT PATH "lvs_top.gds"',
    'SOURCE PRIMARY "lvs_top"',
    'SOURCE PATH "lvs_top.cdl"',
    'VARIABLE POWER_NAME  "VDD"',
    'VARIABLE GROUND_NAME  "VSS"',
    "LVS POWER NAME POWER_NAME",
    "LVS GROUND NAME GROUND_NAME",
    "LVS RECOGNIZE GATES NONE",
    'LVS REPORT "lvs.rep"',
    "LVS REPORT MAXIMUM 1000",
    "LVS REPORT OPTION S",
    "LVS ABORT ON SUPPLY ERROR NO",
    "",
])


class FakeMiddle:
    def __init__(self, *, kind: str = "drc", completed: bool = True,
                 with_calibre_group: bool = True, root: str | None = ROOT,
                 upload_rc: int = 0, download_rc: int = 0,
                 snapshot_rc: int = 0, si_rc: int = 0,
                 netlist_bytes: int = 256, cds_lib_exists: bool = True,
                 ciw_cwd: str | None = "/home/Gent/proj",
                 deck_text: str = DECK_TEXT) -> None:
        self.kind = kind
        self.completed = completed
        self.with_calibre_group = with_calibre_group
        self.root = root
        self.upload_rc = upload_rc
        self.download_rc = download_rc
        self.snapshot_rc = snapshot_rc
        self.si_rc = si_rc
        self.netlist_bytes = netlist_bytes
        self.cds_lib_exists = cds_lib_exists
        self.ciw_cwd = ciw_cwd
        self.deck_text = deck_text
        self.calibre_bin = "/opt/eda/mentor/CALIBRE2025/bin/calibre"
        self.commands: list[str] = []
        self.uploads: list[tuple[str, str]] = []
        self.downloads: list[str] = []
        self.tail_text = "log tail line 1\nlog tail line 2\n"

    # -- 中层接口 -----------------------------------------------------------
    def query(self, *, token: str) -> QueryResult:
        if token != TOKEN:
            return QueryResult(status=ExecutionStatus.ERROR, errors=["invalid token"])
        role = RoleQuery(root=self.root)
        if self.with_calibre_group:
            # per-role 用户组（spec 中层配置文档 §2.3）：role.command.calibre = {bin, version}
            role = RoleQuery(root=self.root, calibre={"bin": self.calibre_bin,
                                                 "version": "v2025.1_16.10"})
        return QueryResult(status=ExecutionStatus.SUCCESS,
                           roles={"command": role})

    def run_command(self, cmd, timeout=None, *, token, parallel=False) -> CommandResult:
        self.commands.append(cmd)
        text = cmd
        if "###PATH" in text:  # check_env
            stdout = "###PATH\n/opt/eda/mentor/CALIBRE2025/bin/calibre\n###VERSION\nCalibre v2025.1_16.10\n###DECK\ndeck_file_ok\ndfm_ok\n"
        elif "si . -batch -command netlist" in text:  # auCdl 导出
            return CommandResult(self.si_rc, "", "si boom" if self.si_rc else "", "command")
        elif "wc -c <" in text:
            stdout = f"{self.netlist_bytes}\n" if self.netlist_bytes else ""
        elif "test -f" in text:
            stdout = "yes\n" if self.cds_lib_exists else "no\n"
        elif "cd" in text and "job.json" in text and "###JOB" in text:  # status snapshot
            if self.snapshot_rc != 0:
                return CommandResult(self.snapshot_rc, "", "snapshot boom", "command")
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
        if self.download_rc != 0:
            return CommandResult(self.download_rc, "", "download boom", "command")
        target = Path(local_path)
        if recursive and target.suffix == "":
            target.mkdir(parents=True, exist_ok=True)
            (target / "probe.txt").write_text("dir", encoding="utf-8")
            return CommandResult(0, "", "", "command")
        target.parent.mkdir(parents=True, exist_ok=True)
        if remote_path.endswith(".drc") or "calibre.lvs" in remote_path:
            content = self.deck_text
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
        return CommandResult(self.upload_rc, "",
                             "upload boom" if self.upload_rc else "", "command")

    def execute_skill(self, skill_code, timeout=None, *, token,
                      log_level=None, log_max_bytes=None) -> VirtuosoResult:
        """CIW 侧事实：只有 `getWorkingDir()`（auCdl 解析 cds.lib 用）。"""
        self.commands.append(f"SKILL:{skill_code}")
        if self.ciw_cwd is None:
            return VirtuosoResult(status=ExecutionStatus.ERROR, errors=["no CIW"])
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=f'"{self.ciw_cwd}"')

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

    def test_deck_missing_inputs_only_reports_existing_placeholders(self):
        self.assertEqual(
            cu.deck_missing_inputs('INCLUDE "/pdk/calibre.lvs"\n', gds=None, top=None, cdl=None),
            [])
        self.assertEqual(
            cu.deck_missing_inputs('SOURCE PATH "lvs_top.cdl"\n', gds="/x/a.gds",
                                   top="a", cdl=None),
            ['"lvs_top.cdl"→cdl'])
        self.assertEqual(
            cu.deck_missing_inputs('LAYOUT PATH "GDSFILENAME"\n', gds=None, top=None, cdl=None),
            ['"GDSFILENAME"→gds'])

    def test_parse_runset_and_locate_run_dir(self):
        """set 只用来**定位产物目录**（轮询/取报告）；参数一律交给官方入口。"""
        runset = ("// Calibre Interactive runset\n"
                  "*lvsLayoutPrimary: inv2\n"
                  "*lvsRunDir: /simulation/SUSER/extract/lvs\n"
                  "*cmnRunMT: 1\n")
        parsed = cu.parse_runset(runset)
        self.assertEqual(parsed["lvsLayoutPrimary"], "inv2")
        self.assertEqual(cu.runset_run_dir(parsed), "/simulation/SUSER/extract/lvs")
        self.assertIsNone(cu.runset_run_dir({"lvsLayoutPrimary": "inv2"}))

    def test_params_only_accept_svrf_statement_heads(self):
        """不做 runset 键→语句的映射表：键必须是 SVRF 语句头（含空格）。"""
        overrides = cu.statements_from_params(
            {"LAYOUT PRIMARY": 'LAYOUT PRIMARY "inv2"'})
        self.assertEqual(overrides, {"LAYOUT PRIMARY": 'LAYOUT PRIMARY "inv2"'})
        with self.assertRaises(ValueError) as ctx:
            cu.statements_from_params({"lvsLayoutPrimary": "inv2"})
        self.assertIn("SVRF 语句头", str(ctx.exception))

    def test_apply_statements_replaces_first_occurrence_in_place(self):
        """first-wins：必须改在 deck 里、改在第一条上（GUI 的 INCLUDE+覆盖对 spec 语句无效）。"""
        deck = ('INCLUDE "/other"\n'
                'LAYOUT PRIMARY "lvs_top"\n'
                'LAYOUT PATH "lvs_top.gds"\n'
                'LAYOUT PRIMARY "second"\n')
        out, changed, appended = cu.apply_statements(deck, {
            "LAYOUT PRIMARY": 'LAYOUT PRIMARY "inv2"',
            "MASK SVDB DIRECTORY": 'MASK SVDB DIRECTORY "/x/svdb" QUERY',
        })
        self.assertEqual(appended, ['MASK SVDB DIRECTORY -> MASK SVDB DIRECTORY "/x/svdb" QUERY'])
        self.assertIn('LAYOUT PRIMARY "inv2"\n', out)
        self.assertIn('LAYOUT PRIMARY "second"\n', out)      # 后面的重复行不动
        self.assertTrue(out.endswith('MASK SVDB DIRECTORY "/x/svdb" QUERY\n'))
        self.assertIn('LAYOUT PRIMARY -> LAYOUT PRIMARY "inv2"', changed)

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

    def test_job_state_input_error_keeps_license_banner_out(self):
        """真机 2026-09-24：control file 语法错被日志头的 LICENSE 字样带偏成 license。"""
        log_tail = ("//  OR ITS LICENSORS AND IS SUBJECT TO LICENSE TERMS.\n"
                    "//  Running on 4 CPUs (pending licensing)\n"
                    "ERROR: Error SYN1 on line 1 of run_lvs.cal - unrecognized operation.\n")
        state = cu.job_state("lvs", process_alive=False, log_tail=log_tail,
                             artifacts=["job.json"])
        self.assertEqual(state.status, "failed")
        self.assertEqual(state.failure_kind, "input")

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
        init_work_dir(self._wd)

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

    def test_lvs_deck_without_source_fails_only_when_placeholder_present(self):
        """deck 没给 cdl 又真的引用了 source → 明确失败（不再靠无条件的 cdl 必填）。"""
        middle = FakeMiddle(deck_text='LAYOUT PATH "/x/ctle.gds"\nSOURCE PATH "lvs_top.cdl"\n')
        result = Package(middle).lvs(RunRequest(
            token=TOKEN, gds="/x/ctle.gds", top="ctle", deck="/x/calibre.lvs",
        ))
        self.assertFalse(result.ok)
        self.assertIn("cdl", result.error or "")
        self.assertIn("自包含", result.error or "")

    def test_self_contained_control_file_needs_no_gds_top_cdl(self):
        """GUI runset 生成的 control file（INCLUDE 原 deck + 覆盖）形态：参数全在文件里。"""
        deck = ('INCLUDE "/pdk/calibre.lvs"\n'
                'LAYOUT PATH "/x/inv2.gds"\n'
                'SOURCE PATH "/x/inv2.cdl"\n'
                'LAYOUT PRIMARY "inv2"\n')
        middle = FakeMiddle(deck_text=deck)
        result = Package(middle).lvs(RunRequest(token=TOKEN, deck="/x/ctl/runset.lvs"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["deck_changes"], [])
        detail = next(s["detail"] for s in result.steps if s["name"] == "rewrite-deck")
        self.assertTrue(detail["self_contained"])
        self.assertEqual(detail["missing"], [])
        self.assertEqual(result.value["job_id"], "lvs_runset.lvs")

    def test_lvs_params_override_deck_in_place(self):
        """无 set 的取数口：SVRF 语句头 → 原位改写 deck（参数合并仍由 Calibre 自己做）。"""
        middle = FakeMiddle()
        result = Package(middle).lvs(RunRequest(
            token=TOKEN, deck="/x/calibre.lvs",
            params={"LAYOUT PATH": 'LAYOUT PATH "/x/inv2.gds"',
                    "LAYOUT PRIMARY": 'LAYOUT PRIMARY "inv2"',
                    "SOURCE PATH": 'SOURCE PATH "/x/inv2.cdl"',
                    "SOURCE PRIMARY": 'SOURCE PRIMARY "inv2"'},
        ))
        self.assertTrue(result.ok, result.error)
        uploaded = next(local for local, remote in middle.uploads if remote.endswith("run_lvs.cal"))
        text = Path(uploaded).read_text(encoding="utf-8")
        self.assertIn('LAYOUT PATH "/x/inv2.gds"', text)
        self.assertIn('LAYOUT PRIMARY "inv2"', text)
        self.assertIn('SOURCE PATH "/x/inv2.cdl"', text)
        self.assertIn("LAYOUT SYSTEM GDSII", text)   # 没被点名的语句保持原样
        detail = next(s["detail"] for s in result.steps if s["name"] == "params")
        self.assertEqual(sorted(detail["keys"]),
                         ["LAYOUT PATH", "LAYOUT PRIMARY", "SOURCE PATH", "SOURCE PRIMARY"])

    def test_lvs_runset_goes_through_official_batch_entry(self):
        """带 set：参数合并交给 Calibre（-gui -lvs -runset <f> -batch），我们不碰 deck。"""
        middle = FakeMiddle()
        original = middle.download_file

        def with_runset(remote_path, local_path, timeout=None, *, token, recursive=False):
            if str(remote_path) == "/x/calibre.runset":
                target = Path(local_path)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("*lvsRulesFile: /pdk/calibre.lvs\n"
                                  "*lvsRunDir: /simulation/SUSER/extract/lvs\n"
                                  "*lvsLayoutPrimary: inv2\n", encoding="utf-8")
                return CommandResult(0, "", "", "command")
            return original(remote_path, local_path, timeout, token=token, recursive=recursive)

        middle.download_file = with_runset
        result = Package(middle).lvs(RunRequest(token=TOKEN, runset="/x/calibre.runset"))
        self.assertTrue(result.ok, result.error)
        launcher = next(local for local, remote in middle.uploads
                        if remote.endswith("launch.sh"))
        script = Path(launcher).read_text(encoding="utf-8")
        self.assertIn("-gui", script)
        self.assertIn("-runset", script)
        self.assertIn("/x/calibre.runset", script)
        self.assertIn("-batch", script)
        detail = next(s["detail"] for s in result.steps if s["name"] == "runset")
        self.assertEqual(detail["run_dir"], "/simulation/SUSER/extract/lvs")   # 只用来定位产物
        self.assertEqual(result.value["run_dir"], "/simulation/SUSER/extract/lvs")
        self.assertEqual(result.value["mode"], "official-batch")
        self.assertFalse(any(remote.endswith("run_lvs.cal") for _, remote in middle.uploads),
                         "带 set 时不允许再自己生成/改写 deck")

    def test_params_with_runset_keys_are_rejected(self):
        """不做 runset 键映射：camelCase 键必须报错并指路官方入口。"""
        result = Package(FakeMiddle()).lvs(RunRequest(
            token=TOKEN, gds="/x/a.gds", top="a", deck="/x/calibre.lvs",
            params={"lvsLayoutPrimary": "inv2"},
        ))
        self.assertFalse(result.ok)
        self.assertIn("SVRF 语句头", result.error or "")
        self.assertIn("runset=", result.error or "")

    def test_export_cdl_uses_official_aucdl_link(self):
        """auCdl：si.env 必须带 auCdl 三件套 + checkCAPPERI（IC618 OSSHNL-411 缺口）。"""
        middle = FakeMiddle()
        result = Package(middle).export_cdl(ExportCdlRequest(
            token=TOKEN, library="CMP_LIB", cell="inv2",
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["run_dir"], f"{ROOM}/cdl_inv2")
        self.assertEqual(result.value["cds_lib"], "/home/Gent/proj/cds.lib")
        self.assertEqual(result.value["cds_lib"], "/home/Gent/proj/cds.lib")
        self.assertEqual(result.value["bytes"], 256)
        si_cmd = next(c for c in middle.commands if "si . -batch" in c)
        self.assertIn("CDS_Netlisting_Mode=Analog", si_cmd)
        # cds.lib 用 run dir 内的副本（CIW 的 cds.lib 只拷贝，不改写）
        self.assertIn(f"-cdslib {ROOM}/cdl_inv2/cds.lib", si_cmd)
        self.assertIn(f"cp /home/Gent/proj/cds.lib {ROOM}/cdl_inv2/cds.lib",
                      next(c for c in middle.commands if "cp " in c and "mkdir" in c))
        si_env_local = next(local for local, remote in middle.uploads
                            if remote.endswith("si.env"))
        text = Path(si_env_local).read_text(encoding="utf-8")
        self.assertIn('simSimulator = "auCdl"', text)
        self.assertIn('simViewList = \'("auCdl" "schematic")', text)
        self.assertIn('simStopList = \'("auCdl")', text)
        self.assertIn("checkCAPPERI = nil", text)
        self.assertIn('simLibName = "CMP_LIB"', text)
        self.assertIn('hnlNetlistFileName = "inv2.cdl"', text)
        names = [step["name"] for step in result.steps]
        self.assertEqual(names, ["query", "ciw-cds-lib", "prepare", "upload", "si"])
        self.assertTrue(result.value["netlist_path"].endswith("inv2.cdl"))

    def test_export_cdl_explicit_cds_lib_skips_ciw(self):
        middle = FakeMiddle(ciw_cwd=None)
        result = Package(middle).export_cdl(ExportCdlRequest(
            token=TOKEN, library="CMP_LIB", cell="inv2",
            cds_lib="/proj/cds.lib", run_dir="/r/cdl", netlist_name="src.cdl",
        ))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["cds_lib"], "/proj/cds.lib")
        self.assertEqual(result.value["netlist_path"], "/r/cdl/src.cdl")
        self.assertFalse(any(c.startswith("SKILL:") for c in middle.commands))

    def test_export_cdl_requires_resolvable_cds_lib(self):
        result = Package(FakeMiddle(ciw_cwd=None)).export_cdl(ExportCdlRequest(
            token=TOKEN, library="CMP_LIB", cell="inv2",
        ))
        self.assertFalse(result.ok)
        self.assertIn("cds.lib not resolved", result.error or "")

    def test_export_cdl_missing_cds_lib_fails(self):
        result = Package(FakeMiddle(cds_lib_exists=False)).export_cdl(
            ExportCdlRequest(token=TOKEN, library="CMP_LIB", cell="inv2"))
        self.assertFalse(result.ok)
        self.assertIn("cds.lib not found", result.error or "")

    def test_export_cdl_si_failure_and_empty_netlist(self):
        failed = Package(FakeMiddle(si_rc=1)).export_cdl(ExportCdlRequest(
            token=TOKEN, library="CMP_LIB", cell="inv2"))
        self.assertFalse(failed.ok)
        self.assertIn("si netlisting failed", failed.error or "")
        self.assertIn("rc=1", failed.error or "")

        empty = Package(FakeMiddle(netlist_bytes=0)).export_cdl(ExportCdlRequest(
            token=TOKEN, library="CMP_LIB", cell="inv2"))
        self.assertFalse(empty.ok)
        self.assertIn("bytes=0", empty.error or "")

    def test_export_cdl_upload_and_prepare_failures(self):
        broken = Package(FakeMiddle(upload_rc=1)).export_cdl(ExportCdlRequest(
            token=TOKEN, library="CMP_LIB", cell="inv2"))
        self.assertFalse(broken.ok)
        self.assertIn("si.env/.simrc upload failed", broken.error or "")

    def test_export_cdl_request_validation(self):
        with self.assertRaises(ValueError):
            ExportCdlRequest(token=TOKEN, library="CMP_LIB", cell="inv2",
                             netlist_name="a/b.cdl")
        with self.assertRaises(ValueError):
            ExportCdlRequest(token=TOKEN, library="", cell="inv2")

    def test_pex_requires_lvs_run_dir(self):
        result = Package(FakeMiddle()).pex(RunRequest(
            token=TOKEN, gds="/x/ctle.gds", top="ctle",
            deck="/x/calibre.rcx", cdl="/x/ctle.cdl",
        ))
        self.assertFalse(result.ok)
        self.assertIn("lvs_run_dir", result.error or "")

    def test_run_requires_command_role_root(self):
        result = Package(FakeMiddle(root=None)).drc(RunRequest(
            token=TOKEN, gds="/x/lay.gds", top="lay_e2e", deck=DECK,
        ))
        self.assertFalse(result.ok)
        self.assertIn("command role root unavailable", result.error)

    def test_run_upload_deck_failure(self):
        result = Package(FakeMiddle(upload_rc=1)).drc(RunRequest(
            token=TOKEN, gds="/x/lay.gds", top="lay_e2e", deck=DECK,
        ))
        self.assertFalse(result.ok)
        self.assertIn("upload deck failed", result.error)

    def test_status_completed(self):
        middle = FakeMiddle(completed=True)
        result = Package(middle).status(StatusRequest(
            token=TOKEN, job_id="drc_lay_e2e", kind="drc",
        ))
        self.assertTrue(result.ok)
        self.assertEqual(result.value["status"], "completed")

    def test_status_snapshot_failure(self):
        result = Package(FakeMiddle(snapshot_rc=1)).status(StatusRequest(
            token=TOKEN, job_id="drc_lay_e2e", kind="drc",
        ))
        self.assertFalse(result.ok)
        self.assertIn("cannot read job state", result.error)

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

    def test_export_download_failure(self):
        with tempfile.TemporaryDirectory(prefix="vb-cal-") as tmp:
            result = Package(FakeMiddle(download_rc=1)).export(ExportRequest(
                token=TOKEN, job_id="drc_lay_e2e", kind="drc",
                items=("summary",), local_dir=str(Path(tmp) / "out"),
            ))
            self.assertFalse(result.ok)
            self.assertIn("nothing downloaded", result.error or "")

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

