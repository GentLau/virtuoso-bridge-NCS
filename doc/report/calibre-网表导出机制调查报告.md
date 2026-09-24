# Calibre 网表导出机制调查报告（含 DRC/LVS/PEX 官方调用形态）

> 日期：2026-09-24｜调查：上层业务包开发助手 + 三个并行 subagent（Locke：官方用法对照 / Helmholtz：auCdl 根因 / Parfit：GUI 背后命令行）
> 范围：Calibre 侧“导出网表/跑 DRC-LVS-PEX”的官方机制，以及我们 `src/pyapi/packages/calibre.py` 与其差距
> 关联：`doc/report/calibre-可行性报告.md`、`doc/report/calibre-调研与方案.md`、`test/reports/第五轮-缺陷清单-上层.md`（P-069）
> 状态：**调查完成**（结论与配方均已真机验证；改造清单见 §5.3/§5.4，待另行排期实施）

## 0. 结论速览

| # | 结论 | 证据 |
|---|---|---|
| 1 | Calibre **不解析原理图**；它的“导出网表”是**驱动 Virtuoso 的 CDL Out / auCdl 净网器**（`si -batch -command netlist`），由 `calibre.skl` + socket + `cdlOutKeys` 完成 | 见 §2.1、§3.1 |
| 2 | Calibre 自带的网表能力是**格式转换**：V2LVS（Verilog→SPICE）、E2LVS（EDIF→SPICE）；LVS 源库只接受 SPICE / CNET | 见 §2.3 |
| 3 | 官方 “Export from source viewer” 背后命令（本机实测取得）是 `si <runDir> -batch -command netlist -cdslib <cds.lib>` | 见 §3.1 |
| 4 | CDL 导出有 **Digital（CDL Out/hnl）** 与 **Analog（auCdl）** 两种模式；本 PDK 走 **auCdl**（器件 CDF 挂 `tsmcCdlSubcktCall`） | 见 §2.2、§3.2 |
| 5 | 测试侧此前 6 个 `si` 变体失败，根因是**模式用错**（hnl 路 + auCdl 视图）；正确模式（Analog/auCdl）下 si 会自行加载 PDK context 并进入器件格式化阶段 | 见 §3.2 |
| 6 | `OSSHNL-411` 根因已定位：IC618 auCdl header `eval` 引用未初始化变量 **`checkCAPPERI`**；在 `si.env`/`.simrc` 注入 `checkCAPPERI = nil` 即成功导出**带器件行的 CDL** | 见 §6 |
| 7 | 早年的 comparator 全流程 LVS **不是** CDL 自动导出：源网表是手写/硬编码 CDL，Calibre 只做比对 | 见 §4 |
| 8 | Calibre GUI 的调用链是 **runset → `calibre -gui … -batch` → 自动生成 control file（`_<rules>_`，`INCLUDE` 原 deck 并覆盖路径）→ raw Calibre**；不存在 `calibre -drc … <runset>` 这种形态 | 见 §5.4 |

## 1. 背景

第五轮 P-069：含 PDK 器件的 cell 在 `si -batch`（auCdl/CDL Out）导出 CDL 时失败，
`calibre.lvs` 因为拿不到源网表只能到 `NOT COMPARED`。该缺陷此前被记为“环境/配方口径问题”，
2026-09-24 定为“业务包跑不通”立案。

本次调查要回答三件事：

1. Calibre 官方到底有没有“导出网表”的功能，机制是什么；
2. 官方 DRC / LVS / PEX 从 GUI 到命令行的真实形态是什么；
3. 我们 `calibre` 包要怎样改，才能“和 Calibre 官方用法一模一样”。

## 2. Calibre 官方机制

### 2.1 “Export from source viewer” 全链路

来源：`calbr_interactive_user`《Calibre Interactive Classic GUI User's Manual》：

- `Contain_NetlistExportInCadenceComposer`：netlist export 例程**使用 `si -batch` 把 schematic 翻成 CDL**；
  命令就是 `si -batch -command netlist`；Calibre Interactive 运行时会生成 `si.env`；用 auCdl 视图时还会读 `.simrc`
  （`cdlSimViewList`/`cdlSimStopList` 会覆盖 si.env，二者不一致会导致 netlisting 失败）。
- `Concept_SettingSocketConnectionsCadenceVirtuoso`：Virtuoso 加载 `calibre.skl` 后建立 TCP socket（默认 9189，
  否则在 5000–9999 找空闲口；`mgc_rve_globals->socket_number` 可查）。
- `General_MgcRveExportNetlistCmd`：`mgc_rve_export_netlist_cmd(libName cellName viewName fileName)`
  返回 Calibre Interactive 实际使用的网表导出命令串。
- `General_CalibreNetlistExportSetupDialogBoxInCadenceComposer`：Netlist Export Setup 对话框里的
  View name / Simulator（**cdl 或 auCdl**）/ View List / Stop List 等设置，保存后生成 `cdlOutKeys` SKILL 变量。

链路的完整形态：

```
Virtuoso 载入 calibre.skl → 建 socket
Calibre Interactive 连接该 socket（Design Tool Settings → Cadence (Virtuoso) → Connected）
勾选 Export from source viewer → Calibre 准备 cdlOutKeys → 调 mgc_rve_export_netlist_cmd()
→ 执行 si（见 §3.1 实测命令）→ 产出 SPICE/CDL 源网表
→ 源网表经 runset 的 `SOURCE SYSTEM/PATH/PRIMARY` 喂给 LVS（`-spice` 是版图提取网表，不是 source，见 §5.2）
```

### 2.2 CDL Out 的两种模式（Digital / Analog）

来源：`C:\Users\user\Desktop\doc\cdloutta\`（CDL Out Task Assistant, IC6.1.8）：

- `How_to_Set_the_Netlisting_Mode_`：`CDS_Netlisting_Mode` 取值 **Digital → CDL Out**、**Analog → auCdl**；
- `What_Do_I_Need_to_Run_auCdl_`：auCdl 需要 ① `CDS_Netlisting_Mode=Analog`；② 停止单元有 **auCdl 视图**；
  ③ 停止单元 CDF 的 auCdl simulator 上定义 **netlistProcedure**；可选 `.simrc` 定制；
- `How_to_Run_auCdl_from_Command-line_`：准备好 `si.env`、把 `cds.lib` 复制到 run 目录，然后 `si -batch -command netlist`；
- `How_to_Prepare_si.env_File_for_CDL_Out_` / `Sample_si.env_File`：CDL Out 的 si.env 样例（`simSimulator="cdl"`、
  `simViewList='("cdl" "schematic" "gate.sch" "symbol")` 等）；
- `Sample_Template_File`（对应 Cadence `samples/transUI/cdlOut.il`）：`cdlOutKeys` 的结构，例如
  `'simLibName "opus"`、`'simCellName "latch.cdl"`、`'simViewName "schematic"`、`'hnlNetlistFileName "netlist"`、
  `'simRunDir "."`、`'shortRES 2000.0`、`'resistorCheck "none"` …；
- `Commonly_Used_.simrc_Parameters`：`auCdlCDFPinCntrl`、`auCdlDefNetlistProc`（`ansCdlSubcktCall` / `ansCdlHnlPrintInst`）
  等 auCdl 常用 .simrc 参数。

本 PDK 走 Analog/auCdl：`tsmcN65/nch` CDF 的 simInfo 为
`auCdl (nil netlistProcedure tsmcCdlSubcktCall instParameters (l w m) componentName nch termOrder (D G S B) namePrefix "M")`，
器件有 `auCdl` 视图（属性只有 `instNamePrefix`），**没有** `hnlCDLParamList/hnlCDLFormatInst` 静态属性。

### 2.3 Calibre 自身的网表能力边界

来源：`calbr_ver_user`《Calibre Verification User's Manual》：

- `Concept_SourceDatabases`：LVS 源数据库只允许 **SPICE / CNET**；源文件必须由外部提供（`SOURCE PATH`）；
- `MGCChap_V2lvs` / `Concept_V2lvsOverview`：**V2LVS = Verilog 结构网表 → Calibre SPICE**（输入必须是 Verilog）；
- `Concept_E2lvsOverview`：**E2LVS = EDIF 结构网表 → SPICE**；
- xRC/PEX（`xrc_user`）：有“导出网表”能力，但那是**从版图提取寄生网表**（layout 侧），不是 LVS 的 source 侧。

结论：**Calibre 没有“从 Virtuoso 原理图产源网表”的功能**；该能力只存在于 Virtuoso 侧（CDL Out/auCdl），
Calibre Interactive 只是通过 socket/SKILL 接口把它封装成 GUI 动作。

## 3. 本环境实测（wsl-gent, 2026-09-24）

### 3.1 Calibre 官方接口 + 导出命令取得

在 vblog CIW 加载 Calibre SKILL 接口：

```skill
load("/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/lib/calibre.skl")  ; → t
isCallable('mgc_rve_export_netlist_cmd)  ; → t
```

按官方模板设置 `cdlOutKeys` 后调用：

```skill
mgc_rve_export_netlist_cmd("CMP_LIB" "inv2" "schematic" "/tmp/vb_mgc_inv2.cdl")
; → "si /tmp/vb_mgc_run/ -batch -command netlist -cdslib /home/Gent/.virtuoso-bridge/vblog/run/cds.lib"
```

这条就是 Calibre GUI “Export from source viewer” 背后真正执行的命令（GUI 负责先生成 `si.env`）。

### 3.2 auCdl 模式实跑：进入器件格式化后报 OSSHNL-411

用正确模式构造 `si.env`（`simSimulator="auCdl"`、`simViewList='("auCdl" "schematic")`、
`simStopList='("auCdl")`），run 目录放 `cds.lib`，执行：

```bash
cd <run_dir> && CDS_Netlisting_Mode=Analog si . -batch -command netlist -cdslib <run_dir>/cds.lib
```

观察：

- si 自行加载 PDK context：`Initializing from libInit.il for library tsmcN65...` +
  `tsmcN65Tool.cxt`、`tsmcN65.cxt`、`pcode1/pcode2.cxt`、`tsmcN65_updateCDFs.il` 等；
- 进入 `Running Artist Hierarchical Netlisting ...`；
- 随后：

```text
ERROR (OSSHNL-411): Stopping netlisting due to SKILL error while formatting devices. To bypass this
check, set the environment variable oss.core stopNetlistingOnFormatterError
```

- 只生成 `inv2.cdl.raw`（含 auCdl 表头）与 `ihnl/`、`map/`，**没有器件行**。

即：**此前“si -batch 缺 PDK 回调”的结论不完整**——正确模式下 si 会加载 PDK context，已走到器件格式化，
只差最后一步；该步根因与解法见 §6。

### 3.3 对照：OCEAN Spectre 网表导出可用

同一会话内（官方 OCEAN 接口）：

```skill
simulator('spectre) → design("CMP_LIB" "inv2" "schematic" "r") → createNetlist(?recreateAll t ?display nil)
; → /home/Gent/simulation/inv2/spectre/schematic/netlist/input.scs（2 器件、0 错误）
M5 (OUT IN VSS VSS) nch l=180.0n w=2u m=1 nf=1 sd=200n ad=3.5e-13 ...
```

`simulator('auCdl)` / `simulator('cdl)` 在 OCEAN 里均不可用（`asiGetSimulatorList` 只有 ams/hspiceD/spectre/UltraSim），
所以“OCEAN 直出 CDL”这条路不存在。

## 4. 与早年 comparator 记录的对照

（subagent Carson 的只读调查，2026-09-24）

- 早年 LVS 的源网表**不是** CDL Out/auCdl 产物：`inv2.cdl` 是脚本里**硬编码器件行**，
  `cmp.cdl`/`cmp_top.cdl` 是整段字面量，`cmp_top_full.cdl` 由 `cat` 拼接；
- bridge 只做仿真用 **Spectre** 网表导出（`client.schematic.export_netlist` → OCEAN `simulator+design+createNetlist`）
  与 Calibre 执行（`sed` 替换 runset 的 `SOURCE PATH` → `calibre -lvs -hier -turbo 4 <runset>`）；
- `inv2/cmp/cmp_top` 的 `lvs.rep` 均为 **CORRECT**。

结论：早年全流程能跑通**不能证明 auCdl 可用**，它绕过了 CDL 导出；与本报告的 auCdl 调查不矛盾。

## 5. 与 Calibre 官方用法的差距（Locke 调查回填）

> 证据：Calibre 手册（`C:\Users\user\Downloads\docs\docs\htmldocs`，v2022.2）+ Cadence CDL Out 文档
> （`C:\Users\user\Desktop\doc\cdloutta`，IC6.1.8）+ 本仓库实现（`src/pyapi/packages/calibre.py`、`_calibre_util.py`）。
> 注意：手册为 v2022.2、现场为 v2025.1_16.10，涉及版本差异的条目需用现场
> `calibre -help / -xrc -fmt -help` 复核。

### 5.1 官方命令行形态

> 先纠四个容易写错的点（Parfit 回填）：
> ① runset **不是** raw Calibre 的 rule file——raw Calibre 的最后一个参数是 rule file 或 GUI 生成的 **control file**，runset 只由 `calibre -gui … -batch` 读取；
> ② GUI **不改写原 deck**，而是生成 control file（`_<ruleFileName>_`），原 deck 被 `INCLUDE` 进去，control file 里的 `LAYOUT PATH/SOURCE PATH/MASK SVDB/PEX NETLIST` 覆盖原 deck；
> ③ LVS 的 `-spice` 是**版图抽取网表**的落点，不是 source CDL；source 由 control file 的 `SOURCE SYSTEM/PATH/PRIMARY` 指定；
> ④ PEX `-fmt` 的参数是 formatter **模式**（`-netmodel|-c|-r|-rc|-rcc|-adms|-all|-simple`），输出到底是 HSPICE/DSPF/SPEF/Spectre 由 `PEX NETLIST` 语句决定。

| 操作 | 官方形态 | 关键选项 |
|---|---|---|
| DRC | `calibre -drc [options] rule_file`；层次化 `calibre -drc -hier ... [-turbo [n] [-turbo_all]] rule_file` | `-turbo` 只列在 hierarchical usage；官方建议尽量省略 CPU 数（取许可允许的最大）；致命错误用非零退出码 + `$?` 判定 |
| LVS | `calibre -lvs [-hier|-flatten] [-spice <layout.sp>] [-hcell ...] [-xcell ...] [-turbo] rule_file` | `-hier` 只在 `-lvs` 下有效；flat 推荐 `-flatten`；`-turbo` 只加速层次提取，比较始终单线程 |
| LVS 的 `-spice` | 指定/生成**从版图提取出的 layout SPICE 网表**，用于 layout 侧比较与 xRC source-name PHDB | 不是 LVS 的 source/schematic CDL；xRC 要求路径与 `MASK SVDB DIRECTORY` 一致 |
| xRC/PEX | 三段：`calibre -xrc -phdb rules` → `calibre -xrc -pdb <mode> rules` → `calibre -xrc -fmt ... rules` | PDB 必须选 `-r|-c|-rc|-rcc|-adms`；`-fmt` 的**模式**是 `-c|-r|-rc|-rcc|-adms|-all|-simple`（默认 `-all`），具体 SPICE/HSPICE/SPECTRE/SPEF 输出格式由 rule file 的 `PEX Netlist` 语句决定 |

source 侧：Source DB 只接受 **SPICE / CNET**，由 `SOURCE SYSTEM` + `SOURCE PATH`（+ 可选 `SOURCE PRIMARY`）指定；
Verilog / EDIF 必须先经官方 `v2lvs` / `e2lvs` 转成 SPICE-like source。
另有官方 batch 形态：`calibre -gui -<drc|lvs|pex|...> -runset ... -batch`（runset 用 `*OPTION: value`），
control file 不承载 Export from viewer / runset env / trigger。

### 5.2 仓库现状与差距清单

| # | 差距 | 官方 | 我们 | 影响 |
|---|---|---|---|---|
| G1 (P0) | xRC formatter 参数映射错误 | `-fmt` 模式是 `-c/-r/-rc/-rcc/-adms/-all/-simple`；输出格式由 deck 的 `PEX Netlist` 决定 | `fmt ∈ {none, spice, simple}`，拼成 `-xrc -fmt spice/simple` | `spice` 不在官方模式表；`simple` 应为 `-simple`；默认 `none` 直接跳过 formatter |
| G2 (P1) | PDB 模式硬编码 `-rc` | 五选一 `-r/-c/-rc/-rcc/-adms`（另有接地/耦合控制） | 固定 `-pdb -rc`；`power/ground` 字段只校验不使用 | 无法表达纯 R/C/耦合/ADMS 模式，伪接口误导调用方 |
| G3 (P1) | PEX 强制依赖 LVS run dir | layout-only PHDB 可直接 `calibre -xrc -phdb`；source-based PHDB 才需要 LVS 产物 | `pex()` 强制 `lvs_run_dir` 并复制 `svdb` | 无 source netlist 时无法独立做 layout PEX；复制旧 SVDB 有 stale 风险 |
| G4 (P1) | 无 `-spice`/layout netlist 支持 | `-spice` 可单独提取 layout netlist，也可与 `-lvs -hier` 联用 | LVS argv 固定 `-lvs -hier -turbo deck` | 无法复用/预生成 layout netlist，xRC source-name 语义受限 |
| G5 (P0) | Source 侧无 SVRF 校验 | 必须解析 `SOURCE SYSTEM/PATH/PRIMARY` | 仅白名单字面量替换，替换 0 次也继续；`top` 同时充当 layout/source top | 可能静默用错 source；source top 与 layout top 不同名的流程无法表达 |
| G6 (P0) | 未校验 `LVS INJECT LOGIC` / `MASK SVDB ... XRC` | `LVS INJECT LOGIC` 默认 YES，且与 xRC 有兼容性限制 | 不解析，LVS/PEX 共用同一改写流程 | 可能把 LVS 产物当 PEX 前置（仓库已实测 `Phdb is not xRC type`） |
| G7 (P1) | 层次控制只有一个 `hier` bool | `-hier/-flatten`、`-hcell`、`-xcell`、`-incontext/-full`、`-corner` | 只有 `hier: bool`；flat 也带 `-turbo` | 大设计无法控制 cell correspondence；flat 语义不完整 |
| G8 (P1) | 未用官方 runset/Interactive batch | `calibre -gui -app -runset ... -batch` + `-runset_options_display` 审计 | 自建直接 CLI + bash launcher | 无法复用官方 runset、无法审计 runset 对 deck 的覆盖、无法走 viewer export |
| G9 (P1) | 业务包无 source viewer export | `calibre.skl` + socket + `cdlOutKeys` + `mgc_rve_export_netlist_cmd` + `si` | 只在测试脚本里手写 `si.env/.simrc`；`lvs_from_schematic_tb.py` 直接手写 CDL | schematic→LVS 未闭环；手写路径缺继承连接/CDF/黑盒/全局信号语义 |
| G10 (P0) | Digital/Analog 模式混用 | Digital→CDL Out（需 `hnlCDL*` 属性）；Analog→auCdl（需 auCdl view + CDF netlistProcedure）；`.simrc` 的 `cdlSimViewList/cdlSimStopList` 会覆盖 si.env | 测试脚本写 `simSimulator="cdl"` 却套 auCdl `.simrc`；探针注释也把 cdl 当 auCdl | 可能只产出端口级/空器件网表 → LVS `NOT COMPARED`（P-069 根因之一） |
| G11 (P0) | 状态判定靠日志字串，不存进程 rc | 官方用非零退出码判 fatal；xRC errors 会 invalidate results | launcher 不记录 `$?`；`job_state` 靠 `FATAL ERROR/ERROR:/FAILED` 字串 + artifacts；PEX errors>0 仍可能 `ok`；非阻塞在进程未确认时也回 `ok(status=unknown)` | 误判 unknown / 漏错 / 把有 errors 的 PEX 当可用结果 |
| G12 (P2) | License/线程选项未暴露 | `-nowait/-wait n/-lmretry/-lmconfig/-turbo_all` | argv 无这些选项；`check_env` 只跑 `calibre -version`（官方说明它只显示版本） | 许可不足时排队到超时或多线程静默降级 |
| G13 (P2) | 无 V2LVS/E2LVS 适配 | Verilog/EDIF 先经官方 translator | `calibre.lvs` 只收一个字符串 `cdl`，不区分格式 | 数字 source 无法直接接入，也缺格式一致性证据 |

### 5.3 “与官方一致”的最小改造优先级（Locke 建议）

**P0（会静默给错结果的契约）**

1. 重做 xRC formatter 参数：引入 `fmt_mode` 映射官方 7 个模式，禁止 `-fmt spice`；输出格式改成读/覆盖 deck 的 `PEX Netlist`；
2. 加 SVRF preflight：解析 `SOURCE SYSTEM/PATH/PRIMARY`、`MASK SVDB ... XRC`、`LVS INJECT LOGIC`；拆分 `layout_top` 与 `source_top`；改写后断言每类语句恰好替换一次；
3. 进程 rc 进状态机：launcher 每段写 rc，`job_state` 优先看 rc、日志尾部兜底；PEX errors>0 明确失败；
4. 统一 Digital/Analog 模式并预检 view/CDF（Analog 要求 auCdl view + CDF netlistProcedure；Digital 要求 primitive `hnlCDL*` 属性；禁止 `simSimulator=cdl` 配 Analog `.simrc`）。

**P1（补齐官方主工作流）**：PEX standalone + `-spice`；层次/提取选项（`hier|flatten`、`hcell`、`xcell`、`incontext/full`、`pdb_mode`、`corner`）；官方 source export（`calibre.skl + cdlOutKeys + mgc_rve_export_netlist_cmd`）或明确“source 由外部提供”；runset/control-file 入口。

**P2（长期一致性）**：License/线程策略参数；V2LVS/E2LVS 适配与 source format 证据链。

> 结论：现有直接 CLI 基线与官方最基础形态接近、PEX 三段顺序正确，但**还达不到“官方一致”**；
> 最严重的是 `-xrc -fmt` 映射、source/SVRF 无校验、PEX 强依赖 LVS 且无 `-spice`、
> source viewer export 未进业务包、状态判定靠日志字串。

### 5.4 GUI 背后的命令行与 runset / control file（Parfit 回填）

**Batch 入口**（runset 必需）：

```bash
calibre -gui -drc -runset_options_display <drc.runset> -batch
calibre -gui -lvs -runset <lvs.runset> -batch
calibre -gui -pex -runset <pex.runset> -batch
```

runset 是 `*<variable>: <value>` 文本（前缀 `drc*`/`lvs*`/`pex*`/`cmn*`）；GUI 读 runset → 生成 control file
（`_<ruleFileName>_`，含 `INCLUDE "<原 deck>"`）→ 调 raw Calibre，control file 充当最后的 rule_file 参数。
control file **不包含** viewer export / runset 环境变量 / OpenAccess-LEFDEF read options / trigger，这些要单独处理。

**GUI 等价命令行模板**（`<CTRL>` = `_<rules>_`）：

```bash
# DRC（hier / flat）
calibre -drc -hier [-turbo [N]] [-turbo_all] [-hyper] [-nowait|-wait <min>] <CTRL>
calibre -drc <CTRL>

# LVS（hier / flat / source-name PHDB）
calibre -lvs -hier [-hcell <hcells>] [-nowait|-wait <min>] [-turbo [N] [-turbo_all]] <CTRL>
calibre -lvs -flatten <CTRL>
calibre -lvs -hier -spice <SVDB>/<layout_primary>.sp [-hcell <hcells>] [-turbo [N]] <CTRL>

# PEX 三段
calibre -xrc -phdb [-turbo [N]] [-hcell <hcells>] <CTRL>            # layout names
calibre -xrc -pdb {-r|-c|-rc|-rcc|-adms} [-turbo [N]] [-xcell <x> [-incontext|-full]] <CTRL>
calibre -xrc -fmt {-netmodel|-c|-r|-rc|-rcc|-adms|-all|-simple} [-corner ...] <CTRL>
```

**runset 关键字段**：DRC `drcRulesFile/drcRunDir/drcLayoutSystem/drcLayoutPaths/drcLayoutPrimary`；
LVS 再加 `lvsSourceSystem/lvsSourcePath/lvsSourcePrimary/lvsUseHCells/lvsHCellsFile/lvsSpiceFile/lvsSVDBDir`；
PEX 再加 `pexPexNetlistType`（PDB 模式）、`pexPexNetlistFormat`（输出格式）、`pexPexNetlistFile`、
`pexPexNetlistNameSource`、`pexRunPHDBStep/pexRunPDBStep/pexRunFMTStep`（默认全 1，可复用已有 PHDB/PDB，只重跑 formatter）。

映射要点：`-turbo` 必须与 `-hier` 联用、官方建议省略 CPU 数让 Calibre 取许可允许的最大值；`-nowait` 是许可排队语义，
不是“后台运行”；`MASK SVDB DIRECTORY ... XRC` 与 `LVS INJECT LOGIC` 共同决定 PHDB 能否被 PEX 复用
（未显式 `LVS INJECT LOGIC YES` 时 XRC 会置为 NO，这就是 `Phdb is not xRC type` 的来源）。

**对我们包的直接影响**（补充 §5.2）：

- 应改为 **runset + `calibre -gui -app -batch`**（或生成 control file 走 raw Calibre），不要再全局改写原 deck；
- `_run()` 当前对 run_dir `rm -rf` 有破坏调用方目录的风险，应改为唯一 job 目录 + 显式复用；
- source netlist 统一通过 `SOURCE PATH`（多文件时生成 `_source.net_` wrapper）传入；
- PEX step 开关（PHDB/PDB/FMT）应显式暴露，支持复用与只重跑 formatter。

## 6. OSSHNL-411 根因与可用配方（Helmholtz 真机调查）

### 6.1 根因

不是 PDK CDF、不是 `tsmcCdlSubcktCall`、不是 top cell 缺 `auCdl/config` 视图。
IC618 的 auCdl formatter 在 `hnlPrintNetlistHeader` 中 `eval` 变量 **`checkCAPPERI`**，
而该变量既不在 `si.env`、也没有默认绑定（Cadence 自带 `Sample_si.env_File` 未列、`tools/dfii/etc/tools/auCdl/.cdsenv` 无默认值）；
异常被 OSS netlister 吞掉后表现为 `OSSHNL-411`。捕获到的原始错误：

```lisp
("eval" 0 t nil ("*Error* eval: unbound variable" checkCAPPERI))
```

证据：包装 `hnlPrintNetlistHeader` 后 `errset` 捕到上述错误；`tsmcCdlSubcktCall` 根本没被调用（失败在实例遍历之前）。
对照实验：直接用 PDK 自带停止单元 `tsmcN65/nch/auCdl` 作 top，不设 `checkCAPPERI` 同样失败，设置后成功。

`oss.core stopNetlistingOnFormatterError=nil` 只隐藏 `OSSHNL-411`，仍 RC=255、无器件行，**不能当修复**。

### 6.2 最小可用配方（已复现）

`si.env`：`simLibName/simCellName/simViewName/hnlNetlistFileName/simRunDir` +
`simSimulator="auCdl"`、`simViewList='("auCdl" "schematic")`、`simStopList='("auCdl")` 等（见 §3.2）；
**`.simrc` 只需一行**：

```lisp
checkCAPPERI = nil      ; 或 t：额外输出 *.CAPPERI 命令
```

运行（run 目录放 `cds.lib`）：

```bash
CDS_Netlisting_Mode=Analog si . -batch -command netlist -cdslib "$PWD/cds.lib"
```

结果（RC=0，`…-29-pure-simrc-onevar/`、`…-30-pure-sienv-onevar/` 两个实验目录产物 sha256 一致）：

```spectre
.SUBCKT inv2 IN OUT VDD VSS
MM5 OUT IN VSS VSS nch l=180.0n w=2u m=1
MM6 OUT IN VDD VDD pch l=180.0n w=8u m=1
.ENDS
```

`checkCAPPERI` 放 `si.env` 或 `.simrc` 均可；`t` 语义已用 `…-31-…checkCAPPERI-t/` 验证。

### 6.3 结论

- **官方 auCdl/CDL 导出在本环境已可产出带器件行的 CDL**，无需改 PDK/CDF，也不需要 `auCdlDefNetlistProc`/`auCdlCDFPinCntrl` 额外设置；
- 上层只需在生成/投递 `si.env`（或 `.simrc`）时固定注入 `checkCAPPERI = nil`，并记录该 IC618 默认值缺口。

## 7. 建议（初步）

1. **源网表导出**：把 Calibre 官方链路（`calibre.skl` + `cdlOutKeys` + `mgc_rve_export_netlist_cmd` → `si`）
   作为目标形态；`checkCAPPERI = nil` 已定位并验证（§6），可作为该链路的前置注入；
   已闭环的 B' 路线（OCEAN Spectre 网表 + 确定性文本转换）保留为兜底与对照。
2. **DRC/LVS/PEX 调用**：改为 **runset + `calibre -gui -app -runset … -batch`**（或按 §5.4 生成 control file 走 raw Calibre），
   原 deck 只 `INCLUDE`、不再全局改写；source 走 `SOURCE SYSTEM/PATH/PRIMARY`；`-spice` 只用于版图抽取网表；
   PEX 拆出 `pdb_mode`/`fmt_mode`/step 开关并写 `PEX NETLIST` 输出格式；launcher 记录每段 rc。
3. **spec/文档**：`spec/design-concepts/上层/12-calibre.md` 的“验收/不做”部分需要按官方机制更新
   （例如明确 source netlist 的两条官方来源：调用方提供 / Calibre 官方导出链路）。

## 8. 落地 реализации（2026-09-24，上层）

调查结论已落成业务操作 `calibre.export_cdl`（`src/pyapi/packages/calibre.py`，spec `上层/12-calibre.md §4.6`）：

| 项 | 值 |
|---|---|
| si.env | `simSimulator="auCdl"`、`simViewList='("auCdl" "schematic")`、`simStopList='("auCdl")`、`hnlNetlistFileName=<cell>.cdl`、**`checkCAPPERI = nil`** |
| .simrc | 同样注入 `checkCAPPERI = nil`（两处任一即可，双保险） |
| cds.lib | 默认取 CIW `getWorkingDir()/cds.lib`（`si` 需要），可显式 `cds_lib` 覆盖；复制进 run dir，不改调用方文件 |
| 命令 | `CDS_Netlisting_Mode=Analog si . -batch -command netlist -cdslib <run_dir>/cds.lib` |
| 判定 | rc=0 **且**产物非空；失败回带 si.log 尾 |
| 返回 | `{run_dir, netlist_path, netlist_name, bytes, cds_lib, log_path}` |

真机实测（token `vb-vblog`，wsl-gent，direct dispatch）：

- `CMP_LIB/inv2` → 680 B，含 `.SUBCKT inv2 IN OUT VDD VSS` + `MM5/MM6` 器件行（`nch/pch`）；
- `CMP_LIB/cmp`、`CMP_LIB/cmp_top`（层次）→ 各 1166/1476 B，子电路实例为 auCdl 形态 `XI0 … / inv2`；
- **闭环**：`export_cdl(CMP_LIB/inv2)` 的 CDL + `/home/Gent/project/test/inv2.gds` 喂 `calibre.lvs`
  → `status=completed`，`read_results.summary.status = correct`（P-069 的"源网表从哪来"在业务包侧闭环）。

## 9. runset / control-file 实测（推翻 §5.4 的一处假设）

对"我们不接 runset，参数怎么改"这个问题做了三组真机对照（PDK deck `/opt/eda/.../Calibre/lvs/calibre.lvs`）：

| # | control file 形态 | 结果 |
|---|---|---|
| 1 | `INCLUDE <deck>` + `LAYOUT PATH/SOURCE PATH`（GUI 文档的"control file 优先"形态） | **覆盖不生效**：仍找 deck 的 `lvs_top.cdl`（`Can not open source netlist file lvs_top.cdl`） |
| 2 | 同上，再补 `LAYOUT PRIMARY` | `SPC1 … superfluous specification statement: layout primary` |
| 3 | 覆盖行放在 `INCLUDE` **之前** | deck 自己的 `LAYOUT PRIMARY` 变成 superfluous → 同样报错 |

结论：Calibre 的 **specification 语句是 first-wins**（手册明确："only the first statement is used and the rest are ignored"，
见 `calbr_lvl_fdi_gd/…/General_ErrorWarningMessages` 的 SPC1 条目）。GUI 文档说的 "control file takes precedence"
对本 PDK deck 不成立——deck 里 `lvs_top.*` 先出现就赢。

**因此本包自己实现"runset 生效"（不走 GUI）**：既然覆盖行只能改在 deck 里、改在第一条上，
那就由我们把参数**原位写进 deck 的第一条同名语句**（缺失才追加），行为即 GUI 的合并结果：

- `params={"lvsLayoutPrimary": "inv2", "lvsSourcePath": "/x/inv2.cdl", …}`（runset 键，见下表）；
- 或 `runset=<远端 .runset 文件路径>`（Calibre Interactive 的 `*key: value` 文本，按同一张表翻译）；
- 键也可直接写 SVRF 语句头（含空格，如 `"LAYOUT PRIMARY"`）作转义舱，值给整条语句；
- 表外/未知键 → 结构化失败并列出支持的键（不静默忽略）；每处改动记进 `deck_changes` 供审计；
- deck 里没占位符（自包含）时 `gds/top/cdl` 全部可省（步骤记 `self_contained: true`）。

支持键 → SVRF 语句：`drcLayoutPaths`/`lvsLayoutPaths`→`LAYOUT PATH`；`drcLayoutPrimary`/`lvsLayoutPrimary`→`LAYOUT PRIMARY`；
`drcLayoutSystem`→`LAYOUT SYSTEM`；`lvsSourcePath`/`lvsSourcePrimary`/`lvsSourceSystem`→`SOURCE PATH/PRIMARY/SYSTEM`；
`lvsSVDBDir`→`MASK SVDB DIRECTORY "…" QUERY`。

真机验证（token `vb-vblog`，2026-09-24）：同一份 PDK deck 不拷贝、不修改，
`params` 内联与 `.runset` 文件两种形态各跑一次 LVS（`inv2.gds` + `export_cdl` 的 CDL）→ **两次都是 `correct`**；
`params={"lvsNotAThing":"1"}` → 明确失败并回带支持的键。

## 10. 同批修掉的两个上层问题

- `_LICENSE_HINTS` 过宽：Calibre 日志头固定含 "SUBJECT TO LICENSE TERMS"、启动也会打 "(pending licensing)"，
  原实现把这些当线索 → control file 语法错被误报 `failure_kind=license`（真机复现）。
  已收紧为"cannot checkout / failed to check out / license request failed / mgcld …"。
- `run_dir` 落在 deck 目录之内时 `cp -r` 会自我递归（真机复现：`cp: cannot copy a directory into itself`）：
  现在前置拒绝并提示换目录（顺带避免 `rm -rf` 波及调用方 deck 目录）。
