# transport TB

- `cov_remote_real.py`：五接口真机 coverage。
- `log_matrix_real_tb.py`：CDS.log 字节增量、off 源头、级别过滤、无注入。
- `one_shot_burst_tb.py`：一次性通道突发超过 `MaxSessions` 时不得暴露 transport 错误。
- `c06_flush_probe.py`：CIW `print` 行缓冲提交（C06）之一击探针。
- `disposable_ciw_c06_p086_tb.py`：可丢弃 CIW 上的 C06/P-086 真机闭环（起停 + 重启后恢复）。
- `delivered_timeout_recovery_tb.py`：**投递超时不得把实例永久置忙**（P-086 家族回归钉，
  独立 disposable `destb2/64601`；2026-09-30 修复 `97baf13` 后 5/5 绿）。用法：
  `PYTHONPATH=src python test/live/transport/delivered_timeout_recovery_tb.py --out test/artifacts/evidence/round9/delivered-timeout-recovery.json`

远端路径必须来自注册表或显式 `--root`，不得使用共享 `/tmp`。
