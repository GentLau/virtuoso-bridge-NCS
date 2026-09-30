# round9 三层结果汇总（机器，B 线生成）

- 生成时间：2026-09-29T21:28:22
- 半真机：`{'file_mtime': '2026-09-29T21:24', 'group': 'all', 'count': 40, 'ok': False, 'failed': ['maestro_env_probe.py', 'maestro_e2e_probe.py', 'one_shot_burst_tb.py']}`

- 门禁（`run_all_http.py`）：file mtime 2026-09-29T21:24，all_passed=**False**，套件 19 / 期望 19，缺 []，多 []

| 套件 | rc | ok | PASS | FAIL |
|---|---|---|---|---|
| infra_e2e_tests.py | 0 | True | 6 | 0 |
| cellview_e2e_tests.py | 0 | True | 5 | 0 |
| schematic_e2e_tests.py | 0 | True | 10 | 0 |
| symbol_e2e_tests.py | 0 | True | 9 | 0 |
| layout_e2e_tests.py | 0 | True | 11 | 0 |
| verilog_e2e_tests.py | 0 | True | 4 | 0 |
| veriloga_e2e_tests.py | 0 | True | 7 | 0 |
| skillref_e2e_tests.py | 0 | True | 6 | 0 |
| spectre_e2e_tests.py | 0 | True | 6 | 0 |
| screenshot_params_e2e_tests.py | 0 | True | 5 | 0 |
| calibre_e2e_tests.py | 1 | False | 0 | 0 |
| calibre_params_e2e_tests.py | 0 | True | 6 | 0 |
| verilog_import_params_e2e_tests.py | 1 | False | 12 | 2 |
| calibre_export_pex_e2e_tests.py | 1 | False | 5 | 2 |
| maestro_view_param_e2e_tests.py | 1 | False | 0 | 0 |
| step_details_e2e_tests.py | 0 | True | 6 | 0 |
| layout_geometry_classification_e2e_tests.py | 0 | True | 4 | 0 |
| gui_e2e_tests.py | 0 | True | 4 | 0 |
| maestro_e2e_tests.py | 1 | False | 0 | 0 |
