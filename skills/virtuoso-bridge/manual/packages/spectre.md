# spectre —— 独立 Spectre 仿真

不经过 Virtuoso：直接把网表交给 Spectre 主机跑，再读结果、量指标、导出数据。适合批量扫描与回归。

## 1. `spectre.check_license` — 查许可

**功能**：确认 Spectre 可执行文件与许可可用。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `spectre_bin` | str | — | 注册时探测到的 | 指定 spectre 可执行文件 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.bin` | str | 实际使用的可执行文件 |
| `value.version` / `value.version_raw` | str | 版本 |
| `value.licenses` | list | 许可信息（`lmstat` 结果） |
| `value.errors` / `value.warnings` | list | 错误与警告 |

**示例**

```json
// 输入
{"operation":"spectre.check_license","token":"TOKEN"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"bin":"/cadence/SPECTRE201/bin/spectre","version":"21.1.0.isr4",
 "licenses":[{"feature":"Virtuoso_Spectre","total":50,"used":12}],"errors":[],"warnings":[]}}
```

## 2. `spectre.run` — 批量跑仿真

**功能**：把一组网表并行交给 Spectre 执行，可选解析并回收结果。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `tasks` | list[dict] | ✅ | — | 任务列表，见下 |
| `max_workers` | int | — | `4` | 并行任务数 |
| `mode` | str | — | `spectre` | `spectre` / `aps` / `cx` / `ax` / `mx` / `lx` / `vx`（Spectre X 用 `+preset` 五档，**不提供 `x`**） |
| `spectre_args` | list[str] | — | 空 | 追加给 spectre 的参数（任务级可覆盖） |
| `spectre_bin` | str | — | 默认 | 指定可执行文件 |
| `parse` | str | — | `auto` | `auto`（自动解析）或 `none`（只跑不解析） |
| `download` | bool | — | `true` | 是否把结果拉回本机 |
| `output_root` | str | — | 自动 | 结果目录 |
| `keep_run_dir` | bool | — | `false` | 是否保留运行目录 |

`tasks[]` 每项：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `job` | str | ✅ | 任务名，**同一次调用里唯一** |
| `netlist` | str | ✅ | 网表路径（目标机器上） |
| `include_files` | list[str] | — | 需要一并可见的 include 文件 |
| `mode` | str | — | 覆盖本次调用的 `mode` |
| `spectre_args` | list[str] | — | 覆盖本次调用的参数 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.runs` | list | 每个任务的执行明细（`job`、状态、运行目录、耗时等） |
| `value.succeeded` / `value.failed` | int | 成功/失败任务数 |

**示例**

```json
{"operation":"spectre.run","token":"TOKEN",
 "tasks":[{"job":"rc_tt","netlist":"/home/user/work/tb.scs"},
          {"job":"rc_ff","netlist":"/home/user/work/tb.scs","spectre_args":["+corners=ff"]}],
 "max_workers":2,"parse":"auto","download":true}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"succeeded":2,"failed":0,
 "runs":[{"job":"rc_tt","status":"ok","run_dir":"/home/user/work/spectre/rc_tt","output_dir":"C:/work/spectre/rc_tt"},
         {"job":"rc_ff","status":"ok","run_dir":"/home/user/work/spectre/rc_ff","output_dir":"C:/work/spectre/rc_ff"}]}}
```

## 3. `spectre.read_results` — 读 PSF 结果

**功能**：解析 Spectre 结果目录/文件，得到按分析组织的数据。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `source` | str | ✅ | — | 结果路径（`.raw` 文件或结果目录） |
| `analysis` | str | — | `all` | 只读某个分析，如 `tran` / `ac` / `dc` |
| `output_dir` | str | — | 无 | 解析结果落点 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.kind` / `value.analysis` | str | 结果类型与分析名 |
| `value.signals` / `value.points` | list | 信号名与数据点 |
| `value.analyses` | list | 多分析时的分组 |
| `value.layout` / `value.header` / `value.files` | — | 数据布局、表头与来源文件 |

**示例**

```json
// 输入
{"operation":"spectre.read_results","token":"TOKEN","source":"/home/user/work/tb.raw","analysis":"all"}
// 输出（data.value 内容，节选）
{"ok":true,"error":null,"value":{"kind":"tran","analysis":"tran","signals":["time","vout"],
 "points":1001,"layout":"sweep","header":["time","vout"],"analyses":["tran"],"files":["/home/user/work/tb.raw"]}}
```

## 4. `spectre.measure` — 量指标

**功能**：从结果里算指标（统计量、过阈值时刻、延时、带宽、噪声积分等）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `metrics` | list[dict] | ✅ | — | 指标列表，见下 |
| `data` | dict | — | 无 | 直接用上一步的结果 |
| `source_path` | str | — | 无 | 或直接从结果路径读 |

指标类型与所需字段：

| `type` | 需要的字段 | 说明 |
|---|---|---|
| `min` / `max` / `mean` / `rms` | `signal` | 统计量 |
| `threshold_crossing` | `signal`, `threshold`；可选 `direction`(默认 `rise`)、`edge`、`start`、`stop`、`x` | 过阈值时刻 |
| `delay` | `from_signal`, `to_signal`, `threshold`；可选 `direction`、`edge`、`start`、`stop` | 两信号间延时 |
| `ac_magnitude` / `bandwidth` / `noise_integral` | `signal` | 频域/噪声指标 |

**返回**：每条指标一项 `{type, ok, value, unit, detail}`（`detail` 里是失败原因）。

**示例**

```json
{"operation":"spectre.measure","token":"TOKEN",
 "metrics":[{"type":"max","signal":"vout"},
            {"type":"threshold_crossing","signal":"vout","threshold":0.5,"direction":"rise"}]}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"metrics":[{"type":"max","ok":true,"value":1.203,"unit":"V","detail":null},
 {"type":"threshold_crossing","ok":true,"value":2.1e-9,"unit":"s","detail":null}]}}
```

## 5. `spectre.export` — 导出数据

**功能**：把结果或指标导出成 CSV/JSON 文件。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `format` | str | ✅ | — | `csv` 或 `json` |
| `output_path` | str | ✅ | — | 落点（本机路径） |
| `data` 或 `source_path` | dict/str | — | 无 | 数据来源 |
| `columns` | list[str] | — | 全部 | 只导出这些列 |
| `precision` | int | — | 默认 | 小数位 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.output_path` | str | 落点 |
| `value.format` | str | 实际格式 |
| `value.columns` / `value.rows` / `value.bytes` | int/list | 列、行数与文件大小 |

**示例**

```json
// 输入
{"operation":"spectre.export","token":"TOKEN","format":"csv","output_path":"C:/work/rc.csv","source_path":"/home/user/work/tb.raw"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"output_path":"C:/work/rc.csv","format":"csv","columns":["time","vout"],"rows":1001,"bytes":24510}}
```

## 6. 注意事项

- 跑之前先 `check_license`，避免批量任务全挂在许可上。
- `tasks[].job` 重复会被拒绝；网表里的 `include` 路径要能在 Spectre 主机上解析。
- `parse=none` 只给运行状态，不解析结果。
