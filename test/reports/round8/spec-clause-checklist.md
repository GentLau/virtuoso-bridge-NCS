# Spec 条款清单（第八轮覆盖矩阵的输入，机器抽取）

> 由 `test/shared/runners/extract_spec_clauses.py` 生成；每条都要在覆盖矩阵里给结论
> （✅有 TB 直接证据 / 🟡间接或历史 / ⬜缺口）。`kind=table-row` 是操作/字段/枚举表行，
> `kind=clause` 是规范性句式（必须/不得/默认/超时/并发…）。

## 总览/1-四层整体架构与接口.md（68 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 总览#004 | clause | 6 | 四层整体架构与接口 | > 状态：已冻结（接口唯一基线） |
| 总览#010 | clause | 18 | 1.1 总述 | - **中层**：负责路由与并发限流，把指令或文件正确地投送到指定位置，并返回可验证结果； |
| 总览#020 | clause | 31 | 1.1 总述 | 接口签名与返回、错误总则的唯一 owner 是本文 §4.1 / §4.5；其它文档只引用，不再复制清单。 |
| 总览#021 | clause | 33 | 1.1 总述 | 四层是职责边界，不要求每层都是独立进程。顶层、上层、中层可以位于同一进程；底层必须是 Virtuoso 可加载、可管理的常驻守护进程。 |
| 总览#022 | table-row | 37 | 1.2 术语 | \| 术语 \| 定义 \| |
| 总览#024 | table-row | 39 | 1.2 术语 | \| **顶层** \| HTTPServer：对外提供 API、接收请求并开线程池（每任务一个线程；池大小见[顶层补充 §5](../顶层/add-控制面与业务面.md)），不实现业务。 \| |
| 总览#025 | table-row | 40 | 1.2 术语 | \| **上层** \| 纯粹的封装层：把业务操作封装为调用中层五个业务接口的业务包；包含原理图、版图、TB、Maestro、库/符号、仿真（一次性 Spectre 命令封装）等模块。 \| |
| 总览#026 | table-row | 41 | 1.2 术语 | \| **中层** \| 路由与并发限流：向上层提供五个业务接口（见 §4.1）与只读查询 `query`（见 §4.2），隐藏本地/SSH、隧道、端口和主机拓扑。 \| |
| 总览#027 | table-row | 42 | 1.2 术语 | \| **底层** \| Virtuoso 常驻守护进程，由 Virtuoso 中加载的 SKILL bridge 和其启动的 `daemon.py` 组成，只处理 Skill。 \| |
| 总览#028 | table-row | 43 | 1.2 术语 | \| **Skill** \| 在 Virtuoso CIW 及其数据库上下文中求值的 SKILL 文本。 \| |
| 总览#029 | table-row | 44 | 1.2 术语 | \| **RunCommand** \| 在指定命令环境中运行的命令行指令，不通过 Virtuoso。 \| |
| 总览#030 | table-row | 45 | 1.2 术语 | \| **File** \| 调用方本地路径与业务服务器路径之间的上传、下载及必要校验。 \| |
| 总览#031 | table-row | 46 | 1.2 术语 | \| **业务服务器** \| 上层看到的逻辑执行环境，不一定对应一台物理主机。 \| |
| 总览#032 | table-row | 47 | 1.2 术语 | \| **指定位置** \| 中层根据 token 参数和路由选择的底层 Skill 端点、命令主机或文件系统。 \| |
| 总览#033 | table-row | 48 | 1.2 术语 | \| **token** \| 上层每次调用携带的寻址与授权参数；中层据此路由，不绑定会话对象。 \| |
| 总览#034 | table-row | 49 | 1.2 术语 | \| **endpoint** \| 一次 SSH 连接的目的地身份，由 `(host, user)` 加可达路径 `(jump, proxy)` 唯一确定；只表达“连到哪”，不携带 token，不携带预算。同一 token 内按 endpoint 去重复用连接，不同 token 即使 endpoint 相同也不共用连接。 \| |
| 总览#035 | table-row | 50 | 1.2 术语 | \| **CIW** \| Virtuoso 命令窗口，底层 Skill 的实际求值环境。 \| |
| 总览#056 | clause | 77 | 2.1 结构 | │  token 路由 · 并发限流 · 指令投送 · 文件传输 · 结果诊断           │ |
| 总览#094 | clause | 132 | 3.2 上层：封装业务复杂度 | 1. 业务参数校验、操作顺序和领域对象； |
| 总览#099 | clause | 142 | 3.3 中层：路由、投送和执行 | 五个请求类型分别投送到各自的 role（Skill→daemon、命令→command、文件→file、GUI→gui、Spectre→spectre）；**唯一映射与职责见[路由设计 §3](../中层/3-路由设计.md)**，本文不复制表格。 |
| 总览#103 | clause | 148 | 3.3 中层：路由、投送和执行 | - 为每个 token 维护线程池：一次未完成的调用占用一个线程，结果返回后线程回池，超限返回错误（预算与记账唯一口径：[并发设计 §2/§3](../中层/2-并发设计.md)）；统一处理连接生命周期、超时、错误分类和诊断信息； |
| 总览#110 | clause | 160 | 3.4 底层：连接端口与 Virtuoso | 4. 将 Skill 交给 Virtuoso 求值，并把结果或错误返回给中层。 |
| 总览#115 | clause | 170 | 3.5 依赖方向 | 顶层不直接访问中层/底层，经上层调用；顶层与上层之间领域方法不固定，调度机制固定（见[顶层 §2](../顶层/1-顶层.md)）。上层不能绕过中层直接连接底层或目标主机；中层不能把传输对象泄漏给上层；底层不能反向调用上层业务代码。 |
| 总览#144 | clause | 220 | 4.2 上层 ↔ 中层：query 只读查询 | - `role` 给定 → 只返回该 role 的事实；`name` 必须与 `role` 同给 → 只返回该 role 的该键（`root` / `display` / `bin` / 用户组名），未配置的键省略； |
| 总览#148 | clause | 224 | 4.2 上层 ↔ 中层：query 只读查询 | - 非法 `role`/`name` 取值 → 参数错误（`TypeError`/`ValueError`）； |
| 总览#159 | clause | 239 | 4.3 中层 ↔ 底层：Skill 投送接口 | `skill`、`timeout` 是现代码字段；`token` 是唯一新增**必填**字段；`log_level`/`log_max_bytes` 属于[日志返回设计标准](../底层/6-日志返回设计标准.md)的可选扩展字段。响应保持 `STX/NAK/RS` 帧，**当前唯一 payload 格式为 JSON**（格式、log 字段与 `off` 语义见日志标准，本文件不复制）： |
| 总览#164 | clause | 246 | 4.3 中层 ↔ 底层：Skill 投送接口 | 命令执行与文件操作不经过此接口。上层传入 token，中层转发给底层，底层校验 token；校验失败时不得接触 Virtuoso。token 到达 daemon 供校验，但不得进入 Virtuoso/SKILL 求值文本，也不回显给上层。 |
| 总览#175 | clause | 265 | 4.4 底层内部实现：连接 Virtuoso（非跨层接口 | 字节示例：成功 `02 33 1e`（`02`=STX，`33`=字符 `3`，`1e`=RS）；失败 `15 <错误文本> 1e`。 |
| 总览#178 | clause | 274 | 4.5 结果与错误合同（本版冻结） | 五个业务接口**对外一律返回结构化结果，不向上抛传输异常**。参数编程错误（token 缺失、类型错误）是调用方错误，允许直接抛出 `TypeError/ValueError`；运行期错误（unknown token、daemon NAK、文件失败、传输失败）必须封装为结果。 |
| 总览#179 | clause | 276 | 4.5 结果与错误合同（本版冻结） | `CommandResult` 增加稳定 `kind` 字段：`command`（真实命令）/ `timeout` / `transport` / `path` / `unknown-effect` / `rejected`（容量拒绝）/ `checksum`（文件摘要不一致）/ `invalid-token`（未知 token）；真实命令返回码即使等于 124/255 也保持 `kind=command`，桥保留码只在 `kind ! |
| 总览#180 | table-row | 278 | 4.5 结果与错误合同（本版冻结） | \| 情形 \| Skill (`VirtuosoResult`) \| 命令/文件/GUI/Spectre (`CommandResult`) \| |
| 总览#182 | table-row | 280 | 4.5 结果与错误合同（本版冻结） | \| 正常 \| `status=success`、`output`、`log` \| `kind=command`、`returncode=命令自身退出码`、`stdout/stderr` \| |
| 总览#183 | table-row | 281 | 4.5 结果与错误合同（本版冻结） | \| 超时 \| `status=error`、`errors=["SKILL execution timed out"]` \| `kind=timeout`、`returncode=124`、`stderr` 含超时说明 \| |
| 总览#184 | table-row | 282 | 4.5 结果与错误合同（本版冻结） | \| 传输失败（连不上/断连） \| `status=error`、`errors` 含 `Daemon connection failed` \| `kind=transport`、`returncode=255`（SSH/Paramiko 非零 rc；中层包装的异常以 `VB-TRANSPORT:` 开头） \| |
| 总览#185 | table-row | 283 | 4.5 结果与错误合同（本版冻结） | \| 路径不可见/文件缺失 \| 不适用 \| `kind=path`、`returncode≠0`、`stderr` 含 `VB-PATH-NOT-VISIBLE:` 或 SSH/SCP 的 no-such-file 诊断 \| |
| 总览#186 | table-row | 284 | 4.5 结果与错误合同（本版冻结） | \| 结果未知（可能已产生副作用） \| `status=error`、`errors` 含 `SKILL execution timed out`；**客户端超时不等于未投递** \| `kind=unknown-effect`、`returncode=255`、`stderr` 含 `VB-UNKNOWN-EFFECT:`，非幂等命令重复执行可能产生副作用；是否重试由上层业务操作自行决断 \| |
| 总览#187 | table-row | 285 | 4.5 结果与错误合同（本版冻结） | \| 容量拒绝（线程/通道超限） \| `errors` 含 `thread pool exceeded` / `channel budget exceeded` / `role max_sessions exceeded` 之一（指明哪一个） \| `kind=rejected`、`returncode=1`、`stderr` 含 `thread pool exceeded` / `channel budget exceeded` / |
| 总览#188 | table-row | 286 | 4.5 结果与错误合同（本版冻结） | \| 文件校验失败 \| 不适用 \| `kind=checksum`、`returncode=1`、`stderr` 含 `sha256 mismatch` \| |
| 总览#189 | table-row | 287 | 4.5 结果与错误合同（本版冻结） | \| unknown token \| `status=error`、`errors=["invalid token"]` \| `kind=invalid-token`、`returncode=1`、`stderr="invalid token"`（token 不发送给命令本体，但参与中层路由） \| |
| 总览#190 | table-row | 288 | 4.5 结果与错误合同（本版冻结） | \| Skill 求值错误 \| `status=error`、`errors=[...]` \| 不适用 \| |
| 总览#192 | clause | 291 | 4.5 结果与错误合同（本版冻结） | - Skill 超时与“结果未知”对外不可区分：一律视为结果未知；是否重试由上层业务操作自行决断；“投递前未投递可安全重试”仅为中层内部策略，不提供可观察的投递状态； |
| 总览#196 | clause | 300 | 4.6 文件执行合同（上传/下载，唯一 owner） | - **落盘**：先写入临时位置，**对临时文件做 SHA-256 校验通过后**才原子替换到目标；校验失败删除临时文件、目标不变；传输中途失败同样清理临时内容、不改动已有目标；目标已存在则**覆盖**； |
| 总览#204 | clause | 318 | 5.2 上层只面向逻辑业务服务器 | - 五个 role（gui/daemon/command/file/spectre）各自独立配置；能力与职责、接口映射与 endpoint 复用规则由[路由设计 §2–§4](../中层/3-路由设计.md)唯一 owner 定义，探测矩阵、部署与文件根见[多用户与注册 §4](../其他/1-多用户与注册.md)，本文不重复； |
| 总览#206 | clause | 320 | 5.2 上层只面向逻辑业务服务器 | - 同一 token 内按解析后的 endpoint 去重（唯一口径：[路由设计 §4](../中层/3-路由设计.md)）：每个 endpoint 一条业务连接 + remote daemon 的专用 Skill 隧道；跨 token 不共用； |
| 总览#208 | clause | 322 | 5.2 上层只面向逻辑业务服务器 | - 每个 role 有自己的文件根；根的回退、`~` 展开与相对路径解析的唯一 owner 是[多用户与注册 §4.2](../其他/1-多用户与注册.md)，本文不复制算法； |
| 总览#210 | clause | 327 | 5.3 中层保证“正确位置”和“可验证结果” | 中层不仅负责发送请求，还要确认请求对应的目标、执行阶段和结果。路径不可见、连接失败、命令非零退出、Skill 错误和文件校验失败必须能够区分。 |
| 总览#211 | clause | 331 | 5.4 底层最小化且一对一 | 底层只连接一个 Virtuoso 会话并执行 Skill，不扩展成通用远程命令代理。**一个 token = 一个活动 daemon = 一个 CIW**；不同 token 不得共享同一个底层 Skill 通道；需要第二个 CIW 必须注册第二个 user/token。 |
| 总览#212 | clause | 335 | 5.5 多用户隔离由中层负责 | 中层按 token 隔离 Skill 端点与命令通道；文件侧只提供“每用户默认目录”约定，**不提供安全沙箱**（见 §5.6）。预算与记账的唯一 owner 是[并发设计 §2/§3](../中层/2-并发设计.md)，连接复用拓扑见[路由设计 §4](../中层/3-路由设计.md)：本文只保留三条原则——**线程预算与最大通道数每 token 一份**、**单目标点通道上限按 endpoint**、**跨 token 永不共享** |
| 总览#215 | clause | 342 | 5.6 路径和位置语义明确 | - 各 role 的 `root` 只是该 role 的**默认工作目录约定**（部署文件、截图、日志、导入网表等），**不是沙箱**：文件操作允许访问业务服务器上任意可达路径；同 SSH 账号下不同 user 之间不承诺跨目录隔离，安全边界由 OS 账号权限提供； |
| 总览#216 | clause | 343 | 5.6 路径和位置语义明确 | - symlink、不存在的目标、覆盖目录按 OS 语义；目标不可见 → 结构化错误 `VB-PATH-NOT-VISIBLE`，不悄悄改写路径或隐式复制； |
| 总览#218 | clause | 348 | 5.7 单 CIW 串行，跨 CIW 并行 | 同一个 Virtuoso CIW 的 Skill 请求必须串行，不同底层会话可以并行；命令默认串行、`parallel=True` 显式并行，文件传输天然并行。排队闸门与超时语义见[并发设计 §1](../中层/2-并发设计.md)。 |
| 总览#219 | clause | 352 | 5.8 可靠性和可扩展性 | 五个业务接口调用使用端到端超时：单次调用默认 30s，连接建立默认 `runtime.connect_timeout=15s`；`timeout` 超出平台能力上限 → 参数错误，不夹紧（当前 Windows 上限 2_147_483s）；中层不得在内部阶段重新开始完整 timeout，子阶段只继承剩余预算。传输建连总尝试 ≤3 次（含初次），且只发生在确认未产生副作用的阶段（建连/握手）；错误分类与保留码见 §4.5。 |
| 总览#220 | clause | 354 | 5.8 可靠性和可扩展性 | **五业务接口 deadline 唯一表**（`timeout=None` 时；每个接口一次调用只有一条 deadline，下表各相位共享它）： |
| 总览#221 | table-row | 356 | 5.8 可靠性和可扩展性 | \| 接口 \| 默认预算 \| deadline 覆盖的相位（同一预算内顺序扣除，不重置；线程预算超限直接拒绝，不排队） \| |
| 总览#223 | table-row | 358 | 5.8 可靠性和可扩展性 | \| Skill 执行 \| 30s \| 线程预算占用（超限即拒绝） + **投递前按 token 排队** + 隧道建立 + TCP 连接 + daemon 执行 + log 第二帧 \| |
| 总览#224 | table-row | 359 | 5.8 可靠性和可扩展性 | \| 命令执行（默认串行） \| 30s \| 线程预算占用（超限即拒绝，不排队） + 等待该 token 的串行命令位 + 常驻 shell 内执行 \| |
| 总览#225 | table-row | 360 | 5.8 可靠性和可扩展性 | \| 命令执行（`parallel=True`） \| 30s \| 线程预算占用（超限即拒绝，不排队） + channel 记账 + 连接建立 + 一次性 exec \| |
| 总览#226 | table-row | 361 | 5.8 可靠性和可扩展性 | \| 文件执行（上传/下载） \| 30s \| 线程预算占用（超限即拒绝，不排队） + channel 记账 + 连接建立 + 传输 + 校验子命令 \| |
| 总览#227 | table-row | 362 | 5.8 可靠性和可扩展性 | \| GUI 命令执行 \| 30s \| 线程预算占用（超限即拒绝，不排队） + channel 记账 + 连接建立 + 一次性命令 \| |
| 总览#228 | table-row | 363 | 5.8 可靠性和可扩展性 | \| Spectre 命令执行 \| 30s \| 线程预算占用（超限即拒绝，不排队） + channel 记账 + 连接建立 + 一次性命令 \| |
| 总览#229 | clause | 365 | 5.8 可靠性和可扩展性 | - `runtime.connect_timeout`（默认 15s）是**该预算内的子预算**，不额外增加总预算；建连阶段耗到该子预算 → `kind=timeout` / `returncode=124`；非超时的拒绝/断连 → `kind=transport` / `returncode=255`（Skill 侧对应 `Daemon connection failed`）； |
| 总览#230 | clause | 366 | 5.8 可靠性和可扩展性 | - 建连重试与失效恢复（≤3 次总尝试、降级直连、常驻 shell 重建）的唯一口径见[并发设计 §4](../中层/2-并发设计.md)，与初次尝试共享同一条 deadline； |
| 总览#231 | clause | 367 | 5.8 可靠性和可扩展性 | - **注册各步**的 deadline（探测、部署、第五步各校验相位）唯一 owner 是[多用户与注册 §3.3](../其他/1-多用户与注册.md)，本表不重复。 |
| 总览#233 | table-row | 371 | 5.8 可靠性和可扩展性 | \| 问题 \| 唯一答案 \| |
| 总览#235 | table-row | 373 | 5.8 可靠性和可扩展性 | \| `timeout=None` \| 五个业务接口一律等于默认 30s（见上表） \| |
| 总览#236 | table-row | 374 | 5.8 可靠性和可扩展性 | \| 建连重试 / 常驻 shell 重建 \| 唯一口径见[并发设计 §4](../中层/2-并发设计.md) \| |
| 总览#237 | table-row | 375 | 5.8 可靠性和可扩展性 | \| log 第二帧超时 \| Skill 第一帧结果优先返回，`log=""` 并附固定 warning，见[日志返回设计标准 §6.3](../底层/6-日志返回设计标准.md) \| |
| 总览#238 | clause | 377 | 5.8 可靠性和可扩展性 | 本版不引入 `request_id` 参数/字段（等待请求留在**中层投递前队列**；daemon 同一时刻只接收/执行一个由闸门放行的 Skill 请求。日志增量由每请求的 `[start,end)` offset 定界）。无法判断请求是否已经产生副作用时返回“结果未知”，中层不盲目重发非幂等操作；是否重试由上层业务操作自行决断；该纪律同样适用于 Skill：**投递前**排队超时=确定未执行（仅中层内部可据此处置）；**投递后**超 |

## 总览/add-本版范围与明确不支持.md（23 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 范围#004 | clause | 6 | 本版范围与明确不支持 | > 状态：Normative（“本版不做什么”的唯一口径） |
| 范围#005 | clause | 7 | 本版范围与明确不支持 | > 说明：本文是正式范围文档；README 中的清单只索引本文。每项给出本版口径，实现按此处理，不得静默降级。 |
| 范围#006 | clause | 11 | 1. 本版支持的范围（一句话） | 四层架构：上层通过中层**五个业务接口**（Skill 执行 / 命令执行 / 文件执行 / GUI 命令执行 / Spectre 命令执行）完成业务，另有一个只读查询 `query`（见[四层整体架构与接口 §4.2](1-四层整体架构与接口.md)）供参数准备；中层负责 local/SSH/多用户路由与投送；底层 daemon 只执行 Skill。多用户、并发、CDS.log 增量返回在本版范围内。以下明确不做。 |
| 范围#007 | table-row | 17 | 2.1 上层业务封装 | \| # \| 不支持 \| 本版口径 \| |
| 范围#009 | table-row | 19 | 2.1 上层业务封装 | \| 1 \| Spectre 高层业务封装（仿真流程、结果解析、编排） \| 只提供 **Spectre 命令执行**（一次性命令）与 `role.spectre.bin` 记录，不提供 `purpose`、不做仿真编排；封装留给上层后续；探测/校验失败只 warning、不阻断注册 \| |
| 范围#010 | table-row | 20 | 2.1 上层业务封装 | \| 2 \| GUI 图形化业务封装 / 独立 deploy role \| 只提供 **GUI 命令执行**（一次性命令，窗口枚举/dismiss/bootstrap 类操作）；部署只投送到 `role.daemon.root`，不设独立 deploy role \| |
| 范围#011 | table-row | 24 | 2.2 旧协议与兼容 | \| # \| 不支持 \| 本版口径 \| |
| 范围#013 | table-row | 26 | 2.2 旧协议与兼容 | \| 3 \| 无 token 旧客户端 / 旧 il \| 请求缺失、null 或不匹配 token → NAK `invalid token`，SKILL 零接触 \| |
| 范围#014 | table-row | 27 | 2.2 旧协议与兼容 | \| 4 \| `profile` / `VB_*` / `.env` 及迁移适配 \| 已删除、无兼容入口；新用户只走六步注册 \| |
| 范围#015 | table-row | 28 | 2.2 旧协议与兼容 | \| 5 \| 非对称签名 / HMAC \| token 是对称共享授权票，不做双方公私钥；四层边界不因未来升级而变（见[四层架构 §5.8](1-四层整体架构与接口.md)） \| |
| 范围#016 | table-row | 29 | 2.2 旧协议与兼容 | \| 6 \| `request_id` \| 不引入请求字段；daemon 同一时刻只有一个 in-flight，增量按 `[start,end)` 定界（见[日志返回设计标准 §3](../底层/6-日志返回设计标准.md)） \| |
| 范围#017 | table-row | 30 | 2.2 旧协议与兼容 | \| 7 \| argv / 无 shell 模式、异步 command handle \| RunCommand 为同步 shell 字符串；长任务由上层 marker/轮询实现 \| |
| 范围#018 | table-row | 34 | 2.3 日志 | \| # \| 不支持 \| 本版口径 \| |
| 范围#020 | table-row | 36 | 2.3 日志 | \| 8 \| split-host CDS.log \| 不保证：daemon 能读到 IL 回传的 `path` 就按普通路径返回增量；读不到 → `log=""` + 固定 warning；`log_level=off` 时源头不读、无 warning；bridge 不做 split-host 判定（见[日志返回设计标准 §2](../底层/6-日志返回设计标准.md)） \| |
| 范围#021 | table-row | 37 | 2.3 日志 | \| 9 \| CDS.log 增量跟随 GUI 读取 \| 增量读取固定锚定 **daemon**（读 IL 回传的 `path + [start,end)`），不在 GUI 主机读 CDS.log（X11 转发场景同样不做）；实现点见[日志返回设计标准 §2](../底层/6-日志返回设计标准.md) \| |
| 范围#022 | table-row | 38 | 2.3 日志 | \| 10 \| 全量日志 parser / push stream / 日志数据库 \| 只做同步增量返回；全文经 File 接口自行读取 \| |
| 范围#023 | table-row | 42 | 2.4 文件 | \| # \| 不支持 \| 本版口径 \| |
| 范围#025 | table-row | 44 | 2.4 文件 | \| 11 \| 文件空间安全沙箱 \| `role.<name>.root` 只是各 role 的默认工作目录约定，不拦截 `..`/任意绝对路径；隔离依赖 OS 账号权限 \| |
| 范围#026 | table-row | 48 | 2.5 daemon 生命周期 | \| # \| 不支持 \| 本版口径 \| |
| 范围#028 | table-row | 50 | 2.5 daemon 生命周期 | \| 12 \| 跨机启动 daemon 的协议（mpsserver / 远程 launcher 等） \| 本版不实现；当前 daemon 是 CIW 的本地 `ipcBeginProcess` 子进程，启动方式与运行账号由站点拓扑决定，bridge 只忠实投送与连接、不参与也不校验 \| |
| 范围#029 | table-row | 54 | 2.6 顶层附加能力 | \| # \| 不支持 \| 本版口径 \| |
| 范围#031 | table-row | 56 | 2.6 顶层附加能力 | \| 13 \| 顶层任务等待池（挂起监督） \| 本版不实现，作为下一代想法；长任务由上层业务包自行同步等待，或由调用方分次查询；顶层收到未定义的 `pending` 声明按未知字段处理 \| |
| 范围#032 | clause | 60 | 3. 与相关文档的关系 | - 每项对应的“该怎么做”由各自 Normative 文档定义：接口见[四层整体架构与接口](1-四层整体架构与接口.md)，路由见[路由设计](../中层/3-路由设计.md)，注册见[多用户与注册](../其他/1-多用户与注册.md)，并发见[并发设计](../中层/2-并发设计.md)，日志见[日志返回设计标准](../底层/6-日志返回设计标准.md)，字段见[中层配置文档](../中层/add-中层配置文档.md)。 |

## 中层/add-中层配置文档.md（68 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 配置#003 | clause | 5 | 中层配置文档 | > 状态：Normative（字段目录、默认值、探测写回、注册表 schema、reservation 与 endpoint key 的唯一规范源） |
| 配置#005 | clause | 7 | 中层配置文档 | > 定位：本文是[多用户与注册](../其他/1-多用户与注册.md)的**字段与 schema 详细补充**——六步状态机与授权归[多用户与注册](../其他/1-多用户与注册.md)；本文是字段与必填清单 owner（§4），并提供默认值、探测写回、注册表 schema、reservation 与 endpoint key。 |
| 配置#006 | clause | 11 | 1. 总述 | - **唯一 owner**：字段名/类型/默认值、注册表 schema（§6.1）、reservation（§6.4）、endpoint canonical key（§6.5）只在本文定义；其它文档只索引，不复制。 |
| 配置#012 | clause | 17 | 1. 总述 | - **默认值约定**：标“默认 X”可省略；标“必填”必须写入。 |
| 配置#013 | table-row | 23 | 2.1 通用 | \| 字段 \| 作用 \| 类型 \| 默认/必填 \| |
| 配置#015 | table-row | 25 | 2.1 通用 | \| `token` \| 每次调用携带的寻址与授权参数；每用户唯一、终生不变（格式见 §5，生命周期见[多用户与注册 §1](../其他/1-多用户与注册.md)） \| 配置 \| 注册生成（未提交则自动生成） \| |
| 配置#016 | table-row | 26 | 2.1 通用 | \| `user` \| 人类可读 id + 路径名，非安全凭证 \| 配置 \| 必填（格式见 §5） \| |
| 配置#017 | table-row | 30 | 2.2 策略 | \| 字段 \| 作用 \| 类型 \| 默认/必填 \| |
| 配置#019 | table-row | 32 | 2.2 策略 | \| `ssh.backend` \| SSH 后端 openssh / paramiko；默认 paramiko：同一业务连接上多 channel 复用；Skill 隧道由外部 OpenSSH `ssh -N -L` 承载 \| 配置 \| 默认 `paramiko` \| |
| 配置#020 | table-row | 33 | 2.2 策略 | \| `ssh.control_master` \| openssh 后端的复用策略 auto/force/disable；复用边界是 token，跨 token 不共享；paramiko 不适用 \| 配置 \| 默认 `auto` \| |
| 配置#021 | table-row | 34 | 2.2 策略 | \| `ssh.tool_override` \| 可选 ssh/scp/tar 工具路径覆盖 \| 配置 \| 可选 \| |
| 配置#022 | table-row | 35 | 2.2 策略 | \| `runtime.thread_pool_size` \| 线程预算：在途请求上限（任何未完成动作占位）；超限语义见[并发设计 §2](2-并发设计.md) \| 配置 \| 默认 `32` \| |
| 配置#023 | table-row | 36 | 2.2 策略 | \| `runtime.channel_budget` \| 最大通道数：token 内所有 endpoint 已打开 SSH 通道总数；超限语义见[并发设计 §2](2-并发设计.md) \| 配置 \| 默认 `10` \| |
| 配置#024 | table-row | 37 | 2.2 策略 | \| `runtime.connect_timeout` \| 连接建立超时（各步 deadline 的子预算，见[四层整体架构与接口 §5.8](../总览/1-四层整体架构与接口.md)） \| 配置 \| 默认 `15` 秒 \| |
| 配置#025 | table-row | 38 | 2.2 策略 | \| `cdslog.log_level` \| 返回日志级别 off/all/warn/error；off 从 IL 源头不读不注入；业务接口可显式覆盖 \| 配置 \| 默认 `all` \| |
| 配置#026 | table-row | 39 | 2.2 策略 | \| `cdslog.log_max_bytes` \| 单次日志内联长度上限，超限自动降级（规则见[日志返回设计标准 §5](../底层/6-日志返回设计标准.md)）；业务接口可显式覆盖 \| 配置 \| 默认 `65536` \| |
| 配置#027 | clause | 43 | 2.3 各 role 公共字段 | 五个 role（`gui / daemon / command / file / spectre`）各有下列公共字段。role 的职责、接口对应与连接复用见[路由设计 §2–§4](3-路由设计.md)，本文只定义字段与默认值。 |
| 配置#028 | table-row | 45 | 2.3 各 role 公共字段 | \| 字段 \| 作用 \| 类型 \| 默认/必填 \| |
| 配置#030 | table-row | 47 | 2.3 各 role 公共字段 | \| `role.<name>.mode` \| 投送方式：`local` = 中层就在该 role 目标主机上直接本地执行、不经 SSH（声明需管理权限，见[多用户与注册 §2](../其他/1-多用户与注册.md)）；`remote` = 经 SSH 投送；不同 role 可混合 \| 配置 \| 回退 `mode.default` \| |
| 配置#031 | table-row | 48 | 2.3 各 role 公共字段 | \| `role.<name>.host/user/jump_host/jump_user/proxy` \| 该 role 登录主机/账号/跳板/代理；`local` role 提交即参数错误 \| 配置 \| 回退 §2.5 全局默认（remote 需可解析） \| |
| 配置#032 | table-row | 49 | 2.3 各 role 公共字段 | \| `role.<name>.key_dir/key` \| 该 role 的 SSH 凭据目录/文件名，位于客户端侧（remote 使用；`local` role 不适用） \| 配置 \| 回退 §2.5 全局默认 \| |
| 配置#033 | table-row | 50 | 2.3 各 role 公共字段 | \| `role.<name>.root` \| 该 role 文件根；申请期缺省 `root.default/<role>`，探测后为最终绝对路径 \| 配置 \| 可选（探测写回，见 §6.2） \| |
| 配置#034 | table-row | 51 | 2.3 各 role 公共字段 | \| `role.<name>.max_sessions` \| 该 role 解析到的 endpoint 的并发通道上限（配置在 role、生效在 endpoint；多 role 同 endpoint 取最小值；`local` 不适用） \| 配置 \| 默认 `10` \| |
| 配置#035 | table-row | 52 | 2.3 各 role 公共字段 | \| `role.<name>.expected_fingerprint` \| 该 role endpoint 的 host-key 指纹比对基准（业务 role 必检；spectre 例外，见 §3）；`mode=local` 无 endpoint，省略或为 `null` \| 校验 \| 探测写入 \| |
| 配置#036 | clause | 54 | 2.3 各 role 公共字段 | - 各 role 可携带**用户组** `role.<name>.<组名>`（如 `role.command.calibre`）：值必须是对象且仅含标量字段；中层只做结构约束，**不校验语义、不探测**，注册原样落盘、`query` 原样返回，含义由上层业务包约定；组名不得与本节/§2.4 固定字段重名（字符集与大小限制见 §5）。 |
| 配置#037 | table-row | 58 | 2.4 role 特有字段 | \| 字段 \| 作用 \| 类型 \| 默认/必填 \| |
| 配置#039 | table-row | 60 | 2.4 role 特有字段 | \| `role.daemon.daemon_port` \| daemon 监听端口，每用户分配不冲突 \| 配置 \| 缺省分配（见 §6.4） \| |
| 配置#040 | table-row | 61 | 2.4 role 特有字段 | \| `role.daemon.local_port` \| `remote` 时是隧道本地端口；`local` 时直连端口，必须 `= daemon_port` \| 配置 \| 缺省分配 \| |
| 配置#041 | table-row | 62 | 2.4 role 特有字段 | \| `role.daemon.python` \| daemon role 上的 python 解释器（部署/启动 daemon 消费；`local` 时即本机 python） \| 环境 \| 显式→校验，缺省→探测；失败=注册失败 \| |
| 配置#042 | table-row | 63 | 2.4 role 特有字段 | \| `role.daemon.expected_hostname` \| daemon 主机名比对基准 \| 校验 \| 探测写入 \| |
| 配置#043 | table-row | 64 | 2.4 role 特有字段 | \| `role.daemon.expected_user` \| daemon 进程账号比对基准 \| 校验 \| 探测写入 \| |
| 配置#044 | table-row | 65 | 2.4 role 特有字段 | \| `role.spectre.bin` \| spectre 可执行文件（显式→校验，缺省→探测；失败仅 warning） \| 环境 \| 可选 \| |
| 配置#045 | table-row | 66 | 2.4 role 特有字段 | \| `role.gui.display` \| gui role 的 X server（`DISPLAY` 值，每用户单值）；经只读查询 `query` 返回，供上层拼 X11 命令（见[四层整体架构与接口 §4.2](../总览/1-四层整体架构与接口.md)） \| 环境 \| 显式→校验；缺省→探测写回，失败留空（见 §3） \| |
| 配置#046 | table-row | 70 | 2.5 全局默认与字段回退 | \| 字段 \| 作用 \| 类型 \| 默认/必填 \| |
| 配置#048 | table-row | 72 | 2.5 全局默认与字段回退 | \| `mode.default` \| 各 role 缺省 mode（local/remote） \| 配置 \| **必填，无默认** \| |
| 配置#049 | table-row | 73 | 2.5 全局默认与字段回退 | \| `ssh.default.host/user` \| 各 role 缺省登录主机/账号 \| 配置 \| 存在未在 role 级提供的 remote role 时必填 \| |
| 配置#050 | table-row | 74 | 2.5 全局默认与字段回退 | \| `ssh.default.jump_host/jump_user/proxy` \| 各 role 缺省跳板/代理 \| 配置 \| 可选 \| |
| 配置#051 | table-row | 75 | 2.5 全局默认与字段回退 | \| `ssh.default.key_dir/key` \| 各 role 缺省 SSH 凭据目录/文件名，位于客户端侧；`key_dir` 缺省 = 客户端 `~/.ssh` \| 配置 \| `key_dir` 可选；存在 remote role 时 `key` 必填 \| |
| 配置#052 | table-row | 76 | 2.5 全局默认与字段回退 | \| `root.default` \| 各 role 文件根的申请期基准；探测后写回各 `role.*.root`，运行期不依赖本字段 \| 配置 \| 默认 `~/.virtuoso-bridge/<userid>`（持久化 `null`） \| |
| 配置#053 | clause | 78 | 2.5 全局默认与字段回退 | - 回退是**逐字段**的：role 有值用自己的，否则回退对应全局默认；`null`/空串 = 未提供； |
| 配置#056 | clause | 84 | 2.6 固定目录结构（非配置项） | - 本地工作目录不是注册字段（启动时传入，不传用实现默认）；子结构固定 `registry.json / config.json / temp/ / log/ / artifact/`，启动时自动创建（`config.json` 见[顶层补充 §5](../顶层/add-控制面与业务面.md)）； |
| 配置#058 | table-row | 89 | 3. 三类处理规则 | \| 类型 \| 规则 \| |
| 配置#060 | table-row | 91 | 3. 三类处理规则 | \| 配置 \| 用户提供；只做格式/范围/查重校验，失败拒绝；无自动探测 \| |
| 配置#061 | table-row | 92 | 3. 三类处理规则 | \| 环境 \| 默认自动探测；用户显式提供时校验，不可用报告并拒绝。例外：spectre（失败级别与提交态见[多用户与注册 §4.1](../其他/1-多用户与注册.md)）与 `role.gui.display`（缺省探测失败仅留空 + WARNING，显式不可达仍拒绝） \| |
| 配置#062 | table-row | 93 | 3. 三类处理规则 | \| 校验 \| 探测写入各 role 的 `expected_*`，只用于比对、不参与业务；在注册探测时比对，**运行期不强制比对**。唯一例外：业务 role 的 host-key 指纹不匹配 = ERROR（含机器重装未确认），见[多用户与注册 §3.2/§5](../其他/1-多用户与注册.md) \| |
| 配置#063 | clause | 95 | 3. 三类处理规则 | 探测动作本身（何时探测、逐 role 探测矩阵、失败级别）见[多用户与注册 §4](../其他/1-多用户与注册.md)，本文只定义字段类型规则。`root` 不是探测发现的环境值，而是按 §2.5 与[多用户与注册 §4.2](../其他/1-多用户与注册.md)的默认算法推导、探测期写回绝对路径，其类型为**配置**。 |
| 配置#065 | clause | 100 | 4. 必填小结 | - 条件必填：每个 remote role 必须可解析出目标（role 级 `host/user` 或 `ssh.default.*`）与凭据（role 级 `key_dir/key` 或 `ssh.default.key_dir/key`）； |
| 配置#068 | clause | 106 | 5. 输入校验与首信任 | - `user` 格式 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`；禁止 `/`、`\`、`..`、绝对路径；Windows 大小写不敏感查重；拒绝保留设备名（CON/PRN/AUX/NUL/COM1–9/LPT1–9 及带扩展名）与结尾 `.`/空格； |
| 配置#070 | clause | 108 | 5. 输入校验与首信任 | - `local` role 显式提交 `host/user/jump_host/jump_user/proxy` 或 `key_dir/key` → 参数错误； |
| 配置#071 | clause | 109 | 5. 输入校验与首信任 | - remote role 必须解析出凭据（`key_dir`+`key`），否则拒绝；`key` 只允许文件名、不含目录成分；凭据按**公钥指纹**查重，已被其他条目登记 → 需**任一**已登记持有者的 token 或管理员凭据，否则拒绝（复用规则见[多用户与注册 §3](../其他/1-多用户与注册.md)）； |
| 配置#072 | clause | 110 | 5. 输入校验与首信任 | - `role.gui.display` 只接受 X display 形式（如 `:11`、`localhost:10.0`、`unix/:0`），禁止空白、引号、`$`、反引号、`;` 等 shell 元字符（防注入）； |
| 配置#073 | clause | 111 | 5. 输入校验与首信任 | - 未知字段拒绝（`extra=forbid`）；各 role 的用户组例外：组名 `^[a-z][a-z0-9_-]{0,63}$`、不与固定字段重名，值为对象、字段值仅 JSON 标量且不含 NUL，每 role 用户组总大小 ≤ 16 KiB；语义由上层业务包约定；空串视为未提供； |
| 配置#075 | clause | 113 | 5. 输入校验与首信任 | - registry 持久化 UTF-8、权限 `0600`、tmp + 原子替换。 |
| 配置#103 | clause | 150 | 6.2 提交 schema 与写回口径 | - 何时探测、何时写回、唯一写盘点见[多用户与注册 §3/§4](../其他/1-多用户与注册.md)；本节只约定提交后的字段形态； |
| 配置#107 | clause | 160 | 6.4 端口 reservation（内存候选，唯一口径 | **唯一性作用域**：`token`/`user` 全局；`daemon_port` 同一 daemon 目标主机（`mode=local` 时即本机）；`local_port` 本机。 |
| 配置#108 | clause | 162 | 6.4 端口 reservation（内存候选，唯一口径 | **联合端口**：`mode=local` 时 `daemon_port` 与 `local_port` 是同一个候选端口——任一缺省由同一值生成并同步写入，显式双值必须相等。 |
| 配置#111 | clause | 168 | 6.4 端口 reservation（内存候选，唯一口径 | **并发**：注册为低并发流程，由注册服务进程内协调；不设跨进程租约与宽限回收。 |
| 配置#112 | clause | 170 | 6.4 端口 reservation（内存候选，唯一口径 | **分配算法**：具体算法与端口范围为实现自由度，合同只要求候选唯一且空闲。 |
| 配置#118 | clause | 180 | 6.5 endpoint canonical key | - 两条独立规则：① 字符串规范化决定“是否同一 endpoint”（`Server-A`、`server-a.` 同 endpoint，指纹必须一致）；② 不做名称解析（不查 DNS、不把 alias 与真实 hostname 合并）；`~/.ssh/config` 只用于 transport 解析与 22 端口校验，canonical key 只按规范化输入字符串计算； |
| 配置#120 | clause | 182 | 6.5 endpoint canonical key | - 测试向量（必须逐条可测）： |
| 配置#121 | table-row | 184 | 6.5 endpoint canonical key | \| # \| host \| user \| jump_host \| jump_user \| proxy \| key 尾段（前加 `v1:`） \| |
| 配置#123 | table-row | 186 | 6.5 endpoint canonical key | \| 1 \| `server-a` \| `ssh-user` \| — \| — \| — \| `8c6325e8a41f89a4c29d81eb66db201c4414d33f87702607d23d43a1baf94b0b` \| |
| 配置#124 | table-row | 187 | 6.5 endpoint canonical key | \| 2 \| ` Server-A. ` \| `ssh-user` \| — \| — \| — \| 与 #1 相同 \| |
| 配置#125 | table-row | 188 | 6.5 endpoint canonical key | \| 3 \| `server-a` \| `SSH-User` \| — \| — \| — \| `40701d25d46c873daea45c841226ee0d6d6939209630d5f57459e55c98c2733b` \| |
| 配置#126 | table-row | 189 | 6.5 endpoint canonical key | \| 4 \| `[::1]` \| `u` \| — \| — \| — \| `0bd185aaa4fa1ce6bd5cbeea0a86f061567a632f3ad6bf6f5a8f36b79556526b` \| |
| 配置#127 | table-row | 190 | 6.5 endpoint canonical key | \| 5 \| `server-a` \| `u` \| `bastion` \| `jump-user` \| — \| `178df3e331df40f8d01408ff226fd22e6be04d8033db187f06bc64a5c3512391` \| |
| 配置#128 | table-row | 191 | 6.5 endpoint canonical key | \| 6 \| `server-a` \| `u` \| — \| — \| `socks5://Proxy:1080` \| `f410f0afc8f618e5230416eb191fa6fcdd5c8313828c2e4c4348eed8cfb33630` \| |
| 配置#130 | clause | 194 | 6.5 endpoint canonical key | - 约束：SSH 端口固定 22（注册期校验目标/jump 解析端口，非 22 拒绝）；proxy 固定 `socks5://host:port`；jump 的 known_hosts 由系统 SSH 配置提供；不接受自定义 known_hosts 路径。 |

## 其他/1-多用户与注册.md（40 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 注册#003 | clause | 5 | 多用户与注册 | > 状态：Normative（注册侧唯一口径） |
| 注册#005 | clause | 7 | 多用户与注册 | > 定位：本文只讲**注册**（六步法、授权、要填参数）与**注册表生命周期**；运行期路由与限流见[路由设计](../中层/3-路由设计.md)、[并发设计](../中层/2-并发设计.md)；字段与默认值的详细清单见[中层配置文档](../中层/add-中层配置文档.md)。 |
| 注册#006 | clause | 11 | 1. 总述与 token（授权） | - **注册表是唯一持久化**：本地一份 `registry.json`，`user` 为键；启动时导入一次到内存快照，运行期**不自动读文件**，管理操作成功后由**业务进程管理端点**触发重新导入或重启（见[顶层补充 §1.1](../顶层/add-控制面与业务面.md)），不自动跨进程传播。 |
| 注册#007 | clause | 12 | 1. 总述与 token（授权） | - **注册与使用解耦**：六步注册结束后，除文件系统变更（registry + 远端部署文件）外不得残留隧道、SSH 进程或控制 socket； |
| 注册#011 | clause | 16 | 1. 总述与 token（授权） | - **token 使用范围**：只用于路由与校验（注册表路由、daemon 比对、Skill 请求）；用户可读路径一律用唯一用户名，不用 token。 |
| 注册#015 | clause | 24 | 2. 要填参数（摘要） | - **条件必填**：每个 remote role 必须可解析出目标与凭据——`role.<name>.host/user` 或 `ssh.default.host/user`，`role.<name>.key_dir/key` 或 `ssh.default.key_dir/key`； |
| 注册#018 | clause | 27 | 2. 要填参数（摘要） | - 非法字段、local role 的 host/user、未知字段一律拒绝（规则见[中层配置文档 §5](../中层/add-中层配置文档.md)）。 |
| 注册#019 | clause | 33 | 3.1 流程与预测目标 | **①申请 → ②本地校验 → ③探测 → ④部署 → ⑤连通性测试 → ⑥写注册表**；**前五步不写 registry**（`registry.json` 零写入，候选只存内存），第六步是唯一写盘点；未完成六步即放弃全部内存候选。 |
| 注册#020 | table-row | 35 | 3.1 流程与预测目标 | \| 步 \| 预测目标（可观察） \| 不达成时 \| 重试 \| |
| 注册#022 | table-row | 37 | 3.1 流程与预测目标 | \| 1 申请 \| 必填参数齐全（见 §2） \| 参数错误，零副作用 \| 修改后重新申请 \| |
| 注册#023 | table-row | 38 | 3.1 流程与预测目标 | \| 2 本地校验 \| 无同名 user；`local_port` 本机未被占用；已提供的 `daemon_port` 在同一 daemon 目标主机上未冲突；凭据（公钥指纹）未被他人登记占用，占用 → 需**任一**已登记持有者 token 或管理权限；生成 reservation 候选（仅内存） \| 返回冲突原因 \| 可原样重试；修正参数需 cancel 后重新 apply \| |
| 注册#024 | table-row | 39 | 3.1 流程与预测目标 | \| 3 探测 \| 逐 role 探测矩阵全过（见 §4）；`expected_*` 固化；`role.*.root` 回写绝对路径 \| ERROR（spectre role 整体仅 WARNING） \| 可原样重试；修正参数需 cancel 后重新 apply \| |
| 注册#025 | table-row | 40 | 3.1 流程与预测目标 | \| 4 部署 \| bridge 文件落到 `role.daemon.root`；产出 `setup_path`（daemon 侧绝对路径，供用户复制到 CIW） \| ERROR \| 可原样重试（覆盖式） \| |
| 注册#026 | table-row | 41 | 3.1 流程与预测目标 | \| 4→5 之间 \| 用户自己 `load(setup_path)` 并拉起 daemon；bridge 不参与、不判断是否拉得起来 \| 不属于 bridge 一步 \| 用户自行重试 \| |
| 注册#027 | table-row | 42 | 3.1 流程与预测目标 | \| 5 连通性 \| 能观察到 daemon 可达 + token 比对通过 + 双冒烟通过；**通过后只报告结果、不落盘** \| ERROR \| 可重试第五步 \| |
| 注册#028 | table-row | 43 | 3.1 流程与预测目标 | \| 6 写注册表 \| 用户**显式确认**后 final re-check 并原子落盘（第五步通过不自动保存） \| ERROR \| 可原地重试（重新 final re-check） \| |
| 注册#029 | table-row | 47 | 3.2 第五步失败语义 | \| 现象 \| 级别 \| 处置 \| |
| 注册#031 | table-row | 49 | 3.2 第五步失败语义 | \| daemon 端口不可达 \| **ERROR** \| 提示在 CIW `load(setup_path)`，不得落盘 \| |
| 注册#032 | table-row | 50 | 3.2 第五步失败语义 | \| token NAK / 不匹配 \| **ERROR** \| SKILL 零接触；确认 load 的是本 user 的 setup \| |
| 注册#033 | table-row | 51 | 3.2 第五步失败语义 | \| host-key 指纹不匹配 \| **ERROR** \| 唯一阻断的期望类校验 \| |
| 注册#034 | table-row | 52 | 3.2 第五步失败语义 | \| banner hostname / daemon user 与 `expected_*` 不一致 \| WARNING \| 记入 report.warnings，不阻断 \| |
| 注册#035 | table-row | 53 | 3.2 第五步失败语义 | \| 命令冒烟失败 / Skill 冒烟 `1+1`≠`2` \| **ERROR** \| 对应通道未打通 \| |
| 注册#036 | clause | 57 | 3.3 deadline 与失败清理 | - 各步**各有一条独立的步级 deadline**（默认 30s），步内相位共享、不重置；`runtime.connect_timeout` 是其中的子预算；探测逐项顺序执行；第四步之后用户 `load` 的等待**不计时**； |
| 注册#038 | clause | 59 | 3.3 deadline 与失败清理 | - **各步失败均不释放候选**：可**原样重试同一步**（不携带参数修正）；**修正参数必须 `cancel` 后重新 `apply`**，从第一步重走；`cancel` / 服务重启才释放候选（见[中层配置文档 §6.4](../中层/add-中层配置文档.md)）；任何失败不写 registry；第四步重试为**覆盖式**（`ramic/`、`setup/`、`status/` 重新投送）； |
| 注册#039 | clause | 60 | 3.3 deadline 与失败清理 | - `cancel` 合法于任意非 committed 进行中会话（含 failed），**幂等**；成功后丢弃候选、会话 token 立即失效，`GET /api/register/<user>` 返回无进行中会话；**apply 后必须手动 cancel 才释放**；cancel 或服务重启后同 user 才可重新 `apply`；服务重启清空全部内存候选； |
| 注册#040 | clause | 61 | 3.3 deadline 与失败清理 | - 第五步通过只报告连通性 OK，**不自动写盘**；第六步由用户显式确认触发（唯一写盘点）； |
| 注册#042 | table-row | 68 | 4.1 第三步探测矩阵 | \| role \| 命令可用性（必测） \| 专项探测 \| 失败级别 \| |
| 注册#044 | table-row | 70 | 4.1 第三步探测矩阵 | \| `gui` \| ✅ 一次性命令 \| SSH 可达 + host-key；`role.gui.root` 可写 \| ERROR \| |
| 注册#045 | table-row | 71 | 4.1 第三步探测矩阵 | \| `daemon` \| ✅ 一次性命令 \| SSH 可达 + host-key；`role.daemon.python`；`daemon_port` 空闲；`role.daemon.root` 可写 \| ERROR \| |
| 注册#046 | table-row | 72 | 4.1 第三步探测矩阵 | \| `command` \| ✅ 一次性命令（命令冒烟） \| SSH 可达 + host-key；`role.command.root` 可写 \| ERROR \| |
| 注册#047 | table-row | 73 | 4.1 第三步探测矩阵 | \| `file` \| ✅ 一次性命令 \| SSH 可达 + host-key；`role.file.root` 可见、可写 \| ERROR \| |
| 注册#048 | table-row | 74 | 4.1 第三步探测矩阵 | \| `spectre` \| ✅ 一次性命令 \| SSH 可达 + host-key；`role.spectre.root` 可写；`bin` 校验/探测 \| **WARNING（不阻断）** \| |
| 注册#051 | clause | 78 | 4.1 第三步探测矩阵 | - `role.gui.display`：显式给出 → 在 gui role 上以该值运行 `xdpyinfo`/`xwininfo -root` 校验，不可达 → ERROR（报告参数问题，不静默改号）；未给出 → 仅在 gui 主机上能唯一确定 Virtuoso 进程时探测并写回，存在多个 Virtuoso 进程或探测不到 → 留 `null` 仅 WARNING；bridge 只使用/校验该值，不迁移、不改变 Virtuoso 实 |
| 注册#057 | table-row | 90 | 5. 注册表生命周期与运维 | \| 操作 \| 语义 \| |
| 注册#059 | table-row | 92 | 5. 注册表生命周期与运维 | \| 导入 \| 启动一次读入内存快照；运行期不自动读文件，管理成功后显式重新导入 \| |
| 注册#060 | table-row | 93 | 5. 注册表生命周期与运维 | \| `user update` \| 路径以 user 定位、经管理权限校验后（端点口径见[顶层补充 §2](../顶层/add-控制面与业务面.md)），白名单字段（`ssh.*`、`root.default`、`role.*`、`runtime.*`、`cdslog.*`、`expected_*`，以及各 role 用户组）→ 整体校验 → 原子覆盖；`token`/`registered_at`/其余未声明字段一律拒绝，扁平别名 |
| 注册#061 | table-row | 94 | 5. 注册表生命周期与运维 | \| `user remove` \| 路径以 user 定位、经管理权限校验后（端点口径见[顶层补充 §2](../顶层/add-控制面与业务面.md)），原子移除条目并关缓存，成功后触发重新导入；**本机解绑 ≠ 远端吊销**（远端 daemon 仍接受原 token，直到 `RBStop()` + 删部署）；删除时返回该条目使用的凭据标识与公钥指纹，并告知是否仍被其他条目使用（系统不自动撤销，撤销由用户负责） \| |
| 注册#062 | table-row | 95 | 5. 注册表生命周期与运维 | \| 机器重装 \| 带外确认后显式 update `expected_fingerprint`；未确认前按不匹配拒绝 \| |
| 注册#063 | table-row | 96 | 5. 注册表生命周期与运维 | \| 跨进程写 \| registry 写采用 OS 文件锁 + 读改写原子替换，不丢更新 \| |
| 注册#064 | table-row | 97 | 5. 注册表生命周期与运维 | \| 端口/租约 \| reservation 候选（内存、作用域、冲突重分配）见[中层配置文档 §6.4](../中层/add-中层配置文档.md) \| |

## 中层/3-路由设计.md（38 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 路由#003 | clause | 5 | 路由设计（5 role） | > 状态：Normative（5 role 拓扑与职责、token↔主机边界、连接复用原则的唯一口径） |
| 路由#005 | clause | 7 | 路由设计（5 role） | > 关联：字段定义见[中层配置文档 §2](../中层/add-中层配置文档.md)；接口基线见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)；并发与预算见[并发设计](2-并发设计.md) |
| 路由#008 | clause | 14 | 0. 两步路由总览（路由是纯消费注册表的行为） | 2. **第二步（用户内检查与投递）**：在用户内按 role 解析目标后，执行并发 owner 的限流检查（线程预算、最大通道数、单目标点上限，见[并发设计 §2/§3](2-并发设计.md)），**容得下才继续投递**；需要排队的进对应队列，不需要排队的直接投递（形态见[并发设计 §1](2-并发设计.md)）。投递目标：串行命令 → command role 常驻 shell，Skill → daemon role 隧道/端口，并 |
| 路由#009 | clause | 15 | 0. 两步路由总览（路由是纯消费注册表的行为） | 3. 任一限流参数容不下 → 返回容量拒绝并**指明是哪个参数**（结果字段见[四层整体架构与接口 §4.5](../总览/1-四层整体架构与接口.md)）；拒绝文本与记账见[并发设计 §2/§3](2-并发设计.md)。 |
| 路由#013 | clause | 20 | 0. 两步路由总览（路由是纯消费注册表的行为） | B --> C["第二步：并发限流检查（见 2-并发设计 §2/§3）"] |
| 路由#014 | clause | 21 | 0. 两步路由总览（路由是纯消费注册表的行为） | C -- 容不下 --> R["容量拒绝，指明哪个参数"] |
| 路由#015 | clause | 22 | 0. 两步路由总览（路由是纯消费注册表的行为） | C -- 容下 --> D["排队或直接投递（见 2-并发设计 §1）"] |
| 路由#018 | clause | 26 | 0. 两步路由总览（路由是纯消费注册表的行为） | - 排队/投递超时语义、预算与记账见[并发设计 §1–§3](2-并发设计.md)；注册表导入与 token 生命周期见[多用户与注册](../其他/1-多用户与注册.md)。 |
| 路由#024 | clause | 38 | 1. 定位与边界 | 这条准则同时是评审 P0-01 的关闭口径：规范不再承诺"gui 与 daemon 必须同机"，也不再假设；bridge 按配置投送。 |
| 路由#025 | table-row | 42 | 2. 五个 role 的职责 | \| role \| 职责 \| 被哪个接口消费 \| 额外字段 \| |
| 路由#027 | table-row | 44 | 2. 五个 role 的职责 | \| `gui` \| Virtuoso CIW / X11 所在主机；执行 GUI 侧一次性命令（窗口枚举、dismiss、bootstrap 等） \| **GUI 命令执行**（一次性） \| `display`（X server） \| |
| 路由#028 | table-row | 45 | 2. 五个 role 的职责 | \| `daemon` \| SKILL daemon 监听主机；bridge 文件的部署目标 \| **Skill 执行**（隧道到 daemon） \| `daemon_port`、`local_port` \| |
| 路由#029 | table-row | 46 | 2. 五个 role 的职责 | \| `command` \| 通用命令执行主机（默认常驻 shell；`parallel=True` 走一次性 exec） \| **命令执行** \| — \| |
| 路由#030 | table-row | 47 | 2. 五个 role 的职责 | \| `file` \| 文件传输目标主机（上传/下载） \| **文件执行** \| — \| |
| 路由#031 | table-row | 48 | 2. 五个 role 的职责 | \| `spectre` \| Spectre 执行主机；上层经 **Spectre 命令执行** 调用 spectre（本版第 5 接口；仿真流程编排留待后续） \| **Spectre 命令执行**（一次性） \| `bin`（可选记录） \| |
| 路由#032 | clause | 52 | 2.1 token 与主机边界（唯一口径） | - 一个 token 拥有**五个 role**，这些 role **可以分布在多个主机**（含混合 local/remote）；bridge 不因为 role 跨主机而拒绝注册或拒绝投送； |
| 路由#033 | clause | 53 | 2.1 token 与主机边界（唯一口径） | - 一个 token **只允许一个 daemon role、一个活动 daemon、一个 CIW**：daemon 是本版唯一“单实例”资源，第二处 `load` 同一 token 属于配置错误；需要第二个 CIW 时注册第二个 user/token； |
| 路由#036 | clause | 56 | 2.1 token 与主机边界（唯一口径） | - 该边界是本文的唯一口径；其它文档不得再出现“一个 token 多主机：不支持”这类无限定的表述。 |
| 路由#037 | clause | 58 | 2.1 token 与主机边界（唯一口径） | `role.<name>.mode=local` 表示中层就在该 role 的目标主机上、直接本地执行、不经 SSH；`mode=remote` 表示经 SSH 投送到该 role 的 host/user；**不同 role 可以混合 mode**（例如客户端就在 daemon 主机上 → daemon=local、command/file=remote）；`mode=local` 是**单用户形态**（声明需管理权限），多用户身份隔离 |
| 路由#039 | table-row | 64 | 3. 五个业务接口与 role 的对应关系 | \| # \| 接口 \| 目标 role \| 执行形态 \| |
| 路由#041 | table-row | 66 | 3. 五个业务接口与 role 的对应关系 | \| 1 \| Skill 执行 \| `daemon` \| 隧道 → daemon → Virtuoso（串行语义） \| |
| 路由#042 | table-row | 67 | 3. 五个业务接口与 role 的对应关系 | \| 2 \| 命令执行 \| `command` \| 默认常驻 shell；`parallel=True` 一次性 exec \| |
| 路由#043 | table-row | 68 | 3. 五个业务接口与 role 的对应关系 | \| 3 \| 文件执行（上传/下载） \| `file` \| 每次传输一个一次性通道 \| |
| 路由#044 | table-row | 69 | 3. 五个业务接口与 role 的对应关系 | \| 4 \| GUI 命令执行 \| `gui` \| **一次性命令**（不建常驻 shell） \| |
| 路由#045 | table-row | 70 | 3. 五个业务接口与 role 的对应关系 | \| 5 \| Spectre 命令执行 \| `spectre` \| **一次性命令**（不建常驻 shell） \| |
| 路由#046 | clause | 72 | 3. 五个业务接口与 role 的对应关系 | **GUI / Spectre 命令的本质**：它们是"用并行模式执行命令"——每次调用在对应 role 上执行一条一次性（one-shot）命令，不建立常驻会话、不保留 cwd/env，等价于 `parallel=True` 的命令语义。两者同样占用该 token 的 channel 预算（见[中层配置文档 §2.2](../中层/add-中层配置文档.md)与[并发设计](2-并发设计.md)）。 |
| 路由#051 | clause | 81 | 4. endpoint 与连接复用 | - **endpoint canonical key 的唯一 owner 是[中层配置文档 §6.5](../中层/add-中层配置文档.md)**（含规范化规则与测试向量），本文不复制算法。 |
| 路由#052 | clause | 82 | 4. endpoint 与连接复用 | - endpoint 身份只由 `(host, user, jump_host, jump_user, proxy)` 决定；**连接复用另要求解析后的 SSH 凭据（`key_dir`+`key`）一致**：同一 endpoint 但解析后凭据不同 → 不共用业务连接；经全局默认回退的 role 解析后天然一致； |
| 路由#053 | clause | 84 | 4. endpoint 与连接复用 | **复用原则（唯一口径）**： |
| 路由#054 | table-row | 86 | 4. endpoint 与连接复用 | \| 关系 \| 是否复用 \| |
| 路由#056 | table-row | 88 | 4. endpoint 与连接复用 | \| 不同 token（即使 endpoint 相同） \| **严格隔离，永不复用**——连接、隧道、常驻 shell、预算都按 token 分开 \| |
| 路由#057 | table-row | 89 | 4. endpoint 与连接复用 | \| 同 token 内不同 endpoint \| **无法复用**——各自独立建连 \| |
| 路由#058 | table-row | 90 | 4. endpoint 与连接复用 | \| 同 token 内同一 endpoint（且解析后凭据一致） \| **尽量复用**——一条业务连接（backend 内多 channel 复用；`backend=openssh` 时可启用 ControlMaster，`backend=paramiko` 时为其 transport）；remote daemon role 另持有一条专用 Skill tunnel（外部 `ssh -N -L`，不经过业务连接） \| |
| 路由#059 | clause | 92 | 4. endpoint 与连接复用 | - 连接生命周期（建连/重试/关闭）见[并发设计 §4](2-并发设计.md)； |
| 路由#060 | clause | 93 | 4. endpoint 与连接复用 | - 预算：线程预算与最大通道数**每 token 一份**（token 内所有 endpoint 共享），单目标点上限按 endpoint（字段配置在 role、共享 endpoint 取最小值）；记账矩阵见[并发设计 §2/§3](2-并发设计.md)，预算不因 role 数量而增加。 |
| 路由#067 | clause | 106 | 6. 与其它文档的关系 | - 字段与默认值：[中层配置文档](../中层/add-中层配置文档.md)； |
| 路由#068 | clause | 107 | 6. 与其它文档的关系 | - 接口签名与错误模型：[四层整体架构与接口](../总览/1-四层整体架构与接口.md) §4； |
| 路由#070 | clause | 109 | 6. 与其它文档的关系 | - 并发、预算与连接复用：[并发设计](2-并发设计.md)； |

## 中层/2-并发设计.md（25 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 并发#003 | clause | 5 | 并发设计 | > 状态：Normative（并发与限流唯一口径） |
| 并发#005 | clause | 7 | 并发设计 | > 关联：字段定义见[中层配置文档 §2.2/§2.3](../中层/add-中层配置文档.md)；接口语义见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)；错误分类见[四层整体架构与接口 §4.5](../总览/1-四层整体架构与接口.md) |
| 并发#006 | clause | 11 | 1. 三种执行形态 | 五个业务接口按并发形态归为三类： |
| 并发#007 | table-row | 13 | 1. 三种执行形态 | \| 形态 \| 接口 \| 投递方式 \| SSH 资源 \| |
| 并发#009 | table-row | 15 | 1. 三种执行形态 | \| 串行·Skill \| Skill 执行 \| **排队投递**：上一请求结果返回、通道明确空闲后才投递下一个，否则排队 \| 专用隧道连接 \| |
| 并发#010 | table-row | 16 | 1. 三种执行形态 | \| 串行·命令 \| 命令执行（默认，`parallel=False`） \| **排队投递**：常驻 shell 空闲后才写入下一条 \| 常驻 shell 会话 \| |
| 并发#011 | table-row | 17 | 1. 三种执行形态 | \| 并行 \| 文件执行、命令执行（`parallel=True`）、GUI 命令、Spectre 命令 \| **直接开通道执行**，无逻辑排队 \| 一次性通道，用完关闭 \| |
| 并发#012 | clause | 19 | 1. 三种执行形态 | - 串行两类的排队都在中层**投递前**发生，按 token 隔离（per-token 闸门）； |
| 并发#013 | clause | 20 | 1. 三种执行形态 | - 排队等待消耗同一条端到端 deadline：**排队中超时 = 未投递**（确定未执行，该“可安全重试”仅属中层内部策略）；**已投递后超时 = 结果未知**（中层不重发；是否重试由上层业务操作自行决断）；Skill 对外超时一律视为结果未知，语义见[四层整体架构与接口 §4.5/§5.8](../总览/1-四层整体架构与接口.md)。 |
| 并发#014 | table-row | 24 | 2. 三个限流配置（每 token 一份） | \| 预算 \| 字段 \| 计量 \| 作用域 \| 超限 \| |
| 并发#016 | table-row | 26 | 2. 三个限流配置（每 token 一份） | \| 线程预算 \| `runtime.thread_pool_size`（默认 32） \| **在途请求数**：任何未完成的动作——排队中、执行中、传输中——都占 1，完成才释放 \| 每 token \| 容量拒绝（`thread pool exceeded`） \| |
| 并发#017 | table-row | 27 | 2. 三个限流配置（每 token 一份） | \| 最大通道数 \| `runtime.channel_budget`（默认 10） \| token 内所有 role/endpoint **已打开的 SSH 通道总数**：开通道即占、关闭即释放；与客户端无关，纯看 ssh 开了多少通道 \| 每 token（跨全部 role） \| 容量拒绝（`channel budget exceeded`） \| |
| 并发#018 | table-row | 28 | 2. 三个限流配置（每 token 一份） | \| 单目标点通道上限 \| `role.<name>.max_sessions`（默认 10） \| 单个 **endpoint** 上的 SSH 通道数（计数与上限均按 endpoint）；字段配置在 role 上、生效在 endpoint；本地代理远端 sshd `MaxSessions`，防止冲崩 \| 每 endpoint（经 role 配置） \| 容量拒绝（`role max_sessions exceeded`） \| |
| 并发#020 | clause | 31 | 2. 三个限流配置（每 token 一份） | - 三个预算互相独立，任一超限 → 返回容量拒绝并指明具体预算（结果字段见[四层整体架构与接口 §4.5](../总览/1-四层整体架构与接口.md)），**不排队等待**； |
| 并发#022 | clause | 33 | 2. 三个限流配置（每 token 一份） | - 多个 role 解析到同一 endpoint 时共享一个计数器，有效上限取这些 role 的 `max_sessions` 最小值；remote daemon 的专用 Skill tunnel 计入该 endpoint 的通道数； |
| 并发#024 | table-row | 38 | 3. 通道记账矩阵（唯一口径） | \| 动作 \| 线程预算 \| 最大通道数（token 合计） \| 单目标点通道上限 \| |
| 并发#026 | table-row | 40 | 3. 通道记账矩阵（唯一口径） | \| 任意接口的在途调用（含排队中） \| 占 1，完成释放 \| 见对应行 \| — \| |
| 并发#027 | table-row | 41 | 3. 通道记账矩阵（唯一口径） | \| Skill 执行 \| 占 1 \| 隧道 forwarding 占 1（每 daemon endpoint 一条，连接建立时占、关闭时释放） \| 占该 daemon endpoint 1 \| |
| 并发#028 | table-row | 42 | 3. 通道记账矩阵（唯一口径） | \| 命令执行（默认串行） \| 占 1 \| 常驻 shell 会话占 1（每 command endpoint 一条） \| 占该 command endpoint 1 \| |
| 并发#029 | table-row | 43 | 3. 通道记账矩阵（唯一口径） | \| 并行命令 / 文件 / GUI / Spectre \| 占 1 \| 占 1（通道关闭即释放） \| 占该 role 的 endpoint 1 \| |
| 并发#030 | table-row | 44 | 3. 通道记账矩阵（唯一口径） | \| `mode=local` 的同类动作 \| 占 1 \| 不占 \| 不占 \| |
| 并发#034 | clause | 52 | 4. 连接生命周期与建连（唯一口径） | - 建连失败只在无副作用阶段重试，**最多 3 次总尝试（含初次）**；ControlMaster 故障自动降级直连；重试共享同一条剩余预算； |
| 并发#038 | clause | 59 | 5. 与其它文档的索引 | - 字段与默认值：[中层配置文档 §2](../中层/add-中层配置文档.md)； |
| 并发#040 | clause | 61 | 5. 与其它文档的索引 | - 错误 kind 与保留码：[四层整体架构与接口 §4.5](../总览/1-四层整体架构与接口.md)； |
| 并发#042 | clause | 63 | 5. 与其它文档的索引 | - 本版不支持的并发能力：[本版范围与明确不支持](../总览/add-本版范围与明确不支持.md)。 |

## 底层/6-日志返回设计标准.md（18 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 日志#003 | clause | 5 | 日志返回设计标准 | > 状态：已冻结（CDS.log 返回唯一口径） |
| 日志#009 | clause | 15 | 1. 目标与硬性边界 | - **不向 CDS.log 注入任何输出**：不得因为“要返回日志”就往 CDS.log 写 BEGIN/END marker 或其他行——日志返回只读文件，不改文件； |
| 日志#011 | table-row | 20 | 2. 实现点：daemon.py + IL 分工 | \| 职责 \| 实现位置 \| |
| 日志#013 | table-row | 22 | 2. 实现点：daemon.py + IL 分工 | \| 执行用户 SKILL；当 log 开启时，请求前后各一次 `hiFlushLogFile()`+`fileLength()`，回传 `path + start_offset + end_offset` \| 底层 `ramic_bridge.il` \| |
| 日志#014 | table-row | 23 | 2. 实现点：daemon.py + IL 分工 | \| 读 `[start,end)`、级别过滤、限长降级、组装 JSON 回包；`off` 时完全不读 \| `ramic_bridge_daemon_*.py` \| |
| 日志#015 | table-row | 24 | 2. 实现点：daemon.py + IL 分工 | \| 解析回包，把 `log` 挂到 `VirtuosoResult` \| 中层 `SkillClient` / models \| |
| 日志#035 | clause | 51 | 3. 增量机制（offset 定界，无 marker、无 | - `[start,end)` 之外的并发输出不属于本次增量；等待请求留在中层投递前队列，daemon 同一时刻只接收/执行一个由闸门放行的 Skill 请求。 |
| 日志#037 | table-row | 57 | 4. 分级 | \| 前缀 \| 级别 \| |
| 日志#039 | table-row | 59 | 4. 分级 | \| `\e` \| error \| |
| 日志#040 | table-row | 60 | 4. 分级 | \| `\w` \| warning \| |
| 日志#041 | table-row | 61 | 4. 分级 | \| 其他（`\o`/`\i`/`\p`/无前缀） \| info \| |
| 日志#045 | clause | 69 | 5. 限长与自动降级 | `log_max_bytes`（默认 64KB）： |
| 日志#055 | clause | 81 | 5. 限长与自动降级 | - 最后一步按**字节截断、只取靠前部分**：例如上限 100 字节、本次增量起于 offset 10、error 增量到 200，则返回 10–110，之后内容本次不补发； |
| 日志#066 | clause | 103 | 6.2 回包（daemon → 中层，唯一当前格式） | {"value": "3", "log": "\\e ...本次错误行...\\n"} |
| 日志#070 | clause | 108 | 6.2 回包（daemon → 中层，唯一当前格式） | - **本版只解析 JSON payload**；旧 daemon（无 token）不在支持范围，收到非法帧按协议错误处理。 |
| 日志#077 | clause | 120 | 6.3 内部 metadata frame（IL → d | - 帧顺序固定：第一帧 `value/error`，第二帧 `meta`；两帧必须由 IL 合并为**一次 `ipcWriteProcess`** 写入，避免重排； |
| 日志#082 | clause | 128 | 7. 边界与错误语义 | - `CDS.log` 不存在/不可读/路径变化且读取失败，或第二帧缺失/超时：**本次 log=""，Skill 结果照常返回**，`VirtuosoResult.warnings` 追加固定文本 `CDS.log unavailable: <reason>`（`<reason>` 仅作诊断，不回退为请求失败）；`log_level=off` 刻意不产生第二帧，**不追加该 warning**。 |
| 日志#091 | clause | 140 | 8. 验收标准 | 7. 非法 `log_level`/`log_max_bytes` 直接拒绝报错；`CDS.log` 不可读时 `log=""` 且 `warnings` 含固定文本 `CDS.log unavailable: <reason>`；截断后尾部不输出半个 UTF-8 字符。 |

## 顶层/1-顶层.md（14 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 顶层#003 | clause | 5 | 顶层：HTTP 入口与业务调度 | > 状态：Normative（顶层调度与响应壳唯一口径） |
| 顶层#005 | clause | 7 | 顶层：HTTP 入口与业务调度 | > 定位：顶层只做入口与调度。业务包与业务操作契约见[上层 §2/§4](../上层/1-上层.md)；分层职责与依赖见[四层整体架构与接口 §3](../总览/1-四层整体架构与接口.md)；五业务接口与错误总则见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。 |
| 顶层#009 | clause | 14 | 1. 总述 | - 限流不是顶层职责：中层 per-token 预算由中层计账（见[并发设计 §2/§3](../中层/2-并发设计.md)），顶层不解释该预算；顶层自身业务请求准入上限见[控制面与业务面 §5](add-控制面与业务面.md)。 |
| 顶层#018 | clause | 29 | 2.1 显式注册表 | - 一个业务包可以出现在多行（每个业务操作一行）；**单操作业务包只登记一行，同样成立**；同一业务操作名重复登记是启动错误； |
| 顶层#028 | clause | 48 | 2.4 中层对象注入 | - 可测试约束：处理/调度模块只允许标准库、`common.paths`、`common.jsonutil`、`common.config`（纯工具基座）、`server.*`、`pyapi.*`；不得出现 `transport.*`、`socket`、`subprocess`、`paramiko`。 |
| 顶层#033 | table-row | 58 | 3. 响应壳与错误分界 | \| 情形 \| HTTP \| 响应体 \| |
| 顶层#035 | table-row | 60 | 3. 响应壳与错误分界 | \| 非法 JSON、缺 `operation`/`token`、token 类型错 \| 4xx \| `ok=false`、`error` \| |
| 顶层#036 | table-row | 61 | 3. 响应壳与错误分界 | \| 未知 `operation` \| 4xx \| `ok=false`、`error` \| |
| 顶层#037 | table-row | 62 | 3. 响应壳与错误分界 | \| Request 构造失败（类型/必填/范围） \| 4xx \| `ok=false`、`error` \| |
| 顶层#038 | table-row | 63 | 3. 响应壳与错误分界 | \| 业务运行期失败 \| 2xx \| `ok=false`、`error`、`data` 含步骤痕迹 \| |
| 顶层#039 | table-row | 64 | 3. 响应壳与错误分界 | \| 业务操作未预期异常 \| 5xx \| `ok=false`、`error`；不带调用栈 \| |
| 顶层#042 | clause | 68 | 3. 响应壳与错误分界 | - 未预期异常必须被顶层捕获：单请求失败不影响其它请求，不终止服务。 |
| 顶层#050 | clause | 82 | 5. 与其它文档的索引 | - 分层职责、依赖方向、五业务接口与错误总则：[四层整体架构与接口](../总览/1-四层整体架构与接口.md) §3/§4； |
| 顶层#051 | clause | 83 | 5. 与其它文档的索引 | - 并发与限流：[并发设计](../中层/2-并发设计.md)； |

## 顶层/add-控制面与业务面.md（55 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 控制面#003 | clause | 5 | 顶层补充：控制面与业务面 | > 状态：Normative（顶层 HTTP 端点清单、端口划分与权限口径的唯一 owner） |
| 控制面#007 | clause | 12 | 1. 双面双端口 | - **控制端口**：注册、用户管理、全局配置与人类操作；低并发，面向人与运维； |
| 控制面#008 | clause | 13 | 1. 双面双端口 | - **业务端口**：业务包调度；程序调用，高并发。 |
| 控制面#011 | clause | 16 | 1. 双面双端口 | - 控制端口默认只绑定 `127.0.0.1`，管理操作经 SSH 隧道访问；业务端口绑定地址按部署配置。 |
| 控制面#012 | table-row | 20 | 2. 权限等级（本文唯一口径） | \| 等级 \| 含义 \| 本版处理 \| |
| 控制面#014 | table-row | 22 | 2. 权限等级（本文唯一口径） | \| 无权限 \| 任何人可调用 \| — \| |
| 控制面#015 | table-row | 23 | 2. 权限等级（本文唯一口径） | \| 会话 token \| 该注册会话自己的 token（`apply` 返回） \| 请求携带并校验 \| |
| 控制面#016 | table-row | 24 | 2. 权限等级（本文唯一口径） | \| 个人 token \| 目标 user 自己的 token（注册表条目） \| 请求携带；结构校验在顶层；业务端口的合法性与路由由中层判定，控制端口 `/api/bug` 例外见 §3 \| |
| 控制面#017 | table-row | 25 | 2. 权限等级（本文唯一口径） | \| 管理权限 \| 管理员身份 \| 本版 = 内置单管理员 token：服务端只存其 **SHA-256 哈希**（不存原文），比较用 `hmac.compare_digest`；私钥签名方案标为**后续版本** \| |
| 控制面#022 | table-row | 35 | 3. 控制端口端点 | \| 方法 \| 路径 \| 用途 \| 权限 \| |
| 控制面#024 | table-row | 37 | 3. 控制端口端点 | \| GET \| `/` \| 注册页（HTML），人类操作入口 \| 无权限 \| |
| 控制面#025 | table-row | 38 | 3. 控制端口端点 | \| GET \| `/health` \| 存活探针（运维用） \| 无权限 \| |
| 控制面#026 | table-row | 39 | 3. 控制端口端点 | \| GET \| `/help` \| 端点清单与用法说明 \| 无权限 \| |
| 控制面#027 | table-row | 40 | 3. 控制端口端点 | \| POST \| `/api/bug` \| 提交 bug 报告（格式不做要求） \| 个人 token \| |
| 控制面#028 | clause | 42 | 3. 控制端口端点 | **六步注册**（语义唯一 owner 见[多用户与注册 §3](../其他/1-多用户与注册.md)） |
| 控制面#029 | table-row | 44 | 3. 控制端口端点 | \| 方法 \| 路径 \| 用途 \| 权限 \| |
| 控制面#031 | table-row | 46 | 3. 控制端口端点 | \| POST \| `/api/register` \| 注册命令：`{user, action, token?, enhanced_token?, 参数}`，`action` ∈ `apply / validate / probe / deploy / verify / commit / cancel` \| `apply` 无权限（声明 `mode=local` 或复用已登记凭据需 `enhanced_token`）；其余 act |
| 控制面#032 | table-row | 47 | 3. 控制端口端点 | \| GET \| `/api/register/<user>` \| 查询进行中的注册状态 \| 会话 token \| |
| 控制面#034 | table-row | 51 | 3. 控制端口端点 | \| action \| 合法前提 \| |
| 控制面#036 | table-row | 53 | 3. 控制端口端点 | \| `apply` \| 无同名进行中会话 \| |
| 控制面#037 | table-row | 54 | 3. 控制端口端点 | \| `validate` \| 刚 `apply`；失败后可原样重试 \| |
| 控制面#038 | table-row | 55 | 3. 控制端口端点 | \| `probe` \| 刚 `validate`；失败后可原样重试 \| |
| 控制面#039 | table-row | 56 | 3. 控制端口端点 | \| `deploy` \| 刚 `probe`；失败后可原样重试 \| |
| 控制面#040 | table-row | 57 | 3. 控制端口端点 | \| `verify` \| 刚 `deploy`；或上一次 `verify` 失败（可原地重试） \| |
| 控制面#041 | table-row | 58 | 3. 控制端口端点 | \| `commit` \| 刚 `verify` 成功；失败后可原地重试 \| |
| 控制面#042 | table-row | 59 | 3. 控制端口端点 | \| `cancel` \| 任意非 committed 的进行中会话 \| 释放内存候选，不落盘 |
| 控制面#043 | clause | 61 | 3. 控制端口端点 | - 非法 action/顺序 → 4xx `{"error": "step order violation", "current_stage": …, "expected": …}`，**不改变会话状态**； |
| 控制面#044 | clause | 62 | 3. 控制端口端点 | - 各步失败后候选保留，可**原样重试同一步**（不携带参数修正）；**修正参数必须 `cancel` 后重新 `apply`**；只有 `cancel`（或服务重启）才释放候选； |
| 控制面#045 | clause | 63 | 3. 控制端口端点 | - `apply` 响应返回 `token`（用户显式提供则原样，缺省自动生成）；除 `apply` 外的 action 必须携带 `token`，服务端校验其与候选一致，缺失/不一致 → 4xx `invalid token`，**不改变会话状态**； |
| 控制面#049 | table-row | 69 | 3. 控制端口端点 | \| 方法 \| 路径 \| 用途 \| 权限 \| |
| 控制面#051 | table-row | 71 | 3. 控制端口端点 | \| GET \| `/api/users` \| 用户列表（响应脱敏 token） \| 管理权限 \| |
| 控制面#052 | table-row | 72 | 3. 控制端口端点 | \| GET \| `/api/user/<user>` \| 读取用户条目（响应脱敏 token） \| 管理权限 \| |
| 控制面#053 | table-row | 73 | 3. 控制端口端点 | \| POST \| `/api/user/<user>/update` \| 修改条目（白名单字段） \| 管理权限 \| |
| 控制面#054 | table-row | 74 | 3. 控制端口端点 | \| DELETE \| `/api/user/<user>` \| 删除条目（本机解绑 ≠ 远端吊销） \| 管理权限 \| |
| 控制面#056 | table-row | 78 | 3. 控制端口端点 | \| 方法 \| 路径 \| 用途 \| 权限 \| |
| 控制面#058 | table-row | 80 | 3. 控制端口端点 | \| GET / PUT \| `/api/config` \| 业务 server 线程池大小（`config.json`，仅 `business_thread_pool_size`） \| 管理权限 \| |
| 控制面#060 | table-row | 84 | 3. 控制端口端点 | \| 方法 \| 路径 \| 用途 \| 权限 \| |
| 控制面#062 | table-row | 86 | 3. 控制端口端点 | \| GET \| `/api/process/status` \| 业务进程 pid/端口/工作路径/启动参数/状态（`starting` / `ready` / `crashed`） \| 管理权限 \| |
| 控制面#063 | table-row | 87 | 3. 控制端口端点 | \| POST \| `/api/process/reload` \| 重新导入 `registry.json` 与 `config.json`、关闭旧 token 缓存；`business_thread_pool_size` 对**新请求**立即生效，在途不受影响 \| 管理权限 \| |
| 控制面#064 | table-row | 88 | 3. 控制端口端点 | \| POST \| `/api/process/restart` \| 拒绝新请求、等在途完成（上限 **30 秒**，超时强杀）、按原启动参数重新拉起；强杀覆盖业务进程组及 SSH 后代 \| 管理权限 \| |
| 控制面#066 | clause | 91 | 3. 控制端口端点 | - `status`：`starting/ready/crashed`（`starting` = 已拉起未 ready）；`restart` 期间监听保持，新请求 `503 + Retry-After`，在途排空 30s 后强杀并重拉；管理端同步等待、自身超时 > 30s； |
| 控制面#069 | clause | 95 | 3. 控制端口端点 | - 修改类（update/delete）路径以 `user` 定位，**收归管理员**：个人 token 不能自助修改；update 请求体含 `token` 字段 → 拒绝； |
| 控制面#071 | clause | 97 | 3. 控制端口端点 | - 请求体上限 **16 MiB**，超限 → `413`； |
| 控制面#072 | clause | 98 | 3. 控制端口端点 | - 控制端口不运行业务操作；`POST /api/bug` 携带个人 token，合法性由控制进程经注册与管理模块的 registry 内存快照校验（不经中层、不读注册表文件）；**无 token 或无效 → 4xx，不记录**；校验通过后，服务端**先剥离 token/Authorization 等凭据**再记录原始请求体，并附加提交 user、提交日期时间、当前状态摘要、备份的近期操作/错误日志，统一写入本地工作目录 `log/bu |
| 控制面#073 | table-row | 102 | 4. 业务端口端点 | \| 方法 \| 路径 \| 用途 \| 权限 \| |
| 控制面#075 | table-row | 104 | 4. 业务端口端点 | \| POST \| `/api/operation` \| 业务调度：`{operation, token, 业务字段}` → 查注册表 → 构造 Request → 调用对应方法 → 响应壳 \| 个人 token \| |
| 控制面#076 | table-row | 105 | 4. 业务端口端点 | \| GET \| `/health` \| 存活探针（运维用） \| 无权限 \| |
| 控制面#077 | table-row | 106 | 4. 业务端口端点 | \| GET \| `/help` \| 端点清单与用法说明 \| 无权限 \| |
| 控制面#079 | clause | 109 | 4. 业务端口端点 | - 调度顺序与响应壳的唯一口径见[顶层 §2/§3](1-顶层.md)。 |
| 控制面#080 | clause | 113 | 5. 全局配置与启动参数 | - 工作路径下除 `registry.json` 外，另存一份配置 JSON `config.json`；`GET/PUT /api/config` 操作该配置：GET 读内存快照，PUT 只覆盖请求里出现的顶层键、未出现的键原样保留，校验通过后更新快照并原子写回 `config.json`； |
| 控制面#081 | clause | 114 | 5. 全局配置与启动参数 | - `config.json` 经 `common.config` 提供**进程级只读快照**（与 `common.paths` 同性质，四层可读）；控制面是唯一写者；业务进程启动与 `/api/process/reload` 或 `restart` 各导入一次，运行期不读文件、请求期零文件 IO； |
| 控制面#083 | clause | 116 | 5. 全局配置与启动参数 | - 控制面只理解并校验自己登记的键（本版 `business_thread_pool_size`），其余顶层键**原样透传、不解读**；`business_thread_pool_size` 是**可变准入上限**：reload 后新请求按新上限准入；在途数 ≥ 新上限时，新请求拒绝（`429 + Retry-After`）直至低于上限； |
| 控制面#085 | clause | 118 | 5. 全局配置与启动参数 | - `runtime.thread_pool_size` 是**每 token** 的注册表配置（唯一 owner 见[并发设计 §2](../中层/2-并发设计.md)），与本节的“全局线程池上限”不是一回事：前者是单用户预算，后者是顶层进程能力上限；两者独立，不互相替代。 |
| 控制面#088 | clause | 124 | 6. 索引 | - 调度顺序、响应壳与错误分界：[顶层 §2/§3](1-顶层.md)； |
| 控制面#089 | clause | 125 | 6. 索引 | - 并发与限流：[并发设计](../中层/2-并发设计.md)； |

## 上层/1-上层.md（24 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| 上层#003 | clause | 5 | 上层：业务包与插件化 | > 状态：Normative（业务包与业务操作契约、插件注册唯一口径） |
| 上层#005 | clause | 7 | 上层：业务包与插件化 | > 定位：五业务接口签名与错误总则见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)；顶层调度见[顶层 §2](../顶层/1-顶层.md)；role 与并发见[路由设计](../中层/3-路由设计.md)、[并发设计](../中层/2-并发设计.md)。 |
| 上层#017 | table-row | 31 | 2.2 方法契约 | \| 项 \| 约定 \| |
| 上层#019 | table-row | 33 | 2.2 方法契约 | \| 入口 \| 每个业务操作一个方法 `method(request) -> Result`；返回时业务已结束（成功或已失败） \| |
| 上层#020 | table-row | 34 | 2.2 方法契约 | \| 同步 \| 返回时业务已结束（成功或已失败）；不返回任务句柄 \| |
| 上层#021 | table-row | 35 | 2.2 方法契约 | \| 无状态 \| 包实例每次请求新建；中间数据不在实例属性里 \| |
| 上层#022 | table-row | 36 | 2.2 方法契约 | \| 注入 \| 构造只接受 `Middle`；不创建连接/进程/隧道 \| |
| 上层#024 | table-row | 42 | 2.3 Request / Result | \| 字段 \| 类型 \| 约定 \| |
| 上层#026 | table-row | 44 | 2.3 Request / Result | \| `token` \| `str` \| 必填；每次中层调用原样透传 \| |
| 上层#027 | table-row | 45 | 2.3 Request / Result | \| 业务字段 \| 包自定义 \| 必须可序列化 \| |
| 上层#028 | table-row | 46 | 2.3 Request / Result | \| `ok` \| `bool` \| 业务是否成功 \| |
| 上层#029 | table-row | 47 | 2.3 Request / Result | \| `steps` \| `list[dict]` \| 步骤痕迹（§2.4） \| |
| 上层#030 | table-row | 48 | 2.3 Request / Result | \| `error` \| `str` 或 `None` \| 失败摘要；成功为 `None` \| |
| 上层#031 | clause | 52 | 2.4 步骤痕迹 | - 每步记 `{"step": 名, "ok": 布尔, "detail": 中层结果}`；默认任一步失败即停止；业务操作可自行决定是否重试某步（条件与痕迹自行约定）； |
| 上层#032 | clause | 53 | 2.4 步骤痕迹 | - 保留全部痕迹；失败不得伪装成成功，也不得只留一句 `error` 丢弃步骤。 |
| 上层#042 | clause | 74 | 3.3 校验与错误 | - 领域校验失败是业务失败，写成 `Result(ok=false)`，**不得抛异常表达**； |
| 上层#043 | clause | 75 | 3.3 校验与错误 | - 下层结构化失败按错误总则处置：校验和不一致不忽略；重试策略由业务操作自行决断；中层只做传输层透明重试（见[并发设计 §4](../中层/2-并发设计.md)）； |
| 上层#044 | clause | 76 | 3.3 校验与错误 | - 失败类别枚举的唯一 owner 见[四层整体架构与接口 §4.5](../总览/1-四层整体架构与接口.md)，本文不复制。 |
| 上层#045 | clause | 82 | 4.1 显式注册 | - **插件的登记单元是业务包，条目落在业务操作级**：`{业务操作名: (业务包类, 方法名, Request 模型)}`；注册表结构与重复登记错误由[顶层 §2.1](../顶层/1-顶层.md)唯一 owner； |
| 上层#047 | table-row | 87 | 4.2 命名与自描述 | \| 项 \| 约定 \| |
| 上层#049 | table-row | 89 | 4.2 命名与自描述 | \| 业务操作名 \| 点分英文分段（领域.对象.动作）；发布后不改名 \| |
| 上层#050 | table-row | 90 | 4.2 命名与自描述 | \| 自描述 \| 每个业务包导出：`Package` 类 + 每个业务操作的 `(操作名, 方法名, Request, Result)`；自描述是包级元数据，顶层注册表值仍为 §2.1 三元组（不含 Result） \| |
| 上层#063 | clause | 115 | 7. 与其它文档的索引 | - 五业务接口签名与错误总则：[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)； |
| 上层#066 | clause | 118 | 7. 与其它文档的索引 | - 排队、预算与 deadline：[并发设计](../中层/2-并发设计.md)； |

## 上层/2-schematic.md（43 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| schematic#004 | clause | 6 | 上层业务包：schematic | > Supersedes：Draft v3（坐标口径再收口：**单点一律 `pos`**，弃用 `xy`，**不拆成两个字段**；见 §1.3） |
| schematic#006 | clause | 11 | 1. 业务操作 | 核心只有读和写。写是按对象对称的原子操作：instance / wire / label / pin 各有 place、delete、rename、set。net 是 label/pin 的派生对象，不做操作。 |
| schematic#007 | table-row | 15 | 1.1 读操作（不改变业务服务器状态） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| schematic#009 | table-row | 17 | 1.1 读操作（不改变业务服务器状态） | \| read \| `focus` 可选，可组合；不填=全部；可带实例过滤与参数白名单 \| 开只读 → 按 focus 执行对应 SKILL 段 → 解析 \| S \| |
| schematic#010 | table-row | 18 | 1.1 读操作（不改变业务服务器状态） | \| screenshot \| 原理图截图：默认 `lib/cell/view`，可选 `window_id`；格式 PNG \| 找/开窗口 → hiWindowSaveImage → 下载 \| S+D \| |
| schematic#014 | clause | 23 | 1.1 读操作（不改变业务服务器状态） | - 可选 `object_filter`：每个对象一个条目，**不写默认 `all`**；条目可以是 `none`（该类一个都不读）。重点是"只看某实例的端子/位置"，不把整图读一遍： |
| schematic#015 | clause | 24 | 1.1 读操作（不改变业务服务器状态） | - `instance`：`all`（默认）/ `none` / `{"names":[...]}` / `{"region":[pos0, pos1]}`； |
| schematic#016 | clause | 25 | 1.1 读操作（不改变业务服务器状态） | - `wire` / `label` / `pin` / `note`：`all`（默认）/ `none` / `{"region":[pos0, pos1]}`。 |
| schematic#017 | clause | 26 | 1.1 读操作（不改变业务服务器状态） | - object_filter 只对 `positions`、`params`、不填=全部生效；`focus` 含 `connectivity` 时忽略（连接关系必须全量）。 |
| schematic#018 | clause | 27 | 1.1 读操作（不改变业务服务器状态） | - `screenshot`：目标默认 `lib/cell/view`，可选 `window_id`；可选 `region=[pos0, pos1]`（user units，截前 `hiZoomIn(window, bBox)` 把区域填满窗口）；`toplevel` / `centralWidget` 暴露；`leave_open` 默认关窗；格式固定 PNG；远端存 daemon role root 的 screenshots/；本 |
| schematic#019 | clause | 31 | 1.2 写操作（改变业务服务器状态） | 对外只有一个**通用写操作** `write`：调用方一次给一组原子命令，业务包内部组织 SKILL 逐个改写，最后统一 check/save。调用方不会按单个原子调用多次。 |
| schematic#020 | table-row | 33 | 1.2 写操作（改变业务服务器状态） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| schematic#022 | table-row | 35 | 1.2 写操作（改变业务服务器状态） | \| write \| 通用写：`lib/cell/view + commands[]` \| 开 cellview(a) → 逐命令执行 → schCheck → dbSave \| S \| |
| schematic#023 | table-row | 36 | 1.2 写操作（改变业务服务器状态） | \| check_and_save \| 对目标显式执行 `schCheck` + `dbSave` \| 开 cellview(a) → check → save \| S \| |
| schematic#024 | clause | 38 | 1.2 写操作（改变业务服务器状态） | `write.commands` 每项 = `{"op": 原子名, ...该原子参数}`；业务包按顺序执行并保留每步痕迹。 |
| schematic#025 | clause | 40 | 1.2 写操作（改变业务服务器状态） | **write 支持的原子命令**：每个原子 = `op` + **索引**（要动哪个对象）+ 附加参数。 |
| schematic#026 | table-row | 42 | 1.2 写操作（改变业务服务器状态） | \| 原子名 \| 索引（动哪个） \| 附加参数 \| |
| schematic#028 | table-row | 44 | 1.2 写操作（改变业务服务器状态） | \| place_instance \| —（新建） \| `master_lib, master_cell, master_view="symbol", name, pos, orient="R0"` \| |
| schematic#029 | table-row | 45 | 1.2 写操作（改变业务服务器状态） | \| delete_instance \| `name` \| — \| |
| schematic#030 | table-row | 46 | 1.2 写操作（改变业务服务器状态） | \| rename_instance \| `name` \| `new_name` \| |
| schematic#031 | table-row | 47 | 1.2 写操作（改变业务服务器状态） | \| set_instance_params \| `name` \| `params: dict` \| |
| schematic#032 | table-row | 48 | 1.2 写操作（改变业务服务器状态） | \| set_term_nets \| `name` \| `term_nets: {term: net}`；内部超短 stub + label；可选样式 `justify/orient/font/height/stub_length`（不传用默认） \| |
| schematic#033 | table-row | 49 | 1.2 写操作（改变业务服务器状态） | \| place_wire \| —（新建） \| `points: [pos, …]`（≥2 点）；可选 `entry/route/width/color/line_style`（传了才拼，不传用底层默认） \| |
| schematic#034 | table-row | 50 | 1.2 写操作（改变业务服务器状态） | \| delete_wire \| `points`（wire 是多个 2 点 line segment，按 `pos` 端点匹配） \| — \| |
| schematic#035 | table-row | 51 | 1.2 写操作（改变业务服务器状态） | \| set_wire_properties \| `points` \| `width?, color?, line_style?` \| |
| schematic#036 | table-row | 52 | 1.2 写操作（改变业务服务器状态） | \| place_label \| —（新建） \| `text, pos`；可选样式 `justify/orient/font/height/alias`（不传用默认） \| |
| schematic#037 | table-row | 53 | 1.2 写操作（改变业务服务器状态） | \| delete_label \| `pos`（可选加 `text` 消歧义） \| — \| |
| schematic#038 | table-row | 54 | 1.2 写操作（改变业务服务器状态） | \| rename_label \| `pos`（可选加 `old_text` 消歧义） \| `new_text` \| |
| schematic#039 | table-row | 55 | 1.2 写操作（改变业务服务器状态） | \| set_label_properties \| `pos`（可选加 `text`） \| `justify?, orient?, font?, height?` \| |
| schematic#040 | table-row | 56 | 1.2 写操作（改变业务服务器状态） | \| place_pin \| —（新建） \| `name, pos`；可选 `direction/orient/off_sheet/power_sens/ground_sens/sig_type`（不传用默认/不拼） \| |
| schematic#041 | table-row | 57 | 1.2 写操作（改变业务服务器状态） | \| delete_pin \| `pos` \| — \| |
| schematic#042 | table-row | 58 | 1.2 写操作（改变业务服务器状态） | \| rename_pin \| `pos` \| `new_name` \| |
| schematic#043 | table-row | 59 | 1.2 写操作（改变业务服务器状态） | \| set_pin_properties \| `pos` \| `direction?` \| |
| schematic#044 | table-row | 60 | 1.2 写操作（改变业务服务器状态） | \| place_note \| —（新建） \| `text, pos, justify="lowerLeft", orient="R0", font="stick", height=0.0625, type="normalLabel"` \| |
| schematic#045 | table-row | 61 | 1.2 写操作（改变业务服务器状态） | \| delete_note \| `pos`（可选加 `text`） \| — \| |
| schematic#046 | table-row | 62 | 1.2 写操作（改变业务服务器状态） | \| rename_note \| `pos`（可选加 `old_text`） \| `new_text` \| |
| schematic#047 | table-row | 63 | 1.2 写操作（改变业务服务器状态） | \| set_note_properties \| `pos`（可选加 `text`） \| `justify?, orient?, font?, height?` \| |
| schematic#048 | clause | 67 | 1.3 坐标口径（P-074 定版） | - **单点坐标一律一个字段 `pos`**，值是两元素数组 `[x, y]`（user units）：索引（delete/rename/set_*）、新建（place_*）、读回（read 的实例/端子/label/pin/note）**同一口径**； |
| schematic#049 | clause | 68 | 1.3 坐标口径（P-074 定版） | - **不再出现 `xy` 字段**；**不把坐标拆成两个字段**（`{"x":…,"y":…}` 一律非法）；`pos` 缺字段/形状不对时校验必须报明缺哪个字段（不得裸 `KeyError`）； |
| schematic#050 | clause | 69 | 1.3 坐标口径（P-074 定版） | - 多点：`points: [pos, …]`；区域/矩形：`region` / `bbox` 一律**对角两点** `[pos0, pos1]`（read 与 write 同形，**不再用四元组**）； |
| schematic#058 | clause | 85 | 3. 待修订 | 跟进时**不做兼容层**（`xy`/拆字段直接判非法），校验错误必须点名缺哪个字段； |
| schematic#059 | clause | 86 | 3. 待修订 | - 唯一 name 索引只有 instance；wire=line segment 列表（无 name），label/note/pin 均按 `pos` 索引（可加 text/name 消歧义）； |
| schematic#066 | clause | 93 | 3. 待修订 | - `check_and_save` 供显式补一次校验保存；读写目标都必须带 `view`，默认 `"schematic"`，不假设只有这个视图名。 |

## 上层/3-symbol.md（73 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| symbol#004 | clause | 6 | 上层业务包：symbol | > Supersedes：Draft v2（坐标口径对齐 [2-schematic.md §1.3](2-schematic.md)：单点一律 `pos`，弃用 `xy`、不拆字段） |
| symbol#010 | clause | 17 | 1. 总述 | - `generate` 可以从 schematic 生成或覆盖 symbol，内部自带临时 view、校验、备份、回滚。 |
| symbol#011 | table-row | 23 | 2.1 读操作 | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| symbol#013 | table-row | 25 | 2.1 读操作 | \| `read` \| 读 terms/labels/shapes/orders/selection boxes；`focus` 可选 \| 只读打开 → 收集 → 解析 \| S \| |
| symbol#014 | table-row | 26 | 2.1 读操作 | \| `screenshot` \| symbol 截图；默认 `lib/cell/view`，可选 `window_id` \| 找/开窗口 → `hiWindowSaveImage` → 下载 \| S+D \| |
| symbol#016 | table-row | 30 | 2.1 读操作 | \| focus \| 返回 \| |
| symbol#018 | table-row | 32 | 2.1 读操作 | \| `terms` \| 每个 terminal：`name / direction / num_bits / bbox / access_dir` \| |
| symbol#019 | table-row | 33 | 2.1 读操作 | \| `labels` \| 每个 label：`text / label_type / pos / layer / purpose / justify / orient / font / height / bbox` \| |
| symbol#020 | table-row | 34 | 2.1 读操作 | \| `shapes` \| 已知类型 line / rect / polygon / ellipse 及兜底类型（path / arc / inst / textDisplay 等）：`kind / layer / purpose / bbox / points` \| |
| symbol#021 | table-row | 35 | 2.1 读操作 | \| `orders` \| `pin_order`（权威，`schGetPinOrder`）；`port_order` / `term_order` raw（兼容旧 reader） \| |
| symbol#022 | table-row | 36 | 2.1 读操作 | \| `selection_boxes` \| `instance/drawing` 矩形列表 \| |
| symbol#023 | clause | 38 | 2.1 读操作 | `read` 默认 `view="symbol"`、`view_type="schematicSymbol"`；必须返回通用 shapes， |
| symbol#026 | clause | 43 | 2.1 读操作 | - `view_type` 默认 `schematicSymbol`；格式固定 PNG； |
| symbol#030 | table-row | 50 | 2.2 写操作 | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| symbol#032 | table-row | 52 | 2.2 写操作 | \| `write` \| 通用写：`lib/cell/view + commands[]` \| 开 cellview(a) → 逐命令执行 → `schSymbolToPinList` → `dbSave` \| S \| |
| symbol#033 | table-row | 53 | 2.2 写操作 | \| `check_and_save` \| 对目标显式执行 symbol check + `dbSave` \| 开 cellview(a) → check → save \| S \| |
| symbol#034 | table-row | 54 | 2.2 写操作 | \| `generate` \| 从 schematic 自动生成 symbol \| 取 pin 序 → 临时 view → 校验 → 安装/回滚 \| S \| |
| symbol#038 | clause | 60 | 2.2 写操作 | 所以 write 必须先显式探测 view 是否存在，再进入 append 编辑。 |
| symbol#041 | clause | 64 | 2.2 写操作 | `write.commands` 每项 = `{"op": 原子名, ...该原子参数}`；按顺序执行并保留每步痕迹。 |
| symbol#042 | table-row | 68 | 2.2.1 几何原子 | \| 原子名 \| 索引 \| 附加参数 \| |
| symbol#044 | table-row | 70 | 2.2.1 几何原子 | \| `place_line` \| —（新建） \| `layer, purpose, points=[pos, …]`（=2 点） \| |
| symbol#045 | table-row | 71 | 2.2.1 几何原子 | \| `place_rect` \| —（新建） \| `layer, purpose, bbox=[pos0, pos1]`（对角两点，与 read 同形） \| |
| symbol#046 | table-row | 72 | 2.2.1 几何原子 | \| `place_polygon` \| —（新建） \| `layer, purpose, points=[pos, …]`（≥3 点） \| |
| symbol#047 | table-row | 73 | 2.2.1 几何原子 | \| `place_ellipse` \| —（新建） \| `layer, purpose, bbox=[pos0, pos1]` \| |
| symbol#048 | table-row | 74 | 2.2.1 几何原子 | \| `delete_shape` \| `kind + bbox/points` \| — \| |
| symbol#049 | table-row | 75 | 2.2.1 几何原子 | \| `set_shape_properties` \| `kind + bbox/points`（旧值定位） \| `layer?, purpose?, new_bbox?, new_points?`（按 kind 取合法项） \| |
| symbol#053 | clause | 81 | 2.2.1 几何原子 | - 新建原子的 `layer/purpose` 必填；不设默认层，避免猜 PDK。 |
| symbol#055 | table-row | 87 | 2.2.2 标签原子 | \| label_kind \| 底层 \| |
| symbol#057 | table-row | 89 | 2.2.2 标签原子 | \| `drawing` \| `dbCreateLabel` / `dbCreateLabel` + labelType \| |
| symbol#058 | table-row | 90 | 2.2.2 标签原子 | \| `pin_name` \| `schCreateSymbolLabel` `"pin name"` \| |
| symbol#059 | table-row | 91 | 2.2.2 标签原子 | \| `instance` \| `schCreateSymbolLabel` `"instance label"` \| |
| symbol#060 | table-row | 92 | 2.2.2 标签原子 | \| `logical` \| `schCreateSymbolLabel` `"logical label"` \| |
| symbol#061 | table-row | 94 | 2.2.2 标签原子 | \| 原子名 \| 索引 \| 附加参数 \| |
| symbol#063 | table-row | 96 | 2.2.2 标签原子 | \| `place_label` \| —（新建） \| `label_kind, text, pos, layer?, purpose?, justify?, orient?, font?, height?` \| |
| symbol#064 | table-row | 97 | 2.2.2 标签原子 | \| `delete_label` \| `label_kind + pos`（可加 `text` 消歧） \| — \| |
| symbol#065 | table-row | 98 | 2.2.2 标签原子 | \| `rename_label` \| `label_kind + pos`（可加 `old_text`） \| `new_text` \| |
| symbol#066 | table-row | 99 | 2.2.2 标签原子 | \| `set_label_properties` \| `label_kind + pos`（可加 `text`） \| `justify?, orient?, font?, height?`；`drawing` 可额外 `layer?, purpose?` \| |
| symbol#067 | clause | 103 | 2.2.3 引脚原子 | pin 以 **terminal name** 为唯一索引；旧代码 `symbol_create_pin` 本身就以 |
| symbol#069 | table-row | 106 | 2.2.3 引脚原子 | \| 原子名 \| 索引 \| 附加参数 \| |
| symbol#071 | table-row | 108 | 2.2.3 引脚原子 | \| `place_pin` \| —（新建） \| `name, pos, direction="inputOutput", half_size=0.0625, label=True, label_pos?, label_justify?, label_orient?, label_font?, label_height?` \| |
| symbol#072 | table-row | 109 | 2.2.3 引脚原子 | \| `delete_pin` \| `name` \| — \| |
| symbol#073 | table-row | 110 | 2.2.3 引脚原子 | \| `rename_pin` \| `name` \| `new_name`（同步 terminal/net/pin 与 pin-name label） \| |
| symbol#074 | table-row | 111 | 2.2.3 引脚原子 | \| `set_pin_properties` \| `name` \| `direction?, access_dir?, label?, label_justify?, label_orient?, label_font?, label_height?` \| |
| symbol#075 | clause | 113 | 2.2.3 引脚原子 | `place_pin` 内部顺序：检查 terminal 不存在 → net → term → pin 矩形 |
| symbol#082 | clause | 122 | 2.2.3 引脚原子 | 真机语义（必须遵守）： |
| symbol#089 | table-row | 133 | 2.2.4 结构原子 | \| 原子名 \| 索引 \| 附加参数 \| |
| symbol#091 | table-row | 135 | 2.2.4 结构原子 | \| `set_selection_box` \| 单例 \| `bbox=[pos0, pos1]`（`instance/drawing` 矩形，替换旧框） \| |
| symbol#092 | table-row | 136 | 2.2.4 结构原子 | \| `set_pin_order` \| —（整体） \| `term_names=[...]`；底层 `schEditPinOrder`，不是写 `cv~>termOrder` \| |
| symbol#098 | table-row | 149 | 2.3 generate | \| 参数 \| 说明 \| |
| symbol#100 | table-row | 151 | 2.3 generate | \| `lib / cell` \| 必填 \| |
| symbol#101 | table-row | 152 | 2.3 generate | \| `schematic_view` \| 默认 `"schematic"` \| |
| symbol#102 | table-row | 153 | 2.3 generate | \| `symbol_view` \| 默认 `"symbol"` \| |
| symbol#103 | table-row | 154 | 2.3 generate | \| `sort_pins` \| `None / "alphanumeric" / "geometric"` \| |
| symbol#104 | table-row | 155 | 2.3 generate | \| `overwrite` \| 默认 `false` \| |
| symbol#105 | table-row | 156 | 2.3 generate | \| `timeout` \| 可选 \| |
| symbol#107 | clause | 160 | 2.3 generate | 1. source/target view 必须不同； |
| symbol#113 | clause | 166 | 2.3 generate | 7. 任一步失败尝试回滚；回滚失败保留 backup view 并返回失败； |
| symbol#117 | clause | 172 | 2.3 generate | `schPinListToSymbolGen` 对显式 pin list 也按传入顺序生成，**`sort_pins` 参数保留但不承诺排序效果**。 |
| symbol#118 | clause | 173 | 2.3 generate | `schPinListToSymbolGen` 会自行 `dbSave`，因此只能用于临时 view（当前实现即如此）。 |
| symbol#121 | clause | 180 | 3. 不在本版 | - `port_order` / `term_order` 的独立写入原子； |
| symbol#124 | clause | 183 | 3. 不在本版 | - 移动类原子（`move_shape / move_label / move_pin`）：底层已确认 `dbMoveFig/dbMoveShape` 可用， |
| symbol#130 | clause | 189 | 3. 不在本版 | - circle / arc / donut / path 原子； |
| symbol#131 | clause | 190 | 3. 不在本版 | - 并发写。 |
| symbol#132 | table-row | 194 | 4. 真机结论（已闭环） | \| 项 \| 结论 \| |
| symbol#134 | table-row | 196 | 4. 真机结论（已闭环） | \| `set_shape_properties` 可写字段 \| line/polygon 的 `points`、rect/ellipse 的 `bBox`、`layerName`/`purpose` 均已真机验证生效 \| |
| symbol#135 | table-row | 197 | 4. 真机结论（已闭环） | \| `set_pin_properties` 移动 pin \| 本版不支持；`dbMoveFig` 可用，留作扩展 \| |
| symbol#136 | table-row | 198 | 4. 真机结论（已闭环） | \| label 索引 \| 坐标容差 0.001；`label_kind` 参与消歧，`pin_name` 另外要求 `pin/label` \| |
| symbol#137 | table-row | 199 | 4. 真机结论（已闭环） | \| `rename_pin` 同步 \| 不联动：必须显式 `dbRenameNet` + 手工改 pin-name label（已测） \| |
| symbol#138 | table-row | 200 | 4. 真机结论（已闭环） | \| `schEditPinOrder` \| 真机生效，`pin_order` 与 `port_order`/`term_order` 一致 \| |
| symbol#139 | table-row | 201 | 4. 真机结论（已闭环） | \| `schCreateSymbolLabel` \| `"pin name"`/`"instance label"`/`"logical label"` 可用；`"device label"` 在 symbol 里返回 nil（文档与实测不符） \| |
| symbol#140 | table-row | 202 | 4. 真机结论（已闭环） | \| `read.shapes` 覆盖 \| 已覆盖 line/rect/polygon/ellipse + 兜底 objType（path/arc/inst/textDisplay 等） \| |
| symbol#141 | table-row | 203 | 4. 真机结论（已闭环） | \| 截图 \| symbol 窗口真机出图；空 symbol 窗口出 1 色黑图（无内容时的正常表现），有内容窗口出 7 色真实图 \| |
| symbol#142 | table-row | 204 | 4. 真机结论（已闭环） | \| `write` 执行方式 \| 逐命令 `execute_skill` + 末尾统一 check/save，保留每步痕迹；**非事务**，失败响应带 `commands applied: k/n` \| |

## 上层/4-layout.md（99 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| layout#004 | clause | 6 | 上层业务包：layout | > Supersedes：Draft v4（坐标口径对齐 [2-schematic.md §1.3](2-schematic.md)：单点一律 `pos`，弃用 `xy`、不拆字段） |
| layout#006 | clause | 11 | 1. 业务操作 | 核心是读和写。写是**按对象对称**的原子操作：shape（rect/polygon/path/line）、label、instance、mosaic、via |
| layout#011 | clause | 18 | 1. 业务操作 | - viewType 固定 `maskLayout`，view 默认 `"layout"`； |
| layout#015 | clause | 22 | 1. 业务操作 | - 不提供"按当前选择集"的写操作（selection 是全局 GUI 状态，不能作业务索引）。 |
| layout#016 | table-row | 26 | 1.1 读操作（不改变业务服务器状态） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| layout#018 | table-row | 28 | 1.1 读操作（不改变业务服务器状态） | \| read \| `focus` 可选、可组合；不填=全部；可带区域/对象过滤 \| 开只读 → 按 focus 执行对应 SKILL 段 → 解析 \| S \| |
| layout#019 | table-row | 29 | 1.1 读操作（不改变业务服务器状态） | \| screenshot \| 版图截图：默认 `lib/cell/view`，可选 `window_id`；格式 PNG \| 找/开窗口 → hiWindowSaveImage → 下载 \| S+D \| |
| layout#023 | clause | 34 | 1.1 读操作（不改变业务服务器状态） | - 可选 `detail`：`geometry`（默认，含坐标与属性）/ `index`（只回 type + LPP，供大版图廉价索引）； |
| layout#024 | clause | 35 | 1.1 读操作（不改变业务服务器状态） | - 可选 `object_filter`：每个对象一个条目，**不写默认 `all`**；条目可以是 `none`（该类一个都不读）； |
| layout#028 | clause | 39 | 1.1 读操作（不改变业务服务器状态） | - 可选 `region_mode`：`intersect`（默认）/ `contain`，作用于 object_filter 里的 region； |
| layout#029 | clause | 40 | 1.1 读操作（不改变业务服务器状态） | - 可选 `depth`：`0`（默认，只读本层）/ `>0`（跨层，需同时给 `region` 或 `layers`）； |
| layout#033 | table-row | 46 | 1.1 读操作（不改变业务服务器状态） | \| focus \| 字段 \| |
| layout#035 | table-row | 48 | 1.1 读操作（不改变业务服务器状态） | \| `summary` \| `bbox`、`shape_count`、`instance_count`、`via_count`、按 LPP 的 shape 计数 \| |
| layout#036 | table-row | 49 | 1.1 读操作（不改变业务服务器状态） | \| `shapes` \| `obj_type / layer / purpose / lpp / bbox / points / width / path_style`；label 额外 `text / pos / height / justify / orient / font` \| |
| layout#037 | table-row | 50 | 1.1 读操作（不改变业务服务器状态） | \| `instances` \| `name / master(lib,cell,view) / pos / orient / num_inst / bbox` \| |
| layout#038 | table-row | 51 | 1.1 读操作（不改变业务服务器状态） | \| `vias` \| `via_name / pos / orient / bbox` \| |
| layout#039 | clause | 55 | 1.2 写操作（改变业务服务器状态） | 对外只有一个**通用写操作** `write`：调用方一次给一组原子命令，业务包内部组织 SKILL 逐个改写，最后统一 `dbSave`。 |
| layout#040 | clause | 56 | 1.2 写操作（改变业务服务器状态） | 调用方不会按单个原子调用多次。 |
| layout#041 | table-row | 58 | 1.2 写操作（改变业务服务器状态） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| layout#043 | table-row | 60 | 1.2 写操作（改变业务服务器状态） | \| write \| 通用写：`lib/cell/view + commands[]` \| 探测 view 存在 → 开 cellview(a) → 逐命令 → dbSave \| S \| |
| layout#044 | table-row | 61 | 1.2 写操作（改变业务服务器状态） | \| gds \| GDS 导入/导出，`action=export\\|import` \| 见 §1.3 \| S+C+U+D \| |
| layout#045 | clause | 63 | 1.2 写操作（改变业务服务器状态） | `write.commands` 每项 = `{"op": 原子名, ...该原子参数}`；按顺序执行并保留每步痕迹。 |
| layout#047 | clause | 65 | 1.2 写操作（改变业务服务器状态） | **不得靠 `a` 模式凭空创建**；非事务——中途失败时前面的命令已生效，失败响应带 `commands applied: k/n`。 |
| layout#048 | clause | 67 | 1.2 写操作（改变业务服务器状态） | **write 支持的原子命令**：每个原子 = `op` + **索引**（要动哪个对象）+ 附加参数。 |
| layout#049 | table-row | 69 | 1.2 写操作（改变业务服务器状态） | \| 对象 \| 原子名 \| 索引（动哪个） \| 附加参数 \| |
| layout#051 | table-row | 71 | 1.2 写操作（改变业务服务器状态） | \| rect \| `place_rect` \| —（新建） \| `layer, purpose, bbox=[pos0, pos1]`（对角两点，**与 read 同形**） \| |
| layout#052 | table-row | 72 | 1.2 写操作（改变业务服务器状态） | \| ellipse \| `place_ellipse` \| —（新建） \| `layer, purpose, bbox=[pos0, pos1]`（同上） \| |
| layout#053 | table-row | 73 | 1.2 写操作（改变业务服务器状态） | \| polygon \| `place_polygon` \| —（新建） \| `layer, purpose, points=[pos, …]`（≥3 点，去重后非退化） \| |
| layout#054 | table-row | 74 | 1.2 写操作（改变业务服务器状态） | \| path \| `place_path` \| —（新建） \| `layer, purpose, points=[pos, …]`（≥2 点）, `width>0`；可选 `style`（7 个合法值，不传用 `truncateExtend`） \| |
| layout#055 | table-row | 75 | 1.2 写操作（改变业务服务器状态） | \| line \| `place_line` \| —（新建） \| `layer, purpose, points=[pos, …]`（=2 点） \| |
| layout#056 | table-row | 76 | 1.2 写操作（改变业务服务器状态） | \| shape（通用） \| `delete_shape` \| `kind + layer/purpose + (bbox\\|points)`；`all=false` 默认唯一命中 \| — \| |
| layout#057 | table-row | 77 | 1.2 写操作（改变业务服务器状态） | \| shape（通用） \| `set_shape_properties` \| 同 `delete_shape` \| `new_bbox?（=[pos0, pos1]）, new_points?, new_width?` \| |
| layout#058 | table-row | 78 | 1.2 写操作（改变业务服务器状态） | \| shape（按层批量） \| `delete_shapes_on_layer` \| `layer, purpose` \| `types?`（缺省=该 LPP 全部类型） \| |
| layout#059 | table-row | 79 | 1.2 写操作（改变业务服务器状态） | \| label \| `place_label` \| —（新建） \| `layer, purpose, pos, text`；可选 `justify/orient/font/height`（不传用底层默认） \| |
| layout#060 | table-row | 80 | 1.2 写操作（改变业务服务器状态） | \| label \| `delete_label` \| `pos`（可选加 `text`/`layer` 消歧义） \| — \| |
| layout#061 | table-row | 81 | 1.2 写操作（改变业务服务器状态） | \| label \| `rename_label` \| `pos`（可选加 `old_text`） \| `new_text` \| |
| layout#062 | table-row | 82 | 1.2 写操作（改变业务服务器状态） | \| label \| `set_label_properties` \| `pos`（可选加 `text`） \| `new_pos?, new_height?, new_justify?, new_orient?, new_font?`（至少给一个） \| |
| layout#063 | table-row | 83 | 1.2 写操作（改变业务服务器状态） | \| instance \| `place_instance` \| —（新建） \| `master_lib, master_cell, master_view="layout", name, pos, orient="R0"`；可选 `num_inst`（数组实例，name 变 `A<0:n>`） \| |
| layout#064 | table-row | 84 | 1.2 写操作（改变业务服务器状态） | \| instance \| `delete_instance` \| `name` \| — \| |
| layout#065 | table-row | 85 | 1.2 写操作（改变业务服务器状态） | \| instance \| `rename_instance` \| `name` \| `new_name` \| |
| layout#066 | table-row | 86 | 1.2 写操作（改变业务服务器状态） | \| instance \| `set_instance_properties` \| `name` \| `new_pos?, new_orient?`（`new_pos` 必须写 point；`mag`/`master` 只读，不在本版） \| |
| layout#067 | table-row | 87 | 1.2 写操作（改变业务服务器状态） | \| mosaic \| `place_mosaic` \| —（新建） \| `master_lib, master_cell, master_view="layout", name, pos, orient` , `rows, cols, row_pitch, col_pitch` \| |
| layout#068 | table-row | 88 | 1.2 写操作（改变业务服务器状态） | \| mosaic \| `delete_mosaic` \| `name` \| — \| |
| layout#069 | table-row | 89 | 1.2 写操作（改变业务服务器状态） | \| via \| `place_via` \| —（新建） \| `via_name, pos, orient="R0"`；techfile-gated（§1.2.2） \| |
| layout#070 | table-row | 90 | 1.2 写操作（改变业务服务器状态） | \| via \| `delete_via` \| `via_name + pos + orient` \| — \| |
| layout#075 | clause | 99 | 1.2.1 LPP 与失败语义 | - 底层 `dbCreateXxx` 失败**返回 nil 而不抛错** → 每个原子必须判返回值，失败即业务失败； |
| layout#076 | clause | 100 | 1.2.1 LPP 与失败语义 | - 默认**不做** techfile 预检；`write` 可选 `strict_lpp=true` 时校验：`techGetLayerNum(tf, layer)` 非 nil + |
| layout#079 | clause | 103 | 1.2.1 LPP 与失败语义 | 批量删层用 `dbShapeQuery(cv lpp bbox 0 <stopLevel>)`，**stopLevel 必须覆盖层次**； |
| layout#086 | table-row | 117 | 1.3 gds（导入 / 导出收拢为一个操作） | \| 参数 \| 说明 \| |
| layout#088 | table-row | 119 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `action` \| `export` / `import`，必填 \| |
| layout#089 | table-row | 120 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `lib / cell` \| 必填；`view` 默认 `"layout"` \| |
| layout#090 | table-row | 121 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `file_path` \| export：本机 GDS 目标路径；import：GDS 源文件（本机→上传，远端→直接用） \| |
| layout#091 | table-row | 122 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `layer_map` \| layer map 文件（export 映射 OA LPP→stream 层号；import 用 `-layerMap` 把 stream 层号映射回 OA）。缺省时导出会走自动 mapping（层号不确定），导入在本环境会直接失败（`XSTRM-74`） \| |
| layout#092 | table-row | 123 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `ref_lib_file` \| 仅 import：参考库清单（`-refLibList`），可选 \| |
| layout#093 | table-row | 124 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `tech_lib` \| import 必填：目标库绑定/对齐的技术库（`-attachTechFileOfLib`） \| |
| layout#094 | table-row | 125 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `log_path` \| export 默认 `<output stem>.xstream.log`；import 默认远端工作目录 `strmIn.log` \| |
| layout#095 | table-row | 126 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `timeout` / `poll_interval` \| export 默认 300s / 0.5s；import 默认 600s / 3s \| |
| layout#096 | table-row | 127 | 1.3 gds（导入 / 导出收拢为一个操作） | \| `cleanup_policy` \| 仅 export：`success`（默认）/ `always` / `never` \| |
| layout#120 | clause | 155 | 1.3 gds（导入 / 导出收拢为一个操作） | `XSTRM-234` + `Translation completed` 才算完成；**完成前不得读目标 cellview**（会读到旧版 stale bbox）； |
| layout#130 | table-row | 171 | 1.4 screenshot | \| 参数 \| 说明 \| |
| layout#132 | table-row | 173 | 1.4 screenshot | \| `lib / cell / view` \| 默认目标；用于在窗口列表里按 `w~>cellView` 的 lib/cell/view 匹配已开窗口 \| |
| layout#133 | table-row | 174 | 1.4 screenshot | \| `window_id` \| 可选显式目标；**显式给了坏 id 直接业务失败，不做 X11/display 回退** \| |
| layout#134 | table-row | 175 | 1.4 screenshot | \| `region` \| `[pos0, pos1]`（user units）；截前 `hiZoomIn(window bbox)` 把区域填满窗口 \| |
| layout#135 | table-row | 176 | 1.4 screenshot | \| `toplevel` / `central_widget` \| 透传给 `hiWindowSaveImage` \| |
| layout#136 | table-row | 177 | 1.4 screenshot | \| `leave_open` \| 默认 `false`；只关闭本操作自己打开的窗口，不动别人已开的窗口 \| |
| layout#139 | clause | 182 | 1.4 screenshot | - **禁止不带 bbox 的 `hiZoomIn`/`hiZoomOut`**（会进交互橡皮筋并卡死 SKILL 通道）； |
| layout#143 | table-row | 190 | 1.5 display（展示，不落数据） | \| 原子 \| 底层 \| 说明 \| |
| layout#145 | table-row | 192 | 1.5 display（展示，不落数据） | \| `set_layers_visible` \| `leSetLayerVisible(lpp t/nil tf)` \| 指定 LPP 显示/隐藏 \| |
| layout#146 | table-row | 193 | 1.5 display（展示，不落数据） | \| `show_only_layers` \| `leSetAllLayerVisible(nil tf)` + 逐个显示 \| 只显示指定 LPP \| |
| layout#147 | table-row | 194 | 1.5 display（展示，不落数据） | \| `set_entry_layer` \| `leSetEntryLayer(lpp tf)` \| 录入层（LSW 当前层） \| |
| layout#148 | table-row | 195 | 1.5 display（展示，不落数据） | \| `fit_view` / `zoom` \| `hiZoomAbsoluteScale(w n)` / `hiZoomIn(w bbox)` \| 需窗口；显式 `window_id` \| |
| layout#152 | table-row | 204 | 2. 归属（不在本包） | \| 能力 \| 归属 \| |
| layout#154 | table-row | 206 | 2. 归属（不在本包） | \| view create/replace/delete/rename、cell delete \| cellview \| |
| layout#155 | table-row | 207 | 2. 归属（不在本包） | \| 结构 Verilog 导入 `ihdl`、PG label、标签后处理流水线 \| digital-import \| |
| layout#156 | table-row | 208 | 2. 归属（不在本包） | \| 截图机制（窗口解析、抓屏、下载） \| gui 机制 + layout 领域封装 \| |
| layout#157 | table-row | 209 | 2. 归属（不在本包） | \| selection / highlight / LSW 交互 \| 不进业务 API \| |
| layout#158 | clause | 213 | 3. 不在本版 | - 路由抽象（多层/总线）与 `clear_routing`：调用方用几何原子组合； |
| layout#163 | clause | 218 | 3. 不在本版 | - 并发写。 |
| layout#164 | table-row | 222 | 4. 决策记录（2026-09-21） | \| # \| 决策 \| |
| layout#166 | table-row | 224 | 4. 决策记录（2026-09-21） | \| 1 \| `display` 作为 layout 的展示子操作（底层 `le*` SKILL，不需要 GUI 也能改可见性） \| |
| layout#167 | table-row | 225 | 4. 决策记录（2026-09-21） | \| 2 \| `export_gds` 放 layout 包（旧公开面即 `client.layout.export_gds`） \| |
| layout#168 | table-row | 226 | 4. 决策记录（2026-09-21） | \| 3 \| GDS 导出的 `reason` 收敛为 §1.3 的 9 个值，不沿用旧 13 值枚举 \| |
| layout#169 | table-row | 227 | 4. 决策记录（2026-09-21） | \| 4 \| via 本版实现，但标注 techfile-gated；真机验收需带 PDK 的环境 \| |
| layout#170 | table-row | 228 | 4. 决策记录（2026-09-21） | \| 5 \| region 查询本版做；`depth>0` 只走 `dbShapeQuery` 路径，不展开完整层级树 \| |
| layout#171 | table-row | 229 | 4. 决策记录（2026-09-21） | \| 6 \| `strict_lpp` 默认 `false`（轻校验），严格模式可选 \| |
| layout#172 | table-row | 230 | 4. 决策记录（2026-09-21） | \| 7 \| 旧 `route_multilayer`/`route_bus`/`clear_routing` 降级为调用方组合；`set_visibility` 进 `display`；`select_delete`/`delete_cell` 不进 API（cell 删除归 cellview） \| |
| layout#173 | table-row | 231 | 4. 决策记录（2026-09-21） | \| 8 \| **GDS 导入与导出都归本包**，收拢为一个 `gds` 操作（`action=export\\|import`）；digital-import 只保留 `ihdl` / PG label / 标签后处理 \| |
| layout#174 | table-row | 232 | 4. 决策记录（2026-09-21） | \| 9 \| 截图口径**参考 schematic + maestro**：cellView 匹配窗口 → `geOpen` 兜底、`window_id` 显式则坏 id 直接失败、`region` 用 `hiZoomIn(bbox)`、`toplevel/central_widget` 透传、PNG 落 role root `screenshots/` 与本地 `artifact/screenshots/`、无 X11 回退 \| |
| layout#175 | table-row | 233 | 4. 决策记录（2026-09-21） | \| 10 \| `gds` 的参数按 vendor 选项拆开：`layer_map`（导出/导入的层映射）与 `ref_lib_file`（仅导入 `-refLibList`）；导入选 cell 用 `-topCell` \| |
| layout#176 | table-row | 234 | 4. 决策记录（2026-09-21） | \| 11 \| 索引容差由 0.001 收敛为 **0.0005**（半个 dbu）；via 索引改为 `pos + orient`（viaDef/name 不可回读） \| |
| layout#179 | clause | 240 | 5. 真机事实（IC6.1.8，2026-09-21 实 | 3. `dbCreateXxx` 失败分两类：**非法 LPP → 抛 SKILL 硬错误**；**几何非法 → nil + WARNING** → |
| layout#180 | clause | 241 | 5. 真机事实（IC6.1.8，2026-09-21 实 | 上层既要判返回值也要能收错误；`pos` 写 **point**（`7:8`），`bBox`/`points` 写 list； |
| layout#181 | clause | 242 | 5. 真机事实（IC6.1.8，2026-09-21 实 | 4. **`dbClose` 不落盘**：必须显式 `dbSave` 后再 `dbClose`；未保存的 cellview 留在会话里会污染导出 |
| layout#184 | clause | 245 | 5. 真机事实（IC6.1.8，2026-09-21 实 | 6. 区域/层级查询显式给 level（`dbShapeQuery(cv lpp bbox 0 32)`）；3 参数默认形式会下探一层 instance |
| layout#185 | clause | 246 | 5. 真机事实（IC6.1.8，2026-09-21 实 | 但**不含 via 生成图形**，不要依赖默认； |
| layout#189 | clause | 250 | 5. 真机事实（IC6.1.8，2026-09-21 实 | 9. via 的 `~>viaDef` / `~>name` **不可读**（都是 nil）⇒ 只能按 `pos + orient` 索引； |
| layout#196 | clause | 257 | 5. 真机事实（IC6.1.8，2026-09-21 实 | **不能**用来判断 `dbCreate*` 是否接受某 LPP（真机已验证 `("y0" "pin")` 不在列表里但可建）； |
| layout#199 | clause | 260 | 5. 真机事实（IC6.1.8，2026-09-21 实 | 与 SKILL 侧会话的在内存库表**不是**同一份 ⇒ 会话 run 目录的 `cds.lib` 是唯一权威解析入口； |
| layout#202 | clause | 263 | 5. 真机事实（IC6.1.8，2026-09-21 实 | 同会话后续 SKILL 调用全部超时（P-075）。批处理路径从根上避开，别再走窗体。 |

## 上层/5-cellview.md（26 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| cellview#006 | clause | 11 | 1. 业务操作 | 重点在“文件”管理，对象体系分三层：**lib → cell → view**（categories 特殊，另行定义）。每层都有 list/create/copy/delete/rename；get/bind 只在 lib 层。 |
| cellview#007 | table-row | 15 | 1.1 读操作（不改变业务服务器状态） | \| 层级 \| 操作名 \| 说明 \| 接口 \| |
| cellview#009 | table-row | 17 | 1.1 读操作（不改变业务服务器状态） | \| lib \| list \| 列出所有 lib \| S \| |
| cellview#010 | table-row | 18 | 1.1 读操作（不改变业务服务器状态） | \| lib \| get \| 读 lib 元数据（path/tech） \| S \| |
| cellview#011 | table-row | 19 | 1.1 读操作（不改变业务服务器状态） | \| cell \| list \| 列出指定 lib 中的所有 cell；给 `category` 时只列该分类下的 cell \| S \| |
| cellview#012 | table-row | 20 | 1.1 读操作（不改变业务服务器状态） | \| view \| list \| 列出指定 cell 中的所有 view \| S \| |
| cellview#013 | table-row | 21 | 1.1 读操作（不改变业务服务器状态） | \| category \| list \| 列出指定 lib 的所有 categories \| S \| |
| cellview#014 | table-row | 25 | 1.2 写操作（改变业务服务器状态） | \| 层级 \| 操作名 \| 说明 \| 接口 \| |
| cellview#016 | table-row | 27 | 1.2 写操作（改变业务服务器状态） | \| lib \| create \| 新建 lib \| S \| |
| cellview#017 | table-row | 28 | 1.2 写操作（改变业务服务器状态） | \| lib \| copy \| 复制 lib \| S \| |
| cellview#018 | table-row | 29 | 1.2 写操作（改变业务服务器状态） | \| lib \| delete \| 删除 lib \| S \| |
| cellview#019 | table-row | 30 | 1.2 写操作（改变业务服务器状态） | \| lib \| rename \| lib 改名 \| S \| |
| cellview#020 | table-row | 31 | 1.2 写操作（改变业务服务器状态） | \| lib \| bind \| 绑定技术库（tech） \| S \| |
| cellview#021 | table-row | 32 | 1.2 写操作（改变业务服务器状态） | \| cell \| copy \| 复制 cell \| S \| |
| cellview#022 | table-row | 33 | 1.2 写操作（改变业务服务器状态） | \| cell \| delete \| 删除 cell \| S \| |
| cellview#023 | table-row | 34 | 1.2 写操作（改变业务服务器状态） | \| cell \| rename \| cell 改名 \| S \| |
| cellview#024 | table-row | 35 | 1.2 写操作（改变业务服务器状态） | \| view \| create \| 在指定 cell 中新建 view；cell 尚不存在时，首个 view 的创建即创建 cell \| S \| |
| cellview#025 | table-row | 36 | 1.2 写操作（改变业务服务器状态） | \| view \| copy \| 复制 view \| S \| |
| cellview#026 | table-row | 37 | 1.2 写操作（改变业务服务器状态） | \| view \| delete \| 删除 view \| S \| |
| cellview#027 | table-row | 38 | 1.2 写操作（改变业务服务器状态） | \| view \| rename \| view 改名 \| S \| |
| cellview#028 | table-row | 39 | 1.2 写操作（改变业务服务器状态） | \| category \| create \| 新建 category \| S \| |
| cellview#029 | table-row | 40 | 1.2 写操作（改变业务服务器状态） | \| category \| delete \| 删除 category（不级联删 cell） \| S \| |
| cellview#030 | table-row | 41 | 1.2 写操作（改变业务服务器状态） | \| category \| rename \| category 改名 \| S \| |
| cellview#031 | table-row | 42 | 1.2 写操作（改变业务服务器状态） | \| category \| add_cell \| 把 cell 加入 category \| S \| |
| cellview#032 | table-row | 43 | 1.2 写操作（改变业务服务器状态） | \| category \| remove_cell \| 把 cell 移出 category \| S \| |
| cellview#038 | clause | 57 | 3. 预留（暂不实现） | - **harvest**：输入一个 lib，一次性枚举 lib → cells → views 全貌，对 view 分类，并附带 Maestro setup/analysis 名与结果目录存在性，输出 JSON 报告。可由三层 `list` 拼出，先不实现。 |

## 上层/6-maestro.md（84 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| maestro#003 | clause | 5 | 上层业务包：maestro | > 状态：Draft（操作与原子已成形；参数细节待逐项定稿；暂未纳入 README 治理） |
| maestro#004 | clause | 6 | 上层业务包：maestro | > Supersedes：Draft v3（补全历史类读写与全部操作/原子的实现底层；去掉 history 复制） |
| maestro#008 | table-row | 17 | 2. 操作总表 | \| 大类 \| 操作 \| 一句话说明 \| 接口 \| |
| maestro#010 | table-row | 19 | 2. 操作总表 | \| 配置类 \| `read_config` \| 读当前配置（变量、参数、tests、corners、specs） \| S \| |
| maestro#011 | table-row | 20 | 2. 操作总表 | \| 配置类 \| `write` \| 通用写，`commands[]` 里的配置原子 \| S \| |
| maestro#012 | table-row | 21 | 2. 操作总表 | \| 结果类 \| `write` \| 同一个通用写，`commands[]` 里的结果原子（output / spec） \| S \| |
| maestro#013 | table-row | 22 | 2. 操作总表 | \| 结果类 \| `read_results` \| 读结果点、spec 状态、yield；读单条波形 \| S+D \| |
| maestro#014 | table-row | 23 | 2. 操作总表 | \| 导出类 \| `export` \| 按 `kind` 批量导出文件 \| S+C+D \| |
| maestro#015 | table-row | 24 | 2. 操作总表 | \| 历史类 \| `read_history` \| 不带 history：列出全部并给完成情况；带 history：给该条进度与详情 \| S \| |
| maestro#016 | table-row | 25 | 2. 操作总表 | \| 历史类 \| `write_history` \| 通用写，`commands[]` 里的历史原子（删/改名/锁） \| S \| |
| maestro#017 | table-row | 26 | 2. 操作总表 | \| 仿真类 \| `open_gui` / `close_gui` \| GUI 会话开关 \| S+G \| |
| maestro#018 | table-row | 27 | 2. 操作总表 | \| 仿真类 \| `run` \| 启动仿真；`blocking` 决定是否等到完成（默认非阻塞） \| S+C \| |
| maestro#019 | table-row | 28 | 2. 操作总表 | \| 展示类 \| `open_waveform_gui` / `close_waveform_gui` \| 给人看的交互波形窗口 \| S+G \| |
| maestro#022 | table-row | 38 | 3.1 read_config | \| 返回项 \| 底层 \| |
| maestro#024 | table-row | 40 | 3.1 read_config | \| 变量表 \| `maeGetVar` / `axlGetVars` \| |
| maestro#025 | table-row | 41 | 3.1 read_config | \| 参数表 \| `maeGetParameter` \| |
| maestro#026 | table-row | 42 | 3.1 read_config | \| tests \| `axlGetTests` \| |
| maestro#027 | table-row | 43 | 3.1 read_config | \| corners \| `axlGetCorners`、`axlGetCornersForATest` \| |
| maestro#028 | table-row | 44 | 3.1 read_config | \| specs \| `axlGetSpecs` \| |
| maestro#029 | table-row | 45 | 3.1 read_config | \| analyses / outputs 列表 \| **待定**：未找到现成枚举函数，需用 `maeGetTestSession` 逐 test 取 \| |
| maestro#030 | clause | 49 | 3.2 write（配置原子） | 每个原子 = `op` + **索引**（动哪个）+ 附加参数。整批在一个后台会话内顺序执行，末尾统一保存。 |
| maestro#031 | table-row | 51 | 3.2 write（配置原子） | \| 分组 \| 原子 \| 索引 \| 附加参数 \| 底层 \| |
| maestro#033 | table-row | 53 | 3.2 write（配置原子） | \| 器件 \| set_test \| test \| lib / cell / view / simulator \| `maeCreateTest` \| |
| maestro#034 | table-row | 54 | 3.2 write（配置原子） | \| 器件 \| set_design \| test \| lib / cell / view \| `maeSetDesign` \| |
| maestro#035 | table-row | 55 | 3.2 write（配置原子） | \| 分析 \| set_analysis \| test \| analysis / enable / options \| `maeSetAnalysis` \| |
| maestro#036 | table-row | 56 | 3.2 write（配置原子） | \| 变量 \| set_var \| name \| value / scope（global、test、corner） \| `maeSetVar`（`?typeName`/`?typeValue`） \| |
| maestro#037 | table-row | 57 | 3.2 write（配置原子） | \| 变量 \| delete_var \| name \| test? \| `axlRemoveElement(axlGetVar(...))` \| |
| maestro#038 | table-row | 58 | 3.2 write（配置原子） | \| 变量 \| set_parameter \| name \| value / scope \| `maeSetParameter` \| |
| maestro#039 | table-row | 59 | 3.2 write（配置原子） | \| 环境 \| set_env_option \| test \| options \| `maeSetEnvOption` \| |
| maestro#040 | table-row | 60 | 3.2 write（配置原子） | \| 环境 \| set_sim_option \| test \| options \| `maeSetSimOption` \| |
| maestro#041 | table-row | 61 | 3.2 write（配置原子） | \| corner \| set_corner \| name \| disable_tests? \| `maeSetCorner` \| |
| maestro#042 | table-row | 62 | 3.2 write（配置原子） | \| corner \| setup_corner \| name \| model_file / model_section / variables \| `maeSetCorner` + `maeSetVar(corner)` + `axlGetCorner`/`axlPutModel`/`axlSetModelFile`/`axlSetModelSection` \| |
| maestro#043 | table-row | 63 | 3.2 write（配置原子） | \| corner \| load_corners \| —（文件导入） \| filepath / sections / operation \| `maeLoadCorners`（CSV 先经 File 接口上传） \| |
| maestro#044 | table-row | 64 | 3.2 write（配置原子） | \| 运行 \| set_run_mode \| —（会话级） \| run_mode \| `maeSetCurrentRunMode` \| |
| maestro#045 | table-row | 65 | 3.2 write（配置原子） | \| 运行 \| set_job_control_mode \| —（会话级） \| mode \| `maeSetJobControlMode` \| |
| maestro#046 | table-row | 66 | 3.2 write（配置原子） | \| 运行 \| set_job_policy \| test? \| policy / job_type \| `maeSetJobPolicy` \| |
| maestro#047 | table-row | 67 | 3.2 write（配置原子） | \| 运行 \| set_simulator_mode \| test \| mode \| `asiSetHighPerformanceOptionVal`（内部映射 `'uniMode` / `'spectreXPreset`） \| |
| maestro#048 | table-row | 73 | 4.1 write（结果原子） | \| 原子 \| 索引 \| 附加参数 \| 底层 \| |
| maestro#050 | table-row | 75 | 4.1 write（结果原子） | \| add_output \| test \| name / output_type / signal_name / expr \| `maeAddOutput` \| |
| maestro#051 | table-row | 76 | 4.1 write（结果原子） | \| set_spec \| test \| name / lt / gt \| `maeSetSpec` \| |
| maestro#052 | table-row | 80 | 4.2 read_results | \| 能力 \| 底层 \| |
| maestro#054 | table-row | 82 | 4.2 read_results | \| 读全部点、spec 状态、yield \| `maeExportOutputView` 导 Detail CSV → 下载 → 解析 \| |
| maestro#055 | table-row | 83 | 4.2 read_results | \| 读单条波形 \| `maeOpenResults` → `openResults` → `selectResults` → `ocnPrint` → 下载文本 \| |
| maestro#056 | table-row | 84 | 4.2 read_results | \| 结果目录/最新 history 定位 \| `asiGetResultsDir` + 旧代码的 mtime / 自然排序规则 \| |
| maestro#058 | table-row | 90 | 5. 导出类 | \| kind \| 产物 \| 底层 \| |
| maestro#060 | table-row | 92 | 5. 导出类 | \| netlist \| 指定 corner 的网表 \| `maeCreateNetlistForCorner` \| |
| maestro#061 | table-row | 93 | 5. 导出类 | \| script \| 等价 OCEAN 脚本 \| `maeWriteScript` \| |
| maestro#062 | table-row | 94 | 5. 导出类 | \| outputs_csv \| outputs 表 CSV \| `maeExportOutputView` \| |
| maestro#063 | table-row | 95 | 5. 导出类 | \| snapshot \| 全量快照包（sdb / active.state / 过滤 XML / 按点 netlist 与 PSF） \| 快照模板 + `find`/`tar` 打包 \| |
| maestro#064 | table-row | 96 | 5. 导出类 | \| screenshot \| Maestro 窗口 PNG \| `hiWindowSaveImage`（窗口按 `cellView~>viewName` 定位） \| |
| maestro#067 | table-row | 106 | 6.1 read_history | \| 返回项 \| 底层 \| |
| maestro#069 | table-row | 108 | 6.1 read_history | \| 全部 history 名称 \| `axlGetHistory` \| |
| maestro#070 | table-row | 109 | 6.1 read_history | \| 每个 history 的完成情况（running / done / failed） \| `axlGetRunStatus` 逐条查询 \| |
| maestro#071 | table-row | 110 | 6.1 read_history | \| 当前 history / 最新 history \| `axlGetCurrentHistory`；旧代码的 mtime 排序 / 自然排序规则 \| |
| maestro#073 | table-row | 114 | 6.1 read_history | \| 返回项 \| 底层 \| |
| maestro#075 | table-row | 116 | 6.1 read_history | \| 进度（完成的点 / 测试 / corner 数） \| `axlGetRunStatus`（指定 history） \| |
| maestro#076 | table-row | 117 | 6.1 read_history | \| 锁状态 \| `axlGetHistoryLock` / `maeGetHistoryLockFlag`（0–4 五种状态） \| |
| maestro#077 | table-row | 118 | 6.1 read_history | \| 结果目录 \| `axlGetResultsLocation` 等路径查询 \| |
| maestro#078 | table-row | 119 | 6.1 read_history | \| 覆盖式运行目标 \| `axlGetOverwriteHistoryName` \| |
| maestro#079 | table-row | 123 | 6.2 write_history（历史原子） | \| 原子 \| 索引 \| 附加参数 \| 底层 \| |
| maestro#081 | table-row | 125 | 6.2 write_history（历史原子） | \| delete \| history \| — \| Assembler：`axlRemoveElement(axlGetHistoryEntry(sdb, name))`；Explorer：`maeDeleteExplorerHistory(session, name)` \| |
| maestro#082 | table-row | 126 | 6.2 write_history（历史原子） | \| delete_results \| history \| keep_netlist? / keep_quick_plot? \| `maeDeleteSimulationData`（对应 GUI 三档）；备选 `axlRemoveSimulationResults` \| |
| maestro#083 | table-row | 127 | 6.2 write_history（历史原子） | \| rename \| history \| new_name \| `axlSetHistoryName(handle, new_name)` \| |
| maestro#084 | table-row | 128 | 6.2 write_history（历史原子） | \| lock / unlock \| history \| — \| `maeSetHistoryLock` / `axlSetHistoryLock` \| |
| maestro#086 | table-row | 136 | 7.1 open_gui / close_gui | \| 操作 \| 底层 \| |
| maestro#088 | table-row | 138 | 7.1 open_gui / close_gui | \| open_gui \| 窗口探测 → 关闭只读副本 → `deOpenCellView(..., "a")` → 找到并复用可编辑会话 \| |
| maestro#089 | table-row | 139 | 7.1 open_gui / close_gui | \| close_gui \| 探测窗口 mode/已修改 → Reading 先 `maeMakeEditable` → `maeSaveSetup` → `hiCloseWindow` → `dbPurge` 释放编辑锁；**固定保存，不提供丢弃** \| |
| maestro#090 | table-row | 143 | 7.2 run | \| 参数 \| 说明 \| |
| maestro#092 | table-row | 145 | 7.2 run | \| `blocking` \| 是否阻塞到仿真结束；**默认 `false`**（立即返回 history 名） \| |
| maestro#093 | table-row | 147 | 7.2 run | \| 模式 \| 行为 \| 底层 \| |
| maestro#095 | table-row | 149 | 7.2 run | \| 非阻塞（默认） \| 启动后立即返回 history 名，调用方之后用 `read_history` 查进度 \| `maeRunSimulation` \| |
| maestro#096 | table-row | 150 | 7.2 run | \| 阻塞（`blocking=true`） \| 启动后在包内等到终态，返回 history 名 + 终态 \| `maeRunSimulation` + 包内轮询 \| |
| maestro#102 | table-row | 164 | 8. 展示类 | \| 操作 \| 底层 \| |
| maestro#104 | table-row | 166 | 8. 展示类 | \| open_waveform_gui \| `maeOpenSetup(?mode "r")` → `maeOpenResults(?history)` → `awvCreatePlotWindow` → `awvPlotWaveform(?expr signals)`；会话保持打开供窗口引用 \| |
| maestro#105 | table-row | 167 | 8. 展示类 | \| close_waveform_gui \| `hiCloseWindow` + `maeCloseSession(?forceClose t)`，关闭后校验窗口与会话列表 \| |
| maestro#106 | table-row | 171 | 9. 内部中间节点（不对外） | \| 节点 \| 底层 \| 被谁使用 \| |
| maestro#108 | table-row | 173 | 9. 内部中间节点（不对外） | \| 后台会话 open / save / close \| `maeOpenSetup` / `maeSaveSetup` / `maeCloseSession` \| write、read_config、read_results、export、write_history \| |
| maestro#109 | table-row | 174 | 9. 内部中间节点（不对外） | \| 确保 maestro view 存在 \| `maeOpenSetup` + `maeSaveSetup` \| write、open_gui（对外不暴露） \| |
| maestro#110 | table-row | 175 | 9. 内部中间节点（不对外） | \| 窗口状态探测（mode / 已修改） \| `hiGetCurrentWindow` + 标题解析 + `davSession` \| close_gui \| |
| maestro#111 | table-row | 176 | 9. 内部中间节点（不对外） | \| Detail CSV 中间导出 \| `maeExportOutputView` \| read_results、export(outputs_csv) \| |
| maestro#113 | clause | 182 | 10. 待定与待验证 | 1. 会话级原子的索引（`set_run_mode` / `set_job_control_mode` 现按"当前会话"处理）； |
| maestro#115 | clause | 184 | 10. 待定与待验证 | 3. analyses / outputs 的枚举函数； |
| maestro#118 | clause | 187 | 10. 待定与待验证 | 6. 各原子的参数与默认值逐项定稿。 |
| maestro#119 | clause | 189 | 10. 待定与待验证 | 待真机验证（写 spec 定稿前必须闭环）： |

## 上层/7-spectre.md（103 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| spectre#017 | table-row | 27 | 2. 操作总表 | \| 类别 \| 操作名 \| 说明 \| 接口 \| |
| spectre#019 | table-row | 29 | 2. 操作总表 | \| 环境 \| `spectre.check_license` \| 查 Spectre 二进制/版本/license \| Sp+C \| |
| spectre#020 | table-row | 30 | 2. 操作总表 | \| 仿真 \| `spectre.run` \| 执行一个或多个独立仿真任务；`tasks[]` \| U+Sp+D \| |
| spectre#021 | table-row | 31 | 2. 操作总表 | \| 结果 \| `spectre.read_results` \| 读/解析 PSF ASCII；自动识别 single/raw/sweep \| D \| |
| spectre#022 | table-row | 32 | 2. 操作总表 | \| 结果 \| `spectre.measure` \| 在已解析数据上算 delay/bandwidth/noise 等 \| — \| |
| spectre#023 | table-row | 33 | 2. 操作总表 | \| 结果 \| `spectre.export` \| 已解析结果导出 CSV/JSON \| — \| |
| spectre#033 | clause | 54 | 3.1 Request / Result | - 每个 Request 必须有 `token: str`，可选 `timeout`；结构校验失败抛 `ValueError`/`TypeError`。 |
| spectre#036 | clause | 57 | 3.1 Request / Result | - 业务失败写 `ok=false` + `error`；只有结构错误或未预期异常才抛出。 |
| spectre#040 | clause | 64 | 3.2 路径与 job | - `run` 的 `job` 必须是安全名：`[A-Za-z0-9][A-Za-z0-9._-]*`，不得含 `/`、`\`、`..`。 |
| spectre#041 | clause | 65 | 3.2 路径与 job | - 包不生成 API 事后不可重建的随机路径；同一 `job` 必须能确定地定位同一组运行目录。 |
| spectre#055 | table-row | 99 | 5.1 Request | \| 字段 \| 类型 \| 默认 \| 说明 \| |
| spectre#057 | table-row | 101 | 5.1 Request | \| `token` \| str \| — \| 必填 \| |
| spectre#058 | table-row | 102 | 5.1 Request | \| `tasks` \| list[Task] \| — \| 一个或多个仿真任务；单仿真也写单元素列表 \| |
| spectre#059 | table-row | 103 | 5.1 Request | \| `max_workers` \| int \| 4 \| 上层并发上限，≥1 \| |
| spectre#060 | table-row | 104 | 5.1 Request | \| `mode` \| str \| `"spectre"` \| 批次默认 mode；task 可覆盖 \| |
| spectre#061 | table-row | 105 | 5.1 Request | \| `spectre_args` \| list[str] \| `[]` \| 批次默认额外 Spectre CLI flag \| |
| spectre#062 | table-row | 106 | 5.1 Request | \| `spectre_bin` \| str \\| None \| `None` \| 覆盖二进制/命令前缀；缺省用 query bin，再退化为 `spectre` \| |
| spectre#063 | table-row | 107 | 5.1 Request | \| `parse` \| str \| `"auto"` \| `auto`=下载后自动解析；`none`=只下载不解析 \| |
| spectre#064 | table-row | 108 | 5.1 Request | \| `download` \| bool \| `True` \| 是否把 raw/log 下载到调用方 \| |
| spectre#065 | table-row | 109 | 5.1 Request | \| `output_root` \| str \\| None \| `None` \| 调用方输出根；各 task 用 `<output_root>/<job>`；缺省 `artifact_dir("spectre", job)` \| |
| spectre#066 | table-row | 110 | 5.1 Request | \| `keep_run_dir` \| bool \| `False` \| 是否保留 role 侧 run_dir \| |
| spectre#067 | table-row | 111 | 5.1 Request | \| `timeout` \| int \\| None \| `None` \| 单次中层调用 deadline \| |
| spectre#069 | table-row | 115 | 5.1 Request | \| 字段 \| 类型 \| 默认 \| 说明 \| |
| spectre#071 | table-row | 117 | 5.1 Request | \| `job` \| str \| — \| 安全名；决定 role 侧与调用方侧运行目录；批次内唯一 \| |
| spectre#072 | table-row | 118 | 5.1 Request | \| `netlist` \| str \| — \| 调用方 netlist 文件；U 上传到 run_dir \| |
| spectre#073 | table-row | 119 | 5.1 Request | \| `include_files` \| list[str] \| `[]` \| 调用方 include 文件；按 basename 上传到 run_dir \| |
| spectre#074 | table-row | 120 | 5.1 Request | \| `mode` \| str \\| None \| `None` \| 为 None 时继承批次默认 \| |
| spectre#075 | table-row | 121 | 5.1 Request | \| `spectre_args` \| list[str] \\| None \| `None` \| 为 None 时继承批次默认；提供时覆盖 \| |
| spectre#077 | clause | 125 | 5.1 Request | - `tasks` 非空；job 唯一且为安全名；`max_workers ≥ 1`。 |
| spectre#078 | clause | 126 | 5.1 Request | - `parse="auto"` 时 `download` 必须为 true；`parse="none"` 时必须 `keep_run_dir=true`，否则后续无法再用 `read_results` 定位 role 侧结果。 |
| spectre#083 | clause | 135 | 5.2 执行链路（每个 task） | 3. 上传 netlist 为 `<run_dir>/<netlist basename>`；上传 include 文件到同一目录。netlist 与 include 的 basename 必须唯一、不得冲突。 |
| spectre#092 | clause | 146 | 5.2 执行链路（每个 task） | - 包内用受 `max_workers` 限制的并发执行所有 task；所有 task 都等待结束，任一失败不取消其余 task。 |
| spectre#093 | clause | 147 | 5.2 执行链路（每个 task） | - 结果按 `tasks` 顺序返回。 |
| spectre#094 | clause | 148 | 5.2 执行链路（每个 task） | - 中层的 token/channel/thread 预算仍可能拒绝某次调用；被拒绝的 task 记失败，不自动重试。 |
| spectre#097 | clause | 154 | 5.3 命令构造 | - 默认参数（已存在则不重复）：`-64`、`+escchars`、`+log <run_dir>/spectre.out`、`-format psfascii`、`-raw <run_dir>/<stem>.raw`、`+lqtimeout 900`、`-maxw 5`、`-maxn 5`、`+logstatus`。 |
| spectre#098 | clause | 155 | 5.3 命令构造 | - 参数顺序：task 的 `spectre_args` 后接 mode 映射参数。 |
| spectre#101 | table-row | 159 | 5.3 命令构造 | \| mode \| 参数 \| |
| spectre#103 | table-row | 161 | 5.3 命令构造 | \| `spectre` \| 无 \| |
| spectre#104 | table-row | 162 | 5.3 命令构造 | \| `aps` \| `+aps` \| |
| spectre#105 | table-row | 163 | 5.3 命令构造 | \| `x` \| `+x` \| |
| spectre#106 | table-row | 164 | 5.3 命令构造 | \| `cx` \| `+preset=cx +mt` \| |
| spectre#107 | table-row | 165 | 5.3 命令构造 | \| `ax` \| `+preset=ax +mt` \| |
| spectre#108 | table-row | 166 | 5.3 命令构造 | \| `mx` \| `+preset=mx +mt` \| |
| spectre#109 | table-row | 167 | 5.3 命令构造 | \| `lx` \| `+preset=lx +mt` \| |
| spectre#110 | table-row | 168 | 5.3 命令构造 | \| `vx` \| `+preset=vx +mt` \| |
| spectre#144 | clause | 207 | 5.4 结果与状态 | - raw 已下载但解析失败：`status="partial"`，`ok=false`，保留解析错误和已下载文件。 |
| spectre#146 | clause | 209 | 5.4 结果与状态 | - 终止失败标记至少包括：`error reading`、`read-in failed`、license error、明确 convergence failure、`spectre terminated prematurely due to fatal error`、`ERROR (`、segmentation/core dump。 |
| spectre#147 | table-row | 215 | 6.1 Request | \| 字段 \| 类型 \| 默认 \| 说明 \| |
| spectre#149 | table-row | 217 | 6.1 Request | \| `token` \| str \| — \| 必填 \| |
| spectre#150 | table-row | 218 | 6.1 Request | \| `source` \| str \| — \| role 文件或目录路径；相对 `file` role 根，绝对路径直通 \| |
| spectre#151 | table-row | 219 | 6.1 Request | \| `analysis` \| str \| `"all"` \| `raw` 时的分析选择：`all`/`tran`/`dc`/`ac`/`info` \| |
| spectre#152 | table-row | 220 | 6.1 Request | \| `output_dir` \| str \\| None \| `None` \| 调用方下载目录；缺省 `artifact_dir("spectre", "results", <source basename>)` \| |
| spectre#153 | table-row | 221 | 6.1 Request | \| `timeout` \| int \\| None \| `None` \| 单次中层调用 deadline \| |
| spectre#154 | table-row | 225 | 6.2 自动识别 | \| source \| 自动判定 \| 行为 \| |
| spectre#156 | table-row | 227 | 6.2 自动识别 | \| 单个 PSF ASCII 文件 \| `single` \| D 下载 → 解析 HEADER/TYPE/SWEEP/TRACE/VALUE \| |
| spectre#157 | table-row | 228 | 6.2 自动识别 | \| 目录，含合法 classic/flat sweep 布局 \| `sweep` \| D 递归下载 → 建点索引 \| |
| spectre#158 | table-row | 229 | 6.2 自动识别 | \| 其他目录 \| `raw` \| D 递归下载 → 按 `analysis` 合并 tran/dc/ac/info \| |
| spectre#189 | table-row | 272 | 7. `spectre.measure` | \| type \| 必填 \| 可选 \| 返回 \| |
| spectre#191 | table-row | 274 | 7. `spectre.measure` | \| `threshold_crossing` \| `signal, threshold` \| `direction=rise`, `edge=1`, `start`, `stop` \| time \| |
| spectre#192 | table-row | 275 | 7. `spectre.measure` | \| `delay` \| `from_signal, to_signal, threshold` \| `direction=rise`, `start`, `stop` \| Δtime \| |
| spectre#193 | table-row | 276 | 7. `spectre.measure` | \| `min`/`max`/`mean`/`rms` \| `signal` \| `start`, `stop` \| scalar \| |
| spectre#194 | table-row | 277 | 7. `spectre.measure` | \| `ac_magnitude` \| `signal, frequency` \| `scale=db/linear` \| magnitude \| |
| spectre#195 | table-row | 278 | 7. `spectre.measure` | \| `bandwidth` \| `signal` \| `drop_db=3`, `reference=dc/max` \| Hz \| |
| spectre#196 | table-row | 279 | 7. `spectre.measure` | \| `noise_integral` \| `signal` \| `start`, `stop` \| integral \| |
| spectre#197 | clause | 281 | 7. `spectre.measure` | - `noise_integral` 需要数据中含频率轴（默认 `freq`）；`ac_magnitude`/`bandwidth` 只适用于 AC 复数数据。 |
| spectre#202 | clause | 290 | 8. `spectre.export` | - CSV：按 columns（缺省取 data 中 list 值的顺序，`time`/`freq`/`sweep_var` 优先）写出矩形表；复数按 `<signal>.re`/`<signal>.im` 展开；缺失值留空。 |
| spectre#205 | table-row | 296 | 9. 内部中间节点（不对外） | \| 节点 \| 作用 \| |
| spectre#207 | table-row | 298 | 9. 内部中间节点（不对外） | \| run 目录/命令构造 \| job 校验、run_dir、upload、`-64/+escchars/+log/-raw/+logstatus`、mode 映射 \| |
| spectre#208 | table-row | 299 | 9. 内部中间节点（不对外） | \| 结果分类器 \| rc、fatal marker、收敛失败、license 失败、partial/failure/error \| |
| spectre#209 | table-row | 300 | 9. 内部中间节点（不对外） | \| PSF ASCII 解析 \| HEADER/TYPE/SWEEP/TRACE/VALUE/END；delta 压缩；AC 复数；STRUCT OP 展平 \| |
| spectre#210 | table-row | 301 | 9. 内部中间节点（不对外） | \| raw 目录分析发现 \| tran/dc/ac/info 文件候选与合并 \| |
| spectre#211 | table-row | 302 | 9. 内部中间节点（不对外） | \| sweep 布局归一化 \| classic `<raw>/sw*.sweep*/N/...` 与 X/LX flat `<raw>/sw*-NNN_*` \| |
| spectre#212 | table-row | 303 | 9. 内部中间节点（不对外） | \| CSV/JSON 写出 \| 矩形表、复数 re/im、列顺序、精度 \| |
| spectre#214 | clause | 307 | 9. 内部中间节点（不对外） | - swept 数据支持 delta 压缩：后续 step 缺省信号沿用前值；首个 step 未出现信号**内部**用缺失哨兵（实现取 `None`；**不得静默填 0**）， |
| spectre#215 | clause | 308 | 9. 内部中间节点（不对外） | **对外 `value.data` 一律转成 `null`/省略**（保持 JSON-safe）。边界唯一出口是 `psf_external()`： |
| spectre#216 | clause | 309 | 9. 内部中间节点（不对外） | 缺失哨兵与任何非有限值（`NaN`/`±Inf`）都在那里收敛成 `null`，其余路径不得自行定义对外表示。 |
| spectre#217 | clause | 310 | 9. 内部中间节点（不对外） | - AC 复数相量不得被破坏；对外 `value.data` 必须 JSON-safe：复数向量用 `{"re": [...], "im": [...]}`，单值用 `{"re": ..., "im": ...}`。 |
| spectre#221 | table-row | 317 | 10. 旧功能覆盖映射 | \| 旧实现 \| 新操作/说明 \| |
| spectre#223 | table-row | 319 | 10. 旧功能覆盖映射 | \| `SpectreSimulator.run_simulation` \| `run(tasks=[<一个 task>])`；等价单仿真 \| |
| spectre#224 | table-row | 320 | 10. 旧功能覆盖映射 | \| `SpectreSimulator.run_parallel` \| `run(tasks=[...], max_workers=N)` \| |
| spectre#225 | table-row | 321 | 10. 旧功能覆盖映射 | \| `parallel_pool` 增量 Future \| 不在本版；分多次 `run` 实现 \| |
| spectre#226 | table-row | 322 | 10. 旧功能覆盖映射 | \| `SpectreSimulator.check_license` \| `check_license` \| |
| spectre#227 | table-row | 323 | 10. 旧功能覆盖映射 | \| `parse_spectre_psf_ascii` \| `read_results(source=<单个 PSF 文件>)` \| |
| spectre#228 | table-row | 324 | 10. 旧功能覆盖映射 | \| `parse_psf_ascii_directory` \| `read_results(source=<raw 目录>)` \| |
| spectre#229 | table-row | 325 | 10. 旧功能覆盖映射 | \| `parse_sweep_psf_directory` \| `read_results(source=<sweep 目录>)`（自动识别 sweep） \| |
| spectre#230 | table-row | 326 | 10. 旧功能覆盖映射 | \| `psf.py` 的 scalar/vector/frequency_hz \| 内部解析/度量工具，不单独暴露业务操作 \| |
| spectre#231 | table-row | 327 | 10. 旧功能覆盖映射 | \| examples 传播延迟计算 \| `measure(metrics=[{type:"delay",...}])` \| |
| spectre#232 | table-row | 328 | 10. 旧功能覆盖映射 | \| examples `_result_io.py` \| `export(format="csv")` / `export(format="json")` \| |
| spectre#233 | table-row | 329 | 10. 旧功能覆盖映射 | \| `spectre_mode_args` \| `run.mode` 映射表 \| |
| spectre#234 | table-row | 330 | 10. 旧功能覆盖映射 | \| `include_files` / `spectre_args` \| `run.tasks[].include_files` / `run.spectre_args` \| |
| spectre#235 | table-row | 331 | 10. 旧功能覆盖映射 | \| `output_format="psfascii"` \| 固定 `psfascii` \| |
| spectre#236 | table-row | 332 | 10. 旧功能覆盖映射 | \| `work_dir` \| `run.output_root` \| |
| spectre#237 | table-row | 333 | 10. 旧功能覆盖映射 | \| `keep_remote_files` \| `run.keep_run_dir` \| |
| spectre#238 | table-row | 334 | 10. 旧功能覆盖映射 | \| `SpectreSimulator.from_env` / `local` / `profile` \| 不在包内；由 token 路由 + `query` 决定 target role \| |
| spectre#252 | table-row | 357 | 13. 决策记录（2026-09-21） | \| # \| 决策 \| |
| spectre#254 | table-row | 359 | 13. 决策记录（2026-09-21） | \| 1 \| 按 schematic/maestro 的领域操作组织：对外收敛为 `check_license`/`run`/`read_results`/`measure`/`export` 五个操作。 \| |
| spectre#255 | table-row | 360 | 13. 决策记录（2026-09-21） | \| 2 \| `run` 用 `tasks[]` 统一单仿真与固定批次；不单独暴露 `run_batch`。 \| |
| spectre#256 | table-row | 361 | 13. 决策记录（2026-09-21） | \| 3 \| `read_results` 自动识别单文件、raw 目录、参数扫描；请求层不暴露 `kind`，只在响应中回写识别结果。 \| |
| spectre#257 | table-row | 362 | 13. 决策记录（2026-09-21） | \| 4 \| `measure` 与 `export` 分别纯 Python 计算/落盘，不接触 PSF 解析内部。 \| |
| spectre#258 | table-row | 363 | 13. 决策记录（2026-09-21） | \| 5 \| 不引入本地/远程模式分支；全部操作只依赖 token + 五业务接口 + `query`；多 server/profile 用不同 token。 \| |
| spectre#259 | table-row | 364 | 13. 决策记录（2026-09-21） | \| 6 \| `run` 的文件布局统一建在 `spectre.root` 下；U/D 用绝对路径跨 role 访问，要求该 root 在 file role 与 spectre 主机均可见。 \| |
| spectre#260 | table-row | 365 | 13. 决策记录（2026-09-21） | \| 7 \| 只支持 PSF ASCII；复数在对外 `value.data` 统一为 `{re, im}` JSON-safe 表示。 \| |
| spectre#261 | table-row | 366 | 13. 决策记录（2026-09-21） | \| 8 \| 不提供 `-param` 注入；参数化由调用方生成多个 netlist。 \| |

## 上层/8-verilog.md（58 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| verilog#009 | table-row | 15 | 1. 业务操作 | \| 类别 \| 操作名 \| 一句话说明 \| 接口 \| |
| verilog#011 | table-row | 17 | 1. 业务操作 | \| 读 \| `virtuoso.verilog.read` \| 读源码文本 / 视图清单 / 导入诊断（`focus` 可选） \| S+D \| |
| verilog#012 | table-row | 18 | 1. 业务操作 | \| 写 \| `virtuoso.verilog.write` \| 通用写：对文本视图做原子文本编辑（只落盘） \| S+U \| |
| verilog#013 | table-row | 19 | 1. 业务操作 | \| 导入 \| `virtuoso.verilog.import` \| 结构 Verilog → functional/symbol（默认），可选 schematic（`ihdl`） \| S+C+U \| |
| verilog#014 | table-row | 20 | 1. 业务操作 | \| 导出 \| `virtuoso.verilog.export` \| `oa2verilog`：schematic → Verilog-2001 网表 \| C+D \| |
| verilog#016 | table-row | 24 | 1. 业务操作 | \| 载体 \| 说明 \| |
| verilog#018 | table-row | 26 | 1. 业务操作 | \| 文本视图 `text.v` \| 主文件 `verilog.v`，与 `text.veriloga` 同属文件式文本视图，可直接写/读 \| |
| verilog#019 | table-row | 27 | 1. 业务操作 | \| 导入生成的视图 \| `functional`（`verilog.v` 文本 + `netlist.oa`，默认）、`symbol`、`schematic`（可选） \| |
| verilog#025 | table-row | 38 | 1.1 读操作（read） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| verilog#027 | table-row | 40 | 1.1 读操作（read） | \| read \| `focus` 可选、可组合；不填=全部 \| 定位源码路径 → 读文本/视图/诊断 \| S+D \| |
| verilog#033 | table-row | 48 | 1.1 读操作（read） | \| focus \| 返回 \| |
| verilog#035 | table-row | 50 | 1.1 读操作（read） | \| `source` \| `text / path / size / sha256 / lines` \| |
| verilog#036 | table-row | 51 | 1.1 读操作（read） | \| `views` \| 该 cell 的视图清单：`name / viewType / dataType / 文件`（用 `ddMapGetFileViewType`/`ddMapGetFileDataType` 判定） \| |
| verilog#037 | table-row | 52 | 1.1 读操作（read） | \| `diagnostics` \| 最近一次 `import` 的 `log_path / status / error_count / errors[]` \| |
| verilog#040 | table-row | 59 | 1.2 写操作（write） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| verilog#042 | table-row | 61 | 1.2 写操作（write） | \| write \| 通用写：`lib/cell/view + commands[]` \| 读现状 → 逐原子改文本 → 覆盖写 \| S+U \| |
| verilog#043 | clause | 63 | 1.2 写操作（write） | `write.commands` 每项 = `{"op": 原子名, ...参数}`；**非事务**，失败响应带 `commands applied: k/n`。 |
| verilog#044 | table-row | 65 | 1.2 写操作（write） | \| 对象 \| 原子名 \| 索引（动哪个） \| 附加参数 \| |
| verilog#046 | table-row | 67 | 1.2 写操作（write） | \| 代码 \| `set_source` \| 目标 view 或 file \| `text`；可选 `expected_sha256`（不符则失败） \| |
| verilog#047 | table-row | 68 | 1.2 写操作（write） | \| 代码 \| `patch_source` \| 目标 view 或 file \| `edits[]`：`{old_text,new_text}` 或 `{start_line,end_line,new_text}`；匹配不唯一默认失败（可 `all=true`） \| |
| verilog#048 | table-row | 69 | 1.2 写操作（write） | \| 文本视图 \| `ensure_view` \| `{library, cell, view}` \| `view_type`（`text.v`）、可选 `create_if_missing=true`；内部写 `master.tag` + 主文件模板 \| |
| verilog#049 | table-row | 70 | 1.2 写操作（write） | \| 文本视图 \| `delete_view` \| `{library, cell, view}` \| —（`ddDeleteObj`，先确认无编辑器窗口/`*.cdslck`） \| |
| verilog#051 | clause | 73 | 1.2 写操作（write） | 结构校验走 `import`（见 §1.3）。有 `*.cdslck`（编辑器开着）时禁止外部写。 |
| verilog#052 | table-row | 77 | 1.3 导入（import） | \| 参数 \| 说明 \| |
| verilog#054 | table-row | 79 | 1.3 导入（import） | \| `file_path` + `file_is_local` \| 源码文件（本机→上传；远端→直接用） \| |
| verilog#055 | table-row | 80 | 1.3 导入（import） | \| `library` / `cell` \| 目标库与顶层 cell（**显式给**，不用文件名推导） \| |
| verilog#056 | table-row | 81 | 1.3 导入（import） | \| `schematic_view` / `functional_view` / `symbol_view` \| 产出视图名（默认 schematic/functional/symbol） \| |
| verilog#057 | table-row | 82 | 1.3 导入（import） | \| `overwrite` \| 映射 `import_if_exists` / `overwrite_symbol` \| |
| verilog#058 | table-row | 83 | 1.3 导入（import） | \| `timeout` / `poll_interval` \| 轮询预算 \| |
| verilog#060 | clause | 86 | 1.3 导入（import） | （ihdl 会往里追加 `DEFINE`，不能给共享/全局那份）； |
| verilog#062 | clause | 88 | 1.3 导入（import） | `structural_views`（1=schematic / 2=netlist / 4=functional / 5=schematic+functional / 6=netlist+functional，**默认 4**）、 |
| verilog#065 | clause | 91 | 1.3 导入（import） | 3. 执行（**必须带 LD_LIBRARY_PATH 前缀**，否则缺 `libsasl2.so.2`、rc=127）： |
| verilog#071 | clause | 97 | 1.3 导入（import） | 6. **返回码不可信**（语法错误也 rc=0）：只用日志 + 产物判成败。 |
| verilog#072 | clause | 99 | 1.3 导入（import） | `functional` 视图 = `verilog.v` 文本 + `netlist.oa`，是 AMS/仿真网表要消费的形态，默认就够； |
| verilog#074 | table-row | 104 | 1.4 导出（export） | \| 参数 \| 说明 \| |
| verilog#076 | table-row | 106 | 1.4 导出（export） | \| `library / cell / view` \| 要导出的 OA 视图（默认 `schematic`） \| |
| verilog#077 | table-row | 107 | 1.4 导出（export） | \| `output_path` \| 本机目标 `.v` 路径 \| |
| verilog#078 | table-row | 108 | 1.4 导出（export） | \| `recursive` \| 是否连层级一起导出（`-recursive`） \| |
| verilog#079 | table-row | 109 | 1.4 导出（export） | \| `timeout` \| 单次命令 deadline \| |
| verilog#086 | table-row | 122 | 2. 归属（不在本包） | \| 能力 \| 归属 \| |
| verilog#088 | table-row | 124 | 2. 归属（不在本包） | \| view CRUD（OA 视图，如 schematic/symbol） \| cellview \| |
| verilog#089 | table-row | 125 | 2. 归属（不在本包） | \| 文本视图（`text.v`）的建立与覆盖 \| **本包例外**（cellview 建不了文本视图） \| |
| verilog#090 | table-row | 126 | 2. 归属（不在本包） | \| VerilogA（`text.veriloga`） \| veriloga 包 \| |
| verilog#091 | table-row | 127 | 2. 归属（不在本包） | \| GDS 导入/导出 \| layout（`layout.gds`） \| |
| verilog#092 | table-row | 128 | 2. 归属（不在本包） | \| 结构 connectivity / 端口 / 参数读回 \| schematic（`schematic.read`） \| |
| verilog#093 | table-row | 129 | 2. 归属（不在本包） | \| 仿真编译 \| spectre 包 \| |
| verilog#097 | clause | 136 | 3. 不在本版 | - 并发写同一 cell。 |
| verilog#099 | clause | 141 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 2. `ihdl` 是 ksh 包装器：裸跑缺 `libsasl2.so.2`（rc=127），必须带 |
| verilog#101 | clause | 143 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 3. `ihdl` **返回码不可信**：语法错误、参考库缺失、降级导入都是 rc=0；成功看 `357/372/345`， |
| verilog#103 | clause | 145 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 4. `ihdl` 会向 `-cdslib` 指定的文件**追加 DEFINE**（目标库未注册时还在 cwd 建同名库目录）→ 必须用按次副本； |
| verilog#108 | clause | 150 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 否则 `VERILOGIN-127` 拒绝并降级 functional； |
| verilog#111 | table-row | 156 | 5. 决策记录（2026-09-21，已确认） | \| # \| 决策 \| |
| verilog#113 | table-row | 158 | 5. 决策记录（2026-09-21，已确认） | \| 1 \| 包名 `verilog` / `8-verilog.md`，operation 前缀 `virtuoso.verilog.*` \| |
| verilog#114 | table-row | 159 | 5. 决策记录（2026-09-21，已确认） | \| 2 \| VerilogA 拆出为独立包 `veriloga`（`11-veriloga.md`），本包只管结构 Verilog \| |
| verilog#115 | table-row | 160 | 5. 决策记录（2026-09-21，已确认） | \| 3 \| 结构装码 = `import`（ihdl）；`structural_views` 默认 `4`（functional only），schematic 显式可选 \| |
| verilog#116 | table-row | 161 | 5. 决策记录（2026-09-21，已确认） | \| 4 \| 文本视图装码 = `write`（只落盘）；不提供 `check_and_save`（Virtuoso 无 Verilog 解析器） \| |
| verilog#117 | table-row | 162 | 5. 决策记录（2026-09-21，已确认） | \| 5 \| `export` 对 `ipin/opin` 噪声行原样导出 + warning，不静默改写 \| |
| verilog#118 | table-row | 163 | 5. 决策记录（2026-09-21，已确认） | \| 6 \| 不提供 open/close 等 GUI 展示操作 \| |

## 上层/9-skillref.md（122 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| skillref#007 | table-row | 13 | 1. 总述 | \| 操作 \| 对应交互 \| |
| skillref#009 | table-row | 15 | 1. 总述 | \| `virtuoso.skillref.search` \| 搜索框：一个 `query` 输入 + 一组选项（搜到哪一层、怎么匹配、搜多大范围） \| |
| skillref#010 | table-row | 16 | 1. 总述 | \| `virtuoso.skillref.info` \| 结果行点进去：按函数名取该函数的详细文档 \| |
| skillref#017 | clause | 26 | 1. 总述 | 3. **本地/远端同义**：同一操作在两种模式下语义一致，差别只在取数方式（见 §3）； |
| skillref#019 | table-row | 33 | 2.1 读操作总表 | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| skillref#021 | table-row | 35 | 2.1 读操作总表 | \| `virtuoso.skillref.search` \| 统一搜索：按 `search_in` 在名称/词条/主题/正文中查 \| 定位 doc root → 按范围取数 → 匹配 → 打分排序 \| C+D（远端模式） \| |
| skillref#022 | table-row | 36 | 2.1 读操作总表 | \| `virtuoso.skillref.info` \| 单函数详细文档 \| 取 `.tgf` → 查表 → 取 1 个 HTML → 抽取 → Markdown \| C+D（远端模式） \| |
| skillref#028 | table-row | 50 | 3. 数据源与运行模式 | \| 层 \| 文件 \| 内容 \| 实测规模（IC618） \| |
| skillref#030 | table-row | 52 | 3. 数据源与运行模式 | \| 词条层 \| `<doc_root>/finder/SKILL/**.fnd` \| 函数名 + 语法 + 一行描述 \| 37 文件 / 2 286 097 B → 9503 条 \| |
| skillref#031 | table-row | 53 | 3. 数据源与运行模式 | \| 主题层 \| `<doc_root>/api_more_info/api_more_info.tgf` \| 函数名 → HTML 文件 + topic \| 9730 行 / 3987 个目标文件 / 924 044 B \| |
| skillref#032 | table-row | 54 | 3. 数据源与运行模式 | \| 正文层 \| `<doc_root>/**.html/.htm/.txt/.xml/.json` \| 参考手册正文与辅助文本 \| **可搜索子集 223.8 MB / 9 426 文件**（`.html` 8 597 / 209.6 MB 为主；整树 6.5 GB 的其余部分是 mp4/gif/pdf/png 与 Cadence 自带 `.cfs` 索引，不参与检索） \| |
| skillref#034 | clause | 59 | 3.1 数据源：显式配置，不探测 | 取值顺序（先到先用，结果原样回带 `source` 与 `doc_root`，便于调用方复用与排错）： |
| skillref#046 | table-row | 76 | 3.1 数据源：显式配置，不探测 | \| 字段 \| 规则 \| |
| skillref#048 | table-row | 78 | 3.1 数据源：显式配置，不探测 | \| `source` \| 必须是 `local` 或 `remote`（大小写不敏感） \| |
| skillref#049 | table-row | 79 | 3.1 数据源：显式配置，不探测 | \| `doc_root` \| 非空绝对路径字符串、不含 NUL；`local` 模式要求在本进程可见，`remote` 模式是业务服务器上的绝对路径 \| |
| skillref#050 | table-row | 80 | 3.1 数据源：显式配置，不探测 | \| `doc_token` \| 只来自配置、请求参数不可覆盖；`remote` 模式必填，必须对应一个已注册 user（控制面 PUT 时校验），`local` 模式忽略 \| |
| skillref#051 | clause | 82 | 3.1 数据源：显式配置，不探测 | **只有这三个字段**——`source` + `doc_root` 是数据源位置，`doc_token` 是远端执行代理账号（必须注册一个 user，用该 user 的远端执行）。 |
| skillref#055 | clause | 89 | 3.2 local 模式（`source="local" | （错误文案带该路径），不退回远端、也不猜别的路径。 |
| skillref#057 | table-row | 95 | 3.3 remote 模式（`source="remot | \| 层 \| 取数方式 \| 体积（实测） \| |
| skillref#059 | table-row | 97 | 3.3 remote 模式（`source="remot | \| 词条层 \| 一次 `download_file(<doc_root>/finder/SKILL, <temp_dir()/skillref/…>, recursive=True)`（落点由包内部决定，§3.4） \| 2.4 MB（tar.gz 压缩后更小） \| |
| skillref#060 | table-row | 98 | 3.3 remote 模式（`source="remot | \| 主题层 \| 一次 `download_file(<doc_root>/api_more_info/api_more_info.tgf, ...)`；命中后只再取 1 个 HTML \| 924 KB + 单文件 \| |
| skillref#061 | table-row | 99 | 3.3 remote 模式（`source="remot | \| 正文层 \| 一次 `command.run` 跑远端候选搜索（`grep -r -l -m1`，形状见 `src_bak/virtuoso_bridge/virtuoso/docs_search.py:417-459`）→ `download_file` 取候选（≤ `max_candidates`）→ 本地打分与摘要 \| 搜索本身 0 传输（整树 0.10–0.15 s）；候选 ≈190–240 KB/个、≈1.9 s/个  |
| skillref#062 | clause | 101 | 3.3 remote 模式（`source="remot | 路径纪律：远端路径一律按 POSIX 语义拼接，**禁止**对远端路径调用 `Path.exists()`。 |
| skillref#064 | clause | 104 | 3.3 remote 模式（`source="remot | 业务失败必须指明"`skillref.doc_token` 无效或已删除"，不得只报 `command failed`。 |
| skillref#069 | clause | 115 | 4. `virtuoso.skillref.search | 唯一搜索入口。一次请求 = 一个 `query` + 一组选项，选项只影响"搜到哪一层"与"怎么匹配"。 |
| skillref#082 | table-row | 132 | 4.1 输入 | \| 参数 \| 必填 \| 默认 \| 说明 \| |
| skillref#084 | table-row | 134 | 4.1 输入 | \| `query` \| 是 \| — \| 唯一输入框；多词按 AND 处理（沿用旧 `_query_terms` 口径） \| |
| skillref#085 | table-row | 135 | 4.1 输入 | \| `source` \| 否 \| 配置表值 \| `local` / `remote`；与 `doc_root` 一起确定数据源（见 §3.1） \| |
| skillref#086 | table-row | 136 | 4.1 输入 | \| `search_in` \| 否 \| `entry` \| 匹配范围，逐级加深：`name` / `entry` / `topic` / `body`；`all` 是 `body` 的别名（见 §4.2） \| |
| skillref#087 | table-row | 137 | 4.1 输入 | \| `mode` \| 否 \| `fuzzy` \| 名称/标题列的匹配方式：`fuzzy` / `prefix` / `suffix` / `exact` / `regex`（见 §4.3） \| |
| skillref#088 | table-row | 138 | 4.1 输入 | \| `under` \| 否 \| — \| doc root 下的相对子目录列表（如 `["cpf_ref"]`），限定正文层扫描范围 \| |
| skillref#089 | table-row | 139 | 4.1 输入 | \| `limit` \| 否 \| 20 \| 结果条数上限（1–200） \| |
| skillref#090 | table-row | 140 | 4.1 输入 | \| `max_candidates` \| 否 \| 50 \| 正文层候选上限（远端模式下同时限制下载文件数） \| |
| skillref#091 | table-row | 141 | 4.1 输入 | \| `max_files` \| 否 \| 5000 \| 正文层未给 `under` 时的扫描文件上限，超出回 `truncated=true` \| |
| skillref#092 | table-row | 142 | 4.1 输入 | \| `snippet` \| 否 \| `true` \| 是否回带命中片段 \| |
| skillref#093 | table-row | 143 | 4.1 输入 | \| `doc_root` \| 否 \| 配置表值 \| 绝对路径；校验规则见 §3.1 \| |
| skillref#094 | table-row | 144 | 4.1 输入 | \| `doc_token` \| **不可由请求给出** \| 配置表值 \| remote 模式的执行代理账号；只来自配置，请求参数不可覆盖（防提权，见 §3.1） \| |
| skillref#095 | table-row | 145 | 4.1 输入 | \| `timeout` \| 否 \| — \| 单次 C/D 调用的超时（正文层远端候选搜索默认 120 s） \| |
| skillref#096 | table-row | 149 | 4.2 匹配范围 `search_in`（逐级加深） | \| 取值 \| 搜什么 \| 命中形态 \| 成本（IC618 实测） \| |
| skillref#098 | table-row | 151 | 4.2 匹配范围 `search_in`（逐级加深） | \| `name` \| `.fnd` 函数名 \| `{name, syntax}` \| 与 `entry` 同（同一份索引解析） \| |
| skillref#099 | table-row | 152 | 4.2 匹配范围 `search_in`（逐级加深） | \| `entry` \| 函数名 + 语法 + 一行描述 \| `{name, syntax, description}` \| 词条层取数 2.4 MB / 1.16 s（远端） \| |
| skillref#100 | table-row | 153 | 4.2 匹配范围 `search_in`（逐级加深） | \| `topic` \| `entry` + `.tgf` 主题名与目标文件名 \| `{topic, target_path, anchor}` \| 追加 tgf 924 KB \| |
| skillref#101 | table-row | 154 | 4.2 匹配范围 `search_in`（逐级加深） | \| `body` \| `topic` + 正文文件标题/相对路径/内容 \| `{title, relative_path, line, snippet}` \| 远端 `grep` 整树 0.10–0.15 s + 逐候选下载 ≈1.9 s/文件；本地纯 Python 全扫 189 s（须给 `under`） \| |
| skillref#102 | clause | 156 | 4.2 匹配范围 `search_in`（逐级加深） | `name` 与 `entry` 的区别只在**是否把语法/描述并入匹配面**，两者共用同一份 `.fnd` 解析。 |
| skillref#103 | clause | 157 | 4.2 匹配范围 `search_in`（逐级加深） | `all` = `body`（最深一档，给"我什么都想搜"的用户一个不用记顺序的取值）。 |
| skillref#107 | clause | 165 | 4.3 `mode` 语义 | （语法、描述、正文）一律按**大小写不敏感的子串 AND** 匹配，不受 `mode` 影响： |
| skillref#108 | table-row | 167 | 4.3 `mode` 语义 | \| mode \| 名称列语义 \| |
| skillref#110 | table-row | 169 | 4.3 `mode` 语义 | \| `fuzzy`（默认） \| 大小写不敏感子串 \| |
| skillref#111 | table-row | 170 | 4.3 `mode` 语义 | \| `prefix` \| 前缀（大小写敏感） \| |
| skillref#112 | table-row | 171 | 4.3 `mode` 语义 | \| `suffix` \| 后缀（大小写敏感） \| |
| skillref#113 | table-row | 172 | 4.3 `mode` 语义 | \| `exact` \| 全等（大小写敏感） \| |
| skillref#114 | table-row | 173 | 4.3 `mode` 语义 | \| `regex` \| Python 正则（`re.IGNORECASE`；非法正则回空结果） \| |
| skillref#116 | table-row | 179 | 4.4 打分与排序 | \| 层 \| 加分项 \| |
| skillref#118 | table-row | 181 | 4.4 打分与排序 | \| 名称 \| 全等 100 / 前缀 80 / 子串 60 \| |
| skillref#119 | table-row | 182 | 4.4 打分与排序 | \| 词条 \| 语法命中 +20 / 描述命中 +10 \| |
| skillref#120 | table-row | 183 | 4.4 打分与排序 | \| 主题 \| topic 全等 90 / 子串 70；目标文件名命中 +10 \| |
| skillref#121 | table-row | 184 | 4.4 打分与排序 | \| 正文 \| 标题命中 40 / 相对路径命中 30 / 正文命中 20；每个额外查询词 +5 \| |
| skillref#129 | clause | 197 | 4.5 返回 | 未命中返回空 `results` 且 `ok=true`（"查不到"是正常业务结果，不是错误）。 |
| skillref#136 | clause | 207 | 4.6 上限与边界 | 因此 `search_in="body"` 在 **local 模式必须给 `under`**（如 `["cpf_ref"]`， |
| skillref#140 | clause | 211 | 4.6 上限与边界 | 在本地打分与出摘要；`max_candidates` 同时是下载上限； |
| skillref#141 | clause | 212 | 4.6 上限与边界 | 4. `timeout` 显式传给每次 C/D 调用；正文层远端候选搜索默认给 120 s，调用方可覆盖。 |
| skillref#144 | table-row | 219 | 5. `virtuoso.skillref.info` | \| 参数 \| 必填 \| 默认 \| 说明 \| |
| skillref#146 | table-row | 221 | 5. `virtuoso.skillref.info` | \| `name` \| 是 \| — \| 函数名；自动尝试 `_ocean` / `_viva_skill` 后缀回退 \| |
| skillref#147 | table-row | 222 | 5. `virtuoso.skillref.info` | \| `include_raw` \| 否 \| `false` \| 是否回带 `raw_html`（默认只回 Markdown） \| |
| skillref#148 | table-row | 223 | 5. `virtuoso.skillref.info` | \| `source` / `doc_root` / `timeout` \| 否 \| — \| 见 §3 \| |
| skillref#153 | clause | 230 | 5. `virtuoso.skillref.info` | 3. 抽取顺序（不可调换，旧实现 `skill_finder/more_info.py:157`）： |
| skillref#166 | clause | 250 | 6.1 配置表：`config.json` 的 `ski | * 本段缺失或 `null` = 未配置，不阻断进程启动，只在调用时返回可读的业务失败。 |
| skillref#167 | clause | 252 | 6.1 配置表：`config.json` 的 `ski | 实现口径（本包）：读取顺序 = 请求参数 `source`+`doc_root` → `common.config` 快照的 |
| skillref#173 | clause | 261 | 6.2 单一搜索入口 | 一个入口，`search_in` 是唯一控制匹配深度的参数。旧 `skill-find` CLI 的语义对应 |
| skillref#180 | clause | 274 | 6.4 与 `tools/skill_doc_serve | 两者共享同一套解析口径（`.fnd` / `.tgf` / HTML→Markdown），实现以本包为唯一维护点。 |
| skillref#182 | table-row | 280 | 6.5 决策记录：本版为什么不建索引 | \| 项 \| 实测 \| |
| skillref#184 | table-row | 282 | 6.5 决策记录：本版为什么不建索引 | \| 首次建索引 + 查一次（223.8 MB 文本 / 71 319 文件） \| 187.66 s \| |
| skillref#185 | table-row | 283 | 6.5 决策记录：本版为什么不建索引 | \| 索引体积 `index.sqlite` \| 159.5 MB \| |
| skillref#186 | table-row | 284 | 6.5 决策记录：本版为什么不建索引 | \| 第二次查询（复用索引） \| 0.21 s \| |
| skillref#187 | table-row | 285 | 6.5 决策记录：本版为什么不建索引 | \| 对照：不建索引（本地直扫 / 远端 `grep`） \| 189 s / **0.10–0.15 s** \| |
| skillref#194 | clause | 293 | 6.5 决策记录：本版为什么不建索引 | → 文档升级后索引静默过期。若将来要建，必须补"文档树指纹"（文件数 + 最新 mtime）， |
| skillref#199 | table-row | 303 | 6.6 待裁决：`doc_token` 与"token  | \| 方案 \| 动作 \| 后果 \| |
| skillref#201 | table-row | 305 | 6.6 待裁决：`doc_token` 与"token  | \| **A. 保留 `doc_token`**（当前实现） \| `1-上层.md §3.1` 加回一行例外（"配置预置的查询账户"） \| 跨机器读文档：调用者 token 只做身份校验，数据源与执行账号由配置决定 \| |
| skillref#202 | table-row | 306 | 6.6 待裁决：`doc_token` 与"token  | \| B. 撤销 `doc_token` \| 本文 §3.1 删除 `doc_token`，remote 的 C/D 改用请求 token \| 远端文档树必须对调用者 token 所在的 role 可见，否则查不了；配置段只剩 `source`+`doc_root` \| |
| skillref#206 | clause | 314 | 7. 已知限制 | 2. 正文层无持久索引：本地模式全树扫描 ~190 s（必须给 `under`）；远端模式靠 `grep` 候选 |
| skillref#211 | clause | 319 | 7. 已知限制 | 6. 正文层远端的 `line` 只在本地算（候选下载后重扫），远端候选本身只保证文件级定位。 |
| skillref#212 | clause | 320 | 7. 已知限制 | 7. **不做路径探测**：`source` 与 `doc_root` 必须由配置表或请求给出；配错只会得到 |
| skillref#218 | table-row | 330 | 8. 验收 | \| 组 \| 用例 \| |
| skillref#220 | table-row | 332 | 8. 验收 | \| search 范围 \| `search_in` 四档各 1（`name` / `entry` / `topic` / `body`），断言层次与命中面一致 \| |
| skillref#221 | table-row | 333 | 8. 验收 | \| search 模式 \| 五种 `mode` 各 1 + `limit` 截断 + 未知查询回空 \| |
| skillref#222 | table-row | 334 | 8. 验收 | \| search 正文层 \| `under=["cpf_ref"]` 命中 `ground bounce`（0.7 s 级）；缺 `under` 时 `truncated` 边界 \| |
| skillref#223 | table-row | 335 | 8. 验收 | \| info \| 现代标记命中（`dbOpenCellViewByType`）、legacy 命中、`NULL` topic 兜底、`_ocean` 回退（`ocnPrint`）、未知函数 `found=false` \| |
| skillref#224 | table-row | 336 | 8. 验收 | \| 数据源 \| 请求参数给定（`local` / `remote` 各 1）、配置表给定（1）、未配置 → 明确失败（1） \| |
| skillref#225 | table-row | 337 | 8. 验收 | \| 失败 \| local 路径不存在、remote 路径不可见、`source` 非法值、正文层超 `max_files` \| |
| skillref#227 | table-row | 341 | 8. 验收 | \| 文件 \| 内容 \| |
| skillref#229 | table-row | 343 | 8. 验收 | \| `src/pyapi/packages/skillref.py` \| 两个业务操作 + 数据源解析 + 本地/远端取数 \| |
| skillref#230 | table-row | 344 | 8. 验收 | \| `src/pyapi/packages/_skillref_docs.py` \| stdlib-only 解析层（`.fnd` / `.tgf` / HTML→Markdown / 正文打分） \| |
| skillref#231 | table-row | 345 | 8. 验收 | \| `test/offline/unit/test_skillref_package.py` \| 27 项单元测试（四层匹配、两种模式、配置快照、错误口径） \| |
| skillref#232 | table-row | 346 | 8. 验收 | \| `test/semi/probes/skillref_probe.py` \| 真机探针（`--from-config` 走 config.json 快照） \| |
| skillref#234 | table-row | 350 | 8. 验收 | \| 调用 \| 本地（`C:\Users\user\Desktop\doc`） \| 远端（`/opt/eda/cadence/IC618/doc`，doc_token=vb-vblog） \| |
| skillref#236 | table-row | 352 | 8. 验收 | \| `search_in=name` \| 0.27 s \| 3.50 s（首个调用含通道预热） \| |
| skillref#237 | table-row | 353 | 8. 验收 | \| `search_in=entry` \| 0.27 s \| 1.80 s \| |
| skillref#238 | table-row | 354 | 8. 验收 | \| `search_in=topic` \| 0.28 s \| 4.21 s \| |
| skillref#239 | table-row | 355 | 8. 验收 | \| `search_in=body`（`under=["cpf_ref"]`） \| 0.91 s（扫 16 文件，1 命中） \| 7.65 s（grep 候选 1 个 + 下载，1 命中） \| |
| skillref#240 | table-row | 356 | 8. 验收 | \| `info(dbOpenCellViewByType)` \| 命中，Markdown 5 719 字符 \| 4.56 s，同 5 719 字符 \| |
| skillref#241 | table-row | 357 | 8. 验收 | \| `info(不存在)` \| `found=false`（ok=true） \| 2.67 s，`found=false` \| |
| skillref#243 | table-row | 361 | 8. 验收 | \| 项 \| 值 \| |
| skillref#245 | table-row | 363 | 8. 验收 | \| `.fnd` \| 37 文件 / 2 286 097 B → **9503 条** \| |
| skillref#246 | table-row | 364 | 8. 验收 | \| `.tgf` \| 924 044 B / 9730 行 / 3987 个目标文件 \| |
| skillref#247 | table-row | 365 | 8. 验收 | \| 远端 doc root（实测路径） \| `/opt/eda/cadence/IC618/doc`（同版本 `virtuoso` 在 `/opt/eda/cadence/IC618/tools/dfII/bin/`；本版只作为配置示例，不做探测） \| |
| skillref#248 | table-row | 366 | 8. 验收 | \| 远端词条层取数 \| 一次递归下载 1.16 s（rc=0） \| |
| skillref#249 | table-row | 367 | 8. 验收 | \| 正文层限定 `cpf_ref`（本地扫描） \| 0.59–0.71 s，命中 `reference.html` 的 `ground bounce` \| |
| skillref#250 | table-row | 368 | 8. 验收 | \| 正文层整树（远端 `grep` 候选） \| 0.10–0.15 s（文本子集 223.8 MB / 9 426 文件） \| |
| skillref#251 | table-row | 369 | 8. 验收 | \| 正文层整树（本地纯 Python，对照） \| 189.17 s \| |
| skillref#252 | table-row | 370 | 8. 验收 | \| 远端单文件下载 \| `.tgf` 924 KB → 2.58 s；HTML 188 KB → 1.86 s；243 KB → 1.96 s \| |
| skillref#253 | table-row | 374 | 9. 证据索引 | \| 证据 \| 位置 \| |
| skillref#255 | table-row | 376 | 9. 证据索引 | \| 旧 finder 探测/解析/搜索 \| `src_bak/virtuoso_bridge/virtuoso/skill_finder/__init__.py:75/103/111/155/191`、`parser.py:44/50/92` \| |
| skillref#256 | table-row | 377 | 9. 证据索引 | \| 旧 More Info \| `src_bak/virtuoso_bridge/virtuoso/skill_finder/more_info.py:53/79/84/131/157/184` \| |
| skillref#257 | table-row | 378 | 9. 证据索引 | \| 旧文档检索 \| `src_bak/virtuoso_bridge/virtuoso/docs_search.py:24/117/191/272/417/742/965` \| |
| skillref#258 | table-row | 379 | 9. 证据索引 | \| 旧 CLI 入口 \| `src_bak/virtuoso_bridge/cli.py:1774/1811/1827` \| |
| skillref#259 | table-row | 380 | 9. 证据索引 | \| 8123 参考实现 \| `tools/skill_doc_server.py:34/74/100/118/197/485/523/664` \| |
| skillref#260 | table-row | 381 | 9. 证据索引 | \| 调研与方案 \| `doc/report/skilltooling-调研与上层包设计方案.md` \| |
| skillref#261 | table-row | 382 | 9. 证据索引 | \| 远端取数成本评估（实测） \| `doc/report/skillref-远端取数成本评估.md` \| |
| skillref#262 | table-row | 383 | 9. 证据索引 | \| 探针 \| `test/semi/probes/skill_tooling_probe.py`、`test/semi/probes/docs_search_probe.py` \| |
| skillref#263 | table-row | 384 | 9. 证据索引 | \| 包实现 \| `src/pyapi/packages/skillref.py`、`src/pyapi/packages/_skillref_docs.py` \| |
| skillref#264 | table-row | 385 | 9. 证据索引 | \| 包级真机探针与日志 \| `test/semi/probes/skillref_probe.py`、`test/artifacts/evidence/skill-tooling-tb/skillref-probe-{local,remote,config-local,config-remote}.log` \| |
| skillref#265 | table-row | 386 | 9. 证据索引 | \| 实测记录 \| `test/artifacts/evidence/skill-tooling-tb/docs-search-probe-20260921.log` \| |

## 上层/10-gui.md（10 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| gui#006 | clause | 11 | 1. 业务操作 | 窗口处理面向“卡住弹窗的恢复”：唯一清单入口是 X11 顶层窗口列表，动作只接受显式 `window_id`。 |
| gui#007 | table-row | 15 | 1.1 读操作（不改变业务服务器状态） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| gui#009 | table-row | 17 | 1.1 读操作（不改变业务服务器状态） | \| list_windows \| 返回 X11 **顶层**窗口列表（含分类、suggested_action） \| `query` 读 `gui.display` → `export DISPLAY` → `xprop _NET_CLIENT_LIST`（无 WM 退 root 直接子窗口）→ `xwininfo -root -tree` → 去重/分类 \| Q+G \| |
| gui#010 | table-row | 18 | 1.1 读操作（不改变业务服务器状态） | \| screenshot \| 截取任意 X11 窗口或整个显示并取回：`target∈{ciw, window_id, display}` \| `query` 读 `gui.display` → `export DISPLAY` → `XGetImage(root/窗口)` → PPM → 下载 \| Q+G+D \| |
| gui#011 | table-row | 22 | 1.2 写操作（改变业务服务器状态） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| gui#013 | table-row | 24 | 1.2 写操作（改变业务服务器状态） | \| send_key \| 对指定窗口注入按键：`key∈{enter, escape}` \| 注入 XTest 按键 → 校验 still_mapped \| G \| |
| gui#014 | table-row | 25 | 1.2 写操作（改变业务服务器状态） | \| auto_dismiss \| 自动发现 modal/dialog 并逐个恢复 \| 清单 → 分类 → 逐个 send_key → 逐窗口证据 \| G \| |
| gui#016 | clause | 31 | 2. 约定 | - 唯一清单入口：`list_windows` 只列 X11 顶层窗口，不再提供 SKILL 会话内清单； |
| gui#019 | clause | 34 | 2. 约定 | - 动作必须带显式 `window_id`，不存在“当前/最近窗口”隐式目标； |
| gui#022 | clause | 37 | 2. 约定 | - `auto_dismiss` 只处理分类为 dialog 的窗口，设次数上限并保留逐窗口证据； |

## 上层/11-veriloga.md（56 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| veriloga#011 | table-row | 19 | 1. 业务操作 | \| 类别 \| 操作名 \| 一句话说明 \| 接口 \| |
| veriloga#013 | table-row | 21 | 1. 业务操作 | \| 读 \| `virtuoso.veriloga.read` \| 读源码文本 / 端口 / 视图清单 / 诊断（`focus` 可选） \| S+D \| |
| veriloga#014 | table-row | 22 | 1. 业务操作 | \| 写 \| `virtuoso.veriloga.write` \| 通用写：对代码做原子文本编辑（只落盘） \| S+U \| |
| veriloga#015 | table-row | 23 | 1. 业务操作 | \| 检查保存 \| `virtuoso.veriloga.check_and_save` \| `VerAParseModule` 检查 + `ahdlUpdateViewInfo` 保存/刷新 CDF \| S+C \| |
| veriloga#017 | table-row | 27 | 1. 业务操作 | \| 载体 \| 说明 \| |
| veriloga#019 | table-row | 29 | 1. 业务操作 | \| 文本视图 `veriloga` \| dfII viewType=`text.veriloga`、dataType=`VERILOGAText`、主文件 `veriloga.va`（+ `master.tag`） \| |
| veriloga#020 | table-row | 30 | 1. 业务操作 | \| 持久化产物 \| `check_and_save` 后生成 `veriloga/netlist.oa` + `veriloga/data.dm`，并更新 cell CDF 的 `viewInfo` \| |
| veriloga#026 | table-row | 41 | 1.1 读操作（read） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| veriloga#028 | table-row | 43 | 1.1 读操作（read） | \| read \| `focus` 可选、可组合；不填=全部 \| 定位源码路径 → 读文本/端口/视图/诊断 \| S+D \| |
| veriloga#033 | table-row | 50 | 1.1 读操作（read） | \| focus \| 返回 \| |
| veriloga#035 | table-row | 52 | 1.1 读操作（read） | \| `source` \| `text / path / size / sha256 / lines` \| |
| veriloga#036 | table-row | 53 | 1.1 读操作（read） | \| `ports` \| 端口表 `name / direction / width`（`ahdlToPinList`；AHDL 上下文未加载时返回 `unsupported` 并说明） \| |
| veriloga#037 | table-row | 54 | 1.1 读操作（read） | \| `views` \| 该 cell 的视图清单（用 `ddMapGetFileViewType`/`ddMapGetFileDataType` 判定） \| |
| veriloga#038 | table-row | 55 | 1.1 读操作（read） | \| `diagnostics` \| 最近一次 `check_and_save` 的 `err_log / status / error_count / errors[]` \| |
| veriloga#041 | clause | 59 | 1.1 读操作（read） | - `read` 纯只读：不得调用 `ahdlUpdateViewInfo` 等会改缓存/视图状态的函数。 |
| veriloga#042 | table-row | 63 | 1.2 写操作（write） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| veriloga#044 | table-row | 65 | 1.2 写操作（write） | \| write \| 通用写：`lib/cell/view + commands[]` \| 读现状 → 逐原子改文本 → 覆盖写 \| S+U \| |
| veriloga#045 | clause | 67 | 1.2 写操作（write） | `write.commands` 每项 = `{"op": 原子名, ...参数}`；**非事务**，失败响应带 `commands applied: k/n`。 |
| veriloga#046 | table-row | 69 | 1.2 写操作（write） | \| 对象 \| 原子名 \| 索引（动哪个） \| 附加参数 \| |
| veriloga#048 | table-row | 71 | 1.2 写操作（write） | \| 代码 \| `set_source` \| 目标 view 或 file \| `text`；可选 `expected_sha256`（不符则失败） \| |
| veriloga#049 | table-row | 72 | 1.2 写操作（write） | \| 代码 \| `patch_source` \| 目标 view 或 file \| `edits[]`：`{old_text,new_text}` 或 `{start_line,end_line,new_text}`；匹配不唯一默认失败（可 `all=true`） \| |
| veriloga#050 | table-row | 73 | 1.2 写操作（write） | \| 文本视图 \| `ensure_view` \| `{library, cell, view="veriloga"}` \| `view_type="text.veriloga"`、可选 `create_if_missing=true`；内部写 `master.tag` + 主文件模板 \| |
| veriloga#051 | table-row | 74 | 1.2 写操作（write） | \| 文本视图 \| `delete_view` \| `{library, cell, view="veriloga"}` \| —（`ddDeleteObj`，先确认无编辑器窗口/`*.cdslck`） \| |
| veriloga#053 | clause | 78 | 1.2 写操作（write） | 1. 写临时文件 → 校验读回 → 原子替换 `veriloga.va`； |
| veriloga#055 | clause | 80 | 1.2 写操作（write） | （`master.tag` = `-- Master.tag File, Rev:1.0\nveriloga.va\n`；模块名必须与 cell 名一致）； |
| veriloga#057 | clause | 82 | 1.2 写操作（write） | 4. 有 `*.cdslck`（编辑器开着）时禁止外部写：报失败并提示关闭编辑器，不自动关别人的窗口。 |
| veriloga#058 | table-row | 86 | 1.3 检查与保存（check_and_save） | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| veriloga#060 | table-row | 88 | 1.3 检查与保存（check_and_save） | \| check_and_save \| GUI "Check and Save" 的 headless 等价序列 \| `VerAParseModule` 检查 → `ahdlUpdateViewInfo` 保存/刷新 CDF \| S+C \| |
| veriloga#067 | clause | 96 | 1.3 检查与保存（check_and_save） | 4. 前置：AHDL 上下文必须已加载（`loadContext("<IC618>/.../ahdlSck.cxt")`，见 §4）； |
| veriloga#068 | clause | 97 | 1.3 检查与保存（check_and_save） | 5. **不用** `ahdlCheckModule` / `ahdlSaveFile` / `ahdlEdit`（编辑器 GUI 内部包装，错误或缺 symbol 会弹模态阻塞 CIW）。 |
| veriloga#069 | clause | 99 | 1.3 检查与保存（check_and_save） | 真机结论：上述序列与 GUI Check and Save 的落盘形态**逐文件一致**，唯一差别是不含 GUI 弹窗生成的 `symbol` 视图； |
| veriloga#072 | table-row | 106 | 2. 归属（不在本包） | \| 能力 \| 归属 \| |
| veriloga#074 | table-row | 108 | 2. 归属（不在本包） | \| view CRUD（OA 视图） \| cellview \| |
| veriloga#075 | table-row | 109 | 2. 归属（不在本包） | \| 文本视图（`text.veriloga`）的建立与覆盖 \| **本包例外**（cellview 建不了） \| |
| veriloga#076 | table-row | 110 | 2. 归属（不在本包） | \| symbol 生成 \| symbol（`ahdlToPinList` 的 ports + `schPinListToSymbol`，待 spike；`ahdlSymbolGen` 禁用） \| |
| veriloga#077 | table-row | 111 | 2. 归属（不在本包） | \| 编译 / 仿真 / `ahdlSimDB` 缓存 \| spectre 包 \| |
| veriloga#078 | table-row | 112 | 2. 归属（不在本包） | \| 结构 Verilog \| verilog 包 \| |
| veriloga#079 | table-row | 113 | 2. 归属（不在本包） | \| GDS 导入/导出 \| layout（`layout.gds`） \| |
| veriloga#083 | clause | 120 | 3. 不在本版 | - 并发写同一 cell。 |
| veriloga#085 | clause | 125 | 4. 真机事实（IC6.1.8，2026-09-21 实 | `dbOpenCellViewByType(..., "veriloga"/"text.veriloga", "w")` **恒 nil** → 必须走文件路径； |
| veriloga#087 | clause | 127 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 3. 读源码用 `infile`/`gets` 或直接读文件；**`lineread` 不能读 `.va`**； |
| veriloga#088 | clause | 128 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 4. `ahdlCompile*` 不存在；编译只能由 Spectre（`ahdlcmi`）完成，缓存 `<netlist>.ahdlSimDB/<srcHash>.*.ahdlcmi/`； |
| veriloga#089 | clause | 129 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 5. AHDL 上下文（`ahdlSck.cxt`）默认未加载；**冷启动 `loadContext("<IC618>/tools.lnx86/dfII/etc/context/ahdlSck.cxt")` |
| veriloga#092 | clause | 132 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 7. 编辑器打开时产生 `veriloga.va.cdslck` 锁 → 外部写文件失效，必须先关编辑器； |
| veriloga#094 | clause | 134 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 9. **headless 的 Check and Save 已真机闭环**：写文件 → `VerAParseModule`（错误进 errFile）→ |
| veriloga#095 | clause | 135 | 4. 真机事实（IC6.1.8，2026-09-21 实 | `ahdlUpdateViewInfo`（CDF + `netlist.oa`/`data.dm`），与 GUI 保存逐文件一致，唯一差别是无 `symbol` 视图； |
| veriloga#096 | clause | 136 | 4. 真机事实（IC6.1.8，2026-09-21 实 | 10. **不要用** `ahdlCheckModule`（错误弹 `QverilogaErr` 阻塞）、`ahdlSaveFile`（缺 symbol 弹模态）、 |
| veriloga#098 | table-row | 141 | 5. 决策记录（2026-09-21，已确认） | \| # \| 决策 \| |
| veriloga#100 | table-row | 143 | 5. 决策记录（2026-09-21，已确认） | \| 1 \| 包名 `veriloga` / `11-veriloga.md`，operation 前缀 `virtuoso.veriloga.*` \| |
| veriloga#101 | table-row | 144 | 5. 决策记录（2026-09-21，已确认） | \| 2 \| 装码 = `write` + `check_and_save`，不提供 import \| |
| veriloga#102 | table-row | 145 | 5. 决策记录（2026-09-21，已确认） | \| 3 \| `check_and_save` = `VerAParseModule` + `ahdlUpdateViewInfo`；AHDL 上下文冷加载用 `loadContext` 全路径 \| |
| veriloga#103 | table-row | 146 | 5. 决策记录（2026-09-21，已确认） | \| 4 \| `write` 允许创建文本视图（`ensure_view`）——view CRUD 归属的显式例外 \| |
| veriloga#104 | table-row | 147 | 5. 决策记录（2026-09-21，已确认） | \| 5 \| 端口方向以 `.va` 的 module 声明为准（默认 `inputOutput`），调用方不重复传方向 \| |
| veriloga#105 | table-row | 148 | 5. 决策记录（2026-09-21，已确认） | \| 6 \| 不独立暴露 `reparse`/`ahdlUpdateViewInfo`，合并进 `check_and_save` \| |
| veriloga#106 | table-row | 149 | 5. 决策记录（2026-09-21，已确认） | \| 7 \| symbol 生成不在本包；需要时走 symbol 包（待 spike），`ahdlSymbolGen` 禁用 \| |
| veriloga#107 | clause | 153 | 6. 待验证（实现前需 spike） | 1. `schPinListToSymbol` 用 `ahdlToPinList` 的 ports 生成 symbol 的可行性（端口顺序/方向）。 |

## 上层/12-calibre.md（84 条）

| 编号 | 类型 | 行 | 小节 | 条款 |
|---|---|---:|---|---|
| calibre#005 | clause | 7 | 上层业务包：calibre | > **`calibre.pex` 未按官方三阶段验收，禁止用于交付/签核**；DRC/LVS/`export_cdl`/set 直驱已真机验证。 |
| calibre#011 | clause | 18 | 1. 总述 | 2. **默认非阻塞 + 三件套**：run 类操作默认立即返回 `job_id`（Calibre 动辄几十分钟），用 `calibre.status` 看进度、`calibre.read_results` 拿结构化结论；需要阻塞时用 `blocking=true`（包内轮询，形态同 maestro）； |
| calibre#014 | clause | 21 | 1. 总述 | 5. **失败可定位**：错误带 `kind`、工具原文片段、run dir 路径；`unknown-effect` 一律不自动重试。 |
| calibre#015 | table-row | 25 | 2. 业务操作 | \| 操作名 \| 说明 \| 步骤摘要 \| 接口 \| |
| calibre#017 | table-row | 27 | 2. 业务操作 | \| `calibre.check_env` \| 环境体检：二进制/版本/许可/PDK deck 可见性 \| C（`which`/`-version`/最小探测） \| C \| |
| calibre#018 | table-row | 28 | 2. 业务操作 | \| `calibre.drc` \| 启动 DRC \| stage deck → 改写占位符 → 后台启动 \| C(+U) \| |
| calibre#019 | table-row | 29 | 2. 业务操作 | \| `calibre.lvs` \| 启动 LVS（版图 vs CDL） \| 同上 + 源网表 \| C(+U) \| |
| calibre#020 | table-row | 30 | 2. 业务操作 | \| `calibre.pex` \| 启动 PEX（`-xrc -phdb → -pdb → fmt`） \| 三阶段串联，逐阶段校验产物 \| C(+U) \| |
| calibre#021 | table-row | 31 | 2. 业务操作 | \| `calibre.status` \| 只读查询：作业状态与进度 \| 读 `job.json` + 进程 + 日志尾 + 产物 \| C \| |
| calibre#022 | table-row | 32 | 2. 业务操作 | \| `calibre.read_results` \| 解析结果（DRC/LVS/PEX） \| 读报告 → 结构化摘要 \| D + 纯 Python \| |
| calibre#023 | table-row | 33 | 2. 业务操作 | \| `calibre.export` \| 按名下载产物 \| report / 结果库 / 网表 / pdb 目录 / 日志尾 \| D \| |
| calibre#024 | table-row | 34 | 2. 业务操作 | \| `calibre.export_cdl` \| 从 schematic 导出 LVS 源网表（CDL），走 Virtuoso 官方 auCdl 机制 \| 解析 cds.lib → 生成 `si.env`/`.simrc` → `si -batch -command netlist` → 校验产物 \| S+C(+U) \| |
| calibre#031 | clause | 47 | 3.1 作业与 run dir（确定性、可重建） | `job_id` 默认 `<kind>_<top>`（如 `drc_inv2`），请求可显式指定； |
| calibre#054 | clause | 80 | 3.3 环境与许可 | 取值顺序：**请求显式 `calibre_bin`** > `query().roles["command"].calibre.bin`； |
| calibre#057 | clause | 83 | 3.3 环境与许可 | - 包内启动器固定先 `ulimit -n 65536`（Calibre 对 fd 上限敏感，实测默认 1024 会告警）； |
| calibre#059 | clause | 85 | 3.3 环境与许可 | 许可问题由工具日志暴露，`read_results`/`status` 负责把 `license` 相关错误单独归类为 `license`（可重试）。 |
| calibre#060 | clause | 89 | 3.4 长任务与状态判据 | run 类操作默认 `blocking=false`：写 launcher、后台启动、立刻返回 `job_id`。 |
| calibre#062 | table-row | 92 | 3.4 长任务与状态判据 | \| 判据 \| 含义 \| |
| calibre#064 | table-row | 94 | 3.4 长任务与状态判据 | \| `job.json` 存在 + `pgrep -f <run_dir>` 命中 \| `running` \| |
| calibre#065 | table-row | 95 | 3.4 长任务与状态判据 | \| 日志尾出现完成标记（DRC: `CALIBRE::DRC-H COMPLETED`；LVS: `LVS completed`；PEX: `COMPLETED`） \| `completed` \| |
| calibre#066 | table-row | 96 | 3.4 长任务与状态判据 | \| 进程消失且无完成标记，或日志含 `FATAL ERROR`/`ERROR (OSSHNL-` \| `failed`（区分 `license` / `input` / `unknown`） \| |
| calibre#067 | table-row | 97 | 3.4 长任务与状态判据 | \| 进程消失、无产物、无日志尾 \| `unknown`（**不自动重试**） \| |
| calibre#068 | clause | 99 | 3.4 长任务与状态判据 | `blocking=true` 时包内循环：`deadline = now + timeout`，按 `poll_interval`（默认 5 s）调 `status`， |
| calibre#069 | clause | 100 | 3.4 长任务与状态判据 | 终态或超时即返回；超时返回 `status=timeout` 且**后台作业继续跑**。 |
| calibre#071 | table-row | 106 | 3.5 结果解析（`read_results`） | \| 字段 \| 内容 \| |
| calibre#073 | table-row | 108 | 3.5 结果解析（`read_results`） | \| `kind` \| `drc` / `lvs` / `pex` \| |
| calibre#074 | table-row | 109 | 3.5 结果解析（`read_results`） | \| `summary` \| DRC：`{total_results, rules_checked, by_rule:{规则名:条数}, first_offenders:[…]}`；LVS：`{status: correct/incorrect/not_compared/unknown, counts:{对象:layout 数, *_source:source 数}, differences:[…]}`；PEX：`{errors, w |
| calibre#075 | table-row | 110 | 3.5 结果解析（`read_results`） | \| `first_offenders` \| DRC：前 `limit` 条 `{rule, cell, bbox, count}`（来自 `DRC_RES.db`，layer 不含）；LVS 差异点在 `summary.differences` \| |
| calibre#076 | table-row | 111 | 3.5 结果解析（`read_results`） | \| `log_tail` \| 有界日志尾（默认 40 行） \| |
| calibre#077 | table-row | 112 | 3.5 结果解析（`read_results`） | \| `artifacts` \| 已产出的关键文件清单（名 + 字节数 + mtime） \| |
| calibre#078 | table-row | 118 | 4.1 `calibre.check_env` | \| 参数 \| 必填 \| 说明 \| |
| calibre#080 | table-row | 120 | 4.1 `calibre.check_env` | \| `token` \| 是 \| 原样透传 \| |
| calibre#081 | table-row | 121 | 4.1 `calibre.check_env` | \| `calibre_bin` \| 否 \| 默认 `calibre` \| |
| calibre#082 | table-row | 122 | 4.1 `calibre.check_env` | \| `deck` \| 否 \| 给了就顺带检查 deck 与同目录 `DFM/` 是否可见 \| |
| calibre#083 | table-row | 123 | 4.1 `calibre.check_env` | \| `timeout` \| 否 \| 默认 30 s \| |
| calibre#085 | table-row | 129 | 4.2 `calibre.drc` | \| 参数 \| 必填 \| 默认 \| 说明 \| |
| calibre#087 | table-row | 131 | 4.2 `calibre.drc` | \| `deck` \| 是 \| — \| DRC deck 路径 \| |
| calibre#088 | table-row | 132 | 4.2 `calibre.drc` | \| `gds` \| 条件 \| — \| 版图 GDS 路径（可用 `virtuoso.layout.gds` 产出）；**只有 deck 里出现 `"GDSFILENAME"`/`"lvs_top.gds"` 等占位符时才必填** \| |
| calibre#089 | table-row | 133 | 4.2 `calibre.drc` | \| `top` \| 条件 \| — \| 顶层 cell 名；同上（`"TOPCELLNAME"`/`"lvs_top"`） \| |
| calibre#090 | table-row | 134 | 4.2 `calibre.drc` | \| `job_id` / `run_dir` \| 否 \| `<kind>_<top>` / role 根下 \| 见 §3.1 \| |
| calibre#091 | table-row | 135 | 4.2 `calibre.drc` | \| `turbo` \| 否 \| 4 \| 传给 `-turbo` \| |
| calibre#092 | table-row | 136 | 4.2 `calibre.drc` | \| `hier` \| 否 \| true \| `-hier` \| |
| calibre#093 | table-row | 137 | 4.2 `calibre.drc` | \| `blocking` / `poll_interval` / `timeout` \| 否 \| false / 5 / 3600 \| 见 §3.4 \| |
| calibre#094 | table-row | 138 | 4.2 `calibre.drc` | \| `params` \| 否 \| — \| 无 set 时的取数口：键=**SVRF 语句头**（含空格），值=整条语句，原位改写 deck \| |
| calibre#095 | table-row | 139 | 4.2 `calibre.drc` | \| `runset` \| 否 \| — \| 远端 Calibre Interactive set（`.lvs`/`.drc`/`.pex`）：**走官方批处理入口**，参数全交给 Calibre \| |
| calibre#096 | clause | 141 | 4.2 `calibre.drc` | **参数一律用官方机制带**（两条路，互斥）： |
| calibre#120 | clause | 176 | 4.3.1 直接喂 Calibre Interactiv | （先默认名，再 `job.json.report_file`，最后在 run dir 内扫描 `*.report/*.rep`），与 set 是否改名无关。 |
| calibre#123 | clause | 181 | 4.3.1 直接喂 Calibre Interactiv | > 边界：set 只携带**参数**，不携带数据——它引用的 layout / 源网表 / hcell 文件必须已存在于远端； |
| calibre#127 | clause | 188 | 4.4 `calibre.pex` | 包会把它复制进 PEX 的 run dir）；`fmt` 可选 `none`/`spice`/`simple`（默认 `none`，即只到 `-pdb`）。 |
| calibre#128 | clause | 189 | 4.4 `calibre.pex` | 内部固定顺序：`-xrc -phdb` → `-xrc -pdb -rc <deck>` →（可选）`-xrc -fmt -<fmt>`， |
| calibre#129 | clause | 190 | 4.4 `calibre.pex` | **每个阶段校验产物存在**才进入下一阶段（phdb 必须是 xRC 类型，见可行性报告 §2）。 |
| calibre#132 | table-row | 197 | 4.5 `calibre.status` / `cali | \| 操作 \| 关键参数 \| |
| calibre#134 | table-row | 199 | 4.5 `calibre.status` / `cali | \| `status` \| `job_id` 或 `run_dir`；`timeout` \| |
| calibre#135 | table-row | 200 | 4.5 `calibre.status` / `cali | \| `read_results` \| `job_id`/`run_dir`；`kind`（可自动探测）；`limit`（默认 20）；`log_lines`（默认 40） \| |
| calibre#136 | table-row | 201 | 4.5 `calibre.status` / `cali | \| `export` \| `job_id`/`run_dir`；`items`（`summary`/`results_db`/`netlist`/`pdb_dir`/`log`/`all_small`）；`local_dir`（默认 `artifact_dir()/calibre/`） \| |
| calibre#140 | table-row | 209 | 4.6 `calibre.export_cdl`（LVS | \| 参数 \| 必填 \| 默认 \| 说明 \| |
| calibre#142 | table-row | 211 | 4.6 `calibre.export_cdl`（LVS | \| `library` / `cell` \| 是 \| — \| 要导出的 schematic 所在单元 \| |
| calibre#143 | table-row | 212 | 4.6 `calibre.export_cdl`（LVS | \| `view` \| 否 \| `schematic` \| 起始视图 \| |
| calibre#144 | table-row | 213 | 4.6 `calibre.export_cdl`（LVS | \| `netlist_name` \| 否 \| `<cell>.cdl` \| 产物文件名（写入 run dir） \| |
| calibre#145 | table-row | 214 | 4.6 `calibre.export_cdl`（LVS | \| `run_dir` \| 否 \| `<command root>/calibre/cdl_<cell>` \| 导出工作目录 \| |
| calibre#146 | table-row | 215 | 4.6 `calibre.export_cdl`（LVS | \| `cds_lib` \| 否 \| CIW `getWorkingDir()/cds.lib` \| cds.lib 路径；显式给出优先 \| |
| calibre#147 | table-row | 216 | 4.6 `calibre.export_cdl`（LVS | \| `timeout` \| 否 \| 600 \| si 超时 \| |
| calibre#151 | clause | 222 | 4.6 `calibre.export_cdl`（LVS | **`checkCAPPERI=nil`**——IC618 auCdl batch 的默认值缺口，缺失即 `OSSHNL-411`）与一致的 `.simrc`； |
| calibre#160 | clause | 235 | 5. 不做与本版限制 | 5. 不做并发调度：同一 token 建议串行跑 PDR；许可争用表现为工具报错，由调用方决定重试。 |
| calibre#171 | clause | 252 | 7. 已知限制 | 2. 大设计的 `svdb`/`*.pdb` 可能很大：`export` 默认只取小文件，目录需显式点名； |
| calibre#172 | clause | 253 | 7. 已知限制 | 3. `power`/`ground` 未给时沿用 deck 默认（可能触发 ERC 告警，见可行性报告 §2 的 LVS 实测）； |
| calibre#173 | clause | 254 | 7. 已知限制 | 4. 许可不足、并发争用未做全局串行（§5.5）。 |
| calibre#176 | table-row | 261 | 8. 验收 | \| 组 \| 用例 \| |
| calibre#178 | table-row | 263 | 8. 验收 | \| env \| `check_env` 返回路径/版本；deck 不可见时报 `deck_ok=false` 并给原因 \| |
| calibre#179 | table-row | 264 | 8. 验收 | \| EXPORT \| `export_cdl` 产出**含 `.SUBCKT` + 器件行**的 CDL（只出端口壳即失败）；`netlist_name` 只能是纯文件名 \| |
| calibre#180 | table-row | 265 | 8. 验收 | \| DRC \| 小 GDS（`lay_e2e.gds` 顶层 `lay_e2e`）跑通：`status=completed`、`read_results` 给 rules_checked/结果计数；对照可行性报告基线（1737 规则 / 36 结果） \| |
| calibre#181 | table-row | 266 | 8. 验收 | \| LVS \| `ctle.gds`+`ctle.cdl`：`status=completed`、`summary.status ∈ {match, incorrect}`、产物含 `svdb/*.phdb` \| |
| calibre#182 | table-row | 267 | 8. 验收 | \| LVS 闭环 \| `export_cdl` 的 CDL 直接喂 LVS（`CMP_LIB/inv2` + `inv2.gds`）；`VB_CALIBRE_REQUIRE_LVS_VERDICT=1` 时要求 `correct` \| |
| calibre#183 | table-row | 268 | 8. 验收 | \| PEX \| 同组输入跑到 `-pdb`：`svdb/*.pdb/` 存在、`summary.errors==0`；`fmt=spice` 时产出网表 \| |
| calibre#184 | table-row | 269 | 8. 验收 | \| 三件套 \| `blocking=true` 与 `blocking=false`+`status` 轮询两种用法结果一致 \| |
| calibre#185 | table-row | 270 | 8. 验收 | \| 失败 \| deck 路径不存在 → 明确失败；GDS 顶层名错 → 工具原文回带；不给 token → 400 \| |
| calibre#186 | table-row | 271 | 8. 验收 | \| 参数面 \| deck 无占位符（自包含）时 `gds/top/cdl` 可省；deck 引用 `"lvs_top.cdl"` 而没给 `cdl` → 明确失败 \| |
| calibre#187 | table-row | 275 | 9. 证据索引 | \| 证据 \| 位置 \| |
| calibre#189 | table-row | 277 | 9. 证据索引 | \| 可行性报告（DRC/LVS/PEX 实跑、CDL 调查、新用户 calprobe 会话） \| `spec/research/calibre/02-可行性报告.md` \| |
| calibre#190 | table-row | 278 | 9. 证据索引 | \| Calibre 环境探针 \| `test/semi/probes/calibre_env_probe.py` \| |
| calibre#191 | table-row | 279 | 9. 证据索引 | \| CDL 批处理探针（si.env/.simrc 生成） \| `test/semi/probes/calibre_cdl_probe.py` \| |
| calibre#192 | table-row | 280 | 9. 证据索引 | \| auCdl 导出机制调查（官方链路、runset/control-file 实测） \| `spec/research/calibre/03-网表导出机制调查报告.md`（§8/§9） \| |
| calibre#193 | table-row | 281 | 9. 证据索引 | \| 实跑现场（远端） \| `/home/Gent/project/vblog/calibre_probe/{drc_run,lvs_run,rcx_run}/` \| |
| calibre#194 | table-row | 282 | 9. 证据索引 | \| 新注册用户与独立 env \| `/home/Gent/project/calprobe/`（`calprobe`，见可行性报告 §3.4） \| |

