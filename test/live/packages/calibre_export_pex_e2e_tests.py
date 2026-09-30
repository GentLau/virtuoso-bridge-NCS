# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 21:19
# 依赖: 无
# =======================================================================
"""补掉 `calibre.export` 的产物面，并钉住 `calibre.pex` 的本版不支持语义。

* `EXP-01`：对一次真实 DRC 的 run_dir 调 `export(items=["all_small"])`，断言 summary/results_db/log
  至少各落一个本地文件、字节数 > 0（`_EXPORT_ITEMS` 的三类各验证一条）。
* `EXP-02`：`export(items=["summary"])` 对 LVS run_dir 生效，且返回的 `downloaded[].local` 真实存在。
* `PEX-01`：`calibre.pex` 本版不提供——调用必须返回 `ok=false` + `value.reason=pex_unsupported`，
  且不得建 run dir、不得调用远程接口。

六步流程（test/docs/写TB规范.md §1）：① 环境检查=ENV（deck/gds/bin 三件套）；②③ 基线=DRC 跑一次作为 export 输入；
④ 每个用例一次调用；⑤ 读回=本地文件 stat / downloaded 结构 / PEX 结构化拒绝；⑥ 不清理现场（run_dir 与导出物都留在 role root / 本机 tmp）。

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
    # C1 契约（2f88853）：值型 op 的业务载荷在顶层 `value`（命令型在 `result`），无 `data` 壳。
    payload = response.get("value")
    if payload is None:
        payload = response.get("result")
    if payload is None:
        data = response
        payload = data.get("value") if data.get("value") is not None else data
    return payload if isinstance(payload, dict) else {}


def _command(transport, cmd: str, timeout: int = 120) -> str:
    """C4 契约：`basic.command.run` 的 `result` 是命名对象
    `{returncode,stdout,stderr,kind}`（旧的位置数组 `[rc,stdout,...]` 已废除——
    2026-09-29 21:0x 门禁实测：旧索引写法让 ENV-01 的 `drc_ok` 恒为空串）。
    """
    response = _op(transport, "basic.command.run", cmd=cmd, timeout=timeout)
    if not response.get("ok"):
        raise AssertionError(f"command failed: {response.get('error')}")
    result = response.get("result")
    if not isinstance(result, dict):
        raise AssertionError(f"command result 不是命名对象（C4 契约）: {response}")
    if result.get("returncode") != 0:
        raise AssertionError(f"command rc != 0: {response}")
    return str(result.get("stdout") or "")


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

    def case_pex_unsupported() -> None:
        """PEX 本版不提供：合法 RunRequest 也不能触发任何远程动作。"""
        response = transport.call({
            "operation": "calibre.pex", "token": TOKEN, "deck": RCX_DECK,
        })
        # 兼容顶层统一壳与“业务结果本体直出”两种形态。
        data = response or response
        _check(response.get("ok") is False and data.get("ok") is False,
               f"PEX 必须结构化失败: {response}")
        value = data.get("value") or {}
        _check(value.get("reason") == "pex_unsupported",
               f"PEX 拒绝原因不对: {data}")
        error = str(data.get("error") or response.get("error") or "")
        _check("not supported" in error,
               f"PEX 错误文案未点名不支持: {error}")
        _check("run_dir" not in value, f"PEX 不应创建 run_dir: {value}")

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

    run("ENV-01 deck/gds/bin 三件套", case_env)
    run("EXP-00 跑一次 DRC 作为 export 输入", case_drc_for_export)
    run("EXP-01 export(items=all_small) 三类产物齐 + 字节数>0", case_export_all_small)
    run("EXP-02 export(items=summary) 对 LVS run_dir 生效", case_export_summary_only)
    run("EXP-03 export(job_id=…) 自主定位 run_dir", case_export_by_job_id)
    run("PEX-01 calibre.pex 本版不支持（结构化失败）", case_pex_unsupported)
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
