# 上层业务包：schematic

> 版本：Draft v2
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：Draft v1（核心收敛为：一个 read + 按对象对称的写原子）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

核心只有读和写。写是按对象对称的原子操作：instance / wire / label / pin 各有 place、delete、rename、set。net 是 label/pin 的派生对象，不做操作。

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read | `focus` 可选，可组合；不填=全部；可带实例过滤与参数白名单 | 开只读 → 按 focus 执行对应 SKILL 段 → 解析 | S |
| screenshot | 原理图截图：默认 `lib/cell/view`，可选 `window_id`；格式 PNG | 找/开窗口 → hiWindowSaveImage → 下载 | S+D |

- focus 取值：`positions`（实例 xy/orient + labels + wires + **每个实例端子的实际中心坐标**）、`connectivity`（实例 + nets + pins）、`params`（每实例 CDF 参数）；不填=全部（实例/terms/params/nets/pins/notes）；
- focus 支持组合，例如 `positions,connectivity`；
- 可选 `param_filter`：参数名列表，只返回白名单内 CDF 参数，防参数淹死；
- 可选 `object_filter`：每个对象一个条目，**不写默认 `all`**；条目可以是 `none`（该类一个都不读）。重点是"只看某实例的端子/位置"，不把整图读一遍：
  - `instance`：`all`（默认）/ `none` / `{"names":[...]}` / `{"region":[x1,y1,x2,y2]}`；
  - `wire` / `label` / `pin` / `note`：`all`（默认）/ `none` / `{"region":[...]}`。
- object_filter 只对 `positions`、`params`、不填=全部生效；`focus` 含 `connectivity` 时忽略（连接关系必须全量）。
- `screenshot`：目标默认 `lib/cell/view`，可选 `window_id`；可选 `region=[x1,y1,x2,y2]`（user units，截前 `hiZoomIn(window, bBox)` 把区域填满窗口）；`toplevel` / `centralWidget` 暴露；`leave_open` 默认关窗；格式固定 PNG；远端存 daemon role root 的 screenshots/；本地存客户端工作目录 artifact/screenshots/。

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
| place_instance | —（新建） | `master_lib, master_cell, master_view="symbol", name, x, y, orient="R0"` |
| delete_instance | `name` | — |
| rename_instance | `name` | `new_name` |
| set_instance_params | `name` | `params: dict` |
| set_term_nets | `name` | `term_nets: {term: net}`；内部超短 stub + label；可选样式 `justify/orient/font/height/stub_length`（不传用默认） |
| place_wire | —（新建） | `points[[x,y],...]`；可选 `entry/route/width/color/line_style`（传了才拼，不传用底层默认） |
| delete_wire | `points`（wire 是多个 2 点 line segment，按端点匹配） | — |
| set_wire_properties | `points` | `width?, color?, line_style?` |
| place_label | —（新建） | `text, x, y`；可选样式 `justify/orient/font/height/alias`（不传用默认） |
| delete_label | `xy`（可选加 `text` 消歧义） | — |
| rename_label | `xy`（可选加 `old_text` 消歧义） | `new_text` |
| set_label_properties | `xy`（可选加 `text`） | `justify?, orient?, font?, height?` |
| place_pin | —（新建） | `name, x, y`；可选 `direction/orient/off_sheet/power_sens/ground_sens/sig_type`（不传用默认/不拼） |
| delete_pin | `xy` | — |
| rename_pin | `xy` | `new_name` |
| set_pin_properties | `xy` | `direction?` |
| place_note | —（新建） | `text, x, y, justify="lowerLeft", orient="R0", font="stick", height=0.0625, type="normalLabel"` |
| delete_note | `xy`（可选加 `text`） | — |
| rename_note | `xy`（可选加 `old_text`） | `new_text` |
| set_note_properties | `xy`（可选加 `text`） | `justify?, orient?, font?, height?` |

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 不在本版

- 继承连接（`schCreateNetExpression` / 实例 `netSet` override）——后续扩展；

- net 的 rename/create/delete——派生对象，不做；
- 通用 DB property 接口——不做。

## 3. 待修订

- 唯一 name 索引只有 instance；wire=line segment 列表（无 name），label/note/pin 均按 xy 索引（可加 text/name 消歧义）；
- wire 的 points 匹配需要定义容差；pin 是 purpose=pin 的实例图形，按 xy 定位；
- `region` 的判定用对象 bBox 还是 xy 待定。
- rename_label / rename_pin / rename_note / set_* 在旧代码中没有公开 builder，SKILL 机制需真机验证后再定实现；
- delete_wire / delete_label 的定位参数（points / bbox / text）待定；
- `param_whitelist` 用请求内联 `list[str]` 还是沿用 YAML 过滤文件，待定；
- `write` 内部是逐命令 `execute_skill` 后统一 check/save，还是把所有命令拼成一个 SKILL 脚本一次执行（二者步骤痕迹粒度不同），待定；
- `check_and_save` 供显式补一次校验保存；读写目标都必须带 `view`，默认 `"schematic"`，不假设只有这个视图名。