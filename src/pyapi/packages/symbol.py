"""``symbol`` business package: semantic read, batched write, and TSG generation.

Spec: ``spec/design-concepts/上层/3-symbol.md`` (Draft v2).

The package only calls the middle ``execute_skill`` / ``run_command`` /
``download_file`` interfaces.  Manual writes are append-only: an existing
``schematicSymbol`` view is opened in mode ``"a"``; creating an empty view is
the cellview package's responsibility.
"""
from __future__ import annotations

import posixpath
import re
import shlex
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from common.paths import artifact_dir
from pyapi.models import Middle, VirtuosoResult
from pyapi.packages import basic
from pyapi.packages._symbol_generate import generate_skill, parse_generation_output


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
    view: str = "symbol"
    view_type: str = "schematicSymbol"
    focus: list[str] | None = None
    timeout: int | None = None


@dataclass(frozen=True)
class WriteRequest:
    token: str
    library: str
    cell: str
    commands: list[dict[str, Any]]
    view: str = "symbol"
    view_type: str = "schematicSymbol"
    timeout: int | None = None


@dataclass(frozen=True)
class CheckSaveRequest:
    token: str
    library: str
    cell: str
    view: str = "symbol"
    view_type: str = "schematicSymbol"
    timeout: int | None = None


@dataclass(frozen=True)
class GenerateRequest:
    token: str
    library: str
    cell: str
    schematic_view: str = "schematic"
    symbol_view: str = "symbol"
    sort_pins: str | None = None
    overwrite: bool = False
    timeout: int | None = None


@dataclass(frozen=True)
class ScreenshotRequest:
    token: str
    library: str
    cell: str
    view: str = "symbol"
    view_type: str = "schematicSymbol"
    window_id: int | None = None
    region: list[float] | None = None
    toplevel: bool = True
    central_widget: bool = True
    leave_open: bool = False
    timeout: int | None = None


# ---------------------------------------------------------------------------
# Validation / formatting helpers
# ---------------------------------------------------------------------------

def _step(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


def _require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
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
    x0, y0, x1, y1 = (_number(item, name) for item in value)
    if x0 >= x1 or y0 >= y1:
        raise ValueError(f"{name} requires x0 < x1 and y0 < y1")
    return x0, y0, x1, y1


def _points(value: Any, name: str, *, minimum: int = 2) -> list[tuple[float, float]]:
    if not isinstance(value, list) or len(value) < minimum:
        raise ValueError(f"{name} must be a list with at least {minimum} points")
    return [_point(item, f"{name}[{index}]") for index, item in enumerate(value)]


def _lpp_expr(layer: str, purpose: str) -> str:
    return f"list({basic.q(layer)} {basic.q(purpose)})"


def _point_expr(point: tuple[float, float]) -> str:
    return f"list({point[0]:g} {point[1]:g})"


def _points_expr(points: list[tuple[float, float]]) -> str:
    return "list(" + " ".join(_point_expr(point) for point in points) + ")"


def _bbox_expr(bbox: tuple[float, float, float, float]) -> str:
    x0, y0, x1, y1 = bbox
    return f"list({_point_expr((x0, y0))} {_point_expr((x1, y1))})"


def _label_choice(label_kind: str) -> tuple[str, str]:
    if label_kind == "pin_name":
        return "pin name", "normalLabel"
    if label_kind == "instance":
        return "instance label", "NLPLabel"
    if label_kind == "logical":
        return "logical label", "NLPLabel"
    raise ValueError("label_kind must be drawing/pin_name/instance/logical")


def _label_defaults(label_kind: str) -> dict[str, Any]:
    if label_kind == "instance":
        return {"justify": "centerLeft", "orient": "R0", "font": "stick", "height": 0.0625}
    if label_kind == "logical":
        return {"justify": "centerCenter", "orient": "R0", "font": "stick", "height": 0.0625}
    if label_kind == "pin_name":
        return {"justify": "centerLeft", "orient": "R0", "font": "stick", "height": 0.0625}
    return {"justify": "lowerLeft", "orient": "R0", "font": "stick", "height": 0.0625}


def _label_text(label_kind: str, command: dict[str, Any], *, required: bool) -> str | None:
    if command.get("text"):
        return str(command["text"])
    if label_kind == "instance":
        return "[@instanceName]"
    if label_kind == "logical":
        return "[@partName]"
    if required:
        raise ValueError("command.text is required")
    return None


def _label_lpp(label_kind: str) -> tuple[str, str] | None:
    if label_kind == "pin_name":
        return "pin", "label"
    if label_kind == "instance":
        return "instance", "label"
    if label_kind == "logical":
        return "device", "label"
    return None


def _match_bbox_expr(binding: str, bbox: tuple[float, float, float, float],
                     tol: float = 0.001) -> str:
    x0, y0, x1, y1 = bbox
    return (
        f"{binding}~>bBox && "
        f"xCoord(car({binding}~>bBox)) >= {x0 - tol:g} && "
        f"xCoord(car({binding}~>bBox)) <= {x0 + tol:g} && "
        f"yCoord(car({binding}~>bBox)) >= {y0 - tol:g} && "
        f"yCoord(car({binding}~>bBox)) <= {y0 + tol:g} && "
        f"xCoord(cadr({binding}~>bBox)) >= {x1 - tol:g} && "
        f"xCoord(cadr({binding}~>bBox)) <= {x1 + tol:g} && "
        f"yCoord(cadr({binding}~>bBox)) >= {y1 - tol:g} && "
        f"yCoord(cadr({binding}~>bBox)) <= {y1 + tol:g}"
    )


def _points_match_expr(binding: str, points: list[tuple[float, float]],
                       tol: float = 0.001) -> str:
    parts = [f"length({binding}~>points) == {len(points)}"]
    for index, (x, y) in enumerate(points):
        parts.append(
            f"abs(xCoord(nth({index} {binding}~>points)) - {x:g}) <= {tol:g} && "
            f"abs(yCoord(nth({index} {binding}~>points)) - {y:g}) <= {tol:g}"
        )
    return " && ".join(parts)


def _shape_match_expr(kind: str, command: dict[str, Any]) -> str:
    points: list[tuple[float, float]] | None = None
    if "bbox" in command:
        bbox = _bbox(command["bbox"])
    elif "points" in command:
        points = _points(command["points"], "command.points")
        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        bbox = (min(xs), min(ys), max(xs), max(ys))
    else:
        raise ValueError("shape command requires bbox or points")
    if points is None and kind in ("line", "polygon") and "points" in command:
        points = _points(command["points"], "command.points")
    parts = [
        f'x~>objType == {basic.q(kind)}',
        _match_bbox_expr("x", bbox),
    ]
    if command.get("layer"):
        parts.append(f"x~>layerName == {basic.q(command['layer'])}")
    if command.get("purpose"):
        parts.append(f"x~>purpose == {basic.q(command['purpose'])}")
    if points is not None:
        parts.append(_points_match_expr("x", points))
    return " && ".join(parts)


def _label_xy(command: dict[str, Any]) -> tuple[float, float]:
    if "xy" in command:
        return _point(command["xy"], "command.xy")
    return _number(command.get("x"), "command.x"), _number(command.get("y"), "command.y")


def _label_match_expr(label_kind: str, command: dict[str, Any]) -> str:
    x, y = _label_xy(command)
    parts = [
        'x~>objType == "label"',
        f"xCoord(x~>xy) >= {x - 0.001:g}",
        f"xCoord(x~>xy) <= {x + 0.001:g}",
        f"yCoord(x~>xy) >= {y - 0.001:g}",
        f"yCoord(x~>xy) <= {y + 0.001:g}",
    ]
    text = _label_text(label_kind, command, required=False)
    if text:
        parts.append(f"x~>theLabel == {basic.q(text)}")
    expected = _label_lpp(label_kind)
    if expected is not None:
        parts.append(f"x~>layerName == {basic.q(expected[0])}")
        parts.append(f"x~>purpose == {basic.q(expected[1])}")
    elif command.get("layer"):
        parts.append(f"x~>layerName == {basic.q(command['layer'])}")
    elif label_kind == "drawing":
        parts.append('x~>labelType == "normalLabel"')
    if command.get("purpose") and expected is None:
        parts.append(f"x~>purpose == {basic.q(command['purpose'])}")
    return " && ".join(parts)


def _pin_match_expr(name: str) -> str:
    return f'x~>objType == "label" && x~>layerName == "pin" && x~>purpose == "label" && x~>theLabel == {basic.q(name)}'


def _safe_name(value: str, fallback: str = "cell") -> str:
    """Restrict a caller-supplied name to a shell/file-safe token."""
    cleaned = re.sub(r"[^0-9A-Za-z_.-]+", "_", value).strip("_")
    return cleaned or fallback


# ---------------------------------------------------------------------------
# Package
# ---------------------------------------------------------------------------

class Package:
    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    # -- low-level Skill helpers ------------------------------------------------
    def _skill(self, expr: str, token: str, timeout: int | float | None = None) -> VirtuosoResult:
        return self.middle.execute_skill(expr, timeout=timeout, token=token)

    def _q(self, expr: str, token: str, timeout: int | float | None = None) -> str:
        result = self._skill(expr, token, timeout)
        if not result.ok:
            raise RuntimeError("; ".join(result.errors) or "SKILL execution failed")
        return result.output or ""

    @staticmethod
    def _open_expr(lib: str, cell: str, view: str, view_type: str, mode: str) -> str:
        return (
            f"dbOpenCellViewByType({basic.q(lib)} {basic.q(cell)} "
            f"{basic.q(view)} {basic.q(view_type)} {basic.q(mode)})"
        )

    def _view_state_expr(self, lib: str, cell: str, view: str, view_type: str) -> str:
        """Return ``"ok"`` / ``"mismatch"`` / ``"missing"`` for the target view.

        ``dbOpenCellViewByType(..., "r")`` returns nil both for a missing view
        and for a view whose type differs, so existence is probed with
        ``ddGetObj`` first to keep the two failures distinguishable.
        """
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

    def _check_save_expr(self, lib: str, cell: str, view: str, view_type: str) -> str:
        """Run on the already-open global ``vbSymCv``; always release it."""
        return (
            "let((vbPinList vbSaved) "
            f"vbPinList = errset(schSymbolToPinList({basic.q(lib)} {basic.q(cell)} {basic.q(view)})) "
            "vbSaved = errset(dbSave(vbSymCv)) "
            "dbClose(vbSymCv) vbSymCv = nil "
            'unless(vbPinList && car(vbPinList) error("symbol pin-list generation failed")) '
            'unless(vbSaved && car(vbSaved) error("symbol save failed")) '
            '"saved")'
        )

    def _open_edit_expr(self, lib: str, cell: str, view: str, view_type: str) -> str:
        """Open for edit once, keep the handle in the global ``vbSymCv``.

        Returns ``"open-ok"`` or ``"locked"`` (missing/mismatch are already
        covered by ``_require_view_exists``).

        不变量：``vbSymCv`` 是会话级全局，依赖"一个 token 独占一个 CIW"；
        多 token 共用 CIW 时须改按 token 命名全局或收进单条 SKILL。
        """
        return (
            "let((vbEdit) "
            f"vbEdit = {self._open_expr(lib, cell, view, view_type, 'a')} "
            'if(vbEdit then vbSymCv = vbEdit "open-ok" else "locked"))'
        )

    def _close_edit_expr(self) -> str:
        return (
            'when(boundp(\'vbSymCv) && vbSymCv dbClose(vbSymCv)) '
            'vbSymCv = nil t'
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
                f"symbol view {request.library}/{request.cell}/{request.view} not found"
            )
        raise RuntimeError(f"unexpected view probe result: {raw.strip()!r}")

    # -- read -------------------------------------------------------------------

    def read(self, request: ReadRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        valid_focus = {"terms", "labels", "shapes", "orders", "selection_boxes"}
        if request.focus is not None:
            if not isinstance(request.focus, list) or not request.focus:
                raise ValueError("focus must be a non-empty list")
            unknown = set(request.focus) - valid_focus
            if unknown:
                raise ValueError(f"unknown focus values: {sorted(unknown)}")

        steps: list[dict[str, Any]] = []
        try:
            raw = self._q(_read_skill(request), request.token, request.timeout)
            steps.append(_step("read", True, raw))
            text = raw.strip()
            if not basic.is_single_complete_skill_list(text):
                raise RuntimeError(
                    f"symbol read output is not a single complete SKILL list: "
                    f"{text[:200]!r}"
                )
            if not isinstance(basic.parse_sexpr(text), list):
                raise RuntimeError(
                    f"symbol read output is not a list: {text[:200]!r}"
                )
            parsed = _parse_read(text)
            if request.focus is None:
                value = parsed
            else:
                value = {}
                wanted = set(request.focus)
                for key in ("terms", "labels", "shapes", "selection_boxes"):
                    if key in wanted:
                        value[key] = parsed[key]
                if "orders" in wanted:
                    value["pin_order"] = parsed["pin_order"]
                    value["port_order"] = parsed["port_order"]
                    value["term_order"] = parsed["term_order"]
            value.update({
                "library": request.library,
                "cell": request.cell,
                "view": request.view,
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
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

        opened = self._skill(
            self._open_edit_expr(request.library, request.cell, request.view, request.view_type),
            request.token,
            request.timeout,
        )
        state = (opened.output or "").strip().strip('"')
        steps.append(_step("open", opened.ok and state == "open-ok", opened))
        if not opened.ok:
            return Result(False, steps, "; ".join(opened.errors) or "open failed")
        if state != "open-ok":
            return Result(
                False, steps,
                f"symbol view {request.library}/{request.cell}/{request.view} "
                "is locked by another session",
            )

        for index, command, expr in planned:
            run = self._skill(expr, request.token, request.timeout)
            steps.append(_step(f"command:{command['op']}", run.ok, run))
            if not run.ok:
                close_run = self._skill(self._close_edit_expr(), request.token, request.timeout)
                detail = "; ".join(run.errors) or f"command {command['op']} failed"
                if not close_run.ok:
                    detail += "; additionally, releasing the edit handle failed: " + (
                        "; ".join(close_run.errors) or "unknown")
                return Result(
                    False, steps,
                    f"{detail} (commands applied: {index}/{len(planned)}; "
                    "symbol.write is not transactional)",
                )

        saved = self._skill(
            self._check_save_expr(request.library, request.cell, request.view, request.view_type),
            request.token,
            request.timeout,
        )
        steps.append(_step("check_and_save", saved.ok, saved))
        if not saved.ok:
            close_run = self._skill(self._close_edit_expr(), request.token, request.timeout)
            if not close_run.ok:
                steps.append(_step("close_edit", False, close_run))
            return Result(False, steps, "; ".join(saved.errors) or "symbol check/save failed")
        return Result(True, steps, None, {"applied": len(request.commands)})

    def check_and_save(self, request: CheckSaveRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_text(request.view_type, "view_type")
        _require_timeout(request.timeout)
        steps: list[dict[str, Any]] = []
        try:
            self._require_view_exists(request)
            opened = self._skill(
                self._open_edit_expr(request.library, request.cell, request.view, request.view_type),
                request.token,
                request.timeout,
            )
            state = (opened.output or "").strip().strip('"')
            steps.append(_step("open", opened.ok and state == "open-ok", opened))
            if not opened.ok:
                return Result(False, steps, "; ".join(opened.errors) or "open failed")
            if state != "open-ok":
                return Result(
                    False, steps,
                    f"symbol view {request.library}/{request.cell}/{request.view} "
                    "is locked by another session",
                )
            run = self._skill(
                self._check_save_expr(request.library, request.cell, request.view, request.view_type),
                request.token,
                request.timeout,
            )
            steps.append(_step("check_and_save", run.ok, run))
            if not run.ok:
                close_run = self._skill(self._close_edit_expr(), request.token, request.timeout)
                if not close_run.ok:
                    steps.append(_step("close_edit", False, close_run))
                return Result(False, steps, "; ".join(run.errors) or "symbol check/save failed")
            return Result(True, steps, None, {"saved": True})
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

    # -- atomic builders --------------------------------------------------------

    def _atomic_expr(self, command: dict[str, Any]) -> str:
        op = command.get("op")
        if not isinstance(op, str) or not op:
            raise ValueError("command.op must be a non-empty string")

        if op in ("place_line", "place_rect", "place_polygon", "place_ellipse"):
            layer = _require_text(command.get("layer"), "command.layer")
            purpose = _require_text(command.get("purpose"), "command.purpose")
            lpp = _lpp_expr(layer, purpose)
            if op == "place_line":
                body = f"dbCreateLine(vbSymCv {lpp} {_points_expr(_points(command.get('points'), 'command.points'))})"
            elif op == "place_polygon":
                body = f"dbCreatePolygon(vbSymCv {lpp} {_points_expr(_points(command.get('points'), 'command.points', minimum=3))})"
            else:
                bbox = _bbox_expr(_bbox(command.get("bbox")))
                fn = "dbCreateRect" if op == "place_rect" else "dbCreateEllipse"
                body = f"{fn}(vbSymCv {lpp} {bbox})"
            return f'let((vbShape) vbShape = {body} unless(vbShape error("shape not created")) vbShape)'

        if op in ("delete_shape", "set_shape_properties"):
            kind = _require_text(command.get("kind"), "command.kind")
            if kind not in ("line", "rect", "polygon", "ellipse"):
                raise ValueError("command.kind must be line/rect/polygon/ellipse")
            pred = _shape_match_expr(kind, command)
            find = f"let((vbShape) vbShape = car(setof(x vbSymCv~>shapes {pred})) unless(vbShape error(\"shape not found\")) "
            if op == "delete_shape":
                return find + "dbDeleteObject(vbShape))"
            assigns: list[str] = []
            if command.get("layer"):
                assigns.append(f"vbShape~>layerName = {basic.q(command['layer'])}")
            if command.get("purpose"):
                assigns.append(f"vbShape~>purpose = {basic.q(command['purpose'])}")
            if "new_points" in command:
                if kind not in ("line", "polygon"):
                    raise ValueError("points is only writable on line/polygon")
                assigns.append(
                    f"vbShape~>points = {_points_expr(_points(command['new_points'], 'command.new_points'))}"
                )
            if "new_bbox" in command:
                if kind not in ("rect", "ellipse"):
                    raise ValueError("bbox is only writable on rect/ellipse")
                assigns.append(
                    f"vbShape~>bBox = {_bbox_expr(_bbox(command['new_bbox'], 'command.new_bbox'))}"
                )
            if not assigns:
                raise ValueError("set_shape_properties requires at least one writable field")
            return find + " ".join(assigns) + " vbShape)"

        if op == "place_label":
            return self._place_label_expr(command)

        if op in ("delete_label", "rename_label", "set_label_properties"):
            label_kind = _require_text(command.get("label_kind", "drawing"), "command.label_kind")
            pred = _label_match_expr(label_kind, command)
            find = f"let((vbLabel) vbLabel = car(setof(x vbSymCv~>shapes {pred})) unless(vbLabel error(\"label not found\")) "
            if op == "delete_label":
                return find + "dbDeleteObject(vbLabel))"
            if op == "rename_label":
                return find + f"vbLabel~>theLabel = {basic.q(_require_text(command.get('new_text'), 'command.new_text'))} vbLabel~>theLabel)"
            assigns: list[str] = []
            for key in ("justify", "orient", "font"):
                if command.get(key):
                    assigns.append(f"vbLabel~>{key} = {basic.q(command[key])}")
            if "height" in command:
                assigns.append(f"vbLabel~>height = {_number(command['height'], 'command.height'):g}")
            if label_kind == "drawing":
                if command.get("layer"):
                    assigns.append(f"vbLabel~>layerName = {basic.q(command['layer'])}")
                if command.get("purpose"):
                    assigns.append(f"vbLabel~>purpose = {basic.q(command['purpose'])}")
                if command.get("label_type"):
                    assigns.append(f"vbLabel~>labelType = {basic.q(command['label_type'])}")
            if not assigns:
                raise ValueError("set_label_properties requires at least one writable field")
            return find + " ".join(assigns) + " vbLabel)"

        if op == "place_pin":
            return self._place_pin_expr(command)
        if op == "delete_pin":
            return self._delete_pin_expr(command)
        if op == "rename_pin":
            return self._rename_pin_expr(command)
        if op == "set_pin_properties":
            return self._set_pin_properties_expr(command)

        if op == "set_selection_box":
            bbox = _bbox_expr(_bbox(command.get("bbox")))
            return (
                "let((vbNew) "
                "foreach(x setof(s vbSymCv~>shapes s~>objType == \"rect\" "
                "&& s~>layerName == \"instance\" && s~>purpose == \"drawing\") "
                "dbDeleteObject(x)) "
                f"vbNew = dbCreateRect(vbSymCv {_lpp_expr('instance', 'drawing')} {bbox}) "
                'unless(vbNew error("selection box not created")) vbNew)'
            )

        if op == "set_pin_order":
            names = command.get("term_names")
            if not isinstance(names, list) or not names:
                raise ValueError("command.term_names must be a non-empty list")
            names_expr = "list(" + " ".join(basic.q(str(name)) for name in names) + ")"
            return (
                "let((vbNames) "
                f"vbNames = {names_expr} "
                "foreach(n vbNames "
                "unless(member(n mapcar(lambda((x) x~>name) vbSymCv~>terminals)) "
                'error(strcat("pin not found: " n)))) '
                "unless(schEditPinOrder(vbSymCv vbNames nil) "
                'error("schEditPinOrder failed")))'
            )

        raise ValueError(f"unknown atomic op: {op}")

    def _place_label_expr(self, command: dict[str, Any]) -> str:
        label_kind = _require_text(command.get("label_kind"), "command.label_kind")
        text = _require_text(
            _label_text(label_kind, command, required=True), "command.text",
        )
        point = _point_expr(_label_xy(command))
        defaults = _label_defaults(label_kind)
        justify = command.get("justify", defaults["justify"])
        orient = command.get("orient", defaults["orient"])
        font = command.get("font", defaults["font"])
        height = _number(command.get("height", defaults["height"]), "command.height")
        if label_kind == "drawing":
            layer = _require_text(command.get("layer"), "command.layer")
            purpose = _require_text(command.get("purpose"), "command.purpose")
            body = (
                f"dbCreateLabel(vbSymCv {_lpp_expr(layer, purpose)} {point} "
                f"{basic.q(text)} {basic.q(justify)} {basic.q(orient)} "
                f"{basic.q(font)} {height:g})"
            )
            if command.get("label_type"):
                return (
                    "let((vbLabel) "
                    f"vbLabel = {body} "
                    'unless(vbLabel error("label not created")) '
                    f"vbLabel~>labelType = {basic.q(command['label_type'])} vbLabel)"
                )
            return f'let((vbLabel) vbLabel = {body} unless(vbLabel error("label not created")) vbLabel)'
        choice, label_type = _label_choice(label_kind)
        return (
            "let((vbLabel) "
            f"vbLabel = schCreateSymbolLabel(vbSymCv {point} "
            f"{basic.q(choice)} {basic.q(text)} {basic.q(justify)} "
            f"{basic.q(orient)} {basic.q(font)} {height:g} {basic.q(label_type)}) "
            'unless(vbLabel error("semantic label not created")) vbLabel)'
        )

    def _place_pin_expr(self, command: dict[str, Any]) -> str:
        name = _require_text(command.get("name"), "command.name")
        x = _number(command.get("x"), "command.x")
        y = _number(command.get("y"), "command.y")
        direction = command.get("direction", "inputOutput")
        if direction not in ("input", "output", "inputOutput", "switch", "jumper"):
            raise ValueError(f"invalid terminal direction: {direction}")
        half = _number(command.get("half_size", 0.0625), "command.half_size")
        label = command.get("label", True)
        _require_bool(label, "command.label")
        label_x = _number(command.get("label_x", x), "command.label_x")
        label_y = _number(command.get("label_y", y), "command.label_y")
        label_justify = command.get("label_justify", "centerLeft")
        label_orient = command.get("label_orient", "R0")
        label_font = command.get("label_font", "stick")
        label_height = _number(command.get("label_height", 0.0625), "command.label_height")
        bbox = (x - half, y - half, x + half, y + half)
        label_expr = ""
        if label:
            label_expr = (
                "vbLabel = schCreateSymbolLabel(vbSymCv "
                f"{_point_expr((label_x, label_y))} \"pin name\" {basic.q(name)} "
                f"{basic.q(label_justify)} {basic.q(label_orient)} "
                f"{basic.q(label_font)} {label_height:g} \"normalLabel\") "
                'unless(vbLabel error("pin label not created")) '
                "when(isCallable('schGlueLabel) schGlueLabel(vbLabel vbRect)) "
            )
        return (
            "let((vbExisting vbNet vbTerm vbRect vbPin vbLabel) "
            f"vbExisting = car(setof(x vbSymCv~>terminals x~>name == {basic.q(name)})) "
            'when(vbExisting error("terminal already exists")) '
            f"vbNet = car(setof(x vbSymCv~>nets x~>name == {basic.q(name)})) "
            f"unless(vbNet vbNet = dbCreateNet(vbSymCv {basic.q(name)})) "
            'unless(vbNet error("net not created")) '
            f"vbTerm = dbCreateTerm(vbNet {basic.q(name)} {basic.q(direction)}) "
            'unless(vbTerm error("term not created")) '
            f"vbRect = dbCreateRect(vbSymCv {_lpp_expr('pin', 'drawing')} {_bbox_expr(bbox)}) "
            'unless(vbRect error("pin rectangle not created")) '
            f"vbPin = dbCreatePin(vbNet vbRect {basic.q(name)} vbTerm) "
            'unless(vbPin error("pin not created")) '
            f"{label_expr}vbPin)"
        )

    def _delete_pin_expr(self, command: dict[str, Any]) -> str:
        name = _require_text(command.get("name"), "command.name")
        return (
            "let((vbTerm vbPin vbFig vbLabel vbNet) "
            f"vbTerm = car(setof(x vbSymCv~>terminals x~>name == {basic.q(name)})) "
            'unless(vbTerm error("terminal not found")) '
            "vbPin = car(vbTerm~>pins) "
            "when(vbPin vbFig = vbPin~>fig) "
            f"vbLabel = car(setof(x vbSymCv~>shapes {_pin_match_expr(name)})) "
            "vbNet = vbTerm~>net "
            "when(vbPin dbDeleteObject(vbPin)) "
            "when(vbFig dbDeleteObject(vbFig)) "
            "when(vbLabel dbDeleteObject(vbLabel)) "
            "dbDeleteObject(vbTerm) "
            "when(vbNet && !vbNet~>terminals dbDeleteObject(vbNet)) "
            "t)"
        )

    def _rename_pin_expr(self, command: dict[str, Any]) -> str:
        name = _require_text(command.get("name"), "command.name")
        new_name = _require_text(command.get("new_name"), "command.new_name")
        return (
            "let((vbTerm vbPin vbNet vbLabel) "
            f"vbTerm = car(setof(x vbSymCv~>terminals x~>name == {basic.q(name)})) "
            'unless(vbTerm error("terminal not found")) '
            "vbPin = car(vbTerm~>pins) "
            "vbNet = vbTerm~>net "
            f"vbLabel = car(setof(x vbSymCv~>shapes {_pin_match_expr(name)})) "
            f"vbTerm~>name = {basic.q(new_name)} "
            f"when(vbPin vbPin~>name = {basic.q(new_name)}) "
            f"when(vbNet && vbNet~>name == {basic.q(name)} "
            "  unless(isCallable('dbRenameNet) error(\"dbRenameNet unavailable\")) "
            f"  unless(dbRenameNet(vbNet {basic.q(new_name)}) error(\"dbRenameNet failed\"))) "
            f"when(vbLabel vbLabel~>theLabel = {basic.q(new_name)}) "
            "t)"
        )

    def _set_pin_properties_expr(self, command: dict[str, Any]) -> str:
        name = _require_text(command.get("name"), "command.name")
        assigns: list[str] = []
        if command.get("direction"):
            if command["direction"] not in ("input", "output", "inputOutput", "switch", "jumper"):
                raise ValueError(f"invalid terminal direction: {command['direction']}")
            assigns.append(f"vbTerm~>direction = {basic.q(command['direction'])}")
        if command.get("access_dir"):
            value = command["access_dir"]
            access_expr = (
                "list(" + " ".join(basic.q(str(item)) for item in value) + ")"
                if isinstance(value, list) else f"list({basic.q(str(value))})"
            )
            assigns.append(
                "when(vbPin "
                "if(isCallable('dbSetPinFigAccessDirection) "
                "unless(dbSetPinFigAccessDirection(vbPin~>fig "
                f"{access_expr}) "
                'error("access direction rejected")) '
                f"vbPin~>accessDir = {access_expr}))"
            )
        label_fields = ("label_justify", "label_orient", "label_font", "label_height")
        if any(key in command for key in label_fields):
            if command.get("label_justify"):
                assigns.append(f"when(vbLabel vbLabel~>justify = {basic.q(command['label_justify'])})")
            if command.get("label_orient"):
                assigns.append(f"when(vbLabel vbLabel~>orient = {basic.q(command['label_orient'])})")
            if command.get("label_font"):
                assigns.append(f"when(vbLabel vbLabel~>font = {basic.q(command['label_font'])})")
            if "label_height" in command:
                h = _number(command["label_height"], "command.label_height")
                assigns.append(f"when(vbLabel vbLabel~>height = {h:g})")
        if "label" in command:
            _require_bool(command["label"], "command.label")
            if command["label"]:
                style_justify = basic.q(command.get("label_justify") or "centerLeft")
                style_orient = basic.q(command.get("label_orient") or "R0")
                style_font = basic.q(command.get("label_font") or "stick")
                style_height = _number(
                    command.get("label_height", 0.0625), "command.label_height"
                )
                assigns.append(
                    "unless(vbLabel "
                    "vbLabel = schCreateSymbolLabel(vbSymCv "
                    "if(vbPin && vbPin~>fig && vbPin~>fig~>bBox "
                    "list((xCoord(car(vbPin~>fig~>bBox)) "
                    "+ xCoord(cadr(vbPin~>fig~>bBox))) / 2.0 "
                    "(yCoord(car(vbPin~>fig~>bBox)) "
                    "+ yCoord(cadr(vbPin~>fig~>bBox))) / 2.0) "
                    "list(0.0 0.0)) "
                    f"\"pin name\" {basic.q(name)} "
                    f"{style_justify} {style_orient} {style_font} {style_height:g} "
                    "\"normalLabel\") "
                    "when(isCallable('schGlueLabel) schGlueLabel(vbLabel vbPin~>fig)))"
                )
            else:
                assigns.append("when(vbLabel dbDeleteObject(vbLabel) vbLabel = nil)")
        if not assigns:
            raise ValueError("set_pin_properties requires at least one field")
        return (
            "let((vbTerm vbPin vbLabel) "
            f"vbTerm = car(setof(x vbSymCv~>terminals x~>name == {basic.q(name)})) "
            'unless(vbTerm error("terminal not found")) '
            "vbPin = car(vbTerm~>pins) "
            f"vbLabel = car(setof(x vbSymCv~>shapes {_pin_match_expr(name)})) "
            + " ".join(assigns)
            + " t)"
        )

    # -- generate ---------------------------------------------------------------

    def generate(self, request: GenerateRequest) -> Result:
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.schematic_view, "schematic_view")
        _require_text(request.symbol_view, "symbol_view")
        _require_timeout(request.timeout)
        if request.schematic_view == request.symbol_view:
            raise ValueError("schematic_view and symbol_view must differ")
        if request.sort_pins not in (None, "alphanumeric", "geometric"):
            raise ValueError("sort_pins must be alphanumeric/geometric/None")
        _require_bool(request.overwrite, "overwrite")
        steps: list[dict[str, Any]] = []
        try:
            skill = generate_skill(
                request.library,
                request.cell,
                schematic_view=request.schematic_view,
                symbol_view=request.symbol_view,
                sort_pins=request.sort_pins,
                overwrite=request.overwrite,
            )
            run = self._skill(skill, request.token, request.timeout)
            steps.append(_step("generate", run.ok, run))
            if not run.ok:
                return Result(False, steps, "; ".join(run.errors) or "symbol generation failed")
            action, terms, pin_order = parse_generation_output(run.output or "")
            if sorted(terms) != sorted(pin_order):
                return Result(False, steps, "generated symbol pin order mismatch")
            return Result(True, steps, None, {
                "library": request.library,
                "cell": request.cell,
                "schematic_view": request.schematic_view,
                "symbol_view": request.symbol_view,
                "action": action,
                "terminal_names": list(terms),
                "pin_order": list(pin_order),
            })
        except Exception as exc:  # noqa: BLE001
            return Result(False, steps, f"{type(exc).__name__}: {exc}")

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
        region = None
        if request.region is not None:
            region = _bbox(request.region, "region")
        steps: list[dict[str, Any]] = []
        remote_png: str | None = None
        try:
            gui_root = self._role_root(request.token, "daemon")
            remote_png = posixpath.join(
                gui_root, "screenshots",
                f"{_safe_name(request.cell)}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}.png",
            )
            quoted = shlex.quote(remote_png)
            mkdir = self.middle.run_command(
                f"mkdir -p $(dirname {quoted})",
                timeout=request.timeout,
                token=request.token,
            )
            steps.append(_step("mkdir", mkdir.returncode == 0, mkdir))
            if mkdir.returncode != 0:
                return Result(False, steps, mkdir.stderr or "mkdir failed")
            run = self._skill(
                _screenshot_skill(request, region, remote_png),
                request.token,
                request.timeout,
            )
            steps.append(_step("capture", run.ok, run))
            if not run.ok:
                return Result(False, steps, "; ".join(run.errors) or "screenshot failed")
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
                        f"rm -f {shlex.quote(remote_png)}",
                        timeout=10, token=request.token,
                    )
                except Exception:
                    pass

    def _role_root(self, token: str, role: str) -> str:
        facts = self.middle.query(token=token)
        if facts.status.value != "success":
            raise RuntimeError("; ".join(facts.errors) or "query failed")
        entry = facts.roles.get(role)
        if entry is None or not entry.root:
            raise RuntimeError(f"{role} role root is not available")
        return entry.root.rstrip("/")


# ---------------------------------------------------------------------------
# SKILL templates
# ---------------------------------------------------------------------------

def _read_skill(request: ReadRequest) -> str:
    lib = basic.q(request.library)
    cell = basic.q(request.cell)
    view = basic.q(request.view)
    view_type = basic.q(request.view_type)
    return f'''
let((vbCv vbResult vbCollected vbShape vbTerm vbPin vbFig vbBBox vbPoints vbXY vbAccess)
  vbCv = dbOpenCellViewByType({lib} {cell} {view} {view_type} "r")
  unless(vbCv error("symbol view not found"))
  vbCollected = errset(progn(vbResult = nil
  foreach(vbTerm vbCv~>terminals
    vbPin = car(vbTerm~>pins)
    vbFig = when(vbPin vbPin~>fig)
    unless(vbFig when(vbPin vbFig = car(vbPin~>figs)))
    vbAccess = when(vbFig
      if(isCallable('dbGetPinFigAccessDirection)
        dbGetPinFigAccessDirection(vbFig)
        when(vbPin vbPin~>accessDir)))
    vbBBox = when(vbFig && vbFig~>bBox
      list(list(xCoord(car(vbFig~>bBox)) yCoord(car(vbFig~>bBox)))
           list(xCoord(cadr(vbFig~>bBox)) yCoord(cadr(vbFig~>bBox)))))
    vbResult = cons(list("term" vbTerm~>name
                         if(vbTerm~>direction vbTerm~>direction "")
                         if(vbTerm~>numBits vbTerm~>numBits 1) vbBBox
                         vbAccess) vbResult))
  foreach(vbShape vbCv~>shapes
    cond(
      (vbShape~>objType == "label"
        vbXY = when(vbShape~>xy list(xCoord(vbShape~>xy) yCoord(vbShape~>xy)))
        vbBBox = when(vbShape~>bBox
          list(list(xCoord(car(vbShape~>bBox)) yCoord(car(vbShape~>bBox)))
               list(xCoord(cadr(vbShape~>bBox)) yCoord(cadr(vbShape~>bBox)))))
        vbResult = cons(list("label" if(vbShape~>theLabel vbShape~>theLabel "")
                             if(vbShape~>labelType vbShape~>labelType "") vbXY
                             if(vbShape~>layerName vbShape~>layerName "")
                             if(vbShape~>purpose vbShape~>purpose "")
                             if(vbShape~>justify vbShape~>justify "")
                             if(vbShape~>orient vbShape~>orient "")
                             if(vbShape~>font vbShape~>font "")
                             if(vbShape~>height vbShape~>height 0) vbBBox) vbResult))
      (vbShape~>objType == "rect" && vbShape~>layerName == "instance"
        && vbShape~>purpose == "drawing"
        vbBBox = when(vbShape~>bBox
          list(list(xCoord(car(vbShape~>bBox)) yCoord(car(vbShape~>bBox)))
               list(xCoord(cadr(vbShape~>bBox)) yCoord(cadr(vbShape~>bBox)))))
        vbResult = cons(list("selectionBox" vbBBox) vbResult))
      (vbShape~>objType == "line" || vbShape~>objType == "polygon"
        || vbShape~>objType == "rect" || vbShape~>objType == "ellipse"
        vbBBox = when(vbShape~>bBox
          list(list(xCoord(car(vbShape~>bBox)) yCoord(car(vbShape~>bBox)))
               list(xCoord(cadr(vbShape~>bBox)) yCoord(cadr(vbShape~>bBox)))))
        vbPoints = when(vbShape~>points
          mapcar(lambda((p) list(xCoord(p) yCoord(p))) vbShape~>points))
        vbResult = cons(list("shape" vbShape~>objType
                             if(vbShape~>layerName vbShape~>layerName "")
                             if(vbShape~>purpose vbShape~>purpose "")
                             vbBBox vbPoints) vbResult))
      (t
        vbBBox = when(vbShape~>bBox
          list(list(xCoord(car(vbShape~>bBox)) yCoord(car(vbShape~>bBox)))
               list(xCoord(cadr(vbShape~>bBox)) yCoord(cadr(vbShape~>bBox)))))
        vbPoints = when(vbShape~>points
          mapcar(lambda((p) list(xCoord(p) yCoord(p))) vbShape~>points))
        vbResult = cons(list("shape" if(vbShape~>objType vbShape~>objType "unknown")
                             if(vbShape~>layerName vbShape~>layerName "")
                             if(vbShape~>purpose vbShape~>purpose "")
                             vbBBox vbPoints) vbResult))))
  vbResult = cons(list("pinOrder" schGetPinOrder(vbCv)) vbResult)
  vbResult = cons(list("portOrder" vbCv~>portOrder) vbResult)
  vbResult = cons(list("termOrder" vbCv~>termOrder) vbResult)
  vbResult))
  dbClose(vbCv)
  unless(vbCollected error("symbol read failed"))
  reverse(car(vbCollected)))
'''.strip()


def _screenshot_skill(request: ScreenshotRequest, region: tuple[float, float, float, float] | None, remote_path: str) -> str:
    if request.window_id is not None:
        target = (
            "let((vbW) foreach(w hiGetWindowList() "
            f"when(w~>windowNum == {int(request.window_id)} vbW = w)) vbW)"
        )
    else:
        target = (
            "let((vbTmp) vbTmp = car(setof(x hiGetWindowList() "
            "x~>cellView && "
            f"x~>cellView~>libName == {basic.q(request.library)} && "
            f"x~>cellView~>cellName == {basic.q(request.cell)} && "
            f"x~>cellView~>viewName == {basic.q(request.view)})) "
            "unless(vbTmp progn(vbTmp = geOpen(?lib "
            f"{basic.q(request.library)} ?cell {basic.q(request.cell)} "
            f"?view {basic.q(request.view)} ?viewType {basic.q(request.view_type)} "
            '?mode "r") vbOpened = t)) vbTmp)'
        )
    zoom = ""
    if region is not None:
        x0, y0, x1, y1 = region
        zoom = f"hiZoomIn(vbW list({x0:g}:{y0:g} {x1:g}:{y1:g})) "
    return (
        "let((vbW vbRc vbOpened) "
        "vbOpened = nil "
        f"vbW = {target} "
        'unless(vbW error("symbol window not found")) '
        f"{zoom}"
        f"vbRc = hiWindowSaveImage(?target vbW ?path {basic.q(remote_path)} "
        f"?format \"png\" ?toplevel {'t' if request.toplevel else 'nil'} "
        f"?centralWidget {'t' if request.central_widget else 'nil'}) "
        f"unless({'t' if request.leave_open else 'nil'} when(vbOpened hiCloseWindow(vbW))) "
        'if(vbRc "saved" "capture-failed"))'
    )


def _parse_read(raw: str) -> dict[str, Any]:
    parsed = basic.parse_sexpr(raw.strip())
    result: dict[str, Any] = {
        "terms": [], "labels": [], "shapes": [],
        "selection_boxes": [], "pin_order": [], "port_order": [], "term_order": [],
    }
    if not isinstance(parsed, list):
        return result
    for record in parsed:
        if not isinstance(record, list) or not record:
            continue
        kind = str(record[0])
        if kind == "term" and len(record) >= 5:
            access = record[5] if len(record) >= 6 else None
            result["terms"].append({
                "name": _s(record[1]), "direction": _s(record[2]),
                "num_bits": _i(record[3], 1), "bbox": _bbox_value(record[4]),
                "access_dir": ([_s(item) for item in access]
                               if isinstance(access, list) else []),
            })
        elif kind == "label" and len(record) >= 11:
            result["labels"].append({
                "text": _s(record[1]), "label_type": _s(record[2]),
                "xy": _point_value(record[3]), "layer": _s(record[4]), "purpose": _s(record[5]),
                "justify": _s(record[6]), "orient": _s(record[7]),
                "font": _s(record[8]), "height": _f(record[9]), "bbox": _bbox_value(record[10]),
            })
        elif kind == "shape" and len(record) >= 6:
            result["shapes"].append({
                "kind": _s(record[1]), "layer": _s(record[2]),
                "purpose": _s(record[3]), "bbox": _bbox_value(record[4]),
                "points": _points_value(record[5]),
            })
        elif kind == "selectionBox" and len(record) >= 2:
            result["selection_boxes"].append(_bbox_value(record[1]))
        elif kind in ("pinOrder", "portOrder", "termOrder") and len(record) >= 2:
            order = record[1] if isinstance(record[1], list) else []
            key = {"pinOrder": "pin_order", "portOrder": "port_order", "termOrder": "term_order"}[kind]
            result[key] = [_s(item) for item in order]
    return result


def _s(value: Any) -> str:
    return "" if value is None else str(value)


def _i(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _point_value(value: Any) -> list[float] | None:
    if isinstance(value, list) and len(value) >= 2:
        return [_f(value[0]), _f(value[1])]
    return None


def _bbox_value(value: Any) -> list[list[float]] | None:
    if isinstance(value, list) and len(value) >= 2:
        first = _point_value(value[0])
        second = _point_value(value[1])
        if first is not None and second is not None:
            return [first, second]
    return None


def _points_value(value: Any) -> list[list[float]] | None:
    if not isinstance(value, list):
        return None
    points = [_point_value(item) for item in value]
    return [point for point in points if point is not None]


#: spec 上层 §4.2: package-level self-description
OPERATIONS = (
    ("virtuoso.symbol.read", "read", ReadRequest, Result),
    ("virtuoso.symbol.write", "write", WriteRequest, Result),
    ("virtuoso.symbol.check_and_save", "check_and_save", CheckSaveRequest, Result),
    ("virtuoso.symbol.generate", "generate", GenerateRequest, Result),
    ("virtuoso.symbol.screenshot", "screenshot", ScreenshotRequest, Result),
)

OPERATION_NAMES = tuple(operation for operation, *_ in OPERATIONS)

__all__ = [
    "CheckSaveRequest", "GenerateRequest", "OPERATIONS", "OPERATION_NAMES",
    "Package", "ReadRequest", "Result", "ScreenshotRequest", "WriteRequest",
]
