"""把六个 norm-review 组（297 条 NORM）合并为第八轮 spec 覆盖矩阵。

输出：
  test/reports/round8/round8-spec覆盖矩阵.md
  test/reports/round8/round8-spec覆盖矩阵.json
  test/reports/round8/round8-gap-actions.md（partial → 待补测试清单）

校验（不通过即 rc=1）：
  * 每条都有 verdict ∈ {direct, indirect, partial, gap, na}；
  * direct/indirect/partial 必须有 evidence；na 必须有 reason；
  * partial/gap 必须有 gap_test；
  * evidence 里引用的**文件路径**必须存在（`::` 后缀忽略）。
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[3]
REVIEW = ROOT / "test" / "reports" / "round8" / "norm-review"
OUT = ROOT / "test" / "reports" / "round8"
GROUPS = ["g1-core", "g2-mid", "g3-reg", "g4-edit", "g5-sim", "g6-calibre"]
VALID = {"direct", "indirect", "partial", "gap", "na"}


def check_evidence_path(token: str) -> str | None:
    """返回缺失路径（None = OK）。允许 `path::test`、`path (说明)` 形态。"""
    raw = token.split("::", 1)[0].strip().rstrip("）)")
    raw = raw.split(" ", 1)[0]
    if not raw or raw.startswith("src/") or raw.startswith("test/artifacts/"):
        # 源码锚点/证据产物不强制存在（artifacts 为运行产物）
        return None
    if raw.startswith("test/"):
        path = ROOT / raw
        if path.exists():
            return None
        if "*" in raw:
            if list(ROOT.glob(raw)):
                return None
        return raw
    return None


def main() -> int:
    rows: list[dict] = []
    group_rows: dict[str, list[dict]] = {}
    for g in GROUPS:
        sub = json.loads((REVIEW / f"{g}.json").read_text(encoding="utf-8"))
        group_rows[g] = sub
        rows.extend(sub)

    problems: list[str] = []
    for r in rows:
        vid = r["id"]
        v = r.get("verdict") or ""
        if v not in VALID:
            problems.append(f"{vid}: verdict 缺失/非法 {v!r}")
            continue
        if v in ("direct", "indirect", "partial") and not r.get("evidence"):
            problems.append(f"{vid}: {v} 但无 evidence")
        if v == "na" and not r.get("reason"):
            problems.append(f"{vid}: na 但无 reason")
        if v in ("partial", "gap") and not r.get("gap_test"):
            problems.append(f"{vid}: {v} 但无 gap_test")
        for token in r.get("evidence") or []:
            missing = check_evidence_path(token)
            if missing:
                problems.append(f"{vid}: evidence 路径不存在 {missing}")

    counts = Counter(r.get("verdict") for r in rows)
    by_doc: dict[str, Counter] = defaultdict(Counter)
    for r in rows:
        by_doc[r["doc"]][r["verdict"]] += 1

    (OUT / "round8-spec覆盖矩阵.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = [
        "# 第八轮 · Spec 条款覆盖矩阵（NORM 297 条逐条裁定）",
        "",
        f"> 生成：`test/shared/runners/merge_round8_spec_matrix.py` ｜ 基线：HEAD=64c803c（工作区被测）",
        f"> 统计：direct {counts['direct']} / indirect {counts['indirect']} / partial {counts['partial']} / "
        f"gap {counts['gap']} / na {counts['na']}（共 {len(rows)}）",
        "",
        "判定口径：",
        "- **direct**：有直接判据（读回/数值/字节/结构化断言）；**indirect**：由下游消费间接体现；",
        "- **partial**：条款的部分子句无证据（`gap_test` 写明补什么）；**gap**：完全无 TB 证据（本轮为 0）；",
        "- **na**：定义/指针/实现自由度/明确不做/已知限制，均给出理由。",
        "- 全量分诊口径（含 OPS/PROSE）：`spec-clause-triage.md`；OPS 793 条由 op×param 矩阵 + 原子矩阵承担。",
        "",
        "## 分组统计",
        "",
        "| 组 | 条数 | direct | indirect | partial | gap | na |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for g in GROUPS:
        sub = group_rows[g]
        c = Counter(r.get("verdict") for r in sub)
        lines.append(f"| {g} | {len(sub)} | {c['direct']} | {c['indirect']} | {c['partial']} | {c['gap']} | {c['na']} |")
    lines += [
        "",
        "## 逐条矩阵",
        "",
        "| 编号 | 文档 | verdict | 说明 | 证据 |",
        "|---|---|---|---|---|",
    ]
    for r in rows:
        text = (r.get("reason") or "").replace("|", "\\|")[:150]
        ev = "<br>".join(r.get("evidence") or [])[:220]
        gap = r.get("gap_test") or ""
        if gap:
            text += " ｜ **缺口**: " + gap.replace("|", "\\|")[:150]
        lines.append(f"| {r['id']} | {r['doc']} | **{r['verdict']}** | {text} | {ev} |")
    (OUT / "round8-spec覆盖矩阵.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # gap actions
    acts = [r for r in rows if r.get("gap_test")]
    act_lines = ["# 第八轮条款缺口动作（partial → 待补测试）", "",
                 f"> 共 {len(acts)} 条；完成后把对应行的 verdict 提升并回填证据。", ""]
    for r in acts:
        act_lines += [f"## {r['id']}（{r['doc']}）", "",
                      f"- 条款：{r['text'][:160]}",
                      f"- 现状：{r.get('reason')}",
                      f"- 待补：{r.get('gap_test')}", ""]
    (OUT / "round8-gap-actions.md").write_text("\n".join(act_lines) + "\n", encoding="utf-8")

    print(f"merged {len(rows)} rows: {dict(counts)}")
    print(f"gap actions: {len(acts)}")
    if problems:
        print(f"VALIDATION PROBLEMS ({len(problems)}):")
        for p in problems[:40]:
            print("  -", p)
        return 1
    print("validation OK（verdict/证据路径/缺口动作齐全）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
