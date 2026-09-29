# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 20:23
# 依赖: test/live/packages/layout_e2e_tests.py
# =======================================================================
"""版图 ``layout.read(depth>0)`` 探针（P-082）。

背景：`read()` 校验 `object_filter.*.region` 必须是**扁平** `[x0,y0,x1,y1]`
（`_filter_region`），但 depth>0 分支又调用 `_bbox(region)`（要求嵌套两点）
→ 任何 depth>0 请求都会在构造 SKILL 文本时抛
`ValueError: bbox must be [ [x, y], [x, y] ]`，属**确定性不可用**。

判据（真机）：
1. depth=0 与 depth=1 都不得出现 “bbox must be” 参数错误；
2. depth=1（下钻 master 实例）读回 shapes 数 **严格大于** depth=0（证明层级下钻语义）；
3. 交付 `test/artifacts/evidence/round8/layout-depth.json`。

用法::

    python test/semi/probes/layout_depth_probe.py --token vb-vblog
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

import design_iterate_tb as tb  # noqa: E402

LIB, CELL, VIEW = "schemtest", "lay_e2e", "layout"
LAYERS = [["y0", "drawing"], ["y1", "drawing"], ["y2", "drawing"],
          ["y3", "drawing"], ["text", "drawing"]]
OUT = ROOT / "test" / "artifacts" / "evidence" / "round8" / "layout-depth.json"


def call_depth(t: Any, depth: int) -> dict[str, Any]:
    payload = {
        "operation": "virtuoso.layout.read", "token": t.token,
        "library": LIB, "cell": CELL, "view": VIEW, "focus": ["shapes"],
        "detail": "index", "depth": depth,
        "object_filter": {"shape": {"layers": LAYERS,
                                    "region": [[0.0, 0.0], [60.0, 60.0]]},
                          "instance": "none", "via": "none"},
    }
    return t.call(payload)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default="vb-vblog")
    ap.add_argument("--base", default=tb.API)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    t = tb.HttpTransport(args.token, args.base)
    evidence: dict[str, Any] = {"lib": LIB, "cell": CELL, "view": VIEW}
    try:
        tb.op(t, "basic.command.run", cmd="echo env-ok", timeout=60)
    except tb.FlowError as exc:
        print(f"环境不可用: {exc.error}")
        return 2

    # 前置（P-085）：本用例读的是"层级下钻"，必须有 master 实例可下钻。
    # 夹具会被别的套件重建，所以这里自建：清 cell → 建 view → 顶层放一个实例。
    try:
        tb.op(t, "virtuoso.cellview.cell.delete", library=LIB, cell=CELL, timeout=120)
    except Exception:  # noqa: BLE001 - 不存在就算了
        pass
    tb.op(t, "virtuoso.cellview.view.create", library=LIB, cell=CELL, view=VIEW,
          view_type="maskLayout", timeout=180)
    tb.op(t, "virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW, timeout=300,
          commands=[
              {"op": "place_rect", "layer": "y0", "purpose": "drawing",
               "bbox": [[0, 0], [2, 1]]},
              {"op": "place_rect", "layer": "y1", "purpose": "drawing",
               "bbox": [[0, 2], [2, 3]]},
              {"op": "place_rect", "layer": "y2", "purpose": "drawing",
               "bbox": [[0, 4], [2, 5]]},
              {"op": "place_instance", "master_lib": LIB, "master_cell": "lay_master",
               "master_view": VIEW, "name": "P085_I1", "pos": [3.0, 3.0],
               "orient": "R0"},
          ])
    evidence["setup"] = "rebuilt cell with 3 rects + 1 master instance"

    flat = call_depth(t, 0)
    deep = call_depth(t, 1)
    evidence["depth0"] = flat
    evidence["depth1"] = deep
    flat_shapes = ((flat.get("data") or {}).get("value") or {}).get("shapes") or []
    deep_shapes = ((deep.get("data") or {}).get("value") or {}).get("shapes") or []
    evidence["depth0_count"] = len(flat_shapes)
    evidence["depth1_count"] = len(deep_shapes)
    evidence["depth0_error"] = flat.get("error")
    evidence["depth1_error"] = deep.get("error")

    problems: list[str] = []
    if "bbox must be" in str(flat.get("error") or ""):
        problems.append(f"depth=0 bbox 参数错误: {flat.get('error')}")
    if "bbox must be" in str(deep.get("error") or ""):
        problems.append(f"depth=1 bbox 参数错误: {deep.get('error')}")
    if not deep.get("ok"):
        problems.append(f"depth=1 失败: {deep.get('error')}")
    elif len(deep_shapes) <= len(flat_shapes):
        problems.append(
            f"depth=1 未下钻: depth0={len(flat_shapes)} depth1={len(deep_shapes)}")
    evidence["verdict"] = "BUG" if problems else "OK"
    evidence["problems"] = problems

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1),
                        encoding="utf-8")
    print(f"depth0 shapes={len(flat_shapes)} ok={flat.get('ok')} err={flat.get('error')}")
    print(f"depth1 shapes={len(deep_shapes)} ok={deep.get('ok')} err={deep.get('error')}")
    for item in problems:
        print(f"BUG: {item}")
    print(f"evidence -> {args.out}")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
