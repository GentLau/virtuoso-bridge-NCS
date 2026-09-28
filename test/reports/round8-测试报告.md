# 第八轮全面测试报告（2026-09-28）

> 状态：**收尾中**（已并入：Linux 离线/真机客户端两条线、覆盖率终值、缺陷台账；**唯一未完成项 = 红队评审结论**，见 §10）
> 口径：**三轴覆盖**（A spec 条款 / B 原子 / C op×参数）× **三层回归**（离线 / 半真机 / 真机）+ 缺陷与"不覆盖声明"。
> 原则：只用可复查证据说话；**弱判据（只看 ok/rc）不作为覆盖结论**；未跑到的显式列缺口，不声称 100%。

## 0. 一句话结论

- 三轴里 **B（原子，60 个）gap=0/weak=0**；**A（条款）297 条已逐条裁定，direct 219 / indirect 16 / partial 9 / na 53，gap=0**；
  **C（op×参数 628 条）** 最新快照 **CANDIDATE 529 / GAP 70 / NO-OP-TB 29**（root + screenshot 两车道已清零，
  calibre 参数面本轮补到只剩"kind 不适用"与红钉项；余量主要是 verilog.import 车道，见 §3/§7）。
- 三层回归：Windows 离线 **1793 例 / 0 红 / 19 skip**（最新树，另加本轮新增的 3 条离线契约用例）；
  半真机 **36 探针（32 绿 + 4 个预期红钉）**；真机 base 五接口 + 文件族 + Linux 客户侧全栈全绿，
  **11 套包 = 9 稳定绿 + 2 被缺陷阻塞**（maestro 卡 P-086/P-095、calibre 卡 `cds_lib` 口径，见 §4.4）；
  注册/流程/压测场景全绿（明细见 §4）。
- 本轮新发现并立案 **18 条缺陷**（P-078…P-095，其中 **P-095 是 P-086 的 P1 根因**：悬空 Overwrite History → ASSEMBLER-3018 模态框卡死 CIW），
  全部有红灯钉住或显式口径声明；**不声称已排干净**。

## 1. 覆盖轴 A：spec 条款

- 抽取：`extract_spec_clauses.py` 从 13 份 Normative 文档抽 **1131 条候选**（标题/表行/规范句式）；
- 裁定：`norm-review/g1..g6` 逐条给出 verdict 与证据（**必须打开证据文件确认断言**），合并稿 `round8-spec覆盖矩阵.md`；
- 当前分布（297 条可测条款）：

| verdict | 条数（最新矩阵快照） | 含义 |
|---|---:|---|
| direct | 219 | 有直接断言（读回/数值/字节/结构化错误） |
| indirect | 16 | 产物被下游消费且有断言（已在矩阵注明） |
| partial | 9 | 部分覆盖，剩余动作见 `round8-gap-actions.md`（原 15 条，已闭环含 root 2 条） |
| na | 53 | 术语表/引用/状态行等不可测，逐条给"为什么不可测" |
| gap | 0 | —— |

> root 已完成其中 2 条缺口动作：**注册#011**（部署路径不得含 token，P3 TB 29/29）、**layout#179**（失败分类 TB 4/4）。
> 机器抽查：全 436 处证据引用，**文件 0 缺失**、函数名不匹配 2 处（1 处过时、1 处暴露 veriloga#068/#096 缺"生成式缺席断言"，已转车道补）。

## 2. 覆盖轴 B：原子操作（60 个）

- 工具：`audit_atom_coverage.py`；证据 `test/artifacts/evidence/atom-coverage-2026-09-28.json`
- 结果：**gap=0 / weak=0 / 待分诊=0 / 间接=0**（semi+live 均有引用；"证据树第二来源"同样 0 遗漏）；
- 本轮补强：serdes calibre 补 `read_results`、ADC/多用户 SerDes 补 `symbol.read` 端口比对、S11 gds 补 stat+sha256。

## 3. 覆盖轴 C：op × 参数（79 个操作 / 628 条）

- 工具：`build_op_param_matrix.py`（AST v2，能解析 `OP + "suffix"` 拼接与跨函数转发）；
- 最新快照：**CANDIDATE 515 / GAP 84 / NO-OP-TB 29**；`NO-OP-TB` 的业务 op 只剩 `calibre.export`、`calibre.pex`（calibre 车道收尾中）；
- root 车道（spectre/maestro/layout 失败分类/注册 token-path）已清零：
  - `spectre_params_e2e_tests.py` **5/5**；`maestro_e2e_tests.py` **23/23**；`layout_geometry_classification_e2e_tests.py` **4/4**；
  - 期间抓出 4 条同源缺陷：P-083（precision 语义未定义）、P-084（include_results 死参数）、**P-088**（delete_var scope=all）、**P-089**（open_waveform_gui.result 死参数）。
- **screenshot 车道本轮清零**（root 自己补的 TB）：`screenshot_params_e2e_tests.py` 三级 kind 各覆盖
  `window_id`/`region`/`toplevel`/`central_widget`/`leave_open`/`view_type`，实测
  schematic **5/5**、symbol **5/5**（均绿）、layout **5 绿 + SC-06 红钉**（bogus `view_type` 不校验 → P-080 同族）；
  期间抓出 **P-091**（symbol/layout 下载后删远端暂存，与 spec「远端存 screenshots/」口径不一致）与
  **P-082 的完整形态**（layout/symbol 要两点、schematic 要四元组，spec 只写了两点）。
- 剩余 GAP：calibre 车道 25（含 `calibre.export`/`pex` 两个零调用 op）、verilog 车道 12（`verilog.import` 9 参数为主）、
  `layout.read.depth`（P-085 红钉）、`verilog.read/write.view_type`（P-080 红钉）——**如实计为未覆盖，不并入 direct**。
- **calibre 参数面本轮大补齐**（root 新增 TB）：`calibre_params_e2e_tests.py` **5/5 绿**，
  覆盖 `check_env(calibre_bin/deck 正负)`、`drc(calibre_bin/hier/turbo/poll_interval/job_id/params/run_dir)`、
  `read_results(log_lines=0/5 双向)`、`lvs(spice_file/hcell_file/xcell_file/hier/turbo/poll_interval)`；
  剩余 GAP 里 **`drc.spice_file/hcell_file/xcell_file/fmt/lvs_run_dir` 与 `lvs.fmt/lvs_run_dir` 属"kind 不适用"**
  （argv 只在 lvs/pex 分支消费，见 `src/pyapi/packages/calibre.py:987-1013`）、**`power`/`ground` 是死参数（P-092）**、
  `drc.runset`（set 模式）仍缺一条真跑——这三类在矩阵里保持 GAP/红钉，不粉饰。
- 期间又抓出 **3 条缺陷**：P-092（power/ground 死参数）、**P-093**（`hier=False` 仍带 `-turbo` → Calibre 判非法、打 usage）、
  **P-094**（工具秒退不被检测：`status` 只报 `unknown`、`blocking=True` 等满 timeout）；红钉探针
  `test/semi/probes/calibre_flat_turbo_probe.py` 已注册进 `run_semi_probes.py --group calibre`。

## 4. 三层回归

### 4.1 离线（Windows，最新树）

- `pytest test/offline -q` → **1793 例 / 0 红 / 19 skip**（`evidence/round8/offline-win-r8.xml`、`offline-win-5.xml` 同口径复核一致）。

### 4.2 离线（Linux py3.9）

- 同一份树在 wsl-gent 仓库副本上跑 → **1793 例 / 0 红 / 29 skip**（`evidence/round8/offline-linux-py39-r8.xml`）；
- **两平台用例数完全一致（1793）**，且都 0 红 → Linux/Windows 客户端离线一致性本轮成立；
- 上一份旧树里的 3 红（P-079 两条 XPASS(strict) 平台门控 + P-078 断言）已由对应子代理处理。

### 4.3 半真机（36 探针）

- `run_semi_probes.py --group all` → **32 绿 / 3 红**（该次快照 35 探针）；本轮又注册 1 条：
  `calibre_flat_turbo_probe.py`（P-093/P-094 红钉，实测 `tool_failed=true` 而 `error_surfaced=false`）→ **36 探针 / 4 红钉**；
- 4 红钉均为已立案预期：`schematic_wire_style_probe`（P-078）、`maestro_export_include_results_probe`（P-084）、
  `layout_depth_probe`（P-085）、`calibre_flat_turbo_probe`（P-093+P-094）；
- 证据：`evidence/round8/semi-probes.json`、`semi-probes-r8.log`、`evidence/round8/p093-flat-turbo-probe.json`。

### 4.4 真机

- **11 套包（三次 gate 分开记，不合并口径）**：
  1. 初版 gate（`package-e2e-r8.log`）**10/11**：唯一红是 root 自己的 WRITE-06 旧判据 → 修判据后 `maestro_e2e_tests.py` **23/23**；
  2. 中间版 gate（`package-e2e-r8-final.log`）**8/11**：三红 layout/verilog/veriloga 全是 `Empty response from daemon`（P-086 族），
     按"红项单独复跑定性"逐套复跑 → `layout` **rc=0**、`verilog` **rc=0**、`veriloga` **7/7**（复跑前出现一次 P-090 形态的
     `mv: cannot stat <stage>`，重跑即绿，已单独立案为观察项）；
  3. **终版 gate（21:51 起，树=当前）`package-e2e-r8-final2.log` = 9 PASS / 2 FAIL**：
     - `maestro_e2e_tests.py` FAIL：`virtuoso.maestro.run` → `RuntimeError: Empty response from daemon`（P-086，同一实例上第 3 次独立复现；
       复跑仍在 `read_config` 处再报同错，**不是** TB 判据问题）；
     - `calibre_e2e_tests.py` FAIL：EXPORT-01 `calibre.export_cdl failed: cds.lib not resolved (CIW cwd unavailable; pass cds_lib explicitly)`
       （TB 未显式传 `cds_lib`，`_ciw_cds_lib()` 的 `getWorkingDir()` 没拿到 cwd；**已交 calibre 车道判定 TB 侧还是产品侧**，见 §7 G12）。
  ⇒ **本轮可复现结论 = 9 套稳定绿**；另外 2 套分别被 P-086 与 calibre `cds_lib` 口径阻塞，**不声称 11/11**。

### 4.5 真机 · Linux 客户端（客户侧全栈）

- 口径：**客户端侧代码全部跑在 Linux**，不是"Windows 客户端连 Linux 目标"——业务面 `api_server` + 中层 `transport`
  + 包层都在 wsl-gent 上，用 `/usr/bin/python3.9`（满足"客户端 ≥3.9"），指向 wsl-gent 上的真实实例 `vbuser2`（daemon 65402，GUI `:103`）。
- 环境：仓库副本 `~/project/vblog/tb-sandbox/linux-client/repo` + 独立注册表 `env-live`（token `vb-vbuser2`）+ Linux 侧业务面 `127.0.0.1:8127`；
  与 Windows 侧常驻 8127 / Gent 实例完全隔离（不同注册表、不同实例）。
- 结果：`infra_e2e_tests.py --transport http` **6/6 PASS**（五接口 skill/command/gui/spectre + 文件上传下载 + 递归目录 + 串并行 + 超时语义 + GUI 枚举/截图），
  证据 `evidence/round8/linux-client-infra.json`（含 `python: 3.9.25`、`platform: Linux-…-WSL2`）。
- 过程中修掉一个**环境漂移**（不是产品 bug）：vbuser1/vbuser2 的 Virtuoso 实际跑在 `:110`/`:103`（`xvfb-run -a` 随机显示号），
  注册表却写 `:100`/`:101`，导致 `virtuoso.gui.*` 报 `no CIW window found`；已把两个注册表改成实际值并写入 `docs/环境与场景.md` 的 DISPLAY 纪律。
- 复现入口见 `docs/环境与场景.md` §7「Linux 客户端真机链路」。**仍不覆盖**：Linux 客户端下跑 *全部* 包套件与 flows（本轮只跑 base 五接口 + 文件族；包/流程层仍以 Windows 客户端为主，见 §7 G6）。
- **注册**：six-local ok、py27 **10/10**、role-split **29/29**、real-ciw **12/12**；
- **流程/规模/并发**：multihop 10/10、scale-100（100 fake）ok、多用户版图接力 12/12、多用户 SerDes **17/17**、ADC **24/24**、role-credential-isolation 8/8、生产面混合压测（此前 216 步 0 失败）。
- **LVS**：`lvs_from_schematic_tb`（源网表由 `schematic.read` 产品数据生成 → 桥导出 GDS → `calibre.lvs` + `read_results`）
  实测 **CORRECT**（`CMP_LIB/cmp_top`，ports 6，`lvs.rep` 行含 `CORRECT`；证据 `evidence/round8/lvs-from-schematic-r8.json`）；
  对照 `s11_full_flow` 的自建版图（只有 M1 矩形无布线）为 `incorrect`（预期）。

## 5. 覆盖率（机器）

**本轮口径**：`coverage run --branch --source=src` 逐层/逐套件采集后合并（含离线三层 + standalone TB + 11 包 direct +
真机五接口 + 注册 + S11 等步骤；与历史"再并入 ssh/paramiko/supervisor 定向运行"的合并口径**不同，禁止混引**）。

| 指标 | 数值 | 证据 |
|---|---|---|
| 语句 | **67.19%**（covered 11641 / 17325，miss 5684） | `evidence/cov-main/coverage-main-strict.json`（2026-09-28 21:36 重跑） |
| 分支 | **50.38%**（covered 3067 / 6088，miss 3021） | 同上 |
| combined | **62.82%**（display 63%） | 同上 |
| 模块数 | 57 | 同上 |
| 未覆盖分类 | 未分类 5638 / 防御性 8 / 环境阻塞 50 | `coverage-pack/coverage-rules-auto.json` |

> 口径说明：① 初轮（`coverage-main-r8.log`）有一处 step rc=1（`packages/maestro (direct)`，root 的 WRITE-06 旧判据）；
> 修正后重跑得本表数字（与初轮 67.12%/50.30%/62.75% 差异仅来自该 step 恢复）。
> ② 与历史 79.31%/69.88%（离线三层，合并 ssh/paramiko/supervisor/register 定向运行）与 86.60%/77.39%
> （再合并真机）**口径不可比**；③ **不声称 100%**，明缺口见 §7。

## 6. 本轮缺陷（全部有红灯钉住或口径声明）

| ID | 层 | 状态 | 一句话 | 钉住物/证据 |
|---|---|---|---|---|
| P-078 | 上层 schematic | 待设计修 | `place_wire` 样式参数（width/color/line_style）与 spec 不符 | 半真机探针红 |
| P-079 | 中层 配置 | 待设计修 | local 联合端口显式双值不等被静默归一化 | 离线 strict xfail（需平台门控） |
| P-080 | 上层 verilog/veriloga/**symbol/layout 截图** | 待设计修 | `view_type` 不校验（read 静默接受；symbol/layout 截图对 bogus 也成功） | 离线 4 strict xfail + `screenshot_params_e2e_tests.py` SC-06 红钉（symbol/layout） |
| P-081 | 中层 SSH | 待设计修 | 远端 POSIX 路径被 `Path()` 改写 | 离线 strict xfail（Linux 侧 XPASS，需门控） |
| P-082 | 上层 + 口径 | 待设计修 | region 两点 vs 四元组口径漂移（三处请求面） | 离线 strict xfail + 探针 |
| P-083 | 上层 spectre | 待归属 | `export.precision` 语义未定义（实现=有效数字） | TB 按实效钉住 |
| P-084 | 上层 maestro | 待设计修 | `export.include_results` 死参数 | 半真机探针红 |
| P-085 | 上层 layout | 待设计修 | `layout.read(depth>0)` + region 任何写法都失败 | 探针红 + 离线 xfail |
| P-086 | 底层/中层 | 观察（根因见 P-095） | 多用户同视图后 / maestro run 后 `Empty response`（30–90s 自愈，模态框形态可 >2 分钟不自愈） | 探针 4/4 + 终版 gate 第 3 次复现 |
| P-087 | 上层 maestro | 待设计修 | `save=False` 改动被后续 save 静默带走 | 磁盘级探针红 |
| P-088 | 上层 maestro | 待设计修 | `delete_var(scope=all)` 确定性 handle 0 | 红灯探针 + scope 矩阵 |
| P-089 | 上层 maestro | 待设计修 | `open_waveform_gui.result` 死参数 | 红灯探针 |
| P-090 | 中层传输 | 观察 | upload 安装步骤偶发 `mv: cannot stat <stage>`（校验通过后 stage 消失；复跑与 40 次 hammer 均绿） | 原始日志 + 复跑对照 + hammer 不入册脚本 |
| P-091 | 上层 symbol/layout | 待决策 | 截图远端产物策略三包不一致（schematic 保留 / symbol+layout `rm -f`），spec 写「远端存 role root screenshots/」 | 新 TB SC-01 的 `remote_present` NOTE + `find` 0 命中 |
| P-092 | 上层 calibre | 待设计修 | `power`/`ground` 声明并校验但实现从不读取（静默无效，与 P-084 同类） | 真机 job.json/argv/报告三者无差异 |
| P-093 | 上层 calibre | 待设计修 | `hier=False` 仍追加 `-turbo` → Calibre 判非法、打 usage、作业秒退 | 半真机探针红 + drc.log 原文 |
| P-094 | 上层 calibre | 待设计修 | 工具秒退不被检测：`status=unknown`/`failure_kind=null`，`blocking=True` 等满 timeout | 同上探针（`tool_failed=true` vs `error_surfaced=false`） |
| P-095 | 上层 maestro | 待设计修 | **P-086 的 P1 根因**：悬空 Overwrite History → `ASSEMBLER-3018` 模态框阻塞 CIW，watchdog 不处理 | 子代理现场（CDS.log 22:48 + 8×15s 空响应） |

## 7. 明缺口 / 不覆盖声明（防"虚高"）

| # | 未覆盖项 | 现状 | 说明 |
|---|---|---|---|
| G1 | **蒙特卡洛驱动** | 无实现（P-070 待产品口径） | 只有"读回 MC 结果"的解析用例；MC 实验还留下过共享库 run_mode 污染（已恢复） |
| G2 | **后仿 / PVT** | 后仿（PEX）仅在 calibre 车道收尾 | 本轮只做前仿（AC/TRAN）+ DRC/LVS；PVT 未测 |
| G3 | **真实 100 台机器** | 用 100 个协议级 fake 替代 | scale-100 是 fake fleet；真机侧只有 8 实例 |
| G4 | **>2 跳拓扑** | 2 跳 + SOCKS5 叠加已测（multihop 10/10） | 3 跳以上未测 |
| G5 | **自建版图的 LVS `correct`** | 仅在复用既有真实版图时成立 | 本轮新增：源网表由产品数据生成（`lvs_from_schematic_tb`，CMP_LIB/cmp_top）→ **CORRECT**；但**版图本身不是桥自建布线**（自建版图仍 `incorrect`）。要闭合需"桥 write 出带布线/端口的版图 → LVS correct" |
| G6 | **Linux 客户端包/流程层未跑** | 本轮新增：Linux 客户侧全栈跑 base 五接口 + 文件族 **6/6**（§4.5）；离线层 py3.9 与 py2.7/3.6 探针已绿 | 仍差：Linux 客户端下跑 11 套包 E2E / flows（多用户、ADC、SerDes）——这些 TB 硬编码 `127.0.0.1:8127 + vb-vblog`，需逐个加 `--api/--token` 覆盖（`infra_e2e_tests.py` 已加，可作样板） |
| G7 | **子进程覆盖率** | 未合并 | `supervisor.py` 等被监督体跑在子进程，当前口径低估（R7-O-11） |
| G8 | **GUI"点击级"交互** | 仅探针级（窗口定位 + 截图 parity） | 无真实鼠标点击/对话框流程用例（模态框类问题靠探针与 X11 工具兜） |
| G9 | **host-key 轮换 TB（P5）** | **TB 未落地** | 测试侧接口已就绪（`w4_hostkey_cycle.sh` status/use-a/use-b/restore + 常驻说明）；设计侧未写 TB |
| G10 | **maestro 多 corner 扫描整链** | 仅有包级 e2e 与历史探针 | 本轮未做"多 corner 扫描 + 结果比对"整链 |
| G11 | **`layout.read(depth>0)`** | **确定性不可用**（P-085） | 已红钉；在修复前该参数组合记"未覆盖（被缺陷阻塞）" |
| G12 | **calibre.export / calibre.pex** | 收尾中（calibre 车道） | 当前 `NO-OP-TB` 两个业务 op；若本轮来不及，按"下轮首项"记录而非假装覆盖 |
| G13 | **calibre 参数面剩余 11 条** | 部分覆盖（见 §3） | 已覆盖：calibre_bin/hier/turbo/poll_interval/job_id/params/run_dir/cdl? 与 lvs 的 spice/hcell/xcell、read_results.log_lines（`calibre_params_e2e_tests.py` 5/5）。**仍未覆盖**：`drc.runset`（set 模式真跑）；**kind 不适用（不构成缺口）**：`drc.spice_file/hcell_file/xcell_file/fmt/lvs_run_dir`、`lvs.fmt/lvs_run_dir`（argv 只在 lvs/pex 分支消费）；**死参数红钉**：`drc/lvs.power/ground`（P-092） |
| G14 | **verilog.import 参数面（9 条）** | 未覆盖（GAP） | file_is_local / functional_view / ground_net / import_lib_cells / overwrite / power_net / ref_libs / schematic_view / symbol_view + `verilog.export.recursive` —— 该 op 是"文本视图装码"族，需真机库配合，留给 verilog 车道收尾 |
| G15 | **screenshot 远端产物留证** | P-091 待决策 | 实测只有 schematic 留远端；symbol/layout 清理 → 审计无法从远端复核三包截图（本地 PNG 均有） |

## 8. 环境与过程（本轮踩坑记录）

- 8127 是 standalone：**改 `src/` 后必须重启**，否则探针读旧代码（本轮两次踩到）；
- 共享库 `maestro_tb/rc_probe` 被 MC 实验改成 `Monte Carlo Sampling` → 常规 run 产出 MC 布局、waveform 读回失败（已恢复）；
- 并发纪律：三个子代理各自起过重叠 runner（两名并发 `run_all_http`、semi 探针与 live 套件互相打断 maestro 会话）→ 已收敛为单 runner 并记录在案。
- **calibre 参数面的教训（P-093/P-094 的发现路径）**：`hier=False + turbo` 组合让 Calibre 秒退，
  而桥的轮询只看"报告是否出现" → 一次 TD 实测挂满 5 分钟才被人工 kill。
  结论写进 §7/G13：**凡是"工具可能秒退"的参数组合，TB 必须自带宽限轮询或走非阻塞 + `status`**（本 TB 的 LVS 用例已改成这种形态）。

## 9. 复现入口（节选）

```powershell
python -m pytest test/offline -q -p no:cacheprovider
PYTHONPATH=src python test/shared/runners/run_semi_probes.py --group all
PYTHONPATH=src python test/live/packages/maestro_e2e_tests.py --transport http
PYTHONPATH=src python test/live/packages/spectre_params_e2e_tests.py --transport http
PYTHONPATH=src python test/live/packages/layout_geometry_classification_e2e_tests.py
PYTHONPATH=src python test/live/packages/screenshot_params_e2e_tests.py --transport http \
  --token vb-vbuser2 --lib serdes_rx --cell rx_top --view schematic --kind schematic   # 另有 --kind symbol / layout
PYTHONPATH=src python test/live/packages/infra_e2e_tests.py --transport http \
  --api http://127.0.0.1:8127/api/operation --token vb-vbuser2 --work-dir <linux 侧 env-live>  # Linux 客户端车道
python test/shared/runners/audit_atom_coverage.py
python test/shared/runners/build_op_param_matrix.py
```

## 10. 红队评审（独立子代理）

- 任务书：`test/reports/round8/red-team-brief.md`（8 条必查清单：≥30 行 direct 复核、弱判据、op×参数抽查、
  原子抽查、数字对账、不覆盖声明、红钉有效性、构造反例）。
- 产出：`test/reports/round8/red-team-review.md`。**当前状态：未执行**（并发槽位被 calibre/verilog/screenshot/serdes 四条车道占满，
  子代理未交付）——本报告**不声称已完成独立复核**，这是本轮唯一明确的流程缺口，建议下一轮首项补上。
