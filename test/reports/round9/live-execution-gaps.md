# round9 · 真机 TB 执行矩阵审计：谁负责跑、跑没跑过

> 执行：subagent `/root/opparam_r9`｜2026-09-29｜工具 `test/reports/round9/live_execution_matrix.py`（只读）
> 原始表：`live-execution-matrix.md` / `.json`（脚本生成）

## 1. 数字

| 指标 | 结果 |
|---|---|
| live TB 文件总数 | **50** |
| 在 HTTP 门禁 `run_all_http.py` SUITES 里 | **16** |
| 既不在门禁、**又没有任何文件引用**（无 runner / 无计划 / 无文档 / 无别的 TB） | **3** |
| `test/artifacts/` 里今天找不到任何证据文件的 | **5** |
| 门禁 16 套今天**都有**证据 | ✅（20:33 那轮 gate 的 `package-e2e-r9-full/*.log`） |

## 2. 关键发现：3 个"没人负责跑"的真机 TB

| TB | 门禁 | 被引用 | 证据 | 判定 |
|---|---|---|---|---|
| `test/live/packages/step_details_e2e_tests.py` | ✅（round9 接线） | ✅ | ✅ `evidence/step-details/step-details.json` | 原为**全树 0 引用 0 证据**；已接线 + 补默认 `--out`，**http 6/6 绿** |
| `test/live/packages/gui_e2e_tests.py` | ✅（round9 接线） | ✅ | ✅ `evidence/gui-atoms-20260929-2046/gui-atoms-green.json` | 已接线，**http 4/4 绿**（WIN-01/KEY-01/DISMISS-01/SHOT-01） |
| `test/live/packages/layout_geometry_classification_e2e_tests.py` | ✅（round9 接线） | ✅ | ✅ `evidence/layout-geometry-classification/…json` | 补 `--transport`（http-only）+ 证据目录从 `round8/` 移到中性目录，**http 4/4 绿** |

> 复现：`python test/reports/round9/live_execution_matrix.py` → `never_referenced` 列表。
> **round9 复跑（23:05 最新）**：**live TB 53 / 门禁 23 / 无人引用 0 / 今日无证据 0**（首轮为 50/16/3/5）。
> 期间接线过的 TB：`step_details`、`layout_geometry_classification`、`gui`（我）＋ `nested_keys`（我）＋ `maestro_mc`、`maestro_nested_keys`（root）。

## 3. 今天没有证据的 5 个（含统计口径说明）

`maestro_mc_e2e_tests.py`、`skill_log_options_e2e_tests.py`、`skill_log_semantics_e2e_tests.py`、
`step_details_e2e_tests.py`、`registration_hostkey_rotation_tb.py`。

其中前三个**今晚确实跑过**（有 `verify-fix-r9/` 或 `round9/` 下的 JSON 证据），只是证据文件名用连字符
（`c06-skill-log-semantics.json`）或写在别的目录，**不匹配 TB 文件名**——所以这一列只能当**弱信号**：
"没有匹配到证据" ≠ "没跑过"。`registration_hostkey_rotation_tb.py` 今晚 20:37 有 `reg-hostkey-rotation.json`
（同样属命名不匹配）。

`step_details_e2e_tests.py` 例外：它是**真的全树 0 条证据**（§2）。

## 4. 建议（按优先级）

1. ~~**P1**：把 `step_details_e2e_tests.py` 加进 SUITES + 默认 `--out`~~ ✅ 已完成（http 6/6 绿，证据已落盘）。
2. ~~**P1**：为 `gui_e2e_tests.py` / `layout_geometry_classification_e2e_tests.py` 明确执行入口~~ ✅ 已完成
   （两者均已接线并 http 全绿；geometry TB 另加了 http-only 的 `--transport` 参数与中性证据目录）。
3. **P2（待办）**：统一证据命名——每个 live TB 的证据文件建议带 TB 名（连字符命名会让自动核对失效）。
4. **P2（待办）**：把本脚本纳入每轮收口：要求"`never_referenced` = 0 或全部有书面豁免"、"门禁套件当天都有证据"。

## 5. 口径

本审计只回答"有没有执行入口 / 有没有证据痕迹"，**不判断这些 TB 的判据强弱**（那是
`weak-assertions.md` 的范围），也不替代真机结论（真机结论只认 HTTP 门禁与登记在案的独立运行）。
