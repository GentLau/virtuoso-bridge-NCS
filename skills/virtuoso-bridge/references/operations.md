# 操作清单（按任务分组）

读法：**只有"必备"列出的键必须给**；`token`（每个请求必带）和 `timeout`（秒；不给 = 默认 30 秒）在表里省略。
返回值怎么看、失败怎么判，见 `SKILL.md` §1。

路径约定：库路径、GDS 路径这类"远端路径"用 Linux 绝对路径（`/home/...`）；
`*.screenshot` 的 `output_path`、`basic.file.*` 的 `local_path` 是本机路径（`C:/...`）。

## basic —— 直连底层（万能逃生口）

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `basic.skill.execute` | `skill_code` | `timeout` | 在 Virtuoso CIW 执行 SKILL；结果在 `data.result`（`status`/`output`/`errors`/`log`） |
| `basic.command.run` | `cmd` | `timeout`, `parallel` | 在命令主机跑 shell 命令；结果在 `data.result`（`returncode`/`stdout`/`stderr`/`kind`） |
| `basic.file.upload` | `local_path`, `remote_path` | `recursive`, `timeout` | 本机 → 远端；`recursive=true` 传整个目录 |
| `basic.file.download` | `remote_path`, `local_path` | `recursive`, `timeout` | 远端 → 本机 |
| `basic.gui.run` | `cmd` | `timeout` | 在 GUI 主机跑一次性命令（如 `xdpyinfo`） |
| `basic.spectre.run` | `cmd` | `timeout` | 在 Spectre 主机跑一次性命令（如 `spectre -W`） |

## 库与 cellview（22 个）

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `virtuoso.cellview.lib.list` | — | — | 列出所有库 |
| `virtuoso.cellview.lib.get` | `library` | — | 单个库的信息 |
| `virtuoso.cellview.lib.create` | `library`, `path` | `technology_library` | 建库；`path` 是库目录（远端绝对路径） |
| `virtuoso.cellview.lib.copy` | `library`, `new_library`, `new_path` | — | 复制库 |
| `virtuoso.cellview.lib.delete` | `library` | — | 删库（**不可逆**） |
| `virtuoso.cellview.lib.rename` | `library`, `new_name` | — | 库改名 |
| `virtuoso.cellview.lib.bind` | `library`, `technology_library` | — | 给库绑工艺库（如 `cdsDefTechLib`、PDK 库名） |
| `virtuoso.cellview.cell.list` | `library` | `category` | 列 cell（可按分类过滤） |
| `virtuoso.cellview.cell.copy` | `library`, `cell`, `new_library`, `new_cell` | — | 复制 cell |
| `virtuoso.cellview.cell.delete` | `library`, `cell` | — | 删 cell（**不可逆**） |
| `virtuoso.cellview.cell.rename` | `library`, `cell`, `new_name` | — | cell 改名 |
| `virtuoso.cellview.view.list` | `library`, `cell` | — | 列视图（还能用来判断视图是否存在） |
| `virtuoso.cellview.view.create` | `library`, `cell`, `view`, `view_type` | — | 建视图 |
| `virtuoso.cellview.view.copy` | `library`, `cell`, `view`, `new_library`, `new_cell`, `new_view` | — | 复制视图 |
| `virtuoso.cellview.view.delete` | `library`, `cell`, `view` | — | 删视图（**不可逆**） |
| `virtuoso.cellview.view.rename` | `library`, `cell`, `view`, `new_name` | — | 视图改名 |
| `virtuoso.cellview.cat.list` | `library` | — | 列分类 |
| `virtuoso.cellview.cat.create` | `library`, `category` | — | 建分类 |
| `virtuoso.cellview.cat.delete` | `library`, `category` | — | 删分类 |
| `virtuoso.cellview.cat.rename` | `library`, `category`, `new_name` | — | 分类改名 |
| `virtuoso.cellview.cat.add_cell` | `library`, `category`, `cell` | — | 把 cell 放进分类 |
| `virtuoso.cellview.cat.remove_cell` | `library`, `category`, `cell` | — | 从分类移除 |

常用 `view_type`：`schematic`、`schematicSymbol`（symbol）、`maskLayout`（layout）、
`maestro`、`text.v`（verilog）、`text.veriloga`（veriloga）。

## 原理图（schematic）

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `virtuoso.schematic.read` | `library`, `cell` | `view`（默认 `schematic`）、`focus` | 读原理图；`focus` 是逗号串，可取 `positions`/`connectivity`/`params`，不给 = 全给 |
| `virtuoso.schematic.write` | `library`, `cell`, `commands` | `view` | 一次给一组原子命令（见下表） |
| `virtuoso.schematic.check_and_save` | `library`, `cell` | `view` | 检查并保存 |
| `virtuoso.schematic.screenshot` | `library`, `cell` | `view`, `region`, `leave_open` | 截图到本机，路径在 `data.local_path` |

`commands[]` 原子（坐标单位 = 用户单位，一般 µm）：

| 原子 | 必备 | 常用可选 |
|---|---|---|
| `place_instance` | `master_lib`, `master_cell`, `name`, `x`, `y` | `master_view`（默认 `symbol`）、`orient`（默认 `R0`） |
| `delete_instance` | `name` | — |
| `rename_instance` | `name`, `new_name` | — |
| `set_instance_params` | `name`, `params`（`{"w":"1u"}`） | — |
| `set_term_nets` | `name`, `term_nets`（`{"G":"net1"}`） | `justify`, `orient`, `font`, `height`, `stub_length` |
| `place_wire` | `points`（`[[x,y],[x,y],…]`） | `entry`（默认 `route`）、`route`（默认 `full`）、`width`, `color`, `line_style` |
| `delete_wire` | `points` | — |
| `set_wire_properties` | `points` | `width`, `color`, `line_style` |
| `place_label` | `x`, `y`, `text` | `justify`, `orient`, `font`, `height`, `alias` |
| `delete_label` / `rename_label` / `set_label_properties` | `x`, `y`（`rename_label` 还要 `new_text`） | `justify`, `orient`, `font`, `height` |
| `place_pin` | `name`, `x`, `y` | `direction`（默认 `inputOutput`；`input`/`output`/`switch`/`jumper`）、`orient` |
| `delete_pin` / `rename_pin` / `set_pin_properties` | `x`, `y`（`rename_pin` 还要 `new_name`） | — |
| `place_note` | `x`, `y`, `text` | `justify`, `orient`, `font`, `height`, `type` |
| `delete_note` / `rename_note` / `set_note_properties` | `x`, `y`（`rename_note` 还要 `new_text`） | `justify`, `orient`, `font`, `height` |

例（放一个器件、连一段线、打一个标签、放一个引脚并设参数）：

```json
{"operation":"virtuoso.schematic.write","token":"T","library":"mylib","cell":"inv","view":"schematic",
 "commands":[
  {"op":"place_instance","master_lib":"mylib","master_cell":"nand2","master_view":"symbol","name":"I0","x":0,"y":0},
  {"op":"place_wire","points":[[0,0],[1,0]]},
  {"op":"place_label","text":"net1","x":0.5,"y":0},
  {"op":"place_pin","name":"IN","x":-1.25,"y":0,"direction":"input","orient":"R0"},
  {"op":"set_instance_params","name":"I0","params":{"w":"1u"}},
  {"op":"set_term_nets","name":"I0","term_nets":{"G":"net1"}}]}
```

## 符号（symbol）

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `virtuoso.symbol.read` | `library`, `cell` | `view`（默认 `symbol`）、`focus` | `focus` 取 `terms`/`labels`/`shapes`/`orders`/`selection_boxes` 的子集；不给 = 全给 |
| `virtuoso.symbol.write` | `library`, `cell`, `commands` | `view` | 原子见下表 |
| `virtuoso.symbol.generate` | `library`, `cell` | `schematic_view`（默认 `schematic`）、`symbol_view`（默认 `symbol`）、`sort_pins`、`overwrite` | **从原理图自动生成 symbol**（最常用） |
| `virtuoso.symbol.check_and_save` | `library`, `cell` | `view` | 检查并保存 |
| `virtuoso.symbol.screenshot` | `library`, `cell` | `view`, `region`, `leave_open` | 截图；路径在 `data.value.local_path` |

`commands[]` 原子：

| 原子 | 必备 | 常用可选 |
|---|---|---|
| `place_line` / `place_polygon` | `layer`, `purpose`, `points`（polygon ≥3 点） | — |
| `place_rect` / `place_ellipse` | `layer`, `purpose`, `bbox`（`[x0,y0,x1,y1]`） | — |
| `delete_shape` / `set_shape_properties` | `kind`（`line`/`rect`/`polygon`/`ellipse`）+ `points`（line/polygon）或 `bbox`（rect/ellipse） | `layer`, `purpose`, `new_points`, `new_bbox` |
| `place_label` | `label_kind`, `text`（`instance`/`logical` 可省） | `x`/`y` 或 `xy`、`justify`, `orient`, `font`, `height`, `layer`, `purpose` |
| `delete_label` / `rename_label` / `set_label_properties` | `label_kind`, `x`/`y`（或 `xy`）（`rename_label` 还要 `new_text`） | `justify`, `orient`, `font`, `height` |
| `place_pin` | `name`, `x`, `y` | `direction`（默认 `inputOutput`）、`half_size`, `label`, `label_x`, `label_y`, `label_justify`, `label_orient`, `label_font`, `label_height` |
| `delete_pin` / `rename_pin` / `set_pin_properties` | `name`（rename 还要 `new_name`） | `direction`（改引脚类型） |
| `set_selection_box` | `bbox` | — |
| `set_pin_order` | `term_names`（`["VDD","IN","OUT"]`） | — |

## 版图（layout）

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `virtuoso.layout.read` | `library`, `cell` | `view`（默认 `layout`）、`focus`、`detail`、`object_filter`, `region_mode`, `depth` | `focus` 取 `summary`/`shapes`/`instances`/`vias`；`detail` 取 `geometry`/`index` |
| `virtuoso.layout.write` | `library`, `cell`, `commands` | `view`, `strict_lpp` | 原子见下表 |
| `virtuoso.layout.gds` | `action`（`export`/`import`）, `library` | `cell`, `view`, `file_path`, `file_is_local`, `tech_lib`, `top_cell`, `layer_map` | 导出/导入 GDS；导出时 `file_path` 是本机路径（默认 `file_is_local=true`） |
| `virtuoso.layout.display` | `library`, `cell`, `commands` | `view` | 控制版图窗口显示：`fit_view`、`zoom`(`scale`)、`show_only_layers`(`layers`)、`set_layers_visible`(`layers`, `visible`)、`set_entry_layer`(`layer`,`purpose`) |
| `virtuoso.layout.screenshot` | `library`, `cell` | `view`, `region`, `leave_open` | 截图；路径在 `data.value.local_path` |

`object_filter` 形如 `{"shape":{"layers":[["M1","drawing"]],"region":[x0,y0,x1,y1]}}`；
`depth>0` 时必须给 `layers` 或 `region`。

`commands[]` 原子：

| 原子 | 必备 | 常用可选 |
|---|---|---|
| `place_rect` | `layer`, `purpose`, `bbox` | — |
| `place_polygon` | `layer`, `purpose`, `points`（≥3 点） | — |
| `place_line` | `layer`, `purpose`, `points`（正好 2 点） | — |
| `place_path` | `layer`, `purpose`, `points`（≥2 点）, `width` | `style`（`extendExtend`/`roundRound`/`truncateExtend`/`squareFlush`…） |
| `place_label` | `layer`, `purpose`, `xy`, `text` | `justify`, `orient`, `font`, `height` |
| `delete_shape` / `set_shape_properties` | `kind`（`rect`/`polygon`/`path`/`line`/`ellipse`）+ `bbox`（rect/ellipse）或 `points`（其余） | `layer`, `purpose`, `all`, `new_bbox`, `new_points`, `new_width` |
| `delete_shapes_on_layer` | `layer`, `purpose` | `types`（`["rect","path"]`） |
| `place_instance` | `master_lib`, `master_cell`, `name`, `xy` | `master_view`（默认 `layout`）、`orient`, `num_inst` |
| `delete_instance` / `rename_instance` / `set_instance_properties` | `name`（rename 还要 `new_name`） | `new_xy`, `new_orient` |
| `place_mosaic` | `master_lib`, `master_cell`, `name`, `xy`, `rows`, `cols`, `row_pitch`, `col_pitch` | `master_view`, `orient` |
| `delete_mosaic` | `name` | — |
| `place_via` | `via_name`, `xy` | `orient`（默认 `R0`） |
| `delete_via` | `xy` | `orient` |
| `delete_label` / `rename_label` / `set_label_properties` | `xy`（rename 还要 `new_text`） | `text`, `layer`, `new_xy`, `new_height`, `new_justify`, `new_orient`, `new_font` |

例（画一块矩形 + 一条走线 + 一个 via）：

```json
{"operation":"virtuoso.layout.write","token":"T","library":"mylib","cell":"inv","view":"layout",
 "commands":[
  {"op":"place_rect","layer":"M1","purpose":"drawing","bbox":[0,0,1,1]},
  {"op":"place_path","layer":"M1","purpose":"drawing","points":[[0,0],[2,0]],"width":0.1},
  {"op":"place_via","via_name":"M1_M2","xy":[1,1],"orient":"R0"}]}
```

## Maestro / ADE

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `virtuoso.maestro.read_config` | `library`, `cell` | `view`（默认 `maestro`）、`include_parameters`, `include_raw` | 读配置（变量/分析/输出/corner） |
| `virtuoso.maestro.write` | `library`, `cell`, `commands` | `view`, `save` | 改配置，原子见下表 |
| `virtuoso.maestro.read_results` | `library`, `cell` | `history`, `test`, `analysis`, `waveform`, `result`, `output_path`, `notation`, `precision` | 读仿真结果；不给 `history` 取最新 |
| `virtuoso.maestro.export` | `library`, `cell`, `kind` | `history`, `test`, `corner`, `output_path` | `kind` = `netlist`/`script`/`outputs_csv`/`snapshot`/`screenshot` |
| `virtuoso.maestro.read_history` | `library`, `cell` | `history`, `view` | 看历史记录与状态（**轮询用这个**） |
| `virtuoso.maestro.write_history` | `library`, `cell`, `commands` | `view` | 原子：`rename`(`history`,`new_name`)、`lock`/`unlock`(`history`)、`delete`(`history`)、`delete_results`(`history`, `keep_netlist`, `keep_quick_plot`) |
| `virtuoso.maestro.run` | `library`, `cell` | `view`, `history`, `blocking`（默认 `false`）, `poll_interval`, `timeout` | 跑仿真；非阻塞时返回新 `history` |
| `virtuoso.maestro.open_gui` / `close_gui` | `library`, `cell` | `view`, `history` | 开关 ADE 窗口 |
| `virtuoso.maestro.open_waveform_gui` | `library`, `cell`, `history`, `signals` | `test`, `analysis`, `result` | 打开波形窗口；`signals` 如 `["VOUT"]` |
| `virtuoso.maestro.close_waveform_gui` | — | `session`, `window` | 关波形窗口 |

`write` 的 `commands[]` 原子（Maestro 这部分最常用）：

| 原子 | 必备 | 常用可选 |
|---|---|---|
| `set_test` | `test`, `lib`（或 `library`）, `cell` | `view`（默认 `schematic`）、`simulator`（默认 `spectre`） |
| `set_design` | `test`, `lib`（或 `library`）, `cell` | `view` |
| `delete_test` | `test` | — |
| `set_analysis` | `test`, `analysis` | `enable`（默认 `true`）、`options`（`{"stop":"10n"}`） |
| `set_var` | `name`, `value` | `scope`（`global`/`test`/`corner`）、`test`/`tests`、`corner`/`corners` |
| `delete_var` | `name` | `scope`（`all` 清所有）、`test`/`tests`、`corner`/`corners`, `all_tests` |
| `set_parameter` | `name`（`Lib/Cell/View/Instance/Property` 五段）, `value` | `scope`（`corner` 时给 `corner`/`corners`） |
| `delete_parameter` | `name` | `scope`, `corner`/`corners` |
| `set_corner` / `delete_corner` | `name` | `enabled`, `enable_tests`, `disable_tests` |
| `setup_corner` | `name` | `variables`（`{"temperature":27}`）、`model_file`, `model_section` |
| `load_corners` | `filepath`（或 `remote_path`） | `sections`（默认 `corners`）、`operation`（默认 `overwrite`） |
| `set_run_mode` | `run_mode` | — |
| `set_job_control_mode` | `mode` | — |
| `set_job_policy` | `policy`（对象或 SKILL 表达式字符串） | `test`, `job_type` |
| `set_simulator_mode` | `mode` | `option`（默认 `uniMode`） |
| `add_output` | `name`, `test` | `output_type`, `signal_name`, `expr`, `plot`, `save` |
| `set_spec` | `name`, `test` + 一个界：`gt`/`lt`/`min`/`max`/`tol`/`range` | `info`, `weight`, `corner` |
| `delete_output` / `delete_spec` | `name`, `test` | `delete_spec` |

例（加一个 tran 分析、设一个变量、导出 outputs.csv）：

```json
{"operation":"virtuoso.maestro.write","token":"T","library":"maestro_tb","cell":"rc_probe","view":"maestro",
 "commands":[
  {"op":"set_analysis","test":"rc_tran","analysis":"tran","options":{"stop":"10n"}},
  {"op":"set_var","name":"vcm","value":"0.6","scope":"global"},
  {"op":"add_output","test":"rc_tran","name":"VOUT","signal_name":"VOUT"}]}
```

## Spectre（独立仿真，不经过 Virtuoso GUI）

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `spectre.check_license` | — | `spectre_bin` | 查许可 |
| `spectre.run` | `tasks` | `max_workers`（默认 4）、`mode`, `spectre_args`, `spectre_bin`, `parse`（默认 `auto`）, `download`（默认 `true`）, `output_root`, `keep_run_dir`, `timeout` | 批量跑；`tasks[]` 见下 |
| `spectre.read_results` | `source`（远端 `.raw` 路径） | `analysis`（默认 `all`）、`output_dir`, `timeout` | 读 PSF 结果 |
| `spectre.measure` | `metrics`（`[{"type":"max","signal":"vout"}]`） | `data`（上一步结果）或 `source_path` | 量指标 |
| `spectre.export` | `format`（`csv`/`json`）, `output_path` | `data` 或 `source_path`, `columns`, `precision` | 导出数据 |

`tasks[]` 每项：`job`（唯一名）、`netlist`（网表路径）必备；可选 `include_files`（附加 include 文件）、`mode`、`spectre_args`。

```json
{"operation":"spectre.run","token":"T",
 "tasks":[{"job":"rc","netlist":"/home/u/work/tb.scs","spectre_args":["+dc"]}],
 "parse":"auto","download":true}
```

## Calibre（DRC / LVS / PEX）

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `calibre.check_env` | — | `calibre_bin`, `deck` | 查环境/许可 |
| `calibre.drc` | `deck` | `gds`, `top`（deck 有占位符时才必需）, `params`/`runset`, `job_id`, `run_dir`, `turbo`（默认 4）、`hier`, `blocking`（默认 `false`）, `poll_interval` | 跑 DRC；默认后台，先用返回的 `job_id` |
| `calibre.lvs` | `deck` | 同上 + `cdl`（deck 引用 `lvs_top.cdl` 时必需）, `lvs_run_dir`, `power`, `ground` | 跑 LVS；`cdl` 可用 `calibre.export_cdl` 现产 |
| `calibre.pex` | `gds`, `top`, `deck` | 同上 + `cdl`, `lvs_run_dir`, `fmt` | 跑 PEX |
| `calibre.status` | `job_id` 或 `run_dir` | `kind`（默认 `drc`） | 查进度 |
| `calibre.read_results` | `job_id` 或 `run_dir` | `kind`, `limit`, `log_lines` | 读结构化结论 |
| `calibre.export` | `job_id` 或 `run_dir` | `kind`, `items`（默认 `["summary"]`）、`local_dir` | 导出报告到本机 |
| `calibre.export_cdl` | `library`, `cell` | `view`（默认 `schematic`）, `netlist_name`, `run_dir`, `cds_lib`, `timeout` | 用 Virtuoso 官方 auCdl 从 schematic 现产 CDL 源网表（LVS 的 source 侧） |

**改参数**：`params={"lvsLayoutPrimary":"inv2", "lvsSourcePath":"/x/inv2.cdl", …}`（也收 `runset=<远端 .runset 路径>`）。
支持的键：`drcLayoutPaths/drcLayoutPrimary/drcLayoutSystem/lvsLayoutPaths/lvsLayoutPrimary/lvsSourcePath/lvsSourcePrimary/lvsSourceSystem/lvsSVDBDir`；
键写成 SVRF 语句头（如 `"LAYOUT PRIMARY"`，值给整条语句）可改表外的语句。参数会被**原位写进 deck**（first-wins 语义），
改动在返回的 `deck_changes` 里。不认识的键会直接失败——不要用 `INCLUDE <deck>` + 覆盖行的 control file，
那对 specification 语句无效（见 `doc/report/calibre-网表导出机制调查报告.md §9`）。

**直接给 Calibre Interactive 的 set**（现场形态，首选）：`runset="/path/xx.lvs"` 一个字段就够。
本包执行官方批处理 `calibre -gui -lvs -runset <set> -batch`，**参数合并、control file 生成全由 Calibre 做**
（run dir 里会看到它生成的 `_calibre.lvs_`）；我们只发起、轮询、定位产物、解析报告。
报告改名也能解析（默认名 → `job.json.report_file` → run dir 内扫 `*.report/*.rep`）。
**set 只带参数不带数据**：它引用的 layout / 源网表 / hcell 文件必须已在远端。
没有 set 时才用 `deck=` + 白名单占位符（外加 `spice_file`/`hcell_file`/`xcell_file`）；
`params` 的键必须是 SVRF 语句头（如 `"LAYOUT PRIMARY"`），camelCase 的 set 键会报错并指路 `runset=`。

## Verilog / Verilog-A

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `virtuoso.verilog.read` | `library`+`cell` 或 `file_path` | `view`（默认 `verilog`）、`focus`, `file_is_local` | 读源码 |
| `virtuoso.verilog.write` | `library`, `cell`, `commands` | `view` | 原子：`ensure_view`、`delete_view`、`set_source`(`text`)、`patch_source`(`edits`) |
| `virtuoso.verilog.import` | `library`, `cell`, `file_path` | `ref_libs`, `overwrite`, `power_net`（默认 `VDD`）、`ground_net`（默认 `VSS`）、`structural_views`, `schematic_view`, `symbol_view`, `timeout` | **把 Verilog 结构导入成原理图/symbol**；库要在 CIW 的 `cds.lib` 里可见 |
| `virtuoso.verilog.export` | `library`, `cell` | `view`（默认 `schematic`）、`output_path`, `recursive` | 从原理图导出网表式 Verilog |
| `virtuoso.veriloga.read` | `library`+`cell` 或 `file_path` | `view`（默认 `veriloga`）、`focus` | 读 Verilog-A |
| `virtuoso.veriloga.write` | `library`, `cell`, `commands` | `view` | 原子同 verilog；典型：`ensure_view` + `set_source` |
| `virtuoso.veriloga.check_and_save` | `library`, `cell` | `view` | 检查并保存 |

`set_source` 支持 `expected_sha256`（给内容上锁，内容对不上就拒绝写）；
`patch_source` 的 `edits[]` 用 `old_text`/`new_text` 或 `start_line`/`end_line`/`new_text`。

## GUI（截屏 / 窗口 / 弹窗）

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `virtuoso.gui.list_windows` | — | `timeout` | 列出 Virtuoso 窗口（拿 `window_id`） |
| `virtuoso.gui.send_key` | `window_id` | `key`（默认 `enter`） | 往指定窗口发按键 |
| `virtuoso.gui.auto_dismiss` | — | `max_attempts`（默认 2） | 自动关掉挡路的对话框 |
| `virtuoso.gui.screenshot` | `output_path` | `target`（默认 `ciw`） | `target` 取 `ciw`/`display`/`0x...` 窗口号；截图落回本机 |

## SKILL 文档查询

| operation | 必备 | 可选 | 说明 |
|---|---|---|---|
| `virtuoso.skillref.search` | `query` | `mode`（默认 `fuzzy`）、`search_in`, `limit`（默认 20）、`under`, `source`, `doc_root` | 模糊找 SKILL 函数 |
| `virtuoso.skillref.info` | `name` | `include_raw` | 查某个函数的详细文档 |

```json
{"operation":"virtuoso.skillref.search","token":"T","query":"hiWindowSaveImage"}
{"operation":"virtuoso.skillref.info","token":"T","name":"hiWindowSaveImage"}
```
