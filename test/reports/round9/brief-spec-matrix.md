# round9 任务书 A：spec 条款矩阵刷新（只读审计 + 报告）

> 执行者：subagent（`/root/spec_matrix_r9`）｜下发：测试/root，2026-09-29
> 产出：`test/reports/round9/spec-matrix-state.md`（+ 机器可读 JSON 若脚本产出）

## 背景
第八轮矩阵：297 条 NORM → direct 222 / indirect 16 / partial 6 / na 53 / **gap 0**。
此后代码发生了这些**可能影响条款结论**的变更（都已提交）：
- `2f88853` C1 响应契约：业务结果本体直返（顶层 `value`/`result`）、失败两字段壳、`steps` 按 `step_details` 出现、JSON 出口 `log`→`CDSlog`、删 `metadata`、`execution_time` 三位小数；
- `977a985`/`e8a0d5b` C4：`CommandResult` 改 pydantic（命名字段）；
- `c70e2c5`/`0b9fec3`：P-070 MC 17 项 run option、P-092 删 `power/ground`、P-093/094 flat DRC/秒退、P-098 timeout 口径、P-105 screenshot `view_type` 校验；
- 还新增了 `C06`（CIW print 未 flush）与 C2（`log_level`/`log_max_bytes` 请求字段）两个面向。

## 任务
1. 用仓库现有工具重新核账（先 `ls test/shared/runners` 找准脚本名，例如 `merge_round8_spec_matrix.py`、
   `check_tb_headers.py`、`audit_atom_coverage.py`；不要重造轮子）：
   - 重新生成/校验 spec 条款覆盖矩阵；
   - 找出**因上述变更而结论失效**的条款（尤其：响应形状、错误壳、steps、CDSlog/log、
     CommandResult 形状、calibre power/ground、MC、screenshot view_type、request 可选参数）；
2. 对每条"结论可能失效"的条款：打开对应 spec 原文 + 对应 TB，给出 新结论/依据路径；
3. 汇总仍有 **gap / partial** 的条款清单（含"为何仍 partial、建议补哪条 TB"）。

## 硬约束（违反即失败）
- **只读**：不得修改 `src/`、`test/` 下任何文件（报告写到 `test/reports/round9/` 可写）；
- 不跑真机（不调 8127）；只允许读文件 + 运行**仓库内的核账脚本**（纯静态/离线）；
- 结论必须能点开证据路径；不得凭印象写"已覆盖"。

## 交付
- `test/reports/round9/spec-matrix-state.md`：① 本次机器核账的数字（条数/状态分布）；② 失效条款逐条表；
  ③ 剩余 gap/partial 清单（含建议）；④ 你没能核到的部分（如实列出）。
