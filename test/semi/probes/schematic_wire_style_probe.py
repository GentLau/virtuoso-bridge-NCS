# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 19:58
# 依赖: test/live/flows/design_iterate_tb.py
# =======================================================================
"""原理图 ``place_wire`` 样式参数探针：width / color / line_style / entry / route

背景（第八轮参数矩阵核账发现）：`place_wire` 只传 `points` 正常；一旦传
`width`/`color`/`line_style`，`src/pyapi/packages/schematic.py` 的拼接会出现
**重复实参**（离线可复现）：

    points only            -> schCreateWire(cv "route" "full" pts 0 0 0)
    width=0.1              -> ... 0 0 0.1 0.1 nil        ← width 被拼两次
    width+color+line_style -> ... 0 0 0.1 "red" "dashed" 0.1 "red" "dashed"

本探针在真机回答两件事：
1. 这些形态**能不能执行**（write 是否报错）；
2. 即使 write 报 ok，**读回的几何属性是否正确**（width/color/line_style）。

判据（每例独立 cell，六步流程见规范）：
    ctrl   : points only           → 1 条 wire
    width  : width=0.1             → wire.width≈0.1
    color  : width=0.1+color=red   → wire.color=="red" 且 width≈0.1
    style  : +line_style=dashed    → wire.line_style=="dashed" 且 color/width 对
    route  : entry/route 显式值    → 1 条 wire（entry/route 不直接读回，判"可执行"）

用法::

    python test/semi/probes/schematic_wire_style_probe.py --token <PDK_TOKEN>

证据：``test/artifacts/evidence/round8/schematic-wire-style.json``
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "test" / "live" / "flows"))
sys.path.insert(0, str(ROOT / "src"))

import design_iterate_tb as tb  # noqa: E402  （复用 HTTP/SKILL 约定）

LIB = "WIRESTYL"
FILE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/file/wire_style"
OUT = ROOT / "test" / "artifacts" / "evidence" / "round8" / "schematic-wire-style.json"

#: case 名 → (cell, 命令, 期望函数)
CASES: dict[str, dict[str, Any]] = {
    "ctrl": {
        "cell": "w_ctrl",
        "cmd": {"op": "place_wire", "points": [[0.0, 0.0], [2.0, 0.0]]},
        "expect": lambda w: w.get("points") is not None,
        "expect_note": "points only → 1 条 wire，端点可读回",
    },
    "width": {
        "cell": "w_width",
        "cmd": {"op": "place_wire", "points": [[0.0, 0.0], [2.0, 0.0]], "width": 0.1},
        "expect": lambda w: abs(float(w.get("width") or 0.0) - 0.1) < 1e-6,
        "expect_note": "width=0.1 → 读回 width≈0.1",
    },
    "color": {
        "cell": "w_color",
        "cmd": {"op": "place_wire", "points": [[0.0, 0.0], [2.0, 0.0]],
                "width": 0.1, "color": "red"},
        "expect": lambda w: (w.get("color") == "red"
                             and abs(float(w.get("width") or 0.0) - 0.1) < 1e-6),
        "expect_note": "width+color → 读回 color==red 且 width≈0.1",
    },
    "style": {
        "cell": "w_style",
        "cmd": {"op": "place_wire", "points": [[0.0, 0.0], [2.0, 0.0]],
                "width": 0.1, "color": "red", "line_style": "dashed"},
        "expect": lambda w: (w.get("color") == "red"
                             and w.get("line_style") == "dashed"),
        "expect_note": "width+color+line_style → 读回三项全对",
    },
    "route": {
        "cell": "w_route",
        "cmd": {"op": "place_wire", "points": [[0.0, 0.0], [2.0, 0.0]],
                "entry": "route", "route": "full"},
        "expect": lambda w: w.get("points") is not None,
        "expect_note": "entry/route 显式值 → 1 条 wire（值本身不读回）",
    },
}


def offline_skill(cmd: dict[str, Any]) -> str:
    """离线生成同一命令的 SKILL 文本（用于证据里记录根因）。"""
    try:
        from pyapi.packages import schematic as sch
        return sch._atomic_skill("place_wire", dict(cmd))
    except Exception as exc:  # noqa: BLE001 - 记录即可
        return f"<offline unavailable: {exc}>"


def write(t: Any, cell: str, commands: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        data = tb.op(t, "virtuoso.schematic.write", library=LIB, cell=cell,
                     view="schematic", commands=commands, timeout=600)
        tb.op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=cell,
              view="schematic", timeout=300)
        return {"write_ok": True, "error": None, "steps": data.get("steps")}
    except tb.FlowError as exc:
        return {"write_ok": False, "error": str(exc.error), "steps": None}


def read_wires(t: Any, cell: str) -> list[dict[str, Any]]:
    data = tb.op(t, "virtuoso.schematic.read", library=LIB, cell=cell,
                 view="schematic", focus="positions", timeout=300)
    value = data.get("value") or {}
    return value.get("wires") or []


def db_shapes(t: Any, cell: str) -> str:
    """DB 级形状清单：objType/width/color/lineStyle —— read 看不见的差异在这里暴露。"""
    return tb.skill(
        t,
        f'let((cv) cv = dbOpenCellViewByType("{LIB}" "{cell}" "schematic" "schematic" "r") '
        f'if(cv mapcar(lambda((s) list(s~>objType s~>width s~>color s~>lineStyle)) '
        f'cv~>shapes) "NO-CV"))',
    ).strip()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default=tb.PDK_TOKEN)
    ap.add_argument("--base", default=tb.API)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    t = tb.HttpTransport(args.token, args.base)
    evidence: dict[str, Any] = {"lib": LIB, "cases": {}}

    # 第 1 步 环境检查：命令面 + PDK lib 可用
    tb.op(t, "basic.command.run", cmd=f"mkdir -p {FILE_ROOT} && echo ok", timeout=120)
    # 第 3 步 构建测试环境：专用 lib + 每例一个 cell
    try:
        tb.op(t, "virtuoso.cellview.lib.create", library=LIB, path=f"{FILE_ROOT}/{LIB}",
              technology_library=tb.PDK_LIB, timeout=300)
        evidence["lib_created"] = True
    except tb.FlowError as exc:
        evidence["lib_created"] = str(exc.error)
    for name, case in CASES.items():
        try:
            tb.op(t, "virtuoso.cellview.view.create", library=LIB, cell=case["cell"],
                  view="schematic", view_type="schematic", timeout=180)
        except tb.FlowError:
            pass  # 已存在即可

    bugs: list[str] = []
    # 第 4 步 执行 + 第 5 步 判据
    for name, case in CASES.items():
        cmd = case["cmd"]
        w = write(t, case["cell"], [cmd])
        wires = read_wires(t, case["cell"]) if w["write_ok"] else []
        wire = (wires[0] if wires else {}) or {}
        shapes = db_shapes(t, case["cell"]) if w["write_ok"] else ""
        ok = bool(w["write_ok"]) and len(wires) == 1 and bool(case["expect"](wire))
        row = {
            "cell": case["cell"],
            "command": cmd,
            "offline_skill": offline_skill(cmd),
            "write_ok": w["write_ok"],
            "write_error": w["error"],
            "wire_count": len(wires),
            "wire": {k: wire.get(k) for k in ("points", "width", "color", "line_style")},
            "db_shapes": shapes,
            "expect": case["expect_note"],
            "verdict": "OK" if ok else "BUG",
        }
        evidence["cases"][name] = row
        if not ok:
            bugs.append(name)
        print(json.dumps({"case": name, **{k: row[k] for k in (
            "write_ok", "write_error", "wire_count", "wire", "db_shapes", "verdict")}},
            ensure_ascii=False))
        print("   skill:", row["offline_skill"][:160])

    evidence["summary"] = {"bugs": bugs, "ok": [n for n in CASES if n not in bugs]}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print("evidence:", args.out)
    print("summary:", json.dumps(evidence["summary"], ensure_ascii=False))
    # 有 BUG 即非零退出：半真机 runner 按 rc 判红（否则"探针打印 BUG 但 rc=0"会被记成 ok）。
    return 1 if bugs else 0


if __name__ == "__main__":
    raise SystemExit(main())
