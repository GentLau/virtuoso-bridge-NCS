# `test/reports/bugs/` —— 未关闭缺陷的唯一跟踪视图

> 维护者：测试工程师（我）｜最近刷新：2026-09-24
> **这个目录回答一个问题：现在还有哪些 bug 没关、谁在等谁、修好的判据是什么。**

## 0. 三条规矩（动这里之前先看）

1. **权威事实在台账**：[问题登记.md](../问题登记.md)。本目录不重复分析，只做「未关闭项」的卡片与索引；
   送修视图（逐条 file:line / 复现 / 验收）在 [round7-缺陷清单-上层.md](../round7-缺陷清单-上层.md) 与
   [round7-缺陷清单-其他.md](../round7-缺陷清单-其他.md)。
2. **状态只能从这五个里选**：`待设计修` / `待测试侧` / `待归属` / `待决策` / `观察`。
   关闭时**不删卡片**：移到 [已关闭-近期.md](已关闭-近期.md) 并写一句「凭什么关的」（证据路径）。
3. **刷新方式**：改 `test/shared/runners/make_bug_cards.py` 的 `OPEN` / `CLOSED_RECENT` 段，
   然后 `python test/shared/runners/make_bug_cards.py`（幂等；`--check` 只校验不写盘）。

## 1. 未关闭（7 条）

| ID | 级别 | 归属 | 状态 | 一句话 | 卡片 |
|---|---|---|---|---|---|
| **P-076** | P2（间歇性挂起；占住 in_flight 线程，客户端只能杀进程） | 设计侧（上层 spectre 包的 run 路径：等待完成/递归下载） | 观察（1 次复现，待设计侧定位） | 间歇：`spectre.run` 请求永不返回（spectre 已 0 error 跑完；服务端线程不释放，需重启业务面） | [P-076-spectre-run-request-never-returns.md](P-076-spectre-run-request-never-returns.md) |
| **P-075** | P1（会话被挂死；多用户/GDS 后继续操作的流程直接卡住） | 设计侧（上层 layout.gds / strmout 调用路径） | 待设计修 | `virtuoso.layout.gds` 导出后会话残留模态对话框（"Stream out translation complete"）→ 同会话 SKILL 通道挂死，必须重启实例 | [P-075-gds-export-modal-blocks-session.md](P-075-gds-export-modal-blocks-session.md) |
| **C0** | P2（测试规范缺陷；导致覆盖系统性缺口 + 缺陷漏检） | 测试侧（规范制定 + 覆盖补齐） | 规范已落地（2026-09-28）；覆盖补齐进行中（B1–B4） | 测试规范缺失：无显式 TB 流程约定（环境检查→构建→完备校验→执行→比对），delete/rename/set 类原子在 semi/live 层系统性无覆盖 | [C0-测试规范-AAA与状态还原缺失.md](C0-测试规范-AAA与状态还原缺失.md) |
| **P-073** | P2（写操作语义错误；set_pin_properties 静默改坏用户数据） | 设计侧（上层 schematic 包 `_atomic_skill`） | 待设计修 | 原理图 pin 原子操作与「pin 有效名」不一致：rename_pin 静默无效、set_pin_properties 把 pin 名改成自动名 | [P-073-pin-atomic-ops-name-mismatch.md](P-073-pin-atomic-ops-name-mismatch.md) |
| **P-074** | P3（文档口径不一致，会绊住所有写 TB 的人） | 设计侧（spec 或实现，二选一改齐） | 待归属 | spec 表格把 pin 的索引写成 `xy`，实现要 `x`/`y`（delete/rename/set_pin_properties） | [P-074-pin-index-xy-doc-mismatch.md](P-074-pin-index-xy-doc-mismatch.md) |
| **P-070** | P2（能力缺失） | 待决策（产品口径：支持驱动 MC or 明确不做）→ 设计侧实现/写 spec | 待决策 | 蒙特卡洛能力缺失：只能读回 MC 结果，不能驱动 MC 仿真 | [P-070-monte-carlo-missing.md](P-070-monte-carlo-missing.md) |
| **P-069** | P2（业务包功能不可用） | 设计侧 | 观察（第七轮复验 **correct**，等上层销案） | Calibre LVS 全链跑不通：auCdl 对 PDK 器件导出 CDL 失败 → 无源网表 | [P-069-lvs-cdl-chain.md](P-069-lvs-cdl-chain.md) |

> 优先级口径：**P1** = Linux 侧资源/安全或核心指标链路断（P-056、P-053）；
> **P2** = 真实设计流会给出错的/空的结果，且多数**静默**；**P3/观察** = 非阻塞但建议顺手修。

## 2. 本轮/近期已关闭（27 条，保留记录）

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

详见 [已关闭-近期.md](已关闭-近期.md)。

## 3. 早期轮次仍未关闭（12 组）

这些多为**已上报外部 bug 系统**（`bug-2026…`）的历史条目，跟踪在外部系统里；这里只做索引，
避免与台账「两份清单打架」。本轮**未复核**它们的最新状态。

| ID | 事项 | 当前状态 |
|---|---|---|
| P-001 | 覆盖度报告（缺负责人） | 待定负责人 |
| P-003 | 环境占用（跑测前检查清单已写） | 待固化到脚本 |
| P-005 | 瞬态红灯（观察中） | 观察 |
| P-006 | 文件纪律（Q1 全链路 / Q2 逐 role / Q3 逐 TB 三项未覆盖） | 待补 |
| P-010 | 文档一致性（§7 需改「已确认发生、待清理」） | 待改文档 |
| P-011 | `/tmp` 口径待定稿（设计内例外 vs 泄露） | 待定稿 |
| P-013 | 客户端文件泄露（A-1 / A-2 两条代码锚点） | 待处理 |
| P-014 | 现场观察（找不到创建者） | 待代码定位 |
| P-016 | 完成度评估 / 补测归口 | 待处理 |
| P-017 | 归属未定（先定创建者） | 待确认 |
| P-019/P-020/P-025/P-026/P-027/P-029/P-030/P-031/P-032/P-034/P-037/P-038/P-039/P-041/P-042 | 早期轮次已上报外部 bug 系统的源码缺陷（`bug-2026…` 编号见台账） | 待设计修（外部系统跟踪） |
| P-046 | S10 e2e 引导源未固定 → 会覆盖别人的 CIW | 测试侧待修（本轮未动） |

## 4. 关联文件

- 台账（唯一事实源）：[问题登记.md](../问题登记.md)
- 最新一轮送修：[上层](../round7-缺陷清单-上层.md)、[其他](../round7-缺陷清单-其他.md)
- Spec 覆盖矩阵（哪些要求被测到）：[round7-spec覆盖矩阵.md](../round7-spec覆盖矩阵.md)
- 覆盖率与缺口：[coverage-pack/](../coverage-pack/)、[覆盖度缺口.md](../覆盖度缺口.md)
- 覆盖率补强要求（**给设计侧的清单**）：[覆盖率补强要求-给设计侧.md](../覆盖率补强要求-给设计侧.md)
- 两个完整项目的验收清单：[两项目全链-验收清单.md](../两项目全链-验收清单.md)
- 新增卡片模板：[_模板.md](_模板.md)
