# maestro —— ADE / Maestro 仿真

Maestro（ADE）是 Virtuoso 的仿真环境：一个 `maestro` 视图里放若干 test（仿真用例）、
变量、corner、分析类型和输出。本包负责**改配置 → 跑仿真 → 读结果 → 看历史**。

前提：目标 cell 已经有一个 `maestro` 视图（通常先在 Virtuoso 里建好或用 ADE 打开保存一次）。
先 `read_config` 能读到内容，再往下做。

## 1. `virtuoso.maestro.read_config` — 读配置

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `maestro` | 视图名 |
| `include_parameters` | bool | — | `true` | 是否包含参数（大设计可以关掉省流量） |
| `include_raw` | bool | — | `false` | 是否附带原始 SKILL 文本 |

返回 `data.value`：`tests.<test>.{variables,analyses,outputs,env_options,sim_options}`、
`corners.<corner>.{variables,parameters}`、全局 `variables`/`parameters`、`run_options`、
`run_mode`、`job_control_mode`、`current_history`。

## 2. `virtuoso.maestro.write` — 改配置

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令组（见 §2.1） |
| `view` | str | — | `maestro` | 视图名 |
| `save` | bool | — | `true` | 改完是否立即保存 |

返回 `data.value` = `{"applied": n}`。

### 2.1 原子命令

| 原子 | 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|---|
| `set_test` | `test` | str | ✅ | — | 测试名（不存在则新建） |
| | `lib`（或 `library`）, `cell` | str | ✅ | — | 该 test 指向的设计 |
| | `view`, `simulator` | str | — | `schematic` / `spectre` | 设计视图与仿真器 |
| `set_design` | `test`, `lib`（或 `library`）, `cell` | str | ✅ | — | 只改 test 绑定的设计 |
| | `view` | str | — | `schematic` | 设计视图 |
| `delete_test` | `test` | str | ✅ | — | 删除测试 |
| `set_analysis` | `test`, `analysis` | str | ✅ | — | 分析类型，如 `tran` / `dc` / `ac` / `noise` |
| | `enable` | bool | — | `true` | 是否启用 |
| | `options` | dict | — | 无 | 分析参数，如 `{"stop":"10n"}` / `{"start":"1u","stop":"10m"}` |
| `set_var` | `name`, `value` | str/任意 | ✅ | — | 变量名与值（值可以是数字/字符串/表达式） |
| | `scope` | str | — | `global` | `global` / `test` / `corner` |
| | `test`（或 `tests`） | str/list | scope=test 时 | — | 作用范围 |
| | `corner`（或 `corners`） | str/list | scope=corner 时 | — | 作用范围 |
| `delete_var` | `name` | str | ✅ | — | 变量名 |
| | `scope` | str | — | `global` | 也可用 `all` 清所有范围 |
| | `test`/`tests`, `corner`/`corners`, `all_tests` | — | — | — | 限定范围 |
| `set_parameter` | `name` | str | ✅ | — | 参数路径，必须是 `库/cell/视图/实例/参数` 五段 |
| | `value` | 任意 | ✅ | — | 新值 |
| | `corner`（或 `corners`） | str/list | — | 无 | 给 corner 级参数时必填 |
| `delete_parameter` | `name` | str | ✅ | — | 参数路径 |
| | `corner`（或 `corners`） | str/list | — | 无 | corner 级参数 |
| `set_env_option` / `set_sim_option` | `test` | str | ✅ | — | 目标测试 |
| | `options` | dict | ✅ | — | 环境/仿真选项，如 `{"temp":"27"}` |
| `set_corner` | `name` | str | ✅ | — | corner 名 |
| | `enabled` | bool | — | 无 | 是否启用 |
| | `enable_tests` / `disable_tests` | list[str] | — | 无 | 该 corner 覆盖哪些 test |
| `delete_corner` | `name` | str | ✅ | — | 删除 corner |
| `setup_corner` | `name` | str | ✅ | — | corner 名 |
| | `variables` | dict | — | 无 | corner 变量，如 `{"temperature":27}` |
| | `model_file`, `model_section` | str | — | 无 | 该 corner 的模型文件与 section |
| `load_corners` | `filepath`（或 `remote_path`） | str | ✅ | — | corner 定义文件 |
| | `sections`, `operation` | str | — | `corners` / `overwrite` | 读哪些段、如何合并 |
| `set_run_mode` | `run_mode` | str | ✅ | — | 运行模式 |
| `set_job_control_mode` | `mode` | str | ✅ | — | 任务控制模式 |
| `set_simulator_mode` | `mode` | str | ✅ | — | 仿真模式值 |
| | `option` | str | — | `uniMode` | 选项名 |
| `set_job_policy` | `policy` | dict 或 str | ✅ | — | 任务策略（对象或 SKILL 表达式） |
| | `test`（或 `test_name`）, `job_type` | str | — | 无 | 限定作用对象 |
| `add_output` | `name`, `test` | str | ✅ | — | 输出名与所属测试 |
| | `signal_name`, `expr`, `output_type` | str | — | 无 | 信号名 / 表达式 / 输出类型 |
| | `plot`, `save` | bool | — | 无 | 是否画图 / 是否保存 |
| `delete_output` | `name`, `test` | str | ✅ | — | 删除输出 |
| | `delete_spec` | bool | — | 无 | 连同 spec 一起删 |
| `set_spec` | `name`, `test` | str | ✅ | — | 给该输出加规格 |
| | `gt` / `lt` / `min` / `max` / `tol` / `range` | 任意 | — | 只给其中一个 | 规格界 |
| | `info`, `weight`, `corner` | 任意 | — | 无 | 说明/权重/适用 corner |
| `delete_spec` | `name`, `test` | str | ✅ | — | 删除规格 |

### 2.2 示例

```json
{"operation":"virtuoso.maestro.write","token":"TOKEN","library":"maestro_tb","cell":"rc_probe","view":"maestro",
 "commands":[
  {"op":"set_analysis","test":"rc_tran","analysis":"tran","options":{"stop":"10n"}},
  {"op":"set_var","name":"vcm","value":"0.6","scope":"global"},
  {"op":"set_corner","name":"TT","enable_tests":["rc_tran"]},
  {"op":"add_output","test":"rc_tran","name":"VOUT","signal_name":"VOUT"},
  {"op":"set_spec","test":"rc_tran","name":"VOUT","min":0.3}]}
```

## 3. `virtuoso.maestro.run` — 跑仿真

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `maestro` | 视图名 |
| `history` | str | — | 新建 | 要跑的 history 名；不给就新建一条 |
| `blocking` | bool | — | `false` | `false` 立即返回 history，`true` 等跑完再返回 |
| `poll_interval` | number | — | `2.0` | `blocking=true` 时的轮询间隔（秒） |

返回：新 history 的名字（后续读结果用它）。

## 4. `virtuoso.maestro.read_history` — 看历史与状态（轮询用这个）

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `history` | str | — | 最新 | history 名 |
| `view` | str | — | `maestro` | 视图名 |

返回 `data.value`：各 history 的状态、时间等信息。**判断"跑完没有"看这里**。

## 5. `virtuoso.maestro.read_results` — 读结果

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `history` | str | — | 最新 | history 名 |
| `test` / `analysis` / `waveform` / `result` | str | — | 全部 | 逐级过滤到某个信号/结果 |
| `view` | str | — | `maestro` | 视图名 |
| `notation` | str | — | `scientific` | 数值表示法 |
| `precision` / `width` | int | — | 无 | 数值精度 / 显示宽度 |
| `output_path` | str | — | 无 | 结果另存到该路径 |

## 6. `virtuoso.maestro.export` — 导出

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `kind` | str | ✅ | — | `netlist` / `script` / `outputs_csv` / `snapshot` / `screenshot` |
| `history` | str | — | 最新 | 针对哪条 history |
| `test` / `corner` | str | — | 全部 | 过滤 |
| `output_path` | str | — | 自动 | 导出落点 |
| `window_id`, `region`, `toplevel` | — | — | — | `kind=screenshot` 时用 |

## 7. `virtuoso.maestro.write_history` — 管理历史记录

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令 |
| `view` | str | — | `maestro` | 视图名 |

历史原子：

| 原子 | 参数 | 必填 | 说明 |
|---|---|---|---|
| `rename` | `history`, `new_name` | ✅ | 重命名 history |
| `lock` / `unlock` | `history` | ✅ | 加锁/解锁（锁住的不能被删） |
| `delete` | `history` | ✅ | 删除 history |
| `delete_results` | `history` | ✅ | 只删结果数据；可选 `keep_netlist`, `keep_quick_plot`（bool） |

## 8. GUI 相关

| 操作 | 参数 | 必填 | 说明 |
|---|---|---|---|
| `virtuoso.maestro.open_gui` | `library`, `cell`；可选 `view`, `history` | ✅ | 打开 ADE 窗口 |
| `virtuoso.maestro.close_gui` | `library`, `cell`；可选 `view` | ✅ | 关闭窗口 |
| `virtuoso.maestro.open_waveform_gui` | `library`, `cell`, `history`, `signals`；可选 `test`, `analysis`, `view` | ✅ | 打开波形窗口，`signals` 如 `["VOUT","VIN"]` |
| `virtuoso.maestro.close_waveform_gui` | 可选 `session`, `window` | — | 关闭波形窗口 |

> 后台操作与 GUI 会话操作同一个 `maestro` 视图时容易互相冲突：跑批量任务前先关掉 ADE 窗口。

## 9. 注意事项

- `run` 默认非阻塞；**不要用 `read_results` 当轮询**，用 `read_history`。
- `set_var` 的值建议用字符串或数字；表达式类值按 SKILL 语义解析。
- corner 相关的原子在 corner 不存在时会直接报 `corner not found: xxx`。
- 改了配置记得确认 `save`（默认 `true`），否则只改了内存中的会话。
