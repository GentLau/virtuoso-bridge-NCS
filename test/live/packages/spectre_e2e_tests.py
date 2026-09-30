# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 11:20
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（靶机指纹 / 业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时正文有注释说明。
"""End-to-end acceptance tests for ``spectre.*``.

Run with ``--transport direct`` (in-process dispatch) or ``--transport http``
(the 8127 business face).
"""
from __future__ import annotations

import argparse
import json
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

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
RC_NETLIST = WORK_DIR / "artifact" / "spectre_probe_rc" / "tb.scs"

BAD_NETLIST = """simulator lang=spectre
global 0
this is not a legal spectre statement
"""


class HttpTransport:
    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
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


def _case_license(transport) -> None:
    value = _value(transport, "spectre.check_license")
    _check(value.get("version"), f"version missing: {value}")
    _check(value.get("bin"), f"bin missing: {value}")
    # 显式 spectre_bin：与自动探测同源；错路径必须结构化失败
    explicit = _value(transport, "spectre.check_license",
                      spectre_bin=value["bin"], timeout=60)
    _check(explicit.get("bin") == value["bin"],
           f"explicit spectre_bin mismatch: {explicit}")
    bad = transport.call({
        "operation": "spectre.check_license", "token": TOKEN,
        "spectre_bin": "/no/such/spectre-binary", "timeout": 60})
    _check(not bad.get("ok"), f"bad spectre_bin must fail: {bad}")


def _case_run_auto(transport) -> None:
    value = _value(
        transport, "spectre.run",
        tasks=[{"job": "e2e_rc_auto", "netlist": str(RC_NETLIST), "parse": "auto"}],
    )
    runs = value.get("runs")
    _check(isinstance(runs, list) and runs, f"runs missing: {value}")
    run = runs[0]
    task = run.get("value") or {}
    _check(task.get("status") == "success", f"run status: {task}")
    _check("tran" in task.get("analyses", []), f"analyses: {task}")
    data = task.get("data", {})
    _check(data.get("OUT") and data.get("time"), f"signals: {sorted(data)}")


def _case_run_raw_and_read(transport) -> None:
    value = _value(
        transport, "spectre.run",
        tasks=[{"job": "e2e_rc_raw", "netlist": str(RC_NETLIST)}],
        parse="none", download=False, keep_run_dir=True,
    )
    run = value["runs"][0]
    run_dir = (run.get("value") or {}).get("run_dir")
    _check(run_dir, f"run_dir missing: {run}")
    try:
        out_dir = Path(WORK_DIR) / "spectre_e2e" / "read_out"
        out_dir.mkdir(parents=True, exist_ok=True)
        read = _value(
            transport, "spectre.read_results",
            source=f"{run_dir}/tb.raw", analysis="all",
            output_dir=str(out_dir), timeout=120,
        )
        _check(read.get("kind") == "raw", f"kind: {read}")
        signals = set(read.get("signals", []))
        _check({"time", "OUT"} <= signals, f"signals: {signals}")
        _check(any(out_dir.iterdir()), f"output_dir must receive files: {out_dir}")
        # 2026-09-30（表 C 真缺口）：read_results 的 analysis/output_dir/source/point_count/files
        # 此前"读了不断言"。逐项值级断言（实测 schema：kind/source/output_dir/analysis/layout/
        # point_count/header/data/points/analyses/signals/files）。
        _check(read.get("analysis") == "all",
               f"analysis 应回显请求值 all（实测 {read.get('analysis')!r}）")
        _check(str(read.get("output_dir") or "") == str(out_dir),
               f"output_dir 应回显下载目录（实测 {read.get('output_dir')!r}）")
        _check(str(read.get("source") or "").endswith("/tb.raw"),
               f"source 应指向读入的 raw（实测 {read.get('source')!r}）")
        # 注：`point_count` 是**扫描点数**（普通 tran 为 0），不是采样点数 —— 实测口径，
        # 采样数据在 `data` 里（`data["time"]` + 各信号等长数组）。据此断言：
        _check(read.get("analyses") == ["tran"],
               f"analyses 应列出网表里的 tran（实测 {read.get('analyses')!r}）")
        files = [str(item) for item in (read.get("files") or [])]
        _check(any(name.endswith(".tran") or "tran" in name for name in files),
               f"files 应包含 tran 结果文件（实测 {files!r}）")
        data = read.get("data") or {}
        _check("time" in data, f"data 必须含 time 轴（实测键 {list(data)[:8]}）")
        lengths = {len(v) for v in data.values() if isinstance(v, list)}
        _check(bool(lengths) and max(lengths) > 10,
               f"波形采样点应 >10（实测每列长度 {sorted(lengths)[:5]}）")
        _check(len(lengths) <= 1,
               f"各信号采样长度应一致（实测长度集合 {sorted(lengths)}）")
    finally:
        _op(
            transport, "basic.spectre.run",
            cmd=f"rm -rf {run_dir}",
        )


def _case_measure_export(transport) -> None:
    value = _value(
        transport, "spectre.run",
        tasks=[{"job": "e2e_rc_measure", "netlist": str(RC_NETLIST), "parse": "auto"}],
    )
    data = (value["runs"][0].get("value") or {})["data"]
    measured = _value(
        transport, "spectre.measure",
        data=data, metrics=[{"type": "max", "signal": "OUT"}],
    )
    metrics = measured.get("metrics")
    _check(metrics and metrics[0].get("ok"), f"measure failed: {measured}")
    _check(isinstance(metrics[0].get("value"), float), f"measure value: {metrics[0]}")
    output_dir = Path(WORK_DIR) / "spectre_e2e"
    output_dir.mkdir(parents=True, exist_ok=True)
    for fmt in ("csv", "json"):
        exported = _value(
            transport, "spectre.export",
            format=fmt, output_path=str(output_dir / f"e2e_rc.{fmt}"), data=data,
        )
        path = Path(exported["output_path"])
        _check(path.is_file() and path.stat().st_size > 0, f"{fmt} export missing")


def _case_multi_task(transport) -> None:
    value = _value(
        transport, "spectre.run",
        tasks=[
            {"job": "e2e_rc_a", "netlist": str(RC_NETLIST)},
            {"job": "e2e_rc_b", "netlist": str(RC_NETLIST)},
        ],
        parse="none", download=False, keep_run_dir=True,
    )
    runs = value.get("runs", [])
    _check(len(runs) == 2, f"runs count: {value}")
    _check(all((run.get("value") or {}).get("status") == "success" for run in runs),
           f"runs: {runs}")
    for run in runs:
        run_dir = (run.get("value") or {}).get("run_dir")
        if run_dir:
            _op(transport, "basic.spectre.run", cmd=f"rm -rf {run_dir}")


def _case_failure(transport) -> None:
    bad = Path(WORK_DIR) / "spectre_e2e" / "bad.scs"
    bad.parent.mkdir(parents=True, exist_ok=True)
    bad.write_text(BAD_NETLIST, encoding="utf-8")
    # 2026-09-30 修：原来只传 parse="none" 且不传 keep_run_dir，请求在**入参校验**就失败
    # （`parse='none' requires keep_run_dir=true`），坏网表从未真正跑过 → 该用例是**假绿**。
    # 现在：唯一 job 名 + keep_run_dir=True，断言"仿真器真的跑起来并报错"（值级）。
    job = f"e2e_rc_bad_{int(time.time())}"
    response = transport.call({
        "operation": "spectre.run", "token": TOKEN,
        "tasks": [{"job": job, "netlist": str(bad)}],
        "parse": "none", "keep_run_dir": True,
    })
    _check(not response.get("ok"), "bad netlist must fail")
    text = json.dumps(response, ensure_ascii=False)
    _check("tasks failed" in text, f"顶层错误应说明任务失败（实测 {response.get('error')!r}）")
    runs = ((response.get("value") or {}).get("runs") or [])
    _check(len(runs) == 1 and runs[0].get("ok") is False, f"run 结果应为失败：{runs}")
    steps = runs[0].get("steps") or []
    execute = next((s for s in steps if s.get("name") == "execute"), None)
    _check(execute is not None, f"失败 run 必须留下 execute 步（实测步骤 {[s.get('name') for s in steps]}）")
    detail = execute.get("detail") or {}
    _check(detail.get("returncode") not in (0, None),
           f"spectre 进程必须非零退出（实测 {detail.get('returncode')!r}）")
    _check("spectre completes with" in str(detail.get("stdout") or ""),
           "execute 步 stdout 必须带 spectre 自己的收尾统计（证明是真跑出来的失败）")
    # P-107 回归（2026-09-30 设计已修，`5e8c29b`）：失败 run 必须
    #   ① `status="failure"`（rc!=0 且 raw 不存在，spec §5.4）；
    #   ② `errors` 回带**仿真器原文**（不再被 "recursive download…" 盖住）；
    #   ③ run 级 `error` 同样指向仿真器错误。
    inner = runs[0].get("value") or {}
    errors = [str(item) for item in (inner.get("errors") or [])]
    _check(inner.get("status") == "failure",
           f"P-107 回归：失败 run 的 status 应为 failure（实测 {inner.get('status')!r}）")
    _check(any("ERROR (" in item for item in errors),
           f"P-107 回归：errors 必须回带仿真器原文（实测 {errors[:1]}）")
    _check("recursive download" not in str(runs[0].get("error") or ""),
           f"P-107 回归：run.error 不得是下载错误（实测 {runs[0].get('error')!r}）")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("LICENSE-01 check_license", lambda: _case_license(transport))
    run("RUN-01 run + auto parse", lambda: _case_run_auto(transport))
    run("RUN-02 raw + read_results", lambda: _case_run_raw_and_read(transport))
    run("RESULT-01 measure + export", lambda: _case_measure_export(transport))
    run("RUN-03 multi task", lambda: _case_multi_task(transport))
    run("RUN-04 bad netlist fails", lambda: _case_failure(transport))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="http",
                        help="direct=故障定位/覆盖率；真机判据必须 http")
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
