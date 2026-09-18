# 中层配置文档

> 版本：Draft v31
> 日期：2026-09-15
> 状态：Normative（字段目录、默认值、探测写回、注册表 schema、reservation 与 endpoint key 的唯一规范源）
> Supersedes：Draft v21–v30（v21–v29 同前；v30 server.json→config.json）
> 定位：本文是[多用户与注册](../其他/1-多用户与注册.md)的**字段与 schema 详细补充**——六步状态机与授权归[多用户与注册](../其他/1-多用户与注册.md)；本文是字段与必填清单 owner（§4），并提供默认值、探测写回、注册表 schema、reservation 与 endpoint key。

## 1. 总述

- **唯一 owner**：字段名/类型/默认值、注册表 schema（§6.1）、reservation（§6.4）、endpoint canonical key（§6.5）只在本文定义；其它文档只索引，不复制。
- **配置跟随用户**：本地只有一份 `registry.json`，`user` 为键，每用户一条独立条目；**远端不放注册表**，远端只有该用户的部署文件（`ramic/`、`setup/`、`status/`，见 §6.3）。
- **运行期只读内存快照**：启动时导入一次，运行期不自动读文件、可显式重新导入；生命周期见[多用户与注册 §5](../其他/1-多用户与注册.md)。
- **双层语义**：每次调用携带 `token`（+接口自身参数，见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)）；`cdslog.*` 是每用户持久化配置，由中层填进 daemon 请求（见[日志返回设计标准 §6.1](../底层/6-日志返回设计标准.md)）。
- **类型标注**：每个字段标 `配置 / 环境 / 校验`，处理规则见 §3。
- **默认值约定**：标“默认 X”可省略；标“必填”必须写入。

## 2. 字段总表（唯一来源）

### 2.1 通用

| 字段 | 作用 | 类型 | 默认/必填 |
|---|---|---|---|
| `token` | 每次调用携带的寻址与授权参数；每用户唯一、终生不变（格式见 §5，生命周期见[多用户与注册 §1](../其他/1-多用户与注册.md)） | 配置 | 注册生成（未提交则自动生成） |
| `user` | 人类可读 id + 路径名，非安全凭证 | 配置 | 必填（格式见 §5） |

### 2.2 策略

| 字段 | 作用 | 类型 | 默认/必填 |
|---|---|---|---|
| `ssh.backend` | SSH 后端 openssh / paramiko；默认 paramiko：同一业务连接上多 channel 复用；Skill 隧道由外部 OpenSSH `ssh -N -L` 承载 | 配置 | 默认 `paramiko` |
| `ssh.control_master` | openssh 后端的复用策略 auto/force/disable；复用边界是 token，跨 token 不共享；paramiko 不适用 | 配置 | 默认 `auto` |
| `ssh.tool_override` | 可选 ssh/scp/tar 工具路径覆盖 | 配置 | 可选 |
| `runtime.thread_pool_size` | 线程预算：在途请求上限（任何未完成动作占位）；超限语义见[并发设计 §2](2-并发设计.md) | 配置 | 默认 `32` |
| `runtime.channel_budget` | 最大通道数：token 内所有 endpoint 已打开 SSH 通道总数；超限语义见[并发设计 §2](2-并发设计.md) | 配置 | 默认 `10` |
| `runtime.connect_timeout` | 连接建立超时（各步 deadline 的子预算，见[四层整体架构与接口 §5.8](../总览/1-四层整体架构与接口.md)） | 配置 | 默认 `15` 秒 |
| `cdslog.log_level` | 返回日志级别 off/all/warn/error；off 从 IL 源头不读不注入；业务接口可显式覆盖 | 配置 | 默认 `all` |
| `cdslog.log_max_bytes` | 单次日志内联长度上限，超限自动降级（规则见[日志返回设计标准 §5](../底层/6-日志返回设计标准.md)）；业务接口可显式覆盖 | 配置 | 默认 `65536` |

### 2.3 各 role 公共字段

五个 role（`gui / daemon / command / file / spectre`）各有下列公共字段。role 的职责、接口对应与连接复用见[路由设计 §2–§4](3-路由设计.md)，本文只定义字段与默认值。

| 字段 | 作用 | 类型 | 默认/必填 |
|---|---|---|---|
| `role.<name>.mode` | 投送方式：`local` = 中层就在该 role 目标主机上直接本地执行、不经 SSH；`remote` = 经 SSH 投送；不同 role 可混合 | 配置 | 回退 `mode.default` |
| `role.<name>.host/user/jump_host/jump_user/proxy` | 该 role 登录主机/账号/跳板/代理；`local` role 提交即参数错误 | 配置 | 回退 §2.5 全局默认（remote 需可解析） |
| `role.<name>.root` | 该 role 文件根；申请期缺省 `root.default/<role>`，探测后为最终绝对路径 | 配置 | 可选（探测写回，见 §6.2） |
| `role.<name>.max_sessions` | 该 role 解析到的 endpoint 的并发通道上限（配置在 role、生效在 endpoint；多 role 同 endpoint 取最小值；`local` 不适用） | 配置 | 默认 `10` |
| `role.<name>.expected_fingerprint` | 该 role endpoint 的 host-key 指纹比对基准（业务 role 必检；spectre 例外，见 §3）；`mode=local` 无 endpoint，省略或为 `null` | 校验 | 探测写入 |

### 2.4 role 特有字段

| 字段 | 作用 | 类型 | 默认/必填 |
|---|---|---|---|
| `role.daemon.daemon_port` | daemon 监听端口，每用户分配不冲突 | 配置 | 缺省分配（见 §6.4） |
| `role.daemon.local_port` | `remote` 时是隧道本地端口；`local` 时直连端口，必须 `= daemon_port` | 配置 | 缺省分配 |
| `role.daemon.python` | daemon role 上的 python 解释器（部署/启动 daemon 消费；`local` 时即本机 python） | 环境 | 显式→校验，缺省→探测；失败=注册失败 |
| `role.daemon.expected_hostname` | daemon 主机名比对基准 | 校验 | 探测写入 |
| `role.daemon.expected_user` | daemon 进程账号比对基准 | 校验 | 探测写入 |
| `role.spectre.bin` | spectre 可执行文件（显式→校验，缺省→探测；失败仅 warning） | 环境 | 可选 |

### 2.5 全局默认与字段回退

| 字段 | 作用 | 类型 | 默认/必填 |
|---|---|---|---|
| `mode.default` | 各 role 缺省 mode（local/remote） | 配置 | **必填，无默认** |
| `ssh.default.host/user` | 各 role 缺省登录主机/账号 | 配置 | 存在未在 role 级提供的 remote role 时必填 |
| `ssh.default.jump_host/jump_user/proxy` | 各 role 缺省跳板/代理 | 配置 | 可选 |
| `root.default` | 各 role 文件根的申请期基准；探测后写回各 `role.*.root`，运行期不依赖本字段 | 配置 | 默认 `~/.virtuoso-bridge/<userid>`（持久化 `null`） |

- 回退是**逐字段**的：role 有值用自己的，否则回退对应全局默认；`null`/空串 = 未提供；
- 不支持逐 role 显式“禁用”全局 jump/proxy——需要不同值就显式写该 role 的最终值；
- `root.default` 的完整展开算法（在哪台机器解释 `~`、`<role>` 拼接、探测后回写）见[多用户与注册 §4.2](../其他/1-多用户与注册.md)。

### 2.6 固定目录结构（非配置项）

- 本地工作目录不是注册字段（启动时传入，不传用实现默认）；子结构固定 `registry.json / config.json / temp/ / log/ / artifact/`，启动时自动创建（`config.json` 见[顶层补充 §5](../顶层/add-控制面与业务面.md)）；
- 远端部署目录写死：`role.daemon.root` 下 `ramic/ / setup/ / status/`，部署规则见[多用户与注册 §4.2](../其他/1-多用户与注册.md)。

## 3. 三类处理规则

| 类型 | 规则 |
|---|---|
| 配置 | 用户提供；只做格式/范围/查重校验，失败拒绝；无自动探测 |
| 环境 | 默认自动探测；用户显式提供时校验，不可用报告并拒绝。唯一例外 spectre（失败级别与提交态见[多用户与注册 §4.1](../其他/1-多用户与注册.md)） |
| 校验 | 探测写入各 role 的 `expected_*`，只用于比对、不参与业务；运行期不一致 WARNING。唯一例外：业务 role 的 host-key 指纹不匹配 = ERROR（含机器重装未确认），见[多用户与注册 §3.2/§5](../其他/1-多用户与注册.md) |

探测动作本身（何时探测、逐 role 探测矩阵、失败级别）见[多用户与注册 §4](../其他/1-多用户与注册.md)，本文只定义字段类型规则。`root` 不是探测发现的环境值，而是按 §2.5 与[多用户与注册 §4.2](../其他/1-多用户与注册.md)的默认算法推导、探测期写回绝对路径，其类型为**配置**。

## 4. 必填小结

- 必填：`mode.default`、`user`；
- 条件必填：每个 remote role 必须可解析目标（role 级 `host/user` 或 `ssh.default.*`）；
- `token` 未提交时自动生成；`role.daemon.daemon_port/local_port` 缺省自动分配；
- 其余按 §2 表；探测结果写入内存候选对象，第六步才落盘（见[多用户与注册 §3](../其他/1-多用户与注册.md)）。

## 5. 输入校验与首信任

- `user` 格式 `^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$`；禁止 `/`、`\`、`..`、绝对路径；Windows 大小写不敏感查重；拒绝保留设备名（CON/PRN/AUX/NUL/COM1–9/LPT1–9 及带扩展名）与结尾 `.`/空格；
- `token` 格式 `^[A-Za-z0-9._-]{1,64}$`；碰撞重生成一次；轮换 = 删除用户重新注册；
- `local` role 显式提交 `host/user/jump_host/jump_user/proxy` → 参数错误；
- 未知字段拒绝（`extra=forbid`）；空串视为未提供；
- host-key 首信任优先级：① known_hosts 匹配 → 记录；② 用户显式指纹 → 校验后记录；③ 两者皆无 → 注册失败；spectre 例外（缺失/失败仅 WARNING、指纹留空）；
- registry 持久化 UTF-8、权限 `0600`、tmp + 原子替换。

## 6. 注册表 schema 与关键算法

### 6.1 registry 条目 schema（示例）

```json
{"alice": {
  "token": "a3f9c2…", "mode": {"default": "remote"},
  "ssh": {"default": {"host": "server-a", "user": "ssh-user"}, "backend": "paramiko", "control_master": "auto"},
  "root": {"default": null},
  "roles": {
    "gui":     {"root": "/home/ssh-user/.virtuoso-bridge/alice/gui", "max_sessions": 10,
                "expected_fingerprint": "SHA256:…"},
    "daemon":  {"root": "/home/ssh-user/.virtuoso-bridge/alice/daemon", "max_sessions": 10,
                "daemon_port": 65081, "local_port": 65082, "python": "/usr/bin/python3",
                "expected_fingerprint": "SHA256:…", "expected_hostname": "server-a", "expected_user": "ssh-user"},
    "command": {"root": "/home/ssh-user/.virtuoso-bridge/alice/command", "max_sessions": 10, "expected_fingerprint": "SHA256:…"},
    "file":    {"root": "/home/ssh-user/.virtuoso-bridge/alice/file", "max_sessions": 10, "expected_fingerprint": "SHA256:…"},
    "spectre": {"root": "/home/ssh-user/.virtuoso-bridge/alice/spectre", "max_sessions": 10,
                "bin": "/opt/eda/cadence/SPECTRE241/bin/spectre", "expected_fingerprint": "SHA256:…"}
  },
  "runtime": {"thread_pool_size": 32, "channel_budget": 10, "connect_timeout": 15.0},
  "cdslog": {"log_level": "all", "log_max_bytes": 65536},
  "registered_at": 1726051200
}}
```

- 示例为提交态节选；role 未显式写出的 `mode`/连接字段按 §2.5 回退解析。

### 6.2 提交 schema 与写回口径

- 提交后的 registry：各 `role.*.root` 为**绝对路径**，`root.default` 为 `null`；运行期不推导；
- `role.daemon.python`、各 `expected_*` 为提交字段；
- spectre 探测失败时其 `root`/`expected_fingerprint`/`bin` 提交为 `null`；
- 何时探测、何时写回、唯一写盘点见[多用户与注册 §3/§4](../其他/1-多用户与注册.md)；本节只约定提交后的字段形态；
- `registered_at` 是注册流程生成的时间戳元数据，不属配置。

### 6.3 目录与部署约定（索引）

- bridge 文件只部署到 `role.daemon.root` 的 `ramic/`、`setup/`、`status/`；根算法与部署规则见[多用户与注册 §4](../其他/1-多用户与注册.md)；
- 各 role 根互相独立，无共享/可见性要求（忠实投送原则见[路由设计 §1](3-路由设计.md)）。

### 6.4 端口 reservation（内存候选，唯一口径）

**唯一性作用域**：`token`/`user` 全局；`daemon_port` 同一 daemon 目标主机（`mode=local` 时即本机）；`local_port` 本机。

**联合端口**：`mode=local` 时 `daemon_port` 与 `local_port` 是同一个候选端口——任一缺省由同一值生成并同步写入，显式双值必须相等。

**载体与残留**：候选只存**注册进程内存**，不产生 `registry.reservation` 等临时文件；第六步提交前零落盘，未完成六步即放弃全部候选（零残留）。

**流程**：第二步在内存分配候选（缺省 `local_port` 本机预分配；缺省远端 `daemon_port` 第三步分配并回写）→ 第四步部署前复核端口占用、冲突重分配一次 → 第六步提交前 final re-check → 失败/取消/成功即释放候选。

**并发**：注册为低并发流程，由注册服务进程内协调；不设跨进程租约与宽限回收。

**分配算法**：具体算法与端口范围为实现自由度，合同只要求候选唯一且空闲。

### 6.5 endpoint canonical key

```text
endpoint_key = "v1:" + SHA256(canonical_json)
canonical_json = json.dumps([host, user, jump_host, jump_user, proxy], ensure_ascii=True, separators=(",", ":"))
```

- 规范化：`host/jump_host` strip→小写→去尾点（IPv6 压缩小写去方括号）；`user/jump_user` 只 strip；`proxy` 只 strip；空段 `""`；
- 两条独立规则：① 字符串规范化决定“是否同一 endpoint”（`Server-A`、`server-a.` 同 endpoint，指纹必须一致）；② 不做名称解析（不查 DNS、不把 alias 与真实 hostname 合并）；`~/.ssh/config` 只用于 transport 解析与 22 端口校验，canonical key 只按规范化输入字符串计算；
- 测试向量（必须逐条可测）：

| # | host | user | jump_host | jump_user | proxy | key 尾段（前加 `v1:`） |
|---|---|---|---|---|---|---|
| 1 | `server-a` | `ssh-user` | — | — | — | `8c6325e8a41f89a4c29d81eb66db201c4414d33f87702607d23d43a1baf94b0b` |
| 2 | ` Server-A. ` | `ssh-user` | — | — | — | 与 #1 相同 |
| 3 | `server-a` | `SSH-User` | — | — | — | `40701d25d46c873daea45c841226ee0d6d6939209630d5f57459e55c98c2733b` |
| 4 | `[::1]` | `u` | — | — | — | `0bd185aaa4fa1ce6bd5cbeea0a86f061567a632f3ad6bf6f5a8f36b79556526b` |
| 5 | `server-a` | `u` | `bastion` | `jump-user` | — | `178df3e331df40f8d01408ff226fd22e6be04d8033db187f06bc64a5c3512391` |
| 6 | `server-a` | `u` | — | — | `socks5://Proxy:1080` | `f410f0afc8f618e5230416eb191fa6fcdd5c8313828c2e4c4348eed8cfb33630` |

- 同 key 同 endpoint：共享业务连接与 fingerprint 基准（拓扑见[路由设计 §4](3-路由设计.md)）；不同 key 不共享；key 变更视为新 endpoint，指纹按首信任重建；同 key 多 role 显式 `expected_fingerprint` 不一致 → 注册 ERROR；
- 约束：SSH 端口固定 22（注册期校验目标/jump 解析端口，非 22 拒绝）；proxy 固定 `socks5://host:port`；jump 的 known_hosts 由系统 SSH 配置提供；不接受自定义 known_hosts 路径。