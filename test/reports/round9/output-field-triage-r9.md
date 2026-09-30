# round9 · 输出字段（表 C）真缺口分诊与修复

> 工具：`test/shared/runners/build_output_field_matrix.py`（AST 抽 op 返回字段 + 扫 TB 断言行 + 扫本轮证据）
> 口径：**「本轮证据里真的出现过该字段、但没有任何 TB 断言它」= 真缺口候选**；其余（只在源码里出现、测试树里完全没出现）单独列。
> 本轮数字：op **79** / 字段行 **1019**（asserted 961 / read_only 28 / absent 30）→ 真缺口候选 **11 个 op / 14 个字段**。

## 1. 真缺口候选 → 处置

| op | 字段 | 处置 | 证据 |
|---|---|---|---|
| `spectre.run` | `succeeded`（顶层） | ✅ **已补**：`spectre_modes_e2e_tests` 每个 mode 断言 `succeeded==1 且 failed==0` | `evidence/round9/spectre-modes-r9.json`（9/9 PASS，含 cx/ax/mx/lx/vx） |
| `virtuoso.cellview.lib.get` | `technology_library` | ✅ **已补**：`cellview_e2e_tests` 由"整包 JSON 找字符串"改为**点名字段值级断言** `== "cdsDefTechLib"` | `evidence/round9/cellview-r9d.txt`（5/5 PASS） |
| `spectre.measure` | `passed` | ⚠ 经核实是**误报**：该字段不在返回体里（返回体只有 `metrics`/`source`），命中来自 TB 自己的证据摘要键 `passed` | 探针：`{"metrics":[…],"source":"…"}` |
| `spectre.read_results` | `analysis` / `output_dir` | ⏳ 待补：属于 spec §6 的结果面字段；需要一次真实 `spectre.run` 产物（可挂在 `spectre_e2e_tests.RUN-02` 上） | — |
| `calibre.export` / `calibre.export_cdl` | `local_dir` / `netlist_name` | ⏳ 待补：读回面存在但 TB 未点名；挂在 calibre TB 的导出用例上（需 calibre 环境） | — |
| `virtuoso.maestro.export` | `remote_path` / `kind` | ✅ **已补**：`maestro_e2e_tests._case_exports` 逐 kind 断言 `kind` 回显 + `remote_path` 远端绝对路径（script/netlist 已用独立探针实测确认；见 §5 的"未端到端复跑"说明） | 探针：`script remote=/home/Gent/.virtuoso-bridge/vblog/.maestro-script-rc_probe-…` |
| `virtuoso.maestro.read_config` | `sim` | ⏳ 待核：疑似内部键（与 `plot` 同族），需先确认是不是对外字段 | — |
| `virtuoso.maestro.read_history` | `points_done` / `points_total`（+ `tests_done/tests_total`、`corners_done/corners_total`、`lock_flag`、`overwrite_target`、`name`、`results_dir`） | ✅ **已补**：`maestro_mc_e2e_tests` 逐字段值级断言（`points_done==points_total`、`tests_done==tests_total`、`corners_done==corners_total`、`lock_flag==0`、`overwrite_target==history`、`results_dir` 为远端绝对路径、`name==history`），**并复跑 8 点 MC 全绿** | `evidence/round9/maestro-mc-r9b.json`（9/9 PASS，`points_done=8/points_total=8`、`tests 1/1`、`corners 1/1`、`lock_flag=0`） |
| `virtuoso.schematic.read` | `numBits` / `sigType` | ✅ **已补（P-113 修复后）**：`schematic_e2e_tests.PIN-OPT` 用 `place_pin(name="NBA<3:0>", sig_type="signal")` → `read(focus="connectivity").nets["NBA<3:0>"]` 断言 **`numBits=="4"` / `sigType=="signal"`**（值级） | `evidence/round9/schematic-r9l.txt`（11/11 PASS） |
| `virtuoso.symbol.read` | `term_order` | ⏳ 待核：返回体确实有该键（`pin_order` 已断言、`term_order` 未断言），但其**语义未在 spec 写明** → 需设计明确后再定判据 | 探针：`value keys: [terms, labels, shapes, selection_boxes, pin_order, port_order, term_order, …]` |

## 2. `absent`（测试树里完全没出现过）30 条的定性

抽查后分三类，**都不是"漏了一个产品字段"**：

* **内部字典键**（handler 内部构造、不进入对外返回体）：如 `spectre.read_results.header`、`maestro.read_config.expression/global_variables/global_parameters`、
  `layout.read.cut_layer/master_cell`、`gui.auto_dismiss.attempts` 等 —— 与 `spectre.measure.passed` 同族（工具已知局限）；
* **错误码/字面量**：`schematic.write/check_and_save` 的 `type-mismatch`、`maestro.read_config` 的 `<MC_RUN_MODE>`；
* **未在真机出现过的字段**：`calibre.status.process_alive`、`spectre.check_license.lmstat_raw/version_raw`、`verilog/veriloga.read.lines`、
  `skillref.search.entries/hits/returned`、`skillref.info.chars/topics`、`spectre.run.output_root` 等 —— **这些才是下一批要补的真候选**，
  但因本轮证据里没有它们的实际取值，先不写断言（避免拍脑袋），下一轮按需补 TB 并在真机上取回真实值。

## 3. 工具本身的下一步（T1 收口）

1. `dict_keys_in_function` 需要区分「返回体构造」与「内部计算」——建议按"进入 `Result(...)`/`_step(...)` payload 的键"过滤；
2. `in_round_evidence` 的命中要用**该 op 证据文件**内的字段（现按整目录文本搜，会被通用名如 `passed` 骗到）；
3. 把「error 码字面量」与「请求回显键」列入白名单，减少噪音。

## 4. 本轮增量复跑记录

```
PYTHONPATH=src python test/live/packages/cellview_e2e_tests.py --transport http        # 5/5 PASS（technology_library 值级）
PYTHONPATH=src python test/live/packages/spectre_modes_e2e_tests.py --transport http   # 9/9 PASS（succeeded/failed 值级）
PYTHONPATH=src python test/live/packages/maestro_mc_e2e_tests.py --transport http      # 9/9 PASS（read_history 8 个字段值级，8 点 MC 约 8 分钟）
PYTHONPATH=src python test/live/packages/schematic_e2e_tests.py --transport http      # 10/10 PASS（含本批 10 个"只在离线出现"的参数）
```

## 4b. op×参数：真机从未传过值的参数 14 → 4（2026-09-30 收敛）

用**新生成的矩阵**（`test/reports/round8/op-param-matrix.json`，2026-09-30 13:53；`round9/` 下那份 20:18 的是旧的，
已同步覆盖）统计"参数命中只出现在 `test/offline/**`、没有任何 semi/live 传值"：

| 时间 | 有 semi/live 命中 | 只在离线出现 | GAP/无命中 |
|---|---|---|---|
| 上午（旧矩阵） | 557 | **14** | 240 |
| 第一批补测后 | 572 | 4 | 237 |
| **place_pin 四档补测后（P-113 已修 + P-114 红钉）** | **576** | **0** | 237 |

补掉的 10 个：`place_label.{font,justify,alias}`、`set_label_properties.font`、`place_note.{font,justify}`、
`set_note_properties.{font,justify}`、`set_wire_properties.line_style`（全部真机传值 + 读回断言，`schematic-r9f.txt`）。

**`place_pin` 四档的处置**：
* `sig_type` —— **P-113 已修并验收**（`sig_type="signal"` 真机 OK，且 `numBits/sigType` 值级读回）；
* `off_sheet` / `power_sens` / `ground_sens`（含四属性组合）—— **P-114 已立卡**，TB 里按红钉固定
  （三档"报 ok 但零对象"的静默 no-op + `off_sheet` 单用 `nth` 硬报错），修好即 UNEXPECTED-GREEN。

> 环境插曲（如实记录）：本批第一次复跑时 `schematic_e2e_tests` 连续两次红在不同位置
> （`pin not found` / `load: error while loading file … line 14`），按 Runbook §10.6 **重启 vblog CIW**
> （按 cwd 精确杀 + 清 `CDS.log.cdslck` + `xvfb-run virtuoso -cdslib ./cds.lib`）后 **10/10 复绿** ——
> 属环境降级，不是本批断言的问题。

## 5. 未完成的端到端复跑（如实记录）

* `maestro_e2e_tests` 本轮加强了两处（`_case_exports` 的 `kind`/`remote_path`、`_case_write_job_policy_sim_mode`
  的 nil 兜底 + 往返一致）。但整条套件跑到 **RUN-01** 时被**已知**的会话句柄问题打断：
  `RuntimeError: Cannot find an active session named fnxSession463`（C09 / P-086 家族，卡内已有记录），
  因此这两处加强**尚无端到端证据**；run 日志 `evidence/round9/maestro-r9f.txt`。
  * 已做的最小验证：`script` / `netlist` 两种导出的 `kind` + `remote_path` 绝对路径（独立探针）；
  * 顺带修掉 TB 自身脆弱点：`asiGetHighPerformanceOptionVal(as 'uniMode)` 返回 nil 时不再把 nil 当 mode 传
    （否则会在无关处结构化失败），改为写入默认 `spectre` 再断言读回一致；
  * 下一轮：等 C09 修好、CIW 安静窗口再整条复跑。
