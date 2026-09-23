# 上层业务包：maestro

> 版本：Draft v4
> 日期：2026-09-20
> 状态：Draft（操作与原子已成形；参数细节待逐项定稿；暂未纳入 README 治理）
> Supersedes：Draft v3（补全历史类读写与全部操作/原子的实现底层；去掉 history 复制）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 总述

maestro 包覆盖 ADE Assembler / Explorer 的**配置、结果、导出、历史、仿真、展示**六类需求，共 11 个对外操作。

会话不出现在对外接口里：非 GUI 操作由包内部 `maeOpenSetup` 打开后台会话、结束时保存并关闭；只有需要人看的场景（GUI 会话、波形窗口）才对外暴露开关。

## 2. 操作总表

| 大类 | 操作 | 一句话说明 | 接口 |
|---|---|---|---|
| 配置类 | `read_config` | 读当前配置（变量、参数、tests、corners、specs） | S |
| 配置类 | `write` | 通用写，`commands[]` 里的配置原子 | S |
| 结果类 | `write` | 同一个通用写，`commands[]` 里的结果原子（output / spec） | S |
| 结果类 | `read_results` | 读结果点、spec 状态、yield；读单条波形 | S+D |
| 导出类 | `export` | 按 `kind` 批量导出文件 | S+C+D |
| 历史类 | `read_history` | 不带 history：列出全部并给完成情况；带 history：给该条进度与详情 | S |
| 历史类 | `write_history` | 通用写，`commands[]` 里的历史原子（删/改名/锁） | S |
| 仿真类 | `open_gui` / `close_gui` | GUI 会话开关 | S+G |
| 仿真类 | `run` | 启动仿真；`blocking` 决定是否等到完成（默认非阻塞） | S+C |
| 展示类 | `open_waveform_gui` / `close_waveform_gui` | 给人看的交互波形窗口 | S+G |

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 3. 配置类

### 3.1 read_config

读指定 cell 的当前配置，一次返回结构化结果。

| 返回项 | 底层 |
|---|---|
| 变量表 | `maeGetVar` / `axlGetVars` |
| 参数表 | `maeGetParameter` |
| tests | `axlGetTests` |
| corners | `axlGetCorners`、`axlGetCornersForATest` |
| specs | `axlGetSpecs` |
| analyses / outputs 列表 | **待定**：未找到现成枚举函数，需用 `maeGetTestSession` 逐 test 取 |

### 3.2 write（配置原子）

每个原子 = `op` + **索引**（动哪个）+ 附加参数。整批在一个后台会话内顺序执行，末尾统一保存。

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
| corner | load_corners | —（文件导入） | filepath / sections / operation | `maeLoadCorners`（CSV 先经 File 接口上传） |
| 运行 | set_run_mode | —（会话级） | run_mode | `maeSetCurrentRunMode` |
| 运行 | set_job_control_mode | —（会话级） | mode | `maeSetJobControlMode` |
| 运行 | set_job_policy | test? | policy / job_type | `maeSetJobPolicy` |
| 运行 | set_simulator_mode | test | mode | `asiSetHighPerformanceOptionVal`（内部映射 `'uniMode` / `'spectreXPreset`） |

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
| 读单条波形 | `maeOpenResults` → `openResults` → `selectResults` → `ocnPrint` → 下载文本 |
| 结果目录/最新 history 定位 | `asiGetResultsDir` + 旧代码的 mtime / 自然排序规则 |

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

`blocking=true` 时，启动与等待共用同一条 deadline。

**不引入服务端等待池**：阻塞由本操作在包内轮询实现，非阻塞由调用方自行查询，理由见[已否决：顶层任务等待池](../../../doc/report/需求-顶层任务等待池.md)。

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
| 确保 maestro view 存在 | `maeOpenSetup` + `maeSaveSetup` | write、open_gui（对外不暴露） |
| 窗口状态探测（mode / 已修改） | `hiGetCurrentWindow` + 标题解析 + `davSession` | close_gui |
| Detail CSV 中间导出 | `maeExportOutputView` | read_results、export(outputs_csv) |

## 10. 待定与待验证

待定：

1. 会话级原子的索引（`set_run_mode` / `set_job_control_mode` 现按"当前会话"处理）；
2. `options` 类参数保持 SKILL alist 字符串还是拆结构化字段；
3. analyses / outputs 的枚举函数；
4. 是否补 `delete_output`（底层有 `axlDeleteOutput`，旧包未用）；
5. `run(blocking=true)` 与 `read_history` 判断"跑完了"的来源：回调 marker（精确，但要求 marker 文件在工作角色间可见）还是 `axlGetRunStatus`（不依赖 marker，但需与期望的点/测试总数对上）；
6. 各原子的参数与默认值逐项定稿。

待真机验证（写 spec 定稿前必须闭环）：

1. `axlRemoveElement` 删整条 history 后的磁盘落盘效应（`maestro.sdb` 与 `results/maestro/*`、新代 `history/*.zip` 是否同步）；
2. `maeDeleteExplorerHistory` 的持久化语义；
3. `axlSetHistoryName` 改名后各存储位置、引用关系、覆盖目标回退的一致性；
4. 各种锁状态下的删除/改名报错形态；
5. 后台会话中执行删除/改名是否可用；
6. `maeDeleteSimulationData` 的三档保留选项与磁盘实际保留范围是否一致；
7. 快照的过滤资产（`snapshot_filter.yaml`）随包分发方式；
8. corner CSV 上传与各导出产物的 role / 路径归属。
