# round10 · 半真机/真机证据的本轮复跑核对（机器生成）

> 输入：`test/reports/round8/round8-spec覆盖矩阵.json` 里 **39 条没有离线证据** 的行；
> 本轮 runner 结果：HTTP 门禁 25 套、flows 9 场景、registration 9 场景、semi 48 探针。
> 判定：该行引用的 semi/live TB 在本轮跑过且绿 = ✅；否则如实标出。

| 条款 | verdict | 引用证据 | 本轮状态 |
|---|---|---|---|
| 总览#179 | direct | `infra_e2e_tests.py`：HTTP 门禁 PASS |
| 路由#024 | indirect | `role_split_tb.py`：flows PASS |
| 注册#007 | direct | `registration_http_six_step_tb.py`：registration six-step PASS<br>`cov_registration_real.py`：registration PASS |
| 注册#011 | indirect | `cov_registration_real.py`：registration PASS<br>`registration_http_six_step_tb.py`：registration six-step PASS |
| 注册#040 | direct | `cov_registration_real.py`：registration PASS<br>`registration_http_six_step_tb.py`：registration six-step PASS |
| schematic#018 | direct | `screenshot_params_e2e_tests.py`：HTTP 门禁 PASS<br>`schematic_e2e_tests.py`：HTTP 门禁 PASS |
| schematic#025 | direct | `schematic_e2e_tests.py`：HTTP 门禁 PASS |
| symbol#023 | direct | `symbol_e2e_tests.py`：HTTP 门禁 PASS |
| symbol#026 | direct | `symbol_e2e_tests.py`：HTTP 门禁 PASS |
| symbol#082 | indirect | `schematic_pin_ops_probe.py`：semi PASS<br>`symbol_e2e_tests.py`：HTTP 门禁 PASS |
| layout#048 | direct | `layout_e2e_tests.py`：HTTP 门禁 PASS |
| layout#079 | indirect | `layout_e2e_tests.py`：HTTP 门禁 PASS<br>`layout_p044_second_write_probe.py`：semi PASS |
| layout#179 | direct | `layout_geometry_classification_e2e_tests.py`：HTTP 门禁 PASS<br>`layout_e2e_tests.py`：HTTP 门禁 PASS |
| verilog#060 | indirect | `verilog_e2e_tests.py`：HTTP 门禁 PASS |
| verilog#065 | indirect | `verilog_e2e_tests.py`：HTTP 门禁 PASS |
| verilog#099 | indirect | `verilog_e2e_tests.py`：HTTP 门禁 PASS |
| veriloga#069 | direct | `veriloga_e2e_tests.py`：HTTP 门禁 PASS |
| veriloga#088 | indirect | `adc_sar_flow_tb.py`：flows PASS<br>`veriloga_e2e_tests.py`：HTTP 门禁 PASS |
| veriloga#094 | direct | `veriloga_e2e_tests.py`：HTTP 门禁 PASS<br>`adc_sar_flow_tb.py`：flows PASS |
| calibre#011 | direct | `calibre_e2e_tests.py`：HTTP 门禁 PASS |
| calibre#060 | direct | `calibre_e2e_tests.py`：HTTP 门禁 PASS |
| calibre#068 | direct | `calibre_timeout_probe.py`：semi PASS |
| calibre#069 | direct | `calibre_timeout_probe.py`：semi PASS |
| schematic#051 | direct | `nested_keys_e2e_tests.py`：HTTP 门禁 PASS |
| schematic#052 | direct | `nested_keys_e2e_tests.py`：HTTP 门禁 PASS |
| schematic#054 | direct | `schematic_e2e_tests.py`：HTTP 门禁 PASS |
| schematic#055 | direct | `schematic_e2e_tests.py`：HTTP 门禁 PASS |
| schematic#056 | direct | `schematic_e2e_tests.py`：HTTP 门禁 PASS |
| schematic#072 | direct | `schematic_e2e_tests.py`：HTTP 门禁 PASS |
| schematic#073 | direct | `schematic_e2e_tests.py`：HTTP 门禁 PASS |
| maestro#081 | direct | `maestro_e2e_tests.py`：HTTP 门禁 PASS |
| maestro#103 | direct | `maestro_nested_keys_e2e_tests.py`：HTTP 门禁 FAIL(红钉)，但 `NKM-07a` PASS |
| maestro#176 | direct | `maestro_mc_e2e_tests.py`：HTTP 门禁 PASS |
| maestro#230 | direct | `maestro_mc_e2e_tests.py`：HTTP 门禁 PASS |
| spectre#145 | direct | `spectre_e2e_tests.py`：HTTP 门禁 PASS |
| verilog#051 | direct | `verilog_e2e_tests.py`：HTTP 门禁 PASS<br>`verilog_import_params_e2e_tests.py`：HTTP 门禁 PASS |
| verilog#052 | direct | `verilog_e2e_tests.py`：HTTP 门禁 PASS<br>`verilog_import_params_e2e_tests.py`：HTTP 门禁 PASS |
| calibre#152 | partial | `calibre_export_pex_e2e_tests.py`：HTTP 门禁 PASS |
| calibre#071 | direct | `calibre_timeout_probe.py`：semi PASS<br>`calibre_e2e_tests.py`：HTTP 门禁 PASS |

> **没有任何本轮 PASS 依据的行：0** → 无
