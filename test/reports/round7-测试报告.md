# 第七轮 · 全量测试报告（离线 / 半真机 / 真机三层）

> 执行者：测试（root） ｜ 2026-09-24 晚 ｜ 口径：**三层递进**（离线 → 半真机 → 真机）
> 代码状态：`HEAD=d05cd85`，工作区 dirty（`worktree_diff_sha=f53d7d33…`，含 calibre set/官方批处理、P-049 边界、work-root 一次性化、删除 `server/stress_server.py`）
> 本轮性质：**非阻塞**（发现红不阻塞，全部跑完再汇总）；TB 明显过时/写错**直接修**，逐条留痕在 `round7-TB修正.md`

---

## 0. 结论摘要（先看这 8 行）

| 层 | 结果 | 证据 |
|---|---|---|
| 离线（Windows，py3.12） | **1731 例 / 0 红 / 0 error / 7 skip**（98 个文件全 PASS） | `test/artifacts/evidence/round7/offline3.xml`、`coverage-main.log`（`files=97 failures=0`） |
| 离线（Linux 客户端 py3.9） | **1731 例 / 0 红 / 0 error / 20 skip**（逐文件收集数与 Windows **完全一致**，差值为 0） | `round7/linux-py39-offline2.xml`、`test/artifacts/tmp/collect-{win2,linux2}.txt` |
| 半真机（**整层 32 个探针**） | **32/32 green（456s）**；其中 `schematic_pin_ops_probe` **抓到 2 条 pin 语义缺陷（P-073）** | `round7/semi-probes.json`、`round7/semi-logs/`、`round7/semi-all.log` |
| 真机（常驻 8 实例 + 5 token） | 11 套包 `all_passed=true`；五接口 ×4 token 各 5/5；SerDes RX **11/11**（含 calibre DRC+LVS）；ADC SAR **22/22**；两用户共建 **15/15**；版图接力 **12/12**；role-split **5/5**；多跳+代理 **11/11**；S11 全链 rc=0 | `round7/live-run-all-http.log`、`round7/serdes/`、`round7/adc-sar.json`、`round7/serdes-multiuser.json`、`env/log-vblog/multiuser-layout-handoff.json`、`env/scenario-role-split/evidence.json`、`round7/multihop.json`、`env/s11/` |
| 并发/规模 | 生产面混合压测 6×6 = 36 轮 216 步 **0 失败**；scale-100 = 100 fake × 2 轮 **0 串台** + 负向对照能抓到错答 | `round7/production-face-stress.json`、`env/scenario-scale-100/evidence.json` |
| Linux/解释器矩阵 | 远端侧 py2.7.6 真解释器 5/5 + handler `silent drop (correct)`；py3.6.8 daemon 5/5 + 编译 ok | wsl-gent `~/project/vblog/tb-sandbox/r7out/` |
| **LVS 全链** | `calibre.export_cdl` → `layout.gds` → `calibre.lvs` → `read_results` = **`correct`**（ports 4/4、nets 4/4、inst 1/1、differences=[]）→ **P-069 建议销案** | `round7/design-iterate/iterate-lvs.json` |
| 覆盖率（本轮单跑，**全步骤通过**） | 语句 **67.31%** / 分支 **49.72%**（combined 62.77%，56 模块）——**不声称 100%**，明缺口见 §7 | `test/artifacts/evidence/cov-main/coverage-main-strict.json`、`round7/coverage-main2.log` |
| 新缺陷 | **P-073**（pin 原子操作语义错，P2）、**P-074**（spec/实现 pin 索引口径不一致，P3）；未关闭还有 P-070（蒙卡口径） | `round7-缺陷清单-上层.md`、`round7-缺陷清单-其他.md` |

---

## 1. 本轮做了什么（与上轮的差别）

1. **三级架构不变，但补上三条硬缺口**：① **设计迭代链**（改图→二次出图→版图二次发布→仿真复测）；
   ② **真机 LVS 得到 `correct`**（P-069 验收判据）；③ **Linux 客户端 py3.9 全量离线复跑**（此前只有 Windows 客户端跑过全量）。
2. **修掉 12 处 TB 问题**（含 3 处"假红"是 TB 自己的错：S11 的假 pin、standalone TB 的 work-root 姿势、py2.7 探针导入姿势），
   全部记录在 `round7-TB修正.md`，每条都回答"断言还成立吗"。
3. **新攻击面**：pin 原子操作（rename/delete/set_properties）四角度对表 → 抓到 P-073；
   `layout.write` 的 append 语义、GDS sha 的时间戳噪声、`calibre.read_results` 的必需参数等口径问题**写进 TB 注释**，避免后人重复踩。

## 2. 离线层（不需要真实环境）

| 项 | 结果 |
|---|---|
| 三层用例（unit/integration/scenario） | **1731 例**、0 红、0 error、7 skip（Windows；`offline3.xml`；含本轮新增的 `test_upper_layer_import_contract.py` 6 例） |
| 逐文件驱动（`run_main_coverage.ps1` 的 L0-L2 多进程） | `files=97 failures=0`（含 `test_ssh.py` 自动降级为"逐节点隔离"后 PASS）；新增 1 个文件后为 98 |
| standalone TB（`offline/core/*`） | api-server / daemon-log-protocol 绿；`semantics_tb` **10/10**、`fault_injection_tb` **8/8**（本轮按 P-072 口径改"每 case 子进程"后转绿） |
| Linux py3.9 客户端 | **1731 例**、0 红、20 skip（与 Windows **逐文件收集数一致**；`collect-win2.txt` vs `collect-linux2.txt` 差值 0） |
| 双解释器（远端侧口径） | py2.7.6：daemon 探针 5/5、handler 真解释器 `silent drop (correct)`；py3.6.8：daemon 探针 5/5、`py_compile` ok |

> 计数口径说明：pytest 9.1.1 的 JUnit `tests=` 属性写 2377、而 `<testcase>` 实际 1725（pytest 8.4.2 写 1725）；
> 本报告**一律以 `<testcase>` 数 + rc 为准**，并在 `round7-缺陷清单-其他.md` R7-O-07 记为观察项。

## 3. 半真机层（需要真机，但不跑完整流程）

**本轮把半真机层**整层**复跑了一遍：32 个探针 / 32 green / 0 red / 合计 456s**。
入口是新加的表驱动 runner（也是给下一轮用的固化姿势）：

```powershell
$env:PYTHONPATH='src'; python test/shared/runners/run_semi_probes.py --group all
```

证据：`test/artifacts/evidence/round7/semi-probes.json`（逐探针 rc/耗时/输出尾巴）、
`round7/semi-logs/*.log`（每个探针的完整 stdout/stderr）、`round7/semi-all.log`（整跑控制台）。

### 3.1 分组结果

| 组 | 探针 | 结论摘要 |
|---|---|---|
| layout | `layout_lock_ownership_probe`（**本轮改判据**，见 R7-TB-14）、`layout_p044_second_write_probe`、`twouser_same_view_probe` | 锁语义干净：**有锁文件时 `layout.write` 照样过锁这一关**（只报 layer 名错误）；P-044 二次写"no defect observed"；两真实用户同视图 7 场景 **全绿**（A 写完 B 读/写、A 持有 edit 时 B 读成功、B 写得到"locked by another session"干净失败、无残留锁） |
| symbol | `symbol_pkg_probe`（P-069 后可用 `--token` 指 PDK 实例）、`symbol_regen_handle_probe`、`symbol_generate_hierarchy_handle_probe`、`symbol_screenshot_probe`、`symbol_http_400_repro` | 句柄 clean（3 次 generate 后视图 CLOSED）；层级 handle clean；同视图 generate 仍稳定返回 **400 `schematic_view and symbol_view must differ`**（负控制有效） |
| schematic | `shared_cdf_pollution_probe`、`schematic_pin_ops_probe` | 共享 CDF **clean**（默认值 1K/400n 未被改写、peer 会话默认值正确）；pin 探针**抓到 2 条缺陷 P-073** |
| maestro | `maestro_env/pkg/session_conflict/leak/e2e/screenshot` | 6/6 通过：环境 29 个 rfExamples cell 可见；会话冲突 false；`maestro_leak_probe` 各 WRITE 用例 PASS；截图 parity PASS |
| calibre | `calibre_env_probe`、`calibre_cdl_probe`、`cdl_export_variants_probe`、`calibre_package_http_probe` | 6/6：env/`--facts` 正常；CDL 探针拿到 `.subckt sch_e2e`；导出变体 26s 完成；HTTP 面 env 通 |
| spectre | `spectre_ac_pipeline_probe` | **clean**（AC 数据管线） |
| skill | `skill_syntax_matrix_tb`、`skill_tooling_probe`、`skillref_probe`、`docs_search_probe` | 4/4：语法矩阵 **10/10**；远端 finder 树 download→parse→search PASS；skillref 远端真链路通；本地 Cadence 文档全文检索通 |
| transport | `paramiko_ssh_config_true`、`lone_surrogate`、`one_shot_burst`、`log_matrix_real`、`ssh_backend_semi`、`role_credential_isolation` | 6/6：ssh_config 3 例；孤立代理项被 400 拒绝（无掉线）；one-shot 突发 0 失败；日志矩阵通；SSH 后端（含**持久 shell 失败 → 一次性 SSH 回退**路径）；按 role 分凭据隔离通 |
| gui | `gui_display_probe` | 通过（真实 display 上的 CIW 定位 + 截图） |
| misc | `gds_publish_path_edges_probe`、`daemon_internal_error_path_probe`、`log_rotation_lock_probe` | 4/4：GDS 路径边界 clean；daemon 内部错误路径契约成立（真 py2.7 版由解释器探针覆盖）；日志轮转 PASS |

> 探针表（"哪个探针怎么跑、要什么环境"）就写在
> `test/shared/runners/run_semi_probes.py:PROBES`，以后每轮至少复跑一次即可。
> 本轮 runner 里另有 2 处参数姿势纠正（`skill_tooling_probe --check`、`skillref_probe --source remote --doc-root …`）与
> 1 处探针改造（`symbol_pkg_probe` 支持 `--token`），见 `round7-TB修正.md` R7-TB-14/15/16。

## 4. 真机层（全真环境，按用户实际用法驱动）

### 4.1 表面

| 项 | 结果 |
|---|---|
| 11 套包（infra/cellview/schematic/symbol/layout/verilog/veriloga/skillref/spectre/maestro/calibre） | `all_passed=true`（`round7/live-run-all-http.log`） |
| 五接口 × 4 token（`cov_remote_real.py`） | `vb-vblog`/`vb-vbuser1`/`vb-vbuser2`/`d6af595b…` 各 **5/5**（skill/command/file/gui/spectre） |
| 注册流程（六步 / 1-4 远程） | 随 cov runner 复跑通过（`registration six-step (local)`、`registration 1-4 (remote)` 无 rc≠0） |

### 4.2 真实业务场景（本轮三例，均带数值判据）

| 场景 | 规模 | 结果 | 数值判据 |
|---|---|---|---|
| **SerDes RX 全流程**（`serdes_rx_flow_tb.py --stage all --with-calibre`） | 11 段：probe→lib→buf→ctle→term→top→layout→gds→cdl→sim→calibre | **11/11 PASS** | AC：gain 5.055 dB@1MHz、peak 5.409 dB@2.5GHz、BW 15.85 GHz；TRAN 摆幅 0.396 V；`shared_cdf_mutated=false` |
| **ADC SAR 全流程** | 22 项（cmp/latch/top + 版图 + 仿真） | **22/22 PASS** | `round7/adc-sar.json` |
| **两真实用户共建 SerDes RX** | 15 项（vbuser1/vbuser2 交叉读写） | **15/15 PASS** | `round7/serdes-multiuser.json` |
| **设计迭代链**（本轮新增 `design_iterate_tb.py`） | 11 段 × 2 轮 | 轮 1 全 PASS；轮 2 **版图/GDS/仿真 PASS**、改图 pin 改名 **2 条红（P-073）** | 平带增益 22.79→22.82 dB（Δ0.03）、峰值基准 3dB 带宽 **2.24 GHz → 446.7 MHz（掉 5.01×）**、摆幅 1.59→1.44 V；版图形状 2→4；GDS 二次发布到新目录 |
| **版图接力（S16）** | 12 项（A 未关闭会话，B 接着读写） | **12/12 PASS** | 含 `B-sees-A-shapes`、`B-writes-after-A`、`A-can-still-write`、`no-cdslck-residue`、`concurrent-write-structured` |
| **S11 全链**（`s11_full_flow.py`） | lib→schematic→symbol→layout→gds→drc→**cdl**→**lvs** | **rc=0** | cdl 693 B（官方 auCdl）；lvs `status=incorrect`（**确定结论**：ports 1/1、nets 5/9、inst 2/2 —— 脚本搭的最小版图无布线，属预期）；`correct` 由下表钉住 |
| **LVS `correct` 验收**（`design_iterate_tb.py --stage lvs`，真实 cell `CMP_LIB/inv2`） | export_cdl 680 B → layout.gds → calibre.lvs(deck+cdl) → read_results | **PASS** | `status=correct`、ports 4/4、nets 4/4、inst 1/1、`differences=[]` |
| **LVS 交叉面复验**（`calibre_package_http_probe.py --kind lvs`，走**另一个业务面 8128** + token `vb-s11cal`） | 同一条链路，独立 work-dir | completed | `status=incorrect`（**确定结论**，与 S11 自跑一致：ports 1/1、nets 5/9、inst 2/2）——两个面结论一致，说明不是单实例假象 |

### 4.3 拓扑与多机

| 项 | 结果 | 说明 |
|---|---|---|
| role-split（`role_split_tb.py --user rolesplit --token vb-s11`） | **5/5** | daemon 落 wsl-gent、command/file 落 w1-gent（`dev` 用户），root 与注册表一致，文件往返内容一致 |
| 多跳 + 代理（`multihop_jump_tb.py`） | **11/11** | 直连/IP 对照、jump 场景 client_ip=w3-gent、**SOCKS5 代理**隧道、jump 文件往返 sha256、经 jump 的 daemon SKILL、经 jump 的 HTTP 业务面 |
| 常驻 8 实例 | 5 真实（wsl-gent：vblog/vbs11/calprobe/vbuser1/vbuser2）+ vbtest + 2 fake（w1） | 见 `test/docs/环境与场景.md` §2（2026-09-28 起原 `推荐测试环境.md` 并入该文档） |

### 4.4 并发与规模

| 项 | 结果 | 说明 |
|---|---|---|
| 生产面混合压测 6×6 | **36 轮 / 216 步 / 0 失败**（35.6s） | 每轮 6 类操作：command / upload / download / **skill** / **gui** / **spectre**（真 daemon） |
| scale-100 | **5/5**：100 fake × 2 轮，100 token **全部答自己**、0 串台、max 24ms | 负向对照（把 B 指到 A 的端口）**必须抓不到 `cloud-b`** —— 本轮它确实抓不到 ⇒ 断言非空 |

## 5. 三级递进的"发现问题即回退修复"记录

本轮在每一层都遇到"上一层/本层红"，按用户要求**先修再继续**（非阻塞）：

1. 离线层：`offline/core` 两个 standalone TB 撞 P-072 新口径 → 改每 case 子进程（R7-TB-11/12）→ 转绿；
2. 半真机层：`calibre_package_http_probe` 默认 deck 为空 → 探针必然红（R7-TB-10）→ 修后 DRC completed；
3. 真机层：S11 的 lvs 长期 FAIL，定位为 **TB 摆了假 pin**（`basic/ipin` 实例而非 `schCreatePin`）→ 修后拿到确定结论（R7-TB-09）；
4. 真机层：迭代链 TB 自身四处错（缺 VSS 地、耦合电容测量频点、读回值带引号、append 语义）→ 修后方向断言成立（R7-TB-01/02/04/05）。

## 6. 本轮缺陷（送修见 `round7-缺陷清单-*.md`）

| 编号 | 级别 | 一句话 | 归属 | 状态 |
|---|---|---|---|---|
| **P-073** | P2 | `rename_pin` 静默无效；`set_pin_properties` 把 pin 名改成自动名（下游 symbol/网表端口跟着变） | 设计侧（`schematic.py:615-637`） | 待设计修 |
| **P-074** | P3 | spec 表格写 pin 索引 `xy`、实现要 `x`/`y`，照表格写必报 `command N invalid: 'x'` | 设计侧（spec/实现二选一） | 待归属 |
| **P-069** | — | **复验通过**：LVS 拿到 `correct`（runset 与 deck 两条入口都好） | 设计侧（已修） | 建议销案 |
| **P-070** | P2 | 蒙特卡洛：只能读结果、不能驱动；等产品定"支持 or 明确不做" | 待决策 | 未关闭 |
| R7-O-01…11 | — | TB/环境/测量口径类 11 条（含"子进程覆盖率未合并"） | 测试侧 | 见 `round7-缺陷清单-其他.md` |

## 7. 覆盖率（真实数字与明缺口）

**本轮单跑（`run_main_coverage.ps1`，含离线三层 + standalone TB + 11 包 direct + 真机 TB + 注册 + S11）**：

```
第二次运行（TB 修好后，全部步骤通过）：
语句 67.31%（missing 5612 / 17168）   分支 49.72%（missing 3005 / 5976）   combined 62.77%   模块 56
第一次运行（3 个步骤 rc=1：standalone TB 的 work-root 假红 + S11 假 pin）：
语句 67.57%                          分支 50.08%                          combined 63.05%
```

证据：`test/artifacts/evidence/cov-main/coverage-main-strict.json`（最新）、`round7/coverage-main2.log`（含"全部步骤通过"与 meta：HEAD/diff sha/dirty）、`round7/coverage-main.log`（第一次）。
两次数字几乎相同 ⇒ 说明那 3 个 rc=1 的步骤**不是**覆盖率缺口的主要来源（它们的数据在失败前也已被采集）。
> 补充口径：该次采集发生在新增离线用例 `test_upper_layer_import_contract.py`（+6 例）**之前**；
> 新增用例只扫 `src/` 源码、不执行新的产品路径，故 `src/` 覆盖率数字不受影响，但引用时请以
> `coverage-main2.log` 的 meta（HEAD/diff sha）为准。

**未覆盖最多的模块（本轮实测，前 8）**：

| 模块 | 覆盖率 | 未覆盖语句 |
|---|---|---|
| `src/common/ssh.py` | 36.1% | 716 |
| `src/common/paramiko_backend.py` | 54.9% | 427 |
| `src/register/server.py` | 41.1% | 380 |
| `src/pyapi/packages/maestro.py` | 74.5% | 339 |
| `src/server/supervisor.py` | **0.0%**（测量口径问题，见下） | 335 |
| `src/pyapi/packages/_spectre_util.py` | 40.6% | 306 |
| `src/register/flow.py` | 59.0% | 277 |
| `src/pyapi/packages/layout.py` | 71.6% | 246 |

**必须同时声明的三条口径**（否则数字会被误读）：

1. **`supervisor.py` 的 0% 是测量问题**：它的离线用例（`test_supervisor_process.py`/`test_supervisor_internals.py`）本轮全绿，
   但被监督体跑在**子进程**里，而 runner 未开子进程覆盖率（`COVERAGE_PROCESS_START`）⇒ 数字低估。已记 R7-O-11，下一轮修。
2. **不同口径的数字不可混用（这点必须写清楚）**：
   - 本轮 = `run_main_coverage.ps1` **单跑**（离线 L0-L2 + standalone TB + 11 包 direct + 五接口 + 注册 + S11）→ **67.57% / 50.08%**；
   - 历史 79.31%/69.88%（离线三层）与 86.60%/77.39%（离线+真机）出自**合并采集**：除 runner 的步骤外，
     还并入了 ssh / paramiko / supervisor / register 的**定向 coverage 运行**
     （`test/artifacts/tmp/cov-{api,ssh,pmk,sup,reg,semi-ssh}*.data`）。runner 默认步骤**不含**这些定向运行，
     所以本轮数字更低——**差值主要来自采集范围，而不是"覆盖率掉了"**（同一个 `src/`，同样的 1725 例离线全绿）。
   - `test/reports/coverage-per-module-branch-2026-09-23.md` 的 77.22%/68.03% 是第三种（该轮合并）口径。
   - **立项要求**：下一轮把定向运行并入 `run_main_coverage.ps1` 的默认步骤（或提供 `--with-uplift` 开关），
     让"单跑"与"合并"两个口径都可一键复现，避免每轮都要解释一次差值。
3. **明确不声称 100%**，也**不声称"已覆盖 spec 全部条款"**：§8 列出本轮明缺口。

## 8. 仍未覆盖 / 不可声称（防止审核驳回的诚实清单）

| # | 未覆盖项 | 现状 | 说明 |
|---|---|---|---|
| G1 | **蒙特卡洛驱动** | 无实现（P-070 待口径） | 只有"读回 MC 结果"的解析用例 |
| G2 | **后仿 / PVT / 蒙卡** | 未覆盖 | 本轮只做前仿（AC/TRAN）+ DRC/LVS；后仿需寄生提取（PEX 未跑） |
| G3 | **真实 100 台机器** | 用 100 个协议级 fake 替代 | scale-100 是 fake fleet；真机侧只有 8 实例 |
| G4 | **>2 跳拓扑** | jump + SOCKS5 代理叠加已测（视为通过）；3 跳以上未测 | — |
| G5 | **自建版图的 LVS `correct`** | 未做到（脚本版图无布线 → `incorrect`） | `correct` 只在复用既有真实 cell（CMP_LIB/inv2）时成立 |
| G6 | **Linux 客户端只跑离线层** | 真机/半真机仍只在 Windows 客户端跑 | 三层里 Linux 只覆盖第 1 层 |
| G7 | **子进程覆盖率** | 未合并（supervisor 等被低估） | 见 R7-O-11 |
| G8 | **GUI 交互**（真实点击/对话框/截图对比） | 仅探针级：`gui_display_probe` + `symbol/maestro_screenshot_probe` 本轮已跑（截图 parity PASS），但没有"点击级"用例 | 交互类只做到"能定位窗口 + 截图"，不做真实鼠标点击 |
| G9 | ~~半真机层探针未复跑~~ **本轮已关闭** | **32/32 探针本轮复跑（§3）**，并新增表驱动入口 `run_semi_probes.py` | 以后每轮至少整层一次 |
| G10 | **maestro 全流程（ADE/多 corner）** | 仅有包级 e2e 与历史探针 | 本轮未做"多 corner 扫描 + 结果比对"整链 |

## 9. 交付物与下一步

**本轮交付**：本报告、`round7-缺陷清单-上层.md`、`round7-缺陷清单-其他.md`、`round7-TB修正.md`、
`round7-spec覆盖矩阵.md`（含机器核对 §14 + **逐行核账 §15**）、`问题登记.md`（第七轮条目）、
`test/reports/bugs/`（4 张未关闭卡片）、新增半真机入口 `test/shared/runners/run_semi_probes.py`、
新增逐行核账工具 `test/shared/runners/audit_spec_matrix_evidence.py`、新增离线用例
`test/offline/unit/test_upper_layer_import_contract.py`。

**下一步（按优先级）**：

1. 等 P-073 修好 → 重跑 `design_iterate_tb`（两条红应自动转绿）+ `schematic_pin_ops_probe`；
2. 补 G7：cov runner 加子进程覆盖率，重算 `supervisor/ssh/register` 的分子；
3. 补 G5：让一个 `correct` 的 LVS 走**自建流程**（需要把版图真有布线/端口层的最小单元做出来）；
4. 让 Linux 客户端也跑半真机/真机层（G6），当前 Linux 只覆盖离线层；
5. G2/G10 需要产品先明确后仿/corner 口径再投入。

## 10. 本轮"补测试"专项（对着缺口动手，而不是只记录）

| 缺口 | 动作 | 结果 |
|---|---|---|
| 设计迭代链无 TB（"改图→二次出图→版图→仿真"整链） | 新增 `test/live/flows/design_iterate_tb.py`（数据驱动：网表由 `schematic.read` 回读的连接+参数现场拼装） | 轮 1 全 PASS；轮 2 数值断言成立（带宽 2.24GHz→446.7MHz）；改图 pin 两条红=P-073 |
| pin 原子操作无攻击面 | 新增 `test/semi/probes/schematic_pin_ops_probe.py`（write 自报 / read / symbol / DB 四角度对表） | 抓到 2 条缺陷（P-073）；`delete_pin` 作为正对照 |
| 半真机层无固化入口 | 新增 `run_semi_probes.py`（32 探针表 + 依赖说明） | 整层 32/32 green |
| spec 矩阵四行引用**已删除**的证据（A17/C1/E8/G7） | 逐行核账工具 `audit_spec_matrix_evidence.py`；修正 3 行路径、**G7 用新离线用例补回** | 缺失证据行 4 → **0**；§15 列出 110 行"历史证据（本轮未复跑）"，不再冒充本轮 |
| work-root 新口径下 standalone TB 起不来 | `semantics_tb` / `fault_injection_tb` 改"每 case 子进程" | 10/10 + 8/8 绿 |
| scale-100 负向对照空转 | 负向对照改子进程（`scale100_negative_control.py`） | 5/5，负向对照**仍能抓到错答** |
