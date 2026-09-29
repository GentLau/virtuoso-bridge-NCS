# calibre —— DRC / LVS 与 CDL 导出（PEX 本版不提供）

在目标机器上跑 Calibre 验证，默认**后台执行**：先拿 `job_id`，再轮询状态、读结论、导出报告。
另外提供 `export_cdl`：从原理图现产 LVS 源网表。`calibre.pex` 本版不提供，
调用会直接返回 `ok=false` + `value.reason=pex_unsupported`。

> **当前状态（请先读）**
>
> - `calibre.drc`、`calibre.lvs`、`calibre.export_cdl` 已真机验证可用；
> - **`calibre.pex` 本版不提供（调试条件受限）；操作保留，但调用不会执行远程动作**；
> - 该包的开发处于暂缓状态，恢复方向见仓库内的调研文档。

## 1. `calibre.check_env` — 查环境

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `calibre_bin` | str | — | 自动探测 | 指定 calibre 可执行文件 |
| `deck` | str | — | 无 | 顺带检查某个 rule deck 是否存在 |

先跑这个，确认工具与许可没问题，再提交任务。

## 2. `calibre.drc` / `calibre.lvs` — 提交任务

两者共用一套参数；差别在"需要哪些输入"，而这一点**由 deck 里是否出现占位符决定**：
（`calibre.pex` 本版不提供；它的 `RunRequest` 仍需 `deck` 或 `runset` 通过结构校验，
随后直接返回 `pex_unsupported`，不会执行任务。）

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `deck` | str | 与 `runset` 二选一 | — | rule deck 路径；deck 里出现 `$gds`/`$top` 一类占位符时，对应参数必须给 |
| `runset` | str | 与 `deck` 二选一 | — | 直接用 GUI runset 生成的 control file（自包含时不必再给 deck/gds/top） |
| `gds` | str | 见上 | 无 | 版图 GDS 路径（目标机器上） |
| `top` | str | 见上 | 无 | 顶层 cell 名 |
| `cdl` | str | 见上 | 无 | 网表（LVS/PEX；deck 引用 `lvs_top.cdl` 时必须给） |
| `lvs_run_dir` | str | — | 无 | PEX 复用 LVS 结果时给 LVS 运行目录 |
| `job_id` | str | — | 自动生成 | 任务名，后续查状态/结果的主键，**建议自己起名** |
| `run_dir` | str | — | 自动 | 运行目录 |
| `calibre_bin` | str | — | 自动 | 可执行文件 |
| `turbo` | int | — | `4` | 并行度，取值 1–64 |
| `hier` | bool | — | `true` | 是否层次化 |
| `fmt` | str | — | `none` | 输出格式：`none` / `spice` / `simple` |
| `params` | dict[str,str] | — | 无 | 覆盖 deck 里的变量；**每个值必须是单行** |
| `spice_file` | str | — | 无 | 指定 SPICE 网表文件（需要时） |
| `hcell_file`, `xcell_file` | str | — | 无 | 层次化/黑盒控制文件 |
| `blocking` | bool | — | `false` | `true` 时等跑完再返回 |
| `poll_interval` | number | — | `5.0` | `blocking=true` 时的轮询间隔（秒，>0） |

```json
{"operation":"calibre.drc","token":"TOKEN","job_id":"drc_inv",
 "gds":"/home/user/work/inv.gds","top":"inv","deck":"/pdks/calibre/drc.deck","blocking":false}

{"operation":"calibre.lvs","token":"TOKEN","job_id":"lvs_inv",
 "gds":"/home/user/work/inv.gds","top":"inv","cdl":"/home/user/work/inv.cdl",
 "deck":"/pdks/calibre/lvs.deck","params":{"TOP":"inv"},"blocking":false}
```

## 3. `calibre.status` — 查进度

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `job_id` 或 `run_dir` | str | **至少给一个** | — | 定位任务 |
| `kind` | str | — | `drc` | `drc` / `lvs` / `pex` |

返回 `data.value`：任务状态、运行目录、阶段信息。**轮询用这个。**

## 4. `calibre.read_results` — 读结论

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `job_id` 或 `run_dir` | str | **至少给一个** | — | 定位任务 |
| `kind` | str | — | 自动 | `drc` / `lvs` / `pex` |
| `limit` | int | — | `20` | 最多返回多少条问题，1–500 |
| `log_lines` | int | — | `40` | 附带多少行日志，0–500 |

返回结构化结论（违规数、类别、摘要等），比翻报告文件快。

## 5. `calibre.export` — 导出报告

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `job_id` 或 `run_dir` | str | **至少给一个** | — | 定位任务 |
| `kind` | str | — | 自动 | `drc` / `lvs` / `pex` |
| `items` | list[str] | — | `["summary"]` | `summary`（报告）/ `results_db`（结果库）/ `netlist`（svdb）/ `log`（日志），或 `all_small`（= summary+results_db+log） |
| `local_dir` | str | — | 无 | 拉回本机的目录 |

## 6. `calibre.export_cdl` — 从原理图导 CDL

用 Virtuoso 官方 auCdl 链路，从原理图现产 LVS 用的源网表（source 侧）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 源原理图 |
| `view` | str | — | `schematic` | 源视图 |
| `netlist_name` | str | — | `<cell>.cdl` | 输出的 CDL 文件名（**只能是文件名**，不能带路径） |
| `run_dir` | str | — | 自动（command 根下 `calibre/cdl_<cell>`） | 运行目录 |
| `cds_lib` | str | — | 从 CIW 推断 | `cds.lib` 路径；CIW 工作目录不可用时必须显式给 |

典型用法：`export_cdl` 产出 CDL → 把它作为 `calibre.lvs` 的 `cdl` 输入。

```json
{"operation":"calibre.export_cdl","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic"}
```

## 7. 注意事项

- 默认后台跑；提交后**不要重复提交同一个 job**，用 `status` 等。
- 输入路径都是目标机器上的路径；本机文件先 `basic.file.upload`。
- 用 `deck` 时，deck 里引用到的文件（GDS/网表/规则）必须都能在目标机器上解析；
  用 `runset` 时，runset 里写死的路径同理。
- `params` 的值是单行字符串，含换行会被拒绝。
- `job_id` 是后续所有操作的主键，命名建议：`<类型>_<cell>_<时间>`。
