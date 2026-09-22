"""End-to-end acceptance tests for ``virtuoso.verilog.*``.

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
LIB = "schemtest"
CELL_TEXT = "vlog_text"
CELL_IMP = "vlog_imp_top"
CELL_EXP = "vlog_exp_top"
VIEW = "verilog"

TEXT_CODE = """module vlog_text(a, b, y);
  input a, b;
  output y;
  assign y = a & b;
endmodule
"""

STRUCTURAL_CODE = """module vlog_imp_top (A, B, Y, Z);
  input  A, B;
  output Y, Z;
  vlog_imp_nand2 u1 (.a(A), .b(B), .y(Y));
  vlog_imp_nand2 u2 (.a(Y), .b(B), .y(Z));
endmodule

module vlog_imp_nand2 (a, b, y);
  input  a, b;
  output y;
  wire   w;
  and g1 (w, a, b);
  not g2 (y, w);
endmodule
"""

BAD_CODE = """module vlog_imp_top (A, B, Y);
  input  A, B;
  output Y;
  not g1 (Y A);
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


def _skill(transport, code: str) -> str:
    data = _op(transport, "basic.skill.execute", skill_code=code)
    result = data.get("result", {})
    if result.get("status") != "success":
        raise AssertionError(f"SKILL failed: {result}")
    return result.get("output", "")


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _delete_cell(transport, cell: str) -> None:
    _skill(
        transport,
        f'let((o) o=ddGetObj("{LIB}" "{cell}") when(o ddDeleteObj(o)))',
    )


def _stage_file(transport, name: str, content: str) -> str:
    path = Path(WORK_DIR) / "verilog" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return str(path)


def _case_text_view(transport) -> None:
    _delete_cell(transport, CELL_TEXT)
    _value(
        transport, "virtuoso.verilog.write",
        library=LIB, cell=CELL_TEXT, view=VIEW,
        commands=[
            {"op": "ensure_view", "create_if_missing": True},
            {"op": "set_source", "text": TEXT_CODE},
        ],
    )
    source = _value(
        transport, "virtuoso.verilog.read",
        library=LIB, cell=CELL_TEXT, view=VIEW, focus=["source"],
    )
    _check("assign y = a & b" in source["source"]["text"], "text view content missing")
    local = _stage_file(transport, "local_read.v", TEXT_CODE)
    file_read = _value(
        transport, "virtuoso.verilog.read",
        file_path=local, file_is_local=True, focus=["source"],
    )
    _check("module vlog_text" in file_read["source"]["text"], "file read failed")


def _case_import(transport) -> None:
    for cell in (CELL_IMP, "vlog_imp_nand2"):
        _delete_cell(transport, cell)
    source = _stage_file(transport, "vlog_imp.v", STRUCTURAL_CODE)
    imported = _value(
        transport, "virtuoso.verilog.import",
        library=LIB, cell=CELL_IMP, file_path=source, timeout=180,
    )
    _check(imported["reason"] == "completed", f"import reason: {imported}")
    _check(CELL_IMP in imported["cells"], f"imported cells: {imported['cells']}")


def _case_import_failure(transport) -> None:
    source = _stage_file(transport, "vlog_bad.v", BAD_CODE)
    response = transport.call({
        "operation": "virtuoso.verilog.import", "token": TOKEN,
        "library": LIB, "cell": CELL_IMP, "file_path": source, "timeout": 180,
    })
    _check(not response.get("ok"), "syntax error must fail import")
    _check((response.get("data") or {}).get("value", {}).get("reason") == "parse_failed",
           f"import failure reason: {response}")


def _case_export(transport) -> None:
    for cell in (CELL_EXP, "vlog_exp_nand2"):
        _delete_cell(transport, cell)
    export_code = STRUCTURAL_CODE.replace("vlog_imp_", "vlog_exp_")
    source = _stage_file(transport, "vlog_exp.v", export_code)
    imported = _value(
        transport, "virtuoso.verilog.import",
        library=LIB, cell=CELL_EXP, file_path=source, timeout=180,
        structural_views=1,
    )
    _check(imported["reason"] == "completed", f"export fixture import: {imported}")
    out = str(Path(WORK_DIR) / "verilog" / f"{CELL_EXP}.out.v")
    exported = _value(
        transport, "virtuoso.verilog.export",
        library=LIB, cell=CELL_EXP, view="schematic", output_path=out, timeout=180,
    )
    _check(Path(exported["verilog_path"]).is_file(), "exported verilog missing")
    text = Path(exported["verilog_path"]).read_text(encoding="utf-8")
    _check(f"module {CELL_EXP}" in text, "exported module header missing")
    _check(exported["module_count"] >= 1, f"module_count: {exported}")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("WRITE-01 text view write/read", lambda: _case_text_view(transport))
    run("IMPORT-01 structural import (functional)", lambda: _case_import(transport))
    run("IMPORT-02 syntax failure", lambda: _case_import_failure(transport))
    run("EXPORT-01 oa2verilog", lambda: _case_export(transport))
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
