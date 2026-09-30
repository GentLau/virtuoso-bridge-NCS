"""round9 · 把"只引 semi/live 证据"的 spec 条款对表到本轮产物（只读）。

输入：`test/reports/round8/round8-spec覆盖矩阵.json`（297 条）+
      `spec-matrix-r9-b.json`（B 线刚生成，带每行 r9_status）。

规则（保守，宁可判"无本轮证据"）：
  * `test/live/packages/<x>_e2e_tests.py` → `test/artifacts/package-e2e-r9-full/<x>.log`
    （本轮日志；含 FAIL 判红）或 `evidence/round9/` 下同名 rerun 日志；
  * `test/live/packages/*_e2e_tests.py`（通配）→ 由 19 套 HTTP 门禁承担，标 `GLOB-GATE`；
  * `test/semi/**` → `evidence/semi-probes.json` / `evidence/semi-logs/<file>.log`（本轮 mtime）；
  * 其它 live（flows/transport/stress/registration）→ 在 `test/artifacts` 里按 stem 找本轮文件；
  * `test/artifacts/**` → 文件存在 + mtime 是否本轮。

用法：`python test/reports/round9/spec_live_evidence_r9.py`
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
CUTOFF = dt.datetime(2026, 9, 29, 18, 0)  # 本轮晚间批起点
PACKAGE_LOGS = ROOT / "test/artifacts/package-e2e-r9-full"
ROUND9_EV = ROOT / "test/artifacts/evidence/round9"
SEMI_JSON = ROOT / "test/artifacts/evidence/semi-probes.json"


def _mtime(path: pathlib.Path) -> dt.datetime | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def _round9(path: pathlib.Path) -> bool:
    m = _mtime(path)
    return bool(m and m >= CUTOFF)


def resolve(ev: str) -> dict:
    """→ {"kind": ..., "evidence": ..., "round9": bool}"""
    name = ev.split("/")[-1]
    if "*" in name:
        return {"kind": "GLOB-GATE", "evidence": "19 套 HTTP 门禁（run_all_http）",
                "round9": None, "note": "通配路径需按门禁结果人工确认"}
    if ev.startswith("test/live/packages/") and name.endswith("_e2e_tests.py"):
        stem = name[: -len("_e2e_tests.py")]
        cands = [PACKAGE_LOGS / f"{stem}.log", ROUND9_EV / f"{stem}-r9.log",
                 ROUND9_EV / f"{stem}-r9b.log", ROUND9_EV / f"{stem}-r9-rerun.log",
                 ROUND9_EV / f"{stem}-r9-rerun2.log"]
        for c in cands:
            if c.is_file():
                text = c.read_text(encoding="utf-8", errors="replace")
                red = "FAIL" in text
                return {"kind": "LIVE-PKG", "evidence": c.relative_to(ROOT).as_posix(),
                        "round9": _round9(c), "red": red}
        return {"kind": "LIVE-PKG", "evidence": None, "round9": False,
                "note": "未找到本轮日志"}
    if ev.startswith("test/semi/"):
        cands = [SEMI_JSON, ROOT / "test/artifacts/evidence/semi-logs" / f"{name}.log"]
        for c in cands:
            if c.is_file():
                return {"kind": "SEMI", "evidence": c.relative_to(ROOT).as_posix(),
                        "round9": _round9(c)}
        return {"kind": "SEMI", "evidence": None, "round9": False}
    if ev.startswith("test/artifacts/"):
        p = ROOT / ev
        return {"kind": "ARTIFACT", "evidence": ev, "round9": _round9(p),
                "exists": p.is_file()}
    # 其它 live（flows / transport / stress / registration / e2e）
    stem = name[:-3] if name.endswith(".py") else name
    hits = [p for p in (ROOT / "test/artifacts").rglob("*")
            if p.is_file() and stem and stem in p.name]
    fresh = [p for p in hits if _round9(p)]
    if fresh:
        return {"kind": "LIVE-OTHER", "evidence": fresh[0].relative_to(ROOT).as_posix(),
                "round9": True}
    if hits:
        return {"kind": "LIVE-OTHER", "evidence": hits[0].relative_to(ROOT).as_posix(),
                "round9": False, "note": "只有旧产物"}
    return {"kind": "LIVE-OTHER", "evidence": None, "round9": False}


def main() -> int:
    matrix = json.loads((ROOT / "test/reports/round8/round8-spec覆盖矩阵.json")
                        .read_text(encoding="utf-8"))
    b = json.loads((OUT / "spec-matrix-r9-b.json").read_text(encoding="utf-8"))
    rows = []
    counts = collections.Counter()
    for row, b_row in zip(matrix, b["rows"]):
        if b_row["r9_status"] != "NO-OFFLINE-EVIDENCE":
            continue
        if row.get("verdict") == "na":
            continue  # na 行不要求证据，交给 spec_matrix_r9_audit 归类

        evidence = [str(e).split("::")[0] for e in (row.get("evidence") or [])]
        resolved = [resolve(e) for e in evidence]
        fresh = any(r.get("round9") for r in resolved)
        red = any(r.get("red") for r in resolved)
        status = ("R9-LIVE-RED" if red else
                  "R9-LIVE-FRESH" if fresh else
                  "R9-LIVE-GLOB" if all(r["kind"] == "GLOB-GATE" for r in resolved) else
                  "R9-LIVE-STALE")
        counts[status] += 1
        rows.append({"id": row.get("id"), "doc": row.get("doc"),
                     "verdict": row.get("verdict"), "status": status,
                     "evidence": evidence, "resolved": resolved,
                     "text": (row.get("text") or "")[:200]})
    doc = {"cutoff": CUTOFF.isoformat(timespec="minutes"),
           "rows_total": len(rows), "status_counts": dict(counts), "rows": rows}
    (OUT / "spec-live-evidence-r9.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = ["# 只引 semi/live 证据的条款 → 本轮产物对表（机器结论）", "",
             f"- 口径：本轮 = mtime ≥ {CUTOFF:%Y-%m-%d %H:%M}",
             f"- 条数 {len(rows)}；状态分布 {dict(counts)}", "",
             "| 条款 | verdict | 本轮状态 | 证据（解析后） |", "|---|---|---|---|"]
    for r in rows:
        ev = "; ".join(str(x.get("evidence")) for x in r["resolved"])[:110]
        lines.append(f"| `{r['id']}` | {r['verdict']} | {r['status']} | {ev} |")
    (OUT / "spec-live-evidence-r9.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("条数", len(rows), "状态", dict(counts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
