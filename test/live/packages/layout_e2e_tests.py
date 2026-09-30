# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-29 20:41
# 依赖: 无
# =======================================================================

"""End-to-end acceptance tests for ``virtuoso.layout.*``.

Run with ``--transport direct`` (in-process dispatch) or ``--transport http``
(the 8127 business face).

六步流程（test/docs/写TB规范.md §1）：
① `require_environment`（真机靶机指纹）；②③ 每个用例自建并校验基线；
④ 只做被测动作；⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。
（某步不适用时，下文会有一行注释说明原因。）
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
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
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
    return response


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
    {"op": "place_rect", "layer": "y0", "purpose": "drawing", "bbox": [[0, 0], [2, 1]]},
    {"op": "place_polygon", "layer": "y1", "purpose": "drawing",
     "points": [[3, 0], [4, 0], [4, 1]]},
    {"op": "place_path", "layer": "y2", "purpose": "drawing",
     "points": [[0, 2], [5, 2]], "width": 0.2, "style": "roundRound"},
    {"op": "place_line", "layer": "y3", "purpose": "drawing",
     "points": [[0, 3], [5, 3]]},
    {"op": "place_label", "layer": "text", "purpose": "drawing",
     "pos": [1, 4], "text": "LBL", "height": 0.5},
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
            object_filter={"shape": {"region": [[-1, -1], [2.5, 3.5]]},
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
             "master_view": VIEW, "name": "I1", "pos": [10, 0], "orient": "R0"},
            {"op": "place_mosaic", "master_lib": LIB, "master_cell": MASTER,
             "master_view": VIEW, "name": "M1", "pos": [20, 0], "orient": "R0",
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
             "new_pos": [12, 3], "new_orient": "MX"},
        ],
    )
    value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                   focus=["instances"],
                   object_filter={"instance": {"names": ["I1X"]}, "shape": "none", "via": "none"})
    inst = value["instances"][0]
    _check(inst["pos"] == [12.0, 3.0], f"instance pos: {inst}")
    _check(inst["orient"] == "MX", f"instance orient: {inst}")

    # 原子：delete_instance / delete_mosaic（读回实例列表）
    _value(
        transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "delete_instance", "name": "I1X"}],
    )
    names = {item["name"] for item in
             _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                    focus=["instances"])["instances"]}
    _check(names == {"M1"}, f"delete_instance: {names}")

    _value(
        transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "delete_mosaic", "name": "M1"}],
    )
    names = {item["name"] for item in
             _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                    focus=["instances"])["instances"]}
    _check(names == set(), f"delete_mosaic: {names}")


def _case_mutate(transport) -> None:
    _value(
        transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
        commands=[
            {"op": "set_shape_properties", "kind": "rect", "bbox": [[0, 0], [2, 1]],
             "new_bbox": [[0, 0], [2.5, 1.5]]},
            {"op": "set_shape_properties", "kind": "path",
             "points": [[0, 2], [5, 2]], "new_width": 0.4},
            {"op": "rename_label", "pos": [1, 4], "text": "LBL", "new_text": "LBL2"},
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
                      "bbox": [[0, 0], [1, 1]]}],
    })
    _check(not missing.get("ok"), "write on missing view must fail")

    wrong = transport.call({
        "operation": "virtuoso.layout.write", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW, "view_type": "schematicSymbol",
        "commands": [{"op": "place_rect", "layer": "y0", "purpose": "drawing",
                      "bbox": [[0, 0], [1, 1]]}],
    })
    _check(not wrong.get("ok"), "write with wrong view_type must fail")
    _check("view type" in (wrong.get("error") or ""),
           f"view-type mismatch not reported: {wrong.get('error')}")

    bad_lpp = transport.call({
        "operation": "virtuoso.layout.write", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW, "strict_lpp": True,
        "commands": [{"op": "place_rect", "layer": "zzNoLayer", "purpose": "drawing",
                      "bbox": [[0, 0], [1, 1]]}],
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

    # 原子：fit_view / zoom —— 判据是「窗口画面变化」（间接判据，证据里标注）
    before = _screenshot_sha(transport)
    _value(
        transport, "virtuoso.layout.display", library=LIB, cell=CELL, view=VIEW,
        commands=[{"op": "fit_view"}, {"op": "zoom", "scale": 2.0}],
    )
    after = _screenshot_sha(transport)
    _check(bool(before) and bool(after), f"fit/zoom screenshot empty: {before} / {after}")
    _check(before != after, "zoom 后窗口画面应变化（间接判据）")


def _screenshot_sha(transport) -> str:
    """截当前 layout 窗口取 sha256（用于 fit_view/zoom 的间接读回）。"""
    import hashlib

    value = _value(transport, "virtuoso.layout.screenshot",
                   library=LIB, cell=CELL, view=VIEW, leave_open=True)
    path = Path(str(value.get("local_path") or ""))
    if not path.is_file():
        return ""
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
                       "pos": [30, 30], "orient": "R0"}],
        )
        value = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                       focus=["vias"])
        _check(len(value["vias"]) == 1, f"via not read back: {value['vias']}")
        _check(value["vias"][0]["pos"] == [30.0, 30.0], f"via pos: {value['vias'][0]}")

        _value(
            transport, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
            commands=[{"op": "delete_via", "pos": [30, 30], "orient": "R0"}],
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
    artifact = ROOT / "test" / "artifacts" / "evidence" / "layout-tb"
    map_file = artifact / "y_map.map"
    gds_file = artifact / f"{CELL}.gds"
    _write_stream_map(map_file)
    for stale in (gds_file, gds_file.with_suffix(".xstream.log")):
        stale.unlink(missing_ok=True)

    def _titles() -> list[str] | None:
        """窗口标题快照；gui display 事实不可用时返回 None（不是本包判据）。"""
        try:
            listed = _op(transport, "virtuoso.gui.list_windows")
        except AssertionError:
            return None
        return [str(w.get("title") or "") for w in (listed.get("windows") or [])]

    before_titles = _titles()
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

    # P-075 红线：导出必须走批处理 strmout —— 同会话 SKILL 必须立刻可用，
    # 且不得新增任何 XStream 窗体/模态框（旧 SKILL 窗体路径会留下
    # "XStream Out" / "strmOut.log" / "Stream out translation complete"）。
    _check(_skill(transport, "1+2").strip() in ('"3"', "3"), "SKILL wedged after GDS export")
    after_titles = _titles()
    fresh = (set(after_titles) - set(before_titles)
             if before_titles is not None and after_titles is not None else set())
    leaked = sorted(t for t in fresh
                    if "stream out translation complete" in t.lower()
                    or t.lower() in ("xstream out", "stream out")
                    or t.lower().startswith("strmout.log"))
    _check(not leaked, f"XStream windows leaked by export: {leaked}")

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


def _case_read_params(transport) -> None:
    """READ-02：region_mode / view_type 与 display 的 view_type 差异。

    `depth>0` 单列在 `test/semi/probes/layout_depth_probe.py`：P-082 未修前
    任何 depth>0 请求都会先在 `_bbox(region)` 上抛格式错误（region 是扁平
    4 元组、`_bbox` 要嵌套两点），本 TB 不断言它以免假红；修复后把
    depth 断言迁回本用例（见 P-082 卡片）。
    """
    # region_mode：同一条 region，intersect 命中跨界 rect，contain 排除
    straddle = {"shape": {"region": [[1, 0], [3, 1.5]]},
                "instance": "none", "via": "none"}
    inter = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL,
                   view=VIEW, focus=["shapes"], detail="index",
                   object_filter=straddle, region_mode="intersect")
    inside = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL,
                    view=VIEW, focus=["shapes"], detail="index",
                    object_filter=straddle, region_mode="contain")
    _check(len(inter["shapes"]) >= 1,
           f"intersect must hit straddling rect: {inter['shapes']}")
    _check(len(inside["shapes"]) == 0,
           f"contain must exclude straddling rect: {inside['shapes']}")

    # view_type：显式 maskLayout 与默认等价；错误类型必须结构化失败
    explicit = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL,
                      view=VIEW, view_type="maskLayout", focus=["summary"])
    default = _value(transport, "virtuoso.layout.read", library=LIB, cell=CELL,
                     view=VIEW, focus=["summary"])
    _check(explicit["shape_count"] == default["shape_count"],
           f"explicit view_type changed read: {explicit['shape_count']} vs "
           f"{default['shape_count']}")
    wrong = transport.call({
        "operation": "virtuoso.layout.read", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW,
        "view_type": "schematic", "focus": ["summary"]})
    _check(not wrong.get("ok"), "wrong view_type must fail")

    # display：显式 view_type 可用；错误 view_type 打不开 layout 视图
    _value(transport, "virtuoso.layout.display", library=LIB, cell=CELL,
           view=VIEW, view_type="maskLayout",
           commands=[{"op": "fit_view"}], timeout=120)
    bad_display = transport.call({
        "operation": "virtuoso.layout.display", "token": TOKEN,
        "library": LIB, "cell": CELL, "view": VIEW,
        "view_type": "schematic", "commands": [{"op": "fit_view"}]})
    _check(not bad_display.get("ok"),
           f"display with wrong view_type must fail: {bad_display}")


def _case_gds_params(transport) -> None:
    """GDS-02：log_path / cleanup_policy / ref_lib_file / view_type。"""
    artifact = ROOT / "test" / "artifacts" / "evidence" / "layout-tb"
    map_file = artifact / "y_map.map"
    _write_stream_map(map_file)
    refs = artifact / "ref_libs.txt"
    refs.write_text("cdsDefTechLib\n", encoding="utf-8", newline="\n")

    def _run_dir_exists(run_dir: str) -> bool:
        out = transport.call({"operation": "basic.command.run", "token": TOKEN,
                              "cmd": f"test -d {run_dir} && echo YES || echo NO"})
        return "YES" in str((out).get("result") or "")

    # cleanup_policy=never：run dir 保留；自定义 log_path 必须落盘
    gds_a = artifact / "lay_params_never.gds"
    log_a = artifact / "lay_params_never.xstream.log"
    for stale in (gds_a, log_a):
        stale.unlink(missing_ok=True)
    response = transport.call({
        "operation": "virtuoso.layout.gds", "token": TOKEN, "action": "export",
        "library": LIB, "cell": CELL, "view": VIEW, "view_type": "maskLayout",
        "file_path": str(gds_a), "log_path": str(log_a), "layer_map": str(map_file),
        # C1 契约：成功响应默认省略 `steps`，本用例要读步骤名 → 显式开启
        "cleanup_policy": "never", "step_details": True, "timeout": 180})
    _check(response.get("ok"), f"export failed: {response.get('error')}")
    data = response
    exported = data.get("value") or {}
    _check(exported["reason"] == "completed", f"export: {exported}")
    _check(log_a.is_file() and log_a.stat().st_size > 0, f"log_path not written: {log_a}")
    _check("XSTRM-234" in log_a.read_text(encoding="utf-8", errors="replace"),
           "custom log missing completion marker")
    step_names = {step.get("name") for step in data.get("steps") or []}
    _check("stage_map" in step_names, f"layer_map not staged: {step_names}")
    run_dir = str(exported.get("remote_run_dir") or "")
    _check(run_dir and _run_dir_exists(run_dir),
           f"cleanup_policy=never must keep run dir: {run_dir}")
    transport.call({"operation": "basic.command.run", "token": TOKEN,
                    "cmd": f"rm -rf {run_dir}"})

    # ref_lib_file 仅 import 生效：导入时 -refLibList 必须被 staging（step=stage_refs）
    import_lib = "laygds2_lib"
    _skill(
        transport,
        "let((lib wd) wd = getWorkingDir() lib = ddGetObj(\"%s\") "
        "unless(lib lib = ddCreateLib(\"%s\" strcat(wd \"/%s\"))) "
        "unless(lib error(\"library create failed\")) ddUpdateLibList() \"lib-ok\")"
        % (import_lib, import_lib, import_lib),
    )
    try:
        imp = transport.call({
            "operation": "virtuoso.layout.gds", "token": TOKEN, "action": "import",
            "library": import_lib, "file_path": str(gds_a),
            "tech_lib": "cdsDefTechLib", "layer_map": str(map_file),
            "ref_lib_file": str(refs), "ref_lib_file_is_local": True,
            # C1 契约：要读步骤名必须显式开启 step_details
            "top_cell": CELL, "step_details": True, "timeout": 180, "poll_interval": 1})
        _check(imp.get("ok"), f"import with ref_lib_file failed: {imp.get('error')}")
        imp_steps = {step.get("name"): step.get("ok")
                     for step in (imp).get("steps") or []}
        _check("stage_refs" in imp_steps and imp_steps["stage_refs"] is True,
               f"ref_lib_file not staged on import: {imp_steps}")
    finally:
        _skill(
            transport,
            "let((o) o = ddGetObj(\"%s\" \"%s\") when(o ddDeleteObj(o)) "
            "o = ddGetObj(\"%s\") when(o ddDeleteObj(o)) \"cleaned\")"
            % (import_lib, CELL, import_lib),
        )

    # cleanup_policy=success（默认）：跑完 run dir 必须消失
    gds_b = artifact / "lay_params_success.gds"
    gds_b.unlink(missing_ok=True)
    exported_b = _value(
        transport, "virtuoso.layout.gds", action="export",
        library=LIB, cell=CELL, view=VIEW,
        file_path=str(gds_b), layer_map=str(map_file), timeout=180,
    )
    _check(exported_b["reason"] == "completed", f"export(success): {exported_b}")
    run_dir_b = str(exported_b.get("remote_run_dir") or "")
    _check(run_dir_b and not _run_dir_exists(run_dir_b),
           f"cleanup_policy=success must remove run dir: {run_dir_b}")

    # cleanup_policy 非法值必须结构化拒绝
    bad = transport.call({
        "operation": "virtuoso.layout.gds", "token": TOKEN, "action": "export",
        "library": LIB, "cell": CELL, "view": VIEW,
        "file_path": str(artifact / "lay_params_bad.gds"),
        "cleanup_policy": "bogus", "timeout": 60})
    _check(not bad.get("ok"), "invalid cleanup_policy must fail")


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
    run("READ-02 region_mode/depth/view_type", lambda: _case_read_params(transport))
    run("VIA-01 place/read/delete via", lambda: _case_via(transport))
    run("DISPLAY-01 layers/entry layer", lambda: _case_display(transport))
    run("SHOT-01 screenshot", lambda: _case_screenshot(transport))
    run("GDS-01 export + import round trip", lambda: _case_gds(transport))
    run("GDS-02 log_path/cleanup_policy/ref_lib_file", lambda: _case_gds_params(transport))
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="http",
                        help="direct=故障定位/覆盖率；真机判据必须 http")
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
