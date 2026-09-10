# Virtuoso 底层调研索引

> 调研日期：2026-09-04（Asia/Shanghai）  
> 项目：`virtuoso-bridge-NCS`  
> 关联规范：[spec/design-concepts/总览/三层整体架构设计.md](../design-concepts/总览/三层整体架构设计.md)、[spec/protocol-v1.md](../protocol-v1.md)
> 范围：Virtuoso/DFII/OpenAccess 数据模型、原理图与 testbench 编辑、Maestro/ADE/Spectre 日志，以及本项目重构的关键技术点。

## 结论先行

1. **Virtuoso 不是“目录里的一堆可独立编辑文本文件”**。它以 DFII 统一数据库对象模型管理设计；当前现场通过 `dbGetDatabaseType()` 验证为 `OpenAccess`。库/Cell/View 是寻址层，`sch.oa`、`layout.oa`、`symbol.oa` 等 OA master/co-master 数据是逻辑/物理设计语义的主要载体，`master.tag`、`data.dm` 和锁等 sidecar 也参与解析与一致性。对 OA 二进制直接做文本替换是高风险且不支持的做法。
2. **原理图编辑应采用“结构化意图 → SKILL/DFII 操作 → schCheck/dbSave → 读回验证”**。新建与增量修改必须明确区分；连接优先通过 terminal-aware 操作或命名网络 stub，而不是猜坐标；PDK 器件参数必须走 CDF 语义。
3. **testbench 是多平面数据，不是一个对象**：DUT schematic、config/`expand.cfg`（层次绑定）、Maestro 的 `maestro.sdb`/`active.state`（仿真设置）、以及按 history 组织的结果树彼此关联但不能混为一谈。配置读写可用后台 session；本项目 bridge 要求可靠运行/观察时使用 GUI session。还要区分“Maestro GUI 的 read-only run”（可在部分版本生成 `.RO` history）与“无 GUI 的 `maeOpenSetup` background session”，不能把二者都称为只读。
4. **Virtuoso 没有唯一的“总日志”**。最可靠的取证方式是按问题组合日志：`*.msg.db`（结构化事件）+ per-point `psf/spectre.out`（模拟器根因）+ `Job*.log`/`virtuoso_ade_debug.log`（调度时序）+ `<history>.log`（人类摘要）；`CDS.log`主要用于 Virtuoso 进程级问题和崩溃取证。
5. **重构的核心不是再包一层 SKILL 字符串，而是建立能力探测、会话/锁状态机、路径/主机解析、异步运行观察器、工件清单与可复现性边界**。

## 文档导航

| 文档 | 覆盖内容 | 对应任务 |
|---|---|---|
| [00-research-method-and-evidence.md](00-research-method-and-evidence.md) | 调研方法、现场只读探针和证据记录 | 全部 |
| [01-virtuoso-data-model-and-editing.md](01-virtuoso-data-model-and-editing.md) | 数据层次、OA/DFII、锁、版本管理、原理图和 TB 编辑方法 | 任务 1 |
| [02-virtuoso-logging-and-observability.md](02-virtuoso-logging-and-observability.md) | 日志分类、路径解析、实时采集、最佳取证策略 | 任务 2 |
| [05-cdslog-incremental-read-options.md](05-cdslog-incremental-read-options.md) | CDS.log 增量：API 调研结论与三个简单实时跟随方案 | 任务 2 |
| [04-log-return-system-proposal.md](04-log-return-system-proposal.md) | 日志返回体系：同步 SKILL 捕获、异步 run observer、事件/工件协议 | 任务 2 + 重构落地 |
| [03-rebuild-key-technical-points.md](03-rebuild-key-technical-points.md) | 重构架构、关键风险、接口草案、测试与实施路线 | 任务 3 |
| [three-interface-report.md](three-interface-report.md) | 已存在的 CLI/MCP/Harness 单注册表研究，不属于本次改写范围 | 相关基础设施 |

## 证据等级与来源

- **Cadence 本地安装文档（最高优先级）**：桌面数据源 `C:\Users\user\Desktop\doc`，通过项目内 `tools/skill_doc_server.py`（`http://127.0.0.1:8123/`）查询。当前服务统计显示已加载 **9503** 个函数条目。
- **项目内参考与实现**：`skills/virtuoso/references/`、`skills/spectre/`、`README.md`、`AGENTS.md`、`docs/adr/`、`examples/`、`tests/`。旧实现当前保存在工作树的 `src_bak/`，原 `src/` 多数文件存在预先的删除变更；本次调研没有恢复、删除或改写这些源码。
- **现场只读验证**：通过 `tools/skill_exec.py` 连接已有桥接端口，验证到 IC6.1.8/OpenAccess，并读取现有库、Maestro 目录、日志和 SQLite schema。现场读取不修改设计数据。
- **外部资料边界**：本次结论不依赖公开网页的版本猜测；涉及具体 API、文件布局和行为时，以本机安装的 IC6.1.8 文档、项目参考和现场验证为准。

## 可复现的只读检查

```powershell
# 本地函数文档服务（已有服务时无需重复启动）
python tools/skill_doc_server.py --doc C:\Users\user\Desktop\doc --host 127.0.0.1 --port 8123

# 运行时只读探针；不要把任意写操作放进探针
python tools/skill_exec.py 'getVersion()' --port 65082
python tools/skill_exec.py 'dbGetDatabaseType()' --port 65082
python tools/skill_exec.py 'maeGetSessions()' --port 65082
```

## 建议的下一步

1. 先恢复/固定一个可运行的最小包边界（transport、basic bridge、models），再以只读 introspection 作为第一条重构垂直切片。
2. 把本目录中的“数据所有权表”和“日志取证算法”转成测试 fixture 与契约测试；不要先追求覆盖所有 Cadence 版本。
3. 以一个全新的临时 library/cell 为唯一写入目标，完成 schematic create/modify、Maestro setup、run observer、artifact manifest 的端到端验收后，再接入真实项目库。

## 外部交叉参考

- [Cadence Virtuosity：Virtuoso Read Mode Done Right](https://community.cadence.com/cadence_blogs_8/b/cic/posts/virtuosity-read-mode-done-right)：用于交叉理解 read-mode 的只读/内存修改边界；具体行为仍以本机 IC6.1.8 文档为准。
- [上游开源项目（README 中引用）](https://github.com/Arcadia-1/virtuoso-bridge-lite)：用于对照原项目的 bridge/远程架构；本仓库的重构建议以本地代码和本目录研究为准。
