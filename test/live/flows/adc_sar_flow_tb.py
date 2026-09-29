# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 16:15
# 依赖: 无
# =====================================================================
"""ADC(SAR) 实际项目全流程 TB（真机级）。

在共享库 `adc_sar`（`/project/libs/adc_sar`，经 `/project/cds.lib.shared` 对多用户可见）里，
由一个用户走完"原理图 → symbol → 版图 → GDS 导出"的真实设计动作，再由另一个用户跨账号回读/改单：

  1. A：建 3 个 schematic（`cmp_*` 比较器、`latch_*` 时钟闩、`sar_top_*` 顶层），画 PDK 器件与引脚；
  2. A：给 `cmp_*` / `latch_*` 生成 symbol，并在 `sar_top_*` 里实例化它们；
  3. A：给 `sar_top_*` 建 layout 视图并画 M1 版图（矩形/走线/标签），读回校验形状数；
  4. A：**GDS 导出到"还不存在"的目录**（顺带回归 P-051：远端发布必须先建目标目录），再用命令接口确认落盘；
  5. B：跨用户回读 `sar_top_*` 的 schematic 与 layout（双向可见），并往 `sar_top_*` 补一个 `latch_*` 实例；
  6. A：回读确认能看到 B 的实例；B 跑 check_and_save；顺带 `spectre.check_license` 环境点检。

用法::

    PYTHONPATH=src python test/live/flows/adc_sar_flow_tb.py \
        --work-dir test/artifacts/env/log-vblog --token-a vb-vbuser1 --token-b vb-vbuser2 \
        --out test/artifacts/evidence/round5-adc-sar.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
_RUNNERS = Path(__file__).resolve().parents[3] / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

PDK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8127/api/operation")
    parser.add_argument("--work-dir", default="test/artifacts/env/log-vblog")
    parser.add_argument("--token-a", default="vb-vbuser1")
    parser.add_argument("--token-b", default="vb-vbuser2")
    parser.add_argument("--lib", default="adc_sar")
    parser.add_argument("--lib-path", default="/project/libs/adc_sar")
    parser.add_argument("--tech", default="tsmcN65")
    parser.add_argument("--layer", default="M1", help="该库里真实存在的层（实测 M1/OD/NW/text 可用）")
    parser.add_argument("--tag", default="")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    require_environment(base=args.base, token=args.token_a, require_lib=[args.tech])

    def call(operation: str, token: str, **fields) -> dict:
        payload = {"operation": operation, "token": token, **fields}
        request = urllib.request.Request(
            args.base, data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))

    def skill(token: str, code: str) -> str:
        data = (call("basic.skill.execute", token, skill_code=code).get("data") or {})
        output = (data.get("result") or {}).get("output")
        if output is None:
            steps = data.get("steps") or []
            output = ((steps[0].get("detail") or {}).get("output") if steps else "") or ""
        return str(output)

    token_a, token_b, lib = args.token_a, args.token_b, args.lib
    tag = args.tag or time.strftime("%H%M%S")
    cmp_cell, latch_cell, top_cell = f"cmp_{tag}", f"latch_{tag}", f"sar_top_{tag}"
    report: dict = {"library": lib, "tag": tag,
                    "cells": {"cmp": cmp_cell, "latch": latch_cell, "top": top_cell},
                    "steps": []}

    def record(name: str, ok: bool, detail) -> None:
        report["steps"].append({"step": name, "ok": bool(ok), "detail": detail})

    def create_view(token: str, cell: str, view: str) -> str:
        kind = "schematic" if view == "schematic" else "maskLayout"
        return skill(token,
                     f'let((cv) cv = dbOpenCellViewByType("{lib}" "{cell}" "{view}" '
                     f'"{kind}" "w") unless(cv error("create failed")) '
                     f'dbSave(cv) dbClose(cv) "created")').strip().strip('"')

    def instances_of(response: dict) -> list:
        value = ((_c1_wrapper(response)).get("value")) or {}
        return value.get("instances") or []

    # ---- 0) 前置：两个会话都能看到共享库 -------------------------------------
    for label, token in (("A", token_a), ("B", token_b)):
        seen = skill(token, f'let((x) x = ddGetObj("{lib}") if(x x sprintf(nil "MISSING")))').strip().strip('"')
        record(f"{label}-sees-library:{lib}", seen.startswith("dd:"), seen)
    if not report["steps"][-1]["ok"]:
        created = call("virtuoso.cellview.lib.create", token_a, library=lib,
                       path=args.lib_path, technology_library=args.tech)
        record("A-lib-create(fallback)", bool(created.get("ok")), created.get("error"))

    # 库必须挂上工艺库，否则版图侧会报 "Invalid layer/purpose"（实测：mkdir 出来的库没有 tech）。
    bound = call("virtuoso.cellview.lib.bind", token_a, library=lib,
                 technology_library=args.tech)
    record("A-lib-bind-tech", bool(bound.get("ok"))
           or "already" in str(bound.get("error", "")).lower()
           or "bound" in str(bound.get("error", "")).lower(),
           {"ok": bound.get("ok"), "error": bound.get("error")})

    # ---- 1) 三个 schematic 视图 + 内容 --------------------------------------
    for cell in (cmp_cell, latch_cell, top_cell):
        state = create_view(token_a, cell, "schematic")
        record(f"A-create-view:{cell}", state == "created", state)

    cmp_cmds = [
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "nch_25",
         "name": "MN1", "pos": [0.0, 0.0]},
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "nch_25",
         "name": "MN2", "pos": [2.0, 0.0]},
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "pch_25",
         "name": "MP1", "pos": [0.0, 2.0]},
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "pch_25",
         "name": "MP2", "pos": [2.0, 2.0]},
        {"op": "place_pin", "name": "INP", "direction": "input", "pos": [-2.0, 1.5]},
        {"op": "place_pin", "name": "INN", "direction": "input", "pos": [-2.0, 0.5]},
        {"op": "place_pin", "name": "OUT", "direction": "output", "pos": [4.5, 1.0]},
        {"op": "place_pin", "name": "VDD", "direction": "inputOutput", "pos": [1.0, 4.0]},
        {"op": "place_pin", "name": "VSS", "direction": "inputOutput", "pos": [1.0, -2.0]},
    ]
    lap_cmds = [
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "nch_25",
         "name": "MT1", "pos": [0.0, 0.0]},
        {"op": "place_instance", "master_lib": args.tech, "master_cell": "nch_25",
         "name": "MT2", "pos": [2.0, 0.0]},
        {"op": "place_pin", "name": "IN", "direction": "input", "pos": [-2.0, 0.5]},
        {"op": "place_pin", "name": "CLK", "direction": "input", "pos": [1.0, -2.0]},
        {"op": "place_pin", "name": "OUT", "direction": "output", "pos": [4.0, 0.5]},
    ]
    for cell, cmds in ((cmp_cell, cmp_cmds), (latch_cell, lap_cmds)):
        response = call("virtuoso.schematic.write", token_a, library=lib, cell=cell, commands=cmds)
        record(f"A-write:{cell}", bool(response.get("ok")), response.get("error"))

    for cell, cmds in ((cmp_cell, cmp_cmds), (latch_cell, lap_cmds)):
        generated = call("virtuoso.symbol.generate", token_a, library=lib, cell=cell, overwrite=True)
        record(f"A-symbol:{cell}", bool(generated.get("ok")), generated.get("error"))
        # B3（C0）：symbol 端口与原理图引脚**直接比对**（不再只判 generate 的 ok）。
        expected = sorted(c["name"] for c in cmds if c.get("op") == "place_pin")
        read = call("virtuoso.symbol.read", token_a, library=lib, cell=cell, view="symbol")
        value = (_c1_wrapper(read)).get("value") or {}
        terms = sorted(t.get("name") for t in (value.get("terms") or []) if t.get("name"))
        record(f"A-symbol-terms:{cell}", terms == expected,
               {"expected": expected, "terms": terms})

    top_cmds = [
        {"op": "place_instance", "master_lib": lib, "master_cell": cmp_cell,
         "name": "XI_CMP", "pos": [0.0, 0.0]},
        {"op": "place_instance", "master_lib": lib, "master_cell": latch_cell,
         "name": "XI_LATCH", "pos": [8.0, 0.0]},
        {"op": "place_pin", "name": "INP", "direction": "input", "pos": [-4.0, 1.0]},
        {"op": "place_pin", "name": "INN", "direction": "input", "pos": [-4.0, -1.0]},
        {"op": "place_pin", "name": "CLK", "direction": "input", "pos": [4.0, -4.0]},
        {"op": "place_pin", "name": "OUT", "direction": "output", "pos": [12.0, 0.0]},
        {"op": "place_pin", "name": "VDD", "direction": "inputOutput", "pos": [4.0, 4.0]},
        {"op": "place_pin", "name": "VSS", "direction": "inputOutput", "pos": [4.0, -6.0]},
    ]
    top = call("virtuoso.schematic.write", token_a, library=lib, cell=top_cell, commands=top_cmds)
    record("A-write:sar_top", bool(top.get("ok")), top.get("error"))

    # ---- 2) 版图：A 给顶层画 M1 版图 ----------------------------------------
    state = create_view(token_a, top_cell, "layout")
    record(f"A-create-view:{top_cell}/layout", state == "created", state)
    layout_cmds = [
        {"op": "place_rect", "layer": args.layer, "purpose": "drawing", "bbox": [[0, 0], [6, 4]]},
        {"op": "place_rect", "layer": args.layer, "purpose": "drawing", "bbox": [[8, 0], [14, 4]]},
        {"op": "place_path", "layer": args.layer, "purpose": "drawing",
         "points": [[6, 2], [8, 2]], "width": 0.2},
        {"op": "place_label", "layer": "text", "purpose": "drawing",
         "text": f"SAR-{tag}", "pos": [0, 5]},
    ]
    layout = call("virtuoso.layout.write", token_a, library=lib, cell=top_cell,
                  view="layout", commands=layout_cmds)
    record("A-write:layout", bool(layout.get("ok")), layout.get("error"))
    read_layout = call("virtuoso.layout.read", token_a, library=lib, cell=top_cell, view="layout")
    shape_count = (((_c1_wrapper(read_layout)).get("value")) or {}).get("shape_count")
    record("A-read:layout shapes>=4", bool(read_layout.get("ok")) and (shape_count or 0) >= 4,
           {"ok": read_layout.get("ok"), "shape_count": shape_count,
            "error": read_layout.get("error")})

    # ---- 3) GDS 导出到"还不存在"的目录（P-051 回归）--------------------------
    gds_path = f"{args.lib_path}/export/{tag}/{top_cell}.gds"
    gds = call("virtuoso.layout.gds", token_a, action="export", library=lib, cell=top_cell,
               view="layout", file_path=gds_path, file_is_local=False, top_cell=top_cell,
               tech_lib=args.tech, layer_map=f"{PDK}/{args.tech}/{args.tech}.layermap",
               layer_map_is_local=False)
    record("A-gds-export(new dir)", bool(gds.get("ok")), gds.get("error"))
    listing = call("basic.command.run", token_a, cmd=f"ls -l {gds_path}")
    record("A-gds-on-disk", ".gds" in json.dumps(listing, ensure_ascii=False),
           json.dumps(_c1_wrapper(listing), ensure_ascii=False)[:200])

    # ---- 4) B 跨用户回读 schematic + layout ---------------------------------
    b_read = call("virtuoso.schematic.read", token_b, library=lib, cell=top_cell)
    record("B-read:A's sar_top", bool(b_read.get("ok")) and len(instances_of(b_read)) >= 2,
           {"names": [item.get("name") for item in instances_of(b_read)],
            "error": b_read.get("error")})
    b_layout = call("virtuoso.layout.read", token_b, library=lib, cell=top_cell, view="layout")
    b_shapes = (((_c1_wrapper(b_layout)).get("value")) or {}).get("shape_count")
    record("B-read:A's layout", bool(b_layout.get("ok")) and (b_shapes or 0) >= 4,
           {"shape_count": b_shapes, "error": b_layout.get("error")})

    # ---- 5) B 改单 + A 回读 + check_and_save + 环境点检 ----------------------
    b_write = call("virtuoso.schematic.write", token_b, library=lib, cell=top_cell,
                   commands=[{"op": "place_instance", "master_lib": lib,
                              "master_cell": latch_cell, "name": "XI_LATCH2",
                              "pos": [8.0, -8.0]}])
    record("B-modify:A's sar_top", bool(b_write.get("ok")), b_write.get("error"))
    a_again = call("virtuoso.schematic.read", token_a, library=lib, cell=top_cell)
    names = [item.get("name") for item in instances_of(a_again)]
    # 失败时把**原始响应**也记进证据（第七轮教训：只记 names 看不出是"读超时"还是"真空"）
    record("A-see:B's instance", "XI_LATCH2" in names,
           {"names": names, "read_ok": bool(a_again.get("ok")),
            "read_error": a_again.get("error")})
    saved = call("virtuoso.schematic.check_and_save", token_b, library=lib, cell=top_cell)
    record("B-check_and_save:sar_top", bool(saved.get("ok")), saved.get("error"))
    license_check = call("spectre.check_license", token_a)
    record("env:spectre-license", bool(license_check.get("ok")), license_check.get("error"))

    report["passed"] = sum(1 for step in report["steps"] if step["ok"])
    report["total"] = len(report["steps"])
    report["ok"] = all(step["ok"] for step in report["steps"])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
