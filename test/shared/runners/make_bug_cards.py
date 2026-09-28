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
* `LEGACY_OPEN`：早期轮次仍未关闭的（多数已上报外部 bug 系统，这里只做索引与状态）。
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BUGS_DIR = ROOT / "test" / "reports" / "bugs"

#: 未关闭条目。状态只允许：待设计修 / 待测试侧 / 待归属 / 待决策 / 观察
OPEN = [
    {
        "id": "P-076",
        "slug": "spectre-run-request-never-returns",
        "title": "间歇：`spectre.run` 请求永不返回（spectre 已 0 error 跑完；服务端线程不释放，需重启业务面）",
        "level": "P2（间歇性挂起；占住 in_flight 线程，客户端只能杀进程）",
        "owner": "设计侧（上层 spectre 包的 run 路径：等待完成/递归下载）",
        "status": "观察（1 次复现，待设计侧定位）",
        "where": "`src/pyapi/packages/spectre.py` `run` → `_run_one`（execute → `download_file(recursive=True)` → 解析）；中间层 `run_spectre_command` / 持久 shell 路径",
        "symptom": "2026-09-28 12:59 `design_iterate_tb` 的 `r2_sim` 阶段（calprobe token，2 任务 / `max_workers=2`）"
                   "卡住 **>25 分钟**：spectre 本身在 12:59:02 就跑完了（两个 run 目录的 `spectre.out` 都是 "
                   "`spectre completes with 0 errors`，`r2_ac.raw/ac.ac`、`r2_tran.raw/tran1.tran.tran` 都在），"
                   "但 HTTP 请求不返回、`/health` 显示 **in_flight=1** 一直不降；客户端把 TB 进程杀掉后，"
                   "服务端线程仍不释放（只能重启 8127 才能清掉）。两侧都没有 ssh/scp/tar 进程 → 阻塞在中间层 Python 路径。\n"
                   "**注意（避免误判）**：同一业务面其它 token 的请求不受影响（卡住期间 vblog/calprobe 的 "
                   "`1+2` 与新的 `spectre.run` 都正常）。",
        "repro": "发生样本（保留现场）：`test/artifacts/evidence/round7/design-iterate/`（r1 各段 12:58 完成，"
                 "r2_edit/r2_sym/r2_layout 12:58:44–53 完成，r2_sim 无产物）；远端 run 目录 "
                 "`/home/Gent/.virtuoso-bridge/calprobe/spectre/spectre/buf_stage_125804_r2_{ac,tran}`（均已 0 error）。\n"
                 "**未能最小复现**（已试，均正常返回）："
                 "① vblog 连续两次单任务 `spectre.run`（6.5s/6.0s）；② vblog 连续两次双击（各 2 任务，"
                 "6.4s/6.7s）；③ 事后 calprobe 单任务 `spectre.run`（6.1s）。复现脚本："
                 "`test/artifacts/tmp/repro_spectre_second_run.py`、`test/artifacts/tmp/repro_spectre_two_tasks_twice.py`。",
        "evidence": "卡住时 `/health → in_flight=1`；`spectre.out` 完成时间 12:59:02；客户端 TB 进程被杀后 in_flight 仍为 1；"
                    "双侧 `ps` 无 ssh/scp/tar。",
        "accept": "① 给出该路径的硬超时（等待完成 / 递归下载都必须有 deadline，超时返回结构化错误而不是永久阻塞）；"
                  "② 复现样本能定位到具体阻塞点（建议设计侧在 `_run_one` 的 execute/download/parse 三段加耗时日志，"
                  "或用 py-spy 抓卡住线程栈）；③ 修好后连跑 3 次 `design_iterate_tb --stage all` 不再挂。",
        "next": "设计侧定位（样本在 12:59 那次；如需现场可让测试侧重跑并按 py-spy 抓栈）；"
                "测试侧暂按'间歇挂起'记录，先跑其余 TB。",
    },
    {
        "id": "P-075",
        "slug": "gds-export-modal-blocks-session",
        "title": "`virtuoso.layout.gds` 导出后会话残留模态对话框（\"Stream out translation complete\"）→ 同会话 SKILL 通道挂死，必须重启实例",
        "level": "P1（会话被挂死；多用户/GDS 后继续操作的流程直接卡住）",
        "owner": "设计侧（上层 layout.gds / strmout 调用路径）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/layout.py` 的 `virtuoso.layout.gds`（strmout/XStream 调用）＋ `src/pyapi/packages/gui.py` 的 `auto_dismiss`（现有规避手段对它无效）",
        "symptom": "在**同一会话**里执行 `virtuoso.layout.gds`（导出 GDS 到新目录，XStream/strmout）之后，"
                   "**该会话若出现模态** `\"Stream out translation complete\"` 窗口（XStream 完成框），"
                   "该会话的 SKILL 通道被一个**模态对话框**阻塞：窗口列表可见 "
                   "`\"Stream out translation complete\"`（class `virtuoso`）＋ `\"XStream Out\"`；"
                   "此后该 token 的任何 `basic.skill.execute` / 依赖 SKILL 的操作都 30s 超时"
                   "（`SKILL execution timed out`）。实测：`virtuoso.gui.auto_dismiss` 返回 ok 但 "
                   "`dismissed=null`（关不掉这个窗口），**只能重启该实例**才能恢复。\n"
                   "受害场景（已复现 3 次）：多用户协同里 A 出完 GDS、B 改同一 cell 的 schematic 后，"
                   "A 的回读超时；单会话流程里\"出 GDS 后继续写原理图\"同样中招。\n"
                   "**观察到的差异（待设计侧定位触发条件）**：同一台机器上 `vblog` / `calprobe` 会话"
                   "导出 GDS 后只有**非模态**的 `\"XStream Out\"` 主窗体、SKILL 仍可用；"
                   "`vbuser1`（Xvfb `:105`，headless）稳定留下**模态完成框**并挂死 —— "
                   "可能与 XStream 表单/焦点/headless 显示或 strmout 参数有关。",
        "repro": "① **最小复现（单会话，无第二用户）**：\n"
                 "`PYTHONPATH=src python test/semi/probes/gds_then_skill_probe.py --token vb-vbuser1 "
                 "--file-root /home/vbuser1/.virtuoso-bridge/vbuser1/file --skill-timeout 45`\n"
                 "→ lib/view/write/read-back/gds-export 全 OK，最后一步 "
                 "`skill-after-gds` FAIL：`elapsed_s=30.0, SKILL execution timed out`（证据 JSON 见下）。\n"
                 "② 二分复现脚本（含多用户版本，定位到 --gds 是触发项）：\n"
                 "`PYTHONPATH=src python test/artifacts/tmp/bisect_cross_user_block.py --cell blk_gds_x "
                 "--symbol --layout --gds`\n"
                 "→ 观察最后一步：`A: read after B write (30.0s) ok=False err=SKILL execution timed out`；"
                 "去掉 `--gds` 的对照组（`--symbol --layout`）通过（0.3s）。\n"
                 "③ 端到端：`PYTHONPATH=src python test/live/flows/adc_sar_flow_tb.py --work-dir "
                 "test/artifacts/env/log-vblog --token-a vb-vbuser1 --token-b vb-vbuser2` → 21/22，"
                 "失败步 `A-see:B's instance`（read_error=SKILL execution timed out）。\n"
                 "④ 窗口取证：`xwininfo -display <A 的 DISPLAY> -root -tree | grep -E 'Stream|XStream'`。",
        "evidence": "`test/artifacts/evidence/round7/gds-then-skill.json`（单会话最小复现：RED）；"
                    "`test/artifacts/evidence/round7/adc-sar-pos2.json`（21/22，失败步带原始 read_error）；"
                    "窗口列表（A 会话）：`0x4001e9 \"Stream out translation complete\"`、"
                    "`0x4001e6 \"XStream Out\"`（test/artifacts/tmp/check_wedge_after_gds.sh 的输出）；"
                    "对照组 E1/E2（symbol / symbol+layout）全绿、E3（+gds）复现。",
        "accept": "① `virtuoso.layout.gds` 返回后，**同会话**的下一次 SKILL 调用在正常时限内成功（无需重启）——"
                  "最小复现即 `gds_then_skill_probe` 转绿；"
                  "② 或由产品在导出结束时关闭自己的 XStream 模态窗口，并让 `gui.auto_dismiss` 能识别/关闭它；"
                  "③ 回归门：新增探针 `test/semi/probes/gds_then_skill_probe.py` 转绿 + ADC TB 回到 22/22。",
        "next": "设计侧定位 strmout 调用（是否用了会弹完成框的 XStream UI 路径；建议改批处理/导出后显式关窗）。"
                "测试侧：新探针先钉住红灯（已加），修好后跑「探针 + ADC TB + 一次多用户 GDS→改单」三轮复验。",
    },
    {
        "id": "C0",
        # 保持独立审计原文件名（用户/评审引用的就是这条路径），不要改成 ASCII slug
        "slug": "测试规范-AAA与状态还原缺失",
        "title": "测试规范缺失：无显式 TB 流程约定（环境检查→构建→完备校验→执行→比对），"
                 "delete/rename/set 类原子在 semi/live 层系统性无覆盖",
        "level": "P2（测试规范缺陷；导致覆盖系统性缺口 + 缺陷漏检）",
        "owner": "测试侧（规范制定 + 覆盖补齐）",
        "status": "规范已落地（2026-09-28）；覆盖补齐进行中（B1–B4）",
        "where": "`test/docs/写TB规范.md`（六步流程与状态还原，2026-09-28 精简合并后的唯一规范入口）"
                 " + 三层测试的写原子覆盖；核账脚本 `test/shared/runners/audit_atom_coverage.py`",
        "symptom": "独立审计（2026-09-27）发现 delete/rename/set 类写原子在**半真机与真机两层无覆盖**，"
                   "其离线证据只是「拼出合法 SKILL 文本」的契约断言（FakeMiddle mock），从不执行、无结果比对。"
                   "测试侧 2026-09-28 核账（60 个原子，schematic/layout/symbol）：**semi/live 两层零引用 12 个**——"
                   "schematic 的 `delete_instance/delete_note/delete_wire/place_note/place_wire/rename_note/"
                   "set_note_properties/set_wire_properties`、layout 的 `delete_instance/delete_mosaic/"
                   "`fit_view/zoom`；另有 20+ 原子 **semi 层**单缺。\n"
                   "根因：`test/reports/internal/测试架构-内部.md §3` 的覆盖度模型是**能力域级**（「某包测没测」），"
                   "粒度不足以发现包内原子缺口；且此前**没有** TB 执行流程与状态还原约定，"
                   "delete/rename/set 类原子需要「先造既有对象」，成本高被系统性绕开。",
        "repro": "`python test/shared/runners/audit_atom_coverage.py --md`（打印 60 原子 × 三层引用面 + GAP 列表）；"
                 "证据 `test/artifacts/evidence/atom-coverage-2026-09-28.json`；"
                 "离线文本断言的典型形态见 `test/offline/unit/test_schematic_contracts.py:209-257`",
        "evidence": "`test/reports/原子覆盖审查-2026-09-28.md`（逐条复核 C0 的清单与「只发不核」意见）；"
                    "`test/docs/写TB规范.md`（六步流程 + 状态还原 + 最小判定强度）；"
                    "`test/artifacts/evidence/atom-coverage-2026-09-28.json` / `.txt`",
        "accept": "① 六步 TB 流程与状态还原规则落地为规范（**已满足**，见 `test/docs/写TB规范.md`）；"
                  "② 12 个两层缺口原子按六步补齐 semi 探针或 live e2e（place→read→delete→read 消失 / "
                  "rename→read 改名 / set→read 属性变化），`audit_atom_coverage.py` 的 gap 列表逐步清零；"
                  "③ 2 处弱判据（SerDes 的 calibre lvs/drc 只看 ok）改为读 `calibre.read_results` 结论",
        "next": "测试侧：B1（schematic 8 原子）→ B2（layout 4 原子，display 原子用窗口/截图判据）→ "
                "B3（弱判据修正）→ B4（按规范 §7 清单抽查 5 份现役 TB）。"
                "每批完成即重跑核账脚本更新本卡状态；关闭判据是 gap=0 且 weak=0",
        "extra": (
            "## 独立审计原文（2026-09-27，逐字保留）\n"
            "\n"
            "> 来源：独立审计卡片 `C0-测试规范-AAA与状态还原缺失.md`。测试侧 2026-09-28 把它并入生成器"
            "（`make_bug_cards.py`）以防刷新丢失；上面「现象/根因/验收」是测试侧的**核账后**版本，"
            "本节保留审计原文以便对照。\n"
            "\n"
            "### 现象\n"
            "\n"
            "独立审计（2026-09-27）发现：**12 个写原子在半真机（semi）和真机（live）两层均无任何测试覆盖**，"
            "且**全部集中在 delete/rename/set（删除/改属性）类**：\n"
            "\n"
            "- schematic（10）：`delete_instance`、`rename_instance`、`place_wire`、`delete_wire`、"
            "`set_wire_properties`、`set_label_properties`、`place_note`、`delete_note`、`rename_note`、"
            "`set_note_properties`\n"
            "- layout（6）：`delete_label`、`set_label_properties`、`delete_instance`、`delete_mosaic`、"
            "`fit_view`、`zoom`\n"
            "\n"
            "这些原子在**离线层只有「拼出合法 SKILL 文本」的契约断言**（FakeMiddle mock），从不经真机执行、无结果比对。\n"
            "\n"
            "### 根因（测试规范缺陷）\n"
            "\n"
            "测试没有一条显式的 TB 流程规范（环境检查 → 构建 → 完备校验 → 执行 → 比对）与**前置构建干净基线**的约定，导致：\n"
            "\n"
            "1. place（新建）类 Arrange = 空画布，几乎免费，被充分测试；\n"
            "2. delete/rename/set 类 Arrange = 需先 seed 一个已知对象（本身依赖 place 或 fixture 注入），成本高，被系统性绕开；\n"
            "3. cellview 是**持久化**对象（非无状态函数），无「前置构建/还原干净基线」约定 → 跨用例污染风险，"
            "进一步劝退写 delete/set 类测试。\n"
            "\n"
            "### 关联缺陷（由本规范缺陷直接/间接导致）\n"
            "\n"
            "- **P-073**（rename_pin 静默无效）：rename 类长期无真机闭环，拖到真机探针才暴露；\n"
            "- **P-074**（spec/实现 pin 索引口径不一致）：定位参数语义无真机验证的同类症状；\n"
            "- **P-072**（init_work_dir 一次性化）、**P-068**（两用户工艺绑定不一致）：同为「状态管理无规范」的症状。\n"
            "\n"
            "### TB 规范流程（6 步，已定 —— 已落入 `test/docs/写TB规范.md` §1）\n"
            "\n"
            "每份 TB 按如下顺序执行，**完成后不清理现场**；现场干净由第 2、3 步（前置构建）负责：\n"
            "\n"
            "1. **检查环境是否为所需测试环境**：不是所需环境 → TB 直接失败（所需环境通常为日常；写 TB 尽量用日常，"
            "非日常需求写好 TB 后移交测试工程师）。\n"
            "2. **检查当前环境并构建测试环境**：要读原理图就准备一张要读的原理图；要写原理图就准备一张**要被写的原理图**"
            "（并还原到未写基线）。\n"
            "3. **最终检查环境**：确认被测动作所需环境已完备（该有的对象/视图/前置状态都在、且干净）。\n"
            "4. **执行操作**。\n"
            "5. **比对结果并记录**（理想 vs 实际）。\n"
            "6. **重复 4、5**，直到本 TB 完结。\n"
            "\n"
            "### 审计给出的验收判据\n"
            "\n"
            "1. 上述 6 步 TB 流程落地为测试规范文档；\n"
            "2. 上述 12 个双缺失原子按 6 步流程补上 semi 探针或 live e2e"
            "（「place→read→delete→read 确认消失 / rename→read 确认改名」闭环）。\n"
        ),
    },
    {
        "id": "P-073",
        "slug": "pin-atomic-ops-name-mismatch",
        "title": "原理图 pin 原子操作与「pin 有效名」不一致：rename_pin 静默无效、set_pin_properties 把 pin 名改成自动名",
        "level": "P2（写操作语义错误；set_pin_properties 静默改坏用户数据）",
        "owner": "设计侧（上层 schematic 包 `_atomic_skill`）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/schematic.py:615-637`（`delete_pin`/`rename_pin`/`set_pin_properties` "
                 "按 **pin 实例** 匹配并把实例名当 pin 名）、`:601-614`（`place_pin`）；"
                 "spec `2-schematic.md:59` 表格",
        "symptom": "真机实测（`DI65` 与 `PINOP` 两个 cell，两种环境）：\n"
                   "① `rename_pin` 返回 `status=success, output=\"新名\"`、`check_and_save` 返回 `saved`，"
                   "但 `virtuoso.schematic.read` 的 pin 列表**仍是旧名**、`symbol.generate` 二次出图的端口名"
                   "**也仍是旧名**（下游网表看到的端口没变）；直接读 DB 才看到只有 **pin 实例名**被改了"
                   "（`(\"PIN0\" \"ipin\")` → `(\"a2\" \"ipin\")`）——即对用户是**静默无操作**。\n"
                   "② `set_pin_properties`（改 direction）写成功，但 pin **名字被换成自动名**："
                   "`y` → `PIN1`，symbol 端口也跟着变成 `PIN1` —— 用户只改方向，端口名被改坏。\n"
                   "③ `delete_pin` 行为正确（pin 从 read 列表消失）。",
        "repro": "`python test/semi/probes/schematic_pin_ops_probe.py --token <PDK_TOKEN>`"
                 "（token 从 `test/artifacts/env/log-vblog/registry.json` 的 calprobe 条目取；报告里不写明文）"
                 "（四个角度：write 自报 / schematic.read / symbol 端口 / DB 里 pin 实例名）；"
                 "迭代链侧复现：`python test/live/flows/design_iterate_tb.py --stage all`"
                 "（`r2_edit` 的 `pin-renamed`、`r2_sym` 的 `symbol-terms-round2` 两条断言）",
        "evidence": "`test/artifacts/evidence/round7/pin-ops.json`（三轮步骤逐条留证）、"
                    "`test/artifacts/evidence/round7/design-iterate/iterate-r2_edit.json`、"
                    "`.../iterate-r2_sym.json`、`test/artifacts/evidence/round7/design_iterate_run.log`",
        "accept": "三个原子在真实 cell 上语义正确：`rename_pin` 后 read 与 symbol 端口名都变；"
                  "`set_pin_properties` 只改方向、pin 名保持不变；`delete_pin` 后端口消失；"
                  "并补离线用例钉住（断言必须落在「下游可见的 pin 名」，不是实例名）",
        "next": "设计侧：pin 的**有效名**在标签/端口对象上，`rename_pin` 要改的是它（或同步改实例名+标签），"
                "`set_pin_properties` 不能用实例名去重建 pin。测试侧：修好后重跑 `design_iterate_tb` 与"
                "`schematic_pin_ops_probe`（本轮这两处是**已登记的预期红**）",
    },
    {
        "id": "P-074",
        "slug": "pin-index-xy-doc-mismatch",
        "title": "spec 表格把 pin 的索引写成 `xy`，实现要 `x`/`y`（delete/rename/set_pin_properties）",
        "level": "P3（文档口径不一致，会绊住所有写 TB 的人）",
        "owner": "设计侧（spec 或实现，二选一改齐）",
        "status": "待归属",
        "where": "`spec/design-concepts/上层/2-schematic.md:59`（`delete_pin | xy` / `rename_pin | xy` / "
                 "`set_pin_properties | xy`）vs `src/pyapi/packages/schematic.py:615-616`"
                 "（`float(cmd[\"x\"])` / `float(cmd[\"y\"])`）",
        "symptom": "按 spec 表格写 `{\"op\":\"rename_pin\",\"xy\":[6.0,0.0],\"new_name\":\"vout_main\"}` → "
                   "`virtuoso.schematic.write` 直接失败：`command 5 invalid: 'x'`（KeyError('x')）。"
                   "只有 label/note/wire 一族用 `xy`，pin 用 `x`/`y` —— 表格与实现相反，"
                   "使用者照表格写必然踩坑（本轮就踩到，见 R7-TB 修正记录）。",
        "repro": "把 `test/live/flows/design_iterate_tb.py` 的 `R2_RENAME` 改回 `xy` 形状即复现；"
                 "或任何 `{\"op\":\"delete_pin\",\"xy\":[...]}` 的 write",
        "evidence": "`test/artifacts/evidence/round7/design-iterate/iterate-r2_edit.json`（早期失败版本的错误串）、"
                    "`test/reports/round7-TB修正.md`（R7-TB-03）",
        "accept": "spec 表格与实现同口径（建议实现同时接受 `xy` 与 `x`/`y`，或 spec 明确写 pin 用 `x`/`y`），"
                  "且校验失败信息能指出「缺 x/y」而不是裸露 KeyError",
        "next": "设计侧定口径；测试侧已按实现口径写 TB（并在 TB 注释里标注）",
        # 09-25 设计侧/评审在卡片上追加的讨论被 09-28 的一次刷新误删，这里回填进数据源，
        # 以后刷新不会再丢（见 CARD_BODY 末尾的生成物警告）。
        "extra": (
            "## 讨论决策（2026-09-25，补充）\n"
            "\n"
            "**定性升级**：本条不是「文档抄错字段名」，而是**坐标表示口径没统一**——三个口径在打架：\n"
            "\n"
            "| 场景 | 坐标表示 |\n"
            "|---|---|\n"
            "| `read` 返回 | `xy: [x, y]`（整体数组） |\n"
            "| `write` 输入（实现） | `x`、`y`（拆开两个字段） |\n"
            "| spec 内部 | place 用 `x,y`，delete/rename/set 索引用 `xy`（自相矛盾） |\n"
            "\n"
            "**核心共识**：坐标本质是一个点，不该拆开写。`read` 已证明正确形态是「一个字段承载 `[x, y]`」；"
            "`write` 把坐标拆成 `x`/`y` 才是别扭、且与 read 不对称的根源。\n"
            "\n"
            "**命名**：弃 `xy`，改 `pos`（或 `position`）。`xy` 字面像「两个分量」、又与 `x`/`y` 视觉太近，"
            "是这类坑的诱因；`pos` 简洁、与 `op` 风格一致、坐标语境无歧义。\n"
            "\n"
            "**落地建议（给设计侧拍板）**：\n"
            "\n"
            "- 统一为 `pos: [x, y]`（两元素数组），read 与 write 同一口径，**不保留兼容**，彻底消灭 `x`/`y` 拆开写法；\n"
            "- 验收：照 spec 写 `{\"op\":\"rename_pin\",\"pos\":[6.0,0.0]}` 能跑通，且校验失败信息指名缺哪个字段"
            "（不再裸报 `KeyError('x')`）。\n"
        ),
    },
    {
        "id": "P-070",
        "slug": "monte-carlo-missing",
        "title": "蒙特卡洛能力缺失：只能读回 MC 结果，不能驱动 MC 仿真",
        "level": "P2（能力缺失）",
        "owner": "待决策（产品口径：支持驱动 MC or 明确不做）→ 设计侧实现/写 spec",
        "status": "待决策",
        "where": "`src/pyapi/packages/_maestro_util.py:141`（唯一 MC 相关代码）、`:291-313`（`parse_overall_yield`）；"
                 "spec：`6-maestro.md:130`（唯一 MC 提及，锁语义）、`7-spectre.md`（分析枚举无 montecarlo）",
        "symptom": "全 `src/` 搜 `monte|carlo`（忽略大小写）**只命中 1 行**（历史目录正则）；"
                   "**没有任何配置/启动 MC 分析的代码**，spectre 分析枚举也只有 `tran/dc/ac/info/noise`。"
                   "现状 = 只能读回别人跑完的结果（yield/mean/sigma + `MonteCarlo.N` 目录识别），"
                   "**不能驱动蒙特卡洛仿真**。用户 2026-09-24 判定：能力缺失要提 bug。",
        "repro": "`rg -n -i \"monte|carlo\" src/`（只 1 行）；`rg -n -i monte spec/`（只 1 处，锁语义）；"
                 "离线只有解析用例：`pytest test/offline/unit/test_maestro_util.py -q`",
        "evidence": "代码锚点见上；测试证据：`test_maestro_util.py::test_overall_yield`、"
                    "`test_natural_sort_histories`（离线）；真机 MC **从未跑过**（无证据）",
        "accept": "二选一：① 支持驱动 —— 能配置 montecarlo 分析并启动，跑完读回 yield/mean/sigma 且与 ADE GUI 对数一致"
                  "（真机一次）；② 不支持 —— spec 明确写「只读 MC 结果、不驱动」并标为明确不做",
        "next": "设计侧先定口径；定了之后测试侧补真机 MC 验证（或补不覆盖声明），并把「两项目全链」里的 MC/PVT 一栏按口径收口",
    },
    {
        "id": "P-069",
        "slug": "lvs-cdl-chain",
        "title": "Calibre LVS 全链跑不通：auCdl 对 PDK 器件导出 CDL 失败 → 无源网表",
        "level": "P2（业务包功能不可用）",
        "owner": "设计侧",
        "status": "观察（第七轮复验 **correct**，等上层销案）",
        "where": "`si -batch`（auCdl）↔ PDK 属性模板（`hnlCDLParamList` / `hnlCDLFormatInst`）↔ `calibre.lvs` 输入",
        "symptom": "含 PDK 器件的 cell 走 CDL 导出时 `si -batch` 失败，报 `hnlCDLParamList` / "
                   "`hnlCDLFormatInst` 缺失 → **没有可用源网表** → `calibre.lvs` 只能到 "
                   "`NOT COMPARED`（再叠加 P-062 还会被截成 `not`）。DRC 侧正常"
                   "（completed，1737 rulechecks / 36 结果）。用户 2026-09-24 判定："
                   "这是**业务包本身跑不通**，立案为缺陷（此前误记为「环境/配方口径问题」）。",
        "repro": "在 wsl-gent 上对含 PDK 器件的 cell 做 CDL 导出（`si -batch`）后跑 "
                 "`calibre.lvs`；或 `python test/semi/probes/calibre_package_http_probe.py --kind lvs`"
                 "（专用环境 `test/artifacts/env/s11-calibre` + 业务面 8128）",
        "evidence": "**第七轮复验（2026-09-24 晚）**：`test/artifacts/evidence/round7/design-iterate/iterate-lvs.json`"
                    "——`calibre.export_cdl(CMP_LIB/inv2, 680 B)` → `virtuoso.layout.gds` → "
                    "`calibre.lvs(deck+cdl)` → `calibre.read_results`：**`status=correct`**、"
                    "ports 4/4、nets 4/4、inst 1/1、`differences=[]`；S11 全链（`test/artifacts/env/s11/`）"
                    "也拿到确定结论（`cdl` 693 B）。旧证据（首报时）：`round5-main/s11-flow2.log`（lvs FAIL）、"
                    "`round5-main/calibre-lvs.json`（`status=NOT COMPARED`）",
        "accept": "含 PDK 器件的 cell 能导出可用 CDL，且 `calibre.lvs` 给出 **CORRECT / INCORRECT** "
                  "的确定结论（不再是 NOT COMPARED）；S11 `lvs` 阶段 PASS",
        "next": "测试侧已复验通过（deck 入口 + runset 入口两条都好）；等上层/设计确认后把卡片移入 `已关闭-近期.md`。"
                "注意：`_calibre.lvs_`（tvf 格式）不是合法 runset，用它当失败证据属『用错文件』",
    },
]

#: 本轮明确闭环（保留记录，避免「消失了没人知道为什么」）
CLOSED_RECENT = [
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
]

#: 早期轮次仍未关闭（多为已上报外部 bug 系统；这里只做索引，避免同一件事两份清单打架）
LEGACY_OPEN = [
    ("P-001", "覆盖度报告（缺负责人）", "待定负责人"),
    ("P-003", "环境占用（跑测前检查清单已写）", "待固化到脚本"),
    ("P-005", "瞬态红灯（观察中）", "观察"),
    ("P-006", "文件纪律（Q1 全链路 / Q2 逐 role / Q3 逐 TB 三项未覆盖）", "待补"),
    ("P-010", "文档一致性（§7 需改「已确认发生、待清理」）", "待改文档"),
    ("P-011", "`/tmp` 口径待定稿（设计内例外 vs 泄露）", "待定稿"),
    ("P-013", "客户端文件泄露（A-1 / A-2 两条代码锚点）", "待处理"),
    ("P-014", "现场观察（找不到创建者）", "待代码定位"),
    ("P-016", "完成度评估 / 补测归口", "待处理"),
    ("P-017", "归属未定（先定创建者）", "待确认"),
    ("P-019/P-020/P-025/P-026/P-027/P-029/P-030/P-031/P-032/P-034/P-037/P-038/P-039/P-041/P-042",
     "早期轮次已上报外部 bug 系统的源码缺陷（`bug-2026…` 编号见台账）", "待设计修（外部系统跟踪）"),
    ("P-046", "S10 e2e 引导源未固定 → 会覆盖别人的 CIW", "测试侧待修（本轮未动）"),
]

CARD_BODY = """# {id} · {title}

| 字段 | 值 |
|---|---|
| 级别 | {level} |
| 归属 | {owner} |
| 状态 | **{status}** |
| 位置 | {where} |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

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
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
"""


def _slug(bug: dict) -> str:
    """卡片文件名用**显式短 slug**（ASCII，便于命令里敲/给设计侧贴）。"""
    return bug.get("slug") or bug["id"].lower()


def render_readme() -> str:
    rows = ["| ID | 级别 | 归属 | 状态 | 一句话 | 卡片 |",
            "|---|---|---|---|---|---|"]
    for bug in OPEN:
        rows.append(f"| **{bug['id']}** | {bug['level']} | {bug['owner']} | {bug['status']} | "
                    f"{bug['title'].replace('|', chr(92) + '|')} | "
                    f"[{bug['id']}-{_slug(bug)}.md]({bug['id']}-{_slug(bug)}.md) |")
    closed = "\n".join(f"| {i} | {t} | {e} |" for i, t, e in CLOSED_RECENT)
    legacy = "\n".join(f"| {i} | {t} | {s} |" for i, t, s in LEGACY_OPEN)
    return f"""# `test/reports/bugs/` —— 未关闭缺陷的唯一跟踪视图

> 维护者：测试工程师（我）｜最近刷新：2026-09-24
> **这个目录回答一个问题：现在还有哪些 bug 没关、谁在等谁、修好的判据是什么。**

## 0. 三条规矩（动这里之前先看）

1. **权威事实在台账**：[问题登记.md](../问题登记.md)。本目录不重复分析，只做「未关闭项」的卡片与索引；
   送修视图（逐条 file:line / 复现 / 验收）在 [第五轮-缺陷清单-上层.md](../第五轮-缺陷清单-上层.md) 与
   [第五轮-缺陷清单-其他.md](../第五轮-缺陷清单-其他.md)。
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

## 3. 早期轮次仍未关闭（{len(LEGACY_OPEN)} 组）

这些多为**已上报外部 bug 系统**（`bug-2026…`）的历史条目，跟踪在外部系统里；这里只做索引，
避免与台账「两份清单打架」。本轮**未复核**它们的最新状态。

| ID | 事项 | 当前状态 |
|---|---|---|
{legacy}

## 4. 关联文件

- 台账（唯一事实源）：[问题登记.md](../问题登记.md)
- 第五轮送修：[第五轮-BUG清单-按层.md](../第五轮-BUG清单-按层.md)、
  [上层](../第五轮-缺陷清单-上层.md)、[其他](../第五轮-缺陷清单-其他.md)
- Spec 覆盖矩阵（哪些要求被测到）：[round5-spec覆盖矩阵.md](../round5-spec覆盖矩阵.md)
- 覆盖率与缺口：[round5-覆盖率补强.md](../round5-覆盖率补强.md)、[覆盖度缺口.md](../覆盖度缺口.md)
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
        extra="## 补充（可选；需要时由 `extra` 字段注入）\n")
    plan = {BUGS_DIR / "README.md": render_readme(),
            BUGS_DIR / "_模板.md": template,
            BUGS_DIR / "已关闭-近期.md": render_closed()}
    for bug in OPEN:
        # `extra` 是给"卡片上后来追加的讨论/决策"留的位置（默认空）——见 CARD_BODY 末尾的警告。
        plan[BUGS_DIR / f"{bug['id']}-{_slug(bug)}.md"] = CARD_BODY.format(
            **{**bug, "extra": bug.get("extra", "")})
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
        print(f"计划文件 {len(plan)} 个；缺失 {len(missing)}；过期 {len(stale)}；"
              f"应清理的旧卡片 {len(orphans)}")
        for item in missing + stale + [str(p.relative_to(ROOT)) for p in orphans]:
            print("  -", item)
        return 1 if (missing or stale or orphans) else 0

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
