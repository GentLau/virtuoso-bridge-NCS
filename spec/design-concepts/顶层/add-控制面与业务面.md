# 顶层补充：控制面与业务面

> 版本：Draft v34
> 日期：2026-09-21
> 状态：Normative（顶层 HTTP 端点清单、端口划分与权限口径的唯一 owner）
> Supersedes：Draft v33（config.json 多键、common.config 只读快照、skillref 段与 doc_token）
> 定位：本文是[顶层](1-顶层.md)的端点补充——[顶层](1-顶层.md)定义顶层职责、调度与响应壳；本文定义顶层开哪些端口、哪些方法、支持哪些请求、每个端点需要什么权限。注册语义见[多用户与注册 §3/§5](../其他/1-多用户与注册.md)。

## 1. 双面双端口

- 顶层对外 HTTP 分两个面，各自独立监听：
  - **控制端口**：注册、用户管理、全局配置与人类操作；低并发，面向人与运维；
  - **业务端口**：业务包调度；程序调用，高并发。
- 标准形态 = **同机双进程**：管理进程为父，业务进程为子（不 detach，管理退出即停业务）；业务崩溃不影响管理。可同进程部署作为简化选项；跨机进程控制本版不做。控制/业务端口的监听地址与端口、工作路径都作为**启动参数**传入，不写入配置 JSON。
- 两面不混用：业务请求只到业务端口，注册/管理/配置只到控制端口；业务崩溃不影响管理，管理退出停止业务；
- 控制端口默认只绑定 `127.0.0.1`，管理操作经 SSH 隧道访问；业务端口绑定地址按部署配置。

## 2. 权限等级（本文唯一口径）

| 等级 | 含义 | 本版处理 |
|---|---|---|
| 无权限 | 任何人可调用 | — |
| 会话 token | 该注册会话自己的 token（`apply` 返回） | 请求携带并校验 |
| 个人 token | 目标 user 自己的 token（注册表条目） | 请求携带；结构校验在顶层；业务端口的合法性与路由由中层判定，控制端口 `/api/bug` 例外见 §3 |
| 管理权限 | 管理员身份 | 本版 = 内置单管理员 token：服务端只存其 **SHA-256 哈希**（不存原文），比较用 `hmac.compare_digest`；私钥签名方案标为**后续版本** |

- 个人/会话 token 随请求传入：POST/DELETE 放请求体；GET 放 `token` 查询参数；
- 管理权限：`Authorization` 携带内置管理员 token，服务端只比对 SHA-256 哈希；校验失败 401；审计日志只记身份，凭据不进日志；
- 权限不足 → 4xx，不改变状态。

## 3. 控制端口端点

**人类操作**

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| GET | `/` | 注册页（HTML），人类操作入口 | 无权限 |
| GET | `/health` | 存活探针（运维用） | 无权限 |
| GET | `/help` | 端点清单与用法说明 | 无权限 |
| POST | `/api/bug` | 提交 bug 报告（格式不做要求） | 个人 token |

**六步注册**（语义唯一 owner 见[多用户与注册 §3](../其他/1-多用户与注册.md)）

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| POST | `/api/register` | 注册命令：`{user, action, token?, 参数}`，`action` ∈ `apply / validate / probe / deploy / verify / commit / cancel` | `apply` 无权限；其余 action 会话 token |
| GET | `/api/register/<user>` | 查询进行中的注册状态 | 会话 token |

状态机转移（本文是[多用户与注册 §3](../其他/1-多用户与注册.md)六步状态机的 HTTP 投影，语义以该文档为准）：

| action | 合法前提 |
|---|---|
| `apply` | 无同名进行中会话 |
| `validate` | 刚 `apply`；失败后可原样重试 |
| `probe` | 刚 `validate`；失败后可原样重试 |
| `deploy` | 刚 `probe`；失败后可原样重试 |
| `verify` | 刚 `deploy`；或上一次 `verify` 失败（可原地重试） |
| `commit` | 刚 `verify` 成功；失败后可原地重试 |
| `cancel` | 任意非 committed 的进行中会话 | 释放内存候选，不落盘

- 非法 action/顺序 → 4xx `{"error": "step order violation", "current_stage": …, "expected": …}`，**不改变会话状态**；
- 各步失败后候选保留，可**原样重试同一步**（不携带参数修正）；**修正参数必须 `cancel` 后重新 `apply`**；只有 `cancel`（或服务重启）才释放候选；
- `apply` 响应返回 `token`（用户显式提供则原样，缺省自动生成）；除 `apply` 外的 action 必须携带 `token`，服务端校验其与候选一致，缺失/不一致 → 4xx `invalid token`，**不改变会话状态**；
- 六步由该命令端点逐个调用完成：`apply` 以 body 中的 `user` 建**内存候选**（尚未进注册表），后续 action 都以该 `user` 定位候选；`commit` 前 registry 不存在该 user，失败/取消则丢弃候选。

**用户管理**（语义见[多用户与注册 §5](../其他/1-多用户与注册.md)）

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| GET | `/api/users` | 用户列表（响应脱敏 token） | 管理权限 |
| GET | `/api/user/<user>` | 读取用户条目（响应脱敏 token） | 管理权限 |
| POST | `/api/user/<user>/update` | 修改条目（白名单字段） | 管理权限 |
| DELETE | `/api/user/<user>` | 删除条目（本机解绑 ≠ 远端吊销） | 管理权限 |

**全局配置**（边界见 §5）

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| GET / PUT | `/api/config` | 业务 server 线程池大小（`config.json`，仅 `business_thread_pool_size`） | 管理权限 |

**业务进程管理**（管理进程为 supervisor，响应脱敏 token）

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| GET | `/api/process/status` | 业务进程 pid/端口/工作路径/启动参数/状态（`starting` / `ready` / `crashed`） | 管理权限 |
| POST | `/api/process/reload` | 重新导入 `registry.json` 与 `config.json`、关闭旧 token 缓存；`business_thread_pool_size` 对**新请求**立即生效，在途不受影响 | 管理权限 |
| POST | `/api/process/restart` | 拒绝新请求、等在途完成（上限 **30 秒**，超时强杀）、按原启动参数重新拉起；强杀覆盖业务进程组及 SSH 后代 | 管理权限 |

- `target` 仅 `business`；子进程意外退出 → `crashed`，不自动拉起，需管理员 `restart`；
- `status`：`starting/ready/crashed`（`starting` = 已拉起未 ready）；`restart` 期间监听保持，新请求 `503 + Retry-After`，在途排空 30s 后强杀并重拉；管理端同步等待、自身超时 > 30s；
- `reload` 走 spawn 时建立的内部控制通道；同进程部署：`reload` 原地重导、`restart` 501、`status` 含 `same_process=true`；
- 未托管或跨机业务进程 → `409/501`；审计日志不含凭据。

- 修改类（update/delete）路径以 `user` 定位，**收归管理员**：个人 token 不能自助修改；update 请求体含 `token` 字段 → 拒绝；
- 控制端口成功返回 JSON（或 HTML 页面）；失败 4xx + `{"error": …}`（可选 `detail`）；注册各步结果含 `warnings`（见[多用户与注册 §3.2](../其他/1-多用户与注册.md)）；任何 **entry 对象**（候选 entry、用户查询/更新返回）均不含 `token`；session token 只作为注册响应顶层字段返回；
- 请求体上限 **16 MiB**，超限 → `413`；
- 控制端口不运行业务操作；`POST /api/bug` 携带个人 token，合法性由控制进程经注册与管理模块的 registry 内存快照校验（不经中层、不读注册表文件）；**无 token 或无效 → 4xx，不记录**；校验通过后，服务端**先剥离 token/Authorization 等凭据**再记录原始请求体，并附加提交 user、提交日期时间、当前状态摘要、备份的近期操作/错误日志，统一写入本地工作目录 `log/bug_reports/`（每份一个条目）；不解析内容、不触发业务，成功返回 2xx 收据。

## 4. 业务端口端点

| 方法 | 路径 | 用途 | 权限 |
|---|---|---|---|
| POST | `/api/operation` | 业务调度：`{operation, token, 业务字段}` → 查注册表 → 构造 Request → 调用对应方法 → 响应壳 | 个人 token |
| GET | `/health` | 存活探针（运维用） | 无权限 |
| GET | `/help` | 端点清单与用法说明 | 无权限 |

- 业务端口只做 operation 调度，不开注册/管理/配置端点；`query` 是上层↔中层接口，不是 HTTP 端点；
- 调度顺序与响应壳的唯一口径见[顶层 §2/§3](1-顶层.md)。

## 5. 全局配置与启动参数

- 工作路径下除 `registry.json` 外，另存一份配置 JSON `config.json`；`GET/PUT /api/config` 操作该配置：GET 读内存快照，PUT 只覆盖请求里出现的顶层键、未出现的键原样保留，校验通过后更新快照并原子写回 `config.json`；
- 当前 `config.json` 登记两个顶层键：`business_thread_pool_size`（业务 server 线程池大小）与 `skillref`（结构校验见下，业务语义见 [skillref §3](../上层/9-skillref.md)）；未登记的键**原样透传**、控制面不解读；
- 控制/业务端口与工作路径由**启动参数**给定，不写入 `config.json`；
- 业务进程启动时导入 `registry.json`/`config.json`，运行期不读文件；`/api/process/reload` 或 `restart` 显式刷新；`PUT /api/config` 只更新控制进程快照并写回 `config.json`；`config.json` 经 `common.config` 提供**进程级只读快照**（控制面是唯一写者、请求期零文件 IO）；`business_thread_pool_size` 是**可变准入上限**：reload 后新请求按新上限准入；在途数 ≥ 新上限时，新请求拒绝（`429 + Retry-After`）直至低于上限；
- `skillref` 段结构校验（本文唯一口径，业务语义见 [skillref §3](../上层/9-skillref.md)）：`source ∈ local/remote`（大小写不敏感）、`doc_root` 非空绝对路径且不含 NUL、`doc_token` 若给出必须是已注册 user 的 token（控制进程经注册与管理模块的 registry 快照校验）；值缺失或 `null` = 未配置，不阻断进程启动；`GET /api/config` 回带 `skillref` 段时 `doc_token` 一律脱敏（不回原文），审计与日志不含该凭据；
- 管理员 token 哈希**写死在代码**（不读环境变量）；原文离线保管、不落配置、不进日志；校验目标与规则同样写死在代码，当前版本单管理员；
- `runtime.thread_pool_size` 是**每 token** 的注册表配置（唯一 owner 见[并发设计 §2](../中层/2-并发设计.md)），与本节的“全局线程池上限”不是一回事：前者是单用户预算，后者是顶层进程能力上限；两者独立，不互相替代。

## 6. 索引

- 六步注册与第五步失败语义：[多用户与注册 §3](../其他/1-多用户与注册.md)；
- 用户 update/remove 与远端吊销：[多用户与注册 §5](../其他/1-多用户与注册.md)；
- 调度顺序、响应壳与错误分界：[顶层 §2/§3](1-顶层.md)；
- 并发与限流：[并发设计](../中层/2-并发设计.md)；
- 本版不做：[本版范围与明确不支持](../总览/add-本版范围与明确不支持.md)。
