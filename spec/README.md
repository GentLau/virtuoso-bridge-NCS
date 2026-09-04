# virtuoso-bridge-NCS Spec

> 版本：Draft v1  
> 日期：2026-09-04  
> 状态：提案，作为下一阶段重构的接口基线；实现前允许通过评审修改。
> 接口正文：[protocol-v1.md](protocol-v1.md)。

## 目标

本项目采用三层架构：

```text
上层（Domain / Product）
  └─ schematic / layout / maestro / library / symbol / spectre / CLI adapters

中层（Business Server Runtime）
  └─ Skill · RunCommand · File 三个对上接口
     隐藏 local / SSH / split-host / tunnel / transfer 细节

底层（Virtuoso Resident Daemon）
  └─ 只在 Virtuoso 内执行 SKILL
     不承担普通命令行和文件传输
```

上层只依赖中层契约，不依赖物理主机位置。中层把“业务服务器”作为逻辑执行环境：本地模式下业务服务器可能就是当前机器，SSH 模式下是远端机器，分裂部署下则由中层内部映射到多个角色主机。

## 文档

| 文件 | 内容 |
|---|---|
| [v1-architecture.md](v1-architecture.md) | 层次职责、依赖边界、运行模式、数据流、状态机、迁移映射 |
| [protocol-v1.md](protocol-v1.md) | **当前唯一接口协议基线**：上层↔中层、中层↔daemon.py、daemon.py↔SKILL 的格式 |
| [v1-interface-contracts.md](v1-interface-contracts.md) | 旧文件名兼容入口；正文已收敛到 `protocol-v1.md` |
| [design-concepts/底层与中层/多用户设计.md](design-concepts/底层与中层/多用户设计.md) | Token 寻址与路由：用户注册、注册表、中层按 token 投送、上层无感 |
| [design-concepts/底层与中层/并发处理设计.md](design-concepts/底层与中层/并发处理设计.md) | 并发模型详解：进程隔离、GIL 与 I/O 等待、单通道串行机制、并发安全纪律 |
| [research/README.md](research/README.md) | Virtuoso 数据模型、TB、日志和重构技术调研 |

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
