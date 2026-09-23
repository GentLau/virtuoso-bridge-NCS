# packages TB

上层 `pyapi.packages.*` 的真机 E2E 套件，统一支持 `--transport direct|http`：

`infra`、`cellview`、`schematic`、`symbol`、`layout`、`verilog`、`veriloga`、
`skillref`、`spectre`、`maestro`。

统一入口是 [`../../shared/runners/run_all_http.py`](../../shared/runners/run_all_http.py)。
本目录只做测试编排，不修改上层业务包实现。
