"""round10 · 当前 spec 的 NORM 条款 vs 297 条覆盖矩阵：找"没进矩阵"的条款。

背景：`round8/round8-spec覆盖矩阵.json` 是 297 条 NORM 的逐条裁定；本轮重新抽取
当前 spec 得到 **328 条 NORM**（`round8/spec-clause-triage.json`）。条款 id 会随
spec 改动漂移 —— 必须先区分"只是换了编号"与"真·新条款"，否则"已逐条核对"站不住。

做法：
  * 归一化文本（去 markdown/空白）后按 **完全相同** 或 `difflib` 相似度 ≥0.90 匹配；
  * 匹配上的 = 编号漂移（覆盖结论沿用旧行）；
  * 没匹配上的 = 候选新条款 → 输出清单供人工裁定并补进矩阵。

用法：`python test/reports/round10/spec_clause_delta_r10.py`
"""
from __future__ import annotations

import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
TRIAGE = ROOT / "test" / "reports" / "round8" / "spec-clause-triage.json"
MATRIX = ROOT / "test" / "reports" / "round8" / "round8-spec覆盖矩阵.json"
OUT = Path(__file__).resolve().parent / "spec-clause-delta-r10"


def norm(text: str) -> str:
    text = re.sub(r"[`*_>|\-]", " ", text or "")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def main() -> int:
    triage = json.loads(TRIAGE.read_text(encoding="utf-8"))
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    norm_rows = [r for r in triage if r.get("category") == "NORM"]
    matrix_norm = {norm(r.get("text")): r for r in matrix if r.get("verdict")}
    keys = list(matrix_norm)

    matched, unmatched = [], []
    for row in norm_rows:
        text = norm(row.get("text"))
        if text in matrix_norm:
            matched.append((row, matrix_norm[text], 1.0))
            continue
        close = difflib.get_close_matches(text, keys, n=1, cutoff=0.90)
        if close:
            matched.append((row, matrix_norm[close[0]], round(
                difflib.SequenceMatcher(None, text, close[0]).ratio(), 3)))
        else:
            unmatched.append(row)

    payload = {
        "norm_total": len(norm_rows),
        "matrix_rows": len(matrix),
        "matched_renumbered": len(matched),
        "unmatched": [
            {"id": r.get("id"), "doc": r.get("doc"), "section": r.get("section"),
             "text": (r.get("text") or "")[:200]}
            for r in unmatched
        ],
    }
    OUT.with_suffix(".json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = [
        "# round10 · spec NORM 条款 vs 覆盖矩阵的差集（机器生成）",
        "",
        f"> 当前 spec NORM **{len(norm_rows)}** 条；矩阵 {len(matrix)} 行；"
        f"按文本匹配上（=编号漂移）**{len(matched)}**；**未匹配 {len(unmatched)}**（候选新条款）。",
        "",
        "## 未匹配清单（需逐条裁定后补进矩阵）",
        "",
    ]
    for r in unmatched:
        lines.append(f"- `{r.get('id')}`（{r.get('doc')} · {r.get('section')}）："
                     f"{(r.get('text') or '')[:120]}")
    lines += ["", "> 匹配口径：归一化后完全相同，或 difflib 相似度 ≥0.90。低于阈值的一律进未匹配清单（宁可人工多看一眼）。"]
    OUT.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"NORM={len(norm_rows)} matched={len(matched)} unmatched={len(unmatched)} -> {OUT.with_suffix('.json')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
