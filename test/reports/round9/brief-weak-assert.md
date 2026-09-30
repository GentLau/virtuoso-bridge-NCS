# round9 任务书 D：断言强度审计（只读）

> 执行者：subagent（`/root/weak_assert_r9`）｜下发：测试/root，2026-09-29
> 产出：`test/reports/round9/weak-assertions.md`

## 背景
上一轮评审的驳回点之一是"假绿/弱断言"：C06 漏检的直接原因就是 TB 只断言了 `ok=true`，
**没有校验 log 的应有返回值**。本轮要系统排查同类问题。

## 任务
对 `test/` 下全部 TB（`test/offline/`、`test/semi/`、`test/live/`，共约 150+ 文件）做**只读**审计：
1. 找出**弱断言模式**并逐条记录（文件 + 行号 + 原断言 + 为什么弱 + 建议加强成什么）：
   - 只断言 `ok is True` / `status == "success"` 而不断言业务值；
   - 只断言 `len(x) > 0` / `x != []` 而不断言内容或数量；
   - 只断言 `"返回非空"`、`assert result` 之类的真值断言；
   - 断言 `error is None` 后不检查 `value` 的**关键字段**（spec 要求返回的字段没被看）。
2. 按**被测对象**分类：结果值类（netlist/波形/统计/坐标）、日志类（`CDSlog`/log 字段）、
   文件类（产物存在/内容/清理）、状态类（session/lock/history）。
3. 汇总 Top-N 风险清单（哪 10 条最可能藏着真 bug），说明理由。

## 硬约束
- **只读**：不得修改任何文件；不得跑真机；不得调用 8127。
- 允许跑纯静态检查脚本；不得把"存在断言"误报为弱断言（例如 `assert x == 3` 不是弱断言）。
- 结论必须能点开证据（文件路径 + 行号），不得凭印象。

## 交付
- `test/reports/round9/weak-assertions.md`：① 总数/分布；② 逐条表（文件/行/断言/风险/建议）；
  ③ Top-N 风险清单；④ 你无法判定的部分（如实列出）。
