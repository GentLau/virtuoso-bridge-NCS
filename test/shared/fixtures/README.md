# `test/shared/fixtures/` —— 跨级夹具

被多级复用的夹具与客户端工具，**自身不产出验收结论**：

- `_win.py`：Windows 子进程隐藏窗口参数。
- `_daemon_harness.py`：CIW/daemon wire 协议脚本化夹具。
- `fake_daemon_host.py`：协议级 fake daemon 群。
- `stress_client.py`：HTTP 并发客户端。
- `probe.py`：单次 operation 探针。

使用者：`test/offline/core/*_tb.py`（daemon 夹具）、`test/live/stress/*`、`test/live/flows/*`、
`test/live/registration/*`、`test/shared/archive/*`（历史脚本）。
路径约定：调用方用 `Path(__file__).resolve().parents[2] / "shared" / "fixtures"` 取本目录；
**修改夹具后至少跑** `python -m pytest test/offline/unit test/offline/integration test/offline/scenario`。
