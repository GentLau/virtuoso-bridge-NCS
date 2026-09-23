---
name: virtuoso-bridge
description: "在远程 Virtuoso 上做事（建库/画原理图/符号/版图、导入 Verilog/Verilog-A、Maestro 仿真、Calibre、Spectre、截屏、查 SKILL 文档）。用户要求任何 Virtuoso/EDA 操作时触发：用 POST http://127.0.0.1:8127/api/operation 调业务操作。"
---

# 怎么用 virtuoso-bridge

本 skill 只讲**怎么把事干成**。所有操作都是同一个 HTTP 调用：

```bash
curl -s http://127.0.0.1:8127/api/operation \
  -H "Content-Type: application/json" \
  -d '{"operation":"<操作名>","token":"<token>",<参数>}'
```

返回统一信封：

```json
{"ok": true, "data": {"ok": true, "value": {...}}, "error": null}
```

- **只看最外层 `ok`**；false 就按 `error` 排查，别继续下一步。
- 每个请求都要带 `token`（照抄用户/环境给的，不要自造）。
- 不知道操作名/参数 → 查 `references/operations.md`；还拿不准就查
  `spec/design-concepts/上层/<N>-<包名>.md`。**不要猜名字。**

## 1. 万能逃生口：直接跑 SKILL / 命令

任何上面没有的细活，直接用这两个：

```json
{"operation":"basic.skill.execute","token":"T","skill_code":"1+1"}
{"operation":"basic.command.run","token":"T","cmd":"command -v strmin"}
```

SKILL 在远端 Virtuoso CIW 执行；命令在远端 command 主机执行。文件用
`basic.file.upload` / `basic.file.download`（`local_path` + `remote_path`）。

## 2. 常见任务照抄（改库名/cell/路径即可）

### 建库、建 cell、建视图

```json
{"operation":"virtuoso.cellview.lib.create","token":"T","library":"mylib","path":"/home/user/.virtuoso-bridge/vblog/mylib"}
{"operation":"virtuoso.cellview.bind","token":"T","library":"mylib","technology_library":"cdsDefTechLib"}
{"operation":"virtuoso.cellview.view.create","token":"T","library":"mylib","cell":"inv","view":"schematic","view_type":"schematic"}
```

列库/cell/view：`virtuoso.cellview.lib.list`、`cell.list`、`view.list`。

### 写原理图（一次给一组原子命令）

```json
{"operation":"virtuoso.schematic.write","token":"T","library":"mylib","cell":"inv","view":"schematic",
 "commands":[
  {"op":"place_instance","master_lib":"mylib","master_cell":"nand2","master_view":"symbol","name":"I0","x":0,"y":0},
  {"op":"place_wire","points":[[0,0],[1,0]]},
  {"op":"place_label","text":"net1","x":0.5,"y":0},
  {"op":"set_instance_params","name":"I0","params":{"w":"1u"}}]}
```

原子名就这几类：`place_/delete_/rename_/set_` + `instance|wire|label|pin|note`，
再加 `set_term_nets`（给器件端子放网络）。读回：`virtuoso.schematic.read`，
`focus` 可给 `positions/connectivity/params` 组合。

### 生成 symbol / 读写符号

```json
{"operation":"virtuoso.symbol.generate","token":"T","library":"mylib","cell":"inv","view":"schematic"}
{"operation":"virtuoso.symbol.read","token":"T","library":"mylib","cell":"inv","view":"symbol","focus":["terms","pin_order"]}
```

### 版图 / GDS

```json
{"operation":"virtuoso.layout.write","token":"T","library":"mylib","cell":"inv","view":"layout",
 "commands":[{"op":"place_rect","layer":"M1","purpose":"drawing","bbox":[0,0,1,1]}]}
{"operation":"virtuoso.layout.gds","token":"T","action":"export","library":"mylib","cell":"inv","view":"layout","file_path":"C:/work/inv.gds"}
{"operation":"virtuoso.layout.gds","token":"T","action":"import","library":"mylib","tech_lib":"cdsDefTechLib","file_path":"C:/work/inv.gds","top_cell":"inv"}
```

### 跑 Maestro 仿真 + 看结果

```json
{"operation":"virtuoso.maestro.run","token":"T","library":"maestro_tb","cell":"rc_probe","view":"maestro","blocking":false}
{"operation":"virtuoso.maestro.read_results","token":"T","library":"maestro_tb","cell":"rc_probe","view":"maestro","history":"Interactive.1"}
```

不填 `history` 会取最新一条；`blocking=false` 立即返回 history，用
`virtuoso.maestro.read_history` 查进度/状态。

### 导入 Verilog / Verilog-A

```json
{"operation":"virtuoso.verilog.import","token":"T","library":"mylib","cell":"top","file_path":"C:/work/top.v","file_is_local":true,"timeout":180}
{"operation":"virtuoso.veriloga.write","token":"T","library":"mylib","cell":"va","view":"veriloga",
 "commands":[{"op":"ensure_view","create_if_missing":true},{"op":"set_source","text":"module va(a,b); endmodule"}]}
{"operation":"virtuoso.veriloga.check_and_save","token":"T","library":"mylib","cell":"va","view":"veriloga"}
```

### 独立 Spectre / Calibre

```json
{"operation":"spectre.run","token":"T","tasks":[{"job":"rc","netlist":"C:/work/tb.scs","parse":"auto"}]}
{"operation":"spectre.read_results","token":"T","source":"/data/rc/tb.raw","analysis":"all"}
{"operation":"calibre.drc","token":"T","gds":"/data/inv.gds","top":"inv","deck":"/pdks/calibre.drc","blocking":false}
{"operation":"calibre.status","token":"T","job_id":"drc_inv","kind":"drc"}
```

### 截屏 / 弹窗

```json
{"operation":"virtuoso.gui.screenshot","token":"T","target":"display","output_path":"C:/work/screen.ppm"}
{"operation":"virtuoso.gui.list_windows","token":"T"}
{"operation":"virtuoso.gui.send_key","token":"T","window_id":"0x2200008","key":"enter"}
```

### 查 SKILL 函数/文档

```json
{"operation":"virtuoso.skillref.search","token":"T","query":"hiWindowSaveImage"}
{"operation":"virtuoso.skillref.info","token":"T","name":"hiWindowSaveImage"}
```

## 3. 失败时看什么

1. 外层 `ok=false` → 读 `error`；
2. `error` 是 SKILL 文本时，`data.steps[].detail` 里有 SKILL/命令原文和 stderr；
3. 常见原因：库/视图不存在、视图被别人锁着（报 “locked”）、视图名/类型写错、
   token 不对（报 invalid token）、gui display 未配置。

锁文件判断：`virtuoso.cellview.view.list` 能列到但写失败 = 大概率被锁；
去远端 `ls <lib路径>/<cell>/<view>/*.cdslck` 确认。

## 4. 别忘了

- 文件远端路径是 Linux 风格（`/home/...`），本机才用 `C:/...`；
- 上传本机文件用 `basic.file.upload`，别自己 SSH；
- 干完写操作，不确定就再 `read` 一次验证，别只信 `ok=true`。
