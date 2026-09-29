# symbol —— 符号

符号（symbol）是原理图上看到的那张"图"。两种用法：

1. **从原理图自动生成**（最常见）：`virtuoso.symbol.generate`，按原理图里的引脚生成；
2. **手工画/改**：`virtuoso.symbol.write`，用原子命令画线、放引脚、定 pin 顺序。

## 1. `virtuoso.symbol.read` — 读符号

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `view` | str | — | `symbol` | 视图名 |
| `view_type` | str | — | `schematicSymbol` | 视图类型 |
| `focus` | list[str] | — | 全部 | 取 `terms` / `labels` / `shapes` / `orders` / `selection_boxes` 的子集 |

返回 `data.value`：按 `focus` 裁剪的符号内容（端子、标签、图形、pin 顺序、选择框）。

## 2. `virtuoso.symbol.write` — 写符号

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `commands` | list[dict] | ✅ | — | 原子命令组 |
| `view` | str | — | `symbol` | 视图名 |
| `view_type` | str | — | `schematicSymbol` | 视图类型 |

### 2.1 图形类原子

坐标：`points` = `[[x,y], …]`，`bbox` = `[x0,y0,x1,y1]`。

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_line` | `layer`, `purpose`, `points` | str,str,list | ✅ | — | 画折线（至少 2 点） |
| `place_polygon` | `layer`, `purpose`, `points` | str,str,list | ✅ | — | 画多边形（至少 3 点） |
| `place_rect` | `layer`, `purpose`, `bbox` | str,str,list | ✅ | — | 画矩形 |
| `place_ellipse` | `layer`, `purpose`, `bbox` | str,str,list | ✅ | — | 画椭圆（按外接框） |
| `delete_shape` | `kind` | str | ✅ | — | `line` / `rect` / `polygon` / `ellipse` |
| | `points` 或 `bbox` | list | ✅ | — | 定位：line/polygon 给 points，rect/ellipse 给 bbox |
| | `layer`, `purpose` | str | — | 无 | 进一步限定 |
| `set_shape_properties` | `kind` | str | ✅ | — | 同上 |
| | `points` 或 `bbox` | list | ✅ | — | 定位用 |
| | `new_points` / `new_bbox` | list | — | 无 | 新几何（line/polygon 用 points，rect/ellipse 用 bbox） |
| | `layer`, `purpose` | str | — | 无 | 也支持直接改图层/用途 |

常用 `layer`/`purpose`：`drawing`/`drawing`（图形）、`pin`/`label`（引脚名）、`device`/`label`、
`annotate`/`drawing`（文字）。具体取值以你所用工艺库/器件库的约定为准。

### 2.2 标签类原子

`label_kind` 取值：

| 值 | 含义 |
|---|---|
| `drawing` | 普通图形标签（要自己给 `layer`/`purpose`/`text`） |
| `pin_name` | 引脚名（位置与引脚一致） |
| `instance` | 实例名（`text` 省略时自动用 `[@instanceName]`） |
| `logical` | 器件名（`text` 省略时自动用 `[@partName]`） |

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_label` | `label_kind` | str | ✅ | — | 见上表 |
| | `text` | str | 视情况 | — | `drawing`/`pin_name` 必给；`instance`/`logical` 可省 |
| | `xy` 或 `x`+`y` | list/number | ✅ | — | 位置 |
| | `layer`, `purpose` | str | `drawing` 时 ✅ | — | 图层 |
| | `justify`, `orient`, `font`, `height` | str/number | — | 按 `label_kind` 取缺省 | 样式 |
| `delete_label` | `label_kind`, `xy`（或 `x`+`y`） | str,list | ✅ | `drawing`/— | 定位；可用 `text`/`layer` 进一步限定 |
| `rename_label` | `label_kind`, `xy`（或 `x`+`y`）, `new_text` | str,list,str | ✅ | `drawing`/—/— | 改文字 |
| `set_label_properties` | `label_kind`, `xy`（或 `x`+`y`） | str,list | ✅ | `drawing`/— | 定位 |
| | `justify`,`orient`,`font`,`height`,`layer`,`purpose`,`label_type` | str/number | — | — | 至少给一个 |

### 2.3 引脚类原子

> 注意：符号引脚的位置参数是 **`pos: [x,y]`**；给 `x`/`y`/`xy` 会被明确拒绝。

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_pin` | `name` | str | ✅ | — | 引脚名 |
| | `pos` | list | ✅ | — | `[x,y]` |
| | `direction` | str | — | `inputOutput` | `input` / `output` / `inputOutput` / `switch` / `jumper` |
| | `half_size` | number | — | `0.0625` | 引脚方块半宽 |
| | `label` | bool | — | `true` | 是否画引脚名 |
| | `label_pos` | list | — | 与 `pos` 相同 | 引脚名位置 |
| | `label_justify` / `label_orient` / `label_font` / `label_height` | str/number | — | `centerLeft`/`R0`/`stick`/`0.0625` | 引脚名样式 |
| `delete_pin` | `name` | str | ✅ | — | 按名字删除 |
| `rename_pin` | `name`, `new_name` | str | ✅ | — | 改名（网络/标签一并更新） |
| `set_pin_properties` | `name` | str | ✅ | — | 定位 |
| | `direction` | str | — | 无 | 改引脚类型 |
| | `label`, `label_font`, `label_justify`, `label_orient`, `label_height` | bool/str/number | — | — | 改标签样式 |
| `set_pin_order` | `term_names` | list[str] | ✅ | — | 引脚显示顺序，如 `["VDD","IN","OUT","VSS"]` |
| `set_selection_box` | `bbox` | list | ✅ | — | 设置 symbol 的选择框（`instance/drawing` 矩形） |

### 2.4 示例

```json
{"operation":"virtuoso.symbol.write","token":"TOKEN","library":"mylib","cell":"inv","view":"symbol",
 "commands":[
  {"op":"place_rect","layer":"drawing","purpose":"drawing","bbox":[-1,-1,1,1]},
  {"op":"place_pin","name":"IN","pos":[-1.5,0],"direction":"input"},
  {"op":"place_pin","name":"OUT","pos":[1.5,0],"direction":"output"},
  {"op":"set_pin_order","term_names":["IN","OUT"]},
  {"op":"set_selection_box","bbox":[-1.5,-1.5,1.5,1.5]}]}
```

## 3. `virtuoso.symbol.generate` — 从原理图生成符号

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `schematic_view` | str | — | `schematic` | 源原理图视图 |
| `symbol_view` | str | — | `symbol` | 目标符号视图 |
| `sort_pins` | str | — | 无 | pin 排序方式（不给就按原理图顺序） |
| `overwrite` | bool | — | `false` | 已存在同名符号时是否覆盖 |

> 原理图里要有引脚（`place_pin`）；改过引脚后要重新生成一次。

## 4. `virtuoso.symbol.check_and_save` — 检查并保存

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `symbol` | 视图名 |
| `view_type` | str | — | `schematicSymbol` | 视图类型 |

## 5. `virtuoso.symbol.screenshot` — 截屏

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `symbol` | 视图名 |
| `view_type` | str | — | `schematicSymbol` | 视图类型 |
| `window_id` | int | — | 无 | 指定窗口 |
| `region` | list[float] | — | 无 | `[x0,y0,x1,y1]` |
| `toplevel` / `central_widget` / `leave_open` | bool | — | `true`/`true`/`false` | 与 schematic 同义 |

返回：`data.value.local_path`（注意：symbol 的截图路径在 `value` 里）。

## 6. 注意事项

- 手写符号时，"引脚名"和"器件名/实例名"是不同 `label_kind`，混用会画错层。
- `set_pin_order` 里出现的名字必须在符号里存在，否则报 `pin not found: xxx`。
- 生成符号会覆盖同名视图——只想微调就别重新生成，直接 `write` 改。
