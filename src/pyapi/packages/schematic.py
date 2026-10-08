"""``schematic`` business package: one read + one batched write over atomic commands.

spec: spec/design-concepts/上层/2-schematic.md
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
import shlex
from typing import Any

import posixpath
from common.paths import artifact_dir
from pyapi.models import Middle, skill_log_kwargs, ResultBase, ResultPackage
from pyapi.packages import basic
from pyapi.packages import _screenshot
from pyapi.packages._common import _require_text, _require_timeout, _step


@dataclass
class Result(ResultBase):
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    value: Any = None


@dataclass(frozen=True)
class ReadRequest:
    token: str
    library: str
    cell: str
    view: str = "schematic"
    focus: str | None = None          # e.g. "positions,params"; None = all
    param_filter: list[str] | None = None
    object_filter: dict[str, Any] | None = None
    timeout: int | None = None
    log_level: str | None = None
    log_max_bytes: int | None = None
    step_details: bool = False


@dataclass(frozen=True)
class WriteRequest:
    token: str
    library: str
    cell: str
    commands: list[dict[str, Any]]
    view: str = "schematic"
    timeout: int | None = None
    log_level: str | None = None
    log_max_bytes: int | None = None
    step_details: bool = False


@dataclass(frozen=True)
class CheckSaveRequest:
    token: str
    library: str
    cell: str
    view: str = "schematic"
    timeout: int | None = None
    log_level: str | None = None
    log_max_bytes: int | None = None
    step_details: bool = False


def _q(value: Any) -> str:
    return basic.q(str(value))


_PIN_SIG_TYPES = {
    "analog", "clock", "ground", "power", "reset", "scan",
    "signal", "tieHi", "tieLo", "tieOff",
}


def _unquote(value: str) -> str:
    return (value or "").replace('\\"', '"').strip('"')


def _region_of(value: Any, name: str = "region") -> tuple[float, float, float, float]:
    """区域统一为**对角两点** `[pos0, pos1]`（P-074 定版；P-082 统一到读过滤/截图）。"""
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError(
            f"{name} must be [ [x0, y0], [x1, y1] ]（对角两点 pos0/pos1；四元组已弃用）"
        )
    try:
        x1, y1 = float(value[0][0]), float(value[0][1])
        x2, y2 = float(value[1][0]), float(value[1][1])
    except (TypeError, ValueError, IndexError) as exc:
        raise ValueError(
            f"{name} must be [ [x0, y0], [x1, y1] ]（对角两点 pos0/pos1）"
        ) from exc
    if not x1 < x2 or not y1 < y2:
        raise ValueError(f"{name} requires pos0 < pos1（对角两点，先小后大）")
    return x1, y1, x2, y2


def _region_in_expr(region: Any) -> str:
    x1, y1, x2, y2 = _region_of(region)
    return (
        f'let((bb ll ur) bb = x~>bBox ll = car(bb) ur = cadr(bb) '
        f'!(xCoord(ur) < {x1:g} || xCoord(ll) > {x2:g} '
        f'|| yCoord(ur) < {y1:g} || yCoord(ll) > {y2:g}))'
    )


def _instance_filter_expr(flt: Any) -> str:
    """Return a SKILL predicate fragment for one instance, or ``"nil"`` when excluded."""
    if flt is None or flt == "all":
        return "t"
    if flt == "none":
        return "nil"
    if not isinstance(flt, dict):
        raise ValueError("instance filter must be all/none/names/region")
    parts: list[str] = ["t"]
    if "names" in flt:
        names = " ".join(_q(n) for n in flt["names"])
        parts.append(f'member(__inst~>name list({names}))')
    if "region" in flt:
        x1, y1, x2, y2 = _region_of(flt["region"], "instance.region")
        parts.append(
            f'xCoord(__inst~>xy) >= {x1:g} && xCoord(__inst~>xy) <= {x2:g} '
            f'&& yCoord(__inst~>xy) >= {y1:g} && yCoord(__inst~>xy) <= {y2:g}'
        )
    return " && ".join(parts)


def _region_shape_expr(region: Any) -> str:
    x1, y1, x2, y2 = _region_of(region, "shape.region")
    return (
        f'x~>bBox && !(xCoord(cadr(x~>bBox)) < {x1:g} '
        f'|| xCoord(car(x~>bBox)) > {x2:g} '
        f'|| yCoord(cadr(x~>bBox)) < {y1:g} '
        f'|| yCoord(car(x~>bBox)) > {y2:g})'
    )


def _shape_filter_expr(flt: Any) -> str:
    if flt is None or flt == "all":
        return "t"
    if flt == "none":
        return "nil"
    if isinstance(flt, dict) and "region" in flt:
        return _region_shape_expr(flt["region"])
    raise ValueError("object filter must be all/none/{region:...}")


def _term_geometry_expr(inst_var: str, term_name: str) -> str:
    """Return ``list(center halfWidth)`` of the transformed pin figure bbox."""
    return (
        f'let((rbInst rbTerm rbPin rbFig rbBBox rbCtr rbHw) '
        f'rbInst = {inst_var} '
        f'rbTerm = car(setof(x rbInst~>master~>terminals x~>name == {_q(term_name)})) '
        'unless(rbTerm error("terminal not found")) '
        'rbPin = car(rbTerm~>pins) '
        'rbFig = when(rbPin car(rbPin~>figs)) '
        'rbBBox = when(rbFig dbTransformBBox(rbFig~>bBox rbInst~>transform)) '
        'rbCtr = when(rbBBox list((xCoord(car(rbBBox)) + xCoord(cadr(rbBBox))) / 2.0 '
        '(yCoord(car(rbBBox)) + yCoord(cadr(rbBBox))) / 2.0)) '
        'rbHw = when(rbBBox (xCoord(cadr(rbBBox)) - xCoord(car(rbBBox))) / 2.0) '
        'when(rbCtr && rbHw list(rbCtr rbHw)))'
    )


def _parse_schematic(raw: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "instances": [], "nets": {}, "pins": [], "labels": [],
        "wires": [], "notes": [],
    }
    section = None
    current_inst: dict[str, Any] | None = None
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        if line in ("INSTANCES", "NETS", "PINS", "LABELS", "WIRES", "NOTES", "END"):
            if current_inst is not None:
                result["instances"].append(current_inst)
                current_inst = None
            section = line.lower()
            continue
        if section == "instances":
            if line.startswith("INST|"):
                if current_inst is not None:
                    result["instances"].append(current_inst)
                parts = line.split("|")
                current_inst = {
                    "name": parts[1], "lib": parts[2], "cell": parts[3],
                    "terms": {}, "params": {}, "terminals": {},
                }
                if len(parts) >= 8:
                    xy = parts[4].strip().strip("()").split()
                    current_inst["pos"] = [float(x) for x in xy] if len(xy) == 2 else [0.0, 0.0]
                    current_inst["orient"] = parts[5]
                    current_inst["bBox"] = parts[6]
                    current_inst["numInst"] = parts[7]
                    current_inst["master_view"] = parts[8] if len(parts) > 8 else "symbol"
            elif line.startswith("TERM|") and current_inst is not None:
                parts = line.split("|")
                if len(parts) >= 3:
                    current_inst["terms"][parts[1]] = parts[2]
            elif line.startswith("TERMXY|") and current_inst is not None:
                parts = line.split("|")
                if len(parts) >= 4:
                    current_inst["terminals"][parts[1]] = [float(parts[2]), float(parts[3])]
            elif line.startswith("PARAM|") and current_inst is not None:
                parts = line.split("|", 2)
                if len(parts) >= 3:
                    current_inst["params"][parts[1]] = (
                        parts[2].replace('\\"', '"').strip('"'))
            elif line.startswith("NLACTION|") and current_inst is not None:
                current_inst["nlAction"] = line.split("|", 1)[1]
        elif section == "nets":
            if line.startswith("NET|"):
                parts = line.split("|")
                if len(parts) >= 5:
                    result["nets"][parts[1]] = {
                        "numBits": parts[2], "sigType": parts[3],
                        "isGlobal": parts[4] == "t", "connections": parts[5:],
                    }
        elif section == "pins":
            if line.startswith("PIN|"):
                parts = line.split("|")
                if len(parts) >= 2:
                    item = {"name": parts[1]}
                    if len(parts) >= 3:
                        item["direction"] = parts[2]
                    # positions 模式：`PIN|<instName>|<dir>|1|(x y)`（P-074：pos 一个字段）
                    if len(parts) >= 5:
                        xy = parts[4].strip().strip("()").split()
                        if len(xy) == 2:
                            item["pos"] = [float(xy[0]), float(xy[1])]
                    result["pins"].append(item)
        elif section == "labels":
            if line.startswith("LABEL|"):
                parts = line.split("|")
                if len(parts) >= 3:
                    xy = parts[2].strip().strip("()").split()
                    label = {
                        "text": parts[1],
                        "pos": [float(x) for x in xy] if len(xy) == 2 else [0.0, 0.0],
                    }
                    if len(parts) >= 7:
                        label["orient"] = _unquote(parts[3])
                        label["justify"] = _unquote(parts[4])
                        label["font"] = _unquote(parts[5])
                        try:
                            label["height"] = float(parts[6])
                        except ValueError:
                            label["height"] = None
                    result["labels"].append(label)
        elif section == "wires":
            if line.startswith("WIRE|"):
                parts = line.split("|")
                pairs = re.findall(r"\(([-\d.eE+]+)\s+([-\d.eE+]+)\)", parts[1])
                wire = {"points": [[float(a), float(b)] for a, b in pairs]}
                if len(parts) >= 3:
                    try:
                        wire["width"] = float(parts[2]) if parts[2].strip() not in ("nil", "()") else 0.0
                    except ValueError:
                        wire["width"] = None
                if len(parts) >= 4:
                    wire["color"] = _unquote(parts[3])
                if len(parts) >= 5:
                    wire["line_style"] = _unquote(parts[4])
                result["wires"].append(wire)
        elif section == "notes":
            if line.startswith("NOTE|"):
                parts = line.split("|")
                if len(parts) >= 2:
                    note = {"text": parts[1]}
                    if len(parts) >= 3:
                        xy = parts[2].strip().strip("()").split()
                        note["pos"] = [float(x) for x in xy] if len(xy) == 2 else [0.0, 0.0]
                    if len(parts) >= 7:
                        note["orient"] = _unquote(parts[3])
                        note["justify"] = _unquote(parts[4])
                        note["font"] = _unquote(parts[5])
                        try:
                            note["height"] = float(parts[6])
                        except ValueError:
                            note["height"] = None
                    result["notes"].append(note)
    if current_inst is not None:
        result["instances"].append(current_inst)
    return result

# ---- read --------------------------------------------------------------------

def _read_skill(request: ReadRequest) -> str:
    focus = {item.strip() for item in (request.focus or "").split(",") if item.strip()}
    all_mode = not focus
    want_conn = all_mode or "connectivity" in focus
    want_pos = all_mode or "positions" in focus
    want_params = all_mode or "params" in focus
    filters = request.object_filter or {}
    inst_flt = _instance_filter_expr(filters.get("instance"))
    wire_flt = _shape_filter_expr(filters.get("wire"))
    label_flt = _shape_filter_expr(filters.get("label"))
    pin_flt = _shape_filter_expr(filters.get("pin"))
    note_flt = _shape_filter_expr(filters.get("note"))
    if want_conn:
        # spec: filters are ignored whenever connectivity is requested
        inst_flt = wire_flt = label_flt = pin_flt = note_flt = "t"

    parts: list[str] = []
    parts.append('let((cv vbOut vbInsts vbCdf vbParam)')
    parts.append(
        f'cv = dbOpenCellViewByType({_q(request.library)} {_q(request.cell)} '
        f'{_q(request.view)} "schematic" "r")'
    )
    parts.append('if(!cv "ERROR" unwindProtect(progn(')
    parts.append('vbOut = ""')

    # INSTANCES (always emitted; filters may reduce it to zero)
    inst_filter_clause = f'setof(__inst cv~>instances __inst~>purpose != "pin" && {inst_flt})'
    parts.append('vbOut = strcat(vbOut "INSTANCES\\n")')
    parts.append(f'vbInsts = {inst_filter_clause}')
    parts.append('foreach(inst vbInsts')
    parts.append(
        'vbOut = strcat(vbOut sprintf(nil "INST|%s|%s|%s" inst~>name inst~>libName inst~>cellName))'
    )
    if want_pos:
        parts.append(
            'vbOut = strcat(vbOut sprintf(nil "|%L|%s|%L|%d|%s" '
            'inst~>xy if(inst~>orient inst~>orient "R0") inst~>bBox '
            'if(inst~>numInst inst~>numInst 1) if(inst~>viewName inst~>viewName "symbol")))'
        )
    parts.append('vbOut = strcat(vbOut "\\n")')
    if want_conn:
        parts.append(
            'foreach(it inst~>instTerms when(it~>net '
            'vbOut = strcat(vbOut sprintf(nil "TERM|%s|%s\\n" it~>name it~>net~>name))))'
        )
    if want_pos:
        parts.append(
            'foreach(it inst~>instTerms let((rbTerm pin fig bb ctr) '
            'rbTerm = car(setof(x inst~>master~>terminals x~>name == it~>name)) '
            'pin = when(rbTerm car(rbTerm~>pins)) fig = when(pin car(pin~>figs)) '
            'bb = when(fig dbTransformBBox(fig~>bBox inst~>transform)) '
            'ctr = when(bb list((xCoord(car(bb)) + xCoord(cadr(bb))) / 2.0 '
            '(yCoord(car(bb)) + yCoord(cadr(bb))) / 2.0)) '
            'when(ctr vbOut = strcat(vbOut sprintf(nil "TERMXY|%s|%g|%g\\n" '
            'it~>name car(ctr) cadr(ctr))))))'
        )
    if want_params:
        whitelist = request.param_filter
        name_pred = (
            't' if not whitelist
            else f'member(p~>name list({" ".join(_q(n) for n in whitelist)}))'
        )
        parts.append(
            'when(ddGetObj(inst~>libName inst~>cellName) let((cdf) '
            'cdf = cdfGetInstCDF(inst) when(cdf foreach(p cdf~>parameters '
            f'when(p~>value != nil && p~>value != "" && {name_pred} '
            '&& strlen(sprintf(nil "%L" p~>value)) <= 120 '
            'vbOut = strcat(vbOut sprintf(nil "PARAM|%s|%L\\n" p~>name p~>value)))))))'
        )
    parts.append('vbOut = strcat(vbOut "\\n")')
    parts.append(')')

    # NETS / PINS
    if want_conn:
        parts.append('vbOut = strcat(vbOut "NETS\\n")')
        parts.append(
            'foreach(net cv~>nets vbOut = strcat(vbOut sprintf(nil "NET|%s|%d|%s|%s" '
            'net~>name if(net~>numBits net~>numBits 1) '
            'if(net~>sigType net~>sigType "signal") if(net~>isGlobal "t" "nil")))'
        )
        parts.append(
            'foreach(it net~>instTerms vbOut = strcat(vbOut '
            'sprintf(nil "|%s.%s" it~>inst~>name it~>name)))'
        )
        parts.append('vbOut = strcat(vbOut "\\n"))')
    if want_conn or want_pos:
        parts.append('vbOut = strcat(vbOut "PINS\\n")')
        if want_pos and not want_conn:
            parts.append(
                f'foreach(__obj setof(x cv~>instances x~>purpose == "pin" && {pin_flt}) '
                'vbOut = strcat(vbOut sprintf(nil "PIN|%s|%s|1|%L\\n" '
                '__obj~>name if(__obj~>master~>cellName == "ipin" "input" '
                'if(__obj~>master~>cellName == "opin" "output" "inputOutput")) __obj~>xy)))'
            )
        else:
            parts.append('foreach(term cv~>terminals')
            parts.append(
                'vbOut = strcat(vbOut sprintf(nil "PIN|%s|%s|%d\\n" term~>name '
                'if(term~>direction term~>direction "inputOutput") '
                'if(term~>numBits term~>numBits 1)))'
            )
            parts.append(')')

    # LABELS / WIRES
    if want_pos:
        parts.append('vbOut = strcat(vbOut "LABELS\\n")')
        parts.append(
            f'foreach(__obj setof(x cv~>shapes x~>objType == "label" '
            f'&& x~>purpose == "label" && {label_flt}) '
            'vbOut = strcat(vbOut sprintf(nil "LABEL|%s|%L|%L|%L|%L|%L\\n" '
            '__obj~>theLabel __obj~>xy __obj~>orient __obj~>justify __obj~>font __obj~>height)))'
        )
        parts.append('vbOut = strcat(vbOut "WIRES\\n")')
        # 带 width/color/lineStyle 的 wire 在 DB 里是 **path** 对象（width=0 才是 line），
        # 两态都算 wire，否则 styled wire 在 read 里完全不可见（P-078）。
        parts.append(
            'foreach(__obj setof(x cv~>shapes '
            f'(x~>objType == "line" || x~>objType == "path") && {wire_flt}) '
            'vbOut = strcat(vbOut sprintf(nil "WIRE|%L|%L|%L|%L\\n" __obj~>points '
            '__obj~>width __obj~>color __obj~>lineStyle)))'
        )

    # NOTES only in all-mode
    if all_mode:
        parts.append('vbOut = strcat(vbOut "NOTES\\n")')
        parts.append(
            f'foreach(__obj setof(x cv~>shapes x~>objType == "label" '
            f'&& x~>purpose == "drawing" && {note_flt}) '
            'vbOut = strcat(vbOut sprintf(nil "NOTE|%s|%L|%L|%L|%L|%L\\n" '
            '__obj~>theLabel __obj~>xy __obj~>orient __obj~>justify __obj~>font __obj~>height)))'
        )
    parts.append('vbOut = strcat(vbOut "END\\n")')
    parts.append('vbOut)')
    parts.append('progn(when(cv dbClose(cv)))))')
    return "\n".join(parts)

# ---- write atoms -------------------------------------------------------------

def _open_edit_skill(library: str, cell: str, view: str) -> str:
    """Probe the view and open it for edit in one call; keep the handle in the
    SKILL global ``vbSchemCv`` so later atoms and the save step can reuse it.

    Returns ``"open-ok"`` / ``"missing"`` / ``"type-mismatch"`` / ``"locked"``.

    不变量：``vbSchemCv`` 是会话级全局、跨多次 ``execute_skill`` 存活，
    依赖"一个 token 独占一个 CIW"（同一 CIW 的 SKILL 串行且不共享）；
    若将来多 token 共用一个 CIW，须改按 token 命名全局，或把整批命令与
    保存收进单条 SKILL。
    """
    return (
        f'let((vbObj vbCv vbEdit) vbObj = ddGetObj({_q(library)} {_q(cell)} {_q(view)}) '
        f'if(vbObj then progn('
        f'vbCv = dbOpenCellViewByType({_q(library)} {_q(cell)} {_q(view)} "schematic" "r") '
        f'if(!vbCv then "type-mismatch" else progn('
        f'when(vbCv dbClose(vbCv)) '
        f'vbEdit = dbOpenCellViewByType({_q(library)} {_q(cell)} {_q(view)} "schematic" "a") '
        f'if(vbEdit then vbSchemCv = vbEdit "open-ok" else "locked")))) '
        'else "missing"))'
    )


def _close_edit_skill() -> str:
    """Release the global edit handle; safe no-op when it is unset."""
    return (
        'when(boundp(\'vbSchemCv) && vbSchemCv dbClose(vbSchemCv)) '
        'vbSchemCv = nil t'
    )


def _save_skill() -> str:
    """schCheck → **dbSetConnCurrent** → dbSave，然后释放全局 edit 句柄。

    `dbSetConnCurrent` 是官方口径（Virtuoso 文档 "Counter Functions" / 后置检查触发器示例：
    "Zero errors, connectivity remains up to date → dbSetConnCurrent(cv)"）：
    抽取完成后必须把 `connectivityLastUpdated` 置为当前 cellview counter，
    否则 `si -batch` 会报 `OSSHNL-108`（属性非整数）或 `OSSHNL-109`（自上次抽取后被改过）。
    """
    return (
        'let((vbRc) vbRc = schCheck(vbSchemCv) '
        'when(vbRc dbSetConnCurrent(vbSchemCv) dbSave(vbSchemCv)) '
        'when(vbSchemCv dbClose(vbSchemCv)) vbSchemCv = nil '
        'if(vbRc "saved" "check-failed"))'
    )


def _open_failure(state: str, library: str, cell: str, view: str) -> str:
    return {
        "missing": f"schematic view {library}/{cell}/{view} not found",
        "type-mismatch": f"{library}/{cell}/{view} exists but is not view type schematic",
        "locked": f"schematic view {library}/{cell}/{view} is locked by another session",
    }.get(state, f"could not open schematic view {library}/{cell}/{view} for edit ({state})")


def _point_str(points: list[Any]) -> str:
    pairs = " ".join(f"{float(x):g}:{float(y):g}" for x, y in points)
    return f"list({pairs})"


def _points_of(cmd: dict[str, Any], key: str) -> list[tuple[float, float]]:
    """多点参数（wire 用）：`points: [[x, y], …]`；形状不对时点名 `points`。"""
    raw = cmd.get(key)
    if not isinstance(raw, (list, tuple)) or len(raw) < 1:
        raise ValueError(f"command requires '{key}': [[x, y], ...]")
    points: list[tuple[float, float]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, (list, tuple)) or len(item) != 2:
            raise ValueError(f"command '{key}' item {index} must be [x, y]")
        points.append((float(item[0]), float(item[1])))
    return points


def _pos_of(cmd: dict[str, Any]) -> tuple[float, float]:
    """单点参数：`pos: [x, y]`（P-074）。`xy`/拆开的 `x`/`y` 一律非法，并点名违规字段。"""
    for legacy in ("xy", "x", "y"):
        if legacy in cmd:
            raise ValueError(
                f"command field '{legacy}' is not allowed：坐标统一用 'pos': [x, y]"
                "（见 spec 上层/2-schematic.md §1.3）"
            )
    raw = cmd.get("pos")
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise ValueError("command requires 'pos': [x, y]")
    return float(raw[0]), float(raw[1])


def _atomic_skill(op: str, cmd: dict[str, Any]) -> str:
    if op == "place_instance":
        x, y = _pos_of(cmd)
        master = f'dbOpenCellViewByType({_q(cmd["master_lib"])} {_q(cmd["master_cell"])} {_q(cmd.get("master_view", "symbol"))} "schematicSymbol" "r")'
        return (
            f'let((vbMaster vbInst) vbMaster = {master} '
            f'vbInst = dbCreateInst(vbSchemCv vbMaster {_q(cmd["name"])} '
            f'{x:g}:{y:g} {_q(cmd.get("orient", "R0"))}) '
            'when(vbMaster dbClose(vbMaster)) vbInst)'
        )
    if op == "delete_instance":
        return (
            f'let((vbInsts vbN) vbInsts = setof(x vbSchemCv~>instances '
            f'x~>name == {_q(cmd["name"])}) vbN = 0 '
            'foreach(x vbInsts when(dbDeleteObject(x) vbN = vbN + 1)) vbN)'
        )
    if op == "rename_instance":
        return (
            f'let((vbInst) vbInst = car(setof(x vbSchemCv~>instances '
            f'x~>name == {_q(cmd["name"])})) '
            f'unless(vbInst error("instance not found")) '
            f'vbInst~>name = {_q(cmd["new_name"])} vbInst~>name)'
        )
    if op == "set_instance_params":
        params = cmd["params"]
        names = " ".join(_q(n) for n in params)
        sets = " ".join(
            f'setarray(vbParamVals {_q(n)} {_q(v)})' for n, v in params.items()
        )
        return f'''
let((vbInst vbCcd vbParamVals vbP vbProp)
  vbInst = car(setof(x vbSchemCv~>instances x~>name == {_q(cmd["name"])}))
  unless(vbInst error("instance not found"))
  vbParamVals = makeTable('vbParamVals)
  {sets}
  vbCcd = cdfGetCellCDF(ddGetObj(vbInst~>libName vbInst~>cellName))
  foreach(vbN list({names})
    vbP = get(vbCcd vbN)
    unless(vbP error(sprintf(nil "unknown CDF param: %s" vbN)))
    vbProp = dbReplaceProp(vbInst vbN "string" arrayref(vbParamVals vbN))
    unless(vbProp error(sprintf(nil "failed to set instance param: %s" vbN))))
  "ok")
'''.strip()
    if op == "set_term_nets":
        just = cmd.get("justify", "lowerCenter")
        orient = cmd.get("orient", "R0")
        font = cmd.get("font", "stick")
        height = float(cmd.get("height", 0.0625))
        explicit_stub = "stub_length" in cmd
        stub = float(cmd["stub_length"]) if explicit_stub else 0.0
        exprs = []
        for term, net in cmd["term_nets"].items():
            geo = _term_geometry_expr(
                f'car(setof(x vbSchemCv~>instances x~>name == {_q(cmd["name"])}))',
                term,
            )
            # 默认 stub 由引脚几何推出（半宽 + 0.05），避免固定 0.5 跨过相邻引脚；
            # 显式传 stub_length 时按调用方给定值。
            # 注意括号：SKILL 里 `(0.5)` 会被当成**函数调用**（报 `eval: not a function 0.5`），
            # 所以默认表达式自带括号，模板里直接用 `+ {stub_expr}`（P-074 顺带修）。
            stub_expr = f"{stub:g}" if explicit_stub else "(rbHw + 0.05)"
            exprs.append(
                f'let((rbGeo rbCtr rbHw rbEnd rbMid) rbGeo = {geo} '
                f'when(rbGeo rbCtr = car(rbGeo) rbHw = cadr(rbGeo) '
                f'rbEnd = list(xCoord(rbCtr) + {stub_expr} yCoord(rbCtr)) '
                f'rbMid = list((xCoord(rbCtr) + xCoord(rbEnd)) / 2.0 '
                f'(yCoord(rbCtr) + yCoord(rbEnd)) / 2.0) '
                f'schCreateWire(vbSchemCv "draw" "full" list(rbCtr rbEnd) 0 0 0 nil nil) '
                f'schCreateWireLabel(vbSchemCv nil rbMid {_q(net)} '
                f'{_q(just)} {_q(orient)} {_q(font)} {height:g} nil)))'
            )
        return "progn(" + " ".join(exprs) + ' "ok")'
    if op == "place_wire":
        pts = _point_str(_points_of(cmd, "points"))
        # 官方签名：schCreateWire(cv entry route points xSpacing ySpacing width [color] [lineStyle])
        # 但实测（真机 2026-09-29）：把 color/lineStyle 当**实参**传不落库
        # （DRF 名字匹配不上就静默忽略），而事后赋值 `~>color`/`~>lineStyle`
        # 有效（与 set_wire_properties 同机制，P-078）。所以样式改成创建后赋值。
        # x_spacing/y_spacing 是 schCreateWire 的**创建期吸附网格**；
        # 即使传 0，底层仍可能使用默认吸附网格（本环境实测步距 0.00625），
        # 不会原样保留输入浮点坐标，也不会写入 wire 的 DB 属性。
        body = (
            f'schCreateWire(vbSchemCv {_q(cmd.get("entry", "route"))} '
            f'{_q(cmd.get("route", "full"))} {pts} '
            f'{float(cmd.get("x_spacing", 0)):g} {float(cmd.get("y_spacing", 0)):g} '
            f'{float(cmd.get("width", 0)):g})'
        )
        assigns = ""
        if "color" in cmd:
            assigns += f' __obj~>color = {_q(cmd["color"])}'
        if "line_style" in cmd:
            assigns += f' __obj~>lineStyle = {_q(cmd["line_style"])}'
        if assigns:
            return (f'let((vbW) vbW = {body} '
                    f'foreach(__obj vbW{assigns}) vbW)')
        return body
    if op == "delete_wire":
        pts = _points_of(cmd, "points")
        x1 = min(x for x, _ in pts) - 0.001
        x2 = max(x for x, _ in pts) + 0.001
        y1 = min(y for _, y in pts) - 0.001
        y2 = max(y for _, y in pts) + 0.001
        return (
            f'let((vbSh vbN) vbN = 0 foreach(__obj setof(x vbSchemCv~>shapes '
            "(x~>objType == \"line\" || x~>objType == \"path\") && "
            f'{_region_shape_expr([[x1, y1], [x2, y2]])}) '
            'when(dbDeleteObject(__obj) vbN = vbN + 1)) vbN)'
        )
    if op == "set_wire_properties":
        pts = _points_of(cmd, "points")
        x1 = min(x for x, _ in pts) - 0.001
        x2 = max(x for x, _ in pts) + 0.001
        y1 = min(y for _, y in pts) - 0.001
        y2 = max(y for _, y in pts) + 0.001
        assignments = []
        if "width" in cmd:
            assignments.append(f'__obj~>width = {float(cmd["width"]):g}')
        if "color" in cmd:
            assignments.append(f'__obj~>color = {_q(cmd["color"])}')
        if "line_style" in cmd:
            assignments.append(f'__obj~>lineStyle = {_q(cmd["line_style"])}')
        body = " ".join(assignments) + ' "ok"' if assignments else '"ok"'
        return (
            f'let((vbN) vbN = 0 foreach(__obj setof(x vbSchemCv~>shapes '
            "(x~>objType == \"line\" || x~>objType == \"path\") && "
            f'{_region_shape_expr([[x1, y1], [x2, y2]])}) '
            f'when(progn({body}) vbN = vbN + 1)) vbN)'
        )
    if op == "place_label":
        _pos = _pos_of(cmd)
        body = (
            f'schCreateWireLabel(vbSchemCv nil {_pos[0]:g}:{_pos[1]:g} '
            f'{_q(cmd["text"])} {_q(cmd.get("justify", "lowerCenter"))} '
            f'{_q(cmd.get("orient", "R0"))} {_q(cmd.get("font", "stick"))} '
            f'{float(cmd.get("height", 0.0625)):g}'
        )
        body += ' t' if cmd.get("alias") else ' nil'
        body += ')'
        return body
    if op in ("delete_label", "rename_label", "set_label_properties"):
        x, y = _pos_of(cmd)
        pred = (
            f'x~>objType == "label" && x~>purpose != "drawing" && '
            f'xCoord(x~>xy) >= {x - 0.001:g} && xCoord(x~>xy) <= {x + 0.001:g} && '
            f'yCoord(x~>xy) >= {y - 0.001:g} && yCoord(x~>xy) <= {y + 0.001:g}'
        )
        if op == "delete_label":
            return f'let((vbN) vbN = 0 foreach(__obj setof(x vbSchemCv~>shapes {pred}) when(dbDeleteObject(__obj) vbN = vbN + 1)) vbN)'
        if op == "rename_label":
            return f'let((vbObj) vbObj = car(setof(x vbSchemCv~>shapes {pred})) unless(vbObj error("label not found")) vbObj~>theLabel = {_q(cmd["new_text"])} vbObj~>theLabel)'
        assignments = []
        for key, prop in (("justify", "justify"), ("orient", "orient"), ("font", "font"), ("height", "height")):
            if key in cmd:
                if key == "height":
                    assignments.append(f'vbObj~>{prop} = {float(cmd[key]):g}')
                else:
                    assignments.append(f'vbObj~>{prop} = {_q(cmd[key])}')
        body = " ".join(assignments) + ' vbObj~>theLabel' if assignments else 'vbObj~>theLabel'
        return f'let((vbObj) vbObj = car(setof(x vbSchemCv~>shapes {pred})) unless(vbObj error("label not found")) {body})'
    if op == "place_pin":
        _pos = _pos_of(cmd)
        if cmd.get("off_sheet"):
            raise ValueError(
                "command.off_sheet=true is not supported in this environment: "
                "no usable off-sheet pin master (P-114)"
            )
        name = _q(cmd["name"])
        direction = _q(cmd.get("direction", "inputOutput"))
        orient = _q(cmd.get("orient", "R0"))
        point = f"{_pos[0]:g}:{_pos[1]:g}"
        # schCreatePin 的 offSheet 是第 5 个**必选**实参；power/ground/sigType
        # 才是尾部可选实参。可选参数按位置传，缺前面的项时补 nil。
        power_sens = (
            _require_text(cmd.get("power_sens"), "command.power_sens")
            if cmd.get("power_sens") is not None else None
        )
        ground_sens = (
            _require_text(cmd.get("ground_sens"), "command.ground_sens")
            if cmd.get("ground_sens") is not None else None
        )
        sig_type = cmd.get("sig_type")
        if sig_type is not None:
            sig_type = _require_text(sig_type, "command.sig_type")
            if sig_type not in _PIN_SIG_TYPES:
                raise ValueError(
                    "command.sig_type must be one of "
                    + ", ".join(sorted(_PIN_SIG_TYPES))
                )
        tail = ""
        if power_sens is not None:
            tail += f" {_q(power_sens)}"
        elif ground_sens is not None or sig_type is not None:
            tail += " nil"
        if ground_sens is not None:
            tail += f" {_q(ground_sens)}"
        elif sig_type is not None:
            tail += " nil"
        if sig_type is not None:
            tail += f" {_q(sig_type)}"
        checks: list[str] = []
        if power_sens is not None:
            checks.append(
                "unless(car(setof(tx vbSchemCv~>terminals "
                f"tx~>name == {_q(power_sens)})) "
                'error("power_sens terminal not found"))'
            )
        if ground_sens is not None:
            checks.append(
                "unless(car(setof(tx vbSchemCv~>terminals "
                f"tx~>name == {_q(ground_sens)})) "
                'error("ground_sens terminal not found"))'
            )
        create = (
            f"schCreatePin(vbSchemCv nil {name} {direction} nil "
            f"{point} {orient}{tail})"
        )
        guard = " ".join(checks)
        return (
            f"let((vbPin) {guard + ' ' if guard else ''}"
            f"vbPin = {create} "
            'if(vbPin && vbPin != 0 vbPin '
            'error("place_pin failed: schCreatePin returned nil")))'
        )
    if op in ("delete_pin", "rename_pin", "set_pin_properties"):
        x, y = _pos_of(cmd)
        pred = (
            f'x~>purpose == "pin" && xCoord(x~>xy) >= {x - 0.001:g} '
            f'&& xCoord(x~>xy) <= {x + 0.001:g} '
            f'&& yCoord(x~>xy) >= {y - 0.001:g} && yCoord(x~>xy) <= {y + 0.001:g}'
        )
        if op == "delete_pin":
            return f'let((vbN) vbN = 0 foreach(__obj setof(x vbSchemCv~>instances {pred}) when(dbDeleteObject(__obj) vbN = vbN + 1)) vbN)'
        if op == "rename_pin":
            # P-073：pin 的**有效名（业务名）是 terminal 名**，不是自动生成的 pin 实例名（PIN0）。
            # 实测：实例 ↔ terminal 的关联是 `inst~>pin`（pin 对象）↔ `terminal~>pins`。
            # 改 `inst~>name` 对 read(connectivity)/symbol 端口完全不可见 = 静默无操作。
            return (
                f'let((vbInst vbTerm) vbInst = car(setof(x vbSchemCv~>instances {pred})) '
                'unless(vbInst error("pin not found")) '
                'vbTerm = car(setof(tx vbSchemCv~>terminals member(vbInst~>pin tx~>pins))) '
                'unless(vbTerm error("pin terminal not found")) '
                f'vbTerm~>name = {_q(cmd["new_name"])} '
                'vbTerm~>name)'
            )
        direction = _q(cmd["direction"])
        # P-073：只改方向、**不得改名字**。旧实现拿 pin 实例名（PIN0）去 schCreatePin →
        # 等于新建了一个叫 PIN0 的 terminal，用户的端口名被换掉。
        # 正确做法（真机验证）：找出该 pin 的 terminal → 用它的名字重建 pin（先删实例与旧 terminal）。
        return (
            f'let((vbInst vbTerm vbName vbXy vbOrient vbNew) '
            f'vbInst = car(setof(x vbSchemCv~>instances {pred})) '
            'unless(vbInst error("pin not found")) '
            'vbTerm = car(setof(tx vbSchemCv~>terminals member(vbInst~>pin tx~>pins))) '
            'vbName = if(vbTerm vbTerm~>name vbInst~>name) '
            'vbXy = vbInst~>xy vbOrient = vbInst~>orient '
            'dbDeleteObject(vbInst) '
            'when(vbTerm dbDeleteObject(vbTerm)) '
            f'vbNew = schCreatePin(vbSchemCv nil vbName {direction} nil vbXy vbOrient) '
            'vbNew)'
        )
    if op == "place_note":
        _pos = _pos_of(cmd)
        return (
            f'schCreateNoteLabel(vbSchemCv {_pos[0]:g}:{_pos[1]:g} '
            f'{_q(cmd["text"])} {_q(cmd.get("justify", "lowerLeft"))} '
            f'{_q(cmd.get("orient", "R0"))} {_q(cmd.get("font", "stick"))} '
            f'{float(cmd.get("height", 0.0625)):g} {_q(cmd.get("type", "normalLabel"))})'
        )
    if op in ("delete_note", "rename_note", "set_note_properties"):
        x, y = _pos_of(cmd)
        pred = (
            f'x~>objType == "label" && x~>purpose == "drawing" && '
            f'xCoord(x~>xy) >= {x - 0.001:g} && xCoord(x~>xy) <= {x + 0.001:g} && '
            f'yCoord(x~>xy) >= {y - 0.001:g} && yCoord(x~>xy) <= {y + 0.001:g}'
        )
        if op == "delete_note":
            return f'let((vbN) vbN = 0 foreach(__obj setof(x vbSchemCv~>shapes {pred}) when(dbDeleteObject(__obj) vbN = vbN + 1)) vbN)'
        if op == "rename_note":
            return f'let((vbObj) vbObj = car(setof(x vbSchemCv~>shapes {pred})) unless(vbObj error("note not found")) vbObj~>theLabel = {_q(cmd["new_text"])} vbObj~>theLabel)'
        assignments = []
        for key, prop in (("justify", "justify"), ("orient", "orient"), ("font", "font"), ("height", "height")):
            if key in cmd:
                if key == "height":
                    assignments.append(f'vbObj~>{prop} = {float(cmd[key]):g}')
                else:
                    assignments.append(f'vbObj~>{prop} = {_q(cmd[key])}')
        body = " ".join(assignments) + ' vbObj~>theLabel' if assignments else 'vbObj~>theLabel'
        return f'let((vbObj) vbObj = car(setof(x vbSchemCv~>shapes {pred})) unless(vbObj error("note not found")) {body})'
    raise ValueError(f"unknown atomic op: {op}")

# ---- package ------------------------------------------------------------------

class Package(ResultPackage):
    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    def read(self, request: ReadRequest) -> Result:
        self._log_level = request.log_level
        self._log_max_bytes = request.log_max_bytes
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        skill = _read_skill(request)
        res = self.middle.execute_skill(
            skill, timeout=request.timeout, token=request.token,
            **skill_log_kwargs(request.log_level, request.log_max_bytes),
        )
        steps = [_step("read", res.ok, res)]
        if not res.ok:
            return Result(False, steps, "; ".join(res.errors) or "read failed")
        raw = (res.output or "").strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        raw = raw.replace("\\n", "\n")
        if raw.strip() == "ERROR":
            return Result(False, steps, "schematic could not be opened")
        return Result(True, steps, None, _parse_schematic(raw))

    def write(self, request: WriteRequest) -> Result:
        self._log_level = request.log_level
        self._log_max_bytes = request.log_max_bytes
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        if not isinstance(request.commands, list) or not request.commands:
            raise ValueError("commands must be a non-empty list")
        steps: list[dict[str, Any]] = []
        planned: list[tuple[int, dict[str, Any], str]] = []
        for index, command in enumerate(request.commands):
            if not isinstance(command, dict) or "op" not in command:
                return Result(False, steps, f"command {index} must be an object with op")
            try:
                skill = _atomic_skill(command["op"], command)
            except Exception as exc:  # noqa: BLE001 - structural command error
                return Result(False, steps, f"command {index} invalid: {exc}")
            planned.append((index, command, skill))
        opened = self.middle.execute_skill(
            _open_edit_skill(request.library, request.cell, request.view),
            timeout=request.timeout, token=request.token,
            **skill_log_kwargs(request.log_level, request.log_max_bytes),
        )
        state = (opened.output or "").strip().strip('"')
        steps.append(_step("open", opened.ok and state == "open-ok", opened))
        if not opened.ok:
            return Result(False, steps, "; ".join(opened.errors) or "open failed")
        if state != "open-ok":
            return Result(
                False, steps,
                _open_failure(state, request.library, request.cell, request.view),
            )
        for index, command, skill in planned:
            run = self.middle.execute_skill(
                skill, timeout=request.timeout, token=request.token,
                **skill_log_kwargs(request.log_level, request.log_max_bytes),
            )
            steps.append(_step(f"command:{command['op']}", run.ok, run))
            if not run.ok:
                close_run = self.middle.execute_skill(
                    _close_edit_skill(), timeout=request.timeout, token=request.token,
                    **skill_log_kwargs(
                        request.log_level, request.log_max_bytes,
                    ),
                )
                detail = "; ".join(run.errors) or f"command {command['op']} failed"
                if not close_run.ok:
                    detail += "; additionally, releasing the edit handle failed: " + (
                        "; ".join(close_run.errors) or "unknown")
                return Result(False, steps, detail)
        save_skill = _save_skill()
        saved = self.middle.execute_skill(
            save_skill, timeout=request.timeout, token=request.token,
            **skill_log_kwargs(request.log_level, request.log_max_bytes),
        )
        steps.append(_step("check_and_save", saved.ok, saved))
        if not saved.ok or "saved" not in (saved.output or ""):
            if not saved.ok:
                close_run = self.middle.execute_skill(
                    _close_edit_skill(), timeout=request.timeout, token=request.token,
                    **skill_log_kwargs(
                        request.log_level, request.log_max_bytes,
                    ),
                )
                if not close_run.ok:
                    steps.append(_step("close_edit", False, close_run))
            return Result(
                False, steps,
                "; ".join(saved.errors) or (saved.output or "").strip()
                or "check/save failed",
            )
        return Result(True, steps)

    def screenshot(self, request: ScreenshotRequest) -> Result:
        self._log_level = request.log_level
        self._log_max_bytes = request.log_max_bytes
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        facts = self.middle.query(token=request.token)
        steps = [_step("query", facts.status.value == "success", facts)]
        if facts.status.value != "success":
            return ScreenshotResult(False, steps, "; ".join(facts.errors) or "query failed")
        daemon_role = facts.roles.get("daemon")
        daemon_root = daemon_role.root if daemon_role else None
        if not daemon_root:
            return ScreenshotResult(False, steps, "daemon role root is not available")
        import time as _time
        name = f"{request.cell}_{int(_time.time() * 1000)}.png"
        remote_abs = posixpath.join(daemon_root.rstrip("/"), "screenshots", name)
        mkdir = self.middle.run_command(
            f"mkdir -p {shlex.quote(posixpath.dirname(remote_abs))}",
            timeout=request.timeout, token=request.token,
        )
        steps.append(_step("mkdir", mkdir.returncode == 0, mkdir))
        if mkdir.returncode != 0:
            return ScreenshotResult(False, steps, mkdir.stderr or "mkdir failed")
        opened_here = False
        try:
            if request.window_id is None:
                ensured = self.middle.execute_skill(
                    _ensure_window_skill(request),
                    timeout=request.timeout,
                    token=request.token,
                    **skill_log_kwargs(
                        request.log_level, request.log_max_bytes),
                )
                steps.append(_step("ensure_window", ensured.ok, ensured))
                if not ensured.ok:
                    return ScreenshotResult(
                        False, steps,
                        "; ".join(ensured.errors) or "window open failed")
                opened_here = (
                    (ensured.output or "").strip().strip('"') == "opened")
                _time.sleep(1)
            captured = self.middle.execute_skill(
                _screenshot_skill(request, remote_abs),
                timeout=request.timeout,
                token=request.token,
                **skill_log_kwargs(request.log_level, request.log_max_bytes),
            )
            steps.append(_step("capture", captured.ok, captured))
            if not captured.ok:
                return ScreenshotResult(
                    False, steps,
                    "; ".join(captured.errors) or "capture failed")
            local_dir = artifact_dir() / "screenshots"
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / name
            downloaded = self.middle.download_file(
                remote_abs, local_path, timeout=request.timeout, token=request.token,
            )
            steps.append(_step("download", downloaded.returncode == 0, downloaded))
            if downloaded.returncode != 0:
                return ScreenshotResult(False, steps, downloaded.stderr or "download failed")
            return ScreenshotResult(True, steps, None, str(local_path))
        finally:
            if opened_here and not request.leave_open:
                try:
                    closed = self.middle.execute_skill(
                        _close_window_skill(request),
                        timeout=request.timeout,
                        token=request.token,
                        **skill_log_kwargs(
                            request.log_level, request.log_max_bytes),
                    )
                    steps.append(_step("close_window", closed.ok, closed))
                except Exception:  # noqa: BLE001 - best effort
                    pass
            # 远端只做暂存，留存位置是客户端 artifact/screenshots/（P-091 口径：
            # 三包统一「下载后清理」）。清理失败不改变业务结果。
            try:
                self.middle.run_command(
                    f"rm -f {shlex.quote(remote_abs)}",
                    timeout=10, token=request.token,
                )
            except Exception:  # noqa: BLE001 - best effort
                pass

    def check_and_save(self, request: CheckSaveRequest) -> Result:
        self._log_level = request.log_level
        self._log_max_bytes = request.log_max_bytes
        _require_text(request.token, "token")
        _require_text(request.library, "library")
        _require_text(request.cell, "cell")
        _require_text(request.view, "view")
        _require_timeout(request.timeout)
        steps: list[dict[str, Any]] = []
        opened = self.middle.execute_skill(
            _open_edit_skill(request.library, request.cell, request.view),
            timeout=request.timeout, token=request.token,
            **skill_log_kwargs(request.log_level, request.log_max_bytes),
        )
        state = (opened.output or "").strip().strip('"')
        steps.append(_step("open", opened.ok and state == "open-ok", opened))
        if not opened.ok:
            return Result(False, steps, "; ".join(opened.errors) or "open failed")
        if state != "open-ok":
            return Result(
                False, steps,
                _open_failure(state, request.library, request.cell, request.view),
            )
        save_skill = _save_skill()
        saved = self.middle.execute_skill(
            save_skill, timeout=request.timeout, token=request.token,
            **skill_log_kwargs(request.log_level, request.log_max_bytes),
        )
        steps.append(_step("check_and_save", saved.ok, saved))
        if not saved.ok or "saved" not in (saved.output or ""):
            if not saved.ok:
                close_run = self.middle.execute_skill(
                    _close_edit_skill(), timeout=request.timeout, token=request.token,
                    **skill_log_kwargs(
                        request.log_level, request.log_max_bytes,
                    ),
                )
                if not close_run.ok:
                    steps.append(_step("close_edit", False, close_run))
            return Result(
                False, steps,
                "; ".join(saved.errors) or (saved.output or "").strip()
                or "check/save failed",
            )
        return Result(True, steps)


# ---- screenshot --------------------------------------------------------------

@dataclass(frozen=True)
class ScreenshotRequest:
    token: str
    library: str
    cell: str
    view: str = "schematic"
    window_id: int | None = None
    region: list[float] | None = None   # [x1,y1,x2,y2] user units; zoom-to-area first
    toplevel: bool = True
    central_widget: bool = True
    leave_open: bool = False
    timeout: int | None = None
    log_level: str | None = None
    log_max_bytes: int | None = None
    step_details: bool = False


@dataclass
class ScreenshotResult(ResultBase):
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    local_path: str | None = None


def _ensure_window_skill(request: ScreenshotRequest) -> str:
    return _screenshot.ensure_window_skill(
        request,
        view_type_expr='"schematic"',
        not_found_message="window not found",
    )


def _close_window_skill(request: ScreenshotRequest) -> str:
    return _screenshot.close_window_skill(request)


def _screenshot_skill(request: ScreenshotRequest, remote_path: str) -> str:
    region = (
        _region_of(request.region, "region")
        if request.region is not None else None
    )
    return _screenshot.screenshot_skill(
        request,
        remote_path,
        region=region,
        not_found_message="window not found",
        view_type_expr='"schematic"',
        window_id_style="window_call",
        zoom_style="pair",
    )

OPERATIONS = (
    ("virtuoso.schematic.read", "read", ReadRequest, Result),
    ("virtuoso.schematic.write", "write", WriteRequest, Result),
    ("virtuoso.schematic.check_and_save", "check_and_save", CheckSaveRequest, Result),
    ("virtuoso.schematic.screenshot", "screenshot", ScreenshotRequest, ScreenshotResult),
)

__all__ = ["CheckSaveRequest", "OPERATIONS", "Package", "ReadRequest", "Result", "ScreenshotRequest", "ScreenshotResult", "WriteRequest"]
