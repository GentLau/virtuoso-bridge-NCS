"""把 spec 条款清单按「是否需要 TB 逐条给结论」分诊，生成第八轮逐条核对底稿。

输入：test/reports/round8/spec-clauses.json（extract_spec_clauses.py 产出）
      test/reports/round8/spec-clause-premap.json（premap_spec_clauses.py 产出，带 tokens/hits）
输出：test/reports/round8/spec-clause-triage.md / .json

分诊口径（三类）：
  - PROSE：定义/术语/目录/示意图/引用类，不需要 TB 逐条给结论；
  - OPS：操作/参数/字段/枚举表行 —— 由「操作×参数矩阵」+ 原子覆盖矩阵负责；
  - NORM：规范性条款（必须/不得/默认/超时/失败语义/顺序/上限…），每条都要落结论。

每条 NORM 带 premap 命中的候选 TB（供复核），但机器命中不等于覆盖。
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

PROSE_PAT = re.compile(
    r"^(>?\s*(状态|版本|日期|维护|作者|读者|目的|口径|说明|注意|备注|参见|见\s)|"
    r"\s*[|│┌└├─]|"
    r".*本文不复制.*|.*唯一 owner 是.*$|.*见\s*§.*$|"
    r"^#+ )"
)

OPS_HDR_PAT = re.compile(
    r"操作|参数|字段|枚举|错误|返回|类型|默认|值|含义|说明|接口|role|token|"
    r"`\w+(\.\w+)+`|kind|status|returncode|stdout|stderr|timeout"
)

NORM_PAT = re.compile(
    r"必须|不得|禁止|一律|应[该当]|不允许|只能|仅当|唯一|默认|超时|拒绝|失败|错误|原子|"
    r"顺序|上限|至少|最多|不再|覆盖|省略|返回|写入|落盘|校验|回滚|幂等|"
    r"串行|并行|预算|释放|重试|降级|冻结|固化|查重|隔离"
)


def classify(rec: dict) -> tuple[str, str]:
    text = (rec.get("text") or "").strip()
    if not text:
        return "PROSE", "空行"
    if rec.get("kind") == "table-row":
        if "术语" in (rec.get("section") or "") or text.startswith("| 术语"):
            return "PROSE", "术语表"
        if OPS_HDR_PAT.search(text):
            return "OPS", "表行：操作/参数/字段定义（由 op-param + 原子矩阵负责）"
        return "OPS", "表行"
    if PROSE_PAT.match(text):
        return "PROSE", "定义/引用/示意图"
    if NORM_PAT.search(text):
        return "NORM", "规范性表述"
    if len(text) < 12:
        return "PROSE", "过短，非条款"
    return "NORM", "未匹配关键词，需人工判定"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--clauses", default=str(ROOT / "test/reports/round8/spec-clauses.json"))
    ap.add_argument("--premap", default=str(ROOT / "test/reports/round8/spec-clause-premap.json"))
    ap.add_argument("--md", default=str(ROOT / "test/reports/round8/spec-clause-triage.md"))
    ap.add_argument("--json", default=str(ROOT / "test/reports/round8/spec-clause-triage.json"))
    args = ap.parse_args()

    clauses = json.loads(Path(args.clauses).read_text(encoding="utf-8"))
    premap = {}
    p = Path(args.premap)
    if p.exists():
        for rec in json.loads(p.read_text(encoding="utf-8")):
            premap[rec.get("id")] = rec

    rows = []
    for rec in clauses:
        cat, why = classify(rec)
        pm = premap.get(rec.get("id"), {})
        rows.append(
            {
                "id": rec.get("id"),
                "doc": rec.get("doc"),
                "line": rec.get("line"),
                "kind": rec.get("kind"),
                "section": rec.get("section"),
                "text": (rec.get("text") or "").strip(),
                "category": cat,
                "why": why,
                "tokens": pm.get("tokens") or [],
                "hits": pm.get("hits") or {},
                "premap_status": pm.get("status"),
                "verdict": "",
                "evidence": "",
            }
        )

    by_doc: dict[str, list[dict]] = {}
    for r in rows:
        by_doc.setdefault(r["doc"], []).append(r)
    counts = {"NORM": 0, "OPS": 0, "PROSE": 0}
    for r in rows:
        counts[r["category"]] += 1

    lines = [
        "# Spec 条款分诊（第八轮逐条核对底稿）",
        "",
        f"- 条款 {len(rows)}：NORM {counts['NORM']} / OPS {counts['OPS']} / PROSE {counts['PROSE']}",
        "- OPS 行由 op-param-matrix + atom-coverage 负责；PROSE 不需要逐条结论；**NORM 必须逐条落 verdict**。",
        "- hits 只是 premap 机器候选（token→命中文件数），**不等于覆盖**。",
        "",
    ]
    for doc in sorted(by_doc, key=lambda d: (-sum(1 for r in by_doc[d] if r["category"] == "NORM"), d)):
        rs = by_doc[doc]
        n_norm = sum(1 for r in rs if r["category"] == "NORM")
        lines.append(f"## {doc}（{len(rs)} 条：NORM {n_norm}）")
        lines.append("")
        lines.append("| 编号 | 行 | 类别 | 条款 | 候选命中 | verdict | evidence |")
        lines.append("|---|---:|---|---|---|---|---|")
        for r in rs:
            text = r["text"].replace("|", "\\|")
            if len(text) > 160:
                text = text[:160] + "…"
            hits = ", ".join(f"{k}x{v}" for k, v in list(r["hits"].items())[:6])
            lines.append(
                f"| {r['id']} | {r['line']} | {r['category']} | {text} | {hits} | {r['verdict']} | {r['evidence']} |"
            )
        lines.append("")

    Path(args.md).write_text("\n".join(lines), encoding="utf-8")
    Path(args.json).write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"分诊完成：NORM {counts['NORM']} / OPS {counts['OPS']} / PROSE {counts['PROSE']}")
    print(f"  -> {args.md}")
    print(f"  -> {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
