# Schematic 原子操作调查（F）

> 日期：2026-09-17
> 目的：为 schematic 业务包确定“一个 read(focus) + 对称写原子”的最终清单。
> 结论先行：net 是 label/pin 派生的，不作为对象；note 是纯注释；property 只保留继承连接用途。

## 1. 对象 × 动作矩阵

证据缩写：`ops`=schematic/ops.py，`par`=schematic/params.py，`rdr`=schematic/reader.py，`ex`=examples/01_virtuoso/schematic/，`pln`=schematic/planner.py。

| 对象 | create | delete | rename | set/update | read |
|---|---|---|---|---|---|
| instance | ✅ `dbCreateInst` / `dbCreateInst` by master（ops:14-66） | ✅ 例 `dbDeleteObject(inst)`（ex06:37-44） | ✅ 例 `inst~>name = new`（ex05:31-43） | ✅ `cdfUpdateInstParam` + callbacks（par:126-235） | ✅ unified `INST\|...`（rdr:61-234） |
| wire | ✅ `schCreateWire`（ops:69-81）；端子间自动连线（ops:470-490） | ❌ 无公开 builder；可用 `dbDeleteObject` 删 line shape | ❌ 无 | — | ✅ legacy placement `WIRES`（rdr 后半 `read_placement`） |
| label | ✅ `schCreateWireLabel`（ops:84-102） | ❌ 无公开 builder | ❌ **无公开 label-rename**；见 §2 | ✅ 建时设 justify/orient/font/height/alias | ✅ placement `LABELS`（`label~>theLabel`、xy） |
| pin | ✅ `schCreatePin`（ops:373-393）；端子处建 pin（ops:396-414） | ❌ 无公开 builder | ❌ 无 evidence | — | ✅ unified `PINS`（name/direction/numBits） |
| net | 由 label/pin 派生，无显式 create | ❌ | ✅ `dbRenameNet(netId,new)` 存在但**无意义**（check 后由 label 重建） | — | ✅ unified `NETS` |
| parameter(CDF) | — | — | — | ✅ `set_instance_params`（par） | ✅ `read_instance_params`（rdr 后半） |
| property | ✅ `dbCreateProp(obj,name,type,val)` 通用；旧代码只写 netSet/nlAction | ❌ | — | ✅ `dbReplaceProp`（netSet：ops:234-247） | ✅ nlAction 随 unified read 返回 |
| inherited connection | ✅ `schCreateNetExpression`（ops:188-222）；GUI 版 `schHiCreateNetExpression` | ❌ | — | ✅ `schInhConSet`（文档有，旧包未封装） | ❌ |
| note | ✅ `schCreateNoteLabel`（SKILL 文档确认，不影响连接）；旧包未封装 | ❌ | — | — | ✅ unified `NOTES`（rdr） |

## 2. label rename 详情

- “label 名字”有两层：**显示文本**（`schCreateWireLabel` 的 `t_text`，对象属性 `theLabel`）与**派生 net 名**（`net~>name`）。
- 旧包**没有公开的 label rename 操作**；读者报告的 labels 只有 `{text, xy}`（reader.py `read_placement`）。
- 改显示文本应改 label 文本属性（等价于重建一个 wire label 的文本）；改 net 名用 `dbRenameNet`，但用户确认这是派生对象、check/save 会由 label 重建，**不作为业务操作**。
- 建议业务语义：`rename_label(lib, cell, old_text, new_text)` = 改显示文本；不提供 `rename_net`。

## 3. read 的 focus 映射

| focus | 旧实现 | 返回字段 |
|---|---|---|
| overview | `read_schematic`（rdr 主 API） | instances(+terms+params+nlAction)、nets、pins、notes；可选位置 |
| positions | `read_placement` | instances(name/lib/cell/xy/orient)、pins、labels(text/xy)、wires |
| connectivity | `read_connectivity` | instances(name/lib/cell)、nets(name+connections)、pins |
| params | `read_instance_params` | 每实例 name/lib/cell/params |

建议 `read(lib, cell, focus)`，四档直接映射；overview 的 `include_positions` 由 focus=positions 取代。

## 4. planner 发出的原语

planner.py 只 emit 两种写：`schematic_create_inst_by_master_name`（pln:415）与 `schematic_create_pin`（pln:444）。未来的 apply 至少需要 place_instance 与 place_pin；wire/label 不在 planner 词汇内。

## 5. 推荐核心清单

| 操作 | 输入 → 输出 | 判定 |
|---|---|---|
| read | lib/cell/focus → 该 focus 结构 | KEEP（唯一读） |
| place_instance | lib/cell + master(lib/cell/view) + name + xy + orient | KEEP |
| delete_instance | lib/cell + name | KEEP |
| rename_instance | lib/cell + old + new（属性赋值） | KEEP（有旧例） |
| set_instance_params | lib/cell + inst + params dict | KEEP |
| place_wire | lib/cell + points + style/mode | KEEP |
| delete_wire | lib/cell + 选择条件（旧无；机制 dbDeleteObject line shape） | KEEP（对称） |
| place_label | lib/cell + text + xy + justify/orient/font/height | KEEP |
| delete_label | lib/cell + text/xy 定位 | KEEP（对称） |
| rename_label | lib/cell + old_text + new_text | KEEP（改显示文本） |
| place_pin | lib/cell + name + direction + xy + orient | KEEP |
| delete_pin | lib/cell + name（删 terminal） | KEEP（对称） |
| rename_pin | — | DROP（无 evidence，需要再查） |
| set_net_expression | lib/cell + net + expression（schCreateNetExpression）/ 实例 override(netSet) | MERGE：一个操作两个子形态 |
| note 操作 | — | DROP（纯注释） |
| net 操作 | — | DROP（派生） |
| 通用 property 接口 | — | DROP（只保留 netSet 语义） |

## 6. 待定

- `rename_pin` 是否进核心（旧代码无；Cadence 中 terminal 名属性改写待验证）。
- `delete_wire/delete_label/delete_pin` 的定位参数用什么（name/text/xy/层），旧代码没有现成约定。
- `set_net_expression` 一个操作合并两个形态，还是拆 `set_net_expression`（wire 侧）与 `set_instance_net_expression`（实例 override）。
- focus 四档之外是否保留 `include_positions` 兼容开关。