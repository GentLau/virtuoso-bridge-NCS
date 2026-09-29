# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 17:45
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：业务面 + `maestro_tb/rc_probe` 有 history（read_history 探活）；
# ②③ 基线：记录当前 run mode；把 run mode 切到 "Monte Carlo Sampling" 并设 mcnumpoints=2；
# ④ 只做被测动作：`run`（非阻塞 + 轮询 read_history）→ `read_results`；
# ⑤ 读回比对：history 名形如 `MonteCarlo.N`；`value.monte_carlo.overall.total_points>0`、
#    `outputs[]` 每条带 yield/mean/target（点数误差不算失败，如实记录）；
# ⑥ 状态还原：run mode 切回 "Single Run, Sweeps and Corners"（共享库里不留改动）。
"""P-070 真机验收：Monte Carlo 配置 → 运行 → 结果读回（`value.monte_carlo`）。

判据（spec/上层 6-maestro.md §7.3）：
  * `set_run_mode` / `set_run_option` 可写；
  * run 产出的 history 名为 `MonteCarlo.*`（用返回值，不猜）；
  * `read_results(history=MonteCarlo.*)` 返回 `value.monte_carlo`：
    `overall`（yield/passed/total/error_points）+ `outputs[]`（yield/mean/target）。

用法::

    PYTHONPATH=src python test/live/packages/maestro_mc_e2e_tests.py --transport http
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
LIB, CELL, VIEW = "maestro_tb", "rc_probe", "maestro"
MC_MODE = "Monte Carlo Sampling"
NORMAL_MODE = "Single Run, Sweeps and Corners"


def _payload(body: dict[str, Any]) -> dict[str, Any]:
    """C1 契约兼容解包：值型 → `value`；命令/skill 型 → `result`；旧壳 → `data.value`/`data`。"""
    if not isinstance(body, dict):
        return {}
    for key in ("value", "result"):
        value = body.get(key)
        if isinstance(value, dict):
            return value
    data = _c1_wrapper(body)
    if isinstance(data, dict):
        inner = data.get("value")
        return inner if isinstance(inner, dict) else data
    return {}


class HttpTransport:
    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=1800) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if response.get("ok") is not True:
        raise AssertionError(f"{operation} failed: {response.get('error')}; {str(response)[:200]}")
    return _payload(response)


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        return value

    def case_env() -> None:
        value = _op(transport, "virtuoso.maestro.read_history", library=LIB, cell=CELL, view=VIEW)
        assert "histories" in value, f"read_history 无 histories 字段: {value}"

    def case_set_run_mode() -> None:
        _op(transport, "virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
            commands=[{"op": "set_run_mode", "run_mode": MC_MODE}])

    def case_set_run_option() -> None:
        _op(transport, "virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
            commands=[{"op": "set_run_option",
                       "options": {"mcmethod": "process", "mcnumpoints": 2,
                                   "samplingmode": "lhs", "saveallplots": False}}])

    def case_run_mc() -> str:
        started = _op(transport, "virtuoso.maestro.run", library=LIB, cell=CELL, view=VIEW,
                      blocking=False, timeout=600)
        history = str(started.get("history") or "")
        assert history.startswith("MonteCarlo."), f"MC run 未产出 MonteCarlo.* history: {started}"
        deadline = time.monotonic() + 900
        last: dict[str, Any] = {}
        while time.monotonic() < deadline:
            last = _op(transport, "virtuoso.maestro.read_history",
                       library=LIB, cell=CELL, view=VIEW, history=history)
            status = str((last.get("history") or {}).get("status") or last.get("status") or "")
            if status in ("done", "failed", "completed", "error"):
                break
            time.sleep(10)
        print(f"NOTE  MC history={history} 终态 status={status!r}（failed 也照读结果，如实记录）",
              flush=True)
        return history

    def case_read_results(history: str | None) -> None:
        assert history, "无 MC history 可读"
        value = _op(transport, "virtuoso.maestro.read_results",
                    library=LIB, cell=CELL, view=VIEW, history=history, test="ac")
        mc = value.get("monte_carlo")
        assert isinstance(mc, dict), f"read_results 未返回 value.monte_carlo: {str(value)[:300]}"
        overall = mc.get("overall") or {}
        assert int(overall.get("total_points") or 0) > 0, f"monte_carlo.overall 无总点数: {overall}"
        outputs = mc.get("outputs") or []
        assert outputs, f"monte_carlo.outputs 为空: {str(mc)[:300]}"
        first = outputs[0]
        for key in ("name", "yield", "mean"):
            assert key in first, f"outputs[0] 缺字段 {key}: {first}"
        print(f"NOTE  MC overall={json.dumps(overall, ensure_ascii=False)[:200]}", flush=True)
        print(f"NOTE  MC outputs[0]={json.dumps(first, ensure_ascii=False)[:240]}", flush=True)

    def case_restore_mode() -> None:
        _op(transport, "virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
            commands=[{"op": "set_run_mode", "run_mode": NORMAL_MODE}])

    run("MC-ENV 环境检查（rc_probe 可读）", case_env)
    run("MC-01 set_run_mode(Monte Carlo Sampling)", case_set_run_mode)
    run("MC-02 set_run_option(mcnumpoints=2)", case_set_run_option)
    history = run("MC-03 run → MonteCarlo.* history（含轮询）", case_run_mc)
    run("MC-04 read_results → value.monte_carlo（overall + outputs）",
        lambda: case_read_results(history))
    run("MC-99 状态还原：run mode 切回 Single Run", case_restore_mode)
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
    results = run_suite(HttpTransport())
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        from pathlib import Path
        evidence = {"api": API, "token": TOKEN, "target": f"{LIB}/{CELL}/{VIEW}",
                    "python": sys.version.split()[0],
                    "results": [{"case": n, "status": s} for n, s in results]}
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"evidence: {out_path}")
    return 0 if results and all(s == "PASS" for _, s in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
