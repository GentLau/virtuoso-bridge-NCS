"""Run every upper-package e2e suite against the business server and record evidence.

Exit code 0 only if every suite passes. Outputs are written to
``test/artifacts/evidence/http-e2e/<suite>.log`` and a machine-readable
``results.json`` summary.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT / "test" / "artifacts" / "evidence" / "http-e2e"
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
    # 第八轮新增：screenshot 参数面（window_id/region/toplevel/central_widget/view_type）
    "screenshot_params_e2e_tests.py",
    # P-060：calibre 进常驻套件（此前 0 真机覆盖）；依赖常驻注册表里的 role.command.calibre.bin
    "calibre_e2e_tests.py",
    # 第八轮新增参数面 TB（补齐 op×参数车道，C 轴）
    "calibre_params_e2e_tests.py",          # 6/6 绿（含 drc(runset=) 官方批处理）
    "verilog_import_params_e2e_tests.py",   # 预期红：IMP-07/08/10 = P-099/P-100/P-101 红钉
    "calibre_export_pex_e2e_tests.py",      # 预期红：PEX-FMT-01 = P-102/P-103 红钉
    "maestro_view_param_e2e_tests.py",      # 预期红：read 族缺失 view 负例 = P-104 红钉
    # maestro 放最后：P-086/P-095 的模态框会把 CIW 卡死，若排在前面会让后面的套件
    # （尤其 calibre 的 getWorkingDir/export_cdl）连带失败——2026-09-29 gate 实测。
    "maestro_e2e_tests.py",
]

#: 个别套件需要附加参数（其余一律只加 `--transport http`）。
#: screenshot_params 的 layout 档带 P-080 红钉（SC-06 bogus view_type），门禁里跑**无红钉的 schematic 档**；
#: layout/symbol 两档按报告 §3 的独立复跑为准（`--kind layout|symbol` 手动指定）。
SUITE_ARGS = {
    "screenshot_params_e2e_tests.py": [
        "--token", "vb-vbuser2", "--lib", "serdes_rx", "--cell", "rx_top",
        "--view", "schematic", "--kind", "schematic",
    ],
}


def main() -> int:
    results: list[dict] = []
    overall_ok = True
    for suite in SUITES:
        log_path = OUT / f"{suite}.log"
        print(f"=== {suite} ===", flush=True)
        with log_path.open("w", encoding="utf-8") as log:
            proc = subprocess.run(
                [sys.executable, str(ROOT / "test" / "live" / "packages" / suite),
                 "--transport", "http", *SUITE_ARGS.get(suite, [])],
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
