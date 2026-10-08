# round10 · 用例档位审计的分诊结论（single / no_negative_hint）

> 工具：`PYTHONPATH=src python test/shared/runners/case_profile_audit.py --matrix test/reports/round8/op-param-matrix.json`
> 数据（fresh）：78 op；**single = 2**、**no_negative_hint = 10**。
> 口径：工具只出"线索"，下面是逐条人工核对（每条给 file:line / 反证）。
> 教训：**不要用 `test/reports/round9/op-param-matrix.json`** —— 它是 14:25 的旧快照
> （C07 迁移前），会把已删除的 `calibre.export_cdl` 当成"single op"；官方 matrix 在
> `test/reports/round8/`（工具 `OUT`）。

## 1. single（live/semi 只出现 1 个调用点）

| op | 事实 | 结论 |
|---|---|---|
| `virtuoso.gui.list_windows` | 调用点在 `test/live/packages/gui_e2e_tests.py:96` 的 `_windows()` helper 里；被 WIN-01（`:123-137`）与其它用例当"读回仪器"反复使用。请求模型 `gui.py:229-232` 只有 token/timeout/step_details（无业务参数，不存在"多参数档位"） | **误报**（helper 间接调用；输出被多用例比对） |
| `virtuoso.skillref.info` | 调用点在 `skillref_e2e_tests.py:89` 的 `_info()` helper；INFO-01（found/missing，`:164-185`）、INFO-02 remote、INFO-03 params（`raw` 两档，`:258-262`）、ERR-01 bad source/root（`:198-211` 断言 `not ok` + 原因） | **误报**（4 条用例覆盖 found/missing/remote/params/非法档） |

## 2. no_negative_hint（所在 TB 没有"预期失败"文字线索）

工具只看 op_sites 列出的文件（最多 8 个），而这些 op 的主套件是 **packages/**，不在那 8 个里 → 逐条 grep 主套件后**全部有非法/失败档**：

| op | 反证（file:line） |
|---|---|
| `basic.command.run` / `basic.skill.execute` | `test/live/packages/infra_e2e_tests.py:212`（`sleep 5` + timeout=1 **must fail**）；BASIC-06 非法档：语法错 skill、`exit 7`→ok=false+rc=7、不存在命令 rc=127（round9 补，7/7 绿） |
| `calibre.lvs` | `calibre_e2e_tests.py::_case_lvs_source_legacy_mutex`（`source`+`cdl` 互斥 → 请求层拒绝）+ `LVS-SRC-XOR` 用例 |
| `calibre.read_results` | 同套件 `EXPORT-02 未知 item 零落盘` + `DRC-02` 坏 deck 结构化失败（同族失败面）；`read_results` 自身的未知 job 由 export/read 的失败分支覆盖（见 round9 分诊） |
| `virtuoso.layout.read/write` | `layout_e2e_tests.py:317,325,544,555,646`（missing view / wrong view_type / invalid cleanup_policy 均 `not ok`）；另有 `layout_geometry_classification_e2e_tests`（4/4） |
| `virtuoso.layout.gds` | `layout_e2e_tests.py` 的 view_type/缺 view 失败档 + `gds_publish_path_edges_probe`（P-051，半真机） |
| `virtuoso.schematic.read/write` | `schematic_e2e_tests.py:120`（`_write_fails`）`:363,:367,:483`（NEG-pos / 非法 sig_type / 非法几何） |
| `virtuoso.gui.list_windows` | 见 §1（无业务参数；同套件另有 `send_key bad window must fail` 的 GUI 失败面） |

## 3. 结论

* 12 条线索**全部为工具局限导致的误报**（helper 间接调用 + op_sites 截断到 8 个文件）；
* 本轮**没有发现"只有单一档位"或"缺非法档"的真实 op**；
* 但保留这个工具与清单：下次 op_sites 截断/helper 形态变化时仍要人工过一遍（不许直接当"通过"）。
