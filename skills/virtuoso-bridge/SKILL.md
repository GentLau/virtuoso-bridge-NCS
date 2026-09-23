---
name: virtuoso-bridge
description: "通过四层 bridge 的 HTTP 业务面（8127）操作远程 Cadence Virtuoso：业务包/业务操作调用。当用户提到 Virtuoso、CIW、SKILL、schematic、symbol、layout、cellview、maestro/ADE、verilog/veriloga、calibre、spectre、skillref、gui 窗口或“业务包/业务操作/上传网表/截图”时触发。"
---

# virtuoso-bridge 上层业务包使用说明

> **铁律：不要凭记忆编造 operation 名或字段。**
> 调任何操作前先查 `references/operations.md`（全部 75 个 operation 的清单与字段），
> 再看对应包的 spec：`spec/design-concepts/上层/<N>-<包名>.md`。
> 名字对不上 = 不存在，不要猜。

## 1. 心智模型

四层分工：**顶层**（HTTP 服务）→ **上层**（业务包，本 skill 的对象）→ **中层**（五个业务接口 + 只读 query）→ **底层**（Virtuoso 里的 SKILL daemon）。

- 上层 = **业务包**（插件单元）＝一组**业务操作**的集合；
- 一个业务操作 = 一个可以单独调用的动作（如“上传网表”“画器件”“跑仿真”“截图”）；
- 调用只有一种形态：`POST http://127.0.0.1:8127/api/operation`，body 必带
  `operation`（操作名）与 `token`（每次原样透传，不缓存不解析）。

```json
{"operation": "basic.skill.execute", "token": "vb-vblog", "skill_code": "1+1"}
```

返回统一信封：`{"ok": bool, "data": {...}, "error": str|null}`；
`data` 里通常是该包的 `Result`（`ok/steps/error/value`）。**先判 `ok`，再取 `value`。**

## 2. 环境与调用规范

| 项 | 值/规则 |
|---|---|
| 业务面 | `http://127.0.0.1:8127/api/operation`（本机）。目标环境可能用别的地址，以环境说明为准 |
| token | 每次调用必填，原样透传给中层；路由/限流由中层按 token 处理 |
| 只读查询 | `middle.query(token)` 经 `demo.paths.facts` 之外由包内部使用：返回各 role 的 `root`、gui 的 `display`、spectre 的 `bin`。**不要自己拼 host/端口/SSH** |
| 文件路径 | 客户端写 `work_root()/temp|log|artifact_dir()`（`common/paths.py`）；远端写 role root（`~/.virtuoso-bridge/<user>/`）。禁止共享 `/tmp`、`$HOME` 根、字面量 `~` 拼接 |
| 失败语义 | 只认 PASS/FAIL/PENDING；工具失败必须返回失败，**不得“假成功”**（网表没建不能说 ok） |
| 证据 | 真机/半真机结果落 `test/artifacts/evidence/<run-id>/`；红→绿成对；报告不写 token 明文 |

## 3. 业务包速览

| 包 | 一句话 | 典型操作 |
|---|---|---|
| `basic` | 中层六个接口的原样直通 | `basic.skill.execute` / `command.run` / `file.upload` / `file.download` / `gui.run` / `spectre.run` |
| `demo` | 参考/示例与探针 | `demo.paths.facts` / `pipeline.run` / `parallel.probe` / `virtuoso.netlist.import`（参考桩，**不建视图，显式失败**） |
| `gui` | X11 顶层窗口、弹窗恢复、截图 | `list_windows` / `send_key` / `auto_dismiss` / `screenshot` |
| `cellview` | lib/cell/view/category 文件管理 | `lib.list/get/create/copy/delete/rename/bind`、`cell.*`、`view.*`、`cat.*` |
| `schematic` | 原理图读/写/校验/截图 | `read` / `write`（原子命令组）/ `check_and_save` / `screenshot` |
| `symbol` | 符号读/写/生成/校验/截图 | `read` / `write` / `generate` / `check_and_save` / `screenshot` |
| `layout` | 版图几何读写、GDS、展示、截图 | `read` / `write` / `gds(export|import)` / `display` / `screenshot` |
| `maestro` | ADE 配置读写、历史、结果、GUI、仿真 | `read_config` / `write` / `read_history` / `write_history` / `read_results` / `export` / `run` / `open_gui` / `close_gui` / `open_waveform_gui` / `close_waveform_gui` |
| `verilog` | 结构 Verilog 文本视图 + ihdl 导入 + oa2verilog 导出 | `read` / `write` / `import` / `export` |
| `veriloga` | Verilog-A 文本视图 + headless Check and Save | `read` / `write` / `check_and_save` |
| `calibre` | DRC/LVS/PEX 三件套（非阻塞 job） | `check_env` / `drc` / `lvs` / `pex` / `status` / `read_results` / `export` |
| `spectre` | 独立 Spectre 仿真/读结果/测量/导出 | `check_license` / `run` / `read_results` / `measure` / `export` |
| `skillref` | SKILL/文档检索 | `search` / `info` |

完整 75 个 operation 与字段见 `references/operations.md`。

## 4. 常见调用模式（真实形态，按此抄）

### 4.1 直接跑 SKILL / 命令

```json
{"operation":"basic.skill.execute","token":"vb-vblog","skill_code":"ddGetLibList()"}
{"operation":"basic.command.run","token":"vb-vblog","cmd":"command -v strmin"}
```

### 4.2 建库 → 建视图 → 写原理图

```json
{"operation":"virtuoso.cellview.lib.create","token":"vb-vblog","library":"mylib","path":"/home/user/.virtuoso-bridge/vblog/mylib"}
{"operation":"virtuoso.cellview.view.create","token":"vb-vblog","library":"mylib","cell":"inv","view":"schematic","view_type":"schematic"}
{"operation":"virtuoso.schematic.write","token":"vb-vblog","library":"mylib","cell":"inv","view":"schematic",
 "commands":[
   {"op":"place_instance","master_lib":"mylib","master_cell":"nand2","master_view":"symbol","name":"I0","x":0,"y":0},
   {"op":"place_label","text":"net1","x":0.5,"y":0}]}
```

`write.commands` 是**原子命令组**：一次给一组，包内统一改完再 check/save；不是逐个调多次。

### 4.3 GDS 导出 / 导入

```json
{"operation":"virtuoso.layout.gds","token":"vb-vblog","action":"export",
 "library":"mylib","cell":"inv","view":"layout","file_path":"C:/work/inv.gds"}
{"operation":"virtuoso.layout.gds","token":"vb-vblog","action":"import",
 "library":"mylib","tech_lib":"cdsDefTechLib","file_path":"C:/work/inv.gds","top_cell":"inv"}
```

`file_is_local=false` 时 `file_path/log_path` 是**远端绝对路径**（原样透传，不拍平成 Windows 反斜杠路径）。

### 4.4 Maestro 仿真

```json
{"operation":"virtuoso.maestro.run","token":"vb-vblog","library":"maestro_tb","cell":"rc_probe","view":"maestro","blocking":false}
{"operation":"virtuoso.maestro.read_results","token":"vb-vblog","library":"maestro_tb","cell":"rc_probe","view":"maestro","history":"Interactive.1"}
```

`run` 默认非阻塞（立即返回 history），阻塞由 `blocking=true` 控制；仿真走 GUI 会话，
残留后台会话会阻塞 GUI 打开——按包内“只上报、不自动关闭”的口径处理，写用例要保证自己关会话。

### 4.5 Verilog 导入 / Verilog-A Check and Save

```json
{"operation":"virtuoso.verilog.import","token":"vb-vblog","library":"mylib","cell":"top",
 "file_path":"C:/work/top.v","file_is_local":true,"timeout":180}
{"operation":"virtuoso.veriloga.check_and_save","token":"vb-vblog","library":"mylib","cell":"amp","view":"veriloga"}
```

`import` 成功只看日志 `End of Logfile.` + 产物视图（不信任 rc）；空 `ref_lib_list` 默认 `basic`；
LD_LIBRARY_PATH 由包自己按 Cadence root 推导。

### 4.6 Calibre / Spectre

```json
{"operation":"calibre.drc","token":"vb-vblog","gds":"/data/inv.gds","top":"inv","deck":"/pdks/calibre.drc","blocking":false}
{"operation":"calibre.status","token":"vb-vblog","job_id":"drc_inv","kind":"drc"}
{"operation":"spectre.run","token":"vb-vblog","tasks":[{"job":"rc","netlist":"C:/work/tb.scs","parse":"auto"}]}
```

Calibre 默认后台 job，用 `status`/`read_results` 收口；pex 第三阶段 `-fmt spice` 才会产可仿真网表。

### 4.7 GUI：列窗口 / 弹窗 / 截图

```json
{"operation":"virtuoso.gui.list_windows","token":"vb-vblog"}
{"operation":"virtuoso.gui.send_key","token":"vb-vblog","window_id":"0x2200008","key":"enter"}
{"operation":"virtuoso.gui.screenshot","token":"vb-vblog","target":"display","output_path":"C:/work/display.ppm"}
```

DISPLAY 由包通过 `query` 读 `roles.gui.display` 自行拼 `export DISPLAY=...`，不猜 `/proc`、不兜底 `:0`；
顶层窗口用 EWMH `_NET_CLIENT_LIST`（无 WM 时退 root 直接子窗口）。

## 5. 关键机制与坑（踩过才写进来的）

1. **不要假成功**：失败必须 `ok=false` + 可归因 error（网表导入、PEX 三阶段、schCheck 等都已按此收敛）。
2. **锁与权限要分清**：版图/文本视图被别的会话持锁时，报“被锁/打开失败”，不能误报“视图不存在”。
3. **SKILL 返回值要判内容**：`schCheck` 失败时 SKILL 执行仍 status=success、输出 `"check-failed"`——包要判字符串。
4. **会话要自己收**：自己 `maeOpenSetup` 打开的会话必须关；`maestro.run` 遇到残留后台会话会报冲突而不是强行关。
5. **路径**：远端一律 posix 语义（`posixpath`），客户端才用 `pathlib`；上传/下载走中层文件接口，不自己 SSH/SCP。
6. **数值/布尔字段**：序列化用统一的 `_skill_value_expr`（数字→数字、bool→`t/nil`、字符串→带引号），不能把数字当字符串。
7. **窗口匹配要精确**：按标题 `Editing:/Reading:` 后的 lib/cell/view 三 token 全等，不要子串匹配。
8. **测试口径**：上层包的纯逻辑必须离线可测（fake middle）；真机证据才写 `test/artifacts/evidence/`，红→绿成对。

## 6. 排查顺序

1. `GET /health`（8127）→ 是否在跑、operation 数；
2. 该包 spec：`spec/design-concepts/上层/<N>-<包名>.md`（字段与语义唯一来源）；
3. `references/operations.md` 核对 operation 名与最小字段；
4. 失败时看返回的 `steps[].detail` 里的 SKILL/命令原文，别只看 error 文本；
5. 环境事实看 `test/docs/环境说明.md`（靶机、端口、账号、恢复步骤）。
