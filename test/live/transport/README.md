# transport TB

- `cov_remote_real.py`：五接口真机 coverage。
- `log_matrix_real_tb.py`：CDS.log 字节增量、off 源头、级别过滤、无注入。
- `one_shot_burst_tb.py`：一次性通道突发超过 `MaxSessions` 时不得暴露 transport 错误。

远端路径必须来自注册表或显式 `--root`，不得使用共享 `/tmp`。
