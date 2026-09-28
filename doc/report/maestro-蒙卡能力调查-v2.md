# maestro 蒙卡（Monte Carlo）能力调查 · v2（含活体证据）

> 取代 v1（`doc/report/maestro-蒙卡能力调查.md`，2026-09-24 文档级调查）。
> 本次 = 文档调查（3 份子报告，见 §附）+ 真机活体实验（2026-09-28）。
> 结论：**可行，改动集中在上层**；关键未知项已用真机消掉，只剩 3 个产品口径待拍板。

## 0. 结论摘要

| 问题 | 结论 | 证据 |
|---|---|---|
| 是不是"先设 mode 再 run"？ | **是**。`maeSetCurrentRunMode(... "Monte Carlo Sampling")` → 裸 `maeRunSimulation(?session s)` → 真跑出 `MonteCarlo.0`（24.8s） | §1 活体 |
| 要不要给 `run` 加 `?runMode`？ | **不需要**（文档写默认 `Single Run,...` 与实测不符，以实测为准） | §1 活体 |
| MC 选项怎么读写？ | 写：`axlPutRunOption` + `axlSetRunOptionValue`（17 项实测可写，`dutsummary` 读回空串）；`maeSetRunOption` 只认 `mcmethod` / `mcnumpoints`。读：`axlGetRunOption` + `axlGetRunOptionValue`（未设置过 = nil） | §2 活体矩阵 |
| 结果怎么读？ | `maeExportOutputView(?view "Yield")` 一次拿到 per-output **Yield/Min/Target/Max/Mean/Std Dev/Cpk/Errors**；`?view "Detail"` 是逐点（`mc_iteration=N`）。`axlWriteMonteCarloResultsCSV` 在本版**不可用**（返回 nil） | §3 活体 |
| 现在为什么跑不出有效结果？ | 三个 maestro fixture 全是 analogLib/ahdlLib，**没有任何 statistics 模型** → 2 点 MC 全部死于 `SPECTRE-16012: no variations in statistics block`，yield 0%（0 passed / 2 error） | §5 活体 + 子报告 3 |
| 环境里有没有统计模型？ | 有：`crn65gplus_2d5_lk_v1d0.scs` 33 个统计块（26 mismatch + 7 process）；但 `cor_25.scs` 等角文件**不 include 它们**，必须与角文件同时挂 | §5 子报告 3 |

## 1. 运行链路（活体确认）

1. 选 mode：`maeSetCurrentRunMode(?session s ?runMode "Monte Carlo Sampling")` → `t`（等价 GUI 里在 Run Mode 列表选 MC）。
2. 设参数：见 §2。
3. 启动：**裸** `maeRunSimulation(?session s ?waitUntilDone t)` → 返回 history `"MonteCarlo.0"`（实测 24.8s；`?waitUntilDone` 不给就是非阻塞）。
4. 进度：`axlGetRunStatus(session ?historyName h ?optionName "all")` → `(12 12)`（只列 `all/Tests/Corners`，官方没有 `points`）。
5. history 命名：`<runType>.<seq>`（同类型递增），`MonteCarlo.N` 与点数无关。
6. 会话：GUI Assembler 会话可跑；**后台会话（`maeOpenSetup`）遇到同 cellview 已开 GUI 会话会失败**（实测 `maeOpenSetup` 返回 nil，包内报 `RuntimeError: maeOpenSetup failed`）——落地要处理这个冲突。

## 2. 参数（17 项）——实测可写性矩阵

**写路径（活体矩阵，2026-09-28）**

| 选项 | `maeSetRunOption` | `axlPutRunOption`+`axlSetRunOptionValue` | 实测值示例/读回 |
|---|---|---|---|
| `mcmethod` | ✅ 可用 | ✅ | `mismatch` / `process` / `all` / `global` 均可写入并原样读回 |
| `mcnumpoints` | ✅ 可用 | ✅ | `"8"` |
| `samplingmode` | ❌ nil | ✅ | `"lhs"` |
| `montecarloseed` | ❌ | ✅ | `"12345"` |
| `donominal` | ❌ | ✅ | `"1"` |
| `saveallplots` | ❌ | ✅ | `"0"` |
| `savemismatch` | ❌ | ✅ | `"1"` |
| `saveprocess` | ❌ | ✅ | `"1"` |
| `mcnumbins` | ❌ | ✅ | `"10"` |
| `mcStopEarly` | ❌ | ✅ | `"t"` |
| `mcStopMethod` | ❌ | ✅ | 存 `"t"` 也被接受（**值域未验证**） |
| `mcstartingrunnumber` | ❌ | ✅ | `"1"` |
| `mcYieldTarget` | ❌ | ✅ | `"99"`（百分比/sigma 语义未验证） |
| `mcYieldAlphaLimit` | ❌ | ✅ | `"95"`（alpha/概率语义未验证） |
| `mcreferencepoint` | ❌ | ✅ | `"nil"` |
| `ignoreflag` | ❌ | ✅ | `"nil"` |
| `dutsummary` | ❌ | ⚠️ 可写但读回空串 | 语义待确认 |

要点：
- **写入层不做任何校验**：传什么字符串就存什么（`mcStopEarly="t"`、`mcYieldTarget="99"` 都照收）⇒ **类型/值域校验必须由上层包做**，否则错误只会在仿真阶段暴露。
- **读回语义**：未显式设置过的选项 `axlGetRunOption` 返回 nil（"未设置，用 ADE 默认"），设置过才有句柄；`axlGetRunOptions` 在本版返回空清单 ⇒ **17 项清单必须包里硬编码**。
- 文档里值域/默认值冲突较多（`mcmethod` 是 `global` 还是 `process`；`samplingmode` 是 `random` 还是 `standard`；`mcnumpoints` 默认 100 还是 200 等），详见子报告 1 的"未确认"清单；实测层面这 4 个字符串都能写入，语义需真跑对照。

## 3. 结果读取（活体样本）

`maeExportOutputView(?session s ?historyName "MonteCarlo.0" ?view "Yield" ?fileName <f>)` 产出的 CSV（实测列名）：

```
Test,Name,Yield,Min,Target,Max,Mean,Std Dev,Cpk,Errors
Yield Estimate: 0 %(0 passed/2 pts)  Confidence Level: <not set>  Filter: <not set>
opamp_ac,,,,,,,,,
,gain_db(summary),0% (0/2),0,> 19,0,0,0,,2
```
- 一次调用就把 **per-output 的 yield/min/target/max/mean/std dev/cpk/errors** 全给了（`<output>(summary)` 是汇总行）。
- `?view "Detail"` 是逐点：`Parameters: mc_iteration=N` 分块 + `Point,Test,Output,Nominal,Spec,Weight,Pass/Fail,Min,Max,...`。
- `maeGetOverallYield("MonteCarlo.0" ?session s)` → `(nil Yield 0 PassedPoints 0 ErrorPoints 2)`（整体良率/通过/错误点数）。
- `axlWriteMonteCarloResultsCSV(...)` 用 `?outputPath` / `?outputName` / 加 `?testName` 三种写法**全部返回 nil** ⇒ 本版不可用，**不要作为主路径**。

## 4. 前置条件与约束

1. **统计模型是硬前提**：模型里必须有 `statistics { process/mismatch }`，且 `mcmethod` 与之一致；否则每个点都 `error`（实测 `SPECTRE-16012`）。
2. PDK 挂载配方（来自模型文件注释 + 子报告 3）：**mismatch** 需把 `stat_mis_<工艺段>`（如 `stat_mis_25`）与角 section（`tt_25` 等）**同时挂**；**process** 需 `stat` 与 `mc_*` 同时挂。`cor_25.scs` 本身不含统计段。
3. 模拟器白名单：Spectre / APS / AMS-Spectre / hspiceD；本环境默认 `spectre`（`simExecName=spectre`）。
4. 输出必须勾 `Plot`，否则不参与 MC 评估（现有 opamp/logic fixture 的 output 全是 `plot=t`，rc_probe 是 0 个 output）。
5. MC × sweep 互斥（`ADEXL-1742`），除非开 `mcreferencepoint`（Use Reference Point）。
6. 其它：`saveallplots/saveprocess/savemismatch` 影响产物体积；`mcYieldTarget/mcYieldAlphaLimit` 只参与 Auto-Stop 判定，不决定单点 pass/fail。

## 5. 环境/载具现状（这是唯一的大缺口）

| 载体 | 器件 | modelFiles | statistics | outputs(plot) | 能否跑 MC |
|---|---|---|---|---|---|
| `maestro_tb/rc_probe` | analogLib R/C/V | nil | 无 | 0 个 | ❌ |
| `maestro_tb/opamp_probe` | ahdlLib/opamp + analogLib | nil | 无 | 7 个(plot=t) | ❌（实测 2 点全 error） |
| `maestro_tb/logic_probe` | Verilog-A/NAND/DFF | nil | 无 | 6 个(plot=t) | ❌ |
| `CMP_TB_LIB/tb_cmp_top`、`DI65/buf_stage_*` 等 | **PDK tsmcN65 器件** | — | 器件参数有统计（`parn1_25` 等） | 无 maestro 视图 | 需先建 maestro setup + 挂 stat section |

实测证据（`MonteCarlo.0`，2 点）：`.../MonteCarlo.0/1/opamp_ac/groupRunDataDir/psf/spectre.out` 里
`SPECTRE-16012 ... no variations in statistics block`，12 个 job 全灭、yield 0%（0 passed / 2 error）。
⇒ **要跑"有意义的 MC"，必须先造一个统计载具**：PDK 器件 cell + Maestro/ADE setup + 模型库挂 `cor_25.scs(tt_25)` + `stat_mis_25` + 输出勾 Plot。

## 6. 与现有实现的合并方式

| 需求 | 现有 | 要加什么（最小） |
|---|---|---|
| 选 MC 模式 | `set_run_mode` 原子 + `read_config.run_mode` | 无（可选：run_mode 白名单） |
| 设 MC 选项 | 无 | **1 条原子**：`set_run_option`，形态照 `set_env_option/set_sim_option` 的 `options` 字典（`maestro.py:1047-1053`、`_maestro_util.py:68-87`）；底层 `axlPutRunOption`+`axlSetRunOptionValue`，表驱动 17 项 + 包内值校验 |
| 读回选项 | 无 | `read_config` 增 `run_options`（按 mode 分组；未设置项返回 null = ADE 默认） |
| 启动 MC | `run`（裸 `maeRunSimulation`） | **不用改**（实测就是先设后跑） |
| 读 MC 结果 | `read_results` 只导 Detail + `maeGetOverallYield` | 增 `?view "Yield"` 导出 + 解析（≈60–90 行），汇总进 `value.monte_carlo` |
| 进度 | `read_history`（`axlGetRunStatus` 通用） | 无（`MonteCarlo.N` 已能识别） |

## 7. 改动量（修正）

| 块 | 量级 | 说明 |
|---|---|---|
| spec（`6-maestro.md`） | 60–100 行 | `set_run_option` 原子、`read_config.run_options`、`read_results.monte_carlo`、前置条件/限制（统计模型、plot、MC×sweep、模拟器） |
| 产品代码（`maestro.py`） | **300–420 行** | 17 项表 + 值校验 + SKILL 生成（~150）、read_config 回读（~50）、read_results Yield 解析（~100–150）、前置校验（~40） |
| TB | 450–650 行 | 选项矩阵/非法值/未设置语义（离线）、Yield CSV 解析（离线，样本已抓到）、真机小样本 MC（8–10 点，需先造统计载具）、`SPECTRE-16012` 负控（无统计模型 → 结构化错误） |
| 中层/底层 | 0 | 全走已有五接口 |
| **合计** | **3–4 人日** | 比 v1 估计略降：结果侧不用写 CSV 解析器（Yield 视图现成） |

## 8. 待你拍板（3 条）

1. **统计载具从哪来**：① 新建 PDK 统计器件的最小 cell + Maestro setup（推荐，最"官方"）；② 给现有 fixture 自写 `.scs` 统计模型挂载；③ 先在 `CMP_TB_LIB/tb_cmp_top` 上建 setup。
2. **选项白名单**：17 项全开（贴合官方）还是只开常用 8 项（`mcmethod/mcnumpoints/samplingmode/montecarloseed/saveallplots/savemismatch/donominal/mcnumbins`）？
3. **未设置选项的读回语义**：`null`（= 用 ADE 默认）还是干脆不列？

## 附：本次调查产物

- 子报告 1（选项语义/值域/默认值）：`doc/report/_explore/MC-1-run-options.md`
- 子报告 2（运行/结果/约束）：`doc/report/_explore/MC-2-run-and-results.md`
- 子报告 3（代码接入点/载体现状/PDK 统计清单）：`doc/report/_explore/MC-3-merge-and-env.md`
- 本次活体实验（只读 + 一个 2 点 MC 样本）留下的痕迹：
  - 测试夹具 `maestro_tb/opamp_probe` 的 GUI 会话里多了一条 history **`MonteCarlo.0`**（2 点，全 error），
    以及若干 run option 的内存改动（`mcnumpoints`/`mcmethod`/`samplingmode` 等，**未保存**，关会话即丢）；
  - 该会话的 run mode 已恢复为 `Single Run, Sweeps and Corners`；
  - 临时导出目录 `/tmp/mc_dump/`（yield.csv / detail.csv）。
