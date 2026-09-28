# P-030 · `schematic.set_term_nets` 默认 `stub_length=0.5` 对 65nm PDK 过大 → 端子被路由到错误网络且静默通过

| 字段 | 值 |
|---|---|
| 级别 | P2（生成的原理图连接关系错误，会带到 CDL/LVS/仿真） |
| 归属 | 设计侧（`schematic.py` 默认值策略） |
| 状态 | **待设计修（已报 `bug-20260922T122850Z-vblog-b7ed6176`）** |
| 位置 | `src/pyapi/packages/schematic.py:469`（默认值）、`:476-483`（stub wire + label） |
| 首报 | 第五轮（2026-09-22；已报 `bug-20260922T122850Z-vblog-b7ed6176`） |
| 最近更新 | 2026-09-28（补齐卡片） |

## 现象

`schCreateWire(entry=route)` 连不上，端子被路由到 `net1/net2` 等错误网络；接口仍 `ok=true`、无 warning。

## 复现

```text
`test/artifacts/env/scenario-project65/evidence-schematic*.json`（stub 0.5 vs 0.05 的 term→net 映射不同）
```

## 证据

`test/artifacts/env/scenario-project65/evidence-schematic*.json`；bug id `bug-20260922T122850Z-vblog-b7ed6176`

## 验收判据（修好即转绿）

默认值改为与 PDK 无关的安全策略（由调用方显式给，或按 tech 的 minWidth 计算）

## 下一步 / 责任人

设计侧修；测试侧在 65nm 环境复验 term→net 映射


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
