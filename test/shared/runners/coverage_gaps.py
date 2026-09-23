"""Coverage gap reporter: turn a coverage.py JSON report into an actionable list.

Usage:
    python test/shared/runners/coverage_gaps.py <coverage.json> [-o out.md] [--min-miss 1]

Emits, per file: missing line ranges (grouped), missing branch count, and a
priority hint (missing lines x file weight). Pure stdlib, no pytest needed.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def _ranges(lines: list[int]) -> list[str]:
    lines = sorted(set(int(v) for v in lines))
    out: list[str] = []
    start = prev = None
    for ln in lines:
        if start is None:
            start = prev = ln
            continue
        if ln == prev + 1:
            prev = ln
            continue
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
        start = prev = ln
    if start is not None:
        out.append(f"{start}" if start == prev else f"{start}-{prev}")
    return out


def build_report(data: dict, min_miss: int = 1) -> str:
    totals = data.get("totals", {})
    # coverage.py 的 JSON totals 里没有现成的"纯行/纯分支百分比"字段：
    # percent_covered 是行+分支合并后的值，percent_covered_branches 也常常缺失。
    # 这里自己按定义算，避免报告里出现 0.00% 这种误导数字。
    stmts = totals.get("num_statements") or 0
    miss_lines = totals.get("missing_lines") or 0
    branches = totals.get("num_branches") or 0
    miss_branches = totals.get("missing_branches") or 0
    line_pct = (stmts - miss_lines) / stmts * 100 if stmts else 0.0
    branch_pct = (branches - miss_branches) / branches * 100 if branches else None
    rows = []
    for name, info in data.get("files", {}).items():
        s = info.get("summary", {})
        miss = s.get("missing_lines", 0)
        if miss < min_miss:
            continue
        rows.append((miss, name, info, s))
    rows.sort(key=lambda r: -r[0])

    lines: list[str] = []
    lines.append("# Coverage gaps (generated)")
    lines.append("")
    lines.append(
        f"TOTAL statements={stmts} missing={miss_lines} line={line_pct:.2f}% "
        f"branches={branches} missing_branches={miss_branches} "
        + (f"branch={branch_pct:.2f}%" if branch_pct is not None else "branch=n/a")
        + f" combined={totals.get('percent_covered', 0):.2f}%"
    )
    lines.append("")
    lines.append(f"files with >= {min_miss} missing lines: {len(rows)}")
    lines.append("")
    lines.append("| miss | stmts | cover | file | line ranges | branches missing |")
    lines.append("|---:|---:|---:|---|---|---:|")
    for miss, name, info, s in rows:
        rel = name.replace("\\", "/")
        rng = ", ".join(_ranges(info.get("missing_lines", []))[:14])
        if len(_ranges(info.get("missing_lines", []))) > 14:
            rng += ", ..."
        nmiss_b = len(info.get("missing_branches", []) or [])
        lines.append(
            f"| {miss} | {s.get('num_statements')} | {s.get('percent_covered', 0):.1f}% "
            f"| `{rel}` | {rng} | {nmiss_b} |"
        )
    lines.append("")
    lines.append("## Detail")
    lines.append("")
    for miss, name, info, s in rows:
        rel = name.replace("\\", "/")
        lines.append(f"### {rel} ({miss} miss / {s.get('num_statements')} stmts)")
        lines.append("")
        lines.append("missing: `" + ", ".join(_ranges(info.get("missing_lines", []))) + "`")
        mb = info.get("missing_branches", []) or []
        if mb:
            lines.append("")
            lines.append("missing branches: `" + ", ".join(f"{a}->{b}" for a, b in mb) + "`")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("json_path", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--min-miss", type=int, default=1)
    args = ap.parse_args(argv)

    data = json.loads(args.json_path.read_text(encoding="utf-8"))
    report = build_report(data, args.min_miss)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(report, encoding="utf-8")
        print(f"wrote {args.out} ({len(report)} bytes)")
    else:
        sys.stdout.write(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
