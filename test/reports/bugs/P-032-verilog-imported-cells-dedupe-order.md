# P-032 · `verilog._imported_cells` 去重顺序错误：未清洗 token 与已清洗列表比较 → 同一 cell 多视图被重复计入

| 字段 | 值 |
|---|---|
| 级别 | P2/P3（返回元数据被污染；当前无真实 VERILOGIN 日志样本，可达性待现场确认） |
| 归属 | 设计侧（`verilog.py`） |
| 状态 | **待设计修（已报 `bug-20260922T124456Z-vblog-70645f43`）** |
| 位置 | `src/pyapi/packages/verilog.py:637-643` |
| 首报 | 第五轮（2026-09-22；已报 `bug-20260922T124456Z-vblog-70645f43`） |
| 最近更新 | 2026-09-28（补齐卡片） |

## 现象

用未清洗 token（`counter8,`）与已清洗列表（`counter8`）比较 → 同一 cell 多视图导入时重复计入，调用方统计/后续处理受污染。

## 复现

```text
`test/offline/unit/test_verilog_contracts.py`（`expectedFailure`）
```

## 证据

`test/offline/unit/test_verilog_contracts.py`；bug id `bug-20260922T124456Z-vblog-70645f43`

## 验收判据（修好即转绿）

先清洗再比较；xfail 转绿

## 下一步 / 责任人

设计侧修；测试侧复验 verilog 包 E2E


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
