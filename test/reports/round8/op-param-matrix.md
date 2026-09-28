# 操作 × 参数覆盖矩阵（机器，AST 解析；**不是覆盖结论**）

- 条目 628：CANDIDATE 529 / GAP 70 / NO-OP-TB 29
- 非 CANDIDATE 中：通用 `timeout` 字段 38 条（由 `test/offline/unit/test_param_timeout_contract.py` 的 79/79 op 合同承担）；其余 61 条为逐 op 缺口。
- 无法静态解析的调用点 76 个（不计覆盖，需人工复核）
- CANDIDATE = 参数名在目标 op 的调用点出现；是否断言语义仍要逐条看 TB 判据。
- op 调用点清单见 `op-coverage.json`；未解析明细见本文件末尾。

## 非 CANDIDATE（按 op 分组）

### `calibre.drc`

- [GAP] `cdl` (str | None, required=False) — op_tb_files=5
- [GAP] `fmt` (str, required=False) — op_tb_files=5
- [GAP] `hcell_file` (str | None, required=False) — op_tb_files=5
- [GAP] `lvs_run_dir` (str | None, required=False) — op_tb_files=5
- [GAP] `runset` (str | None, required=False) — op_tb_files=5
- [GAP] `spice_file` (str | None, required=False) — op_tb_files=5
- [GAP] `xcell_file` (str | None, required=False) — op_tb_files=5

### `calibre.export`

- [NO-OP-TB] `items` (tuple[str, ...], required=False) — op_tb_files=0
- [NO-OP-TB] `job_id` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `kind` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `local_dir` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `run_dir` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `token` (str, required=True) — op_tb_files=0

### `calibre.lvs`

- [GAP] `fmt` (str, required=False) — op_tb_files=6
- [GAP] `ground` (str | None, required=False) — op_tb_files=6
- [GAP] `lvs_run_dir` (str | None, required=False) — op_tb_files=6
- [GAP] `power` (str | None, required=False) — op_tb_files=6

### `calibre.pex`

- [NO-OP-TB] `blocking` (bool, required=False) — op_tb_files=0
- [NO-OP-TB] `calibre_bin` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `cdl` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `deck` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `fmt` (str, required=False) — op_tb_files=0
- [NO-OP-TB] `gds` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `ground` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `hcell_file` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `hier` (bool, required=False) — op_tb_files=0
- [NO-OP-TB] `job_id` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `lvs_run_dir` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `params` (dict[str, str] | None, required=False) — op_tb_files=0
- [NO-OP-TB] `poll_interval` (float, required=False) — op_tb_files=0
- [NO-OP-TB] `power` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `run_dir` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `runset` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `spice_file` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `token` (str, required=True) — op_tb_files=0
- [NO-OP-TB] `top` (str | None, required=False) — op_tb_files=0
- [NO-OP-TB] `turbo` (int, required=False) — op_tb_files=0
- [NO-OP-TB] `xcell_file` (str | None, required=False) — op_tb_files=0

### `virtuoso.layout.read`

- [GAP] `depth` (int, required=False) — op_tb_files=10

### `virtuoso.maestro.close_gui`

- [GAP] `view` (str, required=False) — op_tb_files=1

### `virtuoso.maestro.export`

- [GAP] `view` (str, required=False) — op_tb_files=3

### `virtuoso.maestro.open_gui`

- [GAP] `view` (str, required=False) — op_tb_files=2

### `virtuoso.maestro.open_waveform_gui`

- [GAP] `view` (str, required=False) — op_tb_files=2

### `virtuoso.maestro.read_config`

- [GAP] `view` (str, required=False) — op_tb_files=1

### `virtuoso.maestro.read_history`

- [GAP] `view` (str, required=False) — op_tb_files=3

### `virtuoso.maestro.read_results`

- [GAP] `view` (str, required=False) — op_tb_files=1

### `virtuoso.maestro.run`

- [GAP] `view` (str, required=False) — op_tb_files=1

### `virtuoso.maestro.write`

- [GAP] `view` (str, required=False) — op_tb_files=2

### `virtuoso.maestro.write_history`

- [GAP] `view` (str, required=False) — op_tb_files=1

### `virtuoso.verilog.export`

- [GAP] `recursive` (bool, required=False) — op_tb_files=1

### `virtuoso.verilog.import`

- [GAP] `file_is_local` (bool, required=False) — op_tb_files=1
- [GAP] `functional_view` (str, required=False) — op_tb_files=1
- [GAP] `ground_net` (str, required=False) — op_tb_files=1
- [GAP] `import_lib_cells` (int, required=False) — op_tb_files=1
- [GAP] `overwrite` (bool, required=False) — op_tb_files=1
- [GAP] `power_net` (str, required=False) — op_tb_files=1
- [GAP] `ref_libs` (list[str], required=False) — op_tb_files=1
- [GAP] `schematic_view` (str, required=False) — op_tb_files=1
- [GAP] `symbol_view` (str, required=False) — op_tb_files=1

### `virtuoso.verilog.read`

- [GAP] `view_type` (str, required=False) — op_tb_files=1

### `virtuoso.verilog.write`

- [GAP] `view_type` (str, required=False) — op_tb_files=1

## 未解析调用点（机器，不计覆盖）

- test/offline/core/api_server_tb.py:235 `` (how=payload-dict, params=token)
- test/offline/core/api_server_tb.py:300 `` (how=payload-dict, params=token)
- test/offline/core/api_server_tb.py:396 `` (how=payload-dict, params=token)
- test/offline/core/api_server_tb.py:281 `` (how=payload-dict, params=cmd,token)
- test/offline/core/api_server_tb.py:447 `` (how=payload-dict, params=token)
- test/offline/core/api_server_tb.py:429 `` (how=payload-dict, params=token)
- test/offline/unit/test_api_server_main.py:398 `` (how=payload-dict, params=token)
- test/offline/unit/test_middle_contracts.py:167 `` (how=payload-dict, params=timeout,token)
- test/offline/unit/test_norm_gap_batch2.py:257 `` (how=payload-dict, params=doc_root,query,request_id,source,token)
- test/offline/unit/test_param_timeout_contract.py:174 `` (how=payload-dict, params=timeout,token)
- test/offline/unit/test_round8_clause_gaps.py:93 `` (how=payload-dict, params=request_id,token,value)
- test/offline/unit/test_top_layer_dispatch.py:67 `` (how=payload-dict, params=token,value)
- test/offline/unit/test_top_layer_dispatch.py:89 `` (how=payload-dict, params=token)
- test/offline/unit/test_top_layer_dispatch.py:94 `` (how=payload-dict, params=token,value)
- test/offline/unit/test_top_layer_dispatch.py:101 `` (how=payload-dict, params=token)
- test/offline/unit/test_top_layer_dispatch.py:107 `` (how=payload-dict, params=token)
- test/offline/unit/test_top_layer_pool.py:61 `` (how=payload-dict, params=token)
- test/semi/probes/calibre_package_http_probe.py:111 `f"calibre.{args.kind}"` (how=helper:call, params=token)
- test/semi/probes/calibre_package_http_probe.py:64 `` (how=payload-dict, params=token)
- test/semi/probes/cdl_export_variants_probe.py:69 `` (how=payload-dict, params=token)
- test/semi/probes/gds_publish_path_edges_probe.py:46 `` (how=payload-dict, params=token)
- test/semi/probes/gds_then_skill_probe.py:53 `` (how=payload-dict, params=token)
- test/semi/probes/layout_p044_second_write_probe.py:98 `` (how=payload-dict, params=token)
- test/semi/probes/maestro_export_include_results_probe.py:54 `operation` (how=helper:call, params=token)
- test/semi/probes/maestro_screenshot_probe.py:34 `` (how=payload-dict, params=token)
- test/semi/probes/maestro_screenshot_probe.py:40 `operation` (how=helper:api_call, params=token)
- test/semi/probes/shared_cdf_pollution_probe.py:51 `` (how=payload-dict, params=token)
- test/semi/probes/spectre_ac_pipeline_probe.py:62 `` (how=payload-dict, params=token)
- test/semi/probes/twouser_same_view_probe.py:66 `` (how=payload-dict, params=token)
- test/semi/probes/_maestro_tb.py:43 `operation` (how=helper:call, params=timeout,token)
- test/semi/probes/_maestro_tb.py:29 `` (how=payload-dict, params=token)
- test/live/flows/design_iterate_tb.py:173 `` (how=payload-dict, params=token)
- test/live/flows/design_iterate_tb.py:180 `` (how=payload-dict, params=token)
- test/live/flows/lvs_from_schematic_tb.py:75 `` (how=payload-dict, params=token)
- test/live/flows/multiuser_layout_handoff_tb.py:56 `` (how=payload-dict, params=token)
- test/live/flows/project_flow_tb.py:129 `` (how=payload-dict, params=token)
- test/live/flows/s11_full_flow.py:61 `` (how=payload-dict, params=token)
- test/live/flows/serdes_rx_flow_tb.py:103 `` (how=payload-dict, params=token)
- test/live/packages/calibre_e2e_tests.py:106 `` (how=payload-dict, params=token)
- test/live/packages/calibre_e2e_tests.py:131 `f"calibre.{kind}"` (how=helper:_value, params=token)
- test/live/packages/calibre_e2e_tests.py:113 `operation` (how=helper:_op, params=token)
- test/live/packages/calibre_params_e2e_tests.py:61 `` (how=payload-dict, params=token)
- test/live/packages/calibre_params_e2e_tests.py:65 `operation` (how=helper:_op, params=token)
- test/live/packages/cellview_e2e_tests.py:93 `` (how=payload-dict, params=token)
- test/live/packages/cellview_e2e_tests.py:97 `operation` (how=helper:_call, params=token)
- test/live/packages/cellview_e2e_tests.py:109 `operation` (how=helper:_call, params=token)
- test/live/packages/cellview_e2e_tests.py:277 `operation` (how=helper:_expect_fail, params=token)
- test/live/packages/cellview_e2e_tests.py:105 `operation` (how=helper:_op, params=token)
- test/live/packages/gui_e2e_tests.py:81 `` (how=payload-dict, params=token)
- test/live/packages/infra_e2e_tests.py:98 `` (how=payload-dict, params=token)
- test/live/packages/layout_e2e_tests.py:80 `` (how=payload-dict, params=token)
- test/live/packages/layout_e2e_tests.py:87 `operation` (how=helper:_op, params=token)
- test/live/packages/layout_geometry_classification_e2e_tests.py:63 `` (how=payload-dict, params=)
- test/live/packages/layout_geometry_classification_e2e_tests.py:71 `` (how=payload-dict, params=)
- test/live/packages/maestro_e2e_tests.py:87 `` (how=payload-dict, params=token)
- test/live/packages/maestro_e2e_tests.py:97 `operation` (how=helper:_op, params=token)
- test/live/packages/schematic_e2e_tests.py:86 `` (how=payload-dict, params=token)
- test/live/packages/schematic_e2e_tests.py:93 `operation` (how=helper:_op, params=token)
- test/live/packages/screenshot_params_e2e_tests.py:72 `` (how=payload-dict, params=token)
- test/live/packages/screenshot_params_e2e_tests.py:76 `operation` (how=helper:_op, params=token)
- test/live/packages/screenshot_params_e2e_tests.py:80 `operation` (how=helper:_op, params=token)
- test/live/packages/skillref_e2e_tests.py:74 `` (how=payload-dict, params=token)
- test/live/packages/spectre_e2e_tests.py:76 `` (how=payload-dict, params=token)
- test/live/packages/spectre_e2e_tests.py:83 `operation` (how=helper:_op, params=token)
- test/live/packages/spectre_params_e2e_tests.py:105 `` (how=payload-dict, params=token)
- test/live/packages/spectre_params_e2e_tests.py:113 `` (how=payload-dict, params=token)
- test/live/packages/symbol_e2e_tests.py:76 `` (how=payload-dict, params=token)
- test/live/packages/symbol_e2e_tests.py:83 `operation` (how=helper:_op, params=token)
- test/live/packages/veriloga_e2e_tests.py:94 `` (how=payload-dict, params=token)
- test/live/packages/veriloga_e2e_tests.py:101 `operation` (how=helper:_op, params=token)
- test/live/packages/verilog_e2e_tests.py:105 `` (how=payload-dict, params=token)
- test/live/packages/verilog_e2e_tests.py:112 `operation` (how=helper:_op, params=token)
- test/live/stress/layout_multiuser_lock_tb.py:51 `` (how=payload-dict, params=token)
- test/shared/fixtures/probe.py:13 `` (how=payload-dict, params=token)
- test/shared/fixtures/probe.py:24 `op` (how=helper:call, params=token)
- test/shared/runners/env_check.py:62 `` (how=payload-dict, params=token)

