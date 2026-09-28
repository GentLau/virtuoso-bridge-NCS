"""把 Normative spec 的所有"可测条款"抽成带编号的清单（第八轮覆盖矩阵的输入）。

为什么：评审驳回点是"覆盖率虚高"——包级/能力域级口径掩盖了未测条款。
本工具把粒度下沉到**条款**：每份 normative 文档的标题、表格行、规范性句式
（必须/不得/只在/唯一/默认/枚举/超时/并发/拒绝/上限 …）逐条给编号，
供覆盖矩阵逐条标注「有 TB 证据 / 半覆盖 / 缺口」。

输出：`test/reports/round8/spec-clause-checklist.md`（人读）+ `.../spec-clauses.json`（机读）。

用法::

    python test/shared/runners/extract_spec_clauses.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "spec" / "design-concepts"
OUT_DIR = ROOT / "test" / "reports" / "round8"

#: Normative 文档（以 spec/README.md 的 owner 表为准）
NORMATIVE = [
    ("总览/1-四层整体架构与接口.md", "总览"),
    ("总览/add-本版范围与明确不支持.md", "范围"),
    ("中层/add-中层配置文档.md", "配置"),
    ("其他/1-多用户与注册.md", "注册"),
    ("中层/3-路由设计.md", "路由"),
    ("中层/2-并发设计.md", "并发"),
    ("底层/6-日志返回设计标准.md", "日志"),
    ("顶层/1-顶层.md", "顶层"),
    ("顶层/add-控制面与业务面.md", "控制面"),
    ("上层/1-上层.md", "上层"),
    ("上层/2-schematic.md", "schematic"),
    ("上层/3-symbol.md", "symbol"),
    ("上层/4-layout.md", "layout"),
    ("上层/5-cellview.md", "cellview"),
    ("上层/6-maestro.md", "maestro"),
    ("上层/7-spectre.md", "spectre"),
    ("上层/8-verilog.md", "verilog"),
    ("上层/9-skillref.md", "skillref"),
    ("上层/10-gui.md", "gui"),
    ("上层/11-veriloga.md", "veriloga"),
    ("上层/12-calibre.md", "calibre"),
]

KEYWORD_RE = re.compile(
    r"必须|不得|禁止|只能|只在|唯一|默认|一律|拒绝|错误|超时|上限|至少|不允许|"
    r"不能|应返回|应写|应落|枚举|顺序|并发|串行|幂等|原子|回滚"
)


def doc_id(path: str) -> str:
    return path.replace("/", ":")


def extract(path: Path, prefix: str) -> list[dict]:
    items: list[dict] = []
    section = ""
    counter = 0
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            section = line.lstrip("# ").strip()
            continue
        counter += 1
        cid = f"{prefix}#{counter:03d}"
        if line.startswith("|") and not re.match(r"^\|[\s:|-]+\|$", line):
            items.append({"id": cid, "kind": "table-row", "section": section,
                          "line": lineno, "text": line})
        elif KEYWORD_RE.search(line) and not line.startswith("```"):
            items.append({"id": cid, "kind": "clause", "section": section,
                          "line": lineno, "text": line})
    return items


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_items: list[dict] = []
    md = ["# Spec 条款清单（第八轮覆盖矩阵的输入，机器抽取）", "",
          "> 由 `test/shared/runners/extract_spec_clauses.py` 生成；每条都要在覆盖矩阵里给结论",
          "> （✅有 TB 直接证据 / 🟡间接或历史 / ⬜缺口）。`kind=table-row` 是操作/字段/枚举表行，",
          "> `kind=clause` 是规范性句式（必须/不得/默认/超时/并发…）。", ""]
    for rel, prefix in NORMATIVE:
        path = SPEC / rel
        if not path.exists():
            md.append(f"## {rel}\n\n> **文件不存在**（清单需修正）\n")
            continue
        items = extract(path, f"{prefix}")
        for item in items:
            item["doc"] = rel
        all_items.extend(items)
        md.append(f"## {rel}（{len(items)} 条）")
        md.append("")
        md.append("| 编号 | 类型 | 行 | 小节 | 条款 |")
        md.append("|---|---|---:|---|---|")
        for item in items:
            text = item["text"].replace("|", "\\|")
            md.append(f"| {item['id']} | {item['kind']} | {item['line']} | "
                      f"{item['section'][:28]} | {text[:220]} |")
        md.append("")
    (OUT_DIR / "spec-clause-checklist.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    (OUT_DIR / "spec-clauses.json").write_text(
        json.dumps(all_items, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"条款 {len(all_items)} 条 -> {OUT_DIR / 'spec-clause-checklist.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
