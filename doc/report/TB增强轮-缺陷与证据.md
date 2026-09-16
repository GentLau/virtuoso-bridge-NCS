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
| 2 | registry 跨进程丢更新：两个进程各自 load→register→写回，后写覆盖先写 | `semantics_tb.py`：`registry-cross-process`（4 进程栅栏后并发写）；POSIX 红灯 `registry-lost-update-red.json`：*"cross-process writes lost users ['user0','user2','user3']"* | `registry.py` 改为**锁内读改写**（`_mutate_locked`）：锁内重读磁盘、合并、校验 token 唯一后再原子写 | 同上（4/4 用户均在盘上） |
| 3 | `file_lock` 在 Windows 上向已被锁定的字节区间写入 → `PermissionError`；且 finally 中删除锁文件会破坏互斥（两个进程锁到不同 inode） | 同上（子进程报 `PermissionError: [Errno 13]`） | 锁文件只创建不删除；改为非阻塞重试 + 超时（不再写锁字节） | 同上 |
| 4 | 安装暂存文件时崩溃会丢目标：先 `target→backup` 再 `stage→target`，两次 rename 之间进程死亡则目标路径为空 | `semantics_tb.py`：`install-crash-safety`（子进程在第一次 rename 后 `os._exit(9)`）→ 目标丢失、只剩 `.vbbak-*` | `transfer.py` 普通文件改为**单次 `os.replace`** 原子安装；目录才保留备份流程；`middle.py` 复用同一实现 | 同上（崩溃后目标仍在，内容为旧值或新值） |
| 5 | IL 用子串嗅探判断日志开关：用户 SKILL 文本里出现 `RBDLogOn=t ` 就会在 `log_level=off` 时触发 flush/fileLength/第二帧（违反“off 完全不取日志”） | **源码级护栏**（不是行为红灯，见 §5.1）：`log_matrix_real_tb.py`：`il-log-flag-prefix-guard` | `ramic_bridge.il` 改为**只比较指令前缀**（`equal(substring(data 1 11) "RBDLogOn=t ")`） | `artifacts/log-matrix-real-green.json` |
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

## 2.1 规格变更带来的新接口（只读 query）

评审期间 spec 升级，新增 **§4.2 `middle.query(token)` 只读查询**（旧稿曾叫
`role_facts`，v21 起统一为 `query`，v23 进一步限定范围为 `root`/`bin` 且不得返回
任何拓扑字段）。该接口在代码基线中不存在，按“先红后绿”处理：

| 项 | 内容 |
|---|---|
| 红 | `semantics_tb.py` 四个用例 `query-shape` / `query-unknown-token` / `query-isolation` / `query-no-budget` 全部失败（基线无该方法）；证据 `artifacts/query-baseline-red.json` |
| 实现 | `pyapi/models.py` 新增 `RoleQuery(root, bin)` / `QueryResult(status, roles, errors)`；`BusinessServer.query` 只读返回五个 role 的 `root`/`bin`，未知 token 返回 `status="error"` + `errors=["invalid token"]`，不建连接、不写注册表、不缓存、不占三类预算（有专门用例占满线程池后仍立即返回） |
| 绿 | `artifacts/semantics-green.json`（全部用例通过，含 4 个 query 用例） |
| 文档 | `doc/接口调用指南.md` §1.1 / §3.2（只写 `root`/`bin`，不写拓扑字段） |

## 2.2 子评审（代码 / 测试 / spec 一致性）追加修复

三个只读子评审（代码、测试与证据、spec 一致性）在 2026-09-16 晚给出结论，确认的问题按下表修复：

| # | 缺陷（评审结论） | 红灯证据 | 修复 | 绿灯 |
|---|---|---|---|---|
| 7 | **Skill 在已投递后重发**：`skill_client` 把 connect→send→recv 放在同一次 try 中，RST 后整段重试；实测同一条非幂等 SKILL 被投递 10–15 次 | `skill-delivery-baseline-red.json`（`deliveries=10`） | 区分“建连前失败”（≤3 次重试）与“已投递后失败”（绝不重发，按结果未知返回固定文案 `SKILL execution timed out`） | `semantics-green.json`（`deliveries=1`） |
| 8 | Skill 建连没有消费 `runtime.connect_timeout` 子预算 | — | `SkillClient` 新增 `connect_timeout`，`middle` 传入 `entry.runtime.connect_timeout`；`connect` 只用 `min(剩余预算, 子预算)` | 单元/真机回归 |
| 9 | SSH/SCP “文件不存在”被判成 `kind=command`（本地路径场景是 `path`） | — | `_result_from_rc` 识别 `no such file or directory` / `cannot stat` / `open failed` → `kind=path` | 单元回归 |
| 10 | 注册第 5 步失败后不可重试（与 spec “可重试第五步”冲突） | 六步 TB 新增“第 5 步失败→修复环境→再 verify” | `RegistrationFlow.verify` 允许 stage=failed 且候选 entry 仍在时重跑连通性测试 | `reg-six-local/evidence.json` |
| 11 | 第 5 步缺少 daemon user 与 `expected_user` 的比对（spec 要求 WARNING） | — | IL 解析/写入 `user=`，两个 daemon 的 banner 带上执行账号；`flow.identity_warnings()` 比对 host/user | 单元 + 真机：重新部署并重启 `vblog` 后 identity 为 `host=GLIS-DESKTOP … user=Gent`（`user=` 已落盘），比对逻辑有单元覆盖 |
| 12 | `user update` 放行了白名单外的 `mode` | — | 白名单去掉 `mode`；六步 TB 增加“提交 mode 必须 400”负例 | `reg-six-local/evidence.json` |
| 13 | daemon watchdog 文案不是冻结文案 | 集成测试（原断言 `TimeoutError`） | watchdog 帧改为 `SKILL execution timed out`，并剥掉帧尾 RS，客户端拿到的就是冻结文案 | `test/integration/test_daemon_handler.py` |
| 14 | registry 载入不校验 user key（手写 `../evil` 可进内存并参与落盘路径拼接） | — | `load()` 对每个 key 调用 `validate_user_name` | 单元回归 |
| 15 | 压力 TB 会重试**所有**失败（包括 transport/未知影响/真实命令失败），可能掩盖非幂等缺陷 | — | 只对容量拒绝（线程/通道/max_sessions、含 Skill 容量拒绝与回读校验被拒）重试；其它失败立即记录 | `http-stress-sat/evidence.json`（144/144 最终应答，失败立即暴露） |

### 2.2.1 已记录、本轮不修（附理由）

| 项 | 现状 | 为什么不本轮修 |
|---|---|---|
| 本地一次性命令超时只杀 shell、子进程继续（Windows/POSIX 皆然） | `subprocess.run(shell=True, timeout=…)` | 需要进程组/Job Object 级别的实现与跨平台测试矩阵，属于独立改造；本轮已在报告中标注为已知风险，调用方超时后不得盲目重试 |
| 远端常驻 shell “协议错误重试”可能重放已执行的命令 | `ssh.py` 5 类错误统一重试 | 需要重新设计“是否已投递”的判定与协议层错误分类；本轮先记录，避免引入未经验证的重试语义 |
| 注册 HTTP 层未按用户串行（并发 verify / verify 中 delete 竞态） | `registration_server.py` 只在 dict 上加锁 | 注册是低并发流程（spec 明确不设跨进程租约）；本轮记录为已知竞态，修法（per-user 锁 + 第 6 步前复核 stage）留待后续 |
| IL→daemon 帧未转义（返回值含 RS 会截断） | `ramic_bridge.il` `%L` 原样进帧 | 属协议格式变更，需要 daemon/IL 同步升级与真机矩阵；本轮记录 |
| Skill 超时后残留帧可能计入下一条请求 | daemon 一次性 drain | 需要更强的请求关联机制（spec 本版不做 request_id）；本轮记录 |
| OpenSSH 后端 `rc=255` 判成 transport | `ssh.py` | 需区分“ssh 自身失败”与“远端命令返回 255”，需要真实 OpenSSH 真机矩阵 |
| 本地 shell banner 卡死会阻塞整个中层（构造时持 `_lock`） | `middle.py` | 需要把 shell 启动移出全局锁并加超时；属并发重构，本轮记录 |
| 目录目标安装仍是备份式替换（崩溃窗口） | `transfer.py` 目录分支 | 文件已改为单次 `os.replace`；目录在 Windows 上无法原地原子替换，需要恢复策略设计 |
| `test/计划/*` 中部分用例没有门禁 TB（拓扑/等价性/运维等） | — | 见 `test/tb/README.md` §准出集合：本轮明确哪些计划项未纳入准出，避免“文档里的 TB”与门禁不一致 |

## 3. 本轮新增 TB

| TB | 覆盖 | 环境 | 证据 |
|---|---|---|---|
| `semantics_tb.py` | 本地/远端 Skill 交付纪律、本地文件 deadline、registry 跨进程、崩溃安全、只读 `query` 契约 | 任意平台 | `semantics-*-red/green.json`、`query-baseline-red.json`、`skill-delivery-baseline-red.json` |
| `daemon_log_protocol_tb.py` | daemon 侧日志契约：off/分级/轮转/读不到/降级/截断/第二帧超时/错误帧/监听循环；py3 与 py27 双跑 | 任意平台（脚本化 CIW） | `log-protocol.json`（18 用例） |
| `log_matrix_real_tb.py` | 真机 CDS.log：增量字节一致、off 源头、桥零注入、IL 前缀护栏 | Windows → wsl-gent | `log-matrix-real-*.json` |
| `registration_http_six_step_tb.py` | 真实 HTTP 六步注册（含步骤 6 落盘、读回、更新、删除、乱序拒绝）；远端模式 1–4 步走真 SSH | Windows（+ wsl-gent） | `reg-six-local/evidence.json`（本地 1–6）、`reg-six-remote-14/evidence.json`（远端 1–4）、`reg-six-remote/evidence.json`（远端 1–6） |
| `http_mixed_stress_tb.py` | 五接口 + 组合服务（upload→skill→command→download）HTTP 并发，随机顺序、随机延时、重试计数 | Windows / WSL 客户端 | `http-stress2/evidence.json`、`http-stress-wsl-client.json`、`http-stress-sat/evidence.json` |
| `one_shot_burst_tb.py` | 一次性通道突发（超过服务端 `MaxSessions`）不得把 transport 错误暴露给调用方 | Windows → wsl-gent | `one-shot-burst-red/green.json` |
| `_daemon_harness.py` | 脚本化 CIW 的公共夹具（同时兼容 py3 的 `.buffer` 与 py2.7 的文本流 API） | 任意平台 | — |

## 4. 并发与客户端等价性

- **Windows 客户端**：72/72 请求一一应答（`http-stress2/evidence.json`），覆盖
  skill 9、command 14、upload 10、download 14、gui 9、spectre 4、composite 12。
- **WSL 客户端**：同一 TB、同一工作量 72/72（`http-stress-wsl-client.json`），
  说明客户端所在操作系统不影响投递语义。
- **饱和场景**：把本地 token 线程池压到 4、并发 24，仍 144/144 最终拿到正确应答；
  过程中记录大量**结构化**拒绝（`thread pool exceeded` / `channel budget exceeded` /
  `role max_sessions exceeded`，具体次数以 artifact 为准），无进程崩溃、无请求丢失、
  无跨用户串扰（`http-stress-sat/evidence.json`）。
- **资源盘点（已落 artifact）**：混合压力 TB 记录 `ssh_processes_before/after` 与
  `staging_leftovers` / `new_system_temp_dirs`；Windows 72 请求为 `2 → 2`，饱和 144 请求为
  `2 → 2`，WSL 客户端 72 请求为 `5 → 5`，三者暂存目录残留均为 0。

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
python test/tb/registration_http_six_step_tb.py --work-dir test/tb/artifacts/reg-six-remote-14 `
  --user vbsixremote --daemon-port 65133 --root /home/Gent/.virtuoso-bridge/vbsixremote `
  --stop-after-deploy --out test/tb/artifacts/reg-six-remote-14/evidence.json

# HTTP 混合压力（Windows 客户端）
python test/tb/http_mixed_stress_tb.py --work-dir test/tb/artifacts/http-stress2 `
  --remote-token vb-vblog --remote-daemon-port 65121 `
  --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 6 `
  --out test/tb/artifacts/http-stress2/evidence.json

# 合并覆盖率
powershell -NoProfile -File test/tb/run_coverage.ps1
```

## 5.1 证据性质说明（评审须知）

- **行为红灯**：缺陷 1、2、3、4、6 都由 TB 复现出真实行为差异（丢失更新 / 超时被忽略 /
  崩溃丢目标 / transport 错误外泄）。
- **源码级护栏**：缺陷 5 的 IL 日志开关**无法从客户端行为观测**——被误导时 IL 只是多做
  一次 CIW 侧 flush/fileLength 并多发一帧，而该帧会被 daemon 丢弃（`off-sentinel-payload`
  在修复前后都通过）。因此这条不变量以“源码前缀比较护栏”固定，并在 artifact 中标
  `kind=static-source-guard`；任何引用都不得把它写成行为红灯。
- **真机日志分级/降级/轮转**：Cadence 日志落盘异步，真机侧只稳定断言“增量字节一致 /
  off 不返回 / 桥零注入”；分级、降级提示、轮转、读不到、第二帧超时由
  `daemon_log_protocol_tb.py` 在 daemon 真实代码路径上确定性覆盖，两者不互相替代。

## 6. 仍未闭合 / 需评审知悉

1. **Python 2.7 真运行**：环境无 python2；用 py3 跑 py27 变体的同源协议矩阵做 parity，
   真解释器运行列为 PENDING。
2. **真机日志分级/降级**：Cadence 侧日志落盘异步，真机只稳定断言字节一致与 off；
   分级/降级/轮转/读不到/第二帧超时由协议 TB 在 daemon 真实代码路径上确定性覆盖。
3. **重复注册**：注册是低并发流程（spec 明确不做跨进程租约），当前以注册服务进程内
   协调 + 锁内读改写的 registry 兜底。
