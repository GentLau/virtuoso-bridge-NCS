# round10 · 遗漏复审（主代理亲自执行；subagent 通道故障）

> 作者：测试/root ｜ 2026-09-30
> 为什么要用主代理复审：本轮按要求尝试让 subagent 独立评审，**subagent 消息通道故障**（见 §0），
> 因此改为"主代理以评审员身份重新取证"，并把自证伪结果如实记在这里（不假装有外部评审）。

## 0. subagent 通道故障（如实记录；用户已裁定不再等待）

尝试了 **9 次**，全部**没有把任务送达**（agent 只收到 workspace bootstrap）：

1. `spawn_agent(review_coverage_r10)` + 2. `spawn_agent(review_redteam_r10)`：初始 message 未送达；
3. `followup_task` 补发 2 次：`review_redteam_r10` 回"no task payload has reached me"；
4. `spawn_agent(ping_probe)` 只发了 20 字的"请回复已收到"：agent 仍回"没有收到具体任务指令"。
5. 续跑轮：`spawn_agent(review_c_r10)`（完整任务正文）→ 仍只做环境侦察；
6. 续跑轮：`spawn_agent(ping2)`（"回复两个字：收到"）→ 仍无任务；
7. 收尾轮：`spawn_agent(ping3)`（"回复 OK 两个字母"）→ 回"No task payload arrived in this thread"。

→ 结论：**本会话的 agent 间消息投递不可用**（用户确认这是 Codex 的 bug）。
用户裁定"再简单试一下，不能用就算了" —— 第 9 次仍不可用，因此本轮**不再等待外部 agent**，
独立复审以主代理执行 + 本文档化替代（所有结论都可被下面的命令复跑）。

## 1. 复跑工具 × 对照报告数字（全部为本次实测）

| 工具 | 本次实测 | 报告里的口径 |
|---|---|---|
| `audit_atom_coverage.py` | 写读回 0 / 待人工分诊 0 / 已知误报 16 / 已知弱判据 0 | 一致 |
| `build_op_param_matrix.py` | 811 行（CANDIDATE 571 / GAP 240）/ `NO-OP-TB 0` / 未解析 102 / 零调用点 op 0 | 一致（240 = 215 合同 + 25 N-A，见 `op-param-classification.json`） |
| `build_output_field_matrix.py` | 78 op / **1008 行：asserted 970 / read_only 18 / absent 20**；`real_gap_candidates {}` | 报告写 960/28/20 → 本次因把 10 条"非行内断言"（`KNOWN_ASSERTED` 白名单，逐条带 file:line）归位而变 970/18 |
| `nested_key_audit.py` | 90 op / 104 字段 / 未触碰 0 / **未覆盖枚举 0** | 一致（本轮把 6 个 `sig_type` 取值补齐后归零） |
| `weak_assert_audit.py` | 6362 断言点（strong 4487 / medium 586 / weak 1289）/ 仅弱用例 121 / **日志未断言 0** | 一致（数字随本轮 TB 增删略变） |
| `spec_matrix_r10_audit.py` | R10-GREEN 217 / NO-OFFLINE 23 / NA 57；**变更影响候选 0** | 一致 |
| `check_tb_headers.py` | **118 合格 / 118 候选** | 一致 |
| `live_evidence_currency.py` | 23 条"无离线证据"行 → **22 条有本轮 PASS**，1 条（路由#024）因 flows 首跑失败记录待刷新 | 见 §3（重跑 flows 后归零） |

## 2. 自证伪：3 处弱断言（本轮自评审发现并已加固）

| # | 位置 | 弱点（错误实现也能过） | 加固 | 复跑 |
|---|---|---|---|---|
| 1 | `maestro_e2e_tests.py::_case_read_config_rc` | `detail['sim'] == {test: sim_options}` 在**两边都是空字典**时恒真 → 实现什么都不返回也会绿 | 增加断言：`detail[env/sim]` 的 test 键集合必须 == 公开 `tests` 键集合（防空转） | `maestro-e2e-r10-strengthened.log`（本轮重跑） |
| 2 | `symbol_e2e_tests.py::_case_orders_term_pin116` | 只断言 `pin_order == port_order` 与 `term_order` 是 list → 三者都为空列表也能过 | 增加 `pin_order == ["IN","OUT","BI"]`（命中 fixture 真实顺序） | `symbol-r10-strengthened.log`（10/10 绿） |
| 3 | `calibre_e2e_tests.py::_case_export_all_small` | 只断言 `items ⊆ {summary,results_db,log}` 且非空 → 只下到 1 个文件也能过 | 增加 `{"summary","log"} ⊆ items`（LVS 目录这两个必然存在；`results_db` 是 DRC 产物允许缺） | `calibre-export-r10-strengthened.log`（4/4 绿） |

> 附带：`build_output_field_matrix.py` 增加 10 条 `KNOWN_ASSERTED`（key=op+field，value=file:行指针），
> 把"多行 assert / checks 字典 + for 循环"这类**真实判据**从"read_only/absent"归位为 asserted；
> 它是白名单而不是放宽规则：每条都能点回代码行，`real_gap_candidates` 因此归零。

## 3. 5 条 `na` 的独立核对（P-112/C 组）

| 条款 | 现状 | 结论 |
|---|---|---|
| `calibre#005/#127/#128/#129` | spec 已改写为"PEX 本版不提供 → `pex_unsupported`"；TB `calibre_export_pex_e2e_tests.py` 6/6 断言"调用被结构化拒绝、不建 run_dir" | na 成立（条款语义已作废，替代判据在位） |
| `calibre#172` | `power`/`ground` 字段已从实现删除（P-092）；离线契约断言"传该关键字 → `invalid request`" | na 成立 |
| 其余 25 条非候选 | 分类见 `round9/op-param-classification.json`（215 合同 + 25 N-A/惰性） | 已逐条分类，无"真缺口" |

## 4. 仍然存在的风险 / 本轮未做到的事（不掩盖）

**4.0（本轮复审新增发现，已修复）spec 矩阵并没有"覆盖当前 spec"**：报告此前写"NORM 297 条已逐条核对"，
但用 `spec_clause_delta_r10.py` 把**当前** spec 重新抽取（NORM 328 条）与矩阵按文本对齐后，
只有 286 条是编号漂移，**42 条是新条款 / 文本已换**（C1 契约、C11 自助权限、C09 会话、
P-113/P-114、P-105/P-080/P-081/P-115、P-106/P-107/P-108、P-110、P-070 MC、C07…）。
→ 已逐条裁定：追加 38 行、就地更新 7 行（编号复用）、刷新 3 行证据；复核脚本显示
**unmatched = 0**、变更影响候选 **0**、39 条 live-only 行的本轮 PASS 依据 **全部可核（unresolved 0）**。
这条正好说明：**"矩阵 297 条"≠"当前 spec 全覆盖"，不做差集就会漏报**。

1. **P-117 / P-118 / P-119 / P-120 / P-121 未关闭**（前三条是 spec/实现裁决，P-120 是 probe 忽略 `ssh_backend`，P-121 是 `power→supply` 归一化）。
2. `s11_full_flow` 的 `sim` 阶段 SKIP（未准备仿真网表）；前仿/后仿由 `serdes_rx`（AC/TRAN 数值判据）与 `adc_sar` 承担，`s11_postsim_compare.py` 本轮未跑。
3. 日志 spec §8.4 第 3 档（truncate 说明行）E2E 不可达（SKILL 产不出 `\e` 前缀行）→ 保持 L0。
4. 覆盖率 **未提升**（strict 语句 91.82%、分支 84.07%、combined 89.80%），未覆盖最多的仍是 `maestro.py`（246 行）、`paramiko_backend.py`（171）、`middle.py`（118）、`register/flow.py`（116）—— 这些是"分支多、真机难穷尽"的模块，不能声称已覆盖完全。
5. `flows` / `registration` 首次编排暴露 3 类**调用姿势**问题（role_split 缺 token、s11_full 无 `--out`、hostkey 的 ssh config 漂移）与 1 次环境 flake（w1 ssh 超时）——已修 runner/env 并复跑；这说明"runner 本身"此前缺少复跑验证。

## 5. 结论

* 认可：**没有发现阻断性的覆盖遗漏**（4 张审计表的"真缺口"都为 0，spec 297 条已逐条落 verdict，P-112 的 30 条候选归零）；
* 不认可：**不能说覆盖率已完备** —— 见 §4（5 张未关闭卡 + 覆盖率未提升 + 3 处 E2E 不可达/未跑）。
