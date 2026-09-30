# 上层业务包：maestro

> 版本：Draft v6
> 日期：2026-09-20（2026-09-29 增补蒙卡）
> 状态：Draft（操作与原子已成形；read_config 改为 tests/corners 嵌套结构；Monte Carlo 口径见 §7.3，待评审项见 §10）
> Supersedes：Draft v5（read_config 返回按 test/corner 收拢；MC 配置/运行/结果已增补）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 总述

maestro 包覆盖 ADE Assembler / Explorer 的**配置、结果、导出、历史、仿真、展示**六类需求，共 11 个对外操作。

会话不出现在对外接口里：非 GUI 操作由包内部 `maeOpenSetup` 打开后台会话、结束时保存并关闭；只有需要人看的场景（GUI 会话、波形窗口）才对外暴露开关。

## 2. 操作总表

| 大类 | 操作 | 一句话说明 | 接口 |
|---|---|---|---|
| 配置类 | `read_config` | 按 test/corner 嵌套读当前配置（含 `outputs[].spec`、run options） | S |
| 配置类 | `write` | 通用写，`commands[]` 里的配置原子（含 MC run option） | S |
| 结果类 | `write` | 同一个通用写，`commands[]` 里的结果原子（output / spec） | S |
| 结果类 | `read_results` | 读结果点、spec 状态、yield、MC 统计；读单条波形 | S+D |
| 导出类 | `export` | 按 `kind` 批量导出文件 | S+C+D |
| 历史类 | `read_history` | 不带 history：列出全部并给完成情况；带 history：给该条进度与详情 | S |
| 历史类 | `write_history` | 通用写，`commands[]` 里的历史原子（删/改名/锁） | S |
| 仿真类 | `open_gui` / `close_gui` | GUI 会话开关 | S+G |
| 仿真类 | `run` | 启动仿真；MC 先设 mode/run option 再 run；`blocking` 决定是否等到完成（默认非阻塞） | S+C |
| 展示类 | `open_waveform_gui` / `close_waveform_gui` | 给人看的交互波形窗口 | S+G |

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 3. 配置类

### 3.1 read_config

读指定 cell 的当前配置，一次返回结构化结果。

返回结构按领域收拢：test 级数据放 `tests.<name>`，corner 级数据放 `corners.<name>`，全局数据和运行级数据放顶层。

```json
{
  "library": "…",
  "cell": "…",
  "view": "maestro",
  "tests": {
    "<test>": {
      "variables": {},
      "analyses": {},
      "outputs": [],
      "env_options": {},
      "sim_options": {}
    }
  },
  "variables": {},
  "parameters": {},
  "corners": {
    "<corner>": {
      "variables": {},
      "parameters": {}
    }
  },
  "run_options": {
    "<run mode>": {"<option>": "… 或 null …"}
  },
  "run_mode": "…",
  "job_control_mode": "…",
  "current_history": "…"
}
```

| 数据 | 返回位置 | 底层 |
|---|---|---|
| 全局变量 / 参数 | `variables` / `parameters` | `maeGetVar` / `maeGetParameter` |
| test 列表与 test 级配置 | `tests.<name>.{variables,analyses,outputs,env_options,sim_options}` | `axlGetTests` / `maeGetTestOutputs` / `maeGetEnvOption` / `maeGetSimOption` |
| corner 列表与 corner 级配置 | `corners.<name>.{variables,parameters}` | `axlGetCorners` / `axlGetVars` / `axlGetParameters` |
| run options | `run_options.<mode>.<option>` | `axlGetRunOption` + `axlGetRunOptionValue`（17 项清单由包内固定，`axlGetRunOptions` 用于核对） |
| 运行状态 | `run_mode` / `job_control_mode` / `current_history` | `maeGetCurrentRunMode` / `maeGetJobControlMode` / `axlGetCurrentHistory` |

- output 的 spec 直接挂在 `tests.<test>.outputs[].spec`，不再单列 `specs` 扁平表。
- `run_options` 按 run mode 分组；本版只读 `"Monte Carlo Sampling"`（17 项），未设置过返回 `null`。
  普通 `"Single Run, Sweeps and Corners"` 没有 run-option 集合；`Sampling` / `Global Optimization` /
  `Local Optimization` 各有自己的选项，本版不实现。

### 3.2 write（配置原子）

每个原子 = `op` + **索引**（动哪个）+ 附加参数。整批在一个后台会话内顺序执行，末尾统一保存。

`save` 语义（P-087 定稿）：只支持 `save=true`（整批成功后 `maeSaveSetup` 落盘）。
`save=false` 被**结构化拒绝**（`reason=save_false_unsupported`）：会话若由 GUI 打开，
`maeCloseSession` 按官方文档无法关闭（实测返回 nil），改动会留在会话里被后续 save
静默带走并污染用户 setup，因此本版不提供"不落盘写"。

| 分组 | 原子 | 索引 | 附加参数 | 底层 |
|---|---|---|---|---|
| 器件 | set_test | test | lib / cell / view / simulator | `maeCreateTest` |
| 器件 | set_design | test | lib / cell / view | `maeSetDesign` |
| 分析 | set_analysis | test | analysis / enable / options | `maeSetAnalysis` |
| 变量 | set_var | name | value / scope（global、test、corner） | `maeSetVar`（`?typeName`/`?typeValue`） |
| 变量 | delete_var | name | test? | `axlRemoveElement(axlGetVar(...))` |
| 变量 | set_parameter | name | value / scope | `maeSetParameter` |
| 环境 | set_env_option | test | options | `maeSetEnvOption` |
| 环境 | set_sim_option | test | options | `maeSetSimOption` |
| corner | set_corner | name | disable_tests? | `maeSetCorner` |
| corner | setup_corner | name | model_file / model_section / variables | `maeSetCorner` + `maeSetVar(corner)` + `axlGetCorner`/`axlPutModel`/`axlSetModelFile`/`axlSetModelSection` |
| corner | load_corners | —（文件导入） | filepath / operation / sections? | `maeLoadCorners`（CSV 先经 File 接口上传；`sections` 只对 `.sdb` 显式透传） |
| 运行 | set_run_mode | —（会话级） | run_mode | `maeSetCurrentRunMode` |
| 运行 | set_run_option | —（固定 MC mode） | options（dict） | `axlPutRunOption` + `axlSetRunOptionValue` |
| 运行 | set_job_control_mode | —（会话级） | mode | `maeSetJobControlMode` |
| 运行 | set_job_policy | test? | policy / job_type | `maeSetJobPolicy` |
| 运行 | set_simulator_mode | test | mode | `asiSetHighPerformanceOptionVal`（内部映射 `'uniMode` / `'spectreXPreset`） |

`set_run_option` 只服务 Monte Carlo：`options` 的键必须是 §7.3.1 的 17 项，包内做类型/值域校验并归一化为 ADE 字符串；一条命令可同时写多项。

`load_corners` 对 `.csv` 默认不传 `?sections`；当前 Virtuoso 构建不识别该关键字，
因此只有调用方显式给出 `sections`（针对 `.sdb`）时才透传（P-110）。

## 4. 结果类

### 4.1 write（结果原子）

| 原子 | 索引 | 附加参数 | 底层 |
|---|---|---|---|
| add_output | test | name / output_type / signal_name / expr | `maeAddOutput` |
| set_spec | test | name / lt / gt | `maeSetSpec` |

### 4.2 read_results

| 能力 | 底层 |
|---|---|
| 读全部点、spec 状态、yield | `maeExportOutputView` 导 Detail CSV → 下载 → 解析 |
| MC per-output 统计（Yield/Min/Target/Max/Mean/Std Dev/Cpk/Errors） | `maeExportOutputView ?view "Yield"` → 下载 → 解析（§7.3.3） |
| 读单条波形 | `maeOpenResults` → `openResults` → `selectResults` → `ocnPrint` → 下载文本 |
| 结果目录/最新 history 定位 | `asiGetResultsDir` + 旧代码的 mtime / 自然排序规则 |

`history` 为 `MonteCarlo.*` 时，返回额外带 `value.monte_carlo`；`value.points`/`value.outputs`
保持原有 Detail 口径不变。

## 5. 导出类

一个 `export` 操作，用 `kind` 区分产物。

| kind | 产物 | 底层 |
|---|---|---|
| netlist | 指定 corner 的网表 | `maeCreateNetlistForCorner` |
| script | 等价 OCEAN 脚本 | `maeWriteScript` |
| outputs_csv | outputs 表 CSV | `maeExportOutputView` |
| snapshot | 全量快照包（sdb / active.state / 过滤 XML / 按点 netlist 与 PSF） | 快照模板 + `find`/`tar` 打包 |
| screenshot | Maestro 窗口 PNG | `hiWindowSaveImage`（窗口按 `cellView~>viewName` 定位） |

## 6. 历史类

### 6.1 read_history

按是否显式给出 `history` 分两种形态。

**概览形态（不带 `history`）**：列出全部 history，每条给一个简单的完成情况。

| 返回项 | 底层 |
|---|---|
| 全部 history 名称 | `axlGetHistory` |
| 每个 history 的完成情况（running / done / failed） | `axlGetRunStatus` 逐条查询 |
| 当前 history / 最新 history | `axlGetCurrentHistory`；旧代码的 mtime 排序 / 自然排序规则 |

**详情形态（显式带 `history`）**：给这一条的进度与细节。

| 返回项 | 底层 |
|---|---|
| 进度（完成的点 / 测试 / corner 数） | `axlGetRunStatus`（指定 history） |
| 锁状态 | `axlGetHistoryLock` / `maeGetHistoryLockFlag`（0–4 五种状态） |
| 结果目录 | `axlGetResultsLocation` 等路径查询 |
| 覆盖式运行目标 | `axlGetOverwriteHistoryName` |

### 6.2 write_history（历史原子）

| 原子 | 索引 | 附加参数 | 底层 |
|---|---|---|---|
| delete | history | — | Assembler：`axlRemoveElement(axlGetHistoryEntry(sdb, name))`；Explorer：`maeDeleteExplorerHistory(session, name)` |
| delete_results | history | keep_netlist? / keep_quick_plot? | `maeDeleteSimulationData`（对应 GUI 三档）；备选 `axlRemoveSimulationResults` |
| rename | history | new_name | `axlSetHistoryName(handle, new_name)` |
| lock / unlock | history | — | `maeSetHistoryLock` / `axlSetHistoryLock` |

写前先读锁状态；被引用锁（reference / MC reuse）的 history 不可直接删。

`write_history` 不复用失效的会话/SDB handle：每次写原子前确认 `maeOpenSetup` 返回的会话仍可用；
若 `maeGetSessions()` 列出但实际已失效，关闭后重开一次再继续（C09）。rename 链 A→B→A
必须在同一请求内可连续执行，目标名冲突给点名结构化拒绝。

## 7. 仿真类

### 7.1 open_gui / close_gui

| 操作 | 底层 |
|---|---|
| open_gui | 窗口探测 → 关闭只读副本 → `deOpenCellView(..., "a")` → 找到并复用可编辑会话 |
| close_gui | 探测窗口 mode/已修改 → Reading 先 `maeMakeEditable` → `maeSaveSetup` → `hiCloseWindow` → `dbPurge` 释放编辑锁；**固定保存，不提供丢弃** |

### 7.2 run

| 参数 | 说明 |
|---|---|
| `blocking` | 是否阻塞到仿真结束；**默认 `false`**（立即返回 history 名） |

| 模式 | 行为 | 底层 |
|---|---|---|
| 非阻塞（默认） | 启动后立即返回 history 名，调用方之后用 `read_history` 查进度 | `maeRunSimulation` |
| 阻塞（`blocking=true`） | 启动后在包内等到终态，返回 history 名 + 终态 | `maeRunSimulation` + 包内轮询 |

启动失败（`maeRunSimulation` 返回 `nil`）视为业务失败：先做一次诊断，若发现有模态窗口阻塞则尝试关闭后重试一次，仍失败即返回失败并给出诊断（旧实现同此口径）。

支持覆盖式运行参数（`axlSetOverwriteHistory` + `axlSetOverwriteHistoryName`）。

MC 运行：run mode 由最近一次 `set_run_mode` 决定；必须先设 `"Monte Carlo Sampling"`。`run` 对外仍不新增 `run_mode` 参数，但包内读取当前 mode 并通过 `?runMode` 显式传给 `maeRunSimulation`，避免 ADE 文档默认值退回 `"Single Run, Sweeps and Corners"`。MC 模式下启动前做两项前置检查（§7.3.2）；统计模型是否存在由 Spectre 在仿真中判定。

`blocking=true` 时，启动与等待共用同一条 deadline。

**不引入服务端等待池**：阻塞由本操作在包内轮询实现，非阻塞由调用方自行查询，口径见[本版范围与明确不支持](../总览/add-本版范围与明确不支持.md)第 13 项。

### 7.3 Monte Carlo（配置、运行与结果）

MC 不是新操作，复用 `set_run_mode` / `set_run_option` / `run` / `read_history` / `read_results`。

#### 7.3.1 配置

```json
{"op":"set_run_option","options":{
  "mcmethod":"mismatch",
  "mcnumpoints":8,
  "samplingmode":"lhs",
  "saveallplots":false
}}
```

- run mode 固定 `"Monte Carlo Sampling"`，不逐项重复传；一条命令可写多项。
- 包内校验并归一化为 ADE 字符串；底层 `axlPutRunOption(axlGetMainSetupDB(session) "Monte Carlo Sampling" <name>)` + `axlSetRunOptionValue`。
- 未设置的项读回 `null`（= 用 ADE 默认），`read_config.value.run_options["Monte Carlo Sampling"]` 17 项全列。
- `dutsummary` 读到 ADE 内部末尾终止符 `%#` 时，包内剥离后再返回，保证回读值与写入值一致。
- 没有 reference point 时，ADE 不落 `mcreferencepoint` option，读回为 `null`；写入调用本身仍成功（值域与效果由 ADE 决定）。
- run option 是 **mode 级**概念：`axlGetRunOption(sdb, mode, name)` 的合法 mode 为 `Sampling` / `Global Optimization` / `Local Optimization` / `Monte Carlo Sampling`；`Single Run, Sweeps and Corners` 没有这一组选项，其配置分散在 tests/analyses/outputs/corners/sweeps/job policy。

| 选项 | 含义 | 包内接受值 | 证据 |
|---|---|---|---|
| `mcmethod` | process / mismatch / all | `process`/`mismatch`/`all`/`global`（`global` 为 OCEAN 别名） | 活体可写 + 文档 |
| `mcnumpoints` | 固定采样点数 | 正整数 | 活体 + 文档 |
| `mcnumbins` | LHS 分箱数 | 非负整数或 `""`（自动） | 文档 |
| `samplingmode` | 采样算法 | `random`/`standard`/`orthogonal`/`lhs`/`lds` | 文档；`lhs` 活体 |
| `montecarloseed` | 随机种子 | 非负整数 | 文档 |
| `mcstartingrunnumber` | 起始迭代号 | 正整数 | 文档 |
| `dutsummary` | mismatch 实例范围 | 字符串（格式原样透传） | 活体可写；值域未验证 |
| `ignoreflag` | 排除 `dutsummary` 实例 | 0/1 | 文档 |
| `mcreferencepoint` | 使用 reference point | 0/1 | 文档 |
| `donominal` | 先跑 nominal | 0/1 | 文档 |
| `saveprocess` | 保存 process 数据 | 0/1 | 文档 |
| `savemismatch` | 保存 mismatch 数据 | 0/1 | 文档 |
| `saveallplots` | 保存每次迭代 PSF | 0/1 | 文档 |
| `mcStopEarly` | 启用 auto-stop | `t`/`nil`（0/1 亦可） | 活体可写；类型未完全确认 |
| `mcStopMethod` | auto-stop 方法 | 字符串（值域未验证，原样透传） | 文档 |
| `mcYieldTarget` | 目标良率/σ | >0 数值 | 文档；百分比/σ 编码未验证 |
| `mcYieldAlphaLimit` | 置信度/概率 | (0,100) 数值 | 文档；alpha/概率编码未验证 |

#### 7.3.2 运行

1. 先 `set_run_mode` → `{"op":"set_run_mode","run_mode":"Monte Carlo Sampling"}`，再 `run`；`run` 不带对外 `run_mode`，包内用当前 mode 拼 `maeRunSimulation(... ?runMode "Monte Carlo Sampling")`。
2. 本环境实测 `maeRunSimulation` 需要 GUI session；调用前先 `open_gui`（或确保已有编辑窗口）。
3. MC 模式下启动前检查：
   - 至少一个 output `plot=t`，否则结构化失败 `mc_no_plot_outputs`（对应 ADEXL-1617）；
   - `axlGetAllSweepsEnabled(sdb)=t` 且 `mcreferencepoint` 未开启 → 结构化失败 `mc_sweeps_conflict`（对应 ADEXL-1742）。
4. 进度用 `read_history`（`axlGetRunStatus ?optionName "all"`）；history 名形如 `MonteCarlo.N`，用返回值不要猜。

#### 7.3.3 结果

`read_results` 对 `MonteCarlo.*` 在原有 Detail 导出之外再导 `?view "Yield"`，返回 `value.monte_carlo`：

```json
{
  "history": "MonteCarlo.0",
  "corners": ["_default", "vdd_high"],
  "overall": {
    "yield": 0.0, "yield_text": "0% (0/2)",
    "passed_points": 0, "total_points": 2, "error_points": 2,
    "confidence_level": null, "filter": null
  },
  "outputs": [{
    "test": "opamp_ac", "name": "gain_db", "raw_name": "gain_db(summary)",
    "summary": true, "corner": null,
    "yield": 0.0, "yield_text": "0% (0/2)",
    "passed_points": 0, "total_points": 2,
    "min": 0, "target": "> 19", "target_value": 19, "max": 0,
    "mean": 0, "std_dev": 0, "cpk": null, "errors": 2
  }]
}
```

- `(summary)` 行归 `summary=true`；corner 后缀按 `read_config` 的 corner 名去除并写入 `corner`。
- `target_value` 是 `target` 中的数值（如 `> 19` → 19；`maximize 0.05` → 0.05）。
- `overall.error_points` 优先由 Yield 表的 `total_points - passed_points` 推导；`maeGetOverallYield` 的原始 `ErrorPoints` 只作缺失兜底。
- 顶层 `overall_yield` 保留 `maeGetOverallYield` 原始键；`value.points` 保留 Detail 的 `mc_iteration` 逐点数据。
- `axlWriteMonteCarloResultsCSV` 在本版不可用（实测返回 nil），不采用。

#### 7.3.4 前置条件与限制

1. **统计模型硬前提**：模型必须含 `statistics { process/mismatch }`，且与 `mcmethod` 一致；否则每个点 `SPECTRE-16012`。
2. **PDK 挂载**：mismatch 需把 `stat_mis_*` 与角 section 同时挂；process 需 `stat` 与 `mc_*` 同时挂。
3. **模拟器**：Spectre / APS / AMS-Spectre / hspiceD（各版本文档有差异，以当前环境为准）。
4. **MC × sweep 互斥**：ADEXL-1742；例外是 `mcreferencepoint=1`。
5. output 必须勾 Plot；`saveallplots=1` 会显著增大产物体积。
6. `mcYieldTarget` / `mcYieldAlphaLimit` 只参与 auto-stop，不决定单点 pass/fail。

## 8. 展示类

给人类看的交互窗口，不做截图（截图属导出类的 `kind=screenshot`，可先经这里打开窗口再截）。

| 操作 | 底层 |
|---|---|
| open_waveform_gui | `maeOpenSetup(?mode "r")` → `maeOpenResults(?history)` → `awvCreatePlotWindow` → `awvPlotWaveform(?expr signals)`；会话保持打开供窗口引用 |
| close_waveform_gui | `hiCloseWindow` + `maeCloseSession(?forceClose t)`，关闭后校验窗口与会话列表 |

## 9. 内部中间节点（不对外）

| 节点 | 底层 | 被谁使用 |
|---|---|---|
| 后台会话 open / save / close | `maeOpenSetup` / `maeSaveSetup` / `maeCloseSession` | write、read_config、read_results、export、write_history |
| **读路径不得产生写副作用** | 只读操作（read_config / read_results / export / read_history）开会话一律 `?mode "r"`；写操作沿用官方默认 `"a"` | 全部 |
| **陈旧/他人写锁不弹模态** | 开会话前检查 cellview 目录的 `*.cdslck`：属主进程已死或非本实例 → **结构化失败**（点名锁文件/属主/pid）；本实例自己的锁 → 正常复用会话 | 全部 |
| 确保 maestro view 存在 | `maeOpenSetup` + `maeSaveSetup` | write、open_gui（对外不暴露） |
| 窗口状态探测（mode / 已修改） | `hiGetCurrentWindow` + 标题解析 + `davSession` | close_gui |
| Detail CSV 中间导出 | `maeExportOutputView` | read_results、export(outputs_csv) |
| MC run option 读写 | `axlGetRunOption` / `axlGetRunOptionValue` / `axlPutRunOption` / `axlSetRunOptionValue` | write、read_config |
| MC Yield CSV 中间导出 | `maeExportOutputView ?view "Yield"` | read_results |

## 10. 待定与待验证

待定：

1. 会话级原子的索引（`set_run_mode` / `set_job_control_mode` 现按"当前会话"处理）；
2. `options` 类参数保持 SKILL alist 字符串还是拆结构化字段；
3. analyses / outputs 的枚举函数；
4. 是否补 `delete_output`（底层有 `axlDeleteOutput`，旧包未用）；
5. `run(blocking=true)` 与 `read_history` 判断"跑完了"的来源：回调 marker（精确，但要求 marker 文件在工作角色间可见）还是 `axlGetRunStatus`（不依赖 marker，但需与期望的点/测试总数对上）；
6. 各原子的参数与默认值逐项定稿。
7. MC 选项面：17 项全开还是只开常用 8 项；未设置项读回 `null` 还是省略；`set_run_option` 是否保留单条 `name`/`value` 兼容形态；`mcmethod` 的 `global`/`process` 是否归一化。
8. MC 结果面：`monte_carlo.outputs` 保持扁平（`summary`/`corner` 字段）还是按 corner/summary 分组；`mcYieldTarget` / `mcYieldAlphaLimit` 的百分比/σ/alpha 编码。
9. MC 前置检查：`axlGetAllSweepsEnabled` 反映的是 Sweep 复选框而非实际 sweep 变量，是否把 §7.3.2 的 sweep 检查降级为 warning。
10. MC 统计载具：新建 PDK 统计器件最小 cell + Maestro setup（推荐）/ 给现有 fixture 自写 `.scs` 统计模型 / 在 `CMP_TB_LIB/tb_cmp_top` 上建 setup。
11. plot 前置检查范围：整个 setup 至少一个 `plot=t`，还是每个 test 都必须有。

待真机验证（写 spec 定稿前必须闭环）：

1. `axlRemoveElement` 删整条 history 后的磁盘落盘效应（`maestro.sdb` 与 `results/maestro/*`、新代 `history/*.zip` 是否同步）；
2. `maeDeleteExplorerHistory` 的持久化语义；
3. `axlSetHistoryName` 改名后各存储位置、引用关系、覆盖目标回退的一致性；
4. 各种锁状态下的删除/改名报错形态；
5. 后台会话中执行删除/改名是否可用；
6. `maeDeleteSimulationData` 的三档保留选项与磁盘实际保留范围是否一致；
7. 快照的过滤资产（`snapshot_filter.yaml`）随包分发方式；
8. corner CSV 上传与各导出产物的 role / 路径归属。
