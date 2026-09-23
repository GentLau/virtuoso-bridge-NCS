# 业务操作总表（75 个）

> 与 `/health` 的 `operations` 一致；字段以对应包 spec 为准，本表只给“谁干什么”。
> 传参必带 `token`；`timeout` 各操作可选。

## basic（6）

| operation | 用途 |
|---|---|
| `basic.skill.execute` | 在 Virtuoso CIW 执行 SKILL；`skill_code` |
| `basic.command.run` | command role 一次性命令；`cmd`，可选 `parallel` |
| `basic.file.upload` | 客户端→远端；`local_path`/`remote_path`，可选 `recursive` |
| `basic.file.download` | 远端→客户端；同上 |
| `basic.gui.run` | gui role 一次性命令；`cmd` |
| `basic.spectre.run` | spectre role 一次性命令；`cmd` |

## demo（4）

| operation | 用途 |
|---|---|
| `demo.pipeline.run` | upload→skill→command→download 组合示例 |
| `demo.parallel.probe` | 并发命令/上传探针 |
| `demo.paths.facts` | 本机 work_root/temp/log/artifact 查询 |
| `virtuoso.netlist.import` | 参考桩：显式失败，不建 cell/view/symbol |

## gui（4）

| operation | 用途 |
|---|---|
| `virtuoso.gui.list_windows` | X11 顶层窗口（EWMH，无 WM 退 root 子窗口） |
| `virtuoso.gui.send_key` | 对显式 `window_id` 注入 enter/escape |
| `virtuoso.gui.auto_dismiss` | 逐个恢复分类为 dialog 的窗口 |
| `virtuoso.gui.screenshot` | `target∈{ciw,window_id,display}` → PPM 下载 |

## cellview（22）

lib：`lib.list`、`lib.get`、`lib.create(library,path[,technology_library])`、
`lib.copy`、`lib.delete`、`lib.rename`、`lib.bind(library,technology_library)`。
cell：`cell.list`、`cell.copy`、`cell.delete`、`cell.rename`。
view：`view.list`、`view.create`、`view.copy`、`view.delete`、`view.rename`。
cat：`cat.list`、`cat.create`、`cat.delete`、`cat.rename`、`cat.add_cell`、`cat.remove_cell`。

## schematic（4）

| operation | 用途 |
|---|---|
| `virtuoso.schematic.read` | `focus` 可组合 + `object_filter`/`param_filter` |
| `virtuoso.schematic.write` | `commands[]`：instance/wire/label/pin/note 原子 |
| `virtuoso.schematic.check_and_save` | 显式 `schCheck`+`dbSave`，失败返回字符串也判失败 |
| `virtuoso.schematic.screenshot` | PNG（hiWindowSaveImage） |

## symbol（5）

`read` / `write` / `generate` / `check_and_save` / `screenshot`。

## layout（5）

| operation | 用途 |
|---|---|
| `virtuoso.layout.read` | focus/object_filter/detail |
| `virtuoso.layout.write` | 几何/label/instance/mosaic/via 原子 |
| `virtuoso.layout.gds` | `action=export|import`；`file_is_local` 决定落本机还是远端 |
| `virtuoso.layout.display` | set_layers_visible/show_only_layers/set_entry_layer/fit_view/zoom |
| `virtuoso.layout.screenshot` | PNG |

## maestro（11）

`read_config` / `write` / `read_results` / `export` / `read_history` / `write_history` /
`open_gui` / `close_gui` / `run` / `open_waveform_gui` / `close_waveform_gui`。

## verilog（4）

`read` / `write`（文本视图 `text.v`）/ `import`（ihdl）/ `export`（oa2verilog）。

## veriloga（3）

`read` / `write`（`text.veriloga`）/ `check_and_save`（VerAParseModule + ahdlUpdateViewInfo）。

## calibre（7）

`check_env` / `drc` / `lvs` / `pex` / `status` / `read_results` / `export`。

## spectre（5）

`check_license` / `run` / `read_results` / `measure` / `export`。

## skillref（2）

`virtuoso.skillref.search` / `virtuoso.skillref.info`。
