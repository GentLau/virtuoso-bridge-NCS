# CIW / daemon 停止语义调查（2026-10-08）

> 触发：环境建设期间"杀 CIW 后 daemon 是否残留占端口"的判断前后矛盾。本报告用受控实验 +
> bridge 自带文档检索（`virtuoso.skillref.search/info`）把口径钉死。
> **一句话结论**：本环境**不存在**"杀 CIW 后 daemon 长期存活占端口"的孤儿现象；`RBStop()` 与
> "直接杀 CIW"两条路都会让 daemon 在秒级内退出并释放端口。之前的判断是
> **身份错误 + teardown 时序竞态**造成的误判。

## 1. 范围与口径

- 靶机：wsl-gent（AlmaLinux-8 WSL2，IC618）；对象：`start_disposable_ciw.sh` 起的可丢弃 CIW
  （name=`lifecyc1`，port=64610，token=vb-lifecyc1）。
- "停止"两条路：① CIW 内 `RBStop()`（bridge 提供的正路）；② OS 层杀 CIW（SIGTERM / SIGKILL，
  模拟外部杀进程 / 崩溃）。
- 判定三事实：daemon 端口是否 LISTEN、daemon 进程是否存活、`cdsServIpc` wrapper 是否残留。

## 2. 方法（可复现）

```bash
# 起 + 探活
bash ~/.virtuoso-bridge/disposable/bin/start_disposable_ciw.sh lifecyc1 64610
python3 ~/.virtuoso-bridge/disposable/bin/daemon_ping.py 64610 vb-lifecyc1 "1+1"   # OK '2'

# 只杀 cwd=实例 run 目录的 virtuoso，每 200ms 轮询端口释放
kill -TERM <ciw_pid>     # 或 kill -9 <ciw_pid>

# RBStop 路径
python3 ~/.virtuoso-bridge/disposable/bin/daemon_ping.py 64610 vb-lifecyc1 "RBStop()"
```

文档依据（bridge 自带检索，doc_root=`C:\Users\user\Desktop\doc`）：
`virtuoso.skillref.info` 取 `ipcBeginProcess / ipcKillProcess / ipcKillAllProcesses / ipcWait /
ipcIsAliveProcess / ipcGetExitStatus` 全文；`virtuoso.skillref.search` 全层检索 `ipcBeginProcess`。

## 3. 结果

| # | 停止方式 | 端口释放 | daemon | cdsServIpc wrapper | CIW |
|---|---|---|---|---|---|
| A | `kill -TERM <ciw>` | **1234 ms** | 退出 | +1.2s 仍在（ppid=1），**≤5s 消失** | 退出 |
| B | `kill -9 <ciw>` | **207 ms** | 退出 | ≤5s 消失 | 退出 |
| C | `RBStop()`（socket） | ≤3s（观察到时已 FREE） | 退出 | ramic wrapper 同退；libManager/libSelect/perfUtil wrapper 存活（属 CIW 的其它服务，与本桥无关） | **存活** |

反例（合规项）：三个实验结束 `ss -ltn` 均为 `PORT-FREE`；靶机 `ps -eo ppid,args | grep cdsServIpc`
无 ppid=1 孤儿；11 个日常真实 CIW（vblog/vbs11/calprobe/vbuser1/1b/2/2b/3/3b/4/4b）+ destb1 示例
均与各自 daemon 一一对应。

## 4. 官方文档口径（bridge 自带检索）

- `ipcBeginProcess`：子进程经 stdin/stdout/stderr 与父进程通信；支持 data/error handler 与 postFunc；
  `logFile` 非空时可切 batch 模式；**未承诺"父进程退出时自动终止子进程"**。
- `ipcKillProcess`：向子进程发 UNIX `SIGKILL`（想保留非 0 退出码用 `ipcSignalProcess`）。
- `ipcKillAllProcesses`：杀掉**父进程**经 `ipcBeginProcess` 起的所有子进程（显式清理口）。
- `ipcWait` / `ipcIsAliveProcess` / `ipcGetExitStatus`：等待 / 探活 / 取退出码。

→ 文档层面是"显式清理"语义；本环境实测 IPC 机制（cdsServIpc 层）会在 CIW 死亡时**连带收尸**，
因此观测不到孤儿。结论与文档不矛盾，但"父死子收"属实现行为、不是文档承诺。

## 5. 误判根因（2026-10-08 环境建设期间）

1. **身份错误（主因）**：用 Gent 身份 `kill` vbuser1 的 CIW/daemon → EPERM 被 `|| true` 静默吞掉，
   CIW 与 daemon 都还活着 → 注册 probe 报 `65411 already in use`。这不是"CIW 死了 daemon 还在"，
   而是"两个都没死"。
2. **teardown 时序**：之后用正确身份杀 CIW 时，清理循环在 kill 后**毫秒级**检查端口；
   此时 daemon 仍在 0.2–1.2s 的退出窗口内 → 看起来像"CIW 死了 daemon 还占着端口"，
   并把正在退出的 daemon 又杀了一次（证据里的 `killed-daemon=664455` 即此窗口内的误判）。

## 6. 口径回写

- 正确姿势：① `RBStop()` 优先（只停 daemon、CIW 留着）；② 直接杀 CIW 必须**目标账号身份**执行；
  ③ 无论哪条路，**kill 后轮询等端口释放再继续**（毫秒级检查会撞 teardown 窗口）。
- 已回写：`test/docs/环境与场景.md` §10、`test/reports/internal/环境Runbook-内部.md`、
  `test/shared/runners/bringup_instance.sh` / `register_instance.py` 注释。

## 7. 稳健性观察（非缺陷，改进建议）

1. `ramic_bridge_daemon_3.py::_read_frame()` 把 stdin EOF 当"暂无数据"死循环
   （`if not ch: time.sleep(0.001); continue`）——daemon 自身**没有父进程死亡自保**。
   本次由 cdsServIpc 兜底未出问题；若 IPC 机制被绕过/失效，daemon 会永久占端口。
   低成本加固：daemon 侧低频检查 `virtuoso_pid`（代码已有该变量，目前仅用于超时 SIGINT），
   或把 stdin EOF 视为"CIW 已死 → 优雅退出"。
2. `RBStop()` 不重置 `RBIpc`，紧随的 `RBStart()` 可能误判 "already running"
   （既有记录：`doc/report/底层-IL拆分报告.md` §7）。

## 8. 未覆盖与不确定

- 未测：`logFile` 非空（batch 模式）下的父死子进程行为；CIW 崩溃瞬间有 in-flight SKILL 请求的场景；
  WSL 之外的 Linux 宿主机（本环境为 WSL2）。
- 证据目录：`test/artifacts/evidence/ciw-daemon-lifecycle/`（`kill-ciw-experiment.json`、
  `kill-ciw-timing-experiment.json`、`wrapper-lifetime-experiment.json`、`rbstop-experiment.json`、
  `info-*.json`、`search-ipcBeginProcess.json`）。
- 登记：**非缺陷，不建 bug 卡**；本报告作为当前口径锚点保留在 `internal/`。
