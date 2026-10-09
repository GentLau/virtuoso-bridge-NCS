# symbol —— 符号

符号（symbol）是原理图上看到的那张图。两种用法：**从原理图自动生成**（最常用），或用原子命令**手工画/改**。

## 1. `virtuoso.symbol.read` — 读符号

**功能**：读取符号内容（端子、标签、图形、pin 顺序、选择框）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `symbol` | 视图名 |
| `view_type` | str | — | `schematicSymbol` | 视图类型 |
| `focus` | list[str] | — | 全部 | `terms` / `labels` / `shapes` / `orders` / `selection_boxes` 的子集 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.library` / `value.cell` / `value.view` / `value.view_type` | str | 视图标识 |
| `value.terms` | list | 端子（名字、方向、位置） |
| `value.labels` / `value.shapes` | list | 标签 / 图形 |
| `value.orders` | list | pin 顺序 |
| `value.selection_boxes` | list | 选择框 |

**示例**

```json
// 输入
{"operation":"virtuoso.symbol.read","token":"TOKEN","library":"mylib","cell":"inv","view":"symbol","focus":["terms","orders"]}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"library":"mylib","cell":"inv","view":"symbol","view_type":"schematicSymbol",
 "terms":[{"name":"IN","direction":"input","pos":[-1.5,0]},{"name":"OUT","direction":"output","pos":[1.5,0]}],
 "orders":["IN","OUT"]}}
```

## 2. `virtuoso.symbol.write` — 写符号

**功能**：用原子命令画/改符号（图形、标签、引脚、pin 顺序、选择框）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令组 |
| `view` / `view_type` | str | — | `symbol` / `schematicSymbol` | 视图 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.applied` | int | 成功应用的命令条数 |

### 2.1 图形类原子

`points` = `[[x,y], …]`；`bbox` = `[x0,y0,x1,y1]`。

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_line` | `layer`, `purpose`, `points` | str,str,list | ✅ | — | 折线（≥2 点） |
| `place_polygon` | `layer`, `purpose`, `points` | str,str,list | ✅ | — | 多边形（≥3 点） |
| `place_rect` | `layer`, `purpose`, `bbox` | str,str,list | ✅ | — | 矩形 |
| `place_ellipse` | `layer`, `purpose`, `bbox` | str,str,list | ✅ | — | 椭圆 |
| `delete_shape` | `kind`（`line`/`rect`/`polygon`/`ellipse`）+ `points` 或 `bbox` | str,list | ✅ | — | 删除；可用 `layer`/`purpose` 限定 |
| `set_shape_properties` | `kind` + 定位参数 | — | ✅ | — | 至少给一个 `new_points`/`new_bbox`/`layer`/`purpose` |

常用 `layer`/`purpose`：`drawing`/`drawing`（图形）、`pin`/`label`（引脚名）、`device`/`label`、`annotate`/`drawing`。

### 2.2 标签类原子

`label_kind`：`drawing`（普通标签，需 `layer`/`purpose`/`text`）、`pin_name`（引脚名）、`instance`（实例名，`text` 可省）、
`logical`（器件名，`text` 可省）。

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_label` | `label_kind`, `text` | str | ✅（`instance`/`logical` 可省） | — | 放标签 |
| | `xy` 或 `x`+`y` | list/number | ✅ | — | 位置 |
| | `layer`, `purpose` | str | `drawing` 时 ✅ | — | 图层 |
| | `justify`/`orient`/`font`/`height` | str/number | — | 按类型取缺省 | 样式 |
| `delete_label` | `label_kind`, `xy`（或 `x`+`y`） | str/list | ✅ | `drawing` | 删除 |
| `rename_label` | `label_kind`, `xy`, `new_text` | str/list/str | ✅ | `drawing` | 改文字 |
| `set_label_properties` | `label_kind`, `xy` + 至少一个样式字段 | — | ✅ | `drawing` | 改样式 |

### 2.3 引脚类原子

> 引脚位置统一用 **`pos: [x,y]`**；给 `x`/`y`/`xy` 会被明确拒绝。

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_pin` | `name`, `pos` | str,list | ✅ | — | 放引脚 |
| | `direction` | str | — | `inputOutput` | `input`/`output`/`inputOutput`/`switch`/`jumper` |
| | `half_size` / `label` | number/bool | — | `0.0625` / `true` | 方块半宽 / 是否画引脚名 |
| | `label_pos` | list | — | 与 `pos` 同 | 引脚名位置 |
| | `label_justify`/`label_orient`/`label_font`/`label_height` | str/number | — | `centerLeft`/`R0`/`stick`/`0.0625` | 引脚名样式 |
| `delete_pin` | `name` | str | ✅ | — | 删除 |
| `rename_pin` | `name`, `new_name` | str | ✅ | — | 改名（网络/标签一并更新） |
| `set_pin_properties` | `name` + 至少一个可选字段 | — | ✅（name） | — | `direction`/`label`/`label_font`/`label_justify`/`label_orient`/`label_height` |
| `set_pin_order` | `term_names` | list[str] | ✅ | — | 顺序，如 `["VDD","IN","OUT","VSS"]` |
| `set_selection_box` | `bbox` | list | ✅ | — | 设置选择框 |

**示例**

```json
{"operation":"virtuoso.symbol.write","token":"TOKEN","library":"mylib","cell":"inv","view":"symbol",
 "commands":[
  {"op":"place_rect","layer":"drawing","purpose":"drawing","bbox":[-1,-1,1,1]},
  {"op":"place_pin","name":"IN","pos":[-1.5,0],"direction":"input"},
  {"op":"place_pin","name":"OUT","pos":[1.5,0],"direction":"output"},
  {"op":"set_pin_order","term_names":["IN","OUT"]},
  {"op":"set_selection_box","bbox":[-1.5,-1.5,1.5,1.5]}]}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"applied":5}}
```

## 3. `virtuoso.symbol.generate` — 从原理图生成符号

**功能**：按原理图里的引脚自动生成/更新符号。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `schematic_view` / `symbol_view` | str | — | `schematic` / `symbol` | 源/目标视图 |
| `sort_pins` | str | — | 无 | pin 排序方式 |
| `overwrite` | bool | — | `false` | 已存在时是否覆盖 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.action` | str | 本次动作（新建/覆盖等） |
| `value.terminal_names` | list | 生成的端子名 |
| `value.pin_order` | list | 生成的 pin 顺序 |
| `value.library` / `value.cell` / `value.schematic_view` / `value.symbol_view` | str | 视图标识 |

**示例**

```json
// 输入
{"operation":"virtuoso.symbol.generate","token":"TOKEN","library":"mylib","cell":"inv","overwrite":true}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"library":"mylib","cell":"inv","schematic_view":"schematic","symbol_view":"symbol",
 "action":"overwrite","terminal_names":["IN","OUT","VDD","VSS"],"pin_order":["VDD","IN","OUT","VSS"]}}
```

## 4. `virtuoso.symbol.check_and_save` — 检查并保存

**功能**：检查并保存符号视图。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` / `view_type` | str | — | `symbol` / `schematicSymbol` | 视图 |

**返回**：`value.saved` = 保存结果。

```json
// 输入
{"operation":"virtuoso.symbol.check_and_save","token":"TOKEN","library":"mylib","cell":"inv","view":"symbol"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"saved":true}}
```

## 5. `virtuoso.symbol.screenshot` — 截屏

**功能**：符号窗口截图并送回本机。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` / `view_type` | str | — | `symbol` / `schematicSymbol` | 视图 |
| `window_id` / `region` | int/list | — | 自动/全图 | 窗口与区域 |
| `toplevel`/`central_widget`/`leave_open` | bool | — | `true`/`true`/`false` | 同 schematic |

**返回**：`value.local_path` = 截图落点（注意在 `value` 里）。

```json
// 输入
{"operation":"virtuoso.symbol.screenshot","token":"TOKEN","library":"mylib","cell":"inv","view":"symbol"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"local_path":"C:/work/artifact/screenshots/inv_symbol_1.png"}}
```

## 6. 注意事项

- 手写符号时"引脚名"和"实例名/器件名"是不同 `label_kind`，混用会画错层。
- `set_pin_order` 里的名字必须已存在，否则报 `pin not found: xxx`。
- 生成会覆盖同名符号；只想微调就别重新生成，直接 `write`。
