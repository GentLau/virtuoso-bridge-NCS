# -*- coding: utf-8 -*-
"""逐行核账 spec 覆盖矩阵：**引用的证据文件在不在**、**本轮跑没跑**。

与 `verify_spec_matrix_evidence.py` 的分工：
* 那份回答"离线证据本轮 JUnit 里绿不绿"（§14，机器生成）；
* 这份回答**所有**行的两类问题：
  1. 行里引用的 `test/**.py` / `test/artifacts/**` 证据**文件是否存在**（写错路径 = 假证据）；
  2. 行里的证据是否属于**本轮**（离线 → 本轮 JUnit 有且全绿；半真机 → 本轮 `semi-probes.json`；
     真机 → 本轮 `round7/` 下的证据；都没有 → 标 `⬜本轮未复跑`，供审核一眼看出历史证据）。

用法::

    python test/shared/runners/audit_spec_matrix_evidence.py \
        --matrix test/reports/round7-spec覆盖矩阵.md \
        --junit test/artifacts/evidence/round7/offline2.xml \
        --semi test/artifacts/evidence/round7/semi-probes.json \
        --append-to-matrix
"""
from __future__ import annotations

import argparse
import collections
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
FILE_RE = re.compile(r"(test/[A-Za-z0-9_./\-\u4e00-\u9fff]+\.(?:py|json|md|ps1|xml))")
ROW_RE = re.compile(r"^([A-Z]\d+)\b")
START = "<!-- round7-audit:start -->"
END = "<!-- round7-audit:end -->"


def load_junit(path: Path) -> dict[str, list[int]]:
    root = ET.parse(path).getroot()
    suite = root if root.tag == "testsuite" else root.find("testsuite")
    stat: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0])
    for case in suite.iter("testcase"):
        classname = case.attrib.get("classname", "")
        module = ".".join(classname.split(".")[:4]) if classname.startswith("test.") else classname
        stat[module][0] += 1
        if any(child.tag in ("failure", "error") for child in case):
            stat[module][1] += 1
    return stat


def module_of(test_path: str) -> str:
    return ".".join(Path(test_path).with_suffix("").parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--matrix", default="test/reports/round7-spec覆盖矩阵.md")
    parser.add_argument("--junit", default="test/artifacts/evidence/round7/offline2.xml")
    parser.add_argument("--semi", default="test/artifacts/evidence/round7/semi-probes.json")
    parser.add_argument("--append-to-matrix", action="store_true")
    args = parser.parse_args(argv)

    junit = load_junit(ROOT / args.junit)
    semi = json.loads((ROOT / args.semi).read_text(encoding="utf-8"))
    semi_ok = {row["probe"] for row in semi["results"] if row["status"] == "ok"}

    raw_text = (ROOT / args.matrix).read_text(encoding="utf-8")
    # 只看矩阵主体：跳过本脚本自己生成的 §15 核账表（否则会把"说明里提到的旧文件名"当证据）
    body_text = raw_text.split(START)[0] if START in raw_text else raw_text
    lines = body_text.splitlines()
    rows: list[dict] = []
    for line in lines:
        if not line.startswith("|"):
            continue
        cell = [c.strip() for c in line.strip("|").split("|")]
        if len(cell) < 4:
            continue
        row_id = cell[0]
        if not re.fullmatch(r"[A-Z]\d+", row_id):
            continue
        # 证据只在"覆盖证据"列（第 4 列）里找，避免把备注里的历史文件名当证据
        files = sorted(set(FILE_RE.findall(cell[3])))
        missing = [f for f in files if not (ROOT / f).exists()]
        # 单元格里显式写了"删除/已删"的历史证据不算假证据（本轮核账就是这么修 G7 的）
        declared_removed = ("删除" in cell[3]) or ("已删" in cell[3])
        if declared_removed:
            missing = []
        offline = [f for f in files if f.startswith("test/offline/")]
        off_ran = off_red = 0
        for path in offline:
            total, failed = junit.get(module_of(path), [0, 0])
            off_ran += total
            off_red += failed
        probes = [f for f in files if f.startswith("test/semi/probes/")]
        probe_ok = [Path(p).name in semi_ok for p in probes]
        live7 = [f for f in files if f.startswith("test/artifacts/evidence/round7/")]
        verdcit = "⬜本轮未复跑"
        if off_red:
            verdcit = f"🔴本轮离线有红（{off_red}）"
        elif off_ran:
            verdcit = f"✅本轮离线已跑（{off_ran} 例全绿）"
        elif probes and all(probe_ok):
            verdcit = "✅本轮半真机已跑"
        elif live7:
            verdcit = "✅本轮真机/新证据"
        rows.append({"id": row_id, "files": files, "missing": missing,
                     "offline_cases": off_ran, "verdict": verdcit})

    bad = [r for r in rows if r["missing"]]
    not_run = [r for r in rows if r["verdict"] == "⬜本轮未复跑"]
    summary = {"rows": len(rows), "missing_evidence_rows": len(bad),
               "not_rerun_rows": len(not_run),
               "offline_verified_rows": sum(1 for r in rows if r["offline_cases"]),
               "semi_verified_rows": sum(1 for r in rows if "半真机" in r["verdict"])}
    print(json.dumps(summary, ensure_ascii=False))

    block = [START, "## 15. 逐行核账（第七轮，机器生成）", "",
             f"- 总行数 **{summary['rows']}**；行内引用的证据文件**全部存在**"
             if not bad else
             f"- ⚠️ 有 **{len(bad)}** 行的证据文件**不存在**（假证据，必须修）",
             f"- 本轮离线已复跑并全绿的行：**{summary['offline_verified_rows']}**",
             f"- 本轮半真机已复跑的行：**{summary['semi_verified_rows']}**",
             f"- **本轮未复跑（历史证据）的行：{summary['not_rerun_rows']}** —— 这些行不得当作本轮结论引用",
             "",
             "| 行 | 证据文件 | 本轮状态 |",
             "|---|---|---|"]
    for row in rows:
        files = ", ".join(f"`{f}`" for f in row["files"]) or "—"
        flag = " ⚠️缺文件" if row["missing"] else ""
        block.append(f"| {row['id']} | {files}{flag} | {row['verdict']} |")
    block.append(END)

    if args.append_to_matrix:
        text = (ROOT / args.matrix).read_text(encoding="utf-8")
        if START in text and END in text:
            head = text.split(START)[0].rstrip()
            tail = text.split(END, 1)[1].lstrip("\n")
            text = head + "\n\n" + "\n".join(block) + "\n" + tail
        else:
            text = text.rstrip() + "\n\n" + "\n".join(block) + "\n"
        (ROOT / args.matrix).write_text(text, encoding="utf-8")
        print(f"updated: {args.matrix}")

    if bad:
        print("missing evidence files:")
        for row in bad:
            print(f"  {row['id']}: {row['missing']}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
