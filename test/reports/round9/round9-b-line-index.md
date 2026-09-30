# round9 · B 线交付索引（subagent `/root/opparam_r9`）

> 用途：主报告收口时快速定位"哪份产物解决哪个问题"。全部文件位于 `test/reports/round9/`（除非注明路径）。
> 生成：2026-09-29 22:16

## 1. 报告（人读，按主题）

| 报告 | 解决什么 | 关键数字 |
|---|---|---|
| `op-param-r9.md` | op×参数矩阵刷新 + 240 条非 CANDIDATE 逐条分类 | 811 行；**真缺口 0**（215 合同 + 25 N-A/惰性） |
| `nested-key-coverage.md` | 顶层矩阵盲区：`commands[].*` 嵌套键 | 90 op / 365 (op,键)；20 键 + 5 mode 未触碰 → 已补 L0 |
| `log-options-w1-r9.md` | **W-1**：log `warn` 过滤 / `log_max_bytes` 降级 / off 空值 | 真机 **7/7** |
| `w2-w3-r9.md` | **W-2** 检索内容断言 / **W-3** 失败步骤形状 | 各 **6/6** |
| `w4-flows-r9.md` | **W-4**：serdes flow stage 值级读回 | `--stage buf` 6.75s / `ctle` 16.95s 全绿 |
| `weak-assertions.md` | 断言强度审计（5853 断言点）+ 4 类真弱点（W-1..W-4 全关） | strong 4187 / weak 1207 |
| `atom-coverage-r9.md` | 原子级覆盖独立复核 + 2 条 needs-triage 归入误报 | 60 原子 / 零引用 0 / 误报 13 |
| `live-transport-compliance.md` | 真机传输形态合规（§11） | 门禁强制 http ✓；12 个 TB 默认 direct（已由 root 改） |
| `live-execution-gaps.md` | 真机 TB 执行矩阵：谁负责跑 | 50 live TB；3 无引用 → 已接线跑绿；断链 0 |
| `spec-matrix-r9-b-review.md` | **spec 297 条复核（代 A 线）** | 226 本轮离线重验绿 + 53 na + 18 semi/live 依赖（现已全有本轮证据）+ 30 条改判候选 |
| `ledger-integrity-r9.md` | 缺陷台账完整性（生成器↔卡片↔问题登记） | 未关闭 **5**；断链 0；L6=C09 缺登记行 |
| `closed-cards-evidence-r9-review.md` | 已关闭卡"依据可复跑性" | 17 离线重验绿 + 1 今晚产物；mtime 不可作判据 |
| `gate-r9-live-triage.md` | 门禁 5 红逐条定性 + 我的负载自我披露 | 14 绿 / 5 红（1 假失败竞态 / 1 瞬时已复跑绿 / 1 过期 TB / 1 待安静复跑 / 1 环境卫生） |
| `offline-flaky-r9.md` | 离线 flaky 用例（1/3 观测） | `test_register_flow.py::TestStepRetryAfterFailure…` |
| `round9-flows-not-rerun.md` | 业务流程 TB 本轮复跑情况 | 11 套里 **role_split 已补**，其余最近证据在 round8 |
| `round9-residuals.md` | **残留/待办汇总（主报告 §6 可直接用）** | A 设计 4 / B 测试 6 / C 环境 3 / D 口径 5 条 |
| `coverage-honesty-notes.md` | 覆盖率引用规则与 provenance | `head 86cc169 + dirty + diff 351f5c03… + cov 7.16.0`；append 产物不可引用 |
| `coverage-gap-map-r9.md` | 覆盖率缺口地图（基线） | 0 个 0%/<60% 文件；最大绝对缺口 `maestro.py`（缺 259 行/160 分支） |
| `round9-close-checklist.md` | **收口 8 步检查单** | 每步带前置/命令/期望/证据/失败处置 |
| `review-of-round9-report.md` | 对主报告 20:59 版的交叉复核 | A/B/C/D/E 五节 + 后来补的"§5 已过期"提醒 |

## 2. 脚本（可复跑）

| 脚本 | 用途 |
|---|---|
| `nested_key_audit.py` | 嵌套键覆盖审计（AST；含 handler→op 归属与守卫上下文继承） |
| `weak_assert_audit.py` | 断言强度审计（unittest + 脚本式两套风格） |
| `spec_matrix_r9_audit.py` | spec 297 条 × 本轮 JUnit 新鲜度 + 变更影响候选 |
| `spec_live_evidence_r9.py` | 只引 semi/live 的 18 条对表到本轮产物 |
| `live_execution_matrix.py` | live TB 执行矩阵（门禁/被引用/今日证据） |
| `closed_cards_evidence_r9.py` | 已关闭卡依据可解析性（含 `::` 后缀、裸文件名、相对产物路径解析） |
| `verify_round9_layers.py` | 门禁 19 套 + 半真机 40 探针的汇总核对（19/19 账目一致） |
| `verify_coverage_r9.py` | 覆盖率口径核对（all_steps_passed / head / delta / `stress_server` 回归） |
| `test/shared/runners/run_redpins.py` | **新增**：真机红钉 runner（HOLD/UNEXPECTED-GREEN/BROKEN，后两者 rc=1） |

## 3. 机器产物

`op-param-matrix.{json,md}`、`op-param-classification.json`、`op-coverage.json`、`nested-key-audit.{json,md}`、
`weak-assert-audit.json`、`spec-matrix-r9-b.{json,md}`、`spec-live-evidence-r9.{json,md}`、
`live-execution-matrix.{json,md}`、`closed-cards-evidence-r9.{json,md}`、`round9-layers-summary.{json,md}`、
**`test/artifacts/evidence/round9/coverage-pre-r9-strict.json`**（基线快照，**别删**）、`coverage-verify-r9.json`（已生成）、`spec-op-drift.{json,md}`。

## 4. 我改过的测试侧文件（都与上面报告对应）

| 文件 | 改动 | 对应 |
|---|---|---|
| `test/offline/unit/test_nested_command_keys_contract.py` | **新增 TB**（21 用例） | 嵌套键 L0 |
| `test/live/packages/skill_log_options_e2e_tests.py` | LOG-04/04b/04d/06 值级断言 + 默认 `--out` | W-1 |
| `test/live/packages/skillref_e2e_tests.py` | `_case_search_local` 内容断言 | W-2 |
| `test/live/packages/step_details_e2e_tests.py` | 失败步形状 + 默认 `--out` | W-3 |
| `test/live/flows/serdes_rx_flow_tb.py` | `buf/ctle` 值级读回 | W-4 |
| `test/semi/probes/_maestro_tb.py` | 清掉最后一处 C4 位置索引（`r["result"][1]`） | C4 遗留 |
| `test/shared/runners/run_all_http.py` | 接入 3 套（step_details / layout_geometry / gui） | 执行矩阵 |
| `test/shared/runners/audit_atom_coverage.py` | 2 条 needs-triage 归入已知误报（带理由） | 原子覆盖 |
| `test/shared/runners/make_bug_cards.py` | P-106 补"完成 marker 不匹配"第二处缺口 | P-106 |
| `test/shared/runners/README.md` | 登记 `run_redpins.py` | 红钉纪律 |
| `test/reports/internal/环境Runbook-内部.md` | S2 注册表 paramiko→openssh 修复记录 | 环境 |

## 5. 待跑（我随时可做，等你安排）

1. ~~`verify_coverage_r9.py`~~ ✅ 已跑（22:31，结果见 `coverage-honesty-notes.md §7`）；
2. ~~`run_redpins.py --only c06`~~ ✅ 已跑（22:34，`RED-PIN-HOLDS`，`evidence/redpins/c06.log`）；
3. ~~`maestro_view_param` / `verilog_import_params` 无负载复跑~~ ✅ 已跑（22:35–22:39，**9/9 + 13/13**，证据 `evidence/round9/*-r9b.json`）；
4. ~~离线单会话复跑~~ ✅ 已跑（22:41，rc=0；flaky 统计 **1 红 / 4 次**）；~~`serdes_rx_flow --stage all`~~ ✅ 已跑（22:44，**rc=0 全绿**，证据 `evidence/round9/serdes-r9-full/`）。
5. ~~`design_iterate_tb`~~ ✅ 已跑（22:51，11 stage rc=0，`evidence/round9/design-iterate-r9/`）；
   ~~`adc_sar_flow_tb`~~ ✅ 已跑（22:52，**多用户 24/24 ok**，`evidence/round9/adc-sar-r9/`）→ **"两个完整项目"达成**；
   ~~multiuser_serdes_rx~~（17/17）、~~multiuser_layout_handoff~~（12/12）、~~s11 链~~（PASS/match）、~~lvs_from_schematic~~（**CORRECT**）✅ 均已跑；
   ~~multihop~~（**10/10**，两跳+SOCKS5；途中修 S15 两处环境：ssh config `accept-new→yes`、生成器补 `vb-lab11/12` 基线用户）、
   ~~scale_100~~（100 fake ×2 轮全绿）、~~project_flow~~（rc=0，spectre 0 err/0 warn）✅ →
   **流程 TB 本轮 11/11 全部跑完**，无剩余。
