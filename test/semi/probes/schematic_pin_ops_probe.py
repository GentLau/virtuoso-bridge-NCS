# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 20:40
# 依赖: 无
# =======================================================================
"""原理图 pin 原子操作探针：``rename_pin`` / ``set_pin_properties`` / ``delete_pin``
**写成功**与**改没改**是两件事 —— 本探针只认"改动是否对下游可见"。

背景（第七轮实测发现）：`virtuoso.schematic.write` 的 `rename_pin` 返回
``status=success, output="vout_main"``，`check_and_save` 也返回 `saved`，但

1. `virtuoso.schematic.read` 的 pin 列表里**仍是旧名**；
2. `virtuoso.symbol.generate` 二次出图的端口名**仍是旧名**（即网表/符号下游看不到改名）；
3. 直接读 DB 才看得到变化：pin **实例** 的名字变成了新名
   （`("PIN0" "vout_main" "PIN3" "PIN2")`），而其它 pin 的实例名是自动名
   （PIN0/PIN2/PIN3）——说明"pin 的有效名"来自 pin 标签，而不是实例名。

本探针把这个口径固定下来，四个角度全查：

    baseline → rename_pin → set_pin_properties(direction) → delete_pin
    每步之后都查：write 自报 / schematic.read 的 pins / DB 里 pin 实例名 /
    symbol.generate 后的端口集合

用法::

    python test/semi/probes/schematic_pin_ops_probe.py --token d6af595b342647b58ec63ca6

证据：``test/artifacts/evidence/round7/pin-ops.json``
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "test" / "live" / "flows"))

import design_iterate_tb as tb  # noqa: E402  （复用 HTTP/SKILL/Stage 约定）

LIB = "PINOP"
CELL = "pin_cell"
FILE_ROOT = "/home/Gent/.virtuoso-bridge/calprobe/file/pin_ops"
OUT = ROOT / "test" / "artifacts" / "evidence" / "round7" / "pin-ops.json"

SCHEMATIC = [
    {"op": "place_instance", "master_lib": tb.PDK_LIB, "master_cell": tb.PCH,
     "master_view": "symbol", "name": "MP", "pos": [0.0, 1.0], "orient": "R0"},
    {"op": "place_instance", "master_lib": tb.PDK_LIB, "master_cell": tb.NCH,
     "master_view": "symbol", "name": "MN", "pos": [0.0, -1.0], "orient": "R0"},
    {"op": "set_term_nets", "name": "MP",
     "term_nets": {"G": "a", "D": "y", "S": "vdd", "B": "vdd"}},
    {"op": "set_term_nets", "name": "MN",
     "term_nets": {"G": "a", "D": "y", "S": "vss", "B": "vss"}},
    {"op": "place_pin", "name": "a", "direction": "input", "pos": [-4.0, 0.0]},
    {"op": "place_pin", "name": "y", "direction": "output", "pos": [4.0, 0.0]},
]


def read_pins(t) -> dict[str, Any]:
    data = tb.op(t, "virtuoso.schematic.read", library=LIB, cell=CELL,
                 view="schematic", timeout=300)
    value = data.get("value") or {}
    return {"pins": [p.get("name") for p in (value.get("pins") or [])],
            "nets": sorted((value.get("nets") or {}).keys())}


def db_pin_instances(t) -> Any:
    out = tb.skill(
        t,
        f'let((cv) cv=dbOpenCellViewByType("{LIB}" "{CELL}" "schematic" "schematic" "r") '
        f'mapcar(lambda((i) list(i~>name i~>cellName)) '
        f'setof(i cv~>instances i~>purpose=="pin")))',
    )
    return out.strip()


def symbol_terms(t) -> list[str]:
    tb.op(t, "virtuoso.symbol.generate", library=LIB, cell=CELL,
          schematic_view="schematic", symbol_view="symbol", overwrite=True, timeout=600)
    data = tb.op(t, "virtuoso.symbol.read", library=LIB, cell=CELL, view="symbol",
                 timeout=300)
    value = data.get("value") or {}
    return sorted(x.get("name") for x in (value.get("terms") or []))


def write(t, commands: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        data = tb.op(t, "virtuoso.schematic.write", library=LIB, cell=CELL,
                     view="schematic", commands=commands, timeout=600)
        tb.op(t, "virtuoso.schematic.check_and_save", library=LIB, cell=CELL,
              view="schematic", timeout=300)
        return {"write_ok": True, "steps": data.get("steps"), "error": None}
    except tb.FlowError as exc:
        return {"write_ok": False, "steps": None, "error": str(exc.error)}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default=tb.PDK_TOKEN)
    ap.add_argument("--base", default=tb.API)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    t = tb.HttpTransport(args.token, args.base)
    evidence: dict[str, Any] = {"token_probe": None, "cells": {}}
    tb.op(t, "basic.command.run", cmd=f"mkdir -p {FILE_ROOT} && echo ok", timeout=120)
    try:
        tb.op(t, "virtuoso.cellview.lib.create", library=LIB, path=f"{FILE_ROOT}/{LIB}",
              technology_library=tb.PDK_LIB, timeout=300)
        evidence["lib_created"] = True
    except tb.FlowError as exc:
        evidence["lib_created"] = str(exc.error)
    try:
        tb.op(t, "virtuoso.cellview.view.create", library=LIB, cell=CELL,
              view="schematic", view_type="schematic", timeout=180)
    except tb.FlowError as exc:
        evidence["view_note"] = str(exc.error)

    baseline_write = write(t, SCHEMATIC)
    evidence["baseline_write"] = baseline_write
    baseline = read_pins(t)
    baseline["db_instances"] = db_pin_instances(t)
    baseline["symbol_terms"] = symbol_terms(t)
    evidence["baseline"] = baseline

    results: list[dict[str, Any]] = []

    def snapshot() -> dict[str, Any]:
        pins = read_pins(t)
        return {"pins": pins["pins"], "nets": pins["nets"], "db": db_pin_instances(t)}

    def step(name: str, commands: list[dict[str, Any]], kind: str) -> None:
        before = snapshot()
        w = write(t, commands)
        after = snapshot()
        if kind == "rename":
            effective = after["pins"] != before["pins"]
            expectation = "改名后 schematic.read 的 pin 名应变化"
        elif kind == "direction":
            # 改方向**必须只动方向**：DB 里 pin 实例的 master 要变，而 pin 名集合原样
            # （2026-09-24 实测：名字被换成自动名 PIN1 → 下游 symbol 端口跟着变）
            direction_changed = after["db"] != before["db"]
            names_intact = after["pins"] == before["pins"]
            effective = direction_changed and names_intact
            expectation = ("改方向后 DB 里 pin 实例 master 应变化，"
                           "且 pin 名集合必须保持不变")
        else:
            effective = len(after["pins"]) < len(before["pins"])
            expectation = "删 pin 后 schematic.read 的 pin 数应减少"
        row = {
            "op": name,
            "commands": commands,
            "write_ok": w["write_ok"],
            "write_error": w["error"],
            "write_steps": w["steps"],
            "pins_before": before["pins"],
            "pins_after": after["pins"],
            "db_before": before["db"],
            "db_after": after["db"],
            "effective_change": effective,
            "expectation": expectation,
            "symbol_terms_after": symbol_terms(t),
        }
        row["verdict"] = "OK" if effective else "BUG"
        results.append(row)
        print(json.dumps({k: row[k] for k in ("op", "write_ok", "write_error",
                                              "pins_before", "pins_after",
                                              "effective_change", "verdict")},
                         ensure_ascii=False))
        print("   symbol terms:", row["symbol_terms_after"])
        print("   db before    :", str(row["db_before"])[:200])
        print("   db after     :", str(row["db_after"])[:200])

    # 说明：pin 的索引在实现里是 x/y（spec 表格写 xy，口径不一致见 R7-DOC-01）
    step("rename_pin(a→a2)", [{"op": "rename_pin", "pos": [-4.0, 0.0],
                              "new_name": "a2"}], "rename")
    step("set_pin_properties(y→input)", [{"op": "set_pin_properties", "pos": [4.0, 0.0],
                                         "direction": "input"}], "direction")
    step("delete_pin(a)", [{"op": "delete_pin", "pos": [-4.0, 0.0]}], "delete")

    evidence["steps"] = results
    evidence["summary"] = {
        "bugs": [r["op"] for r in results if r["verdict"] == "BUG"],
        "ok": [r["op"] for r in results if r["verdict"] == "OK"],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print("evidence:", args.out)
    print("summary:", json.dumps(evidence["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
