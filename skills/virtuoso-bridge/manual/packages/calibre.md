# calibre —— DRC / LVS / PEX

在目标机器上跑 Calibre 物理验证。默认**后台执行**：先拿 `job_id`，再轮询、读结论、导出报告。

> **当前状态（先读这一段）**
>
> - `calibre.drc` 与 `calibre.lvs` 可用：无 runset 时走官方 CLI（deck + 白名单占位符改写），
>   给了 `runset` 时走 `calibre -gui -<app> -runset <file> -batch`（本包不翻译参数）；
> - **`calibre.pex` 本版不提供**：操作保留，但调用会立即返回 `pex_unsupported`；
> - 该包整体处于暂缓开发状态，恢复方向见仓库内调研文档。

## 1. `calibre.check_env` — 查环境

**功能**：确认 Calibre 可执行文件、版本与 deck 是否就位。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `calibre_bin` | str | — | 自动探测 | 指定 calibre 可执行文件 |
| `deck` | str | — | 无 | 顺带检查某个 rule deck 是否存在 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.calibre_path` / `value.version` | str | 可执行文件与版本 |
| `value.deck_ok` / `value.deck_detail` | bool/str | deck 检查结果与说明 |

**示例**

```json
// 输入
{"operation":"calibre.check_env","token":"TOKEN","deck":"/pdks/calibre/drc.deck"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"calibre_path":"/eda/calibre/bin/calibre","version":"2023.4_28.15",
 "deck_ok":true,"deck_detail":"exists"}}
```

## 2. `calibre.drc` / `calibre.lvs` — 提交任务

**功能**：跑一次 DRC / LVS（默认后台），返回任务名供后续查询。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `deck` | str | 与 `runset` 二选一 | — | rule deck；deck 里出现的占位符（GDS/顶层/网表等）必须由对应参数补上 |
| `runset` | str | 与 `deck` 二选一 | — | GUI runset 生成的 control file（自包含时不必再给 deck/gds/top） |
| `gds` | str | 见上 | 无 | 版图 GDS 路径（目标机器上） |
| `top` | str | 见上 | 无 | 顶层 cell 名 |
| `cdl` | str | LVS 常用 | 无 | 源网表（deck 引用它时必须给） |
| `source` | dict | — | 无 | **只对 `calibre.lvs` 有效**：源侧网表来源，见下 |
| `emit_cdl` | bool | — | `false` | **只对 `calibre.lvs` 有效**：`source.kind=schematic` 时从原理图现产 CDL |
| `cds_lib` | str | — | 从 CIW 推断 | **只对 `calibre.lvs` 有效**：现产 CDL 用的 `cds.lib` 路径 |
| `lvs_run_dir` | str | — | 无 | 复用已有 LVS 结果时给 |
| `job_id` | str | — | 自动 | 任务名，后续查询的主键（建议自己起名） |
| `run_dir` | str | — | 自动 | 运行目录 |
| `calibre_bin` | str | — | 自动 | 可执行文件 |
| `turbo` | int | — | `4` | 并行度，1–64 |
| `hier` | bool | — | `true` | 层次化 |
| `fmt` | str | — | `none` | `none` / `spice` / `simple` |
| `params` | dict[str,str] | — | 无 | 覆盖 deck 变量；**每个值必须是单行** |
| `spice_file` | str | — | 无 | 指定 SPICE 网表文件 |
| `hcell_file` / `xcell_file` | str | — | 无 | 层次化/黑盒控制文件 |
| `blocking` | bool | — | `false` | `true` 时等跑完 |
| `poll_interval` | number | — | `5.0` | `blocking=true` 时的轮询间隔（秒） |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.job_id` | str | 任务名（后续 `status`/`read_results`/`export` 用它） |
| `value.run_dir` | str | 运行目录 |
| `value.status` | str | 提交后的状态（后台跑时为运行中） |
| `value.source` | dict | LVS 源侧信息（用的哪种 source） |
| `value.emit_cdl` | bool | 本次是否现产了 CDL |

`source` 的两种形态（`calibre.lvs` 专属，与 `cdl` 互斥、不能和 `runset` 同用）：

| 形态 | 写法 | 说明 |
|---|---|---|
| 用已有 CDL | `{"kind":"cdl","path":"/home/user/work/inv.cdl"}` | 先校验该文件在目标机器上存在 |
| 从原理图现产 | `{"kind":"schematic","library":"mylib","cell":"inv","view":"schematic"}` | `view` 可省（默认 `schematic`）；此时可用 `emit_cdl` / `cds_lib` |

**示例**

```json
{"operation":"calibre.drc","token":"TOKEN","job_id":"drc_inv",
 "gds":"/home/user/work/inv.gds","top":"inv","deck":"/pdks/calibre/drc.deck","blocking":false}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"job_id":"drc_inv","run_dir":"/home/user/.virtuoso-bridge/<user>/calibre/drc_inv","status":"running"}}
```

```json
{"operation":"calibre.lvs","token":"TOKEN","job_id":"lvs_inv",
 "gds":"/home/user/work/inv.gds","top":"inv","cdl":"/home/user/work/inv.cdl",
 "deck":"/pdks/calibre/lvs.deck","params":{"TOP":"inv"}}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"job_id":"lvs_inv","run_dir":"/home/user/.virtuoso-bridge/<user>/calibre/lvs_inv","status":"running"}}
```

不想先手工准备 CDL 时，直接让 LVS 从原理图现产：

```json
// 输入
{"operation":"calibre.lvs","token":"TOKEN","job_id":"lvs_inv",
 "gds":"/home/user/work/inv.gds","top":"inv","deck":"/pdks/calibre/lvs.deck",
 "source":{"kind":"schematic","library":"mylib","cell":"inv","view":"schematic"},"emit_cdl":true}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"job_id":"lvs_inv","run_dir":"/home/user/.virtuoso-bridge/<user>/calibre/lvs_inv",
 "status":"running","source":{"kind":"schematic","library":"mylib","cell":"inv","view":"schematic"},"emit_cdl":true}}
```

## 3. `calibre.status` — 查进度

**功能**：查任务当前状态（轮询用）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `job_id` 或 `run_dir` | str | **至少一个** | — | 定位任务 |
| `kind` | str | — | `drc` | `drc` / `lvs` / `pex` |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.status` | str | 任务状态 |
| `value.job_id` / `value.run_dir` | str | 任务标识 |
| `value.process_alive` / `value.pid` | bool/int | 进程是否还活着 |
| `value.log_tail` | str | 日志尾部（排查用） |
| `value.artifacts` | list | 已产生的产物 |
| `value.failure_kind` | str | 失败分类（失败时） |

**示例**

```json
// 输入
{"operation":"calibre.status","token":"TOKEN","job_id":"drc_inv","kind":"drc"}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"job_id":"drc_inv","kind":"drc","status":"done","process_alive":false,
 "run_dir":"/home/user/.virtuoso-bridge/<user>/calibre/drc_inv","log_tail":"TOTAL Results: 0","artifacts":["DRC.rep"]}}
```

## 4. `calibre.read_results` — 读结论

**功能**：把报告解析成结构化结论（违规数、摘要等）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `job_id` 或 `run_dir` | str | **至少一个** | — | 定位任务 |
| `kind` | str | — | 自动 | `drc` / `lvs` / `pex` |
| `limit` | int | — | `20` | 最多返回多少条问题（1–500） |
| `log_lines` | int | — | `40` | 附带日志行数（0–500） |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.summary` | dict | 结论摘要（违规数/结果等） |
| `value.report` | dict | 报告要点（按 kind 分组） |
| `value.report_used` | str | 实际解析的报告文件 |
| `value.log_tail` / `value.log_counters` | str/dict | 日志尾部与计数 |
| `value.artifacts` | list | 产物清单 |

**示例**

```json
// 输入
{"operation":"calibre.read_results","token":"TOKEN","job_id":"drc_inv","kind":"drc","limit":20}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"kind":"drc","run_dir":"/home/user/.virtuoso-bridge/<user>/calibre/drc_inv",
 "summary":{"total_results":0,"errors":0},"report":{"DRC.rep":{"path":"DRC.rep"}},"report_used":"DRC.rep","log_tail":"TOTAL Results: 0"}}
```

## 5. `calibre.export` — 导出报告

**功能**：把报告/结果库/日志拉回本机。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `job_id` 或 `run_dir` | str | **至少一个** | — | 定位任务 |
| `kind` | str | — | 自动 | `drc` / `lvs` / `pex` |
| `items` | list[str] | — | `["summary"]` | `summary` / `results_db` / `netlist` / `log`，或 `all_small` |
| `local_dir` | str | — | 无 | 本机落点目录 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.local_dir` | str | 本机目录 |
| `value.downloaded` | list | 每个文件的下载明细（远程/本地路径、字节数、失败原因） |

**示例**

```json
// 输入
{"operation":"calibre.export","token":"TOKEN","job_id":"drc_inv","kind":"drc","items":["summary","log"],"local_dir":"C:/work/drc"}
// 输出（data.value 内容）
{"ok":true,"error":null,"value":{"local_dir":"C:/work/drc",
 "downloaded":[{"item":"summary","remote":"DRC.rep","local":"C:/work/drc/DRC.rep","bytes":1024,"ok":true}]}}
```

## 6. `calibre.pex` — 本版不提供

**本版不提供**：调用会立即返回 `pex_unsupported`，不要用于交付或签核。

## 7. 注意事项

- 默认后台跑；提交后不要重复提交同一个 job，用 `status` 等。
- 输入路径都是目标机器上的路径；本机文件先上传。
- 用 `deck` 时，deck 引用的文件必须都能在目标机器上解析；用 `runset` 时其内部路径同理。
- `params` 的值必须单行；`job_id` 建议命名 `<类型>_<cell>_<时间>`。
