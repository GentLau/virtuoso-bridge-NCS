"""round9 · 逐条核"已关闭卡片"的依据在本轮是否仍成立（只读）。

输入：`test/reports/bugs/已关闭-近期.md`（表格：| ID | 事项 | 关闭依据（证据） |）
      `test/artifacts/evidence/round9/offline-windows-r9.xml`（本轮离线 JUnit）
      `test/artifacts/evidence/round9/core-multi-r9.json`（脚本式 core TB）

每条：抽出依据里引用的 `test/**.py` 与 `test/artifacts/**` 路径 →
  * 存在的判"文件在"；离线文件再看本轮 JUnit 有没有（有且无红 = R9-GREEN）；
  * 真机/半真机文件/产物看 mtime 是否本轮（≥ 2026-09-29 18:00）；
  * 抽不到路径的判 `NO-PATH-IN-EVIDENCE`（人工看）。

用法：`python test/reports/round9/closed_cards_evidence_r9.py`
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
CLOSED = ROOT / "test/reports/bugs/已关闭-近期.md"
JUNIT = ROOT / "test/artifacts/evidence/round9/offline-windows-r9.xml"
CORE = ROOT / "test/artifacts/evidence/round9/core-multi-r9.json"
CUTOFF = dt.datetime(2026, 9, 29, 18, 0)
#: 反引号里的"像文件"的 token（全路径 / 相对路径 / 裸文件名）
TOKEN_RE = re.compile(r"`([^`\s]+\.(?:py|json|txt|log|md|xml|rep))`")
FILE_EXT = ("py", "json", "txt", "log", "md", "xml", "rep")


def resolve_token(tok: str) -> str | None:
    """把 token 解析成仓库内真实存在的相对路径（找不到返回 None）。"""
    if tok.startswith("test/") and (ROOT / tok).is_file():
        return tok
    name = tok.split("/")[-1]
    if not name:
        return None
    if "/" not in tok:  # 裸文件名 → 在 test/ 下按文件名找
        hits = sorted(p for p in (ROOT / "test").rglob(name) if p.is_file())
    else:  # 相对产物路径（如 verify-fix-r9/x.txt）→ 在 test/artifacts 下按 basename 找
        hits = sorted(p for p in (ROOT / "test/artifacts").rglob(name) if p.is_file())
    if not hits:
        return None
    return hits[0].relative_to(ROOT).as_posix()


def junit_modules() -> dict[str, dict]:
    state: dict[str, dict] = {}
    if not JUNIT.is_file():
        return state
    for case in ET.parse(JUNIT).iter("testcase"):
        parts = (case.get("classname") or "").split(".")
        if parts and parts[-1][:1].isupper():
            parts = parts[:-1]
        entry = state.setdefault(".".join(parts), {"total": 0, "red": 0})
        entry["total"] += 1
        if case.find("failure") is not None or case.find("error") is not None:
            entry["red"] += 1
    return state


def tonight_logs_text() -> str:
    """今晚集中产物的全文（"这个名字今晚出现过"作为可复跑判据）。"""
    chunks: list[str] = []
    for pat in ("test/artifacts/package-e2e-r9-full/*.log",
                "test/artifacts/package-e2e-r9-full/*.json",
                "test/artifacts/evidence/round9/*"):
        for p in sorted(ROOT.glob(pat)):
            if p.is_file() and p.suffix.lower() in (".log", ".txt", ".json", ".xml", ".md"):
                try:
                    chunks.append(p.read_text(encoding="utf-8", errors="replace"))
                except OSError:
                    pass
    return "\n".join(chunks)


def main() -> int:
    rows = []
    for line in CLOSED.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| ") or line.startswith("| ID"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3:
            continue
        rows.append({"id": cells[0], "subject": cells[1][:120], "evidence_text": cells[2]})

    junit = junit_modules()
    logs_text = tonight_logs_text()
    core_ok = False
    if CORE.is_file():
        core_ok = bool(json.loads(CORE.read_text(encoding="utf-8")).get("ok"))

    counted = collections.Counter()
    out_rows = []
    for row in rows:
        tokens = sorted(set(TOKEN_RE.findall(row["evidence_text"])))
        paths = []
        unresolved = []
        for tok in tokens:
            hit = resolve_token(tok)
            (paths if hit else unresolved).append(hit or tok)
        resolved = []
        for p in paths:
            path = ROOT / p
            exists = path.is_file()
            mtime = (dt.datetime.fromtimestamp(path.stat().st_mtime)
                     if exists else None)
            round9 = bool(mtime and mtime >= CUTOFF)
            detail = {"path": p, "exists": exists, "round9": round9}
            if p.startswith("test/offline/") and p.endswith(".py"):
                module = p[:-3].replace("/", ".")
                st = junit.get(module)
                if st is None and core_ok and "/core/" in p:
                    st = {"total": 1, "red": 0}
                    detail["source"] = "core-multi-r9"
                if st:
                    detail.update({"in_junit": True, "red": st["red"]})
                else:
                    detail["in_junit"] = False
            resolved.append(detail)

        # 口径修正：本 worktree 几乎所有文件 mtime 都是"今天"，**mtime 不能当"本轮"判据**。
        # 可靠判据只有：① 离线证据进了今晚 JUnit（且无红）；② 名字出现在今晚集中日志里。
        if not tokens:
            status = "NO-PATH-IN-EVIDENCE"
        elif any(d.get("red") for d in resolved):
            status = "STILL-RED"
        elif any(d.get("in_junit") for d in resolved):
            status = "R9-OFFLINE-GREEN"
        elif any(d.get("path", "").split("/")[-1] in logs_text
                 for d in resolved if d.get("path")):
            status = "R9-IN-TONIGHT-LOGS"
        elif resolved and all(d["exists"] for d in resolved):
            status = "EVIDENCE-NOT-RERUN-TONIGHT"
        else:
            status = "PATH-NOT-FOUND"
        counted[status] += 1
        out_rows.append({**row, "paths": resolved, "status": status})

    doc = {"cards_total": len(out_rows), "status_counts": dict(counted), "rows": out_rows}
    (OUT / "closed-cards-evidence-r9.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    lines = ["# 已关闭卡片：依据在本轮是否仍成立（机器结论）", "",
             f"- 卡片 {len(out_rows)} 张；状态分布 {dict(counted)}", "",
             "| ID | 事项 | 状态 | 引用路径 |", "|---|---|---|---|"]
    for r in out_rows:
        paths = "; ".join(f"{d['path']}{'' if d['exists'] else '(缺)'}" for d in r["paths"])[:120]
        lines.append(f"| {r['id']} | {r['subject'][:40]} | {r['status']} | {paths or '—'} |")
    (OUT / "closed-cards-evidence-r9.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("卡片", len(out_rows), "状态", dict(counted))
    for r in out_rows:
        if r["status"] not in ("R9-OFFLINE-GREEN", "R9-IN-TONIGHT-LOGS"):
            print(f"   {r['status']:24s} {r['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
