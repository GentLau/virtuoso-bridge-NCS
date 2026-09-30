# round9 · op × 参数矩阵刷新报告（工作线 B）

> 执行：subagent `/root/opparam_r9`｜下发：测试/root｜2026-09-29
> 口径：复用仓库现有脚本 `test/shared/runners/build_op_param_matrix.py`（AST 解析，v2），
> 只读（未改 `src/`、未改任何既有 TB）；本报告与机器产物写在 `test/reports/round9/`。

## 0. 产物

| 文件 | 说明 |
|---|---|
| `op-param-matrix.json` / `op-param-matrix.md` | 本轮机器矩阵（811 行，脚本重跑） |
| `op-coverage.json` | 每个 op 的调用点/文件清单 |
| `op-param-classification.json` | **本报告的核心**：240 条非 CANDIDATE 逐条分类（class + 依据 + 证据） |
| `evidence-contract-tbs.txt` | 三份跨切合同 TB 的现跑输出（18/18 通过） |
| `spec-op-drift.md` / `.json` | 顺手跑的 spec↔实现 op 漂移核对（归 A 线，仅参考） |

> 注：脚本 `OUT` 常量原指向 `test/reports/round8/`。本轮用「导入模块 + 覆写 `OUT`」方式重跑，
> 未改动 round8 既有产物（首跑误覆盖的 3 个 round8 文件已用 `git checkout` 还原，现为干净状态）。

## 1. 数字（当前代码）

- 实现 `OPERATIONS`：**79 个 op**；spec 原子表：**34 个原子 op**
- 矩阵 **811 行** = request 层 **736 行**（79 op；CANDIDATE **496** / GAP **240**）+ 原子层 **75 行**（全 CANDIDATE）
- `NO-OP-TB` = **0**（所有 op 至少有一条 TB 调用点）
- 未解析调用点 **99** = 管道行 80（op 载体内部转发形参）+ 待人工复核 **19**（详见 §5.2）
- 跨切字段覆盖面：`step_details` 挂在全部 **79** op；`log_level` 挂在 **56** 个 skill 型 op；`timeout` 挂在全部 **79** op

## 2. 与 round8 的差异

对比 `test/reports/round8/op-param-matrix.json`（628 行）：

| 维度 | 数量 | 明细 |
|---|---|---|
| 新增 (op,param) | **191** | GAP 186 + CANDIDATE 5 |
| 消失 (op,param) | **8** | 见下 |
| 状态变化 | **16** | 9 条 pex 参数 `CANDIDATE→GAP`（PEX 停用后 TB 改为只测 `pex_unsupported`）；7 条 `GAP→CANDIDATE`（calibre.status/maestro/ layout.read/screenshot 的 `timeout` 等） |

**新增的 186 条 GAP** 全部来自跨切字段：`step_details` 77 + `log_max_bytes` 55 + `log_level` 54（C1/C2 引入的响应开关与日志选项，见 §3.1）。

**新增且已 CANDIDATE 的 5 条**：`basic.skill.execute` 的 `log_level`/`log_max_bytes`、`virtuoso.maestro.read_config` 的 `log_level`/`step_details`、`virtuoso.maestro.write` 的 `step_details`。

**消失的 8 条**（字段已从实现删除，属预期）：

| 条目 | 出处 |
|---|---|
| `calibre.drc/lvs/pex` 的 `power`/`ground` | P-092 裁决：字段已删 |
| `virtuoso.maestro.export.include_results` | P-084 裁决：字段已删 |
| `virtuoso.maestro.open_waveform_gui.result` | P-089 相关：实现里 `OpenWaveformRequest` 已无 `result`（`history`/`analysis`/`test` 保留） |

## 3. 非 CANDIDATE 240 条的去噪分类

机器矩阵的 240 条 GAP **不是 240 个测试缺口**。逐条分类结果（机器可读见 `op-param-classification.json`）：

| 分类 | 条数 | 判据与承担者 |
|---|---|---|
| `CONTRACT_STEP_DETAILS` | **77** | 全局响应开关：`src/pyapi/models.py::_finalize_step_details` 包在 `ResultPackage` 子类上（79 op 通吃）；离线合同 `test/offline/unit/test_result_contract.py`（8 用例：成功省略 / `step_details=true` 保留 / 失败恒保留 / 域包同规则） |
| `CONTRACT_LOG_OPTIONS` | **109** | `log_level` 54 + `log_max_bytes` 55；56 个 skill 型 Request 的跨切字段。离线合同 `test/offline/unit/test_skill_log_options.py`（逐 op `subTest` 枚举 `__dataclass_fields__`，`checked>40`）+ 透传样本（basic + 域 op + 顶层 build）；真机 `test/live/packages/skill_log_options_e2e_tests.py`；半真机 `test/semi/transport/log_matrix_real_tb.py` |
| `CONTRACT_TIMEOUT` | **29** | 跨 op 通用字段；离线合同 `test/offline/unit/test_param_timeout_contract.py`（79/79 op 枚举）+ `test_all_ops_timeout_field.py` |
| `NA_PEX_UNSUPPORTED` | **17** | `calibre.pex` 全部参数：spec §4.4「本版不提供 PEX 启动」+ 实现 `calibre.py:425-433` 在 `_run` 前返回 `pex_unsupported`（请求仍按 `RunRequest` 校验，spec:219） |
| `INERT_PEX_ONLY_FIELD` | **4** | `calibre.drc`/`calibre.lvs` 的 `fmt`、`lvs_run_dir`：唯一行为读取点在 PEX 分支（`calibre.py:499`、`1029-1030`）→ 对 drc/lvs 是惰性字段（**见 §4 待办 1**） |
| `NA_KIND_LVS_ONLY` | **3** | `calibre.drc` 的 `hcell_file`/`spice_file`/`xcell_file`：`_argv_for` 只在 `kind=="lvs"` 追加 `-spice/-hcell/-xcell`（`calibre.py:1017-1023`），spec:188 同口径 |
| `NA_KIND_LEGACY_CDL` | **1** | `calibre.drc` 的 `cdl`：经 `deck_rewrite(gds, top, cdl)` 参与占位符替换（`calibre.py:848-850`），语义属 LVS 源网表 |
| **真 TB 缺口（UNDECIDED）** | **0** | — |

跨切合同三件套本轮现跑：**18/18 通过**（`evidence-contract-tbs.txt`）。

### 3.1 任务书点名的重点字段（逐项核对）

| 重点项 | 矩阵可见性 | 结论 |
|---|---|---|
| `step_details` | 顶层字段（79/79 op） | 由全局装饰器生效 + 离线合同覆盖；**非缺口** |
| `log_level` / `log_max_bytes` | 顶层字段（56 个 skill op） | 离线合同逐 op 枚举 + 真机/semi 样本；**非缺口** |
| `CDSlog`（响应字段） | **矩阵盲区**（不是请求参数） | 归 C 线（`skill_log_semantics_e2e_tests.py` 红钉 + C06）；本报告不重复 |
| `CommandResult` 四字段 | **矩阵盲区**（响应形状） | 离线 `test_result_contract.py`：`test_command_result_is_a_named_model` / `test_command_result_json_is_named_object` / `test_basic_command_result_and_step_detail_are_named_objects`（3 用例，本轮同批 18/18 绿） |
| screenshot `view_type` | 顶层字段 | `virtuoso.symbol.screenshot` / `virtuoso.layout.screenshot` 均 **CANDIDATE**（P-105 的 TB 已传）；`virtuoso.schematic.screenshot` 无该字段（13 参，符合 spec） |
| maestro MC 17 项 run option | **矩阵盲区**（嵌在 `maestro.write` 的 `commands[].*` 里，不是顶层参数） | 由 `test/live/packages/maestro_mc_e2e_tests.py`（MC-01..07，含 17 项写→读回 + 非法值拒绝 + 8 点真实 MC）承担；建议后续版本把这类嵌套键纳入矩阵或单独出一张「嵌套键覆盖表」 |
| calibre 已删 `power`/`ground` | 已从实现消失 | 矩阵 8 条"消失"里占 6 条（drc/lvs/pex × 2），与 P-092 一致 → 标 N-A |

## 4. 需要决策/补文档的 2 项（不是 TB 缺口）

1. **`fmt` / `lvs_run_dir` 的适用范围**（`calibre.drc` + `calibre.lvs` 各 2 条）：
   两个字段都被 `RunRequest.__post_init__` 校验、并回填进 `meta`，但对 drc/lvs **不产生任何行为差异**；
   唯一读取点在 PEX（本版不可达）。这与 P-092（`power`/`ground`）同族。
   建议设计二选一：① spec 写明「`fmt`/`lvs_run_dir` 仅 PEX（本版不可用），drc/lvs 上为保留位」→ 矩阵标 N-A；
   ② 在 drc/lvs 路径删除/结构化拒绝这两个字段（与 P-092 同款处理）。
2. **跨切字段的覆盖口径应写进规范**：`step_details`/`log_level`/`log_max_bytes`/`timeout` 由跨 op 合同 TB 承担，
   不逐 op 真机传参。建议在 `test/docs/写TB规范.md` 记一句，并让矩阵脚本把 4 类字段标 `CONTRACT`（脚本已有 `generic` 机制，扩展即可），
   否则每轮都会重演「211 条逐 op 缺口」的误读，也容易被评审判成"覆盖不完整"。

## 5. 未解析调用点（99）

### 5.1 管道行 80

`_op`/`_call`/`_value` 之类的 TB 内部载体把形参转发，真值已在调用点解析，**不构成漏测**。

### 5.2 待人工复核 19（逐条已看）

- `test/offline/core/api_server_tb.py` 6 处、`test/offline/unit/test_top_layer_dispatch.py` 6 处、
  `test_middle_contracts.py:167`、`test_param_timeout_contract.py:174`、`test/shared/fixtures/probe.py:24`：
  payload dict / helper 里的 op 是运行期变量，实参只有 `token`/`value`/`timeout` 这类无 op 归属意义的字段 → **不影响本矩阵结论**。
- `test/offline/unit/test_norm_gap_batch2.py:257`：动态 op 是 `skillref.search.probe`（**不存在的 op 名**），测的是未知字段拒绝负例 → 不是真实覆盖。
- `test/semi/probes/calibre_package_http_probe.py:111`、`test/live/packages/calibre_e2e_tests.py:131`：`f"calibre.{kind}"` 同一 helper 覆盖 drc/lvs/pex 三 kind，
  静态不可归属（实参仅 `token`）。
- `test/live/packages/cellview_e2e_tests.py:277`：`_expect_fail(operation, ...)` 负例 helper。

**结论：19 条没有隐藏任何"参数覆盖"**。改进建议（非缺陷）：TB 里 op 名尽量写成显式字面量，便于下轮机器核账。

## 6. 我无法判定 / 未覆盖到的

1. **CANDIDATE ≠ 断言语义**：本矩阵只证明"参数名出现在调用点"，不证明 TB 断言了该参数的效果；
   断言强度是另一条工作线（`brief-weak-assert.md`）。
2. **跨切字段的逐 op 真机透传**未逐 op 验证（只有模型级枚举 + 样本透传 + 真机 6 例）。若评审要求"79 个 op 每个都真机传一次 log_level"，
   需要设计侧先确认口径（见 §4.2），否则会产出 100+ 条低价值真机用例。
3. **spec 与实现的 calibre 漂移**（归 A 线，我未复核）：
   - spec `12-calibre.md §4.3`（`calibre.lvs`）列了 `source`/`emit_cdl`/`cds_lib` 三个参数，实现 `RunRequest` 中**不存在**（实现走 `cdl`/`spice_file`/`hcell_file`/`xcell_file` + 独立的 `calibre.export_cdl` op）；
   - `calibre.export_cdl` 在 spec `design-concepts/` 下**没有任何 §4 小节**（只在 `spec/research/calibre/` 里出现），但它是实现里的正式 op 且有真机 TB。
   - 顺手跑的 `check_spec_op_drift.py`：实现 79 / spec op 标识 42 / SPEC-ONLY 17 / IMPL-ONLY 54（**启发式口径，需 A 线判定**），产物 `spec-op-drift.md`。
4. `calibre.export_cdl` 的 `log_level`/`log_max_bytes` 确实被消费（`calibre.py:343-344` → `818-820` 传给内部 CIW skill 调用），
   且 `test_skill_log_options.py` 白名单里显式包含它 → 按设计口径记录，未判为缺陷。

## 7. 建议的 TB 补点（按优先级）

| 优先级 | 动作 | 说明 |
|---|---|---|
| P1 | **0 条真缺口**，无需为参数覆盖补 TB | 240 条已全部归类：215 合同 + 25 N-A/惰性 |
| P1 | 把 §4.1 的 `fmt`/`lvs_run_dir` 送设计确认 | 决定"spec 声明"或"删字段"，随后矩阵标 N-A |
| P2 | 矩阵脚本把 `step_details`/`log_level`/`log_max_bytes` 纳入 `generic`（标 CONTRACT） | 让下一轮报表直接反映真实缺口 |
| P2 | `test/docs/写TB规范.md` 记一句"跨切字段由合同 TB 承担" | 对齐评审口径 |
| P3 | TB 里 op 名字面量化（消除 19 条动态 op） | 只影响机器核账可读性 |
| P3 | 若评审坚持逐 op 真机日志透传：优先补 `layout.write`、`schematic.create`、`maestro.run` 三个高频 op 的 `log_level=off/all` 真机两档 | 最小增量、最大说服力（56×2 全量不划算） |
