# 第五轮 · BUG 清单（按层分门别类，送修版）

> 口径：只收**本轮（第五轮）**新发现 + 上轮遗留的本轮复验结论；每条都指向可复查证据与"修好后会自动转绿"的 TB/探针。
> 台账唯一来源：[问题登记.md](问题登记.md)（本文件是**按层重排的送修视图**，编号与台账一致）。
> 状态图例：**待修** = 已复现、有 TB 钉住；**已修（测试侧）** = 本轮测试侧已改；**已闭环** = 本轮复验通过。
>
> **本文件是"单文件总览"**；逐条详情（含 `file:line`、复现命令、修复建议、验收判据）另见两份分层清单：
> [第五轮-缺陷清单-上层.md](第五轮-缺陷清单-上层.md)、[第五轮-缺陷清单-其他.md](第五轮-缺陷清单-其他.md)。
> 三份文件如有出入，**以 [问题登记.md](问题登记.md) 与证据文件为准**。

## 0. 按层汇总（**2026-09-24 修复验证后更新**）

> **本轮修复已验证**：P-052/P-053/P-054/P-055/P-056/P-059/P-061/P-062/P-066/P-067/P-071 与
> P-068（环境问题）全部红转绿/关闭；**P-048 重判为口径问题（非产品缺陷）**。
> 详见 [round6-修复验证报告.md](round6-修复验证报告.md) 与 [bugs/README.md](bugs/README.md)（当前**未关闭 3 条**：
> P-049 / P-069 / P-070；P-060 已由测试侧闭环 —— calibre 已进常驻套件，`run_all_http` **11 套包全绿**）。
> 下表改成"**仍未关闭**"的口径。

| 层 | 条数 | 编号 | 最高级别 | 一句话影响 |
|---|---|---|---|---|
| 上层业务包（calibre / maestro） | 3 | **P-069**（LVS 全链跑不通）、**P-070**（蒙卡能力缺失）、**P-071**（LVS 枚举不一致） | P2 | LVS 段给不出确定结论 / 蒙特卡洛不能驱动 / 同一结论两种枚举值 |
| 源码·出参 | 1 | **P-049** | P2 | 非有限浮点缺统一防线（端到端未复现） |
| ~~控制面 / 进程管理~~ | — | ~~P-048~~ | — | **重判：口径/用法问题（非产品缺陷）** —— spec 要求的是"运行期不自动读文件 + 管理端点显式 reload"；standalone 业务面只能重启，属测试台用法 |
| ~~测试侧（覆盖缺口）~~ | — | ~~P-060~~ | — | **已闭环**：常驻注册表补 calibre 事实 + 新增 `test/live/packages/calibre_e2e_tests.py` 并入 `run_all_http`（11 套包全绿） |
| **合计（仍未关闭）** | **3** | P-049 / P-069 / P-070 | — | — |

## 1. 上层业务包

> 说明：下面保留**第五轮原始送修条目**（含已修复的 P-052/053/054/059/061/062/066/067），
> 便于对照原始判据；**当前状态一律以 §0 汇总 + [bugs/README.md](bugs/README.md) 为准**。

| ID | 包 | 级别 | 问题（根因锚点） | 证据 | 修好判据 |
|---|---|---|---|---|---|
| **P-069** | `calibre` / CDL 导出链 | **P2（功能不可用）** | **LVS 全链跑不通**：`si -batch`（auCdl）对 PDK 器件失败（`hnlCDLParamList`/`hnlCDLFormatInst` 缺失）→ 无源网表 → `calibre.lvs` 只能 `NOT COMPARED`；用户 2026-09-24 改判为产品缺陷 | 真机 `round5-main/s11-flow2.log`、`calibre-lvs.json`、`calibre-drc.json`（DRC 正常对照）；探针 `calibre_package_http_probe.py --kind lvs` | 含 PDK 器件的 cell 能导出可用 CDL，`calibre.lvs` 给 **CORRECT/INCORRECT** 的确定结论；S11 `lvs` 阶段 PASS |
| **P-052** | `schematic` | P2 | `set_instance_params` 写的是**母单元 cell 级 CDF 默认值**（`schematic.py:475-495`）：给实例设参后 `analogLib/res.r` `1K`→`777`、`tsmcN65/nch_25.w` `400n`→`3u`，**共享库被污染**（会话内可见、跨会话不落盘） | 探针 `test/semi/probes/shared_cdf_pollution_probe.py` → `round4-probes/round4-shared-cdf-pollution.json`（含 before/after + peer 会话对照 + 还原） | 探针 verdict 不再是 `same-session-only`；SerDes 场景连跑不再改动 cell 默认值 |
| **P-053** | `spectre` | **P1/P2** | AC 结果链路两处断：① `parse_psf_directory` 只认 `ac.ac`/`*.ac.ac`，分析名为默认 `ac1` 时**整个 AC 数据集丢失**（`spectre.run` → `status=partial`、`analyses=[]`）；② 解析键带 `ac_` 前缀（`ac_freq`），而 `spectre.measure` 的 AC 指标默认 `x="freq"`（spec 明写）→ 按 spec 调用必 `ValueError` | 探针 `test/semi/probes/spectre_ac_pipeline_probe.py` → `round4-probes/round4-spectre-ac-pipeline.json`（A: ac1 丢数据；B: 显式前缀才拿到 `-0.00017 dB`）；场景侧 `round4-scenario/serdes/serdes-sim.json` | 用**默认分析名**跑 `spectre.run(parse=auto)` 能取到 AC 数据；`measure` 按 spec 默认 `x="freq"` 能返回指标 |
| **P-054** | `symbol` | P2 | 层次化 `symbol.generate` 收尾不关**子单元** symbol view → 同会话二次生成（或"改图→重生成"）必失败 `*Error* target symbol is open`（`_symbol_generate.py:143-144`） | 探针 `test/semi/probes/symbol_generate_hierarchy_handle_probe.py` → `round4-probes/round4-symbol-hierarchy-handle.json`；现场：SerDes 第 1 次 9/9 绿但留下 3 个 symbol 打开，第 2 次立刻失败 | 探针 `child-symbol-left-open` → 转绿；SerDes 场景**连续两次**全绿 |
| **P-059** | `calibre` | P2 | `read_results` 解析真实 Calibre **2025 `DRC.rep`** 失效：① 逐规则计数只认旧格式 → `by_rule={}`（36 条违规 / 27 条规则全丢）；② 总数只认旧串 → `None`；③ 把头部 `RUNTIME WARNINGS` 的提示当违规（`rule="Cell"`/`cell="operation"`） | 真机 `round5-main/calibre-drc.json`；裁剪样本 `test/shared/fixtures/calibre_drc_rep_sample.txt`；离线 TB `test/offline/unit/test_calibre_parsers.py`（**有意红**，6 条） | 该 TB 6 条转绿；`read_results` 能给出真实 `by_rule`/总数且 `first_offenders` 无垃圾条目 |
| **P-061** | `calibre` | P2 | 阻塞轮询对"**工具已死 + 日志终止性 ERROR**"不快失败：`lvs.log:21115 ERROR: Can not open source netlist file`，工具 2 秒退出，但 `calibre.status` 返回 `unknown`、`failure_kind=null`，blocking 调用一直等到超时（实测 >9 分钟被手动终止） | `test/offline/unit/test_calibre_job_state.py`（**有意红** 2 条）；真机 `round5-main/calibre-lvs-fastfail.json` | 该 TB 转绿；同样的输入错误在**秒级**返回结构化失败 |
| **P-062** | `calibre` | P2 | `read_results` 把真实 LVS 结论截成半个词：报告/日志是 `LVS completed. NOT COMPARED.`，正则 `LVS completed\.\s*(\w+)` 只吃到 `NOT` → `status="not"`（既非 correct/incorrect 也非 not_compared）；`counts` 恒空（真报告是**表格**） | 真机 `round5-main/calibre-lvs.json`；样本 `test/shared/fixtures/calibre_lvs_rep_sample.txt`；TB `test_calibre_parsers.py` | 该 TB 转绿；`status` 属已知枚举、`counts` 能解出表格 |

## 2. 顶层（HTTP 业务面）

| ID | 级别 | 问题（根因锚点） | 证据 | 修好判据 |
|---|---|---|---|---|
| **P-055** | P2 | 已定义路径 + 错误方法返回 **404**，spec《顶层》§3 要求 **405 + `Allow`**：`server/api_server.py:127-161`（`do_GET` 兜底 404）、`:163-166`（`do_POST` 兜底 404）。真机实测 `GET /api/operation`、`POST /health`、`POST /help` 全 404 且无 `Allow`；**控制面同规则已实现**（`PATCH /api/register` → 405 + `Allow`，`test_registration_server.py:737-764`） | 真机 `round5-live-api/business-port-surface.json`；离线 TB `test/offline/unit/test_api_server_method_not_allowed.py`（**3 红 2 绿**） | 该 TB 3 条转绿（405 + `Allow` 含该路径真实方法集） |

## 3. 控制面 / 进程管理

| ID | 级别 | 问题（根因锚点） | 证据 | 修好判据 |
|---|---|---|---|---|
| **P-056** | **P1（Linux 专属）** | `supervisor._force_kill_tree` 是 `@staticmethod` 却在 POSIX 分支调 `self._signal_process_group(...)` → `NameError`（`src/server/supervisor.py:280-307`）。Windows 走 `taskkill` 正常；Linux 上**进程组既收不到 SIGTERM 也收不到 SIGKILL** | Linux 3.9.25 / 3.14.6 各 3 条既有用例红：`test_process_lifetime.py::TestPosixBusinessProcessLifetime::test_dispose_kills_process_group_descendant`、`test_supervisor_internals.py::TestForceKillTree::test_posix_group_{sigterm_success_returns,sigkills_after_sigterm_timeout}`；日志 `round5-linux-client/{py39,py314}-final2.log` | 上述 3 条在 Linux 转绿；spec《控制面与业务面》§3 的"restart 强杀覆盖业务进程组及 SSH 后代"成立 |

## 4. 测试侧（TB / 口径 / 覆盖缺口）

| ID | 级别 | 问题 | 处置 / 证据 |
|---|---|---|---|
| **P-057** | 口径 | 深嵌套 JSON 拒绝行为随解释器变化：3.9 在 ~1000 层 `RecursionError`→`400 invalid JSON body`；3.14 到 20000 层仍**正常解析**（业务层随后按普通请求处理）→ 旧断言把 CPython 实现细节当产品契约 | **本轮已改口径**：long-int 仍钉 `invalid JSON body`；deep 只钉"400 或 200 + 可解析 JSON 响应壳 + 无断连"，并新增 **200000 层必须 400 invalid JSON body**（两解释器一致）。深度矩阵 `round5-linux-client/json-depth.txt`；**产品建议**：若要跨版本统一，加显式深度上限 |
| **P-058** | 测试侧 | 4 条 **Windows-only** 用例在 Linux 无守卫（`test_windows_appdata_default` → pathlib 在 Linux 抛 `NotImplementedError`；`test_windows_forward_*` 三条测 `if _IS_WINDOWS:` 分支） | **已修**：加 `skipUnless(sys.platform == "win32")` / `skipUnless(ssh_mod._IS_WINDOWS)`；Linux 复跑两文件 2/2 全绿、Windows 行为不变（见 TB 改动清单 R4） |
| **P-060** | 覆盖缺口 | `calibre` 包此前 **0 真机覆盖**：常驻注册表无 `role.command.calibre.bin`、`test/live/packages/` 无 calibre 套件、`run_all_http.py` 的 SUITES 不含 calibre | **本轮已部分补齐**：专用注册表 `test/artifacts/env/s11-calibre/` + 8128 业务面 + `test/semi/probes/calibre_package_http_probe.py`；打通 `check_env → drc → status → read_results`（并因此发现 P-059/P-061/P-062）。**仍缺**：calibre 进 `run_all_http` 常驻套件、LVS 真通过（受 §5 口径约束） |
| **P-063** | 测试侧（并发假红） | 注册类离线用例依赖**机器级端口区间 65081–65130**（`register.probe.allocate_local_port` → `local_port_free`）：同机并发跑测时分配失败 → `validate()` 直接 failed、reservation 没写，产生**与产品无关的假红** | 对照实验：**独占**跑 = 11 红（全为有意钉住，`round5-main/offline-final6.xml`）；**2 路并发** = 各 29 红，其中 `test_register_flow` 15 + `test_reservation` 3 是假红（`round5-main/conc-A.xml`/`conc-B.xml`）；4 路并发 = 30 红（`offline-final5.xml`）。**建议**：注册类用例统一把 `local_port_free`/`allocate_local_port` 打桩/指向测试私有区间；在此之前**离线全量必须独占跑** |
| **P-064** | 测试基建（**已修**） | **并发 pytest 会话互删临时目录**：旧 `test/conftest.py` 在会话结束时删掉 `%TEMP%` 里"本会话开始后新出现"的所有 `vb-*` 目录 → 并发跑测时删掉**别的会话正在用**的 `vb-key-*`（19 条假红：`test_register_flow` 15 + `test_reservation` 3 + `test_credential_routing` 1） | 机制演示 `round5-main/p064-mechanism-demo.txt`（旧逻辑确定性删掉并发目录）；修复前同命令 **30 failed**（`unit-only-order-check.xml`）→ 修复后 **11 failed**（`unit-only-tempfix2.xml`）；**并发回归**两路各 `11 failed / 0 error`（`conc-new-A/B.xml`）；三层口径 `offline-3layer-tempfix.xml` = 11 红 / 9 skip | **已修（测试侧）**：每会话一个进程私有 temp 根 `vbsession-<pid>-<rand>`（conftest 导入时立即生效，只清自己子树，前缀不匹配 `vb-*`）。**送修方无需动作**，但复算"11 红基线"请在修复后的代码上跑 |
| **P-065** | 测试侧（**已修**） | 跨用例串扰：`test_ssh_edges::test_openssh_forward_without_user_targets_bare_host` 把 `subprocess.Popen` 全局打桩且只留最后一次调用，被其它用例遗留线程覆盖 → `'u@server-a' != 'server-a'` | `unit-repro-check3.xml`（12 红）→ 修好后 `unit-final-a.xml`（11 红）；对照 `unit-no-regflow-check.xml` | **已修（测试侧）**：只拦带本地端口 `6503` 的调用；断言未放宽 |
| **P-068** | 真机·多用户（**归属待定**） | 共享 PDK 库 `adc_sar`：`vbuser1` 能写 M1 矩形，`vbuser2` 报 `Invalid layer/purpose ("M1" "drawing")`（能读不能写；自建 cell 也失败） | TB `test/live/flows/multiuser_layout_handoff_tb.py` → `round5-realscen/multiuser-layout-handoff.json`（7/10）；排查记录 `round5-真实场景-补充.md` | 需要**产品侧**（LPP 解析是否依赖会话先前动作）或**环境侧**（B 的 Virtuoso 启动是否需显式打开 PDK tech）定位；测试侧已固化判据 |

## 5. 上轮遗留 / 本轮复验结论（只列被本轮明确判定的）

| ID | 上轮状态 | 本轮结论 | 证据 |
|---|---|---|---|
| P-044 | layout 锁误判 + 写句柄不关 | **已闭环**：layout 包 E2E 与 GDS 段跑到尾（10/10 PASS）；P-044 探针复验 | `round5-main/run-all-http-results.json` |
| P-047 | `verilog.import` 静默依赖 cwd 的 `cds.lib` | **已闭环**（环境侧"启动即完整" + 包 E2E verilog rc=0） | 同上 |
| P-050 | daemon 伪 stdin 下不可导入（Linux 采集期 6 errors） | **已闭环**：Linux 3.9.25 / 3.14.6 都跑完整离线三层、0 collection error | `round5-linux-client/{py39,py314}-final2.log` |
| P-051 | `layout.gds` 远端发布不建目录 | **已闭环**：A/B 复验（新目录成功、远端 4096 B）+ 4 条路径边界攻击 | `round4-scenario/serdes/serdes-gds.json`、`round4-probes/round4-gds-path-edges.json` |
| P-043 | py2.7 daemon 缺 coding cookie | **已闭环（协议级）**：真 Python **2.7.18** 探针 5/5（listen / token / log_level / log_max_bytes / watchdog）；**3.6.8 首次 5/5** | `test/artifacts/evidence/py27-daemon-probe-green.json`、`py36-daemon-probe-green.json` |
| P-048 | 独立启动的业务面不重载 registry | **仍待设计修**（P2）：本轮改用"重启业务面"规避，未复现新证据 | 台账 P-048 |
| P-049 | 出参缺"非有限浮点"统一防线 | **仍待设计修**（代码路径已证、端到端未复现） | 台账 P-049 |

## 6. 明确不立案（本轮判定为"不是缺陷"）

| 现象 | 判定 |
|---|---|
| ~~`si -batch`（auCdl）对 PDK 器件失败~~ **已改判为缺陷 P-069**（2026-09-24 用户判定："这不就是业务包本身跑不通？"） | **立案**：见 §1 的 **P-069**——Calibre LVS 全链在含 PDK 器件的真实设计上给不出结论（`NOT COMPARED`），属业务包功能不可用，不再是"环境/配方口径问题" |
| `twouser_same_view_probe --token-b vb-vbs11` → `invalid token` | 笔误（registry 里是 `vb-s11`），非缺陷 |
| 注册六步 TB 不带 `--local-mode` 直接跑 → step1 `daemon_port >= 1` | 用法问题（远端口径必须给具体端口），非缺陷 |
| py3.14 上 `test_skill_tunnel_rejects_proxy` 红 | **环境缺 `PySocks`**（`pip install PySocks` 后绿），非产品缺陷 |
| `test_ssh_edges.py::TestOpensshDownloadAttempt...` 高负载下偶发 StopIteration | **用例时序脆弱**（mock 的 Popen 序列与"≤3 次重试"不匹配）：本轮已改为 callable 并加"重试有界"断言 |
