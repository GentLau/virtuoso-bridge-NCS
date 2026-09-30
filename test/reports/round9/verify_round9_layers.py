"""round9 · 三层结果汇总核对（门禁 + 半真机），产物写 round9。

输入：
  * `test/artifacts/evidence/http-e2e/results.json`（`run_all_http.py` 的门禁汇总）+ 各套 `.log`
  * `test/artifacts/evidence/semi-probes.json`（半真机整批）

输出：`round9-layers-summary.json` / `.md`（含"套件数是否等于 SUITES、逐套 rc/PASS/FAIL、
半真机 ok/failed 明细"），供主报告 §1 直接引用。

用法：`python test/reports/round9/verify_round9_layers.py`
"""
from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
ROOT = pathlib.Path(__file__).resolve().parents[3]
OUT = pathlib.Path(__file__).resolve().parent
GATE = ROOT / "test/artifacts/evidence/http-e2e"
SEMI = ROOT / "test/artifacts/evidence/semi-probes.json"


def expected_suites() -> list[str]:
    text = (ROOT / "test/shared/runners/run_all_http.py").read_text(encoding="utf-8")
    seen: list[str] = []
    for name in re.findall(r'^    "([a-z0-9_]+_e2e_tests\.py)"', text, re.M):
        if name not in seen:  # SUITE_ARGS 里会重复出现一次
            seen.append(name)
    return seen


def log_counts(path: pathlib.Path) -> dict:
    if not path.is_file():
        return {"pass": 0, "fail": 0, "missing": True}
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "pass": len(re.findall(r"^PASS|\[PASS\]", text, re.M)),
        "fail": len(re.findall(r"^FAIL|\[FAIL\]|ABORT", text, re.M)),
        "missing": False,
    }


def mtime(path: pathlib.Path) -> str:
    return (dt.datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="minutes")
            if path.is_file() else "—")


def main() -> int:
    expected = expected_suites()
    results: dict = {"generated": dt.datetime.now().isoformat(timespec="seconds"),
                     "expected_suites": expected}
    rj = GATE / "results.json"
    if rj.is_file():
        gate = json.loads(rj.read_text(encoding="utf-8"))
        rows = []
        for suite in gate.get("suites", []):
            counts = log_counts(GATE / f"{suite['suite']}.log")
            rows.append({**suite, **counts})
        results["gate"] = {
            "generated_at": gate.get("generated_at"),
            "all_passed": gate.get("all_passed"),
            "file_mtime": mtime(rj),
            "suite_count": len(rows),
            "expected_count": len(expected),
            "missing_from_results": [s for s in expected
                                     if s not in {r["suite"] for r in rows}],
            "extra_in_results": [r["suite"] for r in rows if r["suite"] not in expected],
            "suites": rows,
        }
    else:
        results["gate"] = {"error": "results.json 不存在"}

    if SEMI.is_file():
        semi = json.loads(SEMI.read_text(encoding="utf-8"))
        results["semi"] = {
            "file_mtime": mtime(SEMI),
            "group": semi.get("group"), "count": semi.get("count"),
            "ok": semi.get("ok"), "failed": semi.get("failed"),
        }
    else:
        results["semi"] = {"error": "semi-probes.json 不存在"}

    (OUT / "round9-layers-summary.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    lines = ["# round9 三层结果汇总（机器，B 线生成）", "",
             f"- 生成时间：{results['generated']}",
             f"- 半真机：`{results['semi']}`", ""]
    g = results["gate"]
    if "suites" in g:
        lines += [f"- 门禁（`run_all_http.py`）：file mtime {g['file_mtime']}，"
                  f"all_passed=**{g['all_passed']}**，套件 {g['suite_count']} / 期望 "
                  f"{g['expected_count']}，缺 {g['missing_from_results']}，多 {g['extra_in_results']}",
                  "", "| 套件 | rc | ok | PASS | FAIL |", "|---|---|---|---|---|"]
        for r in g["suites"]:
            lines.append(f"| {r['suite']} | {r['returncode']} | {r['ok']} | {r['pass']} | {r['fail']} |")
    else:
        lines.append(f"- 门禁：{g.get('error')}")
    (OUT / "round9-layers-summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: (v if k != "gate" else {kk: vv for kk, vv in v.items() if kk != "suites"})
                      for k, v in results.items()}, ensure_ascii=False, indent=1)[:1200])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
