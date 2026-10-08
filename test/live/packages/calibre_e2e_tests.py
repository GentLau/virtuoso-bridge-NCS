# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 21:45
# 依赖: 常驻 vblog（业务面 8127, token vb-vblog）+ wsl-gent 上的 Calibre/PDK 环境
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（真机靶机指纹/业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时，正文有一行注释说明。
"""End-to-end acceptance tests for ``calibre.*``（常驻真机套件，P-060）。

为什么要有它：calibre 包在本轮之前**没有任何常驻真机入口**（注册表无 `role.command.calibre`、
`run_all_http.py` 的 SUITES 里也没有 calibre 套件），只能靠一次性探针验证。
本套件把"用户经业务面跑 Calibre"的链固定下来：

* `ENV-01`  `calibre.check_env` —— 工具事实与版本；
* `LVS-02` `calibre.lvs(source.kind=schematic)` —— 官方 auCdl 在 LVS run dir 内现产源网表，
  `emit_cdl=true` 回传 `cdl_path`，且 **必须含 `.SUBCKT` 与器件行**；
* `DRC-01`  DRC 跑完 + `read_results`（规则数 / 结果数 / 逐规则计数 / 违规明细）—— P-059 的验收；
* `DRC-02`  坏 deck 必须**结构化失败**（不挂死、不崩）—— P-061 的同类防线；
* `LVS-01`  LVS 跑完 + `read_results`（结论枚举 + 计数表格 + **两条路径同一枚举**）—— P-062/P-071 的验收；
* `LVS-03`  **闭环**：复用 LVS-02 的内产 CDL，以 `source.kind=cdl` 再跑一次 LVS。
* `PARAM-01` **带参数**（不改 deck、不走 GUI）：`params` 内联 / `.runset` 文件原位改写 deck；未知键结构化失败。
* `EXPORT-01` `calibre.export`（spec §4.5）：`items=[summary, netlist]` 值级读回 ——
  `value.local_dir` 按请求生效、`downloaded[].bytes` 与实际一致、`summary` 本地文件 sha256 == 远端、
  `netlist`（svdb 目录）确实落地；`EXPORT-02` 负例：未知 item 请求层拒绝且**零落盘**。
* `LVS-SRC-XOR` 负例：`source` 与 `cdl` 互斥（spec §4.3 只保留 `source` 口径，旧 `cdl=` 仅兼容）。

`LVS-01` 的口径：默认只断言**结构契约**（status 属已知枚举、`log_counters.lvs_status` 与
`summary.status` 一致、counts 已解出），并在 `status == "not_compared"` 时打印 WARN 指向 **P-069**
（无 PDK 可用的 CDL 源）。**不假装 LVS 已跑通**；等 P-069 修好后用
`VB_CALIBRE_REQUIRE_LVS_VERDICT=1` 打开强断言（那时 `not_compared` 会直接判 FAIL）。

Run with ``--transport direct`` (in-process dispatch) or ``--transport http`` (the business face).
环境变量（都有默认值，指向 wsl-gent 上的 S11 反相器实例）：
``VB_CALIBRE_GDS`` / ``VB_CALIBRE_TOP`` / ``VB_CALIBRE_DRC_DECK`` / ``VB_CALIBRE_LVS_DECK`` /
``VB_CALIBRE_CDL`` / ``VB_CALIBRE_RUN_DIR`` / ``VB_CALIBRE_API`` / ``VB_CALIBRE_TOKEN``。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = os.environ.get("VB_CALIBRE_API", "http://127.0.0.1:8127/api/operation")
TOKEN = os.environ.get("VB_CALIBRE_TOKEN", "vb-vblog")
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"

GDS = os.environ.get("VB_CALIBRE_GDS", "/home/Gent/project/vblog/s11_inv/s11/inv.gds")
TOP = os.environ.get("VB_CALIBRE_TOP", "inv")
PDK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre"
DRC_DECK = os.environ.get("VB_CALIBRE_DRC_DECK", f"{PDK}/drc/calibre.drc")
LVS_DECK = os.environ.get("VB_CALIBRE_LVS_DECK", f"{PDK}/lvs/calibre.lvs")
CDL = os.environ.get("VB_CALIBRE_CDL", "/home/Gent/.virtuoso-bridge/calprobe/command/calibre/inv.cdl")
RUN_DIR = os.environ.get("VB_CALIBRE_RUN_DIR", "/home/Gent/project/vblog/calibre-e2e")
CDL_LIB = os.environ.get("VB_CALIBRE_CDL_LIB", "CMP_LIB")
CDL_CELL = os.environ.get("VB_CALIBRE_CDL_CELL", "inv2")
# round9：每个 job 的 run_dir 带本轮唯一后缀，避免复用陈旧目录导致
# "job already running" / `process_gone_without_report` 误判（2026-09-29 实测）
STAMP = time.strftime("%H%M%S")
CDL_GDS = os.environ.get("VB_CALIBRE_CDL_GDS", "/home/Gent/project/test/inv2.gds")
REQUIRE_LVS_VERDICT = os.environ.get("VB_CALIBRE_REQUIRE_LVS_VERDICT", "") == "1"
KNOWN_VERDICTS = {"correct", "incorrect", "not_compared", "unknown", "not_comparable"}

#: spec `12-calibre.md` §8 的 LVS 验收行用的是 `{match, incorrect}`；实现口径是
#: `{correct, incorrect}`（P-071 统一过枚举）—— 这里两者都收，并把实测值写进失败信息。
STRONG_VERDICTS = {"correct", "incorrect", "match"}

#: spec §8 LVS 行指定的验收输入（ctle 工程）。
CTLE_GDS = os.environ.get("VB_CALIBRE_CTLE_GDS", "/home/Gent/project/test/ctle.gds")
CTLE_CDL = os.environ.get("VB_CALIBRE_CTLE_CDL", "/home/Gent/project/test/ctle.cdl")
CTLE_TOP = os.environ.get("VB_CALIBRE_CTLE_TOP", "ctle")

#: 同一进程内传递：LVS-02 产出的 CDL 路径 / job_id / run_dir，供 LVS-03、PARAM-01、SET-01、EXPORT-01 复用。
_exported: dict[str, str] = {}

#: EXPORT-01 的客户端落地目录（证据目录下的本轮唯一子目录；测完保留供审计）。
EXPORT_DIR = ROOT / "test" / "artifacts" / "evidence" / "round9" / f"calibre-export-{STAMP}"


class HttpTransport:
    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=1800) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


class DirectTransport:
    def __init__(self) -> None:
        from common.paths import init_work_dir
        from server import dispatch
        from server.api_server import register_packages
        from transport.middle import BusinessServer

        init_work_dir(str(WORK_DIR))
        register_packages()
        self.dispatch = dispatch
        self.middle = BusinessServer()

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, body = self.dispatch.dispatch(self.middle, payload)
        if status not in (200, 400):
            raise AssertionError(f"dispatch status {status}: {body}")
        return body


def _op(transport, operation: str, **fields: Any) -> Any:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    return response


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    value = _op(transport, operation, **fields).get("value")
    if not isinstance(value, dict):
        raise AssertionError(f"{operation} returned no value dict")
    return value


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _run_and_read(transport, kind: str, *, deck: str, run_dir: str,
                  cdl: str | None = None, gds: str | None = None,
                  top: str | None = None, source: dict | None = None,
                  emit_cdl: bool = False) -> tuple[dict, dict]:
    fields: dict[str, Any] = {"gds": gds or GDS, "top": top or TOP, "deck": deck,
                              "run_dir": run_dir, "blocking": True, "timeout": 900}
    if cdl:
        fields["cdl"] = cdl
    if source is not None:
        fields["source"] = source
    if emit_cdl:
        fields["emit_cdl"] = True
    job = _value(transport, f"calibre.{kind}", **fields)
    job_id, effective_dir = job.get("job_id"), job.get("run_dir") or run_dir
    _check(job.get("status") == "completed", f"{kind} did not complete: {job.get('status')}")
    read = _value(transport, "calibre.read_results", job_id=job_id,
                  run_dir=effective_dir, kind=kind, limit=20)
    return job, read


def _case_env(transport) -> None:
    value = _value(transport, "calibre.check_env")
    _check(value.get("calibre_path") or value.get("bin"),
           f"calibre 路径缺失（calibre_path/bin）: {value}")
    _check(value.get("version"), f"calibre version missing: {value}")


def _case_drc(transport) -> None:
    _, read = _run_and_read(transport, "drc", deck=DRC_DECK, run_dir=f"{RUN_DIR}/drc-{STAMP}")
    summary = read.get("summary") or {}
    _check((summary.get("rules_checked") or 0) > 0, f"rules_checked missing: {summary}")
    _check((summary.get("total_results") or 0) >= 0, f"total_results missing: {summary}")
    by_rule = summary.get("by_rule") or {}
    _check(by_rule, f"by_rule is empty（P-059 回归）: {json.dumps(summary)[:300]}")
    offenders = summary.get("first_offenders")
    _check(isinstance(offenders, list), f"first_offenders missing: {summary}")
    if (summary.get("total_results") or 0) > 0:
        _check(offenders, f"有违规但 first_offenders 为空（af8e1e0 回归）: {summary}")
        for item in offenders[:3]:
            _check(item.get("rule") and item.get("cell"), f"offender 结构不完整: {item}")
    counters = read.get("log_counters") or {}
    _check(counters.get("rules_checked") == summary.get("rules_checked"),
           f"report/log rules_checked 不一致: {counters} vs {summary}")


def _case_drc_bad_deck(transport) -> None:
    response = transport.call({
        "operation": "calibre.drc", "token": TOKEN,
        "gds": GDS, "top": TOP, "deck": f"{RUN_DIR}/does-not-exist.drc",
        "run_dir": f"{RUN_DIR}/drc-bad-{STAMP}", "blocking": True, "timeout": 120,
    })
    _check(not response.get("ok"), f"bad deck must fail structurally: {response}")
    _check(str(response.get("error") or ""), f"bad deck must carry an error message: {response}")


def _cdl_counts(transport, path: str) -> tuple[int, int]:
    """远端 CDL 的 (subckt 数, 器件行数)——只看计数，不整份下载。"""
    cmd = ("awk '/^\\.SUBCKT/{s++} /^[Mm][^ ]+ +/{d++} END{printf \"%d %d\", s, d}' "
           f"{path}")
    result = _op(transport, "basic.command.run", cmd=cmd).get("result") or {}
    stdout = str(result.get("stdout") or "")
    parts = stdout.split()
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise AssertionError(f"cdl 计数不可解析: {stdout!r}")
    return int(parts[0]), int(parts[1])


def _case_lvs_source_schematic(transport) -> None:
    """LVS-02：`source.kind=schematic` 在 LVS run dir 内走官方 auCdl。"""
    job, read = _run_and_read(
        transport, "lvs", deck=LVS_DECK, gds=CDL_GDS, top=CDL_CELL,
        source={"kind": "schematic", "library": CDL_LIB, "cell": CDL_CELL,
                "view": "schematic"},
        emit_cdl=True, run_dir=f"{RUN_DIR}/lvs-source-sch-{STAMP}",
    )
    path = job.get("cdl_path")
    _check(path, f"LVS source.schematic 未返回 cdl_path: {job}")
    subckts, devices = _cdl_counts(transport, path)
    _check(subckts >= 1, f"CDL 无 .SUBCKT（只剩端口壳）：{job}")
    _check(devices >= 1, f"CDL 无器件行（auCdl 只出了端口）：{job}")
    _exported["cdl"] = path
    _exported["job_id"] = str(job.get("job_id") or "")
    _exported["run_dir"] = str(job.get("run_dir") or "")
    summary = read.get("summary") or {}
    status = summary.get("status")
    _check(status in KNOWN_VERDICTS, f"LVS 结论不在已知枚举: {status!r}")
    _check(summary.get("counts"), f"LVS counts 未解出: {json.dumps(summary)[:300]}")
    if status != "correct":
        if REQUIRE_LVS_VERDICT:
            raise AssertionError(
                f"auCdl 导出的 CDL 未通过 LVS 比对：status={status!r}，"
                f"differences={json.dumps(summary.get('differences'))[:300]}")
        print(f"        WARN   LVS-02 结论是 {status}（source.schematic 的 CDL 未对齐版图）；"
              "结构契约已通过", flush=True)


def _case_lvs_source_cdl(transport) -> None:
    """LVS-03：复用 LVS-02 内产 CDL，验证 `source.kind=cdl` 直接入口。"""
    exported = _exported.get("cdl")
    _check(exported, "LVS-03 依赖 LVS-02 的内产 CDL，但 LVS-02 未产出")
    _, read = _run_and_read(
        transport, "lvs", deck=LVS_DECK, gds=CDL_GDS, top=CDL_CELL,
        source={"kind": "cdl", "path": exported},
        run_dir=f"{RUN_DIR}/lvs-source-cdl-{STAMP}",
    )
    summary = read.get("summary") or {}
    status = summary.get("status")
    _check(status in KNOWN_VERDICTS, f"LVS 结论不在已知枚举: {status!r}")
    _check(summary.get("counts"), f"LVS counts 未解出: {json.dumps(summary)[:300]}")
    if status != "correct" and REQUIRE_LVS_VERDICT:
        raise AssertionError(
            f"source.kind=cdl 未通过 LVS 比对：status={status!r}，"
            f"differences={json.dumps(summary.get('differences'))[:300]}")


def _case_params(transport) -> None:
    """PARAM-01：无 set 的取数口——SVRF 语句头 → deck 原位改写（参数合并仍由 Calibre 自己做）。"""
    exported = _exported.get("cdl")
    _check(exported, "PARAM-01 依赖 EXPORT-01 的 CDL，但 EXPORT-01 未产出")
    params = {"LAYOUT PATH": f'LAYOUT PATH "{CDL_GDS}"',
              "LAYOUT PRIMARY": f'LAYOUT PRIMARY "{CDL_CELL}"',
              "SOURCE PATH": f'SOURCE PATH "{exported}"',
              "SOURCE PRIMARY": f'SOURCE PRIMARY "{CDL_CELL}"'}
    job = _value(transport, "calibre.lvs", deck=LVS_DECK, params=params,
                 run_dir=f"{RUN_DIR}/lvs-params-{STAMP}", blocking=True, timeout=900)
    changes = job.get("deck_changes") or []
    _check(any("LAYOUT PRIMARY" in item for item in changes),
           f"参数没落进 deck（deck_changes={changes}）")
    read = _value(transport, "calibre.read_results", kind="lvs",
                  run_dir=job.get("run_dir"), limit=20)
    status = (read.get("summary") or {}).get("status")
    _check(status in KNOWN_VERDICTS, f"带参数的 LVS 结论不在已知枚举: {status!r}")
    if status != "correct" and REQUIRE_LVS_VERDICT:
        raise AssertionError(f"带参数的 LVS 未通过比对: status={status!r}")

    # 不做 runset 键映射：camelCase 键必须失败并指路官方入口（runset=）
    bad = transport.call({"operation": "calibre.lvs", "token": TOKEN, "deck": LVS_DECK,
                          "gds": CDL_GDS, "top": CDL_CELL, "cdl": exported,
                          "params": {"lvsLayoutPrimary": CDL_CELL},
                          "run_dir": f"{RUN_DIR}/lvs-bad-param-{STAMP}"})
    _check(not bad.get("ok"), f"runset 键不允许出现在 params: {str(bad)[:200]}")
    _check("SVRF 语句头" in str(bad.get("error") or ""), f"错误要指路: {bad}")


def _case_set_file(transport) -> None:
    """SET-01：现场形态的 `.lvs` set 作为**唯一输入**（deck/输入/选项都在 set 里）。"""
    exported = _exported.get("cdl")
    _check(exported, "SET-01 依赖 LVS-02 的内产 CDL，但 LVS-02 未产出")
    run_dir = f"{RUN_DIR}/lvs-set-{STAMP}"
    lines = [
        f"*lvsRulesFile: {LVS_DECK}",
        f"*lvsRunDir: {run_dir}",
        f"*lvsLayoutPrimary: {CDL_CELL}",
        f"*lvsLayoutPaths: {CDL_GDS}",
        "*lvsLayoutLibrary: CMP_LIB",
        "*lvsLayoutView: layout",
        "*lvsLayoutGetFromViewer: 1",
        f"*lvsSourcePath: {exported}",
        f"*lvsSourcePrimary: {CDL_CELL}",
        "*lvsSourceView: schematic",
        "*lvsSpiceFile: inv2.sp",
        "*lvsUseHCells: 0",
        "*lvsPowerNames: VDD",
        "*lvsGroundNames: VSS",
        "*lvsRecognizeGates: NONE",
        "*lvsIncludeCmdsType: SVRF",
        "*lvsSVRFCmds: {LVS FILTER C(CP) OPEN} {}",
        "*lvsReportFile: inv2.lvs.report",
        "*lvsReportMaximumCount: 1000",
        "*lvsReportOptions: S",
        "*lvsAbortOnSupplyError: 0",
        "*lvsSVDBxcal: 1",
        "*cmnRunMT: 1",
        "*cmnPromptSaveRunset: 0",
    ]
    # TB 自己的临时目录（不写常驻 env 目录；规范 §6「尽可能只使用三处」）。
    tmp = ROOT / "test" / "artifacts" / "tmp" / f"calibre-e2e-{STAMP}"
    tmp.mkdir(parents=True, exist_ok=True)
    local = tmp / "e2e-lvs.lvs"
    local.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    remote = f"{RUN_DIR}/e2e-lvs-{STAMP}.lvs"
    _op(transport, "basic.file.upload", local_path=str(local), remote_path=remote, timeout=120)

    job = _value(transport, "calibre.lvs", runset=remote, blocking=True, timeout=900)
    # 官方批处理入口：参数合并全由 Calibre 做，我们只发起 + 分析
    _check(job.get("mode") == "official-batch", f"不是官方批处理模式: {job.get('mode')}")
    _check(job.get("run_dir") == run_dir, f"产物目录应取 set 的 lvsRunDir: {job.get('run_dir')}")
    probe = _op(transport, "basic.command.run",
                cmd=f"ls {run_dir}/_calibre.lvs_ >/dev/null 2>&1 && echo ctrl_ok; "
                    f"ls {run_dir}/inv2.lvs.report >/dev/null 2>&1 && echo report_ok")
    probe_out = str((probe.get("result") or {}).get("stdout") or "")
    _check("ctrl_ok" in probe_out, f"缺 Calibre 生成的 control file：{probe_out!r}")
    _check("report_ok" in probe_out, f"缺 set 指定名字的报告：{probe_out!r}")

    read = _value(transport, "calibre.read_results", kind="lvs", run_dir=run_dir, limit=20)
    _check(read.get("report_used"), f"set 改了报告名后 read_results 找不到报告: {read}")
    status = (read.get("summary") or {}).get("status")
    _check(status in KNOWN_VERDICTS, f"set 驱动的 LVS 结论不在已知枚举: {status!r}")
    if status != "correct":
        if REQUIRE_LVS_VERDICT:
            raise AssertionError(f"set 驱动的 LVS 未通过比对: status={status!r}")
        print(f"        WARN   SET-01 结论是 {status}", flush=True)


def _case_lvs_source_legacy_mutex(transport) -> None:
    """LVS-SRC-XOR：`source` 与旧 `cdl=` 互斥（请求层拒绝，不发起任何远程动作）。"""
    response = transport.call({
        "operation": "calibre.lvs", "token": TOKEN, "deck": LVS_DECK,
        "gds": CDL_GDS, "top": CDL_CELL,
        "source": {"kind": "cdl", "path": CDL}, "cdl": CDL,
        "run_dir": f"{RUN_DIR}/lvs-xor-{STAMP}",
    })
    _check(not response.get("ok"), f"source+cdl 必须被拒绝: {str(response)[:240]}")
    _check("mutually exclusive" in str(response.get("error") or ""),
           f"拒绝原因应点明互斥: {response}")


def _case_lvs_ctle(transport) -> None:
    """LVS-CTLE：spec `12-calibre.md` §8 的 LVS 验收行 —— `ctle.gds` + `source.kind=cdl`。

    要求：`status=completed`、`summary.status ∈ {match/incorrect}`（实现口径 `correct`）、
    产物含 `svdb/*.phdb`。与 LVS-01/02/03（inv2 工程）是不同设计、不同源网表。
    """
    run_dir = f"{RUN_DIR}/lvs-ctle-{STAMP}"
    job, read = _run_and_read(
        transport, "lvs", deck=LVS_DECK, gds=CTLE_GDS, top=CTLE_TOP,
        source={"kind": "cdl", "path": CTLE_CDL}, run_dir=run_dir,
    )
    summary = read.get("summary") or {}
    status = str(summary.get("status") or "")
    _check(status in STRONG_VERDICTS,
           f"spec §8 要求 LVS 给结论（match/incorrect；实现口径 correct/incorrect），"
           f"实测 {status!r}: {json.dumps(summary, ensure_ascii=False)[:300]}")
    _check(summary.get("counts"), f"LVS counts 未解出: {json.dumps(summary)[:300]}")
    effective = str(job.get("run_dir") or run_dir)
    # 注意：`svdb/<cell>.phdb` 是**目录**（Calibre svdb 结构：内含 db/ 与 hdb*.dat）；
    # 断言用 `ls -d` 命中条目本身，并进一步要求 phdb 里的 `db` 子目录存在。
    probe = _op(transport, "basic.command.run",
                cmd=f"ls -d {effective}/svdb/*.phdb 2>/dev/null | head -3")
    out = str((probe.get("result") or {}).get("stdout") or "")
    _check(".phdb" in out, f"spec §8 要求产物 svdb/*.phdb，实测: {out!r}")
    probe_db = _op(transport, "basic.command.run",
                   cmd=f"ls -d {effective}/svdb/*.phdb/db 2>/dev/null | head -1")
    out_db = str((probe_db.get("result") or {}).get("stdout") or "")
    _check(".phdb/db" in out_db, f"svdb phdb 结构不完整（缺 db/ 子目录）: {out_db!r}")


def _remote_sha256(transport, path: str) -> str:
    result = _op(transport, "basic.command.run",
                 cmd=f"sha256sum {path}").get("result") or {}
    out = str(result.get("stdout") or "").split()
    _check(out and len(out[0]) == 64, f"远端 sha256 不可用: {result}")
    return out[0]


def _local_sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def _case_export(transport) -> None:
    """EXPORT-01：`calibre.export` 的 `local_dir` 与下载结果值级读回（spec §4.5）。"""
    job_id = _exported.get("job_id")
    run_dir = _exported.get("run_dir")
    _check(job_id and run_dir, "EXPORT-01 依赖 LVS-02 的 job_id/run_dir，但 LVS-02 未产出")
    # 注意：本 TB 的 job 用的是**自带 run_dir**（`.../calibre-e2e/lvs-source-sch-*`），
    # `job_id` 只有在默认布局 `<role root>/calibre/<job_id>` 下才解析得到 → 这里显式给 run_dir
    # （spec §4.5：`job_id`/`run_dir` 二者其一）。
    value = _value(transport, "calibre.export", run_dir=run_dir,
                   items=["summary", "netlist"], local_dir=str(EXPORT_DIR), timeout=300)
    _check(value.get("run_dir") == run_dir,
           f"export 必须落在同一 run_dir（值级）: {value.get('run_dir')!r} != {run_dir!r}")
    _check(value.get("local_dir") == str(EXPORT_DIR),
           f"local_dir 未按请求生效（值级）: {value.get('local_dir')!r}")
    downloaded = value.get("downloaded") or []
    summaries = [item for item in downloaded if item.get("item") == "summary"]
    netlists = [item for item in downloaded if item.get("item") == "netlist"]
    _check(summaries, f"summary（lvs.rep 等）未下载: {json.dumps(downloaded)[:300]}")
    for entry in summaries:
        local = Path(str(entry.get("local")))
        _check(local.is_file() and local.stat().st_size > 0,
               f"summary 本地文件缺失/为空: {entry}")
        _check(entry.get("bytes") == local.stat().st_size,
               f"bytes 字段与实际文件大小不一致: {entry} vs {local.stat().st_size}")
        remote = f"{run_dir}/{entry.get('remote')}"
        _check(_local_sha256(local) == _remote_sha256(transport, remote),
               f"summary 内容与远端不一致（sha256）: {remote}")
    _check(netlists, f"netlist（svdb 目录）未下载: {json.dumps(downloaded)[:300]}")
    for entry in netlists:
        local = Path(str(entry.get("local")))
        _check(local.is_dir(), f"netlist 本地应是目录: {entry}")
        files = [p for p in local.rglob("*") if p.is_file()]
        _check(files, f"netlist 目录里没有文件: {entry}")


def _case_export_negative(transport) -> None:
    """EXPORT-02：未知 item 请求层拒绝，且**零落盘**（连目标目录都不创建）。"""
    target = EXPORT_DIR / "negative"
    response = transport.call({
        "operation": "calibre.export", "token": TOKEN,
        "job_id": _exported.get("job_id") or "no-such-job",
        "items": ["not_an_item"], "local_dir": str(target),
    })
    _check(not response.get("ok"), f"未知 item 必须被拒绝: {str(response)[:200]}")
    _check("unknown export item" in str(response.get("error") or ""),
           f"拒绝原因应点明 item: {response}")
    _check(not target.exists(), f"被拒绝的 export 不得落盘: {target}")


def _case_export_all_small(transport) -> None:
    """EXPORT-03：`items=["all_small"]` 展开为 summary/results_db/log（spec §4.5 枚举值）。"""
    run_dir = _exported.get("run_dir")
    _check(run_dir, "EXPORT-03 依赖 LVS-02 的 run_dir，但 LVS-02 未产出")
    target = EXPORT_DIR / "all_small"
    value = _value(transport, "calibre.export", run_dir=run_dir, items=["all_small"],
                   local_dir=str(target), timeout=300)
    downloaded = value.get("downloaded") or []
    _check(downloaded, f"all_small 什么都没下到: {value}")
    items = {str(entry.get("item")) for entry in downloaded}
    _check(items <= {"summary", "results_db", "log"},
           f"all_small 只应展开为 summary/results_db/log，实测 {sorted(items)}")
    _check("all_small" not in items, f"展开后不得留 all_small 字面量: {sorted(items)}")
    # 防空转：LVS run dir 里 summary（lvs.rep）与 log（lvs.log）都必须真下到；
    # 只下一个 summary 就"通过"不算覆盖（results_db 是 DRC 产物，LVS 目录可以没有）。
    _check({"summary", "log"} <= items,
           f"all_small 应至少展开出 summary+log，实测 {sorted(items)}")
    for entry in downloaded:
        local = Path(str(entry.get("local")))
        _check(local.exists(), f"all_small 条目未落地: {entry}")


def _case_export_pdb_dir(transport) -> None:
    """EXPORT-04（P-117 记录）：spec §4.5 的 `items` 列了 `pdb_dir`，实现未提供。

    现状：请求层结构化拒绝 `unknown export item: pdb_dir`。
    **决策已定（2026-10-08，见卡片尾部）**：补实现，但只做「预留接口」——
    请求层接受 `pdb_dir`、预留语义结构化点名、且不影响同请求其它 item
    （`items=["summary","pdb_dir"]` 仍要下到 summary 且 sha256 一致）；PEX 真正恢复后再升级为
    pdb 目录的值级落地断言。

    → 本用例目前断言的是"实现未落地前的现状"。**哪天它变红（不再 400），就是设计已落地预留接口**，
    按卡片尾部的决策把这里改成预留语义断言即可。
    """
    run_dir = _exported.get("run_dir")
    _check(run_dir, "EXPORT-04 依赖 LVS-02 的 run_dir，但 LVS-02 未产出")
    response = transport.call({
        "operation": "calibre.export", "token": TOKEN, "run_dir": run_dir,
        "items": ["pdb_dir"], "local_dir": str(EXPORT_DIR / "pdb_dir"),
    })
    _check(not response.get("ok"), f"pdb_dir 现状应被拒绝（P-117）: {str(response)[:200]}")
    _check("unknown export item: pdb_dir" in str(response.get("error") or ""),
           f"拒绝原因应点名 pdb_dir（P-117）: {response}")
    _check(not (EXPORT_DIR / "pdb_dir").exists(), "被拒绝的 export 不得落盘")


def _case_lvs(transport) -> None:
    _, read = _run_and_read(transport, "lvs", deck=LVS_DECK,
                            run_dir=f"{RUN_DIR}/lvs-{STAMP}",
                            source={"kind": "cdl", "path": CDL})
    summary = read.get("summary") or {}
    counters = read.get("log_counters") or {}
    status = summary.get("status")
    _check(status in KNOWN_VERDICTS, f"LVS status 不在已知枚举: {status!r}（P-071 回归）")
    _check(counters.get("lvs_status") == status,
           f"报告路径与日志路径枚举不一致: {status!r} vs {counters.get('lvs_status')!r}（P-071 回归）")
    _check(summary.get("counts"), f"LVS counts 未解出: {json.dumps(summary)[:300]}（P-062 回归）")
    if status == "not_compared":
        if REQUIRE_LVS_VERDICT:
            raise AssertionError(
                "LVS 只到 not_compared：缺 PDK 可用的 CDL 源（P-069），"
                "VB_CALIBRE_REQUIRE_LVS_VERDICT=1 下判 FAIL")
        print("        WARN   LVS 结论是 not_compared（P-069：无 PDK 可用源网表）；"
              "结构契约已通过，未假装跑通", flush=True)


def run_suite(transport, only: str = "") -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
            print(f"PASS    {name}", flush=True)
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            raise

    cases: list[tuple[str, Callable[[], Any]]] = [
        ("ENV-01 check_env", lambda: _case_env(transport)),
        ("DRC-01 run + read_results", lambda: _case_drc(transport)),
        ("DRC-02 bad deck fails", lambda: _case_drc_bad_deck(transport)),
        ("LVS-01 run + read_results", lambda: _case_lvs(transport)),
        ("LVS-02 source.schematic auCdl 内产 + LVS", lambda: _case_lvs_source_schematic(transport)),
        ("LVS-03 source.cdl 复用内产 CDL", lambda: _case_lvs_source_cdl(transport)),
        # spec 12-calibre.md §8 的 LVS 验收行（ctle 工程，与上面 inv2 不同设计）
        ("LVS-CTLE spec §8 ctle.gds + source.cdl", lambda: _case_lvs_ctle(transport)),
        ("PARAM-01 无 set 取数口（SVRF 语句头）", lambda: _case_params(transport)),
        ("SET-01 只给 .lvs set（官方批处理）", lambda: _case_set_file(transport)),
        ("LVS-SRC-XOR source 与 cdl 互斥", lambda: _case_lvs_source_legacy_mutex(transport)),
        ("EXPORT-01 export local_dir + 下载值级读回", lambda: _case_export(transport)),
        ("EXPORT-02 未知 item 零落盘", lambda: _case_export_negative(transport)),
        ("EXPORT-03 all_small 展开值级", lambda: _case_export_all_small(transport)),
        ("EXPORT-04 pdb_dir 现状（P-117 记录）", lambda: _case_export_pdb_dir(transport)),
    ]
    for name, func in cases:
        if only and only.lower() not in name.lower():
            continue
        run(name, func)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="http",
                        help="direct=故障定位/覆盖率；真机判据必须 http")
    parser.add_argument("--only", default="",
                        help="只跑名字里含该子串的用例（增量复跑用；默认全跑）")
    parser.add_argument("--run-dir", default="",
                        help="给 EXPORT-* 用例喂一个已有 run_dir（只跑 EXPORT 时免跑 LVS 前置）")
    args = parser.parse_args()
    if args.run_dir:
        _exported.setdefault("run_dir", args.run_dir)
        _exported.setdefault("job_id", "adhoc")
    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    try:
        results = run_suite(transport, only=args.only)
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
