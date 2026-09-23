# `test/shared/` —— 跨级共享（不属于任何一级）

三级目录只放用例；被多级复用的代码、脚本与历史资产集中在这里。

| 子目录 | 放什么 |
|---|---|
| `fixtures/` | 夹具代码：`fake_daemon_host.py`（协议级 fake daemon 群）、`_daemon_harness.py`（daemon wire 脚本化）、`_win.py`（Windows 子进程隐藏窗口）、`stress_client.py`、`probe.py` |
| `runners/` | 运行与复算脚本：`run_coverage.ps1`、`run_main_coverage.ps1`、`run_package_e2e.ps1`、`run_all_http.py`、`env_up.py`、`registry_add_user.py`、覆盖度工具 |
| `standards/` | 规范指针（真源在 [`../docs/`](../docs/README.md)） |
| `archive/` | 重构前/一次性历史脚本（**非准出**，不作为送审证据） |

约定：`fixtures/` 与 `runners/` 的脚本一律从**仓库根目录**运行，路径取 `parents[3]`；
修改夹具后至少跑一遍离线层：`python -m pytest test/offline/unit test/offline/integration test/offline/scenario`。
