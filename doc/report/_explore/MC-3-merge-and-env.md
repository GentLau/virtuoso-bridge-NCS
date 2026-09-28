# MC-3（合并稿）：蒙卡落地——代码接入点、测试载体与 PDK 统计模型环境

> 调研日期：2026-09-28（CST）
> 仓库：`C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS`（HEAD `c4ab4ff` + 未提交改动；`src/pyapi/packages/maestro.py`、`spec/design-concepts/上层/6-maestro.md` 本身无未提交改动）
> 范围：**只读调研**。未修改仓库任何文件（只新增本报告）；未开关/修改任何 ADE 会话；ssh 仅用 ls/grep/cat/stat/find 等只读命令。
> 姊妹报告（并发产出）：`doc/report/_explore/MC-1-run-options.md`（run option 清单）、`doc/report/_explore/MC-2-run-and-results.md`（运行/进度/结果链路）。本文是两者的**合并 + 环境落地部分**，不重复其文档证据细节，只保留代码/环境接口。
> 行号基线：`src/pyapi/packages/maestro.py` 共 3273 行；`src/pyapi/packages/_maestro_util.py` 共 340 行；`spec/design-concepts/上层/6-maestro.md` 共 198 行。

---

## 0. 结论摘要

1. **代码只需 4 处主改**：`maestro.py:819-1299`（原子分发表）加 `set_run_option`；`maestro.py:1321-1671`（`read_config`）加 `run_options`；`maestro.py:1847-2048`（`read_results`）加 MC 分支；`maestro.py:2839-3073`（`run`）透传 `?runMode`。请求 dataclass 在 `maestro.py:167-175`。
2. **现有 `set_run_mode` 已能启动 MC**：`maestro.py:1115-1117`（`maeSetCurrentRunMode`）+ `run` 的 `maeRunSimulation`（`maestro.py:2857-2861`）在真机上**实际启动过** Monte Carlo（见 §2.3 的 `MonteCarlo.0` 现场证据，2026-09-28 19:39）。
3. **现有 `set_env_option`/`set_sim_option` 的 `options` 已是 dict 形态**：`maestro.py:1047-1053` 调 `skill_alist`（`_maestro_util.py:68-87`），dict/list-of-pairs/原始 alist 字符串都能转成 `?options \`((...))`；读回是 `maeGetEnvOption`/`maeGetSimOption` + `pairs_to_dict`（`maestro.py:1410-1438`、`_maestro_util.py:95-103`）。MC run option 可完全复用该形态。
4. **会话模型是"每操作一个会话，只有自建才关"**：`_open_session`（`maestro.py:397-415`）→ `maeOpenSetup`；`_close_if_created`（`:1303-1317`）在 finally 里只关 `created=True` 的会话；`run` 例外，强制走 GUI 会话（`_ensure_gui_session`，`:568-619`、`:2946-2951`），且从不自动关闭。
5. **`read_config.run_mode` 已经能读**：`maeGetCurrentRunMode` 在 `maestro.py:1350` 的 6 元组里取回，`setup[4]` → `run_mode`（`:1373`），最终进返回结构（`:1654`）。**但没有 `run_options` 字段**（MC 的 `mcmethod/mcnumpoints/...` 读不到）。
6. **`read_results` 现在只有 Detail CSV + `maeGetOverallYield`**（`:1973-2029`），没有 MC 专用导出（`axlWriteMonteCarloResultsCSV`）也没有 per-output mean/sigma。
7. **三个测试载体都不能直接跑 MC**：`rc_probe`/`opamp_probe`/`logic_probe` 的 maestro setup 全部 `modelFiles=nil`，且**没有任何 `statistics{}` 模型块**（case-insensitive grep 的命中全部只是保存选项字段 `simStatisticsInfo`/`simStatistics`，值为 nil）；opamp/logic 用的是 ahdlLib 的 Verilog-A 模型（无统计参数）。真机上 opamp_probe 已试过一次 2 点 MC，**12 个点全部失败于 `SPECTRE-16012`**（见 §2.3）。
8. **PDK 统计模型齐备但要手动组合**：`/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/models/spectre/` 下只有 `crn65gplus_2d5_lk_v1d0.scs` 含 `statistics{}`（33 块：26 个 mismatch + 7 个 process；在线副本另计）；`cor_25.scs` 等 corner 文件**只 include corner section，不 include stat section**，跑 MC 必须另外挂 `stat*`/`mc_*` section（文件头注释 `crn65gplus_2d5_lk_v1d0.scs:523-531` 明说）。
9. **旧代码没有 MC 实现可抄**：`src_bak/` 只有 run mode/仿真启动/overall yield/history 名字识别等管道；`git log -S 'maeSetRunOption'`、`-S 'mcmethod'`、`-S 'axlWriteMonteCarloResultsCSV'` 全部为空。
10. **8~10 点 MC 的最小可行载体**：新建 1 个用 PDK 统计器件的单测试/单 corner 的 cell（推荐电阻 `rppolywo`/`rnodwo` + `stat_res`/`stat_mis_res`，或 MOS + `stat`/`mc_*`），或自写一个带 `statistics{}` 的 .scs 模型挂到现有 cell；前者依赖 PDK，路径已验证存在；挂法与实例 `mismatchflag=1` 需真机确认（§3.3/§3.4）。

---

## 1. 代码接入点清单（`src/pyapi/packages/maestro.py`）

### 1.1 配置原子分发表（`_command_exprs`，`:819-1299`）

`write` / `write_history` 的每个 `{"op": ...}` 都进 `_command_exprs`（`:819`），按 `op` 分支返回 SKILL 表达式列表；未知 op 在 `:1299` 抛 `unknown atomic op`。

| 原子 | 行 | 说明 |
|---|---|---|
| `set_test` | `:832-844` | 建/复用 test（`maeSetDesign`/`maeCreateTest`，默认 simulator `spectre`） |
| `set_design` | `:846-853` | 改 test 的 lib/cell/view |
| `delete_test` | `:855-857` | `maeDeleteTest` |
| `set_analysis` | `:859-868` | `maeSetAnalysis(..., ?options \`alist)`；**`options` 用 `skill_alist`** |
| `set_var` / `delete_var` | `:870-979` | 变量，支持 global/test/corner scope |
| `set_parameter` / `delete_parameter` | `:981-1045` | 参数，corner scope 支持 `?typeName "corner"` |
| `set_env_option` / `set_sim_option` | `:1047-1053` | **`options` 字典形态（见下）** |
| `set_corner` / `delete_corner` | `:1055-1075` | corner 开关/增删 |
| `setup_corner` | `:1077-1101` | **corner 级 model 注入**：`axlPutModel`+`axlSetModelFile`+`axlSetModelSection`（`:1086-1100`），MC 载体挂统计模型可复用的最近原子 |
| `load_corners` | `:1103-1113` | `maeLoadCorners`（CSV 上传逻辑在 `write` 里，`:1706-1735`） |
| `set_run_mode` | `:1115-1117` | `maeSetCurrentRunMode(?runMode ...)`——**当前唯一的 MC 入口** |
| `set_job_control_mode` | `:1119-1121` | `maeSetJobControlMode`（`run` 固定 ICRP，`:2952-2953`） |
| `set_job_policy` | `:1123-1158` | `maeGetJobPolicy`/`maeSetJobPolicy`（dict → `jp->k = v`） |
| `set_simulator_mode` | `:1160-1171` | `asiSetHighPerformanceOptionVal` |
| `add_output` | `:1173-1189` | `maeAddOutput`，支持 `?plot`/`?save`（`:1185-1187`）——MC 要求 output 勾 Plot |
| `set_spec` | `:1191-1234` | `axlAddSpecToOutput`（gt/lt/min/max/tol/range） |
| `delete_output` / `delete_spec` | `:1236-1261` | — |
| 历史类 `delete`/`delete_results`/`rename`/`lock`/`unlock` | `:1263-1297` | `write_history` 复用同一分发表 |

**`set_env_option`/`set_sim_option` 的 options 形态（回答问题①）**：

```python
# maestro.py:1047-1053
if op in ("set_env_option", "set_sim_option"):
    test = _require_text(command.get("test"), "command.test")
    options = skill_alist(command.get("options"), name="command.options")
    if not options:
        raise ValueError("command.options is required")
    fn = "maeSetEnvOption" if op == "set_env_option" else "maeSetSimOption"
    return [f"{fn}({q(test)} ?options `{options}{sess})"]
```

- `skill_alist`（`_maestro_util.py:68-87`）接受三种输入：原始 alist 字符串、`dict`、`[(name, value), ...]`；输出 `("key" value)` 的 SKILL alist 片段。
- 读回侧：`read_config` 对每个 test 调 `maeGetEnvOption`/`maeGetSimOption`（`:1414-1434`），用 `pairs_to_dict`（`_maestro_util.py:95-103`）转回 dict。
- **成对用法现成可抄**：`test/live/packages/maestro_e2e_tests.py:202-235` 已有 `set_sim_option {"temp": ...}` / `set_env_option {"controlMode": ...}` 的写→readback 断言。

**MC 新增原子建议落点**：`set_run_mode`（`:1115-1117`）之后插 `set_run_option`，一次改一项：
`axlPutRunOption(axlGetMainSetupDB(session) mode name)` → `axlSetRunOptionValue(handle value)`（句柄链路见 MC-1 §0.3；`maeSetRunOption` 文档只保证 `mcmethod/mcnumpoints`，见 §6）。

### 1.2 会话模型（问题②）

| 组件 | 行 | 行为 |
|---|---|---|
| `_session_list` | `:393-395` | `maeGetSessions()` → 会话名列表 |
| `_open_session` | `:397-415` | `maeOpenSetup(lib cell view)`；**返回 `(session, created)`**，`created=False` 表示复用了已存在的同 cellview 会话（模块 docstring `:19-22`） |
| `_save_setup` | `:417-432` | `maeSaveSetup(?lib ?cell ?view ?session)` |
| `_close_session` | `:434-444` | `maeCloseSession(?session s ?forceClose t)` |
| `_session_windows` | `:446-483` | 遍历 `hiGetWindowList()`+`axlGetWindowSession()`，标题含 Assembler/Explorer 的窗口 → `{session, window, title, mode}`（`editing`/`reading`） |
| `_ensure_session_editable` | `:510-546` | 无窗口=后台会话直接可写；`reading` GUI 会话先 `maeMakeEditable`（`:536-546`） |
| `_background_sessions` | `:548-566` | 识别非 GUI（后台）残留会话；**故意不自动强关**（IC6.1.8 曾 SIGSEGV，`:555-558`） |
| `_ensure_gui_session` | `:568-619` | `run`/`open_gui` 用：找到同 cellview GUI 窗口并 `maeMakeEditable`；否则 `deOpenCellView(..., "a")` 打开（`:599-610`），最长等 `timeout` 出现窗口 |
| `_close_if_created` | `:1303-1317` | 仅当 `created=True` 才关；`close_session` 失败只记 step，不抛 |

**每批是否新开后台会话 / 何时关闭**：

- `read_config`：开（`:1333`）→ finally 关-if-created（`:1668`）。
- `write`：开（`:1689`）→ `_ensure_session_editable`（`:1697`）→ 顺序执行命令（`:1702-1757`）→ 末尾 `maeSaveSetup`（`:1760-1766`，`save=True` 时）→ finally 关-if-created（`:1778`）。
- `read_results`：开（`:1871`）→ finally 关-if-created（`:2045`）。
- `export`：开（`:2074`）→ 关-if-created（`:2203`）；`read_history`：`:2447`→`:2536`；`write_history`：`:2557`→`:2684`。
- `run`：**不开后台会话**，`_ensure_gui_session`（`:2946-2951`）拿/建 GUI 会话，从头到尾不关（会话留给用户/后续操作）。
- 结论：**"每批新开"只对自建会话成立**；同 cellview 已有会话（尤其 GUI 会话）会被 `maeOpenSetup` 复用，所以写入类操作能直接作用到正在跑的 GUI 会话上；关闭策略是"谁建谁关，自建才关"。

### 1.3 `read_config` 返回结构与 `run_mode`（问题③）

步骤顺序（`read_config`，`:1321-1671`）：`open_session` → `setup` → `analyses` → `options(env/sim)` → `outputs` → `variables` → `test_variables` → `corner_variables` → `parameters` → `corner_parameters` → `specs` → `current_history`。

- 头部 6 元组读取（`:1342-1352`）：`maeGetSetup`、`maeGetSetup ?typeName "corners"`、`... "variables"`、`... "parameters"`、**`maeGetCurrentRunMode`**、`maeGetJobControlMode`。
- `setup[4]` → `run_mode`（`:1373`）；`setup[5]` → `job_control_mode`（`:1374`）。
- 返回 `config`（`:1638-1657`）键：
  `library, cell, view, tests, corners, corner_variables, test_variables, variables, parameters, corner_parameters, analyses, env_options, sim_options, outputs, specs, run_mode, job_control_mode, current_history`（`:1638-1656`）。
- `outputs` 是 `{test: [{name,type,signal,expression,plot,save,eval_type,yaxis_unit,spec}, ...]}`（解析自 `maeGetTestOutputs` 的制表文本，`:1440-1479`）——**MC 需要的 `plot` 字段已在此**。
- **缺**：无 `run_options`；无 `mc_ready`（`axlIsSimUsingStatParams`）；`run_mode` 只是字符串，无白名单。

### 1.4 `read_results` 现有导出/解析/yield 取法（问题④）

`read_results`（`:1847-2048`）：

1. 开会话（`:1871`），`history` 缺省时用 `_latest_history`（`:1879-1882`；实现 `:795-815`，会逐个 `maeOpenResults/maeCloseResults` 试着打开）。
2. **波形分支**（`request.waveform`）：`_results_dir_for_history`（`:1785-1806`）→ `_find_psf_dir`（`:1808-1845`，`find ... -name logFile`）→ `openResults`/`selectResults`/`ocnPrint` 写远端 txt（`:1922-1935`）→ 下载（`:1943`）→ `parse_ocn_text`（`:1955`，`_maestro_util.py:268-291`）。
3. **默认（点/spec/yield）分支**：
   - 导出：`maeExportOutputView(?session s ?testName t ?historyName h ?view "Detail" ?fileName <远端csv>)`（`:1973-1979`）；
   - 下载：`:1991-1998` → `parse_detail_csv`（`:2003`，`_maestro_util.py:178-265`，兼容多点和单点布局）；
   - `overall_spec`：对每个点、每个 output 的 `pass_fail` 汇总（全 pass→passed，否则 failed，`:2005-2018`）；
   - `overall_yield`：`maeGetOverallYield(history, ?session s)`（`:2021-2027`）→ `parse_overall_yield`（`_maestro_util.py:294-316`，把 `(nil Yield 100 PassedPoints 2 ErrorPoints 0)` 解析成 dict）；
   - 返回 payload（`:2033-2041`）：`history, tests, points, outputs, overall_spec, overall_yield, local_path`。
- **MC 缺口**：没有 `axlWriteMonteCarloResultsCSV`；没有 `maeExportOutputView ?view "Yield"`（mean/std/min/max/Cpk 列）；没有按 output 的统计聚合。
- 进度侧已有：`read_history` 用 `_run_status`（`:694-721`，`axlGetRunStatus(session ?historyName h)`）+ tests/corners 两种 `option`（`:2489-2499`），MC history（`MonteCarlo.N`）名字识别在 `_maestro_util.py:141` 已有。

### 1.5 `run` 的启动调用与步骤（问题⑤）

`run`（`:2933-3073`）：

1. `_ensure_gui_session`（`:2946-2951`）——**仿真必须 GUI 会话**（后台会话曾被 "Received stop signal from user" 杀掉，见 `doc/report/机制-maestro-GUI与后台会话冲突.md`）。
2. 强制 `maeSetJobControlMode("ICRP")`（`:2952-2959`）。
3. 显式 `history` 时设置覆盖目标（`axlSetOverwriteHistory`+`axlSetOverwriteHistoryName`，`:2960-2972`）。
4. 启动：`_start_simulation_with_watchdog`（`:2839-2910`）在**独立线程**里执行 `maeRunSimulation({_session_kw(session)})`（`:2857-2861`，**不带 `?runMode`**），主线程只在有 modal dialog 时做有限次 X11 关闭（`:2874-2907`）。
5. 失败（返回 `nil`）→ `_diagnose_run_failure`（`:2912-2931`）→ 关当前 form → **重试一次**（`:2990-3031`）。
6. 非阻塞：立即返回 `{history, status:"started", session}`（`:3033-3038`）；阻塞：按 `poll_interval` 轮询 `_run_status` 直到 `done/failed` 或超时（`:3040-3071`）。
- **缺口**：`RunRequest`（`:167-175`）无 `run_mode` 字段；`maeRunSimulation` 调用点无 `?runMode`。MC-2 已考证"裸 run 的 `?runMode` 默认是 Single Run"（MC-2 §1.2），所以应显式透传。

### 1.6 其他需要同时动的点

| 位置 | 说明 |
|---|---|
| `maestro.py:69-77` `ReadConfigRequest` | 若要 `include_run_options`/选项白名单开关，加字段 |
| `maestro.py:167-175` `RunRequest` | 加 `run_mode: str \| None = None` |
| `maestro.py:91-106` `ReadResultsRequest` | 加 `monte_carlo: bool`（或按 `history.startswith("MonteCarlo.")` 自动识别） |
| `maestro.py:109-124` `ExportRequest` | 若要保留 MC CSV 产物，可加 `kind="mc_csv"` |
| `maestro.py:3239-3253` `OPERATIONS` | 不新增操作的话**无需改**；HTTP/CLI 注册表（`src/server/api_server.py:325-339`、`src/server/dispatch.py:43-70`）按 dataclass 字段自动转换 |
| `skills/virtuoso-bridge/references/operations.md:157-193` | 对外原子表需同步补 `set_run_option`（可选） |
| `test/live/packages/maestro_e2e_tests.py:199-243` | 写→readback 的 e2e 模式可直接扩 MC 用例 |

### 1.7 `spec/design-concepts/上层/6-maestro.md` 增补点（含现有表行号）

现有锚点（行号为当前文件）：

- §2 操作总表 `:17-30`；§3.1 `read_config` 返回表 `:36-45`；§3.2 write 配置原子表 `:49-67`（`set_env_option/set_sim_option` 在 `:59-60`，`setup_corner` `:62`，`load_corners` `:63`，`set_run_mode` `:64`）。
- §4.1 结果原子 `:71-76`；§4.2 `read_results` `:78-84`。
- §6 历史类 `:100-130`；§7.2 `run` `:141-158`；§9 内部节点 `:169-177`；§10 待定/待验证 `:178-198`。

建议增补（与 MC-1 §4.1、MC-2 §7 合并后的口径）：

1. §3.1（`:36-45`）表加一行：MC run options（枚举/读值）= `axlGetRunOptions` + `axlGetRunOption` + `axlGetRunOptionValue`；可选 `mc_ready = axlIsSimUsingStatParams()`。
2. §3.2（`:49-67`）表尾（`:67` 后）加原子：
   - `set_run_option`：索引 `mode`（run mode 名）、`name`/`value`；底层 `axlPutRunOption` + `axlSetRunOptionValue`（备选 `maeSetRunOption`，文档只保证 2 项）；
   - 可选便利原子 `setup_monte_carlo`（一次设 `mcmethod/mcnumpoints/samplingmode/montecarloseed` 等）。
3. §4.2（`:78-84`）加 MC 结果口径：`axlWriteMonteCarloResultsCSV`（按 test/corner 分文件）与/或 `maeExportOutputView ?view "Yield"`（列含 Yield/Min/Target/Max/Mean/Std Dev/Cpk，见 MC-2 §0.8）；`overall_yield` 保留作交叉校验。
4. §7.2（`:141-158`）加 `run_mode` 参数与 `?runMode` 透传；补"MC 与 sweep 互斥（ADEXL-1742）"、"无 statistics 模型 → SPECTRE-16012"两条前置校验。
5. 新增 §7.3「蒙卡（Monte Carlo）」小节（插在 `:158` 后）：模式/17 项 run option/统计模型前置条件/进度（`axlGetRunStatus`）/结果/限制（许可证、VVO、MC+sweep）。
6. §9（`:169-177`）内部节点表加：MC CSV 导出、`axlIsSimUsingStatParams` 就绪检查。
7. §10（`:178-198`）加待定：17 项可写性与编码真机确认、MC CSV 列格式取样、统计载体（fixture）归属、`mismatchflag` 实例参数。

---

## 2. 测试载体现状（`ssh wsl-gent` 只读实测）

### 2.1 库定位

- 远端主机：`wsl-gent`（hostname `GLIS-DESKTOP`，user `Gent`，CST）。
- 库：`/home/Gent/project/vblog/maestro_tb`（`/home/Gent/project/vblog/cds.lib:8` `DEFINE maestro_tb ...`）。
- 每个 cell 有 `schematic/`（OA `sch.oa`，二进制）与 `maestro/`（`maestro.sdb`=XML setup、`active.state`=当前 test 状态、`test_states/<history>.state`、`results/`）。
- 运行结果根：`/home/Gent/simulation/maestro_tb/<cell>/maestro/results/maestro/<history>/...`（`<point>/<test>/netlist/input.scs`、`psf/spectre.out` 可读）。

### 2.2 三载体对照表（全部来自 setup 与网表只读检查）

| 项 | `maestro_tb/rc_probe` | `maestro_tb/opamp_probe` | `maestro_tb/logic_probe` |
|---|---|---|---|
| tests | `ac`（sdb `:16-39`） | `opamp_ac`/`opamp_dc`/`opamp_tran`（sdb `:20+`） | `logic_tb`（sdb `:17+`） |
| analyses | `ac`（netlist `ac start=1 stop=1G`） | `ac`(1..1G)/`dc`/`tran stop=50u step=10n` | `tran stop=1u` |
| corners（sdb） | `_default` + `e2e_param_corner`（`:6-11`，corner 参数 `location maestro_tb/rc_probe/schematic/R0`） | `_default` + `vdd_high`（`:5-16`，vars `VDD=3.0 VSS=-3.0`） | `_default` + `corner_typ`（`:6-13`，var `vlogic=5`） |
| simulator | `spectre`（每 test tooloptions `option sim`） | `spectre` | `spectre` |
| model file / section | **无**（`modelSetup.modelFiles=nil`；整个 sdb 无 `model*` 字符串） | **无**（同上） | **无**（同上） |
| 网表模型引用 | 纯 analogLib 原语（`vsource`/`resistor`/`capacitor`），无 `include` | ahdlLib `opamp` Verilog-A（`ahdl_include .../ahdlLib/opamp/veriloga/veriloga.va`） | ahdlLib `nand_gate`/`d_ff` Verilog-A（两条 `ahdl_include`） |
| `statistics{}` | **无**（grep 命中的只是 save 选项字段 `simStatisticsInfo`/`simStatistics`，均 nil） | **无**（同上；`mismatchflag` 无从谈起） | **无**（同上） |
| outputs | **0 个**（`active.state` 无 `defstruct`/`outputList`，sdb `<specs></specs>`） | 7 个，**全部 `plot=t`**（opamp_ac: `gain_db`,`ugbw_hz`,`vout_ac`；opamp_dc: `vout_op`；opamp_tran: `vout_final`,`vout_max`,`vout_tran`） | 6 个，**全部 `plot=t`**（`CLK`,`Y`,`Q`,`QB`,`q_high`,`q_low`） |
| 当前 run mode（sdb `<currentmode>`） | `Single Run, Sweeps and Corners`（`:13`） | **`Monte Carlo Sampling`（`:18`，今日被改成 MC）**，`runoptions` 仅含 `mcnumpoints=2`（`:370-376`） | `Single Run, Sweeps and Corners`（`:15`） |

### 2.3 现场观测：opamp_probe 已经跑过一次 MC，且因无 statistics 全灭（重要）

观测时间：**2026-09-28 19:39（CST）**，非本次调研触发（只读旁观）：

- `maestro.sdb` 中已有完成记录：`<historyentry ... runningOrFinished="finished">MonteCarlo.0`（`opamp_probe/maestro/maestro.sdb:3880-4275`），`<currentmode>Monte Carlo Sampling</currentmode>`（`:18`），`<runoptions><mode>Monte Carlo Sampling ... mcnumpoints=2`（`:370-376`）。
- MC 网表：`/home/Gent/simulation/maestro_tb/opamp_probe/maestro/results/maestro/MonteCarlo.0/psf/opamp_ac/netlist/input.scs:29-33`

  ```spectre
  mc1 montecarlo numruns=2 seed=12345 variations=all sampling=lds \
      donominal=no scalarfile="../monteCarlo/mcdata" \
      paramfile="../monteCarlo/mcparam" saveprocessparams=no \
      savemismatchparams=no savefamilyplots=yes savedatainseparatedir=yes \
      wfseparation=yes { ac ac start=1 stop=1G annotate=status ... }
  ```

- 每个点（2 run × 3 test × 2 corner = 12）都失败于同一错误（`.../MonteCarlo.0/1/opamp_ac/groupRunDataDir/psf/spectre.out`）：

  ```text
  Error found by spectre during Monte Carlo analysis `mc1'.
      ERROR (SPECTRE-16012): mc1: Attempt to run Monte Carlo analysis with
      process and mismatch variations, but no variations were specified in
      the statistics block.
  ```

- 汇总：`opamp_probe/maestro/results/maestro/MonteCarlo.0.log` → `Number of points completed: 2`、`Number of simulation errors: 12`、`Estimated yield = 0% (0/2), 2 errors`；`mcdata` 全 0。
- **结论（直接回答"能不能直接跑"）**：**不能**。fixture 无 `statistics{}`；`variations=all` 必然报 `SPECTRE-16012`。同时这也证明"`set_run_mode("Monte Carlo Sampling")` + 现有 `run` 链路"在真机上确实能启动 MC 并产出 `MonteCarlo.N` 与进度/良率数据——**启动链路已通，缺的是统计模型与选项/结果读写**。
- 提醒：如后续复用该环境跑 e2e，opamp_probe 当前**仍停留在 MC 模式**（`Single Run` 测试用例依赖运行前读取的 `run_mode` 原值，见 `test/live/packages/maestro_e2e_tests.py:204,212`），需上层决定是否把环境恢复为 Single Run（本次调研不动作）。

---

## 3. PDK 统计模型清单（`/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/models/spectre/`）

### 3.1 文件级：谁含 `statistics{}`

- 目录共 50 个文件（46 个 `cor_*.scs` + `crn65gplus_2d5_lk_v1d0.scs` + 2 个 `*.va` + `tsmcN65.pcf`）。
- **全目录只有 1 个文件含 `statistics{}`**：`crn65gplus_2d5_lk_v1d0.scs`（135214 行，33 个 `statistics {`；26 个 `mismatch {`，7 个 `process {`）。
- 另有在线副本：`models/online/2.5V/spectre/crn65gplus_2d5_lk_v1d0.scs`（同样 33 个 `statistics`）。
- **所有 `cor_*.scs` 都不含 `statistics{}`，也不 include 任何 `stat*`/`mc_*` section**（`grep -h "section ?= ?stat" cor_*.scs` 为空）。

### 3.2 section 级清单（33 个统计块 = 26 mismatch + 7 process）

process（7 个，参数为 `random*`→`par*` 链，`std=1/3` 或 `1/1`）：

| section | 行 | 内容要点 |
|---|---|---|
| `stat` | `:8460`（statistics `:8482`） | MOS 主链：`random1..10`，各 `std=1/3`；`par1..par10=randomN`（`:8471-8480`） |
| `stat_bip_dio` | `:110555`（`:110559`） | `random1_bip_dio`，`std=1/3` |
| `stat_mom` | `:110567`（`:110571`） | `random1_mom`，`std=1/1` |
| `stat_mim` | `:110579`（`:110583`） | `random1_mim`，`std=1/3` |
| `stat_res` | `:112409`（`:112420`） | `random1..4_res`，`std=1/3` |
| `mc_rfjvar`（内嵌） | `:115080`（`:115091`） | `par1mc_rfjvar`，`std=1/3`（统计块写在 mc 段内部） |
| `mc_rfind`（内嵌） | `:116218`（`:116230`） | `par1_ind`/`par2_ind`，`std=1/3` |

mismatch（26 个，全部 `vary <par> dist=gauss std=1/1`，参数为 PDK 子电路里的 `parn*/parp*/par_*` 失配钩子）：

| 分组 | sections（section 起始行） |
|---|---|
| RF MOS | `stat_mis_rfmos` `:533`、`stat_mis_rfmos_18` `:544`、`stat_mis_rfmos_25` `:555`、`stat_mis_rfmos_33` `:566` |
| RF 无源 | `stat_mis_rfmim` `:579`、`stat_mis_rfrtmom` `:588`、`stat_mis_mim` `:598`、`stat_mis_rtmom` `:607` |
| 电阻 | `stat_mis_disres` `:615`、`stat_mis_res` `:625`、`stat_mis_rfres_sa` `:634`、`stat_mis_rfres_rpo` `:644` |
| 体 MOS | `stat_mis` `:8128`、`stat_mis_hvt` `:8139`、`stat_mis_lvt` `:8150`、`stat_mis_18` `:8161`、`stat_mis_25` `:8172`、`stat_mis_25ud18` `:8183`、`stat_mis_25od33` `:8194`、`stat_mis_33` `:8205` |
| Native MOS | `stat_mis_na` `:8216`、`stat_mis_na25` `:8225`、`stat_mis_na25od33` `:8234`、`stat_mis_na33` `:8245` |
| BJT | `stat_mis_bip` `:8257`、`stat_mis_bip_npn` `:8267` |

示例（mismatch，`:8128-8137`；process，`:8460-8495`）：

```spectre
section stat_mis
statistics { mismatch { vary parn1 dist=gauss std=1/1 ...
                        vary parp2 dist=gauss std=1/1 } }
endsection stat_mis

section stat
parameters random1=0 ... par1=random1 ...
statistics { process { vary random1 dist=gauss std=1/3 ... vary random10 dist=gauss std=1/3 } }
endsection stat
```

注意：process 的统计变量与器件参数之间还有一层放大/敏感性映射，例如 `mc` 段（`:8500`）：
`parameters a1=par1 * 6.0316e+000 * 3 / 2.1`（`:8503`）、`dvthp=...+2.6665e-003*a1...`（`:8513`）。
即 `stat`（随机变量）与 `mc`/`mc_*`（映射到器件参数）**必须成对挂载**，这是文件头注释第 2 条的由来。

### 3.3 `cor_25.scs` 等 corner 文件如何 include 它们

`cor_25.scs`（24 行）本身是薄壳：

```spectre
library 25_cor
section tt_25
include "crn65gplus_2d5_lk_v1d0.scs" section = tt_25
endsection tt_25
... ff_25 / fs_25 / sf_25 / ss_25 同构 ...
endlibrary 25_cor
```

- `cor_25.scs` → big file 的 `tt_25`（`:13655-13755`）；`tt_25` 只 include `noiseflag_25`/`post_simu_25` 并给标称参数，**不 include `stat*`/`mc_*`**。
- 文件头注释（`crn65gplus_2d5_lk_v1d0.scs:523-531`）明说：
  1. mismatch 必须把 `stat_mis_xxx` **与目标 corner** 同时 include；
  2. process 必须把 `stat` **与 `mc_xxx`** 同时 include。
- 因此 ADE 的 Model Library Setup 需要**同一文件多 section 挂载**（corner section + stat section + mc section），**不是** cor 文件自动带出。
- 挂载 API 线索：库内已有 `setup_corner`（`maestro.py:1077-1101`，`axlPutModel`/`axlSetModelFile`/`axlSetModelSection`，corner 级）与 `maeSetEnvOption` 的 `modelFiles` 键（老代码 docstring：`src_bak/.../writer.py:200-209` 例子 `(("modelFiles" (("/path/model.scs" "tt"))))`）。
  **用哪条路径在 IC6.1.8 + 本 PDK 上正确挂 MC section，需真机确认**（`maeSetEnvOption` 的键名/结构 vs corner 级 model；未见现成成功案例）。
- 电阻子电路（`section res`，`:112785+`）的失配开关是**实例参数**：`rppolywo`（subckt `:112839`）形如
  `parameters ... mismatchflag=0 ...`（`:112840`）、`factmis=0.007*geo_fac*par_res*mismatchflag`（`:112841`）。
  即 mismatch 生效需要 **`mismatchflag=1`**；CDF/实例属性名是否直接暴露该参数 → **需真机确认**。

### 3.4 现有 fixture 能不能直接跑 8–10 点 MC？要造载体最小做到什么？

**不能直接跑**（证据：§2.2 无 statistics + §2.3 SPECTRE-16012 实机失败）。最小载体建议（两条路线，按落地成本排序）：

**路线 A（推荐）：新建 1 个 PDK 统计器件的最小 cell**

1. 新建 `maestro_tb/mc_probe`（或任意新 cell），schematic 只放：
   - 1 个 PDK 器件（首选电阻：`tsmcN65` 库的 `rppolywo`/`rnodwo`，模型在 big file `section res` `:112785+`；或 MOS `nch_mac`/`pch_mac`）；
   - 1 个 DC/AC/TRAN 激励（analogLib `vsource` 即可）；
   - 1 个 output 表达式且 `plot=t`（如 `value(VT("/net"))`），并至少 1 条 spec（否则 yield 无意义）。
2. Model Library Setup 挂 big file 的多 section：
   - process：`tt_res`（corner） + `stat_res` + `mc_res`（MOS 则 `tt_25` + `stat` + `mc`/`mc_25`）；
   - mismatch：corner + `stat_mis_res`（MOS 则 `stat_mis_25` 等）；
   - 先只做一种（mismatch-only 最省：corner + `stat_mis_res`）。
3. 实例侧确保 `mismatchflag=1`（若选 mismatch）——**需真机确认 CDF 暴露方式**。
4. ADE 配置：`set_run_mode("Monte Carlo Sampling")`、`mcnumpoints=8..10`、`mcmethod=mismatch/all`、`samplingmode=random`、`montecarloseed` 固定；**1 test × 1 corner**（避免 ADEXL-1742、也把 8~10 点成本压到 8~10 次仿真）。
5. 运行：现有 `run()` 可启动（MC 已在 opamp_probe 上验证能启动）；`?runMode` 透传属代码增补项。
6. 结果：按 MC-2 §0.8 用 `axlWriteMonteCarloResultsCSV` 或 `maeExportOutputView ?view "Yield"` 取样。

**路线 B（不依赖 PDK 符号）：自写带 `statistics{}` 的 .scs 模型挂到现有 cell**

- 写一个小模型文件（含 `statistics { mismatch|process { vary ... } }` + 参数化 subckt/bsource），经 ADE Model Library Setup 挂到 test/corner；
- 现成挂载原子只有 corner 级 `setup_corner(model_file, model_section)`（`maestro.py:1077-1101`），test 级 modelFiles 写入未见实现（老代码只有 SKILL 字符串示例，`src_bak/.../writer.py:200-209`）；
- 需真机确认该挂法是否足以让 Spectre 认到统计块。风险：统计块必须绑定到实际器件参数，纯 ADE design variable 默认不参与 `statistics` 采样。

**结论句**："PDK 有现成的 33 个统计块可用，但三个 fixture 一个都没接；要跑 8–10 点 MC，最小动作是造 1 个单 test/单 corner、1 个统计器件、1 个 plot=t 输出+spec 的新 cell，并把对应 corner+stat(+mc) section 同时挂上；挂载路径与 mismatchflag 需真机确认。"

---

## 4. 旧代码参照（`src_bak/` 与 git 历史）

`src_bak/` 存在（旧 `virtuoso_bridge` 包：`src_bak/virtuoso_bridge/...`）。可用/不可用结论：

**有（但只是管道，不是 MC 实现）**：

| 路径:行 | 内容 | 对 MC 的价值 |
|---|---|---|
| `src_bak/virtuoso_bridge/virtuoso/maestro/writer.py:306-314` | `set_current_run_mode`（`maeSetCurrentRunMode(?runMode "...")`），docstring 举的正是 run mode 字符串 | 与现行 `maestro.py:1115-1117` 同源，可直接参照 |
| `src_bak/.../maestro/writer.py:200-221` | `set_env_option`/`set_sim_option`：`options: SKILL alist string`，示例 `(("modelFiles" (("/path/model.scs" "tt"))))`、`(("temp" "85") ...)` | **modelFiles 挂模型的旧用法样例**（现包已升级为 dict 形态，见 §1.1） |
| `src_bak/.../maestro/writer.py:338-355` | `run_simulation`：只发 `?session`/`?callback`，**没有 `?runMode`** | 说明旧包也没做 MC 显式启动 |
| `src_bak/.../maestro/writer.py:491-540` | `run_and_wait`：`?callback` 写 marker + Python 轮询（非阻塞等待） | 等待/回调的老实现；现行 `run` 用 `axlGetRunStatus` 轮询 |
| `src_bak/.../maestro/reader/runs.py:174-183` | `maeGetOverallSpecStatus` + `maeGetOverallYield` + Detail CSV 解析 | 现包 `read_results` 的 yield 口径来源（`maestro.py:2005-2029`） |
| `src_bak/.../maestro/reader/session.py:33-38` | history 识别正则含 `Interactive.N`/`MonteCarlo.N`（+`.RO` 变体） | 现行 `_maestro_util.py:141` 同样含 `MonteCarlo`，MC history 名字识别已具备 |
| `src_bak/.../maestro/reader/bundle.py:123` | `maeGetCurrentRunMode(?session ...)` | run mode 读回的老用法 |
| `src_bak/.../maestro/snapshot_filter.yaml:29` | 快照过滤字段 `currentmode` | 快照对 run mode 的覆盖 |
| `src_bak/.../maestro/ops.py:107-128` | 旧 facade 列出 `set_env_option`/`set_sim_option`/`set_current_run_mode`/`run_simulation`/`run_and_wait` | 接口对照 |

**无（明确没有可抄的 MC/statistics 实现）**：

- `git log --all -S 'maeSetRunOption'`、`-S 'mcmethod'`、`-S 'axlWriteMonteCarloResultsCSV'` 均为空 → 仓库历史从未提交过 MC 选项/结果代码。
- 全仓 `src_bak` + `skills_bak` 内搜 `statistics`/`mcmethod`：无实现命中（只有 `skills_bak/spectre/SKILL.md:260` 的 Spectre 原生 `montecarlo`/`noiseruns` 说明、以及本仓报告文本）。
- 结论：**"无旧 MC 实现可借鉴"**；可借鉴的只有 run mode 透传、env/sim option alist 形态、`maeRunSimulation(+callback)`、`maeGetOverallYield`、`MonteCarlo.N` history 识别。

---

## 5. 未确认 / 需真机确认清单

1. `axlPutRunOption`+`axlSetRunOptionValue` 对 17 项里非 `mcmethod/mcnumpoints` 的 15 项在当前 IC6.1.8 的可写性与取值编码（尤其 `mcStopEarly/mcStopMethod/mcYieldTarget/mcYieldAlphaLimit`）——MC-1 §3.2 同列。
2. ADE 侧如何把 `stat`/`stat_mis_*`/`mc_*` section 与 corner 同时挂到 test（`maeSetEnvOption modelFiles` 结构 vs corner 级 `axlPutModel`）；205 行附录复现命令只做了文件级确认。
3. 电阻实例 `mismatchflag` 在 CDF/实例属性里的暴露方式与默认值（子电路默认 0，如 `rppolywo :112840`/`rnodwo :112789`）。
4. `axlWriteMonteCarloResultsCSV` 的 CSV 列格式（MC-2 §0.9：官方无样例）；实测样品需跑通 MC 后取样。
5. `maeRunSimulation(?runMode ...)` 与"先 `maeSetCurrentRunMode` 再裸 run"的差异（MC-2 §1.2：裸 run 文档默认 Single Run；真机上 opamp_probe 曾以"先设 mode 再 run"启动 MC——但该 run 的 mode 是否由 session 生效，还是由 MC.0 的 sdb checkpoint 里冻结的 `currentmode` 生效，未做对照，**未确认**）。
6. `donominal`/`saveprocess`/`savemismatch` 等默认值在本环境与 netlist 的对应（本次 MC.0 netlist 显示 `donominal=no saveprocessparams=no savemismatchparams=no`，而 MC-1 文档默认 `donominal=1`，属"当前 setup 值 vs 文档默认"的差异，未逐项读回）。

---

## 6. 证据与复现（只读）

本地：

```powershell
# 代码/规格行号
Select-String -Path src\pyapi\packages\maestro.py -Pattern '_command_exprs|set_run_mode|set_env_option|_open_session|def read_config|def read_results|def run|_ensure_gui_session'
$c = Get-Content src\pyapi\packages\maestro.py; $c[1637..1656]      # read_config 返回结构
$c[1869..2040]                                                      # read_results 主分支
$c[2932..3071]                                                      # run
# 文档服务（核对函数名）
Invoke-RestMethod 'http://127.0.0.1:8123/api/find?q=maeSetRunOption'
Invoke-RestMethod 'http://127.0.0.1:8123/api/info?name=axlGetRunOptions'
Invoke-RestMethod 'http://127.0.0.1:8123/api/info?name=axlWriteMonteCarloResultsCSV'
Invoke-RestMethod 'http://127.0.0.1:8123/api/info?name=axlIsSimUsingStatParams'
```

远端（`ssh wsl-gent ...`，全部只读）：

```bash
# 载体 setup
grep -a -n '<currentmode>\|<test>\|<corner' /home/Gent/project/vblog/maestro_tb/{rc_probe,opamp_probe,logic_probe}/maestro/maestro.sdb
grep -a -A 3 '<component Name="modelSetup"' /home/Gent/project/vblog/maestro_tb/rc_probe/maestro/active.state   # modelFiles=nil
grep -a -c '<field Name="plot" Type="symbol">t' /home/Gent/project/vblog/maestro_tb/opamp_probe/maestro/active.state
# 网表与失败证据
cat /home/Gent/simulation/maestro_tb/opamp_probe/maestro/results/maestro/MonteCarlo.0/psf/opamp_ac/netlist/input.scs
grep -a 'SPECTRE-16012' /home/Gent/simulation/maestro_tb/opamp_probe/maestro/results/maestro/MonteCarlo.0/1/opamp_ac/groupRunDataDir/psf/spectre.out
cat /home/Gent/project/vblog/maestro_tb/opamp_probe/maestro/results/maestro/MonteCarlo.0.log
# PDK 统计块
grep -r -a -l 'statistics' /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/models/spectre/
grep -n -E '^section stat|statistics \{|process \{| mismatch \{' /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/models/spectre/crn65gplus_2d5_lk_v1d0.scs
cat /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/models/spectre/cor_25.scs
```

（报告完；本文件为本次调研唯一写入产物。）
