# REVIEW-D · brief #1 全量抽样（42 条 `direct` 语义核验）

> 评审方：独立子代理（`review-D`）｜ 快照：`HEAD=e3e810d` + 未提交工作区
> 对象：`red-team-brief.md` §1 第 1 条（随机抽 ≥30 行标 `direct`，打开被引 TB 确认断言存在且真的断言了该条款，每簇 ≥4 条）
> 覆盖：**42 条 = g1–g6 每簇 7 条**，逐条打开被引证据核断言（非文件名匹配）
> 方法：seed=4092 分层抽样；脚本 `test/artifacts/tmp/r8_direct_sample.py`（抽样）+ `r8_direct_excerpt.py`（按 `::symbol` 抽取函数体、按文件抽取断言行）
> 去重：review-A-lite 已核的 15 条已排除，不重复计数
> 结论：**36 条成立 / 6 条需处置**（无"整行假覆盖"；问题集中在子句级缺口与引用形式）

## 1. 结果总览

| 簇 | 抽样 | ok | 需处置 | 需处置项 |
|---|---:|---:|---:|---|
| g1-core | 7 | 5 | 2 | 总览#175、总览#206 |
| g2-mid | 7 | 5 | 2 | 并发#022、日志#045 |
| g3-reg | 7 | 6 | 1 | 控制面#011 |
| g4-edit | 7 | 6 | 1 | layout#180 |
| g5-sim | 7 | 7 | 0 | — |
| g6-calibre | 7 | 7 | 0 | — |
| **合计** | **42** | **36** | **6** | 其中 5 条为子句/判据须修，1 条为引用形式 |

判定口径与 brief 一致：只有"被引 TB 里存在断言、且该断言真的覆盖条款语义"才算 ✅；
断言存在但只覆盖条款的一部分 → 记为**子句缺口**；条款措辞与断言对象不一致 → 记为**口径不一致**。

## 2. 逐条结论

| 编号（簇） | 被引证据 | 结论 |
|---|---|---|
| 总览#159 (g1) | `test_daemon_handler.py`、`daemon_log_protocol_tb.py` | ✅ token 必填/NAK、`log_level`/`log_max_bytes` 非法即 NAK 且不触管道、成功帧 STX 均有断言 |
| 总览#175 (g1) | `daemon_log_protocol_tb.py`、`test_daemon_handler.py` | ⚠️ **子句缺口**：只断言 STX/NAK 首字节；`1e`(RS) 终止字节在被引证据里未断言（见 §3 F1） |
| 总览#196 (g1) | `test_transfer.py`、`test_tunnel_transfer.py` | ✅ 临时落盘→SHA 校验→原子替换→失败回滚（目标不变）→覆盖语义均有读回断言 |
| 总览#206 (g1) | `test_credential_routing.py`、`test_ssh_tunnel_lifecycle.py`、`role_credential_isolation_tb.py` | ⚠️ **子句缺口**：endpoint 去重/凭据不同不复用成立；"跨 token 不共用"未被被引证据断言（见 §3 F2） |
| 配置#056 (g1) | `test_workdir_contract.py`、`test_common_config.py` | ✅ 子结构固定 + 启动自动创建 + 默认 root 均有断言 |
| 配置#071 (g1) | `test_registration_server_edges.py::test_credential_reuse_requires_enhanced_token`、`::test_apply_rejects_unknown_enhanced_token`、`test_credential_routing.py` | ✅ 401 + `credential reuse requires enhanced_token` + 任一持有者 token 放行 + 未知 token 拒绝，逐条落地 |
| 配置#118 (g1) | `test_spec_contracts.py::test_vectors_from_spec`、`::test_canonical_host_rules` | ✅ 规范化向量（` Server-A. `→`server-a`）+ 指纹一致 + 同文件 `::test_alias_is_not_resolved` 覆盖"不查 DNS"；`~/.ssh/config` 使用范围由 `test_register_flow.py::test_remote_role_non_22_port_is_rejected` 承担（未列在本行证据，属引用可加项） |
| 并发#022 (g2) | `test_endpoint_budgets.py` | ⚠️ **子句缺口**：共享 endpoint 取 `min(max_sessions)` 成立；"daemon 专用 Skill tunnel 计入通道数"无断言（见 §3 F3） |
| 日志#045 (g2) | `test_common_config.py`、`test_daemon_log_utf8_budget.py` | ⚠️ **判据与 reason 不符**：reason 写"默认 64KB 在配置默认值测试"，被引 TB 未断言该默认值（见 §3 F4） |
| 路由#032 (g2) | `role_split_tb.py`（live）、`test_validation_roles.py` | ✅ 混合 local/remote 解析（`command.mode=="remote"`、local role 不解析 SSH 目标）+ 真机 `roles-are-split`/各 role 落主机步骤记录 |
| 路由#037 (g2) | `test_validation_roles.py`、`test_norm_gap_round8.py::TestMixedModeSingleToken` | ✅ `daemon=local + command/file=remote` 原样保留、local 不解析 SSH 目标，用例与条款一一对应 |
| 路由#052 (g2) | `test_credential_routing.py`、`test_spec_contracts.py` | ✅ 同 endpoint 同凭据共用 1 个 runner、凭据不同→2 个 runner、等价路径拼写归一 |
| 路由#060 (g2) | `test_endpoint_budgets.py` | ✅ 线程/通道预算按 token、endpoint 上限取最小值、共享 endpoint 预算不随 role 数增加 |
| 顶层#042 (g2) | `test_api_server_main.py::test_unserializable_result_is_structured_500`、`test_top_layer_pool.py` | ✅ 未预期异常→结构化 500 且服务继续（后续请求仍 200/429/503，不终止） |
| 控制面#007 (g3) | `test_registration_server.py`、`test_api_server_main.py` | ✅ 控制面职责（注册/用户管理/全局配置）与 admin 校验、audit 落盘均有断言；"低并发"为描述性表述 |
| 控制面#008 (g3) | `test_api_server_main.py`、`api_server_tb.py` | ✅ 业务端口调度 + 池化上限（`pool_size_from_snapshot({})==1024`、hot resize、drain）有断言；"高并发"为描述性表述 |
| 控制面#011 (g3) | `src/register/server.py:991`、`test_registration_server.py`、`test_norm_gap_round8.py::TestRegistrationBindsLoopback` | ⚠️ **引用形式**：行为已被 AST 断言覆盖（默认 `--host=127.0.0.1`）；但 `src/...:991` 的行号式引用不在自家 checker 覆盖范围内（见 §3 F5） |
| 控制面#083 (g3) | `test_api_server_main.py`、`test_top_layer_pool.py` | ✅ 可变准入上限：reload 生效、`in_flight>=上限`→429+`Retry-After`、hot resize 放行更多请求 |
| 注册#015 (g3) | `test_register_flow.py`、`test_registration_server_edges.py` | ✅ `key_dir/key` 条件必填：缺失→400 且点名 `key_dir/key`；`key` 带目录成分→400 |
| 注册#038 (g3) | `test_register_flow.py`、`test_reservation.py`、`registration_http_six_step_tb.py` | ✅ 各步失败保留候选可原样重试、`cancel` 才释放、任何失败不写 registry（六步 TB 每步 `assert_no_registry_write`）——本轮抽样中证据最强的一条 |
| 注册#051 (g3) | `test_register_flow.py::test_gui_display_probe_explicit_and_detected` | ✅ 显式 display 校验失败→ERROR 不静默改号；未给出→探测唯一则写回、探测不到→`null`+WARNING |
| layout#023 (g4) | `layout_e2e_tests.py::_case_read_filters`（live） | ✅ `detail=index` 只回 `{kind, layer, purpose, lpp}`、`geometry` 默认含坐标，真机 `_check` 断言字段集合 |
| layout#028 (g4) | `layout_e2e_tests.py::_case_read_params`（live） | ✅ 同一条 region：`intersect` 命中跨界 rect / `contain` 排除，真机对照断言 |
| layout#180 (g4) | `test_layout_contracts.py` | ⚠️ **口径不一致**：spec 写 `pos` 用 point（`7:8`），实现与被引断言为 `list(x y)`（见 §3 F6） |
| schematic#017 (g4) | `test_norm_gap_batch2.py::TestSchematicConnectivityIgnoresFilter` | ✅ `focus=connectivity` 时 `object_filter` 哨兵名不得出现、`focus=positions` 时照常拼接，正反双向断言 |
| schematic#049 (g4) | `schematic_e2e_tests.py::_case_negative`（live）、`test_schematic_contracts.py` | ✅ 真机负控制逐条拒绝 `xy`、拆 `x`/`y`、缺 `pos`，并要求错误文本点名 `pos`；离线侧补 `pos` 形状校验 |
| symbol#038 (g4) | `test_symbol_contracts.py::test_write_reports_view_probe_results` | ✅ view 探测三态（missing→not found / 类型不符→view type / 异常→unexpected view probe）后才进入写路径 |
| symbol#117 (g4) | `test_symbol_generate.py::test_pin_order_is_preserved_not_sorted` | ✅ 显式 pin 顺序 `["z","a"]` 原样保留，且 `sort_pins` 不承诺排序的语义有对应断言 |
| spectre#036 (g5) | `test_spectre_contracts.py` | ✅ 业务失败→`ok=false`+`error`；结构/参数错误→`ValueError`（`bad_mode.ok is False` 且 error 含 ValueError） |
| spectre#040 (g5) | `test_spectre_contracts.py::test_require_bool_and_job` | ✅ 逐例拒绝 `""`、`a/b`、`a\b`、`..`、`-lead`、含空格、None，与条款正则一致 |
| spectre#097 (g5) | `test_spectre_contracts.py::test_build_spectre_command_defaults` | ✅ 9 个默认参数逐个 `assertIn`（`-64`/`+escchars`/`+log spectre.out`/`-format psfascii`/`-raw <stem>.raw`/`+lqtimeout 900`/`-maxw 5`/`-maxn 5`/`+logstatus`） |
| spectre#146 (g5) | `test_spectre_contracts.py::test_has_fatal_detects_markers` | ✅ 9 类终止标记（`ERROR (`、`Error reading`、`read-in failed`、license、`SPCRTRF`、convergence、prematurely、`Segmentation fault`）逐条为正，另附"0 errors"负控制 |
| spectre#197 (g5) | `test_spectre_metrics.py`、`test_spectre_util_contracts.py` | ✅ `noise_integral` 依赖 `freq` 轴并有空窗口失败路径；`ac_magnitude`/`bandwidth` 的复数前置错误路径各有用例 |
| spectre#202 (g5) | `test_spectre_util_psf_contracts.py`、`test_spectre_contracts.py` | ✅ CSV 表头 `time,vout`、列选择、行数与数值读回；复数按 `.re`/`.im` 展开由 psf 契约用例承担 |
| veriloga#057 (g5) | `test_veriloga_contracts.py::test_validation_and_lock`、`veriloga_e2e_tests.py` | ✅ `*.cdslck` 存在时写失败且报 `locked by an open editor`（不自动关窗） |
| calibre#059 (g6) | `test_calibre_package.py::test_job_state_failed_license` | ✅ 日志含 license 缺失→`failure_kind=="license"`，与 input 类失败可区分 |
| calibre#151 (g6) | `test_calibre_package.py`、`s11_full_flow.py`（live） | ✅ si.env/`.simrc` 均断言 `checkCAPPERI = nil`，真机 auCdl 链路复跑 |
| skillref#034 (g6) | `test_skillref_package.py` | ✅ 取值顺序与回带：`source`/`doc_root` 原样回带、缺 `doc_root` 时零远端调用 |
| skillref#051 (g6) | `test_skillref_package.py` | ✅ 仅三个字段：只给其一是业务失败（`同时给出 source 与 doc_root`）、远端缺 `doc_token` 报错点名 |
| skillref#102 (g6) | `test_skillref_docs_contracts.py`、`test_skillref_package.py` | ✅ `name`/`entry` 共用同一匹配器（`name_matches`/`name_score` 契约），差异只在描述并入面 |
| skillref#180 (g6) | `test/semi/probes/skill_tooling_probe.py`、`test_skillref_docs_contracts.py` | ✅ 与 `tools/` 侧共享 `.fnd/.tgf/HTML→Markdown` 口径（半真机探针 + 解析契约） |
| skillref#212 (g6) | `test_skillref_package.py` | ✅ "不做路径探测"：`source`/`doc_root` 必须显式给出，缺失即业务失败 |

## 3. 需处置项（供 root 决策）

### F1 · 总览#175：RS 终止字节不在被引证据内

- 条款：成功帧 `02 33 1e`、失败帧 `15 <文本> 1e`（含 `1e`=RS 终止字节）。
- 事实：`test/offline/core/daemon_log_protocol_tb.py:43` 导入了 `RS` **但全文未再使用**（`rg -n "\bRS\b"` 仅命中 import 行）；
  `test/offline/integration/test_daemon_handler.py` 只断言 `startswith(STX/NAK)`，解码用 `raw[1:].rstrip(RS)`——**RS 缺失也能通过**。
- 实际覆盖位置：`test/offline/unit/test_daemon_parity.py:136` 以 `while b"\x1e" not in data` 等待终止字节，但**该文件未列在本行证据**。
- 建议：把 `test_daemon_parity.py`（或其中一个用例）补进本行证据；或在被引 TB 内补一条 `assertTrue(raw.endswith(RS))`。

### F2 · 总览#206："跨 token 不共用"无被引证据

- 事实：被引 `test/credential_routing.py` 5 个用例全部是**同一 token** 内的 endpoint 去重/凭据区分；`role_credential_isolation_tb.py:105` 用单个 token 建两个 role runner（验证凭据不同不复用）。
- 实际覆盖位置：`test/offline/scenario/test_multi_user_isolation.py:78` `assertIsNot(server._skill("tok-a"), server._skill("tok-b"))` + 两 token 各自路由到自己的 daemon（:54–:75），**未列在本行证据**。
- 建议：补引该 scenario 用例，或把本行 verdict 拆分为"endpoint 去重=direct / 跨 token 隔离=indirect"。

### F3 · 并发#022："daemon 专用 Skill tunnel 计入通道数"无断言

- 事实：实现确实占用通道——`src/transport/tunnel.py:279` `lease = self._acquire_channel(self.targets.daemon)`（`ensure_tunnel`，release 见 :300）。
- 但 `test/offline/unit/test_endpoint_budgets.py` 只断言"共享 endpoint 取 min(max_sessions)/token 预算/线程预算"；全树 `try_acquire_channel` 只出现在 `fault_injection_tb.py`、`test_endpoint_budgets.py`、`test_tunnel_transfer.py`，均非技能隧道计数。
- 建议：新增用例——建 remote client 后断言 `channels_in_use_for(daemon_endpoint)` 因 skill tunnel 占用 +1（或 `endpoint_limit` 已被隧道消耗 1 个名额）；在此之前本行宜降为 partial 并写 `gap_test`。

### F4 · 日志#045：reason 声称的"默认 64KB"判据不存在

- 条款：`log_max_bytes` 默认 64KB。
- 事实：该行 reason 写"默认 64KB 在配置默认值测试"，被引 `test_common_config.py` 只覆盖 `business_thread_pool_size=8` 与"不解读"读取；全树检索 `65536` 的命中均为 recv 缓冲、`ulimit -n 65536`、显式传参（`daemon_log_protocol_tb.py:94` 显式传 65536）或显式配置（1024/2048/4096），**无一条断言默认值**。
- 实现锚点（供补测参照）：`src/common/registry.py:283` `Field(default=65536, ge=1)`、`src/bridge/resources/ramic_bridge_daemon_3.py:389` `int(req.get("log_max_bytes", 65536))`。
- 建议：补一条默认值断言（如 `Cdslog().log_max_bytes == 65536`），或修正 reason 并降级本行。

### F5 · 控制面#011：源码行号式引用不在自家核账范围内

- 事实：`src/register/server.py:991` 内容正确（`parser.add_argument("--host", default="127.0.0.1")`，已核对）；
  但 `test/artifacts/tmp/r8_evidence_exist.py` 把 `src/` 前缀整体排除、且只按 `::` 切分，**该引用永远不会被校验**；全文其余源码锚点用 `file::symbol` 形式。
- 影响：行号会随源码漂移而静默失效；本次抽样中它是唯一一处 `:line` 形式。
- 建议：统一改为 `src/register/server.py::main`（或移除该引用，因为行为已由 `TestRegistrationBindsLoopback` 覆盖）。

### F6 · layout#180：`pos` 的 point 写法与 spec 措辞不一致

- spec：`spec/design-concepts/上层/4-layout.md:241`「`pos` 写 **point**（`7:8`），`bBox`/`points` 写 list」。
- 实现：`src/pyapi/packages/layout.py:195` `_point_expr` 返回 `list(x y)`；`pos`/`new_pos`/`xy` 赋值处（:640、:790、:849、:861、:894）全部使用它。
- 被引断言：`test_layout_contracts.py:134` `assertEqual(L._point_expr((1.5, 2.0)), "list(1.5 2)")`——断言的是实现的写法，而非 spec 的 `7:8`。
- 影响：真机 `layout.write` 全链绿（`list(x y)` 被 IC618 接受，与 schematic 的 `list(0:1 2:3)` 写法不同但等价），因此属**成文口径差异**而非功能缺陷。
- 建议：二选一并留记录——① 把 spec 该句改为"坐标以 `list(x y)`/point 字面量写入（两者等价）"；② 统一实现为 `x:y` 字面量并同步契约用例。

## 4. 方法学备注

- 抽样脚本第一版把 `src/register/server.py:991` 误报为 "MISSING FILE"（我的解析按 `::` 切分），已人工核对源码行确认其内容正确；该现象本身即 F5 的由来。
- 判 ✅ 的行均确认了**断言语句**而非仅文件名；对 `record()/check_true()` 风格的真机/半真机 TB，则核到具体 `case()`/`_check()` 的期望值（如 `layout_e2e_tests.py` 的字段集合、`registration_http_six_step_tb.py` 的 `assert_no_registry_write`）。
- 本轮未改动 `src/`，未改任何被评审文件；抽样与抽取脚本、原始输出留在 `test/artifacts/tmp/r8_direct_sample.{py,md}`、`r8_direct_excerpt.{py,md}`。

## 5. 残留

- brief #1 要求的条数已满足（42 ≥ 30，g1–g6 各 7 ≥ 4），**review-A-lite 的"≥40 条欠账"至此可销**（15 + 42 = 57 条人工语义核验）。
- brief 其余条目（#2–#11）由 review-A/B/C 与本轮共同覆盖情况未变；本文件不重复其结论。
