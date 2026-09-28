# P-031 · schematic `check_and_save`/`write` 忽略 `schCheck` 失败：返回 check-failed 仍 ok=true

| 字段 | 值 |
|---|---|
| 级别 | P2（电气检查失败（悬空/短路/未连线）被静默当成功保存） |
| 归属 | 设计侧（`schematic.py`） |
| 状态 | **待设计修（已报 `bug-20260922T124018Z-vblog-0584e46b`）** |
| 位置 | `src/pyapi/packages/schematic.py:410`、`:690-693`、`:756-759`（layout 同路径有 `"saved" in output` 校验，属实现不一致） |
| 首报 | 第五轮（2026-09-22；已报 `bug-20260922T124018Z-vblog-0584e46b`） |
| 最近更新 | 2026-09-28（补齐卡片） |

## 现象

SKILL 返回 `"check-failed"` 时仍 `ok=true`。

## 复现

```text
`test/offline/unit/test_schematic_contracts.py`（`unittest.expectedFailure`×2）
```

## 证据

`test/offline/unit/test_schematic_contracts.py`；bug id `bug-20260922T124018Z-vblog-0584e46b`

## 验收判据（修好即转绿）

比对 `output` 是否含 `"saved"`，与 `layout.py:490` 对齐；两条 xfail 转绿

## 下一步 / 责任人

设计侧修；测试侧把 xfail 改回正常断言


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
