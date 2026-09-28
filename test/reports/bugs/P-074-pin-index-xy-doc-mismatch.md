# P-074 · spec 表格把 pin 的索引写成 `xy`，实现要 `x`/`y`（delete/rename/set_pin_properties）

| 字段 | 值 |
|---|---|
| 级别 | P3（文档口径不一致，会绊住所有写 TB 的人） |
| 归属 | 设计侧（spec 或实现，二选一改齐） |
| 状态 | **待归属** |
| 位置 | `spec/design-concepts/上层/2-schematic.md:59`（`delete_pin | xy` / `rename_pin | xy` / `set_pin_properties | xy`）vs `src/pyapi/packages/schematic.py:615-616`（`float(cmd["x"])` / `float(cmd["y"])`） |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

## 现象

按 spec 表格写 `{"op":"rename_pin","xy":[6.0,0.0],"new_name":"vout_main"}` → `virtuoso.schematic.write` 直接失败：`command 5 invalid: 'x'`（KeyError('x')）。只有 label/note/wire 一族用 `xy`，pin 用 `x`/`y` —— 表格与实现相反，使用者照表格写必然踩坑（本轮就踩到，见 R7-TB 修正记录）。

## 复现

```text
把 `test/live/flows/design_iterate_tb.py` 的 `R2_RENAME` 改回 `xy` 形状即复现；或任何 `{"op":"delete_pin","xy":[...]}` 的 write
```

## 证据

`test/artifacts/evidence/round7/design-iterate/iterate-r2_edit.json`（早期失败版本的错误串）、`test/reports/round7-TB修正.md`（R7-TB-03）

## 验收判据（修好即转绿）

spec 表格与实现同口径（建议实现同时接受 `xy` 与 `x`/`y`，或 spec 明确写 pin 用 `x`/`y`），且校验失败信息能指出「缺 x/y」而不是裸露 KeyError

## 下一步 / 责任人

设计侧定口径；测试侧已按实现口径写 TB（并在 TB 注释里标注）

## 讨论决策（2026-09-25，补充）

**定性升级**：本条不是「文档抄错字段名」，而是**坐标表示口径没统一**——三个口径在打架：

| 场景 | 坐标表示 |
|---|---|
| `read` 返回 | `xy: [x, y]`（整体数组） |
| `write` 输入（实现） | `x`、`y`（拆开两个字段） |
| spec 内部 | place 用 `x,y`，delete/rename/set 索引用 `xy`（自相矛盾） |

**核心共识**：坐标本质是一个点，不该拆开写。`read` 已证明正确形态是「一个字段承载 `[x, y]`」；`write` 把坐标拆成 `x`/`y` 才是别扭、且与 read 不对称的根源。

**命名**：弃 `xy`，改 `pos`（或 `position`）。`xy` 字面像「两个分量」、又与 `x`/`y` 视觉太近，是这类坑的诱因；`pos` 简洁、与 `op` 风格一致、坐标语境无歧义。

**落地建议（给设计侧拍板）**：

- 统一为 `pos: [x, y]`（两元素数组），read 与 write 同一口径，**不保留兼容**，彻底消灭 `x`/`y` 拆开写法；
- 验收：照 spec 写 `{"op":"rename_pin","pos":[6.0,0.0]}` 能跑通，且校验失败信息指名缺哪个字段（不再裸报 `KeyError('x')`）。

---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
