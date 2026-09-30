# 按《全量测试准则 v0.3》的 TB 缺口评估（round9 收尾后）

> 执行：测试/root ｜ 2026-09-30 ｜ 判据源：`test/reports/internal/全量测试准则-内部.md`（v0.3）
> 数据：本轮**重跑**的审计工具（命令与产物见文末），不是引用旧数字
> 一句话结论：**三条铁律现在都不达标**，但每条都有可执行的缺口清单；最大的结构性缺口是
> **表 C（输出字段表）目前根本没有实体**——这正是 C06 漏检的根因。

## 0b. 修复进展（2026-09-30，TB 侧先行；按用户口径"先修 TB、只跑增量"）

| 项 | 状态 | 证据 |
|---|---|---|
| live 侧"仅弱断言"27 例逐条分诊 | ✅ 完成：**7 条真弱已加强**（含 1 条**假绿**修复），其余为误报/已足够 | `test/reports/round9/weak-assertions-live-triage-r9.md` |
| `spectre_e2e_tests.RUN-04` 假绿 | ✅ 修复：原请求在入参校验就失败（`parse='none' requires keep_run_dir=true`），坏网表从未跑；现断言 run.ok=false + execute 步 + rc!=0 + spectre 收尾统计 | `evidence/round9/spectre-r9d.txt` |
| 参数缺口 #1（`spectre.run.mode` 5 个取值只离线） | ✅ **关闭**：新增 `test/live/packages/spectre_modes_e2e_tests.py`，8 个取值真机全跑，**cx/ax/mx/lx/vx 全绿**（命令行含 `+preset=<mode> +mt`、status=success、rc=0、DC 数据 3 节点），并已接进门禁 | `evidence/round9/spectre-modes-r9.json` |
| 参数缺口附带发现 | ✅ 新立卡 **P-107**（失败 run 被报成"下载失败"、spec §5.4 分类冲突）、**P-108**（`mode="x"` 被 Spectre 24.1 拒绝 SPECTRE-129，spec 映射表需改） | `test/reports/bugs/P-10{7,8}-*.md` |
| 7 条加强用例的增量复跑 | ✅ 全绿：skillref 6/6、symbol 9/9、veriloga 7/7、cellview 5/5、schematic 10/10、spectre 6/6、spectre_params 5/5 | `evidence/round9/*-r9c.txt`、`evidence/round9/spectre-params/` |
| 表 C 生成器（P0） | ✅ **已做第一版**：`test/shared/runners/build_output_field_matrix.py` → 79 op / 1019 字段行（asserted 961 / read_only 28 / absent 30），并用"本轮证据里真出现过该字段"把候选收敛为 **11 op / 14 字段** | `test/reports/round9/output-field-matrix.{json,md}`、`output-field-triage-r9.md` |
| 表 C 真缺口处置 | ✅ 已补 4 处：`spectre.run.succeeded/failed`、`cellview.lib.get.technology_library`、`maestro.read_history` 8 个字段（含 points/tests/corners done==total、lock_flag、overwrite_target、results_dir） | `evidence/round9/spectre-modes-r9.json`、`cellview-r9d.txt`、`maestro-mc-r9b.json` |
| 表 C 剩余候选 | ⏳ 收敛到 **7 op / 13 字段**：`calibre.export.local_dir`、`calibre.export_cdl.netlist_name`（疑内部键）、`spectre.measure.passed`（**已确认误报**）、`maestro.read_config.sim`、`maestro.read_history.*`（**已补，工具未识别 lambda 形式**）、`schematic.read.numBits/sigType`（**被 P-113 阻塞**）、`symbol.read.term_order`（语义待确认） | `output-field-triage-r9.md` §1/§5 |
| 需协调项已立卡 | ✅ P-107（失败归因/分类）、P-108（mode=x）、P-109（maestro 7 键无读回面）、P-110（load_corners 缺合法 CSV 样例）、P-111（set_parameter 缺层次参数样例）、P-112（30 条 spec 待改判）、**P-113（place_pin 可选属性参数真机必失败）** | `test/reports/bugs/`（当前 13 张未关闭） |
| 表 C 第二批补断言（本轮） | ✅ `spectre.read_results` 的 analysis/output_dir/source/analyses/files/data；`maestro.export` 的 kind/remote_path；`maestro.read_history` 8 字段（MC TB）；`spectre.run.succeeded/failed`；`cellview.lib.get.technology_library` | `evidence/round9/spectre-r9e.txt`、`maestro-r9f.txt`、`maestro-mc-r9b.json`、`spectre-modes-r9.json`、`cellview-r9d.txt` |
| 表 B 参数"只在离线出现"收敛 | ✅ **14 → 4 → 0**（新矩阵口径 576 行有 semi/live 命中）：第一批补 `place_label/set_label_properties/place_note/set_note_properties/set_wire_properties` 共 10 个；第二批处置 `place_pin` 四档（`sig_type` **P-113 已修并值级验收**；`off_sheet`/`power_sens`/`ground_sens` → **P-114 红钉**） | `evidence/round9/schematic-r9k/l.txt`（11/11 PASS）、`output-field-triage-r9.md` §4b |
| P-113 | ✅ **已关闭**（设计 `0e14c8b`；测试侧验收：sig_type 写入成功 + `numBits/sigType` 值级 + 非法值枚举拒绝） | `schematic-r9l.txt`、CLOSED_RECENT |
| P-114（新） | ⏳ 待设计修：`power_sens`/`ground_sens`/四属性组合**报 ok 但零对象**（静默 no-op）、`off_sheet` 单用 `nth` 硬报错 | `schematic-place-pin-residual-p114.txt`、卡 `P-114-*` |
| 环境事件 | ✅ vblog CIW 降级（`pin not found` / `load … line 14`）→ 按 Runbook §10.6 重启（按 cwd 杀 + 清锁 + xvfb-run 起）→ `schematic_e2e_tests` 复绿 | `环境Runbook-内部.md` §10.6 |
| 弱断言 offline 97 例 | ⏳ 只登记不改写（低风险，留到与表 C 一起过） | `weak-assertions-live-triage-r9.md` §3 |
| 用例档位（最简/日常/边界/非法） | ⏳ 首版审计已出（静态近似）：79 op 中 **12 个只有一条 semi/live 用例**、**20 个无"非法档"线索**（需人工复核） | `case-profile-audit-r9.md` |
| 用例档位 · 处置（2026-09-30 续补） | ✅ 单例 op **12 → 2**（余 2 个复核为误报）；非法档线索 20 个**逐条复核完**：新增 `basic.*` 非法档 4 条（infra 7/7）、cellview create 族 3 条、schematic.check_and_save 缺失 view；calibre 5 个 op 按**环境限制 → skip**（用户裁定） | `case-profile-audit-r9.md` §2b/§3b、`infra-r9d.txt`、`cellview-r9j.txt`、`schematic-r9m.txt` |
| 新卡 | P-115（`verilog.write` 静默建半成品 view + `view_type` 不校验，红钉已在 TB） | `test/reports/bugs/P-115-*.md` |

## 0c. 增量补测（2026-09-30 晚）——上述缺口的处置

| 缺口 | 处置 | 证据 |
|---|---|---|
| 表 C `calibre.export.local_dir` | ✅ **已补**：`EXPORT-01` 值级（`local_dir` 按请求生效 + `downloaded[].bytes` + summary 文件 **sha256 == 远端** + netlist `svdb/` 落地）；`EXPORT-02` 未知 item **请求层拒绝且零落盘** | `evidence/round9/calibre-c07-r11c.txt` |
| 表 C `calibre.export_cdl.netlist_name` | ✅ **行移除**：独立 op `calibre.export_cdl` 已按 spec 折进 `calibre.lvs(source=…)`（C07，设计 `62575c6`） | 同上（12/12） |
| 表 C `maestro.read_config.sim` | ✅ **已补**：`CONFIG-01` 带 `step_details=true`，断言 `options` 步的 `env`/`sim` 与公开 `tests.*.env_options/sim_options` **逐值一致** | `evidence/round9/maestro-c09-verify2.txt` |
| 表 C `symbol.read.term_order` | ⚠ **立卡 P-116**：spec `3-symbol.md:200` 说 `schEditPinOrder` 后 `pin_order`/`port_order`/`term_order` 一致；真机 term_order 未同步（空/陈旧）→ 红钉放套件最后一条 | `evidence/round9/symbol-p116.txt`、`reports/bugs/P-116-*.md` |
| 参数缺口：`log_level` / `log_max_bytes` 非法档（原只有 L0） | ✅ **已补**：`LOG-08` 5 个非法值经业务面结构化拒绝 + **零副作用**验证 | `evidence/round9/skill-log-options-log08.txt`（9/9 绿） |
| spec §8 calibre LVS 验收行（`ctle.gds`+`ctle.cdl`，此前 TB 只跑 inv2） | ✅ **已补**：`LVS-CTLE`（强结论 + `svdb/*.phdb` 目录结构 + `db/` 子目录） | `evidence/round9/calibre-c07-r11c.txt` |
| T3 未解析调用点 101/102 | ✅ **人工复核完**：A 段 19 条**全部**是解析器局限（测试私有 op `tb.*`/`test.*`、辅助函数形参、循环变量），无真缺口；B 段 80 条为管道行 | `test/artifacts/tmp/a_list.txt`（逐条上下文） |
| 日志 §8.7 非法值/`unavailable` | ✅ 端到端（LOG-08）；§8.4 第 3 档（error 增量仍超限 → 截断说明行）**E2E 不可达**（SKILL 产不出 `\e` 前缀行），保持 L0 覆盖并在 TB 注释里写明 | `skill_log_options_e2e_tests.py` 头注 |
| 控制面写通道（非业务通道也要成体系 TB） | ✅ 新增 `control_plane_write_tb.py` **8/8**（update/config/delete 值级 + 未知 endpoint 零落盘 + 负例） | `evidence/round9/control-plane-write-tb.json` |
| P-086 家族：投递超时永久置忙 | ✅ 修复 `97baf13` + 新增回归钉 **5/5 绿**（disposable，不重启 CIW 自恢复） | `evidence/round9/delivered-timeout-recovery.json` |

## 0. 达标判定摘要

| 铁律 | 判定 | 关键数字 | 主要缺口 |
|---|---|---|---|
| ① 从原始 spec 出发做覆盖检查 | ❌ 不达标 | 297 条款：226 绿 / 53 na / 18 semi+live / **30 待改判**；**日志 spec §8 未成表** | 30 条没落笔；§8 无逐条对表件 |
| ② 每个操作每个参数都覆盖且实际执行过 | ❌ 不达标 | op×参数矩阵 811 行（CANDIDATE 571 / 非候选 240，`real_tb_gaps=0`）+ 嵌套键 90 op/105 字段（未触碰 0） | **7 类确凿缺口**（见 §2），其中 5 类只有 L0/负路径 |
| ③ 每个操作的每个输出值都逐项比对 | ❌ 不达标 | 断言点 5930：strong 4212 / medium 495 / **weak 1223**；**仅弱断言用例 124**（live 27 / offline 97） | 表 C 无实体；124 例未改写；readback:none 清单未裁决 |

## 1. 铁律① 缺口：spec 条款

### 1.1 现状

* 条款总数 **297**；本轮离线重验绿 **226**（221 pytest + 5 core TB 30 用例）+ **53 na**（条款本身不要求证据）+ **18** 只引 semi/live（16 对表通过、`role_split` 5/5 已补、`screenshot_params` 在门禁内）；
* **引用证据不存在 = 0**（`verify_spec_matrix_evidence` 口径）；
* **30 条"变更后待改判"未落笔**：PEX 本版不提供 4 条、P-092 删 power/ground 1 条、C1 响应契约 4 条、
  C2 log 选项 9 条、C4 `CommandResult` 具名字段 2 条，其余为相邻条款（清单见 `round9/spec-matrix-r9-b-review.md §2`）。

### 1.2 缺口

1. **30 条待改判**没有裁定人与去向 → 按准则 §2 表 A，这些行现在状态是"未知"，等同未覆盖；
2. **日志 spec（`6-日志返回设计标准.md`）§8 八条验收标准没有逐条落表**（原派 subagent，其 402 中断）。我已做了一次人工对表，结论如下（**待落成正式表 A 行**）：

| 条款 | 现有证据层级 | 判定 |
|---|---|---|
| §8.1 `off` 零 flush/fileLength/文件读 | L0（`test_log_no_fetch.py` 静态 + `test_log_off.py` 行为）+ S1（`log_matrix_real_tb.case_off_source_cut`） | ✅ 有，缺 S2 |
| §8.2 不得注入 VB-BEGIN/VB-END | L0（`test_daemon_log_contract.py`）+ S1（`case_no_bridge_injection`） | ✅ 有，缺 S2 |
| §8.3 `log` 只含本次增量 | S1（`case_increment_bytes`）+ S2（C2 LOG-01..06、C06 TB） | ⚠ **有红钉**：C06 证 `print` 内容不落本请求增量 |
| §8.4 降级/截断说明行、区间照常推进 | 第 2 档：L0 + S2（`skill_log_options` LOG-04b/04d）；第 3 档（truncate）：**仅 L0** | ⚠ 第 3 档 E2E 不可达（SKILL 产不出 `\e` 行），需受控夹具或降级声明 |
| §8.5 文件轮转/清空 → start 归零 | L0（`daemon_log_protocol_tb.case_rotation_truncation` + `test_daemon_log_contract.test_rotated_file_reads_from_zero`） | ⚠ 仅 L0（无 S1/S2） |
| §8.6 `off` → `log=""` | S2（LOG-02） | ✅ |
| §8.7 非法值拒绝 / `unavailable` warning / 半个 UTF-8 | L0（`test_daemon_runtime_contracts` NAK+warning、`test_daemon_log_utf8_budget` 4 例） | ⚠ 仅 L0 |
| §6.3 第二帧 `US` 定界 / 超时降级 | L0（`test_daemon_runtime_contracts` `_parse_meta` 正负例 + 第二帧超时用例） | ⚠ 仅 L0 |

## 2. 铁律② 缺口：op × 参数

### 2.1 现状（本轮重跑）

* 矩阵 **811 行**：CANDIDATE **571** / 非候选 **240**；`NO-OP-TB = 0`；分类器 `real_tb_gaps = 0`；
* 非候选分布：`CONTRACT_LOG_OPTIONS 109`、`CONTRACT_STEP_DETAILS 77`、`CONTRACT_TIMEOUT 29`、
  `NA_PEX_UNSUPPORTED 17`、`INERT_PEX_ONLY_FIELD 4`、`NA_KIND_LVS_ONLY 3`、`NA_KIND_LEGACY_CDL 1`；
* 嵌套键：**90 op / 105 字段，未被触碰 0、未覆盖枚举值 0**（但口径提醒：该脚本只证"键名被写过"，不证"写后断言了效果"）；
* 未解析调用点 **101**（静态解析器局限，需人工抽样）。

### 2.2 确凿缺口（按准则必须补）

| # | 参数 | 现状 | 补法 | 状态 |
|---|---|---|---|---|
| 1 | `spectre.run.mode` 的 `cx/ax/mx/lx/vx` | **只有 L0 拼装断言**（全 test 树仅 1 处引用），S1/S2 从未跑过 | 用一个极简 netlist（RC/DC）在真机各跑一次；跑不动（许可）则立卡写明 | **缺口** |
| 2 | `place_wire.x_spacing` / `y_spacing` | 真机写后 DB 无可读回属性（`("path" (nil) (nil) (0.05))`） | 设计二选一：补可观察语义 + spec / 删键 | **C10 待裁** |
| 3 | maestro `enabled` / `enable_tests` / `disable_tests` / `model_file` / `model_section` / `job_type` / `test_name` | 仅"接受性"（公开 read 面无字段，记 `readback:none`） | 设计二选一：补读回面 / spec 写明"只写不读" | **待裁** |
| 4 | `load_corners.sections` | 只有负路径（本地文件缺失必须失败） | 要一份**合法 ADE corners CSV 样例**（设计给）→ 正例断言 corner 列表变化 | **缺口（依赖设计）** |
| 5 | `set_parameter` 正例 | 只覆盖了名称契约（非五段路径拒绝） | 要一个**真实层次参数名**（`Lib/Cell/View/Inst/Prop`）→ 正例 + 值级读回 | **缺口（依赖设计）** |
| 6 | `calibre.drc/lvs` 的 `fmt` / `lvs_run_dir` | `INERT_PEX_ONLY_FIELD` ×4：只校验+回填 meta，读取点在**不可达**的 PEX 分支 | 设计二选一：声明保留位 / 删字段（与 P-092 同族） | **待裁** |
| 7 | 跨切字段契约 215 行（`step_details` 77 + `log_*` 109 + `timeout` 29） | 合同级承接（全 79 op 字段存在性 + 少量真机 **6/6**） | 口径待你拍板：按"每域抽 1 条真机 + 合同全量"承接，还是要求逐 op 真机（79×3 条） | **待拍板** |

## 3. 铁律③ 缺口：输出值逐项比对

### 3.1 现状（本轮重跑）

* 断言点 **5930**：strong **4212** / medium **495** / weak **1223**；
* **仅弱断言用例 124**（offline 97 / live 27），weak 最多的几个：
  `screenshot_params_e2e_tests.case_window`(9)、`case_region`(9)、`case_flags`(6)、
  `test_process_lifetime.test_close_kills_parent_and_descendant`(7)、
  `test_maestro_command_exprs.test_every_op_builds_balanced_skill`(5)；
* 审计器报"日志读了但没断言"**2 条**（`skill_log_semantics_e2e_tests.case_f/case_h`）——**经人工核实是误报**：
  这两条正是当前红钉（打印未落日志时它们会红），只是断言写成 `assert not missing` 形式，AST 口径没识别。
  → 顺带说明**审计器本身也有口径缺口**（见 §4）。

### 3.2 结构性缺口（最关键）

1. **表 C 不存在**：现在没有任何"op × 输出字段 × 期望"的实体清单；目前的判据都是 TB 作者各自决定"断言什么"，
   所以才会出现 C06（`CDSlog` 没人断言内容）、`readback:none`（7 个 maestro 键没人知道该断言什么）这类洞。
   → 必须先**生成器 + 表**：从 `src/pyapi/**` 的响应模型（`Result`/`ResultPackage`/各包 dataclass）抽出
   `op → 字段路径` 全集，再扫 TB 的断言，产出"未比对字段"清单。
2. **`readback:none` 清单未裁决**：maestro 7 键 + `place_wire` 2 键 + calibre 4 个惰性字段，
   目前只是"如实标注"，按准则 §2 表 C 必须向设计提"补读回面 or 补 spec"。
3. **失败路径的输出形状**只在部分 TB 覆盖（`step_details` 失败步、错误壳字段），没有系统性清单。
4. 旁路输出（`warnings`/`errors`/`steps`/`CDSlog`/`log`）没有统一登记，C06 就是旁路输出漏检。

## 4. 工具与流程缺口（导致无法自动判定，必须补）

| # | 缺口 | 影响 | 补法 |
|---|---|---|---|
| T1 | 缺**输出字段矩阵生成器**（表 C） | 铁律③无法自动核对，"哪些字段没人断言"只能靠人 | 新增 `test/shared/runners/build_output_field_matrix.py`（AST 抽模型字段 + 扫断言） |
| T2 | `weak_assert_audit` 的"日志未断言"口径误报 | 会漏报真问题、误报假问题 | 识别 `assert not missing` / `assert mark in log` 两种形态 |
| T3 | op×参数矩阵"未解析调用点 101" | 可能藏着真缺口 | 输出清单人工抽样一遍并登记结论 |
| T4 | 嵌套键审计只证"键被写过"，不证"断言了效果" | "未触碰 0"会被误读成全绿 | 与 T1 合并（效果断言归表 C） |
| T5 | spec 改动与表 A 无联动 | spec 一改，表 A 立刻失效（本轮 30 条就是产物） | 用 `check_spec_op_drift.py` 扩成"条款指纹"校验，spec 变更即列出受影响行 |

## 5. 修复优先级（建议）

**P0（不做就无法自称达标）**

1. 写表 C 生成器 + 产出首版表 C，标出"未比对字段"（预计能直接捞出若干漏检，如 C06 同类）；
2. 30 条 spec 待改判逐条落笔（我给裁定建议，你或设计拍板）；
3. 日志 spec §8 八条落成正式表 A 行（§1.2 的草表已可用）。

**P1（真机可补的参数缺口）**

4. `spectre.run.mode` 5 个取值真机各跑一次（小 netlist；跑不动立卡）；
5. 向设计索取：合法 corners CSV 样例（补 `sections` 正例）、真实层次参数名（补 `set_parameter` 正例）；
6. live 侧 27 个"仅弱断言"用例逐条改写（offline 97 条按低风险后排）。

**P2（裁决类）**

7. `readback:none` 7 键 + `place_wire` 2 键 + calibre 4 惰性字段：统一向设计提"补读回面 / 补 spec / 删字段"；
8. 101 个未解析调用点人工抽样；
9. 工具口径三项（T2/T4/T5）。

## 6. 达标条件（在准则 §9 的 12 条之外，本评估新增）

* 表 C 必须有**实体文件**，且"未比对字段"为 0 或每条都有裁决；
* 日志类条款（增量/分级/限长/降级/截断/off/unavailable）必须有**内容级**断言，数量/长度断言不算；
* `readback:none` 必须是"设计已裁定"的状态，不能停留在"测试侧标注"。

---

## 附 · 本次重跑命令与产物

| 工具 | 命令 | 产物 |
|---|---|---|
| 原子级 | `PYTHONPATH=src python test/shared/runners/audit_atom_coverage.py` | `test/artifacts/evidence/atom-coverage-2026-09-30.json`（60 原子 / 零引用 0 / 待分类 2 / 已知误报 13） |
| op×参数 | `PYTHONPATH=src python test/shared/runners/build_op_param_matrix.py` | 811 行：矩阵工具原始口径 **CANDIDATE 574 / GAP 237**（`NO-OP-TB 0`）；分类器复核后 **CANDIDATE 571 / 非候选 240**（3 行按契约/na 归位）→ `round9/op-param-classification.json` |
| 嵌套键 | `python test/reports/round9/nested_key_audit.py` | 90 op / 105 字段 / 未触碰 0 / 未覆盖枚举 0 |
| 断言强度 | `PYTHONPATH=src python test/reports/round9/weak_assert_audit.py` | 5930 点（strong 4212 / medium 495 / weak 1223）；仅弱断言 124；`log_read_but_unasserted` 2（误报） |
| 离线回归 | `python test/shared/runners/run_offline_multi.py` + 单会话 pytest | `evidence/round9/offline-final-r9.log` / `offline-final-r9.xml`（2736 用例 / 0 红 / 10 skip 全有原因） |
