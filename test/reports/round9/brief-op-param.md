# round9 任务书 B：op×参数矩阵刷新（静态 + 半静态核账）

> 执行者：subagent（`/root/opparam_r9`）｜下发：测试/root，2026-09-29
> 产出：`test/reports/round9/op-param-r9.md`（+ JSON 若脚本产出）

## 背景
第八轮 op×参数矩阵 628 行：CANDIDATE 572 / **GAP 56**。此后：
- C1 契约变更（顶层 `value`/`result`、`steps` 仅 `step_details`/失败时出现、**新增请求字段 `step_details`**、
  JSON 出口 `log`→`CDSlog`）；
- C2 落地（**所有 Skill Request 新增 `log_level`/`log_max_bytes`**，56 个 Request 类）；
- C4：`CommandResult` 改 pydantic（`returncode/stdout/stderr/kind`）；
- P-092 删 calibre `power`/`ground`；P-070 补 MC 17 项 run option；P-105 screenshot `view_type` 参与校验。

## 任务
1. 找到并复用仓库现有的矩阵生成脚本（`test/shared/runners/` 下，如 `gen_op_param_matrix.py` /
   `merge_op_param*.py`，以实际存在为准；`test/reports/round8/op-param-matrix.json` 是上一轮产物）；
2. 从**当前代码**重新抽取 op 清单与每个 op 的可传参数（Request 模型字段），生成新矩阵，逐行标：
   **CANDIDATE（有 TB 传过该参数） / GAP（没有任何 TB 传过） / N-A（字段已删或非用户可传）**；
3. 重点核对本轮新增/变更参数是否被 TB 覆盖：
   `step_details`、`log_level`、`log_max_bytes`、`CDSlog`（输出）、`CommandResult` 四字段、
   screenshot `view_type`、maestro MC 的 17 项 run option、calibre 已删的 `power/ground`（应标 N-A）；
4. 产出 GAP 清单：每条给 `op`、`参数`、`为什么算 GAP`、`建议补在哪条 TB`。

## 硬约束
- **只读**：不得改 `src/`、`test/`（报告写入 `test/reports/round9/`）；
- 允许跑**纯离线**脚本/`pytest test/offline -q`（不得调 8127 / 真机）；
- 不得把"离线契约里出现过字段名"当成"真机覆盖"——按第八轮口径区分 CANDIDATE/GAP。

## 交付
- `test/reports/round9/op-param-r9.md`：① 总数/分布；② 与 round8 的差异（新增/消失/改判定）；③ GAP 清单；
  ④ 建议的 TB 补点（按优先级排序）；⑤ 你无法判定的行（列出来）。
