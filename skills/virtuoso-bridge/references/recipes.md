# 端到端照抄流程

每个流程都是"按顺序发请求"；把 `TOKEN`、库名、路径换成实际值即可。
字段含义见 `operations.md`，返回值怎么读见 `SKILL.md` §1。

通用前提：库/cell 用**远端已存在的**；本机文件先 `basic.file.upload`；
每一步失败就停下来修，别继续往下堆。

## 1. 从零建一个 cell（原理图 + symbol）

```json
{"operation":"virtuoso.cellview.lib.create","token":"TOKEN","library":"mylib","path":"/home/user/vblog/mylib","technology_library":"cdsDefTechLib"}
{"operation":"virtuoso.cellview.view.create","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic","view_type":"schematic"}
{"operation":"virtuoso.schematic.write","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic",
 "commands":[
  {"op":"place_pin","name":"IN","x":-2.5,"y":0,"direction":"input"},
  {"op":"place_pin","name":"OUT","x":2.5,"y":0,"direction":"output"},
  {"op":"place_pin","name":"VDD","x":0,"y":2.5,"direction":"inputOutput"},
  {"op":"place_pin","name":"VSS","x":0,"y":-2.5,"direction":"inputOutput"},
  {"op":"place_instance","master_lib":"analogLib","master_cell":"nmos4","master_view":"symbol","name":"M0","x":0,"y":-1,"orient":"R0"},
  {"op":"set_instance_params","name":"M0","params":{"w":"1u","l":"60n"}},
  {"op":"place_wire","points":[[-2.5,0],[-1,0]]},
  {"op":"place_wire","points":[[1,0],[2.5,0]]},
  {"op":"place_label","text":"IN","x":-2.5,"y":0},
  {"op":"place_label","text":"OUT","x":2.5,"y":0}]}
{"operation":"virtuoso.symbol.generate","token":"TOKEN","library":"mylib","cell":"inv","overwrite":true}
{"operation":"virtuoso.schematic.read","token":"TOKEN","library":"mylib","cell":"inv","focus":"connectivity"}
```

要点：

- 先 `place_pin` 再 `symbol.generate`，生成的 symbol 才有端子；改完引脚要重跑 `symbol.generate`。
- 器件（`nmos4`、`res` 等）来自 `analogLib` 或 PDK 库，**库名要对**；不确定就先 `virtuoso.cellview.cell.list` 看。
- `set_instance_params` 的参数名必须是该器件 CDF 里存在的名字，写错会报 `unknown CDF param`。

## 2. 跑一次 Maestro 仿真并读结果

前提：这个 cell 已经有 `maestro` 视图（测试平台）。先确认能读到配置：

```json
{"operation":"virtuoso.maestro.read_config","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro"}
```

改配置 → 开跑 → 轮询 → 读结果：

```json
{"operation":"virtuoso.maestro.write","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro",
 "commands":[
  {"op":"set_analysis","test":"rc_tran","analysis":"tran","options":{"stop":"10n"}},
  {"op":"set_var","name":"vcm","value":"0.6","scope":"global"},
  {"op":"add_output","test":"rc_tran","name":"VOUT","signal_name":"VOUT"}]}
{"operation":"virtuoso.maestro.run","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro","blocking":false}
{"operation":"virtuoso.maestro.read_history","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro","history":"Interactive.1"}
{"operation":"virtuoso.maestro.read_results","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro","history":"Interactive.1","test":"rc_tran"}
{"operation":"virtuoso.maestro.export","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","kind":"outputs_csv","history":"Interactive.1"}
```

要点：

- `run` 默认非阻塞，返回新的 `history`；用 `read_history` 轮询状态，别用 `read_results` 当轮询。
- 不填 `history` 就是"最新一条"；要复现旧结果就显式给名字。
- 结果不理想时先 `read_config` 看当前配置是否真的写进去了。

## 3. 版图 → GDS 导出

```json
{"operation":"virtuoso.cellview.view.create","token":"TOKEN","library":"mylib","cell":"inv","view":"layout","view_type":"maskLayout"}
{"operation":"virtuoso.layout.write","token":"TOKEN","library":"mylib","cell":"inv","view":"layout",
 "commands":[
  {"op":"place_rect","layer":"M1","purpose":"drawing","bbox":[0,0,1,1]},
  {"op":"place_path","layer":"M1","purpose":"drawing","points":[[0,0],[2,0]],"width":0.1}]}
{"operation":"virtuoso.layout.gds","token":"TOKEN","action":"export","library":"mylib","cell":"inv","view":"layout","file_path":"C:/work/inv.gds"}
{"operation":"virtuoso.layout.screenshot","token":"TOKEN","library":"mylib","cell":"inv","view":"layout"}
```

要点：

- 版图写操作要求库已经绑过工艺库（`virtuoso.cellview.lib.bind`），否则图层名解析不了。
- 导出目标目录要已存在；`file_path` 用本机路径（默认 `file_is_local=true`），文件会回到你这里。
- 导入方向：`"action":"import"` + `"tech_lib":"<工艺库>"` + `"top_cell":"inv"`。

## 4. 导入 Verilog 结构

```json
{"operation":"basic.file.upload","token":"TOKEN","local_path":"C:/work/top.v","remote_path":"/home/user/work/top.v"}
{"operation":"virtuoso.verilog.import","token":"TOKEN","library":"mylib","cell":"top","file_path":"/home/user/work/top.v","overwrite":true,"timeout":300}
{"operation":"virtuoso.symbol.generate","token":"TOKEN","library":"mylib","cell":"top","overwrite":true}
```

要点：

- 目标库必须能在 CIW 的 `cds.lib` 里解析（库缺失会报 `VERILOGIN-93` 一类错误）。
- 结构复杂时先给长一点 `timeout`；导入是"跑一次 ihdl"，慢是正常的。
- 导入后建议 `virtuoso.verilog.read` 或 `schematic.read` 复核一次。

## 5. 独立 Spectre 仿真（不经过 Virtuoso）

```json
{"operation":"spectre.check_license","token":"TOKEN"}
{"operation":"basic.file.upload","token":"TOKEN","local_path":"C:/work/tb.scs","remote_path":"/home/user/work/tb.scs"}
{"operation":"spectre.run","token":"TOKEN","tasks":[{"job":"rc","netlist":"/home/user/work/tb.scs"}],"parse":"auto","download":true}
{"operation":"spectre.read_results","token":"TOKEN","source":"/home/user/work/tb.raw","analysis":"all"}
{"operation":"spectre.measure","token":"TOKEN","metrics":[{"type":"max","signal":"vout"}]}
{"operation":"spectre.export","token":"TOKEN","format":"csv","output_path":"C:/work/rc.csv","data":{}}
```

要点：

- `spectre.run` 的 `tasks[].job` 在本次调用里必须唯一；网表里的 `include` 路径要能在远端解析。
- 想读结果就把 `download` 保持 `true`（默认），它会带回 `.raw`；`spectre.read_results` 的 `source` 就是那个 `.raw`。
- `spectre.measure` / `spectre.export` 可以吃上一步的 `data`，也可以给 `source_path` 直接重读。

## 6. Calibre DRC（后台跑 + 轮询 + 出报告）

```json
{"operation":"calibre.check_env","token":"TOKEN","deck":"/pdks/calibre/drc.deck"}
{"operation":"calibre.drc","token":"TOKEN","job_id":"drc_inv","gds":"/home/user/work/inv.gds","top":"inv","deck":"/pdks/calibre/drc.deck","blocking":false}
{"operation":"calibre.status","token":"TOKEN","job_id":"drc_inv","kind":"drc"}
{"operation":"calibre.read_results","token":"TOKEN","job_id":"drc_inv","kind":"drc","limit":20}
{"operation":"calibre.export","token":"TOKEN","job_id":"drc_inv","kind":"drc","items":["summary"],"local_dir":"C:/work/drc"}
```

要点：

- 默认后台跑；`status` 返回没结束时继续等，别重复提交同一个 job。
- `job_id` 自己起个有意义的名字（如 `drc_inv`），后面 `status`/`read_results`/`export` 都靠它定位。

## 7. 查 SKILL 函数怎么写

```json
{"operation":"virtuoso.skillref.search","token":"TOKEN","query":"hiWindowSaveImage"}
{"operation":"virtuoso.skillref.info","token":"TOKEN","name":"hiWindowSaveImage"}
```

需要更底层的能力时，用 `basic.skill.execute` 直接跑 SKILL；要写复杂的多行 SKILL，
用 `let(...)`/`progn(...)` 包起来再发。

## 8. 截屏与弹窗

```json
{"operation":"virtuoso.gui.list_windows","token":"TOKEN"}
{"operation":"virtuoso.gui.screenshot","token":"TOKEN","output_path":"C:/work/ciw.ppm","target":"ciw"}
{"operation":"virtuoso.gui.auto_dismiss","token":"TOKEN"}
{"operation":"virtuoso.gui.send_key","token":"TOKEN","window_id":"0x2200008","key":"enter"}
```

要点：截图文件落回本机；CIW 卡在对话框时先 `auto_dismiss`，不行再 `list_windows` + `send_key`。
