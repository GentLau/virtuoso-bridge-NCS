# 布局说明（2026-09-23）

本证据包生成于 **2026-09-22**，当时 `test/` 还是旧布局（`test/unit`、`test/tb/*`）。
包内的路径字段（`source_json`、逐行 TSV 的文件名等）指向旧布局；**数字本身仍然有效**
（同一批用例、同一批 TB 在同一台机器上的实测）。

2026-09-23 已按三级重组：`test/offline/{unit,integration,scenario,core,frontend}`、
`test/semi/{probes,fakevirt,registration,transport}`、`test/live/{registration,transport,packages,e2e,stress,flows}`；
跨级资产在 `test/shared/{fixtures,runners,standards,archive}`，运行数据在
`test/artifacts/{env,evidence,tmp}`，报告在 `test/reports/`。
需要与新布局完全一致的覆盖率数字时重跑：

```powershell
powershell -NoProfile -File test/shared/runners/run_main_coverage.ps1
```
