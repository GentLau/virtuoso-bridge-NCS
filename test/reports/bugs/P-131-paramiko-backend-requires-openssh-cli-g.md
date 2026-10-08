# P-131 · 默认 paramiko 后端隐式依赖系统 `ssh -G`：无 OpenSSH CLI 的机器上 paramiko 后端构造即失败（注册 port-22 校验同样无回退）

| 字段 | 值 |
|---|---|
| 级别 | P2（无 OpenSSH 环境核心路径断；与「没有 openssh 也要可用」目标冲突） |
| 层 | 中层（`common/paramiko_backend.py`）+ 注册 probe · 无 OpenSSH CLI 机器的 SSH config 解析 |
| 归属 | 设计侧（给 `ParamikoSessionBackend._lookup` 加纯 Python config 解析回退，建议 `paramiko.SSHConfig`；注册 probe 的 `ssh_port_is_22`/`_ssh_config_hostname` 同样回退） |
| 状态 | **待设计修** |
| 位置 | `src/common/paramiko_backend.py:655-760`（`_lookup()` 用 `subprocess.run([self._ssh_cmd, "-G", ...])` 解析 config；`__init__:619` 构造时即调用 `_endpoint` → `_lookup`，`ssh` 缺失时 FileNotFoundError 直接冒出）；`src/register/probe.py:68-122`（`_ssh_config_hostname`/`ssh_port_is_22` 直接调 `ssh -G`，无 CLI 时 port-22 校验恒 False）；对照 `src/common/ssh.py:321`（`shutil.which("ssh") or "ssh"`） |
| 首报 | 2026-10-08（P-120 修复时发现） |
| 最近更新 | 2026-10-08（测试侧建卡） |

## 现象

机器未装 OpenSSH CLI 时，即使默认/显式选择 paramiko 后端，`SSHRunner`/`ParamikoSessionBackend` 构造就因 `ssh -G` 失败；注册第 3 步会先被 port-22 校验拒绝。paramiko 作为「无 OpenSSH 也可用」的后端，实际仍隐式依赖 OpenSSH CLI。

## 复现

```text
影子 PATH（保留 python、去掉 ssh）下构造 `SSHRunner(host="h", backend="paramiko")` → FileNotFoundError；`register.probe.ssh_port_is_22("h")` → False（即使目标就是 22 端口）。
```

## 证据

静态定位（2026-10-08，P-120 修复时发现）：`_lookup` 无 try/except OSError，`ssh -G` 是唯一 config 解析路径；现有离线用例只覆盖 probe 的 ssh-keygen/ssh-keyscan 回退（P-120），未覆盖 ssh 本体缺失。

## 验收判据（修好即转绿）

① 无 `ssh` CLI 时 paramiko 后端仍可解析 config 并建连（回退语义对齐 `ssh -G` 的目标子集：hostname/user/port/identityfile/proxyjump/known_hosts/stricthostkeychecking）；② 注册 port-22 校验同等回退；③ 影子 PATH 离线 TB 转绿；④ 有 CLI 时行为不变（现有用例全绿）。

## 下一步 / 责任人

测试侧先补影子 PATH 离线红钉；设计侧裁决实现路径（`paramiko.SSHConfig` 纯 Python 解析 vs 内置 `ssh -G` 等价器）后修复。


---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
