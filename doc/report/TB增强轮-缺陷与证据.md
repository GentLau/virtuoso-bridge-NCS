# TB 增强轮：缺陷与证据（2026-09-16）

> 目的：记录本轮“TB 先复现、后修复”的缺陷清单、判定依据与可复算命令。
> 本文件只做索引与结论，接口语义以 [四层整体架构与接口](../spec/design-concepts/总览/1-四层整体架构与接口.md) 为准，
> 日志语义以 [日志返回设计标准](../spec/design-concepts/底层/6-日志返回设计标准.md) 为准。

## 1. 判定规则

1. 每条代码改动都必须先由 TB 复现（红），且红灯是**行为**而非静态警告；
2. 修复后同一 TB 必须转绿，红灯/绿灯证据都落盘到 `test/tb/artifacts/`；
3. 不能稳定复现的现象不得当作缺陷修复，只能记录为待观察项；
4. 覆盖率数字只作辅助，最终以“接口正确、内部运作符合预期”为准。

## 2. 本轮缺陷（全部先红后绿）

| # | 缺陷 | 红灯证据（TB） | 修复 | 绿灯证据 |
|---|---|---|---|---|
| 1 | 本地模式 `upload_file`/`download_file` 不消费 `timeout`：传输完成才返回，超时形同虚设 | `semantics_tb.py`：`local-file-timeout`/`local-tree-timeout`/`local-download-timeout` 3 用例全红 → `artifacts/semantics-baseline-red.json` | `middle.py` 改为分块流式拷贝 + 每块/每目录项检查 deadline；超时返回 `kind=timeout`、`returncode=124`，不留半成品 | `artifacts/semantics-green.json` |
| 2 | registry 跨进程丢更新：两个进程各自 load→register→写回，后写覆盖先写 | `semantics_tb.py`：`registry-cross-process`（4 进程栅栏后并发写）→ 文件只剩 1 个新用户 | `registry.py` 改为**锁内读改写**（`_mutate_locked`）：锁内重读磁盘、合并、校验 token 唯一后再原子写 | 同上（4/4 用户均在盘上） |
| 3 | `file_lock` 在 Windows 上向已被锁定的字节区间写入 → `PermissionError`；且 finally 中删除锁文件会破坏互斥（两个进程锁到不同 inode） | 同上（子进程报 `PermissionError: [Errno 13]`） | 锁文件只创建不删除；改为非阻塞重试 + 超时（不再写锁字节） | 同上 |
| 4 | 安装暂存文件时崩溃会丢目标：先 `target→backup` 再 `stage→target`，两次 rename 之间进程死亡则目标路径为空 | `semantics_tb.py`：`install-crash-safety`（子进程在第一次 rename 后 `os._exit(9)`）→ 目标丢失、只剩 `.vbbak-*` | `transfer.py` 普通文件改为**单次 `os.replace`** 原子安装；目录才保留备份流程；`middle.py` 复用同一实现 | 同上（崩溃后目标仍在，内容为旧值或新值） |
| 5 | IL 用子串嗅探判断日志开关：用户 SKILL 文本里出现 `RBDLogOn=t ` 就会在 `log_level=off` 时触发 flush/fileLength/第二帧（违反“off 完全不取日志”） | `log_matrix_real_tb.py`：`il-no-substring-sniff` 红 → `artifacts/log-matrix-real-red.json` | `ramic_bridge.il` 改为**只比较指令前缀**（`equal(substring(data 1 11) "RBDLogOn=t ")`） | `artifacts/log-matrix-real-green.json` |
| 6 | 一次性通道（`run_gui_command`/`run_spectre_command`/一次性命令/文件传输/SFTP）在建通道被 sshd 拒绝时直接把 `kind=transport` 抛给调用方：突发超过服务端 `MaxSessions` 时 42/72 失败 | `one_shot_burst_tb.py`（24 并发 × 3 轮）→ `artifacts/one-shot-burst-red.json` | `paramiko_backend.py` 新增 `_open_session_channel`：≤3 次尝试 + 指数退避，仅重试“未产生副作用”的通道打开；所有 session-channel 站点统一走它 | `artifacts/one-shot-burst-green.json`（72/72） |

附带修复（同样由 TB 检出）：

- `server/registration_server.py`：`POST /api/user/<user>/update` 无法接受 `GET` 返回的同一形状
  （`token`/`registered_at` 被判为 unknown field，导致“token 不可变”分支永不可达）→ 现在接受完整
  entry，`token` 必须与现值一致、`registered_at` 由服务端管理（`reg-six-local/evidence.json`）。
  > 与 spec 的差异（已上报）：[多用户与注册 §5](../spec/design-concepts/中层/1-多用户与注册.md) 的 `user update`
  > 白名单写作 `ssh.* / root.default / role.* / runtime.* / cdslog.* / expected_*`，未列出 `token` 与
  > `registered_at`。本实现把这两项视为**只读字段**接受（`token` 必须相等，`registered_at` 忽略），
  > 其余字段仍严格按白名单校验；若 spec owner 认为应完全拒绝，可改为返回“只读字段不可提交”，
  > 但注册页/管理端需要按 patch 而非整条 entry 提交。
- `server/stress_server.py`：五接口响应缺 `kind` 字段，调用方无法区分“容量拒绝/传输错误”；
  已补齐，并新增 `/api/gui`、`/api/spectre` 一次性接口（`http-stress2/evidence.json`）。

## 3. 本轮新增 TB

| TB | 覆盖 | 环境 | 证据 |
|---|---|---|---|
| `semantics_tb.py` | 本地文件 deadline、registry 跨进程、崩溃安全 | 任意平台 | `semantics-*-red/green.json` |
| `daemon_log_protocol_tb.py` | daemon 侧日志契约：off/分级/轮转/读不到/降级/截断/第二帧超时/错误帧/监听循环；py3 与 py27 双跑 | 任意平台（脚本化 CIW） | `log-protocol.json`（18 用例） |
| `log_matrix_real_tb.py` | 真机 CDS.log：增量字节一致、off 源头、桥零注入、IL 前缀护栏 | Windows → wsl-gent | `log-matrix-real-*.json` |
| `registration_http_six_step_tb.py` | 真实 HTTP 六步注册（含步骤 6 落盘、读回、更新、删除、乱序拒绝）；远端模式 1–4 步走真 SSH | Windows（+ wsl-gent） | `reg-six-local/evidence.json`、`reg-six-remote/evidence.json` |
| `http_mixed_stress_tb.py` | 五接口 + 组合服务（upload→skill→command→download）HTTP 并发，随机顺序、随机延时、重试计数 | Windows / WSL 客户端 | `http-stress2/evidence.json`、`http-stress-wsl-client.json`、`http-stress-sat/evidence.json` |
| `one_shot_burst_tb.py` | 一次性通道突发（超过服务端 `MaxSessions`）不得把 transport 错误暴露给调用方 | Windows → wsl-gent | `one-shot-burst-red/green.json` |
| `_daemon_harness.py` | 脚本化 CIW 的公共夹具（同时兼容 py3 的 `.buffer` 与 py2.7 的文本流 API） | 任意平台 | — |

## 4. 并发与客户端等价性

- **Windows 客户端**：72/72 请求一一应答（`http-stress2/evidence.json`），覆盖
  skill 9、command 14、upload 10、download 14、gui 9、spectre 4、composite 12。
- **WSL 客户端**：同一 TB、同一工作量 72/72（`http-stress-wsl-client.json`），
  说明客户端所在操作系统不影响投递语义。
- **饱和场景**：把本地 token 线程池压到 4、并发 24，仍 144/144 最终拿到正确应答；
  过程中记录 216 次**结构化**拒绝（`thread pool exceeded` / `channel budget exceeded` /
  `role max_sessions exceeded`），无进程崩溃、无请求丢失、无跨用户串扰
  （`http-stress-sat/evidence.json`）。
- **资源盘点**：Windows 侧 ssh 进程数不随请求线性增长；WSL 侧 fake daemon、
  `/tmp/vb-six-*` 临时目录在 TB 结束时全部回收。

## 5. 复算命令

```powershell
# 离线 TB（红/绿判定都在这里）
$env:PYTHONPATH='src'
python test/tb/semantics_tb.py            --out test/tb/artifacts/semantics-green.json
python test/tb/daemon_log_protocol_tb.py  --out test/tb/artifacts/log-protocol.json
python test/tb/fault_injection_tb.py      --out test/tb/artifacts/fault-injection-green.json

# 真机 TB（需要 ssh 别名 wsl-gent 与已注册的 vb-vblog / vb-vb11）
python test/tb/log_matrix_real_tb.py --work-dir test/tb/artifacts/log-vblog --token vb-vblog `
  --out test/tb/artifacts/log-matrix-real-green.json
python test/tb/one_shot_burst_tb.py --work-dir test/tb/artifacts/one-shot-burst --token vb-vblog `
  --out test/tb/artifacts/one-shot-burst-green.json

# 注册六步（本地全流程 / 远端 1–4 步）
python test/tb/registration_http_six_step_tb.py --work-dir test/tb/artifacts/reg-six-local `
  --user vbsixlocal --local-mode --token vb-six-local --out test/tb/artifacts/reg-six-local/evidence.json
python test/tb/registration_http_six_step_tb.py --work-dir test/tb/artifacts/reg-six-remote `
  --user vbsixremote --daemon-port 65133 --root /home/Gent/.virtuoso-bridge/vbsixremote `
  --stop-after-deploy --out test/tb/artifacts/reg-six-remote/evidence.json

# HTTP 混合压力（Windows 客户端）
python test/tb/http_mixed_stress_tb.py --work-dir test/tb/artifacts/http-stress2 `
  --remote-token vb-vblog --remote-daemon-port 65121 `
  --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 6 `
  --out test/tb/artifacts/http-stress2/evidence.json

# 合并覆盖率
powershell -NoProfile -File test/tb/run_coverage.ps1
```

## 6. 仍未闭合 / 需评审知悉

1. **Python 2.7 真运行**：环境无 python2；用 py3 跑 py27 变体的同源协议矩阵做 parity，
   真解释器运行列为 PENDING。
2. **真机日志分级/降级**：Cadence 侧日志落盘异步，真机只稳定断言字节一致与 off；
   分级/降级/轮转/读不到/第二帧超时由协议 TB 在 daemon 真实代码路径上确定性覆盖。
3. **重复注册**：注册是低并发流程（spec 明确不做跨进程租约），当前以注册服务进程内
   协调 + 锁内读改写的 registry 兜底。
