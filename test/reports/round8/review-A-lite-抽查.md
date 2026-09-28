# REVIEW-A（lite）· spec 覆盖矩阵抽查（独立评审）

> 评审方：`/root/verilog_params/red_team`（独立子代理）｜ 快照：`HEAD=e3e810d` + 未提交工作区
> **范围声明：本文件是精简抽样（15 项，其中 1 项深挖），不是 `red-team-brief.md` #1 要求的 ≥40 条全量红队。完整版仍未执行**（子代理线程限导致），建议 root 按 brief 重派。
> 方法：分层抽样（21 个 doc 各 2 条 direct，seed=20260929；脚本 `test/artifacts/tmp/r8_alite_sample.py`），逐项打开被引证据验证；另抽 8 条 `na` 看理由。

## 1. 抽查结果

| 抽样条款 | 被引证据 | 结论 |
|---|---|---|
| **上层#043**（checksum 不一致不忽略 + 传输层透明重试） | `test_middle_contracts.py` + `test_pyapi_packages.py` | **overclaim 候选（高置信）**：两文件内 `rg checksum\|sha256\|mismatch\|校验\|重试\|retry\|透明` **全部为空**；全树命中 `checksum\|sha256` 的是 live flows/stress/docs，不在这两个文件 |
| gui#022 auto_dismiss 只收 dialog | `test_gui_package.py::test_dialog_candidates_only_and_order` | ok（断言存在：dismissed=1、window_id、still_mapped=False） |
| calibre#120 三级报告定位回退 | `test_calibre_package.py::test_read_results_follows_renamed_report_in_job_json` | ok（`report_used="renamed.report"`、rules_checked=1737） |
| verilog#062 structural_views 编码/默认 4 | `test_verilog_contracts.py` + `verilog_e2e_tests.py` | ok（live IMP-09 以 5 档 vs 4 档对照断言；离线仅有负例 =9） |
| 配置#075 registry 0600 | `test_registry_more.py::test_registry_file_mode_is_0600` | ok（`assertEqual(0o600, mode)`） |
| 日志#082 CDS.log 不可读 | `test_daemon_handler.py::test_unavailable_cds_log_uses_frozen_warning_text` | ok（`body["log"]==""` 等） |
| 顶层#028 import 契约 | `test_upper_layer_import_contract.py` | ok（FORBIDDEN_MODULES 含 transport/socket/subprocess/paramiko） |
| 注册#039 cancel 语义 | `test_reservation.py` | ok（cancel 释放 / failed 保留到 cancel 两条用例存在） |
| maestro#030 批量会话 + 统一保存 | `test_maestro_command_exprs.py` | ok（步骤序列含 save_setup/close_session） |
| spectre#214 缺失哨兵不得填 0 | `test_spectre_util_psf_contracts.py` | ok（None 哨兵断言多条） |
| 注册#036 步级 deadline | `test_norm_gap_round8.py::TestStepBudgetDoesNotReset` | ok（类存在，line 211） |
| layout#047 非事务 applied k/n | `test_layout_contracts.py::test_command_failure_reports_applied_prefix` | ok（函数存在，line 616） |
| 中层#034 ≤3 次重试 | `test_connect_retry.py` | ok（`assertEqual(len(calls), 3)`） |
| veriloga#069 headless 与 GUI 逐文件一致 | `veriloga_e2e_tests.py` | 无法确认（live TB 存在；未逐行核该断言） |
| skillref#069 唯一搜索入口 | `test_skillref_package.py` + `skillref_probe.py` | 无法确认（文件存在；关键词核对方法不适用） |

## 2. na 抽样（8 条）

抽 8 条 `na` 逐条看理由：均为"指针/术语/明确不做/枚举保留（如 move_* 系列、路由抽象、并发写同 cell）"，**未发现明显可测却被标 na** 的条目。

## 3. 统计与建议

- 抽查 15 项：**ok 12 / overclaim 候选 1 / 无法确认 2**。
- 建议：① 复核 `上层#043`——找到真实断言文件并改引用，或把该行降为 indirect/weak 并补 TB；② 完整版 ≥40 条抽样仍欠（brief #1），审阅若要求需重跑。
- 原始输出：`test/artifacts/tmp/r8_alite_sample.txt`、`r8_alite_verify.txt`。

## 4. 二轮更新（2026-09-29 00:1x）

- **上层#043 已修复并被核实**：矩阵该行证据已改为
  `test/offline/unit/test_tunnel_transfer.py::test_upload_checksum_mismatch_does_not_move_stage`（:161）、
  `::test_verify_mismatch`（:345）、`test/offline/unit/test_ssh_edges.py::test_retryable_predicate_matrix`（:696）——三个函数均存在。
- **机器加宽核验（55 条 direct 抽样）**：脚本 `test/artifacts/tmp/r8_alite_broad.py` → 10 个 flag 全为启发式误报
  （`Test*` 类引用被 `def` 正则误判、probe/stress TB 用 `record()/steps.append()` 而非 assert 字样），**无新增硬伤**。
- **仍欠**：brief #1 的 ≥40 条人工语义核验（本轮合计 15 项语义 + 55 项机器），建议下一轮首项补。
