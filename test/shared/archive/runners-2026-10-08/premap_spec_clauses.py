"""给 spec 条款做**机器预映射**：条款里的 op / 字段 / 错误码在哪些 TB 里出现过。

输出（`test/reports/round8/`）：
* `spec-clause-premap.md`：逐条 → 命中 TB 文件（最多 6 个）+ 预判状态；
* `spec-clause-premap.json`：机读版，供覆盖矩阵与子代理复核。

预判口径（**保守**：命中只代表"有候选证据"，不等于覆盖）：
* `NONE`：条款里的关键 token 在任何 TB 里都没有出现 → 必须人工/子代理复核（大概率真缺口）；
* `WEAK`：只有 1 个 token 命中，或命中的 TB 与条款主题不同层；
* `CANDIDATE`：≥2 个 token 命中且含 op 名或错误码。

用法::

    python test/shared/runners/premap_spec_clauses.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "test" / "reports" / "round8"
TB_DIRS = ["test/offline", "test/semi", "test/live", "test/shared/fixtures",
           "test/shared/runners"]

OP_RE = re.compile(r"\b(?:basic|virtuoso|spectre|calibre)\.[a-z][a-z0-9_.]*")
BACKTICK_RE = re.compile(r"`([A-Za-z_][A-Za-z0-9_.:\-]{2,})`")
CODE_RE = re.compile(r"\b(?:VB|CMI|XSTRM|OSSHNL|VERILOGIN|STRM)[A-Z0-9-]{3,}\b")


def ops_corpus() -> set[str]:
    ops: set[str] = set()
    for path in (ROOT / "src" / "pyapi" / "packages").glob("*.py"):
        ops.update(OP_RE.findall(path.read_text(encoding="utf-8", errors="replace")))
    return ops


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    clauses = json.loads((OUT / "spec-clauses.json").read_text(encoding="utf-8"))
    ops = ops_corpus()

    files: dict[str, str] = {}
    for rel in TB_DIRS:
        for path in (ROOT / rel).rglob("*.py"):
            files[path.relative_to(ROOT).as_posix()] = path.read_text(
                encoding="utf-8", errors="replace")

    results = []
    for clause in clauses:
        text = clause["text"]
        tokens: set[str] = set()
        for op in ops:
            if op in text:
                tokens.add(op)
        tokens.update(t for t in BACKTICK_RE.findall(text) if len(t) >= 4)
        tokens.update(CODE_RE.findall(text))
        if not tokens:
            results.append({**clause, "tokens": [], "hits": {}, "status": "NO-TOKEN"})
            continue
        hits: dict[str, list[str]] = defaultdict(list)
        for token in sorted(tokens):
            for rel, body in files.items():
                if token in body:
                    hits[token].append(rel)
        flat = sorted({f for v in hits.values() for f in v})
        has_op_or_code = any(t in ops or CODE_RE.fullmatch(t) for t in hits)
        status = ("CANDIDATE" if len(hits) >= 2 and has_op_or_code
                  else "WEAK" if hits else "NONE")
        results.append({**clause, "tokens": sorted(tokens),
                        "hits": {k: v[:6] for k, v in hits.items()},
                        "files": flat[:6], "status": status})

    (OUT / "spec-clause-premap.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = ["# Spec 条款预映射（机器，**不是覆盖结论**）", "",
             "> 由 `test/shared/runners/premap_spec_clauses.py` 生成。`NONE/WEAK` 必须逐条人工/子代理复核；",
             "> `CANDIDATE` 只是找到候选证据文件，是否真覆盖要看该 TB 的判据。", ""]
    counts = defaultdict(int)
    for item in results:
        counts[item["status"]] += 1
    lines.append(f"- 条款总数 **{len(results)}**：CANDIDATE {counts['CANDIDATE']} / "
                 f"WEAK {counts['WEAK']} / NONE {counts['NONE']} / NO-TOKEN {counts['NO-TOKEN']}")
    lines.append("")
    for item in results:
        if item["status"] in ("CANDIDATE",):
            continue
        hit_preview = "；".join(f"`{k}`→{len(v)}" for k, v in list(item["hits"].items())[:5])
        lines.append(f"- **{item['id']}** [{item['status']}] {item['doc']}:{item['line']} — "
                     f"{item['text'][:150]}")
        if hit_preview:
            lines.append(f"  - 命中：{hit_preview}")
    (OUT / "spec-clause-premap.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"预映射完成：{dict(counts)}")
    print(f"  NONE/WEAK 明细 -> {OUT / 'spec-clause-premap.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
