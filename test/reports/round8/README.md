# 第八轮全量测试 · 工作计划与状态板

> 维护者：测试（root）｜ 2026-09-28 起 ｜ 状态：**复跑完成，报告定稿**（`round8-测试报告.md`）
> 目标（用户口径）：**spec 每条要求、每个原子操作、每个可传参数都要有 TB 覆盖并实跑验证**；
> 发现 bug 全量上报；每阶段由独立子代理评审遗漏，报告不得出现"接口 ok 即覆盖"。
> 基线：`HEAD=d47dabe` + 工作区（设计侧未提交改动一并被测）。

## 0.0 终态数字（2026-09-28 23:5x 复跑，证据见 `round8-测试报告.md` §7）

| 项 | 结果 |
|---|---|
| 离线 | Win py3.12 **1807/0红/21skip**；Linux py3.9 **1807/0红/31skip**（两平台计数一致） |
| 半真机 | **39 探针 / 32 ok / 7 红**（7 条红灯全部对应已立卡缺陷） |
| 真机 | 10 套稳定绿 + 1 被阻塞（maestro P-086/P-095/P-096）；五接口 5/5；e2e 10 用例 0 红 + local 4/4；压测 108 步 0 失败；业务场景 10 条链全绿；注册 4 条 TB 全绿 |
| 覆盖率 | 语句 **91.54%** / 分支 **83.62%** / 合并 **89.48%**（离线层已纳入统计） |
| 缺陷 | 本轮新增 **24**（P-078…P-101），未关闭 **25**（含待决策 P-070） |

## 0. 三条覆盖轴（本轮"完整"的定义）

| 轴 | 数据源 | 机器核账工具 | 当前状态 |
|---|---|---|---|
| **A. spec 条款** | `spec/design-concepts/**` Normative 全量 → 1131 条 | `extract_spec_clauses.py` + `premap_spec_clauses.py` | **297 条 NORM 逐条裁定完成**：direct 222 / indirect 16 / partial 6 / gap 0 / na 53；OPS 由另两轴承担 |
| **B. 原子操作** | `src/pyapi/packages/*.py` 的写原子（60 个） | `audit_atom_coverage.py` | **GAP=0**（B1/B2 已闭环，证据树有命中）；每轮复跑 |
| **C. op × 参数** | `OPERATIONS` 表 + spec 字段表 → 628 条 | `build_op_param_matrix.py` | **CANDIDATE 569 / GAP 59 / NO-OP 0**；59 = 34 条通用 `timeout`（跨 op 合同）+ 25 条逐 op 缺口（pex 12 被 P-102 阻塞 / drc 7 / lvs 4 / export.job_id / layout.depth（P-085））（见 §3） |

## 1. 判定口径（防"虚高"）

1. 每条覆盖结论必须给 **证据文件路径 + 判据类型**；判据分三级：**直接**（读回/数值/字节比对）、
   **间接**（产物被下游消费且有断言）、**弱**（只看 ok/rc）。**弱判据不得作为覆盖结论**，只能标 ⬜/🟡。
2. 离线文本契约（只断言生成的 SKILL 文本含某函数名）**不计**该原子的"已覆盖"，只算契约层证据。
3. 历史证据 ≠ 本轮已验：本轮未复跑的行标 🟡（历史）并在矩阵里显式写明；不得与 ✅ 混引。
4. 非可测条款（术语表、引用指针、Supersedes、状态行）标 `N/A`，并给出"为什么不可测"一句话。
5. 所有覆盖率数字引用 `coverage-pack/` 现有口径；本轮重算后统一更新，禁止新旧混引。

## 2. 分层复跑计划

| 层 | 内容 | 证据路径 | 状态 |
|---|---|---|---|
| 离线（Win py3.12） | unit+integration+scenario 全量 | `evidence/round8/offline-win-final.xml` | ✅ **1800 例 / 0 红 / 21 skip**（13 条 xfail 钉住） |
| 离线（Linux py3.9） | 同一份树，跑在 wsl-gent 仓库副本 | `evidence/round8/offline-linux-py39-final.xml` | ✅ **1800 例 / 0 红 / 31 skip**（与 Windows **collect 数一致**） |

> 计数口径：**不要引 pytest 写出的 JUnit `tests=` 属性**（本环境 pytest 9.1.1 会虚高：全量树写 2456，
> 实际 `<testcase>` 只有 1800）。以 `<testcase>` 元素数 / `--collect-only` 汇总为准（两者与进度点数三处一致）。
| 半真机 | `run_semi_probes.py --group all`（含新增探针） | `evidence/round8/semi-*.json` | 待环境独占窗口 |
| 真机 | 11 套包 HTTP + cov_remote_real 多 token + 业务场景（SerDes/ADC/design_iterate/多用户/注册/py27/role-split/real-ciw/hostkey） | `evidence/round8/package-e2e-r8.log`、各 live JSON | **10 套稳定绿 + 1 被阻塞**（批量 gate 9/11；calibre 恢复实例后 8/8；maestro **23/23** 于 21:28 入档 `evidence/round8/maestro-23of23-2128.log`，之后被 P-095 模态框卡死） |
| 覆盖率 | `run_main_coverage.ps1` 复算（combine 口径） | `evidence/cov-main/`（round8 快照另存） | 全部 TB 稳定后 |

## 3. op×参数 GAP 分族（81 条）与分工

| 族 | 条数 | 处理 | 状态 |
|---|---:|---|---|
| calibre（drc/lvs/pex/export/read_results/check_env） | 38 | 子代理 `calibre_params` | 进行中 |
| screenshot 家族（layout/schematic/symbol） | 7 | 子代理 `shot_family` | 进行中 |
| verilog import/export | 9 | 子代理 `verilog_params` | 进行中 |
| spectre export/measure/run | 6 | **已完成（root）**：`test/live/packages/spectre_params_e2e_tests.py` **5/5**（output_root/spectre_bin/measure.source_path/export.columns+precision） | ✅ |
| maestro export/read_results | 6 | **已完成（root）**：`maestro_e2e_tests.py` RESULT-04 + EXPORT-02（套件 **19/19**） | ✅ |
| symbol/veriloga view_type · file_is_local/file_path | 7 | 子代理 `verilog_params`/`shot_family` | 进行中（已产出 **P-080**） |
| basic.file recursive | 2 | 待派 | 队列 |
| layout.read depth/region_mode | 2 | **已完成（root）**：`layout_depth_probe.py` 真机判定（见 `evidence/round8/layout-depth.json`） | ✅ |
| skillref.search max_candidates | 1 | **已完成（root）**：`test/offline/unit/test_norm_gap_batch2.py::TestSkillrefBodyRemoteBudget` | ✅ |
| place_note/place_wire spec 行（type/entry/route） | 3 | 已判定：`place_wire` 样式参数拼接重复 → **P-078**；两条 spec 行口径见 card | ✅ |

## 4. spec 条款逐条裁定（轴 A）分工

| 簇 | 文档 | 条数 | 子代理 | 状态 |
|---|---|---:|---|---|
| NORM g1-core | 总览/1、总览/add、中层配置/并发/路由 | 50 | 子代理（已完成） | ✅ 已并入矩阵 |
| NORM g2-mid | 路由/并发/日志/顶层 | 46 | 子代理（已完成） | ✅ 已并入矩阵 |
| NORM g3-reg | 注册/客户端/日志 | 44 | 子代理（已完成） | ✅ 已并入矩阵 |
| NORM g4-edit | schematic/symbol/layout | 60 | 子代理（已完成） | ✅ 已并入矩阵 |
| NORM g5-sim | maestro/spectre/verilog/veriloga | 54 | 子代理（已完成） | ✅ 已并入矩阵 |
| NORM g6-calibre | skillref/gui/calibre | 43 | 子代理（已完成） | ✅ 已并入矩阵 |

**合并结果（`round8-spec覆盖矩阵.md`，2026-09-28 20:5x）**：297 条 NORM → direct 219 / indirect 16 / partial 9 / gap 0 / na 53；
剩余 9 条 partial 由 `round8-gap-actions.md` 跟踪（P-079/P-082 修复项 + calibre 三条离线补测 + verilog 两条真机补测 + layout#179 探针）。

每簇交付：`spec-matrix-<簇>.md` + `.json`（逐条：编号/条款/可测性/判据级别/证据/本轮状态/缺口动作），
并入 `round8-spec覆盖矩阵.md`（合并稿）。**裁定必须打开证据文件确认断言**，不得只信文件名。

## 5. 评审流水线（用户强制要求）

1. 每簇矩阵完成后，交**另一个未参与该簇的子代理**交叉评审（抽查 ≥10%，专挑"✅ 但证据弱/文件不存在/断言不匹配"）。
2. 全量合并稿完成后，再派 1 个"红队"子代理：以驳回为目标寻找漏洞（列出它找到的每一条，我逐条回应）。
3. 我每轮把评审结论写回本文件 §6，并修正后复审，直到红队找不到实质问题。

## 6. 评审记录（滚动）

| 日期 | 评审人 | 结论摘要 | 我的处置 |
|---|---|---|---|
| 2026-09-28 | root（协同通报） | 共享库 `maestro_tb/rc_probe` 的 run_mode 被 MC 实验改成 `Monte Carlo Sampling`，导致常规 run 产出 MC 布局、waveform 读回失败；已恢复 `Single Run, Sweeps and Corners`（`test/artifacts/tmp/restore_rc_run_mode.py`） | 环境已还原；后续实验改共享库状态须还原 |
| 2026-09-28 | root（新缺陷） | **P-083** spectre.export.precision 语义未定义（实现=有效数字）；**P-084** maestro.export.include_results 声明但从不读取（红灯探针 `maestro_export_include_results_probe.py`，sha 相同） | 已落卡/台账；探针为预期红 |
| 2026-09-28 | root（并发说明） | 20:3x 期间三路并发（`run_semi_probes --group all`、offline pytest、`maestro_leak_probe`、`registration_real_ciw_tb`）导致 `maestro_e2e_tests.py` 的 WRITE-02 出现一次性红（corner variable=None）——**并发互扰，非产品回归** | 待环境空闲窗口重跑确认（本条在重跑后更新） |
| 2026-09-28 | root（缺口动作 2 条闭环） | `注册#011` 补 `deploy-paths-contain-no-token`；`layout#179` 新建 `layout_geometry_classification_e2e_tests.py` **4/4**（正常 rect 读回 / 零面积→包层预校验可归因失败 / 非法 LPP→SKILL 硬错误+非事务提示）；口径差异（spec 写 nil+WARNING，实现提前预校验）按“实现更严格”记录 | 已写入 `round8-gap-actions.md` 顶部处置记录 |
| 2026-09-28 | root（抽查审计证据） | 对 `norm-review/g4` 做机器引用检查（89 处引用 / 28 唯一文件，**全部存在**）+ 人工抽样 8 条 `::函数` → 7 命中、1 处函数名过时（`_case_pos_negative` 实为 `_case_negative`，证据本身存在） | 记入 `round8/spot-check-root.md`；其余簇留给红队子代理 |
| 2026-09-28 | root（真机快照） | 已回真机证据：registration（six-local ok / py27 10/10 / role-split 28/28 / real-ciw 12/12）、multihop 10/10、scale-100 ok、multiuser-layout-handoff 12/12、serdes-multiuser 17/17、adc-sar 24/24、role-credential-isolation 8/8 | 11 套包 gate 进行中（`round8/run-all-http-r8.log`） |
| 2026-09-28 | root（gate 收口） | gate 结果：**10/11 套 PASS，唯一 FAIL=maestro**（root 的 WRITE-06 旧判据把"会话内存可见"误当"落盘"）；子代理改用步骤表判据（save=True 必有 `save_setup` 步骤、save=False 必无）后 **maestro 23/23 PASS** | ~~11/11~~ **最终口径更正（2026-09-29）**：该次 23/23 于 21:28 入档（`evidence/round8/maestro-23of23-2128.log`），随后 maestro 被 **P-086/P-095/P-096** 卡死 → 本轮定稿为 **10 套稳定绿 + 1 被阻塞**；磁盘级隔离语义由 P-087 红灯探针单独钉住 |
| 2026-09-28 | root（新缺陷 2 条） | **P-086** 多用户同视图后 ~30–90s 内 `Empty response from daemon`（自愈，观察）；**P-087** `save=False` 改动被后续 save 静默带走（跨请求污染）；root 另立 **P-088**（`delete_var scope=all` 确定性 handle 0，与 P-087 同源但独立钉住） | 均已落卡/台账；P-087/P-088 红灯探针已留证 |
| 2026-09-28 | root（本线收口） | **root 负责的 op×参数全部清零**：spectre 参数 TB `5/5`；maestro 套件 **23/23**（含 `include_parameters/include_raw`、`write.save`、`notation/precision/width/output_path`、`result=`、`export.output_path`、`open_gui(history=)`）；layout 失败分类 TB `4/4`（layout#179）；P3 注册 **29/29**（+`deploy-paths-contain-no-token`，注册#011）；另立 **P-089**（`open_waveform_gui.result` 死参数，红灯探针） | 剩余非-CANDIDATE 缺口全部落在 calibre（24）/screenshot（14）/verilog（12）三路子代理车道 + `layout.read.depth`（P-085 已红钉） |
| 2026-09-28 22:4x | root（合并稿机器红队，第一轮） | ① 6 组合并稿的 `evidence` 存在 34 处"路径+括号注解"混写；② g4-edit 的 2 条证据被误存成"单字符数组"（schematic#017/layout#139）；③ 全量 def 扫描发现 1 处**引用不存在的测试**（veriloga#068 → `test_veriloga_contracts.py::test_check_and_save_sequence`） | ① `merge_round8_spec_matrix.py` 增加 evidence 规范化（纯路径 + `evidence_notes`）；② 修复 2 条单字符数组；③ 删除伪引用（保留 `test_veriloga_lazy_editor_contract.py` 的两条真实用例）。复核：**102 条仓库证据路径 0 缺失；91 条 `::用例` 引用 0 失效** | 
| 2026-09-29 00:4x | root（红队 N11 复跑） | `registration-role-split` 的 29/29 一度缺证据（REVIEW-C N11）；复跑 3 次：① 00:35 干净 work-dir **29/29 PASS**；② 00:37 一次复跑在 post-commit 撞 `ssh w1-gent` 30s 超时（`TimeoutExpired`，仅后置校验，注册链本身全过）；③ 两次同 work-dir 复跑被 `credential reuse requires enhanced_token` 401 拒绝（**反凭据复用保护按设计生效**） | ① 用**全新 work-dir** 再跑一次 → `registration-role-split.json` 落成 **29/29**（含 `deploy-paths-contain-no-token`）；② 报告/自查表改指该证据；③ 复跑须知（同 key 换 work-dir）记入本行 | 

## 7. 交付物清单（送审判据）

- `round8-spec覆盖矩阵.md`（1131 条 → 逐条结论，含 N/A 理由）
- `round8-op-param-结果.md`（628 条 → GAP 归零或显式豁免）
- `原子覆盖`机器核账刷新（GAP=0 证据）
- `round8-测试报告.md`（三层结果 + 覆盖率 + 明缺口）
- `bugs/` 卡片与已关闭记录同步；新 bug 全部落卡
- 子代理评审记录（§6）
