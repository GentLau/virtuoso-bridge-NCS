"""round10 · 按 P-112 决策表更新 spec 覆盖矩阵（NORM 297 条）。

为什么需要：`spec-matrix-r9-b.json` 的 30 条「变更影响候选」在 spec 侧已
逐条回填（决策表 `round9/P-112-条款决策表.md`），但**矩阵本身**还是旧结论 ——
本轮按决策表把 30 行的 verdict/reason/evidence 落笔，然后重新复核
（`spec_matrix_r10_audit.py` 的 `change_impact_candidates` 应归零）。

口径（决策表 §1~§5）：
  * A 保留（12 条）：verdict 不动，reason 追加 P-112/A 标记 + 本轮证据；
  * B 改判（2 条）：reason 写明新口径 + 本轮证据；
  * C 删除/NA（5 条）：verdict = na（PEX 本版不提供 / power·ground 字段已删）；
  * D 误命中/保留（11 条）：reason 追加标记，条款保持原样。

用法：`python test/reports/round10/apply_p112_decisions.py [--check]`
"""
from __future__ import annotations

import argparse
import collections
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MATRIX = ROOT / "test" / "reports" / "round8" / "round8-spec覆盖矩阵.json"
MD_OUT = ROOT / "test" / "reports" / "round10" / "spec-matrix-r10.md"

#: id -> (kind, reason 追加/改写, evidence 列表)
DECISIONS: dict[str, tuple[str, str, list[str]]] = {
    # ---- C 删除/NA：PEX 本版不提供（4 条）+ power/ground 已删（1 条）
    "calibre#005": (
        "na",
        "P-112/C：spec 已改写为「PEX 本版不提供：`calibre.pex` 返回 `pex_unsupported`，三阶段不作为本版验收项」。",
        ["test/live/packages/calibre_export_pex_e2e_tests.py"],
    ),
    "calibre#127": (
        "na",
        "P-112/C：PEX 对外参数（`fmt` 取值）随 PEX 本版不提供一并作废；调用返回结构化拒绝。",
        ["test/live/packages/calibre_export_pex_e2e_tests.py"],
    ),
    "calibre#128": (
        "na",
        "P-112/C：PEX 内部三阶段描述不再作为本版验收条款（不启动 PEX）。",
        ["test/live/packages/calibre_export_pex_e2e_tests.py"],
    ),
    "calibre#129": (
        "na",
        "P-112/C：阶段产物校验条款随 PEX 条款删除/NA。",
        ["test/live/packages/calibre_export_pex_e2e_tests.py"],
    ),
    "calibre#172": (
        "na",
        "P-112/C：`power`/`ground` 字段已从实现删除（P-092），该已知限制条款作废。",
        ["test/offline/unit/test_calibre_argv_contracts.py"],
    ),
    # ---- B 改判（2 条）
    "上层#031": (
        "B",
        "P-112/B：每步字段已从 `{step:…}` 改为 `{name:…}`，且**成功默认不返回 steps、`step_details=true` 才返回**（spec 已同步）。",
        ["test/offline/unit/test_result_contract.py",
         "test/live/packages/step_details_e2e_tests.py",
         "test/offline/unit/test_common_request_fields_contract.py"],
    ),
    "schematic#018": (
        "B",
        "P-112/B：截图口径已改为「远端暂存 → 下载 → **清理远端**；本地落 `artifact/screenshots/`；`leave_open` 只控制窗口」。",
        ["test/live/packages/screenshot_params_e2e_tests.py",
         "test/live/packages/schematic_e2e_tests.py"],
    ),
    # ---- A 保留（12 条）
    "总览#179": ("A", "", ["test/live/packages/infra_e2e_tests.py"]),
    "总览#229": ("A", "", ["test/offline/unit/test_middle_contracts.py"]),
    "日志#045": ("A", "", ["test/offline/unit/test_skill_log_options.py",
                          "test/live/packages/skill_log_options_e2e_tests.py"]),
    "日志#055": ("A", "", ["test/offline/unit/test_skill_log_options.py",
                          "test/live/packages/skill_log_options_e2e_tests.py"]),
    "日志#082": ("A", "", ["test/offline/unit/test_skill_log_options.py",
                          "test/live/packages/skill_log_options_e2e_tests.py"]),
    "日志#091": ("A", "", ["test/offline/unit/test_daemon_runtime_contracts.py",
                          "test/live/packages/skill_log_options_e2e_tests.py"]),
    "symbol#023": ("A", "", ["test/live/packages/symbol_e2e_tests.py"]),
    "symbol#026": ("A", "", ["test/live/packages/symbol_e2e_tests.py"]),
    "calibre#011": ("A", "", ["test/live/packages/calibre_e2e_tests.py"]),
    "calibre#060": ("A", "", ["test/live/packages/calibre_e2e_tests.py"]),
    "calibre#068": ("A", "", ["test/semi/probes/calibre_timeout_probe.py"]),
    "calibre#069": ("A", "", ["test/semi/probes/calibre_timeout_probe.py"]),
    # ---- D 误命中/保留（11 条）
    "总览#159": ("D", "P-112/D：讲的是中层↔底层帧格式，与上层 log 选项变更无关。", []),
    "总览#215": ("D", "P-112/D：与截图暂存/`view_type` 变更无关。", []),
    "总览#230": ("D", "P-112/D：与 log 选项变更无关。", []),
    "并发#034": ("D", "P-112/D：与 log 选项变更无关。", []),
    "注册#011": ("D", "P-112/D：P-104 是读路径建 view，不涉及 token 范围。", []),
    "控制面#043": ("D", "P-112/D：控制面错误体不是 `basic.skill.execute` 响应壳。", []),
    "layout#139": ("D", "P-112/D：P-091 改的是截图远端暂存/清理，不是缩放安全约束。", []),
    "spectre#214": ("D", "P-112/D：C1 只改对外 JSON 出口，未改内部 PSF 缺失哨兵语义。", []),
    "verilog#101": ("D", "P-112/D：与 log 选项变更无关。", []),
    "verilog#108": ("D", "P-112/D：与 log 选项变更无关。", []),
    "日志#077": ("D", "P-112/D：内部 daemon `meta` 帧保留（spec `431ad3e`「本版不做日志治理」），条款不动。", []),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="只报告，不写回")
    args = parser.parse_args(argv)

    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    by_id = {row["id"]: row for row in rows}
    before = collections.Counter(row.get("verdict") for row in rows)

    missing = [key for key in DECISIONS if key not in by_id]
    if missing:
        print(f"!! 决策表里的条款不在矩阵里: {missing}", file=sys.stderr)
        return 2

    applied = []
    for cid, (kind, note, evidence) in DECISIONS.items():
        row = by_id[cid]
        if kind == "na":
            row["verdict"] = "na"
        elif kind == "B":
            row["verdict"] = "direct"
        marker = f"｜P-112/{kind}：{note or '保留条款，换本轮证据'}"
        reason = row.get("reason") or ""
        if "P-112/" not in reason:
            row["reason"] = reason + marker
        if evidence:
            row["evidence"] = evidence
        applied.append(cid)

    after = collections.Counter(row.get("verdict") for row in rows)
    print(f"应用 {len(applied)} 条决策：verdict {dict(before)} -> {dict(after)}")
    if args.check:
        return 0

    MATRIX.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n",
                      encoding="utf-8")

    lines = [
        f"# 第 10 轮 · Spec 条款覆盖矩阵（NORM {len(rows)} 行逐条裁定："
        f"round8 矩阵 297 + P-112 回填 + round10 spec 差集补判）",
        "",
        "> 生成：`test/reports/round10/apply_p112_decisions.py`（+ `apply_spec_delta_r10.py`）｜ 数据源："
        "`test/reports/round8/round8-spec覆盖矩阵.json`（本轮按 P-112 决策表 + 当前 spec 差集逐条落笔）",
        f"> 统计：direct {after.get('direct', 0)} / indirect {after.get('indirect', 0)} / "
        f"partial {after.get('partial', 0)} / gap {after.get('gap', 0)} / na {after.get('na', 0)}"
        f"（共 {len(rows)}）",
        "",
        "| 条款 | 文档 | 判定 | 章节 | 理由 | 证据 |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        evidence = "<br>".join(row.get("evidence") or [])
        lines.append(
            f"| {row['id']} | {row['doc']} | **{row.get('verdict')}** | "
            f"{row.get('section', '')} | {(row.get('reason') or '').replace('|', '/')} | {evidence} |"
        )
    MD_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"写回：{MATRIX.relative_to(ROOT)} ／ 快照：{MD_OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
