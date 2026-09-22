"""End-to-end acceptance tests for ``virtuoso.veriloga.*``.

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
LIB, CELL, VIEW = "schemtest", "va_e2e", "veriloga"

GOOD_CODE = """// va_e2e - minimal Verilog-A
`include "constants.vams"
`include "disciplines.vams"

module va_e2e(a, b);
  inout a, b;
  electrical a, b;
  parameter real g = 2.5;
  analog V(b) <+ g * V(a);
endmodule
"""

BAD_CODE = """`include "constants.vams"
`include "disciplines.vams"

module va_e2e(a, b);
  inout a, b;
  electrical a b;
  analog V(b) <+ V(a);
endmodule
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


def _case_write_create(transport) -> None:
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "ensure_view", "create_if_missing": True},
            {"op": "set_source", "text": GOOD_CODE},
        ],
    )
    source = _value(
        transport, "virtuoso.veriloga.read",
        library=LIB, cell=CELL, view=VIEW, focus=["source"],
    )
    _check("module va_e2e" in source["source"]["text"], "source text not written")
    _check(source["source"]["sha256"], "sha256 missing")


def _case_check_and_save(transport) -> None:
    checked = _value(
        transport, "virtuoso.veriloga.check_and_save",
        library=LIB, cell=CELL, view=VIEW,
    )
    _check(checked["module_name"] == "va_e2e", f"module_name: {checked}")
    names = {port["name"] for port in checked["ports"]}
    _check(names == {"a", "b"}, f"ports: {checked['ports']}")
    _check(checked["pin_order"] == ["a", "b"], f"pin_order: {checked}")
    params = {param["name"]: param for param in checked["param_list"]}
    _check(params.get("g", {}).get("default") == "2.5", f"params: {checked['param_list']}")


def _case_patch(transport) -> None:
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "patch_source",
             "edits": [{"old_text": "g * V(a)", "new_text": "(g + 1.0) * V(a)"}]},
        ],
    )
    source = _value(
        transport, "virtuoso.veriloga.read",
        library=LIB, cell=CELL, view=VIEW, focus=["source"],
    )
    _check("(g + 1.0) * V(a)" in source["source"]["text"], "patch not applied")


def _case_guard(transport) -> None:
    source = _value(
        transport, "virtuoso.veriloga.read",
        library=LIB, cell=CELL, view=VIEW, focus=["source"],
    )
    sha = source["source"]["sha256"]
    bad = transport.call({
        "operation": "virtuoso.veriloga.write", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW,
        "commands": [{"op": "set_source", "text": "// x\n",
                      "expected_sha256": "0" * 64}],
    })
    _check(not bad.get("ok"), "expected_sha256 mismatch must fail")
    _check("sha256 mismatch" in (bad.get("error") or ""), f"guard error: {bad.get('error')}")
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "set_source", "text": GOOD_CODE, "expected_sha256": sha}],
    )


def _case_bad_syntax(transport) -> None:
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "set_source", "text": BAD_CODE}],
    )
    response = transport.call({
        "operation": "virtuoso.veriloga.check_and_save", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW,
    })
    _check(not response.get("ok"), "bad syntax must fail check")
    errors = (response.get("data") or {}).get("value") or {}
    _check(any("VACOMP-" in item for item in errors.get("errors", [])),
           f"VACOMP diagnostics missing: {errors}")
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "set_source", "text": GOOD_CODE}],
    )
    _value(
        transport, "virtuoso.veriloga.check_and_save",
        library=LIB, cell=CELL, view=VIEW,
    )


def _case_delete(transport) -> None:
    _value(
        transport, "virtuoso.veriloga.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "delete_view"}],
    )
    response = transport.call({
        "operation": "virtuoso.veriloga.read", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW,
    })
    _check(not response.get("ok"), "read after delete must fail")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("WRITE-01 ensure_view + set_source", lambda: _case_write_create(transport))
    run("CHECK-01 check_and_save ports/params", lambda: _case_check_and_save(transport))
    run("WRITE-02 patch_source", lambda: _case_patch(transport))
    run("WRITE-03 expected_sha256 guard", lambda: _case_guard(transport))
    run("CHECK-02 bad syntax diagnostics", lambda: _case_bad_syntax(transport))
    run("WRITE-04 delete_view", lambda: _case_delete(transport))
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
