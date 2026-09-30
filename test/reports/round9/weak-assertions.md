# round9 · 断言强度审计（任务书 D）

> 执行：subagent `/root/opparam_r9`（D 线原定 subagent 因线程上限未启动，由 B 线接手）
> 方法：`test/reports/round9/weak_assert_audit.py`（AST，只读）→ `weak-assert-audit.json`
> 起因：上一轮漏掉 C06（桥执行 `print` 的 CIW 输出与 `CDSlog` 归属）——那一类"只断言 ok、没断言返回值"的用例是本轮重点排查对象。

## 0. 数字与方法

- 扫描范围：`test/offline` / `test/semi` / `test/live` 全部 `.py`
- 断言点 **5853**：strong **4187** / medium **459** / weak **1207**
- "仅弱断言"的用例 **128**（live 31 / offline 97 / semi 0），"读了 log 但完全没断言日志"**0**
- 强度分级：字面量比较、数值区间、字面量集合、startswith/endswith、`assertRaises`、`Evidence.check(expected, actual)` → strong；
  只验真值/`ok`/存在/`isinstance`/`len>0` → weak；其余 → medium
- **重要**：静态分级只能给线索。本报告 §1 是**人工逐条核实过的真弱点**，§2 是**核实过的假阳性类别**，
  §3 才是机器原始候选表（未核实的不要直接当缺陷）。

## 1. 人工核实的真弱点（4 类，按优先级）

### W-1（最高）`skill_log_options_e2e_tests.py` 的 LOG-04/05/06：只验"被接受"，不验日志内容

> **✅ 已于 round9 20:52 关闭**：LOG-04 改为按 §4 断言 warn 过滤、LOG-04b/04d 新增 §5 降级断言、
> LOG-06 补 `CDSlog == ""`（并修掉过期 C1 消费方）→ **http 7/7 绿**。
> 详见 `test/reports/round9/log-options-w1-r9.md` 与证据 `test/artifacts/evidence/round9/skill-log-options-r9.json`。
> 残留：§5 第 3 档（error 截断）在 SKILL 侧不可达，已在同一报告里如实列出。

| 用例 | 现有断言 | 缺口（round9 已按右列补齐） |
|---|---|---|
| LOG-04 `case_warn_accepted`（:100） | `assert response.get("ok")` | `log_level=warn` 的**语义**（应滤掉 info 级 `printf` 文本）没有任何断言 → 实现把 warn 当 all 处理也照样绿 |
| LOG-05 `case_max_bytes_accepted` | 同上（run 标签自述"内容截断不做断言，见 NOTE"） | `log_max_bytes` 的**截断行为**完全未验；brief 里提到过"超长单行在 CDSlog 里消失"的可疑观察，正因这条缺口没被抓住 |
| LOG-06 `case_domain_operation_accepts`（:112） | `assert ok` + `assert steps` | 领域操作带 `log_level=off` 时**没有断言该响应 `CDSlog` 为空**——这正是 C06 同类（"没校验 log 应当的返回值"） |

**建议**：LOG-04 补"warn 下不含 info 标记、含 warn 标记"；LOG-05 补"超限时按 error-only 降级 + 截断说明"（与 `底层/6-日志返回设计标准 §5` 对齐）；LOG-06 补"`CDSlog` 为空串"。
> 该文件属 C 线（log 语义）活跃区，我未直接改，留给 C/root 落笔。

### W-2 `skillref_e2e_tests.py::_case_search_local`：只验命中非空

> **✅ 已于 round9 20:56 关闭**：四档检索改为验内容（层集合、首条命中名/来源文件、`why`/`score`、
> `truncated`）→ **http 6/6 绿**，证据 `test/artifacts/evidence/round9/skillref-r9.txt`，详见 `w2-w3-r9.md`。

`:93-110` 三种 `search_in` + `body` 检索都只 `_check(hits, "…empty")`。检索返回**垃圾结果**（命中项字段缺失、分数乱序、`under` 未生效）时仍绿。
**建议**：对已知查询断言命中项内容——如 `query="dbOpenCellView"` 时某条命中 `name`/`path` 含该串，且每条命中含 spec 要求的字段；`under=["cpf_ref"]` 时断言语料来源受限于该目录。

### W-3 `step_details_e2e_tests.py::case_failure_keeps_steps`：只验 `steps` 非空

> **✅ 已于 round9 20:56 关闭**：补末步形状判据（`name=="command"`、`ok is False`、`detail.returncode==1`、
> `error` 含 `rc=1`）→ **http 6/6 绿**，详见 `w2-w3-r9.md`。

`:130` `assert steps`。SD-05 的语义是"失败响应保留 steps"，但没断言失败步骤的**形状**（`ok is False`、有 `name`、失败 detail 非空）——SD-01 只覆盖成功路径的形状。
**建议**：补 `steps[-1]["ok"] is False` 与 `name` 存在；若失败原因由 `error` 承载，再断言 `error` 非空。

### W-4 `serdes_rx_flow_tb` / `design_iterate_tb` 的 stage 函数：成功由 `op()` 抛出与 `st.bad` 聚合承担，值级读回不均

> **✅ 已于 round9 21:01 关闭（范围经复核修正）**：真正的缺口只有 `serdes_rx_flow_tb.stage_buf`（完全无读回），
> 已补"实例名集合 + 网络名集合"读回判据并接入 `stage_ctle`；`stage_top`/`stage_layout`/`stage_ctle` 复核后本就有值级判据。
> **http 实测：`--stage buf` rc=0（6.75s）、`--stage ctle` rc=0（16.95s）**，
> 证据 `test/artifacts/evidence/round9/serdes-r9-{buf,ctle}/`，详见 `w4-flows-r9.md`。
> `design_iterate_tb.stage_lvs` 仍是"文档化 A/B 分段"（A 段断言 `correct`），不属缺口。

- `Stage.ok()`（`serdes_rx_flow_tb.py:146-147`）**只是记账**，不比较 `detail`；真正的失败判定来自 `op()` 失败即 `raise FlowError`（:94-99）与 `main()` 的 `if any(step.ok is False): failed = True`（:900-905）。
- 因此机器把 `stage_buf/stage_term/stage_top/stage_layout` 判为"仅弱断言"**部分成立**：这些 stage 确实没有值级读回（例如 `stage_buf` 建完 buffer 只调 `check_and_save`+`symbol.generate`，没有回读实例数/连接性）。
- 反例（已核实为**假阳性**）：`design_iterate_tb.stage_lvs` 文档里明确分 A/B 两段——A 段断言 `correct`（P-069 判据），B 段只记录并在 docstring 说明是 TB 手搭版图的局限。

**建议**：对"关键 stage"（buffer/CTLE/top/layout）补一条回读断言（实例数、端口数、bbox 或 connectivity），把"操作成功"升级为"结果正确"。

## 2. 人工核实的假阳性类别（机器列表不能直接当缺陷）

| 类别 | 例子 | 实际强度 |
|---|---|---|
| 断言在 helper 体内 | `screenshot_params_e2e_tests` 的 `case_window/case_region/case_flags/case_default`；`_check_png` → `_png_ok` 校验 **PNG magic（8 字节）+ 文件 ≥1000 字节** | **strong**（值级校验），不是弱断言 |
| 集合包含关系 | `verilog_import_params_e2e_tests::case_result_views_red_pin` 的 `set(truth).issubset(set(returned))` | **strong**（真机视图集合必须被覆盖） |
| `require(results, label, cond)` 形状 | `registration_failure_matrix_tb`（semi，30 条） | **strong**（cond 在 index 2，含 `status==200 and stage==…` 字面量比较） |
| 断言在别处（注册/夹具/runner） | `role_split_tb.main`、`scale_local_fake_tb.main`、`cellview_e2e_tests._case_negative` | 需按文件看，机器判弱不代表真弱 |

## 3. 机器候选表（live，31 条，供派单；未核实项请先看 §2）

| 文件 | 用例 | weak 数 | 首条弱断言 | 核实结论 |
|---|---|---|---|---|
| screenshot_params_e2e_tests.py | case_window | 9 | `opened.get('local_path')` | 假阳性（PNG 内容校验） |
| screenshot_params_e2e_tests.py | case_region | 9 | `value` | 假阳性（同上） |
| screenshot_params_e2e_tests.py | case_flags | 6 | `value` | 假阳性（同上） |
| screenshot_params_e2e_tests.py | case_default | 3 | `value` | 假阳性（同上） |
| maestro_e2e_tests.py | _case_waveform_gui | 3 | `opened['window']` | 待核（开窗类，建议补窗口标题/波形名断言） |
| verilog_import_params_e2e_tests.py | case_result_views_red_pin | 3 | `truth` | 假阳性（issubset） |
| maestro_e2e_tests.py | _case_gui_lifecycle | 2 | `opened['session']` | 待核 |
| maestro_view_param_e2e_tests.py | _case_waveform_gui | 2 | `bool(opened.get('window'))` | 待核 |
| skill_log_options_e2e_tests.py | case_domain_operation_accepts | 2 | `response.get('ok')` | **真弱点 W-1** |
| skill_log_options_e2e_tests.py | case_warn_accepted | 1 | `response.get('ok')` | **真弱点 W-1** |
| skill_log_options_e2e_tests.py | case_max_bytes_accepted | 1 | `response.get('ok')` | **真弱点 W-1** |
| skillref_e2e_tests.py | _case_search_local | 2 | `hits` | **真弱点 W-2** |
| skillref_e2e_tests.py | _case_errors | 2 | `not response.get('ok')` | 待核（负例：应断言错误码/字段） |
| step_details_e2e_tests.py | case_failure_keeps_steps | 2 | `response.get('ok') is False` | **真弱点 W-3** |
| step_details_e2e_tests.py | case_env | 1 | `response.get('ok') is True` | 环境自检，可接受 |
| spectre_params_e2e_tests.py | case_measure_bad_source | 2 | `transport` | 待核（负例） |
| spectre_e2e_tests.py | _case_failure | 1 | `not response.get('ok')` | 待核（负例） |
| cellview_e2e_tests.py | _case_negative | 2 | `transport` | 待核（负例） |
| schematic_e2e_tests.py | _case_check_and_save | 1 | `bool(data.get('ok'))` | 待核 |
| symbol_e2e_tests.py | _case_missing_view | 1 | `not response.get('ok')` | 待核（负例） |
| veriloga_e2e_tests.py | _case_delete | 1 | `not response.get('ok')` | 待核（负例） |
| design_iterate_tb.py | stage_lvs / stage_r1_sch / stage_r1_layout | 2/1/1 | `t` | 假阳性（A 段断言 correct；见 §1 W-4 反例） |
| serdes_rx_flow_tb.py | stage_buf / stage_term / stage_top / stage_layout | 1/1/1/1 | `t` | **部分成立**（W-4：无值级读回） |
| role_split_tb.py | main | 1 | `host` | 待核（环境/编排） |
| scale_local_fake_tb.py | main | 1 | `args.base_port` | 待核（压测编排） |
| registration_role_split_tb.py | main | 1 | `args.lab_host` | 待核（编排） |

## 4. offline 弱断言（97 例）说明

多数是纯函数单测里的 `assertTrue(x)` / `assertIsNotNone`（如 `test_process_lifetime`、`test_paramiko`、`test_ssh_edges`），
语义上"只要过程不炸"就是判据，风险低；仅当用例名声称在验**业务值**时才值得加强（例：`test_calibre_package::test_export_summary`
只 `assertTrue(result.ok)`，可补 summary 字段断言）。**本轮不建议把 97 例全部改写**，收益低且会引入噪声。

## 5. 结论与建议

1. 断言强度整体是健康的（strong 占比 71.5%），**没有发现"整轮只验 ok"的成套 TB**；C06 那类漏洞集中在 W-1（log 语义 3 例）。
2. **W-1 / W-2 / W-3 / W-4 全部关闭**（见 `log-options-w1-r9.md` / `w2-w3-r9.md` / `w4-flows-r9.md`）；
   仅余 offline 97 例低风险弱断言（纯函数单测的 `assertTrue(x)`，按 §4 不建议批量改写）。
3. 本脚本可复跑（只读、5 秒级），建议纳入每轮收口：`python test/reports/round9/weak_assert_audit.py`，
   把"仅弱断言用例数"作为趋势指标；机器列表须经 §2 的假阳性过滤后再派单。
