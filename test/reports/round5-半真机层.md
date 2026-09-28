# 第五轮 · 半真机层（root 直接执行）

> 说明：本轮原计划由独立线（r5_semi）产出，但截至 21:15 该线没有落盘任何证据，
> 为避免"半真机层无证据"，root 直接按同一口径把主干重跑了一遍。
> 环境：常驻 8 实例 + 业务面 8127（`resident_env_check` 8/8）；lab fake 在 w1-gent。
> 证据：`test/artifacts/evidence/round4-probes/round5-*.json`

## 1. 结果总览

| 项 | 结果 | 证据 |
|---|---|---|
| 按 role 分离 SSH 凭据（spec 新特性） | **8/8 PASS**：command role 用 vbuser2 自有钥、file role 用共享钥，两条连接各自认证为 `vbuser2`，指纹与 `ssh-keygen -lf` 交叉一致 | `round5-role-credential-isolation.json` |
| 凭据/注册相关离线单测 | **29 passed**（`test_credential_routing` / `test_ssh_credentials` / `test_registry_keys` / `test_reservation`） | 控制台输出（本轮） |
| 注册六步（本地，HTTP 全链） | **ok=true，18 项断言**：apply→validate→probe→deploy→verify→commit；**步骤 6 才落盘**；读回无 admin→401、有 admin→200；update 拒绝改 mode；delete；cancel→reapply | `round5-registration-six-step.json` |
| 注册 1–4（远端真机） | `stage=deployed, step=4`，**registry 零写入**、无 reservation 残留 | `round5-main/cov-registration-real.log`（r5_live 线） |
| CDS.log 增量矩阵（真机） | **ok=true，failed=0**：`log_grew=3040`、off 源 `off_log_len=0`、skill 基线输出正常 | `round5-log-matrix-real.json` |
| SKILL 语法/多行矩阵 | **10/10 PASS**（多行序列、多行注释、多行 errset/progn 等） | `round5-skill-syntax-matrix.json` |
| 一次性通道突发 | **failures=[]** | `round5-one-shot-burst.json` |
| SSH 双后端（paramiko + openssh） | **ok=true** | `round5-ssh-backend-semi.json` |
| 两用户同视图读写 | **ok=true**（vblog + vbs11，`schemtest/twouser_probe`） | `round5-twouser-same-view.json` |
| 协议级 fake 语义（w1-gent 两实例） | 通过业务面复测：`1/2`→0、`1.0/2`→0.5、`hiFlush()`→t、`boom()`→结构化 SKILL 错误（与真机 IC6.1.8 对照一致） | 控制台输出（本轮） |

## 2. 本轮半真机口径下发现的问题（测试侧）

| # | 现象 | 归因 | 处置 |
|---|---|---|---|
| S1 | `test/semi/probes/twouser_same_view_probe.py --token-b vb-vbs11` → `RuntimeError: invalid token` | **不是缺陷**：registry 里 `vbs11` 条目的 token 是 **`vb-s11`**（`vb-vbs11` 是常见笔误） | 用 `vb-s11` 复跑 → ok=true；已在报告注明，避免下一个执行者再踩 |
| S2 | `test/live/registration/registration_http_six_step_tb.py` 不带参数直接跑 → step 1 报 `daemon_port >= 1` | **不是缺陷**：该 TB 的 `--daemon-port 0` 只在 `--local-mode` 下表示自动分配；远端口径必须给具体端口 | 本地六步用 `--local-mode` 复跑通过；远端口径用 `cov_registration_real.py`（r5_live 线已跑） |
| S3 | 常驻 8129 `--work-dir test/artifacts/env/multi-user-real` 是**上一轮残留进程**（pid 36116） | 环境残留（非本轮代码问题） | 记录待清理，不影响本轮结论 |

## 3. 覆盖边界（不声称）

1. **`enhanced_token` 的跨 entry 复用**：本轮只到"离线规则单测 + 真实 role 凭据隔离"，
   没有在真机上做"两个真实账号复用同一把钥 + 令牌授权"的完整注册-复现；
2. **多跳 jump/proxy 组合**：环境只有单跳（矩阵 X1）；
3. **maestro 跨用户并发**：本轮只做了 schematic/layout 的两用户同视图与多用户锁，
   maestro 的会话冲突仍是设计侧探针口径。
