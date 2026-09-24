# 上层业务包：calibre

> 版本：Draft v1
> 日期：2026-09-22
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无（新包；可行性见 `doc/report/calibre-可行性报告.md`）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)；长任务口径参照 [7-spectre.md](7-spectre.md) 与 maestro 的 `run`/`read_history`。

## 1. 总述

calibre 包覆盖 **物理验证三件套：DRC / LVS / PEX**，外加环境体检与结果读取。

设计目标按"用户（agent）易用"排序：

1. **一个动作一个操作**：`calibre.drc` / `calibre.lvs` / `calibre.pex`，用户只需给"版图 + 顶层名 + deck"，不必懂 deck 内部的占位符与相对 include；
2. **默认非阻塞 + 三件套**：run 类操作默认立即返回 `job_id`（Calibre 动辄几十分钟），用 `calibre.status` 看进度、`calibre.read_results` 拿结构化结论；需要阻塞时用 `blocking=true`（包内轮询，形态同 maestro）；
3. **结果要"能读"**：`read_results` 直接给分类计数（DRC 按规则条数、LVS 对象计数）、LVS match/差异点、PEX warning 清单，而不是让用户去啃 100 KB 报告；DRC 的前 N 条违规（规则名/bbox/cell）从 ASCII 的 `DRC_RES.db` 有界读取解析（layer 不在该文件中）；
4. **不碰共享配置**：所有运行期文件落在 run dir（deck 副本 + DFM、日志、报告、svdb/pdb），不改 `cds.lib`/PDK 配置，包是可插拔的插件；
5. **失败可定位**：错误带 `kind`、工具原文片段、run dir 路径；`unknown-effect` 一律不自动重试。

## 2. 业务操作

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| `calibre.check_env` | 环境体检：二进制/版本/许可/PDK deck 可见性 | C（`which`/`-version`/最小探测） | C |
| `calibre.drc` | 启动 DRC | stage deck → 改写占位符 → 后台启动 | C(+U) |
| `calibre.lvs` | 启动 LVS（版图 vs CDL） | 同上 + 源网表 | C(+U) |
| `calibre.pex` | 启动 PEX（`-xrc -phdb → -pdb → fmt`） | 三阶段串联，逐阶段校验产物 | C(+U) |
| `calibre.status` | 只读查询：作业状态与进度 | 读 `job.json` + 进程 + 日志尾 + 产物 | C |
| `calibre.read_results` | 解析结果（DRC/LVS/PEX） | 读报告 → 结构化摘要 | D + 纯 Python |
| `calibre.export` | 按名下载产物 | report / 结果库 / 网表 / pdb 目录 / 日志尾 | D |
| `calibre.export_cdl` | 从 schematic 导出 LVS 源网表（CDL），走 Virtuoso 官方 auCdl 机制 | 解析 cds.lib → 生成 `si.env`/`.simrc` → `si -batch -command netlist` → 校验产物 | S+C(+U) |

接口简写：S=`execute_skill`、C=`run_command`、U=`upload_file`、D=`download_file`、G=`run_gui_command`、Sp=`run_spectre_command`。
验证类操作（check_env/drc/lvs/pex/status/read_results/export）全部走 **command role**（C/D/U），不使用 S/G/Sp；
`export_cdl` 额外用一次 S（`getWorkingDir()` 解析 CIW 的 `cds.lib`），si 仍在 command role 执行
（因此该操作要求 command role 与 CIW 同主机，与 Calibre Interactive 在本机跑 `si` 的形态一致）。

## 3. 公共契约

### 3.1 作业与 run dir（确定性、可重建）

- 每个 run 类操作产生一个 **job**，标识 `job_id`；
- run dir 规则：请求给 `run_dir` 用请求值；否则用 `<command role root>/calibre/<job_id>`；
  `job_id` 默认 `<kind>_<top>`（如 `drc_inv2`），请求可显式指定；
- run dir 布局（全部在 run dir 内，**不改任何共享配置**）：

  ```
  <run_dir>/
    job.json          # 启动器写：kind/pid/命令/输入与 deck 哈希/起始时间（包只读）
    deck/             # deck 整目录副本（含 DFM/ 等相对 include 依赖）
    run_<kind>.cal    # 改写占位符后的可执行 deck
    inputs/           # gds / cdl 的软链或副本（按需）
    <kind>.log        # 工具完整日志（可用 export 取尾）
    DRC.rep / DRC_RES.db / lvs.rep / svdb/ / *.pdb/ …   # 工具产物，名字由工具决定
  ```

- **一致性**：同一 job 内所有步骤使用同一 run dir；重复用同一 `job_id` 时先检查是否已有 running 作业
  （有则业务失败，提示换 job_id 或先 `calibre.status`）。

### 3.2 deck 与占位符（用户不需要懂）

- 请求只给 `deck`（deck 文件路径，如 `.../Calibre/drc/calibre.drc`）；包把**整个 deck 目录**复制进
  `run_dir/deck/`（解决 `INCLUDE ./DFM/dfm_device` 这类相对依赖）；
- 包在 `run_dir/run_<kind>.cal` 上做**白名单占位符改写**（只改声明过的行）：
  `"GDSFILENAME"→gds`、`"TOPCELLNAME"→top`、`"lvs_top.gds"→gds`、`"lvs_top.cdl"→cdl`、`"lvs_top"→top`；
- 原始 deck 的 sha256 记入 `job.json`，报告里回带，便于复现。

### 3.3 环境与许可

- **工具事实来自注册表的 per-role 用户组**（[中层配置文档 §2.3](../中层/add-中层配置文档.md)：
  中层**不探测、不解释**，原样落盘并由 `query` 原样返回；语义归本包）：

  ```json
  {"role": {"command": {"calibre": {"bin": "/opt/eda/mentor/CALIBRE2025/<ver>/bin/calibre", "version": "v2025.1_16.10"}}}}
  ```

  取值顺序：**请求显式 `calibre_bin`** > `query().roles["command"].calibre.bin`；
  两者都没有 → **业务失败**（文案指明去 `role.command.calibre` 配置），
  **不做探测、不回退 PATH**——用户给错值就让它按工具原样报错（值即权威）；
- 包内启动器固定先 `ulimit -n 65536`（Calibre 对 fd 上限敏感，实测默认 1024 会告警）；
- 许可：**不做前置许可检查**（节点锁定 license 文件无法用 lmstat 查，见可行性报告 §1）；
  许可问题由工具日志暴露，`read_results`/`status` 负责把 `license` 相关错误单独归类为 `license`（可重试）。

### 3.4 长任务与状态判据

run 类操作默认 `blocking=false`：写 launcher、后台启动、立刻返回 `job_id`。
`status` 的三重判据：

| 判据 | 含义 |
|---|---|
| `job.json` 存在 + `pgrep -f <run_dir>` 命中 | `running` |
| 日志尾出现完成标记（DRC: `CALIBRE::DRC-H COMPLETED`；LVS: `LVS completed`；PEX: `COMPLETED`） | `completed` |
| 进程消失且无完成标记，或日志含 `FATAL ERROR`/`ERROR (OSSHNL-` | `failed`（区分 `license` / `input` / `unknown`） |
| 进程消失、无产物、无日志尾 | `unknown`（**不自动重试**） |

`blocking=true` 时包内循环：`deadline = now + timeout`，按 `poll_interval`（默认 5 s）调 `status`，
终态或超时即返回；超时返回 `status=timeout` 且**后台作业继续跑**。

### 3.5 结果解析（`read_results`）

返回结构（字段名固定，便于 agent 直接用）：

| 字段 | 内容 |
|---|---|
| `kind` | `drc` / `lvs` / `pex` |
| `summary` | DRC：`{total_results, rules_checked, by_rule:{规则名:条数}, first_offenders:[…]}`；LVS：`{status: correct/incorrect/not_compared/unknown, counts:{对象:layout 数, *_source:source 数}, differences:[…]}`；PEX：`{errors, warnings, netlist_files, pdb_dirs}` |
| `first_offenders` | DRC：前 `limit` 条 `{rule, cell, bbox, count}`（来自 `DRC_RES.db`，layer 不含）；LVS 差异点在 `summary.differences` |
| `log_tail` | 有界日志尾（默认 40 行） |
| `artifacts` | 已产出的关键文件清单（名 + 字节数 + mtime） |

## 4. 各操作参数

### 4.1 `calibre.check_env`

| 参数 | 必填 | 说明 |
|---|---|---|
| `token` | 是 | 原样透传 |
| `calibre_bin` | 否 | 默认 `calibre` |
| `deck` | 否 | 给了就顺带检查 deck 与同目录 `DFM/` 是否可见 |
| `timeout` | 否 | 默认 30 s |

返回：`calibre_path`、`version`（`calibre -version` 首行）、`deck_ok`、`stderr_snippet`。

### 4.2 `calibre.drc`

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `deck` | 是 | — | DRC deck 路径 |
| `gds` | 条件 | — | 版图 GDS 路径（可用 `virtuoso.layout.gds` 产出）；**只有 deck 里出现 `"GDSFILENAME"`/`"lvs_top.gds"` 等占位符时才必填** |
| `top` | 条件 | — | 顶层 cell 名；同上（`"TOPCELLNAME"`/`"lvs_top"`） |
| `job_id` / `run_dir` | 否 | `<kind>_<top>` / role 根下 | 见 §3.1 |
| `turbo` | 否 | 4 | 传给 `-turbo` |
| `hier` | 否 | true | `-hier` |
| `blocking` / `poll_interval` / `timeout` | 否 | false / 5 / 3600 | 见 §3.4 |
| `params` | 否 | — | 无 set 时的取数口：键=**SVRF 语句头**（含空格），值=整条语句，原位改写 deck |
| `runset` | 否 | — | 远端 Calibre Interactive set（`.lvs`/`.drc`/`.pex`）：**走官方批处理入口**，参数全交给 Calibre |

**参数一律用官方机制带**（两条路，互斥）：

1. **有 set → `runset=<文件>`**：本包执行 `calibre -gui -<app> -runset <file> -batch`，
   参数的解析、合并、控制文件生成（run dir 里的 `_<rules>_`）全部由 Calibre 自己做；
   本包**不解析键、不做键→语句映射、不改 deck、不注入命令**，只做三件与结果有关的事：
   发起（+ 轮询）、定位产物（读 `lvsRunDir`/`drcRunDir`/`pexRunDir` 只为知道去哪儿取报告）、解析报告。
2. **没有 set → `deck=…`**：`calibre -<app> [options] <deck>` 官方 CLI 形态；deck 目录整份 stage 到 run dir
   （相对 `INCLUDE` 照常生效），只按白名单占位符改写 deck 文本（PDK 自己的占位符约定），
   需要额外覆盖时用 `params` 给 **SVRF 语句头**（如 `"LAYOUT PRIMARY"`，值给整条语句），原位替换第一条。

> 为什么不做键映射：Calibre 的 specification 语句 first-wins，手工把 runset 键翻译成 SVRF 语句
> 在不同工艺库会漏（例如 TSMC 65 的电源名在 `VARIABLE POWER_NAME` 且参与 connectivity 规则）。
> 官方批处理入口不做翻译，直接产出 control file，语义与 GUI 完全一致——实测见调查报告 §11。
> 占位符一个都不剩时即"自包含 deck"，`gds`/`top`/`cdl` 全部可省（步骤记 `self_contained`）。

### 4.3 `calibre.lvs`

在 DRC 参数基础上：`cdl`（**条件必填**，deck 引用 `"lvs_top.cdl"` 时必填；可由 `calibre.export_cdl` 产出）、
`power`/`ground`（可选覆盖 deck 的电源地名）。

> 实测（2026-09-24）：`params={lvsLayoutPaths, lvsLayoutPrimary, lvsSourcePath, lvsSourcePrimary}` 跑
> `CMP_LIB/inv2` + `inv2.gds` → `summary.status = correct`；同参数走 `.runset` 文件同样 `correct`；
> 未知键报 `不支持的参数键：…`。**不需要拷改 deck，也不走 GUI batch。**

#### 4.3.1 直接喂 Calibre Interactive 的 set（现场形态，官方批处理）

只给 `runset=<远端 set 路径>` 即可（deck / run dir / 输入 / 选项 / hcell / SVDB 都在 set 里）：

```
calibre -gui -lvs -runset <set> -batch      # 本包实际执行的命令（drc/pex 同理换 -<app>）
```

实测（2026-09-24，token `vb-vblog`，65nm deck + `CMP_LIB/inv2` + `export_cdl` 的 CDL）：
`completed`、`summary.status = correct`；run dir 里能看到 **Calibre 自己生成的 `_calibre.lvs_` control file**、
set 指定名字的报告（`inv2.lvs.report`）、`svdb/`、layout SPICE；`read_results` 按 run dir 里实际产物取报告
（先默认名，再 `job.json.report_file`，最后在 run dir 内扫描 `*.report/*.rep`），与 set 是否改名无关。

返回里记 `mode: "official-batch"`、`runset` 路径与 run dir（审计用）；`deck_changes` 恒为空——带 set 时本包
**不碰 deck**。附带的 `spice_file`/`hcell_file`/`xcell_file` + `params`（SVRF 语句头）只服务没有 set 的路径。

> 边界：set 只携带**参数**，不携带数据——它引用的 layout / 源网表 / hcell 文件必须已存在于远端；
> GUI 的 `*.calibre.db` 布局库由 viewer 导出，本包不产（我们的版图侧产物是 GDS）。
> 轮询用 Calibre 自己的日志标记（`LVS completed` 等）；失败同样以日志标记 + 产物为准（§3.4）。

### 4.4 `calibre.pex`

在 LVS 参数基础上：`deck` 为 **rcx** deck；**`lvs_run_dir` 必填**（PEX 需要 LVS 结果里的 `svdb/`，
包会把它复制进 PEX 的 run dir）；`fmt` 可选 `none`/`spice`/`simple`（默认 `none`，即只到 `-pdb`）。
内部固定顺序：`-xrc -phdb` → `-xrc -pdb -rc <deck>` →（可选）`-xrc -fmt -<fmt>`，
**每个阶段校验产物存在**才进入下一阶段（phdb 必须是 xRC 类型，见可行性报告 §2）。

> 实测（2026-09-22）：`calibre.pex` 用 `ctle` 的 LVS run dir 作输入，`status=completed`、
> `read_results` 给 `errors=0 / warnings=8`，与手工基线一致。

### 4.5 `calibre.status` / `calibre.read_results` / `calibre.export`

| 操作 | 关键参数 |
|---|---|
| `status` | `job_id` 或 `run_dir`；`timeout` |
| `read_results` | `job_id`/`run_dir`；`kind`（可自动探测）；`limit`（默认 20）；`log_lines`（默认 40） |
| `export` | `job_id`/`run_dir`；`items`（`summary`/`results_db`/`netlist`/`pdb_dir`/`log`/`all_small`）；`local_dir`（默认 `artifact_dir()/calibre/`） |

### 4.6 `calibre.export_cdl`（LVS 源网表，官方 auCdl）

背景：Calibre 自身不产源网表；官方 GUI 的 “Export from source viewer” 也是驱动 Virtuoso 的
**CDL Out / auCdl**（`si -batch -command netlist`，见 `doc/report/calibre-网表导出机制调查报告.md`）。
本操作实现同一条官方链路的无头版本，产物路径直接喂给 `calibre.lvs` 的 `cdl`。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `library` / `cell` | 是 | — | 要导出的 schematic 所在单元 |
| `view` | 否 | `schematic` | 起始视图 |
| `netlist_name` | 否 | `<cell>.cdl` | 产物文件名（写入 run dir） |
| `run_dir` | 否 | `<command root>/calibre/cdl_<cell>` | 导出工作目录 |
| `cds_lib` | 否 | CIW `getWorkingDir()/cds.lib` | cds.lib 路径；显式给出优先 |
| `timeout` | 否 | 600 | si 超时 |

行为：

1. 解析 `cds.lib`（显式 > CIW cwd），复制进 run dir；
2. 生成 `si.env`（`simSimulator="auCdl"`、`simViewList='("auCdl" "schematic")`、`simStopList='("auCdl")`、
   **`checkCAPPERI=nil`**——IC618 auCdl batch 的默认值缺口，缺失即 `OSSHNL-411`）与一致的 `.simrc`；
3. `CDS_Netlisting_Mode=Analog si . -batch -command netlist -cdslib <run_dir>/cds.lib`，要求 rc=0 且产物非空；
4. 返回 `{run_dir, netlist_path, netlist_name, bytes, cds_lib, log_path}`。

不做：GUI 的 runset/control-file/模板机制、Viewer 导出（headless 无意义）；digital（hnl）模式暂不支持，
需要时再按官方 `hnlCDL*` 属性要求扩展。

## 5. 不做与本版限制

1. 不解析 Calibre 的二进制结果库（`svdb`/`*.pdb` 只按文件列出与下载，不读内部结构）；
2. 不做 RVE/GUI（Calibre 交互工具不接 G 接口）；
3. 不做分布式（`-remote`/`-hyper`）与多机 license 管理；
4. 不做 deck 语义检查（只做占位符白名单改写 + 原样哈希）；
5. 不做并发调度：同一 token 建议串行跑 PDR；许可争用表现为工具报错，由调用方决定重试。

## 6. 与其它 spec 的关系

1. **注册表事实（已定）**：走 spec 的 **per-role 用户组**机制——`role.command.calibre = {bin, version}`，
   中层不探测、不校验语义、`query` 原样返回；本包在 `check_env`/run 类操作里读取，
   缺失即明确失败（§3.3）。**不需要中层改代码**，只需部署方在注册表里给值；
2. **GDS 来源**：`virtuoso.layout.gds` 已能导出（`src/pyapi/packages/layout.py:924`），本包只接受路径；
3. **CDL 来源**（两条都要能跑）：
   1. 调用方提供远端路径（现状）；
   2. `calibre.export_cdl` 从 schematic 用官方 auCdl 链路现产（§4.6）——
      2026-09-24 真机闭环：`CMP_LIB/inv2` 导出 → `calibre.lvs` 用 `inv2.gds` 比对 → **CORRECT**。

## 7. 已知限制

1. 报告解析基于 Calibre 文本报告（`DRC.rep`/`lvs.rep`/`*.log`）的**稳定关键字**；
   不同 PDK/版本措辞变化时解析会降级为"计数 + 原文尾"（不抛异常）；
2. 大设计的 `svdb`/`*.pdb` 可能很大：`export` 默认只取小文件，目录需显式点名；
3. `power`/`ground` 未给时沿用 deck 默认（可能触发 ERC 告警，见可行性报告 §2 的 LVS 实测）；
4. 许可不足、并发争用未做全局串行（§5.5）。

## 8. 验收

常驻真机套件：`python test/live/packages/calibre_e2e_tests.py --transport direct|http`
（离线矩阵 `test/offline/unit/test_calibre_*.py`；半真机探针 `test/semi/probes/calibre_*.py`）。

| 组 | 用例 |
|---|---|
| env | `check_env` 返回路径/版本；deck 不可见时报 `deck_ok=false` 并给原因 |
| EXPORT | `export_cdl` 产出**含 `.SUBCKT` + 器件行**的 CDL（只出端口壳即失败）；`netlist_name` 只能是纯文件名 |
| DRC | 小 GDS（`lay_e2e.gds` 顶层 `lay_e2e`）跑通：`status=completed`、`read_results` 给 rules_checked/结果计数；对照可行性报告基线（1737 规则 / 36 结果） |
| LVS | `ctle.gds`+`ctle.cdl`：`status=completed`、`summary.status ∈ {match, incorrect}`、产物含 `svdb/*.phdb` |
| LVS 闭环 | `export_cdl` 的 CDL 直接喂 LVS（`CMP_LIB/inv2` + `inv2.gds`）；`VB_CALIBRE_REQUIRE_LVS_VERDICT=1` 时要求 `correct` |
| PEX | 同组输入跑到 `-pdb`：`svdb/*.pdb/` 存在、`summary.errors==0`；`fmt=spice` 时产出网表 |
| 三件套 | `blocking=true` 与 `blocking=false`+`status` 轮询两种用法结果一致 |
| 失败 | deck 路径不存在 → 明确失败；GDS 顶层名错 → 工具原文回带；不给 token → 400 |
| 参数面 | deck 无占位符（自包含）时 `gds/top/cdl` 可省；deck 引用 `"lvs_top.cdl"` 而没给 `cdl` → 明确失败 |

## 9. 证据索引

| 证据 | 位置 |
|---|---|
| 可行性报告（DRC/LVS/PEX 实跑、CDL 调查、新用户 calprobe 会话） | `doc/report/calibre-可行性报告.md` |
| Calibre 环境探针 | `test/semi/probes/calibre_env_probe.py` |
| CDL 批处理探针（si.env/.simrc 生成） | `test/semi/probes/calibre_cdl_probe.py` |
| auCdl 导出机制调查（官方链路、runset/control-file 实测） | `doc/report/calibre-网表导出机制调查报告.md`（§8/§9） |
| 实跑现场（远端） | `/home/Gent/project/vblog/calibre_probe/{drc_run,lvs_run,rcx_run}/` |
| 新注册用户与独立 env | `/home/Gent/project/calprobe/`（`calprobe`，见可行性报告 §3.4） |
