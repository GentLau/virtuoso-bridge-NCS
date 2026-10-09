# maestro —— ADE / Maestro 仿真

Maestro（ADE）是 Virtuoso 的仿真环境：一个 `maestro` 视图里放若干 test、变量、corner、分析和输出。
本包负责**改配置 → 跑仿真 → 读结果 → 管历史**。

前提：目标 cell 已经有 `maestro` 视图（通常先在 Virtuoso 里建好并保存一次）。先 `read_config` 能读到内容再往下做。

## 1. `virtuoso.maestro.read_config` — 读配置

**功能**：读取整个 Maestro 配置（测试、变量、corner、分析、输出、spec、运行模式）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `maestro` | 视图名 |
| `include_parameters` | bool | — | `true` | 是否包含参数（大设计可关掉省流量） |
| `include_raw` | bool | — | `false` | 是否附带原始 SKILL 文本 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.tests` | list | 测试列表（名字、绑定的设计、仿真器） |
| `value.analyses` / `value.outputs` / `value.specs` | list | 分析、输出与规格 |
| `value.variables` / `value.parameters` | list | 全局变量与器件参数 |
| `value.corners` / `value.corner_variables` | list | corner 及其变量 |
| `value.run_mode` / `value.job_control_mode` | str | 运行模式与任务控制模式 |
| `value.current_history` | str | 当前 history |
| `value.raw` | dict | 原始 SKILL（`include_raw=true` 时） |

**示例**

```json
// 输入
{"operation":"virtuoso.maestro.read_config","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro"}
// 输出（data.value 内容，节选）
{"ok":true,"error":null,"value":{"tests":[{"name":"rc_tran","lib":"maestro_tb","cell":"rc_probe","view":"schematic"}],
 "analyses":[{"test":"rc_tran","name":"tran","enable":true,"options":{"stop":"10n"}}],
 "outputs":[{"test":"rc_tran","name":"VOUT","signal_name":"VOUT"}],
 "variables":[{"name":"vcm","value":"0.6","scope":"global"}],
 "corners":["TT"],"run_mode":"single","current_history":"Interactive.1"}}
```

## 2. `virtuoso.maestro.write` — 改配置

**功能**：用原子命令批量修改 Maestro 配置。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令组 |
| `view` | str | — | `maestro` | 视图名 |
| `save` | bool | — | `true` | **本版不支持 `save=false`**（会明确报错） |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.applied` | int | 成功应用的命令条数 |
| `value.session` | str | 本次使用的会话标识 |

### 2.1 原子命令

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `set_test` | `test`, `lib`（或 `library`）, `cell` | str | ✅ | — | 新建/改测试 |
| | `view` / `simulator` | str | — | `schematic` / `spectre` | 设计视图与仿真器 |
| `set_design` | `test`, `lib`, `cell`；可选 `view` | str | ✅ | — | 只改测试绑定的设计 |
| `delete_test` | `test` | str | ✅ | — | 删测试 |
| `set_analysis` | `test`, `analysis` | str | ✅ | — | 分析类型：`tran`/`dc`/`ac`/`noise`… |
| | `enable` / `options` | bool/dict | — | `true` / 无 | 是否启用与参数，如 `{"stop":"10n"}` |
| `set_var` | `name`, `value` | str/任意 | ✅ | — | 变量 |
| | `scope` | str | — | `global` | `global`/`test`/`corner` |
| | `test`/`tests`、`corner`/`corners` | str/list | — | 无 | 限定作用范围 |
| `delete_var` | `name` | str | ✅ | — | 删变量；`scope=all` 清所有范围 |
| | `test`/`tests`、`corner`/`corners`、`all_tests` | — | — | 无 | 限定范围 |
| `set_parameter` | `name`, `value` | str/任意 | ✅ | — | 参数路径必须是 `库/cell/视图/实例/参数` 五段 |
| | `corner`/`corners` | str/list | — | 无 | corner 级参数 |
| `delete_parameter` | `name`；可选 `corner`/`corners` | str | ✅ | — | 删参数 |
| `set_env_option` / `set_sim_option` | `test`, `options` | str/dict | ✅ | — | 环境/仿真选项，如 `{"temp":"27"}` |
| `set_run_option` | `options` | dict | ✅ | — | 运行选项（Monte Carlo 等），至少一项 |
| `set_corner` | `name` | str | ✅ | — | corner；可选 `enabled`、`enable_tests`、`disable_tests` |
| `delete_corner` | `name` | str | ✅ | — | 删 corner |
| `setup_corner` | `name` | str | ✅ | — | corner；可选 `variables`、`model_file`、`model_section` |
| `load_corners` | `filepath`（或 `remote_path`） | str | ✅ | — | 导入 corner 文件（支持 CSV）；可选 `operation`（默认 `overwrite`）、`sections`（仅 .sdb 用） |
| `set_run_mode` | `run_mode` | str | ✅ | — | 运行模式 |
| `set_job_control_mode` | `mode` | str | ✅ | — | 任务控制模式 |
| `set_simulator_mode` | `mode`；可选 `option` | str | ✅ | `uniMode` | 高性能仿真模式 |
| `create_job_policy` | `name`, `policy`；可选 `job_type` | — | name+policy | — | 新建任务策略 |
| `attach_job_policy` | `test`, `name`（策略名）；可选 `test_name`/`job_type` | — | test+name | — | 把策略挂到某个测试 |
| `delete_job_policy` | `name` | str | ✅ | — | 删除策略 |
| `add_output` | `name`, `test` | str | ✅ | — | 加输出；可选 `output_type`、`signal_name`、`expr`、`plot`、`save` |
| `delete_output` | `name`, `test`；可选 `delete_spec` | str/bool | ✅ | — | 删输出 |
| `set_spec` | `name`, `test` + 一个界（`gt`/`lt`/`min`/`max`/`tol`/`range`） | — | ✅ | — | 加规格；可选 `info`、`weight`、`corner` |
| `delete_spec` | `spec_name`（或 `test`+`output`） | str | ✅ | — | 删规格 |

**示例**

```json
{"operation":"virtuoso.maestro.write","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro",
 "commands":[
  {"op":"set_analysis","test":"rc_tran","analysis":"tran","options":{"stop":"10n"}},
  {"op":"set_var","name":"vcm","value":"0.6","scope":"global"},
  {"op":"set_corner","name":"TT","enable_tests":["rc_tran"]},
  {"op":"add_output","test":"rc_tran","name":"VOUT","signal_name":"VOUT"},
  {"op":"set_spec","test":"rc_tran","name":"VOUT","min":0.3}]}
// 输出（data.value 内容；save=false 会被明确拒绝）
{"ok":true,"error":null,"value":{"applied":5,"session":"VB_..._1"}}
```

## 3. `virtuoso.maestro.run` — 跑仿真

**功能**：启动一次仿真（默认后台），返回 history 名。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `maestro` | 视图名 |
| `history` | str | — | 新建 | 要跑的 history；不给就新建一条 |
| `blocking` | bool | — | `false` | `true` 时等跑完再返回 |
| `poll_interval` | number | — | `2.0` | `blocking=true` 时的轮询间隔（秒） |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.history` | str | history 名（读结果用它） |
| `value.status` | str | 运行状态 |
| `value.session` | str | 会话标识 |
| `value.progress` | dict | 进度（运行中时） |

**示例**

```json
// 输入
{"operation":"virtuoso.maestro.run","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro","blocking":false}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"history":"Interactive.2","status":"running","session":"VB_..._2"}}
```

## 4. `virtuoso.maestro.read_history` — 看历史与状态

**功能**：读某条（或当前）history 的状态与进度——**轮询用这个**。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `history` | str | — | 当前 | history 名 |
| `view` | str | — | `maestro` | 视图名 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.histories` | list | 历史记录列表 |
| `value.current` / `value.current_history` | str | 当前 history |
| `value.status` | str | 状态 |
| `value.tests_done` / `value.tests_total` | int | 测试完成/总数 |
| `value.corners_done` / `value.corners_total` | int | corner 完成/总数 |
| `value.points_done` / `value.points_total` | int | 扫描点完成/总数 |
| `value.results_dir` / `value.lock_flag` | str/bool | 结果目录 / 是否加锁 |

**示例**

```json
// 输入
{"operation":"virtuoso.maestro.read_history","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro","history":"Interactive.2"}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"histories":["Interactive.1","Interactive.2"],"current":"Interactive.2",
 "status":"running","tests_done":1,"tests_total":1,"corners_done":0,"corners_total":1,
 "points_done":0,"points_total":1,"results_dir":"/home/user/sim/.../Interactive.2","lock_flag":false}}
```

## 5. `virtuoso.maestro.read_results` — 读结果

**功能**：读取仿真结果（可按 test/analysis/波形过滤）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `history` | str | — | 最新 | history 名 |
| `test` / `analysis` / `waveform` / `result` | str | — | 全部 | 逐级过滤 |
| `view` | str | — | `maestro` | 视图名 |
| `notation` / `precision` / `width` | str/int | — | `scientific`/默认 | 数值格式 |
| `output_path` | str | — | 无 | 结果另存位置 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.history` | str | history 名 |
| `value.tests` / `value.outputs` | list | 测试与输出结果 |
| `value.points` | list | 扫描点结果 |
| `value.overall_spec` / `value.overall_yield` | — | 总体规格通过情况与良率 |
| `value.local_path` | str | 另存位置（给了 `output_path` 时） |

**示例**

```json
// 输入
{"operation":"virtuoso.maestro.read_results","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro","history":"Interactive.1","test":"rc_tran"}
// 输出（data.value 内容，节选）
{"ok":true,"error":null,"value":{"history":"Interactive.1",
 "tests":[{"name":"rc_tran","outputs":[{"name":"VOUT","value":1.203,"unit":"V","spec":{"type":"min","value":0.3,"pass":true}}]}],
 "points":[],"overall_spec":"pass","overall_yield":1.0}}
```

## 6. `virtuoso.maestro.export` — 导出

**功能**：导出网表、脚本、结果 CSV、快照或截图。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `kind` | str | ✅ | — | `netlist` / `script` / `outputs_csv` / `snapshot` / `screenshot` |
| `history` | str | — | 最新 | 针对哪条 history |
| `test` / `corner` | str | — | 全部 | 过滤 |
| `output_path` | str | — | 自动 | 导出落点 |
| `window_id` / `region` / `toplevel` | — | — | — | `kind=screenshot` 时用 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.kind` | str | 导出类型 |
| `value.local_path` | str | 本机落点 |
| `value.remote_path` | str | 目标机器上的原始文件 |
| `value.script` / `value.snapshot` | dict | 脚本/快照内容（对应 kind） |

**示例**

```json
// 输入
{"operation":"virtuoso.maestro.export","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","kind":"outputs_csv","history":"Interactive.1"}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"kind":"outputs_csv","local_path":"C:/work/artifact/maestro/rc_probe/Interactive.1/outputs.csv",
 "remote_path":"/home/user/.virtuoso-bridge/<user>/artifact/maestro/rc_probe/Interactive.1/outputs.csv"}}
```

## 7. `virtuoso.maestro.write_history` — 管理历史记录

**功能**：重命名、加解锁、删除 history 或其结果。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令 |
| `view` | str | — | `maestro` | 视图名 |

历史原子：

| 原子 | 参数 | 必填 | 说明 |
|---|---|---|---|
| `rename` | `history`, `new_name` | ✅ | 重命名 |
| `lock` / `unlock` | `history` | ✅ | 加锁/解锁（锁住不能删） |
| `delete` | `history` | ✅ | 删除 history |
| `delete_results` | `history`；可选 `keep_netlist`、`keep_quick_plot` | ✅ | 只删结果数据 |

**返回**：`value.applied` / `value.rename` / `value.session`。

```json
{"operation":"virtuoso.maestro.write_history","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro",
 "commands":[{"op":"rename","history":"Interactive.1","new_name":"rc_v1"}]}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"applied":1,"rename":{"history":"Interactive.1","new_name":"rc_v1"},"session":"VB_..._1"}}
```

## 8. GUI 相关

### 8.1 `virtuoso.maestro.open_gui` — 打开 ADE 窗口

**功能**：打开 Maestro/ADE 图形窗口。
**输入参数**：`library`, `cell`；可选 `view`、`history`。
**返回**：`value.session` / `value.window` / `value.title` / `value.mode`。

```json
// 输入
{"operation":"virtuoso.maestro.open_gui","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro"}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"session":"VB_..._4","window":"0x2a0000c","title":"ADE Assembler","mode":"gui"}}
```

### 8.2 `virtuoso.maestro.close_gui` — 关闭 ADE 窗口

**功能**：关闭 Maestro/ADE 窗口。
**输入参数**：`library`, `cell`；可选 `view`。
**返回**：`value.session` / `value.window` / `value.closed`。

```json
// 输入
{"operation":"virtuoso.maestro.close_gui","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro"}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"session":"VB_..._4","window":"0x2a0000c","closed":true}}
```

### 8.3 `virtuoso.maestro.open_waveform_gui` — 打开波形窗口

**功能**：把指定信号在波形窗口里画出来。
**输入参数**：`library`, `cell`, `history`, `signals`；可选 `test`、`analysis`、`view`。
**返回**：`value.session` / `value.session_created` / `value.window` / `value.signals`。

```json
// 输入
{"operation":"virtuoso.maestro.open_waveform_gui","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","history":"Interactive.1","signals":["VOUT"]}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"session":"VB_..._3","session_created":true,"window":"0x2a0000b","signals":["VOUT"]}}
```

### 8.4 `virtuoso.maestro.close_waveform_gui` — 关闭波形窗口

**功能**：关闭波形窗口。
**输入参数**：可选 `session`、`window`（都不给则关当前会话的波形窗口）。
**返回**：`value.session` / `value.window` / `value.closed`。

```json
// 输入
{"operation":"virtuoso.maestro.close_waveform_gui","token":"TOKEN","session":"VB_..._3"}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"session":"VB_..._3","window":"0x2a0000b","closed":true}}
```

## 9. 注意事项

- `run` 默认非阻塞；**用 `read_history` 轮询**，不要用 `read_results` 当轮询。
- corner/测试相关的原子在对象不存在时会直接报错（如 `corner not found: xxx`）。
- 后台操作与 GUI 会话操作同一个 `maestro` 视图容易冲突：批量任务前先关掉 ADE 窗口。
- 同一个 maestro 视图已以**只读**方式被别的会话打开时，写操作会被结构化拒绝（不会改坏现场）：
  先关掉那个会话，或改用另一条 history。
