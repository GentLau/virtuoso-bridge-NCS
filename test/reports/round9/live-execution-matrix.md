# 真机 TB 执行矩阵（机器结论，脚本生成）

- live TB 总数 **53**；HTTP 门禁套件 **23**
- **既不在门禁、又没有任何文件引用** 的 TB：**0**
- 今天（2026-09-29）在 `test/artifacts/` 里找不到证据的 TB：**0**

| TB | 门禁 | 被引用数 | 今日证据 |
|---|---|---|---|
| `test/live/e2e/test_business_local_live.py` | — | 3 | ✅ |
| `test/live/e2e/test_business_remote_live.py` | — | 3 | ✅ |
| `test/live/e2e/test_e2e_live.py` | — | 6 | ✅ |
| `test/live/flows/adc_sar_flow_tb.py` | — | 2 | ✅ |
| `test/live/flows/design_iterate_tb.py` | — | 5 | ✅ |
| `test/live/flows/lvs_from_schematic_tb.py` | — | 2 | ✅ |
| `test/live/flows/multihop_jump_tb.py` | — | 2 | ✅ |
| `test/live/flows/multiuser_layout_handoff_tb.py` | — | 1 | ✅ |
| `test/live/flows/multiuser_serdes_rx_tb.py` | — | 1 | ✅ |
| `test/live/flows/project_flow_tb.py` | — | 5 | ✅ |
| `test/live/flows/role_split_tb.py` | — | 5 | ✅ |
| `test/live/flows/s11_full_flow.py` | — | 6 | ✅ |
| `test/live/flows/s11_inprocess_lvs_tb.py` | — | 2 | ✅ |
| `test/live/flows/s11_postsim_compare.py` | — | 2 | ✅ |
| `test/live/flows/scale_100_tb.py` | — | 4 | ✅ |
| `test/live/flows/serdes_rx_flow_tb.py` | — | 2 | ✅ |
| `test/live/manual/business_console/serve.py` | — | 2 | ✅ |
| `test/live/packages/calibre_e2e_tests.py` | ✅ | 8 | ✅ |
| `test/live/packages/calibre_export_pex_e2e_tests.py` | ✅ | 2 | ✅ |
| `test/live/packages/calibre_params_e2e_tests.py` | ✅ | 3 | ✅ |
| `test/live/packages/cellview_e2e_tests.py` | ✅ | 3 | ✅ |
| `test/live/packages/gui_e2e_tests.py` | ✅ | 1 | ✅ |
| `test/live/packages/infra_e2e_tests.py` | ✅ | 6 | ✅ |
| `test/live/packages/layout_e2e_tests.py` | ✅ | 7 | ✅ |
| `test/live/packages/layout_geometry_classification_e2e_tests.py` | ✅ | 1 | ✅ |
| `test/live/packages/maestro_e2e_tests.py` | ✅ | 9 | ✅ |
| `test/live/packages/maestro_mc_e2e_tests.py` | ✅ | 6 | ✅ |
| `test/live/packages/maestro_nested_keys_e2e_tests.py` | ✅ | 1 | ✅ |
| `test/live/packages/maestro_view_param_e2e_tests.py` | ✅ | 3 | ✅ |
| `test/live/packages/nested_keys_e2e_tests.py` | ✅ | 3 | ✅ |
| `test/live/packages/schematic_e2e_tests.py` | ✅ | 2 | ✅ |
| `test/live/packages/screenshot_params_e2e_tests.py` | ✅ | 2 | ✅ |
| `test/live/packages/skill_log_options_e2e_tests.py` | — | 1 | ✅ |
| `test/live/packages/skill_log_semantics_e2e_tests.py` | — | 2 | ✅ |
| `test/live/packages/skillref_e2e_tests.py` | ✅ | 4 | ✅ |
| `test/live/packages/spectre_e2e_tests.py` | ✅ | 3 | ✅ |
| `test/live/packages/spectre_params_e2e_tests.py` | — | 1 | ✅ |
| `test/live/packages/spectre_pvt_e2e_tests.py` | ✅ | 1 | ✅ |
| `test/live/packages/step_details_e2e_tests.py` | ✅ | 1 | ✅ |
| `test/live/packages/symbol_e2e_tests.py` | ✅ | 6 | ✅ |
| `test/live/packages/verilog_e2e_tests.py` | ✅ | 3 | ✅ |
| `test/live/packages/verilog_import_params_e2e_tests.py` | ✅ | 2 | ✅ |
| `test/live/packages/veriloga_e2e_tests.py` | ✅ | 4 | ✅ |
| `test/live/registration/registration_hostkey_rotation_tb.py` | — | 2 | ✅ |
| `test/live/registration/registration_http_six_step_tb.py` | — | 9 | ✅ |
| `test/live/registration/registration_py27_tb.py` | — | 3 | ✅ |
| `test/live/registration/registration_real_ciw_tb.py` | — | 1 | ✅ |
| `test/live/registration/registration_role_split_tb.py` | — | 1 | ✅ |
| `test/live/stress/layout_multiuser_lock_tb.py` | — | 3 | ✅ |
| `test/live/stress/multi_user_routing_tb.py` | — | 1 | ✅ |
| `test/live/stress/production_face_stress_tb.py` | — | 7 | ✅ |
| `test/live/stress/scale_local_fake_tb.py` | — | 2 | ✅ |
| `test/live/transport/cov_remote_real.py` | — | 12 | ✅ |
