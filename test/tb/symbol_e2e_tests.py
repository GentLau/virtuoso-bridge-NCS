"""End-to-end acceptance tests for ``virtuoso.symbol.*``.

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


class HttpTransport:
    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            # 4xx carries the business envelope (ok=false + error) as a body.
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


def _cleanup_view(transport, lib: str, cell: str, view: str) -> None:
    _skill(
        transport,
        f'let((o) o=ddGetObj("{lib}" "{cell}" "{view}") '
        'when(o unless(ddDeleteObj(o) error("delete failed"))))',
    )


def _create_view(transport, lib: str, cell: str, view: str, view_type: str) -> None:
    _skill(
        transport,
        f'let((cv) cv=dbOpenCellViewByType("{lib}" "{cell}" "{view}" '
        f'"{view_type}" "w") '
        'unless(cv error("create failed")) '
        'unless(dbSave(cv) error("save failed")) dbClose(cv) t)',
    )


def _create_symbol_view(transport, lib: str, cell: str, view: str) -> None:
    _create_view(transport, lib, cell, view, "schematicSymbol")


def _close_symbol_window(transport, cell: str) -> None:
    _skill(
        transport,
        'let((w) foreach(x hiGetWindowList() '
        f'when(x~>cellView && x~>cellView~>cellName == "{cell}" w = x)) '
        "when(w hiCloseWindow(w)))",
    )


def _case_read_symfinal(transport) -> None:
    value = _value(
        transport, "virtuoso.symbol.read",
        library="schemtest", cell="symfinal", view="symbol",
    )
    names = {item["name"] for item in value["terms"]}
    _check({"IN", "OUT", "BI"} <= names, f"symfinal terms: {names}")
    _check(value["pin_order"] == ["IN", "OUT", "BI"],
           f"symfinal pin_order: {value['pin_order']}")
    _check(value["selection_boxes"], "symfinal selection box missing")
    kinds = {item["kind"] for item in value["shapes"]}
    _check({"line", "polygon", "rect", "ellipse"} <= kinds,
           f"symfinal shapes: {kinds}")
    labels = {item["text"] for item in value["labels"]}
    _check({"OUT", "BI"} <= labels, f"symfinal labels: {labels}")


def _case_read_focus(transport) -> None:
    value = _value(
        transport, "virtuoso.symbol.read",
        library="schemtest", cell="symfinal", view="symbol",
        focus=["terms", "orders"],
    )
    _check("terms" in value and "labels" not in value, f"focus result: {value.keys()}")
    _check("pin_order" in value, "focus orders missing pin_order")


def _case_write_create(transport) -> str:
    lib, cell, view = "schemtest", "sym_e2e", "symbol"
    _cleanup_view(transport, lib, cell, view)
    _create_symbol_view(transport, lib, cell, view)
    commands = [
        {"op": "place_rect", "layer": "annotate", "purpose": "drawing",
         "bbox": [0, 0, 2, 2]},
        {"op": "place_polygon", "layer": "device", "purpose": "drawing",
         "points": [[-2, -2], [-1, -2], [-1, -1]]},
        {"op": "place_ellipse", "layer": "device", "purpose": "drawing",
         "bbox": [2, 2, 3, 3]},
        {"op": "place_label", "label_kind": "drawing",
         "layer": "annotate", "purpose": "drawing",
         "text": "drawing-label", "x": 0, "y": 0},
        {"op": "place_pin", "name": "IN", "x": -3, "y": 0,
         "direction": "input"},
        {"op": "place_pin", "name": "OUT", "x": 3, "y": 0,
         "direction": "output"},
        {"op": "place_label", "label_kind": "instance", "x": 0, "y": 1},
        {"op": "place_label", "label_kind": "logical", "x": 0, "y": -1},
        {"op": "set_selection_box", "bbox": [-4, -4, 4, 4]},
        {"op": "set_pin_order", "term_names": ["OUT", "IN"]},
    ]
    written = _value(
        transport, "virtuoso.symbol.write",
        library=lib, cell=cell, view=view, commands=commands,
    )
    _check(written["applied"] == len(commands), "not all write commands applied")
    value = _value(
        transport, "virtuoso.symbol.read",
        library=lib, cell=cell, view=view,
    )
    names = {item["name"] for item in value["terms"]}
    _check(names == {"IN", "OUT"}, f"terms after write: {names}")
    _check(value["pin_order"] == ["OUT", "IN"],
           f"pin_order after write: {value['pin_order']}")
    _check(len(value["selection_boxes"]) == 1, "selection box missing")
    return view


def _case_write_modify(transport, view: str) -> None:
    lib, cell = "schemtest", "sym_e2e"
    # Batch A: in-place edits (property setters + renames).  The pin rename has
    # to sync the pin-name label, so it is asserted before the delete batch.
    commands = [
        {"op": "set_shape_properties", "kind": "rect",
         "bbox": [0, 0, 2, 2], "new_bbox": [0, 0, 2.5, 2.5]},
        {"op": "set_shape_properties", "kind": "polygon",
         "points": [[-2, -2], [-1, -2], [-1, -1]],
         "new_points": [[-2, -2], [-1, -2], [-1, -1.5]]},
        {"op": "rename_label", "label_kind": "drawing",
         "xy": [0, 0], "text": "drawing-label", "new_text": "drawing-label-2"},
        {"op": "set_label_properties", "label_kind": "instance",
         "xy": [0, 1], "justify": "lowerLeft", "orient": "R90",
         "height": 0.1},
        {"op": "rename_pin", "name": "OUT", "new_name": "OUT2"},
        {"op": "set_pin_properties", "name": "OUT2",
         "direction": "inputOutput", "access_dir": "left"},
        {"op": "delete_shape", "kind": "ellipse", "bbox": [2, 2, 3, 3]},
    ]
    _value(
        transport, "virtuoso.symbol.write",
        library=lib, cell=cell, view=view, commands=commands,
    )
    value = _value(
        transport, "virtuoso.symbol.read",
        library=lib, cell=cell, view=view,
    )
    _check({item["name"] for item in value["terms"]} == {"IN", "OUT2"},
           "rename_pin did not rename the terminal")
    _check(not any(item["kind"] == "ellipse" for item in value["shapes"]),
           "ellipse was not deleted")
    pin_labels = [item["text"] for item in value["labels"]
                  if item["layer"] == "pin"]
    _check("OUT2" in pin_labels,
           f"rename_pin did not sync the pin-name label: {pin_labels}")
    _check("OUT" not in pin_labels,
           f"stale pin-name label left behind: {pin_labels}")
    out2 = [item for item in value["terms"] if item["name"] == "OUT2"][0]
    _check(out2["access_dir"] == ["left"],
           f"set_pin_properties access_dir not read back: {out2}")
    rect = [item for item in value["shapes"] if item["kind"] == "rect"
            and item["layer"] == "annotate"]
    _check(rect and rect[0]["bbox"] == [[0.0, 0.0], [2.5, 2.5]],
           f"set_shape_properties new_bbox not applied: {rect}")

    # Batch B: deletes.  delete_pin must clear the pin figure and pin-name
    # label, not just detach the figure from the terminal.
    deletes = [
        {"op": "delete_label", "label_kind": "logical", "xy": [0, -1]},
        {"op": "delete_pin", "name": "OUT2"},
    ]
    _value(
        transport, "virtuoso.symbol.write",
        library=lib, cell=cell, view=view, commands=deletes,
    )
    value = _value(
        transport, "virtuoso.symbol.read",
        library=lib, cell=cell, view=view,
    )
    _check({item["name"] for item in value["terms"]} == {"IN"},
           "delete_pin final terms mismatch")
    _check(not any(item["text"] == "[@partName]" for item in value["labels"]),
           "logical label was not deleted")
    pin_labels = [item["text"] for item in value["labels"]
                  if item["layer"] == "pin"]
    _check("OUT2" not in pin_labels,
           f"delete_pin left the pin-name label behind: {pin_labels}")
    pin_rects = [item for item in value["shapes"] if item["layer"] == "pin"]
    _check(len(pin_rects) == 1,
           f"delete_pin left the pin rectangle behind: {pin_rects}")


def _case_view_type_mismatch(transport) -> None:
    """A same-named view of another type must fail, not be edited."""
    lib, cell, view = "schemtest", "sym_e2e", "type_probe"
    _cleanup_view(transport, lib, cell, view)
    _create_view(transport, lib, cell, view, "schematic")
    try:
        response = transport.call({
            "operation": "virtuoso.symbol.write",
            "token": TOKEN,
            "library": lib, "cell": cell, "view": view,
            "commands": [{"op": "place_line", "layer": "device",
                          "purpose": "drawing", "points": [[0, 0], [1, 0]]}],
        })
        _check(not response.get("ok"), "write on a wrong view type must fail")
        _check("view type" in (response.get("error") or ""),
               f"view-type mismatch not reported: {response.get('error')}")
    finally:
        _cleanup_view(transport, lib, cell, view)


def _case_check_and_save(transport, view: str) -> None:
    value = _value(
        transport, "virtuoso.symbol.check_and_save",
        library="schemtest", cell="sym_e2e", view=view,
    )
    _check(value["saved"] is True, "check_and_save did not report saved")


def _case_missing_view(transport) -> None:
    response = transport.call({
        "operation": "virtuoso.symbol.write",
        "token": TOKEN,
        "library": "schemtest",
        "cell": "sym_e2e",
        "view": "missing_view",
        "commands": [{"op": "place_line", "layer": "device",
                      "purpose": "drawing", "points": [[0, 0], [1, 0]]}],
    })
    _check(not response.get("ok"), "write on missing view must fail")


def _case_generate(transport) -> None:
    lib, cell = "schemtest", "gen_e2e"
    _cleanup_view(transport, lib, cell, "schematic")
    _cleanup_view(transport, lib, cell, "symbol_a")
    _create_view(transport, lib, cell, "schematic", "schematic")
    _op(
        transport, "virtuoso.schematic.write",
        library=lib, cell=cell, view="schematic",
        commands=[
            {"op": "place_pin", "name": "C", "x": 0, "y": 0,
             "direction": "input"},
            {"op": "place_pin", "name": "A", "x": 2, "y": 0,
             "direction": "input"},
            {"op": "place_pin", "name": "B", "x": 1, "y": 0,
             "direction": "input"},
        ],
    )
    created = _value(
        transport, "virtuoso.symbol.generate",
        library=lib, cell=cell, schematic_view="schematic",
        symbol_view="symbol_a", sort_pins="alphanumeric",
        overwrite=False,
    )
    _check(created["action"] == "created", f"generate action: {created}")
    _check(set(created["terminal_names"]) == {"A", "B", "C"},
           f"generated terminals: {created['terminal_names']}")

    existing = transport.call({
        "operation": "virtuoso.symbol.generate",
        "token": TOKEN,
        "library": lib, "cell": cell,
        "schematic_view": "schematic", "symbol_view": "symbol_a",
        "overwrite": False,
    })
    _check(not existing.get("ok"), "generate without overwrite must fail")

    replaced = _value(
        transport, "virtuoso.symbol.generate",
        library=lib, cell=cell, schematic_view="schematic",
        symbol_view="symbol_a", overwrite=True,
    )
    _check(replaced["action"] == "replaced", f"overwrite action: {replaced}")

    same_view = transport.call({
        "operation": "virtuoso.symbol.generate",
        "token": TOKEN,
        "library": lib, "cell": cell,
        "schematic_view": "schematic", "symbol_view": "schematic",
    })
    _check(not same_view.get("ok"), "same source/target view must fail")

    _skill(
        transport,
        'deOpenCellView("schemtest" "gen_e2e" "symbol_a" '
        '"schematicSymbol" nil "r")',
    )
    try:
        open_target = transport.call({
            "operation": "virtuoso.symbol.generate",
            "token": TOKEN,
            "library": lib, "cell": cell,
            "schematic_view": "schematic", "symbol_view": "symbol_a",
            "overwrite": True,
        })
        _check(not open_target.get("ok"),
               "generate on an open target must fail")
    finally:
        _close_symbol_window(transport, "gen_e2e")


def _case_screenshot(transport) -> None:
    _skill(
        transport,
        'deOpenCellView("schemtest" "sym_e2e" "symbol" '
        '"schematicSymbol" nil "r")',
    )
    try:
        value = _value(
            transport, "virtuoso.symbol.screenshot",
            library="schemtest", cell="sym_e2e", view="symbol",
            leave_open=True,
        )
        path = Path(value["local_path"])
        _check(path.is_file() and path.stat().st_size > 0,
               "symbol screenshot missing or empty")
    finally:
        _close_symbol_window(transport, "sym_e2e")


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

    run("READ-01 symfinal structured read",
        lambda: _case_read_symfinal(transport))
    run("READ-02 focus filtering",
        lambda: _case_read_focus(transport))
    view = run("WRITE-01 create geometry/labels/pins",
               lambda: _case_write_create(transport))
    run("WRITE-02 delete/set atoms",
        lambda: _case_write_modify(transport, view))
    run("CHECK-01 check_and_save",
        lambda: _case_check_and_save(transport, view))
    run("WRITE-03 missing view fails",
        lambda: _case_missing_view(transport))
    run("WRITE-04 wrong view type fails",
        lambda: _case_view_type_mismatch(transport))
    run("GEN-01/02/03 generate + overwrite",
        lambda: _case_generate(transport))
    run("SHOT-01 symbol screenshot",
        lambda: _case_screenshot(transport))
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
