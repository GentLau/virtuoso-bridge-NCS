# Spec 冲突上报：上层如何获取本机路径

> 状态：**待 spec owner 裁决**；代码当前按 spec 原文执行（未改动 spec）。
> 提出人：实现侧；日期：2026-09-17

## 1. 我的越界改动（已回退）

实现过程中我曾把业务包构造改成 `Package(middle, paths)`，由顶层把"本机路径端口"
注入业务包。该改动**与 spec 冲突**，已全部回退：

| spec 原文 | 位置 |
|---|---|
| "业务包构造只接受一个 `Middle`" | `顶层/1-顶层.md` §2.4 |
| "注入：构造只接受 `Middle`；不创建连接/进程/隧道" | `上层/1-上层.md` §2.2 |
| "文件路径按业务需要给定，由中层按对应 role 根解析" | `上层/1-上层.md` §3.1 |

回退内容：业务包构造函数恢复为 `(middle)`；`server/dispatch.py` 只把 `Middle`
传给业务包；`pyapi/paths.py`（我新增的端口声明）删除；TB 改为**守卫该契约**
（`test.ctor`：断言业务包构造恰好收到 1 个参数且是 `Middle`）。

## 2. 需求与 spec 的冲突（需要裁决）

原始诉求："上层根本拿不到路径，没法用。"

按当前 spec，上层**不应**自己拿本机路径：

- 上层 §3.1：文件路径"按业务需要给定"，相对路径由中层按 role 根解析；
- 上层 §5：不接触 `transport.*`、不读环境变量、**不生成随机且事后无法重建的路径**；
- 上层 §2.2 + 顶层 §2.4：业务包构造只收 `Middle`，因此也没有"注入本机路径"的合法通道。

于是只剩三种可能，需 spec owner 选一种：

| 方案 | 含义 | 需要改 spec 吗 |
|---|---|---|
| **A（当前 spec 已覆盖）** | 所有本机路径由**调用方在 Request 里给**（如 `local_path`、`local_output`）；业务包只管把它交给中层 | 不需要 |
| **B（新增本机路径端口）** | 若业务操作需要"进程级工作目录"（默认落点/临时文件），则由**顶层**提供路径端口并注入业务包 | 需要：新增路径端口一节，并同步放宽 §2.2/§2.4 的"只接受 Middle" |
| **C（Request 补全）** | 顶层在派发前把本机工作目录填进 Request 的可选字段（业务包仍只收 `Middle`） | 需要：定义该字段与补全时机 |

## 3. 已按 spec 完成、与此冲突无关的部分（保留）

- **本机路径下沉为中立基座**：`src/common/paths.py`（四层共享、只读访问器、
  `init_work_dir()` 入口初始化一次、固定子结构
  `registry.json / server.json / temp / log / artifact`）；
- **各层只消费、不解析**：入口（`server.api_server` / `register.server` /
  `server.stress_server`）调用一次 `init_work_dir()`；中层与注册模块只读
  `registry_path()` / `command_log_file()` / `temp_dir()`；旧的
  `transport/runtime_paths.py`、我中途加的 `server/paths.py`/`transport/paths.py`
  均已删除；
- **`middle.query()` 只返回 role 的 `root`/`bin`**（spec 总览 §4.2 唯一口径），
  不再暴露任何本机路径；TB 增加断言：`query` 结果里不得出现 `local` 字段。

## 4. 现状

- 离线 `test/unit + test/integration + test/scenario` 全绿；完整门禁
  `run_coverage.ps1 -IncludeExtended` 全绿（覆盖率 81%）；
- 代码与 spec 原文一致（业务包仍只接收 `Middle`）；上表 A/B/C 任一裁决落地前，
  不再改动上层路径接口。
- 模块边界（本轮已落地，属代码组织，不改任何 spec 合同）：
  `src/common/` = 四层共用工具（paths/registry/validation/ssh/paramiko_backend/
  remote_paths/deploy/setup/skill_client）；`src/register/` = 独立注册模块
  （只依赖 `common.*`，不 import `transport.*`）；`src/transport/` = 中层运行时
  （不 import `register`，只共享 `common.registry` 的 schema/文件格式）。
