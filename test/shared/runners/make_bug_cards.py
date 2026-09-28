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
        "id": "P-103",
        "layer": "上层（calibre 包）· 完成判定",
        "slug": "calibre-pex-premature-completion-masks-stage3-failure",
        "title": "`calibre.pex` 报 `status=completed` 但 stage3 失败：完成判定读到**前一阶段**的 COMPLETED 标记就提前收工（P-102 的真故障被掩盖成绿）",
        "level": "P2（假绿：调用方按 ok/status 判定会以为 PEX 成功，实际没有网表产物）",
        "owner": "设计侧（calibre 运行器的 job_state/等待循环按 log 尾部判完成的口径）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/_calibre_util.py:317-329`（`job_state` 只按 `log_tail` 里出现 `_DONE_MARKERS` 就判 completed）+ "
                 "`src/pyapi/packages/calibre.py:574-594`（blocking 循环一见 completed 就 break）；"
                 "pex 的三阶段日志同名 glob `*.log` 被 `tail -n 40` 合并 → **stage1 的 `CALIBRE xRC::PHDB GENERATOR COMPLETED` 落进 tail**。",
        "symptom": "真机（vblog，2026-09-29 01:05，`pex(fmt=\"spice\")`）run_dir `/home/Gent/project/vblog/calibre-e2e/pex-fmt-1790615068023/`：\n"
                   "- `pex.stage1.log` 尾部 `--- CALIBRE xRC::PHDB GENERATOR COMPLETED ---`（stage1 成功）；\n"
                   "- `pex.stage2.log` 正常结束；\n"
                   "- **`pex.stage3.log` 为空**、**`pex.log` 末行 `stage3_failed`**、run_dir 里 **没有任何 netlist 产物**；\n"
                   "- 但 `calibre.pex` 运行期返回 **`ok=true, status=completed`** ⇒ 假绿。\n"
                   "（同一 run_dir 用 `read_results(kind=pex)` 会因 `stage\\d_failed` 判失败 —— 即**两个入口口径相反**。）",
        "repro": "`PYTHONPATH=src python test/live/packages/calibre_export_pex_e2e_tests.py --transport http`"
                 "（PEX-FMT-01 红钉：断言先查 `stage3_failed`/netlist，再查 status，因此今天判红）",
        "evidence": "run_dir 三份 stage 日志 + `pex.log`（上列实测）；TB 红钉 `PEX-FMT-01`；"
                    "对照 P-102（stage3 argv 非法的根因）与 `_calibre_util.py:322-324` 的 `classify_log`（只认 `ERROR:` 等标记）。",
        "accept": "① 完成判定必须**按阶段**取日志（stage3 的完成标记才算 pex completed），或要求产物（netlist/pdb）齐；"
                  "② `stage\\d_failed` 一旦出现立即判 failed（与 `read_results` 同口径）；③ PEX-FMT-01 转绿。",
        "next": "设计侧与 P-102 一起改（argv + 完成判定）；测试侧复跑 PEX-01/PEX-FMT-01 确认不再假绿。",
        "reported": "2026-09-29（第八轮 calibre PEX 参数面实测，root 直接发现）",
        "updated": "2026-09-29（新立）",
    },

    {
        "id": "P-102",
        "layer": "上层（calibre 包）· xRC 第三阶段",
        "slug": "calibre-pex-stage3-invalid-fmt-argv",
        "title": "`calibre.pex` 第三阶段 argv 非法（`-fmt spice`）：stage1/stage2 成功后 stage3 必被 Calibre 拒绝 → PEX 整体不可用",
        "level": "P2（PEX 作为交付能力不可用；spec 已把它标成「禁止交付」，本条把「为什么」钉到具体 argv 与日志）",
        "owner": "设计侧（calibre 包 `_argv_for` 的 pex 分支；roadmap P0-1 要求改官方 batch）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/calibre.py:1007-1013`（pex 三阶段 argv：stage3 = `[binary, \"-xrc\", \"-fmt\", request.fmt, deck_path]`）；"
                 "Calibre 用法块（`pex.stage3.log:188-215`）只接受 `-fmt { -c | -r | -rc | … | -simple | -netmodel }`，"
                 "`spice`/`simple` **不带前导 `-`** 都不匹配。",
        "symptom": "真机（vblog）实测 2026-09-29 00:05（**用 PDK 的 rcx deck** + LVS 产出的 svdb，其余参数按 spec 12-calibre.md:187）：\n"
                   "- stage1 `calibre -xrc -phdb …` → `--- CALIBRE xRC::PHDB GENERATOR COMPLETED`（成功）；\n"
                   "- stage2 `calibre -xrc -pdb -rc …` → 正常结束；\n"
                   "- stage3 `calibre -xrc -fmt spice …` → 打 usage（`pex.stage3.log:93` 是命令回显，`:188+` 是用法），"
                   "`pex.log` 末尾 `stage3_failed`，桥返回 `pex did not complete: failed input`。\n"
                   "⇒ 三阶段里前两阶段产物（phdb/pdb）都正常，**只有 fmt 阶段的命令形态错**。",
        "repro": "`PYTHONPATH=src python test/artifacts/tmp/pex_rcx_experiment.py`（一次性实验，参数：deck=`/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre/rcx/calibre.rcx`、"
                 "`lvs_run_dir=<含 svdb 的 LVS run>`、`fmt=spice`）",
        "evidence": "run_dir `/home/Gent/project/vblog/calibre-e2e/pex-rcx-1790611157804/`：`pex.stage1.log` 尾部 COMPLETED、"
                    "`pex.stage2.log`、`pex.stage3.log`（命令回显 + usage）、`pex.log` 的 `stage3_failed`；"
                    "TB 侧红钉：`test/live/packages/calibre_export_pex_e2e_tests.py` 的 PEX-01。",
        "accept": "① 按 `spec/research/calibre/00-下一步开发方向.md` P0-1 改成官方链路（有 set 走 `-gui -pex -runset … -batch`，"
                  "与 GUI 基线 `.pex.netlist` 逐字节比对）；或 ② 保留 deck 模式但 stage3 用 Calibre 接受的 flag 形态并断言 `.pex.netlist` 存在；"
                  "③ PEX-01 转绿（或 spec 明确把 deck 模式从接口里删掉）。",
        "next": "设计侧选 ①/②；测试侧按结论改 `calibre_export_pex_e2e_tests.py` 的 PEX 断言（现在是精确红钉）。",
        "reported": "2026-09-29（第八轮 calibre 零调用 op 补测，root 直接定位）",
        "updated": "2026-09-29（新立）",
    },

    {
        "id": "P-101",
        "layer": "上层（verilog 包）",
        "slug": "verilog-import-overwrite-false-silent-noop",
        "title": "`import(overwrite=False)` 对已存在 cell 返回成功但**不写任何内容**，且无 skipped/已存在 标记（用户无法区分「导入成功」与「没做事」）",
        "level": "P3（静默 no-op：调用方会误以为设计已导入）",
        "owner": "待决策（spec 口径：overwrite=False 语义是 skip 还是拒绝）",
        "status": "待决策",
        "where": "`src/pyapi/packages/verilog.py:490`（`import_if_exists := 1 if request.overwrite else 0`）→ ihdl 跳过已存在 cell 并正常结束；"
                 "`import_verilog:562-571` 仍按 `reason=completed` 返回 `cells/views`，未标注「未覆盖/跳过」。",
        "symptom": "真机（vblog）实测：同一 cell（`schemtest/vimp_top`）第二次 `import(overwrite=False)`：\n"
                   "- 返回值 `ok=true, reason=completed`；\n"
                   "- `schemtest/vimp_top/functional` 的 mtime **不变**（1790609122 → 1790609122）⇒ 内容没被改写；\n"
                   "- 结果里 **`cells=[]`、`views=[]`、`warnings=[]`**，但 `reason` 仍是 `completed` ⇒ 与真正导入成功"
                   "（`cells=['vimp_top_child','vimp_top']`）**只在 cells 的空/非空上有区别**，没有 `skipped`/`existing` 标记；\n"
                   "- 2026-09-29 00:15 干净复跑已把这条钉成**红钉**：`test/live/packages/verilog_import_params_e2e_tests.py` IMP-07 断言"
                   "「未写入却 completed 必须带显式跳过标记」→ 当前红（9 绿 + 3 红钉）。\n"
                   "（同一用例另一次运行返回 `RuntimeError: sha256 mismatch`，属 P-090 家族的上传校验抖动，已在 P-090 记录。）",
        "repro": "`PYTHONPATH=src python test/live/packages/verilog_import_params_e2e_tests.py --transport http`（IMP-07 + mtime 对照）",
        "evidence": "`test/artifacts/evidence/round8/verilog-import-params/verilog-import-params.json`；"
                    "mtime 对照见该次运行 stdout（`overwrite=False 返回成功；… mtime … → …（变化=否）`）",
        "accept": "① spec 明确 `overwrite=False` 对已存在 cell 的语义，并在返回里体现（如 `skipped=true` / 结构化错误 `cell_exists`）；"
                  "② TB IMP-07 按结论改成强断言（现在是 NOTE + mtime 检查）。",
        "next": "spec owner 定口径；测试侧把 IMP-07 改成对应断言。",
        "reported": "2026-09-28（第八轮 verilog.import 参数面实测，root 直接发现）",
        "updated": "2026-09-28（新立）",
    },

    {
        "id": "P-100",
        "layer": "上层（verilog 包）· 与 spec 口径",
        "slug": "verilog-import-cell-param-not-honored",
        "title": "`virtuoso.verilog.import` 的 `cell` 参数不参与落地：ihdl 只按**源码顶层模块名**建 cell，取值不同即整体报 `*Error* cell not found`（且写已发生）",
        "level": "P2（spec 说 cell 是显式目标；实际非同名就失败，还会留下已写入的副作用 = 报错但库已改）",
        "owner": "设计侧（verilog 包 `import_verilog` 的 ihdl 调用/参数拼装）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/verilog.py:487-522`（`ihdl_param` 只有 `dest_sch_lib`，**没有任何 dest cell 项**，`ihdl` 因此按源码模块名落地）；"
                 "随后 `_verify_import:575-604` 却用 `request.cell` 去 `ddGetObj` → 不同名必然 `*Error* cell not found`。"
                 "spec：`spec/design-concepts/上层/8-verilog.md:80`「`library` / `cell`：目标库与顶层 cell（**显式给**，不用文件名推导）」。",
        "symptom": "真机（vblog，源文件顶层模块 `vimp_m1`）：\n"
                   "- `import(cell=\"vimp_m1\", …)` → `ok=true, reason=completed`，`schemtest/vimp_m1` 目录存在；\n"
                   "- `import(cell=\"vimp_m2\", 同一个源文件)` → `ok=false, error=RuntimeError: (\"error\" 0 t nil (\"*Error* cell not found\"))`，"
                   "`schemtest/vimp_m2` **不存在**，但 `schemtest/vimp_m1/functional` 的 mtime 已被刷新"
                   "（另一轮实测：23:12:45 → 23:13:22）⇒ **写已发生而调用方收到失败**。\n"
                   "- 结论：`cell` 只在「校验」里被用，落地时被忽略；非同名场景既拿不到产物也拿不到真实原因。",
        "repro": "`PYTHONPATH=src python test/live/packages/verilog_import_params_e2e_tests.py --transport http`"
                 "（IMP-10 是红钉；IMP-01/02/03/09 都按「模块名=请求 cell」跑，故仍能验证其它参数）",
        "evidence": "`test/artifacts/evidence/round8/verilog-import-params/verilog-import-params.json`；"
                    "现场 cell `schemtest/vimp_m1`、`schemtest/vimp_top`（保留不清理）",
        "accept": "① 让 ihdl 按 `request.cell` 落地（在 `ihdl_param`/命令行里给 dest cell，或对源码顶层模块名做显式映射并报错清晰）；"
                  "② 若产品坚持「cell 必须等于顶层模块名」，spec 改口径 + 前置校验（读到模块名不一致时**在写之前**结构化拒绝）；"
                  "③ 两条任一，IMP-10 转绿。",
        "next": "设计侧先定口径（ihdl 能否指定 dest cell 名）；测试侧复跑 IMP-10 与 IMP-01/02 确认无回归。",
        "reported": "2026-09-28（第八轮 verilog.import 参数面实测，root 直接发现）",
        "updated": "2026-09-28（新立）",
    },

    {
        "id": "P-099",
        "layer": "上层（verilog 包）",
        "slug": "verilog-import-returns-empty-views",
        "title": "`virtuoso.verilog.import` 返回值里的 `views` 恒为空，与真机实际视图不符（functional/symbol 明明已生成）",
        "level": "P2（结构化返回值与事实不符：调用方按 `views` 判断产物会得出「什么都没导入」的结论）",
        "owner": "设计侧（verilog 包 `_read_views`）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/verilog.py:251-281`（`_read_views`：SKILL `sprintf(nil \"%L\" out)` → `basic.parse_sexpr` → 遍历取 view/type/data/file）；"
                 "调用点 `_verify_import:594` / `import_verilog:566`（结果 `views` 直接取它）。",
        "symptom": "真机（vblog，`schemtest/vimp_top`）实测：\n"
                   "① `virtuoso.verilog.import(file_is_local=True, ref_libs=[\"basic\"], overwrite=True)` 返回 "
                   "`{\"reason\": \"completed\", \"cells\": [\"vimp_top_child\",\"vimp_top\"], \"views\": [], "
                   "\"instance_count\": 1, \"net_count\": 2, \"term_count\": 2, \"bbox\": [...]}`；\n"
                   "② 同一 cell 用 SKILL 直接查（`mapcar(lambda((v) v~>name) c~>views)`）得到 `(\"functional\" \"symbol\")`；\n"
                   "③ 把 `_read_views` 的**同一条 SKILL 文本**离线跑一遍（`basic.parse_sexpr` + 同一遍历），"
                   "能正常解析出 6 条 view/file 记录 ⇒ 解析逻辑离线可用，问题在真机链路里的实际返回值形态（需设计侧在进程内复现）。",
        "repro": "`PYTHONPATH=src python test/live/packages/verilog_import_params_e2e_tests.py --transport http`"
                 "（IMP-08 是红钉；IMP-01/03 打印 `NOTE P-096` 对照真机实际 views）",
        "evidence": "`test/artifacts/evidence/round8/verilog-import-params/verilog-import-params.json`；"
                    "cell `schemtest/vimp_top` + `schemtest/vimp_top_views`（现场保留，不清理）",
        "accept": "① import 返回值 `views` 至少包含真实生成的视图（与 `mapcar ~>views` 一致）；② IMP-08 红钉转绿。",
        "next": "设计侧在 `_read_views` 里加一行原始返回（`raw`）日志定位真机形态差异；测试侧复跑 IMP-08。",
        "reported": "2026-09-28（第八轮 verilog.import 参数面实测，root 直接发现）",
        "updated": "2026-09-28（新立）",
    },

    {
        "id": "P-097",
        "layer": "上层（verilog 包）/ 库视图刷新时序",
        "slug": "verilog-import-cell-not-found-after-overwrite",
        "title": "覆盖式再导入后紧跟的视图查询偶发 `*Error* cell not found`（同 cell 连导时出现 1 次，之后 2/2 复跑皆成功）",
        "level": "P3（观察：未稳定复现，但用户串行导入同一 cell 时会撞到，表现为整体失败）",
        "owner": "待归属（verilog 包 `_read_views` 与 ihdl 覆盖写后的库视图刷新时序）",
        "status": "观察",
        "where": "`src/pyapi/packages/verilog.py:251-256`（`_read_views` 里 `unless(cell error(\"cell not found\"))`）"
                 "+ `import_verilog:558`（`ddUpdateLibList()` 在 `_verify_import` 之前只刷一次）。",
        "symptom": "2026-09-28 23:03 实测：IMP-01（`file_is_local=True`，overwrite=True）成功后，IMP-02"
                   "（同一 cell、`file_is_local=False`、overwrite=True）在 `_read_views` 处抛 "
                   "`RuntimeError: (\"error\" 0 t nil (\"*Error* cell not found\"))` → 整个 import 返回失败；\n"
                   "随后手工复跑同参数 2 次（远端就地 + overwrite）**2/2 全成功**（`views` 仍为空见 P-096），"
                   "且 `ddGetObj(\"schemtest\" \"vimp_top\")` 一直存在 ⇒ 判定为**时序/刷新**类瞬时现象，非稳定缺陷。",
        "repro": "同参数连跑两次：见 `test/live/packages/verilog_import_params_e2e_tests.py` IMP-01→IMP-02 顺序；"
                 "复现尝试记录见本卡片证据。",
        "evidence": "`test/artifacts/evidence/round8/verilog-import-params/verilog-import-params.json`（`failure` 字段原文）",
        "accept": "① 覆盖式再导入后 `_read_views` 不再出现 cell not found（或在覆盖写后补一次 `ddUpdateLibList()` 再查）；"
                  "② 若确认是瞬时，给 `_read_views` 有界重试并在结果里标注。",
        "next": "设计侧评估覆盖写后的视图刷新时序；测试侧在 IMP-02 前插一次 `ddUpdateLibList` 观察是否消失（不改判据，只做定位）。",
        "reported": "2026-09-28（第八轮 verilog.import 参数面实测，root 直接发现）",
        "updated": "2026-09-28（新立，含 2/2 未复现说明）",
    },

    {
        "id": "P-092",
        "layer": "上层（calibre 包）",
        "slug": "calibre-power-ground-dead-params",
        "title": "`calibre.drc/lvs/pex` 的 `power` / `ground` 声明并校验，但实现**从不读取**（静默无效）",
        "level": "P3（静默无效参数，与 P-084 同类；误导调用方以为能指定电源/地网名）",
        "owner": "设计侧（实现语义或从模型/spec 删除）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/calibre.py:100-101`（字段声明）、`:123-124`（`_opt_text` 校验）——全文件再无 `request.power` / `request.ground` 读取点；"
                 "deck 改写（`:833-849` 的 `rewrite_deck`/`statements_from_params`）也不注入 POWER/GROUND 语句；argv（`:987-1013`）不带对应选项。",
        "symptom": "真机（vblog）实测：`calibre.drc(power=\"VDD\", ground=\"VSS\", …)` 与不传这两个参数的同参数运行"
                   "在 job.json / argv / 报告上**无任何差异**（job.json 里连字段都不出现）；DRC/LVS 结论不变。"
                   "即参数对行为零影响。",
        "repro": "`PYTHONPATH=src python test/live/packages/calibre_params_e2e_tests.py --transport http`"
                 "（CAL-DRC-01 带着 power/ground 跑；CAL-P092-01 记录）",
        "evidence": "`test/artifacts/evidence/round8/calibre-params/calibre-params.json`；"
                    "对照 run_dir `/home/Gent/project/vblog/calibre-e2e/params-drc-*/job.json`（无 power/ground 键）",
        "accept": "① 让 power/ground 参与 deck 改写（注入 `LAYOUT POWER`/`LAYOUT GROUND` 或对应 SVRF 语句）并给可观察差异；"
                  "② 或从模型/spec 删除这两个字段；两者取其一并同步 TB 断言。",
        "next": "设计侧定口径；测试侧按结论把 CAL-P092-01 从 NOTE 改成正向/负向断言。",
        "reported": "2026-09-28（第八轮 calibre 参数面实测，root 直接发现）",
        "updated": "2026-09-28（新立）",
    },

    {
        "id": "P-093",
        "layer": "上层（calibre 包）",
        "slug": "calibre-flat-drc-turbo-invalid-argv",
        "title": "`calibre.drc(hier=False)` 命令行非法：`-turbo` 与 flat 模式冲突 → Calibre 打 usage、作业秒退",
        "level": "P2（该参数组合下 DRC 完全跑不了，且呈现为工具 usage dump 而非可读错误）",
        "owner": "设计侧（calibre 包 `_argv_for`）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/calibre.py:987-997`（`_argv_for`：`-hier` 按 `request.hier` 决定，但 `flags += [\"-turbo\", str(request.turbo)]` 无条件追加）",
        "symptom": "真机（vblog）实测 `calibre.drc(gds=inv.gds, top=inv, deck=PDK/drc/calibre.drc, hier=False, turbo=2)`：\n"
                   "`drc.log` 第 2 行 = `ERROR: The -turbo option is not valid with this flat application.`，随后整段 Calibre usage；\n"
                   "calibre 进程 1s 内退出（`process_alive=false`），run_dir 里只有 usage dump，没有 DRC.rep。\n"
                   "原因：flat（非 `-hier`）DRC 不接受 `-turbo`；桥只按 hier 切换 `-hier`，却始终追加 `-turbo`。",
        "repro": "`PYTHONPATH=src python test/semi/probes/calibre_flat_turbo_probe.py`（预期红）\n"
                 "run_dir 现场：`/home/Gent/project/vblog/calibre-e2e/p093-flat-<ms>/drc.log`",
        "evidence": "`test/artifacts/evidence/round8/p093-flat-turbo-probe.json`（含 drc.log 的 `ERROR:` 原文与 status 快照）",
        "accept": "① `hier=False` 时不追加 `-turbo`（或仅 hier/pex 路径追加）；或 ② 提交前对 `hier=False + turbo` 给结构化拒绝；"
                  "两条任一 + 探针在 flat 模式下能真跑出 DRC.rep（或在非 hier 时明确拒绝）。",
        "next": "设计侧改 `_argv_for` 的 turbo 条件；测试侧复跑探针与 `calibre_params_e2e_tests.py` 的 flat 分支。",
        "reported": "2026-09-28（第八轮 calibre 参数面实测，root 直接发现）",
        "updated": "2026-09-28（新立）",
    },

    {
        "id": "P-094",
        "layer": "上层（calibre 包）· 失败检测",
        "slug": "calibre-tool-death-not-detected",
        "title": "工具秒退不被检测：`status` 只报 `unknown`、`blocking=True` 会等满 timeout（日志里的 `ERROR:` 看不见）",
        "level": "P2（1 秒失败的作业占满 30 分钟预算，且用户拿不到失败原因）",
        "owner": "设计侧（calibre 运行器轮询/状态判定）",
        "status": "待设计修",
        "where": "等待循环 `src/pyapi/packages/calibre.py:574-594`（只在 `completed`/`failed` 时 break）；"
                 "`src/pyapi/packages/_calibre_util.py:317-329`（`process_alive=false` + 有 artifacts + 尾部无 marker → `unknown`）；"
                 "`src/pyapi/packages/calibre.py:929-936`（`_log_tail` 只 `tail -n` 尾部，而 `ERROR:` 在日志第 2 行，"
                 "`classify_log` 的 `_FAIL_MARKERS`（含 `ERROR:`）永远看不到）。",
        "symptom": "实测（同一个 flat DRC 作业）：日志已含 `ERROR: The -turbo option is not valid …`，但\n"
                   "`calibre.status` 返回 `{\"status\": \"unknown\", \"failure_kind\": null, \"process_alive\": false}`；\n"
                   "`calibre.drc(blocking=True, timeout=1800)` 因此蹲满预算（本轮实测 >5 分钟仍停在 poll，被我手工 kill）。\n"
                   "对照 AGENTS.md 的 dual-defense 要求：轮询必须每轮 tail/grep 工具日志里的终态标记——calibre 运行器没做。",
        "repro": "`PYTHONPATH=src python test/semi/probes/calibre_flat_turbo_probe.py`（探针判据：15s 内 status 必须报失败并带 ERROR 行；今天红）",
        "evidence": "`test/artifacts/evidence/round8/p093-flat-turbo-probe.json`（`tool_failed=true` 而 `error_surfaced=false`）",
        "accept": "① 轮询每轮对整份日志（或 `grep -m1 -E 'ERROR:|FATAL ERROR'`）做终态判定；"
                  "② `process_alive=false` 且无完成标记 → 归类 `failed`（failure_kind 如 `process_gone_without_report`）并把 ERROR 行放进 value；"
                  "③ 探针转绿（不再出现秒退作业等满 timeout）。",
        "next": "设计侧改轮询与 `job_state` 的兜底分类；测试侧复跑探针 + `calibre_e2e_tests.py` 的坏 deck 用例确认无回归。",
        "reported": "2026-09-28（第八轮 calibre 参数面实测，root 直接发现）",
        "updated": "2026-09-28（新立）",
    },

    {
        "id": "P-091",
        "layer": "上层（symbol / layout 包）· 与 spec 口径",
        "slug": "screenshot-remote-artifact-cleanup-inconsistent",
        "title": "截图远端产物保留策略三包不一致：schematic 保留、symbol/layout 下载后 `rm -f` 删掉（spec 写「远端存 role root screenshots/」）",
        "level": "P3（口径/文档级：不影响本地产物，但使「远端留证」与审计核对失效）",
        "owner": "待归属（spec 口径 owner 或三包实现统一）",
        "status": "待决策",
        "where": "`src/pyapi/packages/symbol.py:979-987`（finally 里 `rm -f <remote_png>`）；"
                 "`src/pyapi/packages/layout.py:1480-1487`（同款 finally）；"
                 "`src/pyapi/packages/schematic.py:814-852`（**不删**，远端长期保留）；"
                 "spec：`spec/design-concepts/上层/2-schematic.md:27`、`3-symbol.md:41-45`、`4-layout.md:183` 均写「远端存 role root 的 screenshots/」。",
        "symptom": "真机实测（2026-09-28，`screenshot_params_e2e_tests.py`）：\n"
                   "- `virtuoso.schematic.screenshot` 跑完后远端 `role_root/screenshots/<cell>_<ms>.png` **留存**；\n"
                   "- `virtuoso.symbol.screenshot` / `virtuoso.layout.screenshot` 跑完后同名远端文件 **找不到**"
                   "（`find /home/vbuser2 -name 'rx_fe-*'` 与 `find /home/Gent -name 'lay_e2e-*'` 均 0 命中，"
                   "而本地 `artifact/screenshots/*.png` 正常且为合法 PNG）。\n"
                   "⇒ 「远端存 screenshots/」这条 spec 只对 schematic 成立；symbol/layout 把远端当临时暂存并清理。",
        "hypothesis": "两条候选（未直接观测到设计意图）：① spec 想表达的是「远端暂存于 role root/screenshots 再取回」，"
                      "那么 schematic 属于多做（泄漏暂存物），应统一成清理；② spec 想表达的是「远端留证」，"
                      "那么 symbol/layout 属于少做，应去掉 finally 里的 rm。两条都要落成文字或统一实现。",
        "repro": "PYTHONPATH=src python test/live/packages/screenshot_params_e2e_tests.py --transport http \\\n"
                 "  --token vb-vbuser2 --lib serdes_rx --cell rx_fe --view symbol --kind symbol \\\n"
                 "  --out test/artifacts/evidence/round8/screenshot-params/symbol.json\n"
                 "# 同参数换 --kind layout --token vb-vblog --lib schemtest --cell lay_e2e --view layout",
        "evidence": "`test/artifacts/evidence/round8/screenshot-params/{schematic,symbol,layout}.json`"
                    "（SC-01 会把 `remote_present=` 打进 NOTE）；对照 `find` 命令输出见卡片正文。",
        "accept": "① spec 与实现二选一对齐：要么三包统一清理（改 spec 文案为「远端暂存」），"
                  "要么三包统一保留（去 symbol/layout 的 rm）；② 新 TB 的 SC-01 不再出现三包口径分叉。",
        "next": "spec owner 定「暂存 vs 留证」；测试侧按结论改 TB 的 NOTE 为断言。",
        "reported": "2026-09-28（第八轮 screenshot 参数车道实测发现）",
        "updated": "2026-09-28（新立）",
    },

    {
        "id": "P-090",
        "layer": "中层传输（tunnel.upload_file）/ 底层 SSH 常驻 shell",
        "slug": "upload-stage-vanished-before-install",
        "title": "`basic.file.upload` 偶发 `mv: cannot stat <target>.vbtmp-<hex>`：stage 在 sha256 校验通过后消失，安装步骤报错",
        "level": "P3（观察：单次复现、40 次同目标 hammer + 套件复跑均未复现；但错误形态误导为「文件不存在」，掩盖真实性质）",
        "owner": "待归属（中层 tunnel 安装步骤幂等性 / 底层常驻 shell 重试口径，二选一或联合）",
        "status": "观察",
        "where": "`src/transport/tunnel.py:487-497`（stage = `<target>.vbtmp-<hex>` → scp → `sha256sum` 比对 → "
                 "`mv -f -- stage target`）；同一路径被 `src/pyapi/packages/veriloga.py:167-172`（`_write_remote`）与 "
                 "`src/pyapi/packages/basic.py:173-180`（`basic.file.upload`）共用；"
                 "`src/common/ssh.py:1941-1981`（`_run_via_persistent_shell_with_retry` 会对同一命令字符串重发一次）",
        "symptom": "2026-09-28 21:5x：`veriloga_e2e_tests.py --transport http` 的 WRITE-02 patch_source 报 "
                   "`patch_source failed: mv: cannot stat '/home/Gent/project/vblog/schemtest/va_e2e/veriloga/"
                   "veriloga.va.vbtmp-8a7782b8f3884a4aa6e2058e9e8db36f': No such file or directory (commands applied: 0/1)`。\n"
                   "关键点：报错来自 **安装（mv）** 而不是上传或校验——即 upload 已 rc=0、`sha256sum` 已取到并比对通过之后，"
                   "stage 文件在 mv 前消失。\n"
                   "复现性：同套件随后复跑 **7/7 全绿**；同目录同目标 40 次连续 upload **0 失败**（60.7s）；"
                   "同目录 `basic.file.upload`（probe_upload.txt）单次也全绿 ⇒ 非路径/权限/磁盘问题。",
        "hypothesis": "两条候选（均未直接观测到）：①**重试重发**——`_is_retryable_persistent_shell_error` 把 "
                      "`unexpected persistent shell protocol line` / `failed to write to persistent ssh shell` 等"
                      "「已投递但协议异常」判为可重试，重发同一命令串后第二次 `mv` 必然找不到 stage；"
                      "②外部进程在毫秒级窗口删除了 stage（未发现已知的 stage 清理者，`src/` 内无 `*.vbtmp-*` 清理逻辑）。\n"
                      "判别手段：daemon 日志里若有 `Retrying persistent SSH shell for <host> after recoverable protocol error` "
                      "同刻记录，即坐实 ①。",
        "repro": "`PYTHONPATH=src python test/live/packages/veriloga_e2e_tests.py --transport http`（本文件原始失败日志见证据 1）；"
                 "定性探针：`PYTHONPATH=src python test/artifacts/tmp/probe_upload_mv_fail.py`（单次 upload 到同目录，绿）；"
                 "hammer：`PYTHONPATH=src python test/artifacts/tmp/hammer_upload_same_target.py`（40 次同目标覆盖写，绿）",
        "evidence": "① `test/artifacts/tmp/rerun_veriloga.log`（原始 `mv: cannot stat` traceback）；"
                    "② `test/artifacts/tmp/rerun_veriloga2.log`（复跑 7/7 PASS）；"
                    "③ `test/artifacts/tmp/hammer_upload_same_target.py` 输出 `done 40 iters ... fails=0`；"
                    "④ `test/artifacts/env/log-vblog/api-8127-20260928-195332.err.log`（同窗口多次 ConnectionResetError，"
                    "说明该时段客户端/服务端连接确实在异常抖动）",
        "accept": "① 安装步骤幂等化：stage 不存在时若目标文件 digest 与本次 payload 一致，视为已安装并返回成功；"
                  "② 或把重试严格限定在可证明「未投递」的协议错误，并禁止对已投递命令重发；"
                  "③ 两者任一 + 失败时日志打印 `stage/target` 与实际重试原因，使该错误形态不再出现或不再误导。",
        "next": "设计侧评估 `ssh.py` 重试口径与 `tunnel.upload_file` 安装幂等性；测试侧保持观察（本轮 40+1 次未复现），"
                "若再出现请附 `~/.virtuoso-bridge/vblog/run` 日志定位。",
        "reported": "2026-09-28（第八轮真机 gate 复跑 veriloga 套件时发现）",
        "updated": "2026-09-28（新立；含复现性判定：单次/未复现）",
    },

    {
        "id": "P-089",
        "layer": "上层（maestro 包）",
        "slug": "maestro-open-waveform-result-ignored",
        "reported": "2026-09-28（第八轮 op×param 补测；红灯探针已留证）",
        "updated": "2026-09-28（新立）",
        "title": "`maestro.open_waveform_gui.result` 声明但**从不被实现读取**（静默无效）",
        "level": "P3（静默无效参数，与 P-084 同类）",
        "owner": "设计侧（实现语义或从模型/spec 删除）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/maestro.py:187`（`OpenWaveformRequest.result`）；全文件 `request.result` "
                 "只出现在 read_results 的波形表达式（`:1909/:1912`），open_waveform_gui 的 SKILL"
                 "（`:3139-3158`）只做 `v(signal)`，无 `?result` 分支",
        "symptom": "`open_waveform_gui(result=\"ac\")` 与 `result=\"no_such_result_name\"` **都成功**、"
                   "都返回正常窗口（window:243 / window:245）⇒ 参数对行为零影响。",
        "repro": "`PYTHONPATH=src python test/semi/probes/maestro_open_waveform_result_probe.py`（预期红）",
        "evidence": "`test/artifacts/evidence/round8/p089-open-waveform-result.json`",
        "accept": "二选一：① 让 result 参与波形表达式（`?result`）并给出错误名失败语义；"
                  "② 从模型/spec 删除该字段；探针转绿或删除",
        "next": "设计侧定口径；测试侧复跑探针确认",
    },

    {
        "id": "P-088",
        "layer": "上层（maestro 包）",
        "slug": "maestro-delete-var-all-scope-broken",
        "reported": "2026-09-28（第八轮 op×param 补测；红灯探针已留证）",
        "updated": "2026-09-28（新立）",
        "title": "`maestro.write(delete_var, scope=..all..)` 确定性失败：Cannot find a setup database entry for handle 0",
        "level": "P2（用户清理/teardown 常用路径不可用；现有套件用 try/except 掩盖）",
        "owner": "设计侧（maestro 包 delete_var 的 all 分支 SKILL）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/maestro.py:930-941`（all 分支 `foreach(tn cadr(axlGetTests(sdb)) … axlGetTest(sdb tn) …)` / "
                 "`foreach(cn cadr(axlGetCorners(sdb)) … axlGetCorner(sdb cn) …)` → `axlGetVar(0 …)` 报 handle 0）",
        "symptom": "scope 矩阵实测：`global` set/delete 均 ✓；`test`（test=ac）✓；**`all` set ✓ / delete ✗** "
                   "`*Error* error: Cannot find a setup database entry for handle 0`。副产物："
                   "`maestro_e2e_tests.py` 的 scope=all 清理在 try/except 里，失败被吞 → rc_probe 的 sdb 里"
                   "残留 `e2e_save_*` 变量（本轮实测 3 个）。",
        "repro": "`PYTHONPATH=src python test/semi/probes/maestro_delete_var_all_probe.py`（预期红）",
        "evidence": "`test/artifacts/evidence/round8/p086-delete-var-all.json`；`test/artifacts/tmp/probe_delete_var_scopes.py`",
        "accept": "delete_var scope=all 成功删除 global/test/corner 三处同名变量（探针转绿）；"
                  "现有套件的 try/except 清理改为显式断言",
        "next": "设计侧修 all 分支的迭代写法；测试侧复跑探针 + 清理 rc_probe 残留变量",
    },

    {
        "id": "P-083",
        "layer": "上层（spectre 包）",
        "slug": "spectre-export-precision-semantics-undefined",
        "reported": "2026-09-28（第八轮 op×param 补测；未走外部 bug 系统）",
        "updated": "2026-09-28（新立）",
        "title": "`spectre.export.precision` 语义未定义：实现按**有效数字**（`%.Ng`），用户直觉是小数位",
        "level": "P3（口径/文档；会造成「导入的 CSV 精度与预期不符」）",
        "owner": "设计侧（spec 写明语义，或实现改小数位）",
        "status": "待归属",
        "where": "`src/pyapi/packages/spectre.py:1050`（`formatter = f\"{value:.{precision}g}\"`）"
                 "vs `spec/design-concepts/上层/7-spectre.md:287`（只列字段，未定义语义）",
        "symptom": "`export(format=csv, precision=3)` 对 1.23456 输出 `1.23`（3 位有效数字），"
                   "而按「小数位」直觉应为 `1.235`。",
        "repro": "`PYTHONPATH=src python test/live/packages/spectre_params_e2e_tests.py "
                 "--transport http --token vb-vblog`（EXPORT-P1 按实效口径钉住）",
        "evidence": "`test/artifacts/evidence/round8/spectre-params/spectre-params.json`、"
                    "`.../spectre_params_export.csv`（1.23/2.35/3.46）",
        "accept": "spec 明确写「有效数字」，或实现改为小数位；两者取其一并同步 TB 断言",
        "next": "设计侧定口径；测试侧按拍板结果更新 EXPORT-P1 断言",
    },
    {
        "id": "P-084",
        "layer": "上层（maestro 包）",
        "slug": "maestro-export-include-results-ignored",
        "reported": "2026-09-28（第八轮 op×param 补测；红灯探针已留证）",
        "updated": "2026-09-28（新立）",
        "title": "`maestro.export.include_results` 是声明参数但实现**从不读取**（静默无效）",
        "level": "P2（静默无效参数：调用方以为能控制是否携带结果文件）",
        "owner": "设计侧（实现语义或从模型/spec 删除）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/maestro.py:123`（`include_results: bool = True`，全文件仅此一处；"
                 "`rg -n \"include_results\" src/pyapi/packages/maestro.py` 只命中声明行）；spec 未定义该字段",
        "symptom": "同一 `kind=outputs_csv` 下 `include_results=True/False` 导出的文件内容 "
                   "**sha256 完全相同**（本轮实测 3c7e476b…），参数对产物零影响。",
        "repro": "`PYTHONPATH=src python test/semi/probes/maestro_export_include_results_probe.py`"
                 "（预期红；verdict=RED(参数被忽略)）",
        "evidence": "`test/artifacts/evidence/round8/maestro-include-results/include-results.json`",
        "accept": "二选一：① 实现 `include_results` 的真实语义（并在 spec 定义）；"
                  "② 从 `ExportRequest`/spec 删除该字段；探针转绿或删除",
        "next": "设计侧定口径；测试侧复跑探针确认",
    },
    {
        "id": "P-070",
        "layer": "上层（maestro/spectre 包）",
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
        "extra": "## 设计侧进展（2026-09-28，提交 `64c803c`）\n"
                 "- 真机调查 v2：`set_run_mode('Monte Carlo Sampling')` + **裸** `maeRunSimulation` 可跑出真 history "
                 "`MonteCarlo.0`（24.8s）；文档写的 `?runMode` 默认 Single Run 与实测不符。\n"
                 "- 选项矩阵：`maeSetRunOption` 只认 `mcmethod`/`mcnumpoints`；其余 15 项走 `axlPutRunOption`+"
                 "`axlSetRunOptionValue` 可写可回读（`dutsummary` 读回空串）。\n"
                 "- 副作用提醒：MC 实验会把共享库 `maestro_tb/rc_probe` 的 run_mode 改成 Monte Carlo Sampling，"
                 "**跑完务必还原**（本轮已由测试侧恢复过一次）。\n"
                 "- 待办：产品拍板「支持驱动」后，在 maestro 包补正式入口 + spec；测试侧据此补真机 MC 验证与 yield/sigma 对数。\n",
    },
    {
        "id": "P-078",
        "layer": "上层（schematic 包）",
        "slug": "place-wire-style-args",
        "title": "`place_wire` 样式参数拼接重复：width 静默建出 path、color/line_style 直接报错",
        "level": "P2（静默错误结果 + 硬报错）",
        "owner": "设计侧（schematic 包）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/schematic.py:575-583`（两段追加逻辑都保留：575-578 与 579-583 重复拼 width/color/line_style；"
                 "按官方签名应只保留 `width [color [lineStyle]]` 一次 → 删除第二段）",
        "symptom": "`place_wire` 只传 `points` 正常；**一旦传样式参数**：\n"
                   "1. `width=0.1` → 生成 `schCreateWire(... 0 0 0.1 0.1 nil)`，**静默建出 `path` 而不是 `line`(wire)**，"
                   "`schematic.read` 看不到该线（wire_count=0），下游连通性/网表会当它不存在；write 仍报 ok。\n"
                   "2. `width+color` → `too many arguments (at most 9 expected, 10 given)` 硬报错。\n"
                   "3. `width+color+line_style` → `12 given` 硬报错。\n"
                   "真机 DB 复核：ctrl 用例 shape=`((\"line\" nil nil nil))`，width 用例 shape=`((\"path\" 0.1 nil nil))`。",
        "repro": "python test/semi/probes/schematic_wire_style_probe.py            # 真机，5 例：ctrl/route OK，width/color/style BUG\n"
                 "python -m pytest test/offline/unit/test_schematic_contracts.py -q  # 离线钉住用例 test_wire_style_arguments_exact 必红",
        "evidence": "`test/artifacts/evidence/round8/schematic-wire-style.json`（逐例 write/read/DB 三层 + 离线 SKILL 文本）；"
                    "离线失败输出见 round8/offline-win-1.log（本条为**有意红钉住**）",
        "accept": "① 半真机探针 `schematic_wire_style_probe.py` **5/5 OK**（width 读回 width≈0.1 且 read 可见；"
                  "color/line_style 不再报 too-many-arguments 且读回正确）；"
                  "② 离线 `test_wire_style_arguments_exact` 转绿；③ 复跑 `schematic_e2e_tests.py`（含 ATOM-wire）不回归。",
        "next": "设计侧按官方签名收敛为单次拼接（删 579-583 段或 575-578 段，二者只留一）→ 通知测试侧；"
                "测试侧复跑上述三件套后销案。",
        "reported": "2026-09-28（测试侧第八轮参数矩阵发现，卡片直报）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-079",
        "layer": "其他（注册流程）",
        "slug": "local-joint-port-silent-coercion",
        "title": "local 模式显式 `daemon_port`≠`local_port` 被静默归一化（spec 要求双值相等；`_probe` 守卫不可达）",
        "level": "P3（参数被静默丢弃）",
        "owner": "设计侧（注册口径二选一，建议显式拒绝）",
        "status": "待设计修",
        "where": "`src/register/flow.py:1180-1185`（`_prepare_local_port`：`joint = role.local_port or role.daemon_port` 后**同步覆写两值**）"
                 "与 `:705-715`（`_probe` 的‘双值必须相等’守卫——正常流程经第 2 步后二者已相等，**不可达**）；spec：`中层/add-中层配置文档.md` §6.4",
        "symptom": "local 模式显式提交 `daemon_port=65091, local_port=65092`：第 2 步静默把两者都改成 **65092**（local_port 胜出），"
                   "第 3 步照常 `probed`，无错误无告警 —— 调用方指定的 daemon 端口被丢弃。"
                   "spec 措辞是「显式双值必须相等」，既未拒绝、也无文档写明优先级。",
        "repro": "离线最小复现（测试侧实测，2026-09-28）：\n"
                 "  RegistrationRequest(mode=\"local\", user=\"u\", token=\"tok-local\",\n"
                 "      roles={\"daemon\": {\"daemon_port\": 65091, \"local_port\": 65092}})\n"
                 "  → flow.validate() stage=validated、ports=(65092,65092)；flow.probe() stage=probed、errors=[]\n"
                 "脚本：`test/artifacts/tmp/_r8_joint_port.py`",
        "evidence": "同上脚本输出；`test/offline/unit/test_register_flow.py::test_validate_preallocates_joint_port_for_local_mode`（只覆盖缺省同步，不含冲突双值）",
        "accept": "二选一：① **拒绝**（建议）：第 2 步发现显式双值不等 → failed，错误指向两个端口值（并补离线断言）；"
                  "② **文档化优先级**：spec 写明 local_port 优先/或 daemon_port 优先，行为按文档固定并补断言。",
        "next": "设计侧定口径 → 测试侧补离线用例（`test_register_flow.py`）并复跑全套。",
        "reported": "2026-09-28（第八轮条款逐条核账 · g1-core 配置#108 发现）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-080",
        "layer": "上层（verilog / veriloga / layout 包）",
        "slug": "view-type-read-unvalidated",
        "title": "`view_type` 在 read 路径不校验（空串/整数/bogus 静默接受）；write 校验后取值又被忽略",
        "level": "P2（参数合同不一致 + 死参数）",
        "owner": "设计侧（verilog / veriloga 包）；\"view_type 是否参与寻址\"需 spec owner 定口径",
        "status": "待设计修",
        "where": "`src/pyapi/packages/verilog.py:201-230`（read 不碰 view_type）、`:307`（只有 write 校验）、`_view_dir:161`（不使用 view_type）；"
                 "`src/pyapi/packages/veriloga.py:205-235`、`:476`、`_view_dir:145`。主文件名 `MAIN_FILE` 硬编码，"
                 "与 spec `8-verilog.md:45`『主文件名由 viewType 决定（`ddMapGetDataTypeFileName` 查）』不一致。"
                 "截图面同族两处：`src/pyapi/packages/symbol.py:84-96`（ScreenshotRequest.view_type，只透传给 geOpen）、"
                 "`src/pyapi/packages/layout.py:98-109`（同）；两处对 `view_type=\"bogus_type_xyz\"` 都静默成功。",
        "symptom": "真机（vblog）实测：`read(view_type=\"\")`、`read(view_type=123)`、`read(view_type=\"bogus_type_xyz\")` 全部 `ok=true` 且返回默认视图内容（静默忽略取参）；"
                   "同一字段 `write(view_type=\"\")` 返回 400 `invalid request: view_type must be a non-empty string`，而 `write(view_type=\"bogus_type_xyz\")` 返回 ok。"
                   "read/write 校验口径不一致；非默认取值对寻址/主文件名没有任何可观察影响。\n"
                   "**同族第三处（2026-09-28 新增，layout 包）**：`virtuoso.layout.screenshot(view_type=\"bogus_type_xyz\")` "
                   "也返回 ok=true 并出图（`view_type=\"maskLayout\"` 与 bogus 之间无可观察差异）；"
                   "`virtuoso.symbol.screenshot(view_type=\"bogus_type_xyz\")` 同样 ok=true。"
                   "两条都被新 TB `test/live/packages/screenshot_params_e2e_tests.py`（SC-06）红钉住"
                   "（跑 `--kind symbol` / `--kind layout` 会在 SC-06 转红——这是**预期红钉**，不是 TB 坏了）。",
        "repro": "python test/artifacts/tmp/r8_p080_p081_evidence.py（真机；含 read 五态 + write 两态）\n"
                 "python -m pytest test/offline/unit/test_view_type_param_contract.py -q  # 4 条 strict xfail：read 的空串/整数必须 ValueError",
        "evidence": "`test/artifacts/evidence/round8/p080-viewtype-p081-remote-path-2026-09-28.json`（live 五态 + write 两态）；"
                    "`test/offline/unit/test_view_type_param_contract.py`（修复后 xfail→XPASS 转红，强制删标记）",
        "accept": "① read 对 view_type 与 write 同口径校验（空/非字符串 → ValueError；4 条 xfail 转绿）；"
                  "② 产品定口径：若 view_type 按 spec 参与主文件名/视图类型决策 → 实现并对非默认值给可观察差异；"
                  "若仅为兼容字段 → spec 写明『不参与寻址』并统一 read/write 校验。",
        "next": "设计侧先定 ② 口径、修 read 校验与/或主文件名映射；测试侧按结论删 xfail，复跑 verilog/veriloga 两套 E2E 与离线合同。",
        "reported": "2026-09-28（第八轮 op×param 参数矩阵攻击发现，卡片直报）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-081",
        "layer": "上层（verilog / veriloga 包）· Windows/Linux 一致性",
        "slug": "remote-posix-path-mangling",
        "title": "`file_is_local=False` 时 Windows 客户端把 POSIX 远端路径转成反斜杠 → 远端找不到文件",
        "level": "P2（该模式在 Windows 客户端完全不可用）",
        "owner": "设计侧（verilog / veriloga 包）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/verilog.py:218-225`（`path = Path(request.file_path)` → `str(path)` 交给 download）、"
                 "`src/pyapi/packages/veriloga.py:218-225`；Linux 客户端为 `PosixPath` 不受影响 → **同一请求两端行为不同**。",
        "symptom": "Windows 客户端真机实测：`read(file_path=\"/home/Gent/project/vblog/.../veriloga.va\", file_is_local=False)` → "
                   "`RuntimeError: download requires a regular file: /home/Gent/.virtuoso-bridge/vblog/\\home\\Gent\\... (missing)`；"
                   "路径被改写成 `\\home\\Gent\\...`（WindowsPath 形态）并按相对路径拼到 role root 下。`source.path` 回显同样是反斜杠形态。",
        "repro": "python test/artifacts/tmp/r8_p080_p081_evidence.py（真机；看 read_remote_file_is_local_false）\n"
                 "python -m pytest test/offline/unit/test_remote_posix_path_contract.py -q  # 2 条 strict xfail：传给 download 的路径必须逐字节不变",
        "evidence": "`test/artifacts/evidence/round8/p080-viewtype-p081-remote-path-2026-09-28.json`；"
                    "`test/offline/unit/test_remote_posix_path_contract.py`；live 侧已在 `test/live/packages/veriloga_e2e_tests.py` READ-02 留『修复后恢复远端读断言』的注释。",
        "accept": "① Windows 客户端 read(file_is_local=False, file_path=<POSIX>) 成功且 sha256 与库路径读取一致；"
                  "② source.path 原样回显；③ 2 条 xfail 转绿；④ 恢复 live READ-02 的远端读断言。",
        "next": "设计侧不要把远端路径过 `pathlib.Path`（或只在 file_is_local=True 分支使用）；测试侧复跑离线 xfail + veriloga live + 跨平台客户端矩阵。",
        "reported": "2026-09-28（第八轮 op×param 参数矩阵攻击 file_is_local 分支发现，卡片直报）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-082",
        "layer": "上层（schematic + layout 包）",
        "slug": "region-quad-vs-two-points",
        "title": "region 口径漂移（P-074 同类）：spec 定版‘对角两点、禁四元组’，实现（读过滤/截图）仍只收四元组",
        "level": "P2（spec 合规请求直接失败）",
        "owner": "设计侧（schematic / layout 包对齐 P-074 定版）",
        "status": "待设计修",
        "where": "schematic：`src/pyapi/packages/schematic.py:79-126`（region 过滤按 4 个 float 解包）、`:932-935`（screenshot region 强制 len==4）；"
                 "layout：`src/pyapi/packages/layout.py:1707-1714`（`_filter_region` 强制 len==4）。"
                 "spec：`上层/2-schematic.md` §1.3「region/bbox 一律对角两点 [pos0,pos1]（read 与 write 同形，**不再用四元组**）」；"
                 "`上层/4-layout.md:36/71/175`（`{\"region\":[pos0,pos1]}`）。",
        "symptom": "按 spec 传对角两点 `[[x0,y0],[x1,y1]]`：schematic `object_filter.region` → **裸 TypeError**（float(list)）；"
                   "schematic `screenshot.region` → `ValueError: region must be [x1, y1, x2, y2]`；layout `object_filter.region` → "
                   "`ValueError: shape.region must be [x0, y0, x1, y1]`。反之 spec 明令弃用的四元组在三个面全被接受 —— "
                   "同文件 layout `_bbox`（write 侧）已是两点口径，read 过滤与 schematic 截图没跟上 P-074 定版。\n"
                   "**加强证据（真机探针，2026-09-28）**：layout `read(depth>0)` **在两种形态下都必然失败** —— "
                   "扁平四元组过了 `_filter_region` 后被 `_bbox` 拒（`ValueError: bbox must be [ [x, y], [x, y] ]`），"
                   "嵌套两点又被 `_filter_region` 拒 → **depth 特性 100% 不可用**（`layout-depth.json`：depth0 shapes=3 OK，depth1 直接 BUG）。",
        "repro": "python test/artifacts/tmp/_r8_region_shapes.py   # 两点/四元组 ×（schematic instance/shape、layout filter）对照\n"
                 "python test/artifacts/tmp/_r8_public_region.py  # 公共 API：read(object_filter=两点 region) → 裸 TypeError；四元组放行到 middle\n"
                 "离线钉住（修复前必红）：test/offline/unit/test_schematic_contracts.py::test_region_filter_uses_two_points_per_p074_spec；"
                 "test/offline/unit/test_layout_contracts.py::test_object_filter_region_uses_two_points_per_p074_spec",
        "evidence": "`test/artifacts/tmp/_r8_region_shapes.py` 六行输出；现有 TB 用四元组的点位："
                    "`test_layout_contracts.py:382`、`test_schematic_contracts.py:92/104`（修复后需同步改两点）；"
                    "真机探针 `test/semi/probes/layout_depth_probe.py` → `test/artifacts/evidence/round8/layout-depth.json`",
        "accept": "① 三个请求面只接受对角两点、四元组报显式 ValueError（点明 pos0/pos1）；② 两条钉住用例转绿；"
                  "③ 旧四元组点位 TB 同步改两点并全绿（layout/schematic 包 E2E 无回归）；"
                  "④ `layout_depth_probe` 转绿：depth=1 读回 shapes 严格大于 depth=0（层级下钻语义成立）。",
        "next": "设计侧按 P-074 口径统一实现 → 通知测试侧；测试侧改旧点位、复跑离线 + layout/schematic 包 E2E 后销案。",
        "extra": "## 关联\n\n"
                 "- **P-085**：`layout.read(depth>0)` 与 region 的组合任何写法都失败（与本条同源但独立，见该卡片）；"
                 "修本条时两处（`_filter_region` 与 `_bbox`）必须一起对齐。\n",
        "reported": "2026-09-28（第八轮条款逐条核账 · g4-edit schematic#014-018/049-050、layout#023-024/028 发现）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-085",
        "layer": "上层（layout 包）",
        "slug": "layout-depth-region-unusable",
        "title": "`layout.read(depth>0)` 与 `region` 组合**任何写法都失败**（扁平→`_bbox` 拒；两点→`_filter_region` 拒）",
        "level": "P2（spec 声明的参数组合确定性不可用）",
        "owner": "设计侧（layout 包）；与 P-082 同源但独立",
        "status": "待设计修",
        "where": "`src/pyapi/packages/layout.py:1522-1525`（deep 路径 `_bbox(region)` 要求嵌套两点）"
                 "与 `:1707-1714`（`_filter_region` 要求扁平四元组）；spec `上层/4-layout.md:36,40`（region 定版 `[pos0, pos1]`，depth>0 需 region 或 layers）",
        "symptom": "`depth>0` 时两条校验互斥，**没有任何一种 region 写法能通过**：\n"
                   "| 输入 | 结果 |\n"
                   "|---|---|\n"
                   "| `depth=0` + `region=[0,0,60,60]` | ✅ 正常（shapes=3） |\n"
                   "| `depth=1` + `region=[0,0,60,60]`（实现自定的扁平格式） | ❌ `ValueError: bbox must be [ [x, y], [x, y] ]` |\n"
                   "| `depth=1` + `region=[[0,0],[60,60]]`（spec 定版两点） | ❌ `ValueError: shape.region must be [x0, y0, x1, y1]` |\n"
                   "depth>0 因此是**确定性不可用**的参数组合（不是偶发）。",
        "repro": "python test/semi/probes/layout_depth_probe.py            # 期望 RED（现为确定性失败）\n"
                 "python -m pytest test/offline/unit/test_layout_depth_contract.py -q  # 1 条 strict xfail",
        "evidence": "`test/artifacts/evidence/round8/layout-depth.json`（depth0=3 shapes OK / depth1=ValueError）；"
                    "`test/offline/unit/test_layout_depth_contract.py`（stub middle 证明死在参数形态、未触达传输层）",
        "accept": "二选一定口径后实现：① 按 P-074 定版统一 `region` 为对角两点（改 `_filter_region`，deep 分支不动）；"
                  "② 或 deep 分支把扁平四元组转成两点后再交给 `_bbox()` 并同步 spec。"
                  "任一方案都要补回归：`depth=1 + region` 返回跨层结果（shapes>0）且 `layout_depth_probe.py` 转 GREEN。",
        "next": "设计侧与 P-082 一起定 region 形态（两处必须同时对齐）→ 测试侧复跑探针 + 离线 xfail + layout live。",
        "reported": "2026-09-28（第八轮半真机探针 layout_depth_probe.py 发现）",
        "updated": "2026-09-28",
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
                   "该形态 **8×15s 轮询不自愈**，需按 Runbook §10.3 重启实例。",
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
        "updated": "2026-09-28",
    },
    {
        "id": "P-087",
        "layer": "上层（maestro 包）· 会话复用",
        "slug": "maestro-write-save-false-still-persists",
        "title": "`save=False` 的改动不被隔离：后续任意一次 save 会把它静默带走（跨请求污染）；同场景 `delete_var` 清理报 handle 错误",
        "level": "P2（静默跨请求污染用户 setup + 清理失败）",
        "owner": "设计侧（maestro 包）；`save` 的对外语义需 spec owner 定稿",
        "status": "待设计修",
        "where": "`src/pyapi/packages/maestro.py:1760-1765`（save=False 只跳过显式 `maeSaveSetup`，不丢弃/隔离会话内改动）；"
                 "`:1303-1317` `_close_if_created`/`_close_session`；`delete_var` 清理路径（本场景报 handle 错误）。"
                 "spec `6-maestro.md` 未定义 `save` 语义（仅 :173 提到 open/save/close）",
        "symptom": "磁盘级因果链（真机 maestro_tb/rc_probe，2026-09-28 实测）：\n"
                   "1. `write(set_var v=1.0)`（save=True）→ 步骤含 save_setup，sdb 中 v=1.0 ✓\n"
                   "2. `write(save=False, set_var v=2.0)` → 步骤**不含** save_setup，**立即**查 sdb 仍 v=1.0 ✓（未立即落盘）\n"
                   "3. 随后一次**无关**的 `write(set_var other=ok)`（save=True）→ sdb 中 v 被写成 **2.0** ✗ —— "
                   "未保存改动留在复用会话里，被下一次保存静默带走（跨请求污染）。\n"
                   "4. 同场景 `delete_var` 清理两个变量均失败：`*Error* error: Cannot find a setup database entry for handle 0`。",
        "repro": "PYTHONPATH=src python test/semi/probes/maestro_save_false_disk_probe.py   # 期望 RED（第 5 项 FAIL=2.0）\n"
                 "# 证据：test/artifacts/evidence/round8/maestro-save-false-disk.json",
        "evidence": "`test/artifacts/evidence/round8/maestro-save-false-disk.json`（5 项 checks：步骤表/立即磁盘/泄漏判据/清理）；"
                    "live 侧 `maestro_e2e_tests.py` WRITE-06 现按步骤表判定（可过），**不足以防住本条泄漏**，以磁盘探针为准",
        "accept": "① spec 明确 `save` 语义（推荐：save=False 的改动必须被隔离 —— 关闭/丢弃或快照-回滚，后续 save 不得带走）；"
                  "② 实测第 3 步泄漏消失（旧变量仍 1.0），删参数则改为负向「传 save 被拒」；"
                  "③ `delete_var` 在复用会话/失败恢复路径可正常清理（或明确报可读错误）；④ 探针转 GREEN。",
        "next": "设计侧定 `save` 隔离口径 + 修 delete_var handle 路径；测试侧把磁盘探针纳入半真机层并复跑 live WRITE-06。",
        "reported": "2026-09-28（第八轮：live WRITE-06 首红 → 磁盘级探针确认隔离缺失）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-095",
        "layer": "上层（maestro 包）· GUI 模态",
        "slug": "maestro-run-stale-overwrite-history-modal",
        "title": "`maestro.run` 的 Overwrite History 目标悬空：`ASSEMBLER-3018` 模态框阻塞 CIW → daemon 空响应（watchdog 不处理）",
        "level": "P1（可把实例 CIW 挂死；P-086 持久形态的直接根因）",
        "owner": "设计侧（maestro 包 run 流程 + 对话框 watchdog）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/maestro.py:2960-2973`（`request.history` 时 `axlSetOverwriteHistory(setup t)` + `axlSetOverwriteHistoryName(...)`，**运行后/无 history 时不清理或复位**）；"
                 "`_start_simulation_with_watchdog`（未识别/未关闭 `ASSEMBLER-3018` 的 `adexlMessageDialog`）",
        "symptom": "真机（vblog/maestro_tb rc_probe）实测链：先前 run 把 Overwrite History 设为 `Interactive.8`；该 history 之后不存在（cell 只剩 MonteCarlo.*）；"
                   "再跑一次**不带 history** 的 `virtuoso.maestro.run` → ADE 弹模态 "
                   "`ERROR (ASSEMBLER-3018): The history item 'Interactive.8' selected to be overwritten does not exist` + "
                   "`# Displaying modal dbox \"adexlMessageDialog\", title \"ADE Assembler Message 3018\"` → CIW 阻塞，"
                   "daemon 进入 **Empty response 窗口且 2 分钟不自愈**（8×15s 轮询全空响应；query 正常）。"
                   "run 返回 `maeRunSimulation returned nil; diagnosis: {'current_form': None, 'sessions': []}`。",
        "repro": "1) 复现窗口：`python test/artifacts/tmp/_r8_vblog_wait.py`（8×15s 全 Empty response）\n"
                 "2) 现场：` ssh wsl-gent 'tail -n 8 ~/.virtuoso-bridge/vblog/run/CDS.log'` → ASSEMBLER-3018 模态行\n"
                 "3) 恢复：`test/artifacts/tmp/hard_restart_user_instance.sh`（Gent 身份，端口 65121）",
        "evidence": "CDS.log 22:48:02 现场（ASSEMBLER-3018 + adexlMessageDialog 两行）；"
                    "`round8/coverage-main-r8.log` 中同族 Empty response 历史；P-086 卡片（本条是其持久形态的根因）",
        "extra": "## 补充（2026-09-28 22:55，跨重启持久化实证）\n\n"
                 "- 实例硬重启后，用 `open_gui` 拿到 session 后读 setup 标志：`(t \"Interactive.8\")` —— "
                 "**悬空目标跨重启持久化在 .sdb 里**；\n"
                 "- 手动 `axlSetOverwriteHistory(setup nil)` 后复核 `(nil \"Interactive.8\")`，再跑裸 `run` → "
                 "`status=done, history=Interactive.0`（新 history 正常创建，不再弹框）。\n"
                 "- 结论：run 流程必须在设置/使用后复位 Overwrite 标志，或运行前校验目标存在。\n",
        "accept": "① run 结束（成功/失败/超时）后 Overwrite History 状态被复位（或每次 run 前校验目标存在、不存在即清 flag）；"
                  "② watchdog 能识别并关闭 `adexlMessageDialog`/ASSEMBLER-3018（或在弹框前避免）；"
                  "③ 复现件：不带 history 的 run 在悬空 overwrite 目标下**不得**挂死 CIW，且返回结构化失败；"
                  "④ 无窗口期残留（P-086 复跑转绿）。",
        "next": "设计侧修 run 的 overwrite 生命周期 + watchdog 覆盖 ASSEMBLER 模态；测试侧补红灯探针（悬空目标 → 期望结构化失败而非挂死）。",
        "reported": "2026-09-28（第八轮：P-084/P-089 fixture 恢复时定位到根因）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-096",
        "layer": "上层（maestro 包）· 崩溃恢复 / OA 写锁",
        "slug": "maestro-stale-write-lock-modal-wedge",
        "title": "陈旧 OA 写锁（属主进程已死）触发 `axlOpenInRead0` 模态框 → CIW/daemon 再次挂死；应结构化失败或自动强制",
        "level": "P2（崩溃后该 cell 的 maestro 打不开且会挂死实例，需人工删锁）",
        "owner": "设计侧（maestro 打开/写路径的锁判定；可参考 schematic 的“locked by another session”结构化失败）",
        "status": "待设计修",
        "where": "现场：`/home/Gent/project/vblog/maestro_tb/rc_probe/maestro/maestro.sdb.cdslck`（属主为被 kill 的旧实例）；"
                 "`src/pyapi/packages/maestro.py` 的 open/ensure-editable 路径（未先把死属主锁转成结构化失败）；"
                 "CDS.log 弹框：`# Displaying modal dbox \"axlOpenInRead0\", title \"ADE Assembler Open View\"`",
        "symptom": "实例被 kill 后留下 `maestro.sdb.cdslck`（写锁，属主进程已不存在）。新实例上 `maestro.open_gui` → "
                   "`deOpenCellView failed ...: Empty response from daemon`，随后**所有 skill 请求空响应**（实例再次挂死）；"
                   "CDS.log 显示 `Couldn't get a write lock ... currently \"write\" locked by user Gent on machine GLIS-DESKTOP (since …)` + 模态框。"
                   "手动删除陈旧 `cdslck` 并重启实例后 open_gui 立即恢复成功（session fnxSession0, editing）。",
        "repro": "1) 手工复现：杀掉带未释放锁的 maestro 实例 → 新实例 `python test/artifacts/tmp/_r8_opengui2.py` → 观察 Empty response + CDS.log 模态行\n"
                 "2) 恢复：清 `<cellview>/*.cdslck` + 重启实例（见 `round8/../internal/环境Runbook-内部.md` §10.2/§10.3）",
        "evidence": "CDS.log `Couldn't get a write lock … since Mon Sep 28 22:43:53` + `axlOpenInRead0` 两行；"
                    "`_r8_opengui2.py` 输出；恢复后 open_gui ok 对照",
        "accept": "① 打开/编辑前检测写锁属主：属主进程已死（或期望指纹不符）→ 返回结构化失败（或按产品口径自动强制/只读打开），**不得**弹模态；"
                  "② 回归：`kill -9` 实例 → 新实例 open_gui 要么成功（死锁被正确处理）要么明确失败，CIW/daemon 不挂死；"
                  "③ 与 P-095 的 watchdog 修复联动（ASSEMBLER/ADE 模态兜底）。",
        "next": "设计侧定“死属主锁”处置口径并实现；测试侧在 `maestro_pkg_probe`/新探针里补“陈旧锁恢复”回归（先手工造锁再验证行为）。",
        "reported": "2026-09-28（第八轮：vblog 崩溃恢复时实测）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-098",
        "layer": "上层（calibre 包）· 阻塞轮询口径",
        "slug": "calibre-blocking-timeout-status-not-timeout",
        "title": "`blocking=true` 超时返回最后一次 `status`（running/unknown），未按 spec 返回 `status=timeout`",
        "level": "P3（口径偏差：调用方按 spec 判 `status==\"timeout\"` 会永远不成立；作业本身不杀、行为其余正确）",
        "owner": "设计侧（calibre 包轮询收尾）",
        "status": "待设计修",
        "where": "`src/pyapi/packages/calibre.py:575-594`（deadline 到点后 `value.update({\"status\": last.get(\"status\", \"timeout\")})`——"
                 "`last` 在跑过至少一次 poll 后必非空，于是永远是最后一次观测值 `running`/`unknown`）；"
                 "spec：`上层/12-calibre.md:117-121`（§3.4「终态或超时即返回；**超时返回 `status=timeout`** 且后台作业继续跑」）",
        "symptom": "离线可复现（假 middle 让作业永远 running）：`drc(blocking=True, timeout=0.2, poll_interval=0.01)` → "
                   "返回 `value.status='running'`、`elapsed_ms≈202`、`error='drc did not complete: running'`；"
                   "spec 要求的 `status='timeout'` 只会在**从未 poll 过**时意外落到默认值。"
                   "后台作业继续跑（无 kill 命令）这一半符合 spec。",
        "repro": "python -m pytest test/offline/unit/test_calibre_package.py -q -k timeout_reports --runxfail   # 当前红（'timeout' != 'running'）",
        "evidence": "红灯钉 `test/offline/unit/test_calibre_package.py::PackageTests::test_drc_blocking_timeout_reports_timeout_status`"
                    "（strict-xfail；value 全量打印见 --runxfail 输出）",
        "accept": "① deadline 到点且最后状态非终态时，对外 `status` 必须是 `\"timeout\"`（可加 `last_status` 字段保留观测值）；"
                  "② 不得杀后台作业；③ 红钉转绿（XPASS 后删 strict 标记）。",
        "next": "设计侧改收尾口径 → 测试侧复跑该钉与 calibre 套件。",
        "reported": "2026-09-28（第八轮 calibre#069 缺口核账时按 spec 对表发现并复现）",
        "updated": "2026-09-28",
    },
    {
        "id": "P-104",
        "layer": "上层（maestro 包）· 缺失目标的静默成功",
        "slug": "read-config-missing-view-silent-empty",
        "title": "`maestro.read_config` 对**不存在的 view** 静默返回空配置（ok=true）；调用方无法区分「空 setup」与「view 不存在」",
        "level": "P2（静默假数据：空配置会被当成既有 setup 继续消费）",
        "owner": "设计侧（maestro 包）；口径二选一需 spec owner 拍板",
        "status": "待设计修",
        "where": "`src/pyapi/packages/maestro.py:1321`（`read_config` 入口）→ `:3095-3102`（`maeOpenSetup(...)` 读会话），"
                 "**不校验 cellview 是否存在**；同包 `read_results` 对缺失结果目录会结构化失败（口径不一致）。",
        "symptom": "健康真机（vb-s11，2026-09-29 02:2x）实测：`read_config(library=\"maestro_tb\", cell=\"rc_probe\", "
                   "view=\"no_such_view_p104\")` → **ok=true**，返回空配置（`tests=[]`、`corners=[\"Nominal\"]`、"
                   "`variables={}`、`run_mode=\"\"`），steps 为 `open_session/setup/options/...`；调用方无法据此判断 view 不存在。"
                   "同一断言在 `test/live/packages/maestro_view_param_e2e_tests.py` 的只读族（\"不存在的 view 必须结构化失败\"）"
                   "当前为**红钉**（2026-09-29 01:5x 全量覆盖跑 `packages/maestro view-param (direct)` rc=1，报"
                   "`read_config expected structured failure, got ok`）。",
        "repro": "python test/artifacts/tmp/r8_p104_readconfig_probe.py        # vb-vblog 当时被 P-086 卡住，已在 vb-s11 确认\n"
                 "python test/live/packages/maestro_view_param_e2e_tests.py --transport http  # read 族负例当前红",
        "evidence": "`test/artifacts/evidence/round8/p104-readconfig-missing-view.json`（vb-s11 原始响应）；"
                    "`test/artifacts/evidence/round8/coverage-main-r8d.log`（vblog 侧同断言原文）。",
        "accept": "① `read_config` 对不存在 view 返回结构化失败（点名 library/cell/view）；"
                  "或 ② spec 明确「不存在即空配置」语义 → TB 按该口径改成断言空配置并加 NOTE，二者取其一并同步报告。",
        "next": "设计侧定口径；测试侧按结论把 `maestro_view_param_e2e_tests.py` 的 read 族负例改成对应用例后复跑。",
        "reported": "2026-09-29（第八轮覆盖率重算时由 maestro view-param TB 红钉暴露，root 复核并最小化）",
        "updated": "2026-09-29（新立）",
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
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
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
