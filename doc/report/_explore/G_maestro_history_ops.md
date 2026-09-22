# G_maestro_history_ops — Maestro history（历史）管理能力调查报告

> 调查日期：2026-09-20（Asia/Shanghai）
> 仓库：`C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS`
> 只读约束：本次调查未修改任何仓库文件；本报告是唯一写入的文件。
> 调查来源：
> 1. 旧代码 `src_bak/virtuoso_bridge/virtuoso/maestro/**`、`examples/01_virtuoso/maestro/**`、`test_bak/test_maestro_*.py`
> 2. 本地 SKILL 文档服务（`http://127.0.0.1:8123/api/find`、`/api/info`），底层文档 `maeSKILLref.fnd` / `maeSKILLref/maestroSKILL.html` / `historyRelated.html` / `setupDB.html` / `ocnxl.fnd`
> 3. 桌面 Cadence 文档 `C:\Users\user\Desktop\doc`（`assembler/asmCheckpoints.html`、`adexl/adexlCheckpoints.html`、`asmWorkingSetup.html`、`appEnvVars.html`、`asmRunPlan.html`、`maeSKILLref/*`）
>
> 注：subagent 工具在本会话中不可用（多次检索均返回空），本报告由主 agent 直接完成调查。

---

## 0. 结论速览

用户提出的 8 项 history 操作，**全部有 SKILL 层面的实现路径**，没有一项需要 GUI 自动化或文件系统硬删：

| # | 能力 | 结论 | 核心机制 |
|---|---|---|---|
| 1 | 列出 history | ✅ SKILL 直接支持 | `axlGetHistory`（SDB 权威）+ 磁盘枚举（旧代码补充） |
| 2 | 当前 history | ✅ SKILL 直接支持 | `axlGetCurrentHistory(session)`（旧代码已用） |
| 3 | 删除整个 history | ✅ SKILL 直接支持 | `axlRemoveElement(axlGetHistoryEntry(...))`；Explorer 另有 `maeDeleteExplorerHistory` |
| 4 | 删除部分数据（结果） | ✅ SKILL 直接支持 | `maeDeleteSimulationData`（含保留 netlist / quickplot 选项）；`axlRemoveSimulationResults` |
| 5 | 重命名 | ✅ SKILL 直接支持 | `axlSetHistoryName`（官方示例）；OCEAN XL 用 `ocnxlRenameCurrentHistory` |
| 6 | 复制 | ⚠️ 部分支持 | `axlLoadHistory`（复制 setup 分支）/ `axlCommitSetupDBAndHistoryAs`（整体另存）/ `maeImportHistory`（跨 cellview 导入 zip）；**没有"原地复制单条 history"的直接 API** |
| 7 | 锁定 / 解锁 | ✅ SKILL 直接支持 | `maeSetHistoryLock` / `axlSetHistoryLock`；读取用 `maeGetHistoryLockFlag`（5 种状态） |
| 8 | 覆盖式运行 | ✅ SKILL 直接支持 | `axlSetOverwriteHistory` + `axlSetOverwriteHistoryName`（OCEAN 侧 `ocnxl*` 等价） |

三个关键事实：

1. **"删除整个 history"没有以 delete 命名的 API**，官方做法是用通用的 `axlRemoveElement` 删 history 元素句柄。`axlRemoveSimulationResults` 文档明确写了：*"If you need to remove the entire history, use axlRemoveElement for the history element."* 并且给了 `axlRemoveElement(axlGetHistoryEntry(data_sdb, "data_design_verification"))` 的官方示例。
2. **锁定状态有 5 种**（用户锁、被引用锁、Monte Carlo reuse 锁及其组合），删除/改名前必须逐一识别，不能只看"锁没锁"。
3. **存储有两代模型**：老模型（history 在 `maestro.sdb` 内）与新模型（ICADVM20.1 默认的 separate history management：`history/<name>.zip` + `history.sdb`）。SKILL 删除/重命名对两种模型的一致性表现需要真机验证，见 §7。

---

## 1. SKILL API 清单

以下函数均来自 8123 文档服务与桌面 `maeSKILLref`，按"读 / 写 / 明确不存在"分类。签名保留官方原文。

### 1.1 读（list / current / status / lock / results dir）

| 函数 | 签名 | 说明 | 来源 |
|---|---|---|---|
| `axlGetHistory` | `axlGetHistory(x_hsdb) => l_history / nil` | 返回 setup 数据库中**全部 history 条目**的句柄列表与名字列表 | `maeSKILLref.fnd`；`historyRelated.html` |
| `axlGetHistoryEntry` | `axlGetHistoryEntry(x_hsdb, t_historyName) => x_history / nil` | 按名字查找 history 条目并返回句柄 | `maeSKILLref.fnd` |
| `axlGetCurrentHistory` | `axlGetCurrentHistory(t_sessionName) => x_historyHandle / nil` | 当前会话正在使用的 history 条目 | `maeSKILLref.fnd` |
| `axlGetHistoryName` | `axlGetHistoryName(x_historyEntry) => t_historyName / nil` | 取 history 条目名字 | `maeSKILLref.fnd` |
| `axlGetHistoryCheckpoint` | `axlGetHistoryCheckpoint(x_history) => x_checkpoint / nil` | 取 history 条目的 checkpoint 句柄 | `maeSKILLref.fnd` |
| `axlGetHistoryLock` | `axlGetHistoryLock(x_historyHandle) => t / nil` | 布尔锁状态；文档注明锁后 **setup 细节与结果都不能删除** | `maeSKILLref.fnd` |
| `maeGetHistoryLockFlag` | `maeGetHistoryLockFlag([?session s][?historyName h]) => n_flag / nil` | 数字锁状态：`0` 未锁；`1` 用户锁；`2` 被其他 history 引用锁；`3` 两者；`4` Monte Carlo reuse variation 锁 | `maestroSKILL.html` |
| `axlGetHistoryGroup` | `axlGetHistoryGroup(x_hsdb, t_histgrpName) => x_history / nil` | 取命名 history group 句柄 | `maeSKILLref.fnd` |
| `axlGetHistoryGroupChildren` | `axlGetHistoryGroupChildren(x_element) => l_children` | group 内子条目句柄 + 名字 | `maeSKILLref.fnd` |
| `axlGetHistoryGroupChildrenEntry` | `axlGetHistoryGroupChildrenEntry(x_childrenHandle, t_name) => x_history / 0` | 按名字取 group 内子条目 | `maeSKILLref.fnd` |
| `axlGetRunData` | `axlGetRunData(t_sessionName, x_runID) => x_historyHandle / nil` | 由运行 ID 取 history 句柄 | `maeSKILLref.fnd` |
| `axlGetRunStatus` | `axlGetRunStatus(t_sessionName [?optionName][?historyName]) => l_statusValues` | 指定 history 的完成度状态 | `maeSKILLref.fnd` |
| `axlGetHistoryResults` | `axlGetHistoryResults(x_history) => t_results / nil` | 取 history 的结果数据库位置（内部调 `axlGetResultsLocation`） | `maeSKILLref.fnd` |
| `axlReadHistoryResDB` | `axlReadHistoryResDB(t_historyName [?session s]) => h_ResultsDBObj / nil` | 读取该 history 保存的结果数据库句柄 | `maeSKILLref.fnd` |
| `axlGetHistoryPrefix` | `axlGetHistoryPrefix(x_sessionName) => t_historyPrefix / nil` | 当前会话的 history 前缀（决定新 run 命名） | `maeSKILLref.fnd` |
| `axlGetWCCHistory` | `axlGetWCCHistory(x_specHandle) => t_historyName / nil` | worst-case corner spec 对应的 history 名 | `maeSKILLref.fnd` |
| `axlIsLocalResultsDir` | `axlIsLocalResultsDir(x_historyHandle) => t / nil` | 该 history 是否使用本地结果目录 | `maeSKILLref.fnd` |
| `maeGetReferenceHistories` | `maeGetReferenceHistories(x_hsdb) => l_referenceHistoryNames` | 当前 setup/history 引用的 reference history 列表 | `maeSKILLref.fnd` |
| `maeGetCurrentRunPlanName` | `maeGetCurrentRunPlanName() => t_runPlanName` | 当前 run plan 的 history 名 | `maeSKILLref.fnd` |
| `maeGetHistoryCloudUUID` | `maeGetHistoryCloudUUID(session, history) => t_UUID / nil` | 云端运行 history 的 UUID（ICADVM20.1） | `maeSKILLref.fnd` |
| `maeOpenResults` | `maeOpenResults([?session][?history][?run]) => t / nil` | 打开指定 history 的结果指针（旧代码大量使用） | `maeSKILLref.fnd` |
| `maeCloseResults` | `maeCloseResults() => t / nil` | 关闭 `maeOpenResults` 打开的结果 | `maeSKILLref.fnd` |
| `ocnxlGetCurrentHistory` | `ocnxlGetCurrentHistory() => historyName / nil` | OCEAN XL 当前 history 名 | `ocnxl.fnd` |
| `ocnxlGetCurrentHistoryId` | `ocnxlGetCurrentHistoryId([?returnSingleEntryIfGroupRun]) => historyID / nil` | OCEAN XL 当前 history ID | `ocnxl.fnd` |

补充说明：

- **锁状态的两个 API 语义不同**：`axlGetHistoryLock` 只有 t/nil；`maeGetHistoryLockFlag` 才区分"用户锁 / 被引用锁 / reuse 锁"。删除前的安全检查应该用后者（或两者结合）。
- **列出 history 有 SDB 与磁盘两个数据源**：
  - SDB 源：`axlGetHistory` / `axlGetHistoryGroupChildren`（权威、含 group）；
  - 磁盘源：`getDirFiles(strcat(ddGetObj(lib)~>readPath "/<cell>/<view>/results/maestro"))`（旧代码使用的枚举方式，见 §4）。
  两者可能不一致（例如 scratch 目录里的 `.RO` history，见旧代码 `bundle.py` 注释）。

### 1.2 写（delete / rename / copy / lock / commit-as / overwrite / put）

| 函数 | 签名 | 说明 | 来源 |
|---|---|---|---|
| `axlRemoveElement` | `axlRemoveElement(x_element) => t / nil` | **通用元素删除**。"Removes an element and all its children from the setup database." 官方示例即删除 history 条目：`axlRemoveElement(axlGetHistoryEntry(data_sdb, "data_design_verification"))` | `setupDB.html`；`axlRemoveSimulationResults` 文档交叉引用 |
| `maeDeleteExplorerHistory` | `maeDeleteExplorerHistory(t_sessionName, t_historyName) => t / nil` | **ADE Explorer 专用**删除：从给定会话删除一条 history，"一次只能删一条"；名字/会话非法返回 nil | `maestroSKILL.html` |
| `axlRemoveSimulationResults` | `axlRemoveSimulationResults(x_historySDB) => t / nil` | 只删除模拟器保存的结果数据；**结果数据库和 history 条目保留**；参数不能是 checkpoint 句柄 | `historyRelated.html` |
| `maeDeleteSimulationData` | `maeDeleteSimulationData(t_historyName ?session s ?keepNetlist g ?keepQuickPlot g) => t / nil` | 删除指定 history 的仿真数据；可选保留 netlist 目录与 quick plot | `maestroSKILL.html` |
| `axlSetHistoryName` | `axlSetHistoryName(x_historyHandle, t_newHistoryName) => t / nil` | 给指定 history **改名**；官方示例 `axlSetHistoryName(axlGetHistoryEntry(sdb,"SingleRun.1"), "newHistoryName")` | `historyRelated.html` |
| `ocnxlRenameCurrentHistory` | `ocnxlRenameCurrentHistory(t_newNameForHistory) => t / nil` | OCEAN XL 重命名当前 history | `ocnxl.fnd` |
| `axlLoadHistory` | `axlLoadHistory(x_to, x_from) => x_hsdb / nil` | **复制 setup 数据库分支**并返回副本句柄（源是 history checkpoint） | `historyRelated.html` |
| `axlCommitSetupDBAndHistoryAs` | `axlCommitSetupDBAndHistoryAs(x_hsdb, t_setupdbName) => x_hsdb` | 把 setup 数据库连同 history 条目**另存为新名字**（整体另存，不是单条 history） | `setupDB.html` |
| `axlPutHistoryEntry` | `axlPutHistoryEntry(x_hsdb, t_historyName) => x_history / nil` | 插入或查找 history 条目 | `maeSKILLref.fnd` |
| `maeImportHistory` | `maeImportHistory(t_lib, t_cell, t_view [?session][?history][?copyPSF][?overwrite]) => t / nil` | 从其它 cellview **导入 history zip**；前提是启用 separate history management | `maestroSKILL.html` |
| `axlSetHistoryLock` | `axlSetHistoryLock(x_handleHistory, g_enable) => t / nil` | 锁定/解锁指定历史的 checkpoint；锁后不能删除 history 或仿真数据 | `maeSKILLref.fnd` |
| `maeSetHistoryLock` | `maeSetHistoryLock(t_historyName, g_lock [?session s]) => t / nil` | ADE Assembler 中按名字锁/解锁 | `maestroSKILL.html` |
| `axlSetOverwriteHistory` | `axlSetOverwriteHistory(x_setup, g_overwriteStatus) => t / nil` | 打开/关闭 "Overwrite History" 选项 | `maeSKILLref.fnd` |
| `axlSetOverwriteHistoryName` | `axlSetOverwriteHistoryName(x_setup, t_overwriteHistoryName) => t / nil` | 设置被覆盖的 history 名 | `maeSKILLref.fnd` |
| `axlGetOverwriteHistory` / `axlGetOverwriteHistoryName` | `... => t / nil` | 读取覆盖开关与目标名 | `maeSKILLref.fnd` |
| `ocnxlSetOverwriteHistory` / `ocnxlSetOverwriteHistoryName` | `... => t / nil` | OCEAN XL 等价覆盖设置 | `ocnxl.fnd` |
| `axlSetReferenceHistoryItemName` | `axlSetReferenceHistoryItemName(x_hsdb, t_referenceHistoryName) => x_hsdb / 0` | 设置 reference history（增量运行复用结果/netlist 的来源） | `maeSKILLref.fnd` |
| `axlSetUseIncremental` | `axlSetUseIncremental(x_hsdb, g_value) => x_hsdb / 0` | 开关"使用 reference 结果作为缓存" | `maeSKILLref.fnd` |
| `axlSetCopyRefResultsOption` | `axlSetCopyRefResultsOption(x_hsdb, g_value) => x_hsdb / 0` | 设置 reference history 结果是复制还是移动 | `maeSKILLref.fnd` |
| `maeDeleteRun` | `maeDeleteRun([?run l_run] \| [?all t] [?session s]) => t / nil` | **run plan 里的 run** 删除（不是 history 条目，注意区分） | `maestroSKILL.html` |

### 1.3 明确不存在的函数（检索关键词：DeleteHist / RenameHistory / CopyHistory / ExportHistory / ZipHistory / HistoryDelete）

| 猜测的函数名 | 检索结果 | 替代 |
|---|---|---|
| `maeDeleteHistory` | ❌ 不存在 | Assembler 用 `axlRemoveElement`；Explorer 用 `maeDeleteExplorerHistory` |
| `axlDeleteHistory` | ❌ 不存在 | 同上 |
| `maeRenameHistory` / `axlRenameHistory` | ❌ 不存在 | `axlSetHistoryName`；OCEAN XL `ocnxlRenameCurrentHistory` |
| `maeCopyHistory` / `axlCopyHistory` | ❌ 不存在 | `axlLoadHistory` / `maeImportHistory` / 运行方式复现 |
| `maeExportHistory`（zip 导出） | ❌ 未找到 | 桌面文档中导入功能存在（`maeImportHistory`），导出侧只在 GUI `File – Import History` 流程中描述；无公开导出函数 |

---

## 2. 存储模型（理解删除/改名行为的前提）

### 2.1 两代存储格式

**老格式（integrated，所有历史在 sdb 内）**

- history setup 与主 setup 一起保存在 `maestro.sdb`；
- `history/`、`history.sdb` 目录不可见（桌面文档 `asmWorkingSetup.html:211` 附近描述）。

**新格式（separate history management，ICADVM20.1 默认开启）**

- 每条 history 的 setup 信息存为 `history/<name>.zip`；
- history 数据库为 `history.sdb`，位置在 `<lib>/<cell>/<view>/history/`；
- 可通过环境变量在 IC6.1.8 打开：`maestro.setupdb useSeparateHistoryFileManagement`（`appEnvVars.html:3249-3286`）；
- 导入 history 时："zip files ... copied from the source cellview to the `history` directory ... new entries are added to the history database saved in the `history.sdb` file"（`asmCheckpoints.html:525`）。

**由此产生的直接后果**：SKILL 的删除/改名是否同步维护 zip 文件与 `history.sdb`，两种格式下的表现可能不同——这决定了我们要不要把"应用层文件清理"作为兜底（见 §7 待验证清单）。

### 2.2 磁盘上的结果布局（来自旧代码）

旧代码对 `results/maestro/` 目录的识别规则（`src_bak/virtuoso_bridge/virtuoso/maestro/reader/session.py:33-38`）：

```
<name>.rdb        # 结果数据库锚点文件（history 的权威锚）
<name>.log        # 运行日志
<name>.msg.db     # 消息数据库
Interactive.N     # 无 .rdb 时的裸目录（老式）
MonteCarlo.N      # 同上
```

history 名允许用户自定义（例如 `closeloop_PVT_postsim`、`sweep_set.3`、`calibre_rcc_norc_sch`），所以**任何"按名字前缀猜 history"的逻辑都不可靠**（`session.py:157-176` 的注释明确说明了这一点）。

### 2.3 锁语义（来自桌面文档与 SKILL 文档）

- GUI：右键 history → Lock；锁后 Delete 菜单项不可用；子条目（historychildren）随父级一起锁（`asmCheckpoints.html:474-498`）。
- 特殊例外：**`ExplorerRun.0` 不能锁**——ADE Explorer 只有一条 history，每次运行都会被覆盖（`asmCheckpoints.html:482`）。
- 数字锁状态（`maeGetHistoryLockFlag`）：`2/3` 表示被其它 history 引用而锁、`4` 表示 Monte Carlo reuse variation 锁——这些**不是用户能随便解锁的状态**，删除前必须能识别。

---

## 3. 旧代码实现清单

### 3.1 旧代码做过的 history 相关操作

| 能力 | 旧实现 | 引用 |
|---|---|---|
| 枚举 history 文件 | `getDirFiles(<libPath>/<cell>/<view>/results/maestro)` 一次 SKILL 拿文件名列表 | `src_bak/virtuoso_bridge/virtuoso/maestro/reader/bundle.py:138` |
| 枚举 + 排序 | `natural_sort_histories`（自然序）与 `sort_histories_by_mtime`（按最新 mtime 排，优先使用） | `reader/session.py:132-150`、`157-176` |
| 当前 history | `errset(let((h) h=axlGetCurrentHistory(sess) when(h list(h~>name h~>historyName h~>run h~>runName))))`，取第一个非 nil 字符串 | `reader/bundle.py:126-131`、`bundle.py:200-203` |
| 最新有结果的 history | 从磁盘列表倒序扫描，逐个 `maeOpenResults(?history h)` → `maeGetResultOutputs` → `maeCloseResults()`，返回第一条有结果的 | `reader/runs.py:186-215` |
| 打开结果 / 关闭结果 | `maeOpenResults` / `maeCloseResults` | `reader/runs.py:201-204`、`408-410` |
| 导出结果 CSV 的临时文件清理 | 本地 `unlink()` + 远端 `deleteFile(tmp)`（**只清临时文件，不动 history**） | `reader/runs.py:165-172`、`424` |
| 读取聚焦窗口的 maestro 状态 | 解析标题 `ADE Assembler/Explorer Editing/Reading: LIB CELL VIEW*` | `reader/session.py:20-31`、`_fetch_window_state` |
| 全量快照（含指定 history） | 指定或自动挑选 history，抓 `<history>.log/.rdb/.msg.db` 与 per-point netlist/PSF，打包 tar 下载；仅删除临时 tar | `reader/snapshot.py:175-244`、`320-323`、`431-515` |
| 启动仿真 | `maeRunSimulation(?session ?callback)` 返回 history 名；回调写 marker 文件，Python 轮询问结果 | `writer.py:339-355`、`495-575` |
| 启动并等待（含对话框恢复） | 同上 + 共享超时预算 + 失败时诊断输出 | `writer.py:495-575` |
| GUI 打开历史 | `asiGetResultsDir` 解析 history 名 → `maeOpenSetup`? + GUI 打开 + `maeRestoreHistory(history)` | `writer.py:642-673` |
| 波形查看器 | `maeOpenResults(?session ?history)` + AWV 建窗/画图/关窗 | `waveform_viewer.py:113-141`、`151-180` |
| 内存级 purge（不是删除） | `dbPurge(cv)` 把 maestro cellview 逐出虚拟内存，释放编辑锁 | `lifecycle.py:126-136` |
| 删除变量（`axlRemoveElement` 的先例用法） | `axlRemoveElement(axlGetVar(...))` 删除设计变量 | `writer.py:139-155`；`examples/01_virtuoso/maestro/05_gui_session_lifecycle.py:172,230` |

### 3.2 旧代码**没有**实现的操作

全仓库（`src_bak`、`examples`、`test_bak`）检索以下符号均无命中，除 `axlRemoveElement` 被用于删除变量外，没有任何 history 变更操作：

```
axlRemoveElement(history)   → 无
maeDeleteExplorerHistory    → 无
maeDeleteSimulationData     → 无
axlRemoveSimulationResults  → 无
axlSetHistoryName           → 无
maeSetHistoryLock / axlSetHistoryLock → 无
axlRemoveSimulationResults  → 无
axlLoadHistory / axlCommitSetupDBAndHistoryAs → 无
maeImportHistory            → 无
maeDeleteRun                → 无
```

测试侧同样：`test_bak/test_maestro_ops.py:17-21` 导出的旧 API 清单（open/close GUI session、purge、set/get/delete var、get/set parameter 等）不含任何 history 删除/改名；`test_bak/test_maestro_read_results.py:141-148` 只断言临时 CSV 的 `deleteFile` 清理。

**结论：旧包对 history 是"只读 + 运行产出"，删除/改名/锁定/复制/部分删除数据、覆盖式运行配置，全部是本次新增能力，没有旧实现可移植，需要新写 SKILL 序列并真机验证。**

---

## 4. 差距分析（逐项）

### 4.1 列出 history

**支持等级：SKILL 直接支持（首选）+ 文件系统（补充）**

- 首选：`axlGetHistory(x_hsdb)` 取 SDB 内全部 history；group 用 `axlGetHistoryGroup*` 展开。
- 补充：磁盘枚举 `getDirFiles(results/maestro)` + mtime 排序（旧代码方式），用于发现 `.RO`/scratch-only 的漏网 history（`bundle.py:221-245` 注释明确说明"不扫 scratch 会看不见 `.RO` histories"）。
- 风险：SDB 枚举与磁盘枚举可能不一致；对自定义命名 history，磁盘端不能靠命名规则过滤，必须按 `.rdb` 锚点（`session.py:33-37`）。
- 建议：业务操作返回 `{name, lock_flag, has_results, mtime, group}` 的合并视图；名称一律以 SDB 返回为准。

### 4.2 当前 history

**支持等级：SKILL 直接支持**

- `axlGetCurrentHistory(session)` 返回句柄；名字取 `~>name` / `~>historyName` / `~>run` / `~>runName` 的第一个非 nil（旧代码 `bundle.py:126-131` 注释：IC6.1.8 返回的 runHistory 对象 `~>name` 经常是 nil）。
- OCEAN XL 侧 `ocnxlGetCurrentHistory()` / `ocnxlGetCurrentHistoryId()`。
- 风险：需要会话（session）上下文；无 GUI 会话时"当前 history"可能无意义，应返回空而不是报错。

### 4.3 删除整个 history

**支持等级：SKILL 直接支持**

- Assembler：`axlRemoveElement(axlGetHistoryEntry(sdb, name))`。官方交叉引用原文：*"If you need to remove the entire history, use axlRemoveElement for the history element."*（`historyRelated.html` 的 `axlRemoveSimulationResults` 条目）。
- Explorer：`maeDeleteExplorerHistory(session, name)`；文档明确"一次只能删一条"，非法 name/session 返回 nil。
- GUI 行为参照（说明语义边界）：Delete 会"removes the history item and its checkpoint from the History tree **and the raw simulation results from the results directory**"（`asmCheckpoints.html:467`）。SKILL 层是否同样自动清理磁盘（含 zip）待验证（§7）。
- 保护规则：被锁（`maeGetHistoryLockFlag` ≠ 0）时删除应被拒绝；`ExplorerRun.0` 特殊（不可锁，会被下次运行覆盖，不建议提供删除）。
- 风险与安全建议：
  1. 删除前必须读锁状态并检查 reference（`maeGetReferenceHistories`）；
  2. 删除后要"读回验证"（`axlGetHistory` 再取一次，确认条目消失）；
  3. **禁止用 `rm -rf` 代替 API**；若验证发现磁盘残留，只允许对已确认 history 名的具体路径清理，且必须做路径校验（禁止把 `name` 直接拼进 shell；名中带 `..`、`/` 一律拒绝）；
  4. 一次删除一条，不做批量隐式删除（与 `maeDeleteExplorerHistory` 的官方限制对齐）。

### 4.4 删除部分数据（仿真结果）

**支持等级：SKILL 直接支持**

- `maeDeleteSimulationData(history, ?session, ?keepNetlist, ?keepQuickPlot)`：与 GUI "Delete Simulation Data" 的子菜单一一对应（`asmCheckpoints.html:445-457`）：

| GUI 选项 | SKILL 调用 |
|---|---|
| All（删除数据与 netlist） | `maeDeleteSimulationData(hist)` |
| All except Netlists | `maeDeleteSimulationData(hist ?keepNetlist t)` |
| All except Netlists and Quick Plot Data | `maeDeleteSimulationData(hist ?keepNetlist t ?keepQuickPlot t)` |

- 备选：`axlRemoveSimulationResults(historyHandle)`——更老的 API，只删模拟器结果，"结果数据库和 history 条目保留"，不能传 checkpoint 句柄。
- 风险：
  - 锁定的 history 不允许删除数据（`axlSetHistoryLock` 文档原文："After it is locked, you cannot delete the history or the simulation data saved for it."）；
  - 删除的是"模拟器数据"，`maeGetOverallYield` / spec 状态等基于结果数据库导出的内容是否会同步失效，需要真机验证；
  - **不做**文件系统直删（这是最容易把 SDB 与磁盘搞不一致的操作）。

### 4.5 重命名

**支持等级：SKILL 直接支持**

- `axlSetHistoryName(handle, newName)`，官方示例完整：`axlGetHistoryEntry(sdb, "SingleRun.1")` → `axlSetHistoryName(handle, "newHistoryName") => t`。
- OCEAN XL：`ocnxlRenameCurrentHistory(newName)`。
- 桌面文档旁证：run plan 重跑生成的新 history"可以稍后改名，工具会同步改名结果数据库"（`asmRunPlan.html:951`）。
- 风险：
  - 改名后结果目录、`<name>.rdb/.log/.msg.db`、`history/<name>.zip` 是否同步改名，**官方文档没有给出 SKILL 级说明**，必须真机核对；
  - 如果该 history 是 Overwrite History 的目标，文档说锁定/改名/删除后覆盖选项会自动回到 "Next History Run"（`asmCheckpoints.html:184`）——改名前应提示这一副作用；
  - 新名字必须做字符校验（拒绝路径分隔符等）。

### 4.6 复制

**支持等级：部分支持（无"原地复制单条"API）**

- `axlLoadHistory(to, from)`：把源分支（如某条 history 的 checkpoint）**复制进当前 setup 数据库**，返回副本句柄——语义是"把历史 setup 拉出来作为新分支"，不是"生成一条并列 history 条目"。
- `axlCommitSetupDBAndHistoryAs(hsdb, name)`：整体另存（整个 setup DB 连同所有 history 另存为新名字），不是单条复制。
- `maeImportHistory(...)`：从**另一个 cellview** 导入 history zip（要求 separate history management；`?copyPSF`、`?overwrite` 可选）。文档流程：File → Import History，勾选 histories、Copy PSF、Overwrite History（`asmCheckpoints.html:508-525`）。
- 结论：
  - 跨 cellview 复制 → 用 `maeImportHistory`（可行）；
  - 同 cellview 内复制一条 history → **没有直接 API**；可行的迂回是"以该 history 的 setup 重跑一次"或"导入其 zip"，两者都会改变语义（重跑耗资源；zip 导入依赖新格式）。
  - 建议：本版把"复制"标为**暂定/后续扩展**，优先做 delete/rename/lock/delete-results 四件套。

### 4.7 锁定 / 解锁

**支持等级：SKILL 直接支持**

- 写：`maeSetHistoryLock(name, t/nil, ?session)`（Assembler）；`axlSetHistoryLock(handle, enable)`（句柄版）。
- 读：`maeGetHistoryLockFlag` 返回 `0/1/2/3/4`（未锁 / 用户锁 / 引用锁 / 二者 / MC reuse 锁）；`axlGetHistoryLock` 布尔版。
- 规则（桌面文档）：
  - 锁后 Delete 不可用；子条目随父级锁定（`asmCheckpoints.html:474-498`）；
  - `ExplorerRun.0` 不可锁（`asmCheckpoints.html:482`）；
  - 锁的条目不计入"保存条数上限"（同段）。
- 风险：`2/3/4` 类锁定不是"用户手动锁"，来自引用与 Monte Carlo reuse——解锁请求应当区分对待，建议只允许把 `1/3` 中的用户锁部分解锁（即调用 unlock 后复读 flag 验证）。

### 4.8 覆盖式运行

**支持等级：SKILL 直接支持**

- `axlSetOverwriteHistory(setup, t)` 打开覆盖；`axlSetOverwriteHistoryName(setup, name)` 指定被覆盖的 history；读取用 `axlGetOverwriteHistory(Name)`。
- OCEAN XL 等价：`ocnxlSetOverwriteHistory` / `ocnxlSetOverwriteHistoryName`。
- 行为规则（桌面文档）：
  - "Overwrite History" 下拉只列出**未锁定且未被选作 reference** 的 history（`asmCheckpoints.html:183`）；
  - 目标被锁定/改名/删除时，选项自动回落到 "Next History Run"（`asmCheckpoints.html:184`）；
  - 覆盖运行时上一条 history 的结果会被删除再重建；勾选 Retain Netlist Directory 可保留 netlist 复用（`asmCheckpoints.html:158` 附近）。
- 旧代码：`run_simulation` 只调用 `maeRunSimulation`（`writer.py:339-355`），没有覆盖选项处理；覆盖式运行属于新增能力。
- 建议：把"覆盖"设计成仿真运行操作的参数（`overwrite: {enabled, name}`），运行前读锁与 reference 校验，运行后按返回 history 名验证。

---

## 5. 建议的业务操作映射

基于 §4，建议为未来的 maestro 业务包规划如下 history 相关业务操作（名称仅提案）：

| 业务操作 | 建议名 | 底层机制 | 读/写 | 优先级 |
|---|---|---|---|---|
| 列出 history | `virtuoso.maestro.history_list` | `axlGetHistory` + group 展开 + 磁盘 mtime 补充 + `maeGetHistoryLockFlag` | 读 | P1 |
| 当前 history | `virtuoso.maestro.history_current` | `axlGetCurrentHistory`（多 accessor 回退） | 读 | P1 |
| 删除整条 history | `virtuoso.maestro.history_delete` | 锁检查 → `axlRemoveElement(axlGetHistoryEntry)` / Explorer 用 `maeDeleteExplorerHistory` → 验证 | 写 | P1 |
| 删除仿真数据（部分） | `virtuoso.maestro.history_delete_results` | `maeDeleteSimulationData`（keep 选项映射 GUI 三档） | 写 | P2 |
| 重命名 | `virtuoso.maestro.history_rename` | `axlSetHistoryName` → 验证 RDB/目录一致性 | 写 | P2 |
| 锁定 / 解锁 | `virtuoso.maestro.history_lock` / `history_unlock` | `maeSetHistoryLock`；先读 `maeGetHistoryLockFlag` | 写 | P2 |
| 覆盖式运行 | `virtuoso.maestro.run(overwrite=…)` | `axlSetOverwriteHistory(Name)` + `maeRunSimulation` | 写 | P2 |
| 复制（跨 cellview 导入） | `virtuoso.maestro.history_import` | `maeImportHistory`（依赖 separate history 格式） | 写 | P3 暂定 |
| 复制（同 cellview） | `virtuoso.maestro.history_copy` | 无直接 API；需重跑或 zip 导入迂回 | 写 | 暂定（可不做） |

### 5.1 通用安全建议（所有 history 写操作）

1. **先读后写**：任何删除/改名/锁定前，先取该 history 的句柄与锁状态；锁状态 ∈ {2,3,4} 时默认拒绝（可显式 override，但要留痕）。
2. **读回验证**：每个写操作结束后用 `axlGetHistory` / `maeGetHistoryLockFlag` 复读，作为 Result 的步骤证据（沿用上层"步骤痕迹"规范）。
3. **不做文件系统直删**：所有删除走 SKILL。只有当真机验证确认 SKILL 留下了不一致磁盘残留、且业务方明确要求时，才考虑受控清理（路径白名单 + 名称校验），并且必须在 spec 里写清楚风险。
4. **一次一条**：批量删除由调用方循环，不要在业务包内部隐式批量（与官方 API 能力对齐，也便于逐条留证据）。
5. **名称校验**：新名字禁止 `/`、`\`、`..`、空白开头等；宁可在 Request 校验层拒绝，也不要把可疑名字拼进 SKILL 或 shell。
6. **会话绑定**：所有操作显式带 `?session`（旧代码经验：current session 在无 GUI/后台场景不可靠）；无会话时结构化失败而不是回退到"当前窗口"。

---

## 6. 版本与兼容性注意

| 事项 | 说明 | 来源 |
|---|---|---|
| separate history management | ICADVM20.1 默认开启；IC6.1.8 需 `useSeparateHistoryFileManagement` | `appEnvVars.html:3249-3286`、`asmCheckpoints.html:508` |
| `maeDeleteExplorerHistory` | 文档标注为 ADE Explorer 专用；Assembler 用 `axlRemoveElement` | `maestroSKILL.html` |
| `maeGetHistoryLockFlag` | 5 态锁；`2/3/4` 非用户锁 | `maestroSKILL.html` |
| `ocnxlRenameCurrentHistory` | OCEAN XL 场景 | `ocnxl.fnd` |
| 老版本行为 | IC6.1.8 的 `axlGetCurrentHistory` 返回对象 `~>name` 常为 nil（旧代码需要多 accessor 兜底） | `bundle.py:126-131` |

---

## 7. 待真机验证清单（写 spec 前必须闭环）

1. **删除整条 history 的磁盘效应**：`axlRemoveElement(axlGetHistoryEntry(...))` 之后，
   - `results/maestro/<name>.{rdb,log,msg.db}` 与 `<name>/` 目录是否消失？
   - separate 格式下 `history/<name>.zip` 与 `history.sdb` 是否同步？
   - 若残留，官方 GUI Delete 与 SKILL 删除的差异是什么？
2. **`maeDeleteExplorerHistory` 的持久化语义**：只删会话内条目还是也落盘？Explorer 单 history（ExplorerRun.0）删除后还能再跑吗？
3. **改名一致性**：`axlSetHistoryName` 后检查 `results/maestro/*`、`history/*.zip`、reference 关系、Overwrite 目标回退行为（`asmCheckpoints.html:184`）。
4. **锁定与引用**：对被引用（flag 2/3）的 history 执行删除/改名/删除数据的实际报错形态；解锁是否可能把引用锁一并解除。
5. **run-plan 子 history**（HistoryChildren）：删除父条目时子条目是否级联；`maeDeleteRun` 与 history 删除的边界。
6. **Monte Carlo / ImproveYield group history**：`axlGetHistoryGroupChildren` 删除单子条目的可行性。
7. **两种存储格式**：老格式（sdb 内嵌）与新格式（zip + history.sdb）分别跑一遍删除/改名，记录差异。
8. **无 GUI 后台会话**：`maeOpenSetup` 后台会话 + `axlRemoveElement` 组合是否可用（旧代码后台会话经验：`examples/01_virtuoso/maestro/03_bg_open_read_close_maestro.py`）。

---

## 8. 引用来源汇总

### 8.1 仓库内代码

| 文件 | 行 | 内容 |
|---|---|---|
| `src_bak/virtuoso_bridge/virtuoso/maestro/reader/bundle.py` | 126-131 | `axlGetCurrentHistory` 多 accessor 探测 |
| 同上 | 138 | `getDirFiles(results/maestro)` 枚举 |
| 同上 | 221-245 | project/scratch 两处 mtime 合并 |
| `reader/session.py` | 33-38 | `.rdb/.log/.msg.db/Interactive.N/MonteCarlo.N` 识别规则 |
| 同上 | 132-150 | 自然排序 |
| 同上 | 157-176 | mtime 排序与混合命名说明 |
| `reader/runs.py` | 118-142 | 最新有结果 history 的挑选与 CSV 导出 |
| 同上 | 163-172 | 临时 CSV 本地/远端清理（仅临时文件） |
| 同上 | 186-215 | `maeOpenResults`/`maeCloseResults` 扫描 |
| 同上 | 385-414 | `asiGetResultsDir` history 解析与校验 |
| `reader/snapshot.py` | 175-244 | per-history 快照打包 |
| 同上 | 320-323 | 临时 tar 清理（`rm -f` 仅限临时文件） |
| 同上 | 431-515 | 快照 history 选取逻辑 |
| `writer.py` | 139-155 | `axlRemoveElement(axlGetVar(...))` 删除变量（唯一先例） |
| 同上 | 339-355 | `maeRunSimulation` |
| 同上 | 495-575 | run-and-wait marker 轮询 |
| 同上 | 642-673 | GUI 打开 history（`maeRestoreHistory`） |
| `waveform_viewer.py` | 113-141, 151-180 | `maeOpenResults` + AWV 窗口 |
| `lifecycle.py` | 126-136 | `dbPurge` 内存清理（与删除无关） |
| `examples/01_virtuoso/maestro/05_gui_session_lifecycle.py` | 172, 230 | `axlRemoveElement(axlGetVar(...))` 示例 |
| `test_bak/test_maestro_ops.py` | 17-21 | 旧 API 清单（无 history 写操作） |
| `test_bak/test_maestro_read_results.py` | 141-148 | 仅临时 CSV `deleteFile` 断言 |

### 8.2 SKILL 文档（8123 服务）

- `maeSKILLref.fnd`：`axlGetHistory`、`axlGetHistoryEntry`、`axlGetCurrentHistory`、`axlGetHistoryLock`、`axlSetHistoryLock`、`axlSetHistoryName`、`axlSetOverwriteHistory(Name)`、`axlCommitSetupDBAndHistoryAs`、`axlPutHistoryEntry`、`axlLoadHistory`、`axlRemoveSimulationResults`、`maeDeleteExplorerHistory`、`maeDeleteSimulationData`、`maeSetHistoryLock`、`maeGetHistoryLockFlag`、`maeImportHistory`、`maeDeleteRun` 等条目。
- `$maeSKILLref/historyRelated.html`：`axlRemoveSimulationResults`（含 "use axlRemoveElement" 交叉引用与 GUI 对应）、`axlSetHistoryName`（含完整示例）、`axlLoadHistory`。
- `$maeSKILLref/setupDB.html`：`axlRemoveElement`（含官方删除 history 示例）、`axlCommitSetupDBAndHistoryAs`。
- `$maeSKILLref/maestroSKILL.html`：`maeDeleteExplorerHistory`、`maeDeleteSimulationData`、`maeSetHistoryLock`、`maeGetHistoryLockFlag`、`maeImportHistory`、`maeDeleteRun`。
- `ocnxl.fnd`：`ocnxlRenameCurrentHistory`、`ocnxlSetOverwriteHistory(Name)`、`ocnxlGetCurrentHistory(Id)`。

### 8.3 桌面文档

| 文件 | 行 | 内容 |
|---|---|---|
| `assembler/asmCheckpoints.html` | 445-457 | Deleting Simulation Data（三档子菜单） |
| 同上 | 461-467 | Deleting a History Checkpoint（删除语义） |
| 同上 | 471-498 | Locking and Unlocking（含 ExplorerRun.0 例外、子条目继承） |
| 同上 | 508-525 | Importing Histories from Another Cellview（zip + history.sdb） |
| 同上 | 158 | 覆盖运行时上一条 history 数据删除与 Retain Netlist |
| 同上 | 183-184 | Overwrite 下拉限制与自动回退 |
| `adexl/adexlCheckpoints.html` | 506-535 | 同上（ADE XL 版） |
| `assembler/asmWorkingSetup.html` | 211 附近 | separate history management 的 zip 存储描述 |
| `assembler/appEnvVars.html` | 3249-3286 | `useSeparateHistoryFileManagement` 环境变量 |
| `assembler/asmRunPlan.html` | 951 | 改名同步结果数据库的旁证 |

---

## 9. 与既有 spec/报告的关系

- 本报告只解决"history 删除/改名/复制/锁定"的可行性问题，不改变《6-maestro.md》的操作分类（历史读 / 历史写）。
- 建议在 maestro spec 的"历史类"一节的待修订项中引用本报告 §4.3–§4.8 与 §7：
  - 删除：机制已明确（`axlRemoveElement` / `maeDeleteExplorerHistory`），待验证磁盘一致性与锁保护；
  - 改名：机制已明确（`axlSetHistoryName`），待验证一致性；
  - 复制：无单条原地 API，维持"暂定"；
  - 锁定：机制与状态机已明确，可直接进入 spec 定稿；
  - 覆盖式运行：机制明确，建议并入仿真运行的参数而不是独立操作。

（报告完）
