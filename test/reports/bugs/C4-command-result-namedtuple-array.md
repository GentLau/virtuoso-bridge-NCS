# C4 · `CommandResult` NamedTuple 被 JSON 序列化为位置数组，命令 / 文件 / GUI / Spectre 结果丢失字段名

| 字段 | 值 |
|---|---|
| 级别 | P2（跨 basic 操作响应契约缺陷：调用方必须按位置猜字段，后续加字段或调整顺序会破坏兼容性） |
| 层 | 顶层（response serialization）· 上层（pyapi.models） |
| 归属 | 设计侧（`pyapi.models.CommandResult` 的模型形状，或 `server.dispatch.jsonable` 的 NamedTuple 序列化口径） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/models.py:133-144`（`CommandResult` 为 NamedTuple：returncode/stdout/stderr/kind）；`src/server/dispatch.py:58-77`（`jsonable()` 对 tuple 统一转 list，字段名丢失）；`src/pyapi/packages/basic.py:168-181`（command 的 `result` 与 `steps[].detail` 均直接携带 `CommandResult`）。 |
| 首报 | 2026-09-29（用户直报：`basic.command.run` 返回结果难以理解） |
| 最近更新 | 2026-09-29（新立） |

## 现象

实测 `basic.command.run(cmd="hostname")` 返回：
`{"ok":true,"result":[0,"GLIS-DESKTOP\n","","command"]}`；
`[0, stdout, stderr, kind]` 没有字段名，调用方必须记住位置。`steps[0].detail` 又重复同一数组。同一问题覆盖 `basic.file.upload`、`basic.file.download`、`basic.gui.run`、`basic.spectre.run`。

## 复现

```text
curl -sS -X POST http://127.0.0.1:8127/api/operation -H 'Content-Type: application/json' -d '{"operation":"basic.command.run","token":"<token>","cmd":"hostname"}'
```

## 证据

2026-09-29 实测响应：HTTP 200，`result=[0,"GLIS-DESKTOP\n","","command"]`，与 `steps[0].detail` 完全相同；代码锚点：`pyapi/models.py:133-144`、`server/dispatch.py:58-77`、`pyapi/packages/basic.py:176-182`。

## 验收判据（修好即转绿）

① `CommandResult` 在业务响应中稳定序列化为对象：`{"returncode":0,"stdout":"...","stderr":"","kind":"command"}`；② 顶层 `result` 与 `steps[].detail` 不得再使用位置数组表达该结构；③ 新增契约 TB 钉住字段名与值；④ 同步适配依赖位置的消费方。

## 下一步 / 责任人

设计侧选定单点修复：优先在 `jsonable()` 的 tuple 分支前处理 NamedTuple `_asdict()`，或把 `CommandResult` 改为具名模型；测试侧补离线契约 TB 并复跑 basic 五操作 HTTP 冒烟。

## 补充（2026-09-29）

这与 C1 的顶层响应改造叠加：C1 后业务 Result 本体直接返回，因此 `result` 的字段语义必须自描述；继续使用位置数组会让 C1 的“本体直返”契约更难消费。
---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
