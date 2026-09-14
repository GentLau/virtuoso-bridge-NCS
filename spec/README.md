# virtuoso-bridge-NCS Spec

> 版本：Draft v4
> 日期：2026-09-11
> 状态：已冻结（本版验收基线）

## 0. 版本治理（替代“文件修改时间优先”）

本目录不用文件 mtime 判优先级。冲突消解遵循以下确定性规则：

1. **Normative（唯一规范源）**：只有下列文件是正式规范，且每个主题只有一个 owner；
   - 分层/接口/错误总则：[三层整体架构设计](design-concepts/总览/三层整体架构设计.md)（第 4 节为接口唯一基线）
   - 本版范围/非目标：[本版范围与明确不支持](design-concepts/总览/本版范围与明确不支持.md)
   - 配置与注册输入目录：[配置一览](design-concepts/总览/配置一览.md)
   - 多用户/注册/token：[多用户设计](design-concepts/底层与中层/多用户设计.md)
   - 并发/SSH/线程池：[并发处理设计](design-concepts/底层与中层/并发处理设计.md)
   - CDS.log 返回：[日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md)
2. **Informative（只索引/摘要，不定义）**：[核心修改设计](design-concepts/总览/核心修改.md)、[demo](demo/README.md)。
3. **Historical / Non-normative（历史对照，无规范效力）**：[改动报告](design-concepts/总览/改动报告.md)、[代码梳理](design-concepts/底层与中层/代码梳理.md) 及其中的“旧实现/双轨期/迁移阶段”描述；它们不得推翻 Normative。
4. **Research**：[research](research/README.md)，仅作背景知识。
5. 主题冲突时只认其 Normative owner；其余副本若与 owner 不一致，一律以 owner 为准。
6. 版本变更必须记录 `Supersedes`（替换了哪份/哪节）。

## 目标

本项目采用三层架构：

```text
上层（业务封装层）
  └─ 原理图 · 版图 · 测试平台 · Maestro · 库/符号 · 仿真 · 工具适配器

中层（业务服务器运行时）
  └─ Skill · RunCommand · File 三个接口
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
| Normative | [多用户设计](design-concepts/底层与中层/多用户设计.md) | 六步注册、token 寻址/校验、路由与授权 |
| Normative | [并发处理设计](design-concepts/底层与中层/并发处理设计.md) | 并发模型、每 token 预算 + 按 endpoint 复用 SSH、线程池/channel、建连重试 |
| Normative | [日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md) | CDS.log 增量返回唯一口径（offset 定界、分级、限长） |
| Informative | [核心修改设计](design-concepts/总览/核心修改.md) | 五项修改的索引/摘要，不重复定义 |
| Historical | [改动报告](design-concepts/总览/改动报告.md) | 重构前对照与历史迁移，Non-normative |
| Historical | [代码梳理](design-concepts/底层与中层/代码梳理.md) | 旧执行机制梳理，Non-normative |
| Research | [research/README.md](research/README.md) | Virtuoso/TB/日志/并发背景调研 |
| Demo | [demo/README.md](demo/README.md) | 脱钩最小验证（Informative，不复刻正式口径） |

## 冻结 Manifest

| 文档 | 版本 | 状态 | Supersedes |
|---|---|---|---|
| 三层整体架构设计 | Draft v4 | Normative | Draft v3 |
| 本版范围与明确不支持 | v2 | Normative | v1 |
| 配置一览 | Draft v8 | Normative | Draft v7 |
| 多用户设计 | Draft v4 | Normative | Draft v3 |
| 并发处理设计 | Draft v5 | Normative | Draft v4 |
| 日志返回设计标准 | Draft v5 | Normative | Draft v4（废除 marker 定界） |
| 核心修改设计 | Draft v3 | Informative | Draft v2 |
| 改动报告 / 代码梳理 | — | Historical | — |

## 独立 Demo

`demo/` 是与当前实现脱钩的最小参考验证目录，只使用 Python 标准库。其演示口径不构成正式规范；当前 offset 定界的正式规则见[日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md)。

## 本版已经决定的事项

1. 中层对上只承诺三个**操作接口**：`Skill`、`RunCommand`、`File`；`token` 是每次调用的必填关键字参数。
2. 底层 daemon 只处理 `Skill`；shell 命令与文件传输全部由中层执行。
3. 上层不读 `VB_*`/`.env`、不判断 local/SSH、不创建 SSH/socket，也不解析 STX/NAK/RS 协议。
4. 上层使用逻辑 `ServerPath`；实际 host/jump/role/tunnel 由中层按 registry 路由解析。
5. 所有调用采用端到端 deadline；中层子阶段只继承剩余预算。
6. 命令非零退出码是结构化结果；transport 失败、超时、路径不可见、结果未知必须可区分（见三层架构 §4.4 错误总则）。
7. token 是对称共享授权票：部署注入 il/daemon，CIW load 时目视确认；缺失/不匹配一律 NAK 且 SKILL 零接触。
8. 不保留旧项目兼容：`profile`/`VB_*`/`.env` 已删除，双轨期已结束；新用户只走六步注册。

## 本版明确不支持（非目标）

完整清单与“遇到时的行为”唯一口径见[本版范围与明确不支持](design-concepts/总览/本版范围与明确不支持.md)。摘要：

- 不提供 `purpose`/Spectre 业务消费入口、GUI 独立业务入口（gui role 仅记录）、deploy 独立 role；
- 不支持无 token 旧客户端/旧 il、`profile`/`VB_*`/`.env` 迁移、非对称签名；
- 不引入 `request_id`、argv/无 shell 模式、异步 command handle；
- 不支持 split-host CDS.log、全量日志体系、文件安全沙箱。

## 评审重点

后续评审应优先检查：

- 上层能否完全用 fake middle 做单元测试；
- `Skill` 与 `RunCommand` 是否真正分离；
- local/SSH/split-host 是否只影响中层；
- 文件上传是否有原子落盘、校验和和路径可见性保证；
- 同一 Virtuoso CIW 的写操作是否串行；
- `log=off` 是否从 IL 源头不 flush/不读文件、不向 CDS.log 注入任何输出；
- 失败时是否能得到明确的 transport/command/skill/file 证据。
