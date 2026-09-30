# round9 · live 侧"仅弱断言"27 例逐条分诊（弱断言加强记录）

> 执行：测试/root｜2026-09-30｜来源：`test/reports/round9/weak-assert-audit.json`（本轮重跑：5930 断言点 = strong 4212 / medium 495 / weak 1223；仅弱断言用例 124，其中 live 27）
> 口径：**先人肉分诊"真弱 vs 误报"，再决定改不改**——不盲目改断言（避免把已经值级的用例改坏）。
> 影响：本表是《全量测试准则 v0.3》§3.5"弱判据必须补强或登记"的落地记录。

## 1. 已加强（真弱 → 值级；每条都跑过增量验证）

| 用例 | 原判据 | 加强后 | 增量证据 |
|---|---|---|---|
| `schematic_e2e_tests._case_check_and_save` (CHECK-01) | 只判 `ok` | 空基线 → 造 `MN_SAVE` 实例 → `check_and_save` → **`error is None` + 实例集合前后一致（值级）** → 收尾删实例 | `evidence/round9/schematic-r9c.txt`（10/10 PASS） |
| `spectre_e2e_tests._case_failure` (RUN-04) | 只判 `not ok` | **发现假绿**：原请求在入参校验就失败（`parse='none' requires keep_run_dir=true`），坏网表从未跑；已改为唯一 job + `keep_run_dir=True`，并断言 **run.ok=false + 有 execute 步 + rc!=0 + stdout 含 `spectre completes with`** | `evidence/round9/spectre-r9d.txt`（6/6 PASS + P-107 NOTE） |
| `cellview_e2e_tests._case_negative` (NEG) | 只判"错误非空" | 按分层错误码逐条断言：`libraryNotFound` / `cellNotFound` / `viewNotFound` / `categoryNotFound` | `evidence/round9/cellview-r9c.txt`（5/5 PASS） |
| `skillref_e2e_tests._case_errors` (ERR-01) | 两条都只判 `not ok` | 断言错误**原因**：坏 doc_root 要点名 docroot 且说明缺 `finder/SKILL`；坏 source 要给取值域 `source must be one of` | `evidence/round9/skillref-r9c.txt`（6/6 PASS） |
| `symbol_e2e_tests._case_missing_view` (WRITE-03) | 只判 `not ok` | 错误必须**点名 `missing_view`** 且含 `not found` | `evidence/round9/symbol-r9c.txt`（9/9 PASS） |
| `veriloga_e2e_tests._case_delete` (WRITE-04) | 只判 `not ok` | 删后 read 的失败原因必须是 **视图缺失（`missing`）+ 点名视图路径**（证 delete 真生效） | `evidence/round9/veriloga-r9c.txt`（7/7 PASS） |
| `spectre_params_e2e_tests.case_measure_bad_source` (MEASURE-P2) | 只判"错误非空" | 断言 `cannot read source_path` + **点名缺失文件**；同时把证据目录从写死的 `round8` 改成 `--out-dir`（默认 round 无关） | `evidence/round9/spectre-params/spectre-params.json`（5/5 PASS） |

> 连带产出：**P-107**（失败 run 被报成"下载失败"、spec §5.4 分类冲突）、**P-108**（`mode="x"` 被 Spectre 24.1 拒绝，SPECTRE-129）

## 2. 分诊为**误报/已足够**（不改，理由）

| 用例 | 审计为何记 weak | 实际强度 |
|---|---|---|
| `screenshot_params_e2e_tests.case_default/case_window/case_region/case_flags`（9+9+6+3） | 计到 `opened.get('local_path')` / `value` 这类真值判断 | 用例随后调 `_check_png()`：**PNG ≥1000 字节 + 远端暂存已清理**（P-091 口径）→ 已是值级；negative 分支还断言错误文案含 `window`/`view_type` |
| `maestro_e2e_tests._case_waveform_gui` / `maestro_view_param._case_waveform_gui` | 计到 `opened['window']` / `bool(opened.get('window'))` | 断言的是 GUI 句柄三件套（`window`/`session` + `closed=True`）；句柄本身没有更强语义可断言（做格式匹配只会变脆） |
| `design_iterate_tb.stage_lvs` / `stage_r1_*` / `serdes_rx_flow_tb.stage_*` | 计到 `t`（SKILL 返回真值 `t`） | 这些 stage 的判据在**外层**：LVS 段断言 `status/ports/nets/differences`，出图段断言 `shape_count`/实例集合（见 `flow-design-iterate-r9.log`） |
| `cellview_e2e_tests._case_negative` 里的 `transport`、`spectre_params.case_measure_bad_source` 的 `transport` | 计到 helper 形参 | 分诊器按"参数名"计了一遍，不是断言 → 误报（计数上把这两条算进 27） |
| `*_e2e_tests.case_env`（nested_keys / step_details） | 计到 `response.get('ok') is True` | 环境探活用例，判据就该是"探活成功"；真正判据在同套件的功能用例 |
| `spectre_e2e_tests._case_failure` 之外的 `_case_negative`/`_case_delete` 等 | 见 §1 | 已加强 |
| `registration_role_split_tb.main`（`args.lab_host`）/ `scale_local_fake_tb.main`（`args.base_port`） | 计到 argparse 属性 | 环境入参检查，不是结果判据 → 误报 |
| `verilog_import_params.case_result_views_red_pin` | 红钉用例（`truth`） | 故意断言"必须失败"（P-099/P-100 口径），强度由红钉语义承担 |

## 3. 剩余（未改，登记）

* offline 侧 97 例"仅弱断言"：低风险（多为契约/负例形状），本轮**只登记不改写**；下一轮按《准则》§3.5 与表 C 一起过。
* `weak_assert_audit` 自身口径问题（记入工具缺口 T2）：把 `assert not missing` 这类"由 log 派生的集合判据"误报成"日志未断言"（本轮 2 条都在 C06 红钉用例里）。

## 4. 复跑口径

本表所有"已加强"条目都**只跑了增量**（各自 TB 单独 `--transport http`），未跑全量；证据见上表"增量证据"列，命令形如
`PYTHONPATH=src python test/live/packages/<TB>.py --transport http`。全量回归留到下一轮。
