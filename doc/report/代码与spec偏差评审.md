# 代码与 spec 偏差评审（中层 / 底层 / 注册 / 顶层）

> 日期：2026-09-18
> 评审范围：`src/common/**`、`src/transport/**`、`src/register/**`、`src/server/**`、`src/bridge/resources/**`
> 不在评审范围：`src/pyapi/**`（上层）、`spec/**`（规范，只读）
> 依据版本：四层架构 v32、并发设计 v20、路由设计 v17、多用户与注册 v30、中层配置文档 v31、日志返回标准 v15、顶层补充 v19、本版范围 v9
> 方法：逐条对照 Normative 条款阅读实现；每个代码问题先写 TB 复现（红），再改代码（绿）。本文所有“已修复”项都有对应的失败复现记录。

## 1. 结论摘要

- 本轮共确认 **22 处 spec 偏差**：**13 处已修复**（TB 先检出、后修复），**9 处待修**（代码缺陷，下一批处理）。
- 另有 **6 处需要 spec owner 或上层 owner 决策**（接口签名、运行期校验语义、update 白名单等），不属于中层可单方改动的范围，见 §4。
- 已修复项全部通过定向测试；全量门禁（unit + integration + scenario）见 §5。

## 2. 已修复（TB 先检出后修复）

### 2.1 传输与文件合同（`src/transport/tunnel.py`、`src/common/ssh.py`、`src/common/transfer.py`、`src/common/paramiko_backend.py`）

| # | spec 条款 | 原行为 | 修复 | 复现 TB（修复前失败） |
|---|---|---|---|---|
| T1 | 四层接口 §4.6：`recursive=False` 只传单个常规文件；对象类型不符 → `kind=path` | 非 recursive 下载目录时直接执行 `sha256sum`，把 `Is a directory` 当作 `kind=command` 返回；上传侧只挡了目录，FIFO/设备等对象会被送进传输 | 下载先做远端 `[ -d / -f / -e ]` 探测，非 `file` 一律 `kind=path`；上传要求 `is_file()`（跟随 symlink） | `test_tunnel_transfer.py::test_non_recursive_download_of_directory_is_path_kind` |
| T2 | 配置文档 §6.5 / 路由 §4：endpoint = `(host,user,jump_host,jump_user,proxy)`，不同 endpoint 不得共享连接 | OpenSSH `ControlPath` 的 hash 只含 `host/user/jump_host/token`；仅 `jump_user` 或 `proxy` 不同的两个 endpoint 会复用同一个 master（连到错误链路） | `_short_control_path` 纳入 `jump_user`+`proxy`，`SSHRunner` 调用点同步传入 | `test_ssh_tunnel_lifecycle.py::test_control_path_covers_full_endpoint_identity` |
| T3 | 配置文档 §2.2 / 四层接口 §5.8：`runtime.connect_timeout` 是浮点秒，且是调用预算内的连接子预算 | `RemoteClient` 把 `connect_timeout` 做 `int()` 截断（0.5→0）；Paramiko 建连使用外层剩余预算，15s 子预算不生效 | 保留 `float`；`ensure_connected` 取 `min(外层剩余, connect_timeout)` | `test_tunnel_transfer.py::test_connect_timeout_keeps_fractional_seconds`、`test_connect_retry.py::test_connect_timeout_is_a_cap_inside_the_call_budget` |
| T4 | 四层接口 §4.6：symlink 跟随传输 | 上传/下载 tar 均未加 `-h`，链接被当链接传送 | 本地打包 `tar -c -h -f -`、远端打包 `tar -c -h -z -f -` | `test_transfer.py::test_tar_download_dereferences_symlinks`、`::test_tar_upload_dereferences_symlinks` |
| T5 | 四层接口 §4.5 / §5.8：已投递的请求不重发，无法判断副作用 → `unknown-effect` | 常驻 shell 在命令写入后出现协议错乱（协议行/rc 行/base64 损坏/写失败）时抛可重试异常，外层会重建 shell **重发同一条命令** | 写入之后的异常统一 `UnknownEffectError`；`_is_retryable_persistent_shell_error` 对 `UnknownEffectError` 直接返回 False；重试包装器遇到它只关闭 shell、不重发 | `test_persistent_shell_protocol.py::test_unexpected_protocol_line_after_delivery_is_unknown_effect`、`::test_bad_return_line_after_delivery_is_unknown_effect`、`::test_unknown_effect_is_never_retryable` |

### 2.2 注册六步与注册表（`src/register/flow.py`、`src/register/server.py`）

| # | spec 条款 | 原行为 | 修复 | 复现 TB（修复前失败） |
|---|---|---|---|---|
| R1 | 多用户与注册 §3.3 / 顶层补充 §3：`apply` 的前提是“无同名进行中会话” | “检查是否已有会话”与“创建并登记新会话”不在同一临界区，两个并发 `apply` 都能通过检查并互相覆盖（已用双线程复现两个 200） | `check → cancel 旧会话 → start → 登记` 全部在 `flow_lock` 内完成，响应在锁外发送 | `test_registration_server.py::test_concurrent_apply_creates_exactly_one_session` |
| R2 | 多用户与注册 §3.3：各步失败可原样重试 | `verify()` / `commit()` 的重试入口不清空 `errors/report`，重试成功后 `stage=verified/committed` 仍携带上一次失败信息 | 重试入口清空 `errors/warnings/report` | `test_register_flow.py::test_verify_retry_success_clears_stale_errors`、`::test_commit_retry_success_clears_stale_errors` |
| R3 | 顶层补充 §5：PUT `/api/config` 更新快照并原子写回；非法配置拒绝 | 先改内存再落盘（失败时内外不一致）；非法 JSON 直接抛异常断连；`business_thread_pool_size` 不做类型校验 | 先解析+校验（正整数或 null）→ 落盘成功 → 替换内存；异常路径返回结构化 4xx/500 | `test_registration_server.py::test_config_invalid_value_rejected`、`::test_config_malformed_json_is_4xx`、`::test_config_persist_failure_keeps_memory_snapshot` |
| R4 | 配置文档 §6.2：spectre 探测失败时 `root`/`expected_fingerprint`/`bin` 提交为 `null` | 只有角色级探测失败会三项置空；显式 bin 不可用 / 自动探测不到时仅清 `bin`，保留 root 与指纹 | 失败统一经 `nullify_spectre()` 三项置空并附 warning | `test_register_flow.py::TestSpectreAutoProbe::test_explicit_bad_spectre_non_blocking`（扩展断言） |
| R5 | 配置文档 §6.4：`daemon_port` 唯一性作用域是 daemon 目标主机 | `reserved_daemon_ports()` 返回扁平 `set[int]`，不同 daemon host 的同号端口被误判冲突 | 查询按 `daemon_scope` 过滤；probe 与部署前复核分别用各自目标主机的 scope | `test_register_flow.py::test_reserved_daemon_ports_are_scoped_by_target_host` |
| R6 | 配置文档 §6.4：local 模式 `daemon_port`/`local_port` 是同一候选端口，任一缺省用同一值生成 | 只给 `local_port` 时报 “must equal daemon_port”；两个都不给且 65432 被占用时直接失败，不重分配 | 双显式值必须相等；任一显式即取该值同步写入；都缺省先试 65432，被占用或已被其他候选预留则自动分配空闲端口 | `test_register_flow.py::TestLocalJointPort::*`（4 条） |
| R7 | 配置文档 §2.3：`mode=local` 的 role 无 endpoint，`expected_fingerprint` 省略或为 null | 用户为 local role 显式提交指纹时会写入注册表 | local role 探测时强制 `expected_fingerprint=None` | `test_register_flow.py::TestLocalJointPort::test_local_role_expected_fingerprint_is_cleared` |

### 2.3 注册页（`src/register/registration_page.html`）

| # | spec 条款 | 原行为 | 修复 | 复现 TB（修复前失败） |
|---|---|---|---|---|
| R8 | 多用户与注册 §2 / 配置文档 §2.5：`mode.default` 必填、不推断 | 页面默认勾选 remote，且保留“自动判断”逻辑（`resolvedMode()`、`\|\| 'remote'` 兜底） | 取消预选，radio 必选；删除自动推断与 `'auto'` 语义；未选择时提示“请选择运行模式”并阻止提交 | `test_registration_page.py::test_mode_is_never_defaulted_or_inferred` |

## 3. 待修（代码缺陷，下一批按优先级处理）

| # | 级别 | spec 条款 | 证据 | 建议改法 |
|---|---|---|---|---|
| O1 | 高 | 五接口 §4.5：“真实命令返回码即使等于 124/255 也保持 `kind=command`” | `src/common/ssh.py::_is_ssh_transport_255` 仅凭 rc=255 + stderr 文本（`ssh: …`、`connection closed by`、`connection reset by peer`）判定 transport | 只在能证明 stderr 来自本地 OpenSSH 传输层时分类；无法区分时保留 `command` 与真实 rc |
| O2 | 高 | 并发设计 §4：建连/重试共享同一条剩余预算 | `src/common/ssh.py::_start_port_forward_locked` 在 Windows 分支每个 attempt 内重新 `deadline = now + jh_settle`（≥10/30s），POSIX 分支同样重置 | 保留外层不可变 deadline，每次 attempt 取 `min(外层, now + 单次 settle)`，spawn/sleep 前检查剩余预算 |
| O3 | 中 | 四层接口 §4.6：先校验再原子替换 | `src/transport/tunnel.py::_sha256_local` 无 deadline 参数，大文件摘要计算可越过调用 deadline | 传入 deadline，分块前检查剩余预算，超时清理 stage 且不改目标 |
| O4 | 中 | §3.3/§4.2：注册后 `role.root` 为绝对路径，运行期不再解析 `~`；一次调用一条 deadline | `src/transport/tunnel.py::remote_home` 在文件调用内额外占用一个 channel lease、硬编码 15s，且 `remote_root_path` 会把 `~` 直接拼进远端路径 | 运行期对含 `~` 的 root/路径直接返回参数/路径错误；确需支持时移到获取 file lease 之前并共享调用 deadline |
| O5 | 中 | 用户已明确“远端尽量不逃逸到系统临时目录” | `src/common/ssh.py::_run_command_via_persistent_shell_locked` 用远端 `mktemp`（默认 /tmp）保存 stdout/stderr，异常路径不清理 | 常驻 shell 注入 role 根/专用 temp 目录，`mktemp -p` + `trap`（或子 shell）保证 EXIT 清理；无法注入时保留回退 |
| O6 | 中 | 路由设计 §4：每个 remote daemon endpoint 一条专用隧道，失效自动重建 | `src/common/ssh.py::is_tunnel_alive` 对本进程只看 `poll() is None`，不探测 forwarding 是否仍可用；标记 ready 前 POSIX 分支未验证端口可达 | ready 判定加端口可达性检查；对本进程隧道做周期性健康校验（失败重连，不静默复用陈旧 listener） |
| O7 | 中 | 配置文档 §5 / 多用户与注册 §5：`proxy` 是 endpoint 身份的一部分，配置即生效 | OpenSSH 承载的路径（`_build_ssh_base`、Skill 端口转发）完全不使用 `proxy_url`，仅 Paramiko 消费；`backend=openssh` 或 remote daemon 隧道时 proxy 被静默忽略 | 二选一：用 `ProxyCommand`/`nc -X 5` 实现；或在角色含 proxy 且承载路径不支持时报参数错误（不得静默忽略） |
| O8 | 低 | 四层接口 §4.6：“原子替换到目标” | 目录目标替换是 `rename→backup` + `rename→target` 两次重命名，中间有窗口 | 平台支持时用 `renameat2(RENAME_EXCHANGE)`/版本化目录；否则由 spec owner 明确目录目标的例外语义 |
| O9 | 低 | §5.8：一次调用只有一条 deadline（注册步内相位共享） | `src/register/probe.py` 指纹转换使用 `NamedTemporaryFile`（第三步落盘）；与“前五步零落盘”的字面表述存在张力 | 改为 stdin/管道；或由 spec owner 明确“零落盘”仅指 registry/reservation 状态 |

## 4. 需要 spec owner / 上层 owner 决策（本轮未改）

| # | 位置 | 冲突点 | 建议 |
|---|---|---|---|
| D1 | `src/pyapi/models.py::Middle` + `src/transport/middle.py::BusinessServer.query` | spec §4.2 写 `middle.query(*, token)`（关键字专用），实现是 positional-or-keyword，且 `src/pyapi/packages/gui.py` 以位置参数调用 | 二选一：spec 放宽为 `query(token)`；或上层改关键字调用后，中层收紧为 `*, token` |
| D2 | `src/pyapi/models.py::Middle.execute_skill` | 协议签名缺 `log_level`/`log_max_bytes` 可选参数（spec §4.1 有） | 上层接口定义补齐两个关键字参数（`pyapi` 不在本轮改动范围） |
| D3 | `src/register/server.py::_handle_update` | update 只做 `UserEntry` 结构校验，不做与 commit 同级的“整体校验”：可把 remote role 的 host/user 清空、root 写成相对路径、daemon python 置空，仍返回 200 并落盘 | 抽出 commit/load/update 共用的语义校验；update 允许单独改 `root.default` 且不得重写已提交 `role.root` |
| D4 | `src/register/server.py` update 白名单 | spec §5 白名单为 `ssh.* / root.default / role.* / runtime.* / cdslog.* / expected_*`；实现额外接受 `registered_at`（静默忽略）与 `root_default`、`daemon_python` 等扁平别名 | 明确：扁平别名是否升格为协议；`registered_at` 建议显式 4xx |
| D5 | `src/common/registry.py::Registry.register` | `overwrite=True` 允许替换同 user 的 token，与“token 终生有效、不轮换；轮换=删除后重新注册”冲突（HTTP update 已挡住，公共 API 未挡） | 在 `Registry.register` 内拒绝 overwrite 换 token；轮换必须 remove→register |
| D6 | `src/common/registry.py::Registry._mutate_locked` + `server.py` update | 文件锁只保证不损坏，不防 lost update：两个并发 update 改不同字段时，后写者用旧快照整体覆盖 | 提供锁内“重读当前 entry → 合并 patch → 整体校验 → 写回”的 `Registry.update()` |
| D7 | `src/register/flow.py::RegistrationFlow`（公共导出） | 模块级 `cancel()` 对 `committed` 无守卫；`verify()/commit()` 用“改成 failed”表达顺序错误；`register_user()`/`apply()` 可自动走完并 commit，绕过“第六步用户显式确认” | 关闭模块级守卫缺口；把 `register_user()` 移出生产导出或强制显式 `confirm_commit=True` |
| D8 | `src/transport/roles.py` / runtime | spec §3 说 `expected_hostname/user` “运行期不一致 WARNING”，但运行期没有任何消费者（仅注册第五步比对）；host-key 运行期依赖 known_hosts + RejectPolicy | 明确语义：若保留“运行期比对”，中层需要一次可观察的握手；若只在注册比对，请把 §3 措辞收窄为“注册探测比对” |

## 5. 门禁与证据

- 定向复现（修复前红）：传输批 9 条全部失败；注册批 11 条全部失败。
- 修复后定向回归：`test_tunnel_transfer`、`test_transfer`、`test_persistent_shell_protocol`、`test_ssh_tunnel_lifecycle`、`test_connect_retry`、`test_ssh`、`test_paramiko*` 全绿；`test_register_flow`、`test_registration_server`、`test_registration_page`、`test_registration_mock_server` 全绿。
- 全量门禁（2026-09-18）：`python -m pytest test/unit test/integration test/scenario`
  → **548 passed, 1 skipped, 27 subtests passed in 362.41s**。
- 真机复核（Windows 客户端 → `wsl-gent` 真 Virtuoso，token `vb-vblog`）：
  - `test/tb/cov_remote_real.py`：skill / command / file / gui / spectre **5/5 ok**；
  - 递归上传 + 递归下载目录树通过；在远端构造 `link.txt -> real.txt` 后递归下载，本地产物为**常规文件**且内容等于链接目标（验证 `-h` 跟随 symlink）；
  - `test/tb/registration_http_six_step_tb.py --local-mode` 通过（含 cancel 后重新 apply 路径）。
- 回归约束：所有修复均未改动 `spec/**`；未触碰 `src/pyapi/**`。

## 6. 建议的下一批顺序

1. O1/O2（错误分类与 deadline，直接影响结果语义）；
2. D3/D5/D6（注册表整体校验与并发写，直接影响注册表可用性）；
3. O4/O5/O7（运行期路径与代理，涉及“忠实投送”）；
4. O3/O6/O8/O9 与 D1/D2（体验与边界收口）。

## 7. 第二轮：裁决后实施记录（2026-09-18）

> 裁决依据：`doc/report/spec对代码评审的裁决.md`（spec 侧提交 `21f1ee9` / `44c9779` / `4100a7c`）。
> 纪律同上：每项先补/改 TB 复现失败，再改代码。本轮 TB 首轮红灯共 17 条（D 系列 9 条 + O 系列 8 条）。

### 7.1 D 系列（按 spec 补齐）

| 项 | 实施 | TB / 复核 |
|---|---|---|
| D1 `query` keyword-only | `BusinessServer.query(*, token)`、`pyapi.models.Middle.query(*, token)`；调用点 `pyapi/packages/gui.py`、`test/tb/semantics_tb.py` 改为 `query(token=…)` | `test_middle_contracts.py::test_query_token_is_keyword_only`；`semantics_tb.py` rc=0 |
| D2 `execute_skill` log 参数 | `pyapi.models.Middle.execute_skill` 补 `log_level=None`、`log_max_bytes=None`（keyword-only） | `test_middle_contracts.py::test_execute_skill_exposes_log_overrides` |
| D3 update 整体校验 | 抽出 `validate_entry_shape()`，commit 与 update 共用；update 校验 remote 目标可解析、root 绝对、daemon python/端口等（允许只改 `root.default`） | `test_registration_server.py::test_update_rejects_entry_with_unresolvable_remote_role` |
| D4 update 白名单 | 只接受 `ssh/root/roles/runtime/cdslog`；`token`/`registered_at`/未声明字段/扁平别名一律 400（扁平别名翻译整体删除） | `test_registration_server.py::test_update_rejects_registered_at_and_flat_aliases`；`registration_http_six_step_tb.py` 改发白名单 body 后通过 |
| D5 token 不轮换 | `Registry.register(overwrite=True)` 换 token 直接 `RegistryError`；轮换必须 remove→register | `test_registry_decoupling.py::test_overwrite_must_not_rotate_token`、`::test_overwrite_with_same_token_replaces_entry`；`test_registry_more.py::test_overwrite_refreshes_timestamp` 改为同 token |
| D6 并发 update 不丢更新 | 新增 `Registry.update(user, patch, validator=…)`：文件锁内重读当前条目→深合并 patch→整体校验→写回 | `test_registration_server.py::test_concurrent_updates_do_not_lose_fields` |
| D7 第六步显式确认 | `register_user(..., confirm_commit=False)` 缺省拒绝且不落盘；`RegistrationFlow.cancel()` 对 committed 幂等 no-op | `test_register_flow.py::test_requires_explicit_commit_confirmation`、`::test_cancel_does_not_release_committed_session` |
| D8 `expected_*` 收窄 | spec 已收窄为“注册探测时比对，运行期不强制比对”，代码现状即为该口径，无需改动 | 注册第五步 fingerprint/banner 比对保持 |

### 7.2 O 系列（代码缺陷）

| 项 | 实施 | TB / 真机复核 |
|---|---|---|
| O1 rc=255 误分类 | 一次性命令执行自带 rc marker：远端 shell 完成即回传真实 rc；只有“无 marker + rc=255 + 本地 ssh 诊断”才判 transport | `test_ssh.py::test_remote_rc_marker_wins_over_stderr_heuristics`、`::test_wrapped_script_reports_rc_marker`；`one_shot_burst_tb.py` 72/72 |
| O2 隧道重试重置 deadline | 保留外层不可变 deadline，每次 attempt 取 `min(外层, now + attempt_settle)`，spawn 前检查剩余预算 | `test_ssh_tunnel_lifecycle.py::test_port_forward_retry_shares_the_call_deadline` |
| O3 本地摘要不受预算约束 | `RemoteClient._sha256_local`、`BusinessServer._sha256_file` 接受 deadline，分块前检查；超时清理 stage 且不改目标 | `test_tunnel_transfer.py::test_local_sha256_honours_call_deadline` |
| O4 运行期解析 `~` | `RemoteClient.expanded_root` 对 `~` root 报 `RemotePathError`；`resolve_remote_path` 拒绝 `~` 开头的 remote_path；删除运行期 HOME 查询与额外 channel lease | `test_tunnel_transfer.py::test_runtime_tilde_path_is_rejected` |
| O5 远端临时文件逃逸 | `SSHRunner(work_dir=role.root)`：常驻 shell 用 `mktemp -p <role root>` + `trap` 清理；无 work_dir 时保留回退 | `test_persistent_shell_protocol.py::test_remote_temp_files_use_injected_work_dir`；真机检查 role root 无残留 |
| O6 隧道健康只看进程 | `is_tunnel_alive` 与 POSIX ready 判定都要求 forwarding 可达，否则判失败并重建 | `test_ssh_tunnel_lifecycle.py::test_alive_process_with_dead_forward_is_not_healthy` |
| O7 proxy 静默忽略 | openssh backend + proxy 直接 `ValueError`；Skill 隧道（外部 OpenSSH）带 proxy 时明确 `RuntimeError`，不再静默直连 | `test_ssh.py::test_proxy_is_never_silently_ignored`、`::test_skill_tunnel_rejects_proxy` |
| O8 / O9 | 按裁决：目录目标保持 OS 语义、指纹临时文件允许，不改代码 | — |

### 7.3 真机复核时发现的追加缺陷（已修）

第二轮真机复核（`cov_remote_real` 首跑失败）暴露出 O3 修复的连带问题：`runtime.connect_timeout` 保留浮点后，
`ConnectTimeout=15.0` 被 OpenSSH 拒绝（`invalid time value`），隧道无法建立。

- 修复：`_common_ssh_options` 把 ConnectTimeout 渲染为整数秒（`ceil`，最小 1），内部仍保留浮点子预算；
- TB：`test_ssh.py::test_connect_timeout_rendered_as_integer_for_cli`（修复前红）；
- 真机：`cov_remote_real.py` 5/5 ok，`one_shot_burst_tb.py` 72/72，`recursive_link_check` PASS，
  `registration_http_six_step_tb.py --local-mode` rc=0，`fault_injection_tb.py` / `semantics_tb.py` rc=0。

### 7.4 第二轮门禁

- `python -m pytest test/unit test/integration test/scenario`
  → **566 passed, 1 skipped, 27 subtests passed in 329.91s**（2026-09-18，含 ConnectTimeout 回归 TB）。
