# root 对同期审计结论的抽查（2026-09-28 21:1x）

> 目的：评审"审计本身的证据引用是否真实"。方法：对 `norm-review/g4-edit.md` 的全部引用做**机器存在性检查**，
> 再人工抽样核对函数名与断言。

## 1. 机器检查（g4-edit）

- 引用条目 89 处 / 唯一 28 个 → **被引文件全部存在**（0 个不存在）。
- 带 `::函数名` 的抽样 8 条：7 条命中、**1 条不匹配**。

## 2. 发现的不匹配

| 引用 | 实际 | 处置 |
|---|---|---|
| `test/live/packages/schematic_e2e_tests.py::_case_pos_negative` | 实际函数名为 `_case_negative`（`schematic_e2e_tests.py:350`，内容正是"`xy`/拆字段必须被拒且点名 `pos`"） | 引用名过时，**证据本身存在且更强**；合并稿时把引用改为 `_case_negative`（已记，不改 agent 正在编辑的文件） |

## 3. 抽查（人工打开 TB 确认断言）

| 条款 | 引用 | 核对结果 |
|---|---|---|
| schematic#006（原子读写对称） | `test_schematic_contracts.py` + `schematic_e2e_tests.py` | ✅ 离线契约 + 真机原子用例（instance/wire/label/pin/note 的 place/delete/rename/set 均有 read 回读） |
| schematic#014/#015（object_filter all/none/names/region） | `test_schematic_contracts.py::test_instance_filter_all_none_names_region` | ✅ 函数存在，覆盖 all/none/names/region 与非法输入 |
| layout#179（失败分类） | —— | 原评"partial"→**本轮已补**：`layout_geometry_classification_e2e_tests.py` 4/4（见 `round8-gap-actions.md`） |
| 注册#011（token 不得出现在用户可读路径） | —— | 原评"partial"→**本轮已补**：`registration_role_split_tb.py::deploy-paths-contain-no-token` |

## 4. 结论

- 抽查未发现"引用不存在/断言缺失"的严重问题；发现 1 处**函数名过时**（证据真实存在）。
- 该抽查仅覆盖 g4 一簇 + 两条缺口动作；**其余簇（g1/g2/g3/g5/g6）与 op×param 矩阵仍需红队子代理按同法抽查**（见 `README.md` §5 流水线）。

## 5. 扩到的全簇机器核账（2026-09-28 21:4x）

把同样的检查扩到 **g1–g6 全部 436 处引用**：

- 文件不存在：**0**；
- `::函数名` 不匹配：**2**：
  1. `g4-edit.md` → `schematic_e2e_tests.py::_case_pos_negative`（实际 `_case_negative`，证据真实存在，仅名字过时）；
  2. `g5-sim.md` → `test_veriloga_contracts.py::test_check_and_save_sequence` —— **实际不存在**；
     且全仓 `rg -n "ahdlCheckModule|ahdlSaveFile|ahdlEdit" test/` 在**测试代码里零命中**（只命中 round8 报告自身），
     即 `veriloga#068/#096` 标注的"生成式缺席断言"**目前没有测试**（产品源码里同样不出现这三个函数＝实现满足约束，
     但缺"断言其不出现"的用例）。

**处置**：① g4 的函数名过时 → 合并稿时改为 `_case_negative`；② veriloga#068/#096 → 状态下调为 🟡，
并列入"缺口动作"（补离线生成式缺席断言）；已通知 verilog/veriloga 车道的子代理。

**闭环更新（2026-09-28 22:44）**：

- ① 已修：`norm-review/g4-edit.json` 中 `schematic#048` 证据改为 `schematic_e2e_tests.py::_case_negative`，
  重新合并后 `merge_round8_spec_matrix.py` 的路径/函数校验通过。
- ② 已补：车道交付 `test/offline/unit/test_veriloga_lazy_editor_contract.py`（含
  `test_check_and_save_sequence_and_absence`：对 `FORBIDDEN_CALLS=(ahdlCheckModule, ahdlSaveFile, ahdlEdit)`
  逐一 `assertNotIn` 生成文本；`test_write_ops_do_not_touch_view_info`；`test_cold_context_uses_full_path_load_context`）。
  `veriloga#068/#096` 证据已回填该文件，verdict 维持 direct（有真实断言）。
  全仓 `rg "ahdlCheckModule|ahdlSaveFile|ahdlEdit" test/` 现在命中该专测。

## 6. 第二轮人工抽查（2026-09-28 23:5x，语义级）

上一节的机器检查只能保证"引用存在"，**不能保证"引用的用例真的断言了该条款"**。
本轮抽 5 条（覆盖 g1–g6 各簇）人工读断言，**发现 2 条判据强度不足**：

| 条款 | 原引用 | 抽查结论 | 处置 |
|---|---|---|---|
| 日志#035（读精确区间 / 轮转后从头读） | `test_daemon_log_contract.py::test_reads_exact_interval`、`::test_rotated_file_reads_from_zero` | ✅ 直接断言 `_read_range` 返回值与 warning 语义 | 无需动作 |
| 注册#071（凭据复用需任一 holder token） | `test_registration_server_edges.py::test_credential_reuse_requires_enhanced_token` | ✅ 用例自带 registry + server，走真实注册流程 | 无需动作 |
| calibre#128（pex 内部固定顺序三段） | `test_calibre_argv_contracts.py::test_pex_runs_two_stages` | ✅ 逐段 argv 精确比对 | 无需动作 |
| **symbol#053**（新建原子 layer/purpose 必填、不设默认层） | `test_symbol_contracts.py`（理由写的是"缺 layer 即 ValueError"） | ❌ **原文件里只有"生成文本带 layer/purpose"与通用 `_require_text` 用例，没有"缺 layer 即报错"的直接判据** | ✅ 已补 `TestSymbolAtomicMatrix::test_new_shape_atoms_require_layer_and_purpose`（缺 layer/purpose → ValueError 且点名字段；并加 `delete_shape`/`set_shape_properties` 反向对照）；已回填 `g4-edit.json` |
| **spectre#041**（不生成随机路径，同 job 定位同 run_dir） | `test_spectre_contracts.py` | ❌ **原文件没有 run_dir 确定性判据** | ✅ 已补 `TestRunOrchestration::test_run_dir_is_deterministic_per_job`（两次调用同 run_dir、形如 `<role root>/spectre/<job>`、无随机/时间戳分量）；已回填 `g5-sim.json` |

**两条补钉均已实跑转绿**（`pytest test/offline/unit/test_symbol_contracts.py
test/offline/unit/test_spectre_contracts.py -q` → 97 passed）。

**结论**：5 条抽查里 **2 条（40%）判据强度不足**——说明"文件存在"不等于"断言存在"，
该风险只能靠逐条读断言发现。**这正是红队必查清单 §1/§2 要覆盖的范围**，
红队请按同一口径对 g1–g6 各簇再抽 ≥4 条/簇（共 ≥24 条）。

### 6.1 追加抽查（g1/g2 簇，2026-09-29 00:0x）

| 条款 | 引用 | 抽查结论 | 处置 |
|---|---|---|---|
| 总览#196（临时落盘 → SHA 校验 → 原子替换 / 失败回滚 / 覆盖） | `test_transfer.py`、`test_tunnel_transfer.py` | ✅ `test_fresh_file_install` / `test_replace_existing_file_removes_backup` / `test_failure_rolls_back_previous_target` / `test_directory_install_rolls_back_when_new_tree_fails` / `test_install_staged_path_wrapper` / `test_discard_stage` 逐条对应 | 无需动作 |
| 注册#006（启动导入一次、运行期不自动读文件、显式 reload 生效） | `test_registry_decoupling.py`、`test_supervisor_process.py` | ✅ `test_explicit_reload_refreshes_registry_snapshot` + supervisor 端到端 | 无需动作 |
| **总览#215**（role `root` 是默认目录约定、**不是沙箱**） | `test_local_path_expansion.py`（原只有 `~` 展开两条）、`test_transfer.py` | ⚠️ **原引用没有"绝对路径不被拦截"的正面判据**（`test_transfer.py::test_invalid_remote_path_raises` 只覆盖非法入参） | ✅ 已补 `TestLocalTildeExpansion::test_root_is_default_dir_not_a_sandbox`（相对→落 root；绝对且在 root 之外→允许；`..` 按 OS 语义）；已回填 `g1-core.json` |

追加 3 条里 1 条不足 → **累计抽查 8 条，3 条（37.5%）判据强度不足，均已补钉并转绿**。
该比例说明：**"引用存在"与"断言到位"是两件事**，矩阵的 `direct` 标签必须靠逐条读断言复核，
不能靠机器核账代替。红队请把这条当作本报告最需要证伪的结论之一。
