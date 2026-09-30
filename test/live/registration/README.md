# registration TB

- `registration_http_six_step_tb.py`：真实 HTTP 六步（apply→validate→probe→deploy→verify→commit），
  覆盖乱序拒绝、update/delete、前五步零落盘。
- `registration_py27_tb.py`：X4-① 的 Python 2.7 端到端注册；第 3 步校验 py27、
  第 4 步确认 setup 引用 `ramic_bridge_daemon_27.py`，第 5 步用 py27 协议兼容 fake
  daemon 跑双冒烟后 commit。环境不满足 py27/SSH 时第 1 步写 `environment_failed` 并退出。
- `registration_role_split_tb.py`：P3 五 role 跨主机注册；gui/daemon/spectre→wsl，
  command/file→w1，commit 后再用真实中层验证 command/skill/file 的落点。
- `registration_real_ciw_tb.py`：P4 真 CIW 第 5 步注册；用测试侧
  `start_disposable_ciw.sh` + `ciw_load_setup.py` 把第 4 步 setup 注入 CIW，
  第 5 步连接真实 daemon 后 commit。
- `registration_hostkey_rotation_tb.py`：P5 host-key 轮换（w4 独占，需
- `control_plane_tb.py`：控制面（8124）常规通道 + **bug 报告通道**真机 TB ——
  只读管理面（status/users/user/config/reload）、无 admin→401、管理页 `/help` 自描述完整性、
  `HEAD/PATCH→405+Allow`、以及 `POST /api/bug` 正例（200+落盘+**凭据打码**+status/logs 有界）
  与负例（无/无效 token→400 且**零落盘**）。用法：
  `PYTHONPATH=src python test/live/registration/control_plane_tb.py --out test/artifacts/evidence/round9/control-plane-tb.json`
  （需 `test/artifacts/admin-token.txt`；2026-09-30 实测 7/7 绿）。
- `control_plane_write_tb.py`：控制面**写通道**（在**一次性实例**上做，保护常驻注册表）——
  `POST /api/user/<u>/update`（runtime/roles 值级读回、显式指纹迁移、未知 endpoint 拒绝且零落盘）、
  `PUT /api/config`（GET 一致 + 落盘一致）、`DELETE /api/user/<u>`（列表消失 + 详情 404）
  与 404/400/401 负例。用法：
  `PYTHONPATH=src python test/live/registration/control_plane_write_tb.py --out test/artifacts/evidence/round9/control-plane-write-tb.json`
  （需 `test/artifacts/admin-token.txt`；2026-09-30 实测 8/8 绿）。
  `w4_hostkey_cycle.sh` 的 use-b/restore）：轮换期 verify 必须 ERROR 且零落盘，
  恢复后原样重试必须转绿；update 改 role host 时按首信任重建指纹，显式
  `expected_fingerprint` 不被覆盖（§6.5）。
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
