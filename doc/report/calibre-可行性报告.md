# Calibre 业务包可行性报告（DRC / LVS / PEX + CDL 来源）

> 日期：2026-09-22｜执行：上层业务包开发助手｜状态：**调查完成，附未闭环项**
> 关联：`doc/report/calibre-调研与方案.md`（第一轮方案）、`spec/design-concepts/上层/7-spectre.md`（同类先例）
> 约束（用户给定）：① Calibre 走 **command role**；② **不改 cds.lib** 等共享配置，需要 env 就在 run dir 里自建；
> ③ 尽量解耦（上层包 = 插件）；④ 用 **65 工艺**（40 工艺可能有问题）；⑤ DRC/LVS/PEX **全量支持**

## 0. 结论速览

| 能力 | 结论 | 证据 |
|---|---|---|
| **DRC** | ✅ 可行，已真机跑通 | `calibre -drc -hier -turbo 4`：1737 条规则、36 个结果、`DRC.rep`+`DRC_RES.db` |
| **LVS** | ✅ 可行，已真机跑通（输入 CDL 由调用方给） | `calibre -lvs -hier`：产出 `lvs.rep`、`svdb/{xdb,phdb,sp}` |
| **PEX** | ✅ 可行，已真机跑通两段（`-phdb` → `-pdb`） | `svdb/CTLE.pdb/`、`ctle.pdsp/ctle.sp`，xRC Errors=0 |
| **CDL（LVS 源网表）· 调用方提供** | ✅ 可行（当前唯一已验证的可用路径） | 上面的 LVS 实跑用的就是 `ctle.cdl` |
| **CDL · 从 schematic 自动产出** | ⚠️ **Virtuoso 外不可行**；Virtuoso 内可行但需前置条件（见 §3） | 三种失败模式原文见 §3.2 |
| 解耦（不改共享配置） | ✅ 已按 run-dir 自建 env 方式实现 | §4：全部 env 落在 run dir |

## 1. 环境事实（65 工艺，`wsl-gent` / `GLIS-DESKTOP`）

```text
calibre            /opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre   (v2025.1_16.10)
MGC_HOME/CALIBRE_HOME = 上述目录；USE_CALIBRE_VCO=aok；MGC_LIB_PATH=$MGC_HOME/lib
MGLS_LICENSE_FILE  /opt/eda/mentor/license_memtor.dat（653 513 B，节点锁定文件，无 SERVER 行）
                   INCREMENT calibredrc / calibrehlvs / calibreci / calibreadp … 共 19 条，有效期 2049-03-21
PDK(65)            /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/
                   ├─ Calibre/{drc,lvs,rcx}   ← 三套 deck（rcx/rules 20 MB、xcell、calview.cellmap、source.added、DFM/）
                   ├─ tsmcN65/                ← OA 器件库（nch/pch/rppoly/mimcap…，每个器件有 auCdl/auLvs/hspiceD/spectre/symbol 视图）
                   └─ skill/{tsmcN65Tool.cxt,pcode1.cxt,pcode2.cxt}（PDK 的 SKILL context）
进程环境            ulimit -n=1024（Calibre 启动即警告要更大）；登录 shell 已带 PATH/MGC_* 
```

注：`/opt/eda/PDK/smic40ll`（40 工艺）**本次未使用**（按指示避开，且其规则面已见 `icc.rules` 等非 Calibre 产物）。

## 2. DRC / LVS / PEX 实跑记录（65 工艺）

前置（**全部在 run dir 内完成，不碰共享配置**）：

```bash
R=<run dir>; mkdir -p $R/DFM
cp <PDK>/Calibre/<drc|lvs|rcx>/… $R/          # deck 整目录（含相对 include 的 DFM/）
sed -i 's|"GDSFILENAME"|"<gds>"|; s|"TOPCELLNAME"|"<top>"|' $R/run_drc.cal
ulimit -n 65536                               # Calibre 要更大 fd 上限
```

```text
DRC : calibre -drc -hier -turbo 4 run_drc.cal           → rc=0；1737 规则 / 36 结果 / REAL 1 s
      产物 DRC.rep(124 948 B)、DRC_RES.db(ASCII, 7 587 B)、drc.log(3.5 MB)
LVS : calibre -lvs -hier -turbo 4 run_lvs.cal           → rc=0；"INCORRECT"（CDL 与版图不同版，属预期）
      产物 lvs.rep(47 786 B)、svdb/{ctle.xdb,ctle.phdb,ctle.sp,ctle.dv}、lvs.log(1.5 MB)
PEX : calibre -xrc -phdb -turbo 4 calibre.rcx           → rc=0（4 s；**必须先做，且 phdb 必须是 xRC 类型**）
      calibre -xrc -pdb -rc calibre.rcx -turbo 4        → rc=0，xRC Errors=0 / Warnings=8（3 s）
      产物 svdb/CTLE.pdb/、ctle.pdsp、ctle.sp、ctle.pexf
```

**踩坑（已固化）**：
1. 直接用 LVS 产出的 phdb 跑 `-xrc -pdb` → `FATAL ERROR: Restoration of HDB failed. Phdb is not xRC type.
   SVRF rule statement "MASK SVDB" must include "XRC" during phdb creation.` ⇒ PEX 必须自带 `-xrc -phdb` 阶段。
2. deck 有 `INCLUDE ./DFM/dfm_device`（DRC/LVS/RCX 三套同款）⇒ 只拷 deck 单文件会在解析期失败。
3. 后台启动器返回过 `rc=1 kind="path"`（子进程重定向文件尚未创建时 `wc` 抢跑，中层把 "No such file" 归类为 path）
   ⇒ **启动器的 rc/kind 不可信**，必须 PID + 日志尾 + 产物三重校验（`setsid nohup … &` 跨调用存活已验证）。

## 3. CDL（LVS 源网表）专项调查

### 3.1 机制与官方口径（IC6.1.8 自带文档）

| 路线 | 命令/API | 说明 |
|---|---|---|
| CDL Out（GUI） | File → Export → CDL（Top Cell / Library / Netlisting Mode=Analog） | 交互式；会在 run dir 生成 `si.env` |
| CDL Out（批处理） | run dir 放 `cds.lib` + `si.env`，`CDS_Netlisting_Mode=Analog si -batch -command netlist` | 官方要求"先交互式生成 si.env"，**实测手写等价字段即可** |
| SE 变量 | `simLibName/simCellName/simViewName/simSimulator/simViewList/simStopList/simRunDir`…（`simPrintEnvironment()` 写 si.env） | `simStopList` 是**一等变量**（默认 `'("auCdl")`），我第一轮缺它导致下钻报错 |
| 器件行来源 | **CDF netlist procedure = `ansCdlCompPrim`**（`maeSKILLref/chap3`） | 需要 PDK 的 CDF 挂该 procedure；`ansCdl*` 只在加载了 PDK/ADE context 的进程里存在 |
| Virtuoso 内 API | OCEAN `design(lib cell view)` + `createNetlist(?recreateAll t ?display nil)`；ADE 侧 `asiNetlist(session)`（内部调用）、`asiSetNetlistOption` | 老工程 `schematic/netlist.py:154` 用的就是 `createNetlist` |

### 3.2 三种失败模式（都是我实跑出来的原文）

```text
① 缺 stop list（view list 含 symbol）：
   WARNING (OSSHNL-117): Ignoring switch view 'symbol' of cell 'res' … it does not contain any instance.
   → 顶层 subckt 只剩端口，器件全部丢失

② stop list 生效但器件无 CDL 属性（Virtuoso 外跑 si -batch，analogLib 与 tsmcN65 器件都报）：
   Failed to netlist because the hnlCDLParamList property for hierarchical cellview 'nch' is not defined.
   Failed to find 'hnlCDLFormatInst' property for element 'nch' …
   ERROR (OSSHNL-514): Netlist generation failed

③ 换 spectre 网表器（Virtuoso 外）：
   *Error* skill: undefined function - ancNetlistFileInstOutput
   *Error* skill: undefined function - ancFnlPopHier / ancNetlistFileFooter
   si: Netlist did not complete successfully.
```

**根因**：`tsmcN65` 的器件 CDL 依赖 **PDK SKILL context（`skill/tsmcN65Tool.cxt` 等，内含 `ansCdl*`/`netlistProcedure`）+ CDF 更新脚本（`skill/tsmcN65_updateCDFs.il`、`tsmcN65/libInit.il`）**；
bare `si -batch` 是**独立进程**，没有这些回调（与老工程记录的 "`auCdl` export via `si -batch` does not work reliably outside Virtuoso (missing SKILL callbacks)" 完全一致）。
另外：**PDK 目录里 grep 不到 `hnlCDL*` 属性**（56 个 `hnlCDL*` 函数只在 Cadence 文档/`sktransrefOA` 里），进一步说明器件行是由 **CDF procedure** 现算的，而不是静态属性。

### 3.3 结论与两条可用路线

| 路线 | 可行性 | 前置 |
|---|---|---|
| **A. 调用方提供 CDL**（当前唯一已验证） | ✅ | 无（LVS 已跑通） |
| **B. 从 schematic 自动产 CDL（Virtuoso 内）** | ⚠️ 机制存在，未闭环 | ① 目标库 + `tsmcN65` 必须在**真实网表的那个 Virtuoso 会话**里可见（当前 vblog 会话只定义 `schemtest`/`maestro_tb`，`grep tsmc` = 0）；② 用 ADE/OCEAN API（`design()`+`createNetlist()` 或 `asiNetlist`），**不能**用 shell `si -batch`；③ 需要 PDK context/CDF 已按 PDK 安装说明初始化 |
| C. Spectre 网表 → 本地转 CDL | ⚠️ 未闭环（`anc*` 回调缺失同上） | 同样必须在 Virtuoso 内 netlist |
| D. 手写/脚本生成 CDL | ✅ 已用过（`ctle.cdl`） | 无 |

**建议**：v1 以 **A** 为准（明确"调用方提供 CDL"是合法输入）；**B** 作为 `netlist.export` 补包的实现路线，等"库可见性"这一部署前提落实后做真机验证。

## 4. 解耦与环境约束（按你的要求）

1. **不改共享配置**：全部 env 落在 run dir ——
   ```
   <run_dir>/
     cds.lib          # 本次运行自建（可 cp 自调用方指定库定义，或按需生成最小集）
     si.env           # 手写 SE 变量（simLibName/…/simSimulator/simViewList/simStopList/simRunDir）
     .simrc           # cdlSimViewList/cdlSimStopList/cdlNetlistType（CSF 搜索；或直接写进 si.env）
     run_*.cal|*.rcx  # deck 副本（占位符改写）
     DFM/             # deck 的相对 include 依赖
     job.json         # 启动器写：pid/命令/输入与 deck 哈希/起始时间（**包不写状态**）
     <tool>.log、report、svdb/、*.pdb/
   ```
2. 实测中出现的 `LIB analogLib … redefines` 警告来自"整份拷贝 cds.lib"，**推荐生成最小 cds.lib**（只 DEFINE 目标库 + INCLUDE PDK/安装默认库）以消除噪声。
3. 包内一切通过 C/D/U 接口操作；不 import `subprocess`/`socket`；主机与路径由中层路由决定（插件化）。

## 5. 对上层设计的约束（汇总）

| 项 | 结论 |
|---|---|
| role/接口 | Calibre 走 **command role**（C）；结果取回 D；输入（GDS/CDL/deck）U 或服务器既有路径 |
| 环境事实 | 注册表给 **command role 加字段**（建议 `command.calibre_bin` + `calibre_version`，探测方式对齐 `register/probe.py` 的 spectre 探测），并由 middle `query()` 暴露（现在 `bin` 只对 spectre 填值） |
| 长任务 | `run`（默认非阻塞返回 `job_id`）+ `status`（PID/日志/产物三判据）+ `read_results`；`blocking=true` 时内部轮询（形态抄 maestro `RunRequest.blocking/poll_interval/timeout`） |
| 范围 | **DRC + LVS + PEX 全量**（PEX 三阶段：`-xrc -phdb` → `-pdb -rc` → `-fmt`） |
| `read_results` | 复杂但易用：DRC 分类计数+首批坐标/层、LVS match/差异点、PEX warning 清单+产物清单；日志只 tail，不整文件回传 |
| 并发/许可 | 许可数有限且中层不感知；v1 用"每 token 单 PDR 任务"软约束 + 许可错误显式映射 |
| 输入缺口 | LVS 需 CDL：v1 = 调用方给；B 路线（netlist 补包）需先解决"PDK/库可见性" |

## 6. 未闭环项（下一步）

1. **B 路线真机验证**：需要目标库 + `tsmcN65` 在 netlisting 会话可见（新开 session 或注册表层面声明），然后在 CIW 内跑 `design()`+`createNetlist()`；当前会话不可见（`grep tsmc vblog/cds.lib` = 0）。
2. **PEX `-fmt` 阶段**：`-pdb` 已产出 `ctle.sp/.pdsp`；`-fmt`（`-simple`/`-spice`）语法已从工具 usage 抄到，尚未实跑。
3. **许可并发**：多 token 同时跑 DRC 时的许可争用行为未测（需真实许可紧张场景）。
4. **大设计体量**：本次都是小例子；`svdb`/`*.pdb/` 在大设计上的体积与下载策略待评估。
5. **40 工艺**：按指示未测；如需支持另行评估（其 PDK 结构不同，仅见 `icc.rules`）。

## 7. 证据索引

| 证据 | 位置 |
|---|---|
| DRC/LVS/PEX 实跑现场 | `/home/Gent/project/vblog/calibre_probe/{drc_run,lvs_run,rcx_run}/` |
| CDL 批处理现场 | `/home/Gent/project/vblog/calibre_probe/{cdl_run,cdl_gen_multi,cdl_rc_probe*,cdl_ctle*,*_spectre,v1_simStopList,…}/` |
| CDL 探针 | `test/tb/calibre_cdl_probe.py`（si.env/.simrc 生成 + si -batch 执行） |
| Calibre 环境探针 | `test/tb/calibre_env_probe.py`（`--facts` / `--stage drc\|lvs\|pex`） |
| PDK 支持面证据 | `tsmcN65/libInit.il`、`skill/tsmcN65Tool.cxt`（含 `ansCdl`/`netlistProcedure`）、`skill/tsmcN65_updateCDFs.il` |
| 官方文档（本机） | `/opt/eda/cadence/IC618/doc/cdloutta/`（CDL Out Task Assistant）、`$maeSKILLref/chap3`（`ansCdlCompPrim` 等）、`$oceanref/chap6`（`design`/`createNetlist`）、`$netlistsimulateref`（`simPrintEnvironment`） |
| 桌面文档副本 | `C:\Users\user\Desktop\doc\`（同源，可直接用 `_skillref_docs` 解析，本轮即如此查得 API） |
