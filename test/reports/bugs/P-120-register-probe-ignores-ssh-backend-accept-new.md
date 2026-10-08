# P-120 · 注册 probe **忽略** apply 里的 `ssh_backend`（永远 paramiko）；而 paramiko 又拒绝 `StrictHostKeyChecking=accept-new` → 用户即使选了 openssh 后端，只要 ssh config 是 accept-new 就注册不了

| 字段 | 值 |
|---|---|
| 级别 | P3（一致性缺陷：apply 收 `ssh_backend` 但 probe 不用 → 用户按文档选 openssh 也无法绕过 paramiko 的限制；`accept-new` 的 env 要求本身已在 `test/docs/环境与场景.md:110` 写明） |
| 层 | 注册流程（register/flow）· SSH 后端选择与 ssh-config 兼容性 |
| 归属 | 设计侧（`register/flow.py::_new_runner` 透传 `ssh_backend`/`tool_override`；accept-new 的错误文案可加一句「改 ssh config 为 yes/ask 或换 openssh 后端」） |
| 状态 | **待设计修** |
| 位置 | `src/register/flow.py:458-476`（`_new_runner()` 构造 `SSHRunner(...)` 不传 `backend=` → `src/common/ssh.py:298` 默认 paramiko）；`src/register/models.py:156`（apply 收 `ssh_backend`）与 `flow.py:439-441`（只写进候选 entry，不影响 probe）；`src/common/paramiko_backend.py:810-822`（accept-new 结构化拒绝） |
| 首报 | 2026-09-30（round10 注册全量：hostkey 轮换 TB 初跑红，逐层定位到 probe 无视 ssh_backend + paramiko 拒绝 accept-new） |
| 最近更新 | 2026-10-08 12:25（A/B 对照复现取证；TB 增 `--key-dir/--key/--ssh-backend` 供回归） |

## 现象

真机（round10，w4-gent，2026-09-30）：客户端 `~/.ssh/config` 的 w4 条目为 `StrictHostKeyChecking accept-new`（OpenSSH 常用写法）时，`registration_hostkey_rotation_tb` 第 3 步 probe 报 `Paramiko backend requires recorded host keys; StrictHostKeyChecking='accept-new' is not supported for host 'w4-gent' (supported: yes/ask/true)` → 注册失败；在第 1 步 apply 里显式给 `ssh_backend="openssh"`（apply 返回 200、候选 entry 也是 openssh）后，第 3 步 probe **仍然**报同一个 paramiko 错误 —— 证明 probe 没用候选的后端选择。

## 复现

```text
1) 把 w4（或任一 host）的客户端 ssh config 设为 `StrictHostKeyChecking accept-new`；
2) `PYTHONPATH=src python test/live/registration/registration_hostkey_rotation_tb.py --work-dir test/artifacts/env/reg-hostkey-r10`；
3) 观察第 3 步结构性失败；再在 apply body 里加 `ssh_backend:"openssh"` 复跑，错误不变。
```

## 证据

**2026-10-08 重新取证（A/B 对照，专用复现，不再依赖会被覆盖的
轮换 TB 快照）**：
* A：默认后端(paramiko) + w4 ssh config=`accept-new` → step1 apply 200、step2 validate 200、**step3 probe stage=failed**（原文 `Paramiko backend requires recorded host keys; StrictHostKeyChecking='accept-new' is not supported for host 'w4-gent' (supported: yes/ask/true)`）→ rc=2 —— `test/artifacts/evidence/verify-p120/paramiko-accept-new.{json,log}`
* B：**同一链路显式 `ssh_backend="openssh"`** + accept-new → step1 apply 200（后端声明被接受）、**step3 probe 仍报同一个 paramiko 错误** → rc=2 —— `verify-p120/openssh-requested-accept-new.{json,log}`
（复现用的客户端 ssh config 已在 `finally` 里还原成 `yes`，见卡尾命令）
* 环境归位后同一套件（hostkey 轮换 TB）**17/17 绿**：`round10/registration/hostkey_rotation.json`；源码锚点见 where

## 验收判据（修好即转绿）

① probe 使用**候选 entry 的** `ssh.backend`（含 `tool_override`）；② `accept-new` 二选一：paramiko 支持（映射 AutoAddPolicy）或在错误里明确指路“把该 host 的 ssh config 改成 `yes/ask`，或选 `ssh_backend=openssh`”；③ 回归：注册 TB 在 paramiko/openssh × yes/accept-new 四种组合下结论一致、无静默降级。

## 下一步 / 责任人

等设计修（核心是 probe 透传 backend）。测试侧已把 w4 的客户端 ssh config 改回 `yes`（符合 `环境与场景.md:110`，且 host-key 轮换判据要求换 key 必须被拒），改后 TB **17/17 绿**。
**修好后用同一条命令做回归**：`registration_http_six_step_tb.py --host w4-gent --ssh-user dev --key-dir C:/wsl/shared/keys --key lab_ed25519 --ssh-backend openssh` + ssh config=`accept-new` → step3 必须**通过**（probe 真用了 openssh）；同时 paramiko+accept-new 组合仍应结构化拒绝并指路。

## 复现命令（2026-10-08 实测，捕获 A/B 两条证据）

```powershell
# ① 临时把 w4 的客户端 ssh config 改成 accept-new（先备份，finally 还原）
# ② A：默认 paramiko
PYTHONPATH=src python test/live/registration/registration_http_six_step_tb.py \
  --work-dir test/artifacts/env/p120-a --user vbw4p120a --host w4-gent --ssh-user dev \
  --root /home/dev/.virtuoso-bridge/vbw4p120a --daemon-port 65181 \
  --key-dir C:/wsl/shared/keys --key lab_ed25519 --stop-after-deploy \
  --out test/artifacts/evidence/verify-p120/paramiko-accept-new.json
# ③ B：显式声明 openssh 后端（声明被 apply 接受，但 probe 仍走 paramiko → 同一个错误）
PYTHONPATH=src python test/live/registration/registration_http_six_step_tb.py \
  --work-dir test/artifacts/env/p120-b --user vbw4p120b --host w4-gent --ssh-user dev \
  --root /home/dev/.virtuoso-bridge/vbw4p120b --daemon-port 65182 \
  --key-dir C:/wsl/shared/keys --key lab_ed25519 --ssh-backend openssh --stop-after-deploy \
  --out test/artifacts/evidence/verify-p120/openssh-requested-accept-new.json
# ④ 还原客户端 ssh config（脚本在 finally 里做，并打印还原后的 w4 条目）
```

* 静态根因（两条独立证据）：`register/flow.py::_new_runner()` 构造 `SSHRunner(...)` **不传 `backend=`**（默认 paramiko）；`flow.py` 里 `ssh_backend` 只被 `_apply_policies()` 写进**候选 entry**，probe 从不读它。
* 本轮为跑这条复现，给 `registration_http_six_step_tb.py` 增加了 `--key-dir/--key/--ssh-backend` 三个参数
（默认值保持原行为 `~/.ssh` + `id_ed25519`、不传 `ssh_backend`），修好后可直接做四组合回归。
---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
