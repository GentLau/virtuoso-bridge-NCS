"""round9 · 主覆盖率"口径诚实性"核对（只读）。

第八轮的教训：部分口径产物（append/增量）**不得**当作全量覆盖率引用。
本脚本在 `run_main_coverage.ps1` 跑完后核对：

1. 日志尾部是否为 `全部步骤通过`（否则列出 `失败步骤:` 列表）——有失败步骤的 run 其数字不可作为主口径；
2. `cov-main/run-meta.json` 的 `head` 是否等于当前 HEAD、`dirty` 是否为真（脏工作区的数字必须标注）；
3. `coverage-main-strict.json` 的 mtime 是否晚于日志开始（防止引用到上一轮的旧 JSON）；
4. 与"跑前快照"逐文件对比：新增/消失模块（消失的模块若含 `stress_server` 属预期；新模块要能解释）；
5. 打出 strict 的 totals（行/分支）与总文件数，供报告直接引用。

用法：`python test/reports/round9/verify_coverage_r9.py`
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
COV = ROOT / "test/artifacts/evidence/cov-main"
LOG = ROOT / "test/artifacts/evidence/round9/coverage-main-r9.log"
STRICT = COV / "coverage-main-strict.json"
META = COV / "run-meta.json"
BASELINE = ROOT / "test/artifacts/evidence/round9/coverage-pre-r9-strict.json"


def mtime(p: pathlib.Path) -> str:
    return (dt.datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
            if p.is_file() else "—")


def totals(doc: dict) -> dict:
    t = doc.get("totals") or {}
    return {k: t.get(k) for k in ("num_statements", "covered_lines", "missing_lines",
                                  "num_branches", "covered_branches", "missing_branches",
                                  "percent_covered", "percent_covered_display")}


def main() -> int:
    report: dict = {"log": str(LOG.relative_to(ROOT)), "strict": str(STRICT.relative_to(ROOT))}

    # 1) 日志尾部
    if LOG.is_file():
        text = LOG.read_text(encoding="utf-8", errors="replace")
        tail = text[-4000:]
        report["log_mtime"] = mtime(LOG)
        report["all_steps_passed"] = "全部步骤通过" in tail
        failed = re.findall(r"^  - (.+)$", tail, re.M)
        report["failed_steps"] = failed
        total_line = [l for l in tail.splitlines() if l.strip().startswith("TOTAL")]
        report["total_line"] = total_line[-1].strip() if total_line else ""
        report["first_step_time"] = (lambda m: m.group(1) if m else "")(
            re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2})", text[:400]))
    else:
        report["error"] = "日志不存在（覆盖率还没跑完？）"

    # 2) run-meta
    if META.is_file():
        meta = json.loads(META.read_text(encoding="utf-8"))
        head_now = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True,
                                  capture_output=True).stdout.strip()
        report["meta"] = {"head": meta.get("head"), "dirty": meta.get("dirty"),
                          "worktree_diff_sha": meta.get("worktree_diff_sha"),
                          "started_utc": meta.get("started_utc"),
                          "head_now": head_now,
                          "head_matches_now": meta.get("head") == head_now}
    else:
        report["meta"] = {"error": "run-meta.json 不存在"}

    # 3)(4)(5) strict JSON 与基线对比
    if STRICT.is_file():
        new = json.loads(STRICT.read_text(encoding="utf-8"))
        report["strict_mtime"] = mtime(STRICT)
        report["strict_totals"] = totals(new)
        new_files = set((new.get("files") or {}).keys())
        report["strict_file_count"] = len(new_files)
        if BASELINE.is_file():
            base = json.loads(BASELINE.read_text(encoding="utf-8"))
            base_files = set((base.get("files") or {}).keys())
            added = sorted(new_files - base_files)
            removed = sorted(base_files - new_files)
            report["baseline"] = {"path": BASELINE.name, "mtime": mtime(BASELINE),
                                  "totals": totals(base), "file_count": len(base_files),
                                  "added": added[:40], "added_count": len(added),
                                  "removed": removed[:40], "removed_count": len(removed),
                                  "stress_server_reappeared":
                                      any("stress_server" in f for f in added)}
            for key in ("num_statements", "covered_lines", "percent_covered"):
                a, b = report["strict_totals"].get(key), report["baseline"]["totals"].get(key)
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    report.setdefault("delta", {})[key] = round(a - b, 3)
    else:
        report["strict_error"] = "strict JSON 不存在"

    (OUT / "coverage-verify-r9.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=1)[:2500])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
