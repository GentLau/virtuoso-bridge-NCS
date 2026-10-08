# round9 全面测试报告

> 执行：测试/root（主） + subagent 车道 A（spec 矩阵）/B（op×参数·弱断言·嵌套键）/C（log 语义）
> 日期：2026-09-29 ｜ 口径：**关闭条件 = 可复跑证据**；C06 类"只验 ok、不验返回值"为本轮重点
> 三层：离线 / 半真机 / 真机；五张核账：spec 条款 · 原子 · op×参数 · 嵌套键 · 断言强度

## 1. 三层结果

| 层 | 结果 | 证据 |
|---|---|---|
| 离线 | ✅ **0 红**（**收尾后复跑**：23:2x 逐文件 **115 文件 / 0 失败**；单会话 **2736 / 0 失败 / 0 错 / 10 skip**，耗时 241.6s）。10 条 skip **全部有明确原因**：2 条 = C07 红钉（strict xfail）+ 8 条 = POSIX/Windows 平台分支；`check_skip_reasons.py` 汇总"无原因 0"。早先 `offline-full.txt` 是 20:19 被中断的残件（无汇总），**不作为证据**；三次单会话中 1 次 flaky（`test_register_flow` 顺序依赖，已定案测试侧，见 `round9/offline-flaky-r9.md`）→ **已修**（每用例唯一用户名，消共享注册表耦合）。 | `test/artifacts/evidence/round9/offline-final-r9.log`、`round9/offline-final-r9.xml`、`round9/offline-final-r9-single.log`、`round9/offline-r9-official.log` |
| 半真机（40 探针） | 跑批 37 ok / 3 红 → 3 红**全部消解**：`_maestro_tb.py` 的 C4 消费方修复（2 条，复跑 rc=0）+ 并发争用伪红（1 条，solo 36/36+36/36 全绿）。分诊：`round9/semi-r9-failure-triage.md` | `evidence/round9/semi-r9-final.log`、`round9/maestro-env-probe-r9b.log`、`round9/maestro-e2e-probe-r9b.log`、`round9/one-shot-burst-r9.json` |
| 真机（两个 runner，别混） | ① `run_package_e2e.ps1` **10 套**：8 绿 + 2 红 → **layout 修复后 11/11 绿**、maestro 复审；② `run_all_http.py` **19 套**（round9 新接入 step_details/layout_geometry/gui）：首轮 14 绿/5 红 → **复跑后 17/19 绿**；剩 2 红均为产品侧新卡（P-106 / C09） | `test/artifacts/package-e2e-r9-full/`、`evidence/http-e2e/results.json`、`evidence/round9/final*.log` |
| 真机·完整业务流程（round9 新跑） | ① `serdes_rx_flow_tb --stage all` → **全 stage ok**（ctle/term/top+网表+实例映射、layout、GDS 双路径、CDL 697B、AC+tran：gain 5.06dB@1MHz / peaking 0.35dB / swing 0.396V）；② `design_iterate_tb --stage all --with-lvs` → **ok=True / failures=[]**（二次改图→symbol 重生成→layout 2→4 shapes→AC+tran 参数读回一致→**LVS `status=correct`** ports 4/4、nets 4/4、inst 1/1、differences=[]） | `evidence/round9/flow-serdes-rx-r9.log`、`evidence/round9/flow-design-iterate-r9.log` |
| 真机·第二个完整项目（round9 新跑，多用户协同） | `adc_sar_flow_tb`（共享库 `/project/libs/adc_sar` + `tsmcN65`）→ **24/24 ok=True / 29.5s**：A 建 cmp/latch/sar_top 三 schematic（PDK 器件）→ symbol 端子比对（cmp 5/5、latch 3/3）→ sar_top 实例化 → layout 4 shapes → **GDS 导出到"还不存在"的目录**并命令面确认落盘 → **B（另一用户 vb-vbuser2）跨账号回读 A 的 schematic/layout → 往 sar_top 补 `XI_LATCH2` → A 回读看到 B 的实例** → B `check_and_save` → `spectre.check_license` | `evidence/round9/flow-adc-sar-r9.json` |
| 真机·多用户接力/并发（round9 新跑） | `multiuser_layout_handoff_tb`（两个**真实 OS 用户** vbuser1/vbuser2，同一 cellview）→ **12/12 PASS**：A 写 2 rect → A 读回 `shape_count=2`（M1/drawing 2）→ **B 看到同样 2** → B 追加 → **A 回读 `2→3`（跨用户跨 daemon 可见）** → 并发写结构化锁错误（`layout view … is locked by another session`，非超时/崩溃）→ A 仍可写 → **无 `*.cdslck` 残留** → 终值 `shape_count=5` | `evidence/round9/multiuser-layout-handoff-r9.json` |
| 真机·Monte Carlo 独立复验（round9 新跑，7.5 min） | `maestro_mc_e2e_tests`（P-070 关闭后的**测试侧独立复跑**，此前只有设计侧自测证据）→ **9/9 PASS**：17 项 run option 空基线 + 批量写回 + **非法值拒绝且不污染旧值** → 独立 run setup → **8/8 点 process MC 跑完（`MonteCarlo.0` status=done）→ `read_results` Yield Estimate 100%（8 passed/8 pts，0 error pts）** → 无统计 section 负控命中 **SPECTRE-16008**（不是超时/无报告）→ GUI session 关闭 | `evidence/round9/maestro-mc-r9.json` |
| 真机·PVT 扫描（round9 **新增 TB**，此前完全无覆盖） | 新 `test/live/packages/spectre_pvt_e2e_tests.py` → **7/7 PASS**（S11 真设计 `cmp_top` DC 网表，PDK CRN65GPNEW）：基线 tt/27℃/2.5V 14 节点 → **process ss 差 6 节点（max 0.488V @dc_out）/ ff 差 6（0.278V）**；**电压 2.25V 差 7 节点（0.25V）**；**温度 125℃ 差 6（0.0425V）/ -40℃ 差 6（0.00374V）** —— 逐节点值级判据（≥3 节点 >1e-6V 才算这档真的改变结果） | `evidence/round9/spectre-pvt-r9.json` |
| 真机·后仿对照（round9 复跑） | `s11_postsim_compare`（原理图网表 vs 版图提取网表，同测试台/同 PDK/同 `soft_bin`）→ **verdict=match**，4 个节点 max |ΔV| = **8.14e-05**（out 1.6887525→1.6886711） | `evidence/round9/s11-postsim-r9.json` |
| 真机·S11 端到端 LVS（round9 复跑） | `s11_inprocess_lvs_tb`（read→symbol→layout→GDS 导出→上传→**Calibre LVS**）→ **全段 pass，`lvs.rep` 判定 `CORRECT`**（`--run-dir` 必须给**远端绝对路径**，本轮踩过一次客户端相对路径的假红，已在 TB 里加校验） | `evidence/round9/s11-inprocess-lvs-r9.json` |
| 真机·多用户 SERDES RX 共建（round9 复跑） | `multiuser_serdes_rx_tb`（vbuser1 建 `rx_fe`/`clk_buf`/`rx_top` + symbol；**vbuser2 跨用户读并改单加 `XI_CLKBUF`**；vbuser1 回读看到）→ **17/17 PASS** | `evidence/round9/multiuser-serdes-rx-r9.json` |
| 真机·安静窗口复跑（补 B1） | `verilog_import_params` **rc=0**（IMP-08/10/11 全绿）、`maestro_view_param` **9/9 绿**（此前两条红都是并发窗口/夹具态，非产品） | `evidence/round9/gate5-verilog_import_params.log`、`evidence/round9/final2-maestro_view_param_e2e_tests.py.log` |

## 2. 五张核账

### 2.1 原子级（60 原子）
- **零引用 0 / 写不读回 0 / 已知误报 13（均有书面理由）/ 弱判据 0**
- 工具：`test/shared/runners/audit_atom_coverage.py`；报告：`test/reports/round9/atom-coverage-r9.md`

### 2.2 op × 参数（顶层字段）
- 矩阵 **811 行** = request 层 736（**CANDIDATE 496 / GAP 240**）+ 原子层 75（全 CANDIDATE）；`NO-OP-TB = 0`
- GAP 主体是**跨切字段**：`step_details` 77 + `log_max_bytes` 55 + `log_level` 54 = 186 条
- **本轮承接方式**（把"逐 op GAP"转成"合同覆盖"）：
  - 离线全量合同 `test/offline/unit/test_common_request_fields_contract.py` **84 项绿**：
    全 79 op 的 Request 必须含 `step_details`（默认 False）、`log_level`/`log_max_bytes` 必须成对且缺省 None、
    `basic.skill.execute` 必须有两者、**已删字段不得回归**（calibre power/ground、maestro include_results、Result.metadata）；
  - 真机行为 TB `test/live/packages/step_details_e2e_tests.py` **6/6 绿**（skill + 多步领域 op + 失败路径）；
  - 报告：`test/reports/round9/op-param-r9.md`、`op-param-classification.json`

### 2.3 嵌套键（顶层矩阵盲区，B 线新增）
- 90 个命令 op / **365 条 (op,字段)** → 审计发现 **28 条从未被触碰（20 键名）**：symbol pin 标签族、
  maestro test/corner 门控与模型/变量类型、schematic `place_wire` 间距键
- **L0 契约已补**：新增 `test/offline/unit/test_nested_command_keys_contract.py`（**21 用例 21/21 绿**，含负例），
  补点后重跑审计：**未被触碰字段 0 / 未覆盖枚举值 0**
- **真机逐键验证（round9 已落 9/21）**：新增 `test/live/packages/nested_keys_e2e_tests.py` → **5/5 PASS**，
  全部用 **DB 直读值级判据**：`place_pin`/`set_pin_properties` 的 `half_size`（bbox 0.1）、
  `label_font`/`label_height`/`label_justify`/`label_orient`/`label_pos`（`~>font/height/justify/orient/xy`）、
  `place_label(kind=drawing)` 的 `label_type="NLPLabel"`；`place_wire` 的 `x_spacing`/`y_spacing`
  **DB 无可读回属性 → 立卡 C10**（惰性参数候选）
- **maestro 11 键真机已落（round9 新增）**：`test/live/packages/maestro_nested_keys_e2e_tests.py` → **9/9 PASS**：
  `type_name`/`type_value`（set_var → `corners.nkm_c_model.variables.NKM_TYPEVAR == 2.25`）与
  `spec_name`（`set_spec` → `outputs[].spec={lt,1}`，`delete_spec(spec_name=…)` → `spec=null`）**值级**；
  `setup_corner` 的 corner 变量值级；`enabled`/`enable_tests`/`disable_tests`/`model_file`/`model_section`/
  `job_type`/`test_name` 为"接受性 + 无公开读回字段"（**如实标注 readback: none，不冒充值级**）；
  `sections`(load_corners) 只有**负路径**（无合法 CSV 样例）。
- 报告：`test/reports/round9/nested-key-coverage.md`（§7 补点状态 / §8 真机 9 键 / **§9 maestro 11 键**）

### 2.4 断言强度（5853 断言点，B 线）
- 分级：strong **4187** / medium **459** / weak **1207**；"仅弱断言"用例 128（live 31 / offline 97）
- 人工核实 **4 类真弱点**：
  - W-1 `skill_log_options_e2e_tests` LOG-04/05/06 只验"被接受" → **已修并真机 7/7 绿**；
  - W-2 `skillref_e2e_tests` 检索只验非空 → **已修 6/6 绿**；
  - W-3 `step_details_e2e_tests` 失败路径只验非空 → **已修 6/6 绿**（补末步形状）；
  - W-4 **已补并验证**：复核后真缺口只有 `stage_buf`（已补实例名+网络名读回，判据由命令表推导），
    `stage_ctle` 补显式实例集合断言；真机 `--stage buf` rc=0（6.75s，`buf_instances=["MN","MP"]`）、
    `--stage ctle` rc=0（16.95s，9 实例 + 10 网络 + `net_mismatches={}`）。`stage_top`/`stage_layout` 复核后本就有值级判据
- **日志 §5 三档口径（C 线复核）**：`[log truncated: …]` 的 **E2E 不可达**（SKILL 侧产不出 `\e` 行；`printf` 落 `\o` 归 info、`error()` 不进 CDS.log），
  但 **daemon 函数级离线判据完整**（`test_daemon_log_contract.py::test_truncate_when_even_errors_are_too_long`
  + `test_daemon_log_utf8_budget.py` 4 用例 + 预算扫描，round9 官方跑批均 PASS）→ 申报口径为"函数级有覆盖、E2E 不可达"，
  **不把函数级冒充 E2E**
- 报告：`test/reports/round9/weak-assertions.md` + `weak-assert-audit.json`

### 2.5 真机执行矩阵（谁负责跑）
- live TB 共 **53** 个、门禁 **24 套**（23:05 矩阵为 23 套；23:15 B 线把 `skill_log_options_e2e_tests.py`
  也接进门禁并删掉重复登记 → **24 套唯一项**，`run_all_http.py` 实测无重复）；"既不在门禁也无人引用"的 TB **0 个、今日无证据 0 个**：
  本轮接线 5 条 —— 测试侧 `step_details_e2e_tests`（6/6）、`gui_e2e_tests`（4/4）、
  `layout_geometry_classification_e2e_tests`（4/4）、`nested_keys_e2e_tests`（5/5），
  以及 root 侧 `maestro_mc_e2e_tests`、`maestro_nested_keys_e2e_tests`（9/9）
- 报告：`test/reports/round9/live-execution-gaps.md` + `live-execution-matrix.json`

### 2.6 代码覆盖率（分层口径，**不虚高**）
- **离线层（本轮实测）**：`coverage run --source=src -m pytest test/offline` →
  **89%**（18133 statements / 2017 miss；独立 data 文件 `round9/.coverage-r9-offline`，不动共享 `.coverage`）。
  低覆盖模块集中在真机侧：`transport.middle 85%` / `transport.tunnel 84%` / `register.flow 85%` / `register.probe 80%`。
- **全层（round9 官方 `run_main_coverage.ps1` 完整跑完，21:56 → 22:31）**：
  `strict` 口径 **18147 statements / 1473 miss（89.83%，显示 90%）· 6318 branches / 1015 miss（83.93%）· 57 文件**；
  `default` 口径 18133 / 1470 · 6312 / 854 → 90%（差值为 `# pragma: no cover` 行）。
  可复算元数据 `cov-main/run-meta.json`：`head=86cc169`、`dirty=true`、`worktree_diff_sha=351f5c0`、
  `python=3.12.10`、`coverage=7.16.0`；核对脚本 `test/reports/round9/verify_coverage_r9.py` 已落 `coverage-verify-r9.json`。
  **诚实标注**：汇总行是 `失败步骤: packages/maestro (direct) (rc=1)、packages/calibre (direct) (rc=1)` —— 正是本轮
  两张红钉 **C09（HISTORY-01）与 P-106（calibre runset 误杀）**；即该数字是"含 2 个已知失败步骤"的条件覆盖率，
  失败路径本身不计入"通过"。两张卡修复后需复跑一次作为最终签核数字。
- **分层对照**：离线层单跑 = 89%（18133 / 2017 miss）→ 全层把 miss 从 2017 降到 1470，**增量全部来自真机/半真机层**
  （`transport.middle` 83%、`transport.tunnel` 88%、`register.*` 等仍是最低模块）。
- round8 的 89.48 是**上一轮**数字（`coverage-main-strict-2333.json`，2026-09-28），本轮不再引用。

### 2.7 spec 条款（297 条，B 线代 A 线复核）
- 输入：`test/reports/round8/round8-spec覆盖矩阵.json`（297 条）+ 本轮 `round9/offline-windows-r9.xml`（2736 用例）
- 结果（**建议引用口径**）：**226 条本轮离线重验绿**（221 条 pytest JUnit + **5 条脚本 core TB：`run_core_multi.py` 6 TB / 30 用例全绿**）
  + **53 条 na（条款本身不要求证据）** + **18 条只引 semi/live → 全部已有本轮证据**（16 条对表通过；
  `路由#024` role_split 21:25 复跑 ok=5/5；`schematic#018` 由 21:09 的 19 套门禁 `screenshot_params` PASS 覆盖）
  + **引用文件不存在 0**（无假证据）
- **30 条需按本轮变更人工改判**（B 线已给建议，见 `spec-matrix-r9-b-review.md` §2）：
  PEX 本版不提供 4 条（含 `calibre#005` 交付/签核行）、P-092 删 power/ground 1 条、
  C1 响应契约 4 条、C2 log 选项 9 条、C4 `CommandResult` 具名字段 2 条（其余为相邻条款）
- 机器产物：`spec-matrix-r9-b.json` / `.md`、`spec-live-evidence-r9.json`；**未改 round8 覆盖矩阵原文件**

## 3. 本轮新发现（缺陷/红钉）

- **C06 红钉（新）**：`test/live/packages/skill_log_semantics_e2e_tests.py`
  - **C06-A 红**：`print("…")`（不带换行）**不落同一请求的 `CDSlog`**（实测空串）——行缓冲未 flush；
  - **C06-B 红**：该缓冲**串到后续请求**的 `CDSlog`（实测 `\o "C06_MARK_A"…`，并带出更早的残留 `C06_MARK_C`）；
  - C06-C（printf 带换行）绿 = 回归位；**C06-E（load 路径，printf+换行）新增并绿**（21:44 干净窗口）；
    C06-D（print 带换行）NOTE = 边界待 spec 定义。
  - **长行"消失"归因（并入 C06，不另立卡）**：≥500B 无换行单行的 `CDSlog` 为空、下一条请求串场带出；同长行+换行同请求 542B 正常
    （`round9/longline-probe.log`，stamp 214445）。
  - **round9 攻击扩展（22:29 实测，12 条用例：ENV + A–K）**：同一根因再加 6 种形态 →
    **F（同请求 3×print）全缺 / H（循环内 5×print）全缺 / I（600B 无换行长行）CDSlog 长度 0 /
    J（`print`(all)→`printf`(off)→`printf`(all)）归属错位：A 本条为空、内容被 off 请求的换行冲掉 /
    K（`load` 内 `print` 无换行）为空 → 与 A 同族全红**；对照绿位 **G（同请求 `print`+`printf` 换行）两标记同落**、
    C（printf 换行）、E（load+printf 换行）→ 证明**换行才是 CIW 缓冲触发点**。
    D（`print("X\n")`）实测仍延后带出（SKILL `print` 对字符串加引号并转义换行，故不触发 flush）。
    → **关闭条件 = 本 TB 全绿**（只绿 A 属修复不彻底）；证据 `round9/c06-attack-r9c.json`、卡内已同步
  - 证据：`test/artifacts/evidence/verify-fix-r9/c06-skill-log-semantics.json`、`round9/c06-semantics-r9b.json`；卡：`test/reports/bugs/C06-ciw-output-not-flushed.md`（已挂红钉）
- **C07（新，待决策）**：spec `12-calibre.md`（commit `6b1b855`，**仅改 spec**）已把 `calibre.export_cdl` 折进
  `calibre.lvs(source=…)`，实现未跟（`RunRequest` 不接 `source/emit_cdl/cds_lib`；旧 `calibre.export_cdl` 仍在注册表、
  被 4 条 flow TB 使用）。离线红钉 `test/offline/unit/test_calibre_lvs_source_contract.py`（2×strict xfail，现跑 `xx`）。
  卡：`test/reports/bugs/C07-calibre-lvs-source-fold-drift.md`
- **C09（新，待设计修）**：`maestro.write_history` 连续 rename（A→B 再 B→A）第二跳报
  `ASSEMBLER-2404 Cannot find a setup database entry for handle`（隔离复现 handle 118109；单独 `delete` 正常），
  `maestro_e2e_tests.HISTORY-01` 稳定红；证据 `round9/final3-maestro_e2e_tests.py.log`。
  卡：`test/reports/bugs/C09-maestro-write-history-rename-chain-handle-error.md`
- **P-106（新，待设计修，P2）**：`calibre.lvs(runset=…, blocking=true)` **误杀成功作业**——判活口径
  （`pgrep -f <run_dir>`）匹配不到 official-batch 的 calibre 进程 → 5.6s 即 `process_gone_without_report`，
  作业随后写出 `exit code 0` 且产物齐全；两次复现。证据 `round9/calibre-blocking-probe.log`、
  `round9/calibre-set01-falsefail-evidence.txt`。卡：`test/reports/bugs/P-106-calibre-blocking-false-fail.md`

## 4. 测试侧本轮改动

- 新增 TB：`test/live/packages/skill_log_semantics_e2e_tests.py`、`test/live/packages/step_details_e2e_tests.py`、
  `test/live/packages/nested_keys_e2e_tests.py`（5/5 绿）、
  `test/offline/unit/test_common_request_fields_contract.py`（84 绿）、
  `test/offline/unit/test_nested_command_keys_contract.py`（21 绿）
- 新增 TB（**round9 收尾追加**，全部已跑绿并接线进 `run_all_http.py` 门禁）：
  `test/live/packages/spectre_pvt_e2e_tests.py`（PVT 三维度 7/7）、
  `test/live/packages/maestro_nested_keys_e2e_tests.py`（maestro 11 键 9/9）、
  `test/live/packages/skill_log_semantics_e2e_tests.py`（C06 攻击 12 用例：A/F/H/I/J/K 红钉 + C/E/G 回归位）、
  门禁接线：`maestro_mc_e2e_tests.py`（此前**无人引用**，MC 7.5 min）、
  `spectre_pvt_e2e_tests.py`、`nested_keys_e2e_tests.py`、`maestro_nested_keys_e2e_tests.py`
- 修复 C3 残留（C1 成功后默认无 `steps`）：`layout_e2e_tests.py` GDS-02 两处补 `step_details=True` → 11/11 绿
- 修复 C4 残留（`CommandResult` 具名化后仍按位置下标读）：`test/semi/probes/_maestro_tb.py::shell` 兼容具名对象 →
  `maestro_env_probe` / `maestro_e2e_probe` 复跑 rc=0
- 修复**假红 TB**：`test/live/flows/multiuser_layout_handoff_tb.py` 旧版按 `("shape" ...)` **文本**计数，
  而 C1 后 `virtuoso.layout.read` 是**结构化字典** → 恒为 0，产生 3 条假红（A/B/final；其中
  `B-sees-A-shapes` 还因 0==0 变成**假绿**）。改为读 `shape_count`/`shapes`（拿不到才回退文本计数并判"判据不可用"），
  并把 `B-sees-A-shapes` 的判据从"两边相等"收紧为"**A 侧 ≥2 且两边相等**" → 复跑 **12/12 PASS**
- 修复**假红路径**：`test/live/flows/s11_inprocess_lvs_tb.py` 的 `--run-dir` 必须是**远端绝对路径**
  （客户端相对路径会让 Calibre 以 `RUN_ROOT` 为 cwd 找不到 GDS → `Failure to open input file …`，
  本轮真实踩到一次）→ 新增入参校验（非 `/` 开头直接给明确错误）+ docstring 用法纠错 + 注释头改为测试/root
- 强化（B 线）：LOG-04/05/06 值级断言、skillref 检索内容断言、step_details 失败步形状
- 接线（门禁现 **24 套**，唯一项）：B 线接 `step_details` / `layout_geometry_classification` / `gui`（原 3 条"无人引用"）
  + 23:15 补接 `skill_log_options`（C2/CDSlog 真机面，此前只在门禁外人工跑）；root 接 `nested_keys` /
  `maestro_nested_keys` / `spectre_pvt` / `maestro_mc`（MC 此前只有设计侧自测证据）

## 5. 缺陷台账（截至本报告）

- **2026-09-30 收尾后：未关闭 4** —— `C07`（calibre source fold，待设计二选一）、`C09`（maestro rename 链：
  **全量套件里仍复现**，见下）、`P-109`（maestro 7 键读回口径，待决策）、`P-114`（place_pin 可选属性静默 no-op，待设计修）。
  **本轮关闭 10 张**（每张都有可复跑证据）：`C06`（12/12 绿）、`P-086`（disposable TB `p086_ok=true`）、
  `P-106`（calibre 8/8）、`P-107`（spectre 6/6）、`P-108`（modes 9/9）、`P-110`（nested-keys 10/10）、
  `P-111`（测试侧误判，正例夹具已存在且值级复验 PASS）、`P-112`（spec 侧已回填，只剩 P-109）、
  `P-115`（verilog 4/4）、`C10`（改判据为几何对照 + spec 明确，6/6 绿）。
  **C09 仍失败**：设计侧 `2610668` 声称"真机回归通过"，但本轮跑**完整** `maestro_e2e_tests` 时
  `HISTORY-01` 第一步 `rename` 仍报 `Cannot find a setup database entry for handle 83816`
  （证据 `evidence/round9/maestro-r9h.txt`）—— 说明隔离场景通过、套件级路径未覆盖，需按完整套件复现。
- 历史记录（本轮首版）：**未关闭 6**：P-086（空响应窗口）、C06（CIW print 未 flush，本轮新红钉）、**C07**（见下）、**P-106**（见下）、
  **C09**（maestro rename 链，见下）、**C10**（`place_wire` 间距惰性参数，见下）
- 本轮关闭：P-070 / P-092 / P-093 / P-094 / P-098 / P-105 / C4（另 C1、C3 已关）
- **P-070 追加独立证据（测试侧）**：卡内原证据是设计侧自测（`verify-fix-r9/maestro-mc-p070-5.json`）；
  本轮由测试侧独立复跑 `maestro_mc_e2e_tests` → **9/9 PASS**（Yield 100% / 8 点；负控 SPECTRE-16008），
  `evidence/round9/maestro-mc-r9.json`。该 TB 此前**从未在测试侧执行过**（`live-execution-matrix` 的
  `no_evidence_today` 按其命名启发式也漏检），本轮已补齐。
- **新增 C07（待决策）**：spec `12-calibre.md`（commit `6b1b855`）已把 `calibre.export_cdl` 折进
  `calibre.lvs(source=…)`，**实现未跟**（`RunRequest` 不接 `source/emit_cdl/cds_lib`；旧 `calibre.export_cdl` 仍在注册表
  且被 4 条 flow TB 使用）→ 需设计二选一（实现 fold / 回退 spec），测试侧已有离线红钉
- **新增 P-106（待设计修，P2，本轮决定性复现）**：`calibre.lvs(runset=…, blocking=true)` **误杀成功作业**——
  `_status_snapshot` 用 `pgrep -f <run_dir>` 判活，而 official-batch 的 calibre 命令行只含 **runset** 路径、
  不含 run_dir → 首个 poll 即 `process_alive=False` → P-094 分类报 `failed process_gone_without_report`（探针 **5.6s** 即失败）；
  同期远端 `lvs.log` 随后写出 `exit code 0` 与 `inv2.lvs.report`（两次复现）。对照：直连参数路径（全新 run_dir）同环境 **18.9s → completed**。
  证据 `round9/calibre-blocking-probe.log`、`round9/calibre-set01-falsefail-evidence.txt`、`http-e2e/calibre_e2e_tests.py.log`；
  卡 `test/reports/bugs/P-106-calibre-blocking-false-fail.md`
- **新增 C09（待设计修）**：`maestro.write_history` **rename 链**（A→B 再 B→A）第二跳报
  `ASSEMBLER-2404 Cannot find a setup database entry for handle`（隔离复现 handle 118109；`delete` 正常）
  → `maestro_e2e_tests.HISTORY-01` 稳定红
- **新增 C10（待决策，P3）**：schematic `place_wire` 的 `x_spacing`/`y_spacing` **无可观察效果**——
  DB 直读 `("path" (nil) (nil) (0.05))`（width 落库、spacing 读回 nil），spec `5-schematic.md` 亦未记载这两键
  → 需设计二选一（补 spec 并给出可读回语义 / 删键）；TB `test/live/packages/nested_keys_e2e_tests.py::NK-04` 已钉住实测行为
- 已关闭记录 **92+ 条**；`make_bug_cards.py --check` 通过

## 6. 仍缺 / 待办（如实列出）

1. 嵌套键**真机逐键**验证：**20/21 键已落位** —— symbol/schematic 9 键（`nested_keys_e2e_tests.py` **5/5**，DB 直读值级）+
   maestro 11 键（`maestro_nested_keys_e2e_tests.py` **9/9**；其中 7 个无公开读回字段的键**如实标注 readback:none**、`sections` 仅负路径）；
   仅 `place_wire` 的 `x_spacing`/`y_spacing` 属 **C10**（静默无效参数）待设计裁决；
2. §5 第 3 档（`[log truncated: …]`）**函数级离线已覆盖、仅 E2E 不可达**：daemon `filter_delta()` 的截断分支由
   `test_daemon_log_contract.py::test_truncate_when_even_errors_are_too_long` +
   `test_daemon_log_utf8_budget.py`（多例，round9 官方离线 PASS）钉住；E2E 侧因 SKILL 产不出 `\e` 行不可达——
   如评审要求 E2E，需 daemon/IL 侧提供受控夹具（`log-semantics-r9.md §3`，勿写成"无覆盖"）；
3. `calibre.drc`/`calibre.lvs` 的 `fmt`/`lvs_run_dir` 是**惰性字段**（只校验+回填 meta，读取点在不可用的 PEX 分支）
   → 与 P-092 同族，需设计二选一（声明保留位 / 删字段）；
4. **已立卡待设计修**：P-106（calibre runset 误杀）、C09（maestro rename 链）、C07（calibre source fold 漂移）、
   C06（CIW print 未 flush）；
5. 证据命名不统一（3 条 TB 证据用连字符命名 → 自动核对误报"今日无证据"）→ 统一带 TB 名；
6. spec 条款矩阵"变更后失效条款"复核（B 线已给 30 条候选与建议改判）+ `print` 是否应写入 CDS.log 的边界（C06-D）待 spec 裁定。
7. **全层覆盖率**：已按官方 runner 跑完并回填 §2.6（89.83% strict，含 P-106/C09 两个失败步骤）；
   **待两卡修复后复跑一次**取"全绿条件"数字作为签核口径（届时 `verify_coverage_r9.py` 应无失败步骤）。
8. 卡关闭后复跑红钉：`test/shared/runners/run_redpins.py`（见 HOLD / UNEXPECTED-GREEN / BROKEN 三类判定）。
9. **按《全量测试准则》的缺口评估已出**：`test/reports/internal/按准则的TB缺口评估-round9.md`
   （三条铁律均判"不达标"，含 30 条 spec 待改判、7 类参数缺口、表 C 缺实体、124 例弱断言清单与 P0–P2 修复顺序）；
   下一轮以该清单为准收口。
10. **2026-09-30 TB 侧修复（只跑增量，未跑全量）**：
   - 弱断言分诊：`test/reports/round9/weak-assertions-live-triage-r9.md`（live 27 例 → **7 条真弱已加强**、其余误报/已足够；
     每条加强都用 `--transport http` 单独复跑绿：skillref 6/6、symbol 9/9、veriloga 7/7、cellview 5/5、schematic 10/10、
     spectre 6/6、spectre_params 5/5）；
   - **假绿修复**：`spectre_e2e_tests.RUN-04` 原来在入参校验就失败（`parse='none' requires keep_run_dir=true`），
     坏网表从未跑；现断言 run.ok=false + execute 步 + rc!=0 + `spectre completes with`；
   - **参数缺口关闭**：新增 `test/live/packages/spectre_modes_e2e_tests.py`（`mode` **8 个取值真机全跑**，
     cx/ax/mx/lx/vx 全绿：命令行含 `+preset=<mode> +mt` / status=success / rc=0 / DC 3 节点）并接进门禁（门禁 25 套）；
   - **新卡**：P-107（失败 run 被报成"下载失败"，spec §5.4 分类冲突）、P-108（`mode="x"` 被 Spectre 24.1 拒绝 SPECTRE-129）；
   - `spectre_params` 证据目录去掉写死的 `round8`（新增 `--out-dir`）。
11. **2026-09-30 续补（第三批，只跑增量）**：
12. **2026-09-30 非业务面补测（"这种操作也要有 TB"）**：
   - **新真机 TB `test/live/registration/control_plane_tb.py` → 7/7 绿**：控制面只读面
     （`/api/process/status`、`/api/users`、`/api/user/<u>`（且**不回显 token**）、`/api/config`、`/api/process/reload`）、
     无 admin token 一律 401、管理页 HTML + `/help` **15 个端点自描述完整性**、
     `GET /api/register/<user>` 的 404 语义、`HEAD/PATCH → 405 + Allow: GET, POST, PUT, DELETE`、
     未知路径 404；以及 **bug 报告通道**：正例（200 + 落盘 `log/bug_reports/<id>.json` + 凭据打码
     `token/authorization → ***` + `raw_body` 保留 marker + `status/logs` 有界）与负例
     （无/无效 token → 400 且**零落盘**）—— 证据 `evidence/round9/control-plane-tb.json`。
     不覆盖的写通道（`user update`/`DELETE user`/`PUT config`）在 TB 里写明理由（会改常驻注册表），
     由离线单测 + 注册六步 TB 承担。
   - **新离线 TB `test/offline/unit/test_packaging_entrypoints.py` → 4/4 绿**：`pyproject.toml`
     console_scripts 目标可导入且可调用 + 三个 `python -m` 入口（`register.server`/`server.supervisor`/
     `server.api_server`）的 `--help` 参数契约。
   - **接线 3 个此前"无人引用"的半真机探针**（`run_semi_probes.py`）：日志轮转（日志 spec §8.5）、
     layout region/depth（P-082/P-085）、GDS 导出后同会话 SKILL（P-075）→ **3/3 绿**
     （证据 `evidence/round9/semi-wired3.json`）；未接线探针 14 → 11（余下为一次性复现/调查类，待归档或接线）。
   - **撤回一条有毒用例**：曾把"投递超时→dirty"加到常驻门禁 `infra_e2e_tests`，实测会把**共享实例**置忙
     （直连 daemon 报 `SKILL channel busy`，需重启 CIW）→ 已撤除并在原地写明"该语义只放 disposable CIW"，
     随后按 Runbook §10.10 恢复 vblog（CIW + 8124 重启），常驻自检回到 **8/8**、`infra_e2e_tests` **7/7**。
   - `schematic_e2e_tests` **11/11**：`PIN-OPT` 用例——`sig_type` 值级读回 `numBits/sigType`
     （关闭表 C 两个字段）+ 非法 `sig_type` 枚举拒绝 + **P-114 红钉**（`power_sens`/`ground_sens`/四属性组合
     报 ok 但零对象；`off_sheet` 单用 `nth` 报错）；P-113 已随设计 `0e14c8b` 关闭（CLOSED_RECENT）。
   - `cellview_e2e_tests` **6/6**：新增 `NEG2` 用例，给 copy/rename 与 category 成员操作补 **12 条非法档**
     （`destinationExists`/`copyFailed`/`libraryExists`/`cellNotFound`/`viewNotFound`/`cellAlreadyInCategory`/
     `cellNotInCategory`/`destinationCategoryExists`），并断言目标对象不重复、源对象仍在。
   - `symbol_e2e_tests` **9/9**：`CHECK-01` 补"缺失 view 必须结构化失败且点名 view"。
   - `verilog_e2e_tests` **4/4**：新增 **P-115 红钉**——`write` 缺 `ensure_view` 时对不存在的 view
     **静默创建半成品**（只落 `verilog.v`、无 `master.tag`）；非法 `view_type` **不被校验**。
   - 参数矩阵口径：**"只在离线契约出现、真机从未传值"的参数 = 0**（576 行有 semi/live 参数命中）。
   - **skip 政策（用户 2026-09-30 裁定）**：Calibre 侧如遇环境限制（license/工具/夹具不可用）→
     **直接 skip + 写明"环境限制：<原因>"**，不算缺陷、也不算覆盖；skip 清单在报告单列。已写入准则 §3.6。

## 7. 交叉评审索引（subagent，objective 要求）

> 全部评审件都在 `test/reports/round9/`；每件都只引用可复跑的现成证据。

| 评审件 | 评审对象 | 结论（一句话） |
|---|---|---|
| `review-of-round9-report.md` | 主报告（20:59 版） | 3 处过期 + 1 处口径风险 + 4 条残留建议；已并入 §1/§3/§6（本版复核后无未处置项） |
| `spec-matrix-r9-b-review.md` | spec 297 条旧结论 | 226 条本轮离线重验绿 / 53 na / 18 只引 semi+live（16 有本轮证据；`role_split` 已补 5/5、`screenshot_params` 在门禁内）；另给 30 条变更改判候选 |
| `weak-assertions.md`（+ `weak-assert-audit.json`） | 5853 断言点 | 4 类真弱点 W-1..W-4 **全部关闭**；假阳性类别已注明，offline 97 例低风险不再改写 |
| `ledger-integrity-r9.md` | 台账/卡片/红钉机械状态 | 生成器↔卡片一致、红钉可复跑；L1–L5 文案问题已修（C07/C09/P-106 行、链接 7/7、`--check` 9/0/0） |
| `semi-r9-failure-triage.md` | 半真机 3 红 | 2×C4 TB 修复后复跑 **rc=0**；1×并发伪红（solo 36/36+36/36）——全部消解，非产品缺陷 |
| `offline-flaky-r9.md`（+ `offline-single-session-r9d.xml`） | 离线单会话稳定性 | 1 次 flaky 定案为测试侧顺序依赖；r9b/r9c/r9d 复跑 **2736/0/0/10skip** 未再现；建议该 class 用独立 work-root |
| `gate-r9-live-triage.md` | 门禁 5 红 | 逐条分诊：2 TB 侧 C4（已修复复验绿）、1 覆盖率/环境（P-106 真红）、1 C09 真红、1 并发伪红——与 §5 卡片一一对应 |
| `coverage-honesty-notes.md` + `coverage-verify-r9.json` | 覆盖率口径 | strict 89.83%/83.93% + `head=86cc169 dirty=true diff=351f5c03`；如实标注两个失败步骤（C09/P-106），待修后复跑签核 |

> 另：C06 红钉的独立攻击扩展（12 例 A–K，`round9/c06-attack-r9c.json` + `evidence/redpins/`）与
> 半真机/门禁的复跑证据共同构成"缺陷被攻击"的第三方视角，均由 `run_redpins.py` 可复跑。

## 8. 增量补测（2026-09-30 晚，本轮收尾）

> 口径：设计侧本轮修完一批后，测试侧按"先修 TB、只跑增量"补断言 + 复验；下面是**当次实测**结果。

### 8.1 本轮关闭（4 条，全部有真机证据）

| 卡片 | 复验结论 | 证据 |
|---|---|---|
| **C07** spec 把 `export_cdl` 折进 `lvs(source=…)` | `calibre_e2e_tests` **12/12 绿**：`LVS-02 source.kind=schematic`（auCdl 在 run dir 内现产，含 `.SUBCKT`+器件行）、`LVS-03 source.kind=cdl` 复用内产 CDL、**新增 `LVS-CTLE`（spec §8 的 `ctle.gds`+`ctle.cdl`，强结论 + `svdb/*.phdb` 目录结构）**、`PARAM-01`/`SET-01` 官方批处理、`LVS-SRC-XOR`（`source` 与旧 `cdl=` 互斥，请求层拒绝）、`EXPORT-01/02`（`local_dir` 值级 + sha256 + 零落盘）。LVS-01（旧 CDL）仍只到 `not_compared` → 如实 WARN（P-069 家族残留） | `evidence/round9/calibre-c07-r11c.txt` |
| **P-109** maestro 7 个写键 readback:none | `maestro_nested_keys_e2e_tests` **10/10 绿**：NKM-02/03/05 按**值级**读回 `enabled`/`enabled_tests`/`disabled_tests`/`models[].{file,section}`/`job_policy.simulation`（maxJobs=2） | `evidence/round9/maestro-nested-keys-p109-verify.json` |
| **P-114** `place_pin` 可选属性静默 no-op | `schematic_e2e_tests` **11/11 绿**：power/ground sens 引用已存在 terminal → 建出 `PSENS`（connectivity 值级）；引用不存在 terminal → 结构化失败；`off_sheet` 无可用 master → 结构化拒绝（不再 `nth`、不再静默 no-op） | `evidence/round9/schematic-p114-verify.json` |
| **P-086·D** 投递超时把实例永久置忙 | 新增回归钉 `delivered_timeout_recovery_tb` **5/5 绿**（独立 disposable destb2/64601）：超时快速失败 → **不重启 CIW** → 自动 probe idle 恢复 → 再等一拍仍可用；修复 `97baf13` | `evidence/round9/delivered-timeout-recovery.json` |
| **C11** 个人自助权限（个人 token + enhanced_token） | 后端 v42 实现后，测试侧在**一次性实例**上独立复验同一权限矩阵：`control_plane_write_tb` **12/12 绿**（CPW-05..08：self 读 200 / 他人 403 / self 视图不泄露 `key/key_dir` / 普通字段值级落盘 / 只读需 enhanced[无→403、他人 token→401、admin→200] / 保密字段 403 / 个人 DELETE 401 / 被拒改动零落盘） | `evidence/round9/control-plane-write-tb-c11.json` |
| **P-116** symbol `term_order` 口径 | spec 定稿 `b4036d0`（term_order = `cv~>termOrder` legacy raw，可能空/陈旧；pin_order/port_order 才是权威）；TB 从红钉降级为「pin==port 强断言 + term 存在且为 list」：`symbol_e2e_tests` **10/10 绿**（三键真实值入证据） | `evidence/round9/symbol-p116-fixed.txt` |

### 8.2 本轮新增 TB / 补断言

| 对象 | 新增内容 | 结果 |
|---|---|---|
| 控制面**写通道** | `test/live/registration/control_plane_write_tb.py`（一次性实例 + 自带 fixture 用户）：update runtime/roles 值级读回、显式指纹迁移、未知 endpoint **拒绝且注册表逐字节零改动**、PUT config GET+落盘一致、delete 值级、404/400/401 负例 | **8/8 绿**，`evidence/round9/control-plane-write-tb.json` |
| calibre export（表 C 缺口） | `EXPORT-01`（`local_dir` 值级 + `downloaded[].bytes` + summary 文件 **sha256 == 远端** + netlist `svdb/` 落地）/`EXPORT-02`（未知 item 请求层拒绝且**零落盘**） | 随 12/12 绿 |
| calibre spec §8 LVS 行 | `LVS-CTLE`（此前 TB 只跑 inv2，spec 验收行要的是 ctle） | 绿（`correct`/`incorrect` 口径 + phdb 结构） |
| maestro 步骤明细（表 C） | `CONFIG-01` 增 `step_details=true` + **`options` 步的 `env`/`sim` 与公开 `tests.*.env_options/sim_options` 逐值一致** | 绿（`maestro-c09-verify2.txt`） |
| symbol orders（P-116） | `read(focus=orders)` 三键值级断言：`pin_order==port_order` 强断言；`term_order` 单独立红钉（spec 3-symbol.md:200 与真机不符） | 9 绿 + 1 红钉，`evidence/round9/symbol-p116.txt` |
| log 选项非法档（§8.7） | `skill_log_options_e2e_tests.LOG-08`：`log_level=loud/OFF`、`log_max_bytes=many/0/-5` → 端到端结构化拒绝 + **零副作用**（标记不得落 CDSlog） | 见 §8.4 |

### 8.3 未关闭（3 条）

| 卡片 | 现状 | 去向 |
|---|---|---|
| **C09** maestro rename 链 | 完整套件复跑：**前 22 条全 PASS**，`HISTORY-01` 仍报 `Cannot find a setup database entry for handle 162851`（前两轮 83816/118109）→ 隔离路径绿、整链红；复跑期间还把 CIW 挂成 `Library Select` 模态（按 Runbook §10.10 重启恢复） | 退回设计侧：按**完整套件**复现（套件内前序用例留下的会话状态是分歧点）；证据 `evidence/round9/maestro-c09-verify2.txt` |
| **P-117**（新立）`calibre.export.items` 的 `pdb_dir` | spec §4.5 列了 `pdb_dir`（且 §4.4 写明既有 PEX 产物可经 `export` 读取），实现未提供 → `400 unknown export item: pdb_dir`；`all_small`/`summary`/`results_db`/`netlist`/`log` 均可用 | spec 侧二选一（删条目 / 实现补上）；TB `EXPORT-04 按现状钉住`（不阻塞门禁） |
| **P-118**（新立）maestro netlisting job policy | `set_job_policy(job_type="netlisting")` 在**目标 test 没有 netlisting policy** 时 **ok=true 但零效果**（`read_config.job_policy.netlisting` 恒 `null`；同 cell 的 simulation 分支可正常落盘）——静默 no-op | 设计侧修（缺 policy 时应创建或结构化失败）；红钉 `NKM-09` 在 `maestro_nested_keys_e2e_tests` 最后一条 |

> 红钉 runner 现在含 2 条：`python test/shared/runners/run_redpins.py`（c09 / p118）。

### 8.4 证据与待跑

* `skill_log_options_e2e_tests`（含新 LOG-08）**9/9 绿**（`evidence/round9/skill-log-options-log08.txt`）；
  红钉 runner 已更新清单为 C09 + P-116（`python test/shared/runners/run_redpins.py`）。
* 文件纪律修复：`delivered_timeout_recovery_tb` 不再把 fixture 用户写进常驻 `log-vblog` 注册表（历史泄漏已清理），
  改用自带 work-dir；`calibre_e2e_tests` 的本地临时文件从常驻 env 目录迁到 `test/artifacts/tmp/calibre-e2e-<stamp>/`。
