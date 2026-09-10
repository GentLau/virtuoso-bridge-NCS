# 新功能最小 Demo（独立参考验证）

本目录验证 `spec/design-concepts/总览/核心修改.md` 中可先行落地的功能点，
当前收拢为两个自包含 demo：

- **`full_demo.py`**：注册 + token 路由 + 并行的完整业务模拟；
- **`cdslog_demo.py`**：CDS.log 增量返回算法。

**所有代码只依赖 Python 标准库，不导入 `src/virtuoso_bridge`，不需要
`.env`、SSH、Virtuoso 或 Spectre。**（`run_command` 使用系统 PATH 里的
`pwsh` 模拟命令执行。）

> 目前**不验证“脱离环境变量”**；脚本只是刻意不读取环境变量，以便重复运行。

## 目录

| 文件 | 验证内容 |
|---|---|
| `full_demo.py` | 完整业务 demo：注册多个用户 → token 路由 → 单用户并行；`run_command` 用 pwsh 模拟，`execute_skill` 投送到端口、**到达即成功** |
| `cdslog_demo.py` | CDS.log byte cursor、BEGIN/END marker、增量读取、级别过滤、超长 error-only 降级、轮转重置 |
| `TB测试典型场景.md` | 一个典型 testbench 验证场景，说明业务链路如何映射到三层接口、token 路由和并行语义 |
| `run_all.py` | 依次运行 `full_demo` 和 `cdslog_demo` 的短示例 |
| `test_*.py` | 可执行验收单元；只导入本目录 demo 和标准库 |

## 完整业务 demo（full_demo.py）

`full_demo.py` 把注册、token 路由、并行收拢到一个自包含模块，模拟完整业务
闭环：

```text
register(多用户) → deploy → load(起各自 Skill 端口) → connect(双通道冒烟)
                → 上层每次只带 token 调 middle.run_command / middle.execute_skill
```

- `run_command(cmd, token, parallel)`：用系统 `pwsh` 模拟；默认 persistent
  pwsh 串行（保顺序、保会话状态），`parallel=True` 独立 pwsh 进程并行。
  示例输出的 `parallel_commands.elapsed_ms` 含 pwsh 冷启动耗时，并行的证据看
  `max_parallel_in_use=2` 与测试中断言的执行区间重叠；
- `execute_skill(skill, token)`：按 token 路由到对应用户端口，**请求到达端口
  即视为成功**（daemon 记录到达并 ACK，不模拟 SKILL 求值）；
- 同一用户的 Skill 端口是单线程 daemon（串行，Virtuoso CIW 语义），不同用户
  之间真并行；每个用户有独立 worker 池，超限立即返回结构化错误。

```powershell
python spec/demo/full_demo.py
python -m unittest spec.demo.test_full_demo -v
```

### 四步接入

| 步骤 | 行为 | demo 实现 |
|---|---|---|
| ① 注册 | 探测端口 / 分配 token / 写 `registry.json` | `middle.register(user, token=None)` |
| ② 部署 | token 注入伪 `virtuoso_setup.il` | `middle.deploy(user)` |
| ③ load | 起该用户自己的 Skill 端口（单线程 daemon） | `middle.load(user, daemon_delay=…)` |
| ④ 连接 | 命令冒烟 `vb-ok` + Skill 冒烟 `1+1` | `middle.connect(user)` |

`register_and_start()` 一步完成四步，供业务 demo 直接使用。

### 并发语义

| 维度 | 行为 |
|---|---|
| 跨用户 execute_skill | 并行（各自独立 daemon 进程/端口） |
| 同用户 execute_skill | 串行（单线程 daemon，对应单 CIW 语义） |
| run_command 默认 | persistent pwsh 串行，保顺序、保会话状态 |
| run_command `parallel=True` | 每调用独立 pwsh 进程并行 |
| worker 池 | 每用户独立，超限返回 `worker_capacity`，不排队 |

## CDS.log 增量（cdslog_demo.py）

`CdsLogIncrementReader` 只持有 `path + cursor`；`SkillLogEmitter` 模拟底层
`VB-BEGIN → 本次日志 → VB-END → flush → end_offset`；`DemoSkillExecutor` 把
裁剪后的增量挂到 `SkillResult.log`。过滤顺序：

```text
读增量 [cursor, end_offset) → 按 log_level 过滤 → 超 max bytes 时 error-only
                            → error 仍超长时保留头尾
```

覆盖：旧日志不重复返回、`all/warn/error/off`、超长自动降级并附
`[log truncated: error-only, ...]`、文件轮转/清空后 cursor 归零、UTF-8 字节
限制。

```powershell
python spec/demo/cdslog_demo.py
python -m unittest spec.demo.test_cdslog_demo -v
```

## 一键运行

在仓库根目录执行：

```powershell
# 全部验收单元
python -m unittest discover -s spec/demo -p "test_*.py" -v

# 两个短示例（完整业务 + CDS.log）
python -m spec.demo
```

## 与正式实现的边界

这些脚本是**参考验证**，不是对当前包的兼容层，也不替代正式协议实现：

- `run_command` 只跑演示用的 pwsh 命令，不连接 SSH / Spectre；
- `execute_skill` 用一行 JSON + ACK 证明“到达对应端口”，不是 daemon 的
  STX/NAK/RS，也不模拟 SKILL 求值结果；
- 注册 demo 的 daemon 是 loopback 伪服务，`load` 是模拟 CIW 动作；
- CDSlog demo 在本地文件上验证算法，不调用 `hiGetLogFileName()` /
  `hiFlushLogFile()`；
- 不覆盖 SSH、split-host、Virtuoso 单 CIW、环境变量迁移、Spectre、文件通道。

因此通过本目录测试只能说明：**核心数据流和并发/路由/注册/log 算法在脱离
现有代码时具有最小可行性**。进入正式实现前，仍需把这些边界替换成协议规定的
真实 transport 和 daemon 行为。
