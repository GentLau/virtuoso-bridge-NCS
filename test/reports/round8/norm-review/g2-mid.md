# NORM 评审 · g2-mid（46 条）

> verdict: direct / indirect / partial / gap / na；evidence 为已确认断言的 TB 文件。

| 编号 | 条款（截断） | verdict | 证据 | 说明 |
|---|---|---|---|---|
| 路由#005 | > 关联：字段定义见[中层配置文档 §2](../中层/add-中层配置文档.md)；接口基线见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)；并发与预算见[并发设计](2-并发设计.md) | **na** | — | 索引/关联声明，无独立可测行为 |
| 路由#008 | 2. **第二步（用户内检查与投递）**：在用户内按 role 解析目标后，执行并发 owner 的限流检查（线程预算、最大通道数、单目标点上限，见[并发设计 §2/§3](2-并发设计.md)），**容得下才继续投递* | **direct** | test/offline/core/semantics_tb.py<br>test/offline/unit/test_endpoint_budgets.py | 第二步限流检查后‘排队或直接投递’有闸门/预算断言 |
| 路由#009 | 3. 任一限流参数容不下 → 返回容量拒绝并**指明是哪个参数**（结果字段见[四层整体架构与接口 §4.5](../总览/1-四层整体架构与接口.md)）；拒绝文本与记账见[并发设计 §2/§3](2-并发设计.md) | **direct** | test/offline/core/fault_injection_tb.py<br>test/offline/unit/test_endpoint_budgets.py | 容量拒绝时必须指明具体预算，有断言（三预算分别覆盖） |
| 路由#013 | B --> C["第二步：并发限流检查（见 2-并发设计 §2/§3）"] | **na** | — | 流程图节点（与 #008 同义），由 #008 承担 |
| 路由#014 | C -- 容不下 --> R["容量拒绝，指明哪个参数"] | **direct** | test/offline/core/fault_injection_tb.py | ‘容不下 → 容量拒绝并指明哪个参数’有断言（与 #009 同一用例族） |
| 路由#015 | C -- 容下 --> D["排队或直接投递（见 2-并发设计 §1）"] | **direct** | test/offline/core/semantics_tb.py | ‘容下 → 排队或直接投递’由串行闸门用例覆盖 |
| 路由#018 | - 排队/投递超时语义、预算与记账见[并发设计 §1–§3](2-并发设计.md)；注册表导入与 token 生命周期见[多用户与注册](../其他/1-多用户与注册.md)。 | **na** | — | 索引/关联声明，无独立可测行为 |
| 路由#024 | 这条准则同时是评审 P0-01 的关闭口径：规范不再承诺"gui 与 daemon 必须同机"，也不再假设；bridge 按配置投送。 | **indirect** | test/live/flows/role_split_tb.py | role 跨主机不被拒绝已有真机证据（daemon/gui 在 wsl-gent、command/file 在 w1）；**gui 与 daemon 异机**无环境（第二台真 GUI 主机）——桥层按配置投送，不假设同机 ｜ 缺口: 环境限制项：如需闭合，需第二台带 X/Virtuoso 的主机；当前以‘跨主机投送不被拒绝’的同等证据承担 |
| 路由#032 | - 一个 token 拥有**五个 role**，这些 role **可以分布在多个主机**（含混合 local/remote）；bridge 不因为 role 跨主机而拒绝注册或拒绝投送； | **direct** | test/live/flows/role_split_tb.py<br>test/offline/unit/test_validation_roles.py | 五 role 可跨主机（含回退）注册与投送：真机 S2 5/5 + 离线解析用例 |
| 路由#033 | - 一个 token **只允许一个 daemon role、一个活动 daemon、一个 CIW**：daemon 是本版唯一“单实例”资源，第二处 `load` 同一 token 属于配置错误；需要第二个 CIW 时 | **indirect** | test/offline/unit/test_middle_contracts.py<br>test/offline/scenario/test_multi_user_isolation.py<br>test/live/transport/cov_remote_real.py | 一 token→一 daemon 的映射与多 token 隔离有断言；‘第二 CIW=配置错误’属环境约定（无负向用例） |
| 路由#036 | - 该边界是本文的唯一口径；其它文档不得再出现“一个 token 多主机：不支持”这类无限定的表述。 | **na** | — | 唯一口径/文档纪律声明，无可测行为 |
| 路由#037 | `role.<name>.mode=local` 表示中层就在该 role 的目标主机上、直接本地执行、不经 SSH；`mode=remote` 表示经 SSH 投送到该 role 的 host/user；**不同 ro | **direct** | test/offline/unit/test_validation_roles.py<br>test/offline/unit/test_register_flow.py<br>test/offline/unit/test_norm_gap_round8.py::TestMixedModeSingleToken | 逐 role mode 解析有离线断言；同 token 混合模式（daemon=local + command=remote）原样保留由 test_norm_gap_round8 钉住（第八轮补） |
| 路由#046 | **GUI / Spectre 命令的本质**：它们是"用并行模式执行命令"——每次调用在对应 role 上执行一条一次性（one-shot）命令，不建立常驻会话、不保留 cwd/env，等价于 `parallel=Tr | **direct** | test/offline/unit/test_tunnel_transfer.py<br>test/semi/transport/one_shot_burst_tb.py | gui/spectre 一次性命令（不建常驻会话）+ 占 channel 预算，有离线与半真机断言 |
| 路由#052 | - endpoint 身份只由 `(host, user, jump_host, jump_user, proxy)` 决定；**连接复用另要求解析后的 SSH 凭据（`key_dir`+`key`）一致**：同一 en | **direct** | test/offline/unit/test_credential_routing.py<br>test/offline/unit/test_spec_contracts.py | endpoint 身份五元组 + 凭据一致性才复用，向量与隔离用例均有断言 |
| 路由#053 | **复用原则（唯一口径）**： | **na** | — | ‘复用原则’小节标题，内容在 #052/#060 等条目 |
| 路由#059 | - 连接生命周期（建连/重试/关闭）见[并发设计 §4](2-并发设计.md)； | **na** | — | 索引/关联声明，无独立可测行为 |
| 路由#060 | - 预算：线程预算与最大通道数**每 token 一份**（token 内所有 endpoint 共享），单目标点上限按 endpoint（字段配置在 role、共享 endpoint 取最小值）；记账矩阵见[并发设计  | **direct** | test/offline/unit/test_endpoint_budgets.py | 线程预算/最大通道数每 token 一份、单点上限取最小值，均有断言 |
| 路由#067 | - 字段与默认值：[中层配置文档](../中层/add-中层配置文档.md)； | **na** | — | 索引/关联声明，无独立可测行为 |
| 路由#068 | - 接口签名与错误模型：[四层整体架构与接口](../总览/1-四层整体架构与接口.md) §4； | **na** | — | 索引/关联声明，无独立可测行为 |
| 路由#070 | - 并发、预算与连接复用：[并发设计](2-并发设计.md)； | **na** | — | 索引/关联声明，无独立可测行为 |
| 并发#005 | > 关联：字段定义见[中层配置文档 §2.2/§2.3](../中层/add-中层配置文档.md)；接口语义见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)；错误分类见[四层整体架构与接口 §4 | **na** | — | 索引/关联声明，无独立可测行为 |
| 并发#006 | 五个业务接口按并发形态归为三类： | **direct** | test/offline/core/semantics_tb.py<br>test/semi/transport/one_shot_burst_tb.py | 串行 Skill/串行命令/并行三类形态有闸门与 one-shot 断言 |
| 并发#012 | - 串行两类的排队都在中层**投递前**发生，按 token 隔离（per-token 闸门）； | **direct** | test/offline/core/semantics_tb.py | 投递前排队、per-token 闸门、队列不跨 token 有断言 |
| 并发#013 | - 排队等待消耗同一条端到端 deadline：**排队中超时 = 未投递**（确定未执行，该“可安全重试”仅属中层内部策略）；**已投递后超时 = 结果未知**（中层不重发；是否重试由上层业务操作自行决断）；Skill | **direct** | test/offline/core/semantics_tb.py<br>test/offline/unit/test_persistent_shell_protocol.py | 排队超时=未投递（可安全重试）/已投递超时=结果未知，两条语义均有断言 |
| 并发#020 | - 三个预算互相独立，任一超限 → 返回容量拒绝并指明具体预算（结果字段见[四层整体架构与接口 §4.5](../总览/1-四层整体架构与接口.md)），**不排队等待**； | **direct** | test/offline/unit/test_endpoint_budgets.py<br>test/offline/core/fault_injection_tb.py | 三预算独立、超限不排队、指明具体预算，均有断言 |
| 并发#022 | - 多个 role 解析到同一 endpoint 时共享一个计数器，有效上限取这些 role 的 `max_sessions` 最小值；remote daemon 的专用 Skill tunnel 计入该 endpoin | **direct** | test/offline/unit/test_endpoint_budgets.py | 同 endpoint 多 role 共享计数、上限取最小值、daemon Skill 隧道计入，均有断言 |
| 并发#034 | - 建连失败只在无副作用阶段重试，**最多 3 次总尝试（含初次）**；ControlMaster 故障自动降级直连；重试共享同一条剩余预算； | **direct** | test/offline/unit/test_connect_retry.py<br>test/offline/unit/test_ssh_tunnel_lifecycle.py | ≤3 次总尝试、ControlMaster 降级、共享剩余预算，均有断言 |
| 并发#038 | - 字段与默认值：[中层配置文档 §2](../中层/add-中层配置文档.md)； | **na** | — | 索引/关联声明，无独立可测行为 |
| 并发#040 | - 错误 kind 与保留码：[四层整体架构与接口 §4.5](../总览/1-四层整体架构与接口.md)； | **na** | — | 索引/关联声明，无独立可测行为 |
| 并发#042 | - 本版不支持的并发能力：[本版范围与明确不支持](../总览/add-本版范围与明确不支持.md)。 | **na** | — | 索引/关联声明，无独立可测行为 |
| 日志#009 | - **不向 CDS.log 注入任何输出**：不得因为“要返回日志”就往 CDS.log 写 BEGIN/END marker 或其他行——日志返回只读文件，不改文件； | **direct** | test/offline/unit/test_log_no_fetch.py<br>test/offline/unit/test_daemon_log_contract.py::test_daemon_never_writes_markers_into_cds_log | IL/daemon 源码级断言不得出现 VB-BEGIN/END 等注入 marker（日志只读不改文件） |
| 日志#035 | - `[start,end)` 之外的并发输出不属于本次增量；等待请求留在中层投递前队列，daemon 同一时刻只接收/执行一个由闸门放行的 Skill 请求。 | **direct** | test/offline/unit/test_daemon_log_contract.py::test_reads_exact_interval<br>test/offline/unit/test_daemon_log_contract.py::test_rotated_file_reads_from_zero | [start,end) 精确区间与轮转后从 0 读，均有断言 |
| 日志#045 | `log_max_bytes`（默认 64KB）： | **direct** | test/offline/unit/test_common_config.py<br>test/offline/unit/test_daemon_log_utf8_budget.py | 默认 64KB 在配置默认值测试；字节预算是 diff/truncate 用例的边界 |
| 日志#055 | - 最后一步按**字节截断、只取靠前部分**：例如上限 100 字节、本次增量起于 offset 10、error 增量到 200，则返回 10–110，之后内容本次不补发； | **direct** | test/offline/unit/test_daemon_log_utf8_budget.py | ‘只取靠前字节前缀、不补发、切到半个 UTF-8 字符要丢弃’，逐 max_bytes 扫描断言 |
| 日志#066 | {"value": "3", "log": "\\e ...本次错误行...\\n"} | **na** | — | 示例 payload 形态，由 #070/#077/#082 的帧/日志断言覆盖 |
| 日志#070 | - **本版只解析 JSON payload**；旧 daemon（无 token）不在支持范围，收到非法帧按协议错误处理。 | **direct** | test/offline/unit/test_daemon_runtime_contracts.py<br>test/offline/integration/test_daemon_handler.py | 只解析 JSON payload、非法帧/非法字段按协议错误处理，均有断言 |
| 日志#077 | - 帧顺序固定：第一帧 `value/error`，第二帧 `meta`；两帧必须由 IL 合并为**一次 `ipcWriteProcess`** 写入，避免重排； | **direct** | test/offline/core/daemon_log_protocol_tb.py<br>test/offline/unit/test_norm_gap_round8.py::TestIlSingleIpcWrite | 帧顺序在 socket 协议层有断言；‘IL 合并为一次 ipcWriteProcess + meta 追加同一缓冲’由 test_norm_gap_round8 钉住（第八轮补） |
| 日志#082 | - `CDS.log` 不存在/不可读/路径变化且读取失败，或第二帧缺失/超时：**本次 log=""，Skill 结果照常返回**，`VirtuosoResult.warnings` 追加固定文本 `CDS.log u | **direct** | test/offline/integration/test_daemon_handler.py::test_unavailable_cds_log_uses_frozen_warning_text | CDS.log 不可读 → log="" + warnings 固定文案、结果照常返回，有断言 |
| 日志#091 | 7. 非法 `log_level`/`log_max_bytes` 直接拒绝报错；`CDS.log` 不可读时 `log=""` 且 `warnings` 含固定文本 `CDS.log unavailable: <rea | **direct** | test/offline/integration/test_daemon_handler.py<br>test/offline/unit/test_daemon_log_utf8_budget.py | 非法 log_level/log_max_bytes 直接 NAK（不夹紧）、不可读固定 warnings、截断不出半个 UTF-8 字符，均有断言 |
| 顶层#005 | > 定位：顶层只做入口与调度。业务包与业务操作契约见[上层 §2/§4](../上层/1-上层.md)；分层职责与依赖见[四层整体架构与接口 §3](../总览/1-四层整体架构与接口.md)；五业务接口与错误总则见[四 | **na** | — | 定位声明（顶层只做入口与调度），由 #009/#028 的可测条款承担 |
| 顶层#009 | - 限流不是顶层职责：中层 per-token 预算由中层计账（见[并发设计 §2/§3](../中层/2-并发设计.md)），顶层不解释该预算；顶层自身业务请求准入上限见[控制面与业务面 §5](add-控制面与业务面 | **direct** | test/offline/unit/test_upper_layer_import_contract.py<br>test/offline/unit/test_endpoint_budgets.py | 顶层不引 transport（import 契约）+ 预算记账在中层（预算用例），两侧合起来钉死职责边界 |
| 顶层#018 | - 一个业务包可以出现在多行（每个业务操作一行）；**单操作业务包只登记一行，同样成立**；同一业务操作名重复登记是启动错误； | **direct** | test/offline/unit/test_top_layer_dispatch.py::test_duplicate_operation_is_startup_error<br>test/offline/core/api_server_tb.py | 同操作名重复登记=启动错误有断言；单操作包一行成立由 dispatch 用例覆盖 |
| 顶层#028 | - 可测试约束：处理/调度模块只允许标准库、`common.paths`、`common.jsonutil`、`common.config`（纯工具基座）、`server.*`、`pyapi.*`；不得出现 `trans | **direct** | test/offline/unit/test_upper_layer_import_contract.py | 处理/调度模块的允许/禁用 import 清单逐条断言（transport/socket/subprocess/paramiko 禁用） |
| 顶层#042 | - 未预期异常必须被顶层捕获：单请求失败不影响其它请求，不终止服务。 | **direct** | test/offline/unit/test_api_server_main.py::test_unserializable_result_is_structured_500<br>test/offline/unit/test_top_layer_pool.py | 未预期异常结构化 500（不终止服务）+ 线程池/单请求失败隔离用例 |
| 顶层#050 | - 分层职责、依赖方向、五业务接口与错误总则：[四层整体架构与接口](../总览/1-四层整体架构与接口.md) §3/§4； | **na** | — | 索引/关联声明，无独立可测行为 |
| 顶层#051 | - 并发与限流：[并发设计](../中层/2-并发设计.md)； | **na** | — | 索引/关联声明，无独立可测行为 |
