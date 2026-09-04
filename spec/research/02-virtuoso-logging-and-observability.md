# Virtuoso 日志管理与可观测性调研

> 调研日期：2026-09-04  
> 目标：回答“Virtuoso 当前如何管理 log，获取 log 的最好方式是什么”。  
> 核心判断：**不存在一个覆盖所有问题的单一日志文件，必须按 producer、粒度和运行关联键组合采集。**

## 1. 先分清“日志”与“结果”

| 对象 | 是否日志 | 主要回答的问题 |
|---|---|---|
| `CDS.log` / `virtuoso -log FILE` | 是，Virtuoso 进程级会话日志 | Virtuoso 启动、CIW 命令、GUI/DB 错误、崩溃前最后状态 |
| `<history>.log` | 是，Maestro history 摘要 | 该 history 的设计点、参数、best point、完成/错误摘要 |
| `<history>.msg.db` | 是，结构化消息事件库 | 哪个 tool/test/point 在何时发出什么级别的消息，源文件定位在哪里 |
| `virtuoso_ade_debug.log` | 是，ADE 编排/point evaluator 日志 | NewHistory、netlisting、submit、point/history finish、调度上下文 |
| `JobN.log` / `ServiceN.log` / `LoggingServiceN.log` | 是，作业/服务进程日志 | Simulation Monitor、netlist service、expression evaluator 的过程与退出状态 |
| `psf/spectre.out` | 是，Spectre 原始输出 | netlist read-in、license、收敛、warning/error、命令行、最终 fatal 状态 |
| `psf/logFile` | 是，模拟器/仿真器辅助日志 | 某些 flow 的模拟器输出或重定向内容；是否存在取决于 flow |
| `netlist/runSimulation` | 不是日志，但很关键 | 实际启动 Spectre 的命令和参数 |
| `maestro.sdb` / `active.state` | 不是日志 | 仿真 setup 与当前 test 状态 |
| `<history>.rdb` | 不是日志 | scalar/waveform result metadata 与结果值的持久化 DB |
| `exprOutputs.log` / `variables_file` | 结果/表达式辅助工件 | expression evaluator 输入输出与运行变量 |
| bridge daemon stderr / `RB.log` | 是，桥接层日志 | daemon banner、请求统计、异常、端口/host 身份 |

**不要把 result database、waveform、log 混成一个“结果文件”。** 调试某次失败通常要同时看摘要、结构化事件、模拟器输出和实际启动命令。

## 2. 现场观察：一个 history 的四种粒度

2026-09-04 通过现场已有 Virtuoso/bridge 只读检查了一个 IC6.1.8 Maestro 运行树（以下将用户目录抽象为 `<project>`、`<simulation-root>`）：

```text
<project>/<LIB>/<TB>/maestro/
  maestro.sdb                    约 83 KB，XML
  active.state                   约 303 KB，XML
  results/maestro/
    Interactive.21.log           数百字节，摘要
    Interactive.21.msg.db        49 KB，SQLite
    Interactive.21.rdb           约 536 KB，SQLite

<simulation-root>/<LIB>/<TB>/maestro/results/maestro/Interactive.21/
  1/<TEST>/netlist/input.scs
  1/<TEST>/netlist/runSimulation
  1/<TEST>/psf/spectre.out
  .../sharedData/...
```

该现场 history 的特征：

- `<history>.log` 只给出“Starting…、parameters、Number of points、simulation errors、completed”；
- `.msg.db` 的 `logs` 表含 `level/tool/timestamp/message/attrs`，能直接定位 `spectre` 的 `MMSPF-10013`；
- `location` 表把同一点关联到 ADE GUI、Simulation、spectre、Expression 各自的 log 文件和行号；
- `spectre.out` 末尾写明 `spectre completes with 2 errors...` 和 `spectre terminated prematurely due to fatal error`，这才是 simulator 根因层；
- 项目结果目录与 `<simulation-root>` 不一定相同，说明不能只拼 `ddGetObj(lib)~>readPath` 下的一个固定路径。

因此，**摘要 log 适合快速展示，`msg.db + spectre.out + Job*.log` 才适合自动诊断和审计**。

## 3. “最好方式”按问题选择

| 需要回答的问题 | 首选读取顺序 | 说明 |
|---|---|---|
| 仿真是否成功、哪一点失败 | `msg.db` → `psf/spectre.out` → `JobN.log` → `<history>.log` | 结构化状态与根因互补；不能只看进程 exit code |
| 失败的具体 Spectre 原因 | 同一点的 `psf/spectre.out`，再看 `netlist/input.scs` 与 `runSimulation` | 包含 command line、环境、license、error/warning/fatal |
| ADE 如何调度、何时 netlist/submit/finish | `virtuoso_ade_debug.log` + `JobN.log` | 用 history/test/point/jobid 关联 |
| 所有 sweep/corner 点的 scalar output | `maeExportOutputView(?view "Detail")` 导出的 CSV | 不要把 `<history>.log` 当全点结果；不要只调用当前 point 的 `maeGetOutputValue` |
| 一个 waveform | OCEAN `openResults`/`selectResults`/`ocnPrint`，或明确 history 的 PSF | waveform 不应从文本 log 反推 |
| setup 发生了什么 | `maestro.sdb` + `active.state` + raw SKILL probes | XML 是磁盘状态，SKILL probe 是运行时解释状态；两者不一定完全相同 |
| Virtuoso/CIW 崩溃或启动问题 | 启动时指定的 `CDS.log`，以及 panic log | `CDS.log` 应使用每进程唯一名字 |
| bridge daemon 无响应 | client transport log + daemon stderr/banner/stats + CIW `CDS.log` | 区分 tunnel、daemon、CIW/modal dialog 三个层次 |
| 实时进度 | callback/事件文件或 `msg.db` 增量读取 + tail `JobN.log`/`spectre.out` | 不要用阻塞的 SKILL call 作为唯一心跳 |

### 3.1 结论

对本项目建议定义一个 `RunEvidence`：

```text
RunEvidence(
  history, test, point, corner,
  summary_log,
  message_db,
  ade_debug_log,
  job_logs,
  simulator_logs,
  command_files,
  setup_snapshot,
  normalized_events,
)
```

它返回原始文件引用和解析后的诊断，但**永远保留 raw**。

## 4. Virtuoso 进程级 CDS.log

Cadence 本地 `wincfg/gettingStarted.html` 记录：

```bash
virtuoso -log <fileName> &
```

会把本来发往终端的输出同时写入指定日志，Virtuoso 意外退出后仍可读取；默认会话记录通常是 `CDS.log`。同一文档还说明：

- `-logtime`：每条日志加绝对时间，默认 UTC；
- `-logtimerel`：记录相对上一条的间隔；
- `CDS_LOG_TIMESTAMPS=True`：启用时间戳；
- `CDS_USE_LOCAL_TIMESTAMP=True`：需要时显示本地时区；
- 日志带时间戳有助于跨 host 对齐，但旧版本 replay 兼容性需单独验证。

Cadence Application Infrastructure 的 `caiuser/chap11.html` 还给出：

```csh
setenv CDS_LOG_VERSION pid        # logFile.<processId>
setenv CDS_LOG_VERSION sequential # logFile.N
setenv CDS_LOG_PATH dir1:dir2
setenv CDS_LOG_LIMIT N
```

但要注意两个边界：

1. 这些环境变量不是所有 Cadence 应用都使用；
2. 同一页明确注明 **Virtuoso design environment 不使用 `CDS_LOG_LIMIT`**。因此不能把它当 Virtuoso 日志轮转的可靠方案，应由项目外部的 retention/rotation 负责。

### 项目建议

- 启动每个 Virtuoso 实例时显式指定唯一 log：`CDS.<profile>.<pid-or-start>.log`；
- 设 `-logtime`，服务端统一记录 UTC；展示层再换算本地时区；
- 启动 manifest 记录 `virtuoso` command、PID、host、working directory、log path、IC version；
- 不要在多个 profile 间复用同一个 `CDS.log`；
- crash/panic 文件与普通 session log 分开保留。

## 5. Maestro/ADE 的结果与消息层

### 5.1 `<history>.log`：摘要，不是全量

项目参考中已观察到其内容类似：

```text
Starting Single Run, Sweeps and Corners...
Current time: ...
Best design point: ...
Design parameters: ...
Number of points completed: ...
Number of simulation errors: ...
Interactive.N completed.
```

它适合给人快速浏览，也可作为“history 是否产生”的轻量证据；但它通常不包含所有 point 的全部消息，不能承担根因分析。

### 5.2 `*.msg.db`：最适合机器读取的 ADE 事件源

现场 SQLite schema 的核心部分为：

```sql
CREATE TABLE logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  jobid TEXT,
  point TEXT,
  test TEXT,
  level TEXT,
  tool TEXT,
  timestamp TEXT,
  message TEXT,
  attrs TEXT
);

CREATE TABLE location (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  point TEXT,
  test TEXT,
  tool TEXT,
  file TEXT,
  line TEXT,
  UNIQUE(point, test, tool)
);
```

另有 `meta`、`groupPoints`、索引等。`attrs` 是 JSON 文本，现场样例包含 history、hostname、processid、cornername、logfile、simid 等。

推荐只读 SQL：

```sql
-- 先按级别/producer 看问题分布
SELECT level, tool, COUNT(*)
FROM logs
GROUP BY level, tool
ORDER BY tool, level;

-- 取一个 point 的错误/致命事件
SELECT timestamp, level, tool, message, attrs
FROM logs
WHERE point = '1'
  AND level IN ('error', 'fatal', 'warn')
ORDER BY id;

-- 追到真实文件
SELECT point, test, tool, file, line
FROM location
ORDER BY point, test, tool;
```

> 注：不同 IC/ISR 的表结构可能增删列；生产实现应先读取 `PRAGMA table_info(logs)`，再构造 SQL，不能假设所有版本完全相同。

读取时的安全边界：

- 运行中 SQLite 可能尚未 flush 或被锁；优先在远端用 SQLite backup/一致性副本，再下载；
- 不要修改 `.msg.db`/`.rdb`；
- 把 DB 的 schema version、size、mtime、sha256 记入 manifest；
- 读取失败时仍保留“文件存在但不可读”的诊断，不要静默当作没有消息。

### 5.3 `maeGetSimulationMessages`：快速 API，不是全量审计

本机 API 文档确认：

```skill
maeGetSimulationMessages(
  ?session "..."
  ?msgType "ERROR" | "WARNING" | "INFO" | "ALL"
)
```

返回字符串，适合在 CIW/bridge 中做快速摘要或故障提示；它不是替代 `.msg.db`、`JobN.log` 或 simulator log 的全量接口。应把它作为“在线快照”并保存 raw response。

## 6. Spectre 与 per-point 工件

本机 `spectreref/chap2.html` 对命令选项的描述：

| 选项 | 行为 |
|---|---|
| `-log` | 只把 log 写标准输出，不复制到 log file |
| `+log FILE`（`+l`） | 标准输出显示，同时复制到指定 FILE |
| `=log FILE`（`=l`） | 只写指定 FILE，不显示在标准输出 |
| `-raw DIR` | 把模拟结果保存到指定 raw file/directory |
| `+logstatus` | 输出 log status（项目 runner 已使用） |

现场 `runSimulation` 显示了类似：

```text
spectre -64 input.scs +escchars +log ../psf/spectre.out \
  -format psfxl -raw ../psf +aps +mt ... +logstatus
```

因此最佳做法是：

1. 把 `input.scs`、`runSimulation`、`spectre.out` 放进同一个 point artifact；
2. 运行期间 tail `spectre.out`；
3. 每次 poll 都检查终止标记：`fatal error`、`terminated prematurely`、`ERROR (`、明确的 convergence failure、license failure 等；
4. 不因 raw 目录出现几个文件就宣布成功；
5. 结束后记录 exit status 与 log classifier 的共同结论。

项目旧实现的 `SpectreSimulator` 已有方向：显式 `+log`、`-raw`、`+logstatus`，下载 remote output，解析 PSF ASCII，并区分 `SUCCESS/PARTIAL/FAILURE`。重构时应把**原始 log 路径和 log 内容**纳入公开 `SimulationResult.metadata`，而不是只返回解析后的波形。

## 7. 实时采集算法（推荐实现）

### 7.1 运行前

```text
A. 生成 run_id（本地 UUID）
B. 记录 history/test/corner/point 预期键
C. 解析 project root 与 simulation root
D. 创建私有 staging/manifest 目录
E. 清理同名 marker，确认输入文件存在
F. 写入 start event
```

解析路径时优先使用运行时信息：

- `ddGetObj("LIB")~>readPath`：库源路径；
- `asiGetAnalogRunDir(asiGetSession("fnxSessionN"))`：模拟器 run directory；
- `axlGetCurrentHistory` + `axlGetHistoryName` / `axlGetHistoryResults`：当前 history 名与 RDB 结果位置；
- `maeGetEnvOption`/test setup：lib/cell/view/test 绑定；
- 文件系统的 `mtime`、`getDirFiles` 只作为候选发现，不能单独决定归属。

### 7.2 运行中

并行观察多个通道，不阻塞 SKILL：

```text
observer loop (deadline)
  ├─ callback/marker：是否完成
  ├─ msg.db：增量读新增 rows（或周期性一致性副本）
  ├─ Job*.log / ade_debug：增量 tail
  ├─ per-point spectre.out：增量 tail + terminal-failure scan
  ├─ process/SSH：存活、退出码、连接状态
  └─ GUI/X11：仅在疑似 modal dialog 时介入
```

每轮都做 terminal-failure scan。项目 `AGENTS.md` 已明确指出，`system()` 对会 fork 并写 log 的工具（例如 strmin、ihdl、某些 spectre flow）返回码不可靠；如果只轮询目标 artifact，会在工具两秒内失败后仍睡满十分钟。**artifact poll 与 log-tail failure poll 必须是一个不可拆开的组合。**

### 7.3 运行后

```text
A. 以 history/test/point/corner 固化最终路径
B. 获取 summary + msg.db + Job/ADE + spectre logs
C. 读取 Detail CSV / OCEAN waveform（按需求）
D. 建立 normalized events
E. 计算 hash、写 manifest、保存 command/env/version
F. 返回 status + diagnosis + artifact references
```

## 8. 统一事件格式建议

```json
{
  "run_id": "local-uuid",
  "history": "Interactive.21",
  "test": "ctle_ac_pex",
  "point": "1",
  "corner": "Nominal",
  "producer": "spectre",
  "level": "error",
  "timestamp": "2026-08-31T12:15:50.774Z",
  "message": "Unable to read the parasitic file ...",
  "source": {
    "path": ".../psf/spectre.out",
    "line": null
  },
  "attrs": {
    "jobid": "13",
    "pid": "278534"
  },
  "raw_ref": "artifacts/Interactive.21/point-1/spectre.out#sha256:..."
}
```

字段规则：

- `producer` 与 `tool` 分开：`ADE GUI`、`Simulation Monitor`、`spectre`、`Expression Evaluator` 不应被压成一个字符串；
- timestamp 统一内部 UTC，同时保留原始 timestamp；
- message 不做破坏性清洗，分类器另存 `code`/`category`；
- 原始文件只追加、不覆盖；解析器可重跑；
- 对 SKILL/命令行做敏感信息 redaction，但 raw artifact 的权限必须受控。

## 9. 进程、IPC、CIW 输出的边界

Cadence `ipcBeginProcess` 文档说明：子进程通过 stdin/stdout/stderr 与父进程通信；data/error handler 可接收流；如果给出 log file，子进程可在 message/batch 模式间切换；`ipcGetExitStatus`、`ipcIsAliveProcess`、`ipcWait` 用于状态观察。

项目桥接的实际链路是：

```text
Python TCP client
  → JSON {skill, timeout}
  → bridge daemon
  → Virtuoso stdin via ipcBeginProcess
  → evalstring(progn(...))
  → STX/NAK + payload + RS
```

现有实现的好点：

- 用 `progn` 保证多语句不被 `evalstring` 只执行第一式；
- 用 STX/NAK/RS framing，避免把任意 SKILL 文本当换行协议；
- daemon banner 包含 pid/bind/host/ip；
- stderr ring buffer 只在异常退出时刷 CIW，减少噪声。

需要补强：

- 每个 request 增加 `request_id`、client/profile、start/end、skill hash、duration；
- 默认不记录完整敏感 SKILL，记录安全摘要；debug 模式才保留受控 raw；
- 明确 daemon 单连接/并发策略，避免两个写操作交叉进入同一 CIW；
- timeout 后区分“TCP 断开、CIW 被 modal dialog 阻塞、SKILL 长任务、daemon watchdog 中断”；
- `printf` 只写 `poport`/CIW，不是可靠 RPC 返回值；多行诊断应 `sprintf` 聚合、返回结构化 list，或 `outfile`/`fprintf` 后 download。

## 10. 与当前项目文档的矛盾及统一口径

项目历史资料中出现过“Maestro OCEAN 不可用时解析 `.log` 是最可靠”的说明；较新的 `maestro-python-api.md` 已明确 `maeExportOutputView(?view "Detail")` 是全点 × 全 output 的读取路径。统一口径应为：

- **值/结果正确性**：Detail CSV、`maeGetOutputValue`（明确 history/point）或 OCEAN/PSF；
- **诊断/解释性**：`.log`、`.msg.db`、`Job*.log`、`spectre.out`；
- **缺 PSF waveform 的 fallback**：可以解析 log 里的已计算 scalar，但结果必须标记为 `source=summary_log`，不能伪装成完整 waveform/result DB。


### 11.1 每次指令自动取得 `CDS.log` 增量

若目标是让每次 `execute_skill()` 都顺手返回本次指令对应的主日志增量，推荐使用 `hiGetLogFileName()` + `hiFlushLogFile()` + request marker + `fileLength()` byte cursor。不要只做前后 `stat` 的 size diff：它无法处理缓冲、轮转、异步写入和并发。具体流程和异常语义见 [04-log-return-system-proposal.md](04-log-return-system-proposal.md#17-针对核心问题每次指令自动取得-cdslog-增量)。
## 11. 日志 API 的 MVP

> 本文的同步 SKILL 捕获与统一返回协议补充见 [04-log-return-system-proposal.md](04-log-return-system-proposal.md)。其中新增验证了 outstring/getOutstring 和 muffleWarnings/getMuffleWarnings，适合作为同步调用的低延迟捕获层。


建议先实现下列只读接口，不先做复杂 UI：

```python
class RunObserver:
    def discover(self, session, *, history=None) -> RunEvidence: ...
    def snapshot(self, evidence) -> NormalizedRunState: ...
    def tail(self, evidence, *, timeout, poll_interval=1.0): ...
    def collect(self, evidence, *, include_waveforms=False) -> ArtifactManifest: ...
    def diagnose(self, evidence) -> RunDiagnosis: ...
```

`RunDiagnosis` 至少包含：

```text
status: not_started | running | success | partial | failed | unknown
root_cause: enum + human message
counts: errors/warnings/notices/points
primary_source: path + producer + line
related_sources: [...]
confidence: high | medium | low
```

## 12. 关键参考

### 项目内

- `../../AGENTS.md`：`system()` 返回码不可靠、poll 必须同时 tail terminal failure
- `../../README.md`：snapshot 目录与架构
- `../../skills/virtuoso/references/cellview-on-disk-layout.md`：Maestro 文件树、`.log/.msg.db/.rdb`
- `../../skills/virtuoso/references/maestro-python-api.md`：Detail CSV、snapshot、run_and_wait
- `../../skills/virtuoso/references/maestro-skill-api.md`：`maeGetSimulationMessages`、`maeOpenResults`、callback
- `../../skills/virtuoso/references/simulation-flow.md`：GUI session 与非阻塞等待
- `../../skills/virtuoso/references/troubleshooting.md`：dialog、shell output、远端文件
- `../../skills/spectre/SKILL.md`：Spectre 结果契约和失败分类
- `../../src_bak/virtuoso_bridge/virtuoso/maestro/reader/snapshot.py`：实际 artifact whitelist/tar 逻辑
- `../../src_bak/virtuoso_bridge/virtuoso/maestro/reader/runs.py`：Detail CSV 读取与 waveform export
- `../../src_bak/virtuoso_bridge/virtuoso/maestro/writer.py`：callback + marker observer
- `../../src_bak/virtuoso_bridge/spectre/runner.py`：`+log/-raw/+logstatus` 与远程下载

### Cadence 本地文档

- `C:\Users\user\Desktop\doc\wincfg\gettingStarted.html`：`-log`、`-logtime`、`-logtimerel`、保存/重命名 `CDS.log`
- `C:\Users\user\Desktop\doc\caiuser\chap11.html`：`CDS_LOG_PATH`、`CDS_LOG_VERSION`、`CDS_LOG_LIMIT` 的边界
- `C:\Users\user\Desktop\doc\adexl\appEnvVars.html`：`saveDir`、结果 DB/运行日志位置、error 时显示 simulator log
- `C:\Users\user\Desktop\doc\spectreref\chap2.html`：Spectre `-log/+log/=log/-raw/+logstatus`
- `C:\Users\user\Desktop\doc\maeSKILLref\runRelated.html`、`maestroSKILL.html`：Maestro run/result/message API
- `C:\Users\user\Desktop\doc\skipcref\ipcskill_re_ipcBeginProcess.html`、`ipcskill_re_ipcReadProcess.html`、`ipcskill_re_ipcWait.html`：IPC 生命周期
- `C:\Users\user\Desktop\doc\sklangref\inputoutput_re_outfile.html`、`inputoutput_re_fprintf.html`：SKILL 文件输出

## 13. 公开交叉参考

- [Cadence Virtuosity：Virtuoso Read Mode Done Right](https://community.cadence.com/cadence_blogs_8/b/cic/posts/virtuosity-read-mode-done-right)：用于交叉理解 ADE read-only run、project/run 目录与 results database 的分工；具体路径仍以目标版本现场为准。

## 13. 证据定位（便于复核）

| 结论 | 证据 |
|---|---|
| Virtuoso `-log`、`-logtime`、`-logtimerel`、默认 `CDS.log` 与后台运行 | `C:\Users\user\Desktop\doc\wincfg\gettingStarted.html:161-193`、`:522-534`、`:602-613` |
| `CDS_LOG_PATH`、`CDS_LOG_VERSION`、`CDS_LOG_LIMIT`，以及 Virtuoso 不使用 `CDS_LOG_LIMIT` 的说明 | `C:\Users\user\Desktop\doc\caiuser\chap11.html:150-234` |
| ADE `saveDir` 对结果 DB/运行日志路径的影响 | `C:\Users\user\Desktop\doc\adexl\appEnvVars.html:10088-10098` |
| error 时显示 simulator log 的环境项 | `C:\Users\user\Desktop\doc\adexl\appEnvVars.html:9251-9292` |
| Spectre `-log/+log/=log/-raw` 语义 | `C:\Users\user\Desktop\doc\spectreref\chap2.html:177-213` |
| `maeGetSimulationMessages`、`maeOpenResults`、结果输出接口 | `C:\Users\user\Desktop\doc\maeSKILLref\runRelated.html:543-633`；本地 More Info API 查询 |
| `ipcBeginProcess` 的 stdout/stderr handler、logFile、batch/message、退出状态 | `C:\Users\user\Desktop\doc\skipcref\ipcskill_re_ipcBeginProcess.html`（函数锚点 `ipcBeginProcess`）；`ipcReadProcess.html`、`ipcWait.html` |
| Maestro 文件树与 `.log/.msg.db/.rdb` 分类 | `../../skills/virtuoso/references/cellview-on-disk-layout.md:90-155`、`:267-282` |
| Detail CSV、snapshot、run_and_wait | `../../skills/virtuoso/references/maestro-python-api.md:60-159`、`:333-388` |
| callback + marker 非阻塞观察 | `../../skills/virtuoso/references/simulation-flow.md:67-74`；`../../src_bak/virtuoso_bridge/virtuoso/maestro/writer.py:372-417`、`:491-575` |
| `system()` 返回码与 log-tail fast-fail 要求 | `../../AGENTS.md:285-290` |
| 现场 `.msg.db` schema、`spectre.out` fatal 与分裂路径 | `00-research-method-and-evidence.md`、现场只读 SSH/SQLite 输出（2026-09-04） |
