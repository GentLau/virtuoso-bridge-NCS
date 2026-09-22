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
WORK_DIR = ROOT / "test" / "tb" / "artifacts" / "log-vblog"


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
            raise AssertionError(f"dispatch HTTP-like status {status}: {body}")
        return body


def _op(transport, operation: str, **fields: Any) -> Any:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(
            f"{operation} failed: {response.get('error')}; "
            f"data={response.get('data')}"
        )
    return response["data"]


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    data = _op(transport, operation, **fields)
    value = data.get("value")
    if not isinstance(value, dict):
        raise AssertionError(f"{operation} returned no value dict: {data}")
    return value


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _skill(transport, code: str) -> str:
    data = _op(transport, "basic.skill.execute", skill_code=code)
    result = data.get("result", {})
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
    value = _value(
        transport, "virtuoso.maestro.read_config",
        library="maestro_tb", cell="rc_probe",
    )
    _check("ac" in value["tests"], "rc_probe/maestro must list the ac test")
    _check(
        "ac" in value["analyses"]["ac"],
        "rc_probe/maestro must list the ac analysis",
    )


def _case_read_config_logic(transport) -> None:
    value = _value(
        transport, "virtuoso.maestro.read_config",
        library="maestro_tb", cell="logic_probe",
    )
    outputs = value["outputs"].get("logic_tb", [])
    names = {item["name"] for item in outputs}
    _check({"q_high", "q_low", "Q", "CLK"} <= names, f"logic outputs: {names}")
    specs = {entry["name"]: entry for entry in value["specs"]}
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
    names = {item["name"] for item in value["outputs"].get("ac", [])}
    _check("e2e_out" in names, "output not saved")
    spec_names = {entry["name"] for entry in value["specs"]}
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
    names = {item["name"] for item in value["outputs"].get("ac", [])}
    _check("e2e_out" not in names, "output cleanup failed")


def _case_write_atomics(transport) -> None:
    base = {"library": "maestro_tb", "cell": "rc_probe"}
    before = _value(transport, "virtuoso.maestro.read_config", **base)
    temp_value = before["sim_options"]["ac"].get("temp", "27")
    control_mode = before["env_options"]["ac"].get("controlMode", "batch")
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
            after["analyses"]["ac"]["ac"].get("dec") == "10",
            "set_analysis dec=10 not visible",
        )
        _check(
            after["sim_options"]["ac"].get("temp") == temp_value,
            "set_sim_option temp readback mismatch",
        )
        _check(
            after["env_options"]["ac"].get("controlMode") == control_mode,
            "set_env_option controlMode readback mismatch",
        )
        _check(after["job_control_mode"] == "ICRP", "job control mode not ICRP")
        _check("e2e_extra" in after["tests"], "set_test/set_design not visible")
        _check(
            {"e2e_corner", "e2e_setup_corner"} <= set(after["corners"]),
            f"corners not visible: {after['corners']}",
        )
        corner_value = (
            after.get("corner_variables", {})
            .get("e2e_setup_corner", {})
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
            cfg["test_variables"]["ac"].get(name) == "2.0",
            "test variable is not 2.0",
        )
        _check(
            cfg["corner_variables"]["e2e_scope_corner"].get(name) == "3.0",
            "corner variable is not 3.0",
        )

        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[{"op": "delete_corner", "name": "e2e_scope_corner"}],
        )
        cfg = _value(transport, "virtuoso.maestro.read_config", **base)
        _check(
            name not in cfg["corner_variables"].get("e2e_scope_corner", {}),
            "corner variable survived corner deletion",
        )
        _check(cfg["variables"].get(name) == "1.0", "global variable was lost")
        _check(
            cfg["test_variables"]["ac"].get(name) == "2.0",
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
            name not in cfg["test_variables"]["ac"],
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
            cfg["corner_parameters"]["e2e_param_corner"].get(path) == "1K",
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
            path not in cfg["corner_parameters"].get("e2e_param_corner", {}),
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
        _value(
            transport, "virtuoso.maestro.write", **base,
            commands=[
                {"op": "set_job_policy",
                 "policy": {"configuretimeout": configure_timeout}},
                {"op": "set_simulator_mode", "mode": uni_mode,
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
            isinstance(after, list) and after[1] == uni_mode,
            f"simulator mode changed unexpectedly: {before} -> {after}",
        )
    finally:
        _skill(
            transport,
            f"maeCloseSession(?session {json.dumps(session, ensure_ascii=False)} "
            "?forceClose t)",
        )


def _case_run_rc(transport) -> str:
    value = _value(
        transport, "virtuoso.maestro.run",
        library="maestro_tb", cell="rc_probe",
        blocking=False, timeout=120,
    )
    history = value["history"]
    _check(bool(history), "run returned no history")
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

    script = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="script",
    )
    _check(Path(script["local_path"]).is_file(), "script missing")

    netlist = _value(
        transport, "virtuoso.maestro.export",
        library="maestro_tb", cell="rc_probe", kind="netlist",
        test="ac", corner="Nominal",
    )
    netlist_root = Path(netlist["local_path"])
    _check(netlist_root.is_dir(), "netlist directory missing")
    _check(
        any(path.name == "input.scs" for path in netlist_root.rglob("input.scs")),
        "netlist input.scs missing",
    )

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
    value = _value(
        transport, "virtuoso.maestro.run",
        library="maestro_tb", cell="opamp_probe",
        blocking=True, timeout=300, poll_interval=1.0,
    )
    _check(value["status"] == "done", f"opamp run not done: {value}")
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
    value = _value(
        transport, "virtuoso.maestro.run",
        library="maestro_tb", cell="logic_probe",
        blocking=True, timeout=300, poll_interval=1.0,
    )
    _check(value["status"] == "done", f"logic run not done: {value}")
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
            return value
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("CONFIG-01 rc_probe read_config", lambda: _case_read_config_rc(transport))
    run("CONFIG-02 logic_probe read_config", lambda: _case_read_config_logic(transport))
    run("WRITE-01 config write/readback/cleanup", lambda: _case_write_smoke(transport))
    run("WRITE-02 test/analysis/option/corner atomics",
        lambda: _case_write_atomics(transport))
    run("WRITE-03 global/test/corner variable scopes",
        lambda: _case_write_var_scopes(transport))
    run("WRITE-04 global/corner parameter scopes",
        lambda: _case_write_parameter_scopes(transport))
    run("WRITE-05 job policy + simulator mode no-op",
        lambda: _case_write_job_policy_sim_mode(transport))
    rc_history = run("RUN-01 rc non-blocking + poll", lambda: _case_run_rc(transport))
    run("RESULT-01 rc points + waveform", lambda: _case_read_results_rc(transport, rc_history))
    run("EXPORT-01 all export kinds", lambda: _case_exports(transport, rc_history))
    opamp_history = run("RUN-02 opamp blocking", lambda: _case_run_opamp(transport))
    run("RESULT-02 opamp AC results", lambda: _case_opamp_results(transport, opamp_history))
    logic_history = run("RUN-03 logic blocking", lambda: _case_run_logic(transport))
    run("RESULT-03 logic tran results", lambda: _case_logic_results(transport, logic_history))
    run("GUI-01 waveform window open/close", lambda: _case_waveform_gui(transport, logic_history))
    run("GUI-02 ADE window open/close", lambda: _case_gui_lifecycle(transport))
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
