# TB 测试场景验证报告

> 日期：2026-09-09
> 环境：Windows + Python 3.12 + 系统 `pwsh`
> 验证对象：`spec/demo/full_demo.py`（注册 + token 路由 + 并行）、
> `spec/demo/cdslog_demo.py`（CDS.log 增量）
> 复现：`python -m spec.demo.tb_scenario_report`（8 个场景一次性输出 JSON）

本报告只回答三件事：**测了哪些 TB 场景、每个场景的实测效果、一共验证了多少**。
不重复设计文档里的机制推演。

## 1. 结论先行

| 项 | 结果 |
|---|---|
| 实测场景 | **8 个**（接入 / 路由 / 同用户串行 / 跨用户并行 / 命令串行状态 / 命令并行 / 池超限 / CDSlog 增量） |
| 自动化验收 | **18 个测试方法全部通过**（full_demo 11 + cdslog 7），源码静态统计 **95 处断言调用** |
| 多用户接入 | 通过：两次「注册→部署→load→连接」都成功，端口/ token 分离 |
| token 路由隔离 | 通过：每条 Skill 只到达自己的端口，未知 token 零接触 |
| 同用户 Skill 串行 | 通过：两条并发操作不重叠，墙钟 ≈ 两条之和（602.6 ms vs 300 ms/条） |
| 跨用户 Skill 并行 | 通过：墙钟 ≈ 单条耗时（302.4 ms vs 300 ms/条），区间重叠 |
| 命令串行保状态 | 通过：变量跨命令可见（41+1=42），两条 300 ms 命令串行为 674.9 ms 且不重叠 |
| 命令并行 corner | **机制通过、墙钟未加速**：区间重叠、并发度=2，但耗时 3.35 s > 串行基线 2.15 s（原因见 §4） |
| worker 池超限 | 通过：拒绝延迟 0.02 ms，立即返回 `worker_capacity`，不排队 |
| CDSlog 增量 | 通过：只回本次区间、超长降级 error-only、轮转后 cursor 归零 |

一句话：**结构语义全部验证成立；用 pwsh 模拟的“并行墙钟提速”不成立，且原因清楚
（每并行命令 = 新起一个 pwsh 进程，本机冷启动约 2.7 s，而真实 SSH exec channel 是毫秒级）。**

## 2. 每个场景：做法 → 实测数据 → 判据

### 场景 1：多用户接入（TB 工程师上线）

- 做法：`register_and_start("alice", token="alice-prod")`、`register_and_start("bob", token="bob-prod")`，
  自动跑完 ①注册 ②部署 ③load ④命令冒烟+Skill 冒烟。
- 实测（本次运行）：
  - alice 端口 57890，bob 端口 57892（每次运行随机，但必不相等）；
  - 两个用户 `connect_success = true`（命令 `vb-ok` + Skill `1+1` 到达）；
  - `registry.json` 中无 `status` / `authorized` 运行态字段。
- 判据：接入闭环可用，端口/ token 不冲突，注册表只存冷启动事实。

### 场景 2：token 路由（TB 操作只落到自己的 Virtuoso 会话）

- 做法：`execute_skill("alice-tb-op", token="alice-prod")`、`execute_skill("bob-tb-op", token="bob-prod")`、
  再发一个 `wrong-token`。
- 实测：
  - alice 请求到达 endpoint `alice`，bob 到达 endpoint `bob`，`cross_routing_clean = true`；
  - 到达记录：alice = `["1+1", "alice-tb-op"]`，bob = `["1+1", "bob-tb-op"]`，互不混串；
  - `wrong-token` → `ok=false`、错误 `unknown token`，两个端口零新增记录。
- 判据：token 寻址正确；未知 token 在进入任何端口前被拒绝。

### 场景 3：同一用户的两条 TB Skill 串行（单 CIW 语义）

- 做法：一个用户、daemon 每条处理延迟 300 ms，同时发两条 Skill。
- 实测：墙钟 **602.6 ms**，两条到达各耗时 **313.0 / 296.0 ms**，`overlap = false`。
- 判据：同一 daemon 单线程顺序处理，第二条等第一条结束——Virtuoso 单 CIW 串行成立。

### 场景 4：两个用户的 TB Skill 并行（两个 CIW/daemon）

- 做法：两个用户、每条同样延迟 300 ms，同时各发一条。
- 实测：墙钟 **302.4 ms**（≈ 一条 300 ms，而不是串行 600 ms），`overlap = true`。
- 判据：跨用户并行成立，晚发的人不被别人的 daemon 阻塞。

### 场景 5：命令默认串行 + persistent shell 状态（网表→仿真的有依赖步骤）

- 做法：`$tb_netlist_ready=41` 后读 `$tb_netlist_ready+1`；再并发提交两条 300 ms 命令（默认串行）。
- 实测：
  - 状态输出 **`42`**（变量跨命令可见，等价于“上一步生成的文件名下一步还能用”）；
  - 两条命令墙钟 **674.9 ms**，`overlap = false`，执行顺序 `step0 → step1`。
- 判据：默认串行保顺序、保会话状态，有依赖的 TB 步骤不会乱序。

### 场景 6：同一用户两个独立 corner 显式并行

- 做法：预热后，两条 `Start-Sleep -Seconds 1` 的 `corner-tt / corner-ss` 用 `parallel=True` 并发。
- 实测：
  - 串行基线（persistent shell 顺序跑两条）：**2154.6 ms**；
  - 并行墙钟：**3349.1 ms**，speedup **0.64**；
  - 但两条执行区间 `overlap = true`，`max_parallel_in_use = 2`，两条结果都成功。
- 判据：**并行机制成立**（独立进程、同时执行、并发度=2）；**墙钟提速不成立**，原因是
  pwsh 进程冷启动开销 > 1 s 的 sleep 本身，见 §4。

### 场景 7：worker 池满时立即拒绝

- 做法：`max_workers=1`，用一条并行命令占住唯一 worker，再发第二条。
- 实测：第二条返回 `error_kind = worker_capacity`，**拒绝延迟 0.02 ms**；第一条正常完成，Skill 端口 0 到达。
- 判据：超限立即报错、不无限排队，符合“超限拒绝”口径。

### 场景 8：每次 TB 操作返回本次 CDS.log 增量

- 做法：预置 12 字节旧日志，连续两次 Skill 调用；另做超长降级与文件轮转。
- 实测：
  - 第一次增量只含本次 `VB-BEGIN/…/VB-END`，第二次不含第一次内容；
  - 超长输入 → `truncated = true`、含 `[log truncated: error-only` 说明、只留 error；
  - 文件被清空/轮转后，下一次 `start_offset = 0`。
- 判据：增量、级别过滤、限长降级、轮转重置全部成立。

## 3. 验证了多少

- `python -m unittest discover -s spec/demo -p "test_*.py" -v`：**18 个测试方法，OK**；
  - `test_full_demo.py`：11 个方法，54 处断言（接入 2、路由/隔离 4、串行/并行/池 5 等）；
  - `test_cdslog_demo.py`：7 个方法，41 处断言（增量、`all/warn/error/off`、超长、轮转、UTF-8）。
- `pytest -q spec/demo`：**18 passed**。
- `tb_scenario_report.py`：上面 8 个场景的端到端实测，全部输出结构化数据，可重复生成。

## 4. 效果边界（哪些数字不能直接当性能结论）

1. **并行 corner 的墙钟不加速**：demo 的“一条并行命令 = 新起一个 pwsh 进程”，本机实测
   首个 pwsh 冷启动约 2.7 s、随后约 1 s；sleep 1 s 时进程启动成本压过了并行收益
   （3.35 s > 2.15 s）。真实中层在**已建立的 SSH 连接上开 exec channel 是毫秒级**，
   不存在这个成本，所以 demo 只验证“机制”（重叠、并发度、无串包），不验证“速度”。
2. **Skill 只验证到达端口**：`execute_skill` 的判据是请求到达该用户端口即成功，不模拟
   SKILL 求值结果（`1+1=2`、`schCheck` 通过与否），也不验证 daemon 前置 token 比对。
3. **未覆盖**：SSH / split-host / 跳板、真实 Virtuoso CIW 与 `ipcBeginProcess`、Spectre、
   文件通道（PSF 下载）、脱离环境变量、CDS.log 与真实 `hiFlushLogFile` 的对接。
   这些属于正式实现的验收，不在本 demo 范围。

## 5. 复现命令

```powershell
# 8 个场景实测 + JSON 输出
python -m spec.demo.tb_scenario_report

# 自动化验收
python -m unittest discover -s spec/demo -p "test_*.py" -v
uv run --with pytest --python .venv/Scripts/python.exe python -m pytest -q spec/demo
```

> 墙钟类数字随机器负载浮动；**确定性判据**（重叠、顺序、路由端点、拒绝码、字节区间）
> 不随运行变化。
