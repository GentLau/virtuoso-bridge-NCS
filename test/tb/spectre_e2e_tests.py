"""End-to-end acceptance tests for ``spectre.*``.

Run with ``--transport direct`` (in-process dispatch) or ``--transport http``
(the 8127 business face).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "tb" / "artifacts" / "log-vblog"
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
    return response["data"]


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
        read = _value(
            transport, "spectre.read_results",
            source=f"{run_dir}/tb.raw", analysis="all",
        )
        _check(read.get("kind") == "raw", f"kind: {read}")
        signals = set(read.get("signals", []))
        _check({"time", "OUT"} <= signals, f"signals: {signals}")
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
    response = transport.call({
        "operation": "spectre.run", "token": TOKEN,
        "tasks": [{"job": "e2e_rc_bad", "netlist": str(bad)}],
        "parse": "none",
    })
    _check(not response.get("ok"), "bad netlist must fail")


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
