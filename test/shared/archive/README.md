# `test/shared/archive/` —— 历史脚本（非准出）

历史脚本，保留用于调查、复现和迁移参考。它们可能仍引用旧 schema、旧端口、
旧靶机目录或已废弃的接口，**不进入准出集合**。

若某个 legacy 脚本重新纳入准出，必须先：

1. 按当前 spec 重写接口与路由假设；
2. 把远端 scratch 改到注册表 root 或显式 `--root`；
3. 在 `test/shared/runners/run_coverage.ps1` 或新的准出 runner 中登记；
4. 重新生成红/绿证据并更新测试报告。

## 2026-09-30 归档批次（被现有 TB / 新探针取代，**不要**再当准出跑）

| 归档文件 | 取代它的东西 |
|---|---|
| `daemon_internal_error_path_probe.py` | `test/semi/probes/py27_remote_runtime_probe.py`（真 py2.7 下 `_read_frame` ValueError → 静默丢弃，P-039 口径；py3 猴补丁结论不可信） |
| `p076_spectre_run_hang_probe.py` | `test/semi/probes/p076_fix_verify_probe.py`（修复后复验）+ `spectre_params_e2e_tests` |
| `spectre_channel_map_probe.py` | `test/live/packages/spectre_e2e_tests.py`（P-076 已关闭；channel 映射属一次性诊断） |
| `maestro_batch2_verify_probe.py` | `test/live/packages/maestro_e2e_tests.py`（P-091/P-101 回归已并入）+ `verilog_import_params_e2e_tests` |
| `maestro_bugfix_batch_probe.py` | `test/live/packages/maestro_e2e_tests.py`（P-084/087/088/089/095 相关断言已并入） |
| `verilog_cell_and_views_direct_probe.py` | `test/live/packages/verilog_import_params_e2e_tests.py`（P-099/P-100） |

> 归档判据：既不在任何 runner/门禁里，也不被其它 TB 引用，且其断言已被现有 TB 覆盖。
> 之后若要重新纳入准出，按上面 4 步走。
