# spectre —— 独立 Spectre 仿真

不经过 Virtuoso：直接把网表交给 Spectre 主机跑，再读结果、量指标、导出数据。
适合批量扫描、CI 化回归、以及只想跑仿真不需要画图的场景。

## 1. `spectre.check_license` — 查许可

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `spectre_bin` | str | — | 注册时探测到的 | 指定 spectre 可执行文件路径 |

返回 `data.value`：许可可用性与版本信息。

## 2. `spectre.run` — 批量跑仿真

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `tasks` | list[dict] | ✅ | — | 任务列表，见下 |
| `max_workers` | int | — | `4` | 并行任务数 |
| `mode` | str | — | `spectre` | 仿真模式：`spectre` / `aps` / `x` / `cx` / `ax` / `mx` / `lx` / `vx` |
| `spectre_args` | list[str] | — | 空 | 追加给 spectre 的命令行参数（任务级可覆盖） |
| `spectre_bin` | str | — | 默认 | 指定可执行文件 |
| `parse` | str | — | `auto` | `auto`（自动解析结果）或 `none`（只跑不解析） |
| `download` | bool | — | `true` | 是否把结果拉回本机 |
| `output_root` | str | — | 自动 | 结果目录 |
| `keep_run_dir` | bool | — | `false` | 是否保留运行目录 |

`tasks[]` 每一项：

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `job` | str | ✅ | 任务名，**同一次调用里必须唯一** |
| `netlist` | str | ✅ | 网表路径（目标机器上） |
| `include_files` | list[str] | — | 需要一并带上/可见的 include 文件 |
| `mode` | str | — | 覆盖本次调用的 `mode` |
| `spectre_args` | list[str] | — | 覆盖本次调用的参数 |

```json
{"operation":"spectre.run","token":"TOKEN",
 "tasks":[{"job":"rc_tt","netlist":"/home/user/work/tb.scs"},
          {"job":"rc_ff","netlist":"/home/user/work/tb.scs","spectre_args":["+corners=ff"]}],
 "max_workers":2,"parse":"auto","download":true}
```

## 3. `spectre.read_results` — 读 PSF 结果

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `source` | str | ✅ | — | 结果路径（`.raw` 文件或结果目录，目标机器上） |
| `analysis` | str | — | `all` | 只读某个分析，如 `tran` / `ac` / `dc` |
| `output_dir` | str | — | 无 | 解析结果的落点 |

返回 `data.value`：按分析组织的信号数据。

## 4. `spectre.measure` — 量指标

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `metrics` | list[dict] | ✅ | — | 指标列表，见下 |
| `data` | dict | — | 无 | 直接用上一步 `read_results` 的返回 |
| `source_path` | str | — | 无 | 或直接从结果路径读 |

`data` 与 `source_path` 二选一。

支持的指标类型：

| `type` | 需要的字段 | 说明 |
|---|---|---|
| `min` / `max` / `mean` / `rms` | `signal` | 统计量 |
| `threshold_crossing` | `signal`, `threshold`；可选 `direction`(默认 `rise`)、`edge`(默认 1)、`start`, `stop`, `x`(默认 `time`) | 过阈值时刻 |
| `delay` | `from_signal`, `to_signal`, `threshold`；可选 `direction`, `edge`, `start`, `stop` | 两个信号之间的延时 |
| `ac_magnitude` | `signal` | AC 幅度（dB） |
| `bandwidth` | `signal` | 带宽 |
| `noise_integral` | `signal` | 噪声积分 |

```json
{"operation":"spectre.measure","token":"TOKEN",
 "metrics":[{"type":"max","signal":"vout"},
            {"type":"threshold_crossing","signal":"vout","threshold":0.5,"direction":"rise"}]}
```

## 5. `spectre.export` — 导出数据

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `format` | str | ✅ | — | `csv` 或 `json` |
| `output_path` | str | ✅ | — | 落点（本机路径） |
| `data` 或 `source_path` | dict/str | — | 无 | 数据来源（同 `measure`） |
| `columns` | list[str] | — | 全部 | 只导出这些列 |
| `precision` | int | — | 默认 | 小数位 |

## 6. 注意事项

- 网表里的 `include` 路径要能在 Spectre 主机上解析；不确定就先把文件用 `basic.file.upload` 放过去。
- `job` 名重复会被直接拒绝；批量任务建议用"器件+corner"命名。
- `parse=none` 时不会解析结果，只给你运行状态。
- 跑之前先 `check_license`，避免批量任务全挂在许可上。
