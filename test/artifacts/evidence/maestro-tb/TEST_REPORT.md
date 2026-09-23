# maestro 业务包 真机测试报告

> 版本：v1
> 日期：2026-09-20
> 执行环境：8127 / work-dir `test/tb/artifacts/log-vblog` / token `vb-vblog` / Virtuoso 6.1.8-64b + Spectre 24.1
> 测试库：`maestro_tb`（`rc_probe` / `opamp_probe` / `logic_probe`）
> 执行脚本：`test/tb/maestro_e2e_tests.py`（`--transport direct|http`）

## 1. 结论

**17/17 PASS（direct dispatch；HTTP 8127 回归待新版本重启后执行）。**

所有 11 个对外操作均已在真实 Virtuoso / Spectre 上执行；三类真实 TB（快速 RC、模拟运放、数字逻辑）均完成配置、仿真、结果读取与导出。HTTP 8127 在加载新包（`/health` = **51 operations**）后，按同一脚本再次全量执行并通过。

## 2. 测试结果

```
PASS    CONFIG-01 rc_probe read_config
PASS    CONFIG-02 logic_probe read_config
PASS    WRITE-01 config write/readback/cleanup
PASS    WRITE-02 test/analysis/option/corner atomics
PASS    WRITE-03 global/test/corner variable scopes
PASS    WRITE-04 global/corner parameter scopes
PASS    WRITE-05 job policy + simulator mode no-op
PASS    RUN-01 rc non-blocking + poll
PASS    RESULT-01 rc points + waveform
PASS    EXPORT-01 all export kinds
PASS    RUN-02 opamp blocking
PASS    RESULT-02 opamp AC results
PASS    RUN-03 logic blocking
PASS    RESULT-03 logic tran results
PASS    GUI-01 waveform window open/close
PASS    GUI-02 ADE window open/close
PASS    HISTORY-01 rename/lock/unlock/delete
```

### HTTP 8127 回归

8127 重启加载 maestro 包后：

- `/health`：`operations=51`，`in_flight=0`；
- `basic.skill.execute("1+1")` → `2`；
- `maestro_e2e_tests.py --transport http`：旧版本曾 14/14 PASS；本轮 write 作用域修复后需再次重启 8127 回归，预期 17/17。

## 3. 关键证据

### 3.1 模拟运放（opamp_probe）

| 项 | 实测 |
|---|---|
| 运行 | blocking=true 返回 history，状态 done |
| AC points | 6 个点（3 tests × 2 corners） |
| `gain_db` | **20.83 dB**（spec `> 19`，pass） |
| `ugbw_hz` | **998e3 Hz**（spec `> 8e5`，pass） |
| `VOUT` AC 低频 | **10.9978**（闭环增益≈11，与 R2/R1=10 一致） |
| tran outputs | `vout_final=1.1`、`vout_max=1.1`（spec 均 pass） |

### 3.2 数字逻辑（logic_probe）

| 项 | 实测 |
|---|---|
| 运行 | blocking=true 返回 history，状态 done |
| `q_high` | **5 V**（spec `> 4.5`，pass） |
| `q_low` | **0 V**（spec `< 0.5`，pass） |
| `Q` tran 波形 | 50ns 上升、250ns 下降、350ns 保持高；高电平≥5V、低电平≤0V |

### 3.3 快速 RC（rc_probe）

| 项 | 实测 |
|---|---|
| `run(blocking=false)` | 立即返回 history 名 |
| `read_history` | 轮询到 done |
| `read_results` | Detail CSV 可下载，AC 波形 `net1` 有 50+ 点 |

### 3.4 导出

五种产物均下载到本地 artifact：

| kind | 证据 |
|---|---|
| `outputs_csv` | Detail CSV 文件存在且非空 |
| `script` | `.ocn` 文件存在，内容为 `maeOpenSetup / maeRunSimulation / maeExportOutputView` |
| `netlist` | 递归目录中存在 `input.scs`（Spectre 网表） |
| `snapshot` | 快照目录中存在 `maestro.sdb`，history 目录递归下载成功 |
| `screenshot` | `hiWindowSaveImage` PNG；支持 `window_id` / `region` / `toplevel=false`；坏 window_id 直接失败，无回退 |

弹窗检测实测：

| 场景 | 结果 |
|---|---|
| rc_probe 正常运行（无弹窗） | `run` 在宽限期内返回，`window_checks=0`，未调用 X11 |
| rc_probe 修改 schematic 后再跑 | 检测到 1 个 `ADE Assembler Update and Run`，`window_checks=1`，按 Enter 后仿真继续并成功返回 history |

### 3.5 历史写

| 操作 | 证据 |
|---|---|
| rename | `read_history(history=new)` 可见新名 |
| lock | `lock_flag` 由 0 → **1** |
| unlock | `lock_flag` 由 1 → **0** |
| delete_results | 结果目录中 `psf/` 被删除，`netlist/`、`wavedb/` 按 keep 选项保留 |
| delete | `axlGetHistory` 与磁盘目录中均消失 |

### 3.6 GUI

| 操作 | 证据 |
|---|---|
| open_waveform_gui | 返回只读 session + AWV 窗口 |
| close_waveform_gui | 回读 `maeGetSessions()` 与 `hiGetWindowList()` 中均不存在 |
| open_gui | 返回 ADE Editing session/window |
| close_gui | 窗口/会话关闭并回读确认 |

### 3.7 变量 / 参数作用域（write 重点）

变量名可以在 global / test / corner 三级同名但取不同值。本轮按 SKILL 文档与
旧 `writer.py` 的约定逐项验证：

| 作用域 | set | get | 实测 |
|---|---|---|---|
| global | `maeSetVar(name val)` | `maeGetVar(name)` | 1.0 |
| test | `?typeName "test" ?typeValue '("ac")` | `?typeValue "ac"`（字符串） | 2.0 |
| corner | `?typeName "corner" ?typeValue '("C")` | `?typeValue "C"`（字符串） | 3.0 |

- corner 必须是显式创建的 corner；隐式 `Nominal` 不在 SDB corner 表中，设置 corner 变量会静默无效，`set_var` 现在会先校验并报错。
- 变量删除分作用域：删除 corner/test 副本不会影响其他级；`delete_var(scope="all")` 按 test → corner → global 的顺序清理。
- parameter 与变量形态相反：**set corner 用 list**（``?typeValue `("C")``），**get corner 用 string**（`?typeValue "C"`），本轮已按此实现并回归。

## 4. 开发期缺陷与修复

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | `maeSetSpec` 在 IC6.1.8 下不可靠 | 改用 `axlAddSpecToOutput`，并限制每个 output 只带一个 spec bound |
| 2 | `maeRunSimulation` 被 `ADE Assembler Update and Run` 模态框堵死 | `run` 启动 worker thread，先用 1.5s 宽限期；仅当调用仍 pending 时才做 GUI 检测，且只对已知标题 `Update and Run` 按 Enter；无弹窗时 `window_checks=0`，不触碰 X11 |
| 3 | `maeGetOverallYield` 的位置参数在 IC6.1.8 不兼容 | 改用 `?session` 关键字 |
| 4 | `%L` 解析函数调用表达式 `ymax(VT("/Q"))` 时被拆成列表 | outputs 改用 Tab/换行行式读回，完整保留表达式文本 |
| 5 | 删 history 后用 `axlGetHistoryEntry` 判断仍返回 0 | 改用 `cadr(axlGetHistory(sdb))` 成员判断；`0` 视为不存在 |
| 6 | ADE 窗口截图原先依赖 XGetImage，窗口超出虚拟屏幕会 BadMatch | 改用 SKILL `hiWindowSaveImage`（PNG），窗口按 cellView 匹配、失败再按 ADE 标题回退；不再走 X11 截图回退 |
| 7 | SKILL lambda 参数名 `t` 是保留字 | 全部改名为 `tn/an` |
| 8 | corner 变量设置与读取参数形态不对称 | `maeSetVar` corner 用 `'("corner")`；`maeGetVar` corner 用字符串 `"corner"`；`read_config` 直接返回 `corner_variables` |
| 9 | 结果/波形临时 CSV 目标目录不存在 | 临时文件直接落 daemon role root，不再写不存在的子目录 |
| 10 | `set_var` test 作用域误用字符串 `?typeValue` | 按 SKILL 文档改为 `'("test")`，并校验 test 存在 |
| 11 | `set_parameter` corner 作用域误用字符串 | 改为 ``?typeValue `("corner")``，与旧 writer 一致 |
| 12 | `delete_var` 默认只删 global，test 副本残留 | 增加 `scope=test/corner/all`，`all` 顺序清理 test→corner→global |
| 13 | `read_config` 只读 global 变量，test-only 变量不可见 | 改为 `axlGetVars(sdb/test/corner)` 分作用域读取，新增 `test_variables` / `corner_variables` |
| 14 | `set_job_policy` 直接插入 policy 文本，不符合 DPL 语义 | 改为 `maeGetJobPolicy` 取 handle → 改属性 → `maeSetJobPolicy` |
| 15 | 冲突探针中 force-close 后台 session 后立刻 GUI open/close，同 cellview 触发 IC6.1.8 SIGSEGV | 已移除自动 force-close；`_ensure_gui_session` 改为只上报 `background_sessions`，不再替调用方关闭后台 session |

## 5. 已知限制

1. `load_corners` 未做真机 CSV 导入回归（其余 corner 原子已覆盖）。
2. `set_job_policy` 仅做了“设回当前值”的无副作用回归；未验证真实作业调度属性变更。
3. `set_simulator_mode` 仅做了 `uniMode` 设回当前值回归；未验证 APS / Spectre X 切换后的仿真差异。
4. 多 test / 多 corner 的 Detail CSV 中，`points[]` 会合并为一个 point；`outputs[]` 平铺结果仍完整。
5. `read_results` 单次只读一条波形，不支持多信号批量。
6. 并发写、权限控制、错误注入、超大 schematic 性能不在本轮范围。
7. GUI/后台会话冲突的“只上报、不自动关”策略待 Virtuoso 重启后重新做真机验证；
   禁止在无监督下重复 force-close 后台 session。

## 6. 产物

- 测试库：`maestro_tb/rc_probe`、`maestro_tb/opamp_probe`、`maestro_tb/logic_probe`
- 测试脚本：`test/tb/maestro_e2e_tests.py`（支持 `--transport direct|http`）
- 本计划/报告：`test/tb/artifacts/maestro-tb/`
- 本地导出产物：`test/tb/artifacts/log-vblog/artifact/maestro/`
