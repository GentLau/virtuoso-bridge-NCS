# P-027 · `virtuoso.netlist.import` 假成功：对不存在的目标库仍返回 ok=true（三步全绿但什么都没建）

| 字段 | 值 |
|---|---|
| 级别 | P2（静默假成功会污染后续 symbol/LVS/仿真） |
| 归属 | 设计侧（`netlist_import.py`） |
| 状态 | **待设计修（已报 `bug-20260922T123859Z-vblog-202c4e37`）** |
| 位置 | `src/pyapi/packages/netlist_import.py:70-90` |
| 首报 | 第五轮（2026-09-22；已报 `bug-20260922T123859Z-vblog-202c4e37`） |
| 最近更新 | 2026-09-28（补齐卡片） |

## 现象

upload/import/symbol 三步全 ok=true，实际 SKILL 只是 `printf("import lib=…")` / `printf("symbol lib=…")`，不建 view、不建 symbol；同库 `view.list`/`cell.list` → `libraryNotFound`。

## 复现

```text
`netlist.import` 到一个不存在的库；证据 `test/artifacts/evidence/s11-probe/netlist-import-false-success.json`
```

## 证据

`test/artifacts/evidence/s11-probe/netlist-import-false-success.json`；bug id `bug-20260922T123859Z-vblog-202c4e37`

## 验收判据（修好即转绿）

摘出运营面，或真正导入并用 `view.list` 校验后再返回成功；TB 断言改为「view 真实存在且内容非空」

## 下一步 / 责任人

设计侧修；测试侧把 `infra_e2e_tests.py` 断言改为「必须失败且 error 明说 reference stub」（已改，见 round7）


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
