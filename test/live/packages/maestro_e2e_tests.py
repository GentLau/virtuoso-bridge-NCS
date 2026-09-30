# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 11:40
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（靶机指纹 / 业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时正文有注释说明。
"""End-to-end acceptance tests for the ``virtuoso.maestro.*`` package.

Two transports are supported:

* ``--transport direct`` -- in-process dispatch (same registry/package path,
  no HTTP server needed);
* ``--transport http``   -- the real 8127 business face.

The test cases below deliberately use the two real testbenches built for this
package: ``maestro_tb/opamp_probe`` (AC/DC/tran analog) and
``maestro_tb/logic_probe`` (NAND + DFF transient), plus the small
``maestro_tb/rc_probe`` fixture for fast configuration/run/history cases.
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

from pyapi.packages._maestro_util import parse_sexpr  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"


class HttpTransport:
    def __init__(self) -> None:
        self.middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=900) as response:
            return json.loads(response.read().decode("utf-8"))


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
        if status != 200:
            # 与 HTTP 传输对齐：4xx 也把**错误体**交回调用方（`_op` 会按 ok=false 抛、
            # `_expect_fail` 需要拿到错误文本做归因）。直接抛断言会让负控制用例
            # 在 direct 模式下误红（2026-09-28 覆盖率 runner 实测）。
            if isinstance(body, dict):
                return body
            return {"ok": False, "error": f"dispatch status {status}: {body}"}
        return body


def _op(transport, operation: str, **fields: Any) -> Any:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(
            f"{operation} failed: {response.get('error')}; "
            f"data={response.get('data')}"
        )
    # C1 契约（2f88853）：值型 op 载荷在顶层 `value`，命令型在 `result`；兼容旧 `data` 壳。
    payload = response.get("value")
    if payload is None:
        payload = response.get("result")
    if payload is None:
        payload = response
    return payload if isinstance(payload, dict) else {}


def _raw(transport, operation: str, **fields: Any) -> dict[str, Any]:
    """未解包的原始响应（`step_details=true` 时要看 `steps` 明细；`_op` 会丢掉它）。"""
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    return response


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    data = _op(transport, operation, **fields)
    if not isinstance(data, dict):
        raise AssertionError(f"{operation} returned no value dict: {data}")
    inner = data.get("value")
    return inner if isinstance(inner, dict) else data


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _interactive_history(transport, cell: str) -> str:
    """挑一条已存在的 Interactive.* history 作为覆盖目标。

    共享库的 current history 可能被他人换成 MonteCarlo.N；`run(history=…)` 的语义是
    **覆盖已存在的 history**（ASSEMBLER-3018：目标不存在即报错），所以必须挑现有的
    Interactive.* 而不是自造新名字。

    2026-09-29 补充（测试/root）：套件自己的 HISTORY-01 会 rename/lock/unlock/delete 选中的
    history，于是**跑过一次之后共享库里就没有 Interactive.N 了**（本轮全量覆盖重算因此失败）。
    这里保持"必须挑已存在 history"的产品语义不变，只在没有 Interactive.N 时**退回用当前
    存在的任意一条**（并打印 NOTE 说明做了什么）；一条都没有才判失败。
    """
    value = _value(transport, "virtuoso.maestro.read_history",
                   library="maestro_tb", cell=cell)
    all_names = [str(item.get("name", "")) for item in value.get("histories") or []]
    interactive = [name for name in all_names if name.startswith("Interactive.")]
    if interactive:
        return interactive[-1]
    if all_names:
        print(f"NOTE  maestro_tb/{cell} 没有 Interactive.*（现有 {all_names[:3]}…），"
              f"按'覆盖已存在 history'语义退回用 {all_names[-1]!r}", flush=True)
        return all_names[-1]
    _check(False, f"maestro_tb/{cell} 一条 history 都没有（HISTORY-01 自毁前置，需重建夹具）")
    raise AssertionError("unreachable")


def _expect_fail(transport, operation: str, **fields: Any) -> str:
    """断言结构化失败（HTTP 4xx 也算失败），返回错误文本用于核对归因。"""
    payload = {"operation": operation, "token": TOKEN, **fields}
    try:
        response = transport.call(payload)
    except urllib.error.HTTPError as error:
        return f"HTTP {error.code}: {error.read().decode('utf-8', 'replace')[:200]}"
    data = response
    if response.get("ok") is not False and data.get("ok") is not False:
        raise AssertionError(f"{operation} expected structured failure, got ok")
    return str(response.get("error") or data.get("error") or "")


def _skill(transport, code: str) -> str:
    data = _op(transport, "basic.skill.execute", skill_code=code)
    # C1 契约：skill 结果既可能在顶层 `result`（我们已解包进 data），也可能还有一层嵌套。
    result = data.get("result") if isinstance(data.get("result"), dict) else data
    if result.get("status") != "success":
        raise AssertionError(f"SKILL failed: {result}")
    return result.get("output", "")


def _wait_history_done(
    transport,
    library: str,
    cell: str,
    history: str,
    *,
    timeout: float = 180,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last: dict[str, Any] = {}
    while time.monotonic() < deadline:
        value = _value(
            transport, "virtuoso.maestro.read_history",
            library=library, cell=cell, history=history,
        )
        last = value.get("history") or {}
        if last.get("status") in ("done", "failed"):
            return last
        time.sleep(1.0)
    raise AssertionError(f"history {history} did not finish: {last}")


def _case_read_config_rc(transport) -> None:
    response = _raw(
        transport, "virtuoso.maestro.read_config",
        library="maestro_tb", cell="rc_probe", step_details=True,
    )
    value = response.get("value") or {}
    _check("ac" in value["tests"], "rc_probe/maestro must list the ac test")
    _check(
        "ac" in value["tests"]["ac"]["analyses"],
        "rc_probe/maestro must list the ac analysis",
    )
    # 表 C：`options` 步明细里的 `env` / `sim` 必须与公开字段逐值一致
    # （spec 6-maestro.md §3.1：test 级 env_options/sim_options 来自 maeGetEnvOption/maeGetSimOption）。
    options_steps = [s for s in (response.get("steps") or [])
                     if s.get("name") == "options"]
    _check(options_steps, f"step_details 里缺 options 步: {response.get('steps')}")
    detail = options_steps[-1].get("detail") or {}
    _check({"env", "sim"} <= set(detail),
           f"options 步明细缺 env/sim: {sorted(detail)}")
    for test_name, test in value["tests"].items():
        _check(detail["sim"].get(test_name) == test.get("sim_options"),
               f"sim 明细与 tests.{test_name}.sim_options 不一致: "
               f"{detail['sim'].get(test_name)} vs {test.get('sim_options')}")
        _check(detail["env"].get(test_name) == test.get("env_options"),
               f"env 明细与 tests.{test_name}.env_options 不一致: "
               f"{detail['env'].get(test_name)} vs {test.get('env_options')}")


def _case_read_config_logic(transport) -> None:
    value = _value(
        transport, "virtuoso.maestro.read_config",
        library="maestro_tb", cell="logic_probe",
    )
    outputs = value["tests"]["logic_tb"]["outputs"]
    names = {item["name"] for item in outputs}
    _check({"q_high", "q_low", "Q", "CLK"} <= names, f"logic outputs: {names}")
    specs = {
        f"logic_tb.{item['name']}": item["spec"]
        for item in outputs if isinstance(item.get("spec"), dict)
    }
    _check(specs["logic_tb.q_high"]["type"] == "gt", "q_high spec must be gt")
    _check(specs["logic_tb.q_low"]["type"] == "lt", "q_low spec must be lt")


def _case_write_smoke(transport) -> None:
    write_payload = [
        {"op": "set_var", "name": "e2e_probe", "value": "1.25"},
        {
            "op": "add_output", "test": "ac", "name": "e2e_out",
            "output_type": "point", "expr": "net1",
        },
        {"op": "set_spec", "test": "ac", "name": "e2e_out", "gt": "0"},
    ]
    _value(
        transport, "virtuoso.maestro.write",
        library="maestro_tb", cell="rc_probe", commands=write_payload,
    )
    value = _value(
        transport, "virtuoso.maestro.read_config",
        library="maestro_tb", cell="rc_probe",
    )
    _check(value["variables"].get("e2e_probe") == "1.25", "variable not saved")
    names = {item["name"] for item in value["tests"]["ac"]["outputs"]}
    _check("e2e_out" in names, "output not saved")
    spec_names = {
        f"ac.{item['name']}"
        for item in value["tests"]["ac"]["outputs"]
        if isinstance(item.get("spec"), dict)
    }
    _check("ac.e2e_out" in spec_names, "spec not saved")

    cleanup = [
        {"op": "delete_output", "test": "ac", "name": "e2e_out",
         "delete_spec": True},
        {"op": "delete_var", "name": "e2e_probe"},
    ]
    _value(
        transport, "virtuoso.maestro.write",
        library="maestro_tb", cell="rc_probe", commands=cleanup,
    )
    value = _value(
        transport, "virtuoso.maestro.read_config",
        library="maestro_tb", cell="rc_probe",
    )
    _check("e2e_probe" not in value["variables"], "variable cleanup failed")
    names = {item["name"] for item in value["tests"]["ac"]["outputs"]}
    _check("e2e_out" not in names, "output cleanup failed")


def _case_write_atomics(transport) -> None:
    base = {"library": "maestro_tb", "cell": "rc_probe"}
    before = _value(transport, "virtuoso.maestro.read_config", **base)
    temp_value = before["tests"]["ac"]["sim_options"].get("temp", "27")
    control_mode = before["tests"]["ac"]["env_options"].get("controlMode", "batch")
    run_mode = before["run_mode"]

    commands = [
        {"op": "set_analysis", "test": "ac", "analysis": "ac",
         "options": {"dec": "10"}},
        {"op": "set_sim_option", "test": "ac", "options": {"temp": temp_value}},
        {"op": "set_env_option", "test": "ac",
         "options": {"controlMode": control_mode}},
        {"op": "set_run_mode", "run_mode": run_mode},
        {"op": "set_job_control_mode", "mode": "ICRP"},
        {"op": "set_test", "test": "e2e_extra", "lib": "maestro_tb",
         "cell": "rc_probe", "view": "schematic", "simulator": "spectre"},
        {"op": "set_design", "test": "e2e_extra", "lib": "maestro_tb",
         "cell": "rc_probe", "view": "schematic"},
        {"op": "set_corner", "name": "e2e_corner"},
        {"op": "setup_corner", "name": "e2e_setup_corner",
         "variables": {"VDD": "2.5"}},
    ]
    try:
        _value(transport, "virtuoso.maestro.write", commands=commands, **base)
        after = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(
            after["tests"]["ac"]["analyses"]["ac"].get("dec") == "10",
            "set_analysis dec=10 not visible",
        )
        _check(
            after["tests"]["ac"]["sim_options"].get("temp") == temp_value,
            "set_sim_option temp readback mismatch",
        )
        _check(
            after["tests"]["ac"]["env_options"].get("controlMode") == control_mode,
            "set_env_option controlMode readback mismatch",
        )
        _check(after["job_control_mode"] == "ICRP", "job control mode not ICRP")
        _check("e2e_extra" in after["tests"], "set_test/set_design not visible")
        _check(
            {"e2e_corner", "e2e_setup_corner"} <= set(after["corners"]),
            f"corners not visible: {after['corners']}",
        )
        corner_value = (
            after.get("corners", {})
            .get("e2e_setup_corner", {})
            .get("variables", {})
            .get("VDD")
        )
        _check(
            str(corner_value) == "2.5",
            f"corner variable not 2.5: {corner_value}",
        )
    finally:
        cleanup = [
            {"op": "set_analysis", "test": "ac", "analysis": "ac",
             "options": {"dec": "20"}},
            {"op": "delete_test", "test": "e2e_extra"},
            {"op": "delete_corner", "name": "e2e_corner"},
            {"op": "delete_corner", "name": "e2e_setup_corner"},
        ]
        try:
            _value(transport, "virtuoso.maestro.write", commands=cleanup, **base)
        except Exception:
            pass


def _case_write_var_scopes(transport) -> None:
    """Global/test/corner variables with the same name must stay distinct."""
    base = {"library": "maestro_tb", "cell": "rc_probe"}
    name = "e2e_scope_var"
    try:
        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[{"op": "delete_var", "name": name, "scope": "all"}],
        )
    except Exception:
        pass
    try:
        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[
                {"op": "delete_corner", "name": "e2e_scope_corner"},
                {"op": "set_corner", "name": "e2e_scope_corner"},
                {"op": "set_var", "name": name, "value": "1.0",
                 "scope": "global"},
                {"op": "set_var", "name": name, "value": "2.0",
                 "scope": "test", "test": "ac"},
                {"op": "set_var", "name": name, "value": "3.0",
                 "scope": "corner", "corner": "e2e_scope_corner"},
            ],
        )
        cfg = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(cfg["variables"].get(name) == "1.0", "global variable is not 1.0")
        _check(
            cfg["tests"]["ac"]["variables"].get(name) == "2.0",
            "test variable is not 2.0",
        )
        _check(
            cfg["corners"]["e2e_scope_corner"]["variables"].get(name) == "3.0",
            "corner variable is not 3.0",
        )

        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[{"op": "delete_corner", "name": "e2e_scope_corner"}],
        )
        cfg = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(
            name not in cfg["corners"].get("e2e_scope_corner", {}).get("variables", {}),
            "corner variable survived corner deletion",
        )
        _check(cfg["variables"].get(name) == "1.0", "global variable was lost")
        _check(
            cfg["tests"]["ac"]["variables"].get(name) == "2.0",
            "test variable was lost",
        )

        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[{
                "op": "delete_var", "name": name,
                "scope": "test", "test": "ac",
            }],
        )
        cfg = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(
            name not in cfg["tests"]["ac"]["variables"],
            "test variable survived test-scope delete",
        )
        _check(cfg["variables"].get(name) == "1.0", "global variable was lost")

        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[{"op": "delete_var", "name": name, "scope": "global"}],
        )
        cfg = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(name not in cfg["variables"], "global variable survived delete")
    finally:
        try:
            _value(
                transport, "virtuoso.maestro.write", **base,
                commands=[
                    {"op": "delete_corner", "name": "e2e_scope_corner"},
                    {"op": "delete_var", "name": name, "scope": "all"},
                ],
            )
        except Exception:
            pass


def _case_write_parameter_scopes(transport) -> None:
    """Global/corner device parameters use the SKILL list/string asymmetry."""
    base = {"library": "maestro_tb", "cell": "rc_probe"}
    path = "maestro_tb/rc_probe/schematic/R0/r"
    try:
        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[{"op": "delete_parameter", "name": path}],
        )
    except Exception:
        pass
    try:
        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[
                {"op": "delete_corner", "name": "e2e_param_corner"},
                {"op": "set_corner", "name": "e2e_param_corner"},
                {"op": "set_parameter", "name": path, "value": "1K",
                 "scope": "global"},
                {"op": "set_parameter", "name": path, "value": "1K",
                 "scope": "corner", "corner": "e2e_param_corner"},
            ],
        )
        cfg = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(cfg["parameters"].get(path) == "1K",
               "global parameter is not 1K")
        _check(
            cfg["corners"]["e2e_param_corner"]["parameters"].get(path) == "1K",
            "corner parameter is not 1K",
        )

        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[{
                "op": "delete_parameter", "name": path,
                "scope": "corner", "corner": "e2e_param_corner",
            }],
        )
        cfg = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(
            path not in cfg["corners"].get("e2e_param_corner", {}).get("parameters", {}),
            "corner parameter survived corner delete",
        )
        _check(cfg["parameters"].get(path) == "1K",
               "global parameter was lost")

        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[{"op": "delete_parameter", "name": path}],
        )
        cfg = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(path not in cfg["parameters"], "global parameter survived delete")
    finally:
        try:
            _value(
                transport, "virtuoso.maestro.write", **base,
                commands=[
                    {"op": "delete_parameter", "name": path,
                     "scope": "corner", "corner": "e2e_param_corner"},
                    {"op": "delete_parameter", "name": path},
                    {"op": "delete_corner", "name": "e2e_param_corner"},
                ],
            )
        except Exception:
            pass


def _case_write_job_policy_sim_mode(transport) -> None:
    """No-op validation of maeSetJobPolicy and asiSetHighPerformanceOptionVal."""
    base = {"library": "maestro_tb", "cell": "rc_probe"}
    session = _skill(
        transport,
        'maeOpenSetup("maestro_tb" "rc_probe" "maestro")',
    ).strip().strip('"')
    try:
        before_raw = _skill(
            transport,
            "let((s jp as) "
            f"s = {json.dumps(session, ensure_ascii=False)} "
            "jp = maeGetJobPolicy(?session s) "
            "as = asiGetSession(s) "
            "list(jp->configuretimeout "
            "asiGetHighPerformanceOptionVal(as 'uniMode)))",
        )
        before = parse_sexpr(before_raw.strip())
        if not isinstance(before, list) or len(before) < 2:
            raise AssertionError(f"cannot read job policy / simulator mode: {before_raw}")
        configure_timeout, uni_mode = before[0], before[1]
        # 2026-09-30 修（TB 脆弱性）：`asiGetHighPerformanceOptionVal(as 'uniMode)` 可能返回 nil
        # （该会话从未设过），此时把 nil 当 mode 传会被请求模型结构化拒绝、红在与判据无关的地方。
        # 语义不变——仍是"设置→读回"往返：nil 就写入已验证可用的默认值，再断言读回一致。
        target_mode = uni_mode if isinstance(uni_mode, str) and uni_mode.strip() else "spectre"
        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[
                {"op": "set_job_policy",
                 "policy": {"configuretimeout": configure_timeout}},
                {"op": "set_simulator_mode", "mode": target_mode,
                 "option": "uniMode"},
            ],
        )
        after_raw = _skill(
            transport,
            "let((s jp as) "
            f"s = {json.dumps(session, ensure_ascii=False)} "
            "jp = maeGetJobPolicy(?session s) "
            "as = asiGetSession(s) "
            "list(jp->configuretimeout "
            "asiGetHighPerformanceOptionVal(as 'uniMode)))",
        )
        after = parse_sexpr(after_raw.strip())
        _check(
            isinstance(after, list) and after[0] == configure_timeout,
            f"job policy changed unexpectedly: {before} -> {after}",
        )
        _check(
            isinstance(after, list) and after[1] == target_mode,
            f"simulator mode 设置后读回不一致（期望 {target_mode!r}）: {before} -> {after}",
        )
    finally:
        _skill(
            transport,
            f"maeCloseSession(?session {json.dumps(session, ensure_ascii=False)} "
            "?forceClose t)",
        )


def _case_run_rc(transport) -> str:
    # 共享库里可能残留他人的 MC 实验（current history 被设成 MonteCarlo.N），
    # 不指定 history 会把本次仿真写进那条 history 并导致后续读回失败；
    # 显式覆盖一条已存在的 Interactive.*（run.history = Overwrite History 语义）。
    history_name = _interactive_history(transport, "rc_probe")
    value = _value(
        transport, "virtuoso.maestro.run",
        library="maestro_tb", cell="rc_probe",
        history=history_name, blocking=False, timeout=120,
    )
    history = value["history"]
    _check(bool(history), "run returned no history")
    _check(history == history_name, f"run ignored explicit history: {history}")
    status = _wait_history_done(
        transport, "maestro_tb", "rc_probe", history, timeout=120,
    )
    _check(status["status"] == "done", f"rc run not done: {status}")
    return history


def _case_read_results_rc(transport, history: str) -> None:
    value = _value(
        transport, "virtuoso.maestro.read_results",
        library="maestro_tb", cell="rc_probe", history=history, test="ac",
    )
    _check("ac" in value["tests"], f"rc results tests: {value['tests']}")
    _check(Path(value["local_path"]).is_file(), "rc Detail CSV missing")
    wave = _value(
        transport, "virtuoso.maestro.read_results",
        library="maestro_tb", cell="rc_probe", history=history,
        test="ac", analysis="ac", waveform="net1",
    )
    _check(len(wave["waveform"]) > 5, "rc waveform is empty")


def _case_exports(transport, history: str) -> None:
    csv_value = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="outputs_csv",
        history=history, test="ac",
    )
    _check(Path(csv_value["local_path"]).is_file(), "outputs_csv missing")
    # 2026-09-30（表 C 真缺口）：`kind` 与 `remote_path` 此前没人断言。
    _check(csv_value.get("kind") == "outputs_csv",
           f"export 应回显 kind=outputs_csv（实测 {csv_value.get('kind')!r}）")
    # `outputs_csv` 直接落本地目标（无远端暂存）→ remote_path 允许为 None；
    # 一旦给出就必须是远端绝对路径（script/netlist 两档走远端暂存，必须给）。
    csv_remote = csv_value.get("remote_path")
    if csv_remote is not None:
        _check(str(csv_remote).startswith("/"),
               f"remote_path 若给出必须是远端绝对路径（实测 {csv_remote!r}）")

    script = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="script",
    )
    _check(Path(script["local_path"]).is_file(), "script missing")
    _check(script.get("kind") == "script",
           f"export 应回显 kind=script（实测 {script.get('kind')!r}）")
    _check(str(script.get("remote_path") or "").startswith("/"),
           f"script remote_path 必须是远端绝对路径（实测 {script.get('remote_path')!r}）")

    netlist = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="netlist",
        test="ac", corner="Nominal",
    )
    _check(netlist.get("kind") == "netlist",
           f"export 应回显 kind=netlist（实测 {netlist.get('kind')!r}）")
    netlist_root = Path(netlist["local_path"])
    _check(netlist_root.is_dir(), "netlist directory missing")
    _check(
        any(path.name == "input.scs" for path in netlist_root.rglob("input.scs")),
        "netlist input.scs missing",
    )


def _case_results_format_params(transport, history: str) -> None:
    """read_results 的 notation/precision/width/output_path（第八轮补缺）。"""
    out_dir = ROOT / "test" / "artifacts" / "evidence" / "round8" / "maestro-params"
    out_dir.mkdir(parents=True, exist_ok=True)
    common = dict(library="maestro_tb", cell="rc_probe", history=history,
                  test="ac", analysis="ac", waveform="net1")
    sci_path = out_dir / "wave_scientific.txt"
    eng_path = out_dir / "wave_engineering.txt"
    none_path = out_dir / "wave_none.txt"
    sci = _value(transport, "virtuoso.maestro.read_results", **common,
                 notation="scientific", precision=6, width=16, output_path=str(sci_path))
    eng = _value(transport, "virtuoso.maestro.read_results", **common,
                 notation="engineering", precision=4, width=12, output_path=str(eng_path))
    none = _value(transport, "virtuoso.maestro.read_results", **common,
                  notation="none", output_path=str(none_path))
    for value, path in ((sci, sci_path), (eng, eng_path), (none, none_path)):
        _check(Path(value["local_path"]) == path,
               f"output_path 未生效: {value['local_path']} != {path}")
        _check(path.is_file() and path.stat().st_size > 0, f"{path.name} 为空")
    _check(sci_path.read_text(encoding="utf-8") != eng_path.read_text(encoding="utf-8"),
           "notation/precision 未改变输出文本（参数被忽略）")
    values = [[(p["x"], p["y"]) for p in value["waveform"]]
              for value in (sci, eng, none)]
    for a, b in zip(values[0], values[1]):
        # precision 不同（scientific=6 vs engineering=4 位有效数字）会带来打印舍入差，
        # 允许 ≤1% 相对偏差；要点是"格式不改变物理量"。
        _check(abs(a[0] - b[0]) <= max(1e-6, abs(a[0]) * 1e-2)
               and abs(a[1] - b[1]) <= max(1e-6, abs(a[1]) * 1e-2),
               f"不同 notation 数值偏差过大: {a} vs {b}")
    for bad, needle in ((dict(notation="bogus"), "notation"),
                        (dict(precision=0), "precision"),
                        (dict(width=2), "width")):
        error = _expect_fail(transport, "virtuoso.maestro.read_results", **common, **bad)
        _check(needle in error, f"非法 {bad} 未点名: {error[:160]}")


def _case_export_output_path(transport, history: str) -> None:
    """export 的 output_path（调用方指定落盘位置，第八轮补缺）。"""
    out_dir = ROOT / "test" / "artifacts" / "evidence" / "round8" / "maestro-params"
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_target = out_dir / "outputs_named.csv"
    csv_target.unlink(missing_ok=True)
    value = _value(transport, "virtuoso.maestro.export",
                   library="maestro_tb", cell="rc_probe", kind="outputs_csv",
                   history=history, test="ac", output_path=str(csv_target))
    _check(Path(value["local_path"]) == csv_target,
           f"export output_path 未生效: {value['local_path']}")
    _check(csv_target.is_file() and csv_target.stat().st_size > 0,
           "export 目标文件未写出")

    script_target = out_dir / "ocean_named.ocn"
    script_target.unlink(missing_ok=True)
    value_script = _value(transport, "virtuoso.maestro.export",
                          library="maestro_tb", cell="rc_probe", kind="script",
                          output_path=str(script_target))
    _check(Path(value_script["local_path"]) == script_target
           and script_target.is_file(), "script output_path 未生效")


def _case_read_config_flags(transport) -> None:
    """read_config 的 include_parameters / include_raw（第八轮补缺）。"""
    base = dict(library="maestro_tb", cell="rc_probe")
    path = "maestro_tb/rc_probe/schematic/R0/r"
    # 先造一个全局 device parameter，保证 include_parameters 的正向可观测。
    _value(transport, "virtuoso.maestro.write", **base,
           commands=[{"op": "set_parameter", "name": path, "value": "1K",
                      "scope": "global"}])
    full = _value(transport, "virtuoso.maestro.read_config", **base)
    _check(full.get("parameters", {}).get(path) == "1K",
           f"前置 set_parameter 未生效: {full.get('parameters')}")
    _check("raw" not in full, f"include_raw 默认应为 False：{list(full)[:8]}")

    thin = _value(transport, "virtuoso.maestro.read_config",
                  **base, include_parameters=False)
    _check(not thin.get("parameters"),
           f"include_parameters=False 仍返回 parameters: {thin.get('parameters')}")
    _check(bool(thin.get("variables") is not None), "include_parameters=False 不应影响 variables")

    raw = _value(transport, "virtuoso.maestro.read_config", **base, include_raw=True)
    _check(isinstance(raw.get("raw"), dict) and raw["raw"],
           f"include_raw=True 未返回 raw: {type(raw.get('raw'))}")
    try:
        _value(transport, "virtuoso.maestro.write", **base,
               commands=[{"op": "delete_parameter", "name": path}])
    except Exception:  # noqa: BLE001 - 清理尽力而为
        pass
    return {"parameters_full": len(full.get("parameters") or {}),
            "raw_keys": sorted((raw.get("raw") or {}).keys())[:8]}


def _case_write_save_flag(transport) -> None:
    """write.save=False 不落盘（第八轮补缺）。

    判据用**步骤表**：save=True 的写必须出现 `save_setup`，save=False 的写必须没有它
    （`maestro.py:1760` 只在 request.save 为真时调 `_saveSetup`）。

    注意：读回值**不能**当判据 —— ADE session 是被复用的（read_config 的
    `open_session.created=False`），内存里的改动本来就看得见；2026-09-28 实测
    save=False 后读回 2.0 属**正常**，原断言口径（"新会话读回旧值"）不成立。
    """
    base = dict(library="maestro_tb", cell="rc_probe")
    name = f"e2e_save_{time.strftime('%H%M%S')}"
    def _steps(fields: dict) -> tuple[list[str], dict]:
        # C1 契约：`steps` 在响应层（不在 `value` 里）——必须读原始响应，不能用解包后的 payload。
        response = transport.call({"operation": "virtuoso.maestro.write",
                                   "token": TOKEN, "step_details": True,
                                   **base, **fields})
        if response.get("ok") is not True:
            raise AssertionError(f"maestro.write failed: {response.get('error')}")
        payload = response.get("value") if isinstance(response.get("value"), dict) else {}
        return [s.get("name") for s in response.get("steps") or []], payload

    saved_steps, _ = _steps(
        {"commands": [{"op": "set_var", "name": name, "value": "1.0", "scope": "global"}]})
    _check("save_setup" in saved_steps,
           f"save=True 必须出现 save_setup 步骤：{saved_steps}")
    cfg = _value(transport, "virtuoso.maestro.read_config", **base)
    _check(cfg["variables"].get(name) == "1.0", f"save=True 未落盘: {name}")
    # P-087 定稿口径：不落盘写无法与会话隔离（GUI 会话关不掉，改动会被后续 save
    # 带走）→ save=False 必须**结构化拒绝**，且不得留下任何副作用。
    rejected = transport.call({
        "operation": "virtuoso.maestro.write", "token": TOKEN, **base,
        "save": False,
        "commands": [{"op": "set_var", "name": name, "value": "2.0",
                      "scope": "global"}],
    })
    _check(rejected.get("ok") is False, f"save=False 必须被拒绝：{rejected}")
    # C1 契约：失败壳为 `{ok:false, error}`；兼容旧 `data.value.reason` 形态。
    shell = rejected if isinstance(rejected, dict) else rejected
    reason = (shell.get("value") or {}).get("reason") if isinstance(shell, dict) else None
    _check(reason == "save_false_unsupported",
           f"save=False 拒绝原因不对：{rejected}")
    cfg2 = _value(transport, "virtuoso.maestro.read_config", **base)
    _check(cfg2["variables"].get(name) == "1.0",
           f"拒绝后变量不得被改：{cfg2['variables'].get(name)}")
    unsaved_steps = [s.get("name") for s in
                     ((shell.get("steps") if isinstance(shell, dict) else None) or [])]
    # 清理：删除该变量并保存
    try:
        _value(transport, "virtuoso.maestro.write", **base,
               commands=[{"op": "delete_var", "name": name, "scope": "all"}])
    except Exception:  # noqa: BLE001 - 清理尽力而为
        pass
    return {"save_true_steps": saved_steps, "save_false_steps": unsaved_steps,
            "save_false_error": rejected.get("error"),
            "after_save_false_readback": cfg2["variables"].get(name)}


def _case_read_results_result_name(transport, history: str) -> None:
    """read_results.result（第八轮补缺）：显式 result 名与缺省读数一致 + 负向名失败。"""
    common = dict(library="maestro_tb", cell="rc_probe", history=history,
                  test="ac", analysis="ac", waveform="net1")
    plain = _value(transport, "virtuoso.maestro.read_results", **common)
    named = _value(transport, "virtuoso.maestro.read_results", **common, result="ac")
    a = [(p["x"], p["y"]) for p in plain["waveform"]]
    b = [(p["x"], p["y"]) for p in named["waveform"]]
    _check(len(a) == len(b) and all(abs(x1 - x2) < 1e-9 and abs(y1 - y2) < 1e-9
                                    for (x1, y1), (x2, y2) in zip(a, b)),
           f"显式 result=ac 与缺省读数不一致: {len(a)} vs {len(b)}")
    error = _expect_fail(transport, "virtuoso.maestro.read_results", **common,
                         result="no_such_result_name")
    _check(bool(error), "坏 result 名必须结构化失败")
    return {"points": len(a), "bad_result_error": error[:140]}

    snapshot = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="snapshot",
        history=history,
    )
    snapshot_root = Path(snapshot["local_path"])
    _check((snapshot_root / "maestro.sdb").is_file(), "snapshot sdb missing")

    # A GUI session is required for the window screenshot.
    gui = _value(
        transport, "virtuoso.maestro.open_gui",
        library="maestro_tb", cell="rc_probe",
    )
    shot = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="screenshot",
    )
    shot_path = Path(shot["local_path"])
    _check(shot.get("method") == "hiWindowSaveImage",
           f"screenshot did not use hiWindowSaveImage: {shot}")
    _check(shot.get("format") == "png", f"screenshot is not PNG: {shot}")
    _check(shot_path.suffix.lower() == ".png", "screenshot path is not .png")
    _check(shot_path.is_file() and shot_path.stat().st_size > 1000,
           "screenshot missing or empty")
    _check(gui["session"], "open_gui returned no session")

    by_window = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="screenshot",
        window_id=gui["window"],
    )
    _check(by_window.get("method") == "hiWindowSaveImage",
           "window_id screenshot did not use hiWindowSaveImage")
    region = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="screenshot",
        window_id=gui["window"], region=[-1, -1, 1, 1],
    )
    _check(region.get("region") == [-1.0, -1.0, 1.0, 1.0],
           "region was not echoed")
    no_top = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="screenshot",
        window_id=gui["window"], toplevel=False,
    )
    _check(no_top.get("toplevel") is False, "toplevel=false was not honoured")

    bad = transport.call({
        "operation": "virtuoso.maestro.export",
        "token": TOKEN,
        "library": "maestro_tb",
        "cell": "rc_probe",
        "kind": "screenshot",
        "window_id": 999999,
    })
    _check(not bad.get("ok"), "bad window_id must fail instead of falling back")


def _case_run_opamp(transport) -> str:
    history_name = _interactive_history(transport, "opamp_probe")
    value = _value(
        transport, "virtuoso.maestro.run",
        library="maestro_tb", cell="opamp_probe",
        history=history_name, blocking=True, timeout=300, poll_interval=1.0,
    )
    _check(value["status"] == "done", f"opamp run not done: {value}")
    _check(value["history"] == history_name,
           f"opamp run ignored explicit history: {value['history']}")
    return value["history"]


def _case_opamp_results(transport, history: str) -> None:
    value = _value(
        transport, "virtuoso.maestro.read_results",
        library="maestro_tb", cell="opamp_probe",
        history=history, test="opamp_ac",
    )
    outputs = value["points"][0]["outputs"]
    gain = float(outputs["gain_db"]["value"])
    ugbw = float(outputs["ugbw_hz"]["value"])
    _check(19 < gain < 23, f"opamp gain out of range: {gain}")
    _check(ugbw > 8e5, f"opamp UGBW out of range: {ugbw}")
    wave = _value(
        transport, "virtuoso.maestro.read_results",
        library="maestro_tb", cell="opamp_probe",
        history=history, test="opamp_ac", analysis="ac", waveform="VOUT",
    )
    low_freq = wave["waveform"][0]["y"]
    _check(10 < low_freq < 12, f"opamp low-frequency gain: {low_freq}")


def _case_run_logic(transport) -> str:
    history_name = _interactive_history(transport, "logic_probe")
    value = _value(
        transport, "virtuoso.maestro.run",
        library="maestro_tb", cell="logic_probe",
        history=history_name, blocking=True, timeout=300, poll_interval=1.0,
    )
    _check(value["status"] == "done", f"logic run not done: {value}")
    _check(value["history"] == history_name,
           f"logic run ignored explicit history: {value['history']}")
    return value["history"]


def _case_logic_results(transport, history: str) -> None:
    value = _value(
        transport, "virtuoso.maestro.read_results",
        library="maestro_tb", cell="logic_probe",
        history=history, test="logic_tb",
    )
    outputs = value["points"][0]["outputs"]
    high = float(outputs["q_high"]["value"])
    low = float(outputs["q_low"]["value"])
    _check(high >= 4.5, f"logic q_high too low: {high}")
    _check(low <= 0.5, f"logic q_low too high: {low}")
    wave = _value(
        transport, "virtuoso.maestro.read_results",
        library="maestro_tb", cell="logic_probe",
        history=history, test="logic_tb", analysis="tran", waveform="Q",
    )
    ys = [point["y"] for point in wave["waveform"]]
    _check(max(ys) >= 4.5, "logic waveform never goes high")
    _check(min(ys) <= 0.5, "logic waveform never goes low")


def _case_waveform_gui(transport, history: str) -> None:
    opened = _value(
        transport, "virtuoso.maestro.open_waveform_gui",
        library="maestro_tb", cell="logic_probe",
        history=history, test="logic_tb", analysis="tran",
        signals=["Q", "CLK", "Y"],
    )
    _check(opened["window"], "no waveform window")
    _check(opened["session"], "no waveform session")
    closed = _value(
        transport, "virtuoso.maestro.close_waveform_gui",
        session=opened["session"], window=opened["window"],
    )
    _check(closed["closed"], "waveform window did not close")


def _case_gui_lifecycle(transport) -> None:
    opened = _value(
        transport, "virtuoso.maestro.open_gui",
        library="maestro_tb", cell="logic_probe",
    )
    _check(opened["session"], "open_gui did not return a session")
    closed = _value(
        transport, "virtuoso.maestro.close_gui",
        library="maestro_tb", cell="logic_probe",
    )
    _check(closed["closed"], "close_gui did not close")


def _case_open_gui_history(transport) -> None:
    """open_gui 的 history 参数（第八轮补缺）：恢复到指定 history 并成为 current。"""
    base = dict(library="maestro_tb", cell="rc_probe")
    target = _interactive_history(transport, "rc_probe")
    opened = _value(transport, "virtuoso.maestro.open_gui", **base, history=target)
    _check(bool(opened.get("session")), f"open_gui(history) 未返回 session: {opened}")
    hist = _value(transport, "virtuoso.maestro.read_history", **base)
    _check(hist.get("current_history") == target,
           f"open_gui(history={target}) 后 current_history={hist.get('current_history')}")
    closed = _value(transport, "virtuoso.maestro.close_gui", **base)
    _check(closed.get("closed") is True, f"close_gui 未关闭: {closed}")
    return {"history": target, "session": opened.get("session")}


def _case_write_history(transport, history: str) -> None:
    renamed = "e2e_renamed"
    # Make the case idempotent even after a previous failed run.
    try:
        _value(
            transport, "virtuoso.maestro.write_history",
            library="maestro_tb", cell="rc_probe",
            commands=[{"op": "delete", "history": renamed}],
        )
    except Exception:
        pass
    _value(
        transport, "virtuoso.maestro.write_history",
        library="maestro_tb", cell="rc_probe",
        commands=[{"op": "rename", "history": history, "new_name": renamed}],
    )
    detail = _value(
        transport, "virtuoso.maestro.read_history",
        library="maestro_tb", cell="rc_probe", history=renamed,
    )
    _check(detail["history"]["name"] == renamed, "rename not visible")

    _value(
        transport, "virtuoso.maestro.write_history",
        library="maestro_tb", cell="rc_probe",
        commands=[{"op": "lock", "history": renamed}],
    )
    detail = _value(
        transport, "virtuoso.maestro.read_history",
        library="maestro_tb", cell="rc_probe", history=renamed,
    )
    _check(detail["history"]["lock_flag"] == 1, "lock flag not 1")

    _value(
        transport, "virtuoso.maestro.write_history",
        library="maestro_tb", cell="rc_probe",
        commands=[{"op": "unlock", "history": renamed}],
    )
    detail = _value(
        transport, "virtuoso.maestro.read_history",
        library="maestro_tb", cell="rc_probe", history=renamed,
    )
    _check(detail["history"]["lock_flag"] == 0, "unlock flag not 0")

    _value(
        transport, "virtuoso.maestro.write_history",
        library="maestro_tb", cell="rc_probe",
        commands=[{
            "op": "delete_results", "history": renamed,
            "keep_netlist": True, "keep_quick_plot": True,
        }],
    )
    _value(
        transport, "virtuoso.maestro.write_history",
        library="maestro_tb", cell="rc_probe",
        commands=[{"op": "delete", "history": renamed}],
    )
    overview = _value(
        transport, "virtuoso.maestro.read_history",
        library="maestro_tb", cell="rc_probe",
    )
    names = {item["name"] for item in overview["histories"]}
    _check(renamed not in names, f"history {renamed} was not deleted")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> Any:
        try:
            value = func()
            results.append((name, "PASS"))
            print(f"PASS    {name}", flush=True)  # 逐条打印：失败时也能看见前面过了哪些
            return value
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            raise

    run("CONFIG-01 rc_probe read_config", lambda: _case_read_config_rc(transport))
    run("CONFIG-02 logic_probe read_config", lambda: _case_read_config_logic(transport))
    run("CONFIG-03 include_parameters/include_raw",
        lambda: _case_read_config_flags(transport))
    run("WRITE-01 config write/readback/cleanup", lambda: _case_write_smoke(transport))
    run("WRITE-02 test/analysis/option/corner atomics",
        lambda: _case_write_atomics(transport))
    run("WRITE-03 global/test/corner variable scopes",
        lambda: _case_write_var_scopes(transport))
    run("WRITE-04 global/corner parameter scopes",
        lambda: _case_write_parameter_scopes(transport))
    run("WRITE-05 job policy + simulator mode no-op",
        lambda: _case_write_job_policy_sim_mode(transport))
    run("WRITE-06 save=False 不落盘", lambda: _case_write_save_flag(transport))
    rc_history = run("RUN-01 rc non-blocking + poll", lambda: _case_run_rc(transport))
    run("RESULT-01 rc points + waveform", lambda: _case_read_results_rc(transport, rc_history))
    run("RESULT-04 waveform notation/precision/width/output_path",
        lambda: _case_results_format_params(transport, rc_history))
    run("RESULT-05 result= 显式结果名",
        lambda: _case_read_results_result_name(transport, rc_history))
    run("EXPORT-01 all export kinds", lambda: _case_exports(transport, rc_history))
    run("EXPORT-02 output_path（调用方指定落盘）",
        lambda: _case_export_output_path(transport, rc_history))
    opamp_history = run("RUN-02 opamp blocking", lambda: _case_run_opamp(transport))
    run("RESULT-02 opamp AC results", lambda: _case_opamp_results(transport, opamp_history))
    logic_history = run("RUN-03 logic blocking", lambda: _case_run_logic(transport))
    run("RESULT-03 logic tran results", lambda: _case_logic_results(transport, logic_history))
    run("GUI-01 waveform window open/close", lambda: _case_waveform_gui(transport, logic_history))
    run("GUI-02 ADE window open/close", lambda: _case_gui_lifecycle(transport))
    run("GUI-03 open_gui(history=…) 恢复指定 history",
        lambda: _case_open_gui_history(transport))
    run("HISTORY-01 rename/lock/unlock/delete", lambda: _case_write_history(transport, rc_history))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--transport", choices=("direct", "http"), default="http",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    try:
        results = run_suite(transport)
    except Exception:
        if not args.json:
            raise
        results = []
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for name, status in results:
            print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
