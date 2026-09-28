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
