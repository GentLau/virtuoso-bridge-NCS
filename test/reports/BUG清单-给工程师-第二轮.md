# 第二轮测试 · 缺陷明细（给设计工程师，2026-09-23）

> **送修请用唯一一对**：[缺陷清单-上层.md](缺陷清单-上层.md) / [缺陷清单-其他.md](缺陷清单-其他.md)。
> 本文件是更细的技术叙述（含复现命令与验收标准），冲突时以 [问题登记.md](问题登记.md) 为准。

> 证据一律在 `test/artifacts/evidence/`；所有结论都可用仓库内命令复现。

> **2026-09-23 15:10 复核更新（先看这段）**：
> 1. 下面的 **P-045（并发挂死）已撤回**——真因是测试侧 `test/live/e2e/test_e2e_live.py` 的引导逻辑覆盖了正在服务的 CIW（新登记 P-046，测试侧认领修复），
>    干净实例上同形状复跑 **72/72 ok**；**不需要你们排查并发**；
> 2. **P-019 / P-025 / P-037 / P-013 已由你们修复并经我复核**（`lone_surrogate_probe.py` PASS、`log_rotation_lock_probe.py` PASS、
>    `paramiko_backend.py:738-751` 归一化、`ssh.py:477-483` + `middle.py:191-205/450/687` 回收），**请勿重复派工**；
> 3. **P-020 / P-041 / P-042 亦已修复并经复核**（`_spectre_util.py:674-681`、`verilog.py:273` + 用例已同步改、`layout.py:1008-1030`）；
> 4. 因此本文件实际仍需你们动的只有两条：**P-044（P1，layout 锁误判）** 与 **P-043（P2，一行 coding cookie）**。

## P-044（P1）layout 锁探测误判 —— 同一会话第二次写必失败 / 陈旧锁永久挡写

**位置**：`src/pyapi/packages/layout.py` —— `Package._is_locked()`（`ls -A <view>/*.cdslck` 判存在）+ 调用点 `write()` 内 `if self._is_locked(request): raise ... "is locked by another session"`。

**现象**：`virtuoso.layout.write` 报 `RuntimeError: layout view <lib>/<cell>/<view> is locked by another session`，
即使：
1. 锁文件的 owner 就是**执行写入的同一个 CIW**（后缀 `...cdslck.RHEL30.GLIS-DESKTOP.localdomain.<ciw_pid>`）；
2. owner 进程**已经死了**（重启 CIW 后仍残留 14:14 的旧锁）；
3. 归档旧锁后复跑：WRITE-01 成功后**自建新锁**（14:38，owner=新 CIW pid），WRITE-02 立刻被挡。

**反证（同一会话完全能写）**：

```bash
# 任意一次 SKILL 调用即可验证（token 用注册表里的 vblog）
# dbOpenCellViewByType("schemtest" "lay_e2e" "layout" "maskLayout" "a")  ->  db:0x6116e01a
```

**证据**：
- 探针（重启前/后各一份）：`test/artifacts/evidence/round2-layout-lock-probe.json`、`round2-layout-lock-probe-after-restart.json`（verdict=FALSE POSITIVE，`append_open_ok: true`）
- 套件日志：`test/artifacts/evidence/http-e2e/layout_e2e_tests.py.log`
- 探针源码：`test/semi/probes/layout_lock_ownership_probe.py`

**建议修法**（任一即可，建议第 1 条）：
1. 锁文件后缀 `.cdslck.<host>.<pid>` 与本会话 CIW pid 比较，同 pid = 自己的锁，不算锁；
2. 不做文件存在性判断，直接尝试 `dbOpenCellViewByType(..., "a")`，返回 nil 才判"被占用"，并把 owner（若有）带进错误信息；
3. 无论哪种，**陈旧锁（owner 进程不存在）不应挡写**。

**验收**：`python test/live/packages/layout_e2e_tests.py --transport http` 全绿；锁探针在"有陈旧锁"与"同会话锁"两种场景下都应判可写。

## P-045（P1）并发后 CIW↔daemon 通道永久挂死，不自愈

> **已撤回（2026-09-23 复核）**：真因不是并发，而是测试侧 `test/live/e2e/test_e2e_live.py` 用 `RBStop()+load(新 setup)` 覆盖了正在服务的 CIW（P-046）。
> 以下内容保留作历史记录，**请勿据此排查**。

**现象**：`test/live/stress/http_mixed_stress_tb.py --workers 6 --rounds 6`（真机 vblog + 本地 fake 混合）：
72 个请求里 10 个 `SKILL execution timed out`，**全部落在真机实例**；压测结束后该实例：
- `1+1` → `SKILL execution timed out`（持续，非偶发）；
- 之后连 token 校验都返回 `invalid token`；
- 重启该 Virtuoso（保留 `.cdsinit` 自动加载 bridge setup）后立刻恢复正常（`1+1` → `2`，五接口/包 E2E 全部恢复）。

**同类复现（另一实例/另一主机）**：w1-gent 上的 fake 实例 `vb-lab12`（65202）在早前多用户压测后同样进入"连 `1+1` 都超时"的状态，`sudo` 重启 fake 进程后恢复（`{"value": "2"}`）。

**证据**：`test/artifacts/evidence/round2-http-mixed-stress.json`（10 failures，token 全为 vblog）、
`round2-multi-user-routing.json`（vblog 持续红、其它 4 用户正常、0 串号）、
以及重启前后端口探测记录（`ssh wsl-gent: 127.0.0.1:65121` 直连 `1+1`）。

**建议排查方向**：
1. 同一 CIW 上的并发 SKILL 是否真的被串行化（`transport/middle.py` 的 per-token 队列 vs daemon 的 per-connection 线程写同一 stdout/stdin 通道）；
2. 超时（watchdog）触发后，daemon 是否丢失/错位了与 CIW 的帧边界（`_read_frame` 的字节流复位）；
3. 为什么超时之后 token 校验会变化（daemon 状态被覆盖 or CIW 侧重新 RBStart 过）。

**验收**：同一压测 72/72 应答；压后 `1+1`、五接口、包 E2E 全部正常；不再需要人工重启实例。

## P-043（P2，一行修复，仍未修）py2.7 daemon 缺 coding cookie

**位置**：`src/bridge/resources/ramic_bridge_daemon_27.py` 第 1–2 行之间（shebang 后）。

**现象**：真 Python 2.7（wsl-gent 上 Cadence XCELIUM 自带 2.7.6）执行：

```bash
python2.7 ramic_bridge_daemon_27.py 127.0.0.1 <port> <token> <tmp>
# SyntaxError: Non-ASCII character '\xe7' in file ... line 286, but no encoding declared
```

文件里有 12 行中文注释；py3 默认 UTF-8 所以一直没暴露。

**修法**：`#!/usr/bin/env python2.7` 下一行加 `# -*- coding: utf-8 -*-`。

**证据**：`test/artifacts/evidence/round2-py27-clean-copy.json`（仓库文件 0/5，listen 都起不来）+ 探针 `test/semi/probes/py27_daemon_probe.py`；
远程副本补该行后 **5/5 PASS**（`py27-daemon-probe.json`）。

**验收**：`python3 test/semi/probes/py27_daemon_probe.py --py27 /opt/eda/cadence/XCELUMMAIN2309/tools.lnx86/python2.7/bin/python2.7 --daemon <部署> --port 6603 --token py27-probe` 5/5。

## 附：测试侧本轮改了什么（供你们对齐，不需要你们动）

- `test/live/flows/s11_full_flow.py`：schematic 阶段 SKILL 表达式①结尾少一个 `)`、②嵌套 `if` 写成 `(if(..)(if(..)))`（SKILL 会当成函数调用）→ 已修，schematic 现 6 实例、pin 全对；
- `test/live/packages/infra_e2e_tests.py`：`netlist.import` 断言从"假成功"改为"结构化失败 + reference stub"（对齐 202c4e37）；
- `run_all_http.py` 等 29 个 TB/探针：拆分式 artifacts 路径补齐 `env/evidence/tmp` 层级（上轮批量改写的漏网）；
- 新增探针：`py27_daemon_probe.py`、`py27_handler_probe.py`、`layout_lock_ownership_probe.py`；
- P-039 撤回：真 py2.7 下行为正确，原红是 py3 模拟造成的伪结论。
