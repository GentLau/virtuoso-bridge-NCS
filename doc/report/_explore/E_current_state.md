# E_current_state — current implementation inventory and upper-layer readiness

> Snapshot refreshed: 2026-09-16 16:30 +08:00 (Asia/Shanghai)  
> Repository: `C:\Users\user\Desktop\repos_Github\virtuoso-bridge-NCS`  
> Git: branch `codex/refactor-tests-docs`, HEAD `2da45b5`; worktree is dirty and was changing during the audit.  
> Audit scope: maintained files under `src/`, maintained test files under `test/`, `pyproject.toml`, `tools/`, `scripts/`, `doc/`, and `docs/`.  
> Read-only rule: no repository file was modified for evidence gathering. This report is the only file written.

Current dirty-state caveat: the worktree changed during the audit. At refresh time it includes uncommitted changes to `src/transport/middle.py`, `src/transport/registry.py`, and `src/transport/transfer.py`, plus untracked `test/tb/semantics_tb.py` and semantics artifacts. Those changes fix the local-timeout and crash-safety red baseline; the report describes the refreshed filesystem rather than only committed HEAD.

## 1. Package/file inventory

Generated `__pycache__/*.pyc` files are not individually enumerated because bytecode is not maintained source and has no meaningful source purpose/status. At snapshot there are 41 `.pyc` files under `src/` and 106 under `test/` (147 total). All non-bytecode files visible in the requested trees are listed below. Line counts are `splitlines()` counts at snapshot time.

Status legend: **COMPLETE** = implemented as present; **PARTIAL** = useful implementation but known scaffold/compatibility gap; **STUB** = placeholder; **TEST-ONLY** = test/stress/diagnostic asset; **RESOURCE** = generated evidence or data/asset.

### 1.1 `src/` files

| Path | Lines | Purpose | Status |
|---|---:|---|---|
| `src/bridge/__init__.py` | 9 | Bottom-layer package marker and resources_dir() locator. | `COMPLETE` |
| `src/bridge/resources/__init__.py` | 1 | Resource package marker for Virtuoso-side files. | `COMPLETE` |
| `src/bridge/resources/ramic_bridge.il` | 646 | SKILL loaded in CIW; bridges ipcBeginProcess to the daemon. | `RESOURCE` |
| `src/bridge/resources/ramic_bridge_daemon_27.py` | 417 | Python 2.7-compatible bottom daemon implementing the v1 wire protocol. | `COMPLETE` |
| `src/bridge/resources/ramic_bridge_daemon_3.py` | 425 | Python 3 bottom daemon implementing SKILL execution, log deltas, and token checks. | `COMPLETE` |
| `src/pyapi/__init__.py` | 19 | Public re-export of upper-facing models and Middle protocol. | `COMPLETE` |
| `src/pyapi/models.py` | 138 | VirtuosoResult, CommandResult, SimulationResult, VirtuosoInterface, and Middle protocol. | `COMPLETE` |
| `src/pyapi/packages/__init__.py` | 5 | Exports the two current upper business packages. | `COMPLETE` |
| `src/pyapi/packages/file_skill_command_file.py` | 77 | Reference upload -> Skill -> command -> download package. | `PARTIAL` |
| `src/pyapi/packages/parallel_probe.py` | 63 | Thread-pool command/upload probe used by stress and integration TBs. | `TEST-ONLY` |
| `src/server/__init__.py` | 21 | Server package marker; says the business/API top layer is future work. | `PARTIAL` |
| `src/server/registration_page.html` | 2884 | Browser UI for the six-step registration flow. | `RESOURCE` |
| `src/server/registration_server.py` | 317 | Stdlib ThreadingHTTPServer for registration setup/control-plane APIs. | `COMPLETE` |
| `src/server/stress_server.py` | 182 | Test-only HTTP wrapper that calls middle interfaces directly. | `TEST-ONLY` |
| `src/transport/__init__.py` | 25 | Convenience exports for registry and runtime paths. | `COMPLETE` |
| `src/transport/budgets.py` | 144 | Per-token thread and per-endpoint channel budget primitives. | `COMPLETE` |
| `src/transport/deploy.py` | 100 | Deploys generated bottom daemon/SKILL/setup files for one user. | `COMPLETE` |
| `src/transport/middle.py` | 878 | BusinessServer facade, routing, capacity gates, and the five-interface implementation. | `COMPLETE` |
| `src/transport/paramiko_backend.py` | 1523 | Persistent Paramiko SSH backend with bounded channel/session multiplexing. | `COMPLETE` |
| `src/transport/register/__init__.py` | 35 | Registration package exports. | `COMPLETE` |
| `src/transport/register/candidate.py` | 157 | Candidate target resolution and final-shape validation. | `COMPLETE` |
| `src/transport/register/flow.py` | 1040 | Six-step registration state machine, probing, deployment, and commit. | `COMPLETE` |
| `src/transport/register/models.py` | 201 | Pydantic registration request/state/probe models. | `COMPLETE` |
| `src/transport/register/probe.py` | 413 | Read-only host, account, path, Python, and Spectre probes. | `COMPLETE` |
| `src/transport/register/reservation.py` | 103 | In-memory port/token/user reservation table for registration. | `COMPLETE` |
| `src/transport/registry.py` | 494 | Persistent per-user registry, token index, endpoint keys, and file locking. | `COMPLETE` |
| `src/transport/remote_paths.py` | 88 | Calculates remote scratch/ramic/status/identity paths. | `COMPLETE` |
| `src/transport/remote_roles.py` | 9 | Deprecated compatibility shim; implementation moved to roles.py. | `PARTIAL` |
| `src/transport/roles.py` | 136 | Resolves a registry entry into gui/daemon/command/file/spectre targets. | `COMPLETE` |
| `src/transport/runtime_paths.py` | 84 | Local working-directory and registry/temp/log/artifact path policy. | `COMPLETE` |
| `src/transport/setup.py` | 36 | Generates the CIW-loaded virtuoso_setup.il bootstrap text. | `COMPLETE` |
| `src/transport/skill_client.py` | 156 | TCP client to the bottom daemon; token/log payload and response parsing. | `COMPLETE` |
| `src/transport/ssh.py` | 1974 | OpenSSH runner plus persistent shell, fallback, retry, transfer, and Paramiko dispatch. | `COMPLETE` |
| `src/transport/transfer.py` | 438 | Transport-independent staged/tar transfer plans and atomic install helpers. | `COMPLETE` |
| `src/transport/tunnel.py` | 458 | Per-token RemoteClient for daemon tunnel, commands, files, and one-shot GUI/Spectre. | `COMPLETE` |
| `src/transport/validation.py` | 32 | Shared user-name and token validation. | `COMPLETE` |

### 1.2 `test/` files

| Path | Lines | Purpose | Status |
|---|---:|---|---|
| `test/e2e/test_business_local_live.py` | 256 | Live business simulation in LOCAL mode on the Virtuoso host (wsl-gent). | `TEST-ONLY` |
| `test/e2e/test_business_remote_live.py` | 257 | Live business simulation in remote mode against real Virtuoso daemons. | `TEST-ONLY` |
| `test/e2e/test_e2e_live.py` | 200 | Live end-to-end middle+bottom test against the real Virtuoso (wsl-gent). | `TEST-ONLY` |
| `test/frontend_tb/__init__.py` | 1 | Front-end-only registration UI testbench. | `TEST-ONLY` |
| `test/frontend_tb/registration_mock_panel.html` | 349 | Browser UI/resource for a frontend testbench. | `RESOURCE` |
| `test/frontend_tb/registration_mock_server.py` | 628 | Front-end-only testbench for the six-step registration page. | `TEST-ONLY` |
| `test/integration/test_daemon_handler.py` | 347 | Bottom-daemon wire tests. | `TEST-ONLY` |
| `test/integration/test_integration.py` | 138 | Integration tests: fake bottom daemon + local BusinessServer. | `TEST-ONLY` |
| `test/README.md` | 71 | 测试体系（test/） | `RESOURCE` |
| `test/scenario/test_business_local.py` | 359 | Scenario: complete business simulation over the three middle interfaces. | `TEST-ONLY` |
| `test/scenario/test_multi_user_isolation.py` | 111 | Scenario: two registered users are isolated by token at the business layer. | `TEST-ONLY` |
| `test/scenario/test_registration_local_full.py` | 109 | Scenario: full local six-step registration through a fake bottom daemon. | `TEST-ONLY` |
| `test/tb/_win.py` | 28 | Windows console-hidden subprocess kwargs for the live test benches. | `TEST-ONLY` |
| `test/tb/artifacts/cov-registration/log/commands.log` | 960 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/coverage-combined.json` | 1 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/coverage-combined.txt` | 38 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/fault-injection-baseline-red.json` | 36 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/fault-injection-green.json` | 75 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/fault-injection-red-cache-corrected.json` | 11 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/live-evidence.json` | 23 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/reg-vb11/log/commands.log` | 261 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/reg-vb11/registry.json` | 96 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/semantics-baseline-red.json` | 31 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/artifacts/semantics-green.json` | 68 | Captured live/coverage/fault-injection evidence artifact. | `RESOURCE` |
| `test/tb/client_equiv.py` | 130 | C1: same business sequence on Windows and Linux clients against vps fake daemons. | `TEST-ONLY` |
| `test/tb/composite_stress.py` | 407 | Composite HTTPServer business simulation for two client topologies. | `TEST-ONLY` |
| `test/tb/cov_registration_real.py` | 46 | Real remote registration coverage TB (steps 1-4 only, no commit). | `TEST-ONLY` |
| `test/tb/cov_remote_real.py` | 66 | Real remote coverage TB: Windows client -> WSL real Virtuoso daemon. | `TEST-ONLY` |
| `test/tb/f1_connect_burst.py` | 96 | F1 live: cold first-connect burst to the weak vps sshd (MaxStartups). | `TEST-ONLY` |
| `test/tb/f2_daemon_reconnect.py` | 99 | F2 live: daemon killed -> structured transport error -> restart -> reconnect. | `TEST-ONLY` |
| `test/tb/fake_daemon_host.py` | 90 | Standalone protocol-accurate fake daemons for a remote host without Virtuoso. | `TEST-ONLY` |
| `test/tb/fault_injection_tb.py` | 413 | Fault-injection TB. | `TEST-ONLY` |
| `test/tb/log_file_verify.py` | 76 | HTTP-based log byte verification against the real CDS.log interval. | `TEST-ONLY` |
| `test/tb/multi_virtuoso_pilot.py` | 142 | Start N real Virtuoso instances on wsl-gent, one registered user each. | `TEST-ONLY` |
| `test/tb/multienv_mixed.py` | 109 | M1 single-client mixed multi-user: 6 real wsl Virtuoso + 10 vps fake daemons. | `TEST-ONLY` |
| `test/tb/multienv_random.py` | 173 | Randomized mixed-concurrency business simulation (single client, 3 envs). | `TEST-ONLY` |
| `test/tb/p1_log_live.py` | 41 | P1 live CDS.log delta contract against a real Virtuoso daemon. | `TEST-ONLY` |
| `test/tb/p2_extreme_gradient.py` | 145 | P2 live: extreme gradient on the weak vps (100 fake users, 400/500/600). | `TEST-ONLY` |
| `test/tb/README.md` | 49 | Testbench（test/tb/） | `RESOURCE` |
| `test/tb/restart_vb_virtuosos.py` | 57 | Restart the vbNN Virtuoso instances so their daemons pick up the new | `TEST-ONLY` |
| `test/tb/role_mixed_mode.py` | 121 | T3: per-role mixed mode on the client host. | `TEST-ONLY` |
| `test/tb/role_split_cross_host.py` | 100 | T2: per-role split across hosts (daemon/gui on wsl, command/file/spectre on vps). | `TEST-ONLY` |
| `test/tb/semantics_tb.py` | 318 | Semantics TB: contracts the success-path TB does not drive. | `TEST-ONLY` |
| `test/tb/smoke_user.py` | 89 | Per-user smoke test: the five middle interfaces with per-stage timings. | `TEST-ONLY` |
| `test/tb/stress_client.py` | 246 | Stress client for the middle-layer HTTP wrapper. | `TEST-ONLY` |
| `test/tb/stress_live.py` | 166 | Live middle-layer pressure test against wsl-gent. | `TEST-ONLY` |
| `test/tb/stress_local_fake.py` | 98 | 100-user local-mode stress TB (run on WSL with fake daemons). | `TEST-ONLY` |
| `test/tb/stress_multiuser.py` | 139 | 100-user middle-layer routing stress harness. | `TEST-ONLY` |
| `test/tb/stress_multiuser_real.py` | 111 | Multi-user routing stress against REAL Virtuoso daemons (remote mode). | `TEST-ONLY` |
| `test/tb/stress_remote_fake.py` | 87 | Remote-mode stress TB: Windows client -> WSL fake daemons. | `TEST-ONLY` |
| `test/unit/test_commit_shape.py` | 70 | Final registry-shape validation contracts (config v24). | `TEST-ONLY` |
| `test/unit/test_connect_retry.py` | 99 | Deterministic connect-retry contract: at most 3 handshake attempts. | `TEST-ONLY` |
| `test/unit/test_daemon27.py` | 20 | test_daemon27.py | `TEST-ONLY` |
| `test/unit/test_daemon_log_contract.py` | 134 | 底层 daemon 的日志契约单元测试（分级 / 限长降级 / 区间读取 / 只读）。 | `TEST-ONLY` |
| `test/unit/test_daemon_parity.py` | 68 | Parity tests: the Python 3 and Python 2.7 daemons share one fixture set. | `TEST-ONLY` |
| `test/unit/test_endpoint_budgets.py` | 93 | Endpoint-scoped max_sessions accounting (spec v24 / concurrency v17). | `TEST-ONLY` |
| `test/unit/test_local_path_expansion.py` | 38 | local-mode 文件接口必须展开 ~（不得创建字面 ~ 目录）。 | `TEST-ONLY` |
| `test/unit/test_log_no_fetch.py` | 40 | Static contracts: log=off must not fetch the log at any layer. | `TEST-ONLY` |
| `test/unit/test_log_off.py` | 18 | test_log_off.py | `TEST-ONLY` |
| `test/unit/test_middle_contracts.py` | 172 | 五接口错误契约（spec 三层架构 §4.4）——用假 RemoteClient 覆盖映射分支。 | `TEST-ONLY` |
| `test/unit/test_middle_routing.py` | 195 | BusinessServer routing tests with RemoteClient/SkillClient mocked. | `TEST-ONLY` |
| `test/unit/test_models_paths.py` | 147 | Small-module unit coverage: models, paths, SkillClient. | `TEST-ONLY` |
| `test/unit/test_new_core.py` | 109 | test_new_core.py | `TEST-ONLY` |
| `test/unit/test_new_middle.py` | 71 | test_new_middle.py | `TEST-ONLY` |
| `test/unit/test_paramiko.py` | 317 | Paramiko backend unit tests: config parsing and pure helpers (no network). | `TEST-ONLY` |
| `test/unit/test_paramiko_helpers.py` | 84 | Paramiko 后端纯助手与配置解析错误分支。 | `TEST-ONLY` |
| `test/unit/test_paramiko_run_command.py` | 169 | Paramiko run_command / close / ensure_connected 分支。 | `TEST-ONLY` |
| `test/unit/test_paramiko_session_paths.py` | 150 | Paramiko 会话层：传输就绪判定、连接探测、known_hosts 解析、通道聚合。 | `TEST-ONLY` |
| `test/unit/test_persistent_shell_protocol.py` | 165 | 常驻 shell 协议循环（ssh.py::_run_command_via_persistent_shell_locked）。 | `TEST-ONLY` |
| `test/unit/test_probe.py` | 129 | Remote probe helpers: python detection and port allocation. | `TEST-ONLY` |
| `test/unit/test_pyapi_packages.py` | 101 | Upper-layer business package tests (no transport/SSH dependencies). | `TEST-ONLY` |
| `test/unit/test_register_flow.py` | 593 | Six-step registration flow unit tests (probes/deploy/connectivity mocked). | `TEST-ONLY` |
| `test/unit/test_registration_mock_server.py` | 192 | Tests for the front-end-only registration mock testbench. | `TEST-ONLY` |
| `test/unit/test_registration_page.py` | 51 | Static contract of the registration page (per-role override UI, spec r2). | `TEST-ONLY` |
| `test/unit/test_registration_server.py` | 310 | Registration HTTP server smoke tests (local mode, no real daemon). | `TEST-ONLY` |
| `test/unit/test_registry_decoupling.py` | 143 | Registry decoupling contract tests. | `TEST-ONLY` |
| `test/unit/test_registry_more.py` | 108 | Registry persistence / integrity edge cases. | `TEST-ONLY` |
| `test/unit/test_reservation.py` | 161 | Reservation table + step-budget contracts (配置一览 §6.4, 架构 §5.8). | `TEST-ONLY` |
| `test/unit/test_resource_release.py` | 92 | Resource release contracts (spec: 每轮资源盘点零残留). | `TEST-ONLY` |
| `test/unit/test_runner_single_flight.py` | 109 | Runner creation must be single-flight per endpoint / role. | `TEST-ONLY` |
| `test/unit/test_skill_admission.py` | 144 | Skill 投递闸门：排队、串行；对外超时统一为结果未知（spec v17）。 | `TEST-ONLY` |
| `test/unit/test_spec_contracts.py` | 66 | Unit contracts for the frozen spec additions (file-root, connect budget). | `TEST-ONLY` |
| `test/unit/test_ssh.py` | 483 | SSHRunner unit tests: pure helpers, option construction, and one-shot | `TEST-ONLY` |
| `test/unit/test_ssh_dispatch.py` | 151 | ssh.py 分派分支：paramiko / 常驻 shell / 一次性回退，以及连接探测与文本上传。 | `TEST-ONLY` |
| `test/unit/test_ssh_tunnel_lifecycle.py` | 151 | 隧道生命周期契约：两个 OS 分支都必须登记端口/退避（BUG-1 及同类残留回归）。 | `TEST-ONLY` |
| `test/unit/test_stress_server.py` | 132 | Unit coverage for the HTTP stress wrapper around the middle layer. | `TEST-ONLY` |
| `test/unit/test_stress_server_endpoints.py` | 108 | stress_server 的 HTTP 端点契约（upload/download/composite/shutdown）。 | `TEST-ONLY` |
| `test/unit/test_transfer.py` | 182 | Unit tests for transfer plans and staged atomic install. | `TEST-ONLY` |
| `test/unit/test_transport_error_paths.py` | 109 | 错误路径与诊断分支（ssh.py）：纯函数级覆盖。 | `TEST-ONLY` |
| `test/unit/test_tunnel.py` | 179 | RemoteClient / SSHRunner integration tests. | `TEST-ONLY` |
| `test/unit/test_tunnel_transfer.py` | 348 | RemoteClient transport tests with a configurable fake SSHRunner. | `TEST-ONLY` |
| `test/unit/test_validation_roles.py` | 54 | Input validation and role-resolution contracts. | `TEST-ONLY` |
| `test/计划/功能正确性.md` | 100 | 功能正确性（五接口） | `RESOURCE` |
| `test/计划/可靠性与资源回收.md` | 88 | 可靠性与资源回收 | `RESOURCE` |
| `test/计划/并发与容量.md` | 106 | 并发与容量 | `RESOURCE` |
| `test/计划/总览与执行约定.md` | 45 | 测试计划 · 总览与执行约定 | `RESOURCE` |
| `test/计划/拓扑与传输后端.md` | 46 | 拓扑与传输后端 | `RESOURCE` |
| `test/计划/日志返回.md` | 64 | CDS.log 增量返回 | `RESOURCE` |
| `test/计划/注册流程.md` | 100 | 注册流程与内存 reservation | `RESOURCE` |
| `test/计划/注册页与HTTP层.md` | 40 | 注册页与 HTTP 层 | `RESOURCE` |
| `test/计划/等价性.md` | 46 | 等价性 | `RESOURCE` |
| `test/计划/路由与多节点.md` | 64 | 路由与多节点（五 role / 忠实投送） | `RESOURCE` |
| `test/计划/输入安全与首信任.md` | 46 | 输入安全与首信任 | `RESOURCE` |
| `test/计划/运维生命周期.md` | 58 | 运维生命周期 | `RESOURCE` |
| `test/计划/错误与安全.md` | 82 | 错误合同与安全 | `RESOURCE` |

### 1.3 Documentation, tools, and scripts

| Path | Lines | Purpose |
|---|---:|---|
| `doc/report/_explore/A_schematic_symbol.md` | 699 | Legacy Schematic + Symbol Upper-Layer Inventory |
| `doc/report/_explore/B_layout_gds_import.md` | 662 | Legacy Layout / GDS Import Inventory |
| `doc/report/_explore/C_maestro_spectre.md` | 555 | Legacy Maestro/ADE and Standalone Spectre Upper-Layer Inventory |
| `doc/report/_explore/D_library_skill_tooling_gui.md` | 654 | D — Legacy library, SKILL tooling, GUI/desktop, and basic-client inventory |
| `doc/report/_explore/E_current_state.md` | — | This refreshed current-state report. |
| `doc/report/log契约-P1.md` | 46 | Log 契约 P1：off 零获取 + offset 增量（真实 Virtuoso） |
| `doc/report/spec收口说明.md` | 19 | Spec 收口说明（对照最新复审 P0/P1） |
| `doc/report/上层开发指南.md` | 280 | 上层开发指南 |
| `doc/report/五接口三环境真机测试报告.md` | 211 | 五接口三环境真机测试报告（送审版） |
| `doc/report/代码梳理.md` | 201 | 旧实现代码梳理（Historical / Non-normative） |
| `doc/report/反思与缺陷记录.md` | 101 | 反思与缺陷记录（2026-09-15 进程风暴事件） |
| `doc/report/复核测试环境.md` | 72 | 复核测试环境 |
| `doc/report/复核测试计划.md` | 130 | 复核测试计划 |
| `doc/report/客户端等价-C1.md` | 44 | 客户端等价 C1：Windows 与 Linux 客户端 |
| `doc/report/并发专项-三环境随机混合.md` | 74 | 并发专项：三环境随机混合（单客户端多用户） |
| `doc/report/并发准入与投递缺陷记录.md` | 328 | 并发准入与投递缺陷记录（代码走查·2026-09-15） |
| `doc/report/架构总览图.md` | 490 | 架构总览图（四层架构 · 图说） |
| `doc/report/测试执行报告.md` | 63 | 三环境复核测试执行报告 |
| `doc/report/环境支持.md` | 74 | 环境支持文档 |
| `doc/接口调用指南.md` | 209 | 接口调用指南 |
| `doc/测试覆盖报告.md` | 67 | 测试覆盖报告 |
| `doc/设计规格全量复审意见.md` | 138 | 当前 Spec 全量复审意见（SPEC-2026-09-16-r3） |
| `doc/重构执行计划-四层.md` | 69 | 四层重构执行计划（完成记录） |
| `doc/验收审批意见.md` | 50 | Spec 验收审批意见（SPEC-2026-09-16-r3） |
| `docs/adr/0001-explicit-remote-host-roles.md` | 8 | Keep explicit remote host roles behind a legacy fallback |
| `docs/adr/0002-deterministic-schematic-planner.md` | 110 | ADR 0002: Deterministic Python-side schematic planning |
| `docs/CNAME` | 1 | Website metadata/asset. |
| `docs/favicon.svg` | 4 | Website metadata/asset. |
| `docs/index.html` | 491 | Published project website page. |
| `docs/superpowers/plans/2026-04-09-dismiss-dialog.md` | 638 | Dialog Dismissal Feature Implementation Plan |
| `tools/check_spec.py` | 217 | Spec governance checker (the "Spec CI" referenced by spec/README.md). |
| `tools/skill_doc_server.py` | 984 | SKILL 函数离线查询 Web 服务 — 自包含实现(stdlib only)。 |
| `tools/skill_exec.py` | 111 | Execute SKILL in a running Virtuoso session via the RAMIC bridge daemon. |
| `scripts/fix-symlinks.sh` | 56 | Developer shell utility. |
| `scripts/track_traffic.py` | 230 | Pull GitHub repo traffic stats (clones + views) and append to history. |

Documentation map at a glance: `doc/` contains coverage, interface usage, spec review, acceptance, and four-layer refactor records; `doc/report/` contains architecture, implementation, live-test, concurrency, fault, and upper-layer-development reports; `docs/` contains ADRs, the public site, and a dialog-dismissal implementation plan. `tools/check_spec.py` is the Spec governance checker; `tools/skill_exec.py` is a zero-dependency direct daemon client; `tools/skill_doc_server.py` is a local Cadence-document search web tool. `scripts/fix-symlinks.sh` repairs Windows checkout junctions; `scripts/track_traffic.py` records GitHub traffic before the 14-day API window expires.

## 2. Middle-layer interface reality check

The normative contract is `spec/design-concepts/总览/1-四层整体架构与接口.md` §4.1–§4.5. The contract calls this “five interfaces” but defines six methods because upload and download are the two directions of the single File interface (`1-四层整体架构与接口.md:183-188,206-212`).

### 2.1 Actual signatures

| Logical interface | Actual `Middle` signature (`src/pyapi/models.py`) | Concrete `BusinessServer` signature (`src/transport/middle.py`) | Return |
|---|---|---|---|
| Skill execution | `execute_skill(self, skill_code: str, timeout: float \| None = None, *, token: str) -> VirtuosoResult` | same | `VirtuosoResult` |
| Command execution | `run_command(self, cmd: str, timeout: int \| None = None, *, token: str, parallel: bool = False) -> CommandResult` | same | `CommandResult` |
| File upload | `upload_file(self, local_path: Path, remote_path: str, timeout: int \| None = None, *, token: str, recursive: bool = False) -> CommandResult` | same | `CommandResult` |
| File download | `download_file(self, remote_path: str, local_path: Path, timeout: int \| None = None, *, token: str, recursive: bool = False) -> CommandResult` | same | `CommandResult` |
| GUI command | `run_gui_command(self, cmd: str, timeout: int \| None = None, *, token: str) -> CommandResult` | same | `CommandResult` |
| Spectre command | `run_spectre_command(self, cmd: str, timeout: int \| None = None, *, token: str) -> CommandResult` | same | `CommandResult` |

Evidence: protocol declarations at `src/pyapi/models.py:98-128`; public concrete methods at `src/transport/middle.py:524,585,635,661,689,693`. `token` is keyword-only and required in every actual signature. Python binding raises `TypeError` if it is omitted; the method body cannot intercept that binding error. Runtime invalid tokens are caught and converted to structured failures (`middle.py:560-561,628-629,654-655,680-681,713-714`).

### 2.2 Return models and `kind` reality

- `VirtuosoResult` is a Pydantic `BaseModel` with `status: ExecutionStatus`, `output`, `errors`, `warnings`, `execution_time`, `metadata`, and `log` (`src/pyapi/models.py:24-50`). `ExecutionStatus` is a string enum with `success`, `failure`, `partial`, `error` (`models.py:17-21`).
- `CommandResult` is a `NamedTuple`: `(returncode: int, stdout: str, stderr: str, kind: str = "command")` (`src/pyapi/models.py:53-64`). `kind` is an unrestricted string at runtime; there is no Enum or validation.
- Implemented `kind` values observed in source: `command`, `timeout`, `transport`, `path`, `unknown-effect`, `rejected`, `checksum`, `invalid-token`. This matches the frozen enumeration at `1-四层整体架构与接口.md:263`.
- A real command exit code is kept with `kind="command"` even when it is 124 or 255; bridge-reserved codes are used only for bridge-classified failures. This is implemented by `_error_result()` and `_result_from_rc()` (`src/transport/middle.py:104-125`; `src/transport/ssh.py:779-793`).

| Result case | Skill implementation | Command/file/GUI/Spectre implementation |
|---|---|---|
| Normal | `status=success`, output/log | `kind=command`, real rc/stdout/stderr |
| Timeout | `status=error`, `errors=["SKILL execution timed out"]` | `kind=timeout`, rc 124 |
| Transport failure | `status=error`, error contains `Daemon connection failed` | `kind=transport`, rc 255, `VB-TRANSPORT:` |
| Path failure | error contains `VB-PATH-NOT-VISIBLE:` | `kind=path`, non-zero rc |
| Unknown effect | Skill timeout is intentionally indistinguishable | `kind=unknown-effect`, rc 255, `VB-UNKNOWN-EFFECT:` |
| Capacity rejection | `status=error`, `errors=["thread pool exceeded"]` | `kind=rejected`, rc 1, configured denial text |
| Checksum | n/a | `kind=checksum`, rc 1, `sha256 mismatch` |
| Invalid token | `status=error`, `errors=["invalid token"]` | `kind=invalid-token`, rc 1, stderr `invalid token` |

The actual exception policy is “catch `Exception` and return a structured result” for all six public methods, not “raise transport exceptions.” Skill catches at `middle.py:560-579`; command/file/GUI/Spectre catch at `middle.py:628-632,654-658,680-684,713-717`. Parameter programming errors may still raise before/inside argument handling, as the spec permits (`1-四层整体架构与接口.md:261`).

### 2.3 Is `Middle` a Protocol, ABC, or concrete class?

- `Middle` is a structural `typing.Protocol` (`src/pyapi/models.py:98`), not an ABC and not decorated `@runtime_checkable`. Runtime `isinstance()`/`issubclass()` checks are therefore rejected by Python typing; only static type checking benefits from the protocol.
- `VirtuosoInterface` is a separate `ABC` (`models.py:85-95`) with `ensure_ready`, `execute_skill`, and `test_connection`. It is not the five-interface middle protocol and is not the class used by business packages.
- The concrete production object is `BusinessServer` in `src/transport/middle.py:346`. A `python -B` signature/type inspection at snapshot showed `BusinessServer._is_protocol == False`, `BusinessServer.__abstractmethods__ == frozenset()`, and exact signatures matching `Middle` for all six public methods. It is the only current production class that implements the complete middle surface.
- Existing test doubles named `FakeMiddle` are partial structural fakes, not full implementations. For example `test/unit/test_pyapi_packages.py:14-45` implements only upload, Skill, command, and download; it has no GUI or Spectre methods. `test/unit/test_stress_server_endpoints.py:22-45` also omits GUI/Spectre.

### 2.4 Deviations from §4

**Local-timeout and crash-safety defects were fixed during the audit.** The earlier snapshot had a real deviation: local upload/download branches did not pass `budget`, so `_local_upload`/`_local_download` could block past the frozen deadline. The refreshed worktree fixes this by threading `budget` into both local helpers (`src/transport/middle.py:635-658,661-684`), streaming copies with deadline checks in `_copy_file_with_deadline`/`_copy_tree_with_deadline` (`middle.py:45-91`), and returning `kind="timeout", returncode=124` on `_DeadlineExceeded` (`middle.py:770-873`). The refreshed semantics artifact reports all five cases passing (`test/tb/artifacts/semantics-green.json`), including local file/tree/download timeout and install crash safety. The red baseline remains useful historical evidence (`semantics-baseline-red.json`), but it is not the current result.

**Other contract observations:**

- Signature/parameter placement itself matches the spec exactly; no extra positional host/port/tunnel state leaks upward (`models.py:106-128`).
- GUI and Spectre are genuinely one-shot in both local and remote modes; local uses a fresh `subprocess.run` per call, remote acquires a one-shot channel lease (`middle.py:689-737`).
- Remote command/upload/download/GUI/Spectre distinguish channel-budget rejection through `RemoteClient`/`TokenBudgets`; Skill only exposes the facade thread-pool rejection. The contract permits any named capacity reason, but consumers should not assume all three budget strings appear uniformly (`middle.py:468-482,697-717`; `tunnel.py:298-405`).
- The protocol is not runtime-checkable, so there is no runtime guarantee that a fake is a full `Middle`. This is not a frozen-spec violation but is a testability/development risk.
- The captured baseline artifact also reported `registry-cross-process` and `install-crash-safety` red. The refreshed worktree contains registry-lock and atomic-install changes (`src/transport/registry.py:63-107,367-407`; `src/transport/transfer.py:359-428`), and `test/tb/artifacts/semantics-green.json` now reports both passing. These are not yet committed and are outside normal pytest collection.

## 3. Upper-layer status (`src/pyapi/packages/`)

### 3.1 What exists

| Package | Implemented behavior | Public shape | Status |
|---|---|---|---|
| `FileSkillCommandFilePackage` | Upload a file, execute SKILL, run a command, download a file; stop on first failure and retain `BusinessStep` evidence. | `__init__(middle: Middle)`; `run(*, token, local_input, remote_input, skill_code, command, remote_output, local_output, timeout=None, recursive=False) -> BusinessResult` | `PARTIAL` reference scaffold |
| `ParallelProbePackage` | Submit independent commands/uploads to `ThreadPoolExecutor`; collect results and exceptions. | `__init__(middle: Middle)`; `run(*, token, commands, uploads=None, timeout=None, parallel=True, max_workers=None) -> ParallelProbeResult` | `TEST-ONLY` stress/probe utility |

`src/pyapi/packages/__init__.py:1-5` exports both classes. There are no production-grade domain packages yet (for example no schematic, layout, Maestro, netlist, or simulation package in this tree).

### 3.2 Established conventions in the actual code

- Dependency injection: the package constructor receives a `Middle`; packages do not create `BusinessServer`, SSH, sockets, tunnels, or registry objects (`file_skill_command_file.py:29-31`; `parallel_probe.py:19-21`).
- Imports are limited to `pyapi.models` plus local standard library/package models. `file_skill_command_file.py:8-12` imports dataclasses/pathlib/typing and `pyapi.models`; it does not import `transport.*`.
- Results are standard-library dataclasses, mutable and not frozen. `BusinessStep`/`BusinessResult` are at `file_skill_command_file.py:15-26`; `ParallelProbeResult` is at `parallel_probe.py:12-16`. They use `ok`, collected steps/results, and optional error text rather than Pydantic response models.
- Entry style is keyword-only `run(*, token, ...)`, not `run(request)`. The token is an explicit per-call argument and is passed to every middle call. This is the actual convention in both packages (`file_skill_command_file.py:33-45`; `parallel_probe.py:23-32`).
- Command success is tested by `returncode == 0`; Skill success is tested by `skill.ok` (`file_skill_command_file.py:51-73`). The current packages do not branch on `CommandResult.kind` beyond carrying the result object in a step.
- Paths are converted to `Path` for middle calls, and `parallel`/`recursive` are only used when the package intentionally needs middle flags (`file_skill_command_file.py:47-49,67-69`; `parallel_probe.py:37-46`).

### 3.3 Guide conflict: current style vs recommended style

`doc/report/上层开发指南.md` §3 recommends each package contain `Request/Result` data models, a package class, and `package.run(request) -> Result` with frozen request/result dataclasses (`上层开发指南.md:45-84`). The actual packages do not follow that shape: they expose flat keyword arguments and have no Request model (`file_skill_command_file.py:33-45`). The guide is prose guidance, not yet an implemented convention or automated check.

The guide also requires validation before side effects (`上层开发指南.md:190-194`), one business deadline passed as remaining time to each call (`:196-212`), preservation/handling of `kind` (`:214-229`), and explicit concurrency behavior (`:248-253`). The current reference package does not validate inputs, passes the same `timeout` unchanged to each step, and does not implement a package-level deadline. A new production package should decide deliberately whether to follow the guide’s recommended Request/Result convention even though the two current examples use flat kwargs.

### 3.4 What a new package must do to fit the hard boundary

- Accept `Middle` through the constructor and keep it for the package lifetime; never import `transport.*`, Paramiko, socket, subprocess, tunnel, registry, or daemon protocol code.
- Import shared result/interface types from `pyapi.models` and define package-local request/result data models.
- Require `token` on every middle call and never cache it as process-global “current user” state.
- Use `Path`/`str` in the direction required by each middle method and pass `timeout`, `parallel`, or `recursive` explicitly where needed.
- Preserve the result/`kind` of failed steps; do not turn transport failures into apparent success. If following the guide, calculate one end-to-end deadline and pass only remaining time downstream.
- Either use the flat `run(*, ...)` style of current packages or introduce a Request model consistently with the guide; the repository currently has no router that forces either shape.

## 4. Test infrastructure inventory

### 4.1 Test tiers

| Tier | Files | Real unit / live requirement | Notes |
|---|---|---|---|
| `test/unit/` | 42 test modules | Mostly real unit tests; no live Virtuoso or SSH | Uses `unittest`, `mock`, local subprocesses, and local filesystem. Paramiko tests may skip if the optional dependency is absent. |
| `test/integration/` | 2 modules | Needs no Virtuoso; uses real sockets/subprocesses | `test_integration.py` runs a protocol-accurate fake TCP daemon; `test_daemon_handler.py` feeds a fake Virtuoso pipe and can launch the daemon as a subprocess. |
| `test/scenario/` | 3 modules | No external server; local shell/files and fake daemons | Exercises local `BusinessServer`, multi-token isolation, and six-step registration through fake daemon sockets. |
| `test/e2e/` | 3 modules | Real SSH/Virtuoso required when enabled | Gated by `VB_E2E=1` or `VB_E2E_LOCAL=1`; otherwise skipped by class/`setUpClass` checks. |
| `test/tb/` | Manual TB/stress tools plus artifacts | Mixed fake/local/live/manual | Not pytest-collected by design (`test/tb/README.md:3`); includes protocol fake daemons and live stress/fault tools. |
| `test/frontend_tb/` | Mock registration UI server/HTML | No Virtuoso; browser/manual harness | Has no `test_` functions; it is a mock frontend testbench. |

There is no `conftest.py`, no shared pytest fixture module, and no `test/support/` directory in the current tree. Tests create fakes locally inside each module. The normal pytest collection is `test/unit`, `test/integration`, and `test/scenario` only (`pyproject.toml:32-35`). `test/README.md:22` claims a historical 456-collected/all-pass run; this audit did not rerun tests because the instruction was read-only.

### 4.2 Middle-layer fakes/mocks and their locations

| Fake/harness | File:line | What it fakes | Coverage role |
|---|---|---|---|
| `FakeMiddle` | `test/unit/test_pyapi_packages.py:14-45` | Four upper-facing middle methods (upload, Skill, command, download), recording calls | Direct upper-package tests. It does not implement GUI/Spectre and does not record timeout values. |
| `FakeRemote` | `test/unit/test_middle_contracts.py:20-54` | `RemoteClient` operations and injected errors | Tests `BusinessServer` error-to-`kind` mapping; patched at `:78-80`. |
| `FakeRemoteClient` / `FakeSkillClient` | `test/unit/test_middle_routing.py:31-76` | Remote routing and Skill client construction | Patched into `transport.middle` at `:79-80`. |
| `RecordingSkillClient` | `test/unit/test_skill_admission.py:19-61` | Serial Skill delivery, delays, timeout result | Skill gate/queue behavior. |
| `FakeDaemon` | `test/integration/test_integration.py:30-70` | TCP wire protocol daemon | Local `BusinessServer` Skill integration. |
| `FakePipeBuffer`, `FakeStdin`, `FakeStdout` | `test/integration/test_daemon_handler.py:29-68` | Virtuoso pipe/stdin/stdout | Bottom daemon protocol tests. |
| `FakeDaemon` | `test/scenario/test_business_local.py:36-98` | Protocol daemon with timeouts/errors | Full local middle behavior. |
| `FakeDaemon` | `test/scenario/test_multi_user_isolation.py:18-51` | Two independent daemon sockets | Token isolation. |
| `FakeDaemon` | `test/scenario/test_registration_local_full.py:19-64` | Local fake daemon for registration | End-to-end local registration + business use. |
| `FakeMiddle` | `test/unit/test_stress_server_endpoints.py:22-45` | HTTP-server-facing four methods and close() | Stress HTTP wrapper. It omits GUI/Spectre. |
| `FakeDaemon` | `test/unit/test_stress_server.py:22-66` | In-process TCP daemon | Stress server smoke test. |
| Runner fakes | `test/unit/test_endpoint_budgets.py:15`, `test/unit/test_resource_release.py:18`, `test/unit/test_tunnel.py:23`, `test/unit/test_tunnel_transfer.py:18` | SSH runner-like behavior | Budgets, release, tunnel transport. |
| `FakeStream` / `FakePopen` | `test/unit/test_ssh_tunnel_lifecycle.py:21-41` | SSH tunnel process/lifecycle | Tunnel lifecycle. |
| `CountingRunner` | `test/unit/test_runner_single_flight.py:36-52` | Runner creation count | Single-flight behavior. |
| `_FakeProbeRunner` | `test/unit/test_registry_decoupling.py:31-37` | Registration probe runner | Persistence/decoupling contracts. |

The upper-layer test suite is concentrated in `test/unit/test_pyapi_packages.py`. It verifies the happy-path order for `FileSkillCommandFilePackage` (`:48-58`) and failure stop behavior for upload/Skill/command/download (`:60-81`). It verifies mixed success and return-code failure for `ParallelProbePackage` (`:84-97`). It does not cover Request models because none exist, GUI/Spectre because the fakes/packages do not use them, deadline propagation, exception mapping, token-empty validation, or package-level `kind` policy.

### 4.3 Live and manual tests

- `test/e2e/test_e2e_live.py:105-117,183-194` is skipped unless `VB_E2E=1`; it uses `wsl-gent` SSH/real Virtuoso and also exercises the Paramiko backend.
- `test/e2e/test_business_remote_live.py:78-108` is skipped unless `VB_E2E=1` and live bridge daemons are discoverable over SSH.
- `test/e2e/test_business_local_live.py:46-95` is skipped unless `VB_E2E_LOCAL=1` and run on the Virtuoso host; it starts real Virtuoso accounts and uses local mode.
- `test/tb/fake_daemon_host.py` is a protocol-level fake daemon host; `test/tb/cov_remote_real.py` and `test/tb/cov_registration_real.py` are live coverage TBs; `test/tb/semantics_tb.py` is a red-first semantics harness for missing deadline/registry/crash contracts. None is part of default pytest.

### 4.4 How to run tests

Default: `python -m pytest test/unit test/integration test/scenario -q`, or simply `pytest` because `testpaths` already names those three directories (`pyproject.toml:32-35`). CI runs the default suite on Python 3.9 and 3.13 and targeted Windows SSH tests (`.github/workflows/tests.yml:23-24,42-43`). Live E2E remains opt-in. The TB documentation explicitly says TB scripts are not pytest-collected (`test/tb/README.md:3`).

### 4.5 What a new upper package needs for offline testability

- Add a reusable fake-middle fixture/class in a shared test support location, with all six methods, recorded call arguments including token/timeout/parallel/recursive, and configurable return values/`kind` values.
- At minimum add unit cases for: success sequencing; each failure `kind`; timeout propagation and deadline exhaustion; invalid/empty token; missing/invalid path; GUI/Spectre one-shot calls if used; directory recursion; GUI/Spectre capacity rejection; and parallel `rejected` handling.
- Avoid importing `transport.middle.BusinessServer` in upper-package unit tests. The current `FakeMiddle` pattern is the right boundary, but it needs to be shared and completed rather than copied per package.

## 5. Server-layer status

### 5.1 Current structure

| Server | Framework/routing | Current responsibility |
|---|---|---|
| `src/server/registration_server.py` | Stdlib `ThreadingHTTPServer` + `BaseHTTPRequestHandler`, manual `do_GET`/`do_POST`/`do_DELETE` path branching | Setup/control plane for registration: `/`, `/api/users`, `/api/user/...`, `/api/register/apply`, `/api/register/<user>/{validate,probe,deploy,verify}`, legacy `/api/register`, user update/delete. In-memory per-user `RegistrationFlow` and `ReservationTable`; only step 6 persists registry. |
| `src/server/stress_server.py` | Stdlib `ThreadingHTTPServer` + manual `do_POST` | Test-only pressure endpoints: `/api/skill`, `/api/command`, `/api/upload`, `/api/download`, `/api/composite`, `/api/shutdown`. It directly calls `BusinessServer` middle methods. |
| `src/server/__init__.py` | Lazy export of registration `main` | Says the long-running business/API top layer will live here later (`:3-4`). |

The registration server is not a business layer: it imports `transport.register`, `Registry`, and runtime paths (`registration_server.py:28-31`) and manipulates registration state directly. The stress server is also not a business layer: it directly calls `middle.execute_skill`, `run_command`, `upload_file`, and `download_file` (`stress_server.py:55-141`) and even reaches into `middle.registry` to compute a file root (`:94-108`). Thus there is **no** HTTP entry point that selects a business package, constructs a Request, calls `Package(middle).run(request)`, and serializes a business Result.

### 5.2 What the guide says §4 should look like

`doc/report/上层开发指南.md` §4 recommends: HTTP request -> validate body/token -> select business package -> construct Request -> `Package(middle).run(request)` -> serialize Result (`上层开发指南.md:128-139`), with a package registry/router table (`:141-176`). It further requires each HTTP request to run in an independent task thread, token to come from each request body, Server not to inspect SSH/tunnel/daemon state, runtime failures to return structured `ok=false`, and parameter errors to map to HTTP 400 (`:178-186`).

### 5.3 Gap

The gap is structural, not just a missing route: there is no `BusinessApp`/router, no Request-model registry, no package invocation endpoint, no serialization contract for `BusinessResult`/`ParallelProbeResult`, and no production error mapping from package results to HTTP status/body. `ThreadingHTTPServer` satisfies the thread-per-request starting point, but the current stress server is a TB and its composite endpoint deliberately contains the business chain itself. The current `server/__init__.py` explicitly acknowledges the future business HTTP layer.

## 6. Build and packaging

| Area | Current setting | Consequence |
|---|---|---|
| Build backend | setuptools >=64 (`pyproject.toml:1-3`) | Editable/sdist/wheel use setuptools. |
| Project | `virtuoso-bridge` 0.9.0, Python >=3.9 (`:5-9`) | One distribution contains upper/middle/lower packages. |
| Runtime dependency | `pydantic>=2.0` (`:10-12`) | Upper models use Pydantic; transport otherwise relies on stdlib plus optional SSH extras. |
| Extras | `ssh = paramiko>=3.5, PySocks>=1.7.1`; `dev = pytest, paramiko, PySocks, coverage` (`:14-20`) | Paramiko backend is optional; tests may skip without it. |
| Entry point | `virtuoso-bridge = server.registration_server:main` (`:22-23`) | The CLI currently starts the registration server, not a business API server. |
| Package discovery | `[tool.setuptools.packages.find] where = ["src"]` (`:25-26`) | A new `src/pyapi/...` package is discovered automatically. A new subpackage under `src/pyapi/packages/` is also included when it has an `__init__.py`. A new single module in an existing package is included with that package. |
| Package data | Only `server/registration_page.html` and `bridge.resources/*.il/*.py` (`:28-30`) | Any new upper-layer JSON, template, or data asset is **not** automatically guaranteed in a wheel; add package-data or include-package-data configuration. |
| Pytest | `testpaths = ["test/unit", "test/integration", "test/scenario"]`, `pythonpath = ["src"]`, `addopts = "-q"` (`:32-35`) | New unit tests under `test/unit` are collected. E2E/TB are not. |
| Lint/type/coverage config | None in `pyproject.toml` | No Ruff, Flake8, mypy, pyright, or coverage config is enforced by packaging. CI only runs pytest and the spec checker. |

Exact new-package pickup: create `src/pyapi/packages/<name>.py` or `src/pyapi/<subpackage>/__init__.py`. It will be discovered by setuptools because `src` is the package root. Code imports work in pytest because `pythonpath = ["src"]`; installed usage works after `pip install -e .`. Only package data needs explicit configuration.

## 7. Conventions and guardrails already enforced

| Guardrail from the guide/architecture | Automated enforcement today | Evidence/gap |
|---|---|---|
| Upper packages only import `pyapi.models`/local models; no `transport`, `socket`, `subprocess`, Paramiko | **No** | There is no AST/import-ban test. `tools/check_spec.py:156-180` only scans normative spec Markdown for duplicate mechanism text. CI runs pytest/spec checks only (`.github/workflows/tests.yml:23-24,42-43`). |
| Packages receive `Middle` by constructor and do not create connections | Partially conventional, not enforced | Both current packages inject middle; no test scans arbitrary new package constructors. |
| Every call carries `token` | Signature-level and partly tested | `Middle` signatures make token keyword-only (`models.py:106-128`); upper tests record token in `FakeMiddle` (`test_pyapi_packages.py:27-45`). There is no test that a new package cannot cache a token. |
| Request/Result models and `run(request)` | **No** | Guide recommends it (`上层开发指南.md:45-84`), but current packages use `run(*, ...)` and no Request classes. |
| Validate before side effects | **No** | Guide rule only (`上层开发指南.md:190-194`); current package starts upload immediately. |
| One package-level deadline with remaining time per step | **No** | Guide rule only (`:196-212`); current package forwards the same timeout to each middle call. Local file timeout is itself broken. |
| Preserve `kind` and stop on unknown-effect/checksum | Partially tested at middle, not upper | `test/unit/test_middle_contracts.py:92-151` checks middle mappings. No upper package test asserts `kind`-specific policy. |
| Parallel/rejected behavior | Partially tested | `test/unit/test_endpoint_budgets.py`, `test/unit/test_middle_routing.py`, and stress tests cover budget/routing, but the upper `ParallelProbePackage` has no rejected-retry/policy test. |
| Server thin dispatch, no business steps in Server | **No** | No business server exists; stress server directly implements a composite chain (`stress_server.py:90-140`). |
| Spec ownership/no duplicated normative definitions | **Yes for spec Markdown only** | `tools/check_spec.py:87-190` checks hash, versions, links, JSON, banned copies, headings. It does not inspect Python layering. |
| Frozen middle result/error contract | Partially automated | `test/unit/test_middle_contracts.py` maps errors to kinds; `test/unit/test_spec_contracts.py` covers file-root/endpoint vectors. No exhaustive contract test for every interface/mode. |
| Manual semantics/lifecycle TBs | Not in pytest | `test/tb/semantics_tb.py` is untracked and outside `testpaths`; `test/tb/README.md:3` confirms TBs are not auto-collected. |

Key conclusion: almost all of `doc/report/上层开发指南.md` is prose guidance. The only strong automated guardrail is the frozen spec checker for Markdown, plus middle-contract unit tests. There is no Python import-boundary check, no package-conformance check, and no CI job that executes a new upper package against a fake Middle.

## 8. Risks and blockers for upper-layer development

| Risk/blocker | Severity | Why it blocks or slows new packages | Evidence |
|---|---|---|---|
| Semantics fixes are uncommitted and the green TB is outside pytest | **Medium** | The current working tree passes the deadline/crash semantics TB, but a colleague building from committed HEAD or normal pytest would not see those fixes. | `semantics-green.json`; `test/tb/semantics_tb.py` is outside `testpaths`. |
| No business HTTP layer | **High** | A new package cannot be reached by a production HTTP request through a router/request-model path yet. | `src/server/__init__.py:3-4`; no `BusinessApp`; `stress_server.py:90-140` is TB-only. |
| No shared full fake-middle harness | **High for testability** | Each package must duplicate fakes, and current fakes omit GUI/Spectre and timeout/kind recording. A package can pass tests while failing integration. | `test/unit/test_pyapi_packages.py:14-45`; no `conftest.py`/`test/support`. |
| Existing upper packages do not match the guide’s Request/Result convention | **High for consistency** | New developers cannot tell whether to copy flat kwargs or follow the guide; Server code would need to know two invocation styles. | `file_skill_command_file.py:33-45`; `上层开发指南.md:45-84,128-176`. |
| No import-boundary enforcement | **High** | An upper package can accidentally import `transport`, `socket`, or `subprocess`; tests/CI will not catch the layering violation. | no AST import guard; `tools/check_spec.py` only scans docs; `.github/workflows/tests.yml`. |
| Packages lack validation/deadline/kind policy | Medium–High | Failures may be reported late, repeated incorrectly, or with misleading success/failure semantics; 500/400 mapping is undefined. | `上层开发指南.md:190-229`; current package code. |
| Middle protocol is not runtime-checkable | Medium | `isinstance(middle, Middle)` raises; structural conformance is static-only. Fakes can silently omit methods. | `src/pyapi/models.py:98` and `test/unit/test_pyapi_packages.py:14-45`. |
| `CommandResult.kind` is an unchecked string | Medium | Typos/unknown kinds are accepted by the model and can reach business logic. | `src/pyapi/models.py:53-64`. |
| GUI/Spectre upper use is untested | Medium | The middle supports both roles, but no upper package or shared fake exercises them. New GUI/Spectre packages need new fakes and integration cases. | `middle.py:625-654`; current package tests. |
| Packaging data assets | Low–Medium | New JSON/templates under `pyapi` may work from source but disappear from wheels without package-data config. | `pyproject.toml:28-30`. |
| Worktree is dirty/untracked and moving | Medium | `middle.py`, `registry.py`, and `transfer.py` have uncommitted semantics fixes; `semantics_tb.py` and its artifacts are untracked. A colleague may plan against a moving baseline. Re-snapshot before implementation. | Git status at snapshot. |
| No lint/type-check config | Medium | Layer typing, signatures, and package conventions are not mechanically verified. | `pyproject.toml` has no tool.ruff/mypy/pyright sections. |

Recommended minimum work before or alongside new upper packages: (1) commit or otherwise stabilize the current middle semantics fixes and promote the semantics TB into an automated CI tier; (2) choose and document one upper package invocation convention, then make the guide and examples agree; (3) add a reusable full `Middle` fake with all six methods and configurable results/kinds; (4) add an AST import-boundary test and run it in CI; (5) add a thin business HTTP router with request models and structured result/error mapping; (6) add package-level deadline/validation/kind tests; (7) keep normal pytest independent of live TBs while explicitly running the semantics TB in CI.

