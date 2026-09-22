# maestro 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-20
> 对象：`src/pyapi/packages/maestro.py`（业务包：maestro）
> 依据：`spec/design-concepts/上层/6-maestro.md`（Draft v4）

## 1. 目标与范围

验证 maestro 业务包 11 个对外操作在真实 Virtuoso + Spectre 环境下满足 spec：

| 大类 | 操作 |
|---|---|
| 配置 | `read_config` / `write` |
| 结果 | `read_results` |
| 导出 | `export`（netlist / script / outputs_csv / snapshot / screenshot） |
| 历史 | `read_history` / `write_history` |
| 仿真 | `run`（blocking=false / true） |
| 展示 | `open_gui` / `close_gui` / `open_waveform_gui` / `close_waveform_gui` |

重点验证：

1. 非 GUI 配置操作能自动打开/复用会话并落库；
2. `run` 能走 GUI 会话真实仿真，非阻塞返回 history、阻塞轮询到终态；
3. 结果读取能返回 points / spec / yield 和 AC / tran 单条波形；
4. history 的改名、锁、删结果、删整条在真机上可见且可复读；
5. 导出产物真正下载到客户端；
6. GUI / 波形窗口的打开与关闭有回读校验。

## 2. 环境

| 项 | 值 |
|---|---|
| HTTP 服务 | `127.0.0.1:8127`（`server.api_server`） |
| work-dir | `test/tb/artifacts/log-vblog` |
| token | `vb-vblog` |
| Virtuoso | 6.1.8-64b（WSL `wsl-gent`，DISPLAY=:99） |
| Spectre | 24.1（`/opt/eda/cadence/SPECTRE241`） |
| 测试库 | `maestro_tb` |

## 3. 测试台

| cell | 类型 | 配置 | 用途 |
|---|---|---|---|
| `rc_probe` | RC（vdc+res+cap） | test `ac`，AC 1Hz..1GHz，无 output | 快速配置/运行/history 用例 |
| `opamp_probe` | 行为级运放闭环 | test `opamp_ac` / `opamp_dc` / `opamp_tran`；7 outputs；5 specs；corner `vdd_high` | 模拟真实 AC/DC/tran |
| `logic_probe` | NAND + DFF | test `logic_tb`，tran 1us；outputs `Q/Y/CLK/QB/q_high/q_low`；specs `gt 4.5` / `lt 0.5` | 数字时序真实仿真 |

## 4. 测试用例

### 4.1 配置类

| 用例 | 输入 | 预期 |
|---|---|---|
| CONFIG-01 | `read_config` rc_probe | tests 含 `ac`，analyses 含 `ac` |
| CONFIG-02 | `read_config` logic_probe | 输出含 `q_high/q_low/Q/CLK`；spec 类型/值正确 |
| WRITE-01 | `write` 批量 set_var / add_output / set_spec → read_config → delete_output+delete_spec / delete_var | 写后读回变量、output、spec；清理后消失 |
| WRITE-02 | `write` 批量 set_analysis / set_sim_option / set_env_option / set_run_mode / set_job_control_mode / set_test / set_design / set_corner / setup_corner | 读回 dec/temp/controlMode/运行模式/测试/corner/variable 全部正确；测试结束清理 |
| WRITE-03 | 同名变量同时设置 global / test / corner 三级 | 三级值分别保持 1.0 / 2.0 / 3.0；逐级删除互不影响 |
| WRITE-04 | 同名 parameter 同时设置 global / corner 两级 | global 与 corner 读回均为 1K；逐级删除互不影响 |
| WRITE-05 | `set_job_policy` + `set_simulator_mode` 设回当前值 | job policy 与 uniMode 读回不变，验证原子真实可执行 |

### 4.2 仿真与结果

| 用例 | 输入 | 预期 |
|---|---|---|
| RUN-01 | rc_probe `run(blocking=false)` + `read_history` 轮询 | 返回 history；轮询到 done |
| RESULT-01 | rc_probe `read_results` + waveform | Detail 点和波形存在 |
| RUN-02 | opamp_probe `run(blocking=true)` | 返回 history 且 done |
| RESULT-02 | opamp_probe `read_results(opamp_ac)` + waveform `VOUT` | gain≈20.8dB、UGBW≈1MHz、低频增益≈11 |
| RUN-03 | logic_probe `run(blocking=true)` | 返回 history 且 done |
| RESULT-03 | logic_probe `read_results(logic_tb)` + waveform `Q` | q_high≈5、q_low≈0；波形含高/低电平 |

### 4.3 导出类

| 用例 | 输入 | 预期 |
|---|---|---|
| EXPORT-01 | `export(kind=outputs_csv)` | 本地 CSV 存在 |
| EXPORT-01 | `export(kind=script)` | 本地 `.ocn` 存在 |
| EXPORT-01 | `export(kind=netlist, test=ac, corner=Nominal)` | 本地目录含 `input.scs` |
| EXPORT-01 | `export(kind=snapshot, history=...)` | 本地目录含 `maestro.sdb` |
| EXPORT-01 | `export(kind=screenshot)` | 本地截图文件非空 |

### 4.4 历史类

| 用例 | 输入 | 预期 |
|---|---|---|
| HISTORY-01 | `write_history` rename → lock → unlock → delete_results → delete | 每条写后 `read_history` 可见：改名生效、lock_flag=1→0、删结果落盘、整条消失 |

### 4.5 GUI 类

| 用例 | 输入 | 预期 |
|---|---|---|
| GUI-01 | `open_waveform_gui` + `close_waveform_gui` | 窗口/会话创建；关闭后回读不存在 |
| GUI-02 | `open_gui` + `close_gui` | ADE 窗口/会话创建；关闭后回读不存在 |

## 5. 风险与假设

- `maeRunSimulation` 可能弹 `ADE Assembler Update and Run` 模态框；测试计划把“自动按默认按钮”作为 `run` 的显式行为验证。
- `maeSetSpec` 在 IC6.1.8 的实现不稳定；测试按 `axlAddSpecToOutput` 断言。
- 结果目录可能位于 scratch（`/home/Gent/simulation/...`），不假设在库 readPath 下。
- 并发写、权限、错误注入、超大 schematic 不在本版测试范围。

## 6. 退出标准

- 17 个 E2E 用例全部 PASS；
- 每个 PASS 都有真实 SKILL / 文件 / 读回证据；
- 未覆盖项写入“已知限制”并经评审接受。
