# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-30 12:05
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查：`basic.skill.execute("1+2")` 探活 + `ddUpdateLibList()` 后校验库可见；
# ②③ 构建：每条用例用**唯一 cell**（`nk_<tag>_<stamp>`），互不干扰；
# ④ 只做被测动作：每条键各一次写（place_pin / set_pin_properties / place_label / place_wire）；
# ⑤ 读回比对：用 **DB 直读**（`dbOpenCellViewByType ... "r"` + 属性/bbox）断言期望值，
#    不接受"只判 ok"；无法读回的（wire spacing）如实记录为惰性参数候选；
# ⑥ 不改共享库（只建自己的 cell）；JSON 证据落盘。
"""round9 · 嵌套命令键真机覆盖（op×参数矩阵盲区，`nested-key-coverage.md` §2 的 symbol/schematic 部分）。

覆盖键：
  * `place_pin`：`half_size` / `label_font` / `label_height` / `label_justify` / `label_orient` / `label_pos`
  * `set_pin_properties`：`label_justify` / `label_orient` / `label_font` / `label_height`
  * `place_label`（drawing）：`label_type`
  * `place_wire`：`x_spacing` / `y_spacing`（创建期 X/Y 吸附网格；用
    非网格点 + route 几何对照验证，不读 DB property）

用法::

    PYTHONPATH=src python test/live/packages/nested_keys_e2e_tests.py \
        --transport http [--lib schemtest]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
LIB = "schemtest"
STAMP = time.strftime("%H%M%S")


class HttpTransport:
    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return transport.call({"operation": operation, "token": TOKEN, **fields})


def _payload(response: dict[str, Any]) -> dict[str, Any]:
    for key in ("value", "result"):
        value = response.get(key)
        if isinstance(value, dict):
            return value
    return {}


def _skill(transport, code: str) -> str:
    response = _op(transport, "basic.skill.execute", skill_code=code)
    if response.get("ok") is not True:
        raise AssertionError(f"skill failed: {response.get('error')}")
    return str(_payload(response).get("output") or "")


def _readback_pin(transport, cell: str, pin: str) -> str:
    expr = "\n".join([
        "let((cv tm pn fig lbl bb lb out)",
        f'  cv = dbOpenCellViewByType("{LIB}" "{cell}" "symbol" "schematicSymbol" "r")',
        f'  tm = car(setof(x cv~>terminals x~>name == "{pin}"))',
        "  pn = car(tm~>pins)",
        "  fig = pn~>fig",
        f'  lbl = car(setof(s cv~>shapes s~>objType == "label" && s~>theLabel == "{pin}"))',
        "  bb = fig~>bBox",
        "  lb = when(lbl list(lbl~>justify lbl~>orient lbl~>font lbl~>height lbl~>labelType",
        "                        when(lbl~>xy list(xCoord(lbl~>xy) yCoord(lbl~>xy)))))",
        '  out = list("bbox" list(xCoord(car(bb)) yCoord(car(bb)) xCoord(cadr(bb)) yCoord(cadr(bb)))',
        '            "label" lb)',
        "  dbClose(cv)",
        "  out)",
    ])
    return _skill(transport, expr).strip()


def run_suite(transport) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    results: list[tuple[str, str]] = []
    evidence: dict[str, Any] = {"stamp": STAMP}

    def run(name: str, func) -> Any:
        try:
            value = func()
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            print(f"FAIL    {name}: {type(exc).__name__}: {exc}", flush=True)
            return None
        results.append((name, "PASS"))
        return value

    def new_symbol_cell(tag: str) -> str:
        cell = f"nk_{tag}_{STAMP}"
        response = _op(transport, "virtuoso.cellview.view.create",
                       library=LIB, cell=cell, view="symbol",
                       view_type="schematicSymbol")
        assert response.get("ok") is True, f"建 cell 失败: {response.get('error')}"
        return cell

    def new_schematic_cell(tag: str) -> str:
        cell = f"nk_{tag}_{STAMP}"
        response = _op(transport, "virtuoso.cellview.view.create",
                       library=LIB, cell=cell, view="schematic",
                       view_type="schematic")
        assert response.get("ok") is True, f"建 cell 失败: {response.get('error')}"
        return cell

    def read_wire_points(cell: str) -> list[list[float]]:
        raw = _skill(transport, "\n".join([
            "let((cv obj pts out)",
            f'  cv = dbOpenCellViewByType("{LIB}" "{cell}" "schematic" "schematic" "r")',
            "  obj = car(cv~>shapes)",
            "  pts = when(obj~>points",
            "    mapcar(lambda((p) list(xCoord(p) yCoord(p))) obj~>points))",
            "  out = pts",
            "  dbClose(cv)",
            "  out)",
        ])).strip()
        points: list[list[float]] = []
        for match in re.finditer(
                r"\(([-+0-9.eE]+)\s+([-+0-9.eE]+)\)", raw):
            points.append([float(match.group(1)), float(match.group(2))])
        return points

    def write_wire(cell: str, points: list[list[float]],
                   *, x_spacing: float, y_spacing: float) -> None:
        response = _op(
            transport, "virtuoso.schematic.write",
            library=LIB, cell=cell, view="schematic",
            commands=[{
                "op": "place_wire", "points": points,
                "entry": "route", "route": "full",
                "x_spacing": x_spacing, "y_spacing": y_spacing,
                "width": 0.05,
            }])
        assert response.get("ok") is True, (
            f"place_wire 失败: {response.get('error')}")

    def case_env() -> None:
        response = _op(transport, "basic.skill.execute", skill_code="1+2")
        assert response.get("ok") is True, "环境探活失败"
        _skill(transport, "ddUpdateLibList() t")
        visible = _skill(transport, f'ddGetObj("{LIB}")~>name').strip().strip('"')
        assert visible == LIB, f"库不可见: {LIB!r} -> {visible!r}"

    def case_place_pin_label_keys() -> None:
        cell = new_symbol_cell("pin")
        want = {"half_size": 0.1, "label_justify": "lowerLeft",
                "label_orient": "R90", "label_font": "fixed",
                "label_height": 0.2, "label_pos": [0.5, 0.5]}
        response = _op(transport, "virtuoso.symbol.write",
                       library=LIB, cell=cell, view="symbol",
                       view_type="schematicSymbol",
                       commands=[{"op": "place_pin", "name": "P1", "pos": [0, 0],
                                  "direction": "input", **want}])
        assert response.get("ok") is True, f"place_pin 失败: {response.get('error')}"
        got = _readback_pin(transport, cell, "P1")
        evidence["place_pin"] = {"cell": cell, "want": want, "db": got}
        assert "(-0.1 -0.1 0.1 0.1)" in got, f"half_size 未生效（bbox 应 ±0.1）: {got}"
        assert '"lowerLeft" "R90" "fixed" 0.2' in got, f"label 属性未落库: {got}"
        assert "0.5 0.5" in got, f"label_pos 未生效（应 0.5 0.5）: {got}"

    def case_set_pin_properties_label_keys() -> None:
        cell = new_symbol_cell("setpin")
        base = _op(transport, "virtuoso.symbol.write",
                   library=LIB, cell=cell, view="symbol",
                   view_type="schematicSymbol",
                   commands=[{"op": "place_pin", "name": "P1", "pos": [0, 0],
                              "direction": "output"}])
        assert base.get("ok") is True, f"预置 pin 失败: {base.get('error')}"
        changed = _op(transport, "virtuoso.symbol.write",
                      library=LIB, cell=cell, view="symbol",
                      view_type="schematicSymbol",
                      commands=[{"op": "set_pin_properties", "name": "P1",
                                 "label_justify": "upperRight",
                                 "label_orient": "R180", "label_font": "fixed",
                                 "label_height": 0.3}])
        assert changed.get("ok") is True, f"set_pin_properties 失败: {changed.get('error')}"
        got = _readback_pin(transport, cell, "P1")
        evidence["set_pin_properties"] = {"cell": cell, "db": got}
        assert '"upperRight" "R180" "fixed" 0.3' in got, f"键未落库: {got}"

    def case_place_label_type() -> None:
        cell = new_symbol_cell("label")
        response = _op(transport, "virtuoso.symbol.write",
                       library=LIB, cell=cell, view="symbol",
                       view_type="schematicSymbol",
                       commands=[{"op": "place_label", "label_kind": "drawing",
                                  "text": "NK", "pos": [1, 1],
                                  "layer": "text", "purpose": "drawing",
                                  "label_type": "NLPLabel"}])
        assert response.get("ok") is True, f"place_label 失败: {response.get('error')}"
        got = _skill(transport, "\n".join([
            "let((cv lbl out)",
            f'  cv = dbOpenCellViewByType("{LIB}" "{cell}" "symbol" "schematicSymbol" "r")',
            '  lbl = car(setof(s cv~>shapes s~>objType == "label"))',
            "  out = lbl~>labelType",
            "  dbClose(cv)",
            "  out)",
        ])).strip()
        evidence["place_label_type"] = {"cell": cell, "labelType": got}
        assert got.strip(chr(34)) == "NLPLabel", f"label_type 未落库（实测 {got!r}）"

    def case_place_wire_x_spacing() -> None:
        points = [[0.13, 0.07], [1.37, 0.63]]
        base_cell = new_schematic_cell("wire_x_base")
        spaced_cell = new_schematic_cell("wire_x_snap")
        write_wire(base_cell, points, x_spacing=0.0, y_spacing=0.0)
        # x/y 是同一组 route 吸附网格；x 的正例与 y 一起给非零步距，
        # 几何变化只应体现在 x 顶点 0.5625→0.6，y 顶点保持原值。
        write_wire(spaced_cell, points, x_spacing=0.1, y_spacing=0.1)
        base = read_wire_points(base_cell)
        snapped = read_wire_points(spaced_cell)
        evidence["place_wire_x_spacing"] = {
            "points": points,
            "base_cell": base_cell,
            "spaced_cell": spaced_cell,
            "base": base,
            "snapped": snapped,
        }
        assert base and snapped, f"wire points 为空: base={base}, snapped={snapped}"
        assert base != snapped, (
            f"x_spacing=0.1 未改变 route 几何: base={base}, snapped={snapped}")
        base_x = [point[0] for point in base]
        assert any(
            abs(x / 0.1 - round(x / 0.1)) <= 1e-6
            and all(abs(x - old) > 1e-6 for old in base_x)
            for x, _y in snapped
        ), f"x_spacing=0.1 未产生 0.1 网格上的新 x 顶点: {snapped}"

    def case_place_wire_y_spacing() -> None:
        points = [[0.13, 0.07], [0.63, 1.37]]
        base_cell = new_schematic_cell("wire_y_base")
        spaced_cell = new_schematic_cell("wire_y_snap")
        write_wire(base_cell, points, x_spacing=0.0, y_spacing=0.0)
        write_wire(spaced_cell, points, x_spacing=0.0, y_spacing=0.1)
        base = read_wire_points(base_cell)
        snapped = read_wire_points(spaced_cell)
        evidence["place_wire_y_spacing"] = {
            "points": points,
            "base_cell": base_cell,
            "spaced_cell": spaced_cell,
            "base": base,
            "snapped": snapped,
        }
        assert base and snapped, f"wire points 为空: base={base}, snapped={snapped}"
        assert base != snapped, (
            f"y_spacing=0.1 未改变 route 几何: base={base}, snapped={snapped}")
        base_y = [point[1] for point in base]
        assert any(
            abs(y / 0.1 - round(y / 0.1)) <= 1e-6
            and all(abs(y - old) > 1e-6 for old in base_y)
            for _x, y in snapped
        ), f"y_spacing=0.1 未产生 0.1 网格上的新 y 顶点: {snapped}"

    run("NK-ENV 环境检查（1+2）", case_env)
    run("NK-01 place_pin 6 个标签键（bbox+label 值级读回）", case_place_pin_label_keys)
    run("NK-02 set_pin_properties 4 个标签键（值级读回）", case_set_pin_properties_label_keys)
    run("NK-03 place_label(label_type=NLPLabel) 值级读回", case_place_label_type)
    run("NK-04a place_wire x_spacing（非网格点 route 几何对照）",
        case_place_wire_x_spacing)
    run("NK-04b place_wire y_spacing（非网格点 route 几何对照）",
        case_place_wire_y_spacing)
    return results, evidence


def main() -> int:
    global API, TOKEN, LIB
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("http",), default="http")
    parser.add_argument("--api", default=API)
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--lib", default=LIB)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()
    API, TOKEN = args.api, args.token
    LIB = args.lib
    results, evidence = run_suite(HttpTransport())
    for name, status in results:
        print(f"{status:6}  {name}")
    if args.out:
        from pathlib import Path
        evidence["api"] = API
        evidence["results"] = [{"case": n, "status": s} for n, s in results]
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print(f"evidence: {out_path}")
    return 0 if results and all(s == "PASS" for _, s in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
