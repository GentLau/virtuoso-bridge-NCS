# 上层业务包：verilog

> 版本：Draft v6（方案已确认）
> 日期：2026-09-21
> 状态：Draft（方案已与用户确认，待纳入 README 治理）
> Supersedes：`8-digital-import.md` v1、本文件 v1–v5（**VerilogA 拆出为独立包 `11-veriloga.md`**；
> 本包只负责结构 Verilog 的文本视图读写、结构导入与导出）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

本包管**结构 Verilog（数字）代码**：文本视图读写、`ihdl` 结构导入、`oa2verilog` 导出。
VerilogA 归独立包 `veriloga`（见[11-veriloga.md](11-veriloga.md)）。

| 类别 | 操作名 | 一句话说明 | 接口 |
|---|---|---|---|
| 读 | `virtuoso.verilog.read` | 读源码文本 / 视图清单 / 导入诊断（`focus` 可选） | S+D |
| 写 | `virtuoso.verilog.write` | 通用写：对文本视图做原子文本编辑（只落盘） | S+U |
| 导入 | `virtuoso.verilog.import` | 结构 Verilog → functional/symbol（默认），可选 schematic（`ihdl`） | S+C+U |
| 导出 | `virtuoso.verilog.export` | `oa2verilog`：schematic → Verilog-2001 网表 | C+D |

对象模型：

| 载体 | 说明 |
|---|---|
| 文本视图 `text.v` | 主文件 `verilog.v`，与 `text.veriloga` 同属文件式文本视图，可直接写/读 |
| 导入生成的视图 | `functional`（`verilog.v` 文本 + `netlist.oa`，默认）、`symbol`、`schematic`（可选） |

边界：

- 文本视图的建立/覆盖/删除由本包负责（`dbOpenCellViewByType` 建不了文本视图，cellview 包对它只会失败）；
- 结构 connectivity / 端口读回用 `schematic.read`，本包不重复实现网表解析；
- GDS 导入/导出归 `layout.gds`；VerilogA 归 `veriloga` 包；仿真归 `spectre` 包；
- PG label、label restyle、one-shot pipeline、SRAM 自动识别不进本包。

### 1.1 读操作（read）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read | `focus` 可选、可组合；不填=全部 | 定位源码路径 → 读文本/视图/诊断 | S+D |

- 目标二选一：
  - `{library, cell, view}`——文本视图（`view_type="text.v"`，主文件 `verilog.v`）；
  - `{file_path, file_is_local}`——外部 `.v` 文件（显式声明路径域，不做 `Path.exists()` 猜测）；
- 主文件名由 viewType 决定（`text.v` → `verilog.v`，用 `ddMapGetDataTypeFileName` 查，不在包内写死）；
- focus：

| focus | 返回 |
|---|---|
| `source` | `text / path / size / sha256 / lines` |
| `views` | 该 cell 的视图清单：`name / viewType / dataType / 文件`（用 `ddMapGetFileViewType`/`ddMapGetFileDataType` 判定） |
| `diagnostics` | 最近一次 `import` 的 `log_path / status / error_count / errors[]` |

- `ports` 不在本包：文本视图没有 Verilog 解析器；导入后的端口/连通性由 `schematic.read` 提供；
- `read` 纯只读，不触发任何解析/刷新。

### 1.2 写操作（write）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| write | 通用写：`lib/cell/view + commands[]` | 读现状 → 逐原子改文本 → 覆盖写 | S+U |

`write.commands` 每项 = `{"op": 原子名, ...参数}`；**非事务**，失败响应带 `commands applied: k/n`。

| 对象 | 原子名 | 索引（动哪个） | 附加参数 |
|---|---|---|---|
| 代码 | `set_source` | 目标 view 或 file | `text`；可选 `expected_sha256`（不符则失败） |
| 代码 | `patch_source` | 目标 view 或 file | `edits[]`：`{old_text,new_text}` 或 `{start_line,end_line,new_text}`；匹配不唯一默认失败（可 `all=true`） |
| 文本视图 | `ensure_view` | `{library, cell, view}` | `view_type`（`text.v`）、可选 `create_if_missing=true`；内部写 `master.tag` + 主文件模板 |
| 文本视图 | `delete_view` | `{library, cell, view}` | —（`ddDeleteObj`，先确认无编辑器窗口/`*.cdslck`） |

`write` 只落文件：Virtuoso 侧没有 Verilog 语法检查器，**没有 check_and_save**；
结构校验走 `import`（见 §1.3）。有 `*.cdslck`（编辑器开着）时禁止外部写。

### 1.3 导入（import）

| 参数 | 说明 |
|---|---|
| `file_path` + `file_is_local` | 源码文件（本机→上传；远端→直接用） |
| `library` / `cell` | 目标库与顶层 cell（**显式给**，不用文件名推导） |
| `schematic_view` / `functional_view` / `symbol_view` | 产出视图名（默认 schematic/functional/symbol） |
| `overwrite` | 映射 `import_if_exists` / `overwrite_symbol` |
| `timeout` / `poll_interval` | 轮询预算 |

1. 前置：`library`、`ref_libs` 在 cds.lib 可见（`ddGetObj`）；**包自建按次 cds.lib 副本**给 `-cdslib`
   （ihdl 会往里追加 `DEFINE`，不能给共享/全局那份）；
2. 生成 `ihdl_parameter`（`dest_sch_lib`、`ref_lib_list`、`import_if_exists`、`import_cells`、`import_lib_cells`、
   `structural_views`（1=schematic / 2=netlist / 4=functional / 5=schematic+functional / 6=netlist+functional，**默认 4**）、
   `schematic_view_name`、`functional_view_name`、`symbol_view_name`、`log_file_name`、`map_file_name`、
   `work_area`、`power_net`、`ground_net`）与 `-f` 选项文件；
3. 执行（**必须带 LD_LIBRARY_PATH 前缀**，否则缺 `libsasl2.so.2`、rc=127）：
   `cd <work_area> && LD_LIBRARY_PATH=<IC618>/tools.lnx86/lib/64bit/RHEL/RHEL8:$LD_LIBRARY_PATH ihdl -cdslib <copy> -param <file> <design.v>`；
4. 轮询日志：终态 `End of Logfile.`；成功 `Checked-in schematic` / `Checked in symbol` / `Checked in functional view`；
   失败 `ERROR (VERILOGIN-547)`（细节在 `xmvlog.log`）；降级警告（`VERILOGIN-19/22/72/127/575`）作为 `warnings` 上报；
5. `ddUpdateLibList()` → 校验 views；`structural_views` 含 schematic 时再校验 `instances/nets/terminals`，否则只校验
   functional/symbol 存在与端口；
6. **返回码不可信**（语法错误也 rc=0）：只用日志 + 产物判成败。

`functional` 视图 = `verilog.v` 文本 + `netlist.oa`，是 AMS/仿真网表要消费的形态，默认就够；
需要可编辑原理图时调用方把 `structural_views` 设成 1 或 5。

### 1.4 导出（export）

| 参数 | 说明 |
|---|---|
| `library / cell / view` | 要导出的 OA 视图（默认 `schematic`） |
| `output_path` | 本机目标 `.v` 路径 |
| `recursive` | 是否连层级一起导出（`-recursive`） |
| `timeout` | 单次命令 deadline |

行为：`oa2verilog -lib <L> -cell <C> -view <V> [-recursive] -verilog <out.v> -logFile <out.log>`，
工作目录需有能解析目标库的 `cds.lib`（或 `-libDefFile`）；完成后下载产物并校验（rc=0 且日志 `0 errors`）；
返回 `verilog_path / log_path / module_count`。

已知噪声：`ihdl` 画的 pin 是 `basic/ipin|opin` 实例，导出里会出现 `ipin PIN0 ();` 这类行；
本版**原样导出 + warnings 提示**，不静默改写（干净网表由调用方过滤）。

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 归属（不在本包）

| 能力 | 归属 |
|---|---|
| view CRUD（OA 视图，如 schematic/symbol） | cellview |
| 文本视图（`text.v`）的建立与覆盖 | **本包例外**（cellview 建不了文本视图） |
| VerilogA（`text.veriloga`） | veriloga 包 |
| GDS 导入/导出 | layout（`layout.gds`） |
| 结构 connectivity / 端口 / 参数读回 | schematic（`schematic.read`） |
| 仿真编译 | spectre 包 |

## 3. 不在本版

- Verilog 独立语法检查（`xmvlog` 单独调用未验证，见 §5）；
- `import_pipeline` 一键编排、SRAM 自动识别、PG label / label restyle；
- SystemVerilog / VHDL（另有 `systemVerilogText` / `vhdl` 视图类型，不在本版）；
- 并发写同一 cell。

## 4. 真机事实（IC6.1.8，2026-09-21 实测）

1. Verilog 文本视图类型是 `text.v`（主文件 `verilog.v`），与 `text.veriloga` 同属文件式文本视图；
2. `ihdl` 是 ksh 包装器：裸跑缺 `libsasl2.so.2`（rc=127），必须带
   `LD_LIBRARY_PATH=<IC618>/tools.lnx86/lib/64bit/RHEL/RHEL8` 前缀；
3. `ihdl` **返回码不可信**：语法错误、参考库缺失、降级导入都是 rc=0；成功看 `357/372/345`，
   终态 `End of Logfile.`，失败 `VERILOGIN-547`（细节在 `xmvlog.log`）；
4. `ihdl` 会向 `-cdslib` 指定的文件**追加 DEFINE**（目标库未注册时还在 cwd 建同名库目录）→ 必须用按次副本；
5. `ihdl` 对 `.va` 报 `VERILOGIN-547`（`xmvlog` 不认 VerilogA）→ VerilogA 不走 ihdl；
6. 门级原语（`and`/`not`/…）在生成 schematic 时会在目标库产生 `and2`、`not` 之类 symbol-only cell
   （来自 Cadence `sample` 库模板；functional-only 路径待 §5 spike）；
7. 混合设计：Verilog 引用 analogLib/ahdlLib 单元要写进 `ref_lib_list` 且**按名连接**，
   否则 `VERILOGIN-127` 拒绝并降级 functional；
8. 导出走 `oa2verilog`（真机验证，Verilog-2001），需要能解析目标库的 `cds.lib`；
   SKILL 侧没有等价导出器（`schPinListToVerilog` 只生成模块壳）。

## 5. 决策记录（2026-09-21，已确认）

| # | 决策 |
|---|---|
| 1 | 包名 `verilog` / `8-verilog.md`，operation 前缀 `virtuoso.verilog.*` |
| 2 | VerilogA 拆出为独立包 `veriloga`（`11-veriloga.md`），本包只管结构 Verilog |
| 3 | 结构装码 = `import`（ihdl）；`structural_views` 默认 `4`（functional only），schematic 显式可选 |
| 4 | 文本视图装码 = `write`（只落盘）；不提供 `check_and_save`（Virtuoso 无 Verilog 解析器） |
| 5 | `export` 对 `ipin/opin` 噪声行原样导出 + warning，不静默改写 |
| 6 | 不提供 open/close 等 GUI 展示操作 |

## 6. 待验证（实现前需 spike）

1. `xmvlog` 能否独立做 Verilog 语法检查（决定是否给本包加只读 `check`）；
2. `ihdl` 的 `structural_views=4`（functional only）真机行为：是否仍 Checked-in symbol、functional 的
   端口与 `verilog.v` 内容如何回读（当前只有 1/5 的真机证据）。
