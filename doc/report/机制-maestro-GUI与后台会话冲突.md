# 机制记录：Maestro GUI 会话与后台会话冲突

> 日期：2026-09-21
> 环境：Virtuoso IC6.1.8-64b / WSL-Gent / DISPLAY=:99
> 对象：`src/pyapi/packages/maestro.py`
> 级别：重要机制，后续实现/测试必须遵守

## 1. 结论

1. **仿真必须使用 GUI 会话**：后台 `maeOpenSetup` 创建的 session 不能可靠跑
   `maeRunSimulation`；旧环境出现过 `Received stop signal from user`，任务被杀。
2. **不能自动 force-close 后台 session 后再立刻打开/关闭同 cellview 的 GUI 会话**：
   2026-09-21 受控探针在 IC6.1.8 上触发了真实 SIGSEGV，Virtuoso 整体退出。
3. 因此 maestro 包采取保守策略：
   - `run` 只走 GUI session；
   - 非 GUI 操作只关闭**自己创建**的 session；
   - 打开 GUI 前若发现后台 session，只**上报** `background_sessions`，不替调用方关闭；
   - GUI reading session 在写之前先 `maeMakeEditable`。

## 2. 仿真必须 GUI 的证据

- 后台 session 调 `maeRunSimulation` 后，日志出现
  `Received stop signal from user`，仿真被终止。
- 同一 cellview 改为 `deOpenCellView(..., "a")` 打开的 GUI 会话后，
  `maeSetJobControlMode("ICRP")` + `maeRunSimulation` 正常返回 history 并跑完。

## 3. 冲突探针与崩溃证据

### 3.1 探针步骤

1. 关闭已有 GUI；
2. 用 `maeOpenSetup("maestro_tb" "logic_probe" "maestro")` 创建后台 session；
3. force-close 该后台 session；
4. 立刻 `deOpenCellView(... "a")` 打开 GUI；
5. 随后关闭 GUI。

### 3.2 崩溃序列（`/home/Gent/project/vblog/CDS.log`）

```text
# ADE Assembler session 'fnxSession680' started ...
# ADE Assembler session 'fnxSession680' closed ...
# ADE Assembler session 'fnxSession681' started ...
# ADE Assembler session 'fnxSession681' closed ...

INFO (DB-120006): 'virtuoso' exited unexpectedly. Panic files ...
WARNING: Process was terminated with SIGSEGV signal
virtuoso has encountered a fatal internal application error and will now exit.
```

- panic log：`/home/Gent/panic.log.GLIS-DESKTOP.localdomain.9780`
- crash report：`/tmp/crashReport_092126_114910_IC6.1.8-64b.500.34_Gent_GLIS-DESKTOP.log`
- 结论：不是普通 edit lock 失败，而是 Cadence 进程级崩溃。

## 4. 包内现行规则

| 场景 | 规则 |
|---|---|
| `run` / 仿真 | 必须 `_ensure_gui_session()`；设置 ICRP；不在后台 session 跑 |
| 非 GUI 读写 | `maeOpenSetup` 复用已有 session；只关闭 `created=true` 的 session |
| `open_gui` | 需要时可开 GUI；发现后台 session 只返回 `background_sessions` 列表 |
| `write` / `write_history` | 若会话是 reading GUI，先 `maeMakeEditable`，失败则拒绝写 |
| session 清理 | 禁止上层自动 force-close 别人的后台 session |
| 冲突测试 | 先用只读探针；禁止无监督重复破坏性 force-close 探针 |

## 5. 后续验证要求

Virtuoso 重启后按以下顺序重新验证，任何一步异常立即停止：

1. `test/tb/maestro_session_conflict_probe.py` 只读列出 sessions/windows；
2. 正常 `run`（GUI）跑通；
3. 存在后台 session 时调用 `open_gui`，确认返回 `background_sessions`
   而不是崩溃；
4. reading GUI session 调 `write`，确认 `maeMakeEditable` 后写入成功；
5. 以上通过前，不允许再次执行 force-close + GUI open/close 组合。

## 6. 重启后回归状态（2026-09-21）

- 通过 `ssh wsl-gent` 在 `/home/Gent/project/vblog` 启动 Virtuoso；
  `.cdsinit` 自动 `load(.../virtuoso_setup.il)`，daemon 监听 `127.0.0.1:65121`。
- `basic.skill.execute("1+1")` → `2`。
- `open_gui maestro_tb/rc_probe` → `fnxSession0`，GUI 仿真
  `Interactive.10` 轮询到 `done`（2/2 points）。
- 只读诊断 `test/tb/maestro_session_conflict_probe.py`：
  干净状态下 `sessions=[] / gui_windows=[] / background_sessions=[]`。
- 破坏性 force-close 冲突场景本轮**未重复执行**；等基础侧修复完成、
  并经确认后再按第 5 节顺序做受控验证。
