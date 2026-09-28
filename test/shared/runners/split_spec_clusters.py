"""把 spec 条款预映射按簇切片，供第八轮条款裁定子代理使用。

输出 `test/reports/round8/clusters/<簇>.json`（含 premap 命中的 TB 文件）。
用法::

    python test/shared/runners/split_spec_clusters.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "test" / "reports" / "round8"
CLUSTERS = {
    "C1-architecture": [
        "总览/1-四层整体架构与接口.md",
        "总览/add-本版范围与明确不支持.md",
        "顶层/1-顶层.md",
        "顶层/add-控制面与业务面.md",
        "中层/2-并发设计.md",
        "中层/3-路由设计.md",
        "中层/add-中层配置文档.md",
    ],
    "C2-registration-misc": [
        "其他/1-多用户与注册.md",
        "底层/6-日志返回设计标准.md",
        "上层/1-上层.md",
        "上层/5-cellview.md",
    ],
    "C3-sch-sym-lay": [
        "上层/2-schematic.md",
        "上层/3-symbol.md",
        "上层/4-layout.md",
    ],
    "C4-mae-spec-verilog": [
        "上层/6-maestro.md",
        "上层/7-spectre.md",
        "上层/8-verilog.md",
        "上层/11-veriloga.md",
    ],
    "C5-skillref-gui-calibre": [
        "上层/9-skillref.md",
        "上层/10-gui.md",
        "上层/12-calibre.md",
    ],
}


def main() -> int:
    rows = json.loads((OUT / "spec-clause-premap.json").read_text(encoding="utf-8"))
    out_dir = OUT / "clusters"
    out_dir.mkdir(parents=True, exist_ok=True)
    assigned = set()
    for name, docs in CLUSTERS.items():
        sub = [r for r in rows if r["doc"] in docs]
        assigned.update(r["id"] for r in sub)
        (out_dir / f"{name}.json").write_text(
            json.dumps(sub, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{name}: {len(sub)} rows -> {out_dir / (name + '.json')}")
    leftover = [r for r in rows if r["id"] not in assigned]
    if leftover:
        (out_dir / "unassigned.json").write_text(
            json.dumps(leftover, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"unassigned: {len(leftover)} rows")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
