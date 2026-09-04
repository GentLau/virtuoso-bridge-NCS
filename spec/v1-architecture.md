# v1 三层架构规范

> 版本：Draft v1  
> 日期：2026-09-04  
> 状态：提案，作为下一阶段重构的接口基线；实现前允许通过评审修改。  
> 关联：[Spec 索引](README.md)、[接口协议](protocol-v1.md)

## 1. 范围与目标

本规范定义 `virtuoso-bridge-NCS` 的逻辑分层、进程边界和中层对上层提供的最小运行时能力。它不定义 schematic、layout、Maestro 或 Spectre 的全部领域 API；这些 API 属于上层业务模块，必须建立在本规范的中层端口之上。

本版的核心目标是：

> 上层只表达业务意图和消费结果；中层负责把三类操作投送到业务服务器；底层只在 Virtuoso 内执行 Skill。

三层是**逻辑边界**，不是强制的进程边界。v1 可以把上层和中层编译在同一个 Python 进程中；未来也可以把中层做成独立服务，只要对上仍实现同一组三端口契约。

“上层运行在哪里”不是业务语义的一部分。上层可以运行在开发者电脑、业务服务器、CI runner 或另一台控制机；只要能创建中层 runtime，就应看到相同的三个接口和相同的结果语义。

## 2. 术语

| 术语 | 定义 |
|---|---|
| **上层** | 业务/领域层，以及 CLI、MCP、Harness 等适配器。负责表达设计意图、组织流程、校验业务语义和消费结果。 |
| **中层** | Business Server Runtime。负责将 Skill、命令和文件操作投送到正确的执行位置，隐藏 local/SSH 和拓扑细节。 |
| **底层** | Resident Virtuoso Daemon。加载在 Virtuoso CIW 中，由 SKILL bridge 和其拥有的 helper daemon 构成；只执行 Skill。 |
| **调用方** | 运行上层 Python 代码的进程/机器。可以与业务服务器相同，也可以不同。 |
| **业务服务器** | 上层看到的逻辑执行环境。它不是必然对应一台物理机；中层可以把 Skill、命令和文件分别路由到不同角色主机。 |
| **Skill** | 在 Virtuoso CIW/DFII 数据库上下文中执行的 SKILL 表达式或脚本。 |
| **RunCommand** | 在业务服务器命令环境中执行 shell/命令行脚本。它不是 Skill，也不通过 CIW 执行。 |
| **ServerPath** | 业务服务器文件命名空间中的路径；不携带 SSH、host 或 tunnel 信息。 |
| **LocalPath** | 调用方文件系统中的路径。这里的“local”是相对于中层调用进程，而不是固定的开发者电脑。 |
| **daemon host** | 底层 Skill daemon 实际监听/运行的主机。 |
| **command host** | `RunCommand` 实际执行的主机。v1 默认使用现有 `deploy_host`/`VB_DEPLOY_HOST`。 |
| **file host** | `File` 操作中 `ServerPath` 所属的主机。v1 默认与 command host 相同。 |
| **GUI host** | 拥有 Virtuoso CIW/X11 窗口的主机，通常也是底层 SKILL bridge 的父进程主机。 |
| **runtime purpose** | runtime 创建时选择的逻辑用途（例如 `business`、`spectre`），只影响中层默认 command/file 路由，不是物理 host。 |

“本地模式”和“SSH 模式”是中层的部署方式，不是上层业务概念。上层不能根据 `is_remote`、端口号、SSH runner 是否为空等属性改变业务逻辑。

## 3. 总体架构

```text
┌─────────────────────────────────────────────────────────────────────┐
│ 上层：Domain / Product                                              │
│                                                                     │
│ schematic · layout · maestro · library · symbol · spectre          │
│ CLI · MCP · Harness · tests                                         │
│                                                                     │
│ 只依赖 BusinessRuntime 的三个端口                                   │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                                 │ 仅允许 Skill / RunCommand / File
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 中层：Business Server Runtime                                      │
│                                                                     │
│ 端口 1 SkillExecutor      → 路由到 daemon endpoint                 │
│ 端口 2 CommandExecutor     → local subprocess 或 SSH                │
│ 端口 3 FileOperator        → local copy 或 SCP/tar/Paramiko          │
│                                                                     │
│ topology / profile / env / tunnel / host roles / path mapping       │
│ timeout budget / retry / staging / digest / diagnostics             │
└───────────────────────┬───────────────────────┬─────────────────────┘
                        │                       │
       Skill only      │                       │ command + files
                        │                       │
                        ▼                       ▼
        ┌────────────────────────┐    ┌──────────────────────────────┐
        │ 底层：Virtuoso          │    │ 业务服务器命令/文件环境       │
        │ CIW resident bridge     │    │ Spectre / spiceIn / strmOut  │
        │ + helper daemon         │    │ Python / shell / logs         │
        │                         │    │                              │
        │ evalstring(SKILL)       │    │ 不依赖 Virtuoso daemon        │
        │ db/mae/sch/layout APIs  │    │                              │
        └────────────────────────┘    └──────────────────────────────┘
```

### 3.1 三条数据流

```text
上层 ──execute_skill──> 中层 ──TCP 直连/SSH tunnel──> 底层 ──evalstring──> CIW
上层 ──run_command────> 中层 ──本地 subprocess/SSH──> command host shell
上层 ──upload/download─> 中层 ──local copy/SCP/tar──> file host filesystem
```

三条流可以落在同一台机器，也可以落在不同机器；中层必须保持它们的语义一致。底层永远不接管第二、第三条流。

### 3.2 三个端口总览

| 端口 | 输入 | 实际执行位置 | 输出 | 禁止的隐式行为 |
|---|---|---|---|---|
| `SkillExecutor` | SKILL 文本、deadline | Virtuoso CIW（经底层 daemon） | `SkillResult`，含 raw SKILL output | Skill 失败时退回 shell；把 CIW `printf`当 output |
| `CommandExecutor` | command text、可选 `cwd/env`、deadline | runtime 绑定的业务 command host | `CommandResult`，含 exit code/stdout/stderr | 送入 CIW `csh/system`；失败后盲目重跑 |
| `FileOperator` | `LocalPath ↔ ServerPath`、递归/覆盖/校验策略 | runtime 绑定的业务 file host | `FileTransferResult`，含 digest/诊断 | 以 `scp/rm/cp` 字符串替代 File port；混淆两侧路径 |

三条边界的精确方法签名、字段和 framing 见规范正文 [protocol-v1.md](protocol-v1.md)。

## 4. 分层职责

### 4.1 上层职责

上层 MUST：

1. 用领域对象表达意图，例如 `SchematicPlan`、`MaestroSetupRequest`、`RunRequest`；
2. 通过注入的三个端口调用中层；
3. 对 SKILL 返回的 `nil`、命令返回码、文件传输状态做领域语义判断；
4. 在需要时组合三类操作，例如先 `upload_file`，再 `run_command`，再 `execute_skill`；
5. 保存或消费中层返回的 raw output、stdout、stderr、诊断和工件引用；
6. 保持操作可重放或明确声明不可重放。

上层 MUST NOT：

- 读取或解析 `VB_*` 环境变量来决定路径；
- 直接导入 `SSHClient`、`SSHRunner`、Paramiko、OpenSSH、`subprocess`、socket tunnel 实现；
- 直接拼接 SSH 命令、SCP target 或 jump host 参数；
- 通过 `execute_skill("csh(...)"/"sh(...)"/"system(...)")` 执行本应属于 `RunCommand` 的业务命令；
- 依赖底层 STX/NAK/RS framing；
- 把 `dbObject`、session handle 或物理 host 当作跨请求的稳定业务 ID；
- 在没有领域确认的情况下重放可能已产生副作用的请求。

### 4.2 中层职责

中层 MUST：

1. 根据配置解析 local/SSH 模式和 host roles；
2. 提供三个上层端口，并保证调用方看不到物理路由；
3. 将 Skill 路由到正确的底层 daemon；
4. 将 RunCommand 路由到 command host；
5. 将 ServerPath 路由到 file host；
6. 管理 tunnel、底层 setup 部署、daemon identity 和健康检查；
7. 实施统一 timeout budget、有限重试和 staging/校验；
8. 返回结构化结果，不吞掉 stdout、stderr 或原始 SKILL 输出；
9. 对传输失败、命令失败、Skill 失败、文件校验失败分别分类；
10. 记录足够的 transport/audit metadata，但默认不把物理拓扑泄漏给领域代码。

中层 MAY 使用 persistent shell、OpenSSH ControlMaster、Paramiko、多路复用、tar pipe 等优化，但这些属于实现细节，不得改变端口语义。

中层 MUST NOT：

- 把 transport 失败静默降级到另一种模式；
- 在已不确定命令是否执行后自动重放非幂等命令；
- 以“目标文件存在”单独证明上传成功；
- 把 `returncode == 0` 单独当作长任务成功；
- 把 `VirtuosoClient.run_shell_command` 这类 CIW 内 shell 调用当作正式 RunCommand 实现。

### 4.3 底层职责

底层 MUST：

1. 在 Virtuoso CIW 中执行 SKILL；
2. 管理与 CIW 的内部 IPC（当前使用 `ipcBeginProcess`）；
3. 将一次 Skill 请求的结果、错误和超时返回给中层；
4. 对同一 CIW 的 Skill 执行进行串行化；
5. 提供 daemon identity/banner 和基本存活信息；
6. 在 Virtuoso 退出、daemon 异常或 watchdog 触发时清理自身状态。

底层 MAY：

- 使用 `ramic_bridge.il` 作为 CIW 侧 resident code；
- 使用 Python helper daemon 作为 TCP/IPC 适配器；
- 使用内部 marker、identity 文件和 stderr stats；
- 为 Skill 脚本创建临时文件。

底层 MUST NOT：

- 提供任意 shell command API；
- 提供业务文件上传/下载 API；
- 直接管理 Spectre、`spiceIn`、XStream、DRC/LVS 等命令行程序；
- 替上层决定业务服务器、PDK 或结果目录；
- 将 CIW 的 `printf` 输出当作稳定 RPC 返回值。

## 5. 建议的代码布局与归属

逻辑分层不要求立刻重排全部目录，但新代码建议按下面的归属组织：

```text
src/virtuoso_bridge/
├─ contracts/                         # 跨层稳定契约（无 transport 实现）
│  ├─ ports.py                        # SkillExecutor / CommandExecutor / FileOperator
│  ├─ results.py                      # SkillResult / CommandResult / FileTransferResult
│  ├─ errors.py                       # Diagnostic / 领域无关异常
│  └─ paths.py                        # ServerPath / LocalPath 约定
├─ runtime/                           # 中层 BusinessRuntime 组合与 mode backend
│  ├─ business_server.py              # RuntimeSessionFactory / route selection
│  ├─ local_backend.py                # local command/file/skill wiring
│  └─ ssh_backend.py                  # SSH/tunnel/role wiring
├─ transport/                         # 中层内部实现
│  ├─ ssh.py                          # SSHRunner
│  ├─ tunnel.py                       # SSHClient、daemon deployment/tunnel
│  └─ transfer.py                     # staging、tar、atomic install、digest
└─ virtuoso/
   ├─ basic/bridge.py                 # 中层的 Skill TCP client（不是 resident daemon）
   ├─ basic/resources/                # 底层 ramic_bridge.il + helper daemon
   ├─ schematic/ layout/ maestro/…    # 上层领域服务
   └─ ...
```

当前已有的 `models.py` 可以在迁移期继续存放兼容模型；新端口应从 `contracts/` 导出，避免领域模块反向 import `transport`。`virtuoso/basic/bridge.py` 虽然路径位于 `virtuoso` 下，但其职责是“连接底层”的中层适配器；真正运行在 Virtuoso 内的是 `resources/ramic_bridge.il` 和 daemon 文件。

### 5.1 配置归属

以下配置只能由中层读取和解释：

| 配置 | 中层用途 |
|---|---|
| `VB_REMOTE_HOST` | 一主机兼容 fallback |
| `VB_GUI_HOST` | CIW/X11 目标 |
| `VB_DEPLOY_HOST` | setup、脚本、文件目标 |
| `VB_DAEMON_HOST` | Skill daemon/tunnel 目标 |
| `VB_SPECTRE_HOST` | standalone Spectre command 目标 |
| `VB_JUMP_HOST` | SSH 路由，不是业务目标 |
| `VB_REMOTE_USER`、端口和 SSH backend | 连接实现细节 |
| `VB_REMOTE_SCRATCH_ROOT`、client/profile id | staging 隔离 |

上层只通过中层入口获得绑定 token 的 `BusinessSession`；不直接调用 `load_dotenv` 或读取上述变量。runtime 的创建/注册表细节属于中层。

## 6. 上层依赖规则

依赖方向必须单向：

```text
上层 domain ──> contracts/ports ──> 中层 runtime ──> transport/bottom adapter
```

禁止反向依赖：

```text
上层 domain ──X──> transport.ssh / paramiko / subprocess / ramic wire
底层 ──X──> 上层 schematic/layout/maestro domain
```

领域模块应通过构造函数注入端口：

```python
class SchematicService:
    def __init__(self, runtime: BusinessRuntime) -> None:
        self.runtime = runtime

    def inspect(self, lib: str, cell: str) -> dict:
        result = self.runtime.skill.execute_skill(self._read_skill(lib, cell))
        # 领域层只处理 SkillResult，不访问 SSH/tunnel
        return self._decode_readback(result)
```

测试时可以注入 fake runtime；fake 不需要 Virtuoso、SSH 或本地 shell，即可测试 planner、解析和业务校验。

## 7. “业务服务器”抽象

### 7.1 v1 必须补齐的 Local backend

当前代码已经有 local Skill TCP 连接和 local 文件 copy 分支，但 `SSHClient.run_command()` 在 local mode 下会因为没有 deployment runner 而报 “Deployment SSH runner is unavailable in local mode”。这不是目标架构允许的行为，而是重构前需要关闭的实现缺口。

v1 必须提供与 SSH backend 对等的本地实现：

```text
LocalSkillClient      → 127.0.0.1:<daemon-port> TCP
LocalCommandRunner    → subprocess（调用方所在机器 = 逻辑业务服务器）
LocalFileOperator     → staged copy / atomic replace
```

Local backend 与 SSH backend 的差异只能存在于中层内部。上层不能为了绕过该缺口而调用 `csh()`、直接 `subprocess` 或直接 `shutil`。

### 7.2 为什么不能只定义一个 remote host

现有设计已经支持 GUI、deployment、daemon、Spectre 分离：

```text
GUI host       → CIW/X11
Deploy host    → setup/脚本/输入文件部署
Daemon host    → ipcBeginProcess helper 与 Skill tunnel endpoint
Spectre host   → standalone Spectre
```

因此 `VB_REMOTE_HOST` 只能作为兼容 fallback，不能作为上层的物理真相。中层可以内部解析以下逻辑目标：

```text
skill_target   = daemon endpoint
command_target = business command host
file_target    = business file host
```

v1 默认映射：

```text
command_target = deploy_host || remote_host
file_target    = deploy_host || remote_host
skill_target   = daemon_host || remote_host
```

若未来需要命令和文件位于不同主机，再增加中层配置字段；不改变上层端口。若需要另一个逻辑执行域（例如 standalone Spectre），由入口创建 `purpose="spectre"` 的 runtime；中层把该 runtime 的 Command/File 映射到 `spectre_host`，Skill 仍只连接 daemon target；不把物理 host 传入业务调用。

### 7.3 路径语义

- `LocalPath` 永远由调用方解释，中层不得把它当业务服务器路径；
- `ServerPath` 永远由中层解释，中层不得把它交给本地 Python 文件 API（local mode 除外）；
- v1 的 `ServerPath` 表示 runtime 选定的**业务文件命名空间**；它不是 SSH URL，也不是带 host 的物理路径；
- 对默认 business runtime，若同一 ServerPath 要在 File/RunCommand 与 Skill 之间复用，中层 MUST 确认它对 command/file target 和 CIW/daemon target 都可见；
- 如果 split-host 没有共享目录，中层 MUST 返回 `PATH_NOT_VISIBLE`，不得悄悄改写路径或隐式复制；
- `ServerPath` 的格式是目标命令/文件主机接受的原生路径，v1 远端 POSIX 路径使用 `/`；
- 文件接口 v1 SHOULD 使用绝对 `ServerPath`，避免工作目录不明确；
- `run_command(cwd=...)` 的 `cwd` 是 ServerPath；
- Skill 字符串中的路径属于 SKILL 语义，不能由中层自动把 `ServerPath` 替换成 LocalPath；需要转移文件时，上层必须显式调用 File port。

## 8. 运行模式

### 8.1 Local mode

中层配置为 local 时：

- `RunCommand` 在中层所在操作系统启动本地子进程；
- `File` 使用本地文件复制/原子安装；
- `Skill` 连接本机 loopback 上的底层 daemon；
- 不创建 SSH tunnel，不读取 SSH host/user/jump；
- 仍然执行相同的 timeout、结果、digest 和错误分类契约。

Local mode 不意味着底层 daemon 可以省略。若 Virtuoso 没有加载 `ramic_bridge.il` 或 daemon 未启动，Skill port 必须返回明确的 `daemon_unavailable`，而不是退回执行本地 shell。

### 8.2 SSH mode

中层配置为 SSH 时：

- `RunCommand` 通过 role-specific SSH runner 执行；
- `File` 通过 role-specific upload/download runner 执行；
- `Skill` 通过 SSH local forward 连接 daemon host 的 daemon port；
- 中层负责在 GUI/deploy host 部署底层 setup 文件，并校验 daemon banner 与 tunnel endpoint；
- jump host 只属于中层路由，不能出现在上层业务对象中。

### 8.3 Split-host mode

Split-host 是 SSH mode 的一个拓扑变体，不增加上层接口。中层必须验证：

1. deployment root 对 GUI host 和 daemon host 可见；
2. Skill setup 中引用的 helper 路径在 daemon host 可执行；
3. ServerPath 实际落在 file/command host；
4. daemon identity 的 host 与 tunnel endpoint 一致；
5. 不同 role 的 SSH 失败不会被误报为同一种错误。

## 9. 典型业务流程

### 9.1 读取 schematic

```text
上层构造 read-only SKILL
  → Skill port
  → 底层 dbOpenCellViewByType(... "r")
  → 返回 raw s-expression / readback
  → 上层解析并生成领域模型
```

### 9.2 修改 schematic

```text
上层构造 SchematicPlan
  → Skill port 批量提交 DFII 操作
  → 底层执行 dbCreate*/schCreate*
  → Skill port 执行 schCheck + dbSave
  → Skill port 重新 readback
  → 上层做 semantic diff
```

中层只负责投送 Skill；“是否应保存、是否算成功”由上层业务策略和 Skill 结果共同决定，但中层必须报告 transport/evaluation 状态。

### 9.3 运行命令行工具

```text
上层 upload_file(input.scs, /run/<id>/input.scs)
  → 中层把文件放到 file host
上层 run_command("spectre ...", cwd=/run/<id>)
  → 中层在 command host 执行
上层 download_file(/run/<id>/spectre.out, artifacts/spectre.out)
  → 中层返回文件校验结果
```

如果命令是长任务，上层必须按日志/marker/artifact 观察；不能因为 SSH session 返回 0 就跳过结果验证。

### 9.4 配置 Virtuoso/Maestro

- `mae*`、`db*`、`sch*` 等 Virtuoso API 走 Skill port；
- 运行 Spectre、`spiceIn` 或其他外部工具走 RunCommand；
- 读取/保存远端 XML、netlist、log、SQLite 走 File port；
- 不能用一条 `execute_skill("system(...)")` 把三个端口合并成一条隐式通道。

### 9.5 跨端口文件可见性

```text
上层本地文件
   │ File.upload
   ▼
业务 ServerPath（由中层分配/验证）
   ├─ RunCommand 可以访问
   └─ Skill 只有在 shared visibility 成立时才可以访问
```

例如上层上传 `.il` 后要求 Virtuoso `load()`：中层不能假设 command host 的 `/tmp/x.il` 对 CIW 可见；应使用共享 staging 路径，或由上层先上传到 runtime 分配的可见路径。路径验证失败必须是显式诊断，不得把 `PATH_NOT_VISIBLE` 伪装成 Skill 语法错误。


## 10. 生命周期与所有权

### 10.1 中层 runtime

中层 runtime 由应用入口创建并拥有：

```python
with RuntimeSessionFactory.from_env() as runtime:
    service = SchematicService(runtime)
    service.run(...)
```

`close()` MUST：

- 停止中层拥有的 tunnel/persistent shell；
- 释放 SSH/Paramiko 会话；
- 不关闭不属于本 runtime 的 Virtuoso 进程；
- 不删除用户设计文件；
- 对临时 staging 做有界清理，保留失败证据路径。

### 10.2 底层 daemon

底层生命周期由 Virtuoso CIW 所有：

```text
load setup.il
  → RBStart（幂等）
  → daemon ready
  → accept Skill requests
  → RBStop / Virtuoso exit
```

重新加载 setup 不得在同一 CIW 中无条件启动第二个 daemon。若需要切换 profile/port，应先明确停止旧 daemon，再加载新 setup。

### 10.3 CellView 与 session

这是上层领域操作的约束，不由中层擅自简化：

- `r/a/w/s` 模式必须明确；
- `dbObject` 不能跨 `dbClose`/purge 使用；
- Maestro background session 用于配置读写，GUI session 用于本项目的可靠 simulation flow；
- 写操作必须处理 lock、`schCheck`、`dbSave` 和 readback；
- 中层只投送这些 Skill，不替领域层猜测 session 状态。

## 11. 可靠性原则

### 11.1 Timeout budget

调用方给出的 timeout 是端到端 wall-clock budget：

```text
T_total = T_route + T_connect + T_dispatch + T_execute + T_collect
```

中层必须将剩余 budget 传给下一阶段；不得每一阶段重新使用完整 timeout。超时返回时要包含 `phase`。

### 11.2 Retry

- 连接建立前的明确 transient SSH handshake 失败可以有限重试；
- 文件上传在尚未 publish 前可以重试；
- 只读 Skill 可以由上层明确标记后重试；
- 非幂等 Skill、命令一旦可能已执行，断线后不得自动重放；
- 结果为 `unknown` 时必须保留证据和恢复建议。

### 11.3 结果不可混淆

```text
transport_success ≠ command_success
transport_success ≠ skill_business_success
file_exists       ≠ file_verified
history_created   ≠ simulation_completed
```

上层必须有业务 postcondition；中层必须把原始结果和诊断完整返回。

### 11.4 三端口不是分布式事务

`upload_file → run_command → download_file` 或 `upload_file → execute_skill(load(...))` 不构成跨端口原子事务：

- 每个端口只对自己的单次操作负责；
- 中层不能在 command 已启动后回滚其副作用；
- 上层应使用唯一 operation/run id、staging 目录和 manifest 组织补偿；
- 发生中途失败时，必须返回已完成阶段和可保留的证据，而不是声称“全部回滚”。

## 12. 安全边界

- daemon 默认只绑定 loopback 或受 SSH tunnel 保护的地址；
- SSH/Paramiko 凭据只在中层存在；
- ServerPath、LocalPath、命令字符串必须经过路径/控制字符校验和 shell quoting；
- 上传/下载限制在配置允许的根目录或明确的 staging 区；
- 日志默认记录 command hash、长度、目标 role、request id，不记录完整敏感 SKILL；
- 需要保留 raw SKILL/命令时必须由 debug/audit 策略显式开启；
- 上层提供给模型的错误信息不能被当成新的执行授权。

## 13. 与现有实现的目标映射

| 目标概念 | 当前实现 | v1 处理 |
|---|---|---|
| Skill port | `VirtuosoClient.execute_skill()` | 保留行为；抽出 `SkillExecutor` protocol |
| Command port | `SSHClient.run_command()` / `SSHRunner.run_command()` | 作为中层正式实现；统一 local/SSH 结果 |
| File port | `SSHClient.upload_file()`、`download_file()`；`VirtuosoClient` 的 local 分支 | 移入中层 `FileOperator`；保留原子 staging/digest 行为 |
| Middle runtime | `SSHClient`、role runners、tunnel、transfer plans | 重组为注入式 `RuntimeSession`，不让 domain 依赖具体类 |
| Bottom resident code | `ramic_bridge.il` | 保留 CIW 侧职责，只暴露 Skill |
| Bottom helper | `ramic_bridge_daemon_3.py`、`ramic_bridge_daemon_27.py` | 保留为内部 helper；wire protocol 不泄漏到上层 |
| 领域操作 | `virtuoso.schematic/layout/maestro/...` | 改为依赖三个 port/facade，不直接依赖 transport |
| 兼容 facade | `VirtuosoClient.from_env()` / `from_tunnel()` | v1 作为 Skill/旧 facade；新入口使用 `RuntimeSessionFactory.from_env()`，逐步移除混合职责 |
| 旧错误路径 | `VirtuosoClient.run_shell_command()` | 标记 deprecated；不得作为正式 RunCommand |

## 13.1 现有领域代码中的中层泄漏点

重构时不能只新增一个 `BusinessRuntime` 名称，还要清理领域层对 transport 内部对象的直接依赖。当前旧实现中需要重点迁移的点包括：

| 现有位置 | 泄漏内容 | 目标改法 |
|---|---|---|
| `src_bak/virtuoso_bridge/virtuoso/maestro/writer.py` | 通过 `client.ssh_runner` 轮询 marker | 注入 `CommandExecutor`/`FileOperator` 或独立 `RunObserver` |
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/snapshot.py` | 直接区分 runner、拼远端 tar/scp 路径 | 由中层 File port 提供递归下载和 staging |
| `src_bak/virtuoso_bridge/spectre/runner.py` | 直接构造/持有 `SSHRunner` | 注入 purpose 绑定的 `CommandExecutor` + `FileOperator` |
| `src_bak/virtuoso_bridge/virtuoso/layout/streamout.py` | 直接访问远端 runner、自己处理 poll/日志 | 抽出中层 command/file port；领域层只保留 XStream 业务判定 |
| `src/virtuoso_bridge/virtuoso/basic/bridge.py` | Skill、文件转移、CIW shell 便利方法混在一个 facade | 以兼容 facade 委托三个 port；移除正式业务路径中的 `run_shell_command` |

验收标准中的“上层只依赖三个 port”必须通过静态依赖检查和 fake 测试验证，而不是只看类名。

## 14. 非目标

本版不承诺：

- 用中层替上层完成 schematic/layout/maestro 业务语义；
- 让底层 daemon 直接执行任意 shell；
- 在 OA、Maestro XML、SQLite、Spectre PSF 之间建立一个统一可写文件格式；
- 在多个 Virtuoso 实例之间共享 session/dbObject；
- 对所有 IC/ISR/PDK 自动推断可用 API；
- 为跨多个 cellview 的修改提供虚假的全局原子事务。

## 15. 验收标准

架构实现达到 v1 基线时，至少满足：

1. 上层测试可以只注入 fake `BusinessRuntime`，不安装 SSH/Virtuoso；
2. 同一领域调用在 local 与 SSH 两种 runtime 下不改变输入/输出模型；
3. `run_command` 的命令不会出现在 CIW/底层 daemon；
4. File port 的 ServerPath 不会被误当作调用方 LocalPath；
5. Skill port 失败不会触发隐式 shell fallback；
6. split-host 配置下 Skill、命令、文件可以分别路由且诊断可区分；
7. timeout、nonzero exit、SKILL error、transfer failure、unknown outcome 可分别识别；
8. 每个写操作能关联 request id、目标、前置/后置验证和原始证据；
9. 现有 `VirtuosoClient.execute_skill`、`SSHClient.run_command`、`upload_file`、`download_file` 可以通过兼容适配器继续工作；
10. 底层 daemon 不需要知道上层是 schematic、Maestro、Spectre 还是 CLI。

## 16. 参考

- [接口协议](protocol-v1.md)
- [项目 README](../README.md)
- [项目 AGENTS.md](../AGENTS.md)
- [项目 CONTEXT.md](../CONTEXT.md)
- [Virtuoso 数据与编辑调研](research/01-virtuoso-data-model-and-editing.md)
- [日志与可观测性调研](research/02-virtuoso-logging-and-observability.md)
- [重构关键技术点](research/03-rebuild-key-technical-points.md)
- [现有三接口研究](research/three-interface-report.md)
- [ADR 0001：远程角色](../docs/adr/0001-explicit-remote-host-roles.md)
- [ADR 0002：确定性原理图规划](../docs/adr/0002-deterministic-schematic-planner.md)
