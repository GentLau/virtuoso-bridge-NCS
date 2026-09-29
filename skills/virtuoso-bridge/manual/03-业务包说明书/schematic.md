# schematic —— 原理图

原理图（schematic）的读、写、检查保存、截屏。写操作是**原子命令组**：一次给一组命令，
按顺序执行，遇到第一个失败就停。

## 1. `virtuoso.schematic.read` — 读原理图

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `view` | str | — | `schematic` | 视图名 |
| `focus` | str | — | 全部 | 逗号分隔，可取 `positions` / `connectivity` / `params` 的组合，如 `"positions,params"` |
| `param_filter` | list[str] | — | 无 | 只要这些参数名（配合 `focus` 含 `params`） |
| `object_filter` | dict | — | 无 | 只取某个区域内的对象，如 `{"instances":{"region":[x0,y0,x1,y1]}}` |

返回 `data.value`：

| 字段 | 内容 |
|---|---|
| `instances` | 实例列表：`name` / `lib` / `cell` / `master_view` / `pos` / `orient` / `bBox` / `numInst` / `terms`（端子→网络）/ `params`（参数）/ `terminals`（端子坐标） |
| `nets` | 网络 → 连接信息 |
| `pins` | 引脚列表 |
| `labels` | 标签列表 |
| `wires` | 连线列表 |
| `notes` | 注释列表 |

```json
{"operation":"virtuoso.schematic.read","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic","focus":"connectivity"}
```

## 2. `virtuoso.schematic.write` — 写原理图

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `commands` | list[dict] | ✅ | — | 原子命令组，见下表 |
| `view` | str | — | `schematic` | 视图名 |

返回 `data.value` = `{"applied": n}`（成功应用了几条命令）；失败时 `error` 形如
`"... (applied: 2/5)"`，`data.steps` 里有每条命令的结果。

### 2.1 原子命令

坐标单位是用户单位（一般 µm）；`x`/`y` 是数字，`points` 是 `[[x,y], …]`。

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_instance` | `master_lib` | str | ✅ | — | 被放置器件的库 |
| | `master_cell` | str | ✅ | — | 器件名 |
| | `master_view` | str | — | `symbol` | 器件视图 |
| | `name` | str | ✅ | — | 实例名（图中唯一） |
| | `x` / `y` | number | ✅ | — | 放置坐标 |
| | `orient` | str | — | `R0` | 方向，如 `R0`/`R90`/`MX`/`MY` |
| `delete_instance` | `name` | str | ✅ | — | 实例名 |
| `rename_instance` | `name` / `new_name` | str | ✅ | — | 原名 / 新名 |
| `set_instance_params` | `name` | str | ✅ | — | 实例名 |
| | `params` | dict | ✅ | — | 参数名→值，如 `{"w":"1u","l":"60n"}`；参数名必须是该器件的 CDF 参数 |
| `set_term_nets` | `name` | str | ✅ | — | 实例名 |
| | `term_nets` | dict | ✅ | — | 端子→网络，如 `{"G":"net1","D":"OUT"}` |
| | `justify` / `orient` / `font` | str | — | `lowerCenter`/`R0`/`stick` | 生成的网络标签样式 |
| | `height` | number | — | `0.0625` | 标签字高 |
| | `stub_length` | number | — | 按引脚几何自动推导 | 从端子引出的短线长度 |
| `place_wire` | `points` | list | ✅ | — | 折线端点，至少两点 |
| | `entry` | str | — | `route` | 连线类型 |
| | `route` | str | — | `full` | 走线方式 |
| | `x_spacing` / `y_spacing` | number | — | `0` | 总线间距 |
| | `width` / `color` / `line_style` | number/str | — | 无 | 线宽/颜色/线型 |
| `delete_wire` | `points` | list | ✅ | — | 按这条折线的范围删除 |
| `set_wire_properties` | `points` | list | ✅ | — | 定位用 |
| | `width` / `color` / `line_style` | number/str | — | 无 | 至少要给一个 |
| `place_label` | `x` / `y` / `text` | number/number/str | ✅ | — | 标签内容与位置 |
| | `justify` / `orient` / `font` | str | — | `lowerCenter`/`R0`/`stick` | 样式 |
| | `height` | number | — | `0.0625` | 字高 |
| | `alias` | bool | — | `false` | 是否作为别名标签 |
| `delete_label` | `x` / `y` | number | ✅ | — | 按位置删除 |
| `rename_label` | `x` / `y` / `new_text` | number/number/str | ✅ | — | 按位置改名 |
| `set_label_properties` | `x` / `y` | number | ✅ | — | 定位 |
| | `justify` / `orient` / `font` / `height` | str/number | — | — | 至少给一个 |
| `place_pin` | `name` / `x` / `y` | str/number/number | ✅ | — | 引脚名与位置 |
| | `direction` | str | — | `inputOutput` | `input` / `output` / `inputOutput` / `switch` / `jumper` |
| | `orient` | str | — | `R0` | 方向 |
| | `off_sheet` / `power_sens` / `ground_sens` / `sig_type` | bool/str | — | 无 | 引脚高级属性（一般不用给） |
| `delete_pin` | `x` / `y` | number | ✅ | — | 按位置删除 |
| `rename_pin` | `x` / `y` / `new_name` | number/str | ✅ | — | 按位置改名 |
| `set_pin_properties` | `x` / `y` / `direction` | number/str | ✅ | — | 改引脚类型 |
| `place_note` | `x` / `y` / `text` | number/number/str | ✅ | — | 注释文本与位置 |
| | `justify` / `orient` / `font` | str | — | `lowerLeft`/`R0`/`stick` | 样式 |
| | `height` | number | — | `0.0625` | 字高 |
| | `type` | str | — | `normalLabel` | 注释类型 |
| `delete_note` | `x` / `y` | number | ✅ | — | 按位置删除 |
| `rename_note` | `x` / `y` / `new_text` | number/str | ✅ | — | 按位置改名 |
| `set_note_properties` | `x` / `y` | number | ✅ | — | 定位 |
| | `justify` / `orient` / `font` / `height` | str/number | — | — | 至少给一个 |

### 2.2 示例

```json
{"operation":"virtuoso.schematic.write","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic",
 "commands":[
  {"op":"place_pin","name":"IN","x":-2.5,"y":0,"direction":"input"},
  {"op":"place_pin","name":"OUT","x":2.5,"y":0,"direction":"output"},
  {"op":"place_instance","master_lib":"analogLib","master_cell":"nmos4","master_view":"symbol","name":"M0","x":0,"y":-1,"orient":"R0"},
  {"op":"set_instance_params","name":"M0","params":{"w":"1u","l":"60n"}},
  {"op":"place_wire","points":[[-2.5,0],[-1,0]]},
  {"op":"set_term_nets","name":"M0","term_nets":{"G":"IN","D":"OUT"}}]}
```

## 3. `virtuoso.schematic.check_and_save` — 检查并保存

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `view` | str | — | `schematic` | 视图名 |

用途：让 Virtuoso 做一次一致性检查并落盘；写操作后想确认"保存了"可以用它。

## 4. `virtuoso.schematic.screenshot` — 截屏

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `view` | str | — | `schematic` | 视图名 |
| `window_id` | int | — | 无 | 指定窗口；不给就自动找 |
| `region` | list[float] | — | 无 | 只截 `[x0,y0,x1,y1]` 区域 |
| `toplevel` | bool | — | `true` | 是否截顶层窗口 |
| `central_widget` | bool | — | `true` | 是否只截中央绘图区 |
| `leave_open` | bool | — | `false` | 截完是否保持窗口打开 |

返回：`data.local_path`（截图在本机的落点）。

## 5. 注意事项

- 放器件前确认 `master_lib.master_cell.master_view` 存在（用 cellview 包查）。
- 参数名必须是器件 CDF 里真实存在的名字，否则报 `unknown CDF param: xxx`。
- 视图被 Virtuoso 窗口打开时写入可能报锁；写之前先让用户关掉该视图。
- 写完建议 `read` 一次复核连接关系，不要只信 `ok=true`。
