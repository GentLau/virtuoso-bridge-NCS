# MC-2：Cadence 蒙卡运行链路、进度与结果读取调研

> 调研日期：2026-09-28  
> 范围：ADE Assembler / Maestro SKILL、ADE XL/Assembler 本地文档、仓库既有实测记录。  
> 限制：只读调研，未连接真机，未开关 ADE 会话。  
> 主要证据：本地 Cadence HTML 文档、`http://127.0.0.1:8123/api/{find,info}`、仓库内既有报告/代码。  

## 0. 结论速览

| # | 结论 | 证据 |
|---|---|---|
| 1 | GUI 的 Run Mode 下拉选择，最接近的 SKILL 是 `axlSetCurrentRunMode()` / `maeSetCurrentRunMode()`；“点 Run”脚本等价物是显式执行 `maeRunSimulation(?runMode "Monte Carlo Sampling")`。 | `doc/maeSKILLref/maestroSKILL.html:8572-8642`；`/api/info?name=axlSetCurrentRunMode`；`doc/maeSKILLref/runRelated.html:868-1060` |
| 2 | `maeSetCurrentRunMode()` 和 `maeRunSimulation(?runMode ...)` **不是同一个 API**。后者是“设置本次 runMode 并启动”的原子入口；前者的官方描述只是更新 session 当前 runMode。 | `doc/maeSKILLref/maestroSKILL.html:8572-8642`；`doc/maeSKILLref/runRelated.html:868-874` |
| 3 | **不能证明**“先 `maeSetCurrentRunMode("Monte Carlo Sampling")`，再裸调 `maeRunSimulation()`”会跑 MC。官方页把 `?runMode` 默认值写成 `"Single Run, Sweeps and Corners"`；MC 示例始终显式传 `?runMode`。仓库旧报告中“裸 run 沿用当前 mode”的说法应降级为未确认。 | `doc/maeSKILLref/runRelated.html:898-910,1053-1058`；对照旧报告 `doc/report/maestro-蒙卡能力调查.md:16` |
| 4 | history 名是 `runType.seqNum`。同一 cellview 内，某 runType 的第一条 history 是 `.0`，之后递增；所以 MC history 可能是 `MonteCarlo.0`，也可能因历史上已有 MC 而是 `MonteCarlo.1`。必须使用返回值，不要猜固定 `.1`。 | `doc/assembler/asmCheckpoints.html:217-225`；`doc/maeSKILLref/runRelated.html:1050-1058`；`doc/maeSKILLref/historyRelated.html:746` |
| 5 | MC 启动在当前仓库环境中必须用 GUI session；后台 `maeOpenSetup` session 曾出现 `Received stop signal from user`，换 GUI session 后可跑完。这是 IC6.1.8 上的实测结论，不是 Cadence 官方 API 限制。 | `doc/report/机制-maestro-GUI与后台会话冲突.md`；`src/pyapi/packages/maestro.py:2946-2953` |
| 6 | MC 进度主查询是 `axlGetRunStatus()`。本版文档的 `optionName` 只有 `all`（点数）、`Tests`、`Corners`；**没有记录 `points`**。要用点进度应优先用 `all`。 | `doc/maeSKILLref/runRelated.html:3494-3595` |
| 7 | `maeGetOverallYield()` 示例返回 `(nil Yield 100 PassedPoints 2 ErrorPoints 0)`；`Yield`、`PassedPoints`、`ErrorPoints` 可从键名理解，但列表第一个裸 `nil` 的语义未被官方页解释。 | `doc/maeSKILLref/maestroSKILL.html:12167-12238` |
| 8 | per-output 的 `mean/sigma/min/max/yield` 首选不是裸 MC CSV，而是导出 **Yield 结果视图**：`maeExportOutputView(... ?view "Yield" ?historyName h)`。该视图文档列明 Yield/Min/Target/Max/Mean/Std Dev/Cpk 等列。 | `doc/maeSKILLref/maestroSKILL.html:10859-11052`；`doc/assembler/asmViewingResults.html:481-650`；`doc/adexl/adexlViewingResults.html:918-1060` |
| 9 | `axlWriteMonteCarloResultsCSV()` 每个 corner 一个 CSV；文档截图进一步显示文件名至少含 test，形如 `<history>.<test>.<corner>.csv`。但 CSV 列头和单元格布局没有官方样例，必须真机确认。 | `doc/maeSKILLref/historyRelated.html:2488-2619`；`doc/adexl/images/adexlMC-66.gif` |
| 10 | `mcYieldTarget`/`mcYieldAlphaLimit` 参与 **Auto Stop 的置信区间判定**，不直接决定单个 sample 的 pass/fail；单点 pass/fail 仍由 output spec 决定。 | `doc/adexl/adexlMC.html:858-889`；`doc/ocnxl/ocnxlcommands.html:7042-7090,7275-7290` |

---

## 1. 运行链路

### 1.1 GUI 操作到 SKILL 的映射

| GUI 动作 | 最接近的 SKILL | 说明 |
|---|---|---|
| 在 Run Mode 列表选 `Monte Carlo Sampling` | `axlSetCurrentRunMode(x_hsdb "Monte Carlo Sampling")`，高层封装为 `maeSetCurrentRunMode(?runMode "Monte Carlo Sampling" [?session s])` | `maeSetCurrentRunMode` 官方描述是“Updates the current run mode in ADE Assembler”；返回 `t/nil`。 |
| 点击 Run 执行当前 MC mode | `maeRunSimulation(?session s ?runMode "Monte Carlo Sampling" ...)` | `maeRunSimulation` 官方描述是“Sets the given run mode for the given session and runs simulation”，MC 官方示例即此形式。 |
| 先选 mode、再点 Run（GUI 两步） | 脚本里最稳妥仍应写成一步 `maeRunSimulation(?runMode "Monte Carlo Sampling")` | GUI Run 按钮内部是否直接调用 `maeRunSimulation` 未在文档中展开；但“指定 mode 并运行”的脚本对应关系明确。 |

证据：

- `doc/maeSKILLref/maestroSKILL.html:8572-8642`
- `http://127.0.0.1:8123/api/info?name=maeSetCurrentRunMode`
- `http://127.0.0.1:8123/api/info?name=axlSetCurrentRunMode`
- `doc/maeSKILLref/runRelated.html:868-874,1045-1058`

注意：`maeSetCurrentRunMode` 的 `?runMode` 参数说明在本地文档中被误写成 “Name of the corner to be added/updated”，但函数标题、描述和示例都明确是 run mode，属于文档文案缺陷。

### 1.2 `maeSetCurrentRunMode` 与 `maeRunSimulation(?runMode ...)` 是否等价

**结论：不应当视为等价。**

| 对比项 | `maeSetCurrentRunMode()` | `maeRunSimulation(?runMode ...)` |
|---|---|---|
| 动作 | 只更新 session 的当前 runMode | 为该次 run 指定 runMode，并启动 |
| 返回值 | `t / nil` | history 名 / run ID / `nil` |
| 是否启动仿真 | 否 | 是 |
| 是否原子 | 本身是一次 mode 更新；后续 run 是另一次调用 | mode 设置与 run 启动在同一次调用 |
| 官方 MC 示例 | 未作为 MC 启动示例出现 | 明确使用 `?runMode "Monte Carlo Sampling"` |
| 文档中的默认值风险 | 未说明会覆盖 `maeRunSimulation` 的 `?runMode` 默认值 | `?runMode` 默认值明确写为 `"Single Run, Sweeps and Corners"` |

因此：

1. 可以确认 `maeSetCurrentRunMode` 会改变当前 mode。
2. 不能确认随后裸调 `maeRunSimulation()` 会使用该 mode；文档默认值反而指向 Single Run。
3. 对自动化脚本，推荐显式：

```skill
maeRunSimulation(?session s ?runMode "Monte Carlo Sampling")
```

4. 官方文档没有出现 “recommended” 字样；这里说“推荐”是基于签名、默认值和 MC 官方示例得出的工程结论，不是原文字面推荐。

### 1.3 `maeRunSimulation` 参数

官方签名：

```skill
maeRunSimulation(
  [ ?session t_sessionName ]
  [ ?runMode t_runMode ]
  [ ?callback t_callback ]
  [ ?run t_runPlan ]
  [ ?waitUntilDone g_waitUntilDone ]
  [ ?returnRunId g_returnRunId ]
)
=> t_histname / x_runID / nil
```

| 参数 | 作用 | 默认/边界 |
|---|---|---|
| `?session` | ADE Explorer/Assembler session 名 | 省略时用当前 session |
| `?runMode` | 本次 runMode；MC 合法值含 `"Monte Carlo Sampling"` | 文档默认 `"Single Run, Sweeps and Corners"` |
| `?callback` | 仿真完成后执行的回调过程 | 文档正文写 after completing the simulation；示例注释写 after each run，回调粒度存在歧义 |
| `?run` | Run Plan 名称，用于运行 Run Plan assistant 中创建的 run | `"All"` 表示运行 plan 中全部 run；普通 MC 不需要 |
| `?waitUntilDone` | `t`：等待本次 run 完成后才执行下一条脚本；`nil`：不等待 | 默认 `nil`，用于并行启动多个 run |
| `?returnRunId` | `t`：返回 run ID；`nil`：返回 history 名 | 默认按参数表是 `nil` = history；但 Value Returned 注释写成“仅当 `?returnRunId nil` 时返回 run ID”，与参数表相反，属于官方文档自相矛盾，需真机确认 |

来源：`doc/maeSKILLref/runRelated.html:868-1043`；`http://127.0.0.1:8123/api/info?name=maeRunSimulation`。

实践注意：

- `?waitUntilDone t` 会阻塞 SKILL channel；仓库既有资料明确警告它会阻塞 Virtuoso event loop，优先用 `?callback` 或非阻塞启动 + `axlGetRunStatus` 轮询。来源：`skills_bak/virtuoso/references/maestro-skill-api.md:353-360`；`spec/research/01-virtuoso-data-model-and-editing.md:350`。
- callback 只能证明回调被调用，不能单独证明所有点收敛、结果完整或没有 evaluation error。
- `maeRunSimulation` 返回 `nil` 时，应调用 `maeGetSimulationMessages(?session s ?msgType "ERROR")` 取详情；其文档示例正是用于读取 MC/sweep 冲突消息。来源：`doc/maeSKILLref/runRelated.html:610-634`。

### 1.4 history 名语义

ADE Assembler 文档给出统一命名：

```text
runType.seqNum
```

| 部分 | 含义 |
|---|---|
| `runType` | 对应 run mode 的默认前缀；Single Run 是 `Interactive`，Global Optimization 是 `GlobalOpt`；Run Plan 用 plan 名 |
| `seqNum` | 某 runType 在该 cellview 内的第一条为 `0`，之后逐条加 1 |
| `runType.seqNum.TS.seqNum` | 调试某个 design point 时产生的子 history 格式 |

例子：

- MC 官方示例返回 `"MonteCarlo.1"`，说明当时该 cellview 已有 MC history 或编号已推进。
- 文档另一处使用 `MonteCarlo.0`，并写函数从 history 反查 run mode。
- Run Plan child history 用 `Plan.0.Run.0`，打开结果时必须指定 child history，不能只开 parent `Plan.0`。

来源：

- `doc/assembler/asmCheckpoints.html:217-225`
- `doc/maeSKILLref/runRelated.html:1050-1058`
- `doc/maeSKILLref/historyRelated.html:746`
- `doc/maeSKILLref/maestroSKILL.html:12557-12559`

结论：`MonteCarlo.N` 的 `N` 是 per-runType 序号，不是点数、corner 数或“第几次尝试”的全局编号。自动化必须使用 `maeRunSimulation` 返回值。

### 1.5 后台 `maeOpenSetup` session 与 GUI Assembler session

官方 API 层面：

- `maeOpenSetup(lib cell view ...)` 加载 setup 并返回 session 名；它本身没有“必须由 GUI 调用”的签名限制。来源：`doc/maeSKILLref/maestroSKILL.html:6298-6464`。
- 多数 `mae*`/`axl*` 接口接受显式 `?session` 或 session name，因此从 API 契约看不是天然 GUI-only。
- 真正依赖 GUI 焦点/可见选择的是 `maeGetResultsViewSelectedCellsDetails()`：它读取当前可见 results view 中用户选中的单元格，若没有加载结果或当前不是 Detail/Detail-Transpose/Fault，会返回 `nil`。来源：`doc/maeSKILLref/maestroSKILL.html:11750-11834`。
- `hiGetCurrentWindow()`、`axlGetWindowSession(hiGetCurrentWindow())` 这类入口依赖当前窗口；后台无窗口时不可作为 session 获取方式，应显式保存 `maeOpenSetup` 返回的 session。

仓库在该项目的 IC6.1.8 环境中的实测：

- 后台 `maeOpenSetup` session 调 `maeRunSimulation` 后出现 `Received stop signal from user`，任务被杀。
- 同一 cellview 改为 GUI session，并设置 `maeSetJobControlMode("ICRP")` 后，`maeRunSimulation` 正常返回 history 并跑完。
- 因此仓库现行策略是：**仿真启动强制 GUI session**；后台 session 只做打开/配置/读取类工作。

来源：`doc/report/机制-maestro-GUI与后台会话冲突.md`；`src/pyapi/packages/maestro.py:2946-2953`。

| API/操作 | 是否要求 GUI session | 证据与备注 |
|---|---|---|
| `maeOpenSetup` | 否 | 可创建无窗口后台 session |
| `maeSetCurrentRunMode` | API 不要求 | 仍建议在真正要跑的 session 上设置，避免 session 串台 |
| `maeRunSimulation` | API 允许显式 session，但本项目环境实测要求 GUI | 后台 session 曾被终止；这是环境实测，不是官方文档禁令 |
| `maeOpenResults` | 文档支持 `?session ?history` | 结果上下文是进程全局，多个 read 操作需串行化 |
| `maeGetResultOutputs` / `maeGetResultTests` | 依赖已打开的 result pointer | 先 `maeOpenResults`，完成后 `maeCloseResults` |
| `maeExportOutputView` | 文档支持显式 `?session ?historyName` | 仓库 `read_results` 使用 `maeOpenSetup` 后台 session + Detail CSV，已有实现路径 |
| `axlWriteMonteCarloResultsCSV` | 文档签名是 session + history | 没有 GUI 依赖描述；MC 专用导出尚未在本仓库实测 |
| `maeGetOverallYield` | 文档参数是 history + session | 无 GUI 依赖描述 |
| `maeGetResultsViewSelectedCellsDetails` | **是** | 依赖当前可见 results view 和用户选中单元格，后台无此状态 |

仓库结果读取/仿真 session 的实际实现：

- `read_results` 走 `_open_session`，底层是裸 `maeOpenSetup(lib cell view)`。来源：`src/pyapi/packages/maestro.py:399-416,1870+`。
- `run` 走 `_ensure_gui_session()`，再调用 `maeSetJobControlMode("ICRP")` 和裸 `maeRunSimulation(?session ...)`。来源：`src/pyapi/packages/maestro.py:2946-2953`。
- 上面第 2 点再次说明当前包的 `run` 没有显式传 `?runMode`，因此不能仅凭“先调过 set_run_mode”就断言它启动 MC。

---

## 2. MC 进度

### 2.1 `axlGetRunStatus`

```skill
axlGetRunStatus(
  t_sessionName
  [ ?optionName t_optionName ]
  [ ?historyName t_historyName ]
)
=> (completed total)
```

| 项 | 官方语义 |
|---|---|
| `?optionName "all"` | 已完成点数 / 总点数；**默认值** |
| `?optionName "Tests"` | 已完成 test 数 / 总 test 数 |
| `?optionName "Corners"` | 已完成 corner 数 / 总 corner 数 |
| 不给 `?historyName` | 聚合该 session 中所有正在运行的 history |
| 给 `?historyName` | 只查询指定 history |
| 返回 | 两个整数：已完成数、总数 |

来源：`doc/maeSKILLref/runRelated.html:3494-3595`；`http://127.0.0.1:8123/api/info?name=axlGetRunStatus`。

**`points` 的结论：**

- 本版官方接口页只列 `all`、`Tests`、`Corners`，没有 `points`。
- 因此点进度应使用：

```skill
axlGetRunStatus(session ?historyName h ?optionName "all")
=> (done total)
```

- 仓库旧报告和当前 Python 封装对 `"points"` 有使用/描述，但缺少本版官方证据；这属于版本差异/未确认别名。

例子：

```skill
axlGetRunStatus("session0" ?historyName "MonteCarlo.0" ?optionName "all")
=> (4 100)
```

含义是 100 个总点，已完成 4 个；具体返回数必须结合 `mcnumpoints`、corner、nominal 和 auto-stop 实际扩展后的总点数理解。

### 2.2 单点状态

官方还给出更细的 SKILL 路径：

```skill
x_history = axlGetHistoryEntry(x_mainSDB "MonteCarlo.0")
rdbPath   = axlGetHistoryResults(x_history)
r         = axlOpenResDB(rdbPath)
r->testStatus("myTest1" 1)
```

返回码：

| 值 | 状态 |
|---:|---|
| 1 | Pending |
| 2 | Running |
| 3 | Done |
| 10 | Disabled |

来源：`doc/maeSKILLref/runRelated.html:1102-1140`。

### 2.3 推荐的完成判定

1. 先保存 `maeRunSimulation` 返回的 history。
2. 用 `axlGetRunStatus(session ?historyName h ?optionName "all")` 轮询 `(done total)`。
3. 完成后不要只看 `done == total`：还要导出结果视图/日志，确认没有 evaluation error、partial data 和 nominal 预跑失败。
4. 若需要精确到 point，再用 `r->testStatus(test pointId)`。

---

## 3. 结果读取

### 3.1 `axlWriteMonteCarloResultsCSV`

#### 签名与参数

文档正式语法：

```skill
axlWriteMonteCarloResultsCSV(
  t_session
  t_historyName
  [ ?testName t_testName ]
  [ ?cornerName t_cornerName ]
  [ ?outputName t_outputPath ]
)
=> t / nil
```

| 参数 | 语义 | 默认 |
|---|---|---|
| `t_session` | session 名或 session handle | 必填 |
| `t_historyName` | Monte Carlo history 名 | 必填 |
| `?testName` | 只导出指定 test | `nil` = 全部 test |
| `?cornerName` | 只导出指定 corner | `nil` = 全部 corner |
| 路径参数 | CSV 输出目录 | cellview 所在目录 |
| 返回 | `t` 成功 / `nil` 失败 | — |

**重要文档冲突：**

- 正式语法写的是 `?outputName t_outputPath`。
- 同一页官方示例却写：

```skill
axlWriteMonteCarloResultsCSV(
  "session0" "MonteCarlo.1"
  ?testName "AC"
  ?cornerName "C1"
  ?outputPath "/tmp/csvfiles/"
)
=> t
```

- 因此 `?outputName` 与 `?outputPath` 哪个才是当前版本实际接受的参数名，必须在真机确认；不要在没有版本分支的情况下只实现一个拼写。

来源：`doc/maeSKILLref/historyRelated.html:2488-2619`；`http://127.0.0.1:8123/api/info?name=axlWriteMonteCarloResultsCSV`。

#### 输出文件布局

文档文字说：

- “每个 corner 一个单独 `.csv`”。
- `?testName`/`?cornerName` 用于筛出子集。

文档截图进一步显示文件名：

```text
MonteCarlo.0.ACGainBW.C0_VDD_1.6_Temp_0.csv
MonteCarlo.0.ACGainBW.C0_VDD_1.6_Temp_1.csv
MonteCarlo.0.ACGainBW.C1_VDD_2.0_Temp_0.csv
...
```

从截图可读出的模式：

```text
<history>.<test>.<corner>.csv
```

所以至少在这份 ADE XL 文档截图中，文件维度是 **test × corner**，而不是只含 corner。

来源：`doc/adexl/adexlMC.html:1690-1704`；`doc/adexl/images/adexlMC-66.gif`。

#### CSV 列头与列含义

**未确认。**

本地文档没有展示一个打开的 MC CSV，也没有给出表头/列定义。因此以下内容不得凭名字猜测：

- 第一列是否一定是 `Point` / sequence；
- 是否含 `Test`、`Corner`、`Parameter` 列；
- output value、spec、pass/fail、mean/sigma 是否在该 CSV 中；
- 一个 test 多 output 时是宽表还是长表；
- 是否存在 header、注释行、空行或 Cadence 专用转义。

工程结论：

- 如果目标只是“保管原始 MC 数据”，可用 `axlWriteMonteCarloResultsCSV`，但解析前必须真机取样定列。
- 如果目标是 per-output 的 mean/sigma/min/max/yield，优先导出 Yield view，不要先假设 MC CSV 已含统计列。

### 3.2 `maeGetOverallYield`

官方签名：

```skill
maeGetOverallYield(
  t_historyName
  [ t_sessionName ]
)
=> t / nil
```

文档示例：

```skill
maeGetOverallYield("Run.2")
=> (nil Yield 100 PassedPoints 2 ErrorPoints 0)
```

| 字段 | 示例值 | 可确认语义 | 备注 |
|---|---:|---|---|
| 第一个裸 `nil` | `nil` | **未确认** | 无键名，官方页未解释 |
| `Yield` | `100` | history 的 overall yield | 单位/小数位需真机确认；GUI 以百分比显示 |
| `PassedPoints` | `2` | pass 的点数 | 键名明确 |
| `ErrorPoints` | `0` | error 的点数 | 键名明确 |

注意：函数签名/返回值栏写 `t / nil`，但示例实际返回列表/alist，说明文档返回值栏不严谨。仓库现有解析器按“符号 + 下一元素”成对读取，正好能解析 `Yield 100 PassedPoints 2 ErrorPoints 0`，并忽略裸 `nil`。来源：`src/pyapi/packages/_maestro_util.py:286-315`。

`maeGetOverallYield` 是“整条 history 的 overall”入口；不要用它获取每个 output 的 mean/sigma。

### 3.3 per-output 的 mean/sigma/min/max/yield 从哪里取

#### 首选：Yield view CSV

官方 MC 结果示例：

```skill
maeRunSimulation(?runMode "Monte Carlo Sampling")
=> "MonteCarlo.2"
maeWaitUntilDone('All)
maeExportOutputView(
  ?session "fnxSession0"
  ?historyName "MonteCarlo.2"
  ?fileName "./abc.csv"
  ?view "Yield"
)
```

`maeExportOutputView` 完整签名：

```skill
maeExportOutputView(
  [ ?session t_sessionName ]
  [ ?fileName t_fileName ]
  [ ?view t_viewType ]
  [ ?historyName t_historyName ]
  [ ?testName t_testName ]
  [ ?filterName t_filterName ]
  [ ?clearAllFilters g_clearAllFilters ]
)
=> t / nil
```

`?view` 合法值含：

```text
Detail
Detail - Transpose
Status
Summary
Yield
Checks/Asserts
Fault
Current
```

来源：`doc/maeSKILLref/maestroSKILL.html:10859-11052`；`http://127.0.0.1:8123/api/info?name=maeExportOutputView`。

ADE Assembler Yield view 的列：

| 列 | 含义 |
|---|---|
| `Test` | test 名，展开树的顶层 |
| `Name` | output expression / measurement，或 corner 名 |
| `Yield` | 每个 spec 的 yield；Assembler 文档还说显示 pass 点数 / completed 点数 |
| `Min` | 该 output 的最小值 |
| `Target` | spec target |
| `Max` | 该 output 的最大值 |
| `Mean -K Sigma` | mean 减 K 倍 sigma；默认 K=3 |
| `Mean` | mean |
| `Mean +K Sigma` | mean 加 K 倍 sigma；默认 K=3 |
| `Std Dev` | 每个 corner 的统计/最坏值；ADE XL 和 Assembler 文档对“sample 还是 worst-case”表述不完全一致 |
| `CV(%)` | coefficient of variation |
| `Sigma To Target` | `(mean - target) / standard deviation`，默认隐藏 |
| `Cpk` | process capability index |
| `Errors` | 该 output 发生 simulation/evaluation error 的点数 |

来源：`doc/assembler/asmViewingResults.html:481-710`；`doc/adexl/adexlViewingResults.html:918-1080`；`doc/adexl/images/MonteC_Yield.gif`。

多 corner 的 summary row：

| 列 | 跨 corner 汇总 |
|---|---|
| `Yield` | 所有 corner 中的最小 yield |
| `Min` | 所有 corner 中的最小值 |
| `Max` | 所有 corner 中的最大值 |
| `Mean` | 各 corner 的 mean |
| `Cpk` | 最小 Cpk |
| `Errors` | error point 数 |

最顶部灰色行显示 overall yield estimate，是对所有 specification 的综合估计，不等同于某个 output 行。来源：`doc/adexl/adexlViewingResults.html:1040-1075`；`doc/assembler/asmViewingResults.html:650-730`。

#### 重要限制：`?testName` 不能用于 Yield view

`maeExportOutputView` 文档明确写：

- `?testName` 只支持 `Checks/Asserts` 和 `Fault` 结果视图。
- Yield view 的导出不能按 `?testName` 单独筛 test。

因此多 test MC 的 per-output 统计应导出完整 Yield view，然后按 CSV 的 `Test` 列分组。CSV 头部实际拼写仍需真机确认。

#### Detail CSV 的角色

`maeExportOutputView(?view "Detail")` 是逐 design point 的明细：

- MC sample 行名为 `Parameters: monteCarlo::param::sequence=n`；
- 行中有 Point、Test、Output、Value、Spec、Weight、Pass/Fail；
- 它适合核对单点、筛错误、重算 mean/sigma；
- 它不是官方现成的 per-output 统计表。

来源：`doc/adexl/adexlMC.html:231-235`；`doc/adexl/images/monteSampleResults.gif`；`src/pyapi/packages/maestro.py:1970-2035`。

#### 其他结果 API

| API | 作用 | 注意 |
|---|---|---|
| `maeOpenResults(?session s ?history h)` | 打开 history 结果指针 | 结果上下文是进程全局，应串行化 |
| `maeGetResultTests()` | 列出已打开结果的 test | 先 `maeOpenResults` |
| `maeGetResultOutputs([?testName t])` | 列出 output 名 | 不返回 mean/sigma |
| `maeGetOutputValue(output test)` | 取单点值 | 需要 point/test 上下文 |
| `maeGetSpecStatus(output test [?pointId n])` | 取 spec status | 用于 pass/fail，不是统计汇总 |
| `maeGetOverallSpecStatus([?verbose t])` | 整体 spec status | 可与 overall yield 交叉校验 |

### 3.4 `mcYieldTarget` / `mcYieldAlphaLimit` 如何参与 pass/fail

#### 先分清两层

1. **sample/output 的 pass/fail**：由 output spec 判定。Yield view 的每 spec yield = 通过的 sample 数 / 完成 sample 数。
2. **run 何时停止**：由 `mcStopEarly`、`mcStopMethod`、`mcYieldTarget`、`mcYieldAlphaLimit` 控制。

`mcYieldTarget` / `mcYieldAlphaLimit` **不直接给单个 sample 打 pass/fail**。

#### GUI 对应项

GUI 的 `Auto Stop using Yield Verification` 有两个输入：

| GUI 字段 | 官方语义 | 默认 |
|---|---|---|
| `Target Yield` | 设计希望达到的 target yield | 99.73% |
| `Probability (1-alpha)` | significance level，范围 50% 到 <100% | 95% |

停止逻辑：

```text
Confidence Level = 100 * (1 - alpha)
```

- 用 Clopper-Pearson 方法计算 binomial yield confidence interval。
- 若 yield estimate 的 upper bound < target，停止。
- 若 yield estimate 的 lower bound > target，停止。
- target 和 probability 会共同决定 `Max Number of Points`；若停止条件一直不满足，就跑满 max points。

来源：`doc/adexl/adexlMC.html:858-889`；`doc/vvoUG/envVars_re_yieldProbability.html:58-82`。

#### 内部 run option

`axlGetRunOptions(... "Monte Carlo Sampling")` 文档列出的 MC 选项包括：

```text
mcnumpoints mcnumbins samplingmode saveprocess savemismatch
mcreferencepoint donominal saveallplots montecarloseed
mcstartingrunnumber mcStopEarly mcStopMethod
mcYieldTarget mcYieldAlphaLimit
```

OCEAN XL 同名选项进一步说明：

- `mcYieldTarget` = Target yield percentage。
- `mcStopMethod` = 选择停止 MC 的方法。
- `mcYieldAlphaLimit` 在 OCEAN XL 参数表中没有单独描述。

因此可确认的映射：

```text
mcYieldTarget      -> GUI Target Yield
mcYieldAlphaLimit  -> 功能上对应 Probability (1-alpha) / significance/alpha
mcStopEarly        -> 是否启用 Auto Stop
mcStopMethod       -> 选择 Yield Verification / Worst Samples / K-Sigma 等停止法
```

但以下仍需真机确认：

- `mcYieldAlphaLimit` 内部值是 alpha（例如 0.05）还是 probability（例如 95）。
- `mcStopMethod` 的合法字符串值。
- 这些选项的版本存在性和 GUI 往返一致性。

来源：`doc/maeSKILLref/runRelated.html:3360-3392`；`doc/ocnxl/ocnxlcommands.html:7058-7072,7275-7290`。

### 3.5 `donominal` / nominal 点在结果中的体现

两条概念必须分开：

| 概念 | 作用 | 是否计入 MC 统计 |
|---|---|---|
| `donominal` / `Run Nominal Simulation` | 在 MC 主循环前先跑一次 nominal/reference point，作为预检 | 官方没有说它作为 `mcnumpoints` 中的一个 statistical sample 计数 |
| GUI `Nominal Corner` check box | 决定 nominal corner 是否参与本次 MC corner 集合 | 勾选则参与 corner 组合，不勾选则排除 |

官方说明：

- `Run Nominal Simulation` 勾选后，Spectre 在 MC 循环前跑 nominal simulation；若 nominal run 出错，MC 停止。
- 不勾选时，MC iteration 中发生错误会警告并继续下一个 iteration。
- 分布式 MC 时，nominal simulation 只由第一个提交的 job 执行。
- OCEAN XL 文档把 `donominal=1` 描述为“在 reference point 先跑仿真；若失败则不启动 sampling”。
- OCEAN XL 文档写其默认值为 1；GUI 上该选项表现为可选 checkbox。

来源：`doc/adexl/adexlMC.html:208-213`；`doc/ocnxl/ocnxlcommands.html:7190-7200`；`doc/assembler/asmMC.html:109-116`。

结果里如何看 nominal：

- MC Detail/Summary 的 statistical sample 行使用 `Parameters: monteCarlo::param::sequence=n`。
- 通用 Results 视图有 `Nominal` 列；它是 corner/条件语义。
- `donominal` 的预跑结果是否会单独出现在一个 MC CSV、是否被 Yield view 单独计数、在 `MonteCarlo.*.csv` 中如何命名，**官方文档没有写清，需真机确认**。
- 不要把 `donominal` 和 GUI `Nominal Corner` 当成同一个开关。

---

## 4. 约束与互斥

### 4.1 支持的模拟器

本地不同产品/页面的清单不完全一致：

| 文档 | 文档列出的 MC 支持范围 | 备注 |
|---|---|---|
| ADE XL `adexlMC.html` 总览 | Spectre、APS、AMS Designer with Spectre/APS solver | 明确禁止 AMS with UltraSim；AMS + interactive SimVision 不支持 |
| ADE XL `adexlMC.html` 运行步骤 | Spectre、APS、hspiceD、AMS Designer with Spectre | 这里额外出现 hspiceD，且 AMS solver 只写 Spectre |
| ADE Assembler `asmMC.html` 运行准备 | Spectre、APS、AMS Designer with Spectre | 当前 ADE Assembler 页面未列 hspiceD |

来源：`doc/adexl/adexlMC.html:100-114,129-134`；`doc/assembler/asmMC.html:105-112`。

工程上的安全结论：

- 对当前 ADE Assembler，优先限定 Spectre、APS、AMS-with-Spectre。
- hspiceD 只在部分 ADE XL 文档中出现，是否可用取决于 IC 版本/产品。
- UltraSim 明确不能用于 AMS Designer MC。
- AMS Designer + interactive SimVision 明确不支持 MC。
- 不支持模拟器时出现的精确错误码/文案，本地文档未找到，需真机确认。

### 4.2 MC 与 sweep/参数扫描互斥：ADEXL-1742

官方 `maeGetSimulationMessages` 示例给出完整错误：

```text
ERROR (ADEXL-1742): Cannot run 'Monte Carlo Sampling' with swept variable/parameters.
You are trying to run Monte Carlo with sweeps enabled. This is currently not supported.
Disable all sweeps or enable 'Use Reference Point' in the Monte Carlo options to continue.
```

同页还有：

```text
ERROR (ADEXL-1611): Sweep and Corners are using the same variables:...
```

来源：`doc/maeSKILLref/runRelated.html:610-634`。

#### `mcreferencepoint` / Use Reference Point 的作用

- GUI 文案：若已创建 reference point，并希望 MC points 围绕 reference point 采样，勾选 `Use Reference Point`。
- 勾选后必须确认 Run Summary 的 `# Point Sweeps` 被选中。
- ADEXL-1742 的修复建议明确包含 `enable 'Use Reference Point' in the Monte Carlo options`，说明它不是单纯的“优化起始点”选项，也是 sweep + MC 冲突的放行条件之一。
- OCEAN XL 把 `useReference` 描述为“use a schematic point or a reference point that you have created as a starting place”。

来源：`doc/adexl/adexlMC.html:208-210`；`doc/ocnxl/ocnxlcommands.html:7160-7170`；`doc/maeSKILLref/runRelated.html:630-633`。

尚未确认：

- 开启 `mcreferencepoint` 后，哪些 sweep 形式被允许、哪些仍被拒绝。
- 没有预先创建 reference point 时，`mcreferencepoint=1` 是报错、回退到 nominal，还是忽略。
- `# Point Sweeps` 与普通 sweep 的精确互斥/放行矩阵。

### 4.3 与 corner 的组合语义

可以确认：

- MC 可以跨多个 test 和多个 corner 运行。
- 在 Run Summary 勾选 `# Corners` 才会把已启用 corner 纳入 MC。
- 不想要 nominal corner 时，取消 `Nominal Corner` check box。
- Results 按 test、corner、output 报告，并给整个 circuit 一个 total yield。

来源：`doc/adexl/adexlMC.html:125-142,228-234`；`doc/assembler/asmMC.html:105-116,288-294`。

结果层的跨 corner 语义：

- 每个 spec 有一行 per-corner 结果，另有一个 summary row 跨 corner 汇总。
- `Yield` summary = 最小 corner yield。
- `Min` summary = 所有 corner 的最小值。
- `Max` summary = 所有 corner 的最大值。
- `Mean` summary = 各 corner mean。
- `Cpk` summary = 最小 Cpk。
- `Errors` = 对应 output 的错误点数。
- 顶部灰色行 = overall yield estimate，综合所有 specification。

来源：`doc/adexl/adexlViewingResults.html:918-1075`；`doc/assembler/asmViewingResults.html:481-730`。

文档存在一处统计口径冲突：

- ADE XL 页面把 summary 的 `Std Dev` 写成“worst case value of standard deviation as computed per corner”。
- ADE Assembler 页面把 summary 的 `Std Dev` 写成“sample standard deviation across all corners”。
- 因此“跨 corner 的 sigma 究竟如何汇总”在产品文档之间有差异，若上层要严格复现 Cadence 数字，应真机对拍。

### 4.4 output 未勾 Plot 是否参与统计

**不参与。**

官方明确：

```text
Disabled output expressions—expressions for which the Plot check box is not
selected in the Outputs Setup tab—will not be evaluated for Monte Carlo
simulations.
```

所以：

- 想让某 output 进入 Yield view、mean/sigma、pass/fail，必须勾 `Plot`。
- Save 与 Plot 是不同勾选框；不能把“保存波形/数据”与“参与 MC expression evaluation”混为一谈。
- 若某 test 一个 plotting output 都没有，会出现：

```text
(ADEXL-1617): Following tests do not have any outputs selected for plotting:
```

来源：`doc/adexl/adexlMC.html:133-135`；`doc/assembler/asmMC.html:109-112`；`doc/adexl/adexlSavingData.html:358-380`。

### 4.5 save 选项对产物体积的影响

| 选项 | GUI 名称 | 值/默认 | 产物影响 | 文档明确风险 |
|---|---|---|---|---|
| `saveallplots` | Save Data to Allow Family Plots | 0/1；OCEAN XL 默认 0 | `1`：保留每次 MC iteration 的 PSF 原始数据；`0`：expression 评估后删除 simulation data，只保留最后一次 iteration 的 PSF | `1` 时 raw data “can be considerably large”；可只保存 output expression 引用的节点/terminal 减小体积 |
| `saveprocess` | Save Process Data | 0/1；GUI 默认勾选，OCEAN XL 默认 1 | 把 process parameter 信息写入 ADE XL/Assembler results DB，支持 sensitivity results | 文档明确说大 process 变量数会增加 run time；**体积增量未量化** |
| `savemismatch` | Save Mismatch Data | 0/1；GUI 默认不勾选，OCEAN XL 默认 0 | 把 mismatch parameter 信息写入 results DB，支持 mismatch contribution analysis | 文档明确说大 mismatch 变量数会增加 run time；**体积增量未量化** |
| `donominal` | Run Nominal Simulation | 0/1；OCEAN XL 默认 1 | 额外先跑一次 nominal/reference simulation | 会多一次仿真开销；文档未量化磁盘体积 |

重要边界：

- 即使 `saveallplots=0`，scalar output results 仍会为每次 run 计算并保存；它影响的是 raw PSF/waveform data，不是 scalar MC 统计本身。
- `saveallplots=0` 时，signal/waveform expression 不能做 family plot，只能对 scalar expression 做 histogram。
- `saveprocess/savemismatch` 的文档证据主要指向 results DB 内容和 run time，不应把“体积影响”写成已量化的确定值。

来源：`doc/adexl/adexlMC.html:201-220`；`doc/ocnxl/ocnxlcommands.html:7110-7198`；`doc/maeSKILLref/chap7.html:5020-5023`。

### 4.6 错误码与典型文案

| 错误/状态 | 典型文案或含义 | 触发条件 | 来源 |
|---|---|---|---|
| `ERROR (ADEXL-1742)` | `Cannot run 'Monte Carlo Sampling' with swept variable/parameters... Disable all sweeps or enable 'Use Reference Point'` | MC 与 sweep/参数扫描同时启用 | `doc/maeSKILLref/runRelated.html:630-633` |
| `ERROR (ADEXL-1611)` | `Sweep and Corners are using the same variables` | sweep 与 corner 使用同名变量，可在 MC 场景同时出现 | `doc/maeSKILLref/runRelated.html:630-633` |
| `(ADEXL-1617)` | `Following tests do not have any outputs selected for plotting` | test 下没有 output 勾 Plot | `doc/adexl/adexlSavingData.html:377-380` |
| `ADEXL-1703` | 待运行 simulation 数超过阈值时的确认提示 | 超过 `warnWhenSimsExceed` | `doc/adexl/appEnvVars.html:3916` |
| 状态 `Canceled` | 用户 Stop、GUI 异常关闭、磁盘不足、Auto Stop target 达成、nominal 预跑失败 | 多种非正常/提前结束条件 | `doc/adexl/adexlSimulating.html:1563-1576` |
| `maeRunSimulation => nil` | 启动失败，但单条 `nil` 不告诉你根因 | 需要再查 `maeGetSimulationMessages` | `doc/maeSKILLref/runRelated.html:610-634` |

**未确认的报错：**

- 没有统计参数时的精确 error code/完整文案。
- 不支持 simulator 时的精确 error code/完整文案。
- `mcYieldTarget/mcYieldAlphaLimit` 取值非法的精确 error code/完整文案。

---

## 5. 建议的脚本调用流

下面是依据现有证据的保守流程，不代表已经真机验证：

```skill
;; 1. 必须使用 GUI Assembler session
session = axlGetWindowSession(hiGetCurrentWindow())

;; 2. 可选：确认/设置 job control
maeSetJobControlMode("ICRP" ?session session)

;; 3. 关键：显式指定 MC mode，启动
history = maeRunSimulation(
  ?session session
  ?runMode "Monte Carlo Sampling"
)
unless(history errset(printf("MC start failed\n") nil))

;; 4. 进度
done_total = axlGetRunStatus(
  session
  ?historyName history
  ?optionName "all"
)

;; 5. 完成后导出 per-output Yield view
maeExportOutputView(
  ?session session
  ?historyName history
  ?view "Yield"
  ?fileName "/tmp/mc-yield.csv"
)

;; 6. overall yield
maeGetOverallYield(history session)

;; 7. 仅在真机确认参数名和列头后，再调用 MC 原始 CSV
;; axlWriteMonteCarloResultsCSV(
;;   session history
;;   ?testName "..." ?cornerName "..."
;;   ?outputPath "/tmp/mc-csv/"
;; )
```

不推荐把以下形式当成 MC 启动：

```skill
maeSetCurrentRunMode(?runMode "Monte Carlo Sampling")
maeRunSimulation()  ;; 默认值风险：官方写的是 Single Run, Sweeps and Corners
```

如果版本实测证明裸 `maeRunSimulation()` 确实沿用 current mode，应把该结论写成“特定 IC 版本实测”，而不是官方通用语义。

---

## 6. 已确认项

| # | 已确认 |
|---|---|
| 1 | `maeSetCurrentRunMode` 是更新当前 runMode；`maeRunSimulation(?runMode ...)` 是设置 mode 并启动 |
| 2 | `maeRunSimulation` 的 `?runMode` 官方默认值是 Single Run |
| 3 | `?run` 用于 Run Plan；`"All"` 表示 plan 内全部 run |
| 4 | `?callback` 是完成后回调；`?waitUntilDone` 默认 nil；`?returnRunId` 默认返回 history |
| 5 | history 格式是 `runType.seqNum`，同一 runType 从 0 开始递增 |
| 6 | 点进度官方 option 是 `all`，另有 `Tests`、`Corners`；返回 `(done total)` |
| 7 | overall yield 示例字段是 `Yield`、`PassedPoints`、`ErrorPoints` |
| 8 | per-output 统计应看 Yield view；未勾 Plot 的 output 不参与 MC 评估 |
| 9 | MC+sweep 冲突 code 是 ADEXL-1742；修复选项包括禁用 sweeps 或启用 Use Reference Point |
| 10 | `saveallplots=1` 会保留每次 iteration 的 PSF，体积可显著增大 |

## 7. 未确认/需真机项

| # | 未确认项 | 为什么需要真机 |
|---|---|---|
| 1 | 裸 `maeRunSimulation()` 是否沿用已设置的 current MC mode | 官方默认值写 Single Run；仓库旧报告与之冲突 |
| 2 | `axlWriteMonteCarloResultsCSV` 的实际参数名是 `?outputName` 还是 `?outputPath` | 正式语法和同页示例冲突 |
| 3 | MC CSV 文件头、列顺序、长/宽表、单位和空值表示 | 文档没有打开后的 CSV 样例 |
| 4 | `maeGetOverallYield` 返回列表第一个裸 `nil` 的含义 | 官方页未解释 |
| 5 | `mcYieldAlphaLimit` 内部用 alpha 还是 probability，以及 `mcStopMethod` 合法值 | 内部 option 表只列名称/部分描述 |
| 6 | `donominal` 预跑结果是否出现在 MC CSV/Yield 统计及如何命名 | 文档只描述预跑行为，没有结果布局 |
| 7 | `mcreferencepoint=1` 时允许哪些 swept variable/parameter 组合 | 文档只说明冲突放行方向，没有矩阵 |
| 8 | 跨 corner 的 `Std Dev` 汇总口径 | ADE XL 与 Assembler 文档表述不同 |
| 9 | hspiceD 在当前 ADE Assembler/IC 版本是否支持 MC | 不同产品页面的 simulator 清单不一致 |
| 10 | 后台 session 的 MC 导出/运行可靠性是否随 IC 版本变化 | API 签名允许 session，但仓库只在 IC6.1.8 上记录过后台 run 失败 |

---

## 8. 证据索引

### 本地 Cadence 文档

- `doc/maeSKILLref/runRelated.html:868-1140`：`maeRunSimulation`、`axlGetRunStatus`、单点状态
- `doc/maeSKILLref/runRelated.html:610-634`：`maeGetSimulationMessages` 与 ADEXL-1611/1742 示例
- `doc/maeSKILLref/runRelated.html:1380-1570`：`maeSetRunOption` 与 run option
- `doc/maeSKILLref/runRelated.html:3300-3392`：`axlGetRunOptions`
- `doc/maeSKILLref/maestroSKILL.html:6298-6464`：`maeOpenSetup`
- `doc/maeSKILLref/maestroSKILL.html:8572-8642`：`maeSetCurrentRunMode`
- `doc/maeSKILLref/maestroSKILL.html:10859-11052`：`maeExportOutputView`
- `doc/maeSKILLref/maestroSKILL.html:11622-11734`：`maeGetResultOutputs`、`maeGetResultTests`
- `doc/maeSKILLref/maestroSKILL.html:11750-11834`：`maeGetResultsViewSelectedCellsDetails`
- `doc/maeSKILLref/maestroSKILL.html:12167-12238`：`maeGetOverallYield`
- `doc/maeSKILLref/maestroSKILL.html:12447-12570`：`maeOpenResults`
- `doc/maeSKILLref/historyRelated.html:2488-2619`：`axlWriteMonteCarloResultsCSV`
- `doc/maeSKILLref/historyRelated.html:746`：`MonteCarlo.0` 反查 run mode
- `doc/assembler/asmCheckpoints.html:217-225`：`runType.seqNum` history 命名
- `doc/assembler/asmViewingResults.html:481-730`：ADE Assembler Yield view 列与 summary
- `doc/assembler/asmMC.html:100-116,658-678`：ADE Assembler MC 前置条件与 CSV 导出
- `doc/adexl/adexlMC.html:100-235`：simulator、运行步骤、reference point、donominal、Plot gating
- `doc/adexl/adexlMC.html:858-889`：Target Yield / Probability / Auto Stop
- `doc/adexl/adexlMC.html:1690-1704`：MC CSV 导出说明
- `doc/adexl/adexlViewingResults.html:918-1080`：ADE XL Yield view
- `doc/adexl/adexlSavingData.html:358-380`：ADEXL-1617
- `doc/adexl/adexlSimulating.html:1563-1576`：`Canceled` 状态原因
- `doc/ocnxl/ocnxlcommands.html:7042-7290`：OCEAN XL 同名 MC options
- `doc/vvoUG/envVars_re_yieldProbability.html:58-82`：yield probability 环境变量
- `doc/adexl/images/adexlMC-65.gif`：Export Monte Carlo Data to CSV 表单
- `doc/adexl/images/adexlMC-66.gif`：CSV 文件名列表
- `doc/adexl/images/MonteC_Yield.gif`：Yield view 列
- `doc/adexl/images/monteSampleResults.gif`：MC Detail/sample 行

### 文档检索服务

- `/api/info?name=maeRunSimulation`
- `/api/info?name=maeSetCurrentRunMode`
- `/api/info?name=axlSetCurrentRunMode`
- `/api/info?name=axlGetRunStatus`
- `/api/info?name=axlWriteMonteCarloResultsCSV`
- `/api/info?name=maeGetOverallYield`
- `/api/info?name=maeOpenResults`
- `/api/info?name=maeExportOutputView`
- `/api/info?name=ocnxlMonteCarloOptions`

### 仓库内证据

- `doc/report/机制-maestro-GUI与后台会话冲突.md`：GUI/后台 session 实测
- `doc/report/maestro-蒙卡能力调查.md`：旧调查；其中“裸 `maeRunSimulation()` 沿用当前 mode”未被本次独立核实支持
- `src/pyapi/packages/maestro.py:399-416`：`_open_session` 使用 `maeOpenSetup`
- `src/pyapi/packages/maestro.py:1870-2035`：`read_results` Detail CSV + `maeGetOverallYield`
- `src/pyapi/packages/maestro.py:2946-2953`：GUI session + ICRP + 裸 `maeRunSimulation`
- `src/pyapi/packages/_maestro_util.py:286-315`：overall yield 列表解析

