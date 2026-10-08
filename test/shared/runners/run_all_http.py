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
    # round9 接线：CDSlog 请求字段真机面（LOG-01..07：注册表默认/off/all/warn/§5 降级/领域操作/并发归属）。
    # 此前只有人工跑（证据 test/artifacts/evidence/round9/skill-log-options-r9.json），门禁里没有 → 回归无人拦。
    # 位置靠前：LOG-06 读 `maestro_tb/rc_probe` 配置，必须在改动 maestro 夹具的套件之前跑。
    "skill_log_options_e2e_tests.py",
    "cellview_e2e_tests.py",
    "schematic_e2e_tests.py",
    "symbol_e2e_tests.py",
    "layout_e2e_tests.py",
    "verilog_e2e_tests.py",
    "veriloga_e2e_tests.py",
    "skillref_e2e_tests.py",
    "spectre_e2e_tests.py",
    # round9 新增：PVT（process tt/ss/ff · 电压 2.5/2.25V · 温度 27/125/-40℃）真机扫描，
    # 逐节点 DC 工作点值级判据；此前全套 TB 只有 corner 配置面，没有真正跑过 PVT（~25s，6 网表）。
    "spectre_pvt_e2e_tests.py",
    # round9 新增：`spectre.run.mode` 7 个取值的真机覆盖（cx/ax/mx/lx/vx 此前只有离线拼装断言）；
    # P-108 决策删除 `mode="x"`，TB 改为负例钉住请求校验拒绝。
    "spectre_modes_e2e_tests.py",
    # 第八轮新增：screenshot 参数面（window_id/region/toplevel/central_widget/view_type）
    "screenshot_params_e2e_tests.py",
    # P-060：calibre 进常驻套件（此前 0 真机覆盖）；依赖常驻注册表里的 role.command.calibre.bin
    "calibre_e2e_tests.py",
    # 第八轮新增参数面 TB（补齐 op×参数车道，C 轴）
    "calibre_params_e2e_tests.py",          # 6/6 绿（含 drc(runset=) 官方批处理）
    "verilog_import_params_e2e_tests.py",   # P-099/P-100/P-101 回归
    "calibre_export_pex_e2e_tests.py",      # P-102/P-103 已按“PEX 本版不提供”收口
    "maestro_view_param_e2e_tests.py",      # P-104 回归
    # round9 新增：嵌套键真机面（此前只有离线 L0 契约）
    "nested_keys_e2e_tests.py",             # symbol/schematic 9 键值级读回（含 C10 惰性参数钉）
    "maestro_nested_keys_e2e_tests.py",     # maestro 11 键（type_name/type_value、spec_name 值级）
    # round9 接线：三个此前"没有任何 runner 引用"的真机 TB（见 round9/live-execution-gaps.md）
    "step_details_e2e_tests.py",            # C1 契约：成功省略 steps / 失败保留 steps
    "layout_geometry_classification_e2e_tests.py",  # 几何非法/非法 LPP 的可归因失败分类
    "gui_e2e_tests.py",                     # X11 窗口面：list_windows/send_key/auto_dismiss/screenshot
    # 2026-10-08 归档的 bug 回归钉（四步流程：钉红→修复→转绿→进全量；无参脚本，忽略 --transport）
    "gui_screenshot_cleanup_p125_tb.py",    # P-125：gui.screenshot 远端暂存必须清理
    "veriloga_view_gate_p129_tb.py",        # P-129：veriloga 缺失 view 必须结构化拒绝
    # maestro 放最后：P-086/P-095 的模态框会把 CIW 卡死，若排在前面会让后面的套件
    # （尤其 calibre 的 getWorkingDir/export_cdl）连带失败——2026-09-29 gate 实测。
    "maestro_e2e_tests.py",
    # P-070 Monte Carlo 验收：17 项 run option + 正/负例 + 结果面（Yield 表）。
    # 成本约 8 分钟（真实 8 点 process MC + 一次负控），此前**无人引用**（只有设计侧自测证据）
    # → round9 测试侧独立复跑 9/9 后接线（证据 test/artifacts/evidence/round9/maestro-mc-r9.json）。
    "maestro_mc_e2e_tests.py",
]

#: 个别套件需要附加参数（其余一律只加 `--transport http`）。
#: screenshot_params 门禁只跑 schematic 档；layout/symbol 两档按报告 §3 独立复跑
#: （`--kind layout|symbol` 手动指定，P-105 回归后 SC-06 应转绿）。
SUITE_ARGS = {
    "screenshot_params_e2e_tests.py": [
        "--token", "vb-vbuser4", "--lib", "serdes_rx", "--cell", "rx_top",
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
