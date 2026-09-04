# Virtuoso Bridge 重构的关键技术点

> 调研日期：2026-09-04  
> 目标：在已有开源上游能力基础上，给 `virtuoso-bridge-NCS` 提供可落地的重构优先级，而不是立即实现全部功能。

## 1. 重构目标的正确表述

不是“把所有 Cadence 命令封装成 Python 函数”，而是：

> 在不破坏 Virtuoso 数据一致性、GUI event loop 和多主机路径语义的前提下，把**设计意图、执行、观察、验证、工件**组成可重放的事务链。

建议目标架构：

```text
┌──────────────────────────────────────────────────────────────┐
│ Interface / adapters                                         │
│ CLI · Python · MCP/Harness · future notebook                  │
└──────────────────────────────┬───────────────────────────────┘
                               ▼
┌──────────────────────────────────────────────────────────────┐
│ Domain intent                                                 │
│ CellViewRef · SchematicPlan · MaestroSetup · RunRequest       │
└───────────────┬───────────────────┬──────────────────────────┘
                ▼                   ▼
┌──────────────────────┐  ┌────────────────────────────────────┐
│ Capability registry  │  │ Operation compiler / validators     │
│ version · API · PDK  │  │ SKILL · XML · shell · pre/post      │
└──────────────┬───────┘  └──────────────┬─────────────────────┘
               ▼                         ▼
┌──────────────────────────────────────────────────────────────┐
│ Runtime                                                        │
│ Virtuoso session/lock manager · IPC bridge · SSH role paths    │
│ Spectre runner · GUI/X11 recovery · RunObserver               │
└──────────────┬────────────────────────────────────────────────┘
               ▼
┌──────────────────────────────────────────────────────────────┐
│ Artifact + observability                                      │
│ raw files · normalized events · manifest · hashes · diagnosis  │
└──────────────────────────────────────────────────────────────┘
```

## 2. P0：必须先解决的技术点

### P0-1. 数据所有权和修改边界

把文件按“OA binary / text config / XML setup / SQLite result / log”分类，并在代码中给每类不同 adapter：

```text
OAAdapter       → 只能通过 SKILL/DFII
TextConfig      → parse + backup + atomic replace + reopen/verify
XmlSetup        → schema-aware patch + canonical validation
SqliteArtifact  → read-only snapshot/query
LogArtifact     → append/tail/classify
```

公共 API 不应暴露一个通用 `edit_file(path, text)`，因为它会让调用者绕过 OA、锁、CDF 和 Maestro session。

### P0-2. CellView/session/lock 状态机

每个可写 cellview 都需要显式状态：

```text
UNKNOWN
  → DISCOVERED
  → READ_OPEN
  → WRITE_OPEN (exclusive lock verified)
  → DIRTY
  → CHECKED
  → SAVED
  → CLOSED
  → PURGED
```

非法转换要报错，例如：

- `READ_OPEN → SAVED`：不允许把 read mode 当写入；
- `DIRTY → PURGED`：除非用户明确 discard；
- `WRITE_OPEN → second WRITE_OPEN`：返回 conflict，并指出 lock owner；
- `CLOSED → reuse old dbObject`：强制重新 resolve。

Maestro 还要有独立的 GUI/background 状态机；不能把 `maeOpenSetup` 和 `deOpenCellView` 简化成同一方法。

### P0-3. 运行状态机与非阻塞观察

```text
CREATED → ACCEPTED → NETLISTING → SUBMITTED → RUNNING
       → POINT_DONE → HISTORY_DONE → RESULTS_READY → COLLECTED
                    ↘ FAILED / TIMEOUT / CANCELLED / UNKNOWN
```

`maeRunSimulation` 的接受成功不等于仿真成功；返回 history 也不等于结果已经写完。必须把：

- run request accepted；
- point/history finished；
- simulator terminal status；
- expression evaluation；
- result DB flush；

拆成不同事件。

### P0-4. 多主机与路径语义

保留并强化项目已有的角色模型：

```text
GUI host       → CIW、X11、Virtuoso process
Deploy host    → 上传 setup/脚本/输入
Daemon host    → ipcBeginProcess 启动 bridge daemon/tunnel endpoint
Spectre host   → standalone Spectre
Shared root    → GUI/daemon/deploy 都能看到的文件根
```

所有 path 都要标注所属 host：

```python
RemotePath(host_role="daemon", path="/tmp/...", kind="scratch")
LocalPath(path="C:/...", kind="artifact")
```

禁止把本地 Windows 路径直接拼进远端 SKILL；禁止假设 project library root 与 simulation/saveDir root 相同；禁止只因 SSH 命令失败就静默切换 local mode。

### P0-5. 协议 framing 与并发

当前 bridge 采用 JSON request + STX/NAK/RS framing，这是合理的最小协议。重构时补齐：

- `protocol_version`；
- `request_id`、`session/profile`、deadline；
- payload length 或严格 delimiter escaping；
- 单 CIW 写队列（同一 Virtuoso instance 内串行）；
- read-only 请求可合并/批量，write 请求不可交叉；
- daemon banner/identity 与 tunnel endpoint 双向核对；
- daemon graceful shutdown、watchdog、stale process 检测；
- 协议层 raw frame 记录（debug 可开，默认脱敏）。

不要为了追求“真正并发”把两个 SKILL mutation 同时发给一个 CIW；并发应放在独立 Virtuoso instance、独立 Spectre job 或不同 history/point 层。

## 3. P1：核心正确性与可维护性

### P1-1. Capability / version matrix

不同 IC/ISR、ADE 类型、PDK 和安装环境的可用函数并不一致。建立启动时 capability probe：

```text
Virtuoso version
DB type (CDB/OpenAccess)
ADE app (Assembler/Explorer/ADE-L/XL)
mae* availability
asi* availability
axl* availability
OCEAN availability
spiceIn / Spectre / XStream availability
PDK master/CDF schema
```

注意：项目经验已证实 `procedurep()` 对 compiled/built-in 函数可能返回 nil；不能把它当函数存在性检测。对 `mae*` 采用文档/`fboundp`/受控 trial call 的组合，并缓存 probe 结果及版本。

能力表应可序列化：

```json
{
  "ic_version": "IC6.1.8-64b.500.34",
  "db_type": "OpenAccess",
  "capabilities": {
    "maeRunSimulation": {"available": true, "source": "probe"},
    "axlGetCorner": {"available": true, "source": "probe"},
    "pnoise_jitter_api": {"available": "partial", "note": "GUI/form state required"}
  }
}
```

### P1-2. 类型化 serialization，而不是 delimiter string

项目旧 reader 通过 `INST|...|...`、`TERM|...|...` 等字符串传输，容易被 `|`、换行、总线名和错误文本打破。建议：

- SKILL 侧返回 JSON（若环境允许）或长度前缀/严格 s-expression；
- 保留 raw SKILL output；
- Python 侧把 `nil/t/string/number/list/dbObject` 映射成 tagged value；
- 对 CDF value、engineering unit、symbol、waveform reference 不强制猜类型；
- schema 版本化，解析失败返回原文和位置。

### P1-3. Preflight / postcondition / rollback

每个 mutation operation 都应有：

```text
preflight:
  target exists / absent as expected
  correct view type
  no foreign lock
  master/CDF/tech binding resolvable
  input files staged and readable

execute:
  one bounded batch

postcondition:
  return status
  schCheck / setup validation
  readback semantic diff
  file existence + non-empty + owner/hash

recovery:
  close/purge only if safe
  restore backup or write to a new Cell first
  never silently delete user data
```

OA 设计不一定提供跨多个 cellview 的原子事务，所以 MVP 应采用**新 Cell/新 view + 验证 + 显式 publish**，而不是声称全局原子性。

### P1-4. 稳定业务标识与 stale handle

内部对象可以用 `dbObject` 操作，但跨 RPC/跨 close 不保存它。稳定键应是：

```text
(lib, cell, view, hierarchical instance path, terminal name, net name)
```

每次 readback 重新建立 object map；删除/重建后旧 map 全部失效。对于结果则用：

```text
(run_id, history, test, point, corner, artifact relative path)
```

### P1-5. CDF/PDK adapter

将 PDK 差异隔离到 adapter，不让 schematic core 假定 `w/l/nf/m` 或 pin 名称统一：

```text
PdkContext
  ├─ technology library / dbu / grid
  ├─ master resolver
  ├─ terminal aliases and pin order
  ├─ CDF parameter metadata + callbacks
  ├─ default symbol masters
  └─ netlist name mapping
```

先为一个已知 PDK（现场 tsmcN65）做完整 read/write/readback，再扩展。

### P1-6. 结果、waveform、log 三种消费契约

定义不同返回类型：

```text
SetupSnapshot       → raw SKILL/XML + normalized metadata
ScalarResultTable   → points × outputs + spec status
WaveformArtifact    → file reference / sampled data + analysis
RunDiagnosis        → status + cause + evidence refs
```

不要返回一个巨大 dict，让调用者猜 `output` 是 scalar、waveform 还是错误字符串。

## 4. P1：日志和工件的工程化

### 4.1 Artifact manifest

每次操作建立 manifest（JSON）：

```json
{
  "schema_version": 1,
  "operation_id": "...",
  "started_at": "...Z",
  "ended_at": "...Z",
  "client": {"host": "...", "profile": "..."},
  "virtuoso": {"host": "...", "pid": 10797, "version": "..."},
  "target": {"lib": "...", "cell": "...", "view": "..."},
  "run": {"history": "Interactive.21", "test": "..."},
  "artifacts": [
    {"role": "maestro_setup", "path": "...", "sha256": "..."},
    {"role": "message_db", "path": "...", "sha256": "..."},
    {"role": "spectre_log", "path": "...", "sha256": "..."}
  ],
  "diagnosis": {"status": "failed", "primary_source": "..."}
}
```

### 4.2 原始与规范化并存

- raw：原始 XML、SKILL、log、SQLite、netlist、command；
- normalized：事件 JSONL、setup summary、error classification、semantic diff；
- derived：报告、plot、CSV、LLM context。

derived 文件可以重生成，raw 不覆盖。这个分层也能解决未来 AI agent 需要“先看摘要、再按证据钻取”的问题。

### 4.3 失败不是布尔值

至少区分：

```text
transport_error
preflight_conflict
modal_dialog_blocked
skill_error
netlist_error
license_error
simulator_error
convergence_failure
partial_artifact
timeout_unknown
success_with_warnings
success
```

`result.data` 非空不能证明成功；raw directory 存在也不能证明 run 成功。退出码、日志终止标记、结果 DB 状态、artifact completeness 要共同参与分类。

## 5. P1：GUI、modal dialog 与 event loop

Virtuoso 是 GUI application，CIW 和 modal dialog 会影响整个 SKILL channel：

- 一次 `maeMakeEditable()` 可能弹 ASSEMBLER dialog，使后续 RPC 全部 timeout；
- `hiGetCurrentWindow()` 在窗口 churn 后可能不是用户想要的窗口；
- `printf` 在 `evalstring` 下有缓冲行为，不能当 RPC 返回；
- X11 dismiss 是恢复路径，不应成为正常业务流程；
- `open_session`/background 适合 config，不适合依赖 callback/GUI 结果的真实 simulation。

建议实现 `GuiHealth`：

```text
last_successful_skill_at
current_ciw_reachable
current_window_candidates
modal_window_candidates
last_dialog_action
session_titles (Editing/Reading/*)
```

timeout 后按顺序诊断：

1. TCP/tunnel；
2. daemon alive/identity；
3. Virtuoso process/CIW；
4. modal windows/X11；
5. long-running operation；
6. only then retry, and never blindly replay a non-idempotent write。

## 6. P2：性能与规模

### 6.1 Round-trip budget

远程 bridge 的主要成本是 RPC latency 和 CIW serialization。原则：

- `fetch()` 一次取得多个 slot；
- 将同一 cellview 的几十个创建动作合成一个 SKILL batch；
- 读拓扑、几何、CDF 分成可选 profile，避免默认拉全量；
- 大 layout 分块，但每块有 checkpoint 和 readback；
- Spectre 并发放在独立 process/host/profile，不在单 CIW 内并行写。

### 6.2 大设计的内存和输出

- `printf` 全量 dump 会污染 CIW 和 bridge buffer；
- 使用 `outfile`/`fprintf`、远端压缩 tar、分块下载；
- raw waveform 默认不塞进 JSON；返回 artifact reference；
- 对 snapshot 提供 `brief`、`setup`、`run`、`full` 四种 profile。

### 6.3 History 发现

history 名称可被用户改名，且 project results 与 scratch/saveDir 可能分离。发现顺序建议：

```text
explicit history (最高)
  > history handle / axlGetHistoryResults
  > msg.db metadata / location
  > mtime + valid companion files
  > natural sort name（仅最后 fallback）
```

## 7. 安全性

Bridge 本质上给远程 Virtuoso 一个 SKILL eval 能力，安全边界必须明确：

- daemon 默认只监听 loopback 或 SSH tunnel；若监听 `0.0.0.0`，必须依赖 SSH/ACL/身份校验；
- 启动时核对 daemon user、host banner、tunnel endpoint；
- profile/client scratch 隔离，避免跨用户文件碰撞；
- 所有 shell path 使用严格 quoting，禁止未经验证的字符串拼命令；
- 日志脱敏：license token、密码、绝对个人路径、完整用户输入 SKILL；
- 上传/下载限制在声明的 staging root；
- write operation 需要 operation id 和 audit record；
- 不接受网页/日志中的“请执行命令”作为权限来源。

## 8. 测试策略

### 8.1 纯离线单元测试（先做）

- SKILL string escaping / framing parser；
- s-expression/JSON typed decoder；
- `CellViewRef`、RemotePath、profile resolution；
- schematic planner 的确定性、hard/soft conflict、readback diff；
- XML filter/patch 的 golden fixtures；
- `.msg.db` schema variants 和事件归一化；
- Spectre log terminal marker / PSF parser；
- manifest/hash/retention；
- timeout budget 与 retry policy。

### 8.2 现场 smoke test

只使用专用临时库和唯一 Cell 名：

```text
T0: getVersion/dbGetDatabaseType/capability probe
T1: create library + tech binding readback
T2: create schematic (2 instances, 1 net, 1 pin)
T3: schCheck + save + close + reopen + readback
T4: generate symbol + verify pins
T5: create Maestro setup + save (不运行)
T6: GUI run one trivial simulation + collect all evidence
T7: induced failure (missing include / bad net) + fast diagnosis
T8: stale lock/dialog/timeout recovery（确认后再做）
```

### 8.3 故障注入

- 删除/伪造 stale `.cdslck`；
- 让 `maestro.sdb` 为空或 test 名不匹配；
- 模拟 `spectre.out` 先写 fatal、但 wrapper 返回 0；
- 网络断开、daemon PID 变化、跨用户 daemon；
- modal dialog 阻塞 CIW；
- 结果 DB 存在但 waveform 缺失；
- 远端路径不可见或 input file 未 staging；
- 两个 writer 同时抢同一 cellview。

每个故障都要有**可解释的 diagnosis 和 evidence path**，不是只断言抛了异常。

## 9. 建议的最小公共接口

这是研究阶段的接口草案，不要求一次实现全部：

```python
@dataclass(frozen=True)
class CellViewRef:
    lib: str
    cell: str
    view: str
    view_type: str | None = None

@dataclass(frozen=True)
class RunRef:
    history: str
    test: str | None = None
    point: str | None = None
    corner: str | None = None

class VirtuosoRuntime:
    def probe(self) -> CapabilityReport: ...
    def read_cellview(self, ref: CellViewRef, *, profile="topology"): ...
    def apply_schematic(self, intent, *, mode="append") -> OperationResult: ...
    def edit_maestro(self, intent, *, session_mode="background") -> OperationResult: ...

class ArtifactStore:
    def collect(self, run: RunRef, *, policy) -> ArtifactManifest: ...
    def read_log_events(self, manifest) -> list[LogEvent]: ...

class RunObserver:
    def start(self, request) -> RunHandle: ...
    def wait(self, handle, *, timeout) -> RunDiagnosis: ...
```

接口设计原则：

- domain intent 不包含 socket/SSH/GUI 细节；
- transport 结果与 Cadence semantic result 分开；
- `OperationResult` 永远有 diagnostics/raw refs；
- 读取接口可指定“raw / normalized / both”；
- write 默认 dry-run/preflight 可单独执行；
- 不把特定 PDK 或 IC ISR 的 workaround 泄漏到核心模型。

## 10. 实施路线

### Phase 0：基线与契约

- 固定 Python/uv 环境和最小 import；
- 标记当前工作树已有删除/未跟踪变更，不在研究阶段恢复源码；
- 建立 capability、CellViewRef、OperationResult、manifest schema；
- 把本目录 research 的事实转成 fixtures。

### Phase 1：只读垂直切片

- `probe`、library/cell/view 枚举；
- schematic topology/CDF readback；
- Maestro setup raw snapshot；
- log path discovery + msg.db/spectre parser；
- 只读 CLI/MCP/Harness 共享 registry（可复用已有三接口研究）。

### Phase 2：安全 schematic 写入

- create/modify 明确模式；
- batch operation；
- schCheck/save/close/readback；
- 一个 PDK master adapter；
- symbol generation and verification。

### Phase 3：Maestro setup 与 run observer

- background config writer；
- GUI session lifecycle；
- callback + marker + log observer；
- history exact binding；
- Detail CSV/scalar/waveform 三种消费接口。

### Phase 4：工件与可复现

- raw/normalized/derived tree；
- manifest/hash/retention；
- failure diagnosis；
- remote split-root and host role validation；
- replay/compare report。

### Phase 5：扩展能力

- layout/PCell/ROD；
- config hierarchy clone；
- parallel Spectre pools；
- XStream/DRC/LVS/AMS；
- multi-version compatibility matrix；
- policy-controlled XML fallback。

## 11. Definition of Done（MVP）

一个 MVP 不需要支持全部 Virtuoso，但必须满足：

- 对一个专用临时库能创建并读回 schematic；
- 能检测并报告外部锁，而不是覆盖；
- `schCheck` 失败不会被当作成功；
- 运行失败时 30 秒内（或配置的 poll interval 内）指出 primary evidence，而不是等满总 timeout；
- 结果路径在 project root 与 simulation/saveDir 分离时仍能发现；
- 每次 run 有 history/test/point/corner 关联；
- raw log、setup、command、version 和 normalized diagnosis 可一起交付；
- 重复执行相同 intent 要么幂等，要么明确返回 conflict；
- 测试可在无 Virtuoso 环境下覆盖 parser/planner/manifest，在有 Virtuoso 时只跑少量 smoke。

## 12. 尚待实测的问题

这些问题不应在重构中凭记忆假定，需建立版本化实验：

1. 不同 IC6.1.8 ISR、IC23.1 对 `mae*`/`asi*` 的实际 capability 差异；
2. `maestro.sdb`/`active.state` 在不同 ADE 类型和只读 `saveDir` 下的落盘策略；
3. `msg.db` 是否在运行中安全支持 WAL/backup，以及各版本 schema 差异；
4. GUI session 与 background session 在 corner/model/PSS/pnoise 等高级分析的可写边界；
5. 各 PDK CDF callback、PCell super master、bus/pin order 和 netlist mapping；
6. 远端 `ipcBeginProcess` 的 host/path 环境、license、shell 初始化差异；
7. X11 dialog recovery 在 Xvfb、xrdp、Wayland/无 GUI 环境的替代方案。

## 13. 关键参考

- `../../README.md`：整体架构、远程角色、snapshot 说明
- `../../AGENTS.md`：首次检查、环境、锁/日志/`system()` gotchas
- `../../CONTEXT.md`：GUI/daemon/deploy/spectre host 术语
- `../../docs/adr/0001-explicit-remote-host-roles.md`
- `../../docs/adr/0002-deterministic-schematic-planner.md`
- `../../skills/virtuoso/SKILL.md`
- `../../skills/virtuoso/references/cellview-on-disk-layout.md`
- `../../skills/virtuoso/references/schematic-python-api.md`
- `../../skills/virtuoso/references/maestro-python-api.md`
- `../../skills/virtuoso/references/maestro-skill-api.md`
- `../../skills/virtuoso/references/simulation-flow.md`
- `../../skills/virtuoso/references/troubleshooting.md`
- `../../skills/spectre/SKILL.md`
- `../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il`
- `../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge_daemon_3.py`
- `../../src_bak/virtuoso_bridge/virtuoso/maestro/reader/snapshot.py`
- `../../src_bak/virtuoso_bridge/virtuoso/maestro/writer.py`

### Cadence 本地文档

- `C:\Users\user\Desktop\doc\skdfref\chap2.html` / `cvio.html`
- `C:\Users\user\Desktop\doc\caiuser\chap8.html` / `chap11.html`
- `C:\Users\user\Desktop\doc\wincfg\gettingStarted.html`
- `C:\Users\user\Desktop\doc\maeSKILLref\maestroSKILL.html` / `runRelated.html`
- `C:\Users\user\Desktop\doc\skipcref\ipcskill_re_ipcBeginProcess.html`
- `C:\Users\user\Desktop\doc\spectreref\chap2.html`

## 14. 证据定位（便于复核）

| 方向 | 证据 |
|---|---|
| 远程角色、VirtuosoClient/Spectre/SSH 分层 | `../../README.md:318-330`；`../../CONTEXT.md` |
| bridge 的 IPC framing、`progn`、stderr/banner/stats | `../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il`（对应 `RBIpcDataHandler`、`RBIpcErrHandler`、`RBIpcFinishHandler`、`RBStart`）；`git show HEAD:src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge.il` |
| daemon watchdog、STX/NAK/RS、banner | `../../src/virtuoso_bridge/virtuoso/basic/resources/ramic_bridge_daemon_3.py:101-225`、`:245-294` |
| split host / scratch / client isolation | `../../src/virtuoso_bridge/transport/remote_roles.py`、`remote_paths.py`、`../../docs/adr/0001-explicit-remote-host-roles.md` |
| deterministic schematic planner | `../../docs/adr/0002-deterministic-schematic-planner.md` |
| 三接口单注册表 | `three-interface-report.md` |
| 数据、锁、Maestro、原理图约束 | `01-virtuoso-data-model-and-editing.md` |
| 日志、artifact、observer 约束 | `02-virtuoso-logging-and-observability.md` |
| Cadence DFII/OpenAccess 与生命周期 | `C:\Users\user\Desktop\doc\skdfref\chap2.html:156-165`、`cvio.html:2375-2495` |
| Cadence GDM checkout/checkin 抽象 | `C:\Users\user\Desktop\doc\caiuser\chap8.html:119-176` |
| Cadence IPC 子进程日志/状态 | `C:\Users\user\Desktop\doc\skipcref\ipcskill_re_ipcBeginProcess.html`；`ipcGetExitStatus`、`ipcIsAliveProcess`、`ipcWait` More Info |
| Spectre/结果路径 | `C:\Users\user\Desktop\doc\spectreref\chap2.html:177-213`；`adexl/appEnvVars.html:10088-10098` |
