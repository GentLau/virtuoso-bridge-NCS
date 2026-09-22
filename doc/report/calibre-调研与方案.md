# Calibre 业务包调研（DRC / LVS / PEX）

> 日期：2026-09-22｜执行：上层业务包开发助手｜状态：**调研完成，待拍板**
> 关联：`spec/design-concepts/上层/1-上层.md`（业务包契约）、`spec/design-concepts/上层/7-spectre.md`（最接近的同类先例）、`spec/design-concepts/上层/4-layout.md`（GDS 出口）、`spec/design-concepts/总览/1-四层整体架构与接口.md` §4（五接口）
> 证据：本文 §2 的真机实跑记录 + `test/tb/artifacts/log-vblog` 工作目录下的探针输出

## 0. 结论摘要

1. **环境齐备**：真机（command/file role 同一台，`GLIS-DESKTOP`）上 Calibre `v2025.1_16.10`、
   节点锁定 license 文件、TSMC CRN65 的 DRC/LVS/RCX 三套 deck **全部到位**。
2. **三段流程已实跑通**（不是纸面推演）：DRC（1737 条规则、36 个结果）、
   LVS（产出 svdb/phdb/extracted netlist）、xRC（`-phdb` → `-pdb` 产出寄生参数库与网表）。
3. **技术路线可行且不需要新接口**：全部用 C（`run_command`）+ D（`download_file`）；
   S/U/G 在 PDR 流程里基本不用。
4. **但有 6 个硬缺口**（§5）：没有 Calibre 环境事实、没有 job 句柄（长任务形态缺失）、
   `rc/kind` 对"启动器"不可信、run dir 与 deck 改写无约定、**LVS 的 CDL 没有产出方**、
   license 争用对中层不可见。
5. **实现工作量的大头不在跑工具，而在"报告解析"**：DRC 结果 36 条 / `DRC.rep` 125 KB、
   LVS `INCORRECT` 差异点、PEX 8 条 warning —— agent 需要结构化摘要，而不是日志原文。
6. 建议 v1 = DRC + LVS + 结果解析（含 `run`/`status` 启动轮询形态）；PEX 链路已验通，
   作为 v2 落地（多一档 `-fmt` 与 PDB 目录下载策略）。

## 1. 真机事实（2026-09-22 实测）

| 项 | 值 |
|---|---|
| 工具 | `which calibre` → `/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre`；`calibre -version` → `Calibre v2025.1_16.10`（2025-01-02）、`Litho Libraries v2025.1_16.10` |
| 环境 | `MGC_HOME` = `CALIBRE_HOME` = 上述目录；`MGC_LIB_PATH=$MGC_HOME/lib`；`USE_CALIBRE_VCO=aok` |
| License | `MGLS_LICENSE_FILE=/opt/eda/mentor/license_memtor.dat`（653 513 B，节点锁定文件，**无 SERVER 行**）；其中 `INCREMENT calibredrc / calibrehlvs / calibreci / calibreadp …` 等 **19 条** calibre 特性，有效期至 2049-03-21，`HOSTID=ANY` |
| PDK | `/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre/`：`drc/calibre.drc`、`lvs/calibre.lvs`、`rcx/calibre.rcx`（776 KB）+ `rcx/rules`（20 MB）、`xcell`、`calview.cellmap`、`source.added`、三套都带 `DFM/` 目录 |
| 另一 PDK | `/opt/eda/PDK/smic40ll/…`（未细查） |
| 运行环境 | `ulimit -n = 1024` → Calibre 启动即警告 `Please increase descriptors limit for best performance (1024)`；`ulimit -u=63605`、`-l=65536` |
| SKILL 通道 | 直接 dispatch 仍可用（`execute_skill("1+2")` → 3）；8127 当时不可用，不影响验证 |

## 2. 三段流程的实跑记录

**准备**：把 deck 复制进 run dir（deck 里有相对 include，见 §5-D4），用 `sed` 改写占位符：

| deck | 占位符（原文） |
|---|---|
| DRC | `LAYOUT PATH "GDSFILENAME"` / `LAYOUT PRIMARY "TOPCELLNAME"` |
| LVS | `LAYOUT PATH "lvs_top.gds"` / `LAYOUT PRIMARY "lvs_top"` / `SOURCE PATH "lvs_top.cdl"` / `SOURCE PRIMARY "lvs_top"` |
| RCX | 与 LVS 相同的 4 处 + `MASK SVDB DIRECTORY "svdb" XRC` |

**DRC**（`/home/Gent/project/vblog/calibre_probe/drc_run`，输入 `lay_e2e.gds` 顶层 `lay_e2e`）：

```text
ulimit -n 65536; calibre -drc -hier -turbo 4 run_drc.cal     # rc=0, REAL TIME = 1 s
--- TOTAL RULECHECKS EXECUTED = 1737
--- TOTAL RESULTS GENERATED = 36 (36)
--- DRC RESULTS DATABASE FILE = DRC_RES.db (ASCII)
--- SUMMARY REPORT FILE = DRC.rep
产物：DRC.rep(124 948 B)、DRC_RES.db(7 587 B)、drc.log(3 548 444 B)、以及每个检查项一个 .rep/.density
```

**LVS**（`lvs_run`，输入 `ctle.gds` + `ctle.cdl`，顶层 `ctle`）：

```text
calibre -lvs -hier -turbo 4 run_lvs.cal                      # rc=0, ELAPSED TIME = 6 s
LVS completed. INCORRECT. See report file: lvs.rep           # 预期：这个 CDL 与版图不是同一版
--- XDB CROSS REFERENCE DATABASE = svdb/ctle.xdb
--- PERSISTENT HIERARCHICAL DATABASE(PHDB) = svdb/ctle.phdb  # ← PEX 的前置产物
--- SPICE NETLIST FILE = svdb/ctle.sp
--- WARNING: POWER, GROUND, LABELED or TEXT nets required by ERC operations do not exist
产物：lvs.rep(47 786 B)、lvs.rep.ext、svdb/{ctle.xdb,ctle.phdb,ctle.sp,ctle.dv,ctle.extf,ctle.lvsf}、calibre_erc.{db,sum}、lvs.log(1 464 585 B)
```

**PEX / xRC**（`rcx_run`，复用 LVS 的 `svdb`）：

```text
calibre -xrc -phdb -turbo 4 calibre.rcx                      # rc=0, 4 s（关键前置：xRC 类型 phdb）
calibre -xrc -pdb -rc calibre.rcx -turbo 4                   # rc=0, 3 s，xRC Errors = 0 / Warnings = 8
产物：svdb/CTLE.pdb/（寄生参数库）、svdb/ctle.pdsp、svdb/ctle.sp、svdb/ctle.pexf、svdb/ctle.dv
```

**踩坑原文**（第一次跳过了 `-xrc -phdb`，直接用 LVS 产出的 phdb）：

```text
FATAL ERROR: Restoration of HDB failed.  Phdb is not xRC type.
SVRF rule statement "MASK SVDB" must include "XRC" during phdb creation.
```

即：**LVS 阶段的 phdb ≠ xRC 可用的 phdb**，PEX 必须自己先跑一次 `-xrc -phdb`（或让 LVS deck 以
xRC 模式产 db）。这条必须写进 spec，否则每个实现都会踩一次。

## 3. 流程分解与接口映射

| 步骤 | 接口 | 说明 |
|---|---|---|
| 版图 → GDS | S（已实现：`virtuoso.layout.gds`）或 U | `src/pyapi/packages/layout.py:924 gds` / `:935 _gds_export`；也可由调用方提供 GDS |
| 原理图 → CDL（LVS source） | **缺** | 当前无 CDL 产出能力，见 §5-D8 |
| 规则 deck 准备 | C（+ 可能 U） | deck 通常已在服务器（PDK 路径）；自定义 deck 走 U |
| 启动 DRC / LVS / xRC | C | `calibre -drc/-lvs/-xrc …`；**长任务必须后台启动 + 轮询** |
| 轮询进度 | C | `pgrep` / 日志 tail / 产物是否出现（三重校验） |
| 结果取回 | D | summary/report 优先；`svdb`、`*.pdb/` 目录按需、有界 |
| 结果解析 | —（纯 Python） | DRC 违规分类计数、LVS 差异点、PEX warning —— 本包最大工作量 |
| 文档渲染/GUI | 不需要 | Calibre 的 RVE 是独立 GUI，不接 G 接口（本版不做） |

## 4. 推荐设计（业务操作草案）

沿用 spectre 包的组织方式（领域操作、不暴露低层文件形态）与"启动 + 查询"的长任务口径
（顶层任务等待池已被否决，结论就是这一形态）：

| 操作 | 形态 |
|---|---|
| `calibre.check_env` | 查 calibre 二进制/版本/许可可用性（探测式，见 §5-D6） |
| `calibre.drc` | `run` 语义：启动 DRC，返回 `job_id`（= run dir 名）+ 已确认启动的证据；可选 `blocking` |
| `calibre.lvs` | 同上，额外接 `gds` + `cdl` 两个输入与顶层名 |
| `calibre.pex` | 多阶段（`-phdb → -pdb → [fmt]`），同样 `run` 语义 |
| `calibre.status` | 轮询：`running / completed / failed` + 进度线索（日志尾、已产出的报告） |
| `calibre.read_results` | 解析 summary：DRC 分类计数/首批违规坐标、LVS 是否 match/差异点、PEX warning 列表 |
| `calibre.export` | 把指定产物（report/db/netlist）下载到客户端 artifact |

约束（与现有包一致）：只注入 `Middle`；每次调用原样透传 `token`；同步、无状态；
不 import `subprocess`/`socket`；主机与路径由中层路由。

## 5. 当前代码与设计的缺陷

### D1. 没有"外部工具"的通用角色/事实（设计）

五接口里 `run_spectre_command` 是**专用**接口，Spectre 的二进制来自
`query().roles["spectre"].bin`（`src/pyapi/packages/spectre.py:373 _spectre_facts`）；
Calibre 只能走通用 `run_command`，而 command role 没有任何"工具安装路径/环境"字段，
`query()` 返回的 5 个 role 全部 `bin=None`（实测）。

**影响**：包无法知道 calibre 在哪、用哪套环境；只能依赖登录 shell 的 PATH 恰好正确（本次实测确实正确）。
**建议**：要么给 config 段登记 `calibre` 环境（同 skillref 的做法），要么在 role 上加 `bin`/env 字段。

### D2. 长任务形态缺失（设计）

`run_command` 是**同步**调用（默认 30 s，上限 ~2.1e9 s），且每 token 有**串行 command 槽**
（`src/transport/middle.py:761`，非 parallel 时持锁 + 复用一个持久会话）。
一次真实 DRC 可能几十分钟到数小时：

- 前台跑 = 占线程 + 占串行槽 + 通道抖动即 `unknown-effect`（结果未知，spec 明示不可盲目重试）；
- 正确形态是"后台启动 → 轮询"，但**契约里没有 job 句柄**，每个包都要自己发明。

**实测支持**：`setsid nohup … &` 启动的进程**能跨调用存活**（探针：6 s 时 9 行、14 s 时 17 行，跨两次 `run_command`）。
**建议**：把"启动器 + 轮询 + 产物校验"固化成上层规范（可写在 Calibre spec 里作为该包的口径）。

### D3. `rc/kind` 对启动器不可信（代码/契约）

实测启动器返回 `rc=1, kind="path"`，`stderr` 为 `wc: log.txt: No such file or directory`——
原因是后台重定向文件在子进程 fork 后才创建，紧随其后的 `wc` 抢跑；而中层把任何
"no such file or directory" 诊断归类为 `kind=path`（`src/common/ssh.py:866-883`）。

**影响**：上层若按 `rc/kind` 判"启动成功"，会误判成路径不可见；反之也可能把真失败当成功。
AGENTS.md 里的"poll artifact + tail log"纪律正是为此，但**没有固化进契约**。
**建议**：Calibre 包一律"启动器自身零依赖（不 touch 日志）+ 三重校验（PID 文件、进程表、首份产物）"。

### D4. run dir 与 deck 相对 include 无约定（设计）

deck 里有 `INCLUDE ./DFM/dfm_device`（DRC/LVS/RCX 三套都有，行号一致），
而 `DFM/` 在 PDK 目录下。只复制 `calibre.lvs` 到 run dir 会在解析期失败。
当前 D/U 接口只说"按 role 根解析路径"，**没有 run dir 的建立/清理/命名约定**。
**建议**：spec 明确"run dir = 调用方给的 `run_dir`（role 相对或绝对）+ 包内 stage 规则"，
并规定 deck 必须**整目录 stage**（deck + DFM + rules/xcell/cellmap）。

### D5. deck 占位符改写没有安全机制（设计/代码）

三套 deck 都靠占位字符串（`GDSFILENAME`/`TOPCELLNAME`/`lvs_top.*`）指向输入；
必须在 run dir 生成改写副本（本次用 `sed`）。改写是**幂等性敏感**操作：
`rules` 20 MB、`LVS/RCX deck` 各 776 KB，误改会静默改变检查语义。
**建议**：spec 规定改写只允许作用于**声明过的占位行**（白名单），并保留原始 deck 的哈希作为证据。

### D6. license 检查没有通用手段（代码）

实测 `lmstat -c $MGLS_LICENSE_FILE -a` 直接失败：
`Error getting status: No SERVER lines in license file. (-13,66)` —— 因为这是**节点锁定文件**不是 server；
`calibre -version` 不检许可（能跑通）。Spectre 包有 `check_license` 可参照，但 Calibre 没有等价开关。
**建议**：`calibre.check_env` 用"最小 deck 起动探测"（几秒）+ 解析 `FATAL/ERROR` 与 license 关键字，
并把"许可不足"映射成可重试错误；或先向工具方确认 `calibre -licensing` 之类的专用开关。

### D7. 结果体量与形态（设计）

小设计就已经：`drc.log` 3.5 MB、`lvs.log` 1.5 MB、`DRC.rep` 125 KB、`svdb/` 目录多文件、
PEX 额外产 `*.pdb/` 目录。**D 接口 recursive 会把整个目录拉回来**，对大设计不可接受。
**建议**：默认只取 summary/report（白名单），日志只 `tail -n`（C）；
`svdb`/`pdb` 走显式 `export`（用户点名要才下载）。

### D8. LVS 的 CDL 没有产出方（跨包缺口）

全包集合里没有任何 CDL/HSPICE 网表产出能力：`maestro.export` 是**仿真结果**导出、
`schematic` 只有 read/write/check_and_save/screenshot、`netlist_import` 只有导入
（grep `cdl|hspice` 无命中）。LVS = 版图 vs 原理图，**缺一半输入**。
**建议**：要么由调用方提供 CDL（U 上传/服务器已有），要么补一个 `netlist.export`
（CDL/hspice 口径，走 `maestro`/`schematic` 的 netlister）。这条是 Calibre 包能否闭环的前提。

### D9. PEX 阶段顺序与产物校验（代码/文档）

实测证明：用 LVS 的 phdb 直接跑 `-xrc -pdb` 会 `FATAL ERROR: Phdb is not xRC type`；
必须先 `calibre -xrc -phdb`。规范里没有任何"阶段序列 + 阶段产物存在性校验"的表述。
**建议**：PEX 操作内固定三段并对每段产物做存在性+时间戳校验，失败时把工具原文返回给调用方。

### D10. 许可争用对中层不可见（设计）

Calibre 许可在 license 文件里是有限特性数；中层的三预算（线程/通道/单目标点）**不感知许可**。
多 token 并发跑 DRC 会互相抢 license，表现为随机失败（并且是"启动后失败"，不是立即失败）。
**建议**：Calibre 包 v1 用"每 token 单 PDR 任务"的软策略 + 把许可错误显式映射；
若要全局串行化，需要顶层/中层支持（属跨层变更，需 owner 决策）。

### D11. 环境差异未登记（代码）

`ulimit -n = 1024` 而 Calibre 要更大（启动即警告）；`MGC_HOME/CALIBRE_HOME/MGC_LIB_PATH/
USE_CALIBRE_VCO/MGLS_LICENSE_FILE` 全在登录 shell 的 env 里。Spectre 有 `VB_CADENCE_CSHRC`
这类显式机制，Calibre 没有对应物；`run_command` 的 shell 语义（是否 login shell、env 继承）
在 spec 里也没有针对 Calibre 的明确口径。
**建议**：包内启动器先 `ulimit -n 65536`，并在 spec 里写明环境来源（登录 shell 或 config 段）。

### D12. 结果"可读性"层完全缺失（实现量最大）

DRC 36 条结果、LVS `INCORRECT`、PEX 8 条 warning：agent 需要的是
"哪类违规、几条、首个坐标/层、LVS 差异点、warning 清单"，而不是 125 KB 报告正文。
现有包没有任何 report parser 先例（`netlist` skill 里的 `check_spectre_netlist.py` 是唯一近亲）。
**建议**：v1 就把 parser 作为交付物的一半，格式：`DRC.rep` 的规则级计数 + 首批违规坐标；
`lvs.rep` 的 match/差异摘要；`*.log` 的 warning/error 归类。

### D13. 结果目录固定名导致并发冲突（代码）

Calibre 在 **cwd** 下写 `DRC_RES.db`/`DRC.rep`（DRC）、`lvs.rep`/`svdb`（LVS）、
`svdb/*.pdb`（PEX），名字固定。多任务共用目录会互相覆盖。
**建议**：每个 job 一个独立 run dir（`<run_root>/<job_id>/`），job_id 由调用方给出或由包按
"可重建"规则生成（不能用随机且事后无法重建的路径 —— 上层 §5.3）。

### D14. 超时与"结果未知"的边界（契约/实现）

Calibre 的启动器可能派生大量子进程；中层的 timeout 语义是"客户端超时 ≠ 未投递"。
若把 DRC 放在前台调用里，超时后**无法判断是否还在跑**（`unknown-effect`）。
**建议**：同 D2 —— 一律后台 + 轮询，使每次调用都短于默认预算，超时只发生在轮询调用上（可重试）。

## 6. 待确认问题（给 spec / owner）

1. **Calibre 走哪个 role**：现挂在 command role（本次实测可行）；是否需要给 spectre role 扩义或新增 role？
2. **环境事实来源**：登录 shell 默认（现状）还是 config 段登记（如 skillref 那样）？
3. **job 句柄形态**：`run_dir` 由调用方给、还是包按 `job_id` 生成？谁负责清理？
4. **CDL 来源**：调用方上传，还是补 `netlist.export` 包（跨包依赖）？
5. **PEX 是否 v1**：链路已验通，但多两段调用与 `*.pdb/` 目录下载策略；建议 v2。
6. **许可策略**：单 token 单任务（包内软约束）是否可接受？是否需要顶层全局串行化？
7. **报告解析深度**：v1 只给计数+首批坐标，还是要完整违规清单/LVS 差异点逐条？

## 7. 下一步（建议）

1. 先写 spec：`spec/design-concepts/上层/12-calibre.md`（沿用 spectre 的组织方式 + 本文 §4 的操作表 +
   §5 的约束），把 D1–D14 里属于本包的写成硬口径；
2. spec 通过后实现 v1：`check_env` / `drc` / `lvs` / `status` / `read_results`，
   全部走 C+D，落地 §5-D3/D4/D5/D11 的启动器与 stage 规则；
3. 真机 TB：复用本文 §2 的三段命令作为基线（GDS 用 `lay_e2e.gds`，LVS 用 `ctle.gds`+`ctle.cdl`），
   断言"报告计数 + 产物存在 + 阶段序列"；
4. PEX 作为 v2，按 §2 的三段序列实现（含 `-xrc -phdb` 的硬前置）。

## 8. 证据索引

| 证据 | 位置 |
|---|---|
| 工具/环境/license | 本文 §1（真机 `which calibre`、`calibre -version`、`env`、`lmstat` 原文） |
| DRC 实跑 | `/home/Gent/project/vblog/calibre_probe/drc_run/{drc.log,DRC.rep,DRC_RES.db}` |
| LVS 实跑 | `/home/Gent/project/vblog/calibre_probe/lvs_run/{lvs.log,lvs.rep,svdb/}` |
| PEX 实跑 | `/home/Gent/project/vblog/calibre_probe/rcx_run/{pex_phdb.log,pex_pdb2.log,svdb/}` |
| 后台存活探针 | `/tmp/vb_bg_probe/loop.log`（另有探针脚本输出） |
| deck 关键行 | `drc/calibre.drc:178-180`、`lvs/calibre.lvs:793-801/3657/20751`、`rcx/calibre.rcx:793-801/20751-20767` |
| 布局 GDS 出口 | `src/pyapi/packages/layout.py:924 gds`（`_gds_export` 在 `:935`）、`:1077 _gds_import` |
| Spectre 同类先例 | `src/pyapi/packages/spectre.py:373 _spectre_facts`、`spec/design-concepts/上层/7-spectre.md` |
| 长任务口径 | `doc/report/需求-顶层任务等待池.md`（已否决；结论=启动+查询） |
