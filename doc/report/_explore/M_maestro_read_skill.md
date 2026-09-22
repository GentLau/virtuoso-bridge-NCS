# M_maestro_read_skill — Maestro 读取/导出 SKILL 与数据格式参考

> 目标：从旧 reader / waveform viewer 代码中提取“Maestro 读结果、读 setup、做快照、导波形、开关波形窗口”所需的最小 SKILL 集合和数据合同，供新五接口实现直接照抄或改写。
>
> 范围：只分析旧代码的读取/导出路径；不把 GUI 点击、SSH 通道、旧 `VirtuosoClient` 带进新上层。新上层最终只能调用 `execute_skill`、`run_command`、`upload_file`、`download_file`、`run_gui_command`、`run_spectre_command`，以及只读 `query`。

## 0. 源文件别名

后文用短名引用，完整路径如下：

| 短名 | 完整路径 |
|---|---|
| `runs.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/reader/runs.py` |
| `bundle.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/reader/bundle.py` |
| `snapshot.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/reader/snapshot.py` |
| `session.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/reader/session.py` |
| `_parse_sdb.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/reader/_parse_sdb.py` |
| `_parse_skill.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/reader/_parse_skill.py` |
| `_skill.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/reader/_skill.py` |
| `skill_output.py` | `src_bak/virtuoso_bridge/virtuoso/skill_output.py` |
| `waveform_viewer.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/waveform_viewer.py` |
| `writer.py` | `src_bak/virtuoso_bridge/virtuoso/maestro/writer.py` |
| `filter.yaml` | `src_bak/virtuoso_bridge/virtuoso/maestro/snapshot_filter.yaml` |
| `parsers.py` | `src_bak/virtuoso_bridge/spectre/parsers.py` |
| `models.py` | `src/pyapi/models.py` |
| `middle.py` | `src/transport/middle.py` |

## 1. 结论：最短可迁移调用链

1. **定位窗口/session**：一次 `execute_skill` 调 `hiGetCurrentWindow`、`cw->davSession`、`hiGetWindowList()`、`maeGetSessions()`；返回四个 top-level slot（`session.py:65-112`）。
2. **列 history**：一次 `execute_skill` 调 `getDirFiles(<readPath>/<cell>/<view>/results/maestro)`，本地用 `.rdb` 锚点和自然排序/ mtime 排序解析（`bundle.py:138`、`session.py:115-175`）。
3. **当前 history**：`axlGetCurrentHistory(session)` 返回句柄；依次读 `~>name`、`~>historyName`、`~>run`、`~>runName`，取第一个非 nil 字符串（`bundle.py:126-131`、`bundle.py:200-203`）。
4. **读运行状态**：读 `maeGetCurrentRunMode`、`maeGetJobControlMode`、`errset(maeGetRunPlan(...))`、`maeGetSimulationMessages(...)`；旧 reader 没有调用 `axlGetRunStatus`（`bundle.py:123-134`）。
5. **找“最新且有结果”的 history**：按目录自然序倒序，逐个 `maeOpenResults` → `maeGetResultOutputs` → `maeCloseResults`；首个非 nil 就算有结果（`runs.py:186-210`）。
6. **读结果点/spec/yield**：`maeExportOutputView(?view "Detail")` 写远程 CSV，`download_file` 取回，Python 解析 points/outputs/spec/pass_fail；再调 `maeGetOverallSpecStatus()` 和 `maeGetOverallYield(history)`（`runs.py:118-183`、`runs.py:224-314`）。
7. **导单条波形**：先 `maeOpenResults(?history ...)` 找真实 results dir，校验后关闭 Maestro results；再 `openResults(dir)` → `selectResults(analysis)` → `ocnPrint(expr ?output remote.txt)` → 下载 → 删远程临时文件（`runs.py:385-425`）。
8. **做完整快照**：`full_bundle` 收集 setup + 路径；下载 `<view>.sdb`、`active.state`；过滤 XML；按 YAML 白名单对 `<history>` 下的 netlist/psf 打包下载（`snapshot.py:60-80`、`snapshot.py:174-323`、`snapshot.py:429-515`）。
9. **开关波形窗口**：生成一段 `isCallable(...)` 守卫 + `maeOpenSetup` + `maeOpenResults` + `v`/`maeGetOutputValue` + `awvCreatePlotWindow` + `awvPlotWaveform` 的 SKILL；关闭时 `hiCloseWindow` + `maeCloseSession(?forceClose t)`，并复读窗口/session 列表确认关闭（`waveform_viewer.py:35-181`）。

## 2. 通用执行与返回约定

### 2.1 `execute_skill` 包装器

旧 reader 的 `_q` 模板原文（`_skill.py:25-34`；`label` 和 `expr` 由 Python 填入）：

```skill
let((rbResult)
  rbResult = <expr>
  printf("[%s read] <label>\n" nth(2 parseString(getCurrentTime())))
  rbResult)
```

- 用途：执行任意读取表达式，同时给 CIW 留时间戳 breadcrumb；真正的数据仍取 `VirtuosoResult.output`（`_skill.py:25-34`）。
- 参数注入：`label`/`expr` 直接拼进 SKILL 文本；旧代码没有统一调用 `escape_skill_string`（`_skill.py:25-33`）。新实现必须对所有用户字符串做 SKILL 字符串转义，参考 `escape_skill_string` 只转义反斜杠和双引号（`src_bak/virtuoso_bridge/virtuoso/ops.py:7-18`）。
- 返回值： `(r.output or "")` 原文返回，不做 alist→dict 解码（`_skill.py:33-34`）。
- 新接口等价：`middle.execute_skill(skill, timeout=..., token=...)`，读 `VirtuosoResult.output/status/errors/log`（`models.py:24-45`、`models.py:130-138`）。

### 2.2 SKILL 文本解析

`_parse_skill.py` 只是转发共享 tokenizer（`_parse_skill.py:1-17`）。核心规则来自 `skill_output.py`：

- `tokenize_top_level` 识别字符串和括号，切 top-level token；可配置是否保留 group/string/atom（`skill_output.py:22-56`）。
- `parse_sexpr`：`nil→None`、`t→True`、列表递归、字符串反转义，其余 atom 保留为字符串（`skill_output.py:69-95`）。
- `parse_skill_str_list` 递归收集列表或裸字符串中的所有字符串（`skill_output.py:6-19`）。
- 注意：数字 atom、session 句柄按 `parse_sexpr` 仍是字符串；`parse_skill_str_list` 会完全忽略它们（`skill_output.py:69-95`、`skill_output.py:186-194`）。

### 2.3 session 提取

`_get_test` 模板原文（`_skill.py:37-44`）：

```skill
maeGetSetup(?session "<session>")
```

- 解析：从 `output` 中正则找第一个双引号字符串；空/nil 返回 `""`（`_skill.py:39-44`）。
- 用于后续所有 `?testName` 参数，因为多数 `mae*` API 需要显式 test（`runs.py:108-116`、`bundle.py:166-174`）。

## 3. SKILL 清单

### 3.1 聚焦窗口、session、标题

模板原文（`session.py:76-84`）：

```skill
let((cw)
  cw = hiGetCurrentWindow()
  list(
    if(cw hiGetWindowName(cw) nil)
    if(cw cw->davSession nil)
    mapcar(lambda((w) hiGetWindowName(w)) hiGetWindowList())
    maeGetSessions()))
```

- 用途：一次往返同时取聚焦窗口标题、该窗口绑定的 `davSession`、全部标题、全部 Maestro session（`session.py:65-84`）。
- 参数：无；依赖 `hiGetCurrentWindow()` 的焦点（`session.py:76-83`）。
- 执行：`client.execute_skill` 一次（`session.py:76-84`）。
- 解析：剥最外层括号后按 top-level 切 4 个 slot；`title`/`session` 剥引号，后两个 slot 用 `_parse_skill_str_list`（`session.py:85-105`）。
- 标题正则原文：`ADE\s+(Assembler|Explorer)\s+(Editing|Reading):\s+(\S+)\s+(\S+)\s+([^\s*]+)(\*?)(?:\s+Version:\s*\S+(?:\s*-\s*\S+)?)?\s*$`（`session.py:25-32`）。
- 输出字段：`application/lib/cell/view/mode/unsaved`；只解析聚焦标题，不混用其它窗口字段（`session.py:41-61`、`session.py:96-112`）。

### 3.2 brief bundle：setup、analysis、选项

模板原文（`bundle.py:73-81`）：

```skill
list(
  ddGetObj("<lib>")~>readPath
  maeGetSetup(?session "<sess>")
  maeGetEnabledAnalysis(car(maeGetSetup(?session "<sess>")) ?session "<sess>")
  mapcar(lambda((a) maeGetAnalysis(car(maeGetSetup(?session "<sess>")) a ?session "<sess>"))
         maeGetEnabledAnalysis(car(maeGetSetup(?session "<sess>")) ?session "<sess>"))
)
```

- 用途：约 150ms 的 brief snapshot；不下载文件（`snapshot.py:5-7`、`snapshot.py:464-472`）。
- 参数：`lib/sess` 直接填入；test 由 `maeGetSetup` 的第一个字符串决定（`bundle.py:83-87`）。
- 执行：一次 `execute_skill`（`bundle.py:82`）。
- 解析：`_split_top_level(..., 4)`；`_unwrap_errset` 去 `errset` 外层；`_parse_skill_str_list` 取 test/enabled；每个 analysis 单独成为一个 section（`bundle.py:32-56`、`bundle.py:83-98`）。

### 3.3 full bundle：完整 setup 探针

探测分两轮。第一轮模板（`bundle.py:166-170`）：

```skill
list(
  maeGetSetup(?session "<sess>")
  maeGetEnabledAnalysis(car(maeGetSetup(?session "<sess>")) ?session "<sess>"))
```

第二轮把 `_PROBES_TEMPLATE` 逐项 `.format()` 后拼成一个 `list(...)`（`bundle.py:176-189`）。模板顺序与原文如下（`bundle.py:113-140`）：

```skill
list(
  ddGetObj("<lib>")~>readPath
  maeGetSetup(?session "<sess>")
  maeGetEnabledAnalysis("<test>" ?session "<sess>")
  maeGetAnalysis("<test>" "<ana>" ?session "<sess>")          # 每个 enabled ana 一项
  maeGetEnvOption("<test>" ?session "<sess>")
  maeGetSimOption("<test>" ?session "<sess>")
  mapcar(lambda((o) list(o~>name o~>type o~>signal o~>expression
                         o~>plot o~>save o~>evalType o~>yaxisUnit o~>spec))
         maeGetTestOutputs("<test>" ?session "<sess>"))
  maeGetCurrentRunMode(?session "<sess>")
  maeGetJobControlMode(?session "<sess>")
  errset(maeGetRunPlan(?session "<sess>"))
  errset(let((h)
    h = axlGetCurrentHistory("<sess>")
    when(h list(h~>name h~>historyName h~>run h~>runName))))
  errset(maeGetSimulationMessages(?session "<sess>" ?msgType "error"))
  errset(maeGetSimulationMessages(?session "<sess>" ?msgType "warning"))
  errset(maeGetSimulationMessages(?session "<sess>" ?msgType "info"))
  getDirFiles(strcat(ddGetObj("<lib>")~>readPath "/<cell>/<view>/results/maestro"))
  errset(asiGetAnalogRunDir(asiGetSession("<sess>"))))
```

- 用途：快照 setup 的规范化 raw section，并给磁盘 dump 提供 `lib_path/scratch_root/hist_files/current_history`（`bundle.py:143-158`、`bundle.py:191-212`）。
- 参数注入：`sess/lib/cell/view/test` 通过 `.format()`；每次调用都重新拼 SKILL，不用共享 let 变量（`bundle.py:105-112`、`bundle.py:176-188`）。
- 执行：第一轮一次 + 第二轮一次 `execute_skill`（`bundle.py:166-188`）。
- 解析：`_split_top_level` 按 expected slot 数切；`_unwrap_errset` 去 errset；路径项剥引号；history 列表用第一个非 nil 字符串；目录列表用 `_parse_skill_str_list`（`bundle.py:32-56`、`bundle.py:193-211`、`bundle.py:253-261`）。
- `scratch_root`：从 `asiGetAnalogRunDir` 结果中找 `"/<lib>/<cell>/<view>/results/maestro"`，截取前缀（`bundle.py:206-211`）。

### 3.4 列 history

旧代码列 history 的 SKILL 原文是 `getDirFiles` 探针（`bundle.py:138`）：

```skill
getDirFiles(strcat(ddGetObj("<lib>")~>readPath "/<cell>/<view>/results/maestro"))
```

另一个“只找有结果的最新 history”模板先自己构造目录（`runs.py:191-196`）：

```skill
let((p d)
  p = ddGetObj("<lib>")~>readPath
  d = strcat(p "/<cell>/maestro/results/maestro")
  if(isDir(d) getDirFiles(d) nil))
```

- 参数：`lib`、`cell`；第二条把 view 固定为 `maestro`，自定义 view 名不会命中（`runs.py:191-196`）。
- 执行：一次 `execute_skill`，输出给 Python 解析（`runs.py:191-197`、`bundle.py:138`）。
- 解析：`_parse_skill_str_list` 收集文件名；`natural_sort_histories` 只把 `<name>.rdb` 和裸 `Interactive.N`/`MonteCarlo.N` 当作 history；然后自然排序（`runs.py:197-198`、`session.py:131-151`）。
- 命名坑：history 可叫 `Interactive.0.RO`、`closeloop_PVT_postsim`、`sweep_set.3`，不能按固定前缀判断（`session.py:33-38`）。
- mtime 排序才是“最新”的首选：`_fetch_mtimes_via_shell` 用 `find ... -printf '%T@ %f\n'`，本地模式用 `Path.stat().st_mtime`（`bundle.py:264-295`）。
- `sort_histories_by_mtime` 允许 `.rdb/.log/.msg.db` 贡献，取同一 history 的最大 mtime，倒序（`session.py:154-175`）。

### 3.5 当前 history

模板原文（`bundle.py:130-131`）：

```skill
errset(let((h)
  h = axlGetCurrentHistory("<sess>")
  when(h list(h~>name h~>historyName h~>run h~>runName))))
```

- 用途：回答“GUI 当前显示/绑定的是哪条 history”（`bundle.py:126-131`）。
- 参数：`sess`（`davSession`）直接填入（`bundle.py:200-203`）。
- 执行：包含在 full bundle 的单个 `list(...)` 中（`bundle.py:187-188`）。
- 解析：`_unwrap_errset` 后正则找所有引号字符串，返回第一个非空值；兼容 IC6.1.8 的 `~>name == nil`（`bundle.py:200-203`、`bundle.py:253-261`）。
- 优先级：snapshot 自动选历史时是 `mtime > current_history > natural_sort`，不要优先相信 GUI 当前 history（`snapshot.py:490-508`）。

### 3.6 查运行状态、模式和消息

旧 reader 用于“运行状态”的是下面五个探针（`bundle.py:123-134`）：

```skill
maeGetCurrentRunMode(?session "<sess>")
maeGetJobControlMode(?session "<sess>")
errset(maeGetRunPlan(?session "<sess>"))
errset(maeGetSimulationMessages(?session "<sess>" ?msgType "error"))
errset(maeGetSimulationMessages(?session "<sess>" ?msgType "warning"))
errset(maeGetSimulationMessages(?session "<sess>" ?msgType "info"))
```

- 返回：全部按 raw SKILL 文本保存；reader 不做状态枚举映射（`bundle.py:15-18`、`snapshot.py:83-95`）。
- “有结果”判定另有模板（`runs.py:200-206`）：

```skill
when(maeOpenResults(?history "<h>")
  let((outs)
    outs = maeGetResultOutputs(?testName "<test>")
    maeCloseResults()
    outs))
```

- 解析：返回非空且不等于 `nil` 即为有结果；本函数没有轮询，也不判断 run 是否完成（`runs.py:199-210`）。
- 运行完成边界在旧 writer：`maeRunSimulation(?callback ...)` 注册 callback，callback 用 `system("echo done > <marker>")` 写文件，Python 轮询 marker（`writer.py:338-355`、`writer.py:372-417`、`writer.py:491-538`）。
- 新实现建议：把“配置状态”“run 是否在跑”“结果是否可用”拆成三个明确结果，不要复用旧 raw text 的模糊语义。

### 3.7 最新有效 history 的完整流程

模板原文（`runs.py:191-206`）：

```skill
let((p d)
  p = ddGetObj("<lib>")~>readPath
  d = strcat(p "/<cell>/maestro/results/maestro")
  if(isDir(d) getDirFiles(d) nil))
```

随后 Python 对文件名倒序，逐条执行（`runs.py:197-209`）：

```skill
when(maeOpenResults(?history "<h>")
  let((outs)
    outs = maeGetResultOutputs(?testName "<test>")
    maeCloseResults()
    outs))
```

- 参数：`lib/cell/test`；`test` 来自 `maeGetSetup` 的第一个 test（`runs.py:186-203`）。
- 执行：一次目录调用 + 每个候选 history 一次 `execute_skill`（`runs.py:191-206`）。
- 解析：目录名走 `natural_sort_histories`，倒序；结果探测只检查 `output` 非空/non-nil（`runs.py:197-209`）。
- 风险：每条候选都会打开/关闭 Maestro results；结果上下文是共享状态，不能并发扫描（`runs.py:201-205`）。

### 3.8 导出 Detail CSV

导出模板原文（`runs.py:137-147`）：

```skill
maeExportOutputView(
  ?session "<session>"
  ?testName "<test>"
  ?historyName "<latest_history>"
  ?view "Detail"
  ?fileName "/tmp/vb_results_<uuid>.csv"
)
```

- 参数：`session/test/history` 直接填入；远程文件名用 UUID，避免并发碰撞（`runs.py:137-147`）。
- 执行：通过 `_q` 执行，保留 raw return；该 return 在不同 Cadence 版本可能是文件名、`t` 或 `nil`（`runs.py:132-147`）。
- 成功判定：**不要看 SKILL 返回值**；以 `download_file` 是否把 CSV 落到本地为准（`runs.py:148-162`、`test_bak/test_maestro_read_results.py:134-161`）。
- 清理：本地 `Path.unlink()`；远端 `deleteFile("<remote_csv>")`（`runs.py:163-172`）。
- 解析：`_parse_detail_csv` 是纯 Python，返回 `history/tests/points/outputs`（`runs.py:178-183`、`runs.py:224-314`）。

### 3.9 overall spec 与 yield

模板原文（`runs.py:174-176`）：

```skill
maeGetOverallSpecStatus()
maeGetOverallYield("<latest_history>")
```

- 单输出 spec 未走旧 reader；Cadence 参考给出 `maeGetSpecStatus("out" "test") => "fail"`（`skills/virtuoso/references/maestro-skill-api.md:378-380`），旧路径只用 overall + CSV。参数上 spec 模板不带 history，yield 模板带 latest history（`runs.py:174-176`）。
- 执行：各一次 `_q`，均在 CSV 下载和解析之后（`runs.py:174-180`）。
- 解析：`_unquote_atom` 只做 `strip()`、去最外层双引号；空或 `nil` 变 `None`，其它原样保留（`runs.py:317-321`）。
- yield 可能是整个 SKILL list 文本，例如 `(nil Yield 100 PassedPoints 3 ...)`；旧代码不展开它（`runs.py:54-69`、`runs.py:179-180`）。

### 3.10 导出单条 OCEAN 波形

history 自动识别模板（`runs.py:390-392`）：

```skill
asiGetResultsDir(asiGetCurrentSession())
```

得到路径后用 Python 正则取 `runs.py:392` 的 `/maestro/results/maestro/<history>/`。之后完整调用序列原文如下（`runs.py:401-421`）：

```skill
maeOpenResults(?history "<history>")

asiGetResultsDir(asiGetCurrentSession())

maeCloseResults()

openResults("<results_dir>")

selectResults("<analysis>")

ocnPrint(<expression> ?numberNotation '<suffix|engineering|scientific|none>
         [?precision <1..16>] [?width <>=4>]
         ?numSpaces 1
         ?output "/tmp/vb_wave_<safe_history>_<ms>_<nonce>.txt")
```

- 路径安全：history 先经 `_history_token`，只保留 `[A-Za-z0-9_.-]`；空值变 `unknown`（`_skill.py:12-15`）。
- 临时文件：`/tmp/vb_wave_<safe_history>_<ms>_<nonce>.txt`；成功后 `download_file` 再 `deleteFile`（`_skill.py:18-22`、`runs.py:401-425`）。
- 参数校验：`precision` 必须 `int` 且 1..16；`width` 必须 `int` 且 >=4；notation 只能是四个枚举之一（`runs.py:360-377`）。
- 路径校验：非空、非 `nil`、不含 `tmpADE`，且必须包含 `/<history>/`（`runs.py:410-415`）。
- 执行：每一步单独 `execute_skill`，OCEAN 状态跨调用持久；新实现仍需保证串行（`runs.py:405-421`）。
- 返回：仅返回传入的 `local_path`；不解析波形正文（`runs.py:358`、`runs.py:423-425`）。

### 3.11 开关 AWV/ViVA 波形窗口

窗口引用模板：正整数直接变 `window(<n>)`；字符串还接受 `window:<n>` 和 `window(<n>)`（`waveform_viewer.py:16-32`）。

#### 打开窗口：外层骨架

下面是源码生成结果的等价模板；`{...}` 是 Python 填入值，`<signal-block>` 每个 signal 重复一次（`waveform_viewer.py:107-143`）：

```skill
let((vbSession vbResultsOpenResult vbResultsOpen vbResultsDir vbRawResultsOpen
     vbWaveforms vbWaveform vbWaveResult vbTestName vbTestNamesResult vbTestNames
     vbOutputResult vbWindowResult vbWindowId vbPlotResult vbOpenResult vbOpenOk)
  vbOpenOk = nil
  vbOpenResult = errset(progn(
    unless(and(isCallable('maeOpenSetup) isCallable('maeOpenResults)
               isCallable('maeGetResultTests) isCallable('maeGetOutputValue)
               isCallable('openResults) isCallable('awvCreatePlotWindow)
               isCallable('awvPlotWaveform) isCallable('v)
               isCallable('hiCloseWindow) isCallable('maeCloseSession))
      error("waveform viewer API unavailable"))
    vbSession = maeOpenSetup("{lib}" "{cell}" "{view}"
                             ?application "{application}" ?mode "r")
    unless(vbSession error("open maestro failed"))
    vbResultsOpenResult = errset(maeOpenResults(?session vbSession
                                               ?history "{history}") nil)
    vbResultsOpen = if(vbResultsOpenResult then car(vbResultsOpenResult) else nil)
    unless(vbResultsOpen error("open results failed"))
    vbResultsDir = {results_dir_expr}
    vbRawResultsOpen = {raw_open_expr}
    when(vbResultsDir && !vbRawResultsOpen error("open raw results failed"))
    vbTestName = "{test}"
    vbWaveforms = nil
    <signal-block>
    vbWindowResult = errset(awvCreatePlotWindow() nil)
    vbWindowId = if(vbWindowResult then car(vbWindowResult) else nil)
    unless(vbWindowId error("create waveform window failed"))
    vbPlotResult = errset(awvPlotWaveform(vbWindowId vbWaveforms
                                         ?expr list("<sig1>" "<sig2>")) nil)
    unless(vbPlotResult && car(vbPlotResult) error("plot waveform failed"))
    vbOpenOk = t
    list("opened" "{lib}" "{cell}" "{view}" "{history}" vbSession vbWindowId)) nil)
  unless(vbOpenOk
    when(vbWindowId errset(hiCloseWindow(vbWindowId) nil))
    when(vbSession errset(maeCloseSession(?session vbSession ?forceClose t) nil)))
  unless(vbOpenResult error("open waveform viewer failed"))
  car(vbOpenResult))
```

#### 打开窗口：每个 signal 的子块

模板原文（`waveform_viewer.py:89-105`）：

```skill
vbWaveform = nil
vbWaveResult = if(vbRawResultsOpen
  then errset(v("<signal>" ?result "<result>" ?resultsDir vbResultsDir) nil)
  else errset(v("<signal>" ?result "<result>") nil))
vbWaveform = if(vbWaveResult then car(vbWaveResult) else nil)
unless(vbWaveform
  when(vbTestName == ""
    vbTestNamesResult = errset(maeGetResultTests() nil)
    vbTestNames = if(vbTestNamesResult then car(vbTestNamesResult) else nil)
    when(vbTestNames vbTestName = car(vbTestNames)))
  when(vbTestName != ""
    vbOutputResult = <output_value_expr>
    vbWaveform = if(vbOutputResult then car(vbOutputResult) else nil)))
unless(vbWaveform error("missing waveform: <signal>"))
vbWaveforms = append(vbWaveforms list(vbWaveform))
```

- 有显式 `test` 时，`<output_value_expr>` 是 `errset(maeGetOutputValue("<signal>" "<test>") nil)`（`waveform_viewer.py:84-88`）。
- 没有 `test` 时，`<output_value_expr>` 是 `errset(maeGetOutputValue("<signal>" vbTestName) nil)`，先从 `maeGetResultTests()` 取第一个 test（`waveform_viewer.py:87-102`）。
- `results_dir` 为 `None` 时：`results_dir_expr = nil`、`raw_open_expr = nil`；不为 `None` 时：`vbResultsDir = "<dir>"`、`vbRawResultsOpen = car(errset(openResults("<dir>") nil))`，且 raw open 失败必须报错（`waveform_viewer.py:73-79`、`waveform_viewer.py:125-127`）。
- 所有窗口/plot/Waveform 调用都包在 `errset(..., nil)` 或 `isCallable` 守卫中；失败时清理已建窗口和 session（`waveform_viewer.py:112-142`）。
- 返回 shape：`("opened" lib cell view history vbSession vbWindowId)`；调用者保存 session/window 做确定性清理（`waveform_viewer.py:137`、`waveform_viewer.py:200-203`）。

#### 关闭窗口

模板原文（`waveform_viewer.py:161-180`）：

```skill
let((vbWindow vbSession vbWindowCloseResult vbSessionCloseResult
     vbWindowsResult vbWindowsAfter vbSessionsResult vbSessionsAfter)
  vbWindow = <window(n) | nil>
  vbSession = <"session" | nil>
  when(vbWindow
    vbWindowCloseResult = errset(hiCloseWindow(vbWindow) nil)
    unless(vbWindowCloseResult error("close waveform window failed"))
    vbWindowsResult = errset(hiGetWindowList() nil)
    unless(vbWindowsResult error("check waveform window close failed"))
    vbWindowsAfter = car(vbWindowsResult)
    when(member(vbWindow vbWindowsAfter) error("close waveform window failed")))
  when(vbSession
    vbSessionCloseResult = errset(maeCloseSession(?session vbSession ?forceClose t) nil)
    unless(vbSessionCloseResult error("close waveform session failed"))
    vbSessionsResult = errset(maeGetSessions() nil)
    unless(vbSessionsResult error("check waveform session close failed"))
    vbSessionsAfter = car(vbSessionsResult)
    when(member(vbSession vbSessionsAfter) error("close waveform session failed")))
  list("closed" vbSession vbWindow))
```

- 参数：`window` 或 `session` 至少一个；session 不能是空白（`waveform_viewer.py:152-160`）。
- 执行：一次 `execute_skill`；默认 timeout 30s，打开默认 60s（`waveform_viewer.py:184-228`）。
- 返回解析：字符串项可用 `_parse_skill_str_list`；数值 window 用 `parse_sexpr` 时仍可能是字符串，传给 close 的 `_skill_window_ref` 会接受 digit string（`skill_output.py:69-95`、`waveform_viewer.py:16-32`）。
- 保留 session 的原因：AWV 窗口引用打开的 result database，不能在同一次调用末尾关 Maestro session（`waveform_viewer.py:47-51`）。

## 4. 数据格式

### 4.1 Detail CSV 的两代形态

多 point 样例（`test_bak/test_maestro_read_results.py:34-44`）：

```csv
,,Parameter,Nominal,,,

Point,Test,Output,Nominal,Spec,Weight,Pass/Fail
Parameters: VDD=0.9,,,,,,
1,inv_test,Gain_dB,21.63,,,
1,inv_test,Delay_ps,12.4,< 15p,1,passed
Parameters: VDD=1.1,,,,,,
2,inv_test,Gain_dB,22.81,,,
2,inv_test,Delay_ps,9.8,< 15p,1,passed
```

单 point、无 `Point` 列的样例（`test_bak/test_maestro_read_results.py:46-54`）：

```csv
,Parameter,Nominal,,,
Title,Detail Results,,,,

Test,Output,Nominal,Spec,Weight,Pass/Fail
TRAN,IN,,,,
TRAN,OUT,,,,
TRAN,out_max,822.7e-3,< 1,1,passed
```

解析规则（`runs.py:224-314`）：

| 规则 | 行为 | 出处 |
|---|---|---|
| 空行 | 跳过 | `runs.py:232-234` |
| 单 point 表头 | 前 6 列等于 `Test,Output,Nominal,Spec,Weight,Pass/Fail` 时置 `no_point_detail=True` | `runs.py:235-239` |
| 新 point | 首列以 `Parameters:` 开头；按逗号拆 `K=V`；point 号按出现顺序从 1 递增 | `runs.py:240-252` |
| 多 point 数据 | 列序 `point,test,output,nominal,spec,weight,pass_fail`；不足列补空串 | `runs.py:280-296` |
| 单 point 数据 | 列序 `test,output,nominal,spec,weight,pass_fail`；没有 point 行时自动建 point=1 | `runs.py:258-279` |
| 引号逗号 | 交给标准库 `csv.reader` 处理 | `runs.py:231-232`、`runs.py:284-285` |
| 输出键 | 同一 point 内用 output name 做 dict key；同名后值覆盖前值 | `runs.py:273-278`、`runs.py:290-296` |
| tests | 收集到的 test 名去重后字典序排序 | `runs.py:228-229`、`runs.py:288-289`、`runs.py:309-312` |
| 数值 | 全部保留字符串，不转 float | `runs.py:273-277`、`runs.py:290-295` |

返回结构原文（`runs.py:298-314`）：

```python
{
  "history": history,
  "tests": sorted(tests_seen),
  "points": [
    {"point": 1, "parameters": {"VDD": "0.9"},
     "outputs": {"Gain_dB": {"value": "21.63", "spec": "",
                             "weight": "", "pass_fail": ""}}},
  ],
  "outputs": [
    {"point": 1, "name": "Gain_dB", "value": "21.63", "spec_status": ""},
  ],
}
```

- 注意：docstring 声称 flat output 是 `(test,name,value,spec_status)`，但实现没有写入 `test`（`runs.py:71-72`、`runs.py:298-307`）。新实现若要保持兼容，保留这个缺口；若修正，必须标成破坏性变化。
- `overall_spec`/`overall_yield` 是下载并解析 CSV 后追加（`runs.py:178-180`）。

### 4.2 raw SKILL text / `state_from_skill.txt`

格式（`snapshot.py:83-95`）：

```text
[<SKILL probe label>] <raw output>

[<next probe label>] <raw output>
```

- 每个 section 是 `(label, raw_text)`，label 就是实际执行的 SKILL 文本（`bundle.py:105-112`、`snapshot.py:15`）。
- full snapshot 写为 `state_from_skill.txt`；brief 也复用同一 formatter（`snapshot.py:98-102`、`src_bak/virtuoso_bridge/cli.py:1516-1527`）。
- 该文件不是 JSON；CLI docstring 里写 `state_from_skill.json` 与实现不一致（`src_bak/virtuoso_bridge/cli.py:1443-1448`、`snapshot.py:98-102`）。

### 4.3 `maestro.sdb` XML

原始结构只需要理解两级（`filter.yaml:16-24`）：

```xml
<setupdb>
  <active>
    <currentmode>...</currentmode>
    <jobcontrolmode>...</jobcontrolmode>
    <corners>...</corners>
    <tests>...</tests>
    <vars>...</vars>
    <parameters>...</parameters>
    <specs>...</specs>
    <parametersets>...</parametersets>
    <overwritehistoryname>...</overwritehistoryname>
    <plottingoptions>...</plottingoptions>   <!-- GUI，默认丢 -->
    <runoptions>...</runoptions>             <!-- GUI，默认丢 -->
  </active>
  <history>...</history>                     <!-- 历史快照，默认全部丢 -->
</setupdb>
```

- 地址：`<lib_path>/<cell>/<view>/<view>.sdb`，下载到快照目录后改名 `maestro.sdb`（`snapshot.py:67-70`）。
- `filter_sdb_xml` 只保留 `<active>` 的直接子元素，元素 tag 精确匹配 YAML `maestro_sdb.active_keep`；输出新 `<setupdb>`（`_parse_sdb.py:68-106`）。
- 默认保留 `currentmode/jobcontrolmode/corners/tests/vars/parameters/specs/parametersets/overwritehistoryname`（`filter.yaml:26-37`、`_parse_sdb.py:55-58`）。
- 为什么：`<history>` 约占 90% 体积，GUI prefs 约 5%；真正 setup 只有约 5%（`_parse_sdb.py:73-83`）。

### 4.4 `active.state` XML

原始/过滤结构（`filter.yaml:53-82`）：

```xml
<statedb ...>
  <Test Name="TRAN">
    <component Name="adeInfo">...</component>
    <component Name="analyses">...</component>
    <component Name="variables">...</component>
    <component Name="rfstim">...</component>
    <component Name="turboOptions">...</component>
    <component Name="mdlOptions">...</component>
    <component Name="mtsSetup">...</component>
    <component Name="graphicalStimuli">...</component>
    <component Name="outputs">...</component>          <!-- 默认丢 -->
    <component Name="environmentOptions">...</component> <!-- 默认丢 -->
  </Test>
  <Test Name="REMOVED_TEST">...</Test>                  <!-- tombstone -->
</statedb>
```

- 地址：`<lib_path>/<cell>/<view>/active.state`（`snapshot.py:76-77`）。
- `filter_active_state_xml` 保留 root attrib；对每个 `<Test>` 复制 `Name` attrib；只复制 `component Name` 在 keep-list 内的 component（`_parse_sdb.py:164-174`）。
- keep-list：`adeInfo/analyses/variables/rfstim/turboOptions/mdlOptions/mtsSetup/graphicalStimuli`（`filter.yaml:64-82`、`_parse_sdb.py:59-65`）。
- `outputs/environmentOptions/modelSetup` 被有意去掉，因为 SKILL track 的 `maeGetTestOutputs`/`maeGetEnvOption` 已覆盖（`filter.yaml:84-91`）。
- `analyses` 对 pss/pnoise 比 `maeGetAnalysis` 更完整，`rfstim` 不在 SKILL track 中，所以必须保留（`filter.yaml:68-77`）。

### 4.5 `snapshot_filter.yaml` 过滤语义

真正的代码语义只有四类 include list：

| YAML key | 被谁读 | 语义 | 出处 |
|---|---|---|---|
| `maestro_sdb.active_keep` | `filter_sdb_xml` | `<active>` 直接子元素 tag 白名单 | `_parse_sdb.py:96-103` |
| `active_state.components_keep` | `filter_active_state_xml` | `<Test>` 下 `component Name` 白名单 | `_parse_sdb.py:161-171` |
| `per_point.netlist` | `_per_point_list("netlist", ...)` | remote `find -name` / local `fnmatch` 的 netlist basename 模式 | `snapshot.py:162-171`、`snapshot.py:217-223`、`snapshot.py:351-373` |
| `per_point.psf` | `_per_point_list("psf", ...)` | 同上，psf basename 模式 | `snapshot.py:162-171`、`snapshot.py:220-223`、`snapshot.py:352-373` |

- `active_drop`、`components_drop` 是**纯文档**；代码只读 `active_keep` 和 `components_keep`，不会根据 drop 列表主动删除（`_parse_sdb.py:96`、`_parse_sdb.py:161-171`、`filter.yaml:39-51`、`filter.yaml:84-108`）。
- YAML 读取用 `yaml.safe_load`，并以 `lru_cache(maxsize=4)` 缓存；文件/解析失败返回 `{}`（`_parse_sdb.py:26-39`）。
- keep list 缺失时使用硬编码 fallback（`_parse_sdb.py:42-65`）。
- per-point 列表为空或缺失时使用 hard-coded fallback（`snapshot.py:148-171`）。
- 不能通过 `_per_point_list` 注入自定义 YAML 路径；它总是读默认 filter path（`snapshot.py:162-170`、`_parse_sdb.py:21-23`）。
- `*.raw`、`wavedb/`、PDK info dumps 被有意排除，原因是 MB 级、二进制或可从其它文件推导（`filter.yaml:224-231`、`snapshot.py:128-138`）。

### 4.6 PSF ASCII

仓库里的 PSF parser 是离线纯 Python；它能解析快照里选中的 `.dc/.info/.tran/.ac` 等文本文件（`parsers.py:18-48`、`parsers.py:70-197`）。

最小 swept PSF 样例（`test_bak/test_spectre_parsers.py:37-55`）：

```text
HEADER
PROPERTIES
SWEEP
"time" 1
TRACE
"sig_a" "V"
"sig_b" "V"
VALUE
"time" 0.0
"sig_a" 1.0
"time" 1e-9
"sig_a" 1.5
"sig_b" 0.5
"time" 2e-9
"sig_a" 2.0
"sig_b" 0.7
END
```

格式规则：

- section marker 只有 `HEADER`、`TYPE`、`SWEEP`、`TRACE`、`VALUE`、`END`；没有 `VALUE` 则返回空（`parsers.py:300-316`）。
- `HEADER` 行是 `"key" "value"` 或 `"key" value`（`parsers.py:275-298`）。
- `SWEEP` 第一项给 sweep 变量名（`time`、`freq` 等）（`parsers.py:330-341`）。
- `TRACE` 同时支持 `" N" GROUP 1` → `"signal_name" "V"` 映射；VALUE 里按 N 引用时映射回信号名（`parsers.py:343-377`）。
- 标量值 `"name" 1.2`；AC 复数 phasor 写 `"name" (real imag)`；parser 生成 Python `complex`（`parsers.py:395-425`、`test_bak/test_spectre_parsers.py:93-117`）。
- PSF 是 delta-compressed：后续 step 只写变化信号；parser 用 step-interpolation 补齐，缺失初值用 `NaN`，不是 0（`parsers.py:318-328`、`parsers.py:427-456`）。
- 非 swept 文件（如 dcOpInfo）支持 `"M0" "mos" ( ... )` STRUCT，以及 `"M0:gm" "S" 1.906e-04 PROP(...)`（`parsers.py:473-543`、`parsers.py:546-583`）。
- 目录扫描优先 `tran.tran.tran`、`tran.tran`、`*.tran.tran`，DC 支持 `dc.dc/dcOp.dc/spectre.dc/*.dc`，AC 支持 `ac.ac/ac.ac.ac/*.ac.ac`，并递归所有 `*.info`（`parsers.py:79-197`）。
- sweep 子目录布局 `sw1.sweep1/<1-based point>/tran.tran.tran`；扁平 Spectre X/LX 文件 `sw1-000_tran.tran.tran` 会转换成 1-based point（`parsers.py:203-269`）。

### 4.7 OCEAN `ocnPrint` 文本

- `ocnPrint` 输出是 flat text；旧 example 的 parser 只接受每行至少两个 whitespace-separated token，并把前两个 token 转 float（`examples/01_virtuoso/maestro/06b_rc_simulate_and_read.py:28-37`）。
- 因此实际 reader 应容忍 header/非数值行并跳过，不能把首行当数据（同一实现 `try/except ValueError: continue`，`06b_rc_simulate_and_read.py:31-36`）。
- 默认格式是 `?numberNotation 'scientific`；precision/width 默认不写，保留 Cadence/用户设置（`runs.py:348-356`、`runs.py:379-383`、`test_bak/test_maestro_read_results.py:215-230`）。
- `numberNotation 'none` 跳过逐值格式化，是旧代码注明的大文件快速路径（`runs.py:353-356`）。

### 4.8 History 附属文件

| 文件 | 旧代码用途 | 是否解析 |
|---|---|---|
| `<history>.rdb` | history 权威锚；`natural_sort_histories` 只认它（以及裸 Interactive/MonteCarlo 目录） | 不解析，只存在性判断（`session.py:33-38`、`session.py:131-151`） |
| `<history>.log` | Maestro/OA history summary；snapshot 必抓 | 当作 opaque text（`snapshot.py:113`、`snapshot.py:225-245`） |
| `<history>.msg.db` | Maestro run message DB；snapshot 在 include_results 时抓 | opaque DB（`snapshot.py:125-126`、`snapshot.py:239-245`） |
| `<history>/.../netlist/*` | netlister inputs，主要是 symlink | 按 YAML basename 选择；不解析（`snapshot.py:107-110`、`snapshot.py:248-260`） |
| `<history>/.../psf/*` | PSF ASCII/log | 可用 `parsers.py` 解析；snapshot 默认只抓文本（`snapshot.py:111-138`） |

## 5. 文件系统约定

### 5.1 根路径

| 名称 | 公式 | 出处 |
|---|---|---|
| library read path | `ddGetObj(lib)~>readPath` | `bundle.py:114`、`runs.py:193` |
| 项目 results 根 | `<lib_path>/<cell>/<view>/results/maestro` | `bundle.py:138`、`snapshot.py:207` |
| 默认 view 等价式 | `<lib_path>/<cell>/maestro/results/maestro` | `runs.py:193-195`、`runs.py:386-388` |
| scratch results 根 | `<scratch_root>/<lib>/<cell>/<view>/results/maestro` | `snapshot.py:209-210`、`snapshot.py:234` |
| focus 不可用时 | `lib/cell/view` 来自标题；`view` 空则默认 `"maestro"` | `session.py:100-111`、`snapshot.py:459-463` |
| results dir | `asiGetResultsDir(asiGetCurrentSession())`，正则抓 `/maestro/results/maestro/<history>/` | `runs.py:390-399`、`writer.py:657-666` |

### 5.2 单点目录

YAML 注释给出的规范形状（`filter.yaml:110-125`）：

```text
<scratch>/<lib>/<cell>/<view>/results/maestro/<history>/<pt>/<tb>/
  netlist/
  psf/
```

- `<history>` 可以是 `Interactive.N`、`MonteCarlo.N`、`ExplorerRun.N`、用户自定义名；`.RO` 运行可能只在 scratch 根下（`session.py:33-38`、`bundle.py:220-227`）。
- 实际拉取不依赖 `<pt>/<tb>` 命名，只按路径含 `netlist`/`psf` 加 basename 白名单匹配（`snapshot.py:213-223`、`snapshot.py:358-375`）。
- Cadence per-point `netlist/` 大量是 symlink，指向 `psf/.../netlist/`；remote tar 用 `-h` 解引用，local 用 `copy2` 解引用（`snapshot.py:248-255`、`snapshot.py:326-342`）。

### 5.3 snapshot 输出布局

顶层目录：`<output_root>/<YYYYMMDD_HHMMSS>__<lib>__<cell>/`（`snapshot.py:405-411`）：

```text
<snap_dir>/
  maestro.sdb                    # 原始下载
  state_from_sdb.xml             # YAML-filtered
  active.state                   # 原始下载
  state_from_active_state.xml    # YAML-filtered
  state_from_skill.txt           # [label] raw
  <history>/
    <history>.log
    <history>.rdb                # include_results=True
    <history>.msg.db             # include_results=True
    <...>/netlist/<selected>
    <...>/psf/<selected>
```

- XML 通过 `download_file` 拉到 snap_dir 后，本地读取、过滤并写 `state_from_*`（`snapshot.py:36-80`）。
- raw XML 保留原名；filtered XML 单独写，绝不覆盖 raw（`snapshot.py:8-12`、`snapshot.py:67-80`）。
- `state_from_skill.txt` 只在非空时写（`snapshot.py:98-102`）。
- `_dump_run_artifacts` 要求 `history && lib_path && scratch_root` 三者都非空，否则直接跳过（`snapshot.py:194-196`）。

### 5.4 remote tar 与本地映射

remote 命令骨架（`snapshot.py:256-260`）：

```sh
find <hist_remote> \( -type f -o -type l \) <clauses> -print 2>/dev/null \
  | tar -chf <remote_tar> -P -T - --ignore-failed-read <extras> 2>/dev/null \
  && echo OK
```

- netlist clause：`\( -path '*/netlist/*' \( -name 'netlist' -o -name 'input.scs' ... \) \)`（`snapshot.py:217-219`）。
- psf clause：`\( -path '*/psf/*' \( -name 'spectre.out' ... -o -name '*.ac' ... \) \)`（`snapshot.py:220-223`）。
- extras：`<history>.log` 始终；`<history>.rdb/.msg.db` 在 include_results 时加入；project/scratch 两处都列，由 tar 的 ignore-failed-read 决定实际命中（`snapshot.py:225-246`）。
- 解包映射：history extras 平铺到 `<snap_dir>/<history>/`；per-point 文件保留 `/<history>/` 之后的相对路径（`snapshot.py:299-311`）。
- GNU tar 可能把重复 inode 写成 hard-link member；旧代码显式解析 `m.islnk()` 的 `linkname`，否则主 netlist 会被丢掉（`snapshot.py:273-298`）。

### 5.5 新旧 history 存储

- 本任务列出的旧 reader 代码**没有**读取 `<view>/history/*.zip` 或 `history.sdb`；它只识别 results 树中的 `.rdb/.log/.msg.db` 和裸目录（`session.py:115-128`、`snapshot.py:207-246`）。
- 因此 old reader 对 ICADVM20.1 separate history management 不是完整实现；照抄它会让新格式 history 对列表逻辑不可见。
- 仓库相邻调查 `doc/report/_explore/G_maestro_history_ops.md:120-132` 记录了另一种格式：老格式把 history setup 放在 `maestro.sdb`；新格式把每条 setup 放到 `<lib>/<cell>/<view>/history/<name>.zip`，并用 `history.sdb` 建索引。
- 迁移时若必须覆盖两代格式，应把“results 树枚举”与“history zip/sdb 枚举”做成两个 provider，不要假定 `.rdb` 一定存在或在 project 根下。

## 6. 纯 Python 与 SKILL 分工

### 6.1 可以完全离线单测的纯 Python

| 能力 | 旧函数 | 出处 |
|---|---|---|
| Detail CSV 解析 | `_parse_detail_csv` | `runs.py:224-314` |
| overall 原子去引号 | `_unquote_atom` | `runs.py:317-321` |
| XML sdb 过滤 | `filter_sdb_xml` | `_parse_sdb.py:68-106` |
| active.state 过滤/tombstone 去除 | `filter_active_state_xml` | `_parse_sdb.py:131-174` |
| 从 sdb 取 active tests | `_sdb_active_tests` | `_parse_sdb.py:109-128` |
| YAML keep-list 读取/fallback | `_load_filter_config`/`_keep_set` | `_parse_sdb.py:26-65` |
| history 文件名识别 | `_history_name_for_file` | `session.py:115-128` |
| history 自然排序 | `natural_sort_histories` | `session.py:131-151` |
| history mtime 聚合排序 | `sort_histories_by_mtime` | `session.py:154-175` |
| 标题解析 | `_parse_mae_title` | `session.py:25-62` |
| SKILL top-level tokenization | `tokenize_top_level` | `skill_output.py:22-56` |
| SKILL s-expression 解码 | `parse_sexpr`/`parse_skill_str_list` | `skill_output.py:69-95`、`skill_output.py:6-19` |
| PSF ASCII 解析 | `parse_spectre_psf_ascii` 等 | `parsers.py:18-583` |
| OCEAN flat text 解析 | example parser | `examples/01_virtuoso/maestro/06b_rc_simulate_and_read.py:28-37` |
| raw SKILL section 格式化 | `format_skill_sections` | `snapshot.py:83-95` |

### 6.2 必须经 SKILL 的动作

| 动作 | SKILL | 出处 |
|---|---|---|
| 取焦点窗口、davSession、窗口/session 列表 | `hiGetCurrentWindow`、`hiGetWindowName`、`hiGetWindowList`、`maeGetSessions` | `session.py:76-105` |
| 取 test/enabled analysis/analysis details | `maeGetSetup`、`maeGetEnabledAnalysis`、`maeGetAnalysis` | `bundle.py:73-97`、`bundle.py:166-185` |
| 取 env/sim option、outputs | `maeGetEnvOption`、`maeGetSimOption`、`maeGetTestOutputs` | `bundle.py:118-125` |
| 取 run mode/job mode/run plan/messages | `maeGetCurrentRunMode`、`maeGetJobControlMode`、`maeGetRunPlan`、`maeGetSimulationMessages` | `bundle.py:123-134` |
| 取当前 history | `axlGetCurrentHistory` | `bundle.py:126-131` |
| 取 run dir / results dir | `asiGetAnalogRunDir`、`asiGetResultsDir` | `bundle.py:139`、`runs.py:390-407` |
| 列 results 目录 | `getDirFiles` | `bundle.py:138`、`runs.py:191-196` |
| 打开/关闭 Maestro results | `maeOpenResults`、`maeGetResultOutputs`、`maeCloseResults` | `runs.py:200-205`、`runs.py:405-408` |
| 导出 Detail CSV/spec/yield | `maeExportOutputView`、`maeGetOverallSpecStatus`、`maeGetOverallYield` | `runs.py:137-147`、`runs.py:174-176` |
| OCEAN 读波形/导文本 | `openResults`、`selectResults`、`ocnPrint` | `runs.py:417-421` |
| AWV 开窗/画图/关窗 | `awvCreatePlotWindow`、`awvPlotWaveform`、`v`、`maeGetOutputValue`、`hiCloseWindow` | `waveform_viewer.py:89-142`、`waveform_viewer.py:161-180` |

### 6.3 必须经 command/file 接口的动作

- 用 `find -printf '%T@ %f\n'` 取 mtime：旧代码走 `client._tunnel._ssh_runner`，新实现应走 `middle.run_command`（`bundle.py:264-295`、`models.py:140-142`）。
- 用 `find | tar` 打包 per-point 文件、`rm -f` 清临时 tar：新实现走 `run_command`，或拆成显式 `download_file(recursive=True)`（`snapshot.py:256-323`、`models.py:144-150`）。
- 下载 CSV、OCEAN text、sdb、active.state、tar：旧 `client.download_file`，新 `middle.download_file`（`runs.py:152`、`runs.py:423`、`snapshot.py:41`、`models.py:148-150`）。
- 修改 active.state 后再写回：用 `middle.upload_file`；旧代码直接假定本地/远程同文件系统时才能直接 `cp/sed`（`models.py:144-146`、`skills/virtuoso/references/maestro-skill-api.md:478-486`）。

## 7. 迁移风险与五接口替换表

| 旧依赖/假设 | 旧证据 | 新实现应该换成什么 | 风险 |
|---|---|---|---|
| `client.execute_skill` | `runs.py:93-98`、`bundle.py:82` | `middle.execute_skill(skill, timeout, token=...)` | 返回值形状相同方向，但新 `VirtuosoResult` 增加 `status/log`；不要只看 output（`models.py:24-45`） |
| `client.download_file(remote, local)` | `runs.py:152`、`runs.py:423`、`snapshot.py:41` | `middle.download_file(remote, Path(local), timeout, token=..., recursive=False)` | 先检查 `CommandResult.kind=="command"` 和 rc；目录/符号链接语义不同（`models.py:53-64`、`models.py:148-150`） |
| `client.ssh_runner` | `snapshot.py:196` | `middle.run_command(cmd, timeout, token=...)` | `ssh_runner is None` 的本地分支没有替代品；不要在上层判断 local/remote（`middle.py:666-712`） |
| `client._tunnel._ssh_runner` | `bundle.py:270-275` | `middle.run_command(..., token=...)`；路径用 `middle.query(token=...).roles[...]` | `_tunnel` 是旧拓扑内部结构，新上层禁止依赖（`models.py:67-88`、`models.py:160-163`） |
| 直接用本地 `Path` 读远程目录 | `bundle.py:271-280` | 统一 `download_file`；若要枚举远端，用 `run_command` + 解析 stdout | 本机 CWD 不等于 Virtuoso 角色根（`doc/接口调用指南.md:30-59`） |
| 硬编码 `/tmp/vb_*` | `runs.py:137`、`_skill.py:22`、`snapshot.py:211` | 用 token/业务工作目录或角色 root；先 `query` 取 root | Skill/command/file role 可能不同，`/tmp` 不一定跨 role 可见 |
| `find -printf` / GNU tar / `--ignore-failed-read` / `-h` | `bundle.py:284-295`、`snapshot.py:256-260` | 用 `run_command` 明确 shell；必要时改显式文件清单 + `download_file(recursive=True)` | 不是跨平台/跨 shell 保证；hard-link 处理也依赖 GNU tar（`snapshot.py:273-298`） |
| symlink 目录树 | `snapshot.py:248-255` | 新文件接口会跟随 symlink；必须验证目标布局 | recursive download 不保证保留链接层级（`doc/report/_explore/C_maestro_spectre.md:708-716`） |
| Maestro results 全局上下文 | `runs.py:200-205`、`runs.py:405-421` | 串行化同一 token 的结果操作；不可并发 open/close | `maeOpenResults`/OCEAN `openResults` 会互相污染 |
| 聚焦窗口才可 snapshot | `session.py:76-83` | 显式传 `lib/cell/view/session`；如必须聚焦用 `run_gui_command` | GUI command 是一次性，不能保留焦点状态（`models.py:152-154`） |
| `maeExportOutputView` 返回值作成功判定 | `runs.py:132-147` | 以文件接口下载成功/文件大小/非空作为 materialization 证据 | Cadence 版本可能返回 `t/nil/文件名`（`runs.py:133-136`） |
| 只解析 `.rdb` 锚点 | `session.py:131-151` | 增加 `history/*.zip + history.sdb` provider（若目标环境默认新格式） | 新格式下磁盘枚举可能看不到所有 history（`G_maestro_history_ops.md:120-132`） |
| `read_results` 硬编码 `<cell>/maestro/results/maestro` | `runs.py:193-195` | 统一用 `<lib_path>/<cell>/<view>/results/maestro`，view 显式传入 | 自定义 view 会被漏掉（`bundle.py:138`） |
| SKILL 字符串直接 f-string | `runs.py:138-145`、`runs.py:201-203`、`bundle.py:73-80` | 全部经 `escape_skill_string` 或参数化 builder | history/test/session 含双引号或反斜杠会破坏 SKILL（`waveform_viewer.py:65-79` 是旧代码中较好的做法） |
| 无限等待/单次长 timeout | `runs.py:417-421`、`writer.py:372-417` | 每步使用剩余 deadline；结果 unknown 不自动重放 | 新五接口把 timeout/transport 分成 `kind`（`models.py:53-64`） |
| 本地上层解析 CSV/XML | `runs.py:149-153`、`snapshot.py:47-57` | 保留为纯 Python；只把“取字节”交给 file interface | 本地临时路径是上层资源，不是 Virtuoso 路径 |
| `client.dismiss_dialog()` | `writer.py:483-487` | `middle.run_gui_command(..., token=...)`，或把 dialog 处理拆成独立 one-shot | GUI 接口无持久 session，不能复用旧 X11 线程/焦点假设（`models.py:152-154`） |
| Spectre 子进程直跑 | `parsers.py` 外的旧 runner | `middle.run_spectre_command(..., token=...)` | reader 本身不跑 Spectre，只读产物；不要把 `openResults/ocnPrint` 误投给 Spectre role |
| 旧客户端本地/远程分支 | `snapshot.py:196-206`、`bundle.py:270-280` | 不在上层判断 local/remote；只按 role/API 调用 | 旧 `None` runner 分支会静默改变语义 |

## 8. 直接实现时的检查清单

1. 先取 session/window：`hiGetCurrentWindow` → `davSession` → `maeGetSessions`；没有 session 就返回明确错误，不假定焦点（`session.py:76-112`）。
2. 取 test：`maeGetSetup(session)` 第一个字符串；空则停止，提示先 `maeSetupTest`（`_skill.py:37-44`、`runs.py:108-116`）。
3. 取 lib/cell：参数优先；缺失时 `maeGetEnvOption(test ?option "lib"/"cell" ?session ...)`（`runs.py:88-99`）。
4. 取 lib read path 和 scratch run dir：`ddGetObj(lib)~>readPath`、`asiGetAnalogRunDir(asiGetSession(sess))`（`bundle.py:114`、`bundle.py:139`）。
5. 列 history：`getDirFiles(<view results>/maestro)`；同时保存文件名和 mtime（`bundle.py:138`、`bundle.py:228-240`）。
6. 选 history：显式 history > mtime desc > `axlGetCurrentHistory` > natural sort last（`snapshot.py:486-508`）。
7. 读 setup：至少执行 `maeGetSetup/maeGetEnabledAnalysis/maeGetAnalysis/maeGetEnvOption/maeGetSimOption/maeGetTestOutputs`（`bundle.py:113-125`）。
8. 做 CSV：`maeExportOutputView(... ?view "Detail" ?fileName <tmp>)`，下载后解析；不要信 return（`runs.py:132-183`）。
9. 做 spec/yield：`maeGetOverallSpecStatus()` + `maeGetOverallYield(history)`；两者都可为 `None`（`runs.py:174-180`）。
10. 做单波形：`maeOpenResults` → 取 results dir → `maeCloseResults` → `openResults` → `selectResults` → `ocnPrint` → download → delete temp（`runs.py:403-425`）。
11. 做快照 XML：下载 `<view>.sdb` 和 `active.state`；sdb 过滤仅保留 active keep-list；active.state 用同一 sdb 的 test 集去 tombstone（`snapshot.py:60-80`、`_parse_sdb.py:109-174`）。
12. 做快照产物：按 YAML netlist/psf 白名单拉 per-point 文件；保留 `<history>` 后相对路径；history `.log/.rdb/.msg.db` 平铺（`snapshot.py:174-323`）。
13. 做 AWV：用 `awv*` 生成完整 SKILL，保留返回的 session/window；关闭时 `hiCloseWindow` + `maeCloseSession(?forceClose t)` 并复读验证（`waveform_viewer.py:35-181`）。
14. 新代码只依赖五接口 + `query`；不要 import `ssh_runner`、`_tunnel`、旧 `VirtuosoClient` 或自行解析 `.env`（`models.py:122-163`）。

## 9. 一句话边界

**必须过 SKILL 的是“问 Virtuoso 当前状态/让它导出文件/开 GUI 窗口”；纯 Python 只负责“解析已下载的文本、排序、过滤、路径映射”。**旧 reader 的所有正确性都建立在“SKILL 生成 artifact，随后 file/command 接口取回”这一模式上，而不是让 Python 直接猜内存状态。
