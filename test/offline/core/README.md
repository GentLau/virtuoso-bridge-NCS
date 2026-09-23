# core TB

确定性、可离线运行的契约与协议 TB：

- `api_server_tb.py`：顶层 HTTP、调度、响应壳、线程池拒绝与 429 恢复。
- `semantics_tb.py`：文件 deadline、注册表跨进程写、安装崩溃安全、query 形状。
- `fault_injection_tb.py`：租约竞态、shell permit、transport kind、日志参数、缓存失效。
- `daemon_log_protocol_tb.py`：daemon 日志协议矩阵（off/分级/轮转/降级/截断）。

运行方式见 [`../README.md`](../README.md)。产物只写 `../artifacts/`。
