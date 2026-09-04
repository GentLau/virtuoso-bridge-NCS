# Virtuoso Bridge 日志返回体系设计建议

> 调研日期：2026-09-04  
> 文档性质：在已有底层调研基础上的补充研究与架构建议。  
> 核心结论：**不要把日志返回实现成给 `VirtuosoResult.output` 再拼一段文本；应把控制结果、诊断事件和原始工件设计成三个相互关联但独立的返回平面。**

## 1. 本文要解决的问题

如果 `virtuoso-bridge-NCS` 需要把 Virtuoso、Maestro、Spectre 以及 bridge 自身产生的日志可靠地返回给 Python、CLI、MCP 或 Agent，系统至少要同时满足：

1. 单次 SKILL 调用能拿到返回值、`printf` 输出、warning 和 error；
2. 长时间仿真能实时观察，且不阻塞 CIW；
3. 失败时能指出根因证据，而不是只返回 `timeout` 或布尔值；
4. 远程、多主机、分裂结果目录仍能正确定位日志；
5. 大日志不会撑爆 TCP、CIW 或模型上下文；
6. 旧调用者继续使用 `VirtuosoResult(status/output/errors/warnings)`；
7. 原始证据可复核，规范化事件可供机器消费。

本文只写研究结论和落地建议，不修改设计库。工作树中的大量源码删除是预先存在的变更，本次研究只新增 `spec/research` 文档和使用只读/临时探针。

## 2. 关键补充发现：SKILL 原生能力足以做同步捕获

已有调研已确认 Virtuoso 没有一个覆盖全部问题的总日志。本次继续使用本地 Cadence 文档服务和现场 IC6.1.8 会话，发现同步 SKILL 调用可以在 SKILL 侧做比当前实现更完整的捕获。

### 2.1 现场探针

| 探针 | 现场结果（2026-09-04） | 对实现的含义 |
|---|---|---|
| `hiGetLogFileName()` | `/home/Gent/CDS.log` | 从运行时发现 session log，不能硬编码 `CDS.log` |
| `hiFlushLogFile()` | `t` | 读取 log 增量前可显式 flush |
| `asiGetLogFileList(asiGetSession("fnxSession8"))` | `("logFile")` | 模拟器 log 名称可从 session 发现，实际路径仍需结合 run directory |
| `asiGetAnalogRunDir(...)` | `.../.tmpADEDir_Gent/.../netlist` | 模拟器临时目录可能不同于 project/history 目录 |
| `axlGetHistoryResults(...)` | `.../Interactive.0.rdb` | history、RDB、模拟器 run directory 是不同对象 |
| `axlGetRunStatus(...)` | 完成状态如 `(0 0)`、`(1 1)` | 可用于进度观察，但不是根因日志 |
| `outstring()` + 动态 `poport` | 可捕获 `printf`、`info`、`print`、`println` | 同步调用可以返回 stdout-like 文本 |
| `muffleWarnings(...)` + `getMuffleWarnings()` | 可捕获多个 SKILL/C-level warning | warning 不必只依赖 grep `CDS.log` |
| `errset(...)` + `errset.errset` | 得到函数、位置和错误文本列表 | error 应保留结构化 raw 信息 |
| `hiPrintToLogFile(...)` | 写入 `CDS.log`，不进入 `outstring` | session log 与 RPC stdout 必须分通道 |
| `hiStartLog()` / `hiEndLog()` | 能建立 ancillary transaction log | 适合审计/调试，不是所有子进程日志 |

探针只使用唯一前缀；临时文件已清理，没有向设计库提交写操作。现场路径和 SQLite 证据见 [`00-research-method-and-evidence.md`](00-research-method-and-evidence.md)。

### 2.2 已验证的捕获语义

本地文档确认：

- `outstring()` 打开字符串 output port，`getOutstring()` 在 port 仍打开时取回内容；
- `printf` 不带 port，写到 `poport`；`fprintf`、`print`、`println` 可以写指定 port；
- `muffleWarnings()` 会抑制包裹表达式的 warning，紧接着调用 `getMuffleWarnings()` 可以取得 warning 列表；该机制覆盖 SKILL `warn()` 以及 C-level `ilWarn*`；
- `errset()` 出错时返回 `nil`，错误上下文放在 `errset.errset`；
- `unwindProtect()` 即使表达式出错也会执行清理，可用于关闭 port、恢复全局状态；
- `hiPrintToLogFile()` 写入 `CDS.log`/secondary log 而不显示到 CIW；`hiFlushLogFile()` 刷新主、次 log。

实测组合的行为如下：

```text
printf/info/print/println  → 动态 poport 可捕获
warn/C-level warning       → muffleWarnings + getMuffleWarnings 可捕获
error/解析错误              → errset + errset.errset 可捕获
hiPrintToLogFile            → CDS.log/secondary log，不进入 outstring
ipc 子进程 stdout/stderr    → ipcBeginProcess 的 data/err handler 或 logFile
异步 Maestro/Spectre 消息   → callback、状态 API、msg.db 和运行工件
```

这比当前 bridge 只返回 `%L` 计算值的方案更适合机器调用。

### 2.3 推荐的 SKILL 侧包装顺序

下面是**已验证原语的组合示意**，不是可直接粘贴的最终代码；bridge 需要把请求体安全地注入 `progn(...)`，并用 `unwindProtect` 确保 port 被关闭：

```skill
let((p value evalResult warnings captured errorInfo)
  p = outstring()

  ; 动态绑定 poport，只捕获本次同步调用的 stdout-like 输出。
  evalResult = let((poport)
    poport = p
    muffleWarnings(
      errset(
        value = progn(
          ; <bridge injects the request body here>
        )
      )
    )
  )

  ; 必须先保存 errset.errset，再调用其它可能改写错误上下文的代码。
  errorInfo = if(evalResult nil errset.errset)
  warnings = getMuffleWarnings()
  captured = getOutstring(p)
  close(p)

  list(
    list('evalOk if(evalResult t nil))
    list('value value)
    list('stdout captured)
    list('warnings warnings)
    list('error errorInfo)
  )
)
```

实现时需注意：

1. `errset` 成功时返回形如 `(value)` 的列表；即使 `value` 是 `nil`，`evalResult` 仍然可以用来区分“执行成功且返回 nil”和“发生错误”。
2. `muffleWarnings` 会改变 warning 的显示行为。Agent/机器模式可以默认不重复打印到 CIW；交互模式应提供 `mirror_warnings_to_ciw` 选项，不能隐式改变用户体验。
3. `getMuffleWarnings()` 必须紧跟在 `muffleWarnings()` 后调用；它只能捕获该同步表达式期间的 warning，不能替代异步 run 的日志采集。
4. `getWarn()` 只能可靠取得尚未打印的最后一个 warning；要取得一批同步 warning，应使用 `muffleWarnings/getMuffleWarnings`。
5. `hiPrintToLogFile`、模拟器子进程输出、GUI/数据库内部消息不会因为动态绑定 `poport` 自动进入 `stdout` 字段；必须保留 session-log 和 artifact 通道。
6. 任意用户 SKILL 可能自己修改 `poport`、调用 `getMuffleWarnings` 或改变全局状态，因此捕获能力应标记为 `best_effort`，并在 raw evidence 中保留实际 log。

## 3. 当前 bridge 的现状与缺口

### 3.1 当前链路

```text
Python TCP client
  → JSON {skill, timeout}
  → ramic_bridge_daemon_3.py
  → Virtuoso stdin via ipcBeginProcess
  → ramic_bridge.il: evalstring(progn(...))
  → STX/NAK + %L payload + RS
  → daemon closes TCP connection
  → Python VirtuosoResult
```

证据：

- [`src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il:68-93`](../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il#L68-L93)：`RBIpcDataHandler` 使用 `errset`、`evalstring` 和 STX/NAK/RS；
- [`src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il:95-157`](../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il#L95-L157)：stderr ring buffer、banner/stat 解析；
- [`src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge_daemon_3.py:110-243`](../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge_daemon_3.py#L110-L243)：内层 frame、watchdog、外层 TCP response；
- [`src/virtuoso_bridge/virtuoso/basic/bridge.py:313-395`](../../src/virtuoso_bridge/virtuoso/basic/bridge.py#L313-L395) 和 `:1440-1496`：Python 端只把结果解析为 output/errors/warnings。

### 3.2 当前实现值得保留

- 用 `progn` 解决 `evalstring` 只执行一个顶层 form 的问题；
- STX/NAK/RS 让成功、错误和结束边界不依赖普通换行；
- banner 中保存 daemon PID、bind、host、IP，能够诊断 split-host/错误 tunnel；
- stderr ring buffer 在 daemon 非零退出时才刷 CIW，避免例行噪声；
- `maestro/writer.py` 已有 callback + marker 的非阻塞思路：SKILL 注册完成 callback，Python/SSH 轮询 marker，等待期间释放 SKILL channel；
- Spectre runner 已显式使用 `+log`、`-raw`、`+logstatus`，并有 terminal-failure 扫描方向。

### 3.3 当前实现不适合直接承载“完整日志返回”的部分

1. **没有 request ID**：同一个 CIW、同一个 `CDS.log`、多个 profile 或多个 agent 请求无法可靠关联。
2. **`VirtuosoResult.output` 只有 return value**：当前 `printf` 会写到 `poport`/CIW/log，但不会自动进入 RPC output。
3. **warning/error 粒度不一致**：`errset.errset` 被压成一个字符串；warning 主要依赖 CIW/log，无法稳定结构化。
4. **daemon 状态是全局变量**：`timeout_flag`、`watchdog_timer`、`_RB_CALLS` 等是进程级状态；当前 `listen(1)` + 同步 handler 事实上把一个 CIW 变成单通道，但协议没有显式表达这个约束。
5. **外层协议没有版本、长度、序号或续传 cursor**：每个请求依赖连接关闭表示结束，无法自然支持事件流、断线续传和大响应。
6. **只记录“请求成功/失败”**：不能区分“run accepted”“point finished”“history finished”“result DB flushed”。
7. **`CDS.log`、Maestro log、Spectre log 没有统一 artifact manifest**：调用者必须自己猜路径和时间关联。
8. **对 `system()`/fork 工具不能只看 exit code**：项目 `AGENTS.md` 已明确要求在每次 poll 同时 tail 工具 log 的 terminal failure marker，否则会把快速失败误判成长时间运行。

当前公共模型 [`src/virtuoso_bridge/models.py:12-81`](../../src/virtuoso_bridge/models.py#L12-L81) 可以作为兼容外壳，但不应继续把所有诊断塞进 `errors: list[str]` 或 `metadata: dict`。

## 4. 总体建议：三个返回平面

### 4.1 平面 A：控制/语义结果（Control Result）

回答“这次调用的语义结果是什么”：

- `status`：`success | partial | error`（保留旧枚举兼容）；
- `phase`：`accepted | running | finalizing | completed | failed | timeout | cancelled | unknown`；
- `value`：SKILL 返回值（保留 `%L`/S-expression 原始表示，同时可提供 typed decode）；
- `stdout`：本次同步调用捕获的 `poport` 内容；
- `errors`/`warnings`：旧字符串字段，供旧客户端继续工作；
- `diagnostics`：新的结构化诊断列表；
- `artifacts`：大日志、CDS.log delta、raw envelope 等引用；
- `request_id`/`operation_id`/`run_id`；
- `timing`、bridge identity、capability version。

### 4.2 平面 B：诊断事件（Diagnostic Events）

回答“发生了什么、何时发生、由谁产生”：

- bridge transport：连接、重试、超时、daemon restart；
- Virtuoso/SKILL：parse error、runtime error、warning、CIW output；
- ADE/Maestro：history、point、test、corner、job lifecycle；
- Simulation Monitor/Expression Evaluator：启动、退出、资源、表达式计算；
- Spectre：license、netlist、convergence、fatal、summary；
- GUI/X11：modal dialog、window recovery；
- artifact：文件发现、snapshot、SQLite integrity、下载失败。

事件应该支持 cursor/sequence；默认只把摘要事件 inline 返回，大量事件落到本地 JSONL 或 raw log artifact。

### 4.3 平面 C：原始工件（Artifacts）

回答“如何复核和重放”：

- `CDS.log` 或其带 cursor 的片段；
- `*.log` history summary；
- `*.msg.db` 原始 SQLite 快照；
- `virtuoso_ade_debug.log`、`Job*.log`、`Service*.log`；
- 每个 point 的 `netlist/input.scs`、`runSimulation`、`psf/spectre.out`、`psf/logFile`；
- `maestro.sdb`、`active.state`、Detail CSV、waveform export；
- bridge request/response audit（默认脱敏）；
- screenshot/dialog evidence。

RPC 不应把整个 artifact 内容塞入 JSON；只返回 `ArtifactRef`，需要时通过 download/read API 取回。

### 4.4 架构图

```text
                  ┌───────────────────────────────┐
                  │ CLI / Python / MCP / Harness  │
                  └───────────────┬───────────────┘
                                  │ unified result + event page
                  ┌───────────────▼───────────────┐
                  │ Operation / Run Coordinator    │
                  │ request-id · state · deadline  │
                  └───────┬───────────┬───────────┘
                          │           │
              sync SKILL │           │ async run observer
                          │           │
        ┌─────────────────▼──┐   ┌──▼────────────────────────┐
        │ Capture wrapper      │   │ Callback + status + tail   │
        │ outstring            │   │ axl/mae + msg.db + logs   │
        │ muffleWarnings       │   │ spectre per-point files   │
        │ errset/unwindProtect │   │ quiescence + diagnosis    │
        └──────────┬──────────┘   └──────────┬─────────────────┘
                   │                         │
        ┌──────────▼─────────────────────────▼──────────┐
        │ Artifact Store + Event Normalizer               │
        │ raw append-only files · JSONL · manifest/hash   │
        └─────────────────────────────────────────────────┘
```

## 5. 同步 SKILL 调用：推荐的返回流程

### 5.1 请求元数据

Python 端为每次调用生成：

```text
request_id   = 每个 RPC 请求唯一 UUID
operation_id = 高层操作唯一；多个 SKILL call 可共享
profile      = bridge profile
session      = Virtuoso/Maestro session（若已知）
deadline     = 单调时钟绝对截止时间
skill_hash   = SKILL 原文 hash；默认不保存完整原文
capture      = fast | diagnostic | audit | stream
```

请求示意：

```json
{
  "protocol_version": 2,
  "request_id": "req-01J...",
  "operation_id": "op-01J...",
  "skill": "...",
  "timeout": 30.0,
  "capture": {
    "stdout": true,
    "warnings": true,
    "session_log": "on_error",
    "max_inline_bytes": 65536,
    "persist_raw": true
  }
}
```

### 5.2 SKILL 侧包装

下面是已验证原语的组合示意，不是最终可直接复制的资源文件。最终实现应使用安全的 source escaping，并用 `unwindProtect` 做清理：

```skill
let((p value evalResult warnings captured errorInfo)
  p = outstring()

  evalResult = let((poport)
    poport = p
    muffleWarnings(
      errset(
        value = progn(
          ; bridge 注入本次 request body
        )
      )
    )
  )

  ; 先保存错误上下文，再调用其它可能改写它的函数。
  errorInfo = if(evalResult nil errset.errset)
  warnings = getMuffleWarnings()
  captured = getOutstring(p)
  close(p)

  list(
    list('evalOk if(evalResult t nil))
    list('value value)
    list('stdout captured)
    list('warnings warnings)
    list('error errorInfo)
  )
)
```

实现注意事项：

1. `errset` 成功时返回形如 `(value)` 的列表；即使 value 是 `nil`，也能区分“成功返回 nil”和“发生错误”。
2. `muffleWarnings` 改变 warning 的显示行为。Agent/机器模式可以默认不重复打印到 CIW；交互模式应提供 `mirror_warnings_to_ciw` 选项。
3. `getMuffleWarnings()` 必须紧跟在 `muffleWarnings()` 后调用；它只能捕获该同步表达式期间的 warning，不能替代异步 run 的日志采集。
4. `getWarn()` 适合取尚未打印的单个 warning；要取得一批 warning，应使用 `muffleWarnings/getMuffleWarnings`。
5. `hiPrintToLogFile`、模拟器子进程输出、GUI/数据库内部消息不会因为动态绑定 `poport` 自动进入 `stdout` 字段；必须保留 session-log 和 artifact 通道。
6. 任意用户 SKILL 可能自己修改 `poport`、调用 `getMuffleWarnings` 或改变全局状态，因此捕获能力应标记为 `best_effort`，并在 raw evidence 中保留实际 log。
7. 对象、waveform 和超大 list 不应盲目 `%L` 全量序列化；需要长度上限和 artifact fallback。

### 5.3 Python 兼容模型

不要改变 `VirtuosoResult.output` 的旧语义。建议 additive evolution：

```python
class VirtuosoResult(BaseModel):
    status: ExecutionStatus
    output: str = ""                 # 兼容：serialized SKILL return value
    stdout: str = ""                 # 新增：poport capture
    errors: list[str] = []            # 兼容视图
    warnings: list[str] = []          # 兼容视图
    diagnostics: list[Diagnostic] = []
    artifacts: list[ArtifactRef] = []
    request_id: str | None = None
    operation_id: str | None = None
    execution_time: float | None = None
    metadata: dict[str, Any] = {}
```

生产代码仍应使用 `Field(default_factory=list/dict)`；这里是字段语义示意。

## 6. session log 的使用边界

### 6.1 `CDS.log` 不是 RPC stdout

Cadence 文档把 `CDS.log` 定义为 session/transaction-oriented log：它记录 CIW 输入、输出、warning、error 和 GUI/数据库消息，格式包含 `\o`、`\e`、`\w`、`\#`、`\i`、`\p` 等前缀。它适合取证，不适合直接作为一次请求的返回值。

现场观察还显示：

- `printf` 会得到 RPC return `t`，同时在 `CDS.log` 出现 `\o` 行；
- `warn` 会以 warning channel 写入 `CDS.log`，但不在普通 return value 中；
- 人工 CIW 操作、ADE 后台事件和 bridge 请求都可能混在同一 session log 中。

因此 `CDS.log` 的角色应是：**失败时的补充证据和带 marker 的 best-effort request delta，不是同步调用的主返回通道。**

### 6.2 推荐的 delta 算法

当 `CapturePolicy.session_log` 为 `on_error` 或 `audit` 时：

1. 在 CIW 中用 `hiGetLogFileName()` 发现实际路径；
2. 调用 `hiFlushLogFile()`；
3. Python/SSH 记录文件 identity、size、mtime 和起始 byte offset；
4. 可选地写入 `hiPrintToLogFile("VB-BEGIN <request_id>")`；
5. 执行 SKILL capture wrapper；
6. 写入 `VB-END <request_id>` 并再次 `hiFlushLogFile()`；
7. 按 byte offset/marker 读取增量，保存 raw fragment 和 normalized events。

必须使用 offset + identity，而不是只保存行号或 mtime。

### 6.3 `hiStartLog` 只能作为可选审计通道

`hiStartLog(file)`/`hiEndLog()` 可以为一段操作建立 ancillary transaction log，且所有 CIW transaction 仍会继续写主 `CDS.log`。这很适合：

- 独占 CIW 的回归测试；
- 需要保留可 replay transaction 的 debug run；
- 对某个高层操作保存额外审计材料。

不建议把它作为默认的每请求日志机制：secondary log 是 session 级状态，嵌套/并发操作会互相影响，而且它不包含 Spectre/Simulation Monitor 的所有输出。若 CIW 不是 bridge 独占，优先使用 marker + offset，并把关联置信度标为 `best_effort`。

### 6.4 session log 的启动配置

若可以控制 Virtuoso 启动命令：

- 每个实例使用唯一 `-log` 路径；
- 使用 `-logtime`，内部统一按 UTC 保存；
- 用 `CDS_LOG_VERSION=pid` 或明确的 profile/PID 文件名避免多实例混写；
- 不要把 `CDS_LOG_PATH` 误当作 `-log` 的替代，它在本地文档中主要描述 panic log 的放置边界；
- 记录启动 command、PID、host、working directory、log path 和 IC version 到 manifest。

## 7. 异步 Maestro/Spectre：返回句柄，不等待一个巨大字符串

### 7.1 运行启动

`maeRunSimulation()` 返回 history 或 run ID 时，只能证明“运行请求被接受/创建了运行对象”，不能证明模拟成功。推荐流程：

1. preflight 记录 session、lib/cell/view、enabled tests/analyses、版本和 capability；
2. 预先建立唯一 callback marker 路径和 operation manifest；
3. 优先显式请求 run ID（目标版本 capability probe 确认 `?returnRunId` 语义），同时保留 history name；
4. 用 `?callback` 在 run 开始时原子注册完成回调；
5. callback 写入包含 `run_id/history/status/time` 的 marker，最好先写临时文件再 rename；
6. Python 立即返回 `RunHandle`，不在同一次 SKILL request 中调用长时间 `maeWaitUntilDone`。

项目已有 callback + marker 实现：[`src_bak/virtuoso_bridge/virtuoso/maestro/writer.py:491-575`](../../src_bak/virtuoso_bridge/virtuoso/maestro/writer.py#L491-L575)。建议把当前只写 `done` 的 marker 升级为 versioned marker。

### 7.2 观察循环

```text
observer loop (absolute deadline)
  ├─ callback marker：完成/状态/回调时间
  ├─ axlGetRunStatus：points/tests/corners 完成计数
  ├─ maeGetMappingForJobAndPoint：jobid ↔ point 映射（可用时）
  ├─ msg.db：远端一致性副本后按 logs.id 增量读取
  ├─ Job*.log / virtuoso_ade_debug.log：byte cursor tail
  ├─ per-point spectre.out / psf/logFile：byte cursor tail
  ├─ exprOutputs.log：表达式评估状态
  ├─ SSH/process：进程、连接、exit status
  └─ GUI/X11：只在疑似 modal dialog 时介入
```

Cadence 文档对这些 API 的边界很明确：

- `axlGetRunStatus(session ?historyName ... ?optionName "all"|"tests"|"corners")` 返回已完成数/总数，适合进度；
- `maeGetMappingForJobAndPoint(session)` 可辅助诊断 job 与 point 的对应关系；
- `maeGetSimulationMessages(?msgType "ERROR"|"WARNING"|"INFO"|"ALL")` 返回字符串，适合在线摘要，不是全量审计；
- `axlGetHistoryResults()`、`axlGetResultsLocation()`、`asiGetAnalogRunDir()` 分别提供不同层次路径，不能互相替代；
- `asiRegCallBackOnSimComp` 的文档注明只对 local simulation 注册 callback，不能作为所有远程/farm flow 的统一方案。

### 7.3 每轮都要做 terminal-failure scan

不能只等待 marker、raw 目录或某个文件出现。每轮 poll 同时检查：

- `spectre.out` 的 fatal、`terminated prematurely`、license/read-in/convergence failure；
- `msg.db` 的明确 error/fatal，并根据 `point/test/corner/jobid` 追到 `location`；
- `Job*.log`/ADE debug 的子进程退出、启动失败和调度异常；
- SSH/进程连接状态；
- GUI modal dialog。

项目 `AGENTS.md` 已明确：对会 fork 并写 log 的工具，`system()` 返回码不可靠；artifact poll 与 log-tail failure poll 必须是一个不可拆开的组合。

### 7.4 callback 后还要有 finalization/quiescence

callback 到达不等于所有文件已经 flush。建议状态分成：

```text
CREATED → ACCEPTED → NETLISTING → SUBMITTED → RUNNING
       → POINT_DONE → HISTORY_DONE → RESULTS_FLUSHING
       → RESULTS_READY → COLLECTED
       ↘ FAILED / TIMEOUT / CANCELLED / UNKNOWN
```

只有在 result DB 可打开、预期输出存在、关键 log 在两次 poll 间达到 quiescence 后，才把对外状态设为 `success`。

## 8. 统一事件和工件模型

### 8.1 `LogEvent`

```json
{
  "event_id": "msgdb:Interactive.0:42",
  "observed_at": "2026-08-31T04:54:41.278Z",
  "source_time_raw": "1788152061.278247",
  "severity": "info",
  "raw_level": "process",
  "producer": "spectre",
  "message": "spectre completes with 0 errors, 0 warnings, and 7 notices.",
  "correlation": {
    "operation_id": "op-01J...",
    "run_id": "29db...",
    "session": "fnxSession8",
    "history": "Interactive.0",
    "jobid": "22",
    "point": "1",
    "test": "serdes_top_tran",
    "corner": "Nominal",
    "simid": "1",
    "pid": "300057"
  },
  "source": {
    "host_role": "spectre",
    "path": "/.../Interactive.0/1/serdes_top_tran/psf/spectre.out",
    "line": null,
    "byte_offset": 18291
  },
  "attrs": {"message_id": null},
  "raw_ref": "artifacts/Interactive.0/point-1/spectre.out#sha256:..."
}
```

规则：

- `producer` 和 `tool` 分开，不能把 ADE GUI、Simulation Monitor、Expression Evaluator、spectre 压成一个字符串；
- 保存 `raw_level`，因为 msg.db 的 `event/process/info` 不是通用 severity；
- `message` 不做破坏性清洗；`code/category/retryable` 另存；
- 时间统一内部 UTC，同时保留原始 timestamp 和 timezone 原文；
- 每个事件尽量可追到 path/line/offset 或 raw artifact；
- 规范化事件可重算，原始文件才是真相。

### 8.2 `msg.db` 增量读取

现场 `Interactive.0.msg.db` 核心 schema：

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

现场还观察到 `meta.version=1`、`attrs` 为 JSON 文本，且 `location.line` 可能为 `-1`、`location.file` 可能是相对路径。

实现规则：

1. 每个版本先执行 `PRAGMA table_info(logs)`/`location`，不要写死 schema；
2. 运行中不要直接修改源 DB；优先远端 SQLite backup，再下载；
3. 增量游标优先使用 `logs.id`，但仍需检测 DB 替换/轮转；
4. 保存 size、mtime、schema version、sha256；
5. DB 存在但锁定/不可读时返回 `artifact_present_but_unreadable`，不能静默当作无消息；
6. 原始 `attrs` 保留，解析失败不丢字段。

### 8.3 文件 tail cursor

```json
{
  "source_id": "spectre:/path/to/spectre.out:device:inode",
  "offset": 18291,
  "size_seen": 18542,
  "mtime_ns_seen": 1788152061278247000,
  "prefix_sha256": "...",
  "generation": 1
}
```

如果 inode/device 改变、size 小于 offset 或 prefix hash 不匹配，产生 `source_reset`，从 offset 0 重新读取并递增 generation。这样可以处理 `CDS.log` 轮转、Spectre 重跑覆盖、远端临时目录复用。

### 8.4 Artifact manifest

```json
{
  "artifact_id": "art-01J...",
  "kind": "spectre_log",
  "producer": "spectre",
  "host_role": "spectre",
  "remote_path": "/.../Interactive.0/1/tb/psf/spectre.out",
  "local_path": "artifacts/Interactive.0/point-1/spectre.out",
  "size": 17052,
  "mtime": "2026-08-31T04:54:41Z",
  "sha256": "...",
  "complete": true,
  "correlation": {
    "run_id": "...",
    "history": "Interactive.0",
    "point": "1",
    "test": "serdes_top_tran"
  }
}
```

manifest 是 CLI、Python、MCP、回归系统的共同中间层：界面只展示摘要和引用，审计系统读取 hash。

## 9. 远程、多主机和路径规则

### 9.1 运行时发现路径，不猜目录

```text
explicit history/run handle
  > axlGetRunData / axlGetHistoryName / axlGetHistoryResults
  > axlGetResultsLocation（考虑 saveDir/saveResDir）
  > asiGetAnalogRunDir / asiGetLogFileList
  > msg.db attrs/location
  > mtime + companion files（仅 fallback）
  > natural sort history name（最后 fallback）
```

项目现场已经证明 project root 和 simulation root 可以分离；因此不能只把 `ddGetObj(lib)~>readPath` 下的目录拼成结果路径。

### 9.2 所有 path 带 host role

```python
RemotePath(
    host_role="gui",       # CDS.log / CIW-owned path
    path="/home/user/CDS.log",
    kind="session_log",
)

RemotePath(
    host_role="spectre",   # per-point simulator artifact
    path="/scratch/.../psf/spectre.out",
    kind="simulator_log",
)
```

- `CDS.log` 通常属于 GUI host；
- daemon stderr/RB log 属于 daemon host；
- `spectre.out` 属于 Spectre/run host；
- `maestro.sdb`/history summary 通常在 project/deployment root；
- split topology 下只有声明的 shared root 才可以跨角色直接访问。

### 9.3 安全和传输

- 路径使用已有 SSH runner 的严格 quoting；
- raw log/command 默认脱敏后返回，完整 raw 只在受控 artifact 目录；
- 不把 license token、密码、完整环境变量或未经同意的绝对用户路径送入模型；
- 大文件远端压缩/分块下载，禁止把 PSF/waveform 放进普通 JSON；
- 上传到工具 cwd 后再运行，避免 `file not found`；
- `msg.db`/`rdb` 只读采集，不在 bridge 中提供通用编辑入口。

## 10. 协议建议：先兼容、再升级

### 10.1 短期：保留现有 frame，增加逻辑 envelope

现有 STX/NAK/RS 内层协议可以先保留，降低 CIW 侧升级风险。第一阶段只做：

- `protocol_version`；
- `request_id`、`operation_id`；
- 内层 payload 从单个 `%L value` 升级为 `%L envelope`；
- `capture_capabilities`、`capture_state`、`truncated`；
- 明确最大 payload；
- malformed/unknown marker 返回协议错误，而不是默认为成功；
- 外层兼容旧客户端：没有 envelope 时仍填充旧 `output/errors`。

当前 `%L` 对字符串控制字符会生成安全的 SKILL 转义（现场验证 `\036`、`\002`、`\025`），但不要把原始二进制/PSF 塞进 frame。

### 10.2 中期：外层 TCP v2 使用长度前缀

```text
4-byte unsigned big-endian length
N-byte UTF-8 JSON request/response
```

它比“连接关闭即表示结束”更适合限制 frame、支持压缩和未来分页。但不建议一开始就在同一个 CIW socket 上推送无限 event stream。稳妥顺序是：

1. 一次请求一次 control response；
2. 长任务返回 `RunHandle`；
3. 用 `events(run_id, cursor, limit)` pull API 分页；
4. CLI `--follow`、Python generator、MCP stream 都建立在 pull API 上；
5. 明确有需求后再增加 push transport。

### 10.3 并发规则

同一 Virtuoso/CIW：

- SKILL mutation 串行；
- 网络层可以接收/排队多个请求，但 per-instance CIW executor 只能单 writer；
- artifact tail、SQLite backup、SSH 文件传输可以并行；
- 独立 Virtuoso instance、独立 Spectre job、不同 history/point 才是并行边界。

## 11. 返回模型和错误分类

### 11.1 `Diagnostic`

```python
class Diagnostic(BaseModel):
    severity: Literal["debug", "info", "notice", "warning", "error", "fatal"]
    code: str | None = None
    category: str | None = None
    message: str
    producer: str
    phase: str | None = None
    retryable: bool | None = None
    correlation: dict[str, str | None] = {}
    source: SourceRef | None = None
    raw_ref: str | None = None
    confidence: Literal["high", "medium", "low"] = "medium"
```

### 11.2 `RunHandle` / event page

```json
{
  "run_id": "run-01J...",
  "history": "Interactive.21",
  "session": "fnxSession8",
  "phase": "running",
  "next_cursor": "eyJzb3VyY2VzIjo...",
  "events_inline": [
    {"severity": "info", "producer": "ADE GUI", "message": "NewHistoryCreated"}
  ],
  "artifacts": [
    {"artifact_id": "...", "kind": "history_summary", "complete": false}
  ]
}
```

建议 `events(run_id, cursor, limit)` 返回：

```json
{
  "run_id": "run-01J...",
  "events": [/* normalized LogEvent */],
  "next_cursor": "...",
  "source_states": [
    {"source_id": "...", "state": "active", "offset": 18291}
  ],
  "has_more": false,
  "diagnosis": null
}
```

### 11.3 内部状态

```text
transport_state : connected | degraded | disconnected
execution_state : accepted | running | completed | failed | timeout | cancelled | unknown
result_state    : absent | partial | ready | corrupt | unknown
capture_state   : not_started | collecting | partial | complete | failed
```

### 11.4 错误分类

```text
transport.connection_refused
transport.connect_timeout
transport.read_timeout
transport.disconnected
bridge.protocol_malformed
bridge.daemon_exit
skill.parse_error
skill.runtime_error
skill.return_nil                 # 不是错误，是 SKILL 语义信息
cadence.warning
cadence.modal_dialog
cadence.session_missing
maestro.run_not_started
maestro.run_incomplete
simulator.license
simulator.netlist
simulator.convergence
simulator.fatal
simulator.crash
artifact.missing
artifact.unreadable
artifact.corrupt
observer.deadline
observer.unknown
```

### 11.5 CapturePolicy

| 模式 | stdout/warning | session log | raw artifact | 默认场景 |
|---|---|---|---|---|
| `fast` | 不捕获或只保留 error | 不读 | 否 | 高频只读 probe |
| `diagnostic` | 捕获并限长 | 仅失败/异常 | 保存摘要 | Agent 默认 |
| `audit` | 捕获并限长 | 全量 delta/secondary log | 保存全部 | CI、回归、复现 |
| `stream` | 分页/事件 cursor | observer 管理 | 必须持久化 | 长时间 run |

`max_inline_bytes` 建议默认 64 KiB。超过上限必须返回 `truncated=true` 和 `ArtifactRef`，不能静默截断。

## 12. 实施路线

### Phase 0：固定契约和离线 fixture

- 新增 `Diagnostic`、`ArtifactRef`、`LogCursor`、`RunHandle` 模型；
- 建立 `CDS.log`、msg.db、Job log、Spectre log fixture；
- 增加 S-expression envelope/framing parser golden tests；
- capability probe 记录 `outstring`、`muffleWarnings`、`getMuffleWarnings`、`unwindProtect`、`hiGetLogFileName`、`hiFlushLogFile`、`mae*`、`axl*`。

### Phase 1：同步 SKILL 垂直切片

- request 加 `request_id`；
- feature-flagged capture wrapper；
- 维持 `VirtuosoResult.output` 兼容；
- 现场验证 `printf/info/warn/C-warning/error/nil`；
- 失败时读取 `CDS.log` delta，成功时默认不读全量 log。

### Phase 2：统一 artifact store

- 新建 `observability/`：`tail.py`、`cdslog.py`、`msgdb.py`、`manifest.py`、`normalize.py`；
- 所有 remote path 带 host role；
- SQLite backup + schema introspection + hash；
- cursor、rotation/truncation、partial artifact 语义；
- raw 与 normalized 双轨保存。

### Phase 3：Maestro run observer

- 把 callback marker 升级为 versioned marker；
- 返回 `RunHandle`，实现 `events(cursor)`；
- 并行观察 `axlGetRunStatus`、job-point mapping、msg.db、Job/ADE、per-point Spectre；
- terminal failure fast-exit；
- callback 后 quiescence/finalization；
- `maeWaitUntilDone` 仅作明确 fallback，不作为默认长等待路径。

### Phase 4：统一接口适配器

- CLI：人类摘要、`--json` envelope、`--follow`；
- Python：同步 `execute_skill`，异步 `start_run/events/collect`；
- MCP/Harness：共用 tool schema，事件只返回受控大小内容和引用；
- MCP 协议日志必须走 stderr，不能污染 stdout JSON-RPC。

### Phase 5：兼容性和运营

- IC6.1.8、IC23.1、ADE 类型、PDK capability matrix；
- retention、quota、脱敏；
- daemon restart/reconnect、modal dialog、跨用户 daemon、网络断开故障注入；
- run manifest/replay/compare 报告。

## 13. 验收标准

### 同步调用

- `printf/info/println` 进入 `stdout`，return value 仍独立正确；
- 多个 warning 由 `muffleWarnings/getMuffleWarnings` 返回；
- C-level warning 不依赖 grep 也能捕获；
- `errset` 错误保留 raw error object，且不误判为成功返回 nil；
- `hiPrintToLogFile` 出现在 `CDS.log` artifact，而不是 stdout；
- 超过 inline 限制返回 artifact ref + `truncated=true`；
- primitive 缺失时 operation 仍可执行，但标记 `capture_state=partial`。

### 长任务

- accepted、running、point done、history done、results ready 是不同事件；
- callback 缺失/延迟时，status/log observer 仍能给出状态；
- Spectre exit 0 但 log 有 fatal 时，最终不是 success；
- msg.db 锁定或 schema 变化时，不静默返回空消息；
- log rotation/truncation 产生 source_reset 并从新 generation 读取；
- callback 到达但 result DB 仍在写时进入 finalizing；
- 断线后 cursor 可继续读取且不重复大量事件。

### 远程与安全

- GUI/daemon/deploy/Spectre 分裂时，路径和 SSH 角色不混淆；
- 不把本地 Windows 路径直接上传到远端 SKILL；
- raw command、license、密码和个人路径按策略脱敏；
- 同一 CIW 的两个 mutation 不交叉执行；
- 写操作有 operation/audit record。

## 14. 尚待现场验证的问题

1. 目标 IC/ISR 是否都提供 `outstring/getOutstring`、`muffleWarnings/getMuffleWarnings`，以及对各类 C-extension warning 的覆盖范围；
2. `hiStartLog` 在同一 session 的嵌套/并发行为；
3. 不同版本 `CDS.log` 前缀、时间格式和轮转策略；
4. 运行中的 msg.db 在 WAL/锁定/替换时的最佳 backup 窗口；
5. `maeRunSimulation(?returnRunId t)` 在各 ADE 类型的实际返回差异；
6. GUI、background、远程 farm 对 callback 的支持范围；
7. result DB “可打开”与“expected outputs 已 flush”的可靠判据；
8. modal dialog、X11、无 GUI 环境的 observer fallback；
9. raw log 脱敏后是否仍保留足够 PDK/netlist 根因信息。

## 15. 结论

对 `virtuoso-bridge-NCS`，最稳妥的方案不是再写一个 `get_log()`，而是：

> **同步调用用 SKILL 原生 capture primitives 得到小而确定的控制结果；异步运行用 callback + status + cursor tail 观察；所有详细内容落到带关联键和 hash 的 artifact manifest；对外统一返回 result + event page + artifact references。**

最小闭环为：

```text
request_id
  → outstring + muffleWarnings + errset
  → backward-compatible VirtuosoResult
  → on-error CDS.log delta
  → RunHandle + callback marker
  → msg.db / Job / spectre observer
  → normalized diagnosis + artifact manifest
```

这条路径复用了当前 bridge 已有的 `progn`、STX/NAK/RS、daemon banner、callback marker、Spectre terminal scan 和远端角色模型，同时避免把 CIW、模拟器、结果数据库和日志混成一个不可追溯的字符串。

## 16. 证据索引

### 项目内

- [`AGENTS.md`](../../AGENTS.md)：`system()` 返回码不可靠；poll 必须同时 tail terminal failure。
- [`README.md`](../../README.md)：VirtuosoClient/Spectre/SSH 分层与原始 bridge 说明。
- [`skills/virtuoso/references/simulation-flow.md`](../../skills/virtuoso/references/simulation-flow.md)：GUI simulation、callback + marker、非阻塞等待。
- [`skills/virtuoso/references/maestro-skill-api.md`](../../skills/virtuoso/references/maestro-skill-api.md)：`maeGetSimulationMessages`、`maeRunSimulation`、`axl*` 边界。
- [`skills/virtuoso/references/maestro-python-api.md`](../../skills/virtuoso/references/maestro-python-api.md)：Detail CSV、snapshot、run observer 约定。
- [`skills/virtuoso/references/cellview-on-disk-layout.md`](../../skills/virtuoso/references/cellview-on-disk-layout.md)：`.log/.msg.db/.rdb` 职责和只读边界。
- [`skills/virtuoso/references/troubleshooting.md`](../../skills/virtuoso/references/troubleshooting.md)：modal dialog、远端文件、readback 限制。
- [`src/virtuoso_bridge/virtuoso/basic/bridge.py`](../../src/virtuoso_bridge/virtuoso/basic/bridge.py)：当前 TCP request/result、timeout、response parser。
- [`src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il`](../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il)：SKILL IPC handler、stderr ring、daemon lifecycle。
- [`src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge_daemon_3.py`](../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge_daemon_3.py)：内外层 framing、watchdog、banner、`listen(1)`。
- [`src_bak/virtuoso_bridge/virtuoso/maestro/writer.py`](../../src_bak/virtuoso_bridge/virtuoso/maestro/writer.py)：callback marker 观察和 run timeout。
- [`src_bak/virtuoso_bridge/spectre/runner.py`](../../src_bak/virtuoso_bridge/spectre/runner.py)：`+log/-raw/+logstatus`、terminal marker 和结果组装。

### Cadence 本地文档

- `C:\Users\user\Desktop\doc\skuiref\chap2.html`：`hiGetLogFileName`、`hiPrintToLogFile`、`hiFlushLogFile`、`hiStartLog`/`hiEndLog`。
- `C:\Users\user\Desktop\doc\sklangref\inputoutput_re_outstring.html`、`inputoutput_re_getOutstring.html`：字符串 output port。
- `C:\Users\user\Desktop\doc\sklangref\funcprog_re_muffleWarnings.html`、`core_re_getMuffleWarnings.html`：批量 warning capture。
- `C:\Users\user\Desktop\doc\sklangref\funcprog_re_errset.html`、`funcprog_re_unwindProtect.html`：error capture 和清理语义。
- `C:\Users\user\Desktop\doc\skipcref\ipcskill_re_ipcBeginProcess.html`、`ipcReadProcess.html`、`ipcWait.html`：子进程 stdout/stderr、logFile、状态和 UI blocking 语义。
- `C:\Users\user\Desktop\doc\maeSKILLref\runRelated.html`、`historyRelated.html`：Maestro callback、run status、job-point mapping、history/RDB。
- `C:\Users\user\Desktop\doc\spectreref\chap2.html`：Spectre `+log`、`-raw`、`+logstatus`。
- `C:\Users\user\Desktop\doc\wincfg\gettingStarted.html`、`C:\Users\user\Desktop\doc\caiuser\chap11.html`：session log、timestamp、log version/retention。

## 17. 针对核心问题：每次指令自动取得 `CDS.log` 增量

### 17.1 先给结论

**可以实现，而且不需要每次下载整个 `CDS.log`。** 推荐采用：

```text
per-instance cursor
  + serialized CIW execution
  + request begin/end marker
  + hiFlushLogFile()
  + fileLength() byte offsets
  + remote tail/download
```

不要只做：

```text
before_size = stat(CDS.log)
execute()
after_size = stat(CDS.log)
read(before_size:after_size)
```

单纯 size diff 会遇到 buffering、log rotation、异步 ADE 输出和并发请求；它只能作为 fallback。**推荐方案是“marker 定界 + byte cursor 加速”，两者同时使用。**

### 17.2 每个 Virtuoso instance 保存一个 cursor

```json
{
  "host_role": "gui",
  "path": "/home/user/CDS.log",
  "device": 2049,
  "inode": 123456,
  "offset": 425871,
  "generation": 1,
  "prefix_sha256": "..."
}
```

初始化时只做一次：

```skill
hiGetLogFileName()
hiFlushLogFile()
```

然后由 GUI host 上的 SSH runner 读取 `stat`，保存初始 offset。之后每条指令都从上一次 offset 继续读取。

### 17.3 一次指令的精确流程

```text
Python 生成 request_id
        │
        ▼
SKILL handler:
  1. hiGetLogFileName()
  2. hiFlushLogFile()
  3. 写 BEGIN marker
  4. hiFlushLogFile()
  5. 执行用户 SKILL
  6. 在 unwindProtect cleanup 中写 END marker
  7. hiFlushLogFile()
  8. fileLength(log_path) 得到结束 offset
  9. 返回 value + log_path + offsets + complete
        │
        ▼
Python:
  10. 按 host_role/path/offset 读取增量
  11. 用 BEGIN/END marker 截取本次命令片段
  12. 更新 cursor
  13. 返回 result.cdslog_delta
```

`fileLength()` 在本地 Cadence 文档中定义为返回文件字节数；现场测试中，SKILL 返回的结束长度与远端 `stat().st_size` 一致。因此 offset 应按**字节**保存，读取时不要按字符数计算。

### 17.4 推荐的返回结构

逻辑上可以返回：

```json
{
  "request_id": "req-01J...",
  "value": "3",
  "status": "success",
  "cdslog": {
    "path": "/home/user/CDS.log",
    "host_role": "gui",
    "start_offset": 425871,
    "end_offset": 425924,
    "begin_marker": "VB-BEGIN|req-01J...",
    "end_marker": "VB-END|req-01J...",
    "complete": true,
    "text": "\\o ...\\n\\w ...\\n",
    "truncated": false,
    "correlation": "marker"
  }
}
```

由于当前 SKILL 侧没有必要依赖 JSON encoder，第一阶段可以继续使用现有 STX/NAK/RS + `%L`，把上面的对象编码成 SKILL alist/list；Python 再解析为 typed model。

### 17.5 为什么必须同时使用 marker 和 offset

| 方法 | 优点 | 问题 |
|---|---|---|
| 仅 offset | 快、可增量、适合大文件 | 不能判断某行是否属于本次指令 |
| 仅 marker | 能定界命令、容易诊断 | 需要扫描文本，rotation/重复 marker 要处理 |
| **marker + offset** | 既快又可关联 | 实现略复杂，但适合生产 |

具体做法：

- offset 决定从哪里开始读取，避免每次扫描整个文件；
- marker 决定本次命令的逻辑区间；
- 返回中同时保存 raw fragment、offset、marker 和 source identity；
- 解析失败时仍保留 raw fragment，不丢日志。

### 17.6 异常和 timeout 时的行为

必须把“不完整增量”也返回，而不是丢掉：

```json
{
  "complete": false,
  "reason": "timeout",
  "start_offset": 425871,
  "end_offset": 426912,
  "end_marker_seen": false,
  "text": "...partial CDS.log delta..."
}
```

情形处理：

- **正常返回**：看到 END marker，`complete=true`；
- **SKILL runtime error**：`errset` 捕获错误，cleanup 仍写 END marker，`complete=true`，但 control status 为 error；
- **socket timeout/CIW 被 modal dialog 阻塞**：读取 BEGIN 后已有的当前增量，`complete=false`；
- **daemon/Virtuoso 崩溃**：读取最后 cursor 到文件当前末尾，记录 `source_ended`；
- **log rotation/truncation**：产生 `source_reset`，新 generation 从 0 读取；
- **后台异步事件在 END 后到达**：不强行归入本次同步命令，交给对应的 run observer。

### 17.7 这套方法的边界

它对“同步执行一条 SKILL 指令”可以做到很高的关联准确度，但不能承诺 `CDS.log` 中的每一行都严格属于该指令，因为：

- 同一 CIW 可能有人工输入、ADE 后台任务和插件同时写日志；
- 某些 warning 或 GUI 事件在当前 form 返回后才异步落盘；
- 一个 `maeRunSimulation()` 只启动了长任务，后续 Spectre 输出不应继续归属于启动命令。

所以最终字段应包含：

```text
correlation = marker | offset | time_window | unknown
confidence  = high | medium | low
complete    = true | false
```

### 17.8 最小实现建议

第一版可以只实现以下四个变化：

1. `VirtuosoClient.execute_skill()` 每次生成 `request_id`；
2. `RBIpcDataHandler` 用 SKILL wrapper 写 BEGIN/END marker，并在 response 中返回 log path/offset；
3. Python 在 GUI host 上实现 `CdsLogCursor.read_delta()`；
4. `VirtuosoResult` 增加 `cdslog_delta` 和 `cdslog_meta`，旧字段保持不变。

不要一开始做全量 log parser、push stream 或数据库日志系统。先把下面这个闭环跑通：

```text
execute_skill()
  → 一个 SKILL eval
  → 一个 control response
  → 一个 CDS.log delta
  → 一个可更新 cursor
```

### 17.9 与 `hiStartLog` 的关系

`hiStartLog()/hiEndLog()` 可以生成 ancillary transaction log，但它是 session 级 secondary log，不适合默认包围每一个请求。对于“每条指令自动获得主 `CDS.log` 增量”，应优先使用：

```text
hiGetLogFileName
hiFlushLogFile
hiPrintToLogFile marker
fileLength offset
```

`hiStartLog` 仅作为独占 CIW 的回归审计选项。

## 18. 实现时最容易犯的错误：`hiFlush()` 不是 `hiFlushLogFile()`

当前 daemon 在生成 SKILL 请求时会调用 `hiFlush()`。Cadence 文档中，`hiFlush()` 的作用是同步 event/exposure queue、刷新窗口和 form；它不是主 session log 的 flush API。要保证 `CDS.log` 增量在 RPC 返回前可读，必须显式调用：

```skill
hiFlushLogFile()
```

相关函数不要混用：

```text
hiFlush()         → GUI/window/event queue
hiFlushInfo()     → 让前一个程序的输出显示在 CIW
hiFlushLogFile()  → 刷新 CDS.log 和 secondary log
```

因此当前 bridge 若要实现“每条指令自动带回 CDS.log 增量”，至少要把 log capture wrapper 的前后同步点写成：

```text
hiFlushLogFile()
fileLength(log_path)       ; before offset
<execute user SKILL>
hiFlushLogFile()
fileLength(log_path)       ; after offset
```

而不是只依赖目前的 `hiFlush()`。

实际日志字节建议由 Python/SSH 从 GUI host 读取：

```text
SKILL: 发现路径、flush、返回 offset
SSH/SFTP: 按 offset 读取 CDS.log 增量
Python: 解析 marker、更新 cursor、放入 result
```

这样可以避免在 CIW 内部再次用 `infile/gets` 读取大日志，也不会因为日志读取阻塞 Virtuoso event loop。`infile` 仍可作为没有 SSH/SFTP 的 local fallback，但不应作为默认远程实现。
