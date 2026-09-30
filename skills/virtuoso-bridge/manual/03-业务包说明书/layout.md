# layout —— 版图与 GDS

版图的读、写、GDS 导入导出、窗口显示控制、截屏。

点/框约定：`xy` = `[x,y]`；`points` = `[[x,y], …]`；`bbox` = `[x0,y0,x1,y1]`；`layers` = `[["M1","drawing"], …]`。

## 1. `virtuoso.layout.read` — 读版图

**功能**：读取版图内容（图形、实例、via），可按区域/图层过滤。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` / `view_type` | str | — | `layout` / `maskLayout` | 视图 |
| `focus` | list[str] | — | 全部 | `summary` / `shapes` / `instances` / `vias` 的子集 |
| `detail` | str | — | `geometry` | `geometry`（带几何）或 `index`（只给索引，省流量） |
| `object_filter` | dict | — | 无 | 如 `{"shape":{"layers":[["M1","drawing"]],"region":[0,0,10,10]}}` |
| `region_mode` | str | — | `intersect` | `intersect`（相交）或 `contain`（完全包含） |
| `depth` | int | — | `0` | 实例展开层数；**>0 时必须给 `layers` 或 `region` 过滤** |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.summary` | dict | 各类对象计数（按 `focus` 出现） |
| `value.shapes` | list | 图形（图层、类型、几何） |
| `value.instances` | list | 实例（名字、master、位置、方向） |
| `value.vias` | list | via（位置、方向） |

**示例**

```json
// 输入
{"operation":"virtuoso.layout.read","token":"TOKEN","library":"mylib","cell":"inv","view":"layout","focus":["summary"],"detail":"index"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"summary":{"shapes":12,"instances":1,"vias":2}}}
```

## 2. `virtuoso.layout.write` — 写版图

**功能**：用原子命令批量画版图（图形、实例、阵列、via、标签）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令组 |
| `view` / `view_type` | str | — | `layout` / `maskLayout` | 视图 |
| `strict_lpp` | bool | — | `false` | 图层对不上时是否严格报错 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.applied` | int | 成功应用的命令条数 |

### 2.1 图形类原子

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_rect` | `layer`, `purpose`, `bbox` | str,str,list | ✅ | — | 矩形 |
| `place_polygon` | `layer`, `purpose`, `points` | str,str,list | ✅ | — | 多边形（≥3 点） |
| `place_line` | `layer`, `purpose`, `points` | str,str,list | ✅ | — | 直线（正好 2 点） |
| `place_path` | `layer`, `purpose`, `points`, `width` | str,str,list,number | ✅ | — | 走线（≥2 点） |
| | `style` | str | — | 无 | `extendExtend` / `roundRound` / `truncateExtend` / `squareFlush` / `octagonEnded` 等 |
| `place_label` | `layer`, `purpose`, `xy`, `text` | str,str,list,str | ✅ | — | 文字 |
| | `justify`/`orient`/`font`/`height` | str/number | — | `lowerLeft`/`R0`/`fixed`/`1.0` | 样式 |
| `delete_shape` | `kind`（`rect`/`polygon`/`path`/`line`/`ellipse`）+ `bbox` 或 `points` | — | ✅ | — | 删除；`all=true` 删全部匹配 |
| `set_shape_properties` | `kind` + 定位参数 + `new_bbox`/`new_points`/`new_width` | — | ✅ | — | 至少给一个新值 |
| `delete_shapes_on_layer` | `layer`, `purpose` | str | ✅ | — | 整层清理；`types` 限定类型 |

### 2.2 实例、阵列、via、标签

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_instance` | `master_lib`, `master_cell`, `name`, `xy` | str,str,str,list | ✅ | — | 放实例 |
| | `master_view`/`orient`/`num_inst` | str/number | — | `layout`/`R0`/无 | 视图/方向/多实例数 |
| `delete_instance` | `name` | str | ✅ | — | 删除 |
| `rename_instance` | `name`, `new_name` | str | ✅ | — | 改名 |
| `set_instance_properties` | `name` + `new_xy`/`new_orient` | — | ✅（name） | — | 移动/旋转 |
| `place_mosaic` | `master_lib`, `master_cell`, `name`, `xy`, `rows`, `cols`, `row_pitch`, `col_pitch` | str/number | ✅ | — | 阵列 |
| | `master_view` / `orient` | str | — | `layout` / `R0` | |
| `delete_mosaic` | `name` | str | ✅ | — | 删阵列 |
| `place_via` | `via_name`, `xy` | str,list | ✅ | — | `via_name` 是工艺库里的 via 定义名 |
| | `orient` | str | — | `R0` | 方向 |
| `delete_via` | `xy` | list | ✅ | — | 按位置删；可选 `orient` |
| `delete_label` | `xy` | list | ✅ | — | 定位；可用 `text`/`layer` 限定 |
| `rename_label` | `xy`, `new_text` | list,str | ✅ | — | 改名 |
| `set_label_properties` | `xy` + 至少一个 `new_*` | — | ✅（xy） | — | `new_text`/`new_xy`/`new_height`/`new_justify`/`new_orient`/`new_font` |

**示例**

```json
// 输入
{"operation":"virtuoso.layout.write","token":"TOKEN","library":"mylib","cell":"inv","view":"layout",
 "commands":[
  {"op":"place_rect","layer":"M1","purpose":"drawing","bbox":[0,0,1,1]},
  {"op":"place_path","layer":"M1","purpose":"drawing","points":[[0,0],[2,0]],"width":0.1},
  {"op":"place_via","via_name":"M1_M2","xy":[1,1]}]}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"applied":3}}
```

## 3. `virtuoso.layout.gds` — GDS 导入/导出

**功能**：把版图导出成 GDS，或把 GDS 导入成版图。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `action` | str | ✅ | — | `export` 或 `import` |
| `library` | str | ✅ | — | 库名 |
| `cell` | str | — | 无 | cell 名（导出单个 cell 时给） |
| `view` / `view_type` | str | — | `layout` / `maskLayout` | 视图 |
| `file_path` | str | — | 无 | GDS 路径；导出时是本机路径 |
| `file_is_local` | bool | — | `true` | `true` = 文件在调用方本机（自动搬运）；`false` = 已在目标机器 |
| `layer_map` / `layer_map_is_local` | str/bool | — | 无 / `true` | 图层映射文件 |
| `ref_lib_file` / `ref_lib_file_is_local` | str/bool | — | 无 / `true` | 参考库列表 |
| `tech_lib` / `top_cell` | str | — | 无 | 导入时的工艺库与顶层 cell |
| `log_path` / `poll_interval` / `cleanup_policy` | str/number/str | — | 无/无/`success` | 日志、轮询间隔、清理策略 |
| `timeout` | number | — | `30` | **导入导出都可能慢，建议给大** |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value` | dict | 本次动作的结果（按 `action` 分组：导出文件位置 / 导入的 cell 与视图） |

**示例**

```json
// 输入（导出）
{"operation":"virtuoso.layout.gds","token":"TOKEN","action":"export","library":"mylib","cell":"inv","view":"layout","file_path":"C:/work/inv.gds"}
// 输入（导入）
{"operation":"virtuoso.layout.gds","token":"TOKEN","action":"import","library":"mylib","tech_lib":"tsmcN65","file_path":"C:/work/inv.gds","top_cell":"inv"}
// 输出（data 内容，导出）
{"ok":true,"error":null,"value":{"action":"export","export":{"file_path":"C:/work/inv.gds","cell":"inv"}}}
// 输出（data 内容，导入）
{"ok":true,"error":null,"value":{"action":"import","import":{"library":"mylib","top_cell":"inv"}}}
```

## 4. `virtuoso.layout.display` — 控制版图窗口显示

**功能**：调整版图窗口的显示（缩放、图层显隐、当前编辑层）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 显示原子 |
| `view` / `view_type` | str | — | `layout` / `maskLayout` | 视图 |

显示原子：

| 原子 | 参数 | 说明 |
|---|---|---|
| `fit_view` | 无 | 缩放到全图 |
| `zoom` | `scale`（>0） | 按比例缩放 |
| `show_only_layers` | `layers` | 只显示这些图层 |
| `set_layers_visible` | `layers`, `visible` | 批量设置显隐 |
| `set_entry_layer` | `layer`, `purpose`（或 `layers[0]`） | 设置当前编辑层 |

**返回**：`value.applied` = 成功应用的命令条数。

```json
// 输入
{"operation":"virtuoso.layout.display","token":"TOKEN","library":"mylib","cell":"inv","view":"layout",
 "commands":[{"op":"fit_view"},{"op":"set_layers_visible","layers":[["M1","drawing"]],"visible":true}]}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"applied":2}}
```

## 5. `virtuoso.layout.screenshot` — 截屏

**功能**：版图窗口截图并送回本机。

参数与 schematic 截屏一致（`library`/`cell` 必填，`view`/`view_type`/`window_id`/`region`/`toplevel`/`central_widget`/`leave_open` 可选）。

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.local_path` | str | 截图落点 |
| `value.bbox` / `value.shape_count` / `value.instance_count` / `value.via_count` | — | 截图范围与对象计数 |

```json
// 输入
{"operation":"virtuoso.layout.screenshot","token":"TOKEN","library":"mylib","cell":"inv","view":"layout"}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"local_path":"C:/work/artifact/screenshots/inv_layout_1.png","bbox":[0,0,2,1],"shape_count":12,"instance_count":0,"via_count":2}}
```

## 6. 注意事项

- 写版图前库必须已绑定工艺库，否则 `layer`/`purpose` 解析失败。
- `place_via` 的 `via_name` 是工艺库里的 via 定义名，不是图层名。
- 大版图 `read` 建议用 `detail:"index"` 或加 `object_filter`。
