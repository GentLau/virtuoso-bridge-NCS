# 上层业务包：schematic

> 版本：Draft v4
> 日期：2026-09-28
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：Draft v3（坐标口径再收口：**单点一律 `pos`**，弃用 `xy`，**不拆成两个字段**；见 §1.3）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

核心只有读和写。写是按对象对称的原子操作：instance / wire / label / pin 各有 place、delete、rename、set。net 是 label/pin 的派生对象，不做操作。

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read | `focus` 可选，可组合；不填=全部；可带实例过滤与参数白名单 | 开只读 → 按 focus 执行对应 SKILL 段 → 解析 | S |
| screenshot | 原理图截图：默认 `lib/cell/view`，可选 `window_id`；格式 PNG | 找/开窗口 → hiWindowSaveImage → 下载 | S+D |

- focus 取值：`positions`（实例 `pos`/orient + labels + wires + **每个实例端子的实际中心坐标**）、`connectivity`（实例 + nets + pins）、`params`（每实例 CDF 参数）；不填=全部（实例/terms/params/nets/pins/notes）；
- focus 支持组合，例如 `positions,connectivity`；
- 可选 `param_filter`：参数名列表，只返回白名单内 CDF 参数，防参数淹死；
- 可选 `object_filter`：每个对象一个条目，**不写默认 `all`**；条目可以是 `none`（该类一个都不读）。重点是"只看某实例的端子/位置"，不把整图读一遍：
  - `instance`：`all`（默认）/ `none` / `{"names":[...]}` / `{"region":[pos0, pos1]}`；
  - `wire` / `label` / `pin` / `note`：`all`（默认）/ `none` / `{"region":[pos0, pos1]}`。
- object_filter 只对 `positions`、`params`、不填=全部生效；`focus` 含 `connectivity` 时忽略（连接关系必须全量）。
- `screenshot`：目标默认 `lib/cell/view`，可选 `window_id`；可选 `region=[pos0, pos1]`（user units，截前 `hiZoomIn(window, bBox)` 把区域填满窗口）；`toplevel` / `centralWidget` 暴露；`leave_open` 默认关窗；格式固定 PNG；远端**暂存**于 daemon role root 的 screenshots/，下载后清理；留存位置是客户端工作目录 artifact/screenshots/（P-091 三包统一口径）。

### 1.2 写操作（改变业务服务器状态）

对外只有一个**通用写操作** `write`：调用方一次给一组原子命令，业务包内部组织 SKILL 逐个改写，最后统一 check/save。调用方不会按单个原子调用多次。

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| write | 通用写：`lib/cell/view + commands[]` | 开 cellview(a) → 逐命令执行 → schCheck → dbSave | S |
| check_and_save | 对目标显式执行 `schCheck` + `dbSave` | 开 cellview(a) → check → save | S |

`write.commands` 每项 = `{"op": 原子名, ...该原子参数}`；业务包按顺序执行并保留每步痕迹。

**write 支持的原子命令**：每个原子 = `op` + **索引**（要动哪个对象）+ 附加参数。

| 原子名 | 索引（动哪个） | 附加参数 |
|---|---|---|
| place_instance | —（新建） | `master_lib, master_cell, master_view="symbol", name, pos, orient="R0"` |
| delete_instance | `name` | — |
| rename_instance | `name` | `new_name` |
| set_instance_params | `name` | `params: dict` |
| set_term_nets | `name` | `term_nets: {term: net}`；内部超短 stub + label；可选样式 `justify/orient/font/height/stub_length`（不传用默认） |
| place_wire | —（新建） | `points: [pos, …]`（≥2 点）；可选 `entry/route/width/color/line_style`（传了才拼，不传用底层默认）；可选 `x_spacing/y_spacing`（创建期 X/Y 吸附网格，默认 0；不是 wire-to-wire spacing，不落 DB） |
| delete_wire | `points`（wire 是多个 2 点 line segment，按 `pos` 端点匹配） | — |
| set_wire_properties | `points` | `width?, color?, line_style?` |
| place_label | —（新建） | `text, pos`；可选样式 `justify/orient/font/height/alias`（不传用默认） |
| delete_label | `pos`（可选加 `text` 消歧义） | — |
| rename_label | `pos`（可选加 `old_text` 消歧义） | `new_text` |
| set_label_properties | `pos`（可选加 `text`） | `justify?, orient?, font?, height?` |
| place_pin | —（新建） | `name, pos`；`direction`/`orient`；`off_sheet`（`schCreatePin` 第 5 个必选实参）；可选 `power_sens`/`ground_sens`（必须是目标 cellview 内已存在的 terminal 名）、`sig_type` ∈ `analog/clock/ground/power/reset/scan/signal/tieHi/tieLo/tieOff` |
| delete_pin | `pos` | — |
| rename_pin | `pos` | `new_name` |
| set_pin_properties | `pos` | `direction?` |
| place_note | —（新建） | `text, pos, justify="lowerLeft", orient="R0", font="stick", height=0.0625, type="normalLabel"` |
| delete_note | `pos`（可选加 `text`） | — |
| rename_note | `pos`（可选加 `old_text`） | `new_text` |
| set_note_properties | `pos`（可选加 `text`） | `justify?, orient?, font?, height?` |

`place_wire` 的 `x_spacing` / `y_spacing` 是传给底层 `schCreateWire` 的
**创建期 X/Y 吸附网格步距**（默认 `0`）：只影响创建时控制点及
route 生成顶点的吸附，不是两根线之间的固定间距，也不会作为 wire 的 DB
属性保存或读回。默认 `0` **不保证**原样保留输入浮点坐标；底层仍可能使用
默认吸附网格（本环境实测步距 `0.00625`）。

`place_pin` 的尾部可选实参按位置拼装：给 `ground_sens`/`sig_type` 而未给前面的
`power_sens` 时补 `nil`；非法 `sig_type` 在写前结构化拒绝。`off_sheet=true`
需要环境提供可用的 off-sheet pin master；当前测试环境没有该 master 时底层会报错，
包不伪造成功（P-113）。

#### 1.3 坐标口径（P-074 定版）

- **单点坐标一律一个字段 `pos`**，值是两元素数组 `[x, y]`（user units）：索引（delete/rename/set_*）、新建（place_*）、读回（read 的实例/端子/label/pin/note）**同一口径**；
- **不再出现 `xy` 字段**；**不把坐标拆成两个字段**（`{"x":…,"y":…}` 一律非法）；`pos` 缺字段/形状不对时校验必须报明缺哪个字段（不得裸 `KeyError`）；
- 多点：`points: [pos, …]`；区域/矩形：`region` / `bbox` 一律**对角两点** `[pos0, pos1]`（read 与 write 同形，**不再用四元组**）；
- 与 `read` 对称：read 返回的点（实例、端子、label、pin、note、wire 的顶点）全部用 `pos`/`points`，写回时可直接复用，不需要字段换算。

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 不在本版

- 继承连接（`schCreateNetExpression` / 实例 `netSet` override）——后续扩展；

- net 的 rename/create/delete——派生对象，不做；
- 通用 DB property 接口——不做。

## 3. 待修订

- **`pos` 坐标口径已落地**（P-074）：schematic / symbol / layout 的单点统一 `pos`，`xy`/拆字段直接判非法；
- 唯一 name 索引只有 instance；wire=line segment 列表（无 name），label/note/pin 均按 `pos` 索引（可加 text/name 消歧义）；
- wire 的 `points` 匹配需要定义容差；pin 是 purpose=pin 的实例图形，按 `pos` 定位；
- `region` 的判定用对象 bBox 还是 `pos` 待定。
- rename / delete / set 原子均已实现，按 `pos` 索引；label/note/pin 可加文本或名字消歧义；
- `write` 逐条执行原子，全部成功后统一 check/save；中途失败释放 edit handle 并返回失败步骤；
- `check_and_save` 供显式补一次校验保存；读写目标都必须带 `view`，默认 `"schematic"`，不假设只有这个视图名。
