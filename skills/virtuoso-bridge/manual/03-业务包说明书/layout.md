# layout —— 版图与 GDS

版图（layout）的读、写、GDS 导入导出、窗口显示控制、截屏。

点、框约定：`xy` = `[x,y]`；`points` = `[[x,y], …]`；`bbox` = `[x0,y0,x1,y1]`；
`layers` = `[["M1","drawing"], …]`（图层名 + 用途）。

## 1. `virtuoso.layout.read` — 读版图

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `layout` | 视图名 |
| `view_type` | str | — | `maskLayout` | 视图类型 |
| `focus` | list[str] | — | 全部 | `summary` / `shapes` / `instances` / `vias` 的子集 |
| `detail` | str | — | `geometry` | `geometry`（带几何）或 `index`（只给索引，省流量） |
| `object_filter` | dict | — | 无 | 见下 |
| `region_mode` | str | — | `intersect` | 区域判定：`intersect`（相交）或 `contain`（完全包含） |
| `depth` | int | — | `0` | 实例展开层数；**>0 时必须给 `layers` 或 `region` 过滤** |

`object_filter` 形如：

```json
{"shape":{"layers":[["M1","drawing"]],"region":[0,0,10,10]},
 "instance":{"region":[0,0,10,10]},
 "via":{"region":[0,0,10,10]}}
```

## 2. `virtuoso.layout.write` — 写版图

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令组 |
| `view` / `view_type` | str | — | `layout` / `maskLayout` | 视图 |
| `strict_lpp` | bool | — | `false` | 图层对不上时是否严格报错 |

### 2.1 图形类原子

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_rect` | `layer`, `purpose`, `bbox` | str,str,list | ✅ | — | 矩形 |
| `place_polygon` | `layer`, `purpose`, `points` | str,str,list | ✅ | — | 多边形（≥3 点） |
| `place_line` | `layer`, `purpose`, `points` | str,str,list | ✅ | — | 直线（**正好 2 点**） |
| `place_path` | `layer`, `purpose`, `points`, `width` | str,str,list,number | ✅ | — | 带宽度走线（≥2 点） |
| | `style` | str | — | 无 | 端点样式：`extendExtend` / `roundRound` / `truncateExtend` / `squareFlush` / `octagonEnded` 等 |
| `place_label` | `layer`, `purpose`, `xy`, `text` | str,str,list,str | ✅ | — | 文字 |
| | `justify` / `orient` / `font` / `height` | str/number | — | `lowerLeft`/`R0`/`fixed`/`1.0` | 样式 |
| `delete_shape` | `kind` | str | ✅ | — | `rect` / `polygon` / `path` / `line` / `ellipse` |
| | `bbox` 或 `points` | list | ✅ | — | 定位（rect/ellipse 用 bbox，其余用 points） |
| | `layer`, `purpose`, `all` | str/bool | — | 无/false | `all=true` 时删除所有匹配（否则要求唯一匹配） |
| `set_shape_properties` | `kind` + 定位参数 | — | ✅ | — | 同上 |
| | `new_bbox` / `new_points` / `new_width` | list/number | — | 无 | 至少给一个；`new_width` 只对 path |
| `delete_shapes_on_layer` | `layer`, `purpose` | str | ✅ | — | 整层清理 |
| | `types` | list[str] | — | 全部 | 只删这些类型，如 `["rect","path"]` |

### 2.2 实例与阵列

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_instance` | `master_lib`, `master_cell`, `name`, `xy` | str,str,str,list | ✅ | — | 放实例 |
| | `master_view` / `orient` / `num_inst` | str/number | — | `layout` / `R0` / 无 | 视图 / 方向 / 多实例数 |
| `delete_instance` | `name` | str | ✅ | — | 删除 |
| `rename_instance` | `name`, `new_name` | str | ✅ | — | 改名 |
| `set_instance_properties` | `name` | str | ✅ | — | 定位 |
| | `new_xy`, `new_orient` | list/str | — | 无 | 至少给一个 |
| `place_mosaic` | `master_lib`, `master_cell`, `name`, `xy`, `rows`, `cols`, `row_pitch`, `col_pitch` | str/number | ✅ | — | 阵列 |
| | `master_view` / `orient` | str | — | `layout` / `R0` | |
| `delete_mosaic` | `name` | str | ✅ | — | 删除阵列 |

### 2.3 Via 与标签

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_via` | `via_name`, `xy` | str,list | ✅ | — | `via_name` 是工艺库里的 via 定义名 |
| | `orient` | str | — | `R0` | 方向 |
| `delete_via` | `xy` | list | ✅ | — | 按位置删 |
| | `orient` | str | — | `R0` | 方向 |
| `delete_label` | `xy` | list | ✅ | — | 定位；可用 `text`/`layer` 限定 |
| `rename_label` | `xy`, `new_text` | list,str | ✅ | — | 改名 |
| `set_label_properties` | `xy` | list | ✅ | — | 定位 |
| | `new_text`, `new_xy`, `new_height`, `new_justify`, `new_orient`, `new_font` | str/list/number | — | — | 至少给一个 |

## 3. `virtuoso.layout.gds` — GDS 导入/导出

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `action` | str | ✅ | — | `export` 或 `import` |
| `library` | str | ✅ | — | 库名 |
| `cell` | str | — | 无 | cell 名（导出单个 cell 时给；`import` 时可不给） |
| `view` / `view_type` | str | — | `layout` / `maskLayout` | 视图 |
| `file_path` | str | — | 无 | GDS 文件路径：导出时是**本机**路径，导入时按 `file_is_local` 解释 |
| `file_is_local` | bool | — | `true` | `true` = 文件在调用方本机（会自动搬运）；`false` = 文件已在目标机器上 |
| `layer_map` / `layer_map_is_local` | str/bool | — | 无 / `true` | 图层映射文件及其位置 |
| `ref_lib_file` / `ref_lib_file_is_local` | str/bool | — | 无 / `true` | 参考库列表文件及其位置 |
| `tech_lib` | str | — | 无 | 导入时用的工艺库 |
| `top_cell` | str | — | 无 | 导入时的顶层 cell 名 |
| `log_path` | str | — | 无 | 工具日志落点 |
| `poll_interval` | number | — | 无 | 轮询间隔（秒） |
| `cleanup_policy` | str | — | `success` | 成功/失败后是否清理中间文件 |
| `timeout` | number | — | `30` | **导出/导入都可能很慢，建议显式给大值** |

```json
{"operation":"virtuoso.layout.gds","token":"TOKEN","action":"export","library":"mylib","cell":"inv","view":"layout","file_path":"C:/work/inv.gds"}
{"operation":"virtuoso.layout.gds","token":"TOKEN","action":"import","library":"mylib","tech_lib":"tsmcN65","file_path":"C:/work/inv.gds","top_cell":"inv"}
```

## 4. `virtuoso.layout.display` — 控制版图窗口显示

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 显示原子，见下 |
| `view` / `view_type` | str | — | `layout` / `maskLayout` | 视图 |

显示原子：

| 原子 | 参数 | 说明 |
|---|---|---|
| `fit_view` | 无 | 缩放到全图 |
| `zoom` | `scale`（number，>0） | 按比例缩放 |
| `show_only_layers` | `layers`（list，非空） | 只显示这些图层，其余隐藏 |
| `set_layers_visible` | `layers`, `visible`（bool） | 批量设置显隐 |
| `set_entry_layer` | `layer`, `purpose`（或 `layers[0]`） | 设置当前编辑层 |

## 5. `virtuoso.layout.screenshot` — 截屏

参数与 schematic 的截屏一致（`library`/`cell` 必填，`view`、`view_type`、`window_id`、`region`、
`toplevel`、`central_widget`、`leave_open` 可选）。
返回：`data.value.local_path`。

## 6. 注意事项

- 写版图前，库必须已绑定工艺库，否则 `layer`/`purpose` 解析失败。
- `place_via` 的 `via_name` 必须是工艺库里的 via 定义名，不是图层名。
- 导出 GDS 前确保目标目录存在；导出完成后再用截图或 `read` 复核。
- 大版图 `read` 建议用 `detail: "index"` 或加 `object_filter`，否则返回体很大。
