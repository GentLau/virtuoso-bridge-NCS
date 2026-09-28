# 上层业务包：spectre

> 版本：Draft v3
> 日期：2026-09-21
> 状态：Draft（按 schematic/maestro 的领域操作组织）
> Supersedes：Draft v1–v2（v2 的 PSF 低层操作平铺未被采纳；v3 收敛为 5 个领域操作）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 总述

spectre 包覆盖独立 Spectre 的**环境检查、仿真执行、结果读取、指标计算、结果导出**。

组织方式参考 schematic/maestro：

- 对外操作按业务动作划分，不按 PSF 文件类型划分；**不暴露 `parse_psf` / `aggregate` / `parse_sweep` / `result_io` 这类低层入口**。
- `run` 用一个 `tasks[]` 表达一个或多个仿真，和 `schematic.write.commands[]`、`maestro.write.commands[]` 同一形态；单个仿真也写成单元素列表。
- `read_results` 自动识别单文件、raw 目录、参数扫描三种结果形态；响应回写识别到的 `kind`，不在请求层暴露 PSF 文件布局。
- `measure` 只做纯 Python 指标计算；`export` 只做 CSV/JSON 落盘；两者都不接触 PSF 内部结构。
- **不区分本地/远程**：包只接受 `Middle`，每次调用原样透传 `token`；主机、跳板、role 根由中层路由决定。多 server/profile 用不同 token 表达。
- **同步、无状态**：每次请求新建包实例；不保存任务表、Future、缓存。长仿真由 `timeout` 控制，本版不引入异步任务池。
- **不读取环境**：不 import `transport.*`/`subprocess`/`socket`，不读 `.env`/`VB_*`；Spectre 路径来自 `query().roles["spectre"].bin` 或请求显式 `spectre_bin`，否则使用 `spectre`。
- **只支持 PSF ASCII**：固定 `-format psfascii`；`psfbin` 不在本版。
- **不做 `-param` 注入**：Spectre `-param X=Y` 在历史版本不可靠；扫参由调用方生成多个 netlist 后交给 `run.tasks[]`。

## 2. 操作总表

| 类别 | 操作名 | 说明 | 接口 |
|---|---|---|---|
| 环境 | `spectre.check_license` | 查 Spectre 二进制/版本/license | Sp+C |
| 仿真 | `spectre.run` | 执行一个或多个独立仿真任务；`tasks[]` | U+Sp+D |
| 结果 | `spectre.read_results` | 读/解析 PSF ASCII；自动识别 single/raw/sweep | D |
| 结果 | `spectre.measure` | 在已解析数据上算 delay/bandwidth/noise 等 | — |
| 结果 | `spectre.export` | 已解析结果导出 CSV/JSON | — |

> `measure`/`export` 只读写调用方数据，不改变业务服务器状态。
> 接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

### 2.1 典型调用链

```text
run(tasks=[{job: "tb1", netlist: "tb.scs", include_files: ["model.va"], mode: "ax"}])
  → runs[0].data
  → measure(data=runs[0].data, metrics=[{type:"delay", ...}])
  → export(format="csv", data=runs[0].data, output_path="tb1.csv")

# 或解析 role 侧已有的 Spectre/Maestro 结果目录：
read_results(source="spectre/tb1/tb.raw", analysis="all")
```

## 3. 公共契约

### 3.1 Request / Result

- 每个 Request 必须有 `token: str`，可选 `timeout`；结构校验失败抛 `ValueError`/`TypeError`。
- 每个操作返回统一 `Result`：`ok: bool`、`steps: list[dict]`、`error: str | None`、`value: Any`。
- `steps` 每项为 `{"name": str, "ok": bool, "detail": <中层结果或摘要>}`；失败保留已执行步骤。
- 业务失败写 `ok=false` + `error`；只有结构错误或未预期异常才抛出。

### 3.2 路径与 job

- 路径来源由中层接口参数决定，不引入本地/远程模式：
  - **调用方文件**：`upload_file(local_path, ...)` / `download_file(..., local_path)` 使用的路径；
  - **role 路径**：`upload_file(..., remote_path)` / `download_file(remote_path, ...)` / `run_command` / `run_spectre_command` 使用的路径；绝对路径直通，相对路径按对应 role 根解析。
- `run` 的 `job` 必须是安全名：`[A-Za-z0-9][A-Za-z0-9._-]*`，不得含 `/`、`\`、`..`。
- 包不生成 API 事后不可重建的随机路径；同一 `job` 必须能确定地定位同一组运行目录。

### 3.3 run 的角色前提

- `run` 的运行目录统一建在 `spectre.root` 下：`<spectre_root>/spectre/<job>/`。
- U/D 使用该目录的绝对路径；中层分别把它投送到 `file` role 与 `spectre` role。因此要求该绝对路径在 `file` role 和 `spectre` 主机上同时可见（共享文件系统/等价挂载），否则在 staging 校验阶段直接结构化失败，不尝试跨 role 搬运。
- `read_results` 同样用绝对路径从 `file` role 下载；同一可见性前提适用于 `spectre` 产生的 raw 结果。
- 当前 `vb-vblog` 注册表中的 file/spectre 已满足同 host、同 root；split-role 拓扑由调用方用 `basic.*` 自行编排。

## 4. `spectre.check_license`

### 4.1 Request

`token`、`spectre_bin?: str`、`timeout?: int`。

### 4.2 链路

1. `query` 取 spectre root/bin；确定 bin。
2. Sp 执行 `<bin> -V`；在 stdout/stderr 中找 `@(#)$CDS:` 行作为 version。
3. best-effort 查 license：先 C 执行 `lmstat -a`；若命令不可用/失败，再用 Sp 执行 `lmstat -a`。
4. 解析 `Users of` 行、`Error getting status` 等。

### 4.3 结果

`value = {bin, version, version_raw, lmstat_interface, lmstat_raw, lmstat_error, licenses, errors, warnings}`。

- `ok=true` 当且仅当能确认 Spectre 二进制/版本（沿用旧实现：找到二进制即 ok）。
- `lmstat` 不可用、license server 不响应或没有活动 license 不使操作失败；写 warning/`license_error`。
- 版本命令失败 → `ok=false`，保留原始 stdout/stderr。

## 5. `spectre.run`

### 5.1 Request

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `token` | str | — | 必填 |
| `tasks` | list[Task] | — | 一个或多个仿真任务；单仿真也写单元素列表 |
| `max_workers` | int | 4 | 上层并发上限，≥1 |
| `mode` | str | `"spectre"` | 批次默认 mode；task 可覆盖 |
| `spectre_args` | list[str] | `[]` | 批次默认额外 Spectre CLI flag |
| `spectre_bin` | str \| None | `None` | 覆盖二进制/命令前缀；缺省用 query bin，再退化为 `spectre` |
| `parse` | str | `"auto"` | `auto`=下载后自动解析；`none`=只下载不解析 |
| `download` | bool | `True` | 是否把 raw/log 下载到调用方 |
| `output_root` | str \| None | `None` | 调用方输出根；各 task 用 `<output_root>/<job>`；缺省 `artifact_dir("spectre", job)` |
| `keep_run_dir` | bool | `False` | 是否保留 role 侧 run_dir |
| `timeout` | int \| None | `None` | 单次中层调用 deadline |

Task 字段：

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `job` | str | — | 安全名；决定 role 侧与调用方侧运行目录；批次内唯一 |
| `netlist` | str | — | 调用方 netlist 文件；U 上传到 run_dir |
| `include_files` | list[str] | `[]` | 调用方 include 文件；按 basename 上传到 run_dir |
| `mode` | str \| None | `None` | 为 None 时继承批次默认 |
| `spectre_args` | list[str] \| None | `None` | 为 None 时继承批次默认；提供时覆盖 |

校验：

- `tasks` 非空；job 唯一且为安全名；`max_workers ≥ 1`。
- `parse="auto"` 时 `download` 必须为 true；`parse="none"` 时必须 `keep_run_dir=true`，否则后续无法再用 `read_results` 定位 role 侧结果。
- `mode` 只接受 `spectre/aps/x/cx/ax/mx/lx/vx`；输出格式固定 `psfascii`。

`run` 是阻塞操作：返回时所有 task 都已结束，需要解析的已解析完成（或已失败）。单任务等价旧 `run_simulation`；多任务 + `max_workers` 等价旧 `run_parallel`。

### 5.2 执行链路（每个 task）

1. `query` 取 `spectre` root 与 `spectre.bin`。
2. 校验 `job`；确定 `run_dir = <spectre_root>/spectre/<job>/`；若已存在非空则业务失败，避免覆盖。
3. 上传 netlist 为 `<run_dir>/<netlist basename>`；上传 include 文件到同一目录。netlist 与 include 的 basename 必须唯一、不得冲突。
4. 构造命令；命令以 `cd <run_dir> && ...` 开头，因为 `run_spectre_command` 是一次性、无持久 cwd 的命令。
5. `run_spectre_command` 执行。
6. `download=true` 时，用 D 递归下载 `<run_dir>/<stem>.raw/` 到 `output_root/<job>`；`spectre.out`、`spectre.fc`、`spectre.ic` 逐个 best-effort 下载。
7. `parse=auto` 且下载成功时，用 §9 的内部解析器解析：
   - 识别到 sweep 布局 → sweep 结果；
   - 否则 → raw 目录合并结果（只有一个分析文件时也归为 raw 单分析结果）。
8. `keep_run_dir=false` 时，在下载和解析完成后 best-effort 删除 `run_dir`；清理失败记 warning，不改变业务结果。

批次语义：

- 包内用受 `max_workers` 限制的并发执行所有 task；所有 task 都等待结束，任一失败不取消其余 task。
- 结果按 `tasks` 顺序返回。
- 中层的 token/channel/thread 预算仍可能拒绝某次调用；被拒绝的 task 记失败，不自动重试。
- 增量提交由调用方分多次 `run` 实现，不保留旧 `parallel_pool`/Future。

### 5.3 命令构造

- 二进制：`spectre_bin` > `query.roles["spectre"].bin` > `"spectre"`。
- 默认参数（已存在则不重复）：`-64`、`+escchars`、`+log <run_dir>/spectre.out`、`-format psfascii`、`-raw <run_dir>/<stem>.raw`、`+lqtimeout 900`、`-maxw 5`、`-maxn 5`、`+logstatus`。
- 参数顺序：task 的 `spectre_args` 后接 mode 映射参数。
- netlist 以 basename 传给 Spectre（cwd=run_dir）；include 文件也以 basename 被 netlist 引用。
- 不提供 `-param X=Y` 注入；需要扫参时由调用方生成不同 netlist，放入不同 task。

| mode | 参数 |
|---|---|
| `spectre` | 无 |
| `aps` | `+aps` |
| `x` | `+x` |
| `cx` | `+preset=cx +mt` |
| `ax` | `+preset=ax +mt` |
| `mx` | `+preset=mx +mt` |
| `lx` | `+preset=lx +mt` |
| `vx` | `+preset=vx +mt` |

### 5.4 结果与状态

`value`：

```text
{
  "runs": [
    {
      "job": str,
      "status": "success" | "partial" | "failure" | "error",
      "command": str,
      "run_dir": str,          # spectre root 下绝对路径（file/spectre 均可见）
      "netlist_path": str,     # run_dir 下 netlist 绝对路径
      "output_dir": str | None,
      "log_path": str | None,
      "returncode": int | None,
      "transport_kind": str | None,
      "result_kind": "raw" | "sweep" | None,
      "layout": str | None,
      "data": dict,            # raw 数据
      "points": dict,          # sweep 数据
      "analyses": list[str],
      "output_files": list[str],
      "errors": list[str],
      "warnings": list[str],
      "duration": float
    }
  ],
  "succeeded": int,
  "failed": int
}
```

- 整体 `ok=true` 仅当 `failed=0` 且所有 run 的 `status="success"`。
- 单 run `ok=true` 仅当：命令 rc=0、日志无终止失败标记、raw 下载成功、`parse != "none"` 时解析成功。
- rc!=0/终止失败但 raw 已存在：`status="partial"`，`ok=false`，保留 raw/log/data 供诊断。
- rc!=0 且 raw 不存在：`status="failure"`，`ok=false`。
- raw 已下载但解析失败：`status="partial"`，`ok=false`，保留解析错误和已下载文件。
- 传输/上传/下载失败：`status="error"`，`ok=false`。
- 终止失败标记至少包括：`error reading`、`read-in failed`、license error、明确 convergence failure、`spectre terminated prematurely due to fatal error`、`ERROR (`、segmentation/core dump。

## 6. `spectre.read_results`

### 6.1 Request

| 字段 | 类型 | 默认 | 说明 |
|---|---|---|---|
| `token` | str | — | 必填 |
| `source` | str | — | role 文件或目录路径；相对 `file` role 根，绝对路径直通 |
| `analysis` | str | `"all"` | `raw` 时的分析选择：`all`/`tran`/`dc`/`ac`/`info` |
| `output_dir` | str \| None | `None` | 调用方下载目录；缺省 `artifact_dir("spectre", "results", <source basename>)` |
| `timeout` | int \| None | `None` | 单次中层调用 deadline |

### 6.2 自动识别

| source | 自动判定 | 行为 |
|---|---|---|
| 单个 PSF ASCII 文件 | `single` | D 下载 → 解析 HEADER/TYPE/SWEEP/TRACE/VALUE |
| 目录，含合法 classic/flat sweep 布局 | `sweep` | D 递归下载 → 建点索引 |
| 其他目录 | `raw` | D 递归下载 → 按 `analysis` 合并 tran/dc/ac/info |

结果规则：

- `raw`/`sweep` 允许 `source` 是 run_dir；解析器自动下钻到 `<stem>.raw`、`psf/` 等嵌套结果目录（沿用旧 `_spectre_psf_scan_root` 语义）。
- `single` 文件不存在/为空/无 VALUE → `ok=false`。
- `raw` 指定分析无对应文件 → `ok=false`；`analysis="all"` 按旧前缀规则合并。
- `sweep` 未识别出 classic/flat 布局 → `ok=false`。
- points 键固定 1-based：classic 目录的 `N` 保持 `N`；flat 文件名的 0-based `idx` 归一化为 `idx+1`。
- 支持 PSF ASCII 的 `HEADER/TYPE/SWEEP/TRACE/VALUE/END`；具体解析规则见 §9。

调用方控制方式：要强制 `single`，`source` 直接给具体 PSF 文件；要强制 `raw`，给具体 point 子目录或 raw 目录；不设 `kind` 请求参数。

### 6.3 Result

```text
{
  "kind": "single" | "raw" | "sweep",
  "source": str,
  "output_dir": str,
  "analysis": str | None,
  "layout": str | None,
  "point_count": int,
  "header": dict | None,
  "data": dict,
  "points": dict,
  "analyses": list[str],
  "signals": list[str],
  "files": list[str]
}
```

`header`/`data` 仅 `single` 使用，`points`/`layout`/`point_count` 仅 `sweep` 使用，`analyses` 仅 `raw` 使用；其余字段按形态给空值。

## 7. `spectre.measure`

Request：`token`、`data: dict | None`、`source_path: str | None`、`metrics: list[dict]`、`timeout?`。

- `data` 与 `source_path` 二选一；`source_path` 是调用方 JSON 文件（不是 role 路径）。
- 纯 Python，不调用中层；token 仅为统一契约保留。
- `data` 每项为 `signal -> list[float]`；AC 复数信号按 `{"re": [...], "im": [...]}` 表示。
- 首批 metric：

| type | 必填 | 可选 | 返回 |
|---|---|---|---|
| `threshold_crossing` | `signal, threshold` | `direction=rise`, `edge=1`, `start`, `stop` | time |
| `delay` | `from_signal, to_signal, threshold` | `direction=rise`, `start`, `stop` | Δtime |
| `min`/`max`/`mean`/`rms` | `signal` | `start`, `stop` | scalar |
| `ac_magnitude` | `signal, frequency` | `scale=db/linear` | magnitude |
| `bandwidth` | `signal` | `drop_db=3`, `reference=dc/max` | Hz |
| `noise_integral` | `signal` | `start`, `stop` | integral |

- `noise_integral` 需要数据中含频率轴（默认 `freq`）；`ac_magnitude`/`bandwidth` 只适用于 AC 复数数据。
- 每个 metric 独立求值；单个失败不终止其它 metric；整体 `ok` 仅当全部成功。
- `value = {metrics: [{type, ok, value, unit, detail}], source}`。

## 8. `spectre.export`

Request：`token`、`format`（`csv|json`）、`data` 或 `source_path`、`output_path`、`columns?: list[str]`、`precision?: int`、`timeout?`。

- 纯 Python；`output_path` 必填，避免随机不可重建路径。
- CSV：按 columns（缺省取 data 中 list 值的顺序，`time`/`freq`/`sweep_var` 优先）写出矩形表；复数按 `<signal>.re`/`<signal>.im` 展开；缺失值留空。
- JSON：写 `{"format":"json","metadata":...,"data":...}`；复数按 `{re: [...], im: [...]}` 输出。
- `value = {output_path, format, columns, rows, bytes}`。

## 9. 内部中间节点（不对外）

| 节点 | 作用 |
|---|---|
| run 目录/命令构造 | job 校验、run_dir、upload、`-64/+escchars/+log/-raw/+logstatus`、mode 映射 |
| 结果分类器 | rc、fatal marker、收敛失败、license 失败、partial/failure/error |
| PSF ASCII 解析 | HEADER/TYPE/SWEEP/TRACE/VALUE/END；delta 压缩；AC 复数；STRUCT OP 展平 |
| raw 目录分析发现 | tran/dc/ac/info 文件候选与合并 |
| sweep 布局归一化 | classic `<raw>/sw*.sweep*/N/...` 与 X/LX flat `<raw>/sw*-NNN_*` |
| CSV/JSON 写出 | 矩形表、复数 re/im、列顺序、精度 |

PSF 解析约定：

- swept 数据支持 delta 压缩：后续 step 缺省信号沿用前值；首个 step 未出现信号**内部**用缺失哨兵（实现取 `None`；**不得静默填 0**），
  **对外 `value.data` 一律转成 `null`/省略**（保持 JSON-safe）。边界唯一出口是 `psf_external()`：
  缺失哨兵与任何非有限值（`NaN`/`±Inf`）都在那里收敛成 `null`，其余路径不得自行定义对外表示。
- AC 复数相量不得被破坏；对外 `value.data` 必须 JSON-safe：复数向量用 `{"re": [...], "im": [...]}`，单值用 `{"re": ..., "im": ...}`。
- 非 swept 的 STRUCT OP 展平为 `"instance:member"`，例如 `"M0:gm"`。
- `single` 可解析任意 swept/non-swept PSF ASCII；`raw` 自动识别的分析限于 tran/dc/ac/info。
- 本版不做 PSF binary、流式解析、超大文件分块。

## 10. 旧功能覆盖映射

| 旧实现 | 新操作/说明 |
|---|---|
| `SpectreSimulator.run_simulation` | `run(tasks=[<一个 task>])`；等价单仿真 |
| `SpectreSimulator.run_parallel` | `run(tasks=[...], max_workers=N)` |
| `parallel_pool` 增量 Future | 不在本版；分多次 `run` 实现 |
| `SpectreSimulator.check_license` | `check_license` |
| `parse_spectre_psf_ascii` | `read_results(source=<单个 PSF 文件>)` |
| `parse_psf_ascii_directory` | `read_results(source=<raw 目录>)` |
| `parse_sweep_psf_directory` | `read_results(source=<sweep 目录>)`（自动识别 sweep） |
| `psf.py` 的 scalar/vector/frequency_hz | 内部解析/度量工具，不单独暴露业务操作 |
| examples 传播延迟计算 | `measure(metrics=[{type:"delay",...}])` |
| examples `_result_io.py` | `export(format="csv")` / `export(format="json")` |
| `spectre_mode_args` | `run.mode` 映射表 |
| `include_files` / `spectre_args` | `run.tasks[].include_files` / `run.spectre_args` |
| `output_format="psfascii"` | 固定 `psfascii` |
| `work_dir` | `run.output_root` |
| `keep_remote_files` | `run.keep_run_dir` |
| `SpectreSimulator.from_env` / `local` / `profile` | 不在包内；由 token 路由 + `query` 决定 target role |

## 11. 不在本版

- PSF binary 解析。
- `-param`/`parameters` 注入；参数化由调用方生成 netlist。
- 服务端异步任务表、job status/cancel、增量 Future pool。
- role 侧已存在 netlist 的直接执行；`run` 统一从调用方上传，如需直跑 role 文件，由调用方用 `basic.spectre.run` 自行编排。
- 流式/超大 PSF 解析。
- 跨 role 文件可见性搬运；由调用方拓扑保证。
- `.env`、`VB_CADENCE_CSHRC`、cshrc 解析；环境准备由注册/中层负责。

## 12. 待真机验证

1. `lmstat -a` 在 command/spectre role 的可用性与 license 解析（已知：Spectre 24.1 `spectre -V` 可用；裸 `lmstat` 有 loader 坑，SPECTRE241 的 `lmstat` 可能报 license server down，而 Spectre 自身仍可取得 `Virtuoso_Spectre` license）。
2. `+log`/`+logstatus` 在 psfascii 模式下的日志位置与 fatal marker。
3. classic/flat sweep 输出在不同 Spectre version 的文件命名。
4. rc!=0 但 raw 已生成时的 partial 判定。
5. `spectre.root` 在 file role / spectre 主机不可见或绝对路径不一致时的失败文案。
6. 大 netlist/include 上传的 basename 冲突与相对 include 解析。

## 13. 决策记录（2026-09-21）

| # | 决策 |
|---|---|
| 1 | 按 schematic/maestro 的领域操作组织：对外收敛为 `check_license`/`run`/`read_results`/`measure`/`export` 五个操作。 |
| 2 | `run` 用 `tasks[]` 统一单仿真与固定批次；不单独暴露 `run_batch`。 |
| 3 | `read_results` 自动识别单文件、raw 目录、参数扫描；请求层不暴露 `kind`，只在响应中回写识别结果。 |
| 4 | `measure` 与 `export` 分别纯 Python 计算/落盘，不接触 PSF 解析内部。 |
| 5 | 不引入本地/远程模式分支；全部操作只依赖 token + 五业务接口 + `query`；多 server/profile 用不同 token。 |
| 6 | `run` 的文件布局统一建在 `spectre.root` 下；U/D 用绝对路径跨 role 访问，要求该 root 在 file role 与 spectre 主机均可见。 |
| 7 | 只支持 PSF ASCII；复数在对外 `value.data` 统一为 `{re, im}` JSON-safe 表示。 |
| 8 | 不提供 `-param` 注入；参数化由调用方生成多个 netlist。 |
