# `test/semi/` —— 半真机级

> **级别：半真机测试**（需要真机环境，但**不一定完整运行**；用于过程调试、环境确认与单点定位）。
> 判定与目录映射见 [`../docs/测试架构.md`](../docs/测试架构.md) §2。

## 内容

| 子目录 | 放什么 | 说明 |
|---|---|---|
| `probes/` | 环境、工具链、包、单阶段探针（只读/一次性） | 原 `test/tb/probes` |
| `fakevirt/` | fake Virtuoso / CIW 测试替身 | 替掉 CIW，daemon 与链路为真 |
| `registration/` | `cov_registration_real.py`：注册 **1–4 步**（不 commit） | 覆盖前段流程与零落盘 |
| `transport/` | `log_matrix_real_tb.py`（CDS.log 单点矩阵）、`one_shot_burst_tb.py`（通道突发）、`ssh_backend_semi_tb.py`（OpenSSH/Paramiko 传输原语）、`role_credential_isolation_tb.py`（按 role 分离凭据） | 真机单点，不构成完整用户流程 |

## 怎么跑

```powershell
$env:PYTHONPATH='src'
python test/semi/probes/calibre_env_probe.py --work-dir test/artifacts/env/log-vblog --token vb-vblog --facts
python test/semi/probes/lone_surrogate_probe.py                    # 协议健壮性复现件
python test/semi/registration/cov_registration_real.py --work-dir test/artifacts/env/cov-registration `
    --user covreg --token cov-token --port 65112
python test/semi/transport/log_matrix_real_tb.py --work-dir test/artifacts/env/log-vblog --token vb-vblog
python test/semi/transport/one_shot_burst_tb.py  --work-dir test/artifacts/env/one-shot-burst `
    --token vb-vblog --out test/artifacts/evidence/one-shot-burst-green.json
# 传输原语：真实 sshd，不需要 Virtuoso；两个后端 × 持久/一次性 shell 共 48 例
python test/semi/transport/ssh_backend_semi_tb.py `
    --host wsl-gent --ssh-user Gent --out test/artifacts/evidence/ssh-backend-semi.json
# 按 role 分离凭据：用环境里已整理的双钥（id_ed25519 / vbuser2_ed25519）
python test/semi/transport/role_credential_isolation_tb.py `
    --out test/artifacts/evidence/role-credential-isolation.json
```

## 纪律

- 半真机结论**不能**当作验收结论：它回答"这一步对不对/哪里坏了"；
- 需要真机的脚本必须在 docstring 写清前置环境，缺环境时**明确失败**而不是静默跳过；
- 产物路径按 [`../docs/文件使用规范.md`](../docs/文件使用规范.md)：远端写注册表 `roles.<role>.root`，证据写 `test/artifacts/`。
