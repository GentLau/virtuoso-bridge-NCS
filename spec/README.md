# virtuoso-bridge-NCS Spec

> 版本：Release `SPEC-2026-09-16-r3`（送审修订版）
> 日期：2026-09-16
> 状态：Normative 基线（取代 r2）
> Supersedes：`SPEC-2026-09-14-r2`（按 2026-09-15/16 两轮复审意见收口：hash/checker 治理对齐、max_sessions 按 endpoint、Skill 超时合同、探测矩阵按 role mode 条件化、reservation 内存化、新增 Informative 整体流程示例）

## 0. 版本治理（替代“文件修改时间优先”）

本目录不用文件 mtime 判优先级。冲突消解遵循以下确定性规则：

1. **Normative（唯一规范源）**：只有下列文件是正式规范，且每个主题只有一个 owner；
   - 分层/接口/错误总则：[四层整体架构与接口](design-concepts/总览/1-四层整体架构与接口.md)（第 4 节为接口唯一基线）
   - 本版范围/非目标：[本版范围与明确不支持](design-concepts/总览/add-本版范围与明确不支持.md)
   - 配置与注册输入目录：[中层配置文档](design-concepts/中层/add-中层配置文档.md)
   - 多用户/注册/token：[多用户与注册](design-concepts/中层/1-多用户与注册.md)
   - 多节点/5 role 拓扑：[路由设计](design-concepts/中层/3-路由设计.md)
   - 并发/SSH/线程池：[并发设计](design-concepts/中层/2-并发设计.md)
   - CDS.log 返回：[日志返回设计标准](design-concepts/底层/6-日志返回设计标准.md)
   - 顶层入口与业务调度：[顶层：HTTP 入口与业务调度](design-concepts/顶层/1-顶层.md)
   - 上层业务包与插件化：[上层：业务包与插件化](design-concepts/上层/1-上层.md)
2. **Informative（只索引/摘要，不定义）**：[整体流程示例](design-concepts/总览/2-整体流程示例.md)、[demo](demo/README.md)。
3. **Research**：[research](research/README.md)，仅作背景知识。
4. 主题冲突时只认其 Normative owner；其余副本若与 owner 不一致，一律以 owner 为准。
5. 版本变更必须记录 `Supersedes`（替换了哪份/哪节）。
6. **非 owner 不得复制完整定义**：只有一句摘要 + 链接；完整算法/枚举/状态机/矩阵只允许出现在唯一 owner 中（见下节 owner 表）。

## 目标

本项目采用四层架构：

```text
顶层（HTTPServer：API 入口）
  └─ 接收请求 · 每任务一线程（未来可限流）

上层（业务封装层）
  └─ 原理图 · 版图 · 测试平台 · Maestro · 库/符号 · 仿真 · 工具适配器

中层（业务服务器运行时）
  └─ Skill · 命令 · 文件 · GUI 命令 · Spectre 命令（5 接口）
     隐藏本地/SSH、隧道、主机和文件传输细节

底层（Virtuoso 常驻守护进程）
  └─ 连接端口与 Virtuoso，只执行 SKILL
     不承担普通命令行和文件传输
```

上层只依赖中层契约，不依赖物理主机位置。中层把“业务服务器”作为逻辑执行环境：本地模式下业务服务器可能就是当前机器，SSH 模式下是远端机器，分裂部署下则由中层内部映射到多个角色主机。

## 文档

| 类别 | 文件 | 内容 |
|---|---|---|
| Normative | [四层整体架构与接口](design-concepts/总览/1-四层整体架构与接口.md) | 分层、职责、接口唯一基线、错误总则 |
| Normative | [本版范围与明确不支持](design-concepts/总览/add-本版范围与明确不支持.md) | 本版不做什么的唯一口径（每项含本版口径） |
| Normative | [中层配置文档](design-concepts/中层/add-中层配置文档.md) | 字段目录唯一 owner（字段/默认值/探测写回/注册表 schema）+ reservation + endpoint key |
| Normative | [路由设计](design-concepts/中层/3-路由设计.md) | 5 role 拓扑与职责、五业务接口与 role 的对应、token↔主机边界、endpoint 与连接复用 |
| Normative | [多用户与注册](design-concepts/中层/1-多用户与注册.md) | 六步注册、token 寻址/校验、路由与授权 |
| Normative | [并发设计](design-concepts/中层/2-并发设计.md) | 并发与限流唯一口径：排队投递/直接开通道、三预算（线程/最大通道数/单目标点上限）、建连重试 |
| Normative | [日志返回设计标准](design-concepts/底层/6-日志返回设计标准.md) | CDS.log 增量返回唯一口径（offset 定界、分级、限长） |
| Normative | [顶层：HTTP 入口与业务调度](design-concepts/顶层/1-顶层.md) | 顶层职责、插件注册表、业务调度、响应壳与错误分界 |
| Normative | [上层：业务包与插件化](design-concepts/上层/1-上层.md) | 业务包形态、注册、禁止事项、开发规范与检查清单 |
| Research | [research/README.md](research/README.md) | Virtuoso/TB/日志/并发背景调研 |
| Informative | [整体流程示例](design-concepts/总览/2-整体流程示例.md) | 一次请求从顶层到中层再到返回的完整流程示例（不定义机制） |
| Demo | [demo/README.md](demo/README.md) | 脱钩最小验证（Informative，不复刻正式口径） |

## 主题 owner 表（唯一定义处，兼作冲突矩阵）

下表即**冲突矩阵**：每行机制的唯一 owner 与索引位置；非 owner 位置出现完整定义即违反（由 `tools/check_spec.py` 的 owner 规则检查）。

| 主题 | 唯一 owner | 其它文档允许出现的形态 |
|---|---|---|
| 五业务接口签名、返回与错误总则（含 `kind` 枚举、保留码、`query` 查询） | [四层整体架构与接口](design-concepts/总览/1-四层整体架构与接口.md) §4 | 一句摘要 + 链接 |
| 五接口 ↔ role 映射、role 职责、token↔主机边界、连接数量与复用拓扑 | [路由设计](design-concepts/中层/3-路由设计.md) §2.1–§4 | 一句摘要 + 链接 |
| 逐 role 探测流程（何时探测、失败级别、何时提交）与部署/根算法 | [多用户与注册](design-concepts/中层/1-多用户与注册.md) §4 | 一句摘要 + 链接 |
| 字段格式、默认值、候选/提交 schema、写回字段形态、endpoint key、reservation | [中层配置文档](design-concepts/中层/add-中层配置文档.md) | 一句摘要 + 链接 |
| 六步注册状态机、注册 deadline、token 生命周期 | [多用户与注册](design-concepts/中层/1-多用户与注册.md) | 一句摘要 + 链接 |
| 并发形态与排队语义、三预算与通道记账矩阵、连接生命周期、建连重试 | [并发设计](design-concepts/中层/2-并发设计.md) | 一句摘要 + 链接 |
| CDS.log offset/frame/分级/限长/warning | [日志返回设计标准](design-concepts/底层/6-日志返回设计标准.md) | 一句摘要 + 链接 |
| 顶层 HTTP 入口、业务调度与响应壳 | [顶层：HTTP 入口与业务调度](design-concepts/顶层/1-顶层.md) | 一句摘要 + 链接 |
| 业务包形态、插件注册、上层开发规范 | [上层：业务包与插件化](design-concepts/上层/1-上层.md) | 一句摘要 + 链接 |
| 本版不做什么（非目标清单与遇到时的行为） | [本版范围与明确不支持](design-concepts/总览/add-本版范围与明确不支持.md) | 一句摘要 + 链接 |

**Spec CI 检查词表**（只适用于 Normative 设计文档；Informative/Research/Historical/Demo 不适用；标题/索引行/示例标注除外）：

```text
三接口 / 三端口 / 三条数据流（子集示例标注除外）
endpoint_key = ……（完整算法）
root.default/<role> 的完整回退算法
channel 记账完整表
CommandResult.kind 完整枚举
CDS.log metadata frame 完整字节格式
六步注册完整状态机
```

## Release（本基线）

- **Release ID**：`SPEC-2026-09-16-r3`
- **Normative 文件集**（9 份）：四层整体架构与接口、本版范围与明确不支持、中层配置文档、路由设计、多用户与注册、并发设计、日志返回设计标准、顶层：HTTP 入口与业务调度、上层：业务包与插件化；
- **Normative 内容哈希**：`0bcc83270b94be155ee7590056f6225deebb1fb1c80667843e2add27f0fc45df`
  - 算法：路径为**相对 `spec/` 目录**并按路径排序；逐文件 SHA-256（**按 Git 提交内容计算，即 LF 行尾**；Windows 工作区受 `core.autocrlf` 影响的行尾差异不计入）；每行 `<相对路径> <hex>` 以 LF 拼接（**行间分隔、末行无尾 LF**），再取一次 SHA-256；
- **基线 commit**：本 Release 段所在提交即基线（见 `git log -1 -- spec/`）；任何 Normative 文档变更必须同时更新本段哈希。

## 冻结 Manifest

| 文档 | 版本 | 状态 | Supersedes |
|---|---|---|---|
| 四层整体架构与接口 | Draft v21 | Normative | Draft v20（查询改名 query、范围 root/bin；业务接口计数口径统一） |
| 路由设计 | v16 | Normative | v15（业务接口计数口径：5 业务接口 + 只读查询 query） |
| 本版范围与明确不支持 | v9 | Normative | v8（业务接口计数口径：5 业务接口 + 只读查询 query） |
| 中层配置文档 | Draft v27 | Normative | Draft v21–v26（合并说明见文件头 Supersedes） |
| 多用户与注册 | Draft v20 | Normative | Draft v19（reservation 分配/复核/释放细节改为索引 §6.4） |
| 并发设计 | Draft v19 | Normative | Draft v18（只读查询 query 不占三类预算、不进队列） |
| 顶层 | Draft v5 | Normative | Draft v4（五接口口径改五业务接口，另有只读查询 query） |
| 上层 | Draft v5 | Normative | Draft v4（只读查询命名为 query，范围 root/bin；五接口口径改五业务接口） |
| 日志返回设计标准 | Draft v12 | Normative | Draft v11（等待队列留在中层投递前） |

> 版本链规则：每份文档的文件头 `版本 / 日期 / Supersedes` 必须与本表一致；版本号只递增，跳号必须在 `Supersedes` 中说明合并了哪些版本。

## 独立 Demo

`demo/` 是与当前实现脱钩的最小参考验证目录，只使用 Python 标准库。其演示口径不构成正式规范；当前 offset 定界的正式规则见[日志返回设计标准](design-concepts/底层/6-日志返回设计标准.md)。

## 本版已经决定的事项

1. 中层对上承诺五个**业务操作接口**（`Skill`、`RunCommand`、`File`、`GUI 命令`、`Spectre 命令`）与一个只读查询 `query`（见[四层架构 §4.2](design-concepts/总览/1-四层整体架构与接口.md)）；`token` 是每次调用的必填关键字参数。
2. 底层 daemon 只处理 `Skill`；命令、文件、GUI 命令、Spectre 命令全部由中层执行。
3. 上层不读 `VB_*`/`.env`、不判断 local/SSH、不创建 SSH/socket，也不解析 STX/NAK/RS 协议。
4. 上层使用逻辑 `ServerPath`；实际 host/jump/role/tunnel 由中层按 registry 路由解析。
5. 所有调用采用端到端 deadline；中层子阶段只继承剩余预算。
6. 命令非零退出码是结构化结果；transport 失败、超时、路径不可见、结果未知必须可区分（见四层架构 §4.4 错误总则）。
7. token 是对称共享授权票：部署注入 il/daemon，CIW load 时目视确认；缺失/不匹配一律 NAK 且 SKILL 零接触。
8. 不保留旧项目兼容：`profile`/`VB_*`/`.env` 已删除，双轨期已结束；新用户只走六步注册。

## 本版明确不支持（非目标）

完整清单与本版口径的唯一定义见[本版范围与明确不支持](design-concepts/总览/add-本版范围与明确不支持.md)。摘要：

- 不提供 `purpose`、Spectre 高层业务封装（只提供 Spectre 命令执行接口）、GUI 图形化业务封装（只提供 GUI 命令执行接口）、deploy 独立 role；
- 不支持无 token 旧客户端/旧 il、`profile`/`VB_*`/`.env` 迁移、非对称签名；
- 不引入 `request_id`、argv/无 shell 模式、异步 command handle；
- 不支持 split-host CDS.log、全量日志体系、文件安全沙箱。

## 评审重点

后续评审应优先检查：

- 上层能否完全用 fake middle 做单元测试；
- 五个接口（Skill / 命令 / 文件 / GUI 命令 / Spectre 命令）是否各自路由到对应 role；
- local/SSH/split-host 是否只影响中层；
- 文件上传是否有原子落盘、校验和和路径可见性保证；
- 同一 Virtuoso CIW 的写操作是否串行；
- `log=off` 是否从 IL 源头不 flush/不读文件、不向 CDS.log 注入任何输出；
- 失败时是否能得到明确的 transport/command/skill/file 证据。
