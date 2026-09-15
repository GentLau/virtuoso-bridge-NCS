# 08 多节点拓扑调研（2026-09-14）

> **Research / 非规范**：本文只提供背景与依据，**不得用于实现或验收**；各主题的唯一口径见 [Spec 索引](../README.md)。


> 性质：Research（背景与决策依据，**不是规范**）
> 方法：三名独立调查员并行取证后交叉核对——① 旧代码考古（`src_bak/` + git 历史），② 当前 Spec/实现审计，③ 需求与必要性分析。所有结论附证据引用。
> 关联：`spec/design-concepts/总览/1-四层整体架构与接口.md`、`add-中层配置文档.md`、`1-多用户与注册.md`、`doc/设计规格全量复审意见.md`（2026-09-14 版）
>
> **后续决定（2026-09-14）：本文 §5 推荐的"两 endpoint（virtuoso + work）"模型已被 SPEC-2026-09-14-r2 否决。最终决定为：保留 5 role（gui/daemon/command/file/spectre），bridge 只忠实投送、不判断 role 间拓扑关系，每个 role 独立配置文件根（全局默认 + 显式覆盖）。当前口径见 [design-concepts/中层/3-路由设计.md](../design-concepts/中层/3-路由设计.md)。**

## 0. 结论先行

1. **多节点的历史动机是真实的，但旧实现从未真正实现"跨机启动 daemon"。** 旧 ADR 与 README 声称支持 GUI/deploy/daemon/Spectre 分机；但 `ipcBeginProcess(command, t_hostName)` 在旧 `ramic_bridge.il` 中**第二参数固定传空串**（本机执行），`VB_DAEMON_HOST` 只是"隧道往哪里连"，不含任何远程启动协议。真正的跨机启动依赖客户站点自己的 Cadence 机制。
2. **旧模型实际上只有 4 个目标角色 + 1 个全局账号**：GUI、deploy、daemon、Spectre；命令与文件**共用 deploy host**；所有角色共用一个 `VB_REMOTE_USER`；没有 per-role user/jump/proxy，没有 endpoint key，没有 role 级指纹（host key 完全委托 known_hosts / SSH config）。
3. **当前五 role（gui/daemon/command/file/spectre）+ 每 role 独立 user/jump/proxy 是本次重构新引入的复杂度**，不是旧实现的延续；其中 gui 与 spectre 在本版**没有任何运行时消费**。
4. **同一个 token 内、五个 role 任意扇出的拓扑，仓库内没有任何真机验证**；已跑通的"多主机"全部是"多个 token/user 各自落在不同机器"。
5. **物理上本版无法拆分 CIW 与 daemon**：daemon 是 CIW 的本地 `ipcBeginProcess` 子进程、只监听 `127.0.0.1`、部署文件必须能被 CIW `load`、CDS.log 与 daemon 同机读取。在补充"远程 launcher + 生命周期协议"之前，规范不能允许 gui/daemon 独立漂移。
6. **推荐收敛为两个逻辑 endpoint**：必需的 `virtuoso`（CIW + daemon + 部署，强制同 host/同 user/同可见路径）+ 可选的 `work`（RunCommand + File；未来 Spectre 作为其命令能力）。跨 token 多主机继续由"每 token 一条 registry 条目"表达。详见 §5。

---

## 1. 多节点是怎么进来的（背景与历史）

### 1.1 引入时间与原始理由

- `e7ae05d`（feat: support split bridge hosts and safe bootstrap）首次引入显式角色，并写了 ADR：
  > "Virtuoso installations can place the GUI, `ipcBeginProcess()` daemon, bridge files, and Spectre on different machines, so the bridge resolves explicit GUI, daemon, deployment, and Spectre hosts rather than treating one SSH target as physical truth."
  （`git show e7ae05d:docs/adr/0001-explicit-remote-host-roles.md`）
- 同期 README/AGENTS 给出的典型拓扑：
  > "Some Cadence environments are genuinely split: the CIW runs on the jump/login host while `ipcBeginProcess()` launches the daemon on a compute host."
  （`AGENTS.md:135-146`，`git show e7ae05d:README.md`）
  示例配置：`VB_GUI_HOST=gui-host-a`、`VB_DEPLOY_HOST=gui-host-a`、`VB_DAEMON_HOST=compute-host-b`、`VB_SPECTRE_HOST=compute-host-b`、共享 `VB_REMOTE_SCRATCH_ROOT`。

### 1.2 真实动机归纳（三条）

| # | 动机 | 现实性 |
|---|---|---|
| 1 | CIW 在登录/GUI 机，重活/仿真在计算节点（Cadence 分布式进程服务器） | 真实存在，但**依赖站点外部机制**把进程放到计算节点 |
| 2 | Spectre 在独立仿真机 | 真实存在；但本版不消费 Spectre |
| 3 | 部署根在共享文件系统（登录节点可见），daemon 读同一份文件 | 真实存在；旧实现只做 `test -r` 可见性检查 |

### 1.3 关键落差点（本次调研最重要的发现）

Cadence 文档：`ipcBeginProcess(command [, t_hostName] [, ...])` 的第二个参数是 network node，空串=本机执行（`C:\Users\user\Desktop\doc\skipcref\ipcskill_re_ipcBeginProcess.html:61-104`）。

旧 `ramic_bridge.il` 调用时**传入空串**（`src_bak`/`e7ae05d` 中的 `ramic_bridge.il:216-233`）。因此：

- 旧 bridge 实际让 **CIW 本机**拉起 Python daemon；
- `VB_DAEMON_HOST` 只影响 Python 侧隧道目标，不会让 daemon 跨机；
- 旧实现**没有** mpshost/mpssession/libSelect 的处理代码（全仓 0 命中）；
- 旧文档把"站点外部机制可能把 daemon 放到 compute 机"描述成了 bridge 的能力，属于**能力夸大**。

结论：旧项目的多节点支持 = "允许声明目标 + 建隧道 + 可见性/主机名诊断"，**不包含远程启动协议**。

---

## 2. 旧实现到底做了什么（代码事实）

### 2.1 角色与环境变量

| 角色 | 环境变量 | 含义 |
|---|---|---|
| legacy | `VB_REMOTE_HOST` | 单主机兼容值，作为所有角色的兜底 |
| GUI | `VB_GUI_HOST` | CIW / X11 所在机 |
| deploy | `VB_DEPLOY_HOST` | 接收生成的 bridge 文件（部署根） |
| daemon | `VB_DAEMON_HOST` | daemon 监听主机 / 隧道目标 |
| Spectre | `VB_SPECTRE_HOST` | 独立 Spectre 任务机 |
| jump | `VB_JUMP_HOST` / `VB_JUMP_USER` | 全局路由，不是业务角色 |
| account | `VB_REMOTE_USER` | **所有角色共用的唯一 SSH 账号** |

证据：`src_bak/virtuoso_bridge/transport/remote_roles.py:18-33,74-93`；`env.py:56-63`。

### 2.2 实际回退链（比文档写的更"乱"）

```
gui     = GUI or legacy or deploy or daemon or spectre
deploy  = deploy or GUI or legacy or daemon or spectre
daemon  = daemon or legacy or deploy or GUI or spectre
spectre = spectre or legacy or daemon or deploy or GUI
```
（`remote_roles.py:74-83`；`tunnel.py:184-189` 还有第二层兜底）

即：任意角色可以互相兜底，没有严格的分层默认。`SSHClient.from_env()` 硬性要求能解析出 daemon + deploy（`tunnel.py:285-292`）。

### 2.3 四个能力分别走哪里

| 能力 | 目标 |
|---|---|
| Skill | 本机隧道 → daemon host（`ssh -L ...:127.0.0.1:port`） |
| RunCommand | deployment runner = **deploy host** |
| File（upload/download） | 同上，**deploy host** |
| X11/窗口 | gui host |
| Spectre | spectre host（可独立工作，不要求 bridge 隧道） |

证据：`tunnel.py:208-215,604-624,836-850`；`cli.py:883-902`；`spectre/runner.py:633-652,680-714`。

> 注意：高层 API 里有直接使用 daemon runner 的旁路（例如 `maestro/reader/snapshot.py:196`），所以"命令/文件统一走 deploy"只对 `SSHClient` 原语成立。

### 2.4 账号 / endpoint / 指纹

- 账号：只有 `VB_REMOTE_USER`；**没有** `VB_GUI_USER` / `VB_DAEMON_USER` / `VB_DEPLOY_USER` / `VB_SPECTRE_USER`。jump user 仅在跳板目标上覆盖。
- endpoint：没有用户级 endpoint key 概念。
- host key：完全委托——
  - OpenSSH 后端继承 `~/.ssh/config` 与 known_hosts，不注入 `StrictHostKeyChecking=no`（`ssh.py:1634-1669`）；
  - Paramiko 后端读取 known_hosts 并使用 `RejectPolicy()`，无 TOFU（`paramiko_backend.py:807-811`）。
- 没有 role 级指纹记录，也没有运行时指纹比对。

### 2.5 旧模型事实清单（10 条）

1. 角色四个：gui / deploy / daemon / spectre（+ legacy 与全局 jump）。
2. 回退链是角色间全互兜底，不是严格分层。
3. Skill → daemon；命令与文件 → deploy；Spectre → spectre host；X11 → gui host。
4. 只有一个 SSH user（全局），不支持 per-role user。
5. jump/proxy 全局，不支持 per-role。
6. 没有 endpoint key、没有 role 级指纹、没有运行时指纹比对。
7. host key 完全委托 known_hosts / SSH config（Paramiko 严格 RejectPolicy）。
8. `ipcBeginProcess` 实传空 hostName → daemon 只在 CIW 本机启动。
9. 跨机可行性依赖站点外部机制 + 共享 deploy root，旧 bridge 只做可见性/主机名诊断。
10. `VirtuosoClient.from_env()` 冷启动路径仍硬依赖 `VB_REMOTE_HOST`，显式角色配置并未在所有入口生效。

---

## 3. 当前 Spec / 实现的状态与矛盾

### 3.1 现状（五 role）

- 五个 role 均含 `host/user/jump_host/jump_user/proxy`；daemon 额外 `daemon_port/local_port`，spectre 额外 `bin`（`add-中层配置文档.md:35-54`）。
- fallback 是**逐字段**的：role 有值用自己的，否则回退对应 `ssh.default.*`；`null`/空串 = 未提供（`add-中层配置文档.md:31,124,159,215,242-245`）。
- 运行时消费：Skill→daemon、RunCommand→command、File→file；gui 与 spectre **只在注册期探测/记录**，无运行时入口（`src/transport/remote_roles.py:66-91`、`flow.py:242-349`、`middle.py:328-394`）。

### 3.2 物理约束 vs 策略选择

| 约束 | 类型 |
|---|---|
| setup/daemon/il 部署在 daemon 主机 `deploy.scratch_root` | 策略（但受下一行约束） |
| 用户必须在 CIW 中 `load` setup → 该路径必须对 CIW 可见 | **物理** |
| daemon 由 CIW 的 `ipcBeginProcess` 本地拉起，无 run-as | **物理**（除非新增远程启动协议） |
| daemon 固定绑 `127.0.0.1`，经 daemon role 隧道访问 | **物理** |
| CDS.log 与 daemon 同主机 | **物理假设**（本版明确不支持 split log） |
| 文件默认根仅在 `file.host == daemon.host` 时 = scratch_root | 策略；且条件写错（应为完整 endpoint） |
| 一个 token = 一个 daemon = 一个 CIW | 物理 + 策略 |

### 3.3 当前 Spec 的 6 个内部冲突（评审已退回）

1. **GUI 可独立于 daemon，但 setup 部署在 daemon 主机、CIW 在 GUI 侧 load、daemon 又是 CIW 的本地子进程** → 无法保证能启动。
2. **文件默认根只比较 host**，而 endpoint 身份包含 user/jump/proxy → 同 host 不同账号时相对路径指错。
3. **Spectre 非阻断与"任一失败→回退第一步"冲突**；首信任规则也没写 Spectre 例外。
4. **`scratch_root` 是基准根还是最终根未定义**（规范默认已含 `<user>`，注册模型默认基准并追加）。
5. **`daemon_port` 规范要求注册分配，持久模型却允许 `None`**，运行时兜底 65432。
6. **CDS.log 假设与 daemon 同机，但 role 模型允许 GUI/daemon 独立**，且实现未校验。

### 3.4 本轮评审的拓扑相关退回项

- **P0-01**：GUI/daemon 拓扑未闭合 → 要求强制解析后 endpoint 一致，或补齐跨机协议（`设计规格全量复审意见.md:78-82`）。
- **P0-02**：文件默认根条件应为**完整 endpoint 相等**或注册时验证可见根（同文件 `:94-98`）。
- **P0-04**：Spectre 例外要写进首信任与"任一必检失败"（同文件 `:133-137`）。
- **P1-04**：endpoint key 还缺 SSH 端口/alias/proxy/jump known_hosts 合同；**P1-07**：无 run-as 时 `gui.user == daemon.user == expected.daemon_user` 必须写明。

---

## 4. 当前核心需求是什么？多节点有必要吗

### 4.1 仓库实际验证过的拓扑

| 拓扑 | 状态 | 证据 |
|---|---|---|
| 单机 remote（六步注册 + CIW load + 三接口 + CDS.log） | **真机跑过** | `doc/report/测试执行报告.md`、`log契约-P1.md` |
| 单机 local（6 用户并发、持久 shell） | **真机跑过** | `test/e2e/test_business_local_live.py` |
| 同一 registry 下"每 token 一台机器"（6 wsl 真实 + 10 vps fake） | **真机跑过** | `test/tb/multienv_mixed.py`、`并发专项-三环境随机混合.md` |
| 跳板网络路径（Windows→云→wsl） | 真实存在，但通过 SSH config 透明实现 | `doc/report/环境支持.md:22-34` |

### 4.2 从未验证的拓扑

GUI≠daemon、deploy≠daemon、command≠file、独立 Spectre、mpsserver 远程启动 daemon、SOCKS5 真机、role 级 jump、split-host CDS.log —— 全部**没有真机证据**，其中多项连 mock 都没有。复核测试计划本身已把 GUI/deploy 分裂与 split-host log 列为不测（`doc/report/复核测试计划.md:125-129`）。

### 4.3 五个"拆分"的逐项判断

| 候选拆分 | 能否拆 | 本版判断 |
|---|---|---|
| CIW 与 daemon | 物理上不能（`ipcBeginProcess` 本地 + 127.0.0.1 + 共享 load 路径），除非新增远程 launcher（L 级） | **强制同机同账号**，跨机列为后续 |
| 部署与 daemon | 没有独立价值：部署必须对 CIW 可见，而 CIW 与 daemon 同机 | **合并** |
| command 与 daemon | 可以（纯 SSH 命令） | 可作为可选 `work` endpoint |
| file 与 command | 物理上可以，但拆开后 upload→run→download 会断链（无跨机复制） | **合并为一个 work endpoint** |
| Spectre | 可以，但本版不消费 | **删除 role**，未来作为 work 上的命令能力 |

### 4.4 结论

- **跨 token 的多主机是必要需求**（多设计服务器并存），已真机验证，保留。
- **同一 token 内扇出五个 role 不是需求**，是上一轮为满足评审"补齐 split-host 合同"而膨胀出来的模型；它带来的全是未验证组合与规范漏洞。
- 最小可用集合是"一个必选的 Virtuoso endpoint + 一个可选的 work endpoint"。

---

## 5. 推荐模型与决策矩阵

### 5.1 推荐：`virtuoso` + 可选 `work`（方案 B）

```
每个 registry 条目（= 一个 token）最多两个逻辑 endpoint：

virtuoso（必需）   CIW + daemon + 部署根；host/user/可见路径三者绑定
                   —— 强制 gui == daemon == deploy，同账号同可见路径
work（可选）       RunCommand + File（相对根仅当 work == virtuoso）
                   缺省 = virtuoso
每个 endpoint 自带：host / user / jump_host / jump_user / proxy（含全局默认）
```

- 多设计服务器：仍然"每台一个 user/token"，不用一个 token 扇出。
- Spectre：本版不设 role；未来作为 `work` 上的命令（RunCommand）调用，不新增节点。
- 跨机 daemon 启动（mpsserver / 外部 launcher）：明确列为**后续版本 L 级**，本版拒绝配置。

### 5.2 决策矩阵

| 方案 | 支持场景 | 实现复杂度 | 测试可验证性 | 送审代价 |
|---|---|---|---|---|
| A 仅单 endpoint | 本机 + 单机 remote + 多 token 多机 | S | 高 | 低，但放弃计算节点上的命令/文件 |
| **B `virtuoso` + `work`** | A + 计算节点上的命令/文件/Spectre 调用 | M | 高（wsl + vps 可构造真机双 endpoint） | 中，能一次闭合全部拓扑 P0 |
| C 当前五 role | 纸面最多 | L/XL | 低（关键组合无真机） | 高（评审持续退回） |

### 5.3 若采用 B，本轮 P0/P1 的关闭路径

| 退回项 | 关闭方式 |
|---|---|
| P0-01 GUI/daemon 拓扑 | 删除 gui role；`virtuoso` endpoint 强制同 host/user/路径 |
| P0-02 文件根条件 | 相对根成立条件 = `work endpoint == virtuoso endpoint`；否则必须绝对路径 |
| P0-03 CommandResult/unknown token | 四字段模型 + 三接口统一 invalid-token 行为（与拓扑无关，照做） |
| P0-04 Spectre 例外 | 删除 spectre role 后自然消失；`work` 上未来的 spectre 调用走普通 RunCommand 语义 |
| P1-04 endpoint key | endpoint 只剩 1~2 个，key 字段固定；明确端口 22、alias 原文、proxy 语法 |
| P1-07 gui/daemon 账号等式 | 由"virtuoso endpoint 同账号"强制 |

---

## 6. 需要决策/确认的点

1. 是否接受**删除 gui role**（CIW 与 daemon 合并为一个 `virtuoso` endpoint）？
2. 是否接受**删除 spectre role**（本版不消费；未来经 work 的 RunCommand 调用）？
3. 是否接受**command 与 file 合并为可选 `work` endpoint**（缺省 = virtuoso）？
4. 跨机启动 daemon（mpsserver 等）确认**不在本版范围**？
5. 若保留 `work`，其相对文件根是否只在 `work == virtuoso` 时成立（否则必须绝对路径）？

---

## 7. 证据索引

- 旧代码：`src_bak/virtuoso_bridge/transport/remote_roles.py:18-33,74-93`；`transport/tunnel.py:184-189,208-215,234-251,285-292,836-850`；`env.py:56-63`；`daemon_guard.py:37-39,93-110`。
- 旧 ADR / README：`git show e7ae05d:docs/adr/0001-explicit-remote-host-roles.md`；`git show e7ae05d:README.md`（split host 段）；`git show e7ae05d:CONTEXT.md`；`AGENTS.md:56-61,135-150,185-202`。
- Cadence 文档：`C:\Users\user\Desktop\doc\skipcref\ipcskill_re_ipcBeginProcess.html:61-104`（hostName 语义）；`spectreref/chap2.html:805-819`（+mpshost/+mpssession 属 Spectre 交互，不是 daemon 启动）。
- 当前规范：`spec/design-concepts/总览/add-中层配置文档.md:35-64,113-130,215-245`；`1-多用户与注册.md:107-117,131,141-147,296`；`1-四层整体架构与接口.md:42,239-253,271,290`；`日志返回设计标准.md:26`；`本版范围与明确不支持.md:16,23`。
- 当前实现：`src/transport/registry.py:53-99`；`remote_roles.py:41-91`；`tunnel.py:81-140,157-247`；`middle.py:328-394`；`register/flow.py:242-349,370-386`。
- 评审意见：`doc/设计规格全量复审意见.md:67-137,143-189,226-244`；`doc/验收审批意见.md`（2026-09-14）。
- 测试证据：`doc/report/测试执行报告.md`、`并发专项-三环境随机混合.md`、`log契约-P1.md`、`复核测试计划.md:125-129`、`doc/测试覆盖报告.md:170-176`。
