"""``layout`` business package: geometry read/write, GDS, screenshot, display.

Spec: ``spec/design-concepts/上层/4-layout.md`` (Draft v4).

The package only calls the middle ``execute_skill`` / ``run_command`` /
``upload_file`` / ``download_file`` interfaces (plus the read-only ``query``).
Manual writes are append-only: an existing ``maskLayout`` view is opened in
mode ``"a"``; creating an empty view is the cellview package's responsibility.
"""
from __future__ import annotations

import os
import posixpath
import re
import shlex
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import artifact_dir
from pyapi.models import Middle, VirtuosoResult
from pyapi.packages import basic, gui


LAYOUT_VIEW_TYPE = "maskLayout"
_PLACE_ATOMS = ("place_rect", "place_polygon", "place_path", "place_line", "place_label")
_SHAPE_KINDS = ("rect", "polygon", "path", "line", "ellipse")
_PATH_STYLES = (
    "extendExtend", "roundRound", "truncateExtend", "varExtendExtend",
    "squareFlush", "squareOffset", "octagonEnded",
)
_DISPLAY_ATOMS = ("set_layers_visible", "show_only_layers", "set_entry_layer", "fit_view", "zoom")


# ---------------------------------------------------------------------------
# Requests / result
# ---------------------------------------------------------------------------

@dataclass
class Result:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    value: Any = None


@dataclass(frozen=True)
class ReadRequest:
    token: str
    library: str
    cell: str
    view: str = "layout"
    view_type: str = LAYOUT_VIEW_TYPE
    focus: list[str] | None = None
    detail: str = "geometry"
    object_filter: dict[str, Any] | None = None
    region_mode: str = "intersect"
    depth: int = 0
    timeout: int | None = None


@dataclass(frozen=True)
class WriteRequest:
    token: str
    library: str
    cell: str
    commands: list[dict[str, Any]]
    view: str = "layout"
    view_type: str = LAYOUT_VIEW_TYPE
    strict_lpp: bool = False
    timeout: int | None = None


@dataclass(frozen=True)
class GdsRequest:
    token: str
    action: str
    library: str
    cell: str | None = None
    view: str = "layout"
    view_type: str = LAYOUT_VIEW_TYPE
    file_path: str | None = None
    file_is_local: bool = True
    layer_map: str | None = None
    layer_map_is_local: bool = True
    ref_lib_file: str | None = None
    ref_lib_file_is_local: bool = True
    tech_lib: str | None = None
    top_cell: str | None = None
    log_path: str | None = None
    timeout: float | None = None
    poll_interval: float | None = None
    cleanup_policy: str = "success"


@dataclass(frozen=True)
class ScreenshotRequest:
    token: str
    library: str
    cell: str
    view: str = "layout"
    view_type: str = LAYOUT_VIEW_TYPE
    window_id: int | None = None
    region: list[float] | None = None
    toplevel: bool = True
    central_widget: bool = True
    leave_open: bool = False
    timeout: int | None = None


@dataclass(frozen=True)
class DisplayRequest:
    token: str
    library: str
    cell: str
    commands: list[dict[str, Any]]
    view: str = "layout"
    view_type: str = LAYOUT_VIEW_TYPE
    timeout: int | None = None


# ---------------------------------------------------------------------------
# Validation / formatting helpers
# ---------------------------------------------------------------------------

def _step(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _require_timeout(value: Any) -> None:
    if value is not None and (not isinstance(value, (int, float)) or value <= 0):
        raise ValueError("timeout must be a positive number or None")


def _require_bool(value: Any, name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{name} must be a boolean")
    return value


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a number")
    return float(value)


def _point(value: Any, name: str = "point") -> tuple[float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(f"{name} must be [x, y]")
    return _number(value[0], f"{name}[0]"), _number(value[1], f"{name}[1]")


def _bbox(value: Any, name: str = "bbox") -> tuple[float, float, float, float]:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        raise ValueError(f"{name} must be [x0, y0, x1, y1]")
    x0, y0, x1, y1 = (_number(item, f"{name}[{index}]") for index, item in enumerate(value))
    if not x0 < x1 or not y0 < y1:
        raise ValueError(f"{name} must satisfy x0 < x1 and y0 < y1")
    return x0, y0, x1, y1


def _points(value: Any, name: str, *, minimum: int = 2) -> list[tuple[float, float]]:
    if not isinstance(value, (list, tuple)) or len(value) < minimum:
        raise ValueError(f"{name} must be a list of at least {minimum} points")
    return [_point(item, f"{name}[{index}]") for index, item in enumerate(value)]


def _lpp(layer: Any, purpose: Any) -> tuple[str, str]:
    return _require_text(layer, "layer"), _require_text(purpose, "purpose")


def _lpp_expr(layer: str, purpose: str) -> str:
    return f"list({basic.q(layer)} {basic.q(purpose)})"


def _point_expr(point: tuple[float, float]) -> str:
    return f"list({point[0]:g} {point[1]:g})"


def _points_expr(points: list[tuple[float, float]]) -> str:
    return "list(" + " ".join(_point_expr(item) for item in points) + ")"


def _bbox_expr(bbox: tuple[float, float, float, float]) -> str:
    x0, y0, x1, y1 = bbox
    return f"list(list({x0:g} {y0:g}) list({x1:g} {y1:g}))"


def _bbox_from_points(points: list[tuple[float, float]]) -> tuple[float, float, float, float]:
    xs = [item[0] for item in points]
    ys = [item[1] for item in points]
    return min(xs), min(ys), max(xs), max(ys)


#: DB grid is 0.001 user units; compare at half a DBU so adjacent grid points
#: (0.001 vs 0.002) are never treated as equal.
TOLERANCE = 0.0005


def _bbox_match_expr(binding: str, bbox: tuple[float, float, float, float],
                     tol: float = TOLERANCE) -> str:
    x0, y0, x1, y1 = bbox
    return (
        f"{binding}~>bBox && "
        f"abs(xCoord(car({binding}~>bBox)) - {x0:g}) <= {tol:g} && "
        f"abs(yCoord(car({binding}~>bBox)) - {y0:g}) <= {tol:g} && "
        f"abs(xCoord(cadr({binding}~>bBox)) - {x1:g}) <= {tol:g} && "
        f"abs(yCoord(cadr({binding}~>bBox)) - {y1:g}) <= {tol:g}"
    )


def _points_match_expr(binding: str, points: list[tuple[float, float]],
                       tol: float = TOLERANCE) -> str:
    parts = [f"length({binding}~>points) == {len(points)}"]
    for index, (x, y) in enumerate(points):
        parts.append(
            f"abs(xCoord(nth({index} {binding}~>points)) - {x:g}) <= {tol:g} && "
            f"abs(yCoord(nth({index} {binding}~>points)) - {y:g}) <= {tol:g}"
        )
    return " && ".join(parts)


def _shape_match_expr(kind: str, command: dict[str, Any]) -> str:
    parts = [f'x~>objType == {basic.q(kind)}']
    if command.get("layer"):
        parts.append(f"x~>layerName == {basic.q(command['layer'])}")
    if command.get("purpose"):
        parts.append(f"x~>purpose == {basic.q(command['purpose'])}")
    if kind in ("polygon", "path", "line"):
        # Path bBox includes half the width and rects have no points at all, so
        # polygonal shapes are indexed by their centreline points only.
        if "points" not in command:
            raise ValueError(f"{kind} commands require points")
        points = _points(command["points"], "command.points")
        parts.append(_points_match_expr("x", points))
    else:
        if "bbox" not in command:
            raise ValueError(f"{kind} commands require bbox")
        parts.append(_bbox_match_expr("x", _bbox(command["bbox"])))
    return " && ".join(parts)


def _points_value(value: Any) -> list[list[float]] | None:
    if not isinstance(value, list):
        return None
    result: list[list[float]] = []
    for item in value:
        if isinstance(item, list) and len(item) >= 2:
            try:
                result.append([float(item[0]), float(item[1])])
            except (TypeError, ValueError):
                return None
    return result or None


def _point_value(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) >= 2:
        try:
            return [float(value[0]), float(value[1])]
        except (TypeError, ValueError):
            return None
    return None


def _bbox_value(value: Any) -> list[list[float]] | None:
    points = _points_value(value)
    return points if points and len(points) == 2 else None


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _f(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"non-numeric value from SKILL: {value!r}") from exc


def _i(value: Any, default: int) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_name(value: str, fallback: str = "layout") -> str:
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "_", value or "").strip("_")
    return cleaned or fallback


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

class Package:
    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    # -- low level helpers ------------------------------------------------------
    def _skill(self, expr: str, token: str, timeout: int | float | None = None) -> VirtuosoResult:
        return self.middle.execute_skill(expr, timeout=timeout, token=token)

    def _q(self, expr: str, token: str, timeout: int | float | None = None) -> str:
        result = self._skill(expr, token, timeout)
        if not result.ok:
            raise RuntimeError("; ".join(result.errors) or "SKILL execution failed")
        return result.output or ""

    def _sql(self, expr: str, token: str, timeout: int | float | None = None) -> Any:
        text = self._q(expr, token, timeout).strip()
        if not text:
            return None
        return basic.parse_sexpr(text)

    @staticmethod
    def _open_expr(lib: str, cell: str, view: str, view_type: str, mode: str) -> str:
        return (
            f"dbOpenCellViewByType({basic.q(lib)} {basic.q(cell)} "
            f"{basic.q(view)} {basic.q(view_type)} {basic.q(mode)})"
        )

    def _view_state_expr(self, lib: str, cell: str, view: str, view_type: str) -> str:
        """Return ``"ok"`` / ``"mismatch"`` / ``"missing"`` for the target view."""
        return (
            "let((vbObj vbCv vbState) "
            f"vbObj = ddGetObj({basic.q(lib)} {basic.q(cell)} {basic.q(view)}) "
            "if(vbObj progn(ddReleaseObj(vbObj) "
            f"vbCv = dbOpenCellViewByType({basic.q(lib)} {basic.q(cell)} "
            f"{basic.q(view)} {basic.q(view_type)} \"r\") "
            "vbState = if(vbCv progn(dbClose(vbCv) \"ok\") \"mismatch\")) "
            "vbState = \"missing\") "
            "vbState)"
        )

    def _require_view_exists(self, request: Any) -> None:
        raw = self._q(
            self._view_state_expr(
                request.library, request.cell, request.view, request.view_type
            ),
            request.token,
            request.timeout,
        )
        state = basic.parse_sexpr(raw.strip())
        if state == "ok":
            return
        if state == "mismatch":
            raise RuntimeError(
                f"{request.library}/{request.cell}/{request.view} exists but is not "
                f"view type {request.view_type}"
            )
        if state == "missing":
            raise RuntimeError(
                f"layout view {request.library}/{request.cell}/{request.view} not found"
            )
        raise RuntimeError(f"unexpected view probe result: {raw.strip()!r}")

    def _view_dir_path(self, request: Any) -> str:
        raw = self._q(
            f"let((lib) lib = ddGetObj({basic.q(request.library)}) "
            'unless(lib error("library not found")) ddGetObjReadPath(lib))',
            request.token,
            request.timeout,
        )
        root = raw.strip().strip('"')
        if not root:
            raise RuntimeError(f"library {request.library!r} read path unavailable")
        return posixpath.join(root.rstrip("/"), request.cell, request.view)

    def _lock_files_exist(self, request: Any) -> bool:
        """True when the cellview directory contains ``*.cdslck`` lock files."""
        view_dir = self._view_dir_path(request)
        probe = self.middle.run_command(
            f"ls -A {shlex.quote(view_dir)}/*.cdslck 2>/dev/null",
            timeout=60, token=request.token,
        )
        return probe.returncode == 0 and bool((probe.stdout or "").strip())

    def _open_for_edit_error(self, request: Any) -> str | None:
        """Probe an edit-open with immediate close; return a clear error or None.

        同一会话自己持有的锁不算冲突：以“能否 append-open 成功”为准，而不是
        看目录里有没有 ``*.cdslck``（锁文件对 owner 来说总是存在）。
        """
        probe = self._q(
            "let((vbCv) "
            f"vbCv = {self._open_expr(request.library, request.cell, request.view, request.view_type, 'a')} "
            'if(vbCv then progn(dbClose(vbCv) "open-ok") else "open-failed"))',
            request.token,
            request.timeout,
        )
        if basic.parse_sexpr(probe.strip()) == "open-ok":
            return None
        if self._lock_files_exist(request):
            return (
                f"layout view {request.library}/{request.cell}/{request.view} "
                "is locked by another session"
            )
        return f"failed to open layout view {request.library}/{request.cell}/{request.view} for edit"

    def _save_expr(self, request: Any) -> str:
        """Save the already-open global ``vbLayoutCv`` and always release it."""
        return (
            "let((vbSaved) "
            "vbSaved = errset(dbSave(vbLayoutCv)) "
            "dbClose(vbLayoutCv) vbLayoutCv = nil "
            'unless(vbSaved && car(vbSaved) error("layout save failed")) '
            '"saved")'
        )

    def _open_edit_expr(self, request: Any) -> str:
        """Open for edit once and keep the handle in the global ``vbLayoutCv``."""
        return (
            "let((vbEdit) "
            f"vbEdit = {self._open_expr(request.library, request.cell, request.view, request.view_type, 'a')} "
            'if(vbEdit then vbLayoutCv = vbEdit "open-ok" else "locked"))'
        )

    def _close_edit_expr(self) -> str:
        return (
            'when(boundp(\'vbLayoutCv) && vbLayoutCv dbClose(vbLayoutCv)) '
            'vbLayoutCv = nil t'
        )

    def _role_root(self, token: str, role: str) -> str:
        facts = self.middle.query(token=token)
        if facts.status.value != "success":
            raise RuntimeError("; ".join(facts.errors) or "query failed")
        entry = facts.roles.get(role)
        if entry is None or not entry.root:
            raise RuntimeError(f"{role} role root is not available")
        return entry.root.rstrip("/")

    # -- read -------------------------------------------------------------------

    def read(self, request: ReadRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        valid_focus = {"summary", "shapes", "instances", "vias"}
        if request.focus is not None:
            if not isinstance(request.focus, list) or not request.focus:
                raise ValueError("focus must be a non-empty list")
            unknown = set(request.focus) - valid_focus
            if unknown:
                raise ValueError(f"unknown focus values: {sorted(unknown)}")
        if request.detail not in ("geometry", "index"):
            raise ValueError("detail must be geometry or index")
        if request.region_mode not in ("intersect", "contain"):
            raise ValueError("region_mode must be intersect or contain")
        if not isinstance(request.depth, int) or request.depth < 0:
            raise ValueError("depth must be a non-negative integer")
        if request.depth and not _filter_layers_or_region(request.object_filter):
            raise ValueError("depth > 0 requires a layers or region filter")
        if request.object_filter is not None and not isinstance(request.object_filter, dict):
            raise ValueError("object_filter must be an object")

        steps: list[dict[str, Any]] = []
        try:
            raw = self._q(_read_skill(request), request.token, request.timeout)
            steps.append(_step("read", True, raw))
            text = raw.strip()
            if not basic.is_single_complete_skill_list(text):
                raise RuntimeError(
                    f"layout read output is not a single complete SKILL list: {text[:200]!r}"
                )
            parsed = _parse_read(text)
            value = _apply_read_filters(parsed, request)
            value.update({
                "library": request.library, "cell": request.cell, "view": request.view,
                "view_type": request.view_type,
            })
            return Result(True, steps, None, value)
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    # -- write ------------------------------------------------------------------

    def write(self, request: WriteRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        _require_bool(request.strict_lpp, "strict_lpp")
        if not isinstance(request.commands, list) or not request.commands:
            raise ValueError("commands must be a non-empty list")

        steps: list[dict[str, Any]] = []
        planned: list[tuple[int, dict[str, Any], str]] = []
        for index, command in enumerate(request.commands):
            if not isinstance(command, dict) or "op" not in command:
                return Result(False, steps, f"command {index} must be an object with op")
            try:
                planned.append((index, command, self._atomic_expr(command)))
            except Exception as exc:  # noqa: BLE001
                return Result(False, steps, f"command {index} invalid: {exc}")
        try:
            self._require_view_exists(request)
            steps.append(_step("view_exists", True, request.view))
            edit_error = self._open_for_edit_error(request)
            if edit_error:
                raise RuntimeError(edit_error)
            if request.strict_lpp:
                lpp_steps = self._check_lpp(request, planned)
                steps.append(_step("strict_lpp", True, lpp_steps))
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

        opened = self._skill(self._open_edit_expr(request), request.token, request.timeout)
        state = (opened.output or "").strip().strip('"')
        steps.append(_step("open", opened.ok and state == "open-ok", opened))
        if not opened.ok:
            return Result(False, steps, "; ".join(opened.errors) or "open failed")
        if state != "open-ok":
            return Result(
                False, steps,
                f"layout view {request.library}/{request.cell}/{request.view} "
                "is locked by another session",
            )

        for index, command, expr in planned:
            run = self._skill(expr, request.token, request.timeout)
            steps.append(_step(f"command:{command['op']}", run.ok, run))
            if not run.ok:
                self._skill(self._close_edit_expr(), request.token, request.timeout)
                detail = "; ".join(run.errors) or f"command {command['op']} failed"
                return Result(
                    False, steps,
                    f"{detail} (commands applied: {index}/{len(planned)}; "
                    "layout.write is not transactional)",
                )

        saved = self._skill(self._save_expr(request), request.token, request.timeout)
        steps.append(_step("dbSave", saved.ok, saved))
        if not saved.ok or "saved" not in (saved.output or ""):
            if not saved.ok:
                self._skill(self._close_edit_expr(), request.token, request.timeout)
            return Result(False, steps, "; ".join(saved.errors) or "layout save failed")
        return Result(True, steps, None, {"applied": len(request.commands)})

    def _check_lpp(self, request: WriteRequest,
                   planned: list[tuple[int, dict[str, Any], str]]) -> list[str]:
        wanted: list[tuple[str, str]] = []
        for _index, command, _expr in planned:
            if command.get("layer") and command.get("purpose"):
                pair = (str(command["layer"]), str(command["purpose"]))
                if pair not in wanted:
                    wanted.append(pair)
        atom_pairs = " ".join(_lpp_expr(layer, purpose) for layer, purpose in wanted)
        expression = (
            "let((vbTf vbBad) "
            f"vbTf = techGetTechFile(ddGetObj({basic.q(request.library)})) "
            'unless(vbTf error("library has no techfile")) '
            f"foreach(vbPair list({atom_pairs}) "
            "unless(techGetLayerNum(vbTf car(vbPair)) "
            'vbBad = cons(car(vbPair) vbBad)) '
            "unless(member(cadr(vbPair) mapcar(lambda((p) if(symbolp(p) p p)) vbTf~>purposes)) "
            "vbBad = cons(cadr(vbPair) vbBad))) "
            'if(vbBad sprintf(nil "unknown layer/purpose: %L" vbBad) "ok"))'
        )
        raw = self._q(expression, request.token, request.timeout).strip()
        if raw.strip('"') == "ok":
            return [f"{layer}/{purpose}" for layer, purpose in wanted]
        raise RuntimeError(raw.strip('"'))

    # -- atomic builders --------------------------------------------------------

    def _atomic_expr(self, command: dict[str, Any]) -> str:
        op = command.get("op")
        if not isinstance(op, str) or not op:
            raise ValueError("command.op must be a non-empty string")

        if op in _PLACE_ATOMS:
            return self._place_expr(op, command)
        if op in ("delete_shape", "set_shape_properties"):
            return self._shape_mutation_expr(op, command)
        if op == "delete_shapes_on_layer":
            return self._delete_by_layer_expr(command)
        if op in ("delete_label", "rename_label", "set_label_properties"):
            return self._label_mutation_expr(op, command)
        if op == "place_instance":
            return self._place_instance_expr(command)
        if op in ("delete_instance", "rename_instance", "set_instance_properties"):
            return self._instance_mutation_expr(op, command)
        if op == "place_mosaic":
            return self._place_mosaic_expr(command)
        if op == "delete_mosaic":
            return self._delete_mosaic_expr(command)
        if op == "place_via":
            return self._place_via_expr(command)
        if op == "delete_via":
            return self._delete_via_expr(command)
        raise ValueError(f"unknown atomic op: {op}")

    def _place_expr(self, op: str, command: dict[str, Any]) -> str:
        if op == "place_label":
            layer, purpose = _lpp(command.get("layer"), command.get("purpose"))
            xy = _point_expr(_point(command.get("xy"), "command.xy"))
            text = _require_text(command.get("text"), "command.text")
            justify = str(command.get("justify", "lowerLeft"))
            orient = str(command.get("orient", "R0"))
            font = str(command.get("font", "fixed"))
            height = _number(command.get("height", 1.0), "command.height")
            if height <= 0:
                raise ValueError("command.height must be > 0")
            body = (
                f"dbCreateLabel(vbLayoutCv {_lpp_expr(layer, purpose)} {xy} "
                f"{basic.q(text)} {basic.q(justify)} {basic.q(orient)} "
                f"{basic.q(font)} {height:g})"
            )
            return f'let((vbShape) vbShape = {body} unless(vbShape error("label not created")) vbShape)'

        layer, purpose = _lpp(command.get("layer"), command.get("purpose"))
        lpp = _lpp_expr(layer, purpose)
        if op == "place_rect":
            bbox = _bbox_expr(_bbox(command.get("bbox")))
            body = f"dbCreateRect(vbLayoutCv {lpp} {bbox})"
        elif op == "place_polygon":
            points = _points(command.get("points"), "command.points", minimum=3)
            body = f"dbCreatePolygon(vbLayoutCv {lpp} {_points_expr(points)})"
        elif op == "place_line":
            points = _points(command.get("points"), "command.points", minimum=2)
            if len(points) != 2:
                raise ValueError("place_line requires exactly 2 points")
            body = f"dbCreateLine(vbLayoutCv {lpp} {_points_expr(points)})"
        else:
            points = _points(command.get("points"), "command.points", minimum=2)
            width = _number(command.get("width"), "command.width")
            if width <= 0:
                raise ValueError("command.width must be > 0")
            style = command.get("style")
            if style is not None:
                if style not in _PATH_STYLES:
                    raise ValueError(f"command.style must be one of {_PATH_STYLES}")
                body = (
                    f"dbCreatePath(vbLayoutCv {lpp} {_points_expr(points)} "
                    f"{width:g} {basic.q(style)})"
                )
            else:
                body = f"dbCreatePath(vbLayoutCv {lpp} {_points_expr(points)} {width:g})"
        return f'let((vbShape) vbShape = {body} unless(vbShape error("shape not created")) vbShape)'

    def _shape_mutation_expr(self, op: str, command: dict[str, Any]) -> str:
        kind = _require_text(command.get("kind"), "command.kind")
        if kind not in _SHAPE_KINDS:
            raise ValueError(f"command.kind must be one of {_SHAPE_KINDS}")
        pred = _shape_match_expr(kind, command)
        all_shapes = bool(command.get("all"))
        if op == "delete_shape":
            body = (
                "foreach(vbShape vbShapes dbDeleteObject(vbShape)) t"
                if all_shapes
                else 'unless(length(vbShapes) == 1 error(strcat("expected exactly one shape, got " '
                     "length(vbShapes)))) dbDeleteObject(car(vbShapes))"
            )
            return (
                "let((vbShapes) "
                f"vbShapes = setof(x vbLayoutCv~>shapes {pred}) "
                'unless(vbShapes error("shape not found")) '
                f"{body})"
            )
        assigns: list[str] = []
        if "new_bbox" in command:
            if kind not in ("rect", "ellipse"):
                raise ValueError("new_bbox is only writable on rect/ellipse")
            assigns.append(f"vbShape~>bBox = {_bbox_expr(_bbox(command['new_bbox'], 'command.new_bbox'))}")
        if "new_points" in command:
            if kind not in ("polygon", "path", "line"):
                raise ValueError("new_points is only writable on polygon/path/line")
            assigns.append(
                f"vbShape~>points = {_points_expr(_points(command['new_points'], 'command.new_points'))}"
            )
        if "new_width" in command:
            if kind != "path":
                raise ValueError("new_width is only writable on path")
            width = _number(command["new_width"], "command.new_width")
            if width <= 0:
                raise ValueError("command.new_width must be > 0")
            assigns.append(f"vbShape~>width = {width:g}")
        if not assigns:
            raise ValueError("set_shape_properties requires at least one new_* field")
        tail = (
            'unless(length(vbShapes) == 1 error(strcat("expected exactly one shape, got " '
            "length(vbShapes)))) let((vbShape) vbShape = car(vbShapes) "
            + " ".join(assigns) + " vbShape)"
        )
        return (
            "let((vbShapes) "
            f"vbShapes = setof(x vbLayoutCv~>shapes {pred}) "
            'unless(vbShapes error("shape not found")) '
            f"{tail})"
        )

    def _delete_by_layer_expr(self, command: dict[str, Any]) -> str:
        layer, purpose = _lpp(command.get("layer"), command.get("purpose"))
        parts = [
            f"x~>layerName == {basic.q(layer)}",
            f"x~>purpose == {basic.q(purpose)}",
        ]
        types = command.get("types")
        if types is not None:
            if not isinstance(types, list) or not types:
                raise ValueError("command.types must be a non-empty list")
            members = " || ".join(f'x~>objType == {basic.q(str(item))}' for item in types)
            parts.append(f"({members})")
        pred = " && ".join(parts)
        return (
            "let((vbShapes vbCount) "
            f"vbShapes = setof(x vbLayoutCv~>shapes {pred}) "
            "vbCount = length(vbShapes) "
            "foreach(vbShape vbShapes dbDeleteObject(vbShape)) "
            "vbCount)"
        )

    def _label_match_expr(self, command: dict[str, Any]) -> str:
        xy = _point(command.get("xy"), "command.xy")
        parts = [
            'x~>objType == "label"',
            f"abs(xCoord(x~>xy) - {xy[0]:g}) <= {TOLERANCE:g}",
            f"abs(yCoord(x~>xy) - {xy[1]:g}) <= {TOLERANCE:g}",
        ]
        text = command.get("text", command.get("old_text"))
        if text:
            parts.append(f"x~>theLabel == {basic.q(str(text))}")
        if command.get("layer"):
            parts.append(f"x~>layerName == {basic.q(str(command['layer']))}")
        return " && ".join(parts)

    def _label_mutation_expr(self, op: str, command: dict[str, Any]) -> str:
        pred = self._label_match_expr(command)
        head = (
            "let((vbShapes) "
            f"vbShapes = setof(x vbLayoutCv~>shapes {pred}) "
            'unless(vbShapes error("label not found")) '
            'unless(length(vbShapes) == 1 error(strcat("expected exactly one label, got " '
            "length(vbShapes)))) "
        )
        if op == "delete_label":
            return head + "dbDeleteObject(car(vbShapes)))"
        assigns: list[str] = []
        if op == "rename_label":
            new_text = _require_text(command.get("new_text"), "command.new_text")
            assigns.append(f"vbLabel~>theLabel = {basic.q(new_text)}")
        else:
            if "new_text" in command:
                assigns.append(f"vbLabel~>theLabel = {basic.q(str(command['new_text']))}")
            if "new_xy" in command:
                assigns.append(f"vbLabel~>xy = {_point_expr(_point(command['new_xy'], 'command.new_xy'))}")
            if "new_height" in command:
                height = _number(command["new_height"], "command.new_height")
                if height <= 0:
                    raise ValueError("command.new_height must be > 0")
                assigns.append(f"vbLabel~>height = {height:g}")
            for key, attr in (("new_justify", "justify"), ("new_orient", "orient"), ("new_font", "font")):
                if command.get(key):
                    assigns.append(f"vbLabel~>{attr} = {basic.q(str(command[key]))}")
            if not assigns:
                raise ValueError("set_label_properties requires at least one new_* field")
        return head + "let((vbLabel) vbLabel = car(vbShapes) " + " ".join(assigns) + " vbLabel))"

    def _place_instance_expr(self, command: dict[str, Any]) -> str:
        master_lib = _require_text(command.get("master_lib"), "command.master_lib")
        master_cell = _require_text(command.get("master_cell"), "command.master_cell")
        master_view = _require_text(command.get("master_view", "layout"), "command.master_view")
        name = _require_text(command.get("name"), "command.name")
        xy = _point_expr(_point(command.get("xy"), "command.xy"))
        orient = str(command.get("orient", "R0"))
        num_inst = command.get("num_inst")
        extra = ""
        if num_inst is not None:
            count = int(_number(num_inst, "command.num_inst"))
            if count < 1:
                raise ValueError("command.num_inst must be >= 1")
            extra = f" {count}"
        return (
            "let((vbInst) "
            f"vbInst = dbCreateInstByMasterName(vbLayoutCv {basic.q(master_lib)} "
            f"{basic.q(master_cell)} {basic.q(master_view)} {basic.q(name)} "
            f"{xy} {basic.q(orient)}{extra}) "
            'unless(vbInst error("instance not created")) vbInst)'
        )

    def _instance_match_expr(self, name: str, *, mosaic: bool = False) -> str:
        parts = [f"x~>name == {basic.q(name)}"]
        if mosaic:
            parts.append('x~>objType == "mosaic"')
        return " && ".join(parts)

    def _instance_mutation_expr(self, op: str, command: dict[str, Any]) -> str:
        name = _require_text(command.get("name"), "command.name")
        pred = self._instance_match_expr(name)
        head = (
            "let((vbShapes) "
            f"vbShapes = setof(x vbLayoutCv~>instances {pred}) "
            'unless(vbShapes error("instance not found")) '
            'unless(length(vbShapes) == 1 error(strcat("expected exactly one instance, got " '
            "length(vbShapes)))) "
        )
        if op == "delete_instance":
            return head + "dbDeleteObject(car(vbShapes)))"
        assigns: list[str] = []
        if op == "rename_instance":
            new_name = _require_text(command.get("new_name"), "command.new_name")
            assigns.append(f"vbInst~>name = {basic.q(new_name)}")
        else:
            if "new_xy" in command:
                assigns.append(f"vbInst~>xy = {_point_expr(_point(command['new_xy'], 'command.new_xy'))}")
            if command.get("new_orient"):
                assigns.append(f"vbInst~>orient = {basic.q(str(command['new_orient']))}")
            if not assigns:
                raise ValueError("set_instance_properties requires at least one new_* field")
        return head + "let((vbInst) vbInst = car(vbShapes) " + " ".join(assigns) + " vbInst))"

    def _place_mosaic_expr(self, command: dict[str, Any]) -> str:
        master_lib = _require_text(command.get("master_lib"), "command.master_lib")
        master_cell = _require_text(command.get("master_cell"), "command.master_cell")
        master_view = _require_text(command.get("master_view", "layout"), "command.master_view")
        name = _require_text(command.get("name"), "command.name")
        xy = _point_expr(_point(command.get("xy"), "command.xy"))
        orient = str(command.get("orient", "R0"))
        rows = int(_number(command.get("rows"), "command.rows"))
        cols = int(_number(command.get("cols"), "command.cols"))
        row_pitch = _number(command.get("row_pitch"), "command.row_pitch")
        col_pitch = _number(command.get("col_pitch"), "command.col_pitch")
        if rows < 1 or cols < 1:
            raise ValueError("command.rows/cols must be >= 1")
        return (
            "let((vbMaster vbMosaic) "
            f"vbMaster = dbOpenCellViewByType({basic.q(master_lib)} {basic.q(master_cell)} "
            f"{basic.q(master_view)} {basic.q(LAYOUT_VIEW_TYPE)} \"r\") "
            'unless(vbMaster error("mosaic master not found")) '
            f"vbMosaic = dbCreateSimpleMosaic(vbLayoutCv vbMaster {basic.q(name)} {xy} "
            f"{basic.q(orient)} {rows} {cols} {row_pitch:g} {col_pitch:g}) "
            "dbClose(vbMaster) "
            'unless(vbMosaic error("mosaic not created")) vbMosaic)'
        )

    def _delete_mosaic_expr(self, command: dict[str, Any]) -> str:
        name = _require_text(command.get("name"), "command.name")
        pred = self._instance_match_expr(name, mosaic=True)
        return (
            "let((vbShapes) "
            f"vbShapes = setof(x vbLayoutCv~>instances {pred}) "
            'unless(vbShapes error("mosaic not found")) '
            "foreach(vbShape vbShapes dbDeleteObject(vbShape)) t)"
        )

    def _place_via_expr(self, command: dict[str, Any]) -> str:
        via_name = _require_text(command.get("via_name"), "command.via_name")
        xy = _point_expr(_point(command.get("xy"), "command.xy"))
        orient = str(command.get("orient", "R0"))
        return (
            "let((vbTf vbViaDef vbVia) "
            "vbTf = techGetTechFile(ddGetObj(vbLayoutCv~>libName)) "
            'unless(vbTf error("library has no techfile")) '
            f"vbViaDef = techFindViaDefByName(vbTf {basic.q(via_name)}) "
            'unless(vbViaDef error(strcat("via definition not found: " '
            f'{basic.q(via_name)}))) '
            f"vbVia = dbCreateVia(vbLayoutCv vbViaDef {xy} {basic.q(orient)}) "
            'unless(vbVia error("via not created")) vbVia)'
        )

    def _delete_via_expr(self, command: dict[str, Any]) -> str:
        xy = _point(command.get("xy"), "command.xy")
        orient = str(command.get("orient", "R0"))
        # A via's viaDef/name is not readable after creation (both are nil on the
        # instantiated object), so vias are indexed by position + orientation.
        pred = (
            "x~>xy && "
            f"abs(xCoord(x~>xy) - {xy[0]:g}) <= {TOLERANCE:g} && "
            f"abs(yCoord(x~>xy) - {xy[1]:g}) <= {TOLERANCE:g} && "
            f"(x~>orient == {basic.q(orient)} || x~>orient == nil)"
        )
        return (
            "let((vbVias) "
            f"vbVias = setof(x vbLayoutCv~>vias {pred}) "
            'unless(vbVias error("via not found")) '
            "foreach(vbVia vbVias dbDeleteObject(vbVia)) t)"
        )

    # -- display ----------------------------------------------------------------

    def display(self, request: DisplayRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        if not isinstance(request.commands, list) or not request.commands:
            raise ValueError("commands must be a non-empty list")
        steps: list[dict[str, Any]] = []
        for index, command in enumerate(request.commands):
            if not isinstance(command, dict) or "op" not in command:
                return Result(False, steps, f"command {index} must be an object with op")
            try:
                expr = self._display_expr(command, request)
            except Exception as exc:  # noqa: BLE001
                return Result(False, steps, f"command {index} invalid: {exc}")
            run = self._skill(f"let((vbLayoutCv) {expr})", request.token, request.timeout)
            steps.append(_step(f"command:{command['op']}", run.ok, run))
            if not run.ok:
                detail = "; ".join(run.errors) or f"command {command['op']} failed"
                return Result(False, steps, f"{detail} (applied: {index}/{len(request.commands)})")
        return Result(True, steps, None, {"applied": len(request.commands)})

    def _display_expr(self, command: dict[str, Any], request: DisplayRequest) -> str:
        op = command.get("op")
        if op not in _DISPLAY_ATOMS:
            raise ValueError(f"unknown display atom: {op}")
        lib = basic.q(request.library)
        if op in ("fit_view", "zoom"):
            cv_expr = (
                f"vbLayoutCv = {self._open_expr(request.library, request.cell, request.view, request.view_type, 'r')} "
                'unless(vbLayoutCv error("layout view not found")) '
            )
            window = _window_expr(request, basic.q(request.library))
            if op == "fit_view":
                body = "hiZoomIn(vbWin vbLayoutCv~>bBox)"
            else:
                scale = _number(command.get("scale"), "command.scale")
                if scale <= 0:
                    raise ValueError("command.scale must be > 0")
                body = f"hiZoomAbsoluteScale(vbWin {scale:g})"
            return (
                "let((vbWin) "
                f"vbWin = {window} "
                'unless(vbWin error(strcat("window not found for " '
                f'{lib}))) '
                f"{body} "
                "dbClose(vbLayoutCv))"
            )
        layers = command.get("layers")
        if not isinstance(layers, list) or not layers:
            raise ValueError("command.layers must be a non-empty list")
        lpp_list = "list(" + " ".join(
            _lpp_expr(*(_lpp(item[0] if isinstance(item, (list, tuple)) and len(item) == 2 else None,
                             item[1] if isinstance(item, (list, tuple)) and len(item) == 2 else None)))
            for item in layers
        ) + ")"
        if op == "show_only_layers":
            body = (
                "unless(leSetAllLayerVisible(nil vbTf) error(\"leSetAllLayerVisible failed\")) "
                f"foreach(vbLpp {lpp_list} "
                "unless(leSetLayerVisible(vbLpp t vbTf) error(\"leSetLayerVisible failed\")))"
            )
        elif op == "set_layers_visible":
            visible = command.get("visible")
            _require_bool(visible, "command.visible")
            body = (
                f"foreach(vbLpp {lpp_list} "
                f"unless(leSetLayerVisible(vbLpp {'t' if visible else 'nil'} vbTf) "
                'error("leSetLayerVisible failed")))'
            )
        else:
            layer, purpose = _lpp(layers[0][0], layers[0][1]) if isinstance(layers[0], (list, tuple)) \
                else _lpp(command.get("layer"), command.get("purpose"))
            body = (
                f"unless(leSetLayerValid({_lpp_expr(layer, purpose)} t) "
                'error("leSetLayerValid failed")) '
                f"unless(leSetEntryLayer({_lpp_expr(layer, purpose)} vbTf) "
                'error("leSetEntryLayer failed"))'
            )
        return (
            "let((vbTf) "
            f"vbTf = techGetTechFile(ddGetObj({lib})) "
            'unless(vbTf error("library has no techfile")) '
            f"{body} t)"
        )

    # -- gds --------------------------------------------------------------------

    def gds(self, request: GdsRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.action, "action")
        _require_timeout(request.timeout)
        if request.action == "export":
            return self._gds_export(request)
        if request.action == "import":
            return self._gds_import(request)
        raise ValueError("action must be export or import")

    def _gds_export(self, request: GdsRequest) -> Result:
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        output = _require_text(request.file_path, "file_path")
        steps: list[dict[str, Any]] = []
        remote_dir: str | None = None
        try:
            timeout = float(request.timeout or 300)
            interval = float(request.poll_interval or 0.5)
            if request.cleanup_policy not in ("success", "always", "never"):
                raise ValueError("cleanup_policy must be success/always/never")
            if request.file_is_local:
                output_path = Path(output)
                log_path = (
                    Path(request.log_path) if request.log_path
                    else output_path.with_suffix(".xstream.log")
                )
            else:
                # 远端路径必须按原样透传，不能经 Path() 变成本机反斜杠路径
                output_path = output
                log_path = request.log_path or f"{output}.xstream.log"
            if str(log_path) == str(output_path):
                raise ValueError("log_path and file_path must differ")

            root = self._role_root(request.token, "daemon")
            remote_dir = posixpath.join(
                root, "xstream",
                _safe_name(f"{request.library}__{request.cell}__{request.view}"),
            )
            remote_gds = posixpath.join(
                remote_dir, _safe_name(Path(output).name, "output.gds"),
            )
            remote_log = posixpath.join(remote_dir, "xstream.log")
            remote_map = posixpath.join(remote_dir, "stream.map")

            prepared = self.middle.run_command(
                f"mkdir -p {shlex.quote(remote_dir)} && "
                f"rm -f {shlex.quote(remote_gds)} {shlex.quote(remote_log)}",
                timeout=60, token=request.token,
            )
            steps.append(_step("prepare", prepared.returncode == 0, prepared))
            if prepared.returncode != 0:
                return Result(False, steps, prepared.stderr or "prepare failed")

            state_raw = self._q(
                self._view_state_expr(
                    request.library, request.cell, request.view, request.view_type,
                ),
                request.token, request.timeout,
            )
            state = basic.parse_sexpr(state_raw.strip())
            if state == "missing":
                return Result(
                    False, steps,
                    f"layout view {request.library}/{request.cell}/{request.view} not found",
                )
            if state == "mismatch":
                return Result(
                    False, steps,
                    f"layout view {request.library}/{request.cell}/{request.view} "
                    f"is not view type {request.view_type}",
                )
            edit_error = self._open_for_edit_error(request)
            if edit_error:
                return Result(False, steps, edit_error)
            # XStream Out translates the *saved* cellview; a dirty cellview in the
            # session is not exported and can raise a modal "Save All" dialog that
            # blocks the whole SKILL channel.
            flushed = self._skill(
                "let((vbCv vbSaved) "
                f"vbCv = {self._open_expr(request.library, request.cell, request.view, request.view_type, 'a')} "
                'unless(vbCv error("failed to open layout for edit")) '
                "vbSaved = errset(dbSave(vbCv)) "
                "dbClose(vbCv) "
                'unless(vbSaved && car(vbSaved) error("layout save failed")) '
                '"saved")',
                request.token, request.timeout,
            )
            steps.append(_step("flush", flushed.ok, flushed))
            if not flushed.ok or "saved" not in (flushed.output or ""):
                return Result(
                    False, steps,
                    "; ".join(flushed.errors) or "failed to save the layout before export",
                )

            if request.layer_map:
                if request.layer_map_is_local:
                    staged = self.middle.upload_file(
                        Path(request.layer_map), remote_map, timeout=request.timeout, token=request.token,
                    )
                else:
                    staged = self.middle.run_command(
                        f"cp {shlex.quote(request.layer_map)} {shlex.quote(remote_map)}",
                        timeout=60, token=request.token,
                    )
                steps.append(_step("stage_map", staged.returncode == 0, staged))
                if staged.returncode != 0:
                    return Result(False, steps, staged.stderr or "stream map staging failed")

            launched = self._skill(
                _xstream_skill(
                    request.library, request.cell, request.view,
                    remote_gds, remote_map, remote_log, remote_dir,
                ),
                request.token, request.timeout,
            )
            steps.append(_step("xstream", launched.ok, launched))
            output_text = (launched.output or "").strip()
            if not launched.ok or "started" not in output_text:
                reason = "xstream_failure"
                return Result(
                    False, steps,
                    f"{reason}: {output_text or '; '.join(launched.errors)}",
                    {"reason": reason},
                )

            deadline = time.monotonic() + timeout
            log_text, gds_size, failure = "", 0, ""
            while True:
                poll = self.middle.run_command(
                    f"tail -n 400 {shlex.quote(remote_log)} 2>/dev/null; echo '---VBSIZE---'; "
                    f"if [ -f {shlex.quote(remote_gds)} ]; then wc -c < {shlex.quote(remote_gds)}; else echo 0; fi",
                    timeout=60, token=request.token,
                )
                if poll.returncode == 0:
                    body, _, size_text = (poll.stdout or "").partition("---VBSIZE---")
                    log_text = body
                    try:
                        gds_size = int((size_text or "0").strip().splitlines()[0])
                    except (ValueError, IndexError):
                        gds_size = 0
                    failure = _xstream_failure_reason(log_text)
                    if failure or ("XSTRM-234" in log_text and "Translation completed" in log_text):
                        break
                if time.monotonic() >= deadline:
                    failure = "incomplete_log"
                    break
                time.sleep(min(interval, 5.0))

            reason = failure or ("completed" if gds_size > 0 else "missing_gds")
            steps.append(_step("log", not failure, {"reason": reason, "gds_size": gds_size}))
            self._dismiss_xstream_windows(request, steps)

            if request.file_is_local:
                published_log = self._publish_remote(remote_log, log_path, request)
            else:
                published_log = self._publish_remote_copy(
                    remote_log, str(log_path), request,
                )
            steps.append(_step("publish_log", published_log is None, published_log))
            if published_log is not None and reason == "completed":
                return Result(False, steps, f"publication_error: {published_log}",
                              {"reason": "publication_error"})

            if reason != "completed":
                if request.cleanup_policy == "always" and remote_dir:
                    self._cleanup(remote_dir, request, steps)
                return Result(False, steps, f"{reason}: {_xstream_summary(log_text)}",
                              {"reason": reason, "gds_size": gds_size})

            if request.file_is_local:
                published_gds = self._publish_remote(remote_gds, output_path, request)
            else:
                published_gds = self._publish_remote_copy(
                    remote_gds, output, request,
                )
            steps.append(_step("publish_gds", published_gds is None, published_gds))
            if published_gds is not None:
                return Result(False, steps, f"publication_error: {published_gds}",
                              {"reason": "publication_error"})

            if request.cleanup_policy in ("success", "always") and remote_dir:
                self._cleanup(remote_dir, request, steps)
            return Result(True, steps, None, {
                "action": "export", "reason": "completed", "gds_path": str(output_path),
                "log_path": str(log_path), "gds_size": gds_size,
                "translated_structures": _translated_structures(log_text),
                "warnings": _xstream_warnings(log_text),
                "remote_run_dir": remote_dir,
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def _gds_import(self, request: GdsRequest) -> Result:
        gds_file = _require_text(request.file_path, "file_path")
        tech_lib = _require_text(request.tech_lib, "tech_lib")
        steps: list[dict[str, Any]] = []
        try:
            timeout = float(request.timeout or 600)
            interval = float(request.poll_interval or 3.0)
            for name in (request.library, tech_lib):
                exists = self._sql(
                    f"if(ddGetObj({basic.q(name)}) t nil)", request.token, request.timeout,
                )
                steps.append(_step(f"library:{name}", exists is True, exists))
                if exists is not True:
                    return Result(False, steps, f"target_lib_missing: {name}",
                                  {"reason": "target_lib_missing"})

            tool = self.middle.run_command("command -v strmin || which strmin", timeout=30, token=request.token)
            steps.append(_step("strmin", tool.returncode == 0, tool))
            if tool.returncode != 0:
                return Result(False, steps, "tool_missing: strmin not found",
                              {"reason": "tool_missing"})

            workdir_raw = self._q("getWorkingDir()", request.token, request.timeout).strip()
            workdir = workdir_raw.strip('"')
            if not workdir:
                return Result(False, steps, "getWorkingDir() returned nothing")

            gds_name = _safe_name(Path(gds_file).name, "input.gds")
            remote_gds = posixpath.join(workdir, gds_name)
            if request.file_is_local:
                staged = self.middle.upload_file(
                    Path(gds_file), remote_gds, timeout=request.timeout, token=request.token,
                )
            else:
                staged = self.middle.run_command(
                    f"cp {shlex.quote(gds_file)} {shlex.quote(remote_gds)}",
                    timeout=120, token=request.token,
                )
            steps.append(_step("stage_gds", staged.returncode == 0, staged))
            if staged.returncode != 0:
                return Result(False, steps, f"staging_error: {staged.stderr}",
                              {"reason": "staging_error"})

            extra_args = ""
            for label, path_value, is_local, flag in (
                ("stage_layermap", request.layer_map, request.layer_map_is_local, "-layerMap"),
                ("stage_refs", request.ref_lib_file, request.ref_lib_file_is_local, "-refLibList"),
            ):
                if not path_value:
                    continue
                staged_name = _safe_name(Path(path_value).name, flag.lstrip("-"))
                remote_path = posixpath.join(workdir, staged_name)
                if is_local:
                    stage = self.middle.upload_file(
                        Path(path_value), remote_path, timeout=request.timeout, token=request.token,
                    )
                else:
                    stage = self.middle.run_command(
                        f"cp {shlex.quote(path_value)} {shlex.quote(remote_path)}",
                        timeout=60, token=request.token,
                    )
                steps.append(_step(label, stage.returncode == 0, stage))
                if stage.returncode != 0:
                    return Result(False, steps, f"staging_error: {stage.stderr}",
                                  {"reason": "staging_error"})
                extra_args += f" {flag} {shlex.quote(remote_path)}"

            # strmin selects the input structure by name with ``-topCell`` (its
            # "use -cell" hint in XSTRM-80009 is a vendor typo: -cell is not a
            # valid option, see `strmin -help`).
            top_arg = f" -topCell {shlex.quote(request.top_cell)}" if request.top_cell else ""
            log_name = posixpath.join(workdir, "strmIn.log")
            command = (
                f"cd {shlex.quote(workdir)} && rm -f strmIn.log && "
                f"nohup strmin -library {shlex.quote(request.library)} "
                f"-strmFile {shlex.quote(remote_gds)} "
                f"-attachTechFileOfLib {shlex.quote(tech_lib)} "
                f"-logFile strmIn.log{extra_args}{top_arg} -replaceBusBitChar "
                "> /dev/null 2>&1 & echo launched"
            )
            launched = self.middle.run_command(command, timeout=60, token=request.token)
            steps.append(_step("strmin", launched.returncode == 0, launched))
            if launched.returncode != 0:
                return Result(False, steps, launched.stderr or "strmin launch failed")

            deadline = time.monotonic() + timeout
            log_text, failure = "", ""
            while True:
                poll = self.middle.run_command(
                    f"tail -n 400 {shlex.quote(log_name)} 2>/dev/null",
                    timeout=60, token=request.token,
                )
                if poll.returncode == 0:
                    log_text = poll.stdout or ""
                    failure = _xstream_failure_reason(log_text)
                    if failure or ("XSTRM-234" in log_text and "Translation completed" in log_text):
                        break
                self._skill("ddUpdateLibList()", request.token, request.timeout)
                if time.monotonic() >= deadline:
                    failure = "incomplete_log"
                    break
                time.sleep(min(interval, 10.0))

            if failure:
                return Result(False, steps, f"{failure}: {_xstream_summary(log_text)}",
                              {"reason": failure, "log_path": log_name})

            verification: dict[str, Any] = {}
            if request.top_cell:
                verification = self._verify_import(request)
            return Result(True, steps, None, {
                "action": "import", "reason": "completed", "log_path": log_name,
                "translated_structures": _translated_structures(log_text),
                **verification,
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    def _verify_import(self, request: GdsRequest) -> dict[str, Any]:
        raw = self._q(
            "let((vbCv) "
            f"vbCv = dbOpenCellViewByType({basic.q(request.library)} "
            f"{basic.q(request.top_cell or '')} {basic.q(request.view)} "
            f"{basic.q(request.view_type)} \"r\") "
            "if(vbCv "
            "let((vbOut) vbOut = list(length(vbCv~>shapes) length(vbCv~>instances) "
            "list(list(xCoord(car(vbCv~>bBox)) yCoord(car(vbCv~>bBox))) "
            "list(xCoord(cadr(vbCv~>bBox)) yCoord(cadr(vbCv~>bBox))))) "
            "dbClose(vbCv) vbOut) nil))",
            request.token, request.timeout,
        )
        parsed = basic.parse_sexpr(raw.strip()) if raw.strip() else None
        if not isinstance(parsed, list) or len(parsed) < 3:
            return {}
        return {
            "shape_count": _i(parsed[0], 0),
            "instance_count": _i(parsed[1], 0),
            "bbox": _bbox_value(parsed[2]),
        }

    def _publish_remote(self, remote: str, local: Path, request: GdsRequest) -> str | None:
        """Download ``remote`` to ``local`` atomically; returns an error string or None."""
        try:
            local.parent.mkdir(parents=True, exist_ok=True)
            temp = local.with_name(f".{local.name}.part")
            if temp.exists():
                temp.unlink()
            result = self.middle.download_file(remote, temp, timeout=request.timeout, token=request.token)
            if result.returncode != 0:
                return result.stderr or f"download failed: {remote}"
            if not temp.exists() or temp.stat().st_size == 0:
                temp.unlink(missing_ok=True)
                return f"empty artifact: {remote}"
            os.replace(temp, local)
            return None
        except Exception as exc:  # noqa: BLE001
            return f"{type(exc).__name__}: {exc}"

    def _publish_remote_copy(self, remote: str, dest: str,
                             request: GdsRequest) -> str | None:
        """Copy ``remote`` to a remote ``dest``; returns an error string or None."""
        if not posixpath.isabs(dest):
            return f"file_is_local=false requires an absolute remote path: {dest}"
        outcome = self.middle.run_command(
            f"cp {shlex.quote(remote)} {shlex.quote(dest)} && "
            f"test -s {shlex.quote(dest)}",
            timeout=request.timeout, token=request.token,
        )
        if outcome.returncode != 0:
            return outcome.stderr or f"remote publish failed: {remote} -> {dest}"
        return None

    def _cleanup(self, remote_dir: str, request: GdsRequest,
                 steps: list[dict[str, Any]]) -> None:
        if ".." in remote_dir or not remote_dir.endswith("/xstream/" + remote_dir.rsplit("/", 1)[-1]):
            steps.append(_step("cleanup", False, "refusing to clean unexpected path"))
            return
        result = self.middle.run_command(
            f"rm -rf {shlex.quote(remote_dir)}", timeout=60, token=request.token,
        )
        steps.append(_step("cleanup", result.returncode == 0, result))

    def _dismiss_xstream_windows(self, request: GdsRequest,
                                 steps: list[dict[str, Any]]) -> None:
        """Close XStream's own dialogs; the completion box is modal to the CIW.

        ``?showCompletionMsgBox "false"`` does not reliably suppress the box on
        IC6.1.8, and a modal box blocks every later SKILL call, so the export
        cleans up its own windows (XStream form / completion box) and touches
        nothing else.
        """
        try:
            listing = gui.Package(self.middle).list_windows(
                gui.ListWindowsRequest(token=request.token, timeout=request.timeout)
            )
            if not listing.ok:
                return
            for item in listing.windows:
                title = str(item.get("title") or "").lower()
                if "stream out translation complete" in title:
                    key = "enter"
                elif title in ("xstream out", "stream out"):
                    key = "escape"
                else:
                    continue
                result = gui.Package(self.middle).send_key(
                    gui.SendKeyRequest(
                        token=request.token, window_id=str(item.get("window_id")),
                        key=key, timeout=request.timeout,
                    )
                )
                steps.append(_step(f"dismiss:{item.get('title')}", result.ok, item.get("window_id")))
        except Exception as exc:  # noqa: BLE001 - best effort cleanup
            steps.append(_step("dismiss", False, f"{type(exc).__name__}: {exc}"))

    # -- screenshot -------------------------------------------------------------

    def screenshot(self, request: ScreenshotRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        _require_bool(request.toplevel, "toplevel")
        _require_bool(request.central_widget, "central_widget")
        _require_bool(request.leave_open, "leave_open")
        region = _bbox(request.region, "region") if request.region is not None else None
        steps: list[dict[str, Any]] = []
        remote_png: str | None = None
        try:
            root = self._role_root(request.token, "daemon")
            remote_png = posixpath.join(
                root, "screenshots",
                f"{_safe_name(request.cell)}-{int(time.time() * 1000)}.png",
            )
            quoted = shlex.quote(remote_png)
            prepared = self.middle.run_command(
                f"mkdir -p $(dirname {quoted})", timeout=60, token=request.token,
            )
            steps.append(_step("mkdir", prepared.returncode == 0, prepared))
            if prepared.returncode != 0:
                return Result(False, steps, prepared.stderr or "mkdir failed")
            run = self._skill(_screenshot_skill(request, region, remote_png), request.token, request.timeout)
            steps.append(_step("capture", run.ok, run))
            if not run.ok:
                return Result(False, steps, "; ".join(run.errors) or "screenshot failed")
            verify = self.middle.run_command(
                f"if [ -s {shlex.quote(remote_png)} ]; then wc -c < {shlex.quote(remote_png)}; "
                "else echo 0; fi",
                timeout=60, token=request.token,
            )
            steps.append(_step("verify", verify.returncode == 0, verify))
            size = (verify.stdout or "").strip()
            if verify.returncode != 0 or not size or size == "0":
                return Result(False, steps, "hiWindowSaveImage produced no image")
            local_dir = artifact_dir() / "screenshots"
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / Path(remote_png).name
            downloaded = self.middle.download_file(
                remote_png, local_path, timeout=request.timeout, token=request.token,
            )
            steps.append(_step("download", downloaded.returncode == 0, downloaded))
            if downloaded.returncode != 0:
                return Result(False, steps, downloaded.stderr or "download failed")
            return Result(True, steps, None, {"local_path": str(local_path)})
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")
        finally:
            if remote_png:
                try:
                    self.middle.run_command(
                        f"rm -f {shlex.quote(remote_png)}", timeout=10, token=request.token,
                    )
                except Exception:  # noqa: BLE001
                    pass


# ---------------------------------------------------------------------------
# SKILL templates
# ---------------------------------------------------------------------------

def _read_skill(request: ReadRequest) -> str:
    lib = basic.q(request.library)
    cell = basic.q(request.cell)
    view = basic.q(request.view)
    view_type = basic.q(request.view_type)
    shape_body = f'''
  foreach(vbShape vbCv~>shapes
    vbBBox = when(vbShape~>bBox
      list(list(xCoord(car(vbShape~>bBox)) yCoord(car(vbShape~>bBox)))
           list(xCoord(cadr(vbShape~>bBox)) yCoord(cadr(vbShape~>bBox)))))
    vbPoints = when(vbShape~>points
      mapcar(lambda((p) list(xCoord(p) yCoord(p))) vbShape~>points))
    vbXY = when(vbShape~>xy list(xCoord(vbShape~>xy) yCoord(vbShape~>xy)))
    vbOut = cons(list("shape"
      if(vbShape~>objType vbShape~>objType "unknown")
      if(vbShape~>layerName vbShape~>layerName "")
      if(vbShape~>purpose vbShape~>purpose "")
      vbBBox vbPoints
      if(vbShape~>width vbShape~>width 0)
      if(vbShape~>theLabel vbShape~>theLabel "")
      vbXY
      if(vbShape~>height vbShape~>height 0)
      if(vbShape~>justify vbShape~>justify "")
      if(vbShape~>orient vbShape~>orient "")
      if(vbShape~>font vbShape~>font "")
      if(vbShape~>pathStyle vbShape~>pathStyle "")) vbOut))
'''
    if request.depth:
        layers = _filter_layers(request.object_filter)
        region = _filter_region(request.object_filter)
        if not layers or not region:
            raise ValueError("depth > 0 requires layers and region filters")
        bbox = _bbox_expr(_bbox(region))
        lpp_list = "list(" + " ".join(_lpp_expr(*item) for item in layers) + ")"
        shape_body = f'''
  foreach(vbLpp {lpp_list}
    foreach(vbItem dbShapeQuery(vbCv vbLpp {bbox} 0 {request.depth})
      vbShape = vbItem
      while(listp(vbShape) vbShape = cadr(vbShape))
      vbBBox = when(vbShape~>bBox
        list(list(xCoord(car(vbShape~>bBox)) yCoord(car(vbShape~>bBox)))
             list(xCoord(cadr(vbShape~>bBox)) yCoord(cadr(vbShape~>bBox)))))
      vbPoints = when(vbShape~>points
        mapcar(lambda((p) list(xCoord(p) yCoord(p))) vbShape~>points))
      vbOut = cons(list("shape"
        if(vbShape~>objType vbShape~>objType "unknown")
        if(vbShape~>layerName vbShape~>layerName "")
        if(vbShape~>purpose vbShape~>purpose "")
        vbBBox vbPoints
        if(vbShape~>width vbShape~>width 0)
        if(vbShape~>theLabel vbShape~>theLabel "")
        when(vbShape~>xy list(xCoord(vbShape~>xy) yCoord(vbShape~>xy)))
        if(vbShape~>height vbShape~>height 0)
        if(vbShape~>justify vbShape~>justify "")
        if(vbShape~>orient vbShape~>orient "")
        if(vbShape~>font vbShape~>font "")
        if(vbShape~>pathStyle vbShape~>pathStyle "")) vbOut)))
'''
    return f'''
let((vbCv vbOut vbCollected vbShape vbInst vbVia vbItem vbLpp vbBBox vbPoints vbXY)
  vbCv = dbOpenCellViewByType({lib} {cell} {view} {view_type} "r")
  unless(vbCv error("layout view not found"))
  vbCollected = errset(progn(vbOut = nil
  vbOut = cons(list("summary"
    list(list(xCoord(car(vbCv~>bBox)) yCoord(car(vbCv~>bBox)))
         list(xCoord(cadr(vbCv~>bBox)) yCoord(cadr(vbCv~>bBox))))
    length(vbCv~>shapes) length(vbCv~>instances) length(vbCv~>vias)) vbOut)
{shape_body}
  foreach(vbInst vbCv~>instances
    vbBBox = when(vbInst~>bBox
      list(list(xCoord(car(vbInst~>bBox)) yCoord(car(vbInst~>bBox)))
           list(xCoord(cadr(vbInst~>bBox)) yCoord(cadr(vbInst~>bBox)))))
    vbXY = when(vbInst~>xy list(xCoord(vbInst~>xy) yCoord(vbInst~>xy)))
    vbOut = cons(list("instance"
      if(vbInst~>objType vbInst~>objType "inst")
      if(vbInst~>name vbInst~>name "")
      if(vbInst~>libName vbInst~>libName "")
      if(vbInst~>cellName vbInst~>cellName "")
      if(vbInst~>viewName vbInst~>viewName "")
      vbXY
      if(vbInst~>orient vbInst~>orient "")
      if(listp(vbInst~>numInst) car(vbInst~>numInst)
         if(vbInst~>numInst vbInst~>numInst 1))
      vbBBox
      if(listp(vbInst~>rows) car(vbInst~>rows)
         if(vbInst~>rows vbInst~>rows 0))
      if(listp(vbInst~>columns) car(vbInst~>columns)
         if(vbInst~>columns vbInst~>columns 0))) vbOut))
  foreach(vbVia vbCv~>vias
    vbBBox = when(vbVia~>bBox
      list(list(xCoord(car(vbVia~>bBox)) yCoord(car(vbVia~>bBox)))
           list(xCoord(cadr(vbVia~>bBox)) yCoord(cadr(vbVia~>bBox)))))
    vbXY = when(vbVia~>xy list(xCoord(vbVia~>xy) yCoord(vbVia~>xy)))
    vbOut = cons(list("via"
      vbXY
      if(vbVia~>orient vbVia~>orient "")
      vbBBox
      if(vbVia~>cutLayer vbVia~>cutLayer 0)) vbOut))
  vbOut))
  dbClose(vbCv)
  unless(vbCollected error("layout read failed"))
  reverse(car(vbCollected)))
'''.strip()


def _xstream_skill(lib: str, top_cell: str, view: str, stream_file: str,
                   layer_map: str, log_file: str, run_dir: str) -> str:
    fields = (
        ("library", lib, "vbOldLibrary"),
        ("topCell", top_cell, "vbOldTopCell"),
        ("view", view, "vbOldView"),
        ("strmFile", stream_file, "vbOldStreamFile"),
        ("layerMap", layer_map, "vbOldLayerMap"),
        ("logFile", log_file, "vbOldLogFile"),
        ("runDir", run_dir, "vbOldRunDir"),
        # virtualMemory=false: translate the saved cellview from disk and stay
        # non-blocking; the completion message box must stay off for batch use.
        ("virtualMemory", "false", "vbOldVirtualMemory"),
    )
    old_vars = " ".join([old for _f, _v, old in fields] + ["vbOldShowMsgBox", "vbCaptured"])
    captures = "".join(f'{old} = xstGetField("{name}") ' for name, _value, old in fields)
    captures += 'vbOldShowMsgBox = xstGetField("showCompletionMsgBox") '
    setters = "".join(f'xstSetField("{name}" {basic.q(value)}) ' for name, value, _old in fields)
    setters += 'xstSetField("showCompletionMsgBox" "false") '
    restores = "".join(
        f'vbCleanup = errset(xstSetField("{name}" {old}) nil) '
        f'unless(vbCleanup vbFailures = cons("restore {name} failed" vbFailures)) '
        for name, _value, old in fields
    )
    restores += (
        'vbCleanup = errset(xstSetField("showCompletionMsgBox" vbOldShowMsgBox) nil) '
        'unless(vbCleanup vbFailures = cons("restore showCompletionMsgBox failed" vbFailures)) '
    )
    return (
        f"let(({old_vars} vbAttempt vbFailure vbCleanup vbFailures) "
        'vbFailure = "XStream export request failed" '
        "unwindProtect("
        "progn("
        "vbAttempt = errset(progn("
        "unless(and(isCallable('xstGetField) isCallable('xstSetField) "
        'isCallable(\'xstOutDoTranslate)) error("XStream APIs unavailable")) '
        f"{captures}"
        "vbCaptured = t "
        f"{setters}"
        "xstOutDoTranslate()) nil) "
        'unless(vbAttempt vbFailure = sprintf(nil "%L" errset.errset)) '
        "vbAttempt) "
        "progn(when(vbCaptured "
        f"{restores}"
        "))) "
        'if(vbAttempt "started" sprintf(nil "failed: %s" vbFailure)))'
    )


def _screenshot_skill(request: ScreenshotRequest,
                      region: tuple[float, float, float, float] | None,
                      remote_path: str) -> str:
    if request.window_id is not None:
        target = (
            "let((vbW) foreach(w hiGetWindowList() "
            f"when(w~>windowNum == {int(request.window_id)} vbW = w)) vbW)"
        )
    else:
        target = (
            "let((vbW) vbW = car(setof(x hiGetWindowList() "
            "x~>cellView && "
            f"x~>cellView~>libName == {basic.q(request.library)} && "
            f"x~>cellView~>cellName == {basic.q(request.cell)} && "
            f"x~>cellView~>viewName == {basic.q(request.view)})) "
            "unless(vbW vbW = geOpen(?lib "
            f"{basic.q(request.library)} ?cell {basic.q(request.cell)} "
            f"?view {basic.q(request.view)} ?viewType {basic.q(request.view_type)} "
            '?mode "r")) vbW)'
        )
    zoom = ""
    if region is not None:
        x0, y0, x1, y1 = region
        zoom = (
            f"hiZoomIn(vbW list(list({x0:g} {y0:g}) list({x1:g} {y1:g}))) "
        )
    return (
        "let((vbW vbRc) "
        f"vbW = {target} "
        'unless(vbW error("layout window not found")) '
        f"{zoom}"
        f"vbRc = hiWindowSaveImage(?target vbW ?path {basic.q(remote_path)} "
        f"?format \"png\" ?toplevel {'t' if request.toplevel else 'nil'} "
        f"?centralWidget {'t' if request.central_widget else 'nil'}) "
        f"unless({'t' if request.leave_open else 'nil'} when(vbW hiCloseWindow(vbW))) "
        'if(vbRc "saved" "capture-failed"))'
    )


# ---------------------------------------------------------------------------
# Parsing / filtering
# ---------------------------------------------------------------------------

def _parse_read(raw: str) -> dict[str, Any]:
    parsed = basic.parse_sexpr(raw.strip())
    result: dict[str, Any] = {
        "bbox": None, "shape_count": 0, "instance_count": 0, "via_count": 0,
        "shapes": [], "instances": [], "vias": [],
    }
    if not isinstance(parsed, list):
        return result
    for record in parsed:
        if not isinstance(record, list) or not record:
            continue
        kind = str(record[0])
        if kind == "summary" and len(record) >= 5:
            result["bbox"] = _bbox_value(record[1])
            result["shape_count"] = _i(record[2], 0)
            result["instance_count"] = _i(record[3], 0)
            result["via_count"] = _i(record[4], 0)
        elif kind == "shape" and len(record) >= 14:
            result["shapes"].append({
                "kind": _s(record[1]), "layer": _s(record[2]), "purpose": _s(record[3]),
                "lpp": [_s(record[2]), _s(record[3])],
                "bbox": _bbox_value(record[4]), "points": _points_value(record[5]),
                "width": _f(record[6]) or None, "text": _s(record[7]) or None,
                "xy": _point_value(record[8]), "height": _f(record[9]) or None,
                "justify": _s(record[10]) or None, "orient": _s(record[11]) or None,
                "font": _s(record[12]) or None, "path_style": _s(record[13]) or None,
            })
        elif kind == "instance" and len(record) >= 12:
            result["instances"].append({
                "kind": _s(record[1]) or "inst", "name": _s(record[2]),
                "master_lib": _s(record[3]), "master_cell": _s(record[4]),
                "master_view": _s(record[5]), "xy": _point_value(record[6]),
                "orient": _s(record[7]) or None, "num_inst": _i(record[8], 1),
                "bbox": _bbox_value(record[9]),
                "rows": _i(record[10], 0) or None, "cols": _i(record[11], 0) or None,
            })
        elif kind == "via" and len(record) >= 5:
            result["vias"].append({
                "xy": _point_value(record[1]),
                "orient": _s(record[2]) or None, "bbox": _bbox_value(record[3]),
                "cut_layer": _i(record[4], 0) or None,
            })
    return result


def _filter_entry(object_filter: dict[str, Any] | None, name: str) -> Any:
    if not object_filter:
        return "all"
    return object_filter.get(name, "all")


def _filter_layers(object_filter: dict[str, Any] | None) -> list[tuple[str, str]]:
    entry = _filter_entry(object_filter, "shape")
    if not isinstance(entry, dict):
        return []
    layers = entry.get("layers")
    if not isinstance(layers, list):
        return []
    result: list[tuple[str, str]] = []
    for item in layers:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            result.append((str(item[0]), str(item[1])))
    return result


def _filter_region(object_filter: dict[str, Any] | None) -> list[float] | None:
    for name in ("shape", "instance", "via"):
        entry = _filter_entry(object_filter, name)
        if isinstance(entry, dict) and entry.get("region") is not None:
            region = entry["region"]
            if not isinstance(region, (list, tuple)) or len(region) != 4:
                raise ValueError(f"{name}.region must be [x0, y0, x1, y1]")
            return [float(item) for item in region]
    return None


def _filter_layers_or_region(object_filter: dict[str, Any] | None) -> bool:
    if not object_filter:
        return False
    return bool(_filter_layers(object_filter) or _filter_region(object_filter))


def _bbox_hit(bbox: list[list[float]] | None, region: list[float],
              mode: str) -> bool:
    if not bbox or len(bbox) != 2:
        return False
    x0, y0, x1, y1 = region
    bx0, by0 = bbox[0]
    bx1, by1 = bbox[1]
    if mode == "contain":
        return bx0 >= x0 and by0 >= y0 and bx1 <= x1 and by1 <= y1
    return bx1 >= x0 and bx0 <= x1 and by1 >= y0 and by0 <= y1


def _apply_read_filters(parsed: dict[str, Any], request: ReadRequest) -> dict[str, Any]:
    focus = set(request.focus) if request.focus else {"summary", "shapes", "instances", "vias"}
    filters = request.object_filter or {}
    value: dict[str, Any] = {}

    if "summary" in focus:
        counts: dict[str, int] = {}
        for item in parsed["shapes"]:
            key = f"{item['layer']}/{item['purpose']}"
            counts[key] = counts.get(key, 0) + 1
        value.update({
            "bbox": parsed["bbox"],
            "shape_count": parsed["shape_count"],
            "instance_count": parsed["instance_count"],
            "via_count": parsed["via_count"],
            "layer_counts": counts,
        })

    region = _filter_region(request.object_filter)
    if "shapes" in focus and _filter_entry(filters, "shape") != "none":
        entry = _filter_entry(filters, "shape")
        wanted_types = None
        wanted_layers = None
        if isinstance(entry, dict):
            if isinstance(entry.get("types"), list) and entry["types"]:
                wanted_types = {str(item) for item in entry["types"]}
            layers = _filter_layers(filters)
            if layers:
                wanted_layers = {(layer, purpose) for layer, purpose in layers}
        shapes = []
        for item in parsed["shapes"]:
            if wanted_types is not None and item["kind"] not in wanted_types:
                continue
            if wanted_layers is not None and (item["layer"], item["purpose"]) not in wanted_layers:
                continue
            if region is not None and not _bbox_hit(item["bbox"], region, request.region_mode):
                continue
            shapes.append(item)
        if request.detail == "index":
            shapes = [
                {"kind": item["kind"], "layer": item["layer"], "purpose": item["purpose"],
                 "lpp": item["lpp"]}
                for item in shapes
            ]
        value["shapes"] = shapes

    if "instances" in focus and _filter_entry(filters, "instance") != "none":
        entry = _filter_entry(filters, "instance")
        names = None
        if isinstance(entry, dict) and isinstance(entry.get("names"), list) and entry["names"]:
            names = {str(item) for item in entry["names"]}
        instances = []
        for item in parsed["instances"]:
            if names is not None and item["name"] not in names:
                continue
            if region is not None and not _bbox_hit(item["bbox"], region, request.region_mode):
                continue
            instances.append(item)
        value["instances"] = instances

    if "vias" in focus and _filter_entry(filters, "via") != "none":
        vias = []
        for item in parsed["vias"]:
            if region is not None and not _bbox_hit(item["bbox"], region, request.region_mode):
                continue
            vias.append(item)
        value["vias"] = vias
    return value


def _xstream_failure_reason(log_text: str) -> str:
    if not log_text:
        return ""
    for line in log_text.splitlines():
        text = line.strip()
        if "XSTRM-273" in text or "Translation failed" in text or "OPEN_FAILED" in text:
            return "xstream_failure"
    return ""


def _xstream_warnings(log_text: str) -> list[str]:
    """Layer-map / overwrite diagnostics worth surfacing to the caller."""
    notes: list[str] = []
    for line in log_text.splitlines():
        text = line.strip()
        if "XSTRM-25" in text and "invalid record" in text:
            notes.append(text[:300])
        elif "XSTRM-20" in text:
            notes.append(text[:300])
        elif "Dropped Layers" in text:
            notes.append(text[:300])
    return notes


def _xstream_summary(log_text: str) -> str:
    for line in log_text.splitlines():
        text = line.strip()
        if ("ERROR" in text or "XSTRM" in text) and text:
            return text[:300]
    return "no diagnostic line in log"


def _translated_structures(log_text: str) -> list[str]:
    pattern = re.compile(
        r"Translating\s+cellview\s+(\S+)\s+as\s+STRUCTURE\s+(\S+?)\.?\s*$",
        re.IGNORECASE,
    )
    result: list[str] = []
    for line in log_text.splitlines():
        match = pattern.search(line.strip())
        if match:
            result.append(f"{match.group(1)} -> {match.group(2)}")
    return result


def _window_expr(request: Any, lib_expr: str) -> str:
    if getattr(request, "window_id", None) is not None:
        return (
            "let((vbW) foreach(w hiGetWindowList() "
            f"when(w~>windowNum == {int(request.window_id)} vbW = w)) vbW)"
        )
    return (
        "let((vbW) vbW = car(setof(x hiGetWindowList() "
        f"x~>cellView && x~>cellView~>libName == {lib_expr} && "
        f"x~>cellView~>cellName == {basic.q(request.cell)} && "
        f"x~>cellView~>viewName == {basic.q(request.view)})) "
        f"unless(vbW vbW = geOpen(?lib {lib_expr} ?cell {basic.q(request.cell)} "
        f"?view {basic.q(request.view)} ?viewType {basic.q(request.view_type)} ?mode \"r\")) "
        "vbW)"
    )


#: spec 上层 §4.2: package-level self-description
OPERATIONS = (
    ("virtuoso.layout.read", "read", ReadRequest, Result),
    ("virtuoso.layout.write", "write", WriteRequest, Result),
    ("virtuoso.layout.gds", "gds", GdsRequest, Result),
    ("virtuoso.layout.screenshot", "screenshot", ScreenshotRequest, Result),
    ("virtuoso.layout.display", "display", DisplayRequest, Result),
)

OPERATION_NAMES = tuple(operation for operation, *_ in OPERATIONS)

__all__ = [
    "DisplayRequest", "GdsRequest", "LAYOUT_VIEW_TYPE", "OPERATIONS", "OPERATION_NAMES",
    "Package", "ReadRequest", "Result", "ScreenshotRequest", "WriteRequest",
]
