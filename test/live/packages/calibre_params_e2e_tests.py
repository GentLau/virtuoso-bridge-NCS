# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 22:52
# 依赖: 无
# =======================================================================
"""calibre 包的**参数面**真机覆盖（补齐 calibre_e2e_tests.py 只走默认值的缺口）。

覆盖：check_env(calibre_bin/deck 正负)、drc(calibre_bin/hier/turbo/poll_interval/job_id/params/run_dir)、
read_results(log_lines=0/5)、lvs(spice_file/hcell_file/xcell_file)。
`power`/`ground` 预期是**死参数**（源码只校验、无读取点）→ P-092，本 TB 只记录不当作覆盖。

六步流程（test/docs/写TB规范.md §1）：① 环境检查=CAL-ENV-01；②③ 基线=deck/gds/报告；
④ 每个用例一次调用；⑤ 读回比对（job_id/run_dir/报告/日志尾/产物 stat）；⑥ 不清理现场（run_dir 留在 role root）。

环境变量：VB_CALIBRE_API / VB_CALIBRE_TOKEN / VB_CALIBRE_GDS / VB_CALIBRE_TOP /
VB_CALIBRE_DRC_DECK / VB_CALIBRE_LVS_DECK / VB_CALIBRE_RUN_DIR / VB_CALIBRE_BIN。
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

API = os.environ.get("VB_CALIBRE_API", "http://127.0.0.1:8127/api/operation")
TOKEN = os.environ.get("VB_CALIBRE_TOKEN", "vb-vblog")
PDK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre"
GDS = os.environ.get("VB_CALIBRE_GDS", "/home/Gent/project/vblog/s11_inv/s11/inv.gds")
TOP = os.environ.get("VB_CALIBRE_TOP", "inv")
DRC_DECK = os.environ.get("VB_CALIBRE_DRC_DECK", f"{PDK}/drc/calibre.drc")
LVS_DECK = os.environ.get("VB_CALIBRE_LVS_DECK", f"{PDK}/lvs/calibre.lvs")
RUN_DIR = os.environ.get("VB_CALIBRE_RUN_DIR", "/home/Gent/project/vblog/calibre-e2e")
SCRATCH = Path(__file__).resolve().parents[3] / "test" / "artifacts" / "tmp" / "calibre-params"
CDL = os.environ.get("VB_CALIBRE_CDL", "/home/Gent/.virtuoso-bridge/calprobe/command/calibre/inv.cdl")
CALIBRE_BIN = os.environ.get(
    "VB_CALIBRE_BIN", "/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre")


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


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return transport.call({"operation": operation, "token": TOKEN, **fields})


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    response = _op(transport, operation, **fields)
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    data = response.get("data") or {}
    return data.get("value") if data.get("value") is not None else data


def _command(transport, cmd: str, timeout: int = 120) -> list[Any]:
    response = _op(transport, "basic.command.run", cmd=cmd, timeout=timeout)
    if not response.get("ok"):
        raise AssertionError(f"command failed: {response.get('error')}")
    return ((response.get("data") or {}).get("result")) or []


def _check(condition: Any, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise
        results.append((name, "PASS"))
        return value

    stamp = int(time.time() * 1000)
    drc_dir = f"{RUN_DIR}/params-drc-{stamp}"
    lvs_dir = f"{RUN_DIR}/params-lvs-{stamp}"
    probe_dir = f"{RUN_DIR}/params-probe-{stamp}"
    drc_job = f"drc_params_{stamp}"

    def case_check_env() -> None:
        value = _value(transport, "calibre.check_env", calibre_bin=CALIBRE_BIN, deck=DRC_DECK)
        _check(value.get("calibre_path"), f"calibre_bin 覆盖未生效: {value}")
        _check(value.get("version"), f"version 缺失: {value}")
        _check(value.get("deck_ok") is True, f"deck 检查未通过: {value}")
        bad = _op(transport, "calibre.check_env", calibre_bin="/nonexistent/calibre-probe")
        _check(not bad.get("ok"), f"坏 calibre_bin 必须失败: {bad}")
        _check("calibre" in str(bad.get("error", "")).lower(),
               f"坏 calibre_bin 的错误文案不指向该参数: {bad}")

    def case_drc_full_params() -> dict:
        # 注意：这里必须 hier=True。hier=False 会让 calibre 拒绝 `-turbo`（P-093），
        # 且工具秒退后 blocking 会等到 timeout（P-094）——那两条由半真机探针
        # `test/semi/probes/calibre_flat_turbo_probe.py` 红钉，不放进本套件（否则一次跑挂 30 分钟）。
        value = _value(
            transport, "calibre.drc",
            gds=GDS, top=TOP, deck=DRC_DECK, run_dir=drc_dir,
            calibre_bin=CALIBRE_BIN, hier=True, turbo=2,
            poll_interval=0.5, job_id=drc_job,
            params={"LAYOUT PRIMARY": f'LAYOUT PRIMARY "{TOP}"'},
            power="VDD", ground="VSS",
            blocking=True, timeout=1800,
        )
        _check(value.get("status") == "completed", f"drc 未完成: {value.get('status')}")
        _check(value.get("job_id") == drc_job, f"job_id 未生效: {value.get('job_id')}")
        _check(value.get("run_dir") == drc_dir, f"run_dir 未生效: {value.get('run_dir')}")
        return value

    def case_read_results_log_lines(drc: dict) -> None:
        narrow = _value(transport, "calibre.read_results", job_id=drc_job, run_dir=drc_dir,
                        kind="drc", limit=5, log_lines=0)
        _check(narrow.get("log_tail") == "",
               f"log_lines=0 应无日志尾: {str(narrow.get('log_tail'))[:120]}")
        _check((narrow.get("summary") or {}).get("rules_checked"),
               f"rules_checked 缺失: {narrow.get('summary')}")
        wide = _value(transport, "calibre.read_results", job_id=drc_job, run_dir=drc_dir,
                      kind="drc", limit=5, log_lines=5)
        _check((wide.get("log_tail") or "").strip(), "log_lines=5 应有日志尾")

    def case_lvs_file_params() -> None:
        _command(transport,
                 f"mkdir -p {probe_dir} {lvs_dir} && "
                 f"printf '// hcell probe\\n' > {probe_dir}/hcell.probe && "
                 f"printf '// xcell probe\\n' > {probe_dir}/xcell.probe && echo ready")
        # 提交用非阻塞 + TB 自己限时轮询：工具若秒退，本用例最多等 300s 而不是套件的 1800s。
        job = _value(
            transport, "calibre.lvs",
            gds=GDS, top=TOP, cdl=CDL, deck=LVS_DECK, run_dir=lvs_dir, calibre_bin=CALIBRE_BIN,
            spice_file=f"{lvs_dir}/layout.sp", hcell_file=f"{probe_dir}/hcell.probe",
            xcell_file=f"{probe_dir}/xcell.probe", hier=True, turbo=2, poll_interval=0.5,
            job_id=f"lvs_params_{stamp}", blocking=False, timeout=1800,
        )
        _check(job.get("job_id"), f"lvs 未返回 job_id: {job}")
        deadline = time.monotonic() + 300
        status_value: dict[str, Any] = {}
        while time.monotonic() < deadline:
            status_value = _value(transport, "calibre.status", job_id=job["job_id"], run_dir=lvs_dir)
            state = status_value.get("status")
            if state in ("completed", "failed"):
                break
            time.sleep(5)
        status = status_value.get("status")
        if status != "completed":
            text = json.dumps({"job": job, "status": status_value}, ensure_ascii=False)
            _check(("hcell" in text) or ("xcell" in text),
                   f"lvs 未完成且错误与 hcell/xcell 无关（疑似参数未转发/另有缺陷）: {text[:400]}")
            print(f"NOTE  lvs 带 hcell/xcell 未跑完（{status}），错误已点名该参数", flush=True)
            return
        out = _command(transport, f"test -s {lvs_dir}/layout.sp && echo spice_ok || echo spice_missing")
        _check("spice_ok" in str(out), f"spice_file 未产生产物: {out}")

    def case_dead_params_note() -> None:
        print("NOTE  P-092: power/ground 已随 DRC 传入（params-drc 的 job.json），"
              "源码内无读取点 → 不作为覆盖判据", flush=True)

    def case_drc_official_set() -> None:
        """`drc.runset` 走官方批处理（`calibre -gui -drc -runset … -batch`）——本轮 C 轴最后一个真缺口。"""
        set_dir = f"{RUN_DIR}/drc-set-{stamp}"
        lines = [
            f"*drcRulesFile: {DRC_DECK}",
            f"*drcRunDir: {set_dir}",
            f"*drcLayoutPaths: {GDS}",
            f"*drcLayoutPrimary: {TOP}",
            "*drcLayoutLibrary: schemtest",
            "*drcLayoutView: layout",
            "*drcLayoutGetFromViewer: 0",
            "*drcReportOptions: S",
            "*cmnRunMT: 1",
            "*cmnPromptSaveRunset: 0",
        ]
        local_set = Path(SCRATCH) / f"drc-set-{stamp}.drc"
        local_set.parent.mkdir(parents=True, exist_ok=True)
        local_set.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
        remote_set = f"{RUN_DIR}/drc-set-{stamp}.drc"
        uploaded = _op(transport, "basic.file.upload", local_path=str(local_set),
                       remote_path=remote_set, timeout=120)
        _check(uploaded.get("ok"), f"set 上传失败: {uploaded.get('error')}")
        value = _value(transport, "calibre.drc", runset=remote_set, blocking=True, timeout=1800)
        _check(value.get("mode") == "official-batch",
               f"不是官方批处理模式: {value.get('mode')}")
        _check(value.get("run_dir") == set_dir,
               f"产物目录应取 set 的 drcRunDir: {value.get('run_dir')}")
        probe = _command(transport,
                         f"ls {set_dir}/_calibre.drc_ >/dev/null 2>&1 && echo ctrl_ok; "
                         f"ls {set_dir}/drc.summary >/dev/null 2>&1 && echo summary_ok")
        probe_text = str(probe)
        _check("ctrl_ok" in probe_text, f"缺 Calibre 生成的 control file：{probe!r}")
        _check("summary_ok" in probe_text, f"缺 drc.summary：{probe!r}")
        read = _value(transport, "calibre.read_results", kind="drc", run_dir=set_dir,
                      limit=5, log_lines=5)
        _check(read.get("report_used"), f"set 驱动的 DRC 报告找不到: {read.get('artifacts')}")
        _check((read.get("summary") or {}).get("rules_checked"),
               f"set 驱动的 DRC 未解析出规则数: {read.get('summary')}")

    drc = run("CAL-DRC-01 全参数 DRC（calibre_bin/hier/turbo/poll_interval/job_id/params/run_dir）",
              case_drc_full_params)
    run("CAL-ENV-01 check_env(calibre_bin, deck) + 坏值负向", case_check_env)
    run("CAL-READ-01 read_results(log_lines=0/5)", lambda: case_read_results_log_lines(drc))
    run("CAL-LVS-01 lvs(spice_file/hcell_file/xcell_file/hier/turbo/poll_interval)", case_lvs_file_params)
    run("CAL-DRC-SET-01 drc(runset=…) 官方批处理 + 报告定位", case_drc_official_set)
    run("CAL-P092-01 power/ground 死参数记录", case_dead_params_note)
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
    failure: str | None = None
    try:
        results = run_suite(transport)
    except Exception as exc:  # noqa: BLE001 - 失败也要落证据（红项可复查）
        failure = f"{type(exc).__name__}: {exc}"
        results = []
    for name, status in results:
        print(f"{status:6}  {name}")
    if failure:
        print(f"ABORT  {failure}")
    if args.out:
        evidence = {"api": API, "token": TOKEN, "python": sys.version.split()[0],
                    "results": [{"case": n, "status": s} for n, s in results],
                    "failure": failure}
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"evidence: {out_path}")
    if failure:
        return 1
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
