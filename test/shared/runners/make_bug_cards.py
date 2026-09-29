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
        "id": "C3",
        "layer": "测试侧（消费方适配）· C1 破坏性契约变更",
        "slug": "c1-consumer-migration",
        "title": "C1 落地后测试侧消费方未适配：仍按旧 `data` 壳解析响应（\u7ea6 50 个文件）",
        "level": "P2（测试资产失效：不修则 live/semi 门禁假红/读不到 steps）",
        "owner": "测试侧（root）",
        "status": "待测试侧",
        "where": "命中面：`rg -l 'get(\"data\")' test/ --glob '!test/artifacts/**'`；已适配 4 个"
                 "（`calibre_export_pex_e2e_tests.py`、`maestro_e2e_tests.py`、`skill_log_options_e2e_tests.py`、"
                 "`maestro_p095_overwrite_wedge_probe.py`）。",
        "symptom": "C1 契约（`2f88853`）把业务载荷移到顶层（值型 `value`、命令/skill 型 `result`）、"
                   "成功默认省略 `steps`、失败壳去掉 `data`；旧解析 `response.get(\"data\")` 拿到空 dict ⇒ "
                   "假红（calibre 门禁 ENV-01「环境缺 drc_ok」、maestro TB WRITE-05「SKILL failed: {}」）"
                   "或读不到响应级 `steps`（WRITE-06「save_setup 步骤 []」）。",
        "repro": "PYTHONPATH=src python test/live/packages/calibre_export_pex_e2e_tests.py --transport http",
        "evidence": "C1 契约 TB `test/offline/unit/test_top_layer_dispatch.py::test_success_returns_result_body`"
                    "（`{\"ok\":True,\"value\":7}`）；本轮实测：`basic.command.run` → 顶层 `result`；"
                    "`maestro.read_config` → 顶层 `value` + **响应级** `steps`。",
        "accept": "① 命中文件全部改为形状无关解包（顶层 `value`/`result` 优先，兼容旧 `data`）；"
                  "② 需要步骤名的用例改读响应级 `steps`；③ 逐套复跑 live/semi 门禁并如实记账；④ 完成后关 C3，C1 随之可关。",
        "next": "按清单分批适配（优先级 live/packages → semi/probes → live/flows），每批复跑对应门禁。",
        "reported": "2026-09-29（C1 落地后首轮复跑暴露）",
        "updated": "2026-09-29（新立）",
    },


    {
        "id": "C4",
        "layer": "顶层（response serialization）· 上层（pyapi.models）",
        "slug": "command-result-namedtuple-array",
        "title": "`CommandResult` NamedTuple 被 JSON 序列化为位置数组，命令 / 文件 / GUI / Spectre 结果丢失字段名",
        "level": "P2（跨 basic 操作响应契约缺陷：调用方必须按位置猜字段，后续加字段或调整顺序会破坏兼容性）",
        "owner": "设计侧（`pyapi.models.CommandResult` 的模型形状，或 `server.dispatch.jsonable` 的 NamedTuple 序列化口径）",
        "status": "待设计修",
        "where": "`src/pyapi/models.py:133-144`（`CommandResult` 为 NamedTuple：returncode/stdout/stderr/kind）；"
                 "`src/server/dispatch.py:58-77`（`jsonable()` 对 tuple 统一转 list，字段名丢失）；"
                 "`src/pyapi/packages/basic.py:168-181`（command 的 `result` 与 `steps[].detail` 均直接携带 `CommandResult`）。",
        "symptom": "实测 `basic.command.run(cmd=\"hostname\")` 返回：\n"
                   "`{\"ok\":true,\"result\":[0,\"GLIS-DESKTOP\\n\",\"\",\"command\"]}`；\n"
                   "`[0, stdout, stderr, kind]` 没有字段名，调用方必须记住位置。`steps[0].detail` 又重复同一数组。"
                   "同一问题覆盖 `basic.file.upload`、`basic.file.download`、`basic.gui.run`、`basic.spectre.run`。",
        "repro": "curl -sS -X POST http://127.0.0.1:8127/api/operation "
                 "-H 'Content-Type: application/json' "
                 "-d '{\"operation\":\"basic.command.run\",\"token\":\"<token>\",\"cmd\":\"hostname\"}'",
        "evidence": "2026-09-29 实测响应：HTTP 200，`result=[0,\"GLIS-DESKTOP\\n\",\"\",\"command\"]`，"
                    "与 `steps[0].detail` 完全相同；代码锚点：`pyapi/models.py:133-144`、"
                    "`server/dispatch.py:58-77`、`pyapi/packages/basic.py:176-182`。",
        "accept": "① `CommandResult` 在业务响应中稳定序列化为对象："
                  "`{\"returncode\":0,\"stdout\":\"...\",\"stderr\":\"\",\"kind\":\"command\"}`；"
                  "② 顶层 `result` 与 `steps[].detail` 不得再使用位置数组表达该结构；"
                  "③ 新增契约 TB 钉住字段名与值；④ 同步适配依赖位置的消费方。",
        "next": "设计侧选定单点修复：优先在 `jsonable()` 的 tuple 分支前处理 NamedTuple `_asdict()`，"
                "或把 `CommandResult` 改为具名模型；测试侧补离线契约 TB 并复跑 basic 五操作 HTTP 冒烟。",
        "reported": "2026-09-29（用户直报：`basic.command.run` 返回结果难以理解）",
        "updated": "2026-09-29（新立）",
        "extra": "## 补充（2026-09-29）\n\n"
                 "这与 C1 的顶层响应改造叠加：C1 后业务 Result 本体直接返回，因此 `result` 的字段语义必须自描述；"
                 "继续使用位置数组会让 C1 的“本体直返”契约更难消费。",
    },


    {
        "id": "P-105",
        "layer": "上层（symbol / layout 包）· screenshot 参数校验",
        "slug": "screenshot-view-type-unvalidated",
        "title": "`symbol/layout.screenshot` 的 `view_type` 坏值**不被校验**（ok=true 静默接受；P-080 同族的第三个位置）",
        "level": "P3（静默无效参数；与 P-080/P-092/P-084 同类）",
        "owner": "设计侧（screenshot 入参校验；与 P-080 的 read 侧同口径）",
        "status": "待测试侧",
        "where": "`src/pyapi/packages/layout.py`（`ScreenshotRequest` → `_screenshot_skill` 链路，view_type 只透传不校验）；"
                 "`src/pyapi/packages/symbol.py` 同族（待 symbol 档取证）；对照 `verilog/veriloga` 读侧已按 `dda3775` 校验。",
        "symptom": "真机（vblog，2026-09-29 15:4x，`virtuoso.layout.screenshot(view_type=\"bogus_type_xyz\")`）返回 **ok=true**；"
                   "同一 TB 里 `schematic` 档 5/5 绿、`layout` 档仅 SC-06 红。\n"
                   "（symbol 档本轮因 vb-vbuser2 的 CIW `SKILL execution timed out` 未取到证据，属环境态，不当作已覆盖。）",
        "repro": "PYTHONPATH=src python test/live/packages/screenshot_params_e2e_tests.py --transport http\n"
                 "（默认 layout 档；SC-06 断言：坏 view_type 必须 ok=false）",
        "evidence": "`test/artifacts/evidence/verify-fix-r9/shot-layout.txt`（SC-01..05 PASS / SC-06 FAIL）；"
                    "对照 `shot-schematic.txt` 5/5 绿。",
        "accept": "① `virtuoso.symbol.screenshot` 与 `virtuoso.layout.screenshot` 的 `view_type` 与 read/write 同口径校验："
                  "非字符串/空串 → ValueError；不在该包支持枚举内 → 结构化拒绝（点名取值）；② SC-06 转绿；"
                  "③ symbol 档在健康 CIW 上取证并判定（本轮环境超时，未覆盖）。",
        "next": "设计侧定 view_type 的合法集合（layout=maskLayout；symbol=schematicSymbol）并加校验；测试侧复跑三档 screenshot TB。",
        "reported": "2026-09-29（第九轮修复复验，root 直接发现）",
        "updated": "2026-09-29（新立）",
    },


    {
        "id": "C1",
        "layer": "上层（basic 包 + pyapi.models 序列化）· 响应契约",
        "slug": "json-response-redundancy",
        "title": "`basic.skill.execute` 响应 JSON 冗余：同一个 `VirtuosoResult` 在 `data.result` 与 `data.steps[0].detail` 各序列化一次，空可选字段全展开",
        "level": "P2（全局响应形态缺陷：所有 basic.skill.execute 命中；两层重复携带完整结果，日志开启时体积翻倍）",
        "owner": "设计侧（上层 basic.py 的结果构造 + pyapi.models 的序列化口径；若涉及顶层 jsonable 归顶层）",
        "status": "待测试侧",
        "where": "`src/pyapi/packages/basic.py:146-155`（`Result(steps=[... detail=skill], result=skill)` 同一对象放两处）；"
                 "`src/pyapi/models.py:24-37`（`VirtuosoResult` 7 个字段；空 errors/warnings/metadata/log 也参与 model_dump）；"
                 "`src/server/dispatch.py:58-77,151`（`jsonable` → `model_dump(mode=\"json\")`，外层再包 `ok/data/error`）。",
        "symptom": "实测 `basic.skill.execute(skill_code=\"1+1\")` 的响应：外层 `ok`、`data.ok`、`steps[0].ok`、`detail.status` 四处表达成功；"
                   "**同一个 `VirtuosoResult` 在 `data.steps[0].detail` 和 `data.result` 各出现一次**；两份都带\n"
                   "- `errors: []`、`warnings: []`、`metadata: {}`、`log: \"\"`；\n"
                   "- `execution_time: 0.32900000002700835`（完整浮点 repr）。\n"
                   "真正结果只有 `output: \"2\"`，响应仍约 700 字节。",
        "repro": "POST http://127.0.0.1:8127/api/operation\n"
                 "{\"operation\":\"basic.skill.execute\",\"token\":\"<token>\",\"skill_code\":\"1+1\"}\n"
                 "对照：同一响应里 `data.result` 与 `data.steps[0].detail` 的 `output/status/errors/warnings/metadata/log` 完全相同。",
        "evidence": "用户 2026-09-29 实测响应（见卡片原文）；代码锚点三处；"
                    "上游测试现状：`test/live/flows/*` 大量直接读 `data.result`，`adc_sar_flow_tb.py` 等又 fallback 到 `steps[0].detail`，"
                    "说明重复形态已成事实接口。",
        "accept": "① 先定 canonical 位置（建议只保留 `data.result`，`steps` 只留步骤元信息/失败时留原始结果）；"
                  "② 同一 `VirtuosoResult` 不得在同一响应中出现两次；③ 空 `errors/warnings/metadata/log` 按选定口径省略，"
                  "`execution_time` 限定精度；④ 新增离线契约 TB 钉住最小响应形态；⑤ 更新所有消费 `data.result`/`steps[0].detail` 的调用方。",
        "next": "实现已落地（`2f88853` 等）；测试侧剩「消费方适配」——由 **C3** 跟踪（约 50 个文件），C3 收口后关本卡。",
        "reported": "2026-09-29（用户直报：`basic.skill.execute` 的 `1+1` 响应过长）",
        "updated": "2026-09-29（实现已落地；离线 TB 4/4 绿；消费方适配转 C3）",
        "extra": "## 讨论决策（2026-09-29）\n\n"
                 "**决策 1（统一壳）**：顶层不再把业务结果套进 `ok/data/error` 壳——业务包可达且返回结果时，"
                 "**直接返回业务包结果本体**；只有走不到业务包（非法 JSON / 缺 `operation`/`token` / 未知 operation / "
                 "Request 构造失败 / 未预期异常）才返回壳形错误。\n\n"
                 "配套前提（三条，缺一即不可行）：\n"
                 "- 业务 Result 必须保证含 `ok`/`error`——建议在 `pyapi.models` 收口 Result 基类（当前 10 个包各自定义 Result，口径已漂移）；\n"
                 "- `ok`/`error`/`steps` 定为**保留字段**，业务字段不得占用（合并后与业务字段同一命名空间）；\n"
                 "- 属**破坏性变更**：需同步消费方（`test/live/flows/*` 大量读 `data.result`，`adc_sar_flow_tb.py` 等 fallback 到 `steps[0].detail`）。\n\n"
                 "**决策 2（steps 改造）**：任何业务操作支持公共可选参数 `step_details`；**`steps` 出现条件 = 开启 `step_details` 或操作失败**，"
                 "两者皆无则整字段省略；出现时每步记 `{\"name\": 名, \"ok\": 布尔, \"detail\": 中层结果}`，键名统一 `name`。\n\n"
                 "**决策 3（删字段）**：删除 `VirtuosoResult.metadata`（`src/pyapi/models.py:36`）与 `SimulationResult.metadata`（`:111`）——"
                 "新链路无任何写入点、恒为 `{}`；日志已有 `log` 字段，其余扩展信息应由上层 Result 的业务字段承载，"
                 "不由公共模型提供万能字典（`spec/research/04-log-return-system-proposal.md:159` 同向）。\n\n"
                 "影响面（已核对）：`src/` 无写入亦无读取；`examples/` 中 7 处 `result.metadata` 读取的是**旧包** `virtuoso_bridge`"
                 "（旧实现里 metadata 承载 `command`/`spectre_command`/`delivery`/`queue_wait_s` 等），与新模型无关；"
                 "`SimulationResult` 除定义与导出外无其他使用点。\n\n"
                 "**决策 4（`execution_time` 精度）**：**保留三位小数**（毫秒级，`round(x, 3)`）。"
                 "建议在 `VirtuosoResult` 模型层用字段序列化器统一处理——现写入点集中在 `src/common/skill_client.py`（共 10 处），"
                 "逐点 round 既易漏、新路径也会再漏；模型层处理可让 HTTP 响应与 `save_json` 等所有出口口径一致。\n\n"
                 "## 上层落地（设计/上层开发，2026-09-29）\n\n"
                 "- `pyapi.models` 增加公共 `ResultBase` + `ResultPackage`；`ResultBase.model_dump()` 统一控制 `steps` 出现条件。\n"
                 "- 12 个业务包的 Result/特殊 Result 统一继承 `ResultBase`；Package 统一继承 `ResultPackage`。\n"
                 "- 77 个 Request 直接增加公共可选字段 `step_details: bool = False`。\n"
                 "- 成功且未开启 `step_details` → 整个 `steps` 省略；失败始终带 `steps`；开启后成功也带。\n"
                 "- C1 上层契约 TB `test/offline/unit/test_result_contract.py` **4/4 绿**；全量 offline unit 通过。\n"
                 "- 顶层/模型侧（本体直返、两字段错误壳、`CDSlog`、删 `metadata`、`execution_time` 三位小数）已由对应提交完成。\n",
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
        "id": "P-070",
        "layer": "上层（maestro/spectre 包）",
        "slug": "monte-carlo-missing",
        "title": "蒙特卡洛能力缺失：只能读回 MC 结果，不能驱动 MC 仿真",
        "level": "P2（能力缺失）",
        "owner": "待决策（产品口径：支持驱动 MC or 明确不做）→ 设计侧实现/写 spec",
        "status": "待测试侧/待确认",
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
                 "- 待办：产品拍板「支持驱动」后，在 maestro 包补正式入口 + spec；测试侧据此补真机 MC 验证与 yield/sigma 对数。\n"
                 "## 测试侧真机验收（2026-09-29，P-070 复验）\n"
                 "- 驱动链已通：`set_run_mode('Monte Carlo Sampling')` + `set_run_option(mcnumpoints=2)` 回读生效；"
                 "裸 `run` 产出 `MonteCarlo.1`，`read_history` = `done`、**2/2 点**；`read_results` 返回 `points=2`。\n"
                 "- 结果面缺口：同一响应的 `value.monte_carlo.overall.total_points=0`、`outputs=[]`（Yield 表为空，"
                 "文本 `Yield Estimate: 0 %(0 passed/0 pts)`）。\n"
                 "- 待确认：`maestro_tb/rc_probe` 的 output 是否定义了 spec/target（无 spec 时 Yield 表本就为空 ⇒ 属夹具，"
                 "需造带 spec 夹具再验收）；若夹具本应有 spec ⇒ 属 Yield 聚合出口缺陷。\n"
                 "- 新增 TB：`test/live/packages/maestro_mc_e2e_tests.py`（MC-01..04 + 状态还原）。\n",
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
]

#: 本轮明确闭环（保留记录，避免「消失了没人知道为什么」）
CLOSED_RECENT = [
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
