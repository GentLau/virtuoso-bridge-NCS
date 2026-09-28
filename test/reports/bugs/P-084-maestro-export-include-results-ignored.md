# P-084 · `maestro.export.include_results` 是声明参数但实现**从不读取**（静默无效）

| 字段 | 值 |
|---|---|
| 级别 | P2（静默无效参数：调用方以为能控制是否携带结果文件） |
| 层 | 上层（maestro 包） |
| 归属 | 设计侧（实现语义或从模型/spec 删除） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/maestro.py:123`（`include_results: bool = True`，全文件仅此一处；`rg -n "include_results" src/pyapi/packages/maestro.py` 只命中声明行）；spec 未定义该字段 |
| 首报 | 2026-09-28（第八轮 op×param 补测；红灯探针已留证） |
| 最近更新 | 2026-09-28（新立） |

## 现象

同一 `kind=outputs_csv` 下 `include_results=True/False` 导出的文件内容 **sha256 完全相同**（本轮实测 3c7e476b…），参数对产物零影响。

## 复现

```text
`PYTHONPATH=src python test/semi/probes/maestro_export_include_results_probe.py`（预期红；verdict=RED(参数被忽略)）
```

## 证据

`test/artifacts/evidence/round8/maestro-include-results/include-results.json`

## 验收判据（修好即转绿）

二选一：① 实现 `include_results` 的真实语义（并在 spec 定义）；② 从 `ExportRequest`/spec 删除该字段；探针转绿或删除

## 下一步 / 责任人

设计侧定口径；测试侧复跑探针确认


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
