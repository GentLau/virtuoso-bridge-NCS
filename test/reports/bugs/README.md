# `test/reports/bugs/` —— 未关闭缺陷的唯一跟踪视图

> 维护者：测试工程师（我）｜最近刷新：2026-09-28
> **这个目录回答一个问题：现在还有哪些 bug 没关、谁在等谁、修好的判据是什么。**

## 0. 三条规矩（动这里之前先看）

1. **权威事实在台账**：[问题登记.md](../问题登记.md)。本目录不重复分析，只做「未关闭项」的卡片与索引；
   送修视图（逐条 file:line / 复现 / 验收）在 [round7-缺陷清单-上层.md](../round7-缺陷清单-上层.md) 与
   [round7-缺陷清单-其他.md](../round7-缺陷清单-其他.md)。
2. **状态只能从这五个里选**：`待设计修` / `待测试侧` / `待归属` / `待决策` / `观察`。
   关闭时**不删卡片**：移到 [已关闭-近期.md](已关闭-近期.md) 并写一句「凭什么关的」（证据路径）。
3. **刷新方式**：改 `test/shared/runners/make_bug_cards.py` 的 `OPEN` / `CLOSED_RECENT` 段，
   然后 `python test/shared/runners/make_bug_cards.py`（幂等；`--check` 只校验不写盘）。

## 1. 未关闭（6 条）

| ID | 层 | 级别 | 归属 | 状态 | 一句话 | 卡片 |
|---|---|---|---|---|---|---|
| **P-038** | 其他（公共 / 打包） | P2（任何 3.9 客户端/CI 作业不可用；跨客户端一致性在 3.9 上不成立） | 设计侧（打包/依赖或 requires-python 口径） | 待设计修（已报 `bug-20260922T141119Z-vblog-5e939e33`） | 声明支持 Python 3.9，但裸装 3.9 无法导入（pydantic 求值 PEP 604 注解；pyproject 未声明 `eval_type_backport`） | [P-038-py39-pep604-needs-backport.md](P-038-py39-pep604-needs-backport.md) |
| **P-077** | 其他（注册 / 控制面） | P3（口径不一致：注册探测 vs 运行时；会绊住手写配置的用户） | 设计侧（定口径：探测接受 PATH 名 or spec 写明必须绝对路径） | 待归属 | 显式 `role.daemon.python` 传裸命令名（如 `python3`）时注册第 3 步失败；运行时可解析 PATH | [P-077-explicit-daemon-python-bare-name-rejected.md](P-077-explicit-daemon-python-bare-name-rejected.md) |
| **P-076** | 上层（spectre 包；第二嫌疑：中层持久 shell） | P2（间歇性挂起；占住 in_flight 线程，客户端只能杀进程） | 设计侧（上层 spectre 包的 run 路径：等待完成/递归下载） | 观察（1 次复现，待设计侧定位） | 间歇：`spectre.run` 请求永不返回（spectre 已 0 error 跑完；服务端线程不释放，需重启业务面） | [P-076-spectre-run-request-never-returns.md](P-076-spectre-run-request-never-returns.md) |
| **P-075** | 上层（layout/gui 包） | P1（会话被挂死；多用户/GDS 后继续操作的流程直接卡住） | 设计侧（上层 layout.gds / strmout 调用路径） | 待设计修 | `virtuoso.layout.gds` 导出后会话残留模态对话框（"Stream out translation complete"）→ 同会话 SKILL 通道挂死，必须重启实例 | [P-075-gds-export-modal-blocks-session.md](P-075-gds-export-modal-blocks-session.md) |
| **P-073** | 上层（schematic 包） | P2（写操作语义错误；set_pin_properties 静默改坏用户数据） | 设计侧（上层 schematic 包 `_atomic_skill`） | 待设计修 | 原理图 pin 原子操作与「pin 有效名」不一致：rename_pin 静默无效、set_pin_properties 把 pin 名改成自动名 | [P-073-pin-atomic-ops-name-mismatch.md](P-073-pin-atomic-ops-name-mismatch.md) |
| **P-070** | 上层（maestro/spectre 包） | P2（能力缺失） | 待决策（产品口径：支持驱动 MC or 明确不做）→ 设计侧实现/写 spec | 待决策 | 蒙特卡洛能力缺失：只能读回 MC 结果，不能驱动 MC 仿真 | [P-070-monte-carlo-missing.md](P-070-monte-carlo-missing.md) |

> 优先级口径：**P1** = Linux 侧资源/安全或核心指标链路断（P-056、P-053）；
> **P2** = 真实设计流会给出错的/空的结果，且多数**静默**；**P3/观察** = 非阻塞但建议顺手修。

## 2. 本轮/近期已关闭（46 条，保留记录）

| ID | 事项 | 关闭依据（证据） |
|---|---|---|
| P-043 | py2.7 daemon 缺 coding cookie | 真 py2.7 探针 5/5（`py27-daemon-probe-green.json`） |
| P-044 | layout 写锁误判 + 句柄不关 | layout 套件 10/10；陈旧锁不再挡写；两用户同视图 GREEN |
| P-045 | 「并发压测打挂 CIW」 | **撤回**（归因错误，真因 P-046） |
| P-047 | `verilog.import` 依赖 cwd 的 `cds.lib` | 包 E2E verilog rc=0（`run-all-http-results.json`） |
| P-050 | daemon 模块在伪 stdin 下不可导入 | Linux 3.9/3.14 完整三层、0 collection error |
| P-051 | `layout.gds` 远端发布不建目录 | A/B 复验 + 4 条路径边界攻击；S11 gds PASS |
| P-058 | 4 条 Windows-only 用例缺 Linux 守卫 | 加 `skipUnless`；Linux/Windows 双平台复跑绿 |
| P-063 | 注册类离线用例受机器端口区间影响 | 打桩端口分配 + P-064 修复后：端口压力下整目录 **11 红基线**（`p063-d4-fullunit-pressure.xml`） |
| P-064 | 并发 pytest 会话互删临时目录 | 改每会话私有 temp 根；2 路并发各 11 红（`conc-new-{A,B}.xml`） |
| P-065 | `subprocess.Popen` 全局打桩跨用例串扰 | 按本地端口过滤；`test_ssh_edges.py` 74/74 绿。**遗留观察**：具体哪条用例留线程未定案（下轮用 `threading.enumerate()` 定位） |
| P-057 | 深嵌套 JSON 行为随解释器变化 | **口径问题（非产品 bug）**：判定为解释器差异下的**测试断言口径**；测试侧 R5 已改（long-int 钉死 `invalid JSON body`、deep 只钉安全不变量、200000 层必须 400）。产品侧「显式深度上限」保留为建议，不立案、不阻塞 |
| P-068 | 共享 PDK 库里第二个真实 OS 用户画不了版图 | **环境问题（非 bridge bug）**：B 会话绑的是 `cdsDefTechLib`（54 层）而 A 是 `tsmcN65`（216 层）；在 B 会话 `techBindTechFile(ddGetObj("adc_sar") "tsmcN65")` 后，**我独立复跑 S16 接力 TB = 12/12 通过**（`round6-fixcheck/s16-handoff-reverify2.json`）；并把「两用户工艺绑定必须一致」做成 TB 前置自检 + 写进环境文档 |
| P-052 | `set_instance_params` 污染共享库 cell CDF | **真机探针 verdict=clean**（`round6-verify/round4-shared-cdf-pollution.json`）：before/after 默认值不变（1K/400n/280n）、新实例继承原默认、peer 会话干净。修复提交 `f5f1813` |
| P-053 | Spectre AC 结果链路两处断 | **真机探针 verdict=clean**（`round6-verify/round4-spectre-ac-pipeline.json`）：默认分析名 `ac1` → `analyses=["ac"]`、`has_ac_data=true`；spec 形状（缺省 x）可用 |
| P-054 | 层次化 `symbol.generate` 残留子单元视图 | **真机探针 verdict=clean**（`round6-verify/round4-symbol-hierarchy-handle.json`）：leaf 生成后 CLOSED、二次生成 ok、无残留。注：该修复同时把契约改成「目标只读打开不再拒绝」，`symbol_e2e_tests.py` 的旧断言随之更新（见 `round6-修复验证报告.md` §3） |
| P-055 | 业务面 404 而非 405 + Allow | **离线 3 条转绿**（`round6-verify/offline-mine.xml`），两条护栏（`PUT /api/operation`→405、未定义路径→404）保持绿 |
| P-056 | POSIX 强杀进程组失效 | **Linux 3.9.25 / 3.14.6 转绿**（`round6-verify/py39.log` / `py314.log`）；修复提交 `b45864a` |
| P-059 | `read_results` 解不了 Calibre 2025 `DRC.rep` | **真机 `read_results` 转绿**（`round6-verify/calibre-drc.json`）：`rules_checked=1737`、`total_results=36`、**27 条真实规则计数**、`first_offenders=[]` |
| P-061 | calibre 阻塞轮询不快失败 | **真机转绿**：S11 的 LVS 以 `status=failed, failure_kind=input` **秒级**返回（`round6-verify/s11-with-calibre/s11-lvs.json`），不再轮询到超时 |
| P-062 | LVS 结论截成半个词 + counts 恒空 | **部分修复后关闭**：`counts` 已解出（ports 1/4、nets 5/4、inst 2/1）、结论不再半个词（`round6-verify/calibre-lvs.json`）；**残留的枚举不一致拆到 P-071 继续跟** |
| P-066 | `skill_value()` 抛内部 `AttributeError` | **离线转绿**：改为显式 `TypeError`（`round6-verify/offline-mine.xml`） |
| P-067 | 未加引号 `Parameters:` 静默丢参数 | **离线转绿**：整行拼回解析，两个参数都在（同上） |
| P-071 | LVS 结论归一化两条路径不一致（P-062 残留） | **已修复**（提交 `cee02df`）：日志路径与报告路径统一为同一枚举；契约 TB `test/offline/unit/test_calibre_verdict_consistency.py` **3/3 转绿**。另：同一天提交的 `af8e1e0` 让 `first_offenders` 恢复（真机 **20 条**违规明细，`round6-verify/calibre-drc-final2.json`） |
| P-048 | 「业务面不热重载 registry」 | **重判为口径/用法问题（非产品缺陷）**：spec《多用户与注册》§1 与《控制面与业务面》§1.1 明确要求**运行期不自动读文件**、由 `POST /api/process/reload`（管理权限）**显式触发**重导 —— 「热重载要手动发命令」本来就是设计语义。代码/测试对账：process 端点只在控制面；本轮我补了端到端语义 TB `test_supervisor_process.py::test_http_reload_picks_up_registry_file` （4/4 绿：不 reload → 新 token 无效；reload 后立即可用）。**真实差异**：我们的常驻业务面用 `-m server.api_server` **standalone** 启动（spec 标准形态是控制面 spawn 业务面），没有父进程控制通道 → 改注册表后只能重启；属测试台用法口径，已写进环境文档 |
| P-060 | calibre 包缺常驻真机入口（覆盖缺口） | **已闭环（测试侧，2026-09-24）**：① 常驻注册表补上 `role.command.calibre.bin`（vblog/vbs11/calprobe/vbuser1/vbuser2），S11 的 `drc` 阶段因此转 PASS；② 新增常驻套件 `test/live/packages/calibre_e2e_tests.py`（ENV-01 check_env / DRC-01 run+read_results / DRC-02 坏 deck 结构化失败 / LVS-01 结构契约+枚举一致），并接入 `run_all_http.py` → **11 套包 `all_passed=true`**（`round6b-verify/run-all-http-final.log`）。LVS 那条在 `not_compared` 时只打 WARN 指向 P-069，不假装跑通；P-069 修好后用 `VB_CALIBRE_REQUIRE_LVS_VERDICT=1` 打开强断言 |
| P-072 | `init_work_dir` 一次性化 + 删除测试钩子 → 518 条离线用例无法运行 | **已按方案 ② 适配完成**（产品坚持一进程一 work root）：`test/conftest.py` 加 session fixture 绑定唯一一根 +用例级 `registry.json` 重置；28 个用例文件里 38 处 `init_work_dir(...)` 改为 `work_root()`、47 处冗余绑定删除；路径敏感用例改**子进程**（`test_workdir_contract.py`）；跨用例产物残留与 Popen 计数按本用例过滤。**离线三层 1725 项 / 0 红 / 7 skip**（`round6b-verify/offline-sharedroot4.xml`）；官方姿势文档：[test/docs/写TB规范.md](../../docs/写TB规范.md) §3 |
| P-049 | 缺样本 trace 的 NaN 被放行到对外出参（spec :307 与 :308 冲突） | **已修复并验证**（提交 `d892608` + `a2f9aac`）：spec `7-spectre.md:307-309` 改写为「内部用缺失哨兵（实现取 `None`），**对外一律 `null`/省略**，唯一出口 `psf_external()`，NaN/±Inf 在那里收敛」；代码 `_spectre_util.py:70-71` 加了非有限→None 的收敛。**测试侧复跑：`test/offline/unit/test_output_json_safety.py` 3/3 绿**（2 条原红线转绿 + 业务面负控制）。spec 矩阵 X5 随之关闭 |
| P-013 | 客户端文件泄露（`err_dir` 兜底 / 隧道 stderr 日志成功路径不回收） | **已修**：`err_dir` 兜底改 `temp_dir()`（work root）并在 close 时 `rmtree`；隧道 stderr 日志新增 `_discard_tunnel_stderr()`，成功/失败路径都清理（`transport/middle.py:191-205,450,687`；`common/ssh.py:477-483,633,659,678`） |
| P-019 | 孤立代理项（`"\ud800"`）请求 → HTTP 面断连而非 4xx | **已修**：HTTP 面序列化改用 `jsonutil.dumps_strict`（`ensure_ascii=True` 兜底）（`server/api_server.py:30,76,79`、`register/server.py:42,78,81`）；`lone_surrogate_probe` 复跑转绿 |
| P-020 | `spectre.measure` 零幅度 AC 点输出 `-Infinity`（非法 JSON） | **已修**：改抛 `ValueError("magnitude must be positive for dB scale")` → `_metric_error` 结构化失败（commit `d49c892`；`_spectre_util.py:674-681`；`test_spectre_metrics.py` 全绿） |
| P-025 | Windows 多进程共享 work-dir 时 `log/commands.log` 轮转失败（WinError 32） | **已修**：命令日志按进程分片 `log/commands.<pid>.log` 后再轮转，跨进程不再争用句柄（`common/ssh.py:52-80`；`log_rotation_lock_probe` → PASS (process-local rotation)） |
| P-034 | `calibre.pex` 第三阶段 argv 错误且失败被静默（`-xrc -fmt -spice`） | **已修**：argv 改 `-xrc -fmt <fmt>`；`read_results` 对日志 `stage\d_failed` 返回结构化失败（`calibre.py:700`、`:429-490`） |
| P-037 | paramiko 后端把 `ssh -G` 的 `true/false` 当非法值（StrictHostKeyChecking yes 连不上） | **已修**：`true→yes` / `false→no` 归一化，报错回显原始值（`common/paramiko_backend.py:738-751`） |
| P-039 | py2.7 daemon 对 `_read_frame` ValueError 回 NACK（与 py3 分歧） | **撤回**：伪红 —— 真 py2.7 建成后复判分歧不存在（`py27_handler_probe` → `silent drop (correct)`，`round2-py27-handler-real.json`）；原 bug 报告应同步撤回 |
| P-041 | `verilog._read_views` 守卫长度与取值下标不匹配（`>=3` 却读 `[3]`） | **已修**：守卫改 `len(file_entry) >= 4`；离线用例改名 `test_short_view_entry_is_skipped` 并断言 `views == []`（`verilog.py:273`；`test_verilog_contracts.py` 全绿） |
| P-042 | `layout.gds` 遇版图锁时误报 "layout view not found" | **已修**：导出先走 `_view_state_expr` 三态（missing/mismatch/locked），锁冲突单独报 "is locked by another session"（`layout.py:1008-1030`） |
| P-046 | S10 e2e 引导源未固定 → `RBStop()+load()` 会覆盖别人的 CIW（测试侧缺陷） | **已修（测试侧）**：默认不再自动挑实例 —— `test_e2e_live.py` 用 `VB_E2E_BOOTSTRAP_TOKEN/PORT` 固定引导，未固定且未显式 `VB_E2E_ALLOW_AUTO_DISCOVER=1` 时直接拒绝（`test/live/e2e/test_e2e_live.py:56-63`） |
| P-069 | Calibre LVS 全链跑不通：auCdl 对含 PDK 器件的 cell 导出 CDL 失败 → 无源网表 | **测试侧复验通过（第七轮）**：`round7/design-iterate/iterate-lvs.json` —— `calibre.export_cdl(CMP_LIB/inv2, 680 B)` → `layout.gds` → `calibre.lvs(deck+cdl)` → `read_results`：**`status=correct`**、ports 4/4、nets 4/4、inst 1/1、`differences=[]`；S11 全链也拿到确定结论（`cdl` 693 B、lvs rc=0）。等上层销案；注意 `_calibre.lvs_`（tvf）不是合法 runset，用它当失败证据属用错文件 |
| P-026 | maestro 会话匹配用子串（view=maestro 误命中库名 maestro_tb） | **已修（`b36bade`）**：GUI 会话按标题 token 精确匹配 —— `_window_target_fields()` 解析 Editing:/Reading: 后的 `lib cell view` 并逐字段比较（`maestro.py:251-260,494`），不再用 `in` 子串。验证：round7 11 套包 `all_passed=true`（含用 `maestro_tb` 库的 maestro 套件，`round7/live-run-all-http.log`） |
| P-027 | `virtuoso.netlist.import` 假成功（对不存在的库也返回 ok=true） | **已修（`b36bade`）**：参考桩不再伪造成功；该操作已不在运营面（`netlist_import.py` 从生产源码移除、ops 列表无 netlist）。验证：`test/shared/runners/ops_matrix.py` 无 netlist 条目；infra 包 E2E 通过 |
| P-029 | `layout.gds` 导出忽略 `file_is_local=False`（产物下到客户端假路径树） | **已修（`b36bade`）**：gds export 支持 `file_is_local=false` 远端落盘且不拍平路径（`layout.py:1043,1175,1192,1244`）。验证（2026-09-28 复跑）：`test_layout_publish_contracts.py` 4/4、`test_layout_contracts.py` 67/67 绿 |
| P-030 | `set_term_nets` 默认 `stub_length=0.5` 对 65nm 过大 → 端子接错网且静默 | **已修（`b36bade` + `bd75d3d`）**：默认 stub 由引脚几何推导 `(rbHw + 0.05)`，不再固定 0.5；显式值的 SKILL 括号 bug（`(0.5)` 被当函数调用）同批修掉（`schematic.py:540-556`）。验证：`test_schematic_contracts.py` 37/37 绿 |
| P-031 | schematic `check_and_save`/`write` 忽略 `schCheck` 失败（check-failed 仍 ok） | **已修（`b36bade` + `bd75d3d`）**：保存前校验 output 含 saved 标记（`schematic.py:785,862`），并在保存路径补 `dbSetConnCurrent`（避免 si -batch OSSHNL-108/109）。验证：`test_schematic_contracts.py` 37/37 绿（无 xfail 残留） |
| P-032 | `verilog._imported_cells` 去重顺序错误（未清洗 token 参与比较） | **已修（`b36bade`）**：先清洗 `[.,;:]` 尾字符再去重（`verilog.py:659-667`）。验证：`test_verilog_contracts.py` 28/28 绿 |
| P-074 | pin 坐标口径三处不一致（read `xy` / write `x`,`y` / spec `xy`） | **已修（`48fc800`）**：实现统一为 `pos: [x, y]`，`xy`/拆开的 `x`/`y` 一律拒绝并点名违规字段（`schematic.py:480-487`）；spec《2-schematic》已改「单点一律 pos、弃用 xy」。验证：`schematic_pin_ops_probe` 以 `pos` 形状跑通写路径（`round7/pin-ops.json`，2026-09-28 复跑） |
| C0 | 测试规范缺失（六步/状态还原）＋ 原子级覆盖系统性缺口 | **已闭环（2026-09-28）**：① 规范落地 `test/docs/写TB规范.md`（六步＋判据强度＋状态还原＋原子级覆盖义务）；② 机器核账 `audit_atom_coverage.py` → **gap=0 / weak=0 / 待分诊 0**（`atom-coverage-2026-09-28.json`）；③ B3 修弱判据：serdes calibre 补 `read_results`（DRC 1737 规则/28 结果；LVS 显式记录 not_compared 局限）、ADC/多用户 SerDes 补 `symbol.read` 端口比对、S11 gds 补 `stat+sha256`（PASS）；④ B4 抽查报告 `test/reports/TB规范抽查-2026-09-28.md`（5 份，发现 design_iterate 缺 §1 env_check → 已修） |

详见 [已关闭-近期.md](已关闭-近期.md)。

## 3. 非缺陷跟踪项（16 项，不建卡）

文档 / 环境 / 审计 / 覆盖度类条目：**不是产品缺陷**，只在台账与这里索引（避免与缺陷卡片混淆）。
所有**缺陷**（含早期轮次已上报的 `bug-2026…`）都在上面 §1 的卡片里，或已移入 §2 已关闭记录。

| ID | 事项 | 当前状态 |
|---|---|---|
| P-001 | 覆盖度报告 `doc/测试覆盖报告.md` 与当前 `src/` 布局脱节（缺负责人） | 待定负责人 |
| P-003 | 环境占用（跑测前检查清单已写） | 待固化到脚本 |
| P-004 | `.pytest_cache` 里 14 条 lastfailed 指向已不存在的旧路径（缓存噪声） | 已记录（建议定期清缓存） |
| P-005 | 瞬态红灯（观察中） | 观察 |
| P-006 | 文件纪律审计（Q1 全链路 / Q2 逐 role / Q3 逐 TB 三项未覆盖） | 待补（审计项，非缺陷） |
| P-010 | 文档一致性（§7 需改「已确认发生、待清理」） | 待改文档 |
| P-011 | `/tmp` 口径待定稿（设计内例外 vs 泄露） | 待定稿 |
| P-014 | 现场观察（找不到创建者） | 待代码定位 |
| P-016 | 完成度评估 / 补测归口（非缺陷） | 待处理 |
| P-017 | 归属未定（先定创建者） | 待确认 |
| P-021 | 历史实例启动位置不规范（`$HOME`/工程目录污染；规范已落地，现场清理与 legacy 重写待办） | 环境账，非缺陷 |
| P-023 | wsl-gent 起 20 个真 Virtuoso 超出内存（真机上限 10–12；口径已写环境文档） | 待用户确认替代口径 |
| P-028 | 运行中的 vblog CIW 没有 PDK（已按 S1 专用实例口径处置） | 环境账，已给口径 |
| P-033 | `test/artifacts` 231 个文件被跟踪（含 token/二进制；白名单保留需用户确认） | 仓库卫生，待确认 |
| P-036 | lab fake 与 bridge 隧道兼容性（已复测可达，症状未复现） | 观察（降级，不再阻塞） |
| P-040 | 仓库内 `.ps1` 一律 UTF-8 with BOM（约定，已写入首轮报告 §6.1） | 约定，非缺陷 |

## 4. 关联文件

- 台账（唯一事实源）：[问题登记.md](../问题登记.md)
- 最新一轮送修：[上层](../round7-缺陷清单-上层.md)、[其他](../round7-缺陷清单-其他.md)
- Spec 覆盖矩阵（哪些要求被测到）：[round7-spec覆盖矩阵.md](../round7-spec覆盖矩阵.md)
- 覆盖率与缺口：[coverage-pack/](../coverage-pack/)、[覆盖度缺口.md](../覆盖度缺口.md)
- 覆盖率补强要求（**给设计侧的清单**）：[覆盖率补强要求-给设计侧.md](../覆盖率补强要求-给设计侧.md)
- 两个完整项目的验收清单：[两项目全链-验收清单.md](../两项目全链-验收清单.md)
- 新增卡片模板：[_模板.md](_模板.md)
