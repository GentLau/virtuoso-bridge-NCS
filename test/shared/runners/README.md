# `test/shared/runners/` —— 运行与复算脚本

- `run_coverage.ps1`：当前准出集合的覆盖率 + fail-fast 门禁。
- `run_main_coverage.ps1`：主覆盖率复算（隔离 `COVERAGE_FILE`，产出 text/json/分支报告与证据包）。
- `run_package_e2e.ps1`：上层包 E2E 编排（逐套件日志 + `summary.json`）。
- `run_all_http.py`：上层包 HTTP E2E 全量套件。
- `coverage_evidence.py` / `classify_uncovered.py`：覆盖率证据包与未覆盖行自动分类。
- `env_up.py` / `registry_add_user.py`：环境与注册表准备。
- `ops_matrix.py`：列出上层包已注册 operation。
- `ops_used.py`：运行上层套件并统计 operation 覆盖。
- `scenario.py`：按场景名驱动的入口。

上述脚本都从**仓库根目录**运行（`parents[3]` / `$PSScriptRoot\..\..\..`），
命令见 [`../../README.md`](../../README.md) 与三级 README。
运行产物一律落 `test/artifacts/{env,evidence,tmp}/`，脚本自身不写仓库根。
