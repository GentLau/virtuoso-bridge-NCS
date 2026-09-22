"""Run every e2e suite against the business server and record evidence.

Exit code 0 only if every suite passes. Outputs are written to
``test/tb/artifacts/http-e2e/<suite>.log`` and a machine-readable
``results.json`` summary.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "test" / "tb" / "artifacts" / "http-e2e"
OUT.mkdir(parents=True, exist_ok=True)

SUITES = [
    "infra_e2e_tests.py",
    "cellview_e2e_tests.py",
    "schematic_e2e_tests.py",
    "symbol_e2e_tests.py",
    "layout_e2e_tests.py",
    "verilog_e2e_tests.py",
    "veriloga_e2e_tests.py",
    "skillref_e2e_tests.py",
    "spectre_e2e_tests.py",
    "maestro_e2e_tests.py",
]


def main() -> int:
    results: list[dict] = []
    overall_ok = True
    for suite in SUITES:
        log_path = OUT / f"{suite}.log"
        print(f"=== {suite} ===", flush=True)
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "test" / "tb" / suite),
                 "--transport", "http"],
                cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                timeout=3600,
            )
        ok = proc.returncode == 0
        overall_ok = overall_ok and ok
        results.append({
            "suite": suite,
            "ok": ok,
            "returncode": proc.returncode,
            "log": str(log_path),
        })
        print(f"    {'PASS' if ok else 'FAIL'} (rc={proc.returncode})", flush=True)
    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "all_passed": overall_ok,
        "suites": results,
    }
    (OUT / "results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
