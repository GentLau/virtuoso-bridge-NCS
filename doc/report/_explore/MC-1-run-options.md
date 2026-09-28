# MC-1：Cadence 蒙卡（Monte Carlo）run option 调研

日期：2026-09-28  
范围：只读调研；未连接 Virtuoso/ADE，未启动或操作任何仿真。  
本地文档根目录：`C:\Users\user\Desktop\doc`  
项目：`C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS`

本文把“run option”限定为 ADE setup database 中
`axlGetRunOptions(x_hsdb, "Monte Carlo Sampling")` 返回的选项集合。
`ocnxlMonteCarloOptions` 是 OCEAN XL 对同一能力的另一套调用接口，用作值域和语义交叉核对；
它多出来的参数不自动等同于 ADE run option。

---

## 0. 结论摘要

1. `maeSKILLref` 的 `axlGetRunOptions` 官方示例确认 MC run option 集合正好是 17 项：
   `dutsummary`、`ignoreflag`、`mcmethod`、`mcnumpoints`、`mcnumbins`、
   `mcStopEarly`、`mcStopMethod`、`samplingmode`、`saveprocess`、`savemismatch`、
   `mcreferencepoint`、`donominal`、`saveallplots`、`montecarloseed`、
   `mcstartingrunnumber`、`mcYieldTarget`、`mcYieldAlphaLimit`。
   （来源：`doc/maeSKILLref/runRelated.html`，`axlGetRunOptions` 示例，行 3385-3390）

2. 这 17 项都不是“每次调用必须显式传入”的 API 参数；它们都能存在于 setup database 中。
   但固定点数、自动停止、良率验证、保存统计参数等模式在语义上仍要求相应选项有效。

3. 读写的底层主路径是：
   - 枚举：`axlGetRunOptions(x_hsdb, "Monte Carlo Sampling")`
   - 取句柄：`axlGetRunOption(x_hsdb, "Monte Carlo Sampling", t_runoptName)`
   - 读值：`axlGetRunOptionValue(x_runOption)`
   - 建/改句柄：`axlPutRunOption(x_hsdb, "Monte Carlo Sampling", t_runoptName)`
   - 写值：`axlSetRunOptionValue(x_runOption, t_runOptionValue)`
   （来源：`doc/maeSKILLref/runRelated.html`，上述函数）

4. `maeSetRunOption` 是较上层入口，但其官方文档对
   `"Monte Carlo Sampling"` 只列出 `mcmethod` 和 `mcnumpoints` 两项。
   因此：这两项可以用 `maeSetRunOption` 明确写；另外 15 项是否也被它接受，
   当前文档没有保证，**未确认**。其余项目前应以 `axlPutRunOption` +
   `axlSetRunOptionValue` 为通用路径，但这不是“15 项全部已验证可写”的保证。
   （来源：`doc/maeSKILLref/runRelated.html`，`maeSetRunOption`，行 1436-1509）

5. MC 能否真正跑起来，不只取决于 run option。至少还依赖：
   模型/网表中的 `statistics { ... }` 统计块、`process`/`mismatch` 统计参数、
   支持 MC 的模拟器、输出表达式的 `Plot` 勾选，以及 ADE 的运行模式。

6. 最常见的版本冲突集中在：
   - `mcmethod` 的 `global` 与 `process` 两种命名；
   - `samplingmode` 的 `random`、`standard`、`lds`、`orthogonal` 之间的映射；
   - `mcnumpoints` 默认值 100 与 ADE Explorer GUI 默认 200；
   - `saveprocess`/`savemismatch` 的 GUI 默认与环境变量默认不一致；
   - `mcStopEarly`、`mcStopMethod`、`mcYieldTarget`、`mcYieldAlphaLimit`
     的底层枚举/数值编码没有在本地文档中完整给出。

7. 命令行/脚本层面设置 MC 时，最后还应显式指定运行模式：
   `axlSetCurrentRunMode(sdb, "Monte Carlo Sampling")` 或
   `maeRunSimulation(?runMode "Monte Carlo Sampling")`。
   （来源：`doc/maeSKILLref/runRelated.html`，`axlSetCurrentRunMode`、
   `maeRunSimulation`）

---

## 1. 完整 run option 表

### 1.1 采样、点数、DUT 范围

| # | 选项 | 含义 | 类型/值域 | 默认值 | 是否必填 | 底层设置 API | 文档出处 |
|---:|---|---|---|---|---|---|---|
| 1 | `mcmethod` | 统计变化方法：只 process、只 mismatch，或二者都用。 | SKILL 字符串。OCEAN XL 列 `global / mismatch / all`；`maeSKILLref`第 7 章和 Spectre 列 `process / mismatch / all`。两种命名存在冲突，需真机读回确认。 | OCEAN XL 文档明确：`all`。 | 不是 API 必填；但必须与模型中的统计块匹配。 | `axlGetRunOption` + `axlSetRunOptionValue`；`maeSetRunOption` 官方列出此项。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7089-7095；`doc/maeSKILLref/chap7.html` — `asiGetAvailableMCOptions`，行 5012；`doc/spectreuser/chap7.html` — `montecarlo` 参数，行 8555-8557 |
| 2 | `mcnumpoints` | 固定点数 MC 采样点数；Spectre 原生命中为 `numruns`，不含 nominal。 | SKILL 字符串承载整数；应为正整数，文档未给出上限。 | **冲突**：OCEAN XL 文档 `100`；Spectre 原生 `numruns` 默认 `100`；ADE Explorer 2023 GUI 文档和截图显示 `200`。 | 不是 API 必填；在“Run a fixed number of points”模式语义上必须有有效点数。`maeSetRunOption` 文档建议通常不少于统计变量数。 | `axlGetRunOption` + `axlSetRunOptionValue`；`maeSetRunOption` 官方列出此项。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7097-7103；`doc/maeSKILLref/runRelated.html` — `maeSetRunOption`，行 1505-1509；`doc/Explorer/chap8.html` — “Performing a Standard Monte Carlo Run”，行 200-201；`doc/spectreuser/chap7.html` — `numruns`，行 8538-8541、15901 |
| 3 | `mcnumbins` | LHS（或 OCEAN/Spectre 文档中的 orthogonal）分箱数。 | SKILL 字符串承载整数或空串；`""` 表示由模拟器决定。 | OCEAN XL 明确：`""`；Spectre 原生 `numbins=0`。 | 仅 LHS/相关分箱采样时有意义；不是固定点数模式下必须显式设置。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7241-7249；`doc/Explorer/chap8.html` — “Number of Bins”，行 194-198；`doc/spectreuser/chap7.html` — `numbins`，行 8560-8565 |
| 4 | `samplingmode` | 采样算法。 | **冲突/未统一**：OCEAN XL 为 `random / orthogonal / lhs`，默认 `random`；`maeSKILLref`第 7 章为 `standard / lhs`；Spectre 原生为 `standard / lhs / lds / orthogonal`；ADE 2023 GUI 为 `Random / Latin Hypercube / Low-Discrepancy Sequence`，高级表单截图默认 LDS。`random` 与 `standard`、`orthogonal` 与 `lds` 的映射未由本地文档明确给出。 | OCEAN XL 文档：`random`；ADE 环境变量 `adexl.monte samplingMethod` 默认 `lds`；Spectre 原生默认 `standard`。 | 不是 API 必填；GUI 语义上必须选择一个采样方法。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7105-7113；`doc/maeSKILLref/chap7.html` — `asiGetAvailableMCOptions`，行 5016；`doc/spectreuser/chap7.html` — `sampling`，行 8561-8565；`doc/adexl/appEnvVars.html` — `adexl.monte samplingMethod`，行 7205-7311 |
| 5 | `montecarloseed` | 随机数种子；固定 seed 有助于复现实验。 | SKILL 字符串承载整数。文档未给出完整取值范围。 | `12345`。 | 否；不设置时使用默认 seed。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7175-7179；`doc/Explorer/chap8.html` — “Seed”，行 261；`doc/adexl/adexlMC.html` — “Monte Carlo Seed”，行 221-225 |
| 6 | `mcstartingrunnumber` | MC 起始迭代号；Spectre 原生命中为 `firstrun`。 | SKILL 字符串承载整数；文档示例为 `1`。 | `1`。 | 否。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7185-7189；`doc/spectreuser/chap7.html` — `firstrun`，行 8542-8545、15931；`doc/Explorer/chap8.html` — “First Point”，行 262-263 |
| 7 | `dutsummary` | 指定 mismatch 变化作用的 DUT 实例/器件列表。 | SKILL 字符串；OCEAN XL 格式为 `testname%instances%Lib/Cell/View%Master#testname%instances%modelname%Subcircuit...`；多个条目用 `#` 分隔。 | `""`，即不额外限定；ADE 用户文档说明默认会把 mismatch 应用到全部 subcircuit 实例。 | 否；只有需要收窄/枚举 mismatch 实例时才设置。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7195-7207；`doc/adexl/adexlMC.html` — “Specifying Instances for Monte Carlo Mismatch and Process Variation”，行 395-412；`doc/assembler/asmMC.html` — “Setting Run Options…”，行 170-180 |
| 8 | `ignoreflag` | 与 `dutsummary` 配合：置 `1` 时，不对 `dutsummary` 指定的实例及其下层实例应用 mismatch。 | 字符串 `0` 或 `1`；语义为布尔值。 | `0`。 | 否；“排除指定实例”时才设为 `1`。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7229-7238；`doc/maeSKILLref/chap7.html` — `asiGetAvailableMCOptions`，行 5034 |

### 1.2 参考点、nominal 与保存选项

| # | 选项 | 含义 | 类型/值域 | 默认值 | 是否必填 | 底层设置 API | 文档出处 |
|---:|---|---|---|---|---|---|---|
| 9 | `mcreferencepoint` | 是否从 reference point 周围采样。OCEAN XL 对应参数名为 `?useReference`。键名映射由语义和 GUI “Use Reference Point”推得，官方表格没有把两个名字逐字对应。 | 字符串 `0` 或 `1`；OCEAN XL `useReference` 明确为 0/1。 | OCEAN XL `useReference`：`0`。ADE GUI 默认未勾选。 | 否；启用时必须先有 reference point，且 ADE XL 文档要求 `# Point Sweeps` 勾选。 | `axlGetRunOption` + `axlSetRunOptionValue`；reference point 本身可通过 `ocnxlStartingPoint` 或 GUI 创建。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7150-7161；`doc/adexl/adexlMC.html` — “Use Reference Point”，行 208-209；`doc/ocnxl/ocnxlcommands.html` — `ocnxlStartingPoint` |
| 10 | `donominal` | MC 主循环前是否先跑 nominal；nominal 失败时是否阻止 MC 继续。 | 字符串 `0` 或 `1`；Spectre 原生命中为 `yes/no`。 | `1`（OCEAN XL 明确；Spectre 原生 `yes`）。ADE GUI 默认勾选 “Run Nominal Simulation”。 | 否；不设置时沿用默认 nominal 行为。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7163-7172；`doc/adexl/adexlMC.html` — “Run Nominal Simulation”，行 210-212；`doc/spectreuser/chap7.html` — `donominal`，行 8881-8883 |
| 11 | `saveprocess` | 是否把 process 统计参数保存到结果数据库；保存后可做 sensitivity 等后处理。 | 字符串 `0` 或 `1`。 | **冲突**：OCEAN XL 明确为 `1`；ADE XL GUI 文档称“默认选中”；但 `adexl.monte saveProcessOptionDefaultValue` 环境变量章节的 `.cdsenv` 示例/默认值写的是 `nil`。 | 否；需要 process 后处理时建议开启。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7129-7138；`doc/adexl/adexlMC.html` — “Save Process Data”，行 201-204；`doc/adexl/appEnvVars.html` — `saveProcessOptionDefaultValue`，行 7319-7402 |
| 12 | `savemismatch` | 是否把 mismatch 统计参数保存到结果数据库；mismatch contribution、values-based statistical corner 需要它。 | 字符串 `0` 或 `1`。 | OCEAN XL 明确为 `0`；ADE GUI 文档称默认未选；`adexl.monte saveMismatchOptionDefaultValue` 的文字说明也为默认清除。注意该环境变量示例行写成 `boolean t`，但后面的 Default Value 仍是 `nil`，存在排版/版本冲突。 | 否；需要 mismatch 后处理时建议开启。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7139-7148；`doc/adexl/adexlMC.html` — “Save Mismatch Data”，行 205-207；`doc/adexl/appEnvVars.html` — `saveMismatchOptionDefaultValue`，行 7519-7613 |
| 13 | `saveallplots` | 是否为每次 MC 迭代保存原始 `psf` 数据，以支持 family plots、打印/标注/重评估。 | 字符串 `0` 或 `1`。 | `0`；Spectre 原生 `savefamilyplots=no`。 | 否。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7119-7123；`doc/adexl/adexlMC.html` — “Save Data to Allow Family Plots”，行 213-220；`doc/spectreuser/chap7.html` — `savefamilyplots`，行 8941-8945 |

### 1.3 提前停止与良率选项

| # | 选项 | 含义 | 类型/值域 | 默认值 | 是否必填 | 底层设置 API | 文档出处 |
|---:|---|---|---|---|---|---|---|
| 14 | `mcStopEarly` | 是否启用 auto stop。GUI 对应 “Auto Stop” 复选框。 | 本地文档只给出名字，未给出底层枚举/类型。GUI 呈现为复选框，因此可能是布尔型，但具体是 `0/1`、`t/nil` 还是其他编码**未确认**。 | 未确认。GUI 默认表单显示未勾选；不能据此断言 setup database 的底层默认值。 | 否；只有使用自动停止/良率验证时语义上需要开启。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions` 签名，行 7067；`doc/adexl/adexlMC.html` — “Auto Stop”，行 185-200；`doc/Explorer/chap8.html` — “Auto Stop”，行 459-473 |
| 15 | `mcStopMethod` | 选择自动停止方法。OCEAN XL 文档仅写“Sets the statistical variation method to stop Monte Carlo”，没有列枚举。 | 未确认。GUI/用户文档中的候选方法包括：`Yield Verification`、`Yield Verification - Autostop`、`Yield Verification - Sample Reorder`、`Sensitivity Accuracy`、`Worst Samples`、`K-Sigma Corners`、`Scaled-Sigma Sampling`、`Worst Case Distance`、`Confidence Interval - Autostop`。这些是否是底层字符串值**未确认**。 | 未确认；GUI 默认方法为 `Standard Monte Carlo`，即不自动停止。 | 否；`mcStopEarly` 开启时语义上需要选择方法。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions`，行 7285-7290；`doc/Explorer/chap8.html` — “Method” 下拉，行 241-247、459-764；`doc/adexl/adexlMC.html` — “Auto Stop Using”，行 181-192 |
| 16 | `mcYieldTarget` | 良率验证/自动停止的目标良率。GUI 里可以是百分比或 sigma 的同步显示。 | 未确认底层编码：可能是百分数字符串，也可能是 sigma 字符串；文档没有把 run option 与 GUI 字段逐项对应。 | GUI 文档存在版本差异：ADE XL 2022 的 Target Yield 默认 `99.73%`；ADE Explorer 2023 的 guided mode 写 sigma 默认 `3`、百分比默认 `99.865`。因此不能确认该 run option 的固定默认值。 | 否；Yield Verification、Worst Samples 等良率/角点方法需要。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/adexl/adexlMC.html` — “Target Yield”，行 859-868；`doc/Explorer/chap8.html` — “Target Yield”，行 459-470；`doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions` 签名，行 7068 |
| 17 | `mcYieldAlphaLimit` | 良率验证的显著性/概率限制。GUI 对应 `Probability (1-alpha)` 字段。 | 未确认底层编码。GUI 文档明确可用范围是 50% 到 100%（不含 100%），默认 95%。该 run option 到底保存 `95`、`0.95` 还是 `0.05`（alpha）本地文档没有说明。 | 未确认；GUI 默认 `95%`。`adexl.monte yieldProbability` 的 Default Value 也写 `95.0`，但 `.cdsenv` 示例行同时出现 `90`，存在文档不一致。 | 否；Yield Verification 类自动停止需要。 | `axlGetRunOption` + `axlSetRunOptionValue`。 | `doc/adexl/adexlMC.html` — “Probability (1-alpha)”，行 859-868；`doc/adegxl/adeGXLMCPostProc.html` — “Probability (1-alpha)”，行 84-85；`doc/adexl/appEnvVars.html` — `yieldProbability`，行 20124-20240；`doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions` 签名，行 7069 |

---

## 2. 17 项之外的 MC 依赖项（非 run option）

以下设置不在上述 17 个 run option 中，但决定 MC 是否能运行、结果是否有意义。

| 依赖项 | 在哪设 | 关键约束/值 | 与 MC 的关系 | 出处 |
|---|---|---|---|---|
| 运行模式 | ADE `Run` 菜单选 `Monte Carlo Sampling`；SKILL 用 `axlSetCurrentRunMode`、`maeRunSimulation(?runMode ...)`、OCEAN XL `ocnxlRun(?mode 'monteCarlo)`。 | 模式名必须精确；ADE Explorer 的 `maeRunSimulation` 文档限定可设 `"Single Run, Sweeps and Corners"` 或 `"Monte Carlo Sampling"`。 | run option 只在 MC run mode 下生效。 | `doc/maeSKILLref/runRelated.html` — `maeRunSimulation`、`axlSetCurrentRunMode`；`doc/ocnxl/ocnxlcommands.html` — `ocnxlRun` |
| 模拟器 | Data View 中 test 的 simulator / High-Performance Simulation Options。 | ADE XL 2022 文档列 Spectre、APS、hspiceD、AMS Designer with Spectre solver；ADE Assembler 2023 文档列 Spectre、APS、AMS Designer with Spectre solver；ADE Explorer 2023 还允许 AMS Designer with APS solver。文档版本间有差异。 | MC 只由支持的模拟器执行；不支持的模拟器不能靠 run option 绕过。 | `doc/adexl/adexlMC.html` — “Running a Monte Carlo Analysis”，行 104-134；`doc/assembler/asmMC.html` — 行 104-111；`doc/Explorer/chap8.html` — 行 120-157 |
| 统计模型 | 模型文件中的 Spectre `statistics { process { ... } mismatch { ... } }`；文件通过 Model Library Setup 指定。 | 至少要有 process 或 mismatch 之一的分布；也可以二者都有。支持 `dist=`、`std=`、`correlate`、`truncate` 等。 | `mcmethod` 选择 process/mismatch/all 后，模型必须能响应该类变化，否则没有有意义的统计结果。 | `doc/spectreuser/chap7.html` — “Monte Carlo Analysis”“Specifying Parameter Distributions Using Statistics Blocks”，行 8435-8500、9176-9500；`doc/adexl/adexlMC.html` — 行 180；`doc/Explorer/chap8.html` — 行 238 |
| 统计变化方法 | MC 表单的 `Statistical Variation` / `Variation`；底层 run option `mcmethod`。 | Process / Mismatch / All（GUI）；底层命名有 `global` vs `process` 冲突。 | 决定实际施加哪类统计变化。 | 同上；`doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions` |
| mismatch 实例范围 | MC 表单 `Specify Instances/Devices`；底层 `dutsummary` + `ignoreflag`。 | 不指定时默认对全部 subcircuit 实例应用 mismatch；可包含或排除指定实例/器件，且不能同时做 include 和 exclude。 | 决定哪些实例得到 per-instance mismatch。 | `doc/adexl/adexlMC.html` — 行 395-552；`doc/assembler/asmMC.html` — 行 170-180；`doc/ocnxl/ocnxlcommands.html` — `ocnxlMonteCarloOptions` 的 `dutSummary`/`ignoreFlag` |
| 相关性约束 | Constraint Manager；或 Spectre `statistics { correlate ... }`。 | 参数间相关系数、匹配器件对等。 | 影响采样变量的联合分布，从而影响 MC 结果。 | `doc/adexl/adexlMC.html` — 行 125-135；`doc/assembler/asmMC.html` — 行 106-111；`doc/spectreuser/chap7.html` — `correlate`，行 9468-9494 |
| 输出表达式/Plot | Outputs Setup 中每个 output 的 `Plot` 复选框。 | 未勾选 `Plot` 的表达式不会在 MC 中评估。 | 没有有效 output，就没有可用于 histogram/yield 的测量结果。 | `doc/adexl/adexlMC.html` — 行 134；`doc/assembler/asmMC.html` — 行 109-111；`doc/Explorer/chap8.html` — 行 123-125 |
| specifications / yield 判据 | Outputs Setup 的 spec；Yield/Spec 相关设置。 | yield 是对 output 与 spec 的 pass/fail 统计；高级方法还依赖目标良率/概率。 | 没有 spec，就无法计算 yield；Target Yield 等 run option 只对良率模式有意义。 | `doc/adexl/adexlMC.html` — yield view 与 target yield 章节，行 859-888；`doc/Explorer/chap8.html` — 行 439-470 |
| corners | Run Summary 的 `# Corners`、`Nominal Corner`；OCEAN XL `ocnxlRun(?allCornersEnabled ... ?nominalCornerEnabled ...)`。 | 选择是否在多 corner 上跑以及是否含 nominal corner。 | MC 可以对多个 corner 运行；nominal corner 的选择与 `donominal` 不是同一设置。 | `doc/adexl/adexlMC.html` — 行 129-138；`doc/ocnxl/ocnxlcommands.html` — `ocnxlRun` 参数 |
| sweeps / point sweeps | Run Summary 的 `# Point Sweeps` 等；OCEAN XL `ocnxlRun(?allSweepsEnabled ...)`。 | ADE XL/旧 `maeRunSimulation` 相关示例（`maeGetSimulationMessages` 读出）明确：带 swept variable/parameter 的 MC 默认不支持，除非关闭 sweeps 或启用 `Use Reference Point`；ADE Explorer 2023 又写明 Standard Monte Carlo 可以与 sweep values 一起跑，但高级方法不行。**这是文档版本/产品差异，不是可以用本文推断的单一结论。** | 决定 MC 是否跨 sweep 点运行，以及是否与 reference point 联动。 | `doc/maeSKILLref/runRelated.html` — `maeGetSimulationMessages` 示例，行 633（`ADEXL-1742`）；`doc/Explorer/chap8.html` — “Running Monte Carlo with Sweep Values”，行 353-366；`doc/adexl/adexlMC.html` — 行 208-209 |
| reference point | GXL/Explorer 的 reference point 设置；OCEAN XL `ocnxlStartingPoint`；底层 `mcreferencepoint`。 | 需要已创建的 reference point；ADE XL 文档要求 `# Point Sweeps` 勾选。 | 用于采样起点、也是旧文档中 MC+sweeps 的规避路径。 | `doc/adexl/adexlMC.html` — 行 208-209；`doc/ocnxl/ocnxlcommands.html` — `ocnxlStartingPoint` |
| statistical corners | MC 表单 `Create Statistical Corners` / 结果后处理；环境变量 `createStatisticalCornerType`。 | `auto`、`sequence`、`values`、`prompt`、`promptValues`；values-based corner 需要保存 statistical parameter data。 | 不是每次 MC 必需；但如果要自动/交互创建 statistical corner，就需要相应保存选项。 | `doc/adexl/adexlMC.html` — 行 1020-1070、1155-1160；`doc/adexl/appEnvVars.html` — `createStatisticalCornerType`，行 6584-6720；`doc/assembler/asmMC.html` — 行 495-553 |
| 许可证 | Standard MC 可用 ADE Explorer 许可；高级 VVO/良率方法需要 Virtuoso Variation Option。 | ADE Explorer 2023：无 VVO 时仅 Standard Monte Carlo 和 Yield Verification - Autostop；Assembler 文档称 advanced/high-yield 需额外 VVO。 | 决定 `mcStopMethod` 中的高级方法能否使用。 | `doc/Explorer/chap8.html` — 行 157、372、448、535、708；`doc/assembler/asmMC.html` — 行 69、1074-1090 |
| 多技术模式 | MTS 相关设置；每块独立的 model library。 | 可选；不同 MTS block 可以有不同统计/process 参数。 | 影响统计参数作用范围和后处理中的参数命名。 | `doc/assembler/asmMC.html` — “Running Multi-Technology Simulations for Monte Carlo Analysis”，行 299-370 |
| 额外 netlist 选项 | MC 表单 `Netlist Options`；环境变量 `adexl.monte additionalNetlistOptions`。 | 例：`nullmfactorcorrelation=yes`。 | 直接改变生成的 Spectre MC netlist 行为，不属于 17 个 run option。 | `doc/Explorer/chap8.html` — 行 267-270；`doc/adexl/appEnvVars.html` — `additionalNetlistOptions`，行 6396-6460 |

### 2.1 与 Spectre 原生 `montecarlo` 参数的对应关系

这不是 ADE run option API，而是理解这些 run option 最终落到哪里的交叉核对。

| ADE/OCEAN run option | Spectre 原生参数（`montecarlo` 语句） | 说明 | 出处 |
|---|---|---|---|
| `mcmethod` | `variations=` | OCEAN 的 `global` 与 Spectre 的 `process` 命名不同。 | `doc/spectreuser/chap7.html` — `Monte Carlo Analysis Parameters`，行 8555-8557 |
| `mcnumpoints` | `numruns=` | 默认 100。 | 同上，行 8538-8541 |
| `mcstartingrunnumber` | `firstrun=` | 默认 1。 | 同上，行 8542-8545 |
| `mcnumbins` | `numbins=` | 默认 0；有效值按 `max(numbins, numruns + firstrun - 1)` 处理。 | 同上，行 8560-8565 |
| `samplingmode` | `sampling=` | 支持 `standard / lhs / lds / orthogonal`。 | 同上，行 8561-8565 |
| `montecarloseed` | `seed=` | 可选 seed。 | 同上，行 8567-8570 |
| `saveprocess` | `saveprocessparams=` | `yes/no`。 | 同上，行 8743 附近 |
| `savemismatch` | `savemismatchparams=` | `yes/no`。 | 同上，行 8799 附近 |
| `donominal` | `donominal=` | 默认 `yes`。 | 同上，行 8881-8883 |
| `saveallplots` | `savefamilyplots=` | 默认 `no`。 | 同上，行 8941-8945 |
| `dutsummary` / `ignoreflag` | `dut=[...]` / `ignore=[...]` | 语义对应，不是逐字同名。 | 同上，行 8600-8635 |

---

## 3. 值域/默认值的权威来源对照

### 3.1 来源口径

| 来源 | 版本/日期 | 它能回答什么 | 局限 |
|---|---|---|---|
| `doc/maeSKILLref/runRelated.html` | IC6.1.8，2023-10 | 17 个 run option 的完整键名；`axl*` 读写函数；`maeSetRunOption` 文档 | 仅对 `mcmethod`、`mcnumpoints` 给出 MC 的显式值域；默认值没有逐项列出 |
| `doc/ocnxl/ocnxlcommands.html` | IC6.1.8，2023-04 | 同名/近名 OCEAN XL 参数的含义、默认值和部分枚举 | 不是 ADE run option 的结构表；部分参数没有描述；键名大小写不同 |
| `doc/maeSKILLref/chap7.html` | IC6.1.8，2023-10 | `asiGetAvailableMCOptions`/`asiGetSupportedMCOptions` 的旧接口值域 | 故意保留旧命名，出现 `process`、`standard` 等与 OCEAN 2023 不同叫法 |
| `doc/adexl/adexlMC.html` | IC6.1.8，2022-03 | GUI 操作、nominal/reference/save、target yield/probability 的默认与限制 | 较旧，默认采样方法/点数与 Explorer 2023 GUI 可能不同 |
| `doc/assembler/asmMC.html` | IC6.1.8，2023-10 | Assembler 的 MC 表单、advanced methods、VVO 依赖 | 直接使用 Explorer 章节作为表单细节来源 |
| `doc/Explorer/chap8.html` | IC6.1.8，2023-07 | 2023 GUI 的默认点数、采样方法、seed/first point、自动停止方法 | 不是 SKILL run option 的权威枚举 |
| `doc/spectreuser/chap7.html` | 2021-07 | Spectre 原生 `montecarlo` 参数、统计块、默认值 | 原生参数与 ADE run option 名字不同，不能直接当作 run option 默认值 |
| `doc/adexl/appEnvVars.html` | IC6.1.8，2023 | GUI 默认值环境变量：`samplingMethod`、`saveProcessOptionDefaultValue`、`saveSimulationData`、`saveMismatchOptionDefaultValue`、`yieldProbability` | 只控制“新建 setup 的默认值”，不一定等于现有 setup database 中 run option 的当前值 |

### 3.2 冲突/差异逐项核对

| 主题 | `maeSKILLref`/ADE 侧 | OCEAN XL 侧 | Spectre/GUI 侧 | 结论 |
|---|---|---|---|---|
| MC 选项数量 | `axlGetRunOptions` 示例给 17 项 | `ocnxlMonteCarloOptions` 另有 `useReference`、`dutSubckts`、`designUnderTest`、`dutIntances`、`mcSigmaScaleValue`、`dumpParamMode`、`evaluationmode`、`limitOnOutstandingPoints` 等 | GUI 另有一些非 run-option 的保存/方法字段 | 17 是 ADE run option 名单；OCEAN XL 多出的名字不能直接当作 ADE run option |
| `mcmethod` | `maeSKILLref/chap7`：`process / mismatch / all` | `global / mismatch / all`，默认 `all` | GUI：`Process / Mismatch / All` | `global` 与 `process` 冲突；底层实际接受哪套**未确认** |
| `samplingmode` | `standard / lhs` | `random / orthogonal / lhs`，默认 `random` | GUI：Random / Latin Hypercube / Low-Discrepancy Sequence；`adexl.monte samplingMethod` 默认 `lds` | 至少存在 4 种底层名字；`standard` 与 `random`、`orthogonal` 与 `lds` 的映射**未确认** |
| 点数默认 | ADE Explorer GUI：200；`maeSetRunOption` 示例读回 200 只是示例 | `mcNumPoints` 默认 100 | Spectre `numruns` 默认 100 | GUI 默认与 OCEAN/原生默认不一致；run option 当前 setup 的实际值应由 `axlGetRunOptionValue` 读回 |
| process 保存默认 | ADE XL GUI 文字称默认选中；环境变量文字又给默认 `nil` | `saveProcess=1` | netlist `saveprocessparams` 可为 yes/no | 默认口径冲突；应用前显式设置更安全 |
| mismatch 保存默认 | ADE GUI 文字称默认未选 | `saveMismatch=0` | netlist `savemismatchparams` 可为 yes/no | 大体一致（默认关闭），但环境变量示例行有笔误 |
| 良率概率 | GUI `Probability (1-alpha)` 默认 95%，范围 50%-100% 不含 100 | `mcYieldAlphaLimit` 只有名字，无值域 | `yieldProbability` 默认文档写 95.0，但 `.cdsenv` 示例行写 90 | `mcYieldAlphaLimit` 的存储编码和真实默认值**未确认** |
| 目标良率 | ADE XL 默认 99.73%；Explorer guided 的 sigma/% 默认 3 / 99.865 | 仅同名参数名，无默认说明 | — | `mcYieldTarget` 的存储编码和默认值**未确认** |
| 读写 API 覆盖 | `axlGetRunOptions` 能枚举 17 项；但 `axlGetRunOption`/`axlPutRunOption` 的 MC “Valid Values” 文字也只列 `mcmethod`、`mcnumpoints` | `ocnxlMonteCarloOptions` 能设置近名参数 | `maeSetRunOption` 文档只列 `mcmethod`、`mcnumpoints`；`axlSetRunOptionValue` 另有 `savemismatch` 可写示例 | 设置 15 个非文档项时可用 `axlPutRunOption` + `axlSetRunOptionValue` 作为最通用路径，但这 15 项的可写性仍应在目标版本真机读回验证 |

---

## 4. 额外发现的 MC 相关参数

### 4.1 OCEAN XL `ocnxlMonteCarloOptions` 中不属于 17 项的入参

| 参数 | 含义 | 类型/值域 | 默认值 | 是否必填 | 底层 API | 与 17 项关系/出处 |
|---|---|---|---|---|---|---|
| `?useReference` | 是否使用 schematic point 或已创建 reference point 作为 sizing 起点。 | 文档明确为 `0/1`。 | `0`。 | 否。 | `ocnxlMonteCarloOptions`。 | 语义上对应 `mcreferencepoint`；键名映射不是官方逐字表格。`doc/ocnxl/ocnxlcommands.html`，行 7150-7161。 |
| `?dutSubckts` | DUT 的 subcircuit 实例分号列表，例如 `/I0/I0/I1;/I0/I1/I0`。 | 分号分隔字符串；未给更多限制。 | 未确认。 | 否；仅在同时枚举 subcircuit 实例时使用。 | `ocnxlMonteCarloOptions`。 | 不是 17 项之一；可能与 `dutsummary`/实例选择组合使用。同上，行 7210-7228。 |
| `?designUnderTest` | 文档只写 “Design picked up for the test”。 | 未确认。 | 未确认。 | 未确认。 | `ocnxlMonteCarloOptions`。 | 不是 17 项之一。同上，行 7251-7254。 |
| `?dutIntances` | 文档只写 “Number of occurance of DUT intances”（原文拼写）。 | 未确认；文档暗示数量，但无法确认整数还是字符串。 | 未确认。 | 未确认。 | `ocnxlMonteCarloOptions`。 | 不是 17 项之一。同上，行 7256-7259。 |
| `?mcSigmaScaleValue` | 文档只写 “Sets a sigma scale value”。 | 未确认。 | 未确认。 | 未确认；可能是高级良率/K-sigma 相关。 | `ocnxlMonteCarloOptions`。 | 不是 17 项之一。同上，行 7295-7299。 |
| `?dumpParamMode` | 本地 OCEAN 文档没有给描述。 | 未确认。 | 未确认。 | 未确认。 | `ocnxlMonteCarloOptions`。 | 不是 17 项之一。同上，签名行 7072。 |
| `?evaluationmode` | 本地 OCEAN 文档没有给描述。 | 未确认。 | 未确认。 | 未确认。 | `ocnxlMonteCarloOptions`。 | 不是 17 项之一。同上，签名行 7073。 |
| `?limitOnOutstandingPoints` | 本地 OCEAN 文档没有给描述。 | 未确认。 | 未确认。 | 未确认。 | `ocnxlMonteCarloOptions`。 | 不是 17 项之一。同上，签名行 7074。 |

### 4.2 Spectre 原生 `montecarlo` 中值得注意、但不在 17 项中的开关

这些是 netlist/simulator 级参数，不是 ADE run option：

- `runpoints`、`saverunpointsfile`、`loadrunpointsfile`：指定/保存/加载要跑的迭代索引。
- `accuracyaware`、`minmaxpairs`、`smooththresh`：Spectre 原生的运行时监控和自动停止/收敛判据。
- `addnominalresults`：是否把 nominal 结果并入 MC 结果；与 `donominal` 不是同一个开关。
- `paramdumpmode`、`dumpseed`、`dumpvop`：参数/seed 的诊断导出。
- `nullmfactorcorrelation`：m-factor 并联器件的 mismatch 相关性控制。
- `distribute`、`numprocesses` 等：分布式 MC 执行。
- `method=standard/VADE`：Spectre 原生的 MC 分析方法。

（来源：`doc/spectreuser/chap7.html` — `Monte Carlo Analysis Parameters`、
`Specifying the First Iteration Number`、`Detailed Description and Examples` 等章节，
行 8538-8950、9140-9160、9507、12491 等）

这些参数不应与 `axlGetRunOptions` 的 17 项混为一类；它们是最终生成 Spectre
netlist 后由模拟器解释的选项。

---

## 5. 推荐的最小设置路径（只描述方法，不在本次调研中执行）

### 5.1 检查/枚举

```skill
session = axlGetWindowSession()
sdb = axlGetMainSetupDB(session)

;; 返回 (handle (name...))
axlGetRunOptions(sdb "Monte Carlo Sampling")

;; 读一个现有选项
opt = axlGetRunOption(sdb "Monte Carlo Sampling" "mcnumpoints")
axlGetRunOptionValue(opt)
```

`axlGetRunOptions` 的返回结构是“句柄 + 选项名列表”；不要把第一个元素当成选项名。
（来源：`doc/maeSKILLref/runRelated.html` — `axlGetRunOptions`，行 3317-3390）

### 5.2 写入

```skill
;; 已存在的选项：取句柄后写
opt = axlGetRunOption(sdb "Monte Carlo Sampling" "samplingmode")
axlSetRunOptionValue(opt "lhs")

;; 需要新建/编辑句柄时，可用官方示例的写法
axlSetRunOptionValue(
  axlPutRunOption(
    axlGetActiveSetup(axlGetMainSetupDB(axlGetWindowSession()))
    "Monte Carlo Sampling"
    "savemismatch"
  )
  "1"
)
```

（来源：`doc/maeSKILLref/runRelated.html` — `axlPutRunOption`、`axlSetRunOptionValue`，
特别是 `savemismatch` 示例）

### 5.3 用上层入口设置已文档化的两项

```skill
maeSetRunOption("Monte Carlo Sampling" "mcmethod" "all")
maeSetRunOption("Monte Carlo Sampling" "mcnumpoints" "200")
```

`maeSetRunOption` 文档只保证 MC 模式下这两项；其他选项是否支持，**未确认**。
（来源：`doc/maeSKILLref/runRelated.html` — `maeSetRunOption`，行 1436-1509）

### 5.4 选择 MC 运行模式

```skill
axlSetCurrentRunMode(sdb "Monte Carlo Sampling")
;; 或
maeRunSimulation(?runMode "Monte Carlo Sampling")
```

（来源：`doc/maeSKILLref/runRelated.html` — `axlSetCurrentRunMode`、
`maeRunSimulation`）

---

## 6. 最小有效 MC 配置清单

要“支持 MC”，至少应满足：

1. 运行模式为 `Monte Carlo Sampling`。
2. 选中 test 的模拟器在对应产品文档的 MC 支持列表内。
3. 模型/网表包含 `statistics` 块，并且至少包含与预期一致的 process 或 mismatch 分布。
4. 选择与实际统计块匹配的 `mcmethod`。
5. 固定点数模式设置有效 `mcnumpoints`；或选择 auto stop 并配置相应停止方法/目标。
6. 选择 `samplingmode`；跨版本脚本不要依赖默认值，建议显式设置。
7. 需要可复现时同时设置 `montecarloseed` 和 `mcstartingrunnumber`。
8. 所有需要被评估的 output 在 Outputs Setup 中勾选 `Plot`。
9. 需要 yield 时，配置 output/spec 与目标良率/概率。
10. 需要 sensitivity/mismatch contribution/statistical corner 时，按需打开
    `saveprocess`、`savemismatch`，或 GUI 的 `Save Statistical Parameter Data`。
11. 使用 reference point、corners、point sweeps 时，额外确认
    `mcreferencepoint`、reference point 本身、`# Point Sweeps`/`# Corners`
    以及旧版 MC+sweeps 限制。

---

## 7. 未确认/存疑清单

1. **`mcStopEarly` 的底层类型和默认值未确认。** GUI 是复选框，但文档没有给出
   `0/1`、`t/nil` 或其他编码。
2. **`mcStopMethod` 的底层枚举未确认。** 只能确认 GUI 候选方法；
   “Yield Verification”等标签是否是 setup database 中直接保存的字符串尚未证实。
3. **`mcYieldAlphaLimit` 的存储编码未确认。** GUI 的 `Probability (1-alpha)`
   默认 95%，范围 50%-100% 不含 100%；该选项可能保存 95、0.95 或 0.05。
4. **`mcYieldTarget` 的存储编码未确认。** GUI 可在百分比和 sigma 间同步显示，
   但 run option 内保存哪种表示没有文档说明。
5. **`mcreferencepoint` 与 OCEAN `useReference` 的键名对应未由官方表格逐字确认。**
   目前是语义/GUI 映射。
6. **`samplingmode` 的完整合法集合未统一。** `random`、`standard`、
   `lds`、`orthogonal` 之间的关系，特别是 `standard` vs `random`、
   `lds` vs `orthogonal`，未确认。
7. **`mcnumpoints` 的真实 setup database 默认值未确认。** OCEAN/原生文档为 100，
   ADE Explorer 2023 GUI 文档为 200。
8. **`saveprocess`、`savemismatch` 的默认值存在文档冲突。**
   OCEAN 文档给 1/0，ADE GUI 说明与环境变量 `nil` 说明不完全一致。
9. **`maeSetRunOption` 是否能设置 17 项中的其余 15 项未确认。**
   官方 MC 列表只写了 `mcmethod`、`mcnumpoints`。
10. **`ocnxlMonteCarloOptions` 多出的
    `dumpParamMode`、`evaluationmode`、`limitOnOutstandingPoints`、`mcSigmaScaleValue`
    没有足够语义说明。** 它们是否是 ADE run option、以及在哪个版本有效，未确认。
11. **旧版 “MC 不能与 sweep 同时使用，除非 Use Reference Point” 与
    Explorer 2023 “Standard MC 可与 sweep values 一起跑” 冲突。**
    需要按具体产品/版本真机验证。
12. **所有 17 项的真机存在性需要按实际 Virtuoso/ADE 版本读回。**
    本文的 17 项名单来自 IC6.1.8 2023 文档快照。

---

## 8. 证据索引

### 8.1 本地 Cadence 文档

- `C:\Users\user\Desktop\doc\maeSKILLref\runRelated.html`
  - `maeRunSimulation`
  - `maeGetSimulationMessages`（含 `ADEXL-1742` 示例）
  - `maeSetRunOption`
  - `axlGetRunOptions`
  - `axlGetRunOption`
  - `axlGetRunOptionValue`
  - `axlPutRunOption`
  - `axlSetRunOptionValue`
  - `axlSetCurrentRunMode`
- `C:\Users\user\Desktop\doc\maeSKILLref\chap7.html`
  - `asiGetAvailableMCOptions`
  - `asiGetSupportedMCOptions`
- `C:\Users\user\Desktop\doc\ocnxl\ocnxlcommands.html`
  - `ocnxlMonteCarloOptions`
  - `ocnxlYieldEstimationOptions`
  - `ocnxlYieldImprovementOptions`
  - `ocnxlRun`
  - `ocnxlStartingPoint`
- `C:\Users\user\Desktop\doc\adexl\adexlMC.html`
  - “Running a Monte Carlo Analysis”
  - “Specifying Instances for Monte Carlo Mismatch and Process Variation”
  - “Stopping Monte Carlo Based on the Target Yield”
  - “Creating Statistical Corners”
- `C:\Users\user\Desktop\doc\assembler\asmMC.html`
  - “Preparing Setup for Monte Carlo Analysis”
  - “Setting Run Options in the Monte Carlo Form”
  - “Advanced Monte Carlo Methods”
- `C:\Users\user\Desktop\doc\Explorer\chap8.html`
  - “Performing a Standard Monte Carlo Run”
  - “Running Monte Carlo with Sweep Values”
  - “Performing Sensitivity Accuracy”
  - “Performing Yield Verification”
  - “High Yield Methods”
- `C:\Users\user\Desktop\doc\adexl\appEnvVars.html`
  - `adexl.monte samplingMethod`
  - `saveProcessOptionDefaultValue`
  - `saveSimulationData`
  - `saveMismatchOptionDefaultValue`
  - `yieldProbability`
  - `createStatisticalCornerType`
  - `additionalNetlistOptions`
- `C:\Users\user\Desktop\doc\adegxl\adeGXLMCPostProc.html`
  - “Performing Yield Verification Using Sample Reordering”
  - “Performing Sensitivity Accuracy”
  - “Worst Samples Using Sample Reordering”
  - “K-Sigma Corners”
- `C:\Users\user\Desktop\doc\spectreuser\chap7.html`
  - “Monte Carlo Analysis Parameters”
  - “Specifying Parameter Distributions Using Statistics Blocks”
  - “Detailed Description and Examples”

### 8.2 仓库内已有相关记录

- `doc/report/maestro-蒙卡能力调查.md`：既有内部粗查，已指出 17 项名单来自
  `axlGetRunOptions`，并提示版本差异；本报告在该基础上补全了逐项表格、
  OCEAN XL 对照和非 run option 依赖。

（报告完）
