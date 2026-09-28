# registration TB

- `registration_http_six_step_tb.py`：真实 HTTP 六步（apply→validate→probe→deploy→verify→commit），
  覆盖乱序拒绝、update/delete、前五步零落盘。
- `registration_py27_tb.py`：X4-① 的 Python 2.7 端到端注册；第 3 步校验 py27、
  第 4 步确认 setup 引用 `ramic_bridge_daemon_27.py`，第 5 步用 py27 协议兼容 fake
  daemon 跑双冒烟后 commit。环境不满足 py27/SSH 时第 1 步写 `environment_failed` 并退出。
- `cov_registration_real.py`：注册 1–4 步 coverage TB。
- `test/semi/registration/registration_failure_matrix_tb.py`：X4-③ 的六步失败/重试矩阵
  （自包含本地 fake，无外部环境；覆盖每步失败零落盘、原样重试、cancel 后重 apply、
  服务重启清候选）。

## Linux 客户端（X4-②）

`registration_http_six_step_tb.py` 不依赖 Windows；在 wsl-gent 侧 checkout 后可直接跑
本地模式（推荐）：

```bash
cd /home/Gent/.virtuoso-bridge/tb-sixstep/repo
# 需要把本机 test/artifacts/admin-token.txt 带到 Linux 侧（或设置 VB_ADMIN_TOKEN）；
# 它是 gitignored 的管理凭据，不要入库。
PYTHONPATH=src python3 test/live/registration/registration_http_six_step_tb.py \
  --work-dir test/artifacts/env/reg-six-local \
  --local-mode \
  --out test/artifacts/evidence/tb-sixstep-20260928/registration-six-local-linux.json
```

远程模式仍需目标 SSH/py3 可达；Linux 客户端不是新的 TB 文件，而是同一份 TB 的平台矩阵。

远端一次性文件只允许放注册表 root 下的 `tmp/`；本地一次性 root 放在
`--work-dir/local-root-*`，运行结束清理。
