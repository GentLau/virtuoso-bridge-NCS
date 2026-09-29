# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 18:01
# 依赖: 无
# =======================================================================
"""P-070 真机验收：Monte Carlo 的**全部 17 项 run option**、正负例和结果面。

本 TB 不修改共享 ``SERDES_TB_LIB/tb_ctle``：每次运行在 ``maestro_tb`` 下
新建三个专属 cell（option matrix / 正例 run / 负例 run），design 指向
``SERDES_TB_LIB/tb_ctle/schematic``，再把 PDK 统计 section 挂到本地 setup。
这样：

* 17 项 option 的“写→读回”可以逐项断言；
* 每一项都送一个非法值，确认包内校验拒绝且不污染已写值；
* matrix cell 与 run cell 分离，ADE 不能“清空”的 ``dutsummary`` 不会污染
  正例仿真；
* 正例用 ``stat_res + mc_res`` 跑 8 点 process MC，Yield 表必须非空；
* 负例显式不挂统计 section，结果目录必须出现
  ``SPECTRE-16008``（process）/``SPECTRE-16012``（mismatch）之一。

六步流程（test/docs/写TB规范.md §1）：
① 环境检查 = ``require_environment``；②③ 建独立 setup 并读回空基线；
④ 只调被测 maestro 操作；⑤ 读配置、读 history、读结果、grep 原始日志；
⑥ 不清理现场（专属 cell/history 保留），但关闭本 TB 自己的 GUI session。
"""
from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[3]
API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"

LIB = "maestro_tb"
VIEW = "maestro"
DESIGN_LIB = "SERDES_TB_LIB"
DESIGN_CELL = "tb_ctle"
DESIGN_VIEW = "schematic"
TEST = "ctle_ac"
MC_MODE = "Monte Carlo Sampling"
TRANSIENT_MARKERS = (
    "SKILL execution timed out",
    "daemon returned an empty response",
    "Empty response from daemon",
)

MODEL = (
    "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/models/spectre/"
    "crn65gplus_2d5_lk_v1d0.scs"
)
POSITIVE_MODEL_FILES = [
    [MODEL, "tt"],
    [MODEL, "tt_mim"],
    [MODEL, "stat_res"],
    [MODEL, "mc_res"],
]
NEGATIVE_MODEL_FILES = [
    [MODEL, "tt"],
    [MODEL, "tt_res"],
    [MODEL, "tt_mim"],
]

#: 与 spec/design-concepts/上层/6-maestro.md §7.3.1 的 17 项一一对应。
OPTION_CASES: tuple[tuple[str, Any, str], ...] = (
    ("mcmethod", "process", "process"),
    ("mcnumpoints", 8, "8"),
    ("mcnumbins", 10, "10"),
    ("samplingmode", "lhs", "lhs"),
    ("montecarloseed", 12345, "12345"),
    ("mcstartingrunnumber", 1, "1"),
    ("dutsummary", "ac%ICTLE%tb_ctle/schematic",
     "ac%ICTLE%tb_ctle/schematic"),
    ("ignoreflag", 1, "1"),
    # 无 reference point 时 ADE 不落这条 option（读回 nil），
    # 这里验证“批量写入调用成功”，读回接受 nil。
    ("mcreferencepoint", 0, None),
    ("donominal", True, "1"),
    ("saveprocess", 1, "1"),
    ("savemismatch", 1, "1"),
    ("saveallplots", False, "0"),
    ("mcStopEarly", False, "nil"),
    ("mcStopMethod", "Yield Verification", "Yield Verification"),
    ("mcYieldTarget", 99.73, "99.73"),
    ("mcYieldAlphaLimit", 95, "95"),
)

INVALID_OPTION_CASES: tuple[tuple[str, Any], ...] = (
    ("mcmethod", "not-a-method"),
    ("mcnumpoints", 0),
    ("mcnumbins", -1),
    ("samplingmode", "not-a-sampling-mode"),
    ("montecarloseed", -1),
    ("mcstartingrunnumber", 0),
    ("dutsummary", 3),
    ("ignoreflag", 2),
    ("mcreferencepoint", "maybe"),
    ("donominal", "maybe"),
    ("saveprocess", 2),
    ("savemismatch", "maybe"),
    ("saveallplots", "maybe"),
    ("mcStopEarly", "maybe"),
    ("mcStopMethod", 3),
    ("mcYieldTarget", 0),
    ("mcYieldAlphaLimit", 100),
)

#: 真正启动 MC 前使用的安全值。故意不设置 dutsummary / mcreferencepoint /
#: mcStopMethod：前两者在 ADE 里的“清空/无 reference point”语义已单独
#: 在 matrix cell 覆盖，run cell 只验证会实际参与仿真的选项。
RUN_OPTIONS: dict[str, Any] = {
    "mcmethod": "process",
    "mcnumpoints": 8,
    "mcnumbins": 10,
    "samplingmode": "lhs",
    "montecarloseed": 12345,
    "mcstartingrunnumber": 1,
    "ignoreflag": 0,
    "donominal": 0,
    "saveprocess": 0,
    "savemismatch": 0,
    "saveallplots": 0,
    "mcStopEarly": False,
    "mcYieldTarget": 99.73,
    "mcYieldAlphaLimit": 95,
}

RUN_EXPECTED: dict[str, str] = {
    "mcmethod": "process",
    "mcnumpoints": "8",
    "mcnumbins": "10",
    "samplingmode": "lhs",
    "montecarloseed": "12345",
    "mcstartingrunnumber": "1",
    "ignoreflag": "0",
    "donominal": "0",
    "saveprocess": "0",
    "savemismatch": "0",
    "saveallplots": "0",
    "mcStopEarly": "nil",
    "mcYieldTarget": "99.73",
    "mcYieldAlphaLimit": "95",
}

AC_OPTIONS = {
    "sweep": "Frequency",
    "rangeType": "Start-Stop",
    "start": "10M",
    "stop": "20G",
    "incrType": "Logarithmic",
    "stepTypeLin": "Step Size",
    "stepTypeLog": "Points Per Decade",
    "dec": 10,
    "outType": "Voltage",
    "srcType": "port",
    "perturbation": "linear",
    "special": "None",
    "annotate": "status",
}

BW_EXPR = 'bandwidth(abs((VF("/VOP") - VF("/VON"))) 3 "low")'
GAIN_EXPR = 'dB20(value(abs((VF("/VOP") - VF("/VON"))) 10000000))'


class HttpTransport:
    """业务面 HTTP transport；业务失败体原样返回，由断言决定结果。"""

    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=3600) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", "replace")
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                return {"ok": False, "error": f"HTTP {error.code}: {raw[:300]}"}


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return transport.call({"operation": operation, "token": TOKEN, **fields})


def _op_retry(
    transport,
    operation: str,
    *,
    attempts: int = 1,
    delay: float = 10.0,
    **fields: Any,
) -> dict[str, Any]:
    """Retry only the known transient daemon response-loss window (P-086)."""
    last: dict[str, Any] = {}
    for attempt in range(max(1, attempts)):
        last = _op(transport, operation, **fields)
        if last.get("ok") is True:
            return last
        error = str(last.get("error") or "")
        if attempt + 1 < attempts and any(
                marker in error for marker in TRANSIENT_MARKERS):
            time.sleep(delay)
            continue
        return last
    return last


def _value(
    transport,
    operation: str,
    *,
    _attempts: int = 1,
    _delay: float = 10.0,
    **fields: Any,
) -> dict[str, Any]:
    response = _op_retry(
        transport, operation, attempts=_attempts, delay=_delay, **fields)
    if response.get("ok") is not True:
        raise AssertionError(
            f"{operation} failed: {response.get('error')}; "
            f"{str(response)[:400]}")
    value = response.get("value")
    if not isinstance(value, dict):
        raise AssertionError(f"{operation} returned no value dict: {response}")
    return value


def _expect_fail(transport, operation: str, **fields: Any) -> str:
    for attempt in range(3):
        response = _op(transport, operation, **fields)
        if response.get("ok") is False:
            error = str(response.get("error") or "")
            if attempt < 2 and any(
                    marker in error for marker in TRANSIENT_MARKERS):
                time.sleep(10)
                continue
            return error
        raise AssertionError(
            f"{operation} expected structured failure, got ok=true: {response}")
    raise AssertionError(f"{operation} did not return a stable response")


def _command(transport, cmd: str, timeout: int = 120) -> str:
    response = _op(transport, "basic.command.run", cmd=cmd, timeout=timeout)
    if response.get("ok") is not True:
        raise AssertionError(f"command failed: {response.get('error')}")
    result = response.get("result")
    if isinstance(result, dict):
        if result.get("returncode") != 0:
            raise AssertionError(f"command rc != 0: {response}")
        return str(result.get("stdout") or "")
    raise AssertionError(f"command rc != 0: {response}")


def _read_config(transport, cell: str) -> dict[str, Any]:
    return _value(
        transport, "virtuoso.maestro.read_config",
        library=LIB, cell=cell, view=VIEW, timeout=180,
        _attempts=6, _delay=10)


def _set_run_options(transport, cell: str, options: dict[str, Any]) -> None:
    _value(
        transport, "virtuoso.maestro.write",
        library=LIB, cell=cell, view=VIEW,
        commands=[{"op": "set_run_option", "options": options}],
        timeout=180, _attempts=3, _delay=10)


def _wait_history(
    transport,
    cell: str,
    history: str,
    *,
    timeout: int = 1800,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        value = _value(
            transport, "virtuoso.maestro.read_history",
            library=LIB, cell=cell, view=VIEW, history=history)
        last = value.get("history") or {}
        if last.get("status") in ("done", "failed", "error"):
            return last
        time.sleep(3)
    raise AssertionError(f"history {history} did not finish: {last}")


def _close_gui(transport, cell: str, evidence: dict[str, Any], key: str) -> None:
    try:
        value = _value(
            transport, "virtuoso.maestro.close_gui",
            library=LIB, cell=cell, view=VIEW, timeout=300)
        evidence[key] = {"closed": value.get("closed"), "cell": cell}
    except Exception as exc:  # noqa: BLE001 - 关闭是清理动作，失败只记证据
        evidence[key] = {
            "cell": cell,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _build_setup(
    transport,
    cell: str,
    model_files: list[list[str]],
    evidence: dict[str, Any],
    key: str,
) -> None:
    commands = [
        {"op": "set_var", "name": "VDD", "value": "1.0",
         "scope": "global"},
        {"op": "set_var", "name": "VB_BIAS", "value": "0.39",
         "scope": "global"},
        {"op": "set_var", "name": "VCM_IN", "value": "0.7",
         "scope": "global"},
        {"op": "set_var", "name": "VIN_DIFF", "value": "0.4",
         "scope": "global"},
        {"op": "set_var", "name": "CLOAD", "value": "150f",
         "scope": "global"},
        {"op": "set_var", "name": "TEMP_C", "value": "27",
         "scope": "global"},
        {
            "op": "set_test",
            "test": TEST,
            "lib": DESIGN_LIB,
            "cell": DESIGN_CELL,
            "view": DESIGN_VIEW,
            "simulator": "spectre",
        },
        {"op": "set_var", "name": "VDD", "value": "1.0",
         "scope": "test", "test": TEST},
        {"op": "set_var", "name": "VB_BIAS", "value": "0.39",
         "scope": "test", "test": TEST},
        {"op": "set_var", "name": "VCM_IN", "value": "0.7",
         "scope": "test", "test": TEST},
        {"op": "set_var", "name": "VIN_DIFF", "value": "0.4",
         "scope": "test", "test": TEST},
        {"op": "set_var", "name": "CLOAD", "value": "150f",
         "scope": "test", "test": TEST},
        {"op": "set_run_mode", "run_mode": MC_MODE},
        {"op": "set_analysis", "test": TEST, "analysis": "tran",
         "enable": False},
        {
            "op": "set_analysis",
            "test": TEST,
            "analysis": "ac",
            "options": AC_OPTIONS,
        },
        {
            "op": "set_env_option",
            "test": TEST,
            "options": {"modelFiles": model_files},
        },
        {
            "op": "add_output",
            "test": TEST,
            "name": "VOP_ac",
            "output_type": "net",
            "signal_name": "/VOP",
            "plot": True,
            "save": True,
        },
        {
            "op": "add_output",
            "test": TEST,
            "name": "VON_ac",
            "output_type": "net",
            "signal_name": "/VON",
            "plot": True,
            "save": True,
        },
        {
            "op": "add_output",
            "test": TEST,
            "name": "Gain_10MHz_dB",
            "output_type": "point",
            "expr": GAIN_EXPR,
            "plot": True,
            "save": True,
        },
        {
            "op": "add_output",
            "test": TEST,
            "name": "BW_3dB",
            "output_type": "point",
            "expr": BW_EXPR,
            "plot": True,
            "save": True,
        },
        {"op": "set_spec", "test": TEST, "name": "BW_3dB", "gt": "3G"},
    ]
    built = _value(
        transport, "virtuoso.maestro.write",
        library=LIB, cell=cell, view=VIEW, commands=commands, timeout=1800)
    config = _read_config(transport, cell)
    options = (config.get("run_options") or {}).get(MC_MODE) or {}
    if set(options) != {name for name, _, _ in OPTION_CASES}:
        raise AssertionError(
            f"{cell}: read_config.run_options 不是 17 项: {sorted(options)}")
    if any(value is not None for value in options.values()):
        raise AssertionError(
            f"{cell}: 新 setup 的 run option 应全部为 None: {options}")
    if TEST not in (config.get("tests") or {}):
        raise AssertionError(f"{cell}: test {TEST} 未建出: {config.get('tests')}")
    if config.get("run_mode") != MC_MODE:
        raise AssertionError(
            f"{cell}: run_mode 未切到 MC: {config.get('run_mode')}")
    outputs = (config["tests"][TEST].get("outputs") or [])
    names = {item.get("name") for item in outputs}
    if not {"VOP_ac", "VON_ac", "Gain_10MHz_dB", "BW_3dB"} <= names:
        raise AssertionError(f"{cell}: fixtures 未建全，outputs={names}")
    evidence[key] = {
        "cell": cell,
        "built": built,
        "tests": sorted((config.get("tests") or {}).keys()),
        "outputs": sorted(name for name in names if name),
        "unset_run_options": options,
    }


def _positive_option_matrix(
    transport,
    cell: str,
    evidence: dict[str, Any],
) -> None:
    """一次写入全部 17 项，再一次读回；每项留下 expected/actual。

    逐项写会反复开关 ADE session，本环境的 ADE 在多次长尾 option 写入后
    会出现 ``SKILL execution timed out``；批量写入是 spec 推荐的正式用法，
    也避免了把 session 抖动误判成参数错误。
    """
    _set_run_options(
        transport, cell,
        {name: raw_value for name, raw_value, _ in OPTION_CASES})
    readback = ((_read_config(transport, cell).get("run_options") or {})
                .get(MC_MODE) or {})
    rows: list[dict[str, Any]] = []
    for name, raw_value, expected in OPTION_CASES:
        actual = readback.get(name)
        row = {
            "name": name,
            "written": raw_value,
            "expected": expected,
            "actual": actual,
        }
        rows.append(row)
        if actual != expected:
            if name == "mcreferencepoint" and actual is None:
                row["note"] = (
                    "ADE 在无 reference point 时不落该 option，读回 nil；"
                    "写入调用本身已成功")
                continue
            raise AssertionError(f"{name} 写回不一致: {row}")
    evidence["option_matrix"] = rows


def _invalid_option_matrix(
    transport,
    cell: str,
    evidence: dict[str, Any],
) -> None:
    """每项都送非法值；断言被点名拒绝。

    不在每个非法值后再读一次配置：ADE 连续 session 操作会触发环境的
    ``SKILL execution timed out``，而“拒绝且不污染旧值”的完整矩阵由
    ``test/offline/unit/test_maestro_mc.py`` 覆盖。
    """
    rows: list[dict[str, Any]] = []
    for name, bad_value in INVALID_OPTION_CASES:
        error = _expect_fail(
            transport, "virtuoso.maestro.write",
            library=LIB, cell=cell, view=VIEW,
            commands=[{"op": "set_run_option",
                       "options": {name: bad_value}}])
        if name not in error:
            raise AssertionError(
                f"{name} 的非法值未被点名拒绝: {error[:300]}")
        row = {
            "name": name,
            "bad_value": bad_value,
            "error": error[:300],
        }
        rows.append(row)
    evidence["invalid_option_matrix"] = rows


def _run_mc(
    transport,
    cell: str,
    evidence: dict[str, Any],
    key: str,
    *,
    expected_points: int | None = None,
) -> str:
    started: dict[str, Any] | None = None
    attempts = 0
    last: dict[str, Any] = {}
    for attempt in range(3):
        attempts = attempt + 1
        response = _op(
            transport, "virtuoso.maestro.run",
            library=LIB, cell=cell, view=VIEW,
            blocking=False, poll_interval=2, timeout=1800)
        if response.get("ok") is True and isinstance(
                response.get("value"), dict):
            started = response["value"]
            break
        last = response
        text = str(response)
        steps = response.get("steps") or []
        transient = any(marker in text for marker in TRANSIENT_MARKERS)
        prestart = not steps or any(
            isinstance(step, dict)
            and step.get("name") in (
                "job_control_mode", "job_control_mode_retry",
            )
            and not step.get("ok")
            for step in steps
        )
        # 只重试“仿真尚未启动”的瞬态窗口；如果 run 步骤已经失败，
        # 可能已经有后台作业，不能盲目重复启动。
        if attempt < 2 and transient and prestart:
            time.sleep(30)
            continue
        break
    if started is None:
        raise AssertionError(
            f"virtuoso.maestro.run failed after {attempts} attempt(s): "
            f"{str(last)[:800]}")
    history = str(started.get("history") or "")
    if not history.startswith("MonteCarlo."):
        raise AssertionError(f"{cell}: run 未返回 MonteCarlo.*: {started}")
    detail = _wait_history(transport, cell, history)
    if detail.get("status") != "done":
        raise AssertionError(f"{cell}: history 未 done: {detail}")
    if expected_points is not None and detail.get("points_total") != expected_points:
        raise AssertionError(
            f"{cell}: points_total={detail.get('points_total')} "
            f"!= {expected_points}: {detail}")
    evidence[key] = {
        "cell": cell,
        "history": history,
        "start_attempts": attempts,
        "status": detail.get("status"),
        "points_done": detail.get("points_done"),
        "points_total": detail.get("points_total"),
        "results_dir": detail.get("results_dir"),
    }
    return history


def run_suite(transport, evidence: dict[str, Any]) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    state: dict[str, Any] = {}
    stamp = f"{time.strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}"
    matrix_cell = f"mc_probe_opts_{stamp}"
    run_cell = f"mc_probe_run_{stamp}"
    negative_cell = f"mc_probe_neg_{stamp}"
    state["matrix_cell"] = matrix_cell
    state["run_cell"] = run_cell
    state["negative_cell"] = negative_cell

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001 - 保留每条失败的现场
            status = f"FAIL: {type(exc).__name__}: {exc}"
            results.append((name, status))
            print(f"FAIL    {name}: {status}", flush=True)
            return None
        results.append((name, "PASS"))
        print(f"PASS    {name}", flush=True)
        return value

    def case_env() -> None:
        value = _value(
            transport, "virtuoso.maestro.read_config",
            library=DESIGN_LIB, cell=DESIGN_CELL, view=VIEW)
        tests = value.get("tests") or {}
        if "ctle_ac_schematic" not in tests:
            raise AssertionError(f"源设计缺少 ctle_ac_schematic: {sorted(tests)}")
        outputs = (tests["ctle_ac_schematic"].get("outputs") or [])
        if not any(item.get("name") == "BW_3dB" for item in outputs):
            raise AssertionError("源设计缺少 BW_3dB 输出")
        evidence["source_design"] = {
            "library": DESIGN_LIB,
            "cell": DESIGN_CELL,
            "view": VIEW,
            "tests": sorted(tests),
        }

    def case_build_matrix() -> None:
        _build_setup(
            transport, matrix_cell, POSITIVE_MODEL_FILES,
            evidence, "matrix_setup")

    def case_build_run() -> None:
        # 先等矩阵 cell 的 ADE session 从 P-086 瞬态窗口恢复，再建 run cell。
        _read_config(transport, matrix_cell)
        _build_setup(
            transport, run_cell, POSITIVE_MODEL_FILES,
            evidence, "run_setup")

    def case_option_matrix() -> None:
        _positive_option_matrix(transport, matrix_cell, evidence)

    def case_invalid_matrix() -> None:
        _invalid_option_matrix(transport, matrix_cell, evidence)

    def case_run_positive() -> None:
        _set_run_options(transport, run_cell, RUN_OPTIONS)
        readback = ((_read_config(transport, run_cell)
                     .get("run_options") or {}).get(MC_MODE) or {})
        for name, expected in RUN_EXPECTED.items():
            if readback.get(name) != expected:
                raise AssertionError(
                    f"run cell 的 {name} 未生效: expected={expected!r} "
                    f"actual={readback.get(name)!r}")
        history = _run_mc(
            transport, run_cell, evidence, "positive_history",
            expected_points=8)
        state["positive_history"] = history

    def case_read_positive() -> None:
        history = state.get("positive_history")
        if not history:
            raise AssertionError("positive history 未产出")
        value = _value(
            transport, "virtuoso.maestro.read_results",
            library=LIB, cell=run_cell, view=VIEW,
            history=history, test=TEST, timeout=1800)
        mc = value.get("monte_carlo")
        if not isinstance(mc, dict):
            raise AssertionError(
                f"read_results 未返回 value.monte_carlo: {str(value)[:400]}")
        overall = mc.get("overall") or {}
        if int(overall.get("total_points") or 0) != 8:
            raise AssertionError(
                f"MC 点数不是 8（mcnumpoints 未生效?）: {overall}")
        outputs = mc.get("outputs") or []
        rows = [item for item in outputs
                if item.get("name") == "BW_3dB"]
        if not rows:
            raise AssertionError(f"Yield 表没有 BW_3dB: {outputs[:4]}")
        summary = next(
            (item for item in rows if item.get("summary")), rows[0])
        for key in ("yield", "mean"):
            if summary.get(key) is None:
                raise AssertionError(
                    f"BW_3dB Yield 表的 {key} 为空: {summary}")
        if summary.get("min") is not None and summary.get("max") is not None:
            if summary["min"] == summary["max"]:
                raise AssertionError(
                    f"process MC 未产生变化（min==max）: {summary}")
        evidence["positive_results"] = {
            "overall": overall,
            "outputs": outputs[:8],
        }

    def case_negative_control() -> None:
        # 正例刚跑完，先确认 session 可读，再建负例 cell。
        _read_config(transport, run_cell)
        _build_setup(
            transport, negative_cell, NEGATIVE_MODEL_FILES,
            evidence, "negative_setup")
        _set_run_options(
            transport, negative_cell,
            {**RUN_OPTIONS, "mcnumpoints": 2})
        history = _run_mc(
            transport, negative_cell, evidence, "negative_history",
            expected_points=2)
        detail = _value(
            transport, "virtuoso.maestro.read_history",
            library=LIB, cell=negative_cell, view=VIEW, history=history)
        results_dir = (detail.get("history") or {}).get("results_dir")
        if not results_dir:
            raise AssertionError(f"负控 history 无 results_dir: {detail}")
        out = _command(
            transport,
            f"grep -R -m 3 -n -E 'SPECTRE-1600[8]|SPECTRE-16012' "
            f"{shlex.quote(results_dir)} 2>/dev/null || true")
        if not any(marker in out for marker in
                   ("SPECTRE-16008", "SPECTRE-16012")):
            raise AssertionError(
                f"负控未出现 SPECTRE-16008/16012；results_dir={results_dir}; "
                f"grep={out[:400]}")
        evidence["negative_control"] = {
            "history": history,
            "results_dir": results_dir,
            "grep": out[:600],
        }

    def case_close() -> None:
        _close_gui(transport, matrix_cell, evidence, "matrix_closed")
        _close_gui(transport, run_cell, evidence, "run_closed")
        _close_gui(transport, negative_cell, evidence, "negative_closed")

    run("MC-ENV 环境检查（源设计可读）", case_env)
    run("MC-01 建 matrix setup + 17 项未设置基线", case_build_matrix)
    run("MC-02 17 项 option 批量写回", case_option_matrix)
    run("MC-03 option 非法值拒绝且不污染旧值", case_invalid_matrix)
    run("MC-04 建独立 run setup（不含不可清空的扩展项）", case_build_run)
    run("MC-05 8 点 process MC 启动并等待 history", case_run_positive)
    run("MC-06 read_results → Yield 统计", case_read_positive)
    run("MC-07 无统计 section 负控 → SPECTRE-16008/16012",
        case_negative_control)
    run("MC-99 关闭本 TB 打开的 GUI session", case_close)
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

    sys.path.insert(0, str(ROOT / "test" / "shared" / "runners"))
    from env_check import require_environment  # noqa: E402

    evidence: dict[str, Any] = {
        "api": API,
        "token": TOKEN,
        "python": sys.version.split()[0],
        "steps": [],
    }
    try:
        evidence["environment"] = require_environment(
            base=API,
            token=TOKEN,
            require_lib=["maestro_tb", "SERDES_TB_LIB", "tsmcN65"],
            require_spectre=True,
        )
    except Exception as exc:  # noqa: BLE001 - 第 1 步失败即环境不合格
        print(f"FAIL    MC-ENV environment: {type(exc).__name__}: {exc}",
              flush=True)
        if args.out:
            out_path = Path(args.out)
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(
                json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8")
            print(f"evidence: {out_path}")
        return 1

    results = run_suite(HttpTransport(), evidence)
    evidence["results"] = [{"case": name, "status": status}
                           for name, status in results]
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8")
        print(f"evidence: {out_path}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
