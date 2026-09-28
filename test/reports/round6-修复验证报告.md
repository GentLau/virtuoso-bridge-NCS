# 第六轮 · 修复验证报告（2026-09-24）

> 触发：设计侧提交 `b45864a`（P-055/P-056 + host-key 重探）、`f5f1813`（上层 A-0~A-5 + P-066/P-067）、
> `af8e1e0`（`read_results` 解析 `DRC_RES.db`，恢复 `first_offenders`）、`cee02df`（句柄复检 R1/R2/R4/R5 +
> **P-071** + 撤回 `symbol_generate` 过度关闭）。
> 口径：**只认"红转绿 + 无回归"**，不认"设计说改好了"；每条都给可复查证据。
> 测试侧动作：重启三个业务面（8127/8128/8131）让它们加载新代码；离线/半真机/真机三层重跑。

> ⚠️ **本轮踩到的最大坑（见 P-048）**：第一次验证时业务面还是 11:10 启动的旧进程，
> 于是 `af8e1e0` 的 `first_offenders` 看起来**完全没生效**（返回 `[]`）、`cee02df` 的行为也不是最新的。
> **重启业务面后**：`first_offenders` 变成 **20 条真实违规**、P-071 转绿。凡"改完要验"的场景，
> **先重启业务面**，否则会把已修好的实现误判成没修（P-048 的代价，已写进 P-048 卡片）。

## 1. 逐条结论

| ID | 修复前的判据 | 本次验证结果 | 证据 |
|---|---|---|---|
| **P-055** 405+Allow | `test_api_server_method_not_allowed.py` 3 红 | ✅ **转绿**（离线三层 0 红；含两条护栏） | `round6-verify/offline-mine.xml` |
| **P-056** POSIX 强杀 | Linux 3 条 `NameError` 红 | ✅ **转绿** | `round6-verify/py39.log`、`py314.log` |
| **P-052** cell CDF 污染 | 探针 verdict=`same-session-only` | ✅ **verdict=clean**（before/after 默认值不变，新实例继承原默认；peer 会话干净） | `round6-verify/round4-shared-cdf-pollution.json` |
| **P-053** Spectre AC 链路 | 默认分析名丢数据 + measure 默认 x 不可用 | ✅ **verdict=clean**（`analyses=[\"ac\"]`、`has_ac_data=true`、spec 形状可用） | `round6-verify/round4-spectre-ac-pipeline.json` |
| **P-054** 层次化 symbol 二次生成 | 二次生成必失败 | ✅ **verdict=clean**（leaf 生成后 CLOSED、二次生成 ok、无残留） | `round6-verify/round4-symbol-hierarchy-handle.json` |
| **P-059** Calibre 2025 DRC.rep 解析 | `by_rule={}`、总数 None、垃圾 offenders | ✅ **转绿**：真机 `read_results` 给出 `rules_checked=1737`、`total_results=36`、**27 条真实规则计数**、`first_offenders=[]` | `round6-verify/calibre-drc.json` |
| **P-061** 阻塞轮询不快失败 | 工具 2 秒死、状态 unknown、等到超时 | ✅ **转绿**：S11 LVS 以 `status=failed, failure_kind=input`（秒级，日志终止标记）返回 | `round6-verify/s11-with-calibre/s11-lvs.json` |
| **P-062** LVS 结论截半 + counts 空 | `status="not"`、`counts={}` | ✅ **转绿**：counts 已解出（ports 1/4、nets 5/4、inst 2/1）、结论不再是半个词；原先残留的"枚举不一致"由 `cee02df` 一并修掉（见 P-071） | `round6-verify/calibre-lvs.json` |
| **P-066** `skill_value` 错误类型 | 抛内部 `AttributeError` | ✅ **转绿**（改为显式 `TypeError`） | `round6-verify/offline-mine.xml` |
| **P-067** 未加引号 `Parameters:` 丢参数 | 只解出第一个参数 | ✅ **转绿**（整行拼回，两个参数都在） | 同上 |
| **P-068** 第二用户画不了版图 | B 报 `Invalid layer/purpose` | ✅ **已关闭（环境问题）**：B 会话绑的是 `cdsDefTechLib`(54 层)、A 是 `tsmcN65`(216 层)；bind 后 **S16 12/12**；另发现该绑定是**会话级**（Gent 三会话仍 `nil`），已记为环境待固化项 | `round6-fixcheck/s16-handoff-reverify2.json`、`round6-verify/s16-handoff.json` |
| **P-069** LVS 全链跑不通 | LVS 无源网表 | ❌ **仍未修**（本轮新立案）：S11 `lvs` 失败为 `failure_kind=input`；专用环境提供 CDL 时能跑完整流程但结论 `NOT COMPARED` | `round6-verify/s11-with-calibre/s11-lvs.json`、`round6-verify/calibre-lvs.json` |
| **P-070** 蒙特卡洛能力缺失 | 只能读回、不能驱动 | ❌ **仍未修**（待设计侧定口径） | 见 `bugs/P-070-monte-carlo-missing.md` |
| **P-071** LVS 枚举不一致 | 日志路径 `not compared` | ✅ **已修复**（`cee02df`）：契约 TB 3/3 转绿 | `test/offline/unit/test_calibre_verdict_consistency.py` |
| **`af8e1e0`** DRC_RES.db / `first_offenders` | 修复后 `first_offenders` 曾返回 `[]` | ✅ **有效**（重启业务面后）：`first_offenders=20` 条真实违规（rule/cell/bbox），`by_rule=27`、`1737/36` | `round6-verify/calibre-drc-final2.json` |
| **P-048 / P-049** | 业务面热更新 / 非有限浮点 | ❌ 未在本轮提交范围内，仍待设计修 | 台账 P-048/P-049 |

## 2. 三层回归结果（防"修一条坏一片"）

| 层 | 结果 | 证据 |
|---|---|---|
| 离线 Windows（定版） | **1722 项 / 0 红 / 0 error / 7 skip → 1715 passed** | `round6-verify/offline-final.xml` |
| 离线 Linux 3.9.25 / 3.14.6 | **各 1703 passed / 0 failed / 19 skip**（`cee02df` 后重跑，rc=0） | `round6-verify/py39-final.log` / `py314-final.log` |
| 半真机 | P-052/053/054 三条探针 **verdict=clean** | `round6-verify/round4-*.json` |
| 真机·十套包 | **10/10 `all_passed=true`**（重启业务面到 `cee02df` 后重跑） | `round6-verify/run-all-http-results-final.json` |
| 真机·五接口 | vb-vblog / vb-vbuser1 / vb-vbuser2 / vb-s11 **各 5/5** | `round6-verify/final-five-*.json` |
| 真机·S16 两用户版图接力 | **12/12**（含工艺绑定自检） | `round6-verify/final-s16.json` |
| 真机·S2 role 分主机 | **5/5**（daemon→wsl-gent、command/file→w1-gent） | `round6-verify/role-split.json` |
| 真机·混合压测 6×6（本地+远真机） | **72/72，0 失败**，31.4s | `round6-verify/final-stress-6x6.json` |
| S11 工程链（定版） | lib/schematic/symbol/layout/gds **PASS**；**drc PASS**；lvs FAIL（`failure_kind=input` = P-069）；sim SKIP | `round6-verify/final-s11/summary.json` |
| **合并覆盖率**（`run_main_coverage.ps1` 重算） | **语句 91.97%（17255 statements）· 完整分支 83.85%（5900 branches）**；步骤失败只剩 `S11 full flow (LVS)` | `cov-main/coverage-main.{json,txt}`、`round6-verify/` |

## 3. 本轮测试侧的两处 TB 改动（都不是"为绿而改"）

1. **`symbol_e2e_tests.py`：旧契约断言过期**。`f5f1813` 明确把 P-054 的契约改成"目标只读打开不再拒绝，覆盖前 close 只读句柄"，
   而 TB 里 `generate on an open target must fail` 编码的是**修复前**的行为 → 首跑 10 套包里 symbol 失败。
   已按新契约改写并**收紧**为三条：① 调用成功；② `action=replaced`；③ 覆盖后 terminals 仍是 `{A,B,C}`；④ 只读句柄确实被关（能重新以 `"a"` 打开并保存）。
   改后 symbol 套件 8/8 通过、十套包回到 10/10（证据 `round6-verify/run-all-http-results.json`）。
2. **`role_split_tb.py`：token 改从注册表读**。TB 原来写死一个 token，换环境（`scenario-role-split` 的 `rolesplit` 用 `vb-s11`）会全红成 `invalid token`，看着像产品故障；
   现在 `--token` 缺省时从 `<work-dir>/registry.json[user].token` 读，显式传参仍优先。改后 S2 **5/5**。

## 4. 结论与下一步

* 本轮修复**有效**：9 条（P-052/053/054/055/056/059/061/066/067）逐条红转绿，三层无回归（除新钉的 P-071）。
* 仍在等设计侧：**P-071**（LVS 枚举一致，2 条红 TB）、**P-069**（LVS/CDL 全链）、**P-070**（蒙卡口径）、**P-048/P-049**（上轮遗留）。
* 测试侧自己的待办：**P-060 收尾**（把 calibre 探针升级成常驻套件并进 `run_all_http`；本次已先把 calibre 工具事实写进常驻注册表，S11 的 drc 因此转 PASS）、
  **P-068 的环境固化**（把 `techBindTechFile` 做进各用户会话初始化 + bring-up 自检）、py2.7 真 SKILL、真机 ≥6 分散用户 + 100 fake 的规模档、两项目全链。

---

## 5. 第二轮复验（提交 `a268d80`：R3 关闭失败显式上报 + R6 句柄不变量；2026-09-24 下午）

设计侧又推了 `a268d80`（`schematic.py` / `symbol.py` / `layout.py` 的 close 失败显式上报 + 句柄不变量写进注释/spec §3.2）。
按"先重启业务面、再复验"的口径重跑：

| 项 | 结果 | 证据 |
|---|---|---|
| 离线 Windows | **1723 项 / 0 红 / 7 skip**（含本轮我新补的 reload 语义用例） | `round6b-verify/offline-final.xml` |
| 离线 Linux 3.9.25 / 3.14.6 | **各 1703 passed / 0 failed / 20 skip**（rc=0） | `round6b-verify/py39.log` / `py314.log` |
| 半真机三探针（P-052 / P-053 / P-054） | **全部 verdict=clean** | `round6b-verify/round4-*.json` |
| 真机·十套包 | **10/10 `all_passed=true`** | `round6b-verify/run-all-http-results.json` |
| 真机·五接口（4 token） | **各 5/5** | `round6b-verify/five-*.json` |
| 真机·S16 / S2 / 压测 | **12/12 / 5/5 / 72-72 0 失败** | `round6b-verify/{s16,role-split,stress-6x6}.json` |
| Calibre DRC `read_results` | **1737 / 36 / 27 规则 / 20 条 `first_offenders`** | `round6b-verify/calibre-drc.json` |
| Calibre LVS `read_results` | **`status=not_compared`**，`log_counters.lvs_status=not_compared`（两路径同一枚举 = **P-062 + P-071 双绿**），counts 全解出 | `round6b-verify/calibre-lvs.json` |
| S11 工程链 | lib/schematic/symbol/layout/gds/drc **PASS**；lvs FAIL（`failure_kind=input`，= **P-069**）；sim SKIP | `round6b-verify/s11/summary.json` |
| 正常写路径是否出现"close 失败"噪声（R3 新逻辑） | 未见：十套包、S16、S11 的 layout/symbol/schematic 写路径全绿 | 同上 |

### 5.1 P-048 重判：**口径/用法问题，不是产品缺陷**（`test_supervisor_process.py::test_http_reload_picks_up_registry_file` 4/4 绿）

见台账"P-048 结论更新"：spec 明确"运行期不自动读文件 + 管理端点显式 reload"，**热重载本来就要手动发命令**；
差异只在于我们测试台用 **standalone** 业务面（没有控制面父进程通道）→ 只能重启。**已在环境文档 §3.3 写明两种形态的正确做法。**

## 6. 当前仍未关闭（3 条；P-060 已由测试侧闭环）

| ID | 归属 | 说明 |
|---|---|---|
| **P-069** | 设计侧 | LVS/CDL 全链（含 PDK 器件的源网表导出） |
| **P-070** | 设计侧（先定口径） | 蒙特卡洛能力（驱动 or 明确不做） |
| **P-049** | 设计侧 | 出参非有限浮点统一防线：**业务面已守住**，压测面 + daemon 3/27 两处仍是裸 `json.dumps`；已补离线 repro `test/offline/unit/test_output_json_safety.py`（3 红） |

**本轮测试侧闭环**：**P-060** —— 常驻注册表补 calibre 工具事实（S11 `drc` 转 PASS）+ 新增常驻套件
`test/live/packages/calibre_e2e_tests.py` 并接入 `run_all_http.py` → **11 套包 `all_passed=true`**
（`round6b-verify/run-all-http-final.log`）。

### 6.1 `stress_server` 清理 + P-049 口径更正（2026-09-24，按设计侧通知执行）

设计侧通知：**`src/server/stress_server.py`（测试专用压测壳）已从生产源码删除**，测试侧同步清理。已执行：

| 动作 | 内容 |
|---|---|
| 删除只测夹具的用例 | `test/offline/unit/test_stress_server.py`、`test_stress_server_endpoints.py` |
| 删除旧压测工具 | `test/shared/fixtures/stress_client.py`、`test/live/stress/http_mixed_stress_tb.py` |
| 删除引用已删模块的历史脚本 | `test/shared/archive/` 下 6 个（`composite_stress.py` / `log_file_verify.py` / `p2_extreme_gradient.py` / `stress_live.py` / `stress_multiuser.py` / `stress_multiuser_real.py`） |
| **新增生产面压测 TB** | `test/live/stress/production_face_stress_tb.py`：**直接压生产面** `POST /api/operation`（dispatch → basic 包 → 中层）。两种模式：① 缺省**自起**一个 `server.api_server`（临时 work-dir + local 注册表，零依赖，上传/下载文件在 TB 自己的临时目录里现造）；② `--base … --token …` 对接既有真机面（额外混 skill/gui/spectre）。实测：自起 4×4 = 16 轮 / 48 步 / **0 失败**；对接 8127 真机 6×6 = 36 轮 / **216 步 / 0 失败**（`round6b-verify/production-stress-{selfstart,real}.json`） |
| runner 引用 | `scenario.py` 两处 → 换成新 TB；`run_coverage.ps1` 移除 Windows mixed stress / WSL mixed stress / saturation profile 三处，改为一条 `production face stress (self-start)`（PowerShell 语法校验 0 错误） |
| 文档/README | `test/shared/README.md`、`test/shared/fixtures/README.md`、`test/live/stress/README.md`、`test/live/README.md`、`test/docs/用例分层与归口.md`、`test/docs/推荐测试环境.md`（S3）、`test/reports/覆盖度缺口.md`、`doc/测试覆盖报告.md` 全部同步；覆盖清单**不再包含**该模块 |
| 残留引用 | 只剩"说明它已删除"的注释 + **历史快照**（`test/reports/coverage-gaps-2026-09-22-v*.md`、`BUG清单-给工程师-第二轮.md` 等按日期的过程资产）。这些是当时的记录，**未改写**；如需一并清掉请说一声 |

**P-049 口径更正**（设计侧澄清）：① `stress_server` 那一路移出 P-049；② 业务面 `api_server._send` 已用
`dumps_strict` + 500 兜底（本 TB 保留一条**负控制**证明有效）；③ daemon 响应当前只含字符串，
裸 `json.dumps` 属**防御性加固、不立案**；④ **真正剩下的是上层**：`_spectre_util.py:189/196` 在某个 trace
**首个扫描点还没出现**时写 `math.nan`，`:321` 的 `psf_external()` 原样放行 → NaN 进上层出参。
新 repro（不需要缺样本 PSF 文件）：`test/offline/unit/test_output_json_safety.py` 用真实 PSF 文本复现
`vcm == [nan, 0.9]`、`iout.re == [nan, 0.0]` → **2 条红**（预期），业务面负控制 1 条绿。
**验收**：缺样本点给 `null`（或省略），出参整体可 `dumps_strict`。

**清理后离线三层复跑**：**1719 项 / 2 红（= 上述 P-049 新钉）/ 7 skip**，其余全绿
（`round6b-verify/offline-after-cleanup.xml`）。

### 6.2 一条环境观察（不是产品缺陷）

11 套包第一次跑时 `spectre_e2e_tests.py` 出现 **1 次** `1/1 tasks failed`；同一调用立刻复跑成功、
之后整套 11/11 全绿。当时机器上并行跑着 Linux 双解释器矩阵 + Calibre 真机任务（wsl-gent 被压满）。
⇒ 记录为**负载相关观察**，不是缺陷；跑真机套件时避免与其他重任务并行。

## 7. 第三轮：offline 快跑（2026-09-24 晚，工作区仍在重构）

**先答"offline 是不是更快"**：是。离线三层正常约 **3.5–4 分钟**（本轮 108s，因为大面积 setup error 提前结束），
而真机一轮（11 套包 + calibre + S11 + 五接口/压测）约 **15–20 分钟**。所以"先跑 offline 拿信号"是对的。

**本轮 offline 结果：1728 项 / 518 红** —— 但**不是 518 个问题**，按 traceback 归类是**同一个根因**：

| 项 | 事实 |
|---|---|
| 现象 | `RuntimeError: work dir already initialized`（例：`test_calibre_package.PackageTests::test_drc_blocking_completes` 的 `setUp` → `init_work_dir(self._wd)`） |
| 根因 | **工作区里未提交的** `src/common/paths.py`：删除了 `force` 参数与 `override_work_dir_for_tests()` / `reset_work_dir()`，docstring 改为"测试要新路径就起新进程" |
| 影响面 | **91 个测试文件**引用这三个 API；本层大量用例依赖"每个用例一个干净 work root" |
| 证据 | `round6b-verify/offline-latest.xml`（我按 traceback 分类：518/518 都是这一条）；代码 `src/common/paths.py:43-64` |
| 处置 | 立案 **P-072**（P2·阻塞测试），归属待定：①（建议）恢复测试钩子；② 明确"一进程一 work root"并给官方测试姿势，我适配 91 个文件 |

**同时确认的两条好消息**：

* **P-049 已闭环**：提交 `d892608` + `a2f9aac` 把 spec 改成"内部哨兵 / 对外 `null`"（与测试侧建议一致），
  代码在 `psf_external()` 收敛非有限值；我复跑 `test/offline/unit/test_output_json_safety.py` → **3/3 绿**。
* **P-069 有新提交**（`46278b4 feat(calibre): 官方 auCdl 源网表导出 + 参数面定为 deck 文件`，另 `8465fb7` 支持
  runset/params 不走 GUI）——**待真机验证**（要等这轮重构稳定 + 树能跑起来后，再跑 calibre LVS 链与 S11）。

**当轮未关闭（3 条）**：P-069（LVS/CDL，待验证新提交）、P-070（蒙卡口径）、**P-072（work-root 阻塞）**。

### 7.1 P-072 处置：按方案 ② 适配完成（2026-09-24 晚）

产品**坚持"一进程一 work root"**（`init_work_dir` 一次性；换路径报错；不提供测试钩子）。
测试侧按此口径改造，**不再换根**：

| 动作 | 内容 |
|---|---|
| 官方姿势 | `test/docs/工作根与测试姿势.md`：pytest 会话**绑定唯一一根**（`test/conftest.py` session fixture），用例级用 `registry.json` 重置做隔离；**路径敏感用例起子进程**；独立 TB/probe 作为入口在 `main()` 绑自己的根 |
| 机械迁移 | 28 个用例文件：**38 处** `init_work_dir(...)` → `work_root()`，**47 处**冗余绑定删除；修 3 处被误删导致的语法/内嵌脚本损坏（`test_new_core` / `test_probe` / `test_tunnel` / `test_workdir_contract`） |
| 语义修复 | `test_calibre_package`（去掉自带根）、`test_models_paths`（改用 `runtime_paths.work_root()`）、`test_config_snapshot_edges`（不再绑根）、`test_registration_server*`（共享根下只清自己的 `bug_reports/`）、`test_update_host_key_probe`（同一个根 + import 修正）、`test_middle_routing`（共享根下先清自己的 `tree/`）、`test_skillref_package`（自建 config 目录） |
| 抗残留 | `test_ssh_edges::test_failure_reports_combined_stderr_and_discards_stage` 的 `Popen` 计数按**本用例标识**（远端目录 / stage 路径）过滤，避免把别的用例遗留线程算进来（P-065 家族） |
| **结果** | **离线三层 1725 项 / 0 红 / 0 error / 7 skip**（约 4 分钟；`round6b-verify/offline-sharedroot4.xml`） |

**当前未关闭（2 条）**：**P-069**（LVS/CDL，待用新提交跑真机验证）、**P-070**（蒙卡口径待定）。
