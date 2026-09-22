# 上层业务包：veriloga

> 版本：Draft v1（方案已确认）
> 日期：2026-09-21
> 状态：Draft（方案已与用户确认，待纳入 README 治理）
> Supersedes：无（从 `8-verilog.md` v1–v5 拆出）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

本包管 **VerilogA（模拟行为代码）** 的文本视图创建、读写与"Check and Save"。
结构 Verilog 归 `verilog` 包（见[8-verilog.md](8-verilog.md)）。

核心工作流是 GUI 里"打开 → 敲代码 → Check and Save"的 headless 等价：

**`write`（写 `veriloga.va`）→ `check_and_save`（`VerAParseModule` 检查 + `ahdlUpdateViewInfo` 保存/刷新 CDF）**。
不需要 import，不需要 PDK，不需要外部工具（检查内部调用 Spectre 的 AHDL 解析器）。

| 类别 | 操作名 | 一句话说明 | 接口 |
|---|---|---|---|
| 读 | `virtuoso.veriloga.read` | 读源码文本 / 端口 / 视图清单 / 诊断（`focus` 可选） | S+D |
| 写 | `virtuoso.veriloga.write` | 通用写：对代码做原子文本编辑（只落盘） | S+U |
| 检查保存 | `virtuoso.veriloga.check_and_save` | `VerAParseModule` 检查 + `ahdlUpdateViewInfo` 保存/刷新 CDF | S+C |

对象模型：

| 载体 | 说明 |
|---|---|
| 文本视图 `veriloga` | dfII viewType=`text.veriloga`、dataType=`VERILOGAText`、主文件 `veriloga.va`（+ `master.tag`） |
| 持久化产物 | `check_and_save` 后生成 `veriloga/netlist.oa` + `veriloga/data.dm`，并更新 cell CDF 的 `viewInfo` |

边界：

- 文本视图的建立/覆盖/删除由本包负责（`dbOpenCellViewByType` 建不了它，cellview 包的 `view.create` 对它恒失败）；
- symbol 生成不在本包（归 symbol 包能力，见 §2；`ahdlSymbolGen` 禁用）；
- 编译/仿真归 spectre 包（IC6.1.8 无 `ahdlCompile*`）；
- 结构 connectivity 读回用 `schematic.read`。

### 1.1 读操作（read）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read | `focus` 可选、可组合；不填=全部 | 定位源码路径 → 读文本/端口/视图/诊断 | S+D |

- 目标二选一：
  - `{library, cell, view="veriloga"}`——文本视图读源码；
  - `{file_path, file_is_local}`——外部 `.va` 文件（显式声明路径域）；
- focus：

| focus | 返回 |
|---|---|
| `source` | `text / path / size / sha256 / lines` |
| `ports` | 端口表 `name / direction / width`（`ahdlToPinList`；AHDL 上下文未加载时返回 `unsupported` 并说明） |
| `views` | 该 cell 的视图清单（用 `ddMapGetFileViewType`/`ddMapGetFileDataType` 判定） |
| `diagnostics` | 最近一次 `check_and_save` 的 `err_log / status / error_count / errors[]` |

- 源码路径 = `ddGetObjReadPath(ddGetObj(lib cell "veriloga" "veriloga.va"))`；
- 读源码就是读文件（`infile`/`gets` 或 Python 直读），**不用 `lineread`**（它是 SKILL 语法读取器）；
- `read` 纯只读：不得调用 `ahdlUpdateViewInfo` 等会改缓存/视图状态的函数。

### 1.2 写操作（write）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| write | 通用写：`lib/cell/view + commands[]` | 读现状 → 逐原子改文本 → 覆盖写 | S+U |

`write.commands` 每项 = `{"op": 原子名, ...参数}`；**非事务**，失败响应带 `commands applied: k/n`。

| 对象 | 原子名 | 索引（动哪个） | 附加参数 |
|---|---|---|---|
| 代码 | `set_source` | 目标 view 或 file | `text`；可选 `expected_sha256`（不符则失败） |
| 代码 | `patch_source` | 目标 view 或 file | `edits[]`：`{old_text,new_text}` 或 `{start_line,end_line,new_text}`；匹配不唯一默认失败（可 `all=true`） |
| 文本视图 | `ensure_view` | `{library, cell, view="veriloga"}` | `view_type="text.veriloga"`、可选 `create_if_missing=true`；内部写 `master.tag` + 主文件模板 |
| 文本视图 | `delete_view` | `{library, cell, view="veriloga"}` | —（`ddDeleteObj`，先确认无编辑器窗口/`*.cdslck`） |

提交口径：

1. 写临时文件 → 校验读回 → 原子替换 `veriloga.va`；
2. 目标 view 不存在且 `create_if_missing=true` 时先建 `master.tag` + 模板再写内容
   （`master.tag` = `-- Master.tag File, Rev:1.0\nveriloga.va\n`；模块名必须与 cell 名一致）；
3. `write` 只落文件，**不调 `ahdlUpdateViewInfo`**——检查/刷新由调用方随后执行 `check_and_save`；
4. 有 `*.cdslck`（编辑器开着）时禁止外部写：报失败并提示关闭编辑器，不自动关别人的窗口。

### 1.3 检查与保存（check_and_save）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| check_and_save | GUI "Check and Save" 的 headless 等价序列 | `VerAParseModule` 检查 → `ahdlUpdateViewInfo` 保存/刷新 CDF | S+C |

1. `VerAParseModule("<abs .va>", "cell", "<errFile>")`：
   成功返回 `status/moduleName/pinList/pinOrder/paramList`；失败返回 `nil`，`VACOMP-xxxx` 写进 `errFile`；
2. 检查通过后 `ahdlUpdateViewInfo(lib ?cell cell ?view "veriloga")`：
   持久化 parse 结果——更新 CDF `viewInfo`（`moduleName/namePrefix/termOrder/termMapping/parameterList`）、
   生成 `veriloga/netlist.oa` + `veriloga/data.dm`；
3. 返回 `ok / module_name / ports[] / pin_order[] / param_list / errors[] / err_log`；
4. 前置：AHDL 上下文必须已加载（`loadContext("<IC618>/.../ahdlSck.cxt")`，见 §4）；
5. **不用** `ahdlCheckModule` / `ahdlSaveFile` / `ahdlEdit`（编辑器 GUI 内部包装，错误或缺 symbol 会弹模态阻塞 CIW）。

真机结论：上述序列与 GUI Check and Save 的落盘形态**逐文件一致**，唯一差别是不含 GUI 弹窗生成的 `symbol` 视图；
Spectre 用 `ahdl_include` 可直接编译该 cell（`Installed compiled interface`，dc 收敛）。

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 归属（不在本包）

| 能力 | 归属 |
|---|---|
| view CRUD（OA 视图） | cellview |
| 文本视图（`text.veriloga`）的建立与覆盖 | **本包例外**（cellview 建不了） |
| symbol 生成 | symbol（`ahdlToPinList` 的 ports + `schPinListToSymbol`，待 spike；`ahdlSymbolGen` 禁用） |
| 编译 / 仿真 / `ahdlSimDB` 缓存 | spectre 包 |
| 结构 Verilog | verilog 包 |
| GDS 导入/导出 | layout（`layout.gds`） |

## 3. 不在本版

- `compile`：IC6.1.8 无 `ahdlCompile*`，编译归 Spectre；
- GUI 打开/关闭 VerilogA 编辑器（`deOpenCellView`/`hiCloseWindow`）——纯人工操作，不进业务 API；
- view 改名（无 dd API）、`ahdl`（SpectreHDL 遗留格式）、Verilog-AMS/SystemVerilog/VHDL 文本视图；
- 并发写同一 cell。

## 4. 真机事实（IC6.1.8，2026-09-21 实测）

1. **VerilogA 是文本视图**：view=`veriloga`、viewType=`text.veriloga`、dataType=`VERILOGAText`、文件=`veriloga.va`；
   `dbOpenCellViewByType(..., "veriloga"/"text.veriloga", "w")` **恒 nil** → 必须走文件路径；
2. `master.tag` 内容固定 `-- Master.tag File, Rev:1.0\n<主文件名>\n`；写完文件 `ddUpdateLibList()` 即可识别；
3. 读源码用 `infile`/`gets` 或直接读文件；**`lineread` 不能读 `.va`**；
4. `ahdlCompile*` 不存在；编译只能由 Spectre（`ahdlcmi`）完成，缓存 `<netlist>.ahdlSimDB/<srcHash>.*.ahdlcmi/`；
5. AHDL 上下文（`ahdlSck.cxt`）默认未加载；**冷启动 `loadContext("<IC618>/tools.lnx86/dfII/etc/context/ahdlSck.cxt")`
   一条即可**（隔离 `-nograph` 冷实例验证，函数全部变 `funobj`）；
6. `ahdlSymbolGen` 会弹模态窗阻塞 CIW（真机卡死 60s+）→ 禁用；
7. 编辑器打开时产生 `veriloga.va.cdslck` 锁 → 外部写文件失效，必须先关编辑器；
8. 删除 `ddDeleteObj(ddGetObj(lib cell "veriloga"))` 干净（无残留、无编译缓存）；
9. **headless 的 Check and Save 已真机闭环**：写文件 → `VerAParseModule`（错误进 errFile）→
   `ahdlUpdateViewInfo`（CDF + `netlist.oa`/`data.dm`），与 GUI 保存逐文件一致，唯一差别是无 `symbol` 视图；
10. **不要用** `ahdlCheckModule`（错误弹 `QverilogaErr` 阻塞）、`ahdlSaveFile`（缺 symbol 弹模态）、
    `ahdlEdit`（拉起外部编辑器）——三者是编辑器 GUI 内部 hook。

## 5. 决策记录（2026-09-21，已确认）

| # | 决策 |
|---|---|
| 1 | 包名 `veriloga` / `11-veriloga.md`，operation 前缀 `virtuoso.veriloga.*` |
| 2 | 装码 = `write` + `check_and_save`，不提供 import |
| 3 | `check_and_save` = `VerAParseModule` + `ahdlUpdateViewInfo`；AHDL 上下文冷加载用 `loadContext` 全路径 |
| 4 | `write` 允许创建文本视图（`ensure_view`）——view CRUD 归属的显式例外 |
| 5 | 端口方向以 `.va` 的 module 声明为准（默认 `inputOutput`），调用方不重复传方向 |
| 6 | 不独立暴露 `reparse`/`ahdlUpdateViewInfo`，合并进 `check_and_save` |
| 7 | symbol 生成不在本包；需要时走 symbol 包（待 spike），`ahdlSymbolGen` 禁用 |

## 6. 待验证（实现前需 spike）

1. `schPinListToSymbol` 用 `ahdlToPinList` 的 ports 生成 symbol 的可行性（端口顺序/方向）。
