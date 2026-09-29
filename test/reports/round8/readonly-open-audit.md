# 只读审计：read 路径的"打开方式"是否用错（P-104 同类）

> 执行：测试/root 亲自做（subagent 通道不可用）｜ 2026-09-29
> 任务书：`test/reports/round8/readonly-open-audit-brief.md`｜ 范围：`src/`（含 `src/bridge/resources/`、生成的 `*.il`）
> 硬约束遵守情况：**全程只读**——未改任何文件、未开真机会话、未调产品 API、未建/删任何 VG 对象；只用 `rg`/`Get-Content`/`git log` 与 `http://127.0.0.1:8123` 只读查询（该文档服务审计开始时已停，由 root 用 `tools/skill_doc_server.py --port 8123` 重新拉起，载入 9503 条条目）。

## 0. 结论（一句话）

**未发现新的 P-104 同类问题**：`src/` 内所有"打开/获取对象"的调用点，**读路径全部显式传了只读参数**（`"r"` / `?mode "r"`）；默认参数会创建对象的 API（`ddGetObj`、`dbOpenCellViewByType`、`maeOpenSetup`、`ddCatOpen`）在读路径上**没有一处**省略只读参数。`maeOpenSetup` 的两处调用中，读路径（`read_config`/`read_results`/`export`/`read_history`/`open_waveform_gui`）**已传** `?mode "r"`（P-104 修复已在工作区代码里），写路径（`write`/`write_history`）保留默认 `"a"`，符合已定案口径。

另有 2 条**相邻观察**（不属本类判定，见 §4），只进"待真机验证"清单，不进 bug 卡。

## 1. 方法与覆盖面

1. **全量枚举**：用正则 `\b[A-Za-z_][A-Za-z0-9_]*[Oo][pP][eE][nN][A-Za-z0-9_]*\s*\(` 扫 `src/` 全树（`*.py` + `*.il`），把"名字里带 open"的函数一网打尽，避免只按任务书给的清单查漏。命中族：`dbOpenCellViewByType`(21 匹配)、`ddCatOpen`(15)/`ddCatOpenEx`(2)、`geOpen`(4)、`maeOpenSetup`(2)、`maeOpenResults`(1)、`deOpenCellView`(1)、`dbGetOpenCellViews`(1)、`dbFindOpenCellViewByName`(1)、`hiGetWindowList`(12)、`XOpenDisplay`(2)、`ddGetObj`(53)、`ddGetObjFiles`(2)、`Popen`/`fdopen`/`_open_session*`/`_open_*`（子进程/socket/文件句柄，非 Cadence 对象 API）。
2. **逐函数查 8123**：`GET /api/find?q=<fn>&mode=exact`、`GET /api/info?name=<fn>`，三问 = 有没有只读参数 / 默认值是什么 / 默认会不会创建·加锁·进编辑态。
3. **调用点取证**：对每个族的每个调用点提取完整实参（带一层嵌套括号的正则，避免 grep 在跨行调用上截断），标注 mode 实参；再用"最近的上层 `def`"把调用点归到读/写路径。
4. 判定口径（任务书）：**只标记**"读路径 + 未传只读参数 + 默认有创建/加锁/编辑副作用"；写路径用可写/默认模式不算问题。

## 2. 逐函数核对表

| 函数 | 代码位置（文件:行） | 官方文档结论（8123 原文引用） | 实际用法（读/写 + 传了什么） | 风险 | 判定 | 建议的只读写法 |
|---|---|---|---|---|---|---|
| `ddGetObj` | 53 处：`cellview.py`(23)、`layout.py`(6)、`symbol.py`(6)、`_symbol_generate.py`(6)、`maestro.py`(2)、`verilog.py`(4)、`veriloga.py`(3)、`schematic.py`(2) | "Finds libraries, cells, views, and files, **and creates** cells, views, and files"；mode 表末行 **"Default: `r` (read)"**；"`ddGetObj` creates new cells, views, and files **as a side-effect to `w`, `wd`, `a` or `ad` mode requests** when the object is created." | **53/53 都没传 mode 实参** → 全部走默认 `r`。用法多为存在性探测（`if(ddGetObj(...) then ...)`）与取 `~>readPath`。 | 无创建（默认即只读） | **OK** | 已是推荐写法；若要更保守可显式写 `nil "r"`，无必要 |
| `dbOpenCellViewByType` | 21 处匹配 = 18 个直接调用 + 2 处 helper 定义（`layout.py:345`、`symbol.py:328`）+ 1 处注释（`symbol.py:337`）；另有 5 个经 `_open_expr` 的调用（`layout.py:415/447/958/1102`、`symbol.py:375`） | "If you open the cellview for the **read mode, the cellview must exist**. if you open the cellview for other modes, **the cellview is created** if it does not exist."；mode 表：`r`="The cellview must already exist."，`a`="If the cellview does not exist, it is created." | 读路径（`_read_skill`、`_view_state_expr`、`_verify_import`、`_display_expr`、`_symbol_generate` 源/临时/备份视图、`cellview` 复制源）**全部 `"r"`**；写路径 `"a"`（`_symbol_generate.py:179` 目标 symbol、`schematic.py:423` 编辑打开）与 `"w"`（`cellview.py:394` view 创建）——共 r×15 / a×2 / w×1（18 个直接调用）。`_open_expr` 的 `mode` 是**必填位置参数**（无默认值）。 | 无创建（读路径）；写路径本就要创建/编辑 | **OK** | 维持；helper 无默认值是正确设计，防回退 |
| `maeOpenSetup` | 2 处：`maestro.py:412`（`_open_session`）、`maestro.py:3180`（`open_waveform_gui`） | "If the given cellview **does not exist, the function creates a new cellview** with the same name."；`?mode`："`a`: … **This is the default.** `r`: Opens the maestro view in read mode. **You cannot create a new view in read mode.**" | `_open_session(mode=...)`：读路径 4 处已传 `mode="r"`（`read_config:1369`、`read_results:1918`、`export:2122`、`read_history:2496`），写路径 2 处不传（`write:1736`、`write_history:2607` → 默认 `"a"`）；`open_waveform_gui` 写死 `?mode "r"`。 | 读路径无创建（P-104 修复已在代码里） | **OK**（P-104 本体按用户口径不复验，等修复通知） | 保持；建议后续写路径也显式传 `"a"`，消除隐式默认 |
| `ddCatOpen` / `ddCatOpenEx` | 17 处：`cellview.py:472,487,505,511,518,533,539,546,560,570,574,584,593,600,620,629,637` | "The modes `a`, `w`, or `r`."；"`nil` = **The category does not exist or cannot be opened in the specified mode**"；示例注释 "Updates (**or creates**) a category … `ddCatOpen(libId "myCat" "a")`" | 读（list/取成员）全部 `"r"`；写（建/删/改名/增删 cell 分类）`"a"`/`"w"`+`keepEmpty`。 | 无创建（读路径） | **OK** | 维持 |
| `geOpen` | 4 处：`layout.py:1613`（截图）、`layout.py:1862`（截图）、`schematic.py:936`（截图）、`symbol.py:1092`（截图） | `geOpen` 打开窗口；mode 语义同 `dbOpenCellViewByType`（`"r"` 要求已存在） | 4/4 全部 `?mode "r"`，且都在"先 `hiGetWindowList` 找已开窗口、找不到才 geOpen"的兜底分支。 | 无创建 | **OK** | 维持 |
| `deOpenCellView` | 1 处：`maestro.py:604`（`_ensure_gui_session`） | "**Opens an existing cellview** in a window."；"If the open failed, `nil` is returned."；`t_accessMode`："`a` (edit), `r` (read), `w` (clears the old data and edit from scratch)" | 显式 `"maestro" nil "a"`；调用者 = `open_gui`(2752) 与 `run`(3008)，都是"用户要求开 GUI / 跑仿真"的执行路径；失败走结构化报错（609-614）。 | 无创建（文档仅"打开已存在"）；编辑态/编辑锁见 §4-A2 | **OK**（非 P-104 类） | 不建议在 ADE 只读语义确认前改 `"r"`（会破坏 `run`/`maeMakeEditable` 逻辑）；见 §6-V2 |
| `maeOpenResults` | 1 处：`maestro.py:836`（`_latest_history`） | 签名只有 `?session/?history/?run`，**没有只读/模式参数**；"Opens the result for the given history or run plan, and **sets the result pointer** to be used by other functions."（配对 `maeCloseResults`） | 逐条 `maeOpenResults(...)` 后立即 `maeCloseResults()`，只用于"这条 history 是否可打开"的探测。 | 无创建；仅改进程内全局 result 指针（已配对复位） | **OK** | 维持；多 token 共 CIW 时注意指针（§6-V4） |
| `dbGetOpenCellViews` | 1 处：`maestro.py:634`（`_purge_cellview`） | "Returns all opened cellviews in virtual memory."（`$skdfref/cvio.html`） | 纯枚举内存中已打开视图，随后 `errset(dbPurge(cv))`。 | 枚举无副作用；`dbPurge` 另计（§4-A1） | **OK** | 维持 |
| `dbFindOpenCellViewByName` | 1 处：`_symbol_generate.py:144` | "Finds an opened cellview."；"`nil` = The specified cellview is **not open in the memory**." | 只查内存里是否已打开（判断需不需要合并/刷新），不打开、不创建。 | 无 | **OK** | 维持 |
| `hiGetWindowList` | 12 处：`layout.py:1603,1608,1854,1858`、`schematic.py:932`、`symbol.py:1082,1087`、`maestro.py:459,2388,2395,2806,3289` | "Returns a list of window IDs of all windows that have been created but not closed" | 纯枚举窗口句柄。 | 无 | **OK** | 维持 |
| `ddGetObjFiles` | 2 处：`verilog.py:260`、`veriloga.py:278` | "Lists all the files found in the object." | 枚举视图文件（挑 netlist 候选）。 | 无 | **OK** | 维持 |
| `XOpenDisplay`、`Popen`、`fdopen`、`_open_session_channel`、`_open_proxy_socket`、`_execute_openssh_*` | `gui.py:43,101`；`paramiko_backend.py`/`ssh.py`/`server.py`/`ramic_bridge_daemon_*.py` 多处 | — | X11 显示连接 / 子进程 / 文件描述符 / socket，**不是 OA 对象 API**。 | 无 | **N/A** | — |
| `hiOpenWindow`、`hiOpenCellView`、`ahdlOpen`、`schOpen`、`dbOpenLib`、`ddOpenLib`、`dbOpenCellView`、`dbOpenCellViewByName` | — | — | **`src/` 内不存在这些调用**（grep 0 命中）；`src/bridge/resources/*.il` 也没有任何 open 类调用（grep 0 命中）。 | — | **N/A** | — |

### 2.1 正面模式（值得当模板）

凡"先探测存在、再编辑打开"的写法都是**正确姿势**，P-104 类问题的根治法就是它：

- `layout.py:351 _view_state_expr` / `364 _require_view_exists`：先 `ddGetObj` + `dbOpenCellViewByType(..., "r")` 判 `ok/mismatch/missing`，`write`(535) 与 `gds` 导出(1076) **都先过这道闸**，之后的 `_open_for_edit_error`（"a" 探测）与 `_open_edit_expr`（"a" 打开）**只会发生在对象已存在之后**。
- `schematic.py:406 _open_edit_skill`：`ddGetObj`（默认 r）判存在 → `dbOpenCellViewByType(..., "r")` 判类型 → 才 `"a"` 打开；返回 `open-ok/missing/type-mismatch/locked` 四态。
- `symbol.py:483/541`：`_require_view_exists` → `_open_edit_expr("a")`。

结论："编辑打开"在 `src/` 里 **没有一处**发生在"目标可能不存在"的读路径上。

### 2.2 打开/关闭配对抽查（任务书示例项，顺带完成）

对 18 个直接 `dbOpenCellViewByType` 打开点 + 5 个经 `_open_expr` 的打开点逐一核对 `dbClose` 配对（含错误路径）：

| 打开点 | 关闭方式 | 结论 |
|---|---|---|
| `_symbol_generate.generate_skill`（109/129/149/179/212，共 6 个句柄） | 每句柄显式 `dbClose`；整段包在 `unwindProtect`，失败路径另有 6 条 `_cleanup_close_skill`（196-201 行） | **无泄漏**（全仓句柄治理样板；回滚路径 212→232 亦关闭） |
| `layout._read_skill`(1553) | 1592 `dbClose(vbCv)`（在 `errset` 之外，体抛错也会关） | 无泄漏 |
| `symbol._read_skill`(1009) | 1073 同款 | 无泄漏 |
| `schematic._read_skill`(290) | 拼装尾部(401) `progn(when(cv dbClose(cv)))` | 无泄漏 |
| `layout._verify_import`(1357)、`verilog._verify_import`(593) | `unwindProtect` + `progn(when(… dbClose …))` | 无泄漏 |
| `layout._place_mosaic_expr`(871) | `unwindProtect` 关 master | 无泄漏 |
| `layout._view_state_expr`(357)、`cellview._cell_copy_skill`(329)、`cellview._view_copy_skill`(416) | 显式/`unwindProtect` 关闭 | 无泄漏 |
| 编辑打开（`"a"`）：`layout._open_edit_expr`、`schematic._open_edit_skill`、`symbol._open_edit_expr` | 会话级全局 `vbLayoutCv`/`vbSchemCv`/`vbSymCv`，由 `_close_edit_expr`/`_close_edit_skill`/`_save_expr` 释放；`write`/`check_and_save` 各失败分支都调用关闭（`layout.py:562/577`、`symbol.py:508/526/564`、`schematic.py:789/802/890`） | 无泄漏 |
| `_open_for_edit_error`（编辑可用性探测） | 开→立即 `dbClose` | 无泄漏 |

**句柄泄漏：0 处。**

## 3. 判定汇总

| 判定 | 条数 |
|---|---|
| **疑似问题（需立案）** | **0** |
| OK | `ddGetObj` 53、`dbOpenCellViewByType` 23 个打开点、`maeOpenSetup` 2、`ddCatOpen(Ex)` 17、`geOpen` 4、`deOpenCellView` 1、`maeOpenResults` 1、`dbGetOpenCellViews` 1、`dbFindOpenCellViewByName` 1、`ddGetObjFiles` 2、`hiGetWindowList` 12 |
| 句柄配对（`dbClose`） | 23 个打开点全部配对，**0 泄漏**（§2.2） |
| 不适用（非 OA 对象 API / 不存在） | §2 末两行 |
| 无法判定 | 0 |

## 4. 相邻观察（**不进 bug 卡**，仅供 root 排期）

- **A1（低）**：`maestro.py:625 _purge_cellview` 在 `close_gui`(2820) 里 `dbPurge`。文档原文："Forces a cellview to close and removes from virtual memory. … **all changes made, but not saved, are lost.** … purging a cellview **empties any window** in which the cellview is being displayed." 现流程在 purge 前已 `save_setup`(2799)，风险低；但同一 Virtuoso 进程内若**另一个 token/CIW** 正编辑同一 view，purge 是进程级操作，可能连带影响它。
- **A2（中）**：`deOpenCellView(..., "a")`（`maestro.py:604`）用于 `run`(3008)。"a"=edit 会取编辑态；文档另有 `maeOpenSetup` 原文："if the view is already open in some other Virtuoso session, it is opened **in read mode** in the current session"，说明跨会话 edit 语义需实机确认。**是否符合"多用户协同"预期，需真机验证**：用户 A 编辑/跑仿真时，用户 B 对同一 maestro view 调 `run`/`open_gui` 的结果（报锁？自动只读？）。
- **A3（低）**：`_latest_history` 的 `maeOpenResults`/`maeCloseResults` 探测会**改变进程内"当前结果"指针**（探测前后被置为"未打开"）。单 token 独占 CIW 的现行不变量下无影响；多 token 共 CIW 时需注意（`layout.py:439` 注释也写明该不变量）。

## 5. 建议立案清单（供 root 决策）

**0 条**。本次没有达到"读路径 + 未传只读参数 + 默认创建/加锁/编辑副作用"判定标准的调用点，故不建议立案；§4 的 A1/A2 属于语义确认类，建议先按 §6 真机验证，拿到现象再决定是否立案（避免制造无现象的噪声卡）。

## 6. 待 root 真机验证清单（本轮未跑）

| 编号 | 验证内容 | 建议最小动作 | 期望 |
|---|---|---|---|
| V1 | 读路径不再创建 view（P-104 回归，**等修复通知后做**） | 对不存在 view 调 `maestro.read_config`/`read_history`/`export`/`open_waveform_gui`，事后 `ls` 目标 cell 目录 | 无新 view 目录、无 `*.cdslck` 残留 |
| V2（=A2） | 跨用户并发 `maestro.run` 同一 view | 用户 A 起 session 不关；用户 B 同 view `run` | 记录 B 的实际返回（成功/只读/报锁），据此定"是否产品缺陷" |
| V3（=A1） | `close_gui` 的 purge 是否影响同进程他 token 未保存编辑 | 同 CIW 两 token：token1 编辑布局不保存，token2 对**同 view** `maestro.close_gui` | 记录 token1 的编辑是否丢失（判断是否需要隔离） |
| V4（=A3，可选） | `_latest_history` 探测对"当前已打开结果"的影响 | 先 `maeOpenResults` 打开一个 history，再调 `maestro.read_history`，查指针 | 若指针被复位影响后续 `maeGetOutputValue`，再评估 |

## 7. 证据与复现（只读命令）

```powershell
# 8123 文档服务（审计开始时已停，root 重新拉起）
python tools/skill_doc_server.py --port 8123
# 逐函数文档
Invoke-RestMethod "http://127.0.0.1:8123/api/info?name=ddGetObj"
Invoke-RestMethod "http://127.0.0.1:8123/api/find?q=dbGetOpenCellViews&mode=exact&limit=5"
```

- open 家族全量枚举：正则"标识符含 open 且后跟 `(`"，对 `src/` 全树统计（见 §1 命中族清单）。
- `ddGetObj`：53 处调用提取完整实参，显式 mode 实参数量 = **0**。
- `dbOpenCellViewByType`：21 处匹配 → 2 处 helper 定义 + 1 处注释 + 18 处调用，mode 实参 = **r×15 / a×2 / w×1**；另 5 处经 `_open_expr`（`layout.py` 415/447/958/1102、`symbol.py` 375）传 **a,a,r,a,a**。

*关联卡片：P-104（`test/reports/bugs/`，本审计的起因；按用户口径"不要动、等修复通知"）。*
