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
3. **结果要"能读"**：`read_results` 直接给分类计数（DRC 按规则条数、LVS 对象计数）、LVS match/差异点、PEX warning 清单，而不是让用户去啃 100 KB 报告；DRC 的坐标级违规明细在 `DRC_RES.db`，`.rep` 不含，本版不解析；
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

接口简写：S=`execute_skill`、C=`run_command`、U=`upload_file`、D=`download_file`、G=`run_gui_command`、Sp=`run_spectre_command`。
Calibre 全部走 **command role**（C/D/U），不使用 S/G/Sp。

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
| `summary` | DRC：`{total_results, rules_checked, by_rule:{规则名:条数}, first_offenders:[]}`；LVS：`{status: correct/incorrect/not_compared/unknown, counts:{对象:layout 数, *_source:source 数}, differences:[…]}`；PEX：`{errors, warnings, netlist_files, pdb_dirs}` |
| `first_offenders` | DRC 恒为空列表：`.rep` 只有按规则统计表，坐标级明细在 `DRC_RES.db`（本版不解析）；LVS 差异点在 `summary.differences` |
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
| `gds` | 是 | — | 版图 GDS 路径（可用 `virtuoso.layout.gds` 产出） |
| `top` | 是 | — | 顶层 cell 名 |
| `deck` | 是 | — | DRC deck 路径 |
| `job_id` / `run_dir` | 否 | `<kind>_<top>` / role 根下 | 见 §3.1 |
| `turbo` | 否 | 4 | 传给 `-turbo` |
| `hier` | 否 | true | `-hier` |
| `blocking` / `poll_interval` / `timeout` | 否 | false / 5 / 3600 | 见 §3.4 |

### 4.3 `calibre.lvs`

在 DRC 参数基础上：`cdl`（必填，LVS 源网表路径）、`power`/`ground`（可选覆盖 deck 的电源地名）。

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
3. **CDL 来源**：调用方提供（已验证）；"从 schematic 自动产 CDL"的路线见可行性报告 §3.4/§3.6，
   属 `netlist` 补包范畴，不在本包内实现。

## 7. 已知限制

1. 报告解析基于 Calibre 文本报告（`DRC.rep`/`lvs.rep`/`*.log`）的**稳定关键字**；
   不同 PDK/版本措辞变化时解析会降级为"计数 + 原文尾"（不抛异常）；
2. 大设计的 `svdb`/`*.pdb` 可能很大：`export` 默认只取小文件，目录需显式点名；
3. `power`/`ground` 未给时沿用 deck 默认（可能触发 ERC 告警，见可行性报告 §2 的 LVS 实测）；
4. 许可不足、并发争用未做全局串行（§5.5）。

## 8. 验收

脚本 `test/live/packages/calibre_e2e_tests.py --transport direct|http`（**尚未建**：当前 calibre 的实测入口是
离线 `test/offline/unit/test_calibre_package.py`、半真机 `test/semi/probes/calibre_env_probe.py` /
`calibre_cdl_probe.py`、真机 `test/live/flows/lvs_from_schematic_tb.py`；路径按 2026-09-23 `test/` 三级重组更新），
产物落 `test/artifacts/calibre-tb/TEST_PLAN.md` + `TEST_REPORT.md`（目录待建）。

| 组 | 用例 |
|---|---|
| env | `check_env` 返回路径/版本；deck 不可见时报 `deck_ok=false` 并给原因 |
| DRC | 小 GDS（`lay_e2e.gds` 顶层 `lay_e2e`）跑通：`status=completed`、`read_results` 给 rules_checked/结果计数；对照可行性报告基线（1737 规则 / 36 结果） |
| LVS | `ctle.gds`+`ctle.cdl`：`status=completed`、`summary.status ∈ {match, incorrect}`、产物含 `svdb/*.phdb` |
| PEX | 同组输入跑到 `-pdb`：`svdb/*.pdb/` 存在、`summary.errors==0`；`fmt=spice` 时产出网表 |
| 三件套 | `blocking=true` 与 `blocking=false`+`status` 轮询两种用法结果一致 |
| 失败 | deck 路径不存在 → 明确失败；GDS 顶层名错 → 工具原文回带；不给 token → 400 |

## 9. 证据索引

| 证据 | 位置 |
|---|---|
| 可行性报告（DRC/LVS/PEX 实跑、CDL 调查、新用户 calprobe 会话） | `doc/report/calibre-可行性报告.md` |
| Calibre 环境探针 | `test/semi/probes/calibre_env_probe.py` |
| CDL 批处理探针（si.env/.simrc 生成） | `test/semi/probes/calibre_cdl_probe.py` |
| 实跑现场（远端） | `/home/Gent/project/vblog/calibre_probe/{drc_run,lvs_run,rcx_run}/` |
| 新注册用户与独立 env | `/home/Gent/project/calprobe/`（`calprobe`，见可行性报告 §3.4） |
