"""round10 · 把"当前 spec 有、矩阵没有"的 NORM 条款逐条裁定后补进矩阵。

输入：`spec-clause-delta-r10.json`（`spec_clause_delta_r10.py` 产出；42 条未匹配）。
做法：按"这条是新写入的 spec 条款，由本轮哪个 TB 验收"逐条给 verdict/evidence/reason，
追加到 `test/reports/round8/round8-spec覆盖矩阵.json`（不删旧行 —— 旧行是历史裁定）。

用法：`python test/reports/round10/apply_spec_delta_r10.py [--check]`
"""
from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DELTA = Path(__file__).resolve().parent / "spec-clause-delta-r10.json"
TRIAGE = ROOT / "test" / "reports" / "round8" / "spec-clause-triage.json"
MATRIX = ROOT / "test" / "reports" / "round8" / "round8-spec覆盖矩阵.json"

#: id -> (verdict, evidence, reason)
DECISIONS: dict[str, tuple[str, list[str], str]] = {
    "范围#003": ("na", [],
               "声明类：本版不做日志治理（Supersedes v10），无可验收动作。"),
    "配置#013": ("direct", ["test/live/registration/control_plane_write_tb.py",
                          "test/offline/unit/test_registration_server.py"],
               "自助权限矩阵（编辑/只读/保密）：CPW-05..08 真机 + 离线 personal token 用例。"),
    "日志#005": ("direct", ["test/offline/unit/test_result_contract.py",
                          "test/live/packages/skill_log_options_e2e_tests.py"],
               "C1：Python 属性 `log` / JSON 出口 `CDSlog` 命名由离线契约 + 真机 LOG 套件验证。"),
    "顶层#029": ("direct", ["test/offline/unit/test_top_layer_dispatch.py",
                          "test/live/packages/infra_e2e_tests.py"],
               "C1：2xx 直接返回业务本体、只有受理失败才返回壳形错误；离线 dispatch 断言。"),
    "控制面#069": ("direct", ["test/live/registration/control_plane_write_tb.py",
                           "test/offline/unit/test_registration_server.py"],
                "v43 黑名单：DELETE 收归管理员、个人 update 的 enhanced_token 只校验不落盘、token 字段拒绝 → CPW-05..08 + 离线。"),
    "上层#032": ("direct", ["test/offline/unit/test_result_contract.py",
                          "test/live/packages/infra_e2e_tests.py"],
               "C1+C4：CDSlog 命名、不输出 metadata、CommandResult 具名对象。"),
    "上层#033": ("direct", ["test/live/packages/step_details_e2e_tests.py",
                          "test/offline/unit/test_common_request_fields_contract.py"],
               "C1：steps 出现条件（step_details 或失败）+ 字段名 name。"),
    "上层#034": ("direct", ["test/live/packages/step_details_e2e_tests.py",
                          "test/offline/unit/test_result_contract.py"],
               "C1：失败不得伪装成功/不得丢步骤 —— 真机失败路径用例断言 ok=false + steps 保留。"),
    "schematic#049": ("direct", ["test/live/packages/nested_keys_e2e_tests.py"],
                    "C10 口径：spacing 默认 0 只影响创建期控制点；NK-04 几何对照（非网格点）。"),
    "schematic#051": ("direct", ["test/live/packages/nested_keys_e2e_tests.py"],
                    "同上：默认 0 不保证浮点坐标原样保留 → TB 用几何对照而非坐标相等。"),
    "schematic#052": ("direct", ["test/live/packages/nested_keys_e2e_tests.py"],
                    "实测网格步距 0.00625 写入 TB 注释与判据（非网格点必须偏离网格）。"),
    "schematic#054": ("direct", ["test/live/packages/schematic_e2e_tests.py"],
                    "P-113：sig_type 值域 + 非法值写前拒绝；PIN-OPT 十值全枚举。"),
    "schematic#055": ("direct", ["test/live/packages/schematic_e2e_tests.py"],
                    "P-114：power_sens/ground_sens 只能引用已存在 terminal，否则结构化失败。"),
    "schematic#056": ("direct", ["test/live/packages/schematic_e2e_tests.py"],
                    "P-114：schCreatePin 后校验 pin 存在（不再静默 no-op）。"),
    "schematic#058": ("direct", ["test/live/packages/schematic_e2e_tests.py"],
                    "P-114：off_sheet 无可用 master → 直接结构化拒绝，不猜 master。"),
    "schematic#072": ("direct", ["test/live/packages/schematic_e2e_tests.py"],
                    "rename/delete/set 原子按 pos 索引：ATOM-* 用例逐原子值级读回。"),
    "schematic#073": ("direct", ["test/live/packages/schematic_e2e_tests.py"],
                    "write 逐条原子 + 全成功统一 check/save：NEG-pos/失败档 + baseline 复核。"),
    "symbol#026": ("direct", ["test/live/packages/symbol_e2e_tests.py",
                            "test/offline/unit/test_view_type_param_contract.py"],
                 "P-105：view_type 默认且只允许 schematicSymbol；坏值 ValueError（真机 SC-06 + 离线契约）。"),
    "layout#140": ("direct", ["test/live/packages/layout_e2e_tests.py",
                            "test/offline/unit/test_view_type_param_contract.py"],
                 "P-105：layout view_type 只允许 maskLayout；坏值 400/ValueError。"),
    "maestro#081": ("direct", ["test/live/packages/maestro_e2e_tests.py"],
                  "P-087：save=false 结构化拒绝（reason=save_false_unsupported）—— WRITE-06 真机断言。"),
    "maestro#102": ("direct", ["test/live/packages/maestro_mc_e2e_tests.py",
                             "test/offline/unit/test_maestro_command_exprs.py"],
                  "set_run_option 只服务 Monte Carlo；17 项清单由 MC-01/02 真机值级覆盖。"),
    "maestro#103": ("direct", ["test/live/packages/maestro_nested_keys_e2e_tests.py::NKM-07a"],
                  "P-110：load_corners CSV 默认不传 sections，NKM-07a 真机读回 corner 名。"),
    "maestro#146": ("direct", ["test/live/packages/maestro_e2e_tests.py",
                             "test/offline/unit/test_maestro_package_flow.py"],
                  "C09：write_history 用可激活会话（每次写前确认 maeOpenSetup 会话可用）。"),
    "maestro#148": ("direct", ["test/live/packages/maestro_e2e_tests.py",
                             "test/offline/unit/test_maestro_package_flow.py"],
                  "C09：目标名冲突 → 结构化拒绝（HISTORY-01 rename 链 + 离线 fake）。"),
    "maestro#162": ("direct", ["test/live/packages/maestro_mc_e2e_tests.py",
                             "test/offline/unit/test_maestro_command_exprs.py"],
                  "MC：set_run_mode + run 拼 ?runMode；MC-04/05 真机跑通。"),
    "maestro#176": ("direct", ["test/live/packages/maestro_mc_e2e_tests.py"],
                  "未设置 option 读回 null；MC-01 17 项空基线 + value 全列。"),
    "maestro#202": ("direct", ["test/offline/unit/test_maestro_package_flow.py",
                             "test/live/packages/maestro_mc_e2e_tests.py"],
                  "MC 前置检查：无 plot=t → mc_no_plot_outputs（离线断言 reason；真机 MC-05 正例要求 plot）。"),
    "maestro#230": ("direct", ["test/live/packages/maestro_mc_e2e_tests.py"],
                  "统计模型硬前提：MC-05 用 PDK 统计模型跑 8 点 process MC；MC-07 无统计 section 负控。"),
    "maestro#234": ("direct", ["test/live/packages/maestro_mc_e2e_tests.py",
                             "test/offline/unit/test_maestro_command_exprs.py"],
                  "output 请求勾 Plot（saveallplots）在 17 项 option 清单与真机 MC-02 批量写回里。"),
    "maestro#262": ("direct", ["test/offline/unit/test_maestro_package_flow.py",
                             "test/live/packages/maestro_mc_e2e_tests.py"],
                  "plot 前置检查范围（至少一个 plot=t）：离线 preflight + 真机 MC 正/负例。"),
    "spectre#004": ("na", [],
                  "版本声明（Supersedes v3）：删除 mode=\"x\" 映射；实现侧由 P-108 用例钉住（见 spectre#112）。"),
    "spectre#036": ("direct", ["test/live/packages/step_details_e2e_tests.py",
                             "test/offline/unit/test_result_contract.py"],
                  "C1：steps 默认省略、step_details/失败时出现。"),
    "spectre#112": ("direct", ["test/live/packages/spectre_modes_e2e_tests.py",
                             "test/offline/unit/test_spectre_util_contracts.py"],
                  "P-108：不提供 mode=x；合法 preset cx/ax/mx/lx/vx 真机各跑一次。"),
    "spectre#145": ("direct", ["test/live/packages/spectre_e2e_tests.py"],
                  "P-107：rc!=0/raw 缺失 → status=failure，下载失败不得覆盖，errors 回带仿真器原文（RUN-04）。"),
    "verilog#031": ("direct", ["test/live/packages/verilog_e2e_tests.py",
                             "test/offline/unit/test_view_type_param_contract.py"],
                  "P-115：view_type 校验收窄为 text.v；缺 ensure_view 前置结构化失败。"),
    "verilog#032": ("direct", ["test/offline/unit/test_remote_posix_path_contract.py",
                             "test/live/packages/veriloga_e2e_tests.py"],
                  "P-081：file_is_local=false 时远端 POSIX 路径原样保留（离线契约 + 真机 READ-02）。"),
    "verilog#051": ("direct", ["test/live/packages/verilog_e2e_tests.py",
                             "test/live/packages/verilog_import_params_e2e_tests.py"],
                  "P-115：set_source/patch_source 对缺失 view 必须结构化失败（先 ensure_view）。"),
    "verilog#052": ("direct", ["test/live/packages/verilog_e2e_tests.py",
                             "test/live/packages/verilog_import_params_e2e_tests.py"],
                  "P-115：半成品 view（缺 master.tag）视为不完整 → 写入前前置清理/拒绝。"),
    "calibre#069": ("direct", ["test/live/packages/calibre_e2e_tests.py",
                             "test/offline/unit/test_calibre_job_state.py"],
                  "P-106：official-batch 判活用 job.pid + ps -p（SET-01 真机 + 离线 job_state）。"),
    "calibre#117": ("direct", ["test/offline/unit/test_calibre_lvs_source_contract.py",
                             "test/live/packages/calibre_e2e_tests.py"],
                  "C07：runset 指定源时可省 source；source.kind=cdl.path 必须远端可见（LVS-SRC-XOR/互斥断言）。"),
    "calibre#142": ("direct", ["test/live/packages/calibre_e2e_tests.py",
                             "test/offline/unit/test_calibre_package.py"],
                  "C07：CDL 默认写 <run_dir>/<cell>.cdl；emit_cdl=true 回带 cdl_path（LVS-02 + 离线契约）。"),
    "calibre#152": ("partial", ["test/live/packages/calibre_export_pex_e2e_tests.py"],
                  "P-117 阻塞：`export.items` 缺 `pdb_dir`（spec 列了、实现未提供）→ read_results(kind=pex) 可读、"
                  "export 的 pdb 目录导出不可达；gap_test=按 P-117 裁决补实现或改 spec 后复跑。"),
    # —— 编号复用的"旧文本"补充：它们原先占用的 id 被新条款拿走，这里按当前 id 补回 ——
    "schematic#061": ("direct", ["test/offline/unit/test_schematic_contracts.py",
                               "test/live/packages/schematic_e2e_tests.py"],
                    "不再出现 `xy` 字段/缺字段必须报明；负例与契约（离线 + ATOM/NEG 真机）覆盖。"),
    "spectre#037": ("direct", ["test/offline/unit/test_spectre_contracts.py",
                             "test/live/packages/spectre_e2e_tests.py"],
                  "业务失败写 ok=false+error；只有结构错误/未预期异常才抛（离线契约 + 真机失败档 RUN-04）。"),
    "calibre#071": ("direct", ["test/semi/probes/calibre_timeout_probe.py",
                             "test/live/packages/calibre_e2e_tests.py"],
                  "P-098：动态超时 → status=timeout 且不杀后台作业（半真机探针 PASS + 真机套件）。"),
}

#: 每轮都要刷新证据指针的行（值即最终 evidence；幂等）。
REFRESH_EVIDENCE: dict[str, list[str]] = {
    # 套件整体因末位红钉 rc=1，但本行由 NKM-07a 覆盖 → 点名到用例，
    # live_evidence_currency.py 会去套件日志里核对该用例自身 PASS。
    "maestro#103": ["test/live/packages/maestro_nested_keys_e2e_tests.py::NKM-07a"],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)

    delta = json.loads(DELTA.read_text(encoding="utf-8"))["unmatched"]
    full = {r["id"]: r for r in json.loads(TRIAGE.read_text(encoding="utf-8"))}
    rows = json.loads(MATRIX.read_text(encoding="utf-8"))
    known = {r["id"] for r in rows}
    missing = [r["id"] for r in delta if r["id"] not in DECISIONS]
    if missing:
        print(f"!! 未裁定的条款: {missing}")
        return 2

    before = collections.Counter(r.get("verdict") for r in rows)
    added = updated = 0
    by_id = {r["id"]: r for r in rows}
    for item in delta:
        cid = item["id"]
        verdict, evidence, reason = DECISIONS[cid]
        source = full.get(cid) or {}
        if cid in known:
            # 同 id、文本已换（spec 增删行导致编号复用）：就地更新为新文本 + 合并证据。
            row = by_id[cid]
            row["text"] = source.get("text")
            row["section"] = item.get("section")
            old_ev = row.get("evidence") or []
            if isinstance(old_ev, str):
                old_ev = [old_ev]
            merged = list(dict.fromkeys([*old_ev, *evidence]))
            row["evidence"] = merged
            row["verdict"] = verdict
            note = f"｜round10：条款文本已换（编号复用），按新文本复核 → {reason}"
            if note not in (row.get("reason") or ""):
                row["reason"] = (row.get("reason") or "") + note
            updated += 1
            continue
        rows.append({
            "id": cid, "doc": item["doc"], "line": source.get("line"),
            "section": item.get("section"), "text": source.get("text"),
            "tokens": [], "hits": {}, "premap_status": "ROUND10-DELTA",
            "verdict": verdict, "evidence": evidence,
            "reason": f"round10 新增条款裁定：{reason}",
            "gap_test": ("按 P-117 裁决补实现/改 spec 后复跑 export 用例"
                         if cid == "calibre#152" else ""),
            "evidence_level": "live" if any(e.startswith("test/live/") for e in evidence)
                              else ("semi" if any(e.startswith("test/semi/") for e in evidence)
                                    else "offline"),
        })
        added += 1
    after = collections.Counter(r.get("verdict") for r in rows)
    for cid, evidence in REFRESH_EVIDENCE.items():
        row = by_id.get(cid) or next((r for r in rows if r["id"] == cid), None)
        if row is not None:
            row["evidence"] = list(evidence)
    print(f"追加 {added} 行 / 就地更新 {updated} 行：verdict {dict(before)} -> {dict(after)}")
    if args.check:
        return 0
    MATRIX.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"写回 {MATRIX.relative_to(ROOT)}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
