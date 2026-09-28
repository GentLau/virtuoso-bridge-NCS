# 操作 × 参数覆盖矩阵（机器，AST 解析；**不是覆盖结论**）

- 条目 628：CANDIDATE 572 / GAP 56 / NO-OP-TB 0
- 非 CANDIDATE 中：通用 `timeout` 字段 34 条（由 `test/offline/unit/test_param_timeout_contract.py` 的 79/79 op 合同承担）；其余 22 条为逐 op 缺口。
- 无法静态解析的调用点 82 个 = 管道行 64（op 载体内部把形参转发，真值在调用点已解析）+ **待人工复核 18**（不计覆盖）
- CANDIDATE = 参数名在目标 op 的调用点出现；是否断言语义仍要逐条看 TB 判据。
- op 调用点清单见 `op-coverage.json`；未解析明细见本文件末尾。

## 非 CANDIDATE（按 op 分组）

### `calibre.drc`

- [GAP] `cdl` (str | None, required=False) — op_tb_files=6
- [GAP] `fmt` (str, required=False) — op_tb_files=6
- [GAP] `hcell_file` (str | None, required=False) — op_tb_files=6
- [GAP] `lvs_run_dir` (str | None, required=False) — op_tb_files=6
- [GAP] `spice_file` (str | None, required=False) — op_tb_files=6
- [GAP] `xcell_file` (str | None, required=False) — op_tb_files=6

### `calibre.lvs`

- [GAP] `fmt` (str, required=False) — op_tb_files=7
- [GAP] `ground` (str | None, required=False) — op_tb_files=7
- [GAP] `lvs_run_dir` (str | None, required=False) — op_tb_files=7
- [GAP] `power` (str | None, required=False) — op_tb_files=7

### `calibre.pex`

- [GAP] `ground` (str | None, required=False) — op_tb_files=1
- [GAP] `hcell_file` (str | None, required=False) — op_tb_files=1
- [GAP] `hier` (bool, required=False) — op_tb_files=1
- [GAP] `job_id` (str | None, required=False) — op_tb_files=1
- [GAP] `params` (dict[str, str] | None, required=False) — op_tb_files=1
- [GAP] `poll_interval` (float, required=False) — op_tb_files=1
- [GAP] `power` (str | None, required=False) — op_tb_files=1
- [GAP] `runset` (str | None, required=False) — op_tb_files=1
- [GAP] `spice_file` (str | None, required=False) — op_tb_files=1
- [GAP] `turbo` (int, required=False) — op_tb_files=1
- [GAP] `xcell_file` (str | None, required=False) — op_tb_files=1

### `virtuoso.layout.read`

- [GAP] `depth` (int, required=False) — op_tb_files=10

## 未解析调用点（机器，不计覆盖）

### A. 待人工复核（18）——非管道行，需逐条确认是真实调用点还是辅助函数

- test/offline/core/api_server_tb.py:235 `` (how=payload-dict, enclosing=main, params=token)
- test/offline/core/api_server_tb.py:300 `` (how=payload-dict, enclosing=main, params=token)
- test/offline/core/api_server_tb.py:396 `` (how=payload-dict, enclosing=main, params=token)
- test/offline/core/api_server_tb.py:281 `` (how=payload-dict, enclosing=main, params=cmd,token)
- test/offline/core/api_server_tb.py:447 `` (how=payload-dict, enclosing=main, params=token)
- test/offline/core/api_server_tb.py:429 `` (how=payload-dict, enclosing=slow_call, params=token)
- test/offline/unit/test_middle_contracts.py:167 `` (how=payload-dict, enclosing=test_invalid_timeout_maps_to_dispatch_400, params=timeout,token)
- test/offline/unit/test_norm_gap_batch2.py:257 `` (how=payload-dict, enclosing=test_unknown_field_rejected_on_dataclass_request, params=doc_root,query,request_id,source,token)
- test/offline/unit/test_param_timeout_contract.py:174 `` (how=payload-dict, enclosing=setUpClass, params=timeout,token)
- test/offline/unit/test_top_layer_dispatch.py:67 `` (how=payload-dict, enclosing=test_success_shell, params=token,value)
- test/offline/unit/test_top_layer_dispatch.py:89 `` (how=payload-dict, enclosing=test_unknown_operation_is_404, params=token)
- test/offline/unit/test_top_layer_dispatch.py:94 `` (how=payload-dict, enclosing=test_invalid_request_fields_are_400, params=token,value)
- test/offline/unit/test_top_layer_dispatch.py:101 `` (how=payload-dict, enclosing=test_domain_validation_failure_is_400, params=token)
- test/offline/unit/test_top_layer_dispatch.py:107 `` (how=payload-dict, enclosing=test_unexpected_exception_is_5xx_without_traceback, params=token)
- test/semi/probes/calibre_package_http_probe.py:111 `f"calibre.{args.kind}"` (how=helper:call, enclosing=main, params=token)
- test/live/packages/calibre_e2e_tests.py:131 `f"calibre.{kind}"` (how=helper:_value, enclosing=_run_and_read, params=token)
- test/live/packages/cellview_e2e_tests.py:277 `operation` (how=helper:_expect_fail, enclosing=_case_negative, params=token)
- test/shared/fixtures/probe.py:24 `op` (how=helper:call, enclosing=None, params=token)

### B. 管道行（64）——op 载体内部转发形参，真值在调用点已解析，不构成漏测

- test/offline/unit/test_api_server_main.py:398 `` (enclosing=test_unserializable_result_is_structured_500, params=token)
- test/offline/unit/test_top_layer_pool.py:61 `` (enclosing=_post, params=token)
- test/semi/probes/calibre_package_http_probe.py:64 `` (enclosing=call, params=token)
- test/semi/probes/cdl_export_variants_probe.py:69 `` (enclosing=call, params=token)
- test/semi/probes/gds_publish_path_edges_probe.py:46 `` (enclosing=call, params=token)
- test/semi/probes/gds_then_skill_probe.py:53 `` (enclosing=call, params=token)
- test/semi/probes/layout_p044_second_write_probe.py:98 `` (enclosing=op, params=token)
- test/semi/probes/maestro_export_include_results_probe.py:55 `operation` (enclosing=value, params=token)
- test/semi/probes/maestro_screenshot_probe.py:34 `` (enclosing=api_call, params=token)
- test/semi/probes/maestro_screenshot_probe.py:40 `operation` (enclosing=api_data, params=token)
- test/semi/probes/shared_cdf_pollution_probe.py:51 `` (enclosing=call, params=token)
- test/semi/probes/spectre_ac_pipeline_probe.py:62 `` (enclosing=call, params=token)
- test/semi/probes/twouser_same_view_probe.py:66 `` (enclosing=_op, params=token)
- test/semi/probes/_maestro_tb.py:43 `operation` (enclosing=data, params=timeout,token)
- test/semi/probes/_maestro_tb.py:29 `` (enclosing=call, params=token)
- test/live/flows/design_iterate_tb.py:173 `` (enclosing=op, params=token)
- test/live/flows/design_iterate_tb.py:180 `` (enclosing=raw_call, params=token)
- test/live/flows/lvs_from_schematic_tb.py:75 `` (enclosing=op, params=token)
- test/live/flows/multiuser_layout_handoff_tb.py:56 `` (enclosing=call, params=token)
- test/live/flows/project_flow_tb.py:129 `` (enclosing=raw_call, params=token)
- test/live/flows/s11_full_flow.py:61 `` (enclosing=call, params=token)
- test/live/flows/serdes_rx_flow_tb.py:103 `` (enclosing=raw_call, params=token)
- test/live/packages/calibre_e2e_tests.py:106 `` (enclosing=_op, params=token)
- test/live/packages/calibre_e2e_tests.py:113 `operation` (enclosing=_value, params=token)
- test/live/packages/calibre_export_pex_e2e_tests.py:65 `` (enclosing=_op, params=token)
- test/live/packages/calibre_export_pex_e2e_tests.py:69 `operation` (enclosing=_value, params=token)
- test/live/packages/calibre_params_e2e_tests.py:62 `` (enclosing=_op, params=token)
- test/live/packages/calibre_params_e2e_tests.py:66 `operation` (enclosing=_value, params=token)
- test/live/packages/cellview_e2e_tests.py:93 `` (enclosing=_call, params=token)
- test/live/packages/cellview_e2e_tests.py:97 `operation` (enclosing=_op, params=token)
- test/live/packages/cellview_e2e_tests.py:109 `operation` (enclosing=_expect_fail, params=token)
- test/live/packages/cellview_e2e_tests.py:105 `operation` (enclosing=_value, params=token)
- test/live/packages/gui_e2e_tests.py:81 `` (enclosing=_op, params=token)
- test/live/packages/infra_e2e_tests.py:98 `` (enclosing=_op, params=token)
- test/live/packages/layout_e2e_tests.py:80 `` (enclosing=_op, params=token)
- test/live/packages/layout_e2e_tests.py:87 `operation` (enclosing=_value, params=token)
- test/live/packages/layout_geometry_classification_e2e_tests.py:63 `` (enclosing=_value, params=)
- test/live/packages/layout_geometry_classification_e2e_tests.py:71 `` (enclosing=_expect_fail, params=)
- test/live/packages/maestro_e2e_tests.py:87 `` (enclosing=_op, params=token)
- test/live/packages/maestro_e2e_tests.py:97 `operation` (enclosing=_value, params=token)
- test/live/packages/maestro_view_param_e2e_tests.py:95 `` (enclosing=_op, params=token)
- test/live/packages/maestro_view_param_e2e_tests.py:104 `operation` (enclosing=_value, params=token)
- test/live/packages/maestro_view_param_e2e_tests.py:116 `` (enclosing=_expect_fail_text, params=token)
- test/live/packages/schematic_e2e_tests.py:86 `` (enclosing=_op, params=token)
- test/live/packages/schematic_e2e_tests.py:93 `operation` (enclosing=_value, params=token)
- test/live/packages/screenshot_params_e2e_tests.py:72 `` (enclosing=_op, params=token)
- test/live/packages/screenshot_params_e2e_tests.py:76 `operation` (enclosing=_raw, params=token)
- test/live/packages/screenshot_params_e2e_tests.py:80 `operation` (enclosing=_value, params=token)
- test/live/packages/skillref_e2e_tests.py:74 `` (enclosing=_op, params=token)
- test/live/packages/spectre_e2e_tests.py:76 `` (enclosing=_op, params=token)
- test/live/packages/spectre_e2e_tests.py:83 `operation` (enclosing=_value, params=token)
- test/live/packages/spectre_params_e2e_tests.py:105 `` (enclosing=op, params=token)
- test/live/packages/spectre_params_e2e_tests.py:113 `` (enclosing=expect_fail, params=token)
- test/live/packages/symbol_e2e_tests.py:76 `` (enclosing=_op, params=token)
- test/live/packages/symbol_e2e_tests.py:83 `operation` (enclosing=_value, params=token)
- test/live/packages/veriloga_e2e_tests.py:94 `` (enclosing=_op, params=token)
- test/live/packages/veriloga_e2e_tests.py:101 `operation` (enclosing=_value, params=token)
- test/live/packages/verilog_e2e_tests.py:105 `` (enclosing=_op, params=token)
- test/live/packages/verilog_e2e_tests.py:112 `operation` (enclosing=_value, params=token)
- test/live/packages/verilog_import_params_e2e_tests.py:79 `` (enclosing=_op, params=token)
- test/live/packages/verilog_import_params_e2e_tests.py:83 `operation` (enclosing=_value, params=token)
- test/live/stress/layout_multiuser_lock_tb.py:51 `` (enclosing=call, params=token)
- test/shared/fixtures/probe.py:13 `` (enclosing=call, params=token)
- test/shared/runners/env_check.py:62 `` (enclosing=_call_http, params=token)

