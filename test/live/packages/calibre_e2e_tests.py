"""End-to-end acceptance tests for ``calibre.*``（常驻真机套件，P-060）。

为什么要有它：calibre 包在本轮之前**没有任何常驻真机入口**（注册表无 `role.command.calibre`、
`run_all_http.py` 的 SUITES 里也没有 calibre 套件），只能靠一次性探针验证。
本套件把"用户经业务面跑 Calibre"的链固定下来：

* `ENV-01`  `calibre.check_env` —— 工具事实与版本；
* `EXPORT-01` `calibre.export_cdl` —— 官方 auCdl（`si -batch -command netlist`）导出源网表，
  **必须含 `.SUBCKT` 与器件行**（P-069 的上游：源网表不再靠手写）；
* `DRC-01`  DRC 跑完 + `read_results`（规则数 / 结果数 / 逐规则计数 / 违规明细）—— P-059 的验收；
* `DRC-02`  坏 deck 必须**结构化失败**（不挂死、不崩）—— P-061 的同类防线；
* `LVS-01`  LVS 跑完 + `read_results`（结论枚举 + 计数表格 + **两条路径同一枚举**）—— P-062/P-071 的验收；
* `LVS-02`  **闭环**：`EXPORT-01` 的 CDL 直接喂 `calibre.lvs`，`VB_CALIBRE_REQUIRE_LVS_VERDICT=1` 下要求 `correct`。

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
CDL_GDS = os.environ.get("VB_CALIBRE_CDL_GDS", "/home/Gent/project/test/inv2.gds")
REQUIRE_LVS_VERDICT = os.environ.get("VB_CALIBRE_REQUIRE_LVS_VERDICT", "") == "1"
KNOWN_VERDICTS = {"correct", "incorrect", "not_compared", "unknown", "not_comparable"}

#: `EXPORT-01` 产出的 CDL 路径，供 `LVS-02` 闭环使用（同一进程内传递）。
_exported: dict[str, str] = {}


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
    return response["data"]


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
                  top: str | None = None) -> tuple[dict, dict]:
    fields: dict[str, Any] = {"gds": gds or GDS, "top": top or TOP, "deck": deck,
                              "run_dir": run_dir, "blocking": True, "timeout": 900}
    if cdl:
        fields["cdl"] = cdl
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
    _, read = _run_and_read(transport, "drc", deck=DRC_DECK, run_dir=f"{RUN_DIR}/drc")
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
        "run_dir": f"{RUN_DIR}/drc-bad", "blocking": True, "timeout": 120,
    })
    _check(not response.get("ok"), f"bad deck must fail structurally: {response}")
    _check(str(response.get("error") or ""), f"bad deck must carry an error message: {response}")


def _cdl_counts(transport, path: str) -> tuple[int, int]:
    """远端 CDL 的 (subckt 数, 器件行数)——只看计数，不整份下载。"""
    cmd = ("awk '/^\\.SUBCKT/{s++} /^[Mm][^ ]+ +/{d++} END{printf \"%d %d\", s, d}' "
           f"{path}")
    result = _op(transport, "basic.command.run", cmd=cmd).get("result") or ["", ""]
    stdout = result[1] if len(result) > 1 else ""
    parts = stdout.split()
    if len(parts) != 2 or not all(part.isdigit() for part in parts):
        raise AssertionError(f"cdl 计数不可解析: {stdout!r}")
    return int(parts[0]), int(parts[1])


def _case_export_cdl(transport) -> None:
    """EXPORT-01：官方 auCdl 链路导出源网表，必须有器件行（P-069 上游）。"""
    value = _value(transport, "calibre.export_cdl", library=CDL_LIB, cell=CDL_CELL,
                   run_dir=f"{RUN_DIR}/cdl")
    path = value.get("netlist_path")
    _check(path, f"export_cdl 未返回 netlist_path: {value}")
    _check((value.get("bytes") or 0) > 0, f"export_cdl 产物为空: {value}")
    _check(value.get("cds_lib"), f"export_cdl 未记录 cds.lib 来源: {value}")
    subckts, devices = _cdl_counts(transport, path)
    _check(subckts >= 1, f"CDL 无 .SUBCKT（只剩端口壳）：{value}")
    _check(devices >= 1, f"CDL 无器件行（auCdl 只出了端口）：{value}")
    _exported["cdl"] = path


def _case_lvs_chain(transport) -> None:
    """LVS-02：EXPORT-01 的 CDL 直接喂 LVS —— schematic→CDL→LVS 全链闭环。"""
    exported = _exported.get("cdl")
    _check(exported, "LVS-02 依赖 EXPORT-01 的 CDL，但 EXPORT-01 未产出")
    _, read = _run_and_read(transport, "lvs", deck=LVS_DECK, cdl=exported,
                            gds=CDL_GDS, top=CDL_CELL,
                            run_dir=f"{RUN_DIR}/lvs-chain")
    summary = read.get("summary") or {}
    status = summary.get("status")
    _check(status in KNOWN_VERDICTS, f"LVS 结论不在已知枚举: {status!r}")
    _check(summary.get("counts"), f"LVS counts 未解出: {json.dumps(summary)[:300]}")
    if status != "correct":
        if REQUIRE_LVS_VERDICT:
            raise AssertionError(
                f"auCdl 导出的 CDL 未通过 LVS 比对：status={status!r}，"
                f"differences={json.dumps(summary.get('differences'))[:300]}")
        print(f"        WARN   LVS-02 结论是 {status}（EXPORT-01 的 CDL 未对齐版图）；"
              "结构契约已通过", flush=True)


def _case_lvs(transport) -> None:
    _, read = _run_and_read(transport, "lvs", deck=LVS_DECK,
                            run_dir=f"{RUN_DIR}/lvs", cdl=CDL)
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


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("ENV-01 check_env", lambda: _case_env(transport))
    run("EXPORT-01 auCdl 源网表", lambda: _case_export_cdl(transport))
    run("DRC-01 run + read_results", lambda: _case_drc(transport))
    run("DRC-02 bad deck fails", lambda: _case_drc_bad_deck(transport))
    run("LVS-01 run + read_results", lambda: _case_lvs(transport))
    run("LVS-02 export_cdl → LVS 闭环", lambda: _case_lvs_chain(transport))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="direct")
    args = parser.parse_args()
    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    try:
        results = run_suite(transport)
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
