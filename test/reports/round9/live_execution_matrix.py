"""round9 · 真机 TB 执行矩阵（只读）。

回答三个问题（每个 live TB 一行）：
 1. 是否在 HTTP 门禁 `run_all_http.py` 的 SUITES 里；
 2. 是否有**任何**文件（runner / 计划 / 文档 / 别的 TB）引用它 —— 即"有没有人负责跑它"；
 3. `test/artifacts/` 下有没有**本轮（今天）**的产物/日志提到它的名字 —— 即"跑没跑过"的弱证据。

用法：`python test/reports/round9/live_execution_matrix.py`
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys
from collections import defaultdict

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
SKIP_DIRS = ("test/reports", "test/artifacts", "test/__pycache__")
TEXT_EXT = {".log", ".json", ".txt", ".md", ".xml", ".out", ".rep", ".rpt"}


def _excluded(rel: str) -> bool:
    """本轮不参与扫描的目录（避免与分析产物互相递归）。"""
    return any(rel.startswith(d) for d in SKIP_DIRS) or "__pycache__" in rel


def main() -> int:
    today = dt.date.today().isoformat()
    live = sorted(p for p in (ROOT / "test/live").rglob("*.py")
                  if p.is_file() and not p.name.startswith("_") and p.name != "__init__.py")
    gate = set(re.findall(r'"([a-z0-9_]+_e2e_tests\.py)"',
                          (ROOT / "test/shared/runners/run_all_http.py").read_text(encoding="utf-8")))

    corpus: dict[str, str] = {}
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix not in {".py", ".ps1", ".sh", ".md", ".json"}:
            continue
        rel = p.relative_to(ROOT).as_posix()
        if _excluded(rel):
            continue
        try:
            corpus[rel] = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

    artifacts: list[tuple[str, str, str]] = []  # (rel, text, mtime_date)
    for p in (ROOT / "test/artifacts").rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT).as_posix()
        size = p.stat().st_size
        if size > 3_000_000 or p.suffix.lower() not in TEXT_EXT:
            continue
        try:
            artifacts.append((rel, p.read_text(encoding="utf-8", errors="replace")[:200_000],
                              dt.date.fromtimestamp(p.stat().st_mtime).isoformat()))
        except OSError:
            continue

    rows = []
    for p in live:
        name = p.name
        rel = p.relative_to(ROOT).as_posix()
        refs = sorted(r for r, t in corpus.items() if name in t and r != rel)
        stems = {name, name.removesuffix(".py"),
                 re.sub(r"_(e2e_tests|tests|tb)\.py$", "", name)}
        ev_today, ev_any = [], []
        for art_rel, text, mtime_day in artifacts:
            hit = any(s and s in art_rel for s in stems) or name in text
            if not hit:
                continue
            ev_any.append(art_rel)
            if mtime_day == today:
                ev_today.append(art_rel)
        rows.append({
            "tb": rel, "in_gate": name in gate,
            "referenced_by": refs[:6], "ref_count": len(refs),
            "evidence_today": ev_today[:4], "evidence_any": ev_any[:4],
        })

    never_runner = [r for r in rows if not r["in_gate"] and r["ref_count"] == 0]
    no_evidence_today = [r for r in rows if not r["evidence_today"]]
    doc = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
           "live_tb_total": len(rows), "gate_suites": len(gate),
           "never_referenced": [r["tb"] for r in never_runner],
           "no_evidence_today": [r["tb"] for r in no_evidence_today],
           "rows": rows}
    (OUT / "live-execution-matrix.json").write_text(
        __import__("json").dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = ["# 真机 TB 执行矩阵（机器结论，脚本生成）", "",
             f"- live TB 总数 **{len(rows)}**；HTTP 门禁套件 **{len(gate)}**",
             f"- **既不在门禁、又没有任何文件引用** 的 TB：**{len(never_runner)}**",
             f"- 今天（{today}）在 `test/artifacts/` 里找不到证据的 TB：**{len(no_evidence_today)}**",
             "", "| TB | 门禁 | 被引用数 | 今日证据 |", "|---|---|---|---|"]
    for r in rows:
        lines.append(f"| `{r['tb']}` | {'✅' if r['in_gate'] else '—'} | {r['ref_count']} | "
                     f"{'✅' if r['evidence_today'] else '—'} |")
    (OUT / "live-execution-matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"live TB {len(rows)}；门禁 {len(gate)}；无人引用 {len(never_runner)}；今日无证据 {len(no_evidence_today)}")
    print("never_referenced:", *never_runner, sep="\n  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
