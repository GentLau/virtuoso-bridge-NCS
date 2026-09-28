# P-026 · maestro 会话匹配用子串：`view="maestro"` 命中库名 `maestro_tb` 的 Reading 窗口 → `maestro.run` 整体报错

| 字段 | 值 |
|---|---|
| 级别 | P2（同名/子串命名在真机很常见，一旦并存必然失败） |
| 归属 | 设计侧（`maestro.py` 窗口匹配） |
| 状态 | **待设计修（已报 `bug-20260922T121908Z-vblog-b06063ab`）** |
| 位置 | `src/pyapi/packages/maestro.py:472-486`（`library/cell/view in title` 子串判断）、抛错点 `:572-579` |
| 首报 | 第五轮（2026-09-22；已报 `bug-20260922T121908Z-vblog-b06063ab`） |
| 最近更新 | 2026-09-28（补齐卡片） |

## 现象

窗口快照里 `("fnxSession160" 23 "…Reading: maestro_tb opamp_probe schematic…")` 与 `("fnxSession160" 12 "…Editing: maestro_tb opamp_probe maestro")` 并存时，`view="maestro"` 命中的是 Reading 窗口 → 走 reading 分支调 `maeMakeEditable` 失败 → `maestro.run` 报错。

## 复现

```text
真机 maestro 场景：库名含 maestro（maestro_tb）+ view=maestro；见台账 P-026 行窗口快照
```

## 证据

`test/reports/问题登记.md` P-026 行（窗口快照）；bug id `bug-20260922T121908Z-vblog-b06063ab`

## 验收判据（修好即转绿）

解析窗口标题结构（Editing/Reading 后三个 token 逐字段相等），不再用 `in` 子串匹配；同名库/cell 场景 maestro.run 通过

## 下一步 / 责任人

设计侧修；测试侧复验 maestro 包 E2E + 同名 cell 场景后移入已关闭


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
