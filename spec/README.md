# virtuoso-bridge-NCS Spec

> 版本：Release `SPEC-2026-09-14-r2`（送审修订版）
> 日期：2026-09-14
> 状态：Normative 基线（取代 r1）
> Supersedes：`SPEC-2026-09-14-r1`（五接口口径收口、token↔主机边界、root 唯一算法、注册失败合同、预算与 deadline 矩阵、reservation 跨平台模型、去重索引化）

## 0. 版本治理（替代“文件修改时间优先”）

本目录不用文件 mtime 判优先级。冲突消解遵循以下确定性规则：

1. **Normative（唯一规范源）**：只有下列文件是正式规范，且每个主题只有一个 owner；
   - 分层/接口/错误总则：[三层整体架构设计](design-concepts/总览/三层整体架构设计.md)（第 4 节为接口唯一基线）
   - 本版范围/非目标：[本版范围与明确不支持](design-concepts/总览/本版范围与明确不支持.md)
   - 配置与注册输入目录：[配置一览](design-concepts/总览/配置一览.md)
   - 多用户/注册/token：[多用户设计](design-concepts/底层与中层/多用户设计.md)
   - 多节点/5 role 拓扑：[多节点设计](design-concepts/底层与中层/多节点设计.md)
   - 并发/SSH/线程池：[并发处理设计](design-concepts/底层与中层/并发处理设计.md)
   - CDS.log 返回：[日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md)
2. **Informative（只索引/摘要，不定义）**：[核心修改设计](design-concepts/总览/核心修改.md)、[demo](demo/README.md)。
3. **Historical / Non-normative（历史对照，无规范效力）**：[改动报告](design-concepts/总览/改动报告.md)、[代码梳理](design-concepts/底层与中层/代码梳理.md) 及其中的“旧实现/双轨期/迁移阶段”描述；它们不得推翻 Normative。
4. **Research**：[research](research/README.md)，仅作背景知识。
5. 主题冲突时只认其 Normative owner；其余副本若与 owner 不一致，一律以 owner 为准。
6. 版本变更必须记录 `Supersedes`（替换了哪份/哪节）。
7. **非 owner 不得复制完整定义**：只有一句摘要 + 链接；完整算法/枚举/状态机/矩阵只允许出现在唯一 owner 中（见下节 owner 表）。

## 目标

本项目采用三层架构：

```text
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
| Normative | [三层整体架构设计](design-concepts/总览/三层整体架构设计.md) | 分层、职责、接口唯一基线、错误总则 |
| Normative | [本版范围与明确不支持](design-concepts/总览/本版范围与明确不支持.md) | 本版不做什么的唯一口径（含遇到时的行为） |
| Normative | [配置一览](design-concepts/总览/配置一览.md) | 全部配置 + 注册可提交参数目录 + 每用户隔离 |
| Normative | [多节点设计](design-concepts/底层与中层/多节点设计.md) | 5 role 拓扑与职责、五接口与 role 的对应、逐 role 探测、部署与 endpoint |
| Normative | [多用户设计](design-concepts/底层与中层/多用户设计.md) | 六步注册、token 寻址/校验、路由与授权 |
| Normative | [并发处理设计](design-concepts/底层与中层/并发处理设计.md) | 并发模型、每 token 预算 + 按 endpoint 复用 SSH、线程池/channel、建连重试 |
| Normative | [日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md) | CDS.log 增量返回唯一口径（offset 定界、分级、限长） |
| Informative | [核心修改设计](design-concepts/总览/核心修改.md) | 五项修改的索引/摘要，不重复定义 |
| Historical | [改动报告](design-concepts/总览/改动报告.md) | 重构前对照与历史迁移，Non-normative |
| Historical | [代码梳理](design-concepts/底层与中层/代码梳理.md) | 旧执行机制梳理，Non-normative |
| Research | [research/README.md](research/README.md) | Virtuoso/TB/日志/并发背景调研 |
| Demo | [demo/README.md](demo/README.md) | 脱钩最小验证（Informative，不复刻正式口径） |

## 主题 owner 表（唯一定义处）

| 主题 | 唯一 owner | 其它文档允许出现的形态 |
|---|---|---|
| 五接口签名、返回与错误总则（含 `kind` 枚举、保留码） | [三层整体架构设计](design-concepts/总览/三层整体架构设计.md) §4 | 一句摘要 + 链接 |
| 五接口 ↔ role 映射、role 职责、token↔主机边界、per-role 根算法 | [多节点设计](design-concepts/底层与中层/多节点设计.md) | 一句摘要 + 链接 |
| 字段与默认值、per-role mode/字段回退、endpoint canonical key、reservation | [配置一览](design-concepts/总览/配置一览.md) | 一句摘要 + 链接 |
| 六步注册状态机、探测/部署/连通性合同、注册 deadline、token 生命周期 | [多用户设计](design-concepts/底层与中层/多用户设计.md) | 一句摘要 + 链接 |
| 并发形态、线程池/channel 记账矩阵、SSH 连接生命周期、建连重试 | [并发处理设计](design-concepts/底层与中层/并发处理设计.md) | 一句摘要 + 链接 |
| CDS.log offset/frame/分级/限长/warning | [日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md) | 一句摘要 + 链接 |
| 本版不做什么（非目标清单与遇到时的行为） | [本版范围与明确不支持](design-concepts/总览/本版范围与明确不支持.md) | 一句摘要 + 链接 |

**Spec CI 检查词表**（出现在非 owner 文档的正文中即视为违规；标题/索引行/示例标注除外）：

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

- **Release ID**：`SPEC-2026-09-14-r2`
- **Normative 文件集**（7 份）：三层整体架构设计、本版范围与明确不支持、配置一览、多节点设计、多用户设计、并发处理设计、日志返回设计标准；
- **Normative 内容哈希**：`1f8bab90690252879d40ddd04c5315ce16d1e90e53a65b2bb2364fde77f39573`
  - 算法：按相对路径排序，逐文件 SHA-256（**按 Git 提交内容计算，即 LF 行尾**；Windows 工作区受 `core.autocrlf` 影响的行尾差异不计入）的 `"<相对路径> <hex>"` 行以 LF 拼接，再取一次 SHA-256；
- **基线 commit**：本 Release 段所在提交即基线（见 `git log -1 -- spec/`）；任何 Normative 文档变更必须同时更新本段哈希。

## 冻结 Manifest

| 文档 | 版本 | 状态 | Supersedes |
|---|---|---|---|
| 三层整体架构设计 | Draft v9 | Normative | Draft v8（五接口口径收口：五数据流、五接口 deadline 表、去重复定义） |
| 多节点设计 | v7 | Normative | v6（token↔主机边界、根算法唯一化） |
| 本版范围与明确不支持 | v5 | Normative | v4（新增跨机 daemon 启动非目标） |
| 配置一览 | Draft v16 | Normative | Draft v15（reservation 跨平台模型与唯一性作用域、root 定义索引化） |
| 多用户设计 | Draft v12 | Normative | Draft v11（六步预测目标/失败合同、注册 deadline、resolver 复用口径） |
| 并发处理设计 | Draft v10 | Normative | Draft v9（channel 记账矩阵、local role 预算口径） |
| 日志返回设计标准 | Draft v7 | Normative | Draft v6（split-host 边界索引） |
| 核心修改设计 | Draft v4 | Informative | Draft v3 |
| 改动报告 / 代码梳理 | — | Historical | — |

> 版本链规则：每份文档的文件头 `版本 / 日期 / Supersedes` 必须与本表一致；版本号只递增，跳号必须在 `Supersedes` 中说明合并了哪些版本。

## 独立 Demo

`demo/` 是与当前实现脱钩的最小参考验证目录，只使用 Python 标准库。其演示口径不构成正式规范；当前 offset 定界的正式规则见[日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md)。

## 本版已经决定的事项

1. 中层对上只承诺五个**操作接口**：`Skill`、`RunCommand`、`File`、`GUI 命令`、`Spectre 命令`；`token` 是每次调用的必填关键字参数。
2. 底层 daemon 只处理 `Skill`；命令、文件、GUI 命令、Spectre 命令全部由中层执行。
3. 上层不读 `VB_*`/`.env`、不判断 local/SSH、不创建 SSH/socket，也不解析 STX/NAK/RS 协议。
4. 上层使用逻辑 `ServerPath`；实际 host/jump/role/tunnel 由中层按 registry 路由解析。
5. 所有调用采用端到端 deadline；中层子阶段只继承剩余预算。
6. 命令非零退出码是结构化结果；transport 失败、超时、路径不可见、结果未知必须可区分（见三层架构 §4.4 错误总则）。
7. token 是对称共享授权票：部署注入 il/daemon，CIW load 时目视确认；缺失/不匹配一律 NAK 且 SKILL 零接触。
8. 不保留旧项目兼容：`profile`/`VB_*`/`.env` 已删除，双轨期已结束；新用户只走六步注册。

## 本版明确不支持（非目标）

完整清单与“遇到时的行为”唯一口径见[本版范围与明确不支持](design-concepts/总览/本版范围与明确不支持.md)。摘要：

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
