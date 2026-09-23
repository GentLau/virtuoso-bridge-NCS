# 上层业务包：symbol

> 版本：Draft v2
> 日期：2026-09-21
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：Draft v1（操作收敛为 read/write/check_and_save/generate/screenshot；write 只 append）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 总述

symbol 包覆盖 **符号语义读回、手工批写、校验保存、从原理图自动生成、截图** 五类需求。

手工写与自动生成分开：

- `write` 只编辑**已存在的** symbol cellview，追加模式 `a`，不负责 create/replace；
- 新建空 symbol view 由 cellview 包负责（`view.create`，view type `schematicSymbol`）；
- `generate` 可以从 schematic 生成或覆盖 symbol，内部自带临时 view、校验、备份、回滚。

## 2. 业务操作

### 2.1 读操作

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| `read` | 读 terms/labels/shapes/orders/selection boxes；`focus` 可选 | 只读打开 → 收集 → 解析 | S |
| `screenshot` | symbol 截图；默认 `lib/cell/view`，可选 `window_id` | 找/开窗口 → `hiWindowSaveImage` → 下载 | S+D |

`read.focus` 取值可组合；不填=全部：

| focus | 返回 |
|---|---|
| `terms` | 每个 terminal：`name / direction / num_bits / bbox / access_dir` |
| `labels` | 每个 label：`text / label_type / xy / layer / purpose / justify / orient / font / height / bbox` |
| `shapes` | 已知类型 line / rect / polygon / ellipse 及兜底类型（path / arc / inst / textDisplay 等）：`kind / layer / purpose / bbox / points` |
| `orders` | `pin_order`（权威，`schGetPinOrder`）；`port_order` / `term_order` raw（兼容旧 reader） |
| `selection_boxes` | `instance/drawing` 矩形列表 |

`read` 默认 `view="symbol"`、`view_type="schematicSymbol"`；必须返回通用 shapes，
否则 `write` 写入的几何无法读回验证。

`screenshot` 与 schematic 同口径：

- `view_type` 默认 `schematicSymbol`；格式固定 PNG；
- 可选 `window_id`、`region=[x1,y1,x2,y2]`（截前 `hiZoomIn`）、`toplevel`、`central_widget`、`leave_open`；
- 远端存 daemon/gui role root，本地存客户端工作目录 artifact/screenshots/；
- `hiWindowSaveImage` 失败直接业务失败，不做 X11/display 回退。

### 2.2 写操作

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| `write` | 通用写：`lib/cell/view + commands[]` | 开 cellview(a) → 逐命令执行 → `schSymbolToPinList` → `dbSave` | S |
| `check_and_save` | 对目标显式执行 symbol check + `dbSave` | 开 cellview(a) → check → save | S |
| `generate` | 从 schematic 自动生成 symbol | 取 pin 序 → 临时 view → 校验 → 安装/回滚 | S |

`write` 只接受已存在的 view，打开模式固定 `a`；不提供 `replace`。
需要新建 symbol view 时，调用方先走 cellview 包的 `view.create`。

注意：`dbOpenCellViewByType(..., "a")` 在 view 不存在时也会创建，
所以 write 必须先显式探测 view 是否存在，再进入 append 编辑。
真机已验证：`"r"` 对不存在的 view 返回 nil；`"a"`/`"w"` 返回可编辑的内存
cellview，但在 `dbSave` 前磁盘上不存在。

`write.commands` 每项 = `{"op": 原子名, ...该原子参数}`；按顺序执行并保留每步痕迹。

#### 2.2.1 几何原子

| 原子名 | 索引 | 附加参数 |
|---|---|---|
| `place_line` | —（新建） | `layer, purpose, points[[x,y],...]` |
| `place_rect` | —（新建） | `layer, purpose, bbox=[x0,y0,x1,y1]` |
| `place_polygon` | —（新建） | `layer, purpose, points[[x,y],...]` |
| `place_ellipse` | —（新建） | `layer, purpose, bbox=[x0,y0,x1,y1]` |
| `delete_shape` | `kind + bbox/points` | — |
| `set_shape_properties` | `kind + bbox/points`（旧值定位） | `layer?, purpose?, new_bbox?, new_points?`（按 kind 取合法项） |

几何索引规则：

- line / polygon：按 points 匹配，容差 0.001；
- rect / ellipse：按 bbox 匹配，容差 0.001；
- 新建原子的 `layer/purpose` 必填；不设默认层，避免猜 PDK。

#### 2.2.2 标签原子

标签统一用 `label_kind` 区分：

| label_kind | 底层 |
|---|---|
| `drawing` | `dbCreateLabel` / `dbCreateLabel` + labelType |
| `pin_name` | `schCreateSymbolLabel` `"pin name"` |
| `instance` | `schCreateSymbolLabel` `"instance label"` |
| `logical` | `schCreateSymbolLabel` `"logical label"` |

| 原子名 | 索引 | 附加参数 |
|---|---|---|
| `place_label` | —（新建） | `label_kind, text, x, y, layer?, purpose?, justify?, orient?, font?, height?` |
| `delete_label` | `label_kind + xy`（可加 `text` 消歧） | — |
| `rename_label` | `label_kind + xy`（可加 `old_text`） | `new_text` |
| `set_label_properties` | `label_kind + xy`（可加 `text`） | `justify?, orient?, font?, height?`；`drawing` 可额外 `layer?, purpose?` |

#### 2.2.3 引脚原子

pin 以 **terminal name** 为唯一索引；旧代码 `symbol_create_pin` 本身就以
name 检查 terminal 是否存在。

| 原子名 | 索引 | 附加参数 |
|---|---|---|
| `place_pin` | —（新建） | `name, x, y, direction="inputOutput", half_size=0.0625, label=True, label_x?, label_y?, label_justify?, label_orient?, label_font?, label_height?` |
| `delete_pin` | `name` | — |
| `rename_pin` | `name` | `new_name`（同步 terminal/net/pin 与 pin-name label） |
| `set_pin_properties` | `name` | `direction?, access_dir?, label?, label_justify?, label_orient?, label_font?, label_height?` |

`place_pin` 内部顺序：检查 terminal 不存在 → net → term → pin 矩形
`pin/drawing` → `dbCreatePin` → 可选 pin-name label（创建后 `schGlueLabel` 挂到 pin 上，
使 label 随 pin 移动）。

`access_dir` 走官方 `dbSetPinFigAccessDirection`（合法值 `left/right/top/bottom`，
可传列表）；`read.terms.access_dir` 用 `dbGetPinFigAccessDirection` 回读，保证可往返校验。
`set_pin_properties(label=true)` 在 pin-name label 缺失时按 pin 实际位置 +
请求里的 label 样式重建（不用 (0,0)）。

真机语义（必须遵守）：

- `dbDeleteObject(pin)` 只 detach figure，不删矩形；
- `dbDeleteObject(term)` 级联删 pin，但 net 与 figure 仍在；
- 因此 `delete_pin` 要显式清理 pin → figure → pin-name label；
  net 在同名且无其他 terminal 时可一并清理；
- 改 `term~>name` / `pin~>name` **不会**自动改 net 名称，也不会自动改
  pin-name label；rename 要显式 `dbRenameNet` + 手工同步 label。

#### 2.2.4 结构原子

| 原子名 | 索引 | 附加参数 |
|---|---|---|
| `set_selection_box` | 单例 | `bbox=[x0,y0,x1,y1]`（`instance/drawing` 矩形，替换旧框） |
| `set_pin_order` | —（整体） | `term_names=[...]`；底层 `schEditPinOrder`，不是写 `cv~>termOrder` |

`port_order` / `term_order` 本版只做 raw 读回；设置统一走 `set_pin_order`
（底层 `schEditPinOrder`，官方支持 schematic/symbol）。

#### 2.2.5 检查与保存

- `write` 末尾统一执行：`schSymbolToPinList(lib cell view)` 非 nil → `dbSave`；
- symbol check 失败则不保存，返回失败与步骤痕迹；
- `check_and_save` 用于显式补一次 check/save，语义与 `write` 末尾相同。

### 2.3 generate

| 参数 | 说明 |
|---|---|
| `lib / cell` | 必填 |
| `schematic_view` | 默认 `"schematic"` |
| `symbol_view` | 默认 `"symbol"` |
| `sort_pins` | `None / "alphanumeric" / "geometric"` |
| `overwrite` | 默认 `false` |
| `timeout` | 可选 |

行为：

1. source/target view 必须不同；
2. 目标 symbol 已打开 → 失败；
3. 目标存在且 `overwrite=false` → 失败；
4. 收集 schematic terminals 与 `schGetPinOrder`；
5. 临时 view：`schSchemToPinList` → `schPinListToSymbol` → 校验 terminals/pin order；
6. `overwrite=true` 时备份旧 symbol；安装新 symbol 后再次校验；
7. 任一步失败尝试回滚；回滚失败保留 backup view 并返回失败；
8. `ssgSortPins` 临时覆盖后无论成功失败都恢复。

返回：`action`（`created` / `replaced`）、`terminal_names`、`pin_order`。

真机结论（2026-09-21）：`ssgSortPins` 在 IC6.1.8 是未定义函数，`schPinListToSymbol` /
`schPinListToSymbolGen` 对显式 pin list 也按传入顺序生成，**`sort_pins` 参数保留但不承诺排序效果**。
`schPinListToSymbolGen` 会自行 `dbSave`，因此只能用于临时 view（当前实现即如此）。

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 3. 不在本版

- generic DB property（除 label/shape/pin 已列字段外）；
- `port_order` / `term_order` 的独立写入原子；
- 符号电气规则检查（DRC/pin type consistency 等）；
- 图形层次/group/fig group 操作；
- 移动类原子（`move_shape / move_label / move_pin`）：底层已确认 `dbMoveFig/dbMoveShape` 可用，
  当前用 delete + place 代替；
- 逐图元 width / color / lineStyle / fillStyle：`dbSetShapeStyle*` 系列在 IC6.1.8 不存在；
  `schSetShapeStyle` 可写但不改变 IC6.1.8 渲染（渲染由 LPP/DRF packet 决定，如
  `device/drawing1` = 实心）；`dbCreatePath` 的 width 与 `schCreateSymbolShape` 的
  `style/width` 留作后续扩展；
- circle / arc / donut / path 原子；
- 并发写。

## 4. 真机结论（已闭环）

| 项 | 结论 |
|---|---|
| `set_shape_properties` 可写字段 | line/polygon 的 `points`、rect/ellipse 的 `bBox`、`layerName`/`purpose` 均已真机验证生效 |
| `set_pin_properties` 移动 pin | 本版不支持；`dbMoveFig` 可用，留作扩展 |
| label 索引 | 坐标容差 0.001；`label_kind` 参与消歧，`pin_name` 另外要求 `pin/label` |
| `rename_pin` 同步 | 不联动：必须显式 `dbRenameNet` + 手工改 pin-name label（已测） |
| `schEditPinOrder` | 真机生效，`pin_order` 与 `port_order`/`term_order` 一致 |
| `schCreateSymbolLabel` | `"pin name"`/`"instance label"`/`"logical label"` 可用；`"device label"` 在 symbol 里返回 nil（文档与实测不符） |
| `read.shapes` 覆盖 | 已覆盖 line/rect/polygon/ellipse + 兜底 objType（path/arc/inst/textDisplay 等） |
| 截图 | symbol 窗口真机出图；空 symbol 窗口出 1 色黑图（无内容时的正常表现），有内容窗口出 7 色真实图 |
| `write` 执行方式 | 逐命令 `execute_skill` + 末尾统一 check/save，保留每步痕迹；**非事务**，失败响应带 `commands applied: k/n` |
