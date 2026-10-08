# op × 输出字段矩阵（表 C 第一版 · 静态近似）

> 工具：`test/shared/runners/build_output_field_matrix.py`｜op **78** 个 / 字段行 **1008** 条
> 状态分布：`{"asserted": 970, "absent": 20, "read_only": 18}`（asserted=有断言行命中；read_only=只在读取/证据里出现；absent=测试树里没出现）

## 1. 未断言字段最多的 op（Top 15）

| op | 未断言字段数 | 字段 |
|---|---|---|
| `virtuoso.maestro.read_config` | 5 | <MC_RUN_MODE>, expression, global_parameters, global_variables, plot |
| `virtuoso.maestro.run` | 3 | monte_carlo, progress, window_checks |
| `virtuoso.skillref.search` | 3 | entries, hits, returned |
| `virtuoso.symbol.read` | 3 | pinOrder, portOrder, termOrder |
| `virtuoso.layout.read` | 2 | cut_layer, master_cell |
| `virtuoso.maestro.read_results` | 2 | overall_spec, overall_yield |
| `virtuoso.maestro.close_waveform_gui` | 2 | session_present, window_present |
| `virtuoso.skillref.info` | 2 | chars, topics |
| `spectre.check_license` | 2 | lmstat_raw, version_raw |
| `calibre.check_env` | 1 | deck_detail |
| `calibre.status` | 1 | process_alive |
| `calibre.read_results` | 1 | log_counters |
| `virtuoso.gui.auto_dismiss` | 1 | attempts |
| `virtuoso.maestro.open_waveform_gui` | 1 | session_created |
| `virtuoso.schematic.write` | 1 | type-mismatch |

## 1b. 真缺口候选（本轮证据里**真的出现过**该字段、但 TB 没断言）

> 扫描证据：`test/artifacts/evidence/round9`（93 个 JSON）

| op | 字段 |
|---|---|
| — | （无） |

## 2. live/semi 无调用点的 op（没有真机/半真机执行证据）

（无）

## 3. 口径与局限

* 本表是**静态近似**：`asserted` 只表示「断言行里出现了该字段名」，不等于判据强度达标；
  `read_only` 与 `absent` 都算「**未逐项比对**」，需要补 TB 断言或立「读回面/参数裁决」卡；
* 字典键会包含「请求回显」字段（多报），helper 只跟一层（可能漏报）；下一版按 op 逐个复核；
* 真机行为证据仍以各 TB 的证据 JSON 为准；本表只负责把「待比对字段」缩到可人工复核的规模。
