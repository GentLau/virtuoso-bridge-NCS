"""End-to-end acceptance tests for ``virtuoso.layout.*``.

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

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "log-vblog"
LIB = "schemtest"
CELL = "lay_e2e"
MASTER = "lay_master"
VIEW = "layout"


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


def _delete_view(transport, cell: str, view: str = VIEW) -> None:
    _skill(
        transport,
        f'let((o) o=ddGetObj("{LIB}" "{cell}" "{view}") '
        'when(o unless(ddDeleteObj(o) error("delete failed"))))',
    )


def _create_layout(transport, cell: str, shapes: bool = False) -> None:
    body = ""
    if shapes:
        body = (
            'dbCreateRect(cv list("y0" "drawing") list(0:0 2:1)) '
            'dbCreateRect(cv list("y1" "drawing") list(0:0 1:2)) '
        )
    _skill(
        transport,
        f'let((cv) cv=dbOpenCellViewByType("{LIB}" "{cell}" "{VIEW}" '
        f'"maskLayout" "w") unless(cv error("create failed")) {body}'
        'unless(dbSave(cv) error("save failed")) dbClose(cv) t)',
    )


def _close_window(transport, cell: str) -> None:
    _skill(
        transport,
        'let((w) foreach(x hiGetWindowList() '
        f'when(x~>cellView && x~>cellView~>cellName == "{cell}" w = x)) '
        "when(w hiCloseWindow(w)))",
    )


def _shape_kinds(value: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in value.get("shapes", []):
        counts[item["kind"]] = counts.get(item["kind"], 0) + 1
    return counts


SHAPE_COMMANDS: list[dict[str, Any]] = [
    {"op": "place_rect", "layer": "y0", "purpose": "drawing", "bbox": [0, 0, 2, 1]},
    {"op": "place_polygon", "layer": "y1", "purpose": "drawing",
     "points": [[3, 0], [4, 0], [4, 1]]},
    {"op": "place_path", "layer": "y2", "purpose": "drawing",
     "points": [[0, 2], [5, 2]], "width": 0.2, "style": "roundRound"},
    {"op": "place_line", "layer": "y3", "purpose": "drawing",
     "points": [[0, 3], [5, 3]]},
    {"op": "place_label", "layer": "text", "purpose": "drawing",
     "xy": [1, 4], "text": "LBL", "height": 0.5},
]


def _seed_shapes(transport, cell: str = CELL) -> None:
    _value(transport, "virtuoso.layout.write", library=LIB, cell=cell, view=VIEW,
           commands=SHAPE_COMMANDS)


# ---------------------------------------------------------------------------
# cases
# ---------------------------------------------------------------------------

def _case_write_create(transport) -> None:
    _delete_view(transport, CELL)
    _create_layout(transport, CELL)
    written = _value(transport, "virtuoso.layout.write",
                     library=LIB, cell=CELL, view=VIEW, commands=SHAPE_COMMANDS)
    _check(written["applied"] == len(SHAPE_COMMANDS), "not all write commands applied")

    value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW)
    kinds = _shape_kinds(value)
    for kind in ("rect", "polygon", "path", "line", "label"):
        _check(kinds.get(kind) == 1, f"{kind} not read back: {kinds}")
    _check(value["shape_count"] == 5, f"shape_count: {value['shape_count']}")
    labels = [item for item in value["shapes"] if item["kind"] == "label"]
    _check(labels[0]["text"] == "LBL", f"label text: {labels[0]}")
    paths = [item for item in value["shapes"] if item["kind"] == "path"]
    _check(paths[0]["width"] == 0.2, f"path width: {paths[0]}")
    _check(paths[0]["path_style"] == "roundRound", f"path style: {paths[0]}")


def _case_read_filters(transport) -> None:
    summary = _value(
        transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
        focus=["summary"],
        object_filter={"shape": "none", "instance": "none", "via": "none"},
    )
    _check("shapes" not in summary and "instances" not in summary,
           f"object_filter none ignored: {sorted(summary)}")
    _check(summary["shape_count"] == 5, f"summary counts: {summary['shape_count']}")
    _check(summary["bbox"], "summary bbox missing")

    only_rects = _value(
        transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
        focus=["shapes"], detail="index",
        object_filter={"shape": {"types": ["rect"]}, "instance": "none", "via": "none"},
    )
    _check(len(only_rects["shapes"]) == 1, f"types filter: {only_rects['shapes']}")
    _check(set(only_rects["shapes"][0]) == {"kind", "layer", "purpose", "lpp"},
           f"detail=index fields: {only_rects['shapes'][0]}")

    region = _value(
        transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
        focus=["shapes"], detail="index",
        object_filter={"shape": {"region": [-1, -1, 2.5, 3.5]},
                       "instance": "none", "via": "none"},
    )
    # region [-1,-1,2.5,3.5] intersects rect / path / line (polygon starts at x=3,
    # label sits at y=4) → exactly 3 hits.
    _check(len(region["shapes"]) == 3, f"region filter: {region['shapes']}")


def _case_instances(transport) -> None:
    # Drop the referencing cell first: deleting a cell that another cell still
    # instantiates makes Virtuoso raise a modal "Save All" dialog.
    _delete_view(transport, CELL)
    _delete_view(transport, MASTER)
    _create_layout(transport, MASTER, shapes=True)
    _create_layout(transport, CELL)
    _seed_shapes(transport)
    created = _value(
        transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "place_instance", "master_lib": LIB, "master_cell": MASTER,
             "master_view": VIEW, "name": "I1", "xy": [10, 0], "orient": "R0"},
            {"op": "place_mosaic", "master_lib": LIB, "master_cell": MASTER,
             "master_view": VIEW, "name": "M1", "xy": [20, 0], "orient": "R0",
             "rows": 2, "cols": 3, "row_pitch": 4, "col_pitch": 4},
        ],
    )
    _check(created["applied"] == 2, "instance/mosaic not applied")
    value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                   focus=["instances"])
    names = {item["name"] for item in value["instances"]}
    _check({"I1", "M1"} <= names, f"instances after create: {names}")
    mosaic = [item for item in value["instances"] if item["name"] == "M1"][0]
    _check(mosaic["kind"] == "mosaic", f"mosaic kind: {mosaic}")
    _check(mosaic["rows"] == 2 and mosaic["cols"] == 3, f"mosaic shape: {mosaic}")

    _value(
        transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "rename_instance", "name": "I1", "new_name": "I1X"},
            {"op": "set_instance_properties", "name": "I1X",
             "new_xy": [12, 3], "new_orient": "MX"},
        ],
    )
    value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                   focus=["instances"],
                   object_filter={"instance": {"names": ["I1X"]}, "shape": "none", "via": "none"})
    inst = value["instances"][0]
    _check(inst["xy"] == [12.0, 3.0], f"instance xy: {inst}")
    _check(inst["orient"] == "MX", f"instance orient: {inst}")


def _case_mutate(transport) -> None:
    _value(
        transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "set_shape_properties", "kind": "rect", "bbox": [0, 0, 2, 1],
             "new_bbox": [0, 0, 2.5, 1.5]},
            {"op": "set_shape_properties", "kind": "path",
             "points": [[0, 2], [5, 2]], "new_width": 0.4},
            {"op": "rename_label", "xy": [1, 4], "text": "LBL", "new_text": "LBL2"},
            {"op": "delete_shape", "kind": "line", "points": [[0, 3], [5, 3]]},
        ],
    )
    value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW)
    kinds = _shape_kinds(value)
    _check("line" not in kinds, f"line not deleted: {kinds}")
    rects = [item for item in value["shapes"] if item["kind"] == "rect"]
    _check(rects[0]["bbox"] == [[0.0, 0.0], [2.5, 1.5]], f"rect not resized: {rects[0]}")
    paths = [item for item in value["shapes"] if item["kind"] == "path"]
    _check(paths[0]["width"] == 0.4, f"path width not set: {paths[0]}")
    _check(any(item["text"] == "LBL2" for item in value["shapes"]), "label not renamed")

    deleted = _value(
        transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "delete_shapes_on_layer", "layer": "y1", "purpose": "drawing"}],
    )
    _check(deleted["applied"] == 1, "delete_shapes_on_layer failed")
    value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW)
    _check(not any(item["kind"] == "polygon" for item in value["shapes"]),
           "polygon on y1 not deleted")


def _case_guards(transport) -> None:
    missing = transport.call({
        "operation": "virtuoso.layout.write", "token": TOKEN,
        "library": LIB, "cell": "lay_no_such_cell", "view": VIEW,
        "commands": [{"op": "place_rect", "layer": "y0", "purpose": "drawing",
                      "bbox": [0, 0, 1, 1]}],
    })
    _check(not missing.get("ok"), "write on missing view must fail")

    wrong = transport.call({
        "operation": "virtuoso.layout.write", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW, "view_type": "schematicSymbol",
        "commands": [{"op": "place_rect", "layer": "y0", "purpose": "drawing",
                      "bbox": [0, 0, 1, 1]}],
    })
    _check(not wrong.get("ok"), "write with wrong view_type must fail")
    _check("view type" in (wrong.get("error") or ""),
           f"view-type mismatch not reported: {wrong.get('error')}")

    bad_lpp = transport.call({
        "operation": "virtuoso.layout.write", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW, "strict_lpp": True,
        "commands": [{"op": "place_rect", "layer": "zzNoLayer", "purpose": "drawing",
                      "bbox": [0, 0, 1, 1]}],
    })
    _check(not bad_lpp.get("ok"), "strict_lpp must reject unknown layer")
    _check("unknown layer" in (bad_lpp.get("error") or ""),
           f"strict_lpp error text: {bad_lpp.get('error')}")


def _case_display(transport) -> None:
    _value(
        transport, "virtuoso.layout.display", library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "set_entry_layer", "layers": [["y0", "drawing"]]},
            {"op": "set_layers_visible", "layers": [["y0", "drawing"]], "visible": True},
            {"op": "show_only_layers", "layers": [["y0", "drawing"], ["y1", "drawing"]]},
        ],
    )
    entry = _skill(transport, 'let((tf) tf = techGetTechFile(ddGetObj("schemtest")) '
                              "sprintf(nil \"%L\" leGetEntryLayer(tf)))")
    _check("y0" in entry, f"entry layer not set: {entry}")


def _case_via(transport) -> None:
    """Session-only viaDef is enough: create it, place/read/delete a via, drop it."""
    _skill(
        transport,
        "let((vbTf) vbTf = techGetTechFile(ddGetObj(\"schemtest\")) "
        "unless(vbTf error(\"no techfile\")) "
        "vbLayTestViaDef = techCreateStdViaDef(vbTf \"lay_e2e_via\" \"y0\" \"y1\" "
        "list(\"y2\" 0.2 0.2) list(1 1 list(0.2 0.2)) "
        "list(0.1 0.1) list(0.1 0.1) list(0.0 0.0) list(0.0 0.0) list(0.0 0.0)) "
        'unless(vbLayTestViaDef error("viaDef not created")) "viaDef-ok")',
    )
    try:
        _value(
            transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
            commands=[{"op": "place_via", "via_name": "lay_e2e_via",
                       "xy": [30, 30], "orient": "R0"}],
        )
        value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                       focus=["vias"])
        _check(len(value["vias"]) == 1, f"via not read back: {value['vias']}")
        _check(value["vias"][0]["xy"] == [30.0, 30.0], f"via xy: {value['vias'][0]}")

        _value(
            transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
            commands=[{"op": "delete_via", "xy": [30, 30], "orient": "R0"}],
        )
        value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                       focus=["vias"])
        _check(not value["vias"], f"via not deleted: {value['vias']}")
    finally:
        _skill(
            transport,
            "progn(when(boundp('vbLayTestViaDef) "
            "techDeleteViaDef(vbLayTestViaDef)) vbLayTestViaDef = nil \"viaDef-cleaned\")",
        )


def _case_screenshot(transport) -> None:
    _skill(
        transport,
        f'geOpen(?lib "{LIB}" ?cell "{CELL}" ?view "{VIEW}" '
        '?viewType "maskLayout" ?mode "r")',
    )
    try:
        value = _value(
            transport, "virtuoso.layout.screenshot",
            library=LIB, cell=CELL, view=VIEW, leave_open=True,
        )
        path = Path(value["local_path"])
        _check(path.is_file() and path.stat().st_size > 0,
               "layout screenshot missing or empty")
    finally:
        _close_window(transport, CELL)


def _write_stream_map(path: Path) -> None:
    """Minimal LF-only layer map for the cdsDefTechLib system layers."""
    lines = [
        "# OA layer  purpose  streamLayer  datatype",
    ]
    for index in range(10):
        lines.append(f"y{index} drawing {index} 0")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="ascii", newline="\n")


def _case_gds(transport) -> None:
    artifact = ROOT / "test" / "artifacts" / "layout-tb"
    map_file = artifact / "y_map.map"
    gds_file = artifact / f"{CELL}.gds"
    _write_stream_map(map_file)
    for stale in (gds_file, gds_file.with_suffix(".xstream.log")):
        stale.unlink(missing_ok=True)

    exported = _value(
        transport, "virtuoso.layout.gds", action="export",
        library=LIB, cell=CELL, view=VIEW,
        file_path=str(gds_file), layer_map=str(map_file), timeout=180,
    )
    _check(exported["reason"] == "completed", f"export reason: {exported}")
    _check(gds_file.is_file() and gds_file.stat().st_size > 0, "GDS not published")
    _check(any(CELL in item for item in exported["translated_structures"]),
           f"translated structures: {exported['translated_structures']}")
    log_text = Path(exported["log_path"]).read_text(encoding="utf-8", errors="replace")
    _check("XSTRM-234" in log_text, "log has no completion marker")

    # Round trip: import the exported GDS into a scratch library so the source
    # layout is not overwritten by the imported structure of the same name.
    import_lib = "laygds_lib"
    _skill(
        transport,
        "let((lib wd) wd = getWorkingDir() lib = ddGetObj(\"%s\") "
        "unless(lib lib = ddCreateLib(\"%s\" strcat(wd \"/%s\"))) "
        "unless(lib error(\"library create failed\")) ddUpdateLibList() \"lib-ok\")"
        % (import_lib, import_lib, import_lib),
    )
    imported = _value(
        transport, "virtuoso.layout.gds", action="import",
        library=import_lib, file_path=str(gds_file), tech_lib="cdsDefTechLib",
        layer_map=str(map_file),
        top_cell=CELL, timeout=180, poll_interval=1,
    )
    _check(imported["reason"] == "completed", f"import reason: {imported}")
    _check(imported.get("shape_count", 0) > 0, f"imported shapes: {imported}")
    _skill(
        transport,
        "let((o) o = ddGetObj(\"%s\" \"%s\") when(o ddDeleteObj(o)) "
        "o = ddGetObj(\"%s\") when(o ddDeleteObj(o)) \"cleaned\")"
        % (import_lib, CELL, import_lib),
    )


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

    run("WRITE-01 place geometry/label", lambda: _case_write_create(transport))
    run("READ-01 focus/object_filter/detail", lambda: _case_read_filters(transport))
    run("WRITE-02 instance + mosaic atoms", lambda: _case_instances(transport))
    run("WRITE-03 set/delete/rename atoms", lambda: _case_mutate(transport))
    run("WRITE-04 guards", lambda: _case_guards(transport))
    run("VIA-01 place/read/delete via", lambda: _case_via(transport))
    run("DISPLAY-01 layers/entry layer", lambda: _case_display(transport))
    run("SHOT-01 screenshot", lambda: _case_screenshot(transport))
    run("GDS-01 export + import round trip", lambda: _case_gds(transport))
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
