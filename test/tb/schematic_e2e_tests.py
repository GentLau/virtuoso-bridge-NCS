"""End-to-end acceptance tests for ``virtuoso.schematic.*``."""
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
LIB, CELL, VIEW = "schemtest", "sch_e2e", "schematic"


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


def _ensure_cell(transport) -> None:
    _skill(
        transport,
        f'let((o) o=ddGetObj("{LIB}" "{CELL}") when(o ddDeleteObj(o))) '
        f'let((cv) cv=dbOpenCellViewByType("{LIB}" "{CELL}" "{VIEW}" '
        '"schematic" "w") unless(cv error("create failed")) '
        'unless(dbSave(cv) error("save failed")) dbClose(cv) t)',
    )


def _case_read(transport) -> None:
    value = _value(
        transport, "virtuoso.schematic.read",
        library="maestro_tb", cell="rc_probe", view="schematic",
        focus="positions",
    )
    _check("instances" in value or "positions" in value,
           f"read result keys: {sorted(value)}")


def _case_write(transport) -> None:
    _ensure_cell(transport)
    _op(
        transport, "virtuoso.schematic.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "place_label", "text": "net1", "x": 0, "y": 0},
            {"op": "place_label", "text": "net2", "x": 0, "y": 1},
        ],
    )
    _op(
        transport, "virtuoso.schematic.write",
        library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "rename_label", "x": 0, "y": 1, "new_text": "net2x"},
            {"op": "delete_label", "x": 0, "y": 0},
        ],
    )
    value = _value(
        transport, "virtuoso.schematic.read",
        library=LIB, cell=CELL, view=VIEW, focus="positions",
    )
    labels = [
        item for item in value.get("labels", [])
        if isinstance(item, dict) and item.get("text") in ("net1", "net2", "net2x")
    ]
    _check(any(item.get("text") == "net2x" for item in labels),
           f"rename not visible: {labels}")
    _check(not any(item.get("text") == "net1" for item in labels),
           f"delete not applied: {labels}")


def _case_check_and_save(transport) -> None:
    data = _op(
        transport, "virtuoso.schematic.check_and_save",
        library=LIB, cell=CELL, view=VIEW,
    )
    _check(data.get("ok"), f"check_and_save: {data}")


def _case_screenshot(transport) -> None:
    _skill(
        transport,
        f'deOpenCellView("{LIB}" "{CELL}" "{VIEW}" "schematic" nil "r")',
    )
    try:
        value = _op(
            transport, "virtuoso.schematic.screenshot",
            library=LIB, cell=CELL, view=VIEW, leave_open=True,
        )
        path = Path(value.get("local_path") or "")
        _check(path.is_file() and path.stat().st_size > 0,
               f"screenshot missing: {value}")
    finally:
        _skill(
            transport,
            'let((w) foreach(x hiGetWindowList() '
            f'when(x~>cellView && x~>cellView~>cellName == "{CELL}" w = x)) '
            "when(w hiCloseWindow(w)))",
        )


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    run("READ-01 positions", lambda: _case_read(transport))
    run("WRITE-01 label atoms + readback", lambda: _case_write(transport))
    run("CHECK-01 check_and_save", lambda: _case_check_and_save(transport))
    run("SHOT-01 screenshot", lambda: _case_screenshot(transport))
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
