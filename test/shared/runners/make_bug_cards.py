"""生成/刷新 `test/reports/bugs/` —— 未关闭缺陷的唯一跟踪视图。

为什么用脚本生成：缺陷的**权威事实**在 `test/reports/问题登记.md`（台账）与
`第五轮-缺陷清单-*.md`（送修视图）。这个目录是给「还在等修复」的条目做**逐条卡片**
（状态 / 责任人 / 下一步 / 验收判据 / 证据），必须和台账口径一致、且能一键刷新，
否则很快会变成第三份互相矛盾的清单。

用法::

    python test/shared/runners/make_bug_cards.py            # 刷新 cards + README 索引
    python test/shared/runners/make_bug_cards.py --check    # 只检查（收尾/CI 用，不写盘）

维护约定（改状态时改本文件的 `OPEN` / `CLOSED_RECENT` / `LEGACY_OPEN` 三段即可）：

* `OPEN`：**未关闭**的缺陷/观察项 —— 每条生成一张卡片 + 进 README 索引表；
* `CLOSED_RECENT`：本轮明确闭环的（保留近期记录，避免「消失了没人知道为什么」）；
* `LEGACY_OPEN`：**非缺陷**跟踪项（文档/环境/审计/覆盖度）——不建卡，只在 README 索引。
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUGS_DIR = ROOT / "test" / "reports" / "bugs"

#: 未关闭条目。状态只允许：待设计修 / 待测试侧 / 待归属 / 待决策 / 观察
OPEN = [

    {
        "id": "C10",
        "layer": "上层（schematic 包）· place_wire 惰性参数",
        "slug": "place-wire-spacing-lazy-params",
        "title": "`place_wire` 的 `x_spacing`/`y_spacing` 无可观察效果（spec 未记载、DB 无属性、写后读不回来）",
        "level": "P3（静默无效参数，与 P-092/C07 同族；调用方以为能控制走线间距）",
        "owner": "设计侧（实现可观察语义并写进 spec，或从命令模型/spec 删字段）",
        "status": "待决策",
        "where": "`src/pyapi/packages/schematic.py:604`（`schCreateWire(cv entry route points xSpacing ySpacing width)`——两值只做创建期实参、不落库）；"
                 "spec `2-schematic.md` 的 `place_wire` 参数表未记载这两个键",
        "symptom": "真机（vblog，round9）：`virtuoso.schematic.write(place_wire points=[[0,0],[1,0]] x_spacing=1.5 y_spacing=0.25 width=0.05)` → ok；"
                   "DB 直读该 shape：`(\"path\" (nil) (nil) (0.05))` —— **width 落库、xSpacing/ySpacing 读回 nil**；"
                   "不同 spacing 取值之间也观察不到几何差异（2 点直连路由）。",
        "repro": "PYTHONPATH=src python test/live/packages/nested_keys_e2e_tests.py --transport http  # NK-04",
        "evidence": "`test/artifacts/evidence/round9/nested-keys-symbol-schematic.json`（NK-04 `db` 字段）；`test/reports/round9/nested-key-coverage.md` §2",
        "accept": "① 实现语义并在 spec 写明（给出可观察差异的判据，例如多段 VHV 路由间距或 DB 属性）或 ② 从命令模型/spec 删除这两个字段；"
                  "NK-04 相应升级为值级断言或删除。",
        "next": "设计侧定口径；测试侧按结论改 NK-04。",
        "reported": "2026-09-29（round9 嵌套键真机覆盖发现）",
        "updated": "2026-09-29（新立）",
    },


    {
        "id": "C09",
        "layer": "上层（maestro 包）· write_history rename 链",
        "slug": "maestro-write-history-rename-chain-handle-error",
        "title": "`maestro.write_history` 连续 rename（A→B，再 B→A）第二跳报 `ASSEMBLER-2404 Cannot find a setup database entry for handle`",
        "level": "P3（重命名链不可用：`maestro_e2e_tests.HISTORY-01` 因此稳定红）",
        "owner": "设计侧（已修：maestro 包会话/SDB handle 生命周期）",
        "status": "待测试侧",
        "where": "`src/pyapi/packages/maestro.py`（`write_history` 的 rename 分支与 SDB handle 复用；`_open_session` 会话内 handle 在重命名后失效）",
        "symptom": "隔离复现（round9，vblog，21:5x）：`rename(Interactive.8 → e2e_renamed)` **ok=True**；紧接着 "
                   "`rename(e2e_renamed → Interactive.8)` → `(\"error\" 0 t nil (\"*Error* error: Cannot find a setup database entry for handle 118109.\" nil))`。"
                   "同一形态在门禁 `maestro_e2e_tests.py::HISTORY-01 rename/lock/unlock/delete` 稳定复现（今日 3 次，handle 号不同）。"
                   "对照：单独 `delete e2e_renamed` **ok=True** 且列表确实少一条 → delete 正常，问题在 rename 链。",
        "repro": "PYTHONPATH=src python test/live/packages/maestro_e2e_tests.py --transport http  # HISTORY-01\n"
                 "隔离：read_history → pick Interactive.* → write_history(rename H→e2e_renamed) ok → write_history(rename e2e_renamed→H) → ASSEMBLER-2404",
        "evidence": "`test/artifacts/evidence/round9/final3-maestro_e2e_tests.py.log`（HISTORY-01 报错原文）；隔离探针 stdout（rename ok / restore fail, handle 118109）",
        "accept": "① rename 链（含目标名已存在、重命名回原名）必须成功或给出**点名冲突**的结构化拒绝（对照：重名 rename 已有清晰文案）；"
                  "② 不得报 SDB handle 错误；③ `maestro_e2e_tests.py` HISTORY-01 转绿。",
        "next": "**设计侧已修 `2610668` + `50e6576`（2026-09-30 12:47）**：`_open_session` 校验 `maeOpenSetup` 返回会话可活跃、失效则关闭重开，rename 链按本次创建路径收尾。"
                "真机证据 `test/artifacts/evidence/verify-fix-r10/c09-maestro-history-green.json`（HISTORY-01 HTTP 全链通过）。待测试侧复跑 `maestro_e2e_tests.py` HISTORY-01 后把本卡移入已关闭。",
        "reported": "2026-09-29（round9 门禁复跑 + root 隔离复现）",
        "updated": "2026-09-30 18:20（设计侧已修 + 真机绿证据，转测试侧收口）",
    },

    {
        "id": "C11",
        "layer": "控制面权限模型（个人自助 registry）",
        "slug": "control-plane-personal-self-service-missing",
        "title": "`/api/user/*` 仍收归管理员且 `enhanced_token` 未接入 update：个人 token + 增强凭据无法自助查询/修改自己的注册表条目",
        "level": "P2（个人管理核心能力不可达：真实控制面对个人 token 稳定 401；前端只能显示缺口或错误地借用管理员权限）",
        "owner": "设计侧（先定个人自助权限矩阵/端点语义，再由 server 实现；不能只改前端）",
        "status": "待决策",
        "where": "spec：`spec/design-concepts/顶层/add-控制面与业务面.md:67-95`（query/update/delete 均标管理权限，且明确“个人 token 不能自助修改”）、`spec/design-concepts/中层/add-中层配置文档.md:47`（仅 `mode=local` 需管理权限，无字段级个人权限矩阵）；"
                 "实现：`src/register/server.py:232-285`（`/api/users`、`/api/user/<user>`、update、delete 入口先走 `_require_admin()`）、`:723-802`（update 只接受管理端 patch）、`:361-390`（`enhanced_token` 只在 `POST /api/register apply` 校验）。",
        "symptom": "真实 8124 实测：`Authorization: Bearer <管理员 token>` → `GET /api/user/<user>` 200；`Authorization: Bearer <该 user 的个人 token>` → 401 `unauthorized`。"
                   "因此个人页无法按目标语义“个人 token 证明本人身份 + enhanced_token 证明受保护变更权限”工作。"
                   "当前 spec 与实现彼此一致（都规定 admin-only），但都缺少产品要求的个人自助权限模型。",
        "repro": "1. 从 work-dir registry 取某 user 的个人 token；\n"
                 "2. `curl -H 'Authorization: Bearer <personal>' http://127.0.0.1:8124/api/user/<user>` → 401；\n"
                 "3. 同请求改用管理员 token → 200；\n"
                 "4. 前端个人页严格用 personal Authorization 提交，不再回退管理员凭据。",
        "evidence": "`doc/report/控制台三页-后端接口与权限缺口.md`；代码锚点 `src/register/server.py:232-285,361-390,723-802`；"
                    "页面契约测试 `test/offline/unit/test_registration_page.py::test_personal_page_combines_query_and_update`（要求 personal Authorization 且禁止 enhanced 回退）。",
        "accept": "① spec 补字段级权限矩阵，明确 personal token 只能访问本人、哪些字段普通修改、哪些字段必须 `enhanced_token`；"
                  "② server 提供 personal-token-only-own-user 的查询/更新语义，并在 update 接入 `enhanced_token`（只校验、不落盘、不回显）；"
                  "③ 个人页无需管理员 token 即可查询/修改自己的 registry；④ 负例：个人 token 访问他人条目必须拒绝。",
        "next": "spec owner 先拍板权限矩阵与 self 端点形状；后端按 spec 实现。前端已移除管理员 Authorization 回退，仍在 401 时显式点名该缺口。",
        "reported": "2026-09-30（个人管理页真机查询 401，root 复核 spec 与实现）",
        "updated": "2026-09-30（新立；前端停止用管理员凭据代偿）",
    },



    {
        "id": "C06",
        "layer": "底层（CIW 侧 `ramic_bridge.il` + daemon 表达式）· CIW 输出刷新",
        "slug": "ciw-output-not-flushed",
        "title": "桥执行 `print` 的输出在 CIW 不显示：evalstring 路径行缓冲未刷，daemon 补的是 `hiFlush()` 而非 `hiFlushInfo()`",
        "level": "P2（用户可见功能缺陷：SKILL 的打印输出静默不显示；且积压输出会串进下一次交互，造成归因误判）",
        "owner": "设计侧（`ramic_bridge.il` 的 CIW 侧刷新点；daemon 两版残留的 `hiFlush()` 清理）",
        "status": "待设计修",
        "where": "`src/bridge/resources/ramic_bridge.il:102-119`（`evalstring` 之后只做日志侧 `hiFlushLogFile()`，从不刷 CIW 输出缓冲）；"
                 "`src/bridge/resources/ramic_bridge_daemon_3.py:419,426`、`src/bridge/resources/ramic_bridge_daemon_27.py:417,423`（表达式尾部补的是 `hiFlush()`）。",
        "symptom": "经桥执行 `print`（输出一个常量串，不带换行）后 CIW **不显示**该内容；"
                   "随后在 CIW 手动敲任意命令（或手敲 `hiFlush()`）时，此前若干次输出**一次性涌出**且彼此无换行分隔。"
                   "同一请求返回的 `CDSlog` 为空串。对照：输出以换行结尾时（`printf` + 换行）经桥执行**能正常显示**。",
        "repro": "① 页面 / HTTP 调 `basic.skill.execute`，skill_code 填 `print` 加一个常量串 → CIW 无输出；\n"
                 "② 同法改用带换行的 `printf` → CIW 立即显示；\n"
                 "③ 回到 ①，手动在 CIW 敲任意命令 → 积压内容全部涌出。",
        "evidence": "用户 2026-09-29 实测：CIW 一次性涌出三次输出（无换行分隔），同响应 JSON 的 `CDSlog` 为空串；"
                    "`ramic_bridge.il:70-74` 注释自述 evalstring 路径为行缓冲、只有以换行结尾的输出才立即 flush；"
                    "8123 手册（skuiref.fnd）区分四者语义：`hiFlush` = 同步事件队列/处理曝光事件（重画窗口）、"
                    "`hiFlushCIW` = flushes any buffered output to the CIW、`hiFlushInfo` = 让上一个程序的输出在 SKILL 执行期间显示到 CIW、"
                    "`hiFlushLogFile` = 刷新主/次日志文件；"
                    "spec `spec/design-concepts/底层/6-日志返回设计标准.md:49` 已写明 `hiFlush()` ≠ `hiFlushLogFile()`，须用后者。",
        "accept": "**测试侧红钉（2026-09-29 已立）**：`test/live/packages/skill_log_semantics_e2e_tests.py` —— C06-A `print`（不带换行）必须落**同一请求**的 `CDSlog`；C06-B 后续请求 `CDSlog` 不得串入上一条缓冲；C06-C `printf`（带换行）回归不破；C06-E `load`（printf+换行）回归不破（21:44 干净窗口实测 PASS）；C06-D `print+换行` 的归属只打 NOTE（待 spec 定边界）。实测证据 `test/artifacts/evidence/verify-fix-r9/c06-skill-log-semantics.json` 与 `round9/c06-semantics-r9b.json`：A 空、B 串场（且带出更早的残留）、E 绿。长行探针 `round9/longline-probe.log`（stamp 214445）：**≥500B 无换行单行**同请求 `CDSlog` 空、下一条串场带出；同长行+换行同请求 542B 正常 —— 长行\"消失\"并入 C06 本体口径，不另立卡。原判据：① 经桥执行 `print` 后 CIW **立即**显示，无需任何手动交互；"
                  "② 连续多次 `print` 不再堆叠到下一次交互；"
                  "③ 同一请求的 `CDSlog` 非空（若确认 `print` 本就不写 CDS.log，需在 spec 写明该边界）；"
                  "④ 回归：带换行的 `printf` 与多行 `load` 路径行为不变。"
                  "**round9 攻击扩展（2026-09-29 22:29 实测，证据 `test/artifacts/evidence/round9/c06-attack-r9c.json`）**："
                  "同一根因再补 6 条形态 —— F 同请求 3×`print` 三标记全缺；G `print`+`printf`(换行) 同请求两标记都在"
                  "（对照：**换行才是 CIW 缓冲的触发点**）；H 循环内 5×`print` 全缺；I 600B 无换行长行 `print` 的 CDSlog 长度为 0；"
                  "J `print`(all)→`printf`(off)→`printf`(all) 归属错位（A 本条为空、缓冲被 off 请求的换行冲掉）；"
                  "K `load` 内 `print`（无换行）为空 —— **A/F/H/I/J/K 同族全红；只绿 A 不算修完，本 TB 全绿才是卡关闭条件**。"
                  "另 D 实测 `print` 带换行仍在后续请求才带出（SKILL `print` 对字符串加引号并转义换行，故不触发 CIW 缓冲 flush）。",
        "next": "设计侧在 `ramic_bridge.il` 的 `evalstring` 之后、`lo_end` 抓取**之前**插入 `errset(hiFlushInfo())`"
                "（不要用 `hiFlushCIW()`——它会处理输入与定时器事件，在 evalstring 内存在重入风险）；"
                "同时清理 daemon 两版残留的 `hiFlush()`（对 CIW 输出与日志都无效，属误导）。"
                "测试侧补一条探针：桥执行 `print` 后校验 CIW 可见性与 `CDSlog` 非空。",
        "reported": "2026-09-29（用户直报：页面执行 `print` 后 CIW 不显示）",
        "updated": "2026-09-29 22:29（补 C06-E load 回归 + 长行归因 + 攻击扩展 F–K：A/F/H/I/J/K 同族全红）",
    },

    {
        "id": "C07",
        "layer": "spec↔实现一致性（上层 calibre / LVS 源网表入口）",
        "slug": "calibre-lvs-source-fold-drift",
        "title": "spec 把 `calibre.export_cdl` 折进 `calibre.lvs` 的 `source` 参数（`source/emit_cdl/cds_lib`）：实现已落地、独立 op 已删除，待测试侧复跑销卡",
        "level": "P3（一致性：spec §8 验收两行在现行实现上不可达；TB 仍跑在 spec 已删除的旧入口上）",
        "owner": "设计侧（已选①：实现 fold；测试侧收口红钉）",
        "status": "待测试侧",
        "where": "spec：`spec/design-concepts/上层/12-calibre.md` §4.3 参数表（`:157-168`）、§4.3.2 auCdl 内产（`:194-208`）、§6.3（`:246-249`）、§8 验收（`:258-273`），源自 commit `6b1b855`（2026-09-29 14:29，**只改 spec**）；实现：`src/pyapi/packages/calibre.py:82-145`（`RunRequest` 无这 3 个字段）、`:1115-1124`（OPERATIONS 仍注册 `calibre.export_cdl`，实体在 `:341-423`）。",
        "symptom": "按 spec §8 调 `calibre.lvs(source=…)` 会在请求解析即 400：`server/dispatch.py::build_request` → `RunRequest(**fields)` → `TypeError: got an unexpected keyword argument 'source'` → `invalid request for operation: …`。"
                   "反向：spec 已删的 `calibre.export_cdl` 仍可调用，且真机套件与 4 条 flow TB 都在用它 —— 审计口径下「spec 验收行无实现无 TB」与「TB 覆盖的是 spec 不认的入口」同时成立。",
        "repro": "离线（不碰真机）：\n```python\nfrom pyapi.packages.calibre import RunRequest\nRunRequest(token='t', deck='/r/deck', source={'kind':'cdl','path':'/r/x.cdl'})\n# TypeError: … unexpected keyword argument 'source'\n```\n"
                 "红钉：`test/offline/unit/test_calibre_lvs_source_contract.py`（strict xfail ×2，挂本卡）。",
        "evidence": "`git show 6b1b855`（spec-only：删 §4.6 `export_cdl`、§4.3 增 `source/emit_cdl/cds_lib`、§8 验收改 source 口径）；"
                    "`test/reports/round9/op-param-r9.md` §6.3（B 线独立发现）；"
                    "旧 API TB：`test/live/packages/calibre_e2e_tests.py:186-193,339,343`、`test/live/flows/design_iterate_tb.py:763,841`、"
                    "`test/live/flows/project_flow_tb.py:371`、`test/live/flows/serdes_rx_flow_tb.py:618`、`test/live/flows/s11_full_flow.py:286`；"
                    "研究文档仍写 export_cdl 独立可用：`spec/research/calibre/README.md:21,30`。",
        "accept": "二选一：① **实现**——`calibre.lvs` 接受 `source.kind=cdl|schematic`（schematic 按 §4.3.2 在 run dir 内走 auCdl 现产并作为 LVS 源）+ `emit_cdl` + `cds_lib`，"
                  "同时明确 `calibre.export_cdl` 去留（删除，或标注兼容保留并在 spec 写明）→ 红钉 XPASS 转绿流程走完；"
                  "② **回退 spec**——写回独立 `export_cdl` 与 §4.6、删除 source 口径 → 测试侧把红钉改为非缺陷断言并销卡。",
        "next": "**设计侧已落地（2026-09-30）**：`RunRequest` 收 `source/emit_cdl/cds_lib`，`calibre.lvs` 在 run dir 内折 `source`；独立 `calibre.export_cdl` 已删除；4 条 flow TB（design_iterate/project_flow/s11_full_flow/serdes_rx）与包 E2E 已迁到 `source=` 口径。"
                "真机证据：`test/artifacts/evidence/verify-fix-r10/c07-lvs-source-fold-green.json`（LVS-02/03 均 `correct`）与 `c07-design-iterate-lvs3.txt`（`design_iterate --stage lvs` ok=true、source.schematic→`correct`、cdl 680 B）。"
                "离线：`test/offline/unit/test_calibre_lvs_source_contract.py` 红钉转绿 + `test_calibre_package.py` 新增 cds_lib 回归（`test_lvs_source_schematic_with_cds_lib_completes`）。"
                "待测试侧复跑包 E2E（含 flow 抽跑）后把本卡移入已关闭；LVS-01（旧 `cdl=` 参数）不在 spec 口径内、强判据预期红，属 TB 侧残留，建议一并清理。",
        "reported": "2026-09-29（第九轮 B 线发现 + 测试/root 复核 commit `6b1b855` 与实现后定案）",
        "updated": "2026-09-30 17:50（设计侧实现 + 真机闭环证据，转测试侧收口）",
    },

    {
        "id": "P-106",
        "layer": "上层 calibre · 长任务判活/完成判定（official-batch `runset=` 路径）",
        "slug": "calibre-blocking-false-fail",
        "title": "`calibre.lvs(runset=…, blocking=true)` 误杀成功作业：`pgrep -f <run_dir>` 匹配不到 calibre 进程 → 首个 poll 即报 `process_gone_without_report`",
        "level": "P2（false-fail：成功完成的 LVS 被报 `failed`；SET-01 稳定红，用户在官方批处理入口拿不到结论）",
        "owner": "设计侧（calibre 包判活口径 + P-094 分类的输入）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/calibre.py:918-944`（`_status_snapshot` 用 `pgrep -f <run_dir>` 判活：official-batch 的 calibre 命令行只含 **runset** 路径、不含 run_dir → 恒无匹配）；"
                 "`_run` 轮询 `:586-604` + `_calibre_util.py:317-333`（`process_alive=False` + 无完成 marker → `failed process_gone_without_report`）。触发 TB：`test/live/packages/calibre_e2e_tests.py::_case_set_file`（SET-01）。",
        "symptom": "`blocking=true` 的 LVS 在 5.6s（另一次 ~数秒）即返回 `lvs did not complete: failed process_gone_without_report`；"
                   "但远端 `lvs.log` 随后写出 `--- CALIBRE::LVS/xRC COMPLETED - … 21:26:48 ---` 与 `*** LVS run finished with exit code 0 ***`（line 15619）、`inv2.lvs.report` 37957B 齐全；"
                   "事后对同一 run_dir 调 `calibre.status` 得到 `completed`。⇒ 判活在首个 poll 误判进程已死（实际 calibre 还要跑 ~16-30s），P-094 把它归类成终态 failed 提前收工。"
                   "两次复现：21:11 门禁 SET-01（lvs-set/lvs.log:15624 exit code 0）+ 21:26 探针（lvs-set-r9b）。",
        "repro": "python test/artifacts/tmp/r9_calibre_blocking_probe.py\n"
                 "# ② 段：新 run dir 的 blocking LVS → 5.6s 报 failed process_gone_without_report；\n"
                 "# 同一作业远端日志 21:26:48 写出 exit code 0（证据见下）",
        "evidence": "`test/artifacts/evidence/round9/calibre-blocking-probe.log`（探针输出：failed @5.6s、pid=3691775、log_tail 只有文件头）；"
                    "`test/artifacts/evidence/round9/calibre-set01-falsefail-evidence.txt`（远端 `lvs-set-r9b/lvs.log:15606/15619`、report 37957B、job.json=official-batch；另一条 21:11 门禁 `lvs-set/lvs.log:15624` exit 0）；"
                    "`test/artifacts/evidence/http-e2e/calibre_e2e_tests.py.log`（21:11 SET-01 红）。",
        "accept": "① 判活改用真实 pid 判据（`kill -0 $(cat job.pid)` / `ps -p`），不再依赖 `pgrep -f <run_dir>`；"
                  "② `process_gone_without_report` 的判定必须基于**已确认 pid 消失**（且无完成 marker/失败 marker）；"
                  "③ 回归：`calibre_e2e_tests.py` SET-01 `blocking=true` 转绿；P-093/094/098 三个探针保持绿（坏 deck 快失败 + timeout 语义不回归）。",
        "next": "设计侧修 `_status_snapshot` 判活与分类输入；测试侧红钉即 SET-01（保持红直到修复）；修复后复跑 calibre_e2e 全绿再销案。"
                " **B 线 22:2x 静态复核补充（同一路径的第二处缺口）**："
                "`_calibre_util.py:272-276` 的 `_DONE_MARKERS['lvs']` 只有 `('LVS completed',)`，"
                "而 official-batch 的 `lvs.log` 写的是 `CALIBRE::LVS/xRC COMPLETED` 与 `LVS run finished with exit code 0` —— "
                "**两者都不匹配**；即使判活修好，完成判定仍会落空（会一直轮询到 timeout）。"
                "建议把这两个 marker 一并加入（或按 kind 分 deck/batch 两套 marker）。",
        "reported": "2026-09-29（第九轮；门禁 SET-01 红 → 测试/root 探针 21:26 决定性复现）",
        "updated": "2026-09-29 21:31（立卡，含两次成功作业被误杀的证据）",
    },




















    {
        "id": "P-086",
        "layer": "底层 daemon / 中层连接（多用户场景）",
        "slug": "empty-response-window-after-long-skill",
        "title": "多用户同视图场景后 ~30–90s 窗口内同 token 请求得到 `Empty response from daemon`（随后自愈）",
        "level": "P3（观察：可恢复，但窗口期错误不可读、无结构化语义）",
        "owner": "待归属（底层 daemon 请求生命周期 / 中层连接复用，二选一或联合）",
        "status": "观察",
        "where": "底层：`src/bridge/resources/ramic_bridge_daemon_3.py:187`（`_read_frame` 对空 stdin 只 1ms 轮询、无 EOF/停滞判定）；"
                 "中层：`src/common/skill_client.py:185`（读空 → `errors=[\"Empty response from daemon\"]`，非 spec 枚举文案）；"
                 "触发 TB：`test/semi/probes/twouser_same_view_probe.py`（holder 单请求内 `dbOpenCellViewByType a` + `hiSleep(20)` 持锁）",
        "symptom": "复现 4/4（2026-09-28）：跑完 twouser 多用户同视图场景后，**同 token 新请求立即得到 "
                   "`Empty response from daemon`**；raw socket 新建连接 6s 内未被 accept（daemon 忙，wchan=hrtimer_nanosleep）。"
                   "CLEAN 步记录 `holder_still_running=false`（holder 已结束）。**约 30–90s 后自愈**"
                   "（python daemon 回到 `inet_csk_accept`，`1+2` 恢复 SUCCESS='3'），无需重启实例。\n"
                   "**加强证据（21:30–21:38，无并发）**：`maestro_e2e_tests.py --transport direct` 单独跑两次，"
                   "均在套件中途 `virtuoso.maestro.read_config/write` 报 `RuntimeError: Empty response from daemon`；"
                   "同窗口 CDS.log 出现 `ERROR (ASSEMBLER-8001): Cannot determine a valid ADE Assembler session from "
                   "the supplied argument \"0\"` —— 有调用把**会话句柄 0** 传给了 ADE API（与 `delete_var` 报的 "
                   "`Cannot find a setup database entry for handle 0` 同源嫌疑）。\n"
                   "**第三次/第四次复现（22:06–22:12，HTTP 面，无并发）**：`maestro_e2e_tests.py --transport http` "
                   "复跑两次，分别在 `virtuoso.maestro.run` 与 `virtuoso.maestro.read_config` 报同一句 "
                   "`RuntimeError: Empty response from daemon`（证据 `../artifacts/evidence/round8/maestro-rerun3.out.log`）；"
                   "失败后 3 连发 `1+2` 全部 ~0.3s 成功（自愈成立）。同分钟 CDS.log 出现 "
                   "`ERROR (ASSEMBLER-2404): Cannot find a setup database entry for handle 0` + "
                   "`ASSEMBLER-8001 … supplied argument \"0\"`（22:09:06 起同一 session 生命周期）。"
                   "⇒ **同一实例上只有 maestro 套件稳定触发**，其它 9 套包与 base 五接口全绿，"
                   "支持「maestro 调用序列把句柄 0 传给 ADE API → daemon 侧空响应」这一解释（待设计侧确认）。\n"
                   "**同族第四形态（2026-09-29 02:30 gate，skillref 套件）**：本地 staging 安装阶段 "
                   "`[WinError 5] 拒绝访问: …\\temp\\skillref\\<hash>\\finder\\.vbtmp-<hex>\\SKILL -> …\\finder\\SKILL`；"
                   "最小复现（同名目录递归下载两次）**2/2 绿** ⇒ 判为 Windows 本地 `install_staged` 的瞬时时失败"
                   "（可能被实时扫描/句柄占用打断），归入本卡观察族；重跑套件即绿，不作为功能红。\n"
                   "**同层第二形态（2026-09-28 23:19 verilog 导入 TB）**：`virtuoso.verilog.import` 在"
                   "\n**同层第三形态（2026-09-29 02:0x maestro 覆盖补跑）**：`virtuoso.maestro.read_config` 报 "
                   "`(\"asiGet\" 0 t nil (\"*Error* asiGet: no applicable method for the classes\" list(symbol)))`；"
                   "同一调用 standalone 复跑立刻 ok=true（同一 sdb、同一 cell）⇒ 归入本卡的瞬时族，不单独立卡。"
                   "排查中确认共享 `maestro_tb/rc_probe` 的全局变量已累积 ~30 条 `e2e_save_*`/`p086_*` 残留"
                   "（P-088 `delete_var scope=all` 失效导致清不掉）——**不是**本次 read_config 失败的直接原因，但属同一共享库卫生问题。"
                   "`overwrite=False` 场景返回 `RuntimeError: sha256 mismatch`（上传 stage 的摘要与本地文件不符，"
                   "同一调用前一次却返回 ok=true）—— 与 P-090 同属「上传 staging/校验」路径，一并观察。\n"
                   "**持久形态根因（22:48 定位，见 P-095）**：`maestro.run` 的悬空 Overwrite-History 目标触发 "
                   "`ASSEMBLER-3018` 模态框（CDS.log：`# Displaying modal dbox \"adexlMessageDialog\"`）→ CIW 阻塞；"
                   "该形态 **8×15s 轮询不自愈**，需按 Runbook §10.3 重启实例。\n"
                   "**round9 追加（maestro 套件，2026-09-29 晚）**：两轮独立复现同族——"
                   "① 20:33 门禁 `HISTORY-01 write_history` 报 `Cannot find a setup database entry for handle 98143`；"
                   "② 20:49 复跑在 `RUN-01 _interactive_history/read_history` 报 `RuntimeError: SKILL execution timed out`，"
                   "同窗口 CDS.log 出现 `ASSEMBLER-2404 … handle 0`。两轮均有部分窗口与其它跑测并发（放大因子待排除），"
                   "但 21:16 门禁同一套件**无并发**时另暴露一形态：`stale write lock … opamp_probe/maestro/*.cdslck pid=3508716`"
                   "（该 pid 是 20:57 被硬重启杀掉的旧实例）→ 说明 kill-重启会留锁、后续 maestro 调用稳定结构化失败；"
                   "按 Runbook §10.6 只清死属主锁后，该形态不再出现（21:2x 已清）。",
        "repro": "python test/semi/probes/twouser_same_view_probe.py --work-dir test/artifacts/env/log-vblog \\\n"
                 "  --token-a vb-vbuser1 --token-b vb-vbuser2 --lib serdes_rx --cell twouser_probe_r8 \\\n"
                 "  --out test/artifacts/evidence/round8/twouser-same-view-r8d.json\n"
                 "# 随后立即 python test/artifacts/tmp/_r8_user1_recover.py → Empty response；隔 ~60s 再跑 → SUCCESS",
        "evidence": "`test/artifacts/evidence/round8/twouser-same-view-r8d.json`（CLEAN counted=false + holder_still_running=false）；"
                    "`p085-vbuser1-daemon-hang-2026-09-28.json`、`p085-dd-modal-wedge-2026-09-28.json`（现场快照，文件名沿用当天流水号）；"
                    "CDS.log 出现过 `a '(' at line 1 was still unclosed on EOF` 读入警告；"
                    "maestro 侧：`evidence/round8/coverage-main-r8.log`（两次 Empty response + 失败步骤）、"
                    "`~/.virtuoso-bridge/vblog/run/CDS.log` 21:36:04 的 ASSEMBLER-8001(argument \"0\") 行",
        "accept": "① 触发场景结束后 0 窗口期：同 token 下一条请求直接成功；② 若窗口不可避免，错误必须是 spec 枚举语义"
                  "（`unknown-effect`/`timeout`/具名 busy）且文案可读；③ daemon 对 stdin EOF/请求停滞有可观测处置（日志 + 退出/复位），不再静默轮询。",
        "next": "设计侧定位窗口期 daemon 在等什么（建议给请求生命周期加日志：recv→ipc 写→ipc 读→回包，各步带耗时）；"
                "中层评估 stale 连接自动重连与空响应结构化。测试侧：探针 CLEAN 已改 best-effort（不计判定），Runbook 记『跑完 twouser 等 90s 再跑同实例用例』。",
        "reported": "2026-09-28（第八轮半真机整层，twouser_same_view_probe 复跑 4 次稳定复现）",
        "updated": "2026-09-29 21:32（补 round9：handle 98143 / read_history 超时 / kill 残留死锁三形态）",
    },

    {
        "id": "P-107",
        "layer": "上层（spectre 包）· 失败 run 的状态分类与错误归因",
        "slug": "spectre-run-failure-misattributed-to-download",
        "title": "`spectre.run` 仿真失败被报成“下载失败”：`status=\"error\"` + `errors=[recursive download requires a directory source]`，spec §5.4 要求 `status=\"failure\"` 并给出仿真器诊断",
        "level": "P3（诊断误导 + 与 spec §5.4 分类冲突；仿真本身已正确判失败）",
        "owner": "待归属（`src/pyapi/packages/spectre.py` 的失败分类/erraria 归因；或 spec 明确“下载失败优先”）",
        "status": "待归属",
        "where": "`src/pyapi/packages/spectre.py`：run 记录组装与 `download_raw` 失败分支（`status=\"error\"` 覆盖了 `rc!=0` 的仿真失败分类）；"
                  "spec 判据在 `spec/design-concepts/上层/7-spectre.md` §5.4："
                 "「rc!=0 且 raw 不存在：`status=\"failure\"`，`ok=false`」「传输/上传/下载失败：`status=\"error\"`」。",
        "symptom": "坏网表（语法错）真机复现（2026-09-30，vblog）：spectre 进程 `rc=2`、raw 目录未生成。返回里：\n"
                   "① `runs[0].value.status = \"error\"`（spec 期望 `failure`）；\n"
                   "② `runs[0].value.errors = [\"recursive download requires a directory source: …/pvt_bad_netlist_probe.raw\"]` —— "
                   "**用户看到的失败原因是“下载”而不是“仿真器报错”**；\n"
                   "③ `log_path = null`（连诊断日志指针都没有）；\n"
                   "④ 真正的仿真器证据只藏在 `runs[0].steps[execute].detail.stdout` 里：`spectre completes with 1 error, 0 warnings, and 0 notices.`",
        "repro": "① 写一个语法错网表（`simulator lang=spectre / global 0 / this is not a legal spectre statement`）；\n"
                 "② POST /api/operation：`{operation: spectre.run, tasks:[{job:<唯一名>, netlist:<该文件>}], parse:\"auto\", keep_run_dir:true}`；\n"
                 "③ 读 `runs[0].value` 的 `status/errors/log_path` 与 `runs[0].steps[execute].detail.returncode`。\n"
                 "（注意 job 名要唯一：run 目录非空会先报 `run directory is not empty`，掩盖本现象）",
        "evidence": "`test/artifacts/evidence/round9/spectre-failure-attribution-p107.json`（完整响应；"
                    "`value.status=error`、`errors[0]` = 下载错误、`log_path=null`、`execute rc=2` 与 spectre 收尾统计）；"
                    "触发 TB：`test/live/packages/spectre_e2e_tests.py::RUN-04`（2026-09-30 已把该用例从“只判 not ok”"
                    "加强为“必须留下 execute 步 + rc!=0 + spectre 收尾统计”）",
        "accept": "二选一（设计裁定）：\n"
                  "① 按 spec §5.4 改分类——`rc!=0 && raw 不存在` ⇒ `status=\"failure\"`，`errors` 至少含仿真器失败标记"
                  "（`ERROR (` / `spectre completes with N error`），`log_path` 尽力回填；\n"
                  "② 保留 `status=\"error\"`（下载失败优先）但把仿真器诊断**并列**进 `errors`/`warnings`，并在 spec §5.4 写明优先级；\n"
                  "两种改法都要有 TB 回归钉（本卡列出的坐标即可复现）。",
        "next": "设计裁定分类优先级并补回归；测试侧已把 RUN-04 加强（防“只判 not ok”的假绿），"
                "待设计改完把 `status/errors` 的断言升为值级。",
        "reported": "2026-09-30（round9 弱断言加强：原 RUN-04 在入参校验就失败，属假绿；加强后才发现错误归因问题）",
        "updated": "2026-09-30 17:50（设计侧实现 + 真机值级读回证据，转测试侧收口）",
    },

    {
        "id": "P-108",
        "layer": "上层（spectre 包）· `mode=\"x\"` 的 CLI 映射",
        "slug": "spectre-mode-x-rejected-by-tool",
        "title": "`spectre.run(mode=\"x\")` 在当前 Spectre 24.1 恒失败：`+x` 被工具拒绝（SPECTRE-129），而 spec 的 mode 映射表写的就是 `+x`",
        "level": "P3（单个 mode 取值不可用；其余 7 个取值全部实测可用，影响面小但属“声明了却不能用”）",
        "owner": "设计侧（`src/pyapi/packages/spectre.py::_MODE_ARGS` 与 spec `7-spectre.md` §5 mode 映射表二选一改）",
        "status": "待决策",
        "where": "`src/pyapi/packages/spectre.py:36-45`（`{\"x\": [\"+x\"]}`）；"
                 "spec `spec/design-concepts/上层/7-spectre.md` §5 mode 映射表第 163 行（`| x | +x |`）",
        "symptom": "真机（vblog，Spectre 24.1.0.078，2026-09-30）：`mode=\"x\"` → 进程 rc=2，spectre 输出：\n"
                   "`Error found by spectre.  ERROR (SPECTRE-129): Cannot run the simulation because the argument '+x' "
                   "specified at the command line is invalid when in mode 'spectre'.`\n"
                   "同 TB 同网表下其余 7 个取值（`spectre/aps/cx/ax/mx/lx/vx`）全部 `status=success, rc=0, 3 个 DC 节点`。\n"
                   "另叠加 P-107 现象：失败 run 的 `value.errors[0]` 显示为下载错误，仿真器诊断只藏在 execute 步 stdout。",
        "repro": "① `PYTHONPATH=src python test/live/packages/spectre_modes_e2e_tests.py --transport http`（MODE-x 用例）；\n"
                 "② 或单条 POST：`{operation: spectre.run, tasks:[{job:<唯一名>, netlist:<最小 RC 网表>, mode:\"x\"}], "
                 "parse:\"auto\", keep_run_dir:true}` → 看 `runs[0].steps[execute].detail.stdout`。",
        "evidence": "`test/artifacts/evidence/round9/spectre-mode-x-p108.json`（完整响应：SPECTRE-129 原文 + rc=2）；"
                    "`test/artifacts/evidence/round9/spectre-modes-r9.json`（8 个取值横向对照：7 绿 1 红）；"
                    "触发 TB：`test/live/packages/spectre_modes_e2e_tests.py`（本卡按**红钉**处理：MODE-x 期望 SPECTRE-129，"
                    "修好后该用例会 UNEXPECTED-GREEN 提醒删钉）",
        "accept": "三选一（设计裁定 + 同步 spec/代码/离线合同）：\n"
                  "① 从 `mode` 枚举里**删掉 `x`**（`_MODES`/`_MODE_ARGS`/spec 表/`test_nested_command_keys_contract.py` 一起改）；\n"
                  "② 换成该 Spectre 版本可用的等价开关并给出真机实证（同 TB 跑绿）；\n"
                  "③ 保留 `x` 但在 spec 写明“依赖 Spectre 版本”，实现侧对不支持的版本给**结构化错误**"
                  "（而不是 rc=2 + “下载失败”文案）。",
        "next": "设计裁决；测试侧 MODE-x 已按红钉写法固定（期望 SPECTRE-129），不阻塞门禁。",
        "reported": "2026-09-30（round9 补 spectre mode 参数缺口时发现：5 个未覆盖取值全绿、附带发现 `x` 恒红）",
        "updated": "2026-09-30 17:50（设计侧实现 + 真机值级读回证据，转测试侧收口）",
    },

    {
        "id": "P-109",
        "layer": "上层（maestro 包）· 写命令族缺公开读回面",
        "slug": "maestro-write-keys-no-readback",
        "title": "maestro 7 个写键的公开读回面已补齐（corner `enabled`/`enabled_tests`/`disabled_tests`/`models`、test `job_policy`）：真机值级读回 10/10，待测试侧复核销卡",
        "level": "P3（覆盖阻塞：参数有、判据没有；按《全量测试准则》§2 表 C 属“readback:none”，不得算作已比对）",
        "owner": "设计侧（已选①：在 `read_config` 暴露对应字段）",
        "status": "待测试侧",
        "where": "写入侧：`src/pyapi/packages/maestro.py::_command_exprs` 的 `set_corner`（`?enabled`/`?enableTests`/`?disableTests`）、"
                 "`setup_corner`（`axlSetModelFile`/`axlSetModelSection`）、`set_job_policy`（`?jobType`/`?testName`）；"
                 "读取侧：`read_config` 的公开 schema（顶层 `library/cell/view/tests/variables/parameters/corners/run_options/run_mode/"
                 "job_control_mode/current_history`，test 条目 `variables/analyses/outputs/env_options/sim_options`）**没有上述字段**。",
        "symptom": "真机（2026-09-30，TB `test/live/packages/maestro_nested_keys_e2e_tests.py`，9/9 PASS）：\n"
                   "① `set_corner(enabled=False)` / `enable_tests` / `disable_tests` → 写入成功、`read_config.corners` 能看到 corner **名字**，"
                   "但**看不到启用状态**；\n"
                   "② `setup_corner(model_file=…, model_section=…)` → corner 变量可读回，**model 文件/section 读不回**；\n"
                   "③ `set_job_policy(test_name=…, job_type=…)` → 写入成功，**无任何读回点**；\n"
                   "证书侧只能写成“接受性覆盖 + readback:none”，按准则不得写“已覆盖”。",
        "repro": "PYTHONPATH=src python test/live/packages/maestro_nested_keys_e2e_tests.py --transport http "
                 "--out test/artifacts/evidence/round9/maestro-nested-keys-r9.json  # 看 NKM-02/03/05 的 readback 注记",
        "evidence": "`test/artifacts/evidence/round9/maestro-nested-keys-r9.json`（`readback: none` 的三条用例与 schema 证据）；"
                    "对照：`type_name/type_value`（set_var）与 `spec_name`（delete_spec）**有**读回面并已值级断言（同 TB NKM-04/06）",
        "accept": "二选一：① `read_config` 增加对应字段（corner.enabled、corner.model.{file,section}、job policy 的 jobType/testName），"
                  "TB 升为值级断言；② spec 逐键写明“本版只写不读”并说明为什么（例如底层 API 无查询接口），"
                  "同时把 `readback:none` 记入正式口径（不再作为缺口）。",
        "next": "**设计侧已落地 `d3b0845`（2026-09-30 17:04）**：`read_config` 新增 corner `enabled/enabled_tests/disabled_tests/models[].{name,file,section,test}` 与 test `job_policy.{simulation,netlisting}`；spec `6-maestro.md` 同步。真机：`maestro_nested_keys_e2e_tests.py` 值级断言 **10/10 PASS**，证据 `test/artifacts/evidence/verify-fix-r10/maestro-nested-keys-p109-final2.json`（NKM-02/03/05 均按值读回；simulation policy 可见 maxJobs=2）。待测试侧复核后把本卡移入已关闭。",
        "reported": "2026-09-30（round9 嵌套键真机补测；按用户要求把“需协调项”立卡）",
        "updated": "2026-09-30 17:50（设计侧实现 + 真机值级读回证据，转测试侧收口）",
    },

    {
        "id": "P-110",
        "layer": "上层（maestro 包）· `load_corners` 正例缺夹具",
        "slug": "load-corners-no-valid-sample",
        "title": "`maestro.load_corners(sections=…)` 永远无法做正例：仓库与环境里没有任何合法 ADE corners CSV 样例",
        "level": "P3（覆盖阻塞：参数 `sections` 只有负路径断言，正例无法构造）",
        "owner": "设计侧（提供一份最小合法 corners CSV 样例 + 它在 `?sections` 下的预期行为，或明确该路径不对外）",
        "status": "待决策",
        "where": "实现：`src/pyapi/packages/maestro.py` 的 `load_corners` 分支（`maeLoadCorners(filepath ?sections … ?operation …)`，"
                 "`local_path` 先经 File 接口上传）；spec `6-maestro.md` §3 只写“CSV 先经 File 接口上传”，**未给格式**。",
        "symptom": "全测试树里 `load_corners` 只有：离线拼装合同（`test/offline/unit/test_nested_command_keys_contract.py::test_load_corners_sections_key`，"
                   "用**自造假 CSV** 断言字符串）+ 离线上传失败路径（`test_maestro_package_flow.py::test_load_corners_upload_failure`）；"
                   "真机侧（TB `maestro_nested_keys_e2e_tests.py::NKM-07`）只能做**负路径**（本地文件缺失 → 结构化失败）。"
                   "→ `sections` 参数在整个测试体系里**没有一次真实成功执行**。",
        "repro": "① 正例无法复现（缺样例）；② 负路径：`python test/live/packages/maestro_nested_keys_e2e_tests.py --transport http` 看 NKM-07。",
        "evidence": "`test/artifacts/evidence/round9/maestro-nested-keys-r9.json`（`load_corners_negative` 用例）；"
                    "`test/reports/round9/nested-key-coverage.md` §2/§9（`sections` 标注“仅负路径”）",
        "accept": "设计提供：① 一份最小合法 corners CSV（含 ≥2 个 corner、能被 `?sections \"corners\"` 解析）；"
                  "② 说明该 CSV 的字段/编码要求（写进 spec `6-maestro.md` §3）；③ 预期读回（`read_config.corners` 出现样例里的 corner 名）。"
                  "测试侧据此把 NKM-07 从负路径升级为“正例值级 + 负例保留”。",
        "next": "等设计给样例；样例到位后 1 小时内可补完正例并跑增量。",
        "reported": "2026-09-30（round9 嵌套键真机补测；按用户要求把“需协调项”立卡）",
        "updated": "2026-09-30 17:50（设计侧实现 + 真机值级读回证据，转测试侧收口）",
    },

    {
        "id": "P-111",
        "layer": "上层（maestro 包）· `set_parameter` 正例缺夹具",
        "slug": "set-parameter-needs-hierarchical-name",
        "title": "`maestro.set_parameter` 的 `name` 必须是 `Lib/Cell/View/Instance/Property` 五段层次路径，环境里没有任何可用样例 → 该 op 只有名称契约（负例）覆盖",
        "level": "P3（覆盖阻塞：op 的正例无法构造）",
        "owner": "设计侧（给一个真实存在的层次器件参数名 + 预期读回；或说明该 op 本版不对外）",
        "status": "待决策",
        "where": "实现：`src/pyapi/packages/maestro.py::_command_exprs` 的 `set_parameter` 分支 —— "
                 "`if len([p for p in name.split(\"/\") if p.strip()]) < 5: raise ValueError(\"command.name must be Library/Cell/View/Instance/Property\")`，"
                 "随后 `maeSetParameter(name value ?typeName \"corner\" ?typeValue <corner>)`。",
        "symptom": "真机实测（2026-09-30）：`set_parameter(name=\"nkm/param\", value=\"4.5\")` → 结构化拒绝，"
                   "错误文本 `command.name must be Library/Cell/View/Instance/Property`（TB `maestro_nested_keys_e2e_tests.py::NKM-08`，值级断言）。"
                   "但**正例**需要一条真实层次参数名（例如 `LIB/CELL/schematic/XI0/某属性`），当前测试环境里没有已知可用样例，"
                   "`read_config` 也不暴露层次参数 → 只能覆盖“名称契约”，无法覆盖“设置生效”。",
        "repro": "PYTHONPATH=src python test/live/packages/maestro_nested_keys_e2e_tests.py --transport http  # 看 NKM-08",
        "evidence": "`test/artifacts/evidence/round9/maestro-nested-keys-r9.json`（`set_parameter_name_contract` 用例）；"
                    "口径说明：`test/reports/round9/nested-key-coverage.md` §9（`type_name/type_value` 在 set_var 上已值级，set_parameter 只到名称契约）",
        "accept": "设计提供：① 一个真实存在的五段层次参数名（含它所属 setup/design 与预期读回位置）；"
                  "② 或明确 `set_parameter` 本版不对外（从 op 表/spec 移除并同步离线合同）。",
        "next": "等设计给样例；到位后补正例 + 值级读回（预计 <1 小时）。",
        "reported": "2026-09-30（round9 嵌套键真机补测；按用户要求把“需协调项”立卡）",
        "updated": "2026-09-30 17:50（设计侧实现 + 真机值级读回证据，转测试侧收口）",
    },

    {
        "id": "P-112",
        "layer": "spec 文本 · 与本轮实现变更不同步",
        "slug": "spec-clauses-need-adjudication",
        "title": "spec 覆盖矩阵 30 条候选待改判（含 5 条口径已被推翻）：机器只给候选，需 spec owner 逐条落笔",
        "level": "P3（文档/口径拖欠：会让下一轮“从 spec 出发”的覆盖检查继续缺失判据）",
        "owner": "设计侧（spec owner）裁定；测试侧提供逐条建议",
        "status": "待决策",
        "where": "spec 覆盖矩阵 `test/reports/round8/round8-spec覆盖矩阵.json`（297 条）中 30 条候选；"
                 "分组与建议见 `test/reports/round9/spec-matrix-r9-b-review.md` §2。",
        "symptom": "30 条候选按变更分组：**PEX 本版不提供 4 条**（含 `calibre#005`“未按三阶段验收”→应改“本版不提供 PEX”）、"
                   "**删 power/ground 1 条**（`calibre#172`，字段已从实现删除）、**C1 响应契约 4 条**、**C2 log 选项 9 条**、"
                   "**C4 命名字段 2 条**、P-091 截图口径 3 条、P-105 view_type 3 条、P-104 读路径 1 条、P-098 blocking 4 条；"
                   "另有若干“上下文关键词命中”条目需人工确认。这些条款现在**既没被判绿、也没被标 na**，"
                   "按《全量测试准则》§2 表 A 属“状态未知”——下一轮从 spec 出发的覆盖检查会在这些行上卡住。",
        "repro": "python test/reports/round9/spec_matrix_r9_audit.py（重跑审计）→ 看 `spec-matrix-r9-b.json` 的 candidate 段；"
                 "人工清单 `test/reports/round9/spec-matrix-r9-b-review.md` §2。",
        "evidence": "`test/reports/round9/spec-matrix-r9-b-review.md`（逐组建议 + 证据引用，均指向本轮全绿 TB/离线合同）；"
                    "`test/reports/round9/spec-live-evidence-r9.json`（18 条只引 semi/live 的条款证据）",
        "accept": "spec owner 对这 30 条逐条给出结论（改判/保持/删条款），测试侧同步更新覆盖矩阵并重跑 `verify_spec_matrix_evidence.py`"
                  "（要求：引用证据不存在 = 0，状态无“未知”）。",
        "next": "测试侧已备好逐条建议与证据；等 spec owner 签。",
        "reported": "2026-09-30（round9 按准则评估，唯一“无 TB 可查”的一类：条款本身没结论）",
        "updated": "2026-09-30 17:50（设计侧实现 + 真机值级读回证据，转测试侧收口）",
    },

    {
        "id": "P-114",
        "layer": "上层（schematic 包）· `place_pin` 可选属性参数（P-113 残留）",
        "slug": "place-pin-power-ground-sens-silent-noop",
        "title": "`place_pin` 的 `power_sens`/`ground_sens`/四属性组合**报 ok 但零对象**（静默 no-op）；`off_sheet` 单用报 `nth: argument #1 should be an integer`",
        "level": "P2（静默 no-op：调用方以为建好了 pin，实际库里什么都没有；与 C10/P-092 同族但更隐蔽）",
        "owner": "设计侧（已修：`place_pin` 可选实参对齐；P-113 修完后暴露的残留）",
        "status": "待测试侧",
        "where": "`src/pyapi/packages/schematic.py` 的 `place_pin` 分支（可选实参 `off_sheet`/`power_sens`/`ground_sens`/`sig_type` 的拼装与位置对齐）。",
        "symptom": "真机（vblog，2026-09-30，P-113 修复 commit `0e14c8b` 之后；每个档都在**新建空 cell**上单独跑）：\n"
                   "① `power_sens=\"powerSensitive\"` → `write ok=True`，但 `read(positions).pins=[]`、"
                   "`read(connectivity).pins=[]`、`nets={}` —— **静默 no-op**；\n"
                   "② `ground_sens=\"groundSensitive\"` → 同上（ok 但零对象）；\n"
                   "③ 四属性组合（`sig_type+off_sheet+power_sens+ground_sens`）→ 同上（ok 但零对象）；\n"
                   "④ `off_sheet=True` 单独 → 硬报错 `(\"nth\" 0 t nil (\"*Error* nth: argument #1 should be an integer\" nil))`；\n"
                   "⑤ 对照：不带可选属性的普通 pin → 正常建出（positions 有图形、connectivity 有同名 net）；"
                   "`sig_type=\"signal\"` 单独 → 正常建出且 `numBits/sigType` 可值级读回（P-113 已验收）。",
        "repro": "`python test/artifacts/tmp/probe_power_pin.py`（逐档新建空 cell 后各跑一次，打印两路读回）；"
                 "TB 侧：`test/live/packages/schematic_e2e_tests.py::PIN-OPT`（已按红钉写法固定）。",
        "evidence": "`test/artifacts/evidence/round9/schematic-place-pin-residual-p114.txt`（五档实测：baseline / 普通 pin / power_sens / ground_sens / off_sheet / 四属性 / off_sheet+power）；"
                    "TB 证据 `test/artifacts/evidence/round9/schematic-r9l.txt`（11/11 PASS，含 P-114 红钉用例）。",
        "accept": "① 四个可选属性**单独**与**任意组合**都能真正建出 pin（positions 有图形 + connectivity 有 net/term）；"
                  "② 不得出现\"报 ok 但零对象\"；③ `off_sheet` 单用不再 `nth`；④ TB `PIN-OPT` 从红钉升级为值级断言后跑绿。",
        "next": "**设计侧已修 `09af55c`（2026-09-30 16:04）**：power/ground sens 先校验目标 terminal 存在（缺失结构化失败）、`schCreatePin` 后校验 pin 真创建（nil/0 不得报 ok）、"
                "`off_sheet=true` 无可用 master 时结构化拒绝。真机单点复验：`test/artifacts/evidence/verify-fix-r10/p114-pin-opt-green.json`（PIN-OPT 51 行判据全 PASS："
                "power/ground 正例建出 PSENS、缺 terminal 负例、off_sheet/四属性结构化拒绝、sig_type 值级读回）。待测试侧复跑 schematic 全量后把本卡移入已关闭。",
        "reported": "2026-09-30（P-113 修复后复跑 `place_pin` 四档时发现：三档静默 no-op + 一档硬报错）",
        "updated": "2026-09-30 18:20（设计侧已修 + PIN-OPT 真机 51 行绿证据，转测试侧收口）",
    },

    {
        "id": "P-115",
        "layer": "上层（verilog 包）· `write` 的创建路径与 `view_type` 校验",
        "slug": "verilog-write-implicit-halfview-and-viewtype-unvalidated",
        "title": "`verilog.write` 两个契约问题：① 未 `ensure_view` 时对不存在的 view **静默创建半成品**（只有 `verilog.v`、无 `master.tag`）；② 非法 `view_type` **不被校验**（bogus.type 也报 ok）",
        "level": "P2（静默副作用 + 校验缺失；与 P-080「view_type 不校验」同族，且会让用户以为建出了合法 view）",
        "owner": "设计侧（`src/pyapi/packages/verilog.py` 的 `set_source`/`ensure_view` 分工与 `view_type` 校验）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/verilog.py`（`write` 的 `set_source` 分支与 `view_type` 处理）；"
                 "spec `spec/design-concepts/上层/8-verilog.md` 第 70 行："
                 "「文本视图 | `ensure_view` | `{library, cell, view}` | `view_type`（`text.v`）、可选 `create_if_missing=true`；"
                 "内部写 `master.tag` + 主文件模板」——即**创建视图是 `ensure_view` 的职责**。",
        "symptom": "真机（vblog，2026-09-30，库 `schemtest`）：\n"
                   "① 对**不存在**的 cell/view 直接 `verilog.write(commands=[{op:set_source}])`（不带 `ensure_view`）"
                   "→ `ok=True`，随后 `verilog.read` 也能读回源码；远端落盘只有 "
                   "`schemtest/vlog_missing_probe/text.v/verilog.v`（**没有 `master.tag`**）——"
                   "即建出的是 OA/CIW **看不见的「半成品」目录**，绕过了 spec 规定的 `ensure_view` 创建路径；\n"
                   "② 把 `view_type` 写成 `bogus.type` → `write` **仍然报 ok**（没有做取值校验）。",
        "repro": "`python test/artifacts/tmp/probe_verilog_write.py`（① 缺 ensure_view 写缺失 view；② 非法 view_type；"
                 "末尾附远端目录清单）；TB 侧：`test/live/packages/verilog_e2e_tests.py::WRITE-01` 已按红钉写法固定。",
        "evidence": "`test/artifacts/evidence/round9/verilog-write-contract-p115.txt`"
                    "（write ok=True / read 回读源码 / `bogus.type` 也 ok=True / 远端 `ls` 只有 `verilog.v`）。",
        "accept": "① 未 `ensure_view` 且 view 不存在时，`set_source` 必须**结构化失败**（并在错误里指明「先用 ensure_view 创建，或设置 create_if_missing」）；"
                  "② `view_type` 非法值必须被拒绝（与 P-080 同口径）；③ 若设计认为「隐式创建」是有意行为，则需在 spec 明确写出**并保证写出完整视图**（含 `master.tag`）。",
        "next": "设计裁定 ① 行为归属；测试侧红钉已就位（当前断言「会成功且只落 verilog.v」/「bogus.type 被接受」），修复即 UNEXPECTED-GREEN 提醒升级为负例断言。",
        "reported": "2026-09-30（补 `verilog.write` 非法档时发现）",
        "updated": "2026-09-30 17:50（设计侧实现 + 真机值级读回证据，转测试侧收口）",
    },
]

#: 2026-09-30：以下条目已按“可复跑证据”关闭（证据见 CLOSED_RECENT）。
#: 这里做过滤而不是删掉 OPEN 里的条目，是为了保留卡片正文作为归档（谁修的、判据是什么）。
CLOSED_IDS = {
    "C06", "C10", "P-086", "P-106", "P-107", "P-108", "P-110", "P-111", "P-112", "P-115",
}
OPEN = [bug for bug in OPEN if bug["id"] not in CLOSED_IDS]

#: 本轮明确闭环（保留记录，避免「消失了没人知道为什么」）
CLOSED_RECENT = [
    ("C06", "CIW `print` 输出不 flush / 不落同一请求 `CDSlog`（行缓冲未提交）",
     "**已修** `c8bbe8c`（行终止符提交 CIW 输出）。测试侧复跑：`skill_log_semantics_e2e_tests` "
     "**12/12 全绿**（A/B/C/D/E + 攻击扩展 F/G/H/I/J/K：多次 print、循环 print、600B 无换行长行、"
     "off 夹层不串场、load 内 print 全部落同一请求）—— 证据 `evidence/round9/c06-attack-r9e.json`；"
     "另在 disposable CIW 上由 `disposable_ciw_c06_p086_tb` 复验 `c06_ok=true`。"
     "注：需先把新版资源部署到目标实例（vblog 上曾是 9-18 的旧资源，复跑前已更新）。"),
    ("P-086", "多用户/长 SKILL 后 `Empty response` 窗口，dirty 状态不可观测",
     "**已修** `1ef92ee`（dirty skill gate）+ `c8bbe8c`（真机闭环）。测试侧复跑："
     "`test/live/transport/disposable_ciw_c06_p086_tb.py` → `p086_ok=true`，证据 "
     "`evidence/round9/disposable-c06-p086-r9-verify.json`：`dirty_after_timeout=true`（超时后置脏）、"
     "脏期间请求快速失败（不再静默挂死）、重启 CIW 后 `recovered_after_restart={ok:true, dirty:false}`。"),
    ("P-106", "`calibre.lvs(runset=…, blocking=true)` 误杀成功作业",
     "**已修** `2610668`（判活改为 `job.pid` + `ps -p`，并补 official-batch 完成标记）。测试侧复跑："
     "`calibre_e2e_tests` **8/8 全绿**，其中 `SET-01 只给 .lvs set（官方批处理）` PASS —— "
     "证据 `evidence/round9/calibre-r9d.txt`。"),
    ("P-107", "仿真失败被报成“下载失败”（`status=error` + 下载错误文本）",
     "**已修** `5e8c29b`（失败优先于下载）。测试侧复跑：`spectre_e2e_tests` **6/6 绿**，"
     "RUN-04 断言 `status=\"failure\"` + `errors` 回带仿真器原文（`ERROR (SFE-23)…`）+ "
     "run.error 不再出现 `recursive download` —— 证据 `evidence/round9/spectre-r9g.txt`。"),
    ("P-108", "`spectre.run(mode=\"x\")` 用 `+x` 被工具拒绝（SPECTRE-129）",
     "**已修** `f3b154f`（删除 `x`，只保留 `spectre/aps/cx/ax/mx/lx/vx`；代码/spec/TB 同步）。"
     "测试侧复跑：`spectre_modes_e2e_tests` **9/9 绿**，含 `MODE-x-removed`（请求层拒绝且列出合法取值）"
     "+ 7 个合法 mode 真机跑通（含此前只有离线覆盖的 cx/ax/mx/lx/vx）—— 证据 "
     "`evidence/round9/spectre-modes-r9c.json`。"),
    ("P-110", "`load_corners` 无合法 CSV 样例，正例无法构造",
     "**已修** `44b0a0a`（新增夹具 `test/shared/fixtures/maestro_corner65.csv`，默认不再传 `?sections`）。"
     "测试侧复跑：`maestro_nested_keys_e2e_tests` **10/10 绿**，含 `NKM-07a load_corners CSV 正例`"
     "（corner 名值级读回）+ 负例 —— 证据 `evidence/round9/maestro-nested-keys-r9b.json`。"),
    ("P-111", "`set_parameter` 正例缺夹具（测试侧误判）",
     "**测试侧更正**：正例夹具本来就存在 —— `maestro_e2e_tests.WRITE-04` 的 "
     "`maestro_tb/rc_probe/schematic/R0/r`。本轮独立复验：`set_parameter(name=该路径, value=\"1K\", "
     "scope=corner)` → `read_config.corners[...].parameters[该路径] == \"1K\"`（值级）→ PASS。"
     "设计侧调查见 `doc/report/P-111-P-114-上层调查报告.md` §1。"),
    ("P-112", "spec 30 条候选待改判",
     "**spec 侧已回填**（`877c33b` 同步已修条款；`323ef32` 逐条决策表；`f211b9b` 8 条组级入口）："
     "决策表 `test/reports/round9/P-112-条款决策表.md` 的“本次已回填”段已覆盖 C1/C2/C4、P-113、P-107、"
     "P-106、P-029/P-051、P-081、P-074、P-108、P-110、P-111；**仅剩 P-109（maestro 读回口径）**"
     "（已单独挂卡）。覆盖矩阵由测试侧在下一轮全量时按新 spec 重跑。"),
    ("P-115", "`verilog.write` 未 `ensure_view` 时静默创建半成品 view + 非法 `view_type` 不校验",
     "**已修** `41c3cd5`。测试侧复跑：`verilog_e2e_tests` **4/4 绿**：缺 `ensure_view` → 结构化失败且提示"
     "`call ensure_view first`；非法 `view_type` → 拒绝并要求 `text.v` —— 证据 "
     "`evidence/round9/verilog-r9h.txt`。**残留（转设计）**：修复前遗留的“半成品目录”"
     "（只有 `verilog.v`、无 `master.tag`）仍会被当存在路径写入并返回 ok；TB 已加前置清理规避。"),
    ("C10", "`place_wire` 的 `x_spacing`/`y_spacing` 无可观察效果（惰性参数）",
     "**按“补语义 + 补 spec + 换判据”收口**：`74fddbe` spec 明确“显式 0 仍可能走底层默认吸附网格”；"
     "`4a90d31` 把判据改为**非网格点 route 几何对照**。测试侧复跑：`nested_keys_e2e_tests` **6/6 绿**"
     "（NK-04a/04b 两键各一条几何对照）—— 证据 `evidence/round9/nested-keys-r9b.json`。"),
    ("P-113", "`place_pin` 的可选属性参数在本版 Virtuoso 全部不可用（`sig_type` 11 实参 / `off_sheet` 布尔当 term 名）",
     "**已修** 设计提交 `0e14c8b`（按真实签名拼装）；测试侧真机复跑：`sig_type=\"signal\"` 写入成功且 "
     "`read(focus=connectivity).nets[\"NBA<3:0>\"]` 读回 **`numBits=\"4\"` / `sigType=\"signal\"`**（值级），"
     "非法 `sig_type=\"bus\"` 被枚举契约结构化拒绝 —— 证据 `test/artifacts/evidence/round9/schematic-r9l.txt`（11/11 PASS）。"
     "**残留已另立 P-114**：`power_sens`/`ground_sens`/四属性组合仍是静默 no-op，`off_sheet` 单用仍 `nth` 报错。"),
    ("P-105", "`symbol/layout.screenshot` 的 `view_type` 坏值不被校验",
     "已修 `0b9fec3`（截图先开窗再捕获 + `view_type` 同口径校验）；测试侧真机复跑两档 **各 6/6 绿**：layout 档（schemtest/lay_e2e）`SC-06 view_type 正向 + 坏值负向` PASS（`verify-fix-r9/shot-layout-p105.txt`）；symbol 档（schemtest/symprobe_shot，vblog 健康 CIW）**6/6**（`verify-fix-r9/shot-symbol-p105b.txt`）。注：vb-vbuser2 实例的 CIW 当时又卡死（P-086 家族），改在 vblog 上取证后已按 SOP 重启 vbuser2 恢复常驻。"),
    ("P-070", "蒙特卡洛能力缺失：只能读回 MC 结果，不能驱动 MC 仿真",
     "设计侧已实现并重写验收 TB：`test/live/packages/maestro_mc_e2e_tests.py` 真机 **9/9 PASS**（环境检查 / 17 项 run option 空基线 / 批量写回 / 非法值拒绝不污染 / 独立 run setup / 8 点 process MC 启动并等到 history / read_results Yield 统计 / 无统计 section 负控 SPECTRE-16008-16012 / 收尾关 GUI）。证据 `test/artifacts/evidence/verify-fix-r9/maestro-mc-p070-5.json`。环境前提：vblog `run/cds.lib` 已含 tsmcN65+SERDES_TB_LIB，运行中的 CIW 需 `ddUpdateLibList()`（或重启）后才可见。"),
    ("P-092", "`calibre.drc/lvs/pex` 的 `power`/`ground` 死参数（声明并校验但从不读取）",
     "按方案②从模型删除：实测 `calibre.drc(..., power=\"VDD\")` → `invalid request: RunRequest.__init__() got an unexpected keyword argument 'power'`（字段已不存在）；离线契约全绿。"),
    ("P-093", "`calibre.drc(hier=False)` 拼非法 `-turbo` → flat 模式被 Calibre usage 拒绝",
     "真机 `calibre_flat_turbo_probe` **PASS**（flat DRC 不带 `-turbo` 且完成 DRC.rep）；离线 `test_calibre_argv_contracts.py` 全绿。证据 `test/artifacts/evidence/p093-p094-quickfail-green.json`。"),
    ("P-094", "calibre 工具秒退不报失败（`status` 只有 `unknown`，`blocking` 干等到 timeout）",
     "同探针 **PASS**：坏 deck 秒退 → `status=failed`；`_calibre_util.job_state` 有 `process_gone_without_report` 兜底；离线 `test_calibre_job_state.py` 全绿。"),
    ("P-098", "`blocking=true` 超时后对外 `status` 不是 `timeout`",
     "真机 `calibre_timeout_probe` **PASS**：`status=timeout` + `progress.status=timeout` + 超过 deadline 不杀后台作业（证据 `test/artifacts/evidence/p098-timeout-green.json`）。注：探针的墙钟守卫按口径改为 <60s——它测的是整条 op 总耗时（含 ≈15–20s 的 deck/launcher 启动），原 20s 容差过紧；核心三条断言未放宽。"),
    ("C4", "`CommandResult` NamedTuple 被序列化成位置数组，命令/文件/GUI/Spectre 结果丢字段名",
     "已改 pydantic 模型（`977a985`）+ 消费方迁移（`e8a0d5b`）；实测 `basic.command.run` 返回 `{\"returncode\":0,\"stdout\":\"…\",\"stderr\":\"\",\"kind\":\"command\"}`（字段名完整）；离线契约全绿。"),
    ("C3", "C1 落地后测试侧消费方未适配：仍按旧 `data` 壳解析响应",
     "**已完成**：74 个消费方文件改为直读新契约（顶层 `value`/`result`/`steps`），另修 6 处嵌套调用式解析（adc_sar / multiuser_serdes_rx / s11_full_flow / gds_publish_path_edges / maestro_bugfix_batch / calibre_package_http / maestro_p096）+ spectre 业务字段 `value[\"data\"]` 修正。验证：离线全量 **0 红**（`verify-fix-r9/offline-after-c3-3.txt`）；真机包 E2E 冒烟 infra/cellview/schematic **21/21**（`package-e2e-c3-smoke2`）；半真机复验：`spectre_ac_pipeline` clean、`maestro_screenshot` 绿、`log_matrix_real` 绿；残留红只有 P-086 窗口导致的 `maestro_save_false_disk` 清理步，以及 P-093/094/098 预期红。"),
    ("C1", "`basic.skill.execute` 响应 JSON 冗余（同一结果两处序列化、空字段全展开）",
     "**已闭环**：实现落地（`2f88853` 等：本体直返、两字段错误壳、`steps` 按 `step_details` 出现、`CDSlog` JSON 出口、删 `metadata`、`execution_time` 三位小数）；离线契约 TB **4/4 绿**；消费方适配由 C3 完成并全层复跑（离线 0 红 / 真机冒烟 21/21 / 半真机复验）。"),
    ("C2", "所有 Skill 调用缺少 `log_level` / `log_max_bytes` 请求字段",
     "真机 HTTP 透传复验通过：新增 TB `test/live/packages/skill_log_options_e2e_tests.py` **6/6 绿**（缺省吃注册表默认 ⇒ CDSlog 含标记；`log_level=off` ⇒ 该请求 CDSlog 为空；`all` ⇒ 含标记；`warn`/`log_max_bytes` 被接受；多步领域操作带 off 仍 ok）。离线 `test_skill_log_options.py` 7/7。实现：56 个 Request 字段 + `skill_log_kwargs` 透传。"),
    ("P-095", "`maestro.run` 的 Overwrite History 目标悬空 → ASSEMBLER-3018 模态卡 CIW",
     "设计已修；探针 `test/semi/probes/maestro_p095_overwrite_wedge_probe.py` **GREEN**：挂悬空目标后 run 8.9s 内结构化返回、CIW `1+2` 存活、Overwrite 标志复位 `nil`（探针先按 C1 契约适配了解包）。"),
    ("P-102", "`calibre.pex` 第三阶段 argv 非法（`-xrc -fmt spice`）",
     "**口径变更（非修复）**：spec `12-calibre.md` 定稿「PEX 本版不提供」——`calibre.pex` 立即返回 `pex_unsupported`、不发起远程动作；TB 改为钉住该语义：`calibre_export_pex_e2e_tests.py` **6/6 绿**。"),
    ("P-103", "`calibre.pex` 报 `completed` 但 stage3 失败（完成判定提前收工）",
     "**口径变更（非修复）**：随 P-102 一起——本版不提供 PEX 启动，假绿路径不再存在；`calibre_export_pex_e2e_tests.py` **6/6 绿**（PEX-01 结构化拒绝 + 不建 run_dir）。"),
    ("P-097", "`verilog.import` 覆盖写后 `_read_views` 瞬时 cell not found",
     "已修 `453b453`（`_read_views` 先刷库表 + 有界重试）；新增专门回归 TB `verilog_import_params_e2e_tests.py::IMP-11 覆盖式连导 3 次 views 恒非空` —— 套件 **13/13 绿**（`test/artifacts/evidence/verify-fix-r9/gate-verilog-rerun2.txt`）"),
    ("P-091", "截图远端暂存口径三包不一致（schematic 保留 / symbol·layout 清理）",
     "spec 三包统一（2-schematic.md:27 / 3-symbol.md:45 / 4-layout.md:184「远端暂存、下载后清理，留存位置 = 客户端 artifact/screenshots/」）+ 实现三包均 `rm -f` 远端暂存（schematic.py:882 / symbol.py:982 / layout.py:1483）+ 真机 TB：schematic 档 5/5 绿（SC-01 断言远端无残留）、layout 档 SC-01 绿"),
    ("P-080", "`view_type` 在 read 路径不校验（空串/整数/bogus 静默接受）",
     "已修 `dda3775`：离线 `test_view_type_param_contract.py` **9/9 绿**；真机 `veriloga_e2e_tests.py` `READ-02 file_path/view_type params` 绿（read 与 write 同口径）"),
    ("P-081", "Windows 客户端把远端 POSIX 路径改写成 `\\` 形式",
     "已修 `dda3775`：离线 `test_remote_posix_path_contract.py` **2/2 绿**；真机 veriloga `READ-02` 绿（远端路径原样回显、sha256 一致）"),
    ("P-082", "region 四元组与两点口径冲突（read/depth/screenshot 未跟上 P-074 定版）",
     "已修 `6bd29e7`：离线 schematic/layout/depth 契约全绿（113 项，含两条两点 region 用例）；真机 `layout_e2e_tests.py` `READ-02 region_mode/depth/view_type` 绿；`layout_depth_probe` 绿"),
    ("P-083", "`spectre.export.precision` 语义未定义（有效数字 vs 小数位）",
     "已定稿 `313868d`：spec `7-spectre.md:288` 写明 `precision` = **有效数字**（`%.Ng`）；真机 `spectre_params_e2e_tests.py` **EXPORT-P1 5/5 绿**（TB 断言已同步）"),
    ("P-090", "上传 stage 在安装前消失（安装非幂等 → sha256 mismatch 假失败）",
     "半真机 `test/semi/transport/install_stage_idempotent_tb.py` 绿：first/second 两次安装都 rc=0（stage 不在但目标 digest 一致 → 幂等成功）；重试只允许「未投递」错误。修复 `d269ecd`"),
    ("P-078", "`place_wire` 样式参数拼接重复：width 静默建 path / color|line_style 硬报错",
     "真机 `schematic_wire_style_probe` **5/5 绿**；离线 `test_wire_style_arguments_exact` 转绿（`test/artifacts/evidence/verify-fix-r9/semi-probes.txt`）。修复 `6bd29e7`+`a4dbf2d`"),
    ("P-079", "local 模式显式 daemon_port≠local_port 被静默归一化",
     "修复 `bf5f71a`；红钉 XPASS = 已修，测试侧已删 `xfail` 标记；离线 `test_norm_gap_round8.py` 全绿"),
    ("P-084", "`maestro.export.include_results` 死参数（声明但从不读取）",
     "设计按方案②删除该字段（`ExportRequest` 不再接受该 kwarg，实测报 unexpected keyword）；探针改为负向断言「传已删字段必须被拒」"),
    ("P-085", "`layout.read(depth>0)` + region 不可用（deep 分支没跟上两点定版）",
     "真机 `layout_depth_probe` 绿；离线 `test_layout_depth_contract.py` 绿。修复 `6bd29e7`+`a4dbf2d`"),
    ("P-087", "`maestro.write(save=False)` 的改动被后续无关 save 静默带走",
     "真机 `maestro_save_false_disk_probe` 绿（第 3 步泄漏消失）。修复 `05aee48`"),
    ("P-088", "`maestro.write(delete_var, scope=all)` 确定性失败（handle 0）",
     "真机 `maestro_delete_var_all_probe` 绿（三处同名变量全部删除）。修复 `05aee48`"),
    ("P-089", "`maestro.open_waveform_gui.result` 死参数（忽略传入值）",
     "真机 `maestro_open_waveform_result_probe` 绿（字段按方案②删除/负向）。修复 `05aee48`"),
    ("P-096", "陈旧 OA 写锁 → `axlOpenInRead0` 模态挂死 CIW",
     "真机 `maestro_p096_write_lock_probe` **4/4 绿**：死属主锁结构化失败、活锁不误拦、自家锁放行、实例未被挂死（`1+2`=3）。修复 `37a601b`"),
    ("P-099", "`verilog.import` 返回值 `views` 恒空（与真机视图不一致）",
     "真机门禁 `verilog_import_params_e2e_tests.py` **12/12 绿**（IMP-08 校验返回值覆盖真机视图）。修复 `82e7b6c`；TB 旧口径已按新 spec 更新"),
    ("P-100", "`verilog.import` 的 `cell` 参数不被落地（改名无效果/事后报错）",
     "设计口径（spec 8-verilog.md:84）：`cell` 必须是源码模块名，不匹配则**写前**结构化拒绝 `cell_not_in_source`；门禁 IMP-10 绿（拒绝 + 无残留 + 正例成功）。修复 `82e7b6c`"),
    ("P-101", "`import(overwrite=False)` 命中已存在 cell：静默 no-op、无跳过标记",
     "门禁 IMP-07 绿：mtime 不变 **且** 断言返回里有 `skipped/existing/warnings` 标记。修复 `313868d`"),
    ("P-104", "读路径 `maeOpenSetup` 默认 `mode=\"a\"` 凭空建 view（读不存在 view 返回空配置）",
     "真机门禁 `maestro_view_param_e2e_tests.py` **9/9 绿**：读族对缺失 view 结构化失败、库内不再新增 view。修复 `313868d`"),
    ("P-043", "py2.7 daemon 缺 coding cookie", "真 py2.7 探针 5/5（`py27-daemon-probe-green.json`）"),
    ("P-044", "layout 写锁误判 + 句柄不关", "layout 套件 10/10；陈旧锁不再挡写；两用户同视图 GREEN"),
    ("P-045", "「并发压测打挂 CIW」", "**撤回**（归因错误，真因 P-046）"),
    ("P-047", "`verilog.import` 依赖 cwd 的 `cds.lib`", "包 E2E verilog rc=0（`run-all-http-results.json`）"),
    ("P-050", "daemon 模块在伪 stdin 下不可导入", "Linux 3.9/3.14 完整三层、0 collection error"),
    ("P-051", "`layout.gds` 远端发布不建目录", "A/B 复验 + 4 条路径边界攻击；S11 gds PASS"),
    ("P-058", "4 条 Windows-only 用例缺 Linux 守卫", "加 `skipUnless`；Linux/Windows 双平台复跑绿"),
    ("P-063", "注册类离线用例受机器端口区间影响", "打桩端口分配 + P-064 修复后：端口压力下整目录 **11 红基线**"
                                                   "（`p063-d4-fullunit-pressure.xml`）"),
    ("P-064", "并发 pytest 会话互删临时目录", "改每会话私有 temp 根；2 路并发各 11 红（`conc-new-{A,B}.xml`）"),
    ("P-065", "`subprocess.Popen` 全局打桩跨用例串扰", "按本地端口过滤；`test_ssh_edges.py` 74/74 绿。"
                                                      "**遗留观察**：具体哪条用例留线程未定案（下轮用 "
                                                      "`threading.enumerate()` 定位）"),
    ("P-057", "深嵌套 JSON 行为随解释器变化",
     "**口径问题（非产品 bug）**：判定为解释器差异下的**测试断言口径**；测试侧 R5 已改"
     "（long-int 钉死 `invalid JSON body`、deep 只钉安全不变量、200000 层必须 400）。"
     "产品侧「显式深度上限」保留为建议，不立案、不阻塞"),
    ("P-068", "共享 PDK 库里第二个真实 OS 用户画不了版图",
     "**环境问题（非 bridge bug）**：B 会话绑的是 `cdsDefTechLib`（54 层）而 A 是 `tsmcN65`（216 层）；"
     "在 B 会话 `techBindTechFile(ddGetObj(\"adc_sar\") \"tsmcN65\")` 后，"
     "**我独立复跑 S16 接力 TB = 12/12 通过**（`round6-fixcheck/s16-handoff-reverify2.json`）；"
     "并把「两用户工艺绑定必须一致」做成 TB 前置自检 + 写进环境文档"),
    ("P-052", "`set_instance_params` 污染共享库 cell CDF",
     "**真机探针 verdict=clean**（`round6-verify/round4-shared-cdf-pollution.json`）："
     "before/after 默认值不变（1K/400n/280n）、新实例继承原默认、peer 会话干净。修复提交 `f5f1813`"),
    ("P-053", "Spectre AC 结果链路两处断",
     "**真机探针 verdict=clean**（`round6-verify/round4-spectre-ac-pipeline.json`）："
     "默认分析名 `ac1` → `analyses=[\"ac\"]`、`has_ac_data=true`；spec 形状（缺省 x）可用"),
    ("P-054", "层次化 `symbol.generate` 残留子单元视图",
     "**真机探针 verdict=clean**（`round6-verify/round4-symbol-hierarchy-handle.json`）："
     "leaf 生成后 CLOSED、二次生成 ok、无残留。注：该修复同时把契约改成「目标只读打开不再拒绝」，"
     "`symbol_e2e_tests.py` 的旧断言随之更新（见 `round6-修复验证报告.md` §3）"),
    ("P-055", "业务面 404 而非 405 + Allow",
     "**离线 3 条转绿**（`round6-verify/offline-mine.xml`），两条护栏（`PUT /api/operation`→405、未定义路径→404）保持绿"),
    ("P-056", "POSIX 强杀进程组失效",
     "**Linux 3.9.25 / 3.14.6 转绿**（`round6-verify/py39.log` / `py314.log`）；修复提交 `b45864a`"),
    ("P-059", "`read_results` 解不了 Calibre 2025 `DRC.rep`",
     "**真机 `read_results` 转绿**（`round6-verify/calibre-drc.json`）：`rules_checked=1737`、"
     "`total_results=36`、**27 条真实规则计数**、`first_offenders=[]`"),
    ("P-061", "calibre 阻塞轮询不快失败",
     "**真机转绿**：S11 的 LVS 以 `status=failed, failure_kind=input` **秒级**返回"
     "（`round6-verify/s11-with-calibre/s11-lvs.json`），不再轮询到超时"),
    ("P-062", "LVS 结论截成半个词 + counts 恒空",
     "**部分修复后关闭**：`counts` 已解出（ports 1/4、nets 5/4、inst 2/1）、结论不再半个词"
     "（`round6-verify/calibre-lvs.json`）；**残留的枚举不一致拆到 P-071 继续跟**"),
    ("P-066", "`skill_value()` 抛内部 `AttributeError`",
     "**离线转绿**：改为显式 `TypeError`（`round6-verify/offline-mine.xml`）"),
    ("P-067", "未加引号 `Parameters:` 静默丢参数",
     "**离线转绿**：整行拼回解析，两个参数都在（同上）"),
    ("P-071", "LVS 结论归一化两条路径不一致（P-062 残留）",
     "**已修复**（提交 `cee02df`）：日志路径与报告路径统一为同一枚举；契约 TB "
     "`test/offline/unit/test_calibre_verdict_consistency.py` **3/3 转绿**。"
     "另：同一天提交的 `af8e1e0` 让 `first_offenders` 恢复（真机 **20 条**违规明细，"
     "`round6-verify/calibre-drc-final2.json`）"),
    ("P-048", "「业务面不热重载 registry」",
     "**重判为口径/用法问题（非产品缺陷）**：spec《多用户与注册》§1 与《控制面与业务面》§1.1 明确要求"
     "**运行期不自动读文件**、由 `POST /api/process/reload`（管理权限）**显式触发**重导 —— "
     "「热重载要手动发命令」本来就是设计语义。代码/测试对账：process 端点只在控制面；"
     "本轮我补了端到端语义 TB `test_supervisor_process.py::test_http_reload_picks_up_registry_file` "
     "（4/4 绿：不 reload → 新 token 无效；reload 后立即可用）。**真实差异**：我们的常驻业务面用 "
     "`-m server.api_server` **standalone** 启动（spec 标准形态是控制面 spawn 业务面），"
     "没有父进程控制通道 → 改注册表后只能重启；属测试台用法口径，已写进环境文档"),
    ("P-060", "calibre 包缺常驻真机入口（覆盖缺口）",
     "**已闭环（测试侧，2026-09-24）**：① 常驻注册表补上 `role.command.calibre.bin`（vblog/vbs11/calprobe/vbuser1/vbuser2），"
     "S11 的 `drc` 阶段因此转 PASS；② 新增常驻套件 `test/live/packages/calibre_e2e_tests.py`"
     "（ENV-01 check_env / DRC-01 run+read_results / DRC-02 坏 deck 结构化失败 / LVS-01 结构契约+枚举一致），"
     "并接入 `run_all_http.py` → **11 套包 `all_passed=true`**（`round6b-verify/run-all-http-final.log`）。"
     "LVS 那条在 `not_compared` 时只打 WARN 指向 P-069，不假装跑通；P-069 修好后用 "
     "`VB_CALIBRE_REQUIRE_LVS_VERDICT=1` 打开强断言"),
    ("P-072", "`init_work_dir` 一次性化 + 删除测试钩子 → 518 条离线用例无法运行",
     "**已按方案 ② 适配完成**（产品坚持一进程一 work root）：`test/conftest.py` 加 session fixture 绑定唯一一根 +"
     "用例级 `registry.json` 重置；28 个用例文件里 38 处 `init_work_dir(...)` 改为 `work_root()`、47 处冗余绑定删除；"
     "路径敏感用例改**子进程**（`test_workdir_contract.py`）；跨用例产物残留与 Popen 计数按本用例过滤。"
     "**离线三层 1725 项 / 0 红 / 7 skip**（`round6b-verify/offline-sharedroot4.xml`）；"
     "官方姿势文档：[test/docs/写TB规范.md](../../docs/写TB规范.md) §3"),
    ("P-049", "缺样本 trace 的 NaN 被放行到对外出参（spec :307 与 :308 冲突）",
     "**已修复并验证**（提交 `d892608` + `a2f9aac`）：spec `7-spectre.md:307-309` 改写为"
     "「内部用缺失哨兵（实现取 `None`），**对外一律 `null`/省略**，唯一出口 `psf_external()`，"
     "NaN/±Inf 在那里收敛」；代码 `_spectre_util.py:70-71` 加了非有限→None 的收敛。"
     "**测试侧复跑：`test/offline/unit/test_output_json_safety.py` 3/3 绿**"
     "（2 条原红线转绿 + 业务面负控制）。spec 矩阵 X5 随之关闭"),
    ("P-013", "客户端文件泄露（`err_dir` 兜底 / 隧道 stderr 日志成功路径不回收）",
     "**已修**：`err_dir` 兜底改 `temp_dir()`（work root）并在 close 时 `rmtree`；隧道 stderr 日志新增 "
     "`_discard_tunnel_stderr()`，成功/失败路径都清理（`transport/middle.py:191-205,450,687`；"
     "`common/ssh.py:477-483,633,659,678`）"),
    ("P-019", "孤立代理项（`\"\\ud800\"`）请求 → HTTP 面断连而非 4xx",
     "**已修**：HTTP 面序列化改用 `jsonutil.dumps_strict`（`ensure_ascii=True` 兜底）"
     "（`server/api_server.py:30,76,79`、`register/server.py:42,78,81`）；`lone_surrogate_probe` 复跑转绿"),
    ("P-020", "`spectre.measure` 零幅度 AC 点输出 `-Infinity`（非法 JSON）",
     "**已修**：改抛 `ValueError(\"magnitude must be positive for dB scale\")` → `_metric_error` 结构化失败"
     "（commit `d49c892`；`_spectre_util.py:674-681`；`test_spectre_metrics.py` 全绿）"),
    ("P-025", "Windows 多进程共享 work-dir 时 `log/commands.log` 轮转失败（WinError 32）",
     "**已修**：命令日志按进程分片 `log/commands.<pid>.log` 后再轮转，跨进程不再争用句柄"
     "（`common/ssh.py:52-80`；`log_rotation_lock_probe` → PASS (process-local rotation)）"),
    ("P-034", "`calibre.pex` 第三阶段 argv 错误且失败被静默（`-xrc -fmt -spice`）",
     "**已修**：argv 改 `-xrc -fmt <fmt>`；`read_results` 对日志 `stage\\d_failed` 返回结构化失败"
     "（`calibre.py:700`、`:429-490`）"),
    ("P-037", "paramiko 后端把 `ssh -G` 的 `true/false` 当非法值（StrictHostKeyChecking yes 连不上）",
     "**已修**：`true→yes` / `false→no` 归一化，报错回显原始值（`common/paramiko_backend.py:738-751`）"),
    ("P-039", "py2.7 daemon 对 `_read_frame` ValueError 回 NACK（与 py3 分歧）",
     "**撤回**：伪红 —— 真 py2.7 建成后复判分歧不存在（`py27_handler_probe` → `silent drop (correct)`，"
     "`round2-py27-handler-real.json`）；原 bug 报告应同步撤回"),
    ("P-041", "`verilog._read_views` 守卫长度与取值下标不匹配（`>=3` 却读 `[3]`）",
     "**已修**：守卫改 `len(file_entry) >= 4`；离线用例改名 `test_short_view_entry_is_skipped` 并断言 `views == []`"
     "（`verilog.py:273`；`test_verilog_contracts.py` 全绿）"),
    ("P-042", "`layout.gds` 遇版图锁时误报 \"layout view not found\"",
     "**已修**：导出先走 `_view_state_expr` 三态（missing/mismatch/locked），锁冲突单独报 "
     "\"is locked by another session\"（`layout.py:1008-1030`）"),
    ("P-046", "S10 e2e 引导源未固定 → `RBStop()+load()` 会覆盖别人的 CIW（测试侧缺陷）",
     "**已修（测试侧）**：默认不再自动挑实例 —— `test_e2e_live.py` 用 `VB_E2E_BOOTSTRAP_TOKEN/PORT` 固定引导，"
     "未固定且未显式 `VB_E2E_ALLOW_AUTO_DISCOVER=1` 时直接拒绝（`test/live/e2e/test_e2e_live.py:56-63`）"),
    ("P-069", "Calibre LVS 全链跑不通：auCdl 对含 PDK 器件的 cell 导出 CDL 失败 → 无源网表",
     "**测试侧复验通过（第七轮）**：`round7/design-iterate/iterate-lvs.json` —— "
     "`calibre.export_cdl(CMP_LIB/inv2, 680 B)` → `layout.gds` → `calibre.lvs(deck+cdl)` → "
     "`read_results`：**`status=correct`**、ports 4/4、nets 4/4、inst 1/1、`differences=[]`；"
     "S11 全链也拿到确定结论（`cdl` 693 B、lvs rc=0）。等上层销案；"
     "注意 `_calibre.lvs_`（tvf）不是合法 runset，用它当失败证据属用错文件"),
    ("P-026", "maestro 会话匹配用子串（view=maestro 误命中库名 maestro_tb）",
     "**已修（`b36bade`）**：GUI 会话按标题 token 精确匹配 —— `_window_target_fields()` 解析 Editing:/Reading: 后的 `lib cell view` 并逐字段比较（`maestro.py:251-260,494`），不再用 `in` 子串。验证：round7 11 套包 `all_passed=true`（含用 `maestro_tb` 库的 maestro 套件，`round7/live-run-all-http.log`）"),
    ("P-027", "`virtuoso.netlist.import` 假成功（对不存在的库也返回 ok=true）",
     "**已修（`b36bade`）**：参考桩不再伪造成功；该操作已不在运营面（`netlist_import.py` 从生产源码移除、ops 列表无 netlist）。验证：`test/shared/runners/ops_matrix.py` 无 netlist 条目；infra 包 E2E 通过"),
    ("P-029", "`layout.gds` 导出忽略 `file_is_local=False`（产物下到客户端假路径树）",
     "**已修（`b36bade`）**：gds export 支持 `file_is_local=false` 远端落盘且不拍平路径（`layout.py:1043,1175,1192,1244`）。验证（2026-09-28 复跑）：`test_layout_publish_contracts.py` 4/4、`test_layout_contracts.py` 67/67 绿"),
    ("P-030", "`set_term_nets` 默认 `stub_length=0.5` 对 65nm 过大 → 端子接错网且静默",
     "**已修（`b36bade` + `bd75d3d`）**：默认 stub 由引脚几何推导 `(rbHw + 0.05)`，不再固定 0.5；显式值的 SKILL 括号 bug（`(0.5)` 被当函数调用）同批修掉（`schematic.py:540-556`）。验证：`test_schematic_contracts.py` 37/37 绿"),
    ("P-031", "schematic `check_and_save`/`write` 忽略 `schCheck` 失败（check-failed 仍 ok）",
     "**已修（`b36bade` + `bd75d3d`）**：保存前校验 output 含 saved 标记（`schematic.py:785,862`），并在保存路径补 `dbSetConnCurrent`（避免 si -batch OSSHNL-108/109）。验证：`test_schematic_contracts.py` 37/37 绿（无 xfail 残留）"),
    ("P-032", "`verilog._imported_cells` 去重顺序错误（未清洗 token 参与比较）",
     "**已修（`b36bade`）**：先清洗 `[.,;:]` 尾字符再去重（`verilog.py:659-667`）。验证：`test_verilog_contracts.py` 28/28 绿"),
    ("P-074", "pin 坐标口径三处不一致（read `xy` / write `x`,`y` / spec `xy`）",
     "**已修（`48fc800`）**：实现统一为 `pos: [x, y]`，`xy`/拆开的 `x`/`y` 一律拒绝并点名违规字段（`schematic.py:480-487`）；spec《2-schematic》已改「单点一律 pos、弃用 xy」。验证：`schematic_pin_ops_probe` 以 `pos` 形状跑通写路径（`round7/pin-ops.json`，2026-09-28 复跑）"),
    ("C0", "测试规范缺失（六步/状态还原）＋ 原子级覆盖系统性缺口",
     "**已闭环（2026-09-28）**：① 规范落地 `test/docs/写TB规范.md`（六步＋判据强度＋状态还原＋原子级覆盖义务）；"
     "② 机器核账 `audit_atom_coverage.py` → **gap=0 / weak=0 / 待分诊 0**（`atom-coverage-2026-09-28.json`）；"
     "③ B3 修弱判据：serdes calibre 补 `read_results`（DRC 1737 规则/28 结果；LVS 显式记录 not_compared 局限）、"
     "ADC/多用户 SerDes 补 `symbol.read` 端口比对、S11 gds 补 `stat+sha256`（PASS）；"
     "④ B4 抽查报告 `test/reports/TB规范抽查-2026-09-28.md`（5 份，发现 design_iterate 缺 §1 env_check → 已修）"),
    ("P-038", "py3.9 裸装缺 `eval-type-backport` 声明",
     "**已修（`2ab6acf3`）**：`pyproject.toml:14` 运行时依赖含 `eval-type-backport>=0.2; python_version < '3.10'`（wheel METADATA 同）；CI `uv run --python 3.9 --extra dev` 会装运行时依赖 → 3.9 作业不再缺 backport。测试侧复核：依赖行存在；wsl-gent py3.9（pydantic 2.13.5 + backport）import OK"),
    ("P-073", "pin 原子操作与「pin 有效名」不一致（rename 静默无效 / set 改坏 pin 名）",
     "**已修（`3e45442`）**：pin 原子改按「有效名(terminal)」而非 pin 实例名操作。`schematic_pin_ops_probe` 复跑 **clean**（rename 生效、set 只改方向保名、delete OK）。注：验证前必须重启 8127 —— 常驻进程只在启动时导入代码，老进程会回旧行为（Runbook §10）"),
    ("P-075", "`layout.gds` 导出后残留模态框 → 同会话 SKILL 挂死（P1）",
     "**已修**：`layout.gds` 导出收尾自动关 XStream 窗口（`layout.py::_dismiss_xstream_windows`，completion box→Enter / XStream Out→Esc）。`gds_then_skill_probe` 复跑 **clean**（GDS 后 SKILL **0.3s** 返回，此前 30s 超时）；ADC 全链回到 **24/24**（`round8/adc-sar.json`）"),
    ("P-077", "注册探测拒绝裸 python 名（`test -x python3`）",
     "**已修（`3886cb4`）**：显式 python/bin 接受 PATH 命令名（`command -v` 解析 + 真实文件/可执行校验），与运行时 `/usr/bin/env <value>` 一致；新增离线用例 3/3。端到端回归：P3 跨主机注册（裸 `python3`）**28/28**、P4 真 CIW **12/12**"),
    ("P-076", "`spectre.run` 间歇永不返回（in_flight 不释放，需重启业务面）",
     "**已修（`f769750` + `3f2fbcc`；看门狗方案 `cd818e7` 已 revert）**：中层递归 tar 下载的完成判定"
     "只依赖 channel+tar、pump 线程可协作取消（修前：数据已在 `.vbtmp-*` 却未安装，pump 线程永久残留）。"
     "复验（2026-09-28 晚，8127 重启后）：① `p076_fix_verify_probe.py` direct **3/3**"
     "（raw 安装到位 + spectre.out 在 + 无 .vbtmp 残留 + thread_delta=0）；"
     "② HTTP 面 `repro_p076_rounds.py` **6/6**（每轮 2 任务 success，~7s）；"
     "③ 验收③：`design_iterate_tb --stage all` **连跑 3 次 ok=True failures=[]**（65/64/63s）；"
     "④ 影响面回归：11 套包 `run_all_http.py` **all_passed=true**（含 spectre/maestro/calibre）"),
]

#: 非缺陷跟踪项（文档/环境/审计/覆盖度）：不建卡，只在 README 索引，避免与缺陷视图混淆
LEGACY_OPEN = [
    ("P-001", "覆盖度报告 `doc/测试覆盖报告.md` 与当前 `src/` 布局脱节（缺负责人）", "待定负责人"),
    ("P-003", "环境占用（跑测前检查清单已写）", "待固化到脚本"),
    ("P-004", "`.pytest_cache` 里 14 条 lastfailed 指向已不存在的旧路径（缓存噪声）", "已记录（建议定期清缓存）"),
    ("P-005", "瞬态红灯（观察中）", "观察"),
    ("P-006", "文件纪律审计（Q1 全链路 / Q2 逐 role / Q3 逐 TB 三项未覆盖）", "待补（审计项，非缺陷）"),
    ("P-010", "文档一致性（§7 需改「已确认发生、待清理」）", "待改文档"),
    ("P-011", "`/tmp` 口径待定稿（设计内例外 vs 泄露）", "待定稿"),
    ("P-014", "现场观察（找不到创建者）", "待代码定位"),
    ("P-016", "完成度评估 / 补测归口（非缺陷）", "待处理"),
    ("P-017", "归属未定（先定创建者）", "待确认"),
    ("P-021", "历史实例启动位置不规范（`$HOME`/工程目录污染；规范已落地，现场清理与 legacy 重写待办）", "环境账，非缺陷"),
    ("P-023", "wsl-gent 起 20 个真 Virtuoso 超出内存（真机上限 10–12；口径已写环境文档）", "待用户确认替代口径"),
    ("P-028", "运行中的 vblog CIW 没有 PDK（已按 S1 专用实例口径处置）", "环境账，已给口径"),
    ("P-033", "`test/artifacts` 231 个文件被跟踪（含 token/二进制；白名单保留需用户确认）", "仓库卫生，待确认"),
    ("P-036", "lab fake 与 bridge 隧道兼容性（已复测可达，症状未复现）", "观察（降级，不再阻塞）"),
    ("P-040", "仓库内 `.ps1` 一律 UTF-8 with BOM（约定，已写入首轮报告 §6.1）", "约定，非缺陷"),
]

CARD_BODY = """# {id} · {title}

| 字段 | 值 |
|---|---|
| 级别 | {level} |
| 层 | {layer} |
| 归属 | {owner} |
| 状态 | **{status}** |
| 位置 | {where} |
| 首报 | {reported} |
| 最近更新 | {updated} |

## 现象

{symptom}

## 复现

```text
{repro}
```

## 证据

{evidence}

## 验收判据（修好即转绿）

{accept}

## 下一步 / 责任人

{next}

{extra}
---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
"""


def _slug(bug: dict) -> str:
    """卡片文件名用**显式短 slug**（ASCII，便于命令里敲/给设计侧贴）。"""
    return bug.get("slug") or bug["id"].lower()


def render_readme() -> str:
    rows = ["| ID | 层 | 级别 | 归属 | 状态 | 一句话 | 卡片 |",
            "|---|---|---|---|---|---|---|"]
    for bug in OPEN:
        rows.append(f"| **{bug['id']}** | {bug.get('layer', '—')} | {bug['level']} | {bug['owner']} | {bug['status']} | "
                    f"{bug['title'].replace('|', chr(92) + '|')} | "
                    f"[{bug['id']}-{_slug(bug)}.md]({bug['id']}-{_slug(bug)}.md) |")
    closed = "\n".join(f"| {i} | {t} | {e} |" for i, t, e in CLOSED_RECENT)
    legacy = "\n".join(f"| {i} | {t} | {s} |" for i, t, s in LEGACY_OPEN)
    return f"""# `test/reports/bugs/` —— 未关闭缺陷的唯一跟踪视图

> 维护者：测试工程师（我）｜最近刷新：2026-09-29
> **这个目录回答一个问题：现在还有哪些 bug 没关、谁在等谁、修好的判据是什么。**

## 0. 三条规矩（动这里之前先看）

1. **权威事实在台账**：[问题登记.md](../问题登记.md)。本目录不重复分析，只做「未关闭项」的卡片与索引；
   送修视图（逐条 file:line / 复现 / 验收）在 [round7-缺陷清单-上层.md](../round7-缺陷清单-上层.md) 与
   [round7-缺陷清单-其他.md](../round7-缺陷清单-其他.md)。
2. **状态只能从这五个里选**：`待设计修` / `待测试侧` / `待归属` / `待决策` / `观察`。
   关闭时**不删卡片**：移到 [已关闭-近期.md](已关闭-近期.md) 并写一句「凭什么关的」（证据路径）。
3. **刷新方式**：改 `test/shared/runners/make_bug_cards.py` 的 `OPEN` / `CLOSED_RECENT` 段，
   然后 `python test/shared/runners/make_bug_cards.py`（幂等；`--check` 只校验不写盘）。

## 1. 未关闭（{len(OPEN)} 条）

{chr(10).join(rows)}

> 优先级口径：**P1** = Linux 侧资源/安全或核心指标链路断（P-056、P-053）；
> **P2** = 真实设计流会给出错的/空的结果，且多数**静默**；**P3/观察** = 非阻塞但建议顺手修。

## 2. 本轮/近期已关闭（{len(CLOSED_RECENT)} 条，保留记录）

| ID | 事项 | 关闭依据（证据） |
|---|---|---|
{closed}

详见 [已关闭-近期.md](已关闭-近期.md)。

## 3. 非缺陷跟踪项（{len(LEGACY_OPEN)} 项，不建卡）

文档 / 环境 / 审计 / 覆盖度类条目：**不是产品缺陷**，只在台账与这里索引（避免与缺陷卡片混淆）。
所有**缺陷**（含早期轮次已上报的 `bug-2026…`）都在上面 §1 的卡片里，或已移入 §2 已关闭记录。

| ID | 事项 | 当前状态 |
|---|---|---|
{legacy}

## 4. 关联文件

- 台账（唯一事实源）：[问题登记.md](../问题登记.md)
- 最新一轮送修：[上层](../round7-缺陷清单-上层.md)、[其他](../round7-缺陷清单-其他.md)
- Spec 覆盖矩阵（哪些要求被测到）：[round7-spec覆盖矩阵.md](../round7-spec覆盖矩阵.md)
- 覆盖率与缺口：[coverage-pack/](../coverage-pack/)、[覆盖度缺口.md](../覆盖度缺口.md)
- 覆盖率补强要求（**给设计侧的清单**）：[覆盖率补强要求-给设计侧.md](../覆盖率补强要求-给设计侧.md)
- 两个完整项目的验收清单：[两项目全链-验收清单.md](../两项目全链-验收清单.md)
- 新增卡片模板：[_模板.md](_模板.md)
"""


def render_closed() -> str:
    lines = ["# 已关闭（近期）", "",
             "> 关闭 = 有复跑证据，不是「设计说改好了」。每条都要能点开证据。", "",
             "| ID | 事项 | 关闭依据（证据） |", "|---|---|---|"]
    lines += [f"| {i} | {t} | {e} |" for i, t, e in CLOSED_RECENT]
    lines += ["", "## 早期轮次已关闭 / 撤回（摘要）", "",
              "| ID | 结论 |", "|---|---|",
              "| P-002 | 已关闭：`AGENTS.md` 属重构前残留，不在测试范围 |",
              "| P-008 | 已关闭：带 `bak` 的目录属重构前代码，不关注 |",
              "| P-009 | 已闭环：目录规范 + 各层 README 落地 |",
              "| P-012 | 已闭环：改系统 temp + `vb-` 前缀 |",
              "| P-015 | 已闭环：同名双实现收敛（`24333c0`），本轮复核 |",
              "| P-018 | 已闭环：121 处加 `prefix=\"vb-\"`（后被 P-064 进一步加固） |",
              "| P-022 / P-024 | 已闭环：env_up 保活 / 能力验证 |",
              "| P-035 | 已闭环（测试侧）：前后仿 netlist 统一 soft_bin |",
              "| P-040 | 已闭环：`.ps1` 一律 UTF-8 with BOM |",
              ""]
    return "\n".join(lines)


def build_plan() -> dict[Path, str]:
    template = CARD_BODY.format(
        id="P-0XX", title="<一句话缺陷标题>", level="P1 / P2 / P3",
        owner="设计侧 / 测试侧 / 待归属", status="待设计修 / 待测试侧 / 待归属 / 待决策 / 观察",
        where="`src/...:line`（根因锚点）", symptom="现象（含实测数字与「静默/报错」判定）",
        repro="最小复现命令（可粘贴执行）", evidence="证据路径（JSON / 日志 / 探针）",
        accept="修好后哪条用例或探针转绿", next="谁做什么，含复验方式",
        reported="<YYYY-MM-DD>（已报 `bug-…`）", updated="<YYYY-MM-DD>",
        layer="上层 / 其他 / 测试侧",
        extra="## 补充（可选；需要时由 `extra` 字段注入）\n")
    plan = {BUGS_DIR / "README.md": render_readme(),
            BUGS_DIR / "_模板.md": template,
            BUGS_DIR / "已关闭-近期.md": render_closed()}
    for bug in OPEN:
        # `extra` 是给"卡片上后来追加的讨论/决策"留的位置（默认空）——见 CARD_BODY 末尾的警告。
        plan[BUGS_DIR / f"{bug['id']}-{_slug(bug)}.md"] = CARD_BODY.format(
            **{**bug, "extra": bug.get("extra", ""),
               "reported": bug.get("reported", "第五轮（2026-09-23）／见台账"),
               "updated": bug.get("updated", "2026-09-24（测试侧整理 bug 卡）"),
               "layer": bug.get("layer", "—")})
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="只校验（不写文件）")
    args = parser.parse_args(argv)
    plan = build_plan()
    # 已关闭/改判的卡片：计划里不再有 → 目录里不该留（否则索引说"已关闭"、目录里还挂着一张
    # "待修"卡片，两边打架）。正常模式直接清掉并打印；--check 模式只报告。
    # 注意：不只 `P-0*`——评审/审计可能会新立 `C*`（规范类）等编号的卡片，
    # 它们同样必须受"计划内 or 清理"的约束，否则会出现"卡片在目录里、索引里没有"。
    _reserved = {"README.md", "_模板.md", "已关闭-近期.md"}
    orphans = sorted(p for p in BUGS_DIR.glob("*.md")
                     if p.name not in _reserved and p not in plan)

    if args.check:
        missing = [str(p.relative_to(ROOT)) for p in plan if not p.is_file()]
        stale = [str(p.relative_to(ROOT)) for p, text in plan.items()
                 if p.is_file() and p.read_text(encoding="utf-8") != text]
        # 2026-09-30（用户裁定）：**卡片允许手改**，因此"与生成文本不一致"只作信息提示，
        # 不再算失败；只有"计划里的卡缺失"和"目录里有计划外的卡"才是硬错误。
        print(f"计划文件 {len(plan)} 个；缺失 {len(missing)}；手改/过期（信息）{len(stale)}；"
              f"应清理的旧卡片 {len(orphans)}")
        for item in missing + [str(p.relative_to(ROOT)) for p in orphans]:
            print("  -", item)
        if stale:
            print(f"  （信息）以下卡片与生成文本不同：{', '.join(stale)}")
        return 1 if (missing or orphans) else 0

    BUGS_DIR.mkdir(parents=True, exist_ok=True)
    for path, text in plan.items():
        path.write_text(text, encoding="utf-8")
    for stale in orphans:
        stale.unlink()
    print(f"已刷新 {BUGS_DIR.relative_to(ROOT)}：{len(plan)} 个文件（未关闭 {len(OPEN)} 条）"
          + (f"；清理旧卡片 {len(orphans)} 张" if orphans else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
