# virtuoso-bridge-NCS Spec

> 版本：Draft v1  
> 日期：2026-09-07
> 状态：提案，作为下一阶段重构的接口基线；实现前允许通过评审修改。
> **版本治理（已定）**：本目录内文档冲突时，以**文件修改时间更晚**的为准；接口基线唯一为《三层整体架构设计》第 4 节；《日志返回设计标准》是其专项扩展；《核心修改设计》只索引设计文档，不重复定义。
> 接口基线：[三层整体架构设计](design-concepts/总览/三层整体架构设计.md) 第 4 节；CDS.log 请求与回包扩展见[日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md)。

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

| 文件 | 内容 |
|---|---|
| [三层整体架构设计](design-concepts/总览/三层整体架构设计.md) | **当前架构与接口基线**：总述、整体结构、层次职责、上层↔中层及中层↔daemon.py 接口 |
| [配置一览](design-concepts/总览/配置一览.md) | 本地/远端全部配置，以及配置跟随用户、`VB_*`/`RB_*` 的迁移映射 |
| [核心修改设计](design-concepts/总览/核心修改.md) | 五项核心修改：并行、token、注册表替换 profile、脱离环境变量、CDSlog 增量返回 |
| [改动报告](design-concepts/总览/改动报告.md) | 中层与底层按五项修改的改动位置、工作量、如何改与实施顺序 |
| [design-concepts/底层与中层/多用户设计.md](design-concepts/底层与中层/多用户设计.md) | Token 寻址与路由：用户注册、注册表、中层按 token 投送、上层无感 |
| [当前底层与中层代码梳理](design-concepts/底层与中层/代码梳理.md) | 现状执行机制、功能清单，以及保留/删除/改造的判定 |
| [日志返回设计标准](design-concepts/底层与中层/日志返回设计标准.md) | CDS.log 增量返回、实现点、分级过滤与限长降级的唯一设计标准 |
| [design-concepts/底层与中层/并发处理设计.md](design-concepts/底层与中层/并发处理设计.md) | 并发模型详解：进程隔离、GIL 与 I/O 等待、单通道串行机制、并发安全纪律 |
| [research/README.md](research/README.md) | Virtuoso 数据模型、TB、日志和重构技术调研 |
| [demo/README.md](demo/README.md) | 新功能独立最小验证：注册 + token 路由 + 并行的完整业务模拟，以及 CDS.log 增量 |
| [demo/TB测试场景验证报告.md](demo/TB测试场景验证报告.md) | 8 个 TB 场景的实测数据与验证结论（复用 `tb_scenario_report.py`） |


## 独立 Demo

`demo/` 是与当前实现脱钩的最小参考验证目录。它只使用 Python 标准库，
不读取 `.env`，不连接 SSH/Virtuoso；运行方式和验收口径见
[demo/README.md](demo/README.md)。截至 **2026-09-09**，`full_demo.py` 收拢
注册多用户、token 到端口路由、同用户串行/并行（`run_command` 用 pwsh 模拟，
`execute_skill` 到达端口即成功），`cdslog_demo.py` 单独验证 CDS.log 增量
算法；8 个 TB 场景的实测数据与验证结论见 [demo/TB测试场景验证报告.md](demo/TB测试场景验证报告.md)。

## 本版已经决定的事项

1. 中层对上只承诺三个**操作接口**：
   - `Skill`：向 Virtuoso CIW 执行 SKILL；
   - `RunCommand`：在业务服务器的命令环境执行命令行；
   - `File`：在上层所在机器与业务服务器之间传输/管理文件。
2. 底层 daemon 只处理 `Skill`；普通 shell 命令、Spectre、`spiceIn`、`strmOut` 等命令行工具都由中层的 `RunCommand` 执行。
3. 上层不读取 `VB_*`、不判断 local/SSH、不创建 SSH/Paramiko/subprocess/socket，也不解析底层 STX/NAK/RS 协议。
4. 上层使用逻辑 `ServerPath` 表示业务服务器路径；实际 host、jump、role、tunnel 和共享目录由中层解析。
5. 所有调用采用端到端 deadline；中层不得在内部阶段重新开始完整 timeout。
6. 普通命令的非零退出码是结构化结果，不是传输异常；传输异常、超时和路径不可见必须可区分。
7. runtime 在创建时可以选择逻辑 `purpose`（例如 `business`/`spectre`），由中层映射到角色主机；每次业务调用仍不接触物理 host。
8. 现有 `VirtuosoResult`、`SSHRunner`、`SSHClient`、`ramic_bridge.il` 等实现先通过适配层迁移，暂不要求一次性删除兼容 API。

## 本版尚未决定的事项

- v1 的 `RunCommand` 保持 shell 字符串接口；argv/无 shell 模式作为 v2 扩展。
- v1 先提供同步 `run_command`；长任务通过上层生成 marker/log 后轮询，专用异步 command handle 作为后续扩展。
- 第一个完整 Spectre 垂直切片需要确认 `RuntimePurpose` 的最小枚举和路径共享规则；新增 purpose 仍不能暴露物理 host。
- 是否引入正式认证/签名协议，取决于 daemon 是否需要脱离 SSH tunnel 使用。

## 评审重点

后续评审应优先检查：

- 上层是否能够完全用 fake middle 做单元测试；
- `Skill` 与 `RunCommand` 是否真正分离，是否存在把 `csh/system` 偷渡进底层的路径；
- local/SSH/split-host 是否只影响中层；
- 文件上传是否有原子落盘、校验和和路径可见性保证；
- 同一 Virtuoso CIW 的写操作是否串行；
- 失败时是否能得到明确的 transport/command/skill/file 证据。
