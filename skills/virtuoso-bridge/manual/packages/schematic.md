# schematic —— 原理图

原理图的读、写、检查保存、截屏。`write` 是**一组原子命令**：按顺序执行，遇到第一个失败就停。

## 1. `virtuoso.schematic.read` — 读原理图

**功能**：读取视图内容（器件、连线、引脚、标签、参数），可按 `focus` 裁剪。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `schematic` | 视图名 |
| `focus` | str | — | 全部 | 逗号分隔，可取 `positions` / `connectivity` / `params`，如 `"positions,params"` |
| `param_filter` | list[str] | — | 无 | 只要这些参数名（配合含 `params` 的 focus） |
| `object_filter` | dict | — | 无 | 只取某区域内的对象 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.instances` | list | 实例：`name`/`lib`/`cell`/`master_view`/`pos`/`orient`/`bBox`/`numInst`/`terms`/`params`/`terminals` |
| `value.nets` | dict | 网络 → 连接信息 |
| `value.pins` / `value.labels` / `value.wires` / `value.notes` | list | 引脚 / 标签 / 连线 / 注释 |

**示例**

```json
// 输入
{"operation":"virtuoso.schematic.read","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic","focus":"connectivity"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{
  "instances":[{"name":"M0","lib":"analogLib","cell":"nmos4","master_view":"symbol",
                "pos":[0,-1],"orient":"R0","terms":{"G":"IN","D":"OUT"},"params":{"w":"1u"}}],
  "nets":{"IN":[["M0","G"]],"OUT":[["M0","D"]]},
  "pins":[],"labels":[],"wires":[],"notes":[]}}
```

## 2. `virtuoso.schematic.write` — 写原理图

**功能**：用原子命令批量修改原理图（放器件、连线、引脚、标注、改参数……）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令组 |
| `view` | str | — | `schematic` | 视图名 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value` | null | 成功时不返回业务数据；失败时 `error` 会写 `(applied: n/m)` |

### 2.1 原子命令

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `place_instance` | `master_lib`, `master_cell`, `name`, `x`, `y` | str/number | ✅ | — | 放实例 |
| | `master_view` / `orient` | str | — | `symbol` / `R0` | 器件视图与方向 |
| `delete_instance` | `name` | str | ✅ | — | 删实例 |
| `rename_instance` | `name`, `new_name` | str | ✅ | — | 改名 |
| `set_instance_params` | `name`, `params`（`{"w":"1u"}`） | str/dict | ✅ | — | 改参数（参数名必须是该器件的 CDF 参数） |
| `set_term_nets` | `name`, `term_nets`（`{"G":"net1"}`） | str/dict | ✅ | — | 给端子指定网络 |
| | `justify`/`orient`/`font`/`height`/`stub_length` | — | — | `lowerCenter`/`R0`/`stick`/`0.0625`/自动 | 生成的网络标签样式 |
| `place_wire` | `points` | list | ✅ | — | 折线，至少两点 |
| | `entry`/`route`/`x_spacing`/`y_spacing`/`width`/`color`/`line_style` | — | — | `route`/`full`/`0`/`0`/— | 走线样式（注意：即使 spacing 给 0，底层仍可能按默认网格吸附） |
| `delete_wire` | `points` | list | ✅ | — | 按折线范围删除 |
| `set_wire_properties` | `points` + `width`/`color`/`line_style` | list/… | ✅（points） | — | 改线属性 |
| `place_label` | `x`, `y`, `text` | number/str | ✅ | — | 放标签 |
| | `justify`/`orient`/`font`/`height`/`alias` | — | — | `lowerCenter`/`R0`/`stick`/`0.0625`/false | 样式 |
| `delete_label` | `x`, `y` | number | ✅ | — | 按位置删 |
| `rename_label` | `x`, `y`, `new_text` | number/str | ✅ | — | 按位置改名 |
| `set_label_properties` | `x`, `y` + 至少一个样式字段 | — | ✅（x,y） | — | 改标签样式 |
| `place_pin` | `name` + (`pos` 或 `x`+`y`) | str/list | ✅ | — | 放引脚（`pos:[x,y]` 与 `x`/`y` 二选一） |
| | `direction` / `orient` | str | — | `inputOutput` / `R0` | `input`/`output`/`inputOutput`/`switch`/`jumper` |
| | `power_sens` / `ground_sens` | str | — | 无 | 目标 cellview 里**已存在**的端子名；按位置拼装，只给后面的项时前面自动补 `nil` |
| | `sig_type` | str | — | 无 | 取值须在 `analog`/`clock`/`ground`/`power`/`reset`/`scan`/`signal`/`tieHi`/`tieLo`/`tieOff` 之内；非法值在写前被结构化拒绝 |
| | `off_sheet` | bool | — | — | **本环境不支持**，传 `true` 会被明确拒绝 |

> `sig_type` 按 Virtuoso DB 词汇读回：`power` 会被归一化成 `supply`（其余原样）；
> `read` 出来的 `sigType` 以 DB 词汇为准（可能是 `supply`），但 `supply` **不是**合法入参。
| `delete_pin` | `x`, `y` | number | ✅ | — | 按位置删 |
| `rename_pin` | `x`, `y`, `new_name` | number/str | ✅ | — | 按位置改名 |
| `set_pin_properties` | `x`, `y`, `direction` | number/str | ✅ | — | 改引脚类型 |
| `place_note` | `x`, `y`, `text` | number/str | ✅ | — | 放注释 |
| | `justify`/`orient`/`font`/`height`/`type` | — | — | `lowerLeft`/`R0`/`stick`/`0.0625`/`normalLabel` | 样式 |
| `delete_note` | `x`, `y` | number | ✅ | — | 删注释 |
| `rename_note` | `x`, `y`, `new_text` | number/str | ✅ | — | 注释改名 |
| `set_note_properties` | `x`, `y` + 至少一个样式字段 | — | ✅（x,y） | — | 改注释样式 |

**示例**

```json
// 输入
{"operation":"virtuoso.schematic.write","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic",
 "commands":[
  {"op":"place_pin","name":"IN","x":-2.5,"y":0,"direction":"input"},
  {"op":"place_pin","name":"OUT","pos":[2.5,0],"direction":"output"},
  {"op":"place_instance","master_lib":"analogLib","master_cell":"nmos4","master_view":"symbol","name":"M0","x":0,"y":-1},
  {"op":"set_instance_params","name":"M0","params":{"w":"1u","l":"60n"}},
  {"op":"place_wire","points":[[-2.5,0],[-1,0]]},
  {"op":"set_term_nets","name":"M0","term_nets":{"G":"IN","D":"OUT"}}]}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

## 3. `virtuoso.schematic.check_and_save` — 检查并保存

**功能**：让 Virtuoso 做一次一致性检查并落盘。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `schematic` | 视图名 |

**返回**：`value` = null；失败时看 `error` 与 `steps`。

```json
// 输入
{"operation":"virtuoso.schematic.check_and_save","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

## 4. `virtuoso.schematic.screenshot` — 截屏

**功能**：把原理图窗口截图并送回本机。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `schematic` | 视图名 |
| `window_id` | int | — | 自动 | 指定窗口 |
| `region` | list[float] | — | 全图 | `[x0,y0,x1,y1]` |
| `toplevel` / `central_widget` / `leave_open` | bool | — | `true`/`true`/`false` | 顶层窗口 / 只截绘图区 / 截完保持打开 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `local_path` | str | 截图在本机的落点 |

```json
// 输入
{"operation":"virtuoso.schematic.screenshot","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic"}
// 输出（data 内容）
{"ok":true,"error":null,"local_path":"C:/work/artifact/screenshots/inv_schematic_1.png"}
```

## 5. 注意事项

- 放器件前确认 `master_lib/master_cell/master_view` 存在。
- 参数名必须是器件 CDF 里真实存在的名字，否则报 `unknown CDF param: xxx`。
- 视图被窗口打开时写入可能报锁；写完建议 `read` 复核连接关系。
