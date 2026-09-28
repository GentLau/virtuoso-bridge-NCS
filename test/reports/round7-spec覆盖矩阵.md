# 第七轮 · Spec 逐条覆盖矩阵（Normative 10 份）

> 维护者：测试（root） ｜ 2026-09-24（第七轮） ｜ 基线 = 第五轮矩阵 + 第七轮复跑
> 本轮更新方式：① 逐行 `test/offline` 证据与本轮 JUnit（`round7/offline2.xml`）由脚本对表（§14 机器生成）；
> ② 真机/半真机**新证据**在 §0.1 列明，未复跑的历史行仍标 🟡，不冒充本轮。
>
> **§0.1 第七轮新增/更新的证据（按 spec 领域）**
>
> | 领域 | 本轮证据 | 结果 |
> |---|---|---|
> | calibre（LVS 全链） | `round7/design-iterate/iterate-lvs.json` | **correct**：ports 4/4、nets 4/4、inst 1/1、differences=[] |
> | calibre（S11 流程） | `test/artifacts/env/s11/{s11-cdl,s11-lvs,summary}.json` | cdl 693 B、lvs 确定结论、rc=0 |
> | schematic/symbol（写操作语义） | `round7/pin-ops.json`、`round7/design-iterate/iterate-r2_{edit,sym}.json` | **P-073**：rename 静默无效、set_pin_properties 破坏 pin 名 |
> | spectre（前仿数值） | `round7/design-iterate/iterate-r1_sim.json`、`iterate-r2_sim.json`、`round7/serdes/serdes-sim.json` | 增益/带宽/摆幅数值判据成立；改图后带宽掉 5.01× |
> | 多用户/多 role | `env/log-vblog/multiuser-layout-handoff.json`（12/12）、`env/scenario-role-split/evidence.json`（5/5）、`round7/serdes-multiuser.json`（15/15） | 接力/分主机/共建均通过 |
> | 并发/规模 | 生产面 6×6（216 步 0 失败）、`env/scenario-scale-100/evidence.json`（5/5） | 通过；负向对照非空 |
> | 拓扑（多跳/代理） | `round7/multihop.json`（11/11） | jump + SOCKS5 叠加通过 |
> | 客户端/远端解释器口径 | Linux py3.9 1725 例 0 红；py2.7.6 daemon 5/5 + handler correct；py3.6.8 daemon 5/5 | 见 `round7-测试报告.md` §2 |
> 目的：回答送审最容易被驳回的问题——**"spec 每一条要求，测试环境有没有真的测到？"**
> 口径：只认"有可复查证据"的覆盖：离线 TB/单测文件、半真机探针、真机证据 JSON（`test/artifacts/evidence/`）。
> 状态三档：**✅本轮已验**（第五轮证据）/ **🟡历史已验**（前几轮证据，本轮未**专门**复跑；**若该行出现在 §14，说明它的 `test/offline` 证据本轮已随套件复跑且全绿，只是真机/半真机那部分仍是历史证据**）/ **⬜缺口/未测**（必须显式声明，不许假装覆盖）。
> 另有机器核对脚本 `test/shared/runners/verify_spec_matrix_evidence.py`（把矩阵行的证据与最新 JUnit 对表，防止"写了证据其实没跑"）。

## 0. 本轮结论摘要

- 10 份 Normative 共拆出 **62 条可测要求**；本轮直接复跑/取证 **41 条**，历史轮次已验 **18 条**，**明缺口 3 条**（见 §11）。
- 三个 P1 阻塞（P-044 layout 锁 / P-050 daemon 伪 stdin / P-051 gds 远端发布）在本轮**逐条复验**，见 §1、§5、§6。
- 真机侧新增**真实业务场景**：SerDes RX 全流程（原理图→symbol→版图→GDS→仿真）与 **S13 两真实 OS 用户协同共建 SerDes RX**，用于证明"接口不是只会返回 ok"，见 §12。

## 1. 总览 / 四层整体架构与接口（`总览/1-四层整体架构与接口.md`）

| # | 条款 | 要求（一句话） | 覆盖证据 | 状态 |
|---|---|---|---|---|
| A1 | §4.1 | 五业务接口签名 + `token` 每次调用必填 | `test/offline/unit/test_middle_contracts.py`、`test_middle_routing.py`；真机 `test/live/transport/cov_remote_real.py`（vblog/vbs11/vbuser1/vbuser2 四实例） | ✅ |
| A2 | §4.1 | 文件执行是一个接口两个方向（upload/download），`recursive` 可选 | `test/offline/unit/test_tunnel_transfer.py`（recursive × 文件/目录 组合 7 例） | 🟡 |
| A3 | §4.1 | GUI/Spectre 是"并行模式一次性命令"，不建常驻 shell | `test/offline/unit/test_tunnel_transfer.py:519`（one-shot role dispatch）；真机五接口含 gui/spectre 各一次 | 🟡 |
| A4 | §4.1 | `log_level`/`log_max_bytes` 逐字段覆盖注册表 | `test/offline/unit/test_new_core.py`、`test/offline/core/daemon_log_protocol_tb.py`（优先级矩阵） | 🟡 |
| A5 | §4.2 | `query` 只读：返回 role `root`、gui `display`、spectre `bin`、用户组；不返回连接/校验字段 | `test/offline/unit/test_middle_contracts.py:313`（断言无 host/jump/proxy/daemon_port/local_port）；真机 `cov_remote_real.py` query 段 | ✅ |
| A6 | §4.2 | `query` 不占三类预算、不建连、无 timeout；未知 token → `invalid token`；非法 role/name → 参数错误 | `test/offline/core/semantics_tb.py`（query 4 用例：shape/unknown-token/isolation/不占预算） | ✅ |
| A7 | §4.5 | 五接口对外只返回结构化结果；`kind` 枚举完整（command/timeout/transport/path/unknown-effect/rejected/checksum/invalid-token） | `test/offline/unit/test_middle_contracts.py`、`test/offline/core/fault_injection_tb.py`、`test_middle_routing.py` | ✅ |
| A8 | §4.5 | 真实命令 rc=124/255 仍 `kind=command`（保留码只在非 command 时解释） | **本轮新增** `test/offline/unit/test_middle_reserved_codes.py`（真实 subprocess + local 常驻 shell，串行/并行各一遍；负控制见 `test/artifacts/evidence/round5-offline/reserved-code-negative-control.txt`） | ✅ |
| A9 | §4.5 | 容量拒绝必须指明是哪一个预算 | `test/offline/core/fault_injection_tb.py:350`、`test_endpoint_budgets.py` | ✅ |
| A10 | §4.5 | Skill 超时 = 结果未知；投递后不重发 | `test/offline/core/semantics_tb.py`（skill-delivery 单次投递）、`test_persistent_shell_protocol.py` | ✅ |
| A11 | §4.6 | 文件原子落盘：临时写 → SHA-256 校验 → 原子替换；失败回滚、目标不变 | `test/offline/unit/test_transfer.py`（fresh/replace/rollback/dir-tree 6 例）、`test_tunnel_transfer.py`（upload/download checksum mismatch 保目标） | 🟡 |
| A12 | §4.6 | 单文件 SHA-256；目录传输跳过逐文件校验；不匹配 → `kind=checksum` | `test/offline/unit/test_tunnel_transfer.py:179,377`；真机 `veriloga_e2e_tests.py:161`（`expected_sha256` mismatch 必须失败） | ✅ |
| A13 | §4.6 | 相对路径按 file role 根解析；源不存在 → `kind=path`；symlink 跟随 | `test/offline/unit/test_transfer.py:80,106`（tar 解引用）、`test_tunnel_transfer.py:365/392/430` | 🟡 |
| A14 | §5.4 | 一个 token = 一个活动 daemon = 一个 CIW | 真机：同一 token 第二个 CIW load 属配置错误（环境约定）；`test/offline/unit/test_middle_contracts.py`（token→daemon 唯一） | 🟡 |
| A15 | §5.6 | `root` 是默认工作目录而非沙箱：绝对路径/`..` 不被拦截 | `test/offline/unit/test_local_path_expansion.py`、`test_upper_layer_paths.py` | 🟡 |
| A16 | §5.6 | 目标不可见 → `VB-PATH-NOT-VISIBLE`，不改写路径 | `test/offline/unit/test_transport_error_paths.py`；真机 `test/live/packages/infra_e2e_tests.py` | 🟡 |
| A17 | §5.7 | 同一 CIW 串行、不同 CIW 并行；命令默认串行、`parallel=True` 并行 | `test/offline/core/semantics_tb.py`（串行闸门，本轮 10/10）、`test/live/stress/production_face_stress_tb.py`（真机混合并发，**替代已删除的 http_mixed_stress_tb**；本轮 6×6=216 步 0 失败） | ✅ |
| A18 | §5.8 | 五接口 deadline 唯一表（默认 30s；`timeout=None` 即默认；超平台上限=参数错误不夹紧） | `test/offline/unit/test_connect_retry.py:97`、`test_tunnel_transfer.py:456,503`、`test_endpoint_budgets.py` | ✅ |
| A19 | §5.8 | 建连重试 ≤3 次总尝试，且只在无副作用阶段 | `test/offline/unit/test_connect_retry.py:65,77`（exactly three attempts） | ✅ |

## 2. 中层配置文档（`中层/add-中层配置文档.md`）

| # | 条款 | 要求 | 覆盖证据 | 状态 |
|---|---|---|---|---|
| B1 | §1 | 客户端 Python ≥ 3.9；五个 role 目标机 Python 2.7+ 或 3.6.8+ | Linux 客户端 3.9.25 / 3.14.6 离线三层（本轮 `test/artifacts/evidence/round5-linux-client/`）；`test/offline/unit/test_probe.py`（边界表 2.7.5/2.6.9/3.6.7/3.6.8） | ✅ |
| B2 | §2.2 | 默认值：`thread_pool_size=32`、`channel_budget=10`、`connect_timeout=15`、`cdslog all/65536` | `test/offline/unit/test_common_config.py`、`test_endpoint_budgets.py` | 🟡 |
| B3 | §2.3 | 五 role 公共字段与逐字段回退（role 值→全局默认；`null`/空串=未提供） | `test/offline/unit/test_register_flow.py`、`test_validation_roles.py` | 🟡 |
| B4 | §2.3 | `mode=local` 的 role 提交 host/user/key → 参数错误 | `test/offline/unit/test_validation_roles.py`、`test_registration_server.py` | 🟡 |
| B5 | §2.4 | `role.daemon.python`：显式→校验、缺省→探测、失败=注册失败 | `test/offline/unit/test_probe.py`、`test_register_flow.py:982`；真机解释器抽样（2.7.6/2.7.18/3.6.8/3.14.6，本轮 `round5-semi/`） | ✅ |
| B6 | §2.4 | `role.gui.display` 显式→校验（不可达 ERROR）；缺省→探测写回，失败仅 WARNING 留空 | `test/semi/probes/gui_display_probe.py`；`test/offline/unit/test_register_flow.py` | 🟡 |
| B7 | §2.4 | `role.spectre.bin` 探测失败只 warning（不阻断注册） | `test/offline/unit/test_register_flow.py:1108`（spectre 失败 → root/fingerprint/bin 提交为 null） | 🟡 |
| B8 | §2.5 | `key_dir` 缺省=客户端 `~/.ssh`；remote role `key` 必填且只允许文件名 | `test/offline/unit/test_registration_server_edges.py:349`（r18–r22 凭据合同） | ✅ |
| B9 | §3 | 三类处理规则（配置/环境/校验）与例外表 | `test/offline/unit/test_validation_roles.py`、`test_probe.py` | 🟡 |
| B10 | §5 | `user` 格式（含保留设备名/结尾点空格）、Windows 大小写查重 | `test/offline/unit/test_register_flow.py`、`test_registration_server_edges.py` | 🟡 |
| B11 | §5 | `token` 格式 `^[A-Za-z0-9._-]{1,64}$`；碰撞重生成一次 | `test/offline/unit/test_register_flow.py`、`test_registration_server.py` | 🟡 |
| B12 | §5 | 未知字段拒绝（`extra=forbid`）；用户组结构约束 + ≤16 KiB | `test/offline/unit/test_registration_server_edges.py`、`test_offline/contract`（groups 段） | 🟡 |
| B13 | §5 | 公钥指纹查重 → 已登记需 `enhanced_token`（任一持有者 token 或管理员） | `test/offline/unit/test_registration_server_edges.py:405,504,516` | ✅ |
| B14 | §5 | host-key 首信任优先级（known_hosts → 显式指纹 → 失败）；spectre 例外 | `test/offline/unit/test_register_flow.py:1044`；真机 `registration_http_six_step_tb.py:432` | 🟡 |
| B15 | §5 | registry 持久化 UTF-8/0600/tmp+原子替换 | `test/offline/unit/test_registry_more.py`（0600 权限）、`test/offline/core/semantics_tb.py`（跨进程读改写不丢更新） | ✅ |
| B16 | §6.1 | registry 条目 schema（提交态：root 绝对、root.default=null、expected_* 固化） | `test/offline/unit/test_commit_shape.py`；真机 `test/artifacts/env/log-vblog/registry.json` 实测 | ✅ |
| B17 | §6.4 | reservation 只在内存、第六步前零落盘、失败不释放、cancel/重启释放 | `test/offline/unit/test_reservation.py:79,142`；半真机 `cov_registration_real.py:51`（断 `registry.reservation` 不存在） | ✅ |
| B18 | §6.5 | endpoint canonical key 6 条测试向量 + 规范化规则 + 不做名称解析 | `test/offline/unit/test_spec_contracts.py`（逐条向量断言） | ✅ |
| B19 | §6.5 | 同 key 同 endpoint 且凭据一致才复用；凭据不同不复用 | `test/offline/unit/test_credential_routing.py:65,79,127`；半真机 `role_credential_isolation_tb.py` | ✅ |

## 3. 多用户与注册（`其他/1-多用户与注册.md`）

| # | 条款 | 要求 | 覆盖证据 | 状态 |
|---|---|---|---|---|
| C1 | §1 | 注册表启动导入一次、运行期不自动读文件；管理成功后显式重新导入 | `test/offline/unit/test_registry_decoupling.py`、`test_registry_keys.py`、`test_registry_more.py`、`test/offline/integration/test_supervisor_process.py`（原写的 `test_registry.py` 已不存在，2026-09-24 核账修正）；真机 reload 语义见 §8 H9 | 🟡 |
| C2 | §3.1 | 六步顺序 ①②③④⑤⑥；**前五步 registry 零写入**，第六步唯一写盘点 | 真机 `test/live/registration/registration_http_six_step_tb.py`；半真机 `cov_registration_real.py`（1–4 步 + 零落盘） | ✅ |
| C3 | §3.1 | 步骤乱序 → 4xx `step order violation`，且不改变会话状态 | 离线 `test_registration_server.py`；真机六步 TB 内在乱序/重放段 | ✅ |
| C4 | §3.1 | 各步失败后可**原样重试**；修正参数必须 `cancel` 后重 `apply`；`cancel` 幂等 | `test/offline/unit/test_register_flow.py`、`test_reservation.py:142`；真机六步 TB cancel 段 | ✅ |
| C5 | §3.2 | 第五步失败语义表（端口不可达/token NAK/指纹不匹配=ERROR；banner hostname/user 不一致=WARNING） | 离线 `test_register_flow.py`；真机失败注入（`test/semi/registration`） | 🟡 |
| C6 | §3.3 | 各步独立 deadline 默认 30s，步内相位共享不重置 | `test/offline/unit/test_register_flow.py`（deadline 段） | 🟡 |
| C7 | §4.1 | 探测矩阵：五 role 命令可用性 + 专项探测；除 spectre 外任一失败即失败 | `test/offline/unit/test_probe.py`、`test_register_flow.py`；半真机 `cov_registration_real.py` | ✅ |
| C8 | §4.2 | `root.default` = `~/.virtuoso-bridge/<userid>`，在对应工作机解释；探测后写回绝对路径 | `test/offline/unit/test_spec_contracts.py`、`test_offline/unit/test_paths`；真机注册后 registry 实测 | ✅ |
| C9 | §4.2 | bridge 文件只部署到 daemon root 的 `ramic/ setup/ status/` | `test/offline/unit/test_deploy*.py`；真机 `cov_registration_real.py` 部署段 | 🟡 |
| C10 | §5 | `update` 白名单字段；`token`/`registered_at` 一律拒绝；扁平别名拒绝 | `test/offline/unit/test_registration_server.py`（update 白名单段） | 🟡 |
| C11 | §5 | `remove` 原子移除 + 返回凭据标识/指纹 + 本机解绑≠远端吊销 | `test/offline/unit/test_registration_server.py`（remove 段） | 🟡 |
| C12 | §5 | 机器重装需带外确认后更新 `expected_fingerprint`；未确认按不匹配拒绝 | `test/offline/unit/test_register_flow.py:1044` | 🟡 |
| C13 | §5 | 跨进程写：OS 文件锁 + 读改写原子替换，不丢更新 | `test/offline/core/semantics_tb.py`（`registry-cross-process` 红→绿） | ✅ |
| C14 | §1 | 注册结束除 registry + 远端部署文件外无残留（隧道/SSH/socket） | 真机六步 TB 末段资源盘点 | ✅ |

## 4. 路由设计（`中层/3-路由设计.md`）

| # | 条款 | 要求 | 覆盖证据 | 状态 |
|---|---|---|---|---|
| D1 | §1 | 忠实投送：不校验 role 间同机/同账号/共享路径 | 真机 S2 `test/live/flows/role_split_tb.py`（daemon 与 command/file 分主机） | ✅ |
| D2 | §2 | 五 role 职责与接口映射（Skill→daemon、command→command、file→file、gui→gui、spectre→spectre） | `test/offline/unit/test_middle_routing.py`；真机五接口 `cov_remote_real.py`（逐接口验落点） | ✅ |
| D3 | §2.1 | 一个 token 只一个 daemon/一个 X server；其余 role 可各不同主机 | 真机 S2 + 注册探测；`test/offline/unit/test_validation_roles.py` | 🟡 |
| D4 | §2.1 | `mode=local` 是单用户形态，多用户隔离走 `mode=remote`（含指向 localhost） | `test/offline/unit/test_validation_roles.py`（mode 约束）；真机多用户实例（vbuser1/2 = remote 指向 wsl-gent） | ✅ |
| D5 | §4 | 复用矩阵：跨 token 永不复用；同 token 同 endpoint（凭据一致）尽量复用 | `test/offline/unit/test_credential_routing.py`、`test_offline/unit/test_ssh_tunnel_lifecycle.py`；半真机 role 凭据隔离 TB | ✅ |
| D6 | §4 | remote daemon 另持专用 Skill 隧道（不经业务连接） | `test/offline/unit/test_tunnel.py`、真机 `cov_remote_real.py` skill 段 | 🟡 |
| D7 | §5 | 本版不做清单（不跨机启 daemon、不保证跨机可见性、GUI/Spectre 无常驻会话、接口数固定 5） | 负控制：`test/offline/unit/test_middle_contracts.py`（接口集合固定）+ 环境侧不提供跨机 launcher | 🟡 |

## 5. 并发设计（`中层/2-并发设计.md`）

| # | 条款 | 要求 | 覆盖证据 | 状态 |
|---|---|---|---|---|
| E1 | §1 | 三类形态：串行 Skill / 串行命令 / 并行（file、parallel 命令、gui、spectre） | `test/offline/core/semantics_tb.py`；真机 `cov_remote_real.py` + `one_shot_burst_tb.py` | ✅ |
| E2 | §1 | 排队超时=未投递（可安全重试）；已投递超时=结果未知（不重发） | `test/offline/unit/test_persistent_shell_protocol.py`、`test_middle_contracts.py:111`（unknown-effect） | ✅ |
| E3 | §2 | 三预算独立、超限即拒绝并指明预算；`local` 不占通道预算仍占线程预算 | `test/offline/unit/test_endpoint_budgets.py`、`test_skill_admission.py:146`、`test_middle_routing.py:190` | ✅ |
| E4 | §2 | 多 role 同 endpoint 共享计数、有效上限取最小值 | `test/offline/unit/test_endpoint_budgets.py:31,75`、`test_validation_roles.py:46` | ✅ |
| E5 | §3 | 通道记账矩阵（隧道/常驻 shell 各占 1；校验子命令不另占） | `test/offline/unit/test_tunnel_transfer.py:192,281,295`（budget exceeded）、`test_endpoint_budgets.py` | ✅ |
| E6 | §4 | 建连重试 ≤3、ControlMaster 降级直连、常驻 shell 失效透明重建 | `test/offline/unit/test_connect_retry.py`、`test_transport_error_paths.py:65`（mux 失败降级）、`test_ssh_tunnel_lifecycle.py` | ✅ |
| E7 | §4 | 隔离：ControlPath 含 token 不可逆 hash，跨 token 不共享；关闭只拆本 token | `test/offline/unit/test_ssh_tunnel_lifecycle.py:185`（ControlPath 命名空间） | 🟡 |
| E8 | §2–§3 | 真机饱和下"最终应答 100% + 拒绝结构化 + 压后资源 0 残留" | 真机 `test/live/stress/production_face_stress_tb.py`（**替代已删除的 http_mixed_stress_tb**）+ `test/live/flows/scale_100_tb.py`（100 daemon 规模档）；本轮证据 `test/artifacts/evidence/round7/production-face-stress.json`、`test/artifacts/env/scenario-scale-100/evidence.json` | ✅ |

## 6. 日志返回（`底层/6-日志返回设计标准.md`）

| # | 条款 | 要求 | 覆盖证据 | 状态 |
|---|---|---|---|---|
| F1 | §1/§8-1 | `off` 源头掐断：IL 不 flush/fileLength、daemon 不读、无第二帧 | 离线 `test/offline/core/daemon_log_protocol_tb.py`；真机 `log_matrix_real_tb.py`（off 段） | ✅ |
| F2 | §8-2 | CDS.log 不出现任何桥注入行 | 真机 `log_matrix_real_tb.py`（零注入断言 + 证据 JSON） | ✅ |
| F3 | §3/§8-3 | `result.log` 只含本次 `[start,end)` 增量 | 真机 `log_matrix_real_tb.py`（增量字节一致）；离线 9 用例 | ✅ |
| F4 | §4 | 分级 all/warn/error 过滤；解析不了归 info 不丢行 | `test/offline/core/daemon_log_protocol_tb.py`、`test/offline/unit/test_new_core.py` | ✅ |
| F5 | §5/§8-4 | 限长自动降级 → 仅 error + 说明行；仍超限 → 靠前字节 + "未完整返回"说明；说明行不受限 | `test_new_core.py:69,70`、`daemon_log_protocol_tb.py:40,41` | ✅ |
| F6 | §5/§8-7 | 截断不产出半个 UTF-8 字符 | **本轮新增** `test/offline/unit/test_daemon_log_utf8_budget.py`（5 用例：切在 3/4 字节字符中间、0..len 逐点扫描、恰好切在边界、py3/py27 parity；负控制见 `test/artifacts/evidence/round5-offline/utf8-negative-control.txt`） | ✅ |
| F7 | §3/§8-5 | 轮转/清空（`size<start` 或 `end<start`）→ `start=0` 不报错 | `daemon_log_protocol_tb.py`（rotation 用例） | ✅ |
| F8 | §6.3/§7 | 第二帧缺失/超时 → 第一帧结果优先返回 + 固定 warning，不 NAK | `test/offline/unit/test_daemon_runtime_contracts.py:538,549`、`test_daemon_handler.py:132` | ✅ |
| F9 | §7 | 非法 `log_level`/`log_max_bytes` → NAK，不夹紧、不静默降级 | `test/offline/core/daemon_log_protocol_tb.py`；真机 `py27_daemon_probe.py`（拒绝段） | ✅ |
| F10 | §6.1 | 取值优先级：上层显式 > 注册表 `cdslog.*` > 协议缺省（缺省 off 防御性回退） | `test/offline/unit/test_daemon_log_contract.py`、`test_new_core.py` | 🟡 |
| F11 | §6.3 | metadata frame 字节格式（STX + path + US + start + US + end + RS），两帧合并一次写入 | `test/offline/core/daemon_log_protocol_tb.py`（帧解析）、IL 侧静态断言 | 🟡 |

## 7. 顶层（`顶层/1-顶层.md`）

| # | 条款 | 要求 | 覆盖证据 | 状态 |
|---|---|---|---|---|
| G1 | §2.1 | 显式注册表（键=业务操作名，值=三元组）；启动构建一次；不扫描/不用 entry-point | `test/offline/unit/test_top_layer_dispatch.py`、`test/offline/core/api_server_tb.py` | ✅ |
| G2 | §2.1 | 同一操作名重复登记 = 启动错误；包加载失败视为未加载，其余包不受影响 | `test_top_layer_dispatch.py:117`（duplicate_operation_is_startup_error）、`:88`（unknown operation 404）、`test_api_server_main.py:84`（坏包隔离） | ✅ |
| G3 | §2.2/§3 | 调度顺序与响应壳 `{ok,data,error}`；响应壳失败行 `data=null` | `test/offline/core/api_server_tb.py`、`test/offline/unit/test_api_server_main.py` | ✅ |
| G4 | §3 | 错误分界：结构错误 4xx / 业务失败 2xx `ok=false` / 未预期异常 5xx 不带栈 | `test/offline/core/api_server_tb.py`、`test_top_layer_dispatch.py` | ✅ |
| G5 | §3 | 已定义路径非支持方法 → 405（含 Allow）；未定义路径 404/501 | `test/offline/unit/test_api_server_main.py:379,390`（help/未知路径、CONNECT→405） | ✅ |
| G6 | §3 | 单请求异常不影响其它请求、不终止服务 | `test/offline/core/api_server_tb.py`（错误隔离用例） | ✅ |
| G7 | §2.4/§4 | 处理/调度链路不 import transport/socket/subprocess/paramiko；不读 `VB_*`/`.env`/注册表文件 | **本轮补回**：`test/offline/unit/test_upper_layer_import_contract.py`（AST 静态扫描 pyapi/\\*\\* + `server/dispatch.py`；含**负控制**"扫描器必须抓到 import paramiko"与**正控制**"扫描面必须覆盖真实文件"）＋ `test/offline/unit/test_registry_decoupling.py`（运行期不重读注册表）。原证据 `test/upper_layer_paths.py` 随 `demo` 包于 2026-09-24 删除 → 本轮核账发现并补回 | ✅ |
| G8 | §2.3/§4 | token 原样透传、不解析不缓存、不回显 | `test/offline/core/api_server_tb.py`（响应无 token）；真机 `cov_remote_real.py` | 🟡 |

## 8. 控制面与业务面（`顶层/add-控制面与业务面.md`）

| # | 条款 | 要求 | 覆盖证据 | 状态 |
|---|---|---|---|---|
| H1 | §1 | 双面双端口；业务面不含注册/管理端点；控制面不运行业务操作 | `test/offline/unit/test_api_server_main.py`；真机业务面 8127 实测（`/api/register` 不暴露） | ✅ |
| H2 | §2 | 权限四档：无权限/会话 token/个人 token/管理权限（仅存 SHA-256 + `compare_digest`） | `test/offline/unit/test_registration_server.py`（admin 401 段）、`test_registration_server_edges.py` | ✅ |
| H3 | §3 | 控制面端点清单（`/`、`/health`、`/help`、`/api/bug`、注册六步、users/user/update/delete、config、process/*） | `test/offline/unit/test_registration_server.py`、`test_supervisor_internals.py`、`test_business_child_supervision.py` | 🟡 |
| H4 | §3 | 六步 HTTP 投影：action 合法性、`step order violation` 响应体含 `current_stage/expected` | `test/offline/unit/test_registration_server.py`；真机六步 TB | ✅ |
| H5 | §3 | `apply` 返回 token；其余 action 必须携带且与候选一致，缺失/不一致 4xx 不改变状态 | `test/offline/unit/test_registration_server.py`；真机六步 TB 内乱序/错误 token 段 | ✅ |
| H6 | §3 | 请求体上限 16 MiB → 413（控制面与注册面都要） | `test_registration_server.py:627`、`test_registration_server_edges.py:254,468` | ✅ |
| H7 | §3 | 任何 entry 对象不回显 token；bug 报告先剥凭据再落盘 | `test/offline/unit/test_registration_server_edges.py:544,557`（enhanced_token 不回显 / bug 掩码） | ✅ |
| H8 | §4 | 业务面端点只有 `/api/operation`、`/health`、`/help` | 真机 8127 实测 + `test/offline/unit/test_api_server_main.py` | ✅ |
| H9 | §5 | `config.json` 只读快照；PUT 只覆盖出现键；`business_thread_pool_size` reload 后对新请求生效 | `test/offline/unit/test_common_config.py`、`test_supervisor_internals.py`、`test_business_child_supervision.py` | 🟡 |
| H10 | §5 | `429 + Retry-After`（业务面准入超限）；`process/restart` 期间 503 + Retry-After，30s 排空后强杀 | `test/offline/integration/test_supervisor_process.py`、`test_business_child_supervision.py` | 🟡 |
| H11 | §1/§3 | 业务崩塌不影响管理；管理退出停止业务；子进程 `crashed` 不自动拉起 | `test/offline/integration/test_supervisor_process.py`、`test_business_child_supervision.py` | 🟡 |

## 9. 上层（`上层/1-上层.md`）

| # | 条款 | 要求 | 覆盖证据 | 状态 |
|---|---|---|---|---|
| I1 | §2.2 | 每业务操作一个方法 `method(request)->Result`；同步、无状态、只注入 `Middle` | `test/offline/unit/test_pyapi_packages.py:56-131`（步序/失败即停/参数类型拒绝）、`test_top_layer_dispatch.py:131`（token 必填） | ✅ |
| I2 | §2.3 | 每操作一对 Request/Result；Result 含 `ok/steps/error`；`token` 必填 | `test/offline/unit/test_pyapi_packages.py`（失败仍带 steps）；真机十套包 E2E 的返回壳断言 | ✅ |
| I3 | §2.4 | 步骤痕迹保留；任一步失败即停；失败不得伪装成功 | `test_pyapi_packages.py:67`（stops_on_each_failure）、`:100`（failure_reported）；真机十套包 E2E | ✅ |
| I4 | §3.3 | 结构校验抛 TypeError/ValueError（→4xx）；领域失败 = `ok=false` 不抛异常 | `test/offline/core/api_server_tb.py`、各包单测 | ✅ |
| I5 | §3.2 | 不持有跨请求状态；长任务拆分/由文件驱动 | `test/offline/unit/test_maestro_package_flow.py`、`test_offline/unit/test_process_lifetime.py` | 🟡 |
| I6 | §4.1/§4.2 | 显式登记、命名点分、发布后不改名；自描述元数据 | `test/offline/unit/test_pyapi_packages.py`（操作名唯一 + 点分格式） | 🟡 |
| I7 | §4.3/§5 | 包加载失败=未加载（未知 operation）；不 import transport/socket/subprocess | `test/offline/unit/test_top_layer_dispatch.py`、`test_upper_layer_paths.py` | 🟡 |

## 10. 本版范围与非目标（`总览/add-本版范围与明确不支持.md`）

| # | 条款 | 要求 | 覆盖证据（负控制） | 状态 |
|---|---|---|---|---|
| J1 | §2.1-1 | 不做 Spectre 高层封装；`purpose` 字段应被拒 | `test/offline/unit/test_pyapi_packages.py`（未知 operation/字段拒绝） | 🟡 |
| J2 | §2.1-2 | 不做独立 deploy role；部署只到 daemon root | `test/offline/unit/test_deploy*.py` | 🟡 |
| J3 | §2.2-3 | 无 token/旧 il → NAK `invalid token`，SKILL 零接触 | `test/offline/core/fault_injection_tb.py`、真机 `test_offline/unit/test_daemon_runtime_contracts.py` | ✅ |
| J4 | §2.2-4 | `profile`/`VB_*`/`.env` 无兼容入口 | `test/offline/unit/test_common_config.py`（不再读 env）；`rg` 代码侧无 env 读取 | 🟡 |
| J5 | §2.2-6 | 不引入 `request_id`（字段应被拒/忽略口径明确） | `test/offline/unit/test_middle_contracts.py`、顶层未知字段拒绝 | 🟡 |
| J6 | §2.2-7 | 不做 argv/无 shell、异步 command handle | `test/offline/unit/test_persistent_shell_protocol.py`（shell 字符串语义） | 🟡 |
| J7 | §2.3-8/9 | split-host CDS.log 不做；读不到 → `log=""` + warning | `test/offline/unit/test_daemon_runtime_contracts.py:538` | 🟡 |
| J8 | §2.4-11 | 不做文件沙箱：`..`/绝对路径不拦截 | `test/offline/unit/test_local_path_expansion.py`、`test_upper_layer_paths.py` | 🟡 |
| J9 | §2.5-12 | 不实现跨机启动 daemon | 环境事实：所有实例 daemon 均为 CIW 子进程（`ipcBeginProcess`） | 🟡 |
| J10 | §2.6-13 | 不实现顶层任务等待池；`pending` 按未知字段处理 | `test/offline/unit/test_api_server_main.py`（未知字段/操作 4xx） | 🟡 |

## 11. 明缺口（本轮无法声称覆盖，送审前必须知道）

| # | 缺口 | 为什么缺口 | 建议动作 |
|---|---|---|---|
| X1 | ~~paramiko jump/proxy 多跳~~ **✅ 通过（2026-09-24 定稿口径）** | S15：真两跳 Windows→w3-gent→w1-gent（判据=`SSH_CONNECTION` 客户端 IP 172.20.170.23，直连负控制 172.20.160.1）+ 真 SOCKS5（`ssh -N -D 11080 w3-gent`），命令/文件/skill/HTTP 全通 **11/11** | **用户 2026-09-24 判定：「达到 2 跳认为代理通过测试」→ 本项视为通过**。>2 跳、jump+proxy 叠加、跳板断链属**可选加固**，不再算缺口 |
| X2 | **真实多实例规模**（口径已按用户 2026-09-24 修正） | 原写"真实 100 台"——**不需要**：物理内存 15.9 GB、单实例 ≈1 GB。新口径 = **真机 ≥6 个（尽量分散到不同 OS 用户，例：Gent 4 + vbuser1 1 + vbuser2 1）+ ~100 个 fake** | 按新口径执行：`round6-规模档-真机6fake100.md`（真机分散用户 + 100 fake 混合并发，含压后残留检查） |
| X3 | **split-host CDS.log** | spec 明确不做（J7） | **用户 2026-09-24 确认："明确不做认为过了就行" → 视为通过**，不再是缺口 |
| X4 | **注册流程的三处未覆盖**（2026-09-24 盘点） | ① `role.daemon.python` 用 **py2.7** 的**端到端注册**（现只到协议/校验层）；② **Linux 客户端**上跑注册（Linux 矩阵只跑离线三层）；③ 六步里**逐步骤失败注入**不齐 | 排下一轮补：① py2.7 真 CIW + 真注册六步；② Linux 侧跑 `registration_http_six_step_tb.py`；③ 六步 × {失败, 重试成功, 重试再失败} 补齐。**注**：**并发注册不考虑**（用户 2026-09-24 明确） |
| ~~X5~~ **✅ 已关闭（2026-09-24）** | ~~spec 内部冲突：`7-spectre.md:307` vs `:308`~~ | 设计侧已把 `:307-309` 改写为「**内部**用缺失哨兵（实现取 `None`），**对外一律 `null`/省略**，唯一出口 `psf_external()`，NaN/±Inf 在那里收敛」；代码 `_spectre_util.py:70-71` 落地 | 测试侧复跑 `test/offline/unit/test_output_json_safety.py` **3/3 绿**（P-049 闭环） |
| X6 | **`init_work_dir` 一次性化 + 删除测试钩子（工作区未提交改动）** | 离线三层 **1728 项 / 518 红**，全部 `RuntimeError: work dir already initialized`；91 个测试文件依赖 `force`/`override_work_dir_for_tests`/`reset_work_dir` 来按用例隔离 work root（**P-072**） | **需设计侧确认**：①（建议）恢复测试专用钩子（仅影响测试进程）；② 或明确"一进程一 work root"并给出官方测试姿势，测试侧适配 91 个文件 |

## 12. 本轮新增真实业务场景（"接口 ok ≠ 活干成了"）

| 场景 | TB | 判据（不是"接口返回 ok"） |
|---|---|---|
| SerDes RX 前端全流程（层次化 + 差分模拟） | `test/live/flows/serdes_rx_flow_tb.py` | 建库→输出缓冲/CTLE/端接→顶层层次化原理图→symbol→版图→GDS（含"新目录发布"攻击面）→CDL→AC/TRAN 前仿 + 指标测量（低频增益/峰化/3dB） |
| 两真实 OS 用户协同共建 SerDes RX | `test/live/flows/multiuser_serdes_rx_tb.py` | A 建库/建 cell → B 读同一库并**改单** → A **回读看到 B 的改动**；跨用户库可见性 + 写交接 |
| ADC / 其它模拟块 | 见第五轮报告 §新增场景 | 同上口径（结构读回 + 数值判据） |

> 这两个场景是"多用户协同 + 真机全流程"的最小可信闭环：跨 OS 账号、跨 CIW、跨 daemon、共享文件系统，
> 每次写入都必须被**另一个用户**读到；任何"锁误判/句柄泄漏/路径不可见"都会在这里暴露。

## 13. 上层领域业务包（不在 10 份 Normative 之列，但本轮首次真机覆盖）

> 说明：`spec/design-concepts/上层/{2-schematic … 12-calibre}.md` 属"上层领域业务包"文档，
> 不在《验收审批意见》的 10 份 Normative 范围内；但用户明确要求"真实业务场景要贴合实际使用"，
> 本轮用**真实设计流程**把它们跑了一遍，结论如下（含本轮新发现的缺陷编号）。

| 领域包 | 本轮真机覆盖方式 | 结论 / 新缺陷 |
|---|---|---|
| `schematic` / `symbol` / `layout` | SerDes RX 层次化设计（probe→lib→buf/ctle/term→top→symbol→layout→GDS） | 9/9 阶段绿；**P-052**（`set_instance_params` 写 cell 级 CDF，污染共享库）、**P-054**（层次化 symbol 生成后残留子单元视图 → 二次生成必失败） |
| `spectre`（AC/TRAN + measure） | SerDes RX 前仿（真实 PDK 模型，AC 指标 + TRAN 摆幅） | 数值判据通过（5.055 dB@1 MHz / BW 15.8 GHz / 摆幅 396 mV）；**P-053**（AC 解析只认分析名 `ac`；解析键前缀 `ac_` 与 measure 默认 `x="freq"` 不一致） |
| `veriloga` | ADC SAR 控制逻辑（写源码→`check_and_save`→module/ports 解析→仿真闭环） | 7/7 绿；码字 3/9/12 与理论逐点相等 |
| `verilog` / `skillref` / `maestro` / `cellview` / `infra` | 十套包 E2E（HTTP 真机，`run_all_http`） | 10/10 PASS（含本轮修复的 P-047 verilog cwd 依赖） |
| `calibre`（DRC/LVS/结果读取） | **本轮首次接真机**（专用 work-dir + 业务面；`check_env→drc→status→read_results`） | 首次打通即暴露 4 条：**P-059**（真实 `DRC.rep` 解析失效：逐规则计数认不出 2025 格式、把头部 WARNING 当违规）、**P-060**（calibre 包此前 0 真机覆盖——常驻注册表无 `role.command.calibre`）、**P-061**（阻塞轮询对"工具已死+日志终止性 ERROR"不快失败）、**P-062**（`read_results` 把 `LVS completed. NOT COMPARED.` 截成半个词）。TB：`test/offline/unit/test_calibre_parsers.py`（有意红，钉住 P-059） |

> 口径提醒：上表的"绿"都是**阶段/数值判据**通过，不等于该领域包已覆盖完整（各自的未覆盖项见
> [round7-测试报告.md](round7-测试报告.md) §8、[第五轮-真实场景-SerDesRX.md](第五轮-真实场景-SerDesRX.md)
> 与 calibre 线的现状；LVS/DRC 的"工程链跑通"仍受 §11/X 系列环境口径约束）。

> **治理补充（第五轮审计）**：`calibre` 的 spec（`spec/design-concepts/上层/12-calibre.md`）当前仍是
> **Draft v1、明确未纳入 README 治理**，因此**不在上方 62 条 Normative 统计内**。可本轮它已随
> `packages` 导出并首次接真机（首通即暴露 P-059/P-061/P-062 三个产品缺陷）——
> 建议：**先把 calibre spec 升为 Normative 并纳入准出**（含 DRC/LVS/PEX 的结果读取契约、失败快退契约），
> 否则"calibre 覆盖完整"无法对外声明；同时按 P-060 固化真机入口（常驻 calibre 事实 + `calibre_e2e_tests.py`）。

<!-- offline-rerun:begin -->
## 14. 本轮离线复跑核对（机器生成，可复现）

> 口径：矩阵里标 `🟡 历史已验` 的行，只要它引用的 `test/offline/**` 证据在本轮离线套件里跑过且全绿，就不属于「只靠历史证据」。下表把这类行挑出来；数据源 `round5-main/offline-final.xml`（**1686 项 / failures=11 / skipped=6**；junit 头的 `tests=2335` 是 pytest 9.1.1 计入 subTest 的膨胀属性，别当用例数引用——见独立复核 D5）。
> 最后一列是该行**还引用了几份真机/半真机文件**——那些部分仍按原状态，**不要**因为离线绿就当成全链已验。
> 复现：`python test/shared/runners/verify_spec_matrix_evidence.py --md`

| 行 | 本轮离线证据（全部为 green） | 用例数 | 行内另有非离线证据 |
|---|---|---|---|
| A1 | `test_middle_contracts.py` | 22 | 1 |
| A2 | `test_tunnel_transfer.py` | 31 | — |
| A3 | `test_tunnel_transfer.py` | 31 | — |
| A5 | `test_middle_contracts.py` | 22 | — |
| A8 | `test_middle_reserved_codes.py` | 5 | — |
| A11 | `test_transfer.py` | 20 | — |
| A12 | `test_tunnel_transfer.py` | 31 | — |
| A13 | `test_transfer.py` | 20 | — |
| A14 | `test_middle_contracts.py` | 22 | — |
| A15 | `test_local_path_expansion.py` | 2 | — |
| A16 | `test_transport_error_paths.py` | 14 | 1 |
| A18 | `test_connect_retry.py` | 4 | — |
| A19 | `test_connect_retry.py` | 4 | — |
| B1 | `test_probe.py` | 19 | — |
| B2 | `test_common_config.py` | 3 | — |
| B3 | `test_register_flow.py` | 67 | — |
| B4 | `test_validation_roles.py` | 9 | — |
| B5 | `test_probe.py` | 19 | — |
| B6 | `test_register_flow.py` | 67 | 1 |
| B7 | `test_register_flow.py` | 67 | — |
| B8 | `test_registration_server_edges.py` | 47 | — |
| B9 | `test_validation_roles.py` | 9 | — |
| B10 | `test_register_flow.py` | 67 | — |
| B11 | `test_register_flow.py` | 67 | — |
| B12 | `test_registration_server_edges.py` | 47 | — |
| B13 | `test_registration_server_edges.py` | 47 | — |
| B14 | `test_register_flow.py` | 67 | — |
| B16 | `test_commit_shape.py` | 8 | — |
| B17 | `test_reservation.py` | 13 | — |
| B18 | `test_spec_contracts.py` | 4 | — |
| B19 | `test_credential_routing.py` | 5 | — |
| C4 | `test_register_flow.py` | 67 | — |
| C6 | `test_register_flow.py` | 67 | — |
| C7 | `test_probe.py` | 19 | — |
| C8 | `test_spec_contracts.py` | 4 | — |
| C10 | `test_registration_server.py` | 74 | — |
| C11 | `test_registration_server.py` | 74 | — |
| C12 | `test_register_flow.py` | 67 | — |
| D2 | `test_middle_routing.py` | 23 | — |
| D3 | `test_validation_roles.py` | 9 | — |
| D4 | `test_validation_roles.py` | 9 | — |
| D5 | `test_credential_routing.py` | 5 | — |
| D6 | `test_tunnel.py` | 8 | — |
| D7 | `test_middle_contracts.py` | 22 | — |
| E2 | `test_persistent_shell_protocol.py` | 13 | — |
| E3 | `test_endpoint_budgets.py` | 5 | — |
| E4 | `test_endpoint_budgets.py` | 5 | — |
| E5 | `test_tunnel_transfer.py` | 31 | — |
| E6 | `test_connect_retry.py` | 4 | — |
| E7 | `test_ssh_tunnel_lifecycle.py` | 12 | — |
| F6 | `test_daemon_log_utf8_budget.py` | 5 | — |
| F8 | `test_daemon_runtime_contracts.py` | 54 | — |
| F10 | `test_daemon_log_contract.py` | 12 | — |
| G5 | `test_api_server_main.py` | 22 | — |
| H1 | `test_api_server_main.py` | 22 | — |
| H2 | `test_registration_server.py` | 74 | — |
| H3 | `test_registration_server.py` | 74 | — |
| H4 | `test_registration_server.py` | 74 | — |
| H5 | `test_registration_server.py` | 74 | — |
| H7 | `test_registration_server_edges.py` | 47 | — |
| H8 | `test_api_server_main.py` | 22 | — |
| H9 | `test_common_config.py` | 3 | — |
| H10 | `test_supervisor_process.py` | 4 | — |
| H11 | `test_supervisor_process.py` | 4 | — |
| I1 | `test_pyapi_packages.py` | 5 | — |
| I2 | `test_pyapi_packages.py` | 5 | — |
| I5 | `test_maestro_package_flow.py` | 22 | — |
| I6 | `test_pyapi_packages.py` | 5 | — |
| I7 | `test_top_layer_dispatch.py` | 10 | — |
| J1 | `test_pyapi_packages.py` | 5 | — |
| J4 | `test_common_config.py` | 3 | — |
| J5 | `test_middle_contracts.py` | 22 | — |
| J6 | `test_persistent_shell_protocol.py` | 13 | — |
| J7 | `test_daemon_runtime_contracts.py` | 54 | — |
| J8 | `test_local_path_expansion.py` | 2 | — |
| J10 | `test_api_server_main.py` | 22 | — |
<!-- offline-rerun:end -->

<!-- round7-audit:start -->
## 15. 逐行核账（第七轮，机器生成）

- 总行数 **195**；行内引用的证据文件**全部存在**
- 本轮离线已复跑并全绿的行：**84**
- 本轮半真机已复跑的行：**0**
- **本轮未复跑（历史证据）的行：110** —— 这些行不得当作本轮结论引用

| 行 | 证据文件 | 本轮状态 |
|---|---|---|
| A1 | `test/live/transport/cov_remote_real.py`, `test/offline/unit/test_middle_contracts.py` | ✅本轮离线已跑（22 例全绿） |
| A2 | `test/offline/unit/test_tunnel_transfer.py` | ✅本轮离线已跑（31 例全绿） |
| A3 | `test/offline/unit/test_tunnel_transfer.py` | ✅本轮离线已跑（31 例全绿） |
| A4 | `test/offline/core/daemon_log_protocol_tb.py`, `test/offline/unit/test_new_core.py` | ✅本轮离线已跑（8 例全绿） |
| A5 | `test/offline/unit/test_middle_contracts.py` | ✅本轮离线已跑（22 例全绿） |
| A6 | `test/offline/core/semantics_tb.py` | ⬜本轮未复跑 |
| A7 | `test/offline/core/fault_injection_tb.py`, `test/offline/unit/test_middle_contracts.py` | ✅本轮离线已跑（22 例全绿） |
| A8 | `test/offline/unit/test_middle_reserved_codes.py` | ✅本轮离线已跑（5 例全绿） |
| A9 | `test/offline/core/fault_injection_tb.py` | ⬜本轮未复跑 |
| A10 | `test/offline/core/semantics_tb.py` | ⬜本轮未复跑 |
| A11 | `test/offline/unit/test_transfer.py` | ✅本轮离线已跑（20 例全绿） |
| A12 | `test/offline/unit/test_tunnel_transfer.py` | ✅本轮离线已跑（31 例全绿） |
| A13 | `test/offline/unit/test_transfer.py` | ✅本轮离线已跑（20 例全绿） |
| A14 | `test/offline/unit/test_middle_contracts.py` | ✅本轮离线已跑（22 例全绿） |
| A15 | `test/offline/unit/test_local_path_expansion.py` | ✅本轮离线已跑（2 例全绿） |
| A16 | `test/live/packages/infra_e2e_tests.py`, `test/offline/unit/test_transport_error_paths.py` | ✅本轮离线已跑（14 例全绿） |
| A17 | `test/live/stress/production_face_stress_tb.py`, `test/offline/core/semantics_tb.py` | ⬜本轮未复跑 |
| A18 | `test/offline/unit/test_connect_retry.py` | ✅本轮离线已跑（4 例全绿） |
| A19 | `test/offline/unit/test_connect_retry.py` | ✅本轮离线已跑（4 例全绿） |
| B1 | `test/offline/unit/test_probe.py` | ✅本轮离线已跑（19 例全绿） |
| B2 | `test/offline/unit/test_common_config.py` | ✅本轮离线已跑（3 例全绿） |
| B3 | `test/offline/unit/test_register_flow.py` | ✅本轮离线已跑（67 例全绿） |
| B4 | `test/offline/unit/test_validation_roles.py` | ✅本轮离线已跑（9 例全绿） |
| B5 | `test/offline/unit/test_probe.py` | ✅本轮离线已跑（19 例全绿） |
| B6 | `test/offline/unit/test_register_flow.py`, `test/semi/probes/gui_display_probe.py` | ✅本轮离线已跑（67 例全绿） |
| B7 | `test/offline/unit/test_register_flow.py` | ✅本轮离线已跑（67 例全绿） |
| B8 | `test/offline/unit/test_registration_server_edges.py` | ✅本轮离线已跑（47 例全绿） |
| B9 | `test/offline/unit/test_validation_roles.py` | ✅本轮离线已跑（9 例全绿） |
| B10 | `test/offline/unit/test_register_flow.py` | ✅本轮离线已跑（67 例全绿） |
| B11 | `test/offline/unit/test_register_flow.py` | ✅本轮离线已跑（67 例全绿） |
| B12 | `test/offline/unit/test_registration_server_edges.py` | ✅本轮离线已跑（47 例全绿） |
| B13 | `test/offline/unit/test_registration_server_edges.py` | ✅本轮离线已跑（47 例全绿） |
| B14 | `test/offline/unit/test_register_flow.py` | ✅本轮离线已跑（67 例全绿） |
| B15 | `test/offline/core/semantics_tb.py`, `test/offline/unit/test_registry_more.py` | ✅本轮离线已跑（20 例全绿） |
| B16 | `test/artifacts/env/log-vblog/registry.json`, `test/offline/unit/test_commit_shape.py` | ✅本轮离线已跑（8 例全绿） |
| B17 | `test/offline/unit/test_reservation.py` | ✅本轮离线已跑（13 例全绿） |
| B18 | `test/offline/unit/test_spec_contracts.py` | ✅本轮离线已跑（4 例全绿） |
| B19 | `test/offline/unit/test_credential_routing.py` | ✅本轮离线已跑（5 例全绿） |
| C1 | `test/offline/integration/test_supervisor_process.py`, `test/offline/unit/test_registry_decoupling.py` | ✅本轮离线已跑（18 例全绿） |
| C2 | `test/live/registration/registration_http_six_step_tb.py` | ⬜本轮未复跑 |
| C3 | — | ⬜本轮未复跑 |
| C4 | `test/offline/unit/test_register_flow.py` | ✅本轮离线已跑（67 例全绿） |
| C5 | — | ⬜本轮未复跑 |
| C6 | `test/offline/unit/test_register_flow.py` | ✅本轮离线已跑（67 例全绿） |
| C7 | `test/offline/unit/test_probe.py` | ✅本轮离线已跑（19 例全绿） |
| C8 | `test/offline/unit/test_spec_contracts.py` | ✅本轮离线已跑（4 例全绿） |
| C9 | — | ⬜本轮未复跑 |
| C10 | `test/offline/unit/test_registration_server.py` | ✅本轮离线已跑（74 例全绿） |
| C11 | `test/offline/unit/test_registration_server.py` | ✅本轮离线已跑（74 例全绿） |
| C12 | `test/offline/unit/test_register_flow.py` | ✅本轮离线已跑（67 例全绿） |
| C13 | `test/offline/core/semantics_tb.py` | ⬜本轮未复跑 |
| C14 | — | ⬜本轮未复跑 |
| D1 | `test/live/flows/role_split_tb.py` | ⬜本轮未复跑 |
| D2 | `test/offline/unit/test_middle_routing.py` | ✅本轮离线已跑（23 例全绿） |
| D3 | `test/offline/unit/test_validation_roles.py` | ✅本轮离线已跑（9 例全绿） |
| D4 | `test/offline/unit/test_validation_roles.py` | ✅本轮离线已跑（9 例全绿） |
| D5 | `test/offline/unit/test_credential_routing.py` | ✅本轮离线已跑（5 例全绿） |
| D6 | `test/offline/unit/test_tunnel.py` | ✅本轮离线已跑（8 例全绿） |
| D7 | `test/offline/unit/test_middle_contracts.py` | ✅本轮离线已跑（22 例全绿） |
| E1 | `test/offline/core/semantics_tb.py` | ⬜本轮未复跑 |
| E2 | `test/offline/unit/test_persistent_shell_protocol.py` | ✅本轮离线已跑（13 例全绿） |
| E3 | `test/offline/unit/test_endpoint_budgets.py` | ✅本轮离线已跑（5 例全绿） |
| E4 | `test/offline/unit/test_endpoint_budgets.py` | ✅本轮离线已跑（5 例全绿） |
| E5 | `test/offline/unit/test_tunnel_transfer.py` | ✅本轮离线已跑（31 例全绿） |
| E6 | `test/offline/unit/test_connect_retry.py` | ✅本轮离线已跑（4 例全绿） |
| E7 | `test/offline/unit/test_ssh_tunnel_lifecycle.py` | ✅本轮离线已跑（12 例全绿） |
| E8 | `test/artifacts/env/scenario-scale-100/evidence.json`, `test/artifacts/evidence/round7/production-face-stress.json`, `test/live/flows/scale_100_tb.py`, `test/live/stress/production_face_stress_tb.py` | ✅本轮真机/新证据 |
| F1 | `test/offline/core/daemon_log_protocol_tb.py` | ⬜本轮未复跑 |
| F2 | — | ⬜本轮未复跑 |
| F3 | — | ⬜本轮未复跑 |
| F4 | `test/offline/core/daemon_log_protocol_tb.py`, `test/offline/unit/test_new_core.py` | ✅本轮离线已跑（8 例全绿） |
| F5 | — | ⬜本轮未复跑 |
| F6 | `test/offline/unit/test_daemon_log_utf8_budget.py` | ✅本轮离线已跑（5 例全绿） |
| F7 | — | ⬜本轮未复跑 |
| F8 | `test/offline/unit/test_daemon_runtime_contracts.py` | ✅本轮离线已跑（54 例全绿） |
| F9 | `test/offline/core/daemon_log_protocol_tb.py` | ⬜本轮未复跑 |
| F10 | `test/offline/unit/test_daemon_log_contract.py` | ✅本轮离线已跑（12 例全绿） |
| F11 | `test/offline/core/daemon_log_protocol_tb.py` | ⬜本轮未复跑 |
| G1 | `test/offline/core/api_server_tb.py`, `test/offline/unit/test_top_layer_dispatch.py` | ✅本轮离线已跑（10 例全绿） |
| G2 | — | ⬜本轮未复跑 |
| G3 | `test/offline/core/api_server_tb.py`, `test/offline/unit/test_api_server_main.py` | ✅本轮离线已跑（22 例全绿） |
| G4 | `test/offline/core/api_server_tb.py` | ⬜本轮未复跑 |
| G5 | `test/offline/unit/test_api_server_main.py` | ✅本轮离线已跑（22 例全绿） |
| G6 | `test/offline/core/api_server_tb.py` | ⬜本轮未复跑 |
| G7 | `test/offline/unit/test_registry_decoupling.py`, `test/offline/unit/test_upper_layer_import_contract.py`, `test/upper_layer_paths.py` | ✅本轮离线已跑（19 例全绿） |
| G8 | `test/offline/core/api_server_tb.py` | ⬜本轮未复跑 |
| H1 | `test/offline/unit/test_api_server_main.py` | ✅本轮离线已跑（22 例全绿） |
| H2 | `test/offline/unit/test_registration_server.py` | ✅本轮离线已跑（74 例全绿） |
| H3 | `test/offline/unit/test_registration_server.py` | ✅本轮离线已跑（74 例全绿） |
| H4 | `test/offline/unit/test_registration_server.py` | ✅本轮离线已跑（74 例全绿） |
| H5 | `test/offline/unit/test_registration_server.py` | ✅本轮离线已跑（74 例全绿） |
| H6 | — | ⬜本轮未复跑 |
| H7 | `test/offline/unit/test_registration_server_edges.py` | ✅本轮离线已跑（47 例全绿） |
| H8 | `test/offline/unit/test_api_server_main.py` | ✅本轮离线已跑（22 例全绿） |
| H9 | `test/offline/unit/test_common_config.py` | ✅本轮离线已跑（3 例全绿） |
| H10 | `test/offline/integration/test_supervisor_process.py` | ✅本轮离线已跑（4 例全绿） |
| H11 | `test/offline/integration/test_supervisor_process.py` | ✅本轮离线已跑（4 例全绿） |
| I1 | `test/offline/unit/test_pyapi_packages.py` | ✅本轮离线已跑（5 例全绿） |
| I2 | `test/offline/unit/test_pyapi_packages.py` | ✅本轮离线已跑（5 例全绿） |
| I3 | — | ⬜本轮未复跑 |
| I4 | `test/offline/core/api_server_tb.py` | ⬜本轮未复跑 |
| I5 | `test/offline/unit/test_maestro_package_flow.py` | ✅本轮离线已跑（22 例全绿） |
| I6 | `test/offline/unit/test_pyapi_packages.py` | ✅本轮离线已跑（5 例全绿） |
| I7 | `test/offline/unit/test_top_layer_dispatch.py` | ✅本轮离线已跑（10 例全绿） |
| J1 | `test/offline/unit/test_pyapi_packages.py` | ✅本轮离线已跑（5 例全绿） |
| J2 | — | ⬜本轮未复跑 |
| J3 | `test/offline/core/fault_injection_tb.py` | ⬜本轮未复跑 |
| J4 | `test/offline/unit/test_common_config.py` | ✅本轮离线已跑（3 例全绿） |
| J5 | `test/offline/unit/test_middle_contracts.py` | ✅本轮离线已跑（22 例全绿） |
| J6 | `test/offline/unit/test_persistent_shell_protocol.py` | ✅本轮离线已跑（13 例全绿） |
| J7 | `test/offline/unit/test_daemon_runtime_contracts.py` | ✅本轮离线已跑（54 例全绿） |
| J8 | `test/offline/unit/test_local_path_expansion.py` | ✅本轮离线已跑（2 例全绿） |
| J9 | — | ⬜本轮未复跑 |
| J10 | `test/offline/unit/test_api_server_main.py` | ✅本轮离线已跑（22 例全绿） |
| X1 | — | ⬜本轮未复跑 |
| X2 | — | ⬜本轮未复跑 |
| X3 | — | ⬜本轮未复跑 |
| X4 | — | ⬜本轮未复跑 |
| X6 | — | ⬜本轮未复跑 |
| A1 | — | ⬜本轮未复跑 |
| A2 | — | ⬜本轮未复跑 |
| A3 | — | ⬜本轮未复跑 |
| A5 | — | ⬜本轮未复跑 |
| A8 | — | ⬜本轮未复跑 |
| A11 | — | ⬜本轮未复跑 |
| A12 | — | ⬜本轮未复跑 |
| A13 | — | ⬜本轮未复跑 |
| A14 | — | ⬜本轮未复跑 |
| A15 | — | ⬜本轮未复跑 |
| A16 | — | ⬜本轮未复跑 |
| A18 | — | ⬜本轮未复跑 |
| A19 | — | ⬜本轮未复跑 |
| B1 | — | ⬜本轮未复跑 |
| B2 | — | ⬜本轮未复跑 |
| B3 | — | ⬜本轮未复跑 |
| B4 | — | ⬜本轮未复跑 |
| B5 | — | ⬜本轮未复跑 |
| B6 | — | ⬜本轮未复跑 |
| B7 | — | ⬜本轮未复跑 |
| B8 | — | ⬜本轮未复跑 |
| B9 | — | ⬜本轮未复跑 |
| B10 | — | ⬜本轮未复跑 |
| B11 | — | ⬜本轮未复跑 |
| B12 | — | ⬜本轮未复跑 |
| B13 | — | ⬜本轮未复跑 |
| B14 | — | ⬜本轮未复跑 |
| B16 | — | ⬜本轮未复跑 |
| B17 | — | ⬜本轮未复跑 |
| B18 | — | ⬜本轮未复跑 |
| B19 | — | ⬜本轮未复跑 |
| C4 | — | ⬜本轮未复跑 |
| C6 | — | ⬜本轮未复跑 |
| C7 | — | ⬜本轮未复跑 |
| C8 | — | ⬜本轮未复跑 |
| C10 | — | ⬜本轮未复跑 |
| C11 | — | ⬜本轮未复跑 |
| C12 | — | ⬜本轮未复跑 |
| D2 | — | ⬜本轮未复跑 |
| D3 | — | ⬜本轮未复跑 |
| D4 | — | ⬜本轮未复跑 |
| D5 | — | ⬜本轮未复跑 |
| D6 | — | ⬜本轮未复跑 |
| D7 | — | ⬜本轮未复跑 |
| E2 | — | ⬜本轮未复跑 |
| E3 | — | ⬜本轮未复跑 |
| E4 | — | ⬜本轮未复跑 |
| E5 | — | ⬜本轮未复跑 |
| E6 | — | ⬜本轮未复跑 |
| E7 | — | ⬜本轮未复跑 |
| F6 | — | ⬜本轮未复跑 |
| F8 | — | ⬜本轮未复跑 |
| F10 | — | ⬜本轮未复跑 |
| G5 | — | ⬜本轮未复跑 |
| H1 | — | ⬜本轮未复跑 |
| H2 | — | ⬜本轮未复跑 |
| H3 | — | ⬜本轮未复跑 |
| H4 | — | ⬜本轮未复跑 |
| H5 | — | ⬜本轮未复跑 |
| H7 | — | ⬜本轮未复跑 |
| H8 | — | ⬜本轮未复跑 |
| H9 | — | ⬜本轮未复跑 |
| H10 | — | ⬜本轮未复跑 |
| H11 | — | ⬜本轮未复跑 |
| I1 | — | ⬜本轮未复跑 |
| I2 | — | ⬜本轮未复跑 |
| I5 | — | ⬜本轮未复跑 |
| I6 | — | ⬜本轮未复跑 |
| I7 | — | ⬜本轮未复跑 |
| J1 | — | ⬜本轮未复跑 |
| J4 | — | ⬜本轮未复跑 |
| J5 | — | ⬜本轮未复跑 |
| J6 | — | ⬜本轮未复跑 |
| J7 | — | ⬜本轮未复跑 |
| J8 | — | ⬜本轮未复跑 |
| J10 | — | ⬜本轮未复跑 |
<!-- round7-audit:end -->
