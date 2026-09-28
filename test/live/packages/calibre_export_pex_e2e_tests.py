# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 23:48
# 依赖: 无（PEX 用例会优先复用本机已有 LVS svdb；没有就自己造一个 LVS set 跑一遍）
# =======================================================================
"""补掉 calibre 剩下的两个**零调用 op**：`calibre.export` 与 `calibre.pex`。

* `EXP-01`：对一次真实 DRC 的 run_dir 调 `export(items=["all_small"])`，断言 summary/results_db/log
  至少各落一个本地文件、字节数 > 0（`_EXPORT_ITEMS` 的三类各验证一条）。
* `EXP-02`：`export(items=["summary"])` 对 LVS run_dir 生效，且返回的 `downloaded[].local` 真实存在。
* `PEX-01`：`calibre.pex(lvs_run_dir=<含 svdb 的 LVS 目录>)`——三阶段 xRC。若目录里没有 `svdb/`，
  本 TB 会先用 set 形态跑一次 LVS（`*lvsSVDBxcal: 1`）把 svdb 造出来；仍失败则如实记录错误（不假装跑通）。

六步流程（test/docs/写TB规范.md §1）：① 环境检查=ENV（deck/gds/bin 三件套）；②③ 基线=DRC 跑一次作为 export 输入；
④ 每个用例一次调用；⑤ 读回=本地文件 stat / downloaded 结构 / pex 三阶段日志；⑥ 不清理现场（run_dir 与导出物都留在 role root / 本机 tmp）。

环境变量与 `calibre_params_e2e_tests.py` 相同：`VB_CALIBRE_API/TOKEN/GDS/TOP/DRC_DECK/LVS_DECK/RUN_DIR/BIN`。
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
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
API = os.environ.get("VB_CALIBRE_API", "http://127.0.0.1:8127/api/operation")
TOKEN = os.environ.get("VB_CALIBRE_TOKEN", "vb-vblog")
PDK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre"
GDS = os.environ.get("VB_CALIBRE_GDS", "/home/Gent/project/vblog/s11_inv/s11/inv.gds")
TOP = os.environ.get("VB_CALIBRE_TOP", "inv")
DRC_DECK = os.environ.get("VB_CALIBRE_DRC_DECK", f"{PDK}/drc/calibre.drc")
LVS_DECK = os.environ.get("VB_CALIBRE_LVS_DECK", f"{PDK}/lvs/calibre.lvs")
RUN_DIR = os.environ.get("VB_CALIBRE_RUN_DIR", "/home/Gent/project/vblog/calibre-e2e")
CALIBRE_BIN = os.environ.get(
    "VB_CALIBRE_BIN", "/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre")
CDL = os.environ.get("VB_CALIBRE_CDL", "/home/Gent/.virtuoso-bridge/calprobe/command/calibre/inv.cdl")
RCX_DECK = os.environ.get("VB_CALIBRE_RCX_DECK", f"{PDK}/rcx/calibre.rcx")
SCRATCH = ROOT / "test" / "artifacts" / "tmp" / "calibre-export-pex"


class HttpTransport:
    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=2400) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return transport.call({"operation": operation, "token": TOKEN, **fields})


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    response = _op(transport, operation, **fields)
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    data = response.get("data") or {}
    return data.get("value") if data.get("value") is not None else data


def _command(transport, cmd: str, timeout: int = 120) -> str:
    response = _op(transport, "basic.command.run", cmd=cmd, timeout=timeout)
    if not response.get("ok"):
        raise AssertionError(f"command failed: {response.get('error')}")
    return str((((response.get("data") or {}).get("result")) or ["", ""])[1])


def _check(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    notes: list[str] = []

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        return value

    SCRATCH.mkdir(parents=True, exist_ok=True)
    stamp = int(time.time() * 1000)
    drc_dir = f"{RUN_DIR}/export-drc-{stamp}"
    lvs_dir = f"{RUN_DIR}/pex-lvs-{stamp}"

    def case_env() -> None:
        probe = _command(transport,
                         f"test -f {DRC_DECK} && echo drc_ok; test -f {LVS_DECK} && echo lvs_ok; "
                         f"test -x {CALIBRE_BIN} && echo bin_ok; test -f {GDS} && echo gds_ok")
        for token in ("drc_ok", "lvs_ok", "bin_ok", "gds_ok"):
            _check(token in probe, f"环境缺 {token}: {probe!r}")

    def case_drc_for_export() -> dict:
        value = _value(transport, "calibre.drc", gds=GDS, top=TOP, deck=DRC_DECK,
                       run_dir=drc_dir, calibre_bin=CALIBRE_BIN, hier=True, turbo=2,
                       job_id=f"export_drc_{stamp}", blocking=True, timeout=1800)
        _check(value.get("status") == "completed", f"export 的输入 DRC 未完成: {value.get('status')}")
        # 写回读：DRC 产物必须能被 read_results 解析（不做"跑完就算过"的弱判据）
        read = _value(transport, "calibre.read_results", kind="drc", run_dir=drc_dir,
                      limit=5, log_lines=5)
        _check(read.get("report_used"), f"DRC 报告不可定位: {read.get('artifacts')}")
        _check((read.get("summary") or {}).get("rules_checked"),
               f"DRC read_results 未解析出规则数: {read.get('summary')}")
        return value

    def case_export_all_small() -> None:
        local_dir = SCRATCH / f"all_small_{stamp}"
        value = _value(transport, "calibre.export", kind="drc", run_dir=drc_dir,
                       local_dir=str(local_dir), items=["all_small"], timeout=600)
        downloaded = value.get("downloaded") or []
        _check(downloaded, f"all_small 什么都没导出: {value}")
        items = {entry.get("item") for entry in downloaded}
        _check({"summary", "results_db", "log"} <= items,
               f"all_small 三类应各有一条（summary/results_db/log），实际 {items}")
        for entry in downloaded:
            local = Path(entry["local"])
            _check(local.is_file() and local.stat().st_size > 0,
                   f"导出的文件不存在或为空: {entry}")

    def case_export_summary_only() -> None:
        # 先造一个 LVS run_dir（deck 形态）；svdb 是否生成由 deck 决定，本用例只验证 summary 类导出
        value = _value(transport, "calibre.lvs", gds=GDS, top=TOP, cdl=CDL, deck=LVS_DECK,
                       run_dir=lvs_dir, calibre_bin=CALIBRE_BIN, hier=True, turbo=2,
                       job_id=f"pex_lvs_{stamp}", blocking=True, timeout=1800)
        status = value.get("status")
        # LVS 可能 not_compared（P-069），但 run_dir 与报告应已生成
        _check(status in ("completed", "failed"), f"LVS 未产生终态: {status}")
        local_dir = SCRATCH / f"summary_{stamp}"
        exported = _value(transport, "calibre.export", kind="lvs", run_dir=lvs_dir,
                          local_dir=str(local_dir), items=["summary"], timeout=600)
        downloaded = exported.get("downloaded") or []
        _check(downloaded, f"summary 导出为空（LVS status={status}）: {exported}")
        for entry in downloaded:
            _check(Path(entry["local"]).is_file(), f"导出文件缺失: {entry}")

    def case_pex() -> None:
        has_svdb = "yes" in _command(transport, f"test -d {lvs_dir}/svdb && echo yes || echo no")
        if not has_svdb:
            notes.append("LVS run_dir 里没有 svdb/，PEX 用 set 形态再造一次（*lvsSVDBxcal: 1）")
            runset = f"{RUN_DIR}/pex-lvs-{stamp}.lvs"
            lines = [
                f"*lvsRulesFile: {LVS_DECK}",
                f"*lvsRunDir: {lvs_dir}",
                f"*lvsLayoutPrimary: {TOP}",
                f"*lvsLayoutPaths: {GDS}",
                "*lvsLayoutGetFromViewer: 1",
                f"*lvsSourcePath: {CDL}",
                f"*lvsSourcePrimary: {TOP}",
                "*lvsSourceView: schematic",
                "*lvsPowerNames: VDD",
                "*lvsGroundNames: VSS",
                "*lvsSVDBxcal: 1",
                "*lvsReportFile: inv.lvs.report",
                "*cmnRunMT: 1",
                "*cmnPromptSaveRunset: 0",
            ]
            local = SCRATCH / f"pex-{stamp}.lvs"
            local.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
            _op(transport, "basic.file.upload", local_path=str(local), remote_path=runset, timeout=120)
            _value(transport, "calibre.lvs", runset=runset, blocking=True, timeout=1800)
            has_svdb = "yes" in _command(transport, f"test -d {lvs_dir}/svdb && echo yes || echo no")
        _check(has_svdb, f"没有 svdb/，PEX 前提不成立（{lvs_dir}）")
        # P-102 红钉：deck 必须是 **rcx deck**（spec 12-calibre.md:187），今天 stage3 的 `-fmt spice` 非法 →
        # 前两阶段成功、第三阶段打 usage，整体 failed。修好后本条应转绿。
        result = _op(transport, "calibre.pex", gds=GDS, top=TOP, cdl=CDL, deck=RCX_DECK,
                     lvs_run_dir=lvs_dir, run_dir=f"{RUN_DIR}/pex-run-{stamp}",
                     calibre_bin=CALIBRE_BIN, blocking=True, timeout=2400)
        value = (result.get("data") or {}).get("value") or {}
        if not result.get("ok"):
            # 如实判红：PEX 是零调用 op 之一，跑不通就是未覆盖，不许拿 NOTE 换 PASS
            raise AssertionError(f"PEX 未跑通（如实记录，不假装覆盖）：{str(result.get('error'))[:220]}")
        value_status = value.get("status")
        _check(value_status == "completed", f"PEX 未完成: {value_status} {value.get('progress')}")

    def case_export_by_job_id() -> None:
        """`export(job_id=…)`：不带 run_dir，让桥自己按 job_id 定位（C 轴最后一条低成本真缺口）。"""
        job_id = f"export_by_id_{stamp}"
        value = _value(transport, "calibre.drc", gds=GDS, top=TOP, deck=DRC_DECK,
                       job_id=job_id, calibre_bin=CALIBRE_BIN, hier=True, turbo=2,
                       blocking=True, timeout=1800)
        _check(value.get("status") == "completed", f"job_id 定位用的 DRC 未完成: {value.get('status')}")
        run_dir = value.get("run_dir")
        _check(run_dir, f"DRC 未返回 run_dir: {value}")
        local_dir = SCRATCH / f"by_job_id_{stamp}"
        exported = _value(transport, "calibre.export", kind="drc", job_id=job_id,
                          local_dir=str(local_dir), items=["summary"], timeout=600)
        _check(exported.get("run_dir") == run_dir,
               f"export 按 job_id 定位到的 run_dir 不一致: {exported.get('run_dir')} vs {run_dir}")
        downloaded = exported.get("downloaded") or []
        _check(downloaded, f"export(job_id=…) 什么都没导出: {exported}")
        for entry in downloaded:
            _check(Path(entry["local"]).is_file(), f"导出文件缺失: {entry}")

    def case_pex_fmt_red_pin() -> None:
        """P-102 红钉：`pex(fmt="spice")` 会多跑第三阶段，而 stage3 的 argv 形态非法 → 今天必红。

        说明：不传 `fmt` 时 PEX 只跑 phdb/pdb 两阶段（PEX-01 已绿）；`fmt` 一旦给定，
        `_argv_for` 会追加 `calibre -xrc -fmt spice <deck>`，Calibre 只接受 `-fmt -<flag>` → usage + stage3_failed。
        """
        run_dir = f"{RUN_DIR}/pex-fmt-{stamp}"
        result = _op(transport, "calibre.pex", gds=GDS, top=TOP, cdl=CDL, deck=RCX_DECK,
                     lvs_run_dir=lvs_dir, run_dir=run_dir, calibre_bin=CALIBRE_BIN,
                     fmt="spice", blocking=True, timeout=2400)
        value = (result.get("data") or {}).get("value") or {}
        status = value.get("status")
        # 先判 P-103：桥的完成判定会被 stage1 的 COMPLETED 标记提前触发 → 报 completed 但 stage3_failed。
        # P-103 让桥在 stage1 的 COMPLETED 标记处就返回，此时 stage2/3 可能还没写完日志 →
        # 必须限时等一个"终态"再断言，否则会因检查太早而假绿（本轮实测踩到）。
        import time as _time
        deadline = _time.monotonic() + 180
        log_state = ""
        netlist_state = "0"
        while _time.monotonic() < deadline:
            log_state = str(_command(transport,
                                     f"tail -2 {run_dir}/pex.log 2>/dev/null; "
                                     f"ls {run_dir}/*.netlist {run_dir}/*.pex.netlist 2>/dev/null | head -2"))
            netlist_state = str(_command(transport, f"ls -1 {run_dir} | grep -c netlist || true"))
            if "stage3_failed" in log_state or int((netlist_state.strip("[]', \\n") or "0") or 0) > 0:
                break
            _time.sleep(10)
        _check("stage3_failed" not in log_state,
               f"P-103：pex.log 记 stage3_failed（无网表，netlist_count={str(netlist_state).strip()[:20]}），"
               f"但运行期报 status={status} → 完成判定被前一阶段标记提前触发")
        _check(result.get("ok") and status == "completed",
               f"P-102：带 fmt=spice 的三阶段 PEX 应完成，实际 ok={result.get('ok')} "
               f"status={status} err={str(result.get('error'))[:160]}")
        _check(value.get("fmt") in (None, "none", "spice", "simple"), f"fmt 异常: {value}")

    run("ENV-01 deck/gds/bin 三件套", case_env)
    run("EXP-00 跑一次 DRC 作为 export 输入", case_drc_for_export)
    run("EXP-01 export(items=all_small) 三类产物齐 + 字节数>0", case_export_all_small)
    run("EXP-02 export(items=summary) 对 LVS run_dir 生效", case_export_summary_only)
    run("EXP-03 export(job_id=…) 自主定位 run_dir", case_export_by_job_id)
    run("PEX-01 calibre.pex 三阶段（有 svdb 才跑）", case_pex)
    # 红钉放最后：PEX + fmt 今天必红（P-102），但不许挡住上面的覆盖率
    run("PEX-FMT-01 fmt=spice 三阶段（P-102 红钉）", case_pex_fmt_red_pin)
    for note in notes:
        print(f"NOTE  {note}", flush=True)
    return results


def main() -> int:
    global API, TOKEN

    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    API, TOKEN = args.api, args.token
    transport = HttpTransport()
    results = run_suite(transport)
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        evidence = {"api": API, "token": TOKEN, "python": sys.version.split()[0],
                    "results": [{"case": n, "status": s} for n, s in results]}
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"evidence: {out_path}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
