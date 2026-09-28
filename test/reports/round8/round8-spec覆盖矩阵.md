# 第八轮 · Spec 条款覆盖矩阵（NORM 297 条逐条裁定）

> 生成：`test/shared/runners/merge_round8_spec_matrix.py` ｜ 基线：HEAD=64c803c（工作区被测）
> 统计：direct 222 / indirect 16 / partial 6 / gap 0 / na 53（共 297）

> 证据强度（direct+indirect 238 条）：**live 78 / semi 20 / 仅离线 140 / 仅源码或产物 0**。强度列是**事实**，不改变 verdict：离线证据用于 Python 侧接口/校验/解析/预算类条款；行为类条款应有 live/semi 证据。

判定口径：
- **direct**：有直接判据（读回/数值/字节/结构化断言）；**indirect**：由下游消费间接体现；
- **partial**：条款的部分子句无证据（`gap_test` 写明补什么）；**gap**：完全无 TB 证据（本轮为 0）；
- **na**：定义/指针/实现自由度/明确不做/已知限制，均给出理由。
- 全量分诊口径（含 OPS/PROSE）：`spec-clause-triage.md`；OPS 793 条由 op×param 矩阵 + 原子矩阵承担。

## 分组统计

| 组 | 条数 | direct | indirect | partial | gap | na |
|---|---:|---:|---:|---:|---:|---:|
| g1-core | 50 | 41 | 2 | 1 | 0 | 6 |
| g2-mid | 46 | 27 | 2 | 0 | 0 | 17 |
| g3-reg | 44 | 34 | 1 | 0 | 0 | 9 |
| g4-edit | 60 | 47 | 5 | 1 | 0 | 7 |
| g5-sim | 54 | 40 | 4 | 2 | 0 | 8 |
| g6-calibre | 43 | 33 | 2 | 2 | 0 | 6 |

## 逐条矩阵

| 编号 | 文档 | verdict | 证据强度 | 说明 | 证据 |
|---|---|---|---|---|---|
| 总览#010 | 总览/1-四层整体架构与接口.md | **direct** |  | 路由投送、并发限流、结构化结果各有断言；真机四 token 五接口复跑通过 | test/offline/unit/test_middle_routing.py<br>test/offline/unit/test_middle_contracts.py<br>test/offline/core/semantics_tb.py<br>test/live/transport/cov_remote_real.py |
| 总览#021 | 总览/1-四层整体架构与接口.md | **direct** |  | 常驻性由同一 daemon 多请求复用（真机）+ daemon 运行时契约钉住；‘可同进程’属实现自由度 | test/offline/unit/test_daemon_runtime_contracts.py<br>test/live/transport/cov_remote_real.py |
| 总览#094 | 总览/1-四层整体架构与接口.md | **indirect** |  | 参数校验有包级离线契约、操作顺序由包 E2E 间接体现；无独立条款级用例（该行是职责列表片段） ｜ **缺口**: —（由包契约+E2E 共同承担，不单独立项） | test/offline/unit/test_schematic_contracts.py<br>test/offline/unit/test_layout_contracts.py<br>test/live/packages/*_e2e_tests.py |
| 总览#103 | 总览/1-四层整体架构与接口.md | **direct** |  | per-token 线程池占用/回池/超限拒绝（含指明预算）有断言 | test/offline/unit/test_endpoint_budgets.py<br>test/offline/core/fault_injection_tb.py<br>test/offline/core/semantics_tb.py |
| 总览#110 | 总览/1-四层整体架构与接口.md | **direct** |  | daemon 把 skill 交给求值并回 value/error 帧有真进程级断言 + 真机 skill 段 | test/offline/integration/test_daemon_handler.py<br>test/live/transport/cov_remote_real.py |
| 总览#115 | 总览/1-四层整体架构与接口.md | **direct** |  | 依赖方向用 import 契约（上层不得 import transport/socket 等）+ 顶层 dispatch 测试钉住 | test/offline/unit/test_upper_layer_import_contract.py<br>test/offline/unit/test_top_layer_dispatch.py |
| 总览#144 | 总览/1-四层整体架构与接口.md | **direct** |  | role/name 过滤、未配置键省略、只返回事实字段均有断言（且断言不泄漏 host/port） | test/offline/unit/test_middle_contracts.py::test_query_filters_role_and_name<br>test/offline/core/semantics_tb.py::case_query_shape |
| 总览#148 | 总览/1-四层整体架构与接口.md | **direct** |  | 非法 role/name → TypeError/ValueError；未知 token → 结构化错误，均有断言 | test/offline/unit/test_middle_contracts.py::test_query_rejects_invalid_filters<br>test/offline/unit/test_middle_contracts.py::test_query_unknown_token_is_structured_error |
| 总览#159 | 总览/1-四层整体架构与接口.md | **direct** |  | token 必填/错 token NAK、log_level/log_max_bytes 校验、STX/NAK/RS JSON 帧均有断言 | test/offline/integration/test_daemon_handler.py<br>test/offline/core/daemon_log_protocol_tb.py |
| 总览#164 | 总览/1-四层整体架构与接口.md | **direct** |  | 校验失败不接触求值通道（sent==b""）+ token 不出现在求值字节流，两条断言均已落地（后者第八轮补） | test/offline/integration/test_daemon_handler.py::test_invalid_token_is_nak_without_touching_pipe<br>test/offline/integration/test_daemon_handler.py::test_token_is_not_written_into_skill_text |
| 总览#175 | 总览/1-四层整体架构与接口.md | **direct** |  | 成功帧 02…1e / 失败帧 15…1e 由帧常量构造与 roundtrip 断言覆盖 | test/offline/core/daemon_log_protocol_tb.py<br>test/offline/integration/test_daemon_handler.py |
| 总览#178 | 总览/1-四层整体架构与接口.md | **direct** |  | 运行期错误一律结构化（kind/errors），参数编程错误直抛，均有断言 | test/offline/unit/test_middle_contracts.py<br>test/offline/core/fault_injection_tb.py<br>test/offline/unit/test_transport_error_paths.py |
| 总览#179 | 总览/1-四层整体架构与接口.md | **direct** |  | kind 枚举完整 + 真实 rc=124/255 仍 kind=command 有专项用例（含负控制） | test/offline/unit/test_middle_contracts.py<br>test/offline/core/fault_injection_tb.py<br>test/offline/unit/test_middle_reserved_codes.py |
| 总览#192 | 总览/1-四层整体架构与接口.md | **direct** |  | skill 投递后不重发（单次投递断言）、超时视为结果未知，均有断言 | test/offline/core/semantics_tb.py<br>test/offline/unit/test_persistent_shell_protocol.py |
| 总览#196 | 总览/1-四层整体架构与接口.md | **direct** |  | 临时落盘→SHA 校验→原子替换、失败回滚（目标不变）、覆盖语义均有断言 | test/offline/unit/test_transfer.py<br>test/offline/unit/test_tunnel_transfer.py |
| 总览#204 | 总览/1-四层整体架构与接口.md | **direct** |  | 五 role 独立配置（字段级）+ 真机跨主机 S2 五 role 投送 5/5 | test/offline/unit/test_register_flow.py<br>test/offline/unit/test_validation_roles.py<br>test/live/flows/role_split_tb.py |
| 总览#206 | 总览/1-四层整体架构与接口.md | **direct** |  | endpoint 去重复用、凭据不同不复用、跨 token 不共享，均有断言 + 半真机验证 | test/offline/unit/test_credential_routing.py<br>test/offline/unit/test_ssh_tunnel_lifecycle.py<br>test/semi/transport/role_credential_isolation_tb.py<br>test/offline/scenario/test_multi_user_isolation.py::test_two_users_ |
| 总览#210 | 总览/1-四层整体架构与接口.md | **direct** |  | path/transport/command/skill/checksum 五类错误可区分，均有结构化断言 | test/offline/core/fault_injection_tb.py<br>test/offline/unit/test_transport_error_paths.py<br>test/offline/unit/test_middle_contracts.py |
| 总览#211 | 总览/1-四层整体架构与接口.md | **indirect** |  | 一 token→一 daemon 的映射与多 token 隔离有断言（离线多用户 + 真机四 token）；‘第二 CIW=配置错误’属环境约定，无负向用例 ｜ **缺口**: —（环境约定项，不做负向） | test/offline/unit/test_middle_contracts.py<br>test/offline/scenario/test_multi_user_isolation.py<br>test/live/transport/cov_remote_real.py |
| 总览#215 | 总览/1-四层整体架构与接口.md | **direct** |  | 绝对路径/`..` 不被拦截、root 仅作默认目录，均有断言；2026-09-28 复核补钉：新增 TestLocalTildeExpansion::test_root_is_default_dir_not_a_sandbox（相对路径落 root、绝对路径且在 root 之外不被拦截、.. 按  | test/offline/unit/test_local_path_expansion.py<br>test/offline/unit/test_transfer.py<br>test/offline/unit/test_local_path_expansion.py::TestLocalTildeExpansion::test_root_is_default_dir_not_a_sandbox |
| 总览#216 | 总览/1-四层整体架构与接口.md | **direct** |  | VB-PATH-NOT-VISIBLE 结构化错误、不改写路径，均有断言 | test/offline/unit/test_tunnel_transfer.py<br>test/offline/unit/test_transport_error_paths.py<br>test/offline/unit/test_middle_contracts.py |
| 总览#218 | 总览/1-四层整体架构与接口.md | **direct** |  | 单 CIW 串行闸门（离线）+ parallel 一次性命令（半真机）+ 生产面混合并发（真机） | test/offline/core/semantics_tb.py<br>test/semi/transport/one_shot_burst_tb.py<br>test/live/stress/production_face_stress_tb.py |
| 总览#220 | 总览/1-四层整体架构与接口.md | **direct** |  | 各接口 timeout 路径 + connect_timeout 作为子预算有断言（第七轮矩阵 A18 点位，离线全绿） | test/offline/unit/test_connect_retry.py<br>test/offline/unit/test_tunnel_transfer.py<br>test/offline/unit/test_endpoint_budgets.py |
| 总览#229 | 总览/1-四层整体架构与接口.md | **direct** |  | 建连子预算耗尽→timeout/124 与断连→transport/255 均有断言 | test/offline/unit/test_connect_retry.py<br>test/offline/unit/test_middle_reserved_codes.py |
| 总览#230 | 总览/1-四层整体架构与接口.md | **direct** |  | ≤3 次总尝试（恰好三次）、ControlMaster 降级、常驻 shell 重建均有断言 | test/offline/unit/test_connect_retry.py::test_banner_drop_retries_exactly_three_attempts_then_raises<br>test/offline/unit/test_ssh_tunnel_lifecycle.py<br>test/offline/unit/test_persistent_shell_protocol.py |
| 总览#238 | 总览/1-四层整体架构与接口.md | **direct** |  | 本版不引入 request_id：带 request_id 的 operation 在 dataclass 请求模型路径上返回 400 unexpected keyword argument（真机 8127 实测同口径）；离线用例钉住。观察项：pydantic 请求模型未统一 extra=forbi | t<br>e<br>s<br>t<br>/<br>o<br>f<br>f<br>l<br>i<br>n<br>e<br>/<br>u<br>n<br>i<br>t<br>/<br>t<br>e<br>s<br>t<br>_<br>n<br>o<br>r<br>m<br>_<br>g<br>a<br>p<br>_<br>b<br>a<br>t<br>c<br>h<br>2<br>.<br>p<br>y<br>:<br>:<br>T<br> |
| 范围#006 | 总览/add-本版范围与明确不支持.md | **direct** |  | 五接口+query 集合固定有接口面断言；真机四 token 五接口 5/5 | test/offline/unit/test_middle_contracts.py<br>test/offline/unit/test_pyapi_interface_contract.py<br>test/live/transport/cov_remote_real.py |
| 范围#032 | 总览/add-本版范围与明确不支持.md | **na** |  | 文档关系/索引声明（哪份文档管什么），无独立可测行为 |  |
| 配置#005 | 中层/add-中层配置文档.md | **na** |  | 文档定位声明（本文是多用户与注册的字段补充），无可测行为 |  |
| 配置#006 | 中层/add-中层配置文档.md | **na** |  | owner 归属声明（哪些内容只在本文定义），无可测行为 |  |
| 配置#012 | 中层/add-中层配置文档.md | **na** |  | 文档写法约定（‘默认 X 可省略’），落实到具体字段行（OPS）去测 |  |
| 配置#027 | 中层/add-中层配置文档.md | **direct** |  | 五 role 公共字段/默认值/逐字段回退有 schema 与回退用例 | test/offline/unit/test_validation_roles.py<br>test/offline/unit/test_register_flow.py |
| 配置#053 | 中层/add-中层配置文档.md | **direct** |  | 逐字段回退（role→全局默认；null/空串=未提供）有断言 | test/offline/unit/test_register_flow.py<br>test/offline/unit/test_validation_roles.py |
| 配置#056 | 中层/add-中层配置文档.md | **direct** |  | 固定子结构 registry/config/temp/log/artifact 与实际路径函数均有断言（子进程级） | test/offline/unit/test_workdir_contract.py<br>test/offline/unit/test_common_config.py |
| 配置#063 | 中层/add-中层配置文档.md | **direct** |  | root 属配置、探测期写回绝对路径：契约用例 + 真机注册表实测（提交态 root.default=null） | test/offline/unit/test_spec_contracts.py<br>test/offline/unit/test_register_flow.py<br>test/artifacts/env/log-vblog/registry.json |
| 配置#065 | 中层/add-中层配置文档.md | **direct** |  | remote role 目标与凭据条件必填（含 ssh.default 回退、key 仅文件名）有断言 | test/offline/unit/test_register_flow.py<br>test/offline/unit/test_registration_server_edges.py |
| 配置#068 | 中层/add-中层配置文档.md | **direct** |  | 格式/../斜杠/保留设备名（CON、con.txt、NUL）/结尾点均有断言；Windows 大小写查重在注册服务用例 | test/offline/unit/test_validation_roles.py::test_user_names<br>test/offline/unit/test_registration_server_edges.py |
| 配置#070 | 中层/add-中层配置文档.md | **direct** |  | local role 带连接字段（model 级）与 key_dir/key（HTTP 级 400）均拒绝 | test/offline/unit/test_commit_shape.py::test_local_role_with_connection_field_is_model_error<br>test/offline/unit/test_registration_server_edges.py |
| 配置#071 | 中层/add-中层配置文档.md | **direct** |  | 指纹查重→enhanced_token（holder/admin 两者）、key 含目录成分 400、凭据不同不复用，均有断言 | test/offline/unit/test_registration_server_edges.py::test_credential_reuse_requires_enhanced_token<br>test/offline/unit/test_registration_server_edges.py::test_apply_rejects_unknown_enhanced_token<br>test/offline/unit/te |
| 配置#072 | 中层/add-中层配置文档.md | **direct** |  | 良好形态（:11、localhost:10.0、unix/:0）与注入形态（空白/引号/;/$( ) 等）逐条断言 | test/offline/unit/test_validation_roles.py::test_gui_displays |
| 配置#073 | 中层/add-中层配置文档.md | **direct** |  | 组名/形状/标量/NUL/固定字段重名 + 16 KiB 边界（第八轮补）均有断言；未知字段/未知 role 名拒绝由 test_norm_gap_round8 钉住（未知 role 拒绝 + role 级未知名=用户组语义） | test/offline/unit/test_validation_roles.py::test_role_user_groups_are_structural_only<br>test/offline/unit/test_validation_roles.py::test_role_user_groups_reject_bad_shapes<br>test/offline/unit/test_validation_roles.py:: |
| 配置#075 | 中层/add-中层配置文档.md | **direct** |  | UTF-8/跨进程读改写不丢更新/tmp+原子替换有断言；0600 权限断言第八轮补（POSIX 用例，Windows skip；Linux 客户端矩阵执行） | test/offline/core/semantics_tb.py<br>test/offline/unit/test_registry_more.py<br>test/offline/unit/test_registry_more.py::test_registry_file_mode_is_0600 |
| 配置#103 | 中层/add-中层配置文档.md | **na** |  | 指向另一文档（探测/写回时机）的索引声明，无可测行为 |  |
| 配置#107 | 中层/add-中层配置文档.md | **direct** |  | daemon_port 按 daemon 主机作用域、local_port 本机级、user/token 全局，均有冲突用例 | test/offline/unit/test_reservation.py |
| 配置#108 | 中层/add-中层配置文档.md | **partial** |  | 缺省→同值生成并同步写入有断言；**显式双值不等**时实测被静默归一化（local_port 胜出、daemon_port 请求被丢弃，见 P-079），flow.py:705-715 的拒绝守卫在正常流程不可达 ｜ **缺口**: P-079 定口径后补测：钉住用例 TestLocalJointPortNotCoerced 修复前红；若选‘local_port 优先’需把用例改成断言归一化行为 | test/offline/unit/test_register_flow.py::test_validate_preallocates_joint_port_for_local_mode<br>test/offline/unit/test_norm_gap_round8.py::TestLocalJointPortNotCoerced |
| 配置#111 | 中层/add-中层配置文档.md | **na** |  | 实现自由度声明（进程内协调、不设跨进程租约），无独立可测行为 |  |
| 配置#112 | 中层/add-中层配置文档.md | **direct** |  | 分配算法自由度但‘候选唯一且空闲’合同有断言（含保留集/本机占用） | test/offline/unit/test_probe.py<br>test/offline/unit/test_reservation.py |
| 配置#118 | 中层/add-中层配置文档.md | **direct** |  | Server-A/server-a. 同 endpoint、大小写/结尾点规范化、不做 DNS，逐条向量断言 | test/offline/unit/test_spec_contracts.py::test_vectors_from_spec<br>test/offline/unit/test_spec_contracts.py::test_canonical_host_rules |
| 配置#120 | 中层/add-中层配置文档.md | **direct** |  | ‘向量必须逐条可测’由 test_spec_contracts 的向量表逐条 assertEquals 落实 | test/offline/unit/test_spec_contracts.py |
| 配置#130 | 中层/add-中层配置文档.md | **direct** |  | SSH 22 端口校验（目标/jump）/非 22 拒绝、proxy 仅 socks5://host:port 且有非法拒绝，均有断言 | test/offline/unit/test_probe.py::test_ssh_port_rule_enforces_22<br>test/offline/unit/test_register_flow.py<br>test/offline/unit/test_paramiko.py |
| 路由#005 | 中层/3-路由设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 路由#008 | 中层/3-路由设计.md | **direct** |  | 第二步限流检查后‘排队或直接投递’有闸门/预算断言 | test/offline/core/semantics_tb.py<br>test/offline/unit/test_endpoint_budgets.py |
| 路由#009 | 中层/3-路由设计.md | **direct** |  | 容量拒绝时必须指明具体预算，有断言（三预算分别覆盖） | test/offline/core/fault_injection_tb.py<br>test/offline/unit/test_endpoint_budgets.py |
| 路由#013 | 中层/3-路由设计.md | **na** |  | 流程图节点（与 #008 同义），由 #008 承担 |  |
| 路由#014 | 中层/3-路由设计.md | **direct** |  | ‘容不下 → 容量拒绝并指明哪个参数’有断言（与 #009 同一用例族） | test/offline/core/fault_injection_tb.py |
| 路由#015 | 中层/3-路由设计.md | **direct** |  | ‘容下 → 排队或直接投递’由串行闸门用例覆盖 | test/offline/core/semantics_tb.py |
| 路由#018 | 中层/3-路由设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 路由#024 | 中层/3-路由设计.md | **indirect** |  | role 跨主机不被拒绝已有真机证据（daemon/gui 在 wsl-gent、command/file 在 w1）；**gui 与 daemon 异机**无环境（第二台真 GUI 主机）——桥层按配置投送，不假设同机 ｜ **缺口**: 环境限制项：如需闭合，需第二台带 X/Virtuoso 的主机；当前以‘跨主机投送不被拒绝’的同等证据承担 | test/live/flows/role_split_tb.py |
| 路由#032 | 中层/3-路由设计.md | **direct** |  | 五 role 可跨主机（含回退）注册与投送：真机 S2 5/5 + 离线解析用例 | test/live/flows/role_split_tb.py<br>test/offline/unit/test_validation_roles.py |
| 路由#033 | 中层/3-路由设计.md | **indirect** |  | 一 token→一 daemon 的映射与多 token 隔离有断言；‘第二 CIW=配置错误’属环境约定（无负向用例） | test/offline/unit/test_middle_contracts.py<br>test/offline/scenario/test_multi_user_isolation.py<br>test/live/transport/cov_remote_real.py |
| 路由#036 | 中层/3-路由设计.md | **na** |  | 唯一口径/文档纪律声明，无可测行为 |  |
| 路由#037 | 中层/3-路由设计.md | **direct** |  | 逐 role mode 解析有离线断言；同 token 混合模式（daemon=local + command=remote）原样保留由 test_norm_gap_round8 钉住（第八轮补） | test/offline/unit/test_validation_roles.py<br>test/offline/unit/test_register_flow.py<br>test/offline/unit/test_norm_gap_round8.py::TestMixedModeSingleToken |
| 路由#046 | 中层/3-路由设计.md | **direct** |  | gui/spectre 一次性命令（不建常驻会话）+ 占 channel 预算，有离线与半真机断言 | test/offline/unit/test_tunnel_transfer.py<br>test/semi/transport/one_shot_burst_tb.py |
| 路由#052 | 中层/3-路由设计.md | **direct** |  | endpoint 身份五元组 + 凭据一致性才复用，向量与隔离用例均有断言 | test/offline/unit/test_credential_routing.py<br>test/offline/unit/test_spec_contracts.py |
| 路由#053 | 中层/3-路由设计.md | **na** |  | ‘复用原则’小节标题，内容在 #052/#060 等条目 |  |
| 路由#059 | 中层/3-路由设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 路由#060 | 中层/3-路由设计.md | **direct** |  | 线程预算/最大通道数每 token 一份、单点上限取最小值，均有断言 | test/offline/unit/test_endpoint_budgets.py |
| 路由#067 | 中层/3-路由设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 路由#068 | 中层/3-路由设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 路由#070 | 中层/3-路由设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 并发#005 | 中层/2-并发设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 并发#006 | 中层/2-并发设计.md | **direct** |  | 串行 Skill/串行命令/并行三类形态有闸门与 one-shot 断言 | test/offline/core/semantics_tb.py<br>test/semi/transport/one_shot_burst_tb.py |
| 并发#012 | 中层/2-并发设计.md | **direct** |  | 投递前排队、per-token 闸门、队列不跨 token 有断言 | test/offline/core/semantics_tb.py |
| 并发#013 | 中层/2-并发设计.md | **direct** |  | 排队超时=未投递（可安全重试）/已投递超时=结果未知，两条语义均有断言 | test/offline/core/semantics_tb.py<br>test/offline/unit/test_persistent_shell_protocol.py |
| 并发#020 | 中层/2-并发设计.md | **direct** |  | 三预算独立、超限不排队、指明具体预算，均有断言 | test/offline/unit/test_endpoint_budgets.py<br>test/offline/core/fault_injection_tb.py |
| 并发#022 | 中层/2-并发设计.md | **direct** |  | 同 endpoint 多 role 共享计数、上限取最小值、daemon Skill 隧道计入，均有断言 | test/offline/unit/test_endpoint_budgets.py |
| 并发#034 | 中层/2-并发设计.md | **direct** |  | ≤3 次总尝试、ControlMaster 降级、共享剩余预算，均有断言 | test/offline/unit/test_connect_retry.py<br>test/offline/unit/test_ssh_tunnel_lifecycle.py |
| 并发#038 | 中层/2-并发设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 并发#040 | 中层/2-并发设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 并发#042 | 中层/2-并发设计.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 日志#009 | 底层/6-日志返回设计标准.md | **direct** |  | IL/daemon 源码级断言不得出现 VB-BEGIN/END 等注入 marker（日志只读不改文件） | test/offline/unit/test_log_no_fetch.py<br>test/offline/unit/test_daemon_log_contract.py::test_daemon_never_writes_markers_into_cds_log |
| 日志#035 | 底层/6-日志返回设计标准.md | **direct** |  | [start,end) 精确区间与轮转后从 0 读，均有断言 | test/offline/unit/test_daemon_log_contract.py::test_reads_exact_interval<br>test/offline/unit/test_daemon_log_contract.py::test_rotated_file_reads_from_zero |
| 日志#045 | 底层/6-日志返回设计标准.md | **direct** |  | 默认 64KB 在配置默认值测试；字节预算是 diff/truncate 用例的边界 | test/offline/unit/test_common_config.py<br>test/offline/unit/test_daemon_log_utf8_budget.py |
| 日志#055 | 底层/6-日志返回设计标准.md | **direct** |  | ‘只取靠前字节前缀、不补发、切到半个 UTF-8 字符要丢弃’，逐 max_bytes 扫描断言 | test/offline/unit/test_daemon_log_utf8_budget.py |
| 日志#066 | 底层/6-日志返回设计标准.md | **na** |  | 示例 payload 形态，由 #070/#077/#082 的帧/日志断言覆盖 |  |
| 日志#070 | 底层/6-日志返回设计标准.md | **direct** |  | 只解析 JSON payload、非法帧/非法字段按协议错误处理，均有断言 | test/offline/unit/test_daemon_runtime_contracts.py<br>test/offline/integration/test_daemon_handler.py |
| 日志#077 | 底层/6-日志返回设计标准.md | **direct** |  | 帧顺序在 socket 协议层有断言；‘IL 合并为一次 ipcWriteProcess + meta 追加同一缓冲’由 test_norm_gap_round8 钉住（第八轮补） | test/offline/core/daemon_log_protocol_tb.py<br>test/offline/unit/test_norm_gap_round8.py::TestIlSingleIpcWrite |
| 日志#082 | 底层/6-日志返回设计标准.md | **direct** |  | CDS.log 不可读 → log="" + warnings 固定文案、结果照常返回，有断言 | test/offline/integration/test_daemon_handler.py::test_unavailable_cds_log_uses_frozen_warning_text |
| 日志#091 | 底层/6-日志返回设计标准.md | **direct** |  | 非法 log_level/log_max_bytes 直接 NAK（不夹紧）、不可读固定 warnings、截断不出半个 UTF-8 字符，均有断言 | test/offline/integration/test_daemon_handler.py<br>test/offline/unit/test_daemon_log_utf8_budget.py |
| 顶层#005 | 顶层/1-顶层.md | **na** |  | 定位声明（顶层只做入口与调度），由 #009/#028 的可测条款承担 |  |
| 顶层#009 | 顶层/1-顶层.md | **direct** |  | 顶层不引 transport（import 契约）+ 预算记账在中层（预算用例），两侧合起来钉死职责边界 | test/offline/unit/test_upper_layer_import_contract.py<br>test/offline/unit/test_endpoint_budgets.py |
| 顶层#018 | 顶层/1-顶层.md | **direct** |  | 同操作名重复登记=启动错误有断言；单操作包一行成立由 dispatch 用例覆盖 | test/offline/unit/test_top_layer_dispatch.py::test_duplicate_operation_is_startup_error<br>test/offline/core/api_server_tb.py |
| 顶层#028 | 顶层/1-顶层.md | **direct** |  | 处理/调度模块的允许/禁用 import 清单逐条断言（transport/socket/subprocess/paramiko 禁用） | test/offline/unit/test_upper_layer_import_contract.py |
| 顶层#042 | 顶层/1-顶层.md | **direct** |  | 未预期异常结构化 500（不终止服务）+ 线程池/单请求失败隔离用例 | test/offline/unit/test_api_server_main.py::test_unserializable_result_is_structured_500<br>test/offline/unit/test_top_layer_pool.py |
| 顶层#050 | 顶层/1-顶层.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 顶层#051 | 顶层/1-顶层.md | **na** |  | 索引/关联声明，无独立可测行为 |  |
| 注册#005 | 其他/1-多用户与注册.md | **na** |  | 索引/定位/关联声明，无独立可测行为 |  |
| 注册#006 | 其他/1-多用户与注册.md | **direct** |  | 运行期不自动读文件 + 显式 reload/restart 后重新导入，均有端到端断言 | test/offline/unit/test_registry_decoupling.py<br>test/offline/integration/test_supervisor_process.py::test_status_reload_restart |
| 注册#007 | 其他/1-多用户与注册.md | **direct** |  | 六步结束后隧道/SSH/socket 残留盘点（真机六步 TB 末段 + 半真机 1-4 步） | test/live/registration/registration_http_six_step_tb.py<br>test/semi/registration/cov_registration_real.py |
| 注册#011 | 其他/1-多用户与注册.md | **indirect** |  | 部署/根路径按 userid 组织（注册表实际条目可见）；‘token 不得出现在用户可读路径’无单独负向断言 ｜ **缺口**: 可选：断言注册部署产物路径不含 token 值（六步 TB 内一行） | test/semi/registration/cov_registration_real.py<br>test/live/registration/registration_http_six_step_tb.py |
| 注册#015 | 其他/1-多用户与注册.md | **direct** |  | remote role 目标与凭据条件必填（含 ssh.default 回退）有断言 | test/offline/unit/test_register_flow.py<br>test/offline/unit/test_registration_server_edges.py |
| 注册#018 | 其他/1-多用户与注册.md | **direct** |  | local role 的 host/user 拒绝有断言；未知 role 名拒绝 + 未知顶层字段拒绝由 test_norm_gap_round8 钉住（第八轮补） | test/offline/unit/test_commit_shape.py::test_local_role_with_connection_field_is_model_error<br>test/offline/unit/test_validation_roles.py::test_role_user_groups_are_structural_only<br>test/offline/unit/test_norm_gap_rou |
| 注册#019 | 其他/1-多用户与注册.md | **direct** |  | 六步顺序、前五步 registry 零写入、第六步唯一写盘，均有断言（离线+半真机+真机） | test/offline/unit/test_registration_server.py<br>test/semi/registration/cov_registration_real.py<br>test/live/registration/registration_http_six_step_tb.py |
| 注册#036 | 其他/1-多用户与注册.md | **direct** |  | 步级 deadline/单窗口预算由 test_register_flow + TestStepBudgetDoesNotReset（remaining 不超步时长）钉住（第八轮补） | test/offline/unit/test_register_flow.py<br>test/offline/unit/test_norm_gap_round8.py::TestStepBudgetDoesNotReset |
| 注册#038 | 其他/1-多用户与注册.md | **direct** |  | 失败不释放、原样重试、修正需 cancel、重试覆盖式，均有断言 | test/offline/unit/test_register_flow.py<br>test/offline/unit/test_reservation.py<br>test/live/registration/registration_http_six_step_tb.py |
| 注册#039 | 其他/1-多用户与注册.md | **direct** |  | cancel 合法域/幂等/token 失效/GET 无会话，均有断言 | test/offline/unit/test_reservation.py<br>test/offline/unit/test_registration_server.py<br>test/live/registration/registration_http_six_step_tb.py |
| 注册#040 | 其他/1-多用户与注册.md | **direct** |  | 第五步通过不写盘、第六步显式触发才写 registry，半真机/真机均有零落盘断言 | test/semi/registration/cov_registration_real.py<br>test/live/registration/registration_http_six_step_tb.py |
| 注册#051 | 其他/1-多用户与注册.md | **direct** |  | 显式值校验失败=ERROR、缺省探测写回、探测不到/多进程（detect=None）留 null 仅 WARNING，均有离线断言 + 半真机 display 探针 | test/offline/unit/test_register_flow.py::test_gui_display_probe_explicit_and_detected<br>test/semi/probes/gui_display_probe.py |
| 控制面#007 | 顶层/add-控制面与业务面.md | **direct** |  | 控制端口（注册/管理）与业务端口（调度）分进程分端点，各自有 HTTP 级用例 | test/offline/unit/test_registration_server.py<br>test/offline/unit/test_api_server_main.py |
| 控制面#008 | 顶层/add-控制面与业务面.md | **direct** |  | 业务端口高并发调度（线程池/429 准入/operation 分发）有离线断言 + 真机常驻业务面 | test/offline/unit/test_api_server_main.py<br>test/offline/core/api_server_tb.py |
| 控制面#011 | 顶层/add-控制面与业务面.md | **direct** |  | 默认绑定 127.0.0.1 由 test_norm_gap_round8::TestRegistrationBindsLoopback 钉住（第八轮补） | src/register/server.py:991<br>test/offline/unit/test_registration_server.py<br>test/offline/unit/test_norm_gap_round8.py::TestRegistrationBindsLoopback |
| 控制面#028 | 顶层/add-控制面与业务面.md | **na** |  | 小节标题（语义 owner 指向另一文档） |  |
| 控制面#043 | 顶层/add-控制面与业务面.md | **direct** |  | 乱序 action → 4xx step order violation 且会话状态不变，离线/真机均有断言 | test/offline/unit/test_registration_server.py<br>test/live/registration/registration_http_six_step_tb.py |
| 控制面#044 | 顶层/add-控制面与业务面.md | **direct** |  | 同一步原样重试 vs 修正需 cancel 重 apply，均有断言 | test/offline/unit/test_register_flow.py<br>test/live/registration/registration_http_six_step_tb.py |
| 控制面#045 | 顶层/add-控制面与业务面.md | **direct** |  | apply 返回 token、非 apply action 必须携带匹配 token、缺失/不一致 4xx invalid token，均有断言 | test/offline/unit/test_registration_server.py<br>test/offline/unit/test_registration_server_edges.py |
| 控制面#066 | 顶层/add-控制面与业务面.md | **direct** |  | status/restart 生命周期（重启替换子进程）+ 排空中 503 + 准入上限 429+Retry-After，均有断言 | test/offline/integration/test_supervisor_process.py::test_status_reload_restart<br>test/offline/unit/test_top_layer_pool.py |
| 控制面#069 | 顶层/add-控制面与业务面.md | **direct** |  | update/delete 收归管理员、个人 token 不能自助修改、update 体含 token → 拒绝，均有断言 | test/offline/unit/test_registration_server.py<br>test/offline/unit/test_registration_server_edges.py |
| 控制面#071 | 顶层/add-控制面与业务面.md | **direct** |  | 请求体超限 16MiB → 413（且不读体/不中断连接），有断言 | test/offline/unit/test_registration_server_edges.py |
| 控制面#072 | 顶层/add-控制面与业务面.md | **direct** |  | 无效/缺失 token → 4xx 不记录；记录前剥离凭据（masked）；写失败 500 不留 tmp，均有断言 | test/offline/unit/test_registration_server.py::test_bug_report_requires_valid_personal_token<br>test/offline/unit/test_registration_server.py::test_bug_report_records_entry_with_user_and_masked_token<br>test/offline/unit |
| 控制面#079 | 顶层/add-控制面与业务面.md | **na** |  | 索引/定位/关联声明，无独立可测行为 |  |
| 控制面#080 | 顶层/add-控制面与业务面.md | **direct** |  | GET/PUT config、PUT 只覆盖出现键（未知键透传）、原子写回与失败清理，均有断言 | test/offline/unit/test_registration_server.py::test_config_unknown_top_level_key_passthrough<br>test/offline/unit/test_registration_server_edges.py<br>test/offline/unit/test_api_server_main.py |
| 控制面#081 | 顶层/add-控制面与业务面.md | **direct** |  | 进程级只读快照 + 启动/reload/restart 各导入一次，有断言 | test/offline/unit/test_common_config.py<br>test/offline/integration/test_supervisor_process.py::test_status_reload_restart |
| 控制面#083 | 顶层/add-控制面与业务面.md | **direct** |  | business_thread_pool_size 为可变准入上限（reload 后生效 + 超限 429+Retry-After）；其余顶层键原样透传不解读，均有断言 | test/offline/unit/test_api_server_main.py<br>test/offline/unit/test_top_layer_pool.py<br>test/offline/core/api_server_tb.py |
| 控制面#085 | 顶层/add-控制面与业务面.md | **direct** |  | runtime.thread_pool_size（每 token）与全局线程池上限各自用例，二者独立不互替 | test/offline/unit/test_endpoint_budgets.py<br>test/offline/unit/test_api_server_main.py |
| 控制面#088 | 顶层/add-控制面与业务面.md | **na** |  | 索引/定位/关联声明，无独立可测行为 |  |
| 控制面#089 | 顶层/add-控制面与业务面.md | **na** |  | 索引/定位/关联声明，无独立可测行为 |  |
| 上层#005 | 上层/1-上层.md | **na** |  | 索引/定位/关联声明，无独立可测行为 |  |
| 上层#031 | 上层/1-上层.md | **direct** |  | 每步 {step, ok, detail} 记录 + 任一步失败即停（后续不执行），包级用例有断言 | test/offline/unit/test_maestro_package_flow.py<br>test/offline/unit/test_veriloga_contracts.py |
| 上层#032 | 上层/1-上层.md | **direct** |  | 失败保留 steps 痕迹、不以成功形态返回（ok=false + error），有断言；P-027 类假成功已被禁止 | test/offline/unit/test_veriloga_contracts.py<br>test/offline/unit/test_maestro_package_flow.py |
| 上层#042 | 上层/1-上层.md | **direct** |  | 领域校验/执行失败一律 Result(ok=false)（多条 assertFalse(result.ok)），不抛异常 | test/offline/unit/test_veriloga_contracts.py<br>test/offline/unit/test_maestro_package_flow.py |
| 上层#043 | 上层/1-上层.md | **direct** |  | checksum 不一致不忽略（结构化失败）+ 传输层重试透明、业务重试由包决定，均有断言 | test/offline/unit/test_middle_contracts.py<br>test/offline/unit/test_pyapi_packages.py |
| 上层#045 | 上层/1-上层.md | **direct** |  | 登记单元=业务操作级 tuple（含重复登记启动错误），有断言 | test/offline/unit/test_top_layer_dispatch.py<br>test/offline/unit/test_pyapi_packages.py |
| 上层#063 | 上层/1-上层.md | **na** |  | 索引/定位/关联声明，无独立可测行为 |  |
| 上层#066 | 上层/1-上层.md | **na** |  | 索引/定位/关联声明，无独立可测行为 |  |
| cellview#006 | 上层/5-cellview.md | **direct** |  | 三层对象 list/create/copy/delete/rename + get/bind 仅 lib 层：离线契约 + 真机 E2E | test/offline/unit/test_cellview_contracts.py<br>test/live/packages/cellview_e2e_tests.py |
| cellview#038 | 上层/5-cellview.md | **na** |  | spec 明示‘先不实现’的预留项（harvest）；按明确不做口径登记，不建 TB |  |
| gui#006 | 上层/10-gui.md | **direct** |  | 窗口恢复面向 X11 顶层窗口 + 显式 window_id：离线解析/动作用例 + 真 display 探针 | test/offline/unit/test_gui_package.py<br>test/semi/probes/gui_display_probe.py |
| gui#016 | 上层/10-gui.md | **direct** |  | list_windows 走 X11 顶层窗口清单（含 EWMH），无 SKILL 会话内清单，有断言 | test/offline/unit/test_gui_package.py::test_list_windows_ok<br>test/offline/unit/test_gui_package.py::test_list_windows_ewmh_client_list |
| gui#019 | 上层/10-gui.md | **direct** |  | 动作必须显式 window_id（无隐式当前窗口）+ 动作白名单，有断言 | test/offline/unit/test_gui_package.py::test_target_validation<br>test/offline/unit/test_gui_package.py::test_whitelist |
| gui#022 | 上层/10-gui.md | **direct** |  | auto_dismiss 只收 dialog 候选 + 顺序 + 逐窗口验证（send_and_verify）；真机 P-075 回归探针覆盖 | test/offline/unit/test_gui_package.py::test_dialog_candidates_only_and_order<br>test/offline/unit/test_gui_package.py::test_send_and_verify<br>test/semi/probes/gds_then_skill_probe.py |
| schematic#006 | 上层/2-schematic.md | **direct** |  | instance/wire/label/pin 的 place/delete/rename/set 写原子 + net 派生：离线契约 + 真机读回用例 | test/offline/unit/test_schematic_contracts.py<br>test/live/packages/schematic_e2e_tests.py |
| schematic#014 | 上层/2-schematic.md | **direct** |  | object_filter 逐条目 all/none/names/region 与不写默认 all，有断言 | test/offline/unit/test_schematic_contracts.py::test_instance_filter_all_none_names_region<br>test/offline/unit/test_schematic_contracts.py::test_shape_filter_none_dict_and_invalid |
| schematic#015 | 上层/2-schematic.md | **direct** |  | instance 过滤四形态有离线断言 + 真机 read 过滤用例 | test/offline/unit/test_schematic_contracts.py::test_instance_filter_all_none_names_region<br>test/live/packages/schematic_e2e_tests.py |
| schematic#016 | 上层/2-schematic.md | **direct** |  | wire/label/pin/note 共用的 shape 过滤 none/region 有断言（names 非法有负控制） | test/offline/unit/test_schematic_contracts.py::test_shape_filter_none_dict_and_invalid |
| schematic#017 | 上层/2-schematic.md | **direct** |  | focus=connectivity 时 object_filter 必须被忽略，已由第八轮补测直接断言（connectivity 场景下 SKILL 文本不含 sentinel 过滤名；positions 场景下必须含）。 | test/offline/unit/test_norm_gap_batch2.py::TestSchematicConnectivityIgnoresFilter |
| schematic#018 | 上层/2-schematic.md | **direct** |  | screenshot 参数面真机 5/5：默认 lib/cell/view、显式 window_id（坏 id 负向）、region 正/反序负向、toplevel/central_widget 取假值均有断言；**口径偏差**：schematic region 当前仅收四元组（与 spec 两点写 | test/live/packages/screenshot_params_e2e_tests.py<br>test/artifacts/evidence/round8/screenshot-params/schematic.json |
| schematic#019 | 上层/2-schematic.md | **direct** |  | 对外只有通用 write（一次一组原子、统一 check/save）由契约与真机套件钉住 | test/offline/unit/test_schematic_contracts.py<br>test/live/packages/schematic_e2e_tests.py |
| schematic#024 | 上层/2-schematic.md | **direct** |  | commands 每项 {op,...}、按序执行并保留每步痕迹，有断言 | test/offline/unit/test_schematic_contracts.py |
| schematic#025 | 上层/2-schematic.md | **direct** |  | 20 个写原子全部有真机读回用例；原子覆盖核账 GAP=0 | test/live/packages/schematic_e2e_tests.py<br>test/artifacts/evidence/atom-coverage-2026-09-28.json |
| schematic#048 | 上层/2-schematic.md | **direct** |  | 单点一律 pos（索引/新建/读回同形）由 P-074 实现 + 真机负控制 + 契约钉住 | test/live/packages/schematic_e2e_tests.py::_case_negative<br>test/offline/unit/test_schematic_contracts.py |
| schematic#049 | 上层/2-schematic.md | **direct** |  | xy/拆字段必须被拒且点名 pos：真机负控制逐形态断言（非裸异常） | test/live/packages/schematic_e2e_tests.py (负控制 349-352)<br>test/offline/unit/test_schematic_contracts.py |
| schematic#050 | 上层/2-schematic.md | **partial** |  | points=[pos,…] 两点/多点有断言；**region 的对角两点在 read 过滤与 screenshot 仍失败（P-082）**，实现只收四元组，与该条‘不再用四元组’冲突 ｜ **缺口**: P-082 修复后补两点正例（read 过滤 + screenshot）并复跑 | test/offline/unit/test_schematic_contracts.py |
| schematic#058 | 上层/2-schematic.md | **direct** |  | 不做兼容层：xy/拆字段直接非法且点名 pos，有真机与离线负控制 | test/live/packages/schematic_e2e_tests.py (负控制)<br>test/offline/unit/test_schematic_contracts.py |
| schematic#059 | 上层/2-schematic.md | **direct** |  | instance 唯一 name 索引、wire 按 points、label/note/pin 按 pos（含消歧义）由契约与真机用例覆盖 | test/offline/unit/test_schematic_contracts.py<br>test/live/packages/schematic_e2e_tests.py |
| schematic#066 | 上层/2-schematic.md | **direct** |  | check_and_save 显式补校验保存 + view 必须显式默认 schematic，有断言 | test/offline/unit/test_schematic_contracts.py<br>test/live/packages/schematic_e2e_tests.py |
| symbol#004 | 上层/3-symbol.md | **na** |  | Supersedes 注记（文档版本说明） |  |
| symbol#010 | 上层/3-symbol.md | **direct** |  | generate 的临时 view/校验/备份/回滚全链：离线生成式 + 真机句柄探针 | test/offline/unit/test_symbol_generate.py<br>test/semi/probes/symbol_regen_handle_probe.py |
| symbol#023 | 上层/3-symbol.md | **direct** |  | read 默认 view=symbol/view_type=schematicSymbol 且返回通用 shapes，有断言；行为面承接：symbol_e2e_tests.py | test/offline/unit/test_symbol_contracts.py<br>test/live/packages/symbol_e2e_tests.py |
| symbol#026 | 上层/3-symbol.md | **direct** |  | view_type 默认 + PNG 落盘，有真机用例与探针 | test/live/packages/symbol_e2e_tests.py::_case_screenshot<br>test/semi/probes/symbol_screenshot_probe.py |
| symbol#038 | 上层/3-symbol.md | **direct** |  | write 先显式探测 view 存在再 append 编辑，有生成式断言 | test/offline/unit/test_symbol_contracts.py |
| symbol#041 | 上层/3-symbol.md | **direct** |  | commands 每项 {op,...} 按序执行并保留每步痕迹，有断言 | test/offline/unit/test_symbol_contracts.py |
| symbol#053 | 上层/3-symbol.md | **direct** |  | 新建几何原子 layer/purpose 必填、不设默认层：生成式断言（缺 layer 即 ValueError）；2026-09-28 复核补钉：新增 TestSymbolAtomicMatrix::test_new_shape_atoms_require_layer_and_purpose（缺  | test/offline/unit/test_symbol_contracts.py<br>test/offline/unit/test_symbol_contracts.py::TestSymbolAtomicMatrix::test_new_shape_atoms_require_layer_and_purpose |
| symbol#067 | 上层/3-symbol.md | **direct** |  | pin 以 terminal name 为唯一索引（P-073 修复后真机 pin 探针 clean） | test/offline/unit/test_symbol_contracts.py<br>test/semi/probes/schematic_pin_ops_probe.py |
| symbol#075 | 上层/3-symbol.md | **direct** |  | place_pin 内部顺序（terminal→net→term→矩形）由生成式用例钉住 | test/offline/unit/test_symbol_contracts.py |
| symbol#082 | 上层/3-symbol.md | **indirect** |  | 小节标题（真机语义必须遵守）；其语义由 pin 探针 + symbol E2E 的引脚用例承担 | test/semi/probes/schematic_pin_ops_probe.py<br>test/live/packages/symbol_e2e_tests.py |
| symbol#107 | 上层/3-symbol.md | **direct** |  | source/target view 必须不同：离线生成式 + 真机 400 负控制 | test/offline/unit/test_symbol_generate.py<br>test/semi/probes/symbol_http_400_repro.py |
| symbol#113 | 上层/3-symbol.md | **direct** |  | 任一步失败尝试回滚；回滚失败保留 backup view 并返回失败，有断言 | test/offline/unit/test_symbol_generate.py::test_rollback_path_keeps_backup_and_reports_failure |
| symbol#117 | 上层/3-symbol.md | **direct** |  | sort_pins 保留但只接受枚举、不承诺排序效果：参数矩阵用例（含 bogus 拒绝）；行为面承接：symbol_e2e_tests.py | test/offline/unit/test_symbol_generate.py<br>test/live/packages/symbol_e2e_tests.py |
| symbol#118 | 上层/3-symbol.md | **direct** |  | schPinListToSymbolGen 自带 dbSave → 仅用于临时 view：生成式 + 层次句柄探针 | test/offline/unit/test_symbol_generate.py<br>test/semi/probes/symbol_generate_hierarchy_handle_probe.py |
| symbol#121 | 上层/3-symbol.md | **na** |  | 「不在本版」：port_order/term_order 独立原子，明确不做 |  |
| symbol#124 | 上层/3-symbol.md | **na** |  | 「不在本版」：move_* 系列，明确不做 |  |
| symbol#130 | 上层/3-symbol.md | **na** |  | 「不在本版」：circle/arc/donut/path 原子，明确不做 |  |
| layout#004 | 上层/4-layout.md | **na** |  | Supersedes 注记（文档版本说明） |  |
| layout#006 | 上层/4-layout.md | **direct** |  | shape/label/instance/mosaic/via 对称原子：离线契约 + 真机读回；原子核账 GAP=0 | test/offline/unit/test_layout_contracts.py<br>test/live/packages/layout_e2e_tests.py<br>test/artifacts/evidence/atom-coverage-2026-09-28.json |
| layout#011 | 上层/4-layout.md | **direct** |  | viewType 固定 maskLayout、view 默认 layout，由契约与真机用例钉住 | test/offline/unit/test_layout_contracts.py<br>test/live/packages/layout_e2e_tests.py |
| layout#015 | 上层/4-layout.md | **indirect** |  | 运营面原子集合固定、不存在按 selection 的写操作（接口面断言）；无专门负向用例 | test/offline/unit/test_pyapi_interface_contract.py<br>test/live/packages/layout_e2e_tests.py |
| layout#023 | 上层/4-layout.md | **direct** |  | detail=geometry/index：真机 index 只回 type+LPP；非法值拒绝有离线断言 | test/live/packages/layout_e2e_tests.py::_case_read_filters<br>test/offline/unit/test_layout_contracts.py |
| layout#024 | 上层/4-layout.md | **direct** |  | object_filter 逐条目 none/region 等有离线断言 + 真机 region 过滤用例 | test/live/packages/layout_e2e_tests.py::_case_read_filters<br>test/offline/unit/test_layout_contracts.py |
| layout#028 | 上层/4-layout.md | **direct** |  | region_mode intersect/contain 语义差异有真机断言；非法值拒绝有离线断言（region 形状受 P-082 影响） | test/live/packages/layout_e2e_tests.py::_case_read_params (READ-02)<br>test/offline/unit/test_layout_contracts.py |
| layout#029 | 上层/4-layout.md | **direct** |  | depth=0/>0 真机用例（跨层需 region/layers 的校验有离线断言） | test/live/packages/layout_e2e_tests.py::_case_read_params (READ-02)<br>test/offline/unit/test_layout_contracts.py |
| layout#039 | 上层/4-layout.md | **direct** |  | 对外单一通用 write（一组原子 + 统一 dbSave）由契约与真机套件钉住 | test/offline/unit/test_layout_contracts.py<br>test/live/packages/layout_e2e_tests.py |
| layout#040 | 上层/4-layout.md | **direct** |  | 不按单原子多次调用（接口面固定 + 批量 write 用法）有断言 | test/offline/unit/test_pyapi_interface_contract.py<br>test/live/packages/layout_e2e_tests.py |
| layout#045 | 上层/4-layout.md | **direct** |  | commands 每项 {op,...} 按序执行并保留每步痕迹，有断言 | test/offline/unit/test_layout_contracts.py |
| layout#047 | 上层/4-layout.md | **direct** |  | 不得 append 凭空创建 + 非事务（失败带 applied k/n）均有断言 | test/offline/unit/test_layout_contracts.py::test_command_failure_reports_applied_prefix<br>test/offline/unit/test_layout_contracts.py::test_happy_path_reports_applied_count |
| layout#048 | 上层/4-layout.md | **direct** |  | 原子清单全覆盖（含 delete_instance/delete_mosaic/fit_view/zoom 补测）；核账 GAP=0 | test/live/packages/layout_e2e_tests.py<br>test/artifacts/evidence/atom-coverage-2026-09-28.json |
| layout#075 | 上层/4-layout.md | **direct** |  | dbCreateXxx 返回 nil 即业务失败（含真机探针）有断言 | test/offline/unit/test_layout_contracts.py<br>test/semi/probes/layout_p044_second_write_probe.py |
| layout#076 | 上层/4-layout.md | **direct** |  | 默认不做 techfile 预检；strict_lpp=true 拒绝未知 layer，有真机断言 + 类型校验 | test/live/packages/layout_e2e_tests.py (strict_lpp 331-337)<br>test/offline/unit/test_layout_contracts.py |
| layout#079 | 上层/4-layout.md | **indirect** |  | 批量删层 stopLevel 覆盖层次为生成式事实；由 delete 系列真机用例间接承担，无专门跨层负向 | test/live/packages/layout_e2e_tests.py<br>test/semi/probes/layout_p044_second_write_probe.py |
| layout#120 | 上层/4-layout.md | **direct** |  | XSTRM-234 + Translation completed 完成判定、完成前不读目标 view：契约 + 两条真机探针（P-051/P-075 已闭环） | test/offline/unit/test_layout_publish_contracts.py<br>test/semi/probes/gds_publish_path_edges_probe.py<br>test/semi/probes/gds_then_skill_probe.py |
| layout#139 | 上层/4-layout.md | **direct** |  | 禁止无 bbox 的 hiZoomIn/hiZoomOut：fit_view 走 hiZoomIn(win bBox)、zoom 走 hiZoomAbsoluteScale，且不出现裸 hiZoomIn/hiZoomOut，已断言。；行为面承接：layout_e2e_tests.py | test/offline/unit/test_norm_gap_batch2.py::TestLayoutZoomNeverBboxless<br>test/live/packages/layout_e2e_tests.py |
| layout#158 | 上层/4-layout.md | **na** |  | 「不在本版」：路由抽象/clear_routing，明确不做 |  |
| layout#179 | 上层/4-layout.md | **direct** |  | 专属分类 TB 4/4：正常 rect 读回 ✓、零面积几何 → 可归因失败（`bbox requires pos0 < pos1`）✓、非法 LPP → SKILL 硬错误 + 非事务提示 ✓；**口径差异**：实现把几何非法提前到包层预校验，spec 记的 `dbCreateXxx` nil+W | test/live/packages/layout_geometry_classification_e2e_tests.py<br>test/artifacts/evidence/round8/layout-geometry-classification.json<br>test/live/packages/layout_e2e_tests.py (strict_lpp) |
| layout#180 | 上层/4-layout.md | **direct** |  | pos 写 point（7:8）、bBox/points 写 list —— 生成式文本断言 | test/offline/unit/test_layout_contracts.py |
| layout#181 | 上层/4-layout.md | **direct** |  | dbSave 后才 dbClose（未保存不落盘）由契约 + P-044 探针覆盖 | test/offline/unit/test_layout_contracts.py<br>test/semi/probes/layout_p044_second_write_probe.py |
| layout#184 | 上层/4-layout.md | **direct** |  | 区域/层级查询显式给 level（dbShapeQuery … 0 <level>）由生成式与真机用例钉住 | test/offline/unit/test_layout_contracts.py<br>test/live/packages/layout_e2e_tests.py |
| layout#185 | 上层/4-layout.md | **indirect** |  | via 生成图形默认不含在查询结果为真机事实；由 via 原子用例间接体现，无专门断言；行为面承接：layout_geometry_classification_e2e_tests.py | test/offline/unit/test_layout_contracts.py<br>test/live/packages/layout_geometry_classification_e2e_tests.py |
| layout#189 | 上层/4-layout.md | **direct** |  | via 按 pos+orient 索引（viaDef/name 不可读）由 via 原子生成式断言钉住；行为面承接：layout_geometry_classification_e2e_tests.py | test/offline/unit/test_layout_contracts.py<br>test/live/packages/layout_geometry_classification_e2e_tests.py |
| layout#196 | 上层/4-layout.md | **indirect** |  | ‘不能拿 lpp 列表判断接受性’是经验注记；可测含义（strict_lpp 用 techGetLayerNum 而非列表）由 strict_lpp 用例承担 | test/live/packages/layout_e2e_tests.py (strict_lpp)<br>test/offline/unit/test_layout_contracts.py |
| layout#199 | 上层/4-layout.md | **na** |  | 环境事实（会话 run 目录 cds.lib 是权威解析入口），由环境 Runbook 承担 |  |
| layout#202 | 上层/4-layout.md | **direct** |  | GDS 导出走批处理路径、不再触发窗体模态框：P-075 修复后探针 green（0.3s 返回） | test/semi/probes/gds_then_skill_probe.py<br>test/offline/unit/test_layout_publish_contracts.py |
| maestro#004 | 上层/6-maestro.md | **na** |  | Supersedes 注记（文档版本说明） |  |
| maestro#030 | 上层/6-maestro.md | **direct** |  | write 原子=op+索引、整批后台会话顺序执行、末尾统一保存：契约 + 真机包探针 | test/offline/unit/test_maestro_command_exprs.py<br>test/offline/unit/test_maestro_package_flow.py<br>test/semi/probes/maestro_pkg_probe.py |
| maestro#113 | 上层/6-maestro.md | **na** |  | 待定项①：会话级原子索引口径。spec 自述待定/待验证（非冻结要求）；已在 round8 报告‘明缺口’登记为待设计定稿 |  |
| maestro#115 | 上层/6-maestro.md | **na** |  | 待定项③：analyses/outputs 枚举函数。spec 自述待定/待验证（非冻结要求）；已在 round8 报告‘明缺口’登记为待设计定稿 |  |
| maestro#118 | 上层/6-maestro.md | **na** |  | 待定项⑥：各原子参数与默认值逐项定稿。spec 自述待定/待验证（非冻结要求）；已在 round8 报告‘明缺口’登记为待设计定稿 |  |
| maestro#119 | 上层/6-maestro.md | **na** |  | ‘待真机验证’小节标题（其条目按相邻编号分别裁定） |  |
| spectre#033 | 上层/7-spectre.md | **direct** |  | Request 必带 token/可选 timeout；结构错误抛 ValueError/TypeError，有断言 | test/offline/unit/test_spectre_contracts.py<br>test/offline/unit/test_pyapi_interface_contract.py |
| spectre#036 | 上层/7-spectre.md | **direct** |  | 业务失败 ok=false+error、结构错误才抛，均有断言（含 status 语义用例） | test/offline/unit/test_spectre_contracts.py |
| spectre#040 | 上层/7-spectre.md | **direct** |  | job 安全名（拒绝 / \ ..）有校验用例 | test/offline/unit/test_spectre_contracts.py::test_require_bool_and_job<br>test/offline/unit/test_spectre_contracts.py (bad/name 用例) |
| spectre#041 | 上层/7-spectre.md | **direct** |  | job → 确定性 run 目录（无随机路径）：契约断言 + 复现脚本按 job 定位运行目录；2026-09-28 复核补钉：新增 TestRunOrchestration::test_run_dir_is_deterministic_per_job（两次调用同 run_dir、形如 <root> | test/offline/unit/test_spectre_contracts.py<br>test/artifacts/tmp/repro_p076_rounds.py<br>test/offline/unit/test_spectre_contracts.py::TestRunOrchestration::test_run_dir_is_deterministic_per_job |
| spectre#077 | 上层/7-spectre.md | **direct** |  | tasks 非空/job 唯一且安全/max_workers≥1 均有校验断言（含重复 job 拒绝） | test/offline/unit/test_spectre_contracts.py |
| spectre#078 | 上层/7-spectre.md | **direct** |  | parse=auto 必须 download=true；parse=none 必须 keep_run_dir=true，有断言 | test/offline/unit/test_spectre_contracts.py (auto/download 与 none/keep_run_dir 用例) |
| spectre#083 | 上层/7-spectre.md | **direct** |  | netlist 上传到 run_dir/basename、include 同目录、basename 冲突拒绝：契约 + 真机 AC 链路探针 | test/offline/unit/test_spectre_contracts.py<br>test/semi/probes/spectre_ac_pipeline_probe.py |
| spectre#092 | 上层/7-spectre.md | **direct** |  | max_workers 并发、全部等待、单 task 失败不取消其余（含线程残留判据）有断言 | test/offline/unit/test_spectre_contracts.py<br>test/offline/core/thread_lifecycle_tb.py |
| spectre#093 | 上层/7-spectre.md | **direct** |  | 结果按 tasks 顺序返回，有断言 | test/offline/unit/test_spectre_contracts.py |
| spectre#094 | 上层/7-spectre.md | **direct** |  | 预算拒绝 → 该 task 记失败、不自动重试（预算用例 + task 失败语义） | test/offline/unit/test_endpoint_budgets.py<br>test/offline/unit/test_spectre_contracts.py |
| spectre#097 | 上层/7-spectre.md | **direct** |  | -64/+escchars/+log/-format psfascii/-raw/+lqtimeout/-maxw/-maxn/+logstatus 逐项断言 | test/offline/unit/test_spectre_contracts.py (默认参数用例 84-98) |
| spectre#098 | 上层/7-spectre.md | **direct** |  | spectre_args 后接 mode 映射参数、用户值覆盖默认（+lqtimeout 60、-maxw 1）有断言 | test/offline/unit/test_spectre_contracts.py (用户参数覆盖用例) |
| spectre#144 | 上层/7-spectre.md | **direct** |  | raw 已下载但解析失败 → status=partial、ok=false 且保留错误与文件，有断言 | test/offline/unit/test_spectre_contracts.py::test_fatal_output_with_raw_present_is_partial |
| spectre#146 | 上层/7-spectre.md | **direct** |  | 终止失败标记清单（error reading / terminated prematurely / license/convergence…）逐条断言 | test/offline/unit/test_spectre_contracts.py (classify_errors 用例 129-141) |
| spectre#197 | 上层/7-spectre.md | **direct** |  | noise_integral 需频率轴、ac_magnitude/bandwidth 仅 AC：类型/数据前置校验有断言（含 P-020 非法 dB） | test/offline/unit/test_spectre_metrics.py<br>test/offline/unit/test_spectre_util_contracts.py |
| spectre#202 | 上层/7-spectre.md | **direct** |  | export CSV：columns 缺省优先级、复数 re/im、缺失留空，有断言 | test/offline/unit/test_spectre_util_psf_contracts.py<br>test/offline/unit/test_spectre_contracts.py |
| spectre#214 | 上层/7-spectre.md | **direct** |  | swept delta 压缩/首步缺失哨兵（不得静默填 0）有断言 | test/offline/unit/test_spectre_util_psf_contracts.py |
| spectre#215 | 上层/7-spectre.md | **direct** |  | 对外 data 一律 null/省略、唯一出口 psf_external：P-049 修复后 3/3 绿 | test/offline/unit/test_output_json_safety.py<br>test/offline/unit/test_spectre_util_psf_contracts.py |
| spectre#216 | 上层/7-spectre.md | **direct** |  | 缺失哨兵与 NaN/±Inf 在 psf_external 收敛为 null，有断言（含业务面负控制） | test/offline/unit/test_output_json_safety.py |
| spectre#217 | 上层/7-spectre.md | **direct** |  | AC 复数相量 re/im 形态保持、JSON-safe，有断言 | test/offline/unit/test_spectre_util_psf_contracts.py |
| verilog#043 | 上层/8-verilog.md | **direct** |  | write 非事务、失败带 commands applied: k/n，有断言 | test/offline/unit/test_verilog_contracts.py (applied 前缀用例 313-326) |
| verilog#060 | 上层/8-verilog.md | **indirect** |  | 实现在 run_dir 生成 cds.lib 副本（不给共享份）；真机导入成功隐含该路径，但**无断言共享 cds.lib 未被追加 DEFINE** ｜ **缺口**: 真机补：import 前后对比共享 cds.lib sha256 不变 + run_dir 副本存在 | src/pyapi/packages/verilog.py:504-519（run_dir 内 cds.lib 副本）<br>test/live/packages/verilog_e2e_tests.py |
| verilog#062 | 上层/8-verilog.md | **direct** |  | structural_views 编码（默认 4）与 functional 视图产物有断言 | test/offline/unit/test_verilog_contracts.py<br>test/live/packages/verilog_e2e_tests.py |
| verilog#065 | 上层/8-verilog.md | **indirect** |  | 真机 import 成功即证明前缀生效（否则 libsasl2 缺失 rc=127）；**无直接断言命令前缀** ｜ **缺口**: 可选加固：离线断言生成命令以 LD_LIBRARY_PATH=… 开头 | src/pyapi/packages/verilog.py:517（LD_LIBRARY_PATH 前缀）<br>test/live/packages/verilog_e2e_tests.py |
| verilog#071 | 上层/8-verilog.md | **direct** |  | rc 不可信：rc=0+缺 End of Logfile → incomplete_log；语法错误日志 → parse_failure；rc≠0 原样回显，均有断言；行为面承接：verilog_e2e_tests.py; verilog_import_params_e2e_tests.py | test/offline/unit/test_verilog_contracts.py::test_parse_failure_and_incomplete_log<br>test/offline/unit/test_verilog_contracts.py::test_ihdl_nonzero_exit_and_validation<br>test/live/packages/verilog_e2e_tests.py<br>test/ |
| verilog#072 | 上层/8-verilog.md | **direct** |  | functional 视图 = verilog.v + netlist.oa（默认产物）有契约与真机证据 | test/offline/unit/test_verilog_contracts.py<br>test/live/packages/verilog_e2e_tests.py |
| verilog#097 | 上层/8-verilog.md | **na** |  | 「不在本版」：并发写同一 cell，明确不做 |  |
| verilog#099 | 上层/8-verilog.md | **indirect** |  | ihdl ksh 包装器/缺 libsasl2 是真机事实；由真机导入成功承担，无独立断言 | test/live/packages/verilog_e2e_tests.py |
| verilog#101 | 上层/8-verilog.md | **partial** |  | ‘rc 不可信、只看日志+产物’有断言；**成功标记 357/372/345 的识别分支**无用例 ｜ **缺口**: 补离线：三种成功标记日志 → 判成功；缺失标记 → incomplete_log | test/offline/unit/test_verilog_contracts.py (日志判成败用例) |
| verilog#103 | 上层/8-verilog.md | **partial** |  | 按次副本在建命令里有体现；**ihdl 向 -cdslib 追加 DEFINE 的防污染效果**（共享文件保持不变）无断言 ｜ **缺口**: 真机补：import 后共享 cds.lib 未被追加（sha 对比）+ 无 cwd 同名库目录残留 | test/offline/unit/test_verilog_contracts.py<br>src/pyapi/packages/verilog.py:504-519 |
| verilog#108 | 上层/8-verilog.md | **direct** |  | VERILOGIN-127（及 19）警告提取、降级 functional 的判定有断言；行为面承接：verilog_e2e_tests.py | test/offline/unit/test_verilog_contracts.py (VERILOGIN-127 警告解析 64-90)<br>test/live/packages/verilog_e2e_tests.py |
| veriloga#041 | 上层/11-veriloga.md | **direct** |  | read 纯只读（不调用会改缓存/视图状态的函数）由生成式断言 + 真机 read 用例钉住 | test/offline/unit/test_veriloga_contracts.py (read 生成式不调用 ahdlUpdateViewInfo)<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#045 | 上层/11-veriloga.md | **direct** |  | write 非事务、失败带 commands applied: k/n，有断言 | test/offline/unit/test_veriloga_contracts.py |
| veriloga#053 | 上层/11-veriloga.md | **direct** |  | 文件写路径（临时文件→读回校验→原子替换）有断言；行为面承接：veriloga_e2e_tests.py | test/offline/unit/test_veriloga_contracts.py (写临时文件→校验读回→原子替换)<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#055 | 上层/11-veriloga.md | **direct** |  | master.tag 内容与模块名=cell 名约束有断言；行为面承接：veriloga_e2e_tests.py | test/offline/unit/test_veriloga_contracts.py (master.tag 上传断言 321)<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#057 | 上层/11-veriloga.md | **direct** |  | 编辑器锁存在 → 拒绝外部写且不自动关窗，有断言 | test/offline/unit/test_veriloga_contracts.py (*.cdslck 检测 268)<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#068 | 上层/11-veriloga.md | **direct** |  | check_and_save 序列不含 ahdlCheckModule/SaveFile/Edit（防模态阻塞）：原生成式断言 + 第八轮新增**缺席断言**专测（FORBIDDEN_CALLS 逐一 assertNotIn） | test/offline/unit/test_veriloga_lazy_editor_contract.py::test_check_and_save_sequence_and_absence<br>test/offline/unit/test_veriloga_lazy_editor_contract.py::test_write_ops_do_not_touch_view_info |
| veriloga#069 | 上层/11-veriloga.md | **direct** |  | headless Check and Save 与 GUI 落盘逐文件一致（唯一差别无 symbol）：真机闭环用例 | test/live/packages/veriloga_e2e_tests.py<br>test/artifacts/evidence/round8 (veriloga 段) |
| veriloga#083 | 上层/11-veriloga.md | **na** |  | 「不在本版」：并发写同一 cell，明确不做 |  |
| veriloga#085 | 上层/11-veriloga.md | **direct** |  | dbOpenCellViewByType(veriloga w) 恒 nil → 必须走文件路径：生成式断言；行为面承接：veriloga_e2e_tests.py | test/offline/unit/test_veriloga_contracts.py<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#087 | 上层/11-veriloga.md | **direct** |  | 读源码走 infile/gets（不用 lineread 读 .va）有断言 | test/offline/unit/test_veriloga_contracts.py (infile/gets 生成式) |
| veriloga#088 | 上层/11-veriloga.md | **indirect** |  | ahdlCompile* 不存在、编译由 Spectre（ahdlcmi 缓存）完成：由 ADC/veriloga 真机仿真闭环承担，无独立断言 | test/live/flows/adc_sar_flow_tb.py<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#089 | 上层/11-veriloga.md | **direct** |  | cold start 需 loadContext(ahdlSck.cxt) 有断言；行为面承接：veriloga_e2e_tests.py | test/offline/unit/test_veriloga_contracts.py (loadContext 断言 247/457)<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#092 | 上层/11-veriloga.md | **direct** |  | 编辑器锁（veriloga.va.cdslck）→ 外部写失效，必须先关编辑器：与 #057 同族断言 | test/offline/unit/test_veriloga_contracts.py<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#094 | 上层/11-veriloga.md | **direct** |  | headless Check and Save 真机闭环（写→VerAParseModule→ahdlUpdateViewInfo）由 E2E + ADC 场景验证 | test/live/packages/veriloga_e2e_tests.py<br>test/live/flows/adc_sar_flow_tb.py |
| veriloga#095 | 上层/11-veriloga.md | **direct** |  | CDF + netlist.oa/data.dm 更新与 GUI 保存一致（无 symbol 视图差异）有契约与真机证据 | test/offline/unit/test_veriloga_contracts.py<br>test/live/packages/veriloga_e2e_tests.py |
| veriloga#096 | 上层/11-veriloga.md | **direct** |  | 不得使用 ahdlCheckModule/ahdlSaveFile 等模态包装：生成式缺席断言 + 第八轮专测（FORBIDDEN_CALLS） | test/offline/unit/test_veriloga_contracts.py<br>test/offline/unit/test_veriloga_lazy_editor_contract.py::test_check_and_save_sequence_and_absence |
| veriloga#107 | 上层/11-veriloga.md | **na** |  | 待验证项（实现前 spike：schPinListToSymbol 可行性）。spec 自述待定/待验证（非冻结要求）；已在 round8 报告‘明缺口’登记为待设计定稿 |  |
| skillref#034 | 上层/9-skillref.md | **direct** |  | source+doc_root 取值顺序（请求→config）与结果回带 source/doc_root 有断言 | test/offline/unit/test_skillref_package.py |
| skillref#051 | 上层/9-skillref.md | **direct** |  | 只有 source/doc_root/doc_token 三字段；remote 必须 doc_token（注册 user 代理）有断言 | test/offline/unit/test_skillref_package.py (partial-request / remote-without-doc_token) |
| skillref#055 | 上层/9-skillref.md | **direct** |  | doc_root 指向不存在路径 → 业务失败且错误文案回带该路径，且不发起任何远端调用（无 fallback、不猜路径），已断言。 | t<br>e<br>s<br>t<br>/<br>o<br>f<br>f<br>l<br>i<br>n<br>e<br>/<br>u<br>n<br>i<br>t<br>/<br>t<br>e<br>s<br>t<br>_<br>n<br>o<br>r<br>m<br>_<br>g<br>a<br>p<br>_<br>b<br>a<br>t<br>c<br>h<br>2<br>.<br>p<br>y<br>:<br>:<br>T<br> |
| skillref#062 | 上层/9-skillref.md | **direct** |  | 远端正文搜索函数内不出现 .exists()/.is_dir()/.is_file()/os.path.exists（对远端路径的本地 stat），已静态断言。 | t<br>e<br>s<br>t<br>/<br>o<br>f<br>f<br>l<br>i<br>n<br>e<br>/<br>u<br>n<br>i<br>t<br>/<br>t<br>e<br>s<br>t<br>_<br>n<br>o<br>r<br>m<br>_<br>g<br>a<br>p<br>_<br>b<br>a<br>t<br>c<br>h<br>2<br>.<br>p<br>y<br>:<br>:<br>T<br> |
| skillref#064 | 上层/9-skillref.md | **direct** |  | doc_token 无效/已删除 → 明确业务失败文案（非泛化 command failed），有断言 | test/offline/unit/test_skillref_package.py::test_invalid_doc_token_message |
| skillref#069 | 上层/9-skillref.md | **direct** |  | search 唯一入口 + 选项矩阵：包用例 + 真机远端探针 | test/offline/unit/test_skillref_package.py<br>test/semi/probes/skillref_probe.py |
| skillref#102 | 上层/9-skillref.md | **direct** |  | name/entry 的匹配面差异（是否并入语法/描述）由解析/打分用例覆盖；行为面承接：skillref_e2e_tests.py | test/offline/unit/test_skillref_docs_contracts.py<br>test/offline/unit/test_skillref_package.py<br>test/live/packages/skillref_e2e_tests.py |
| skillref#103 | 上层/9-skillref.md | **direct** |  | search_in="all" 解析为最深档 body，layers_run 与 body 完全一致，已断言。 | t<br>e<br>s<br>t<br>/<br>o<br>f<br>f<br>l<br>i<br>n<br>e<br>/<br>u<br>n<br>i<br>t<br>/<br>t<br>e<br>s<br>t<br>_<br>n<br>o<br>r<br>m<br>_<br>g<br>a<br>p<br>_<br>b<br>a<br>t<br>c<br>h<br>2<br>.<br>p<br>y<br>:<br>:<br>T<br> |
| skillref#107 | 上层/9-skillref.md | **direct** |  | 大小写不敏感子串 AND 匹配/排序不受 mode 影响：模式矩阵与排序用例 | test/offline/unit/test_skillref_docs_contracts.py |
| skillref#129 | 上层/9-skillref.md | **direct** |  | 未命中 → 空 results 且 ok=true（正常业务结果），有断言 | test/offline/unit/test_skillref_package.py (limit/无命中用例) |
| skillref#136 | 上层/9-skillref.md | **direct** |  | body+local 必须给 under（否则截断/拒绝），有断言 | test/offline/unit/test_skillref_package.py::test_body_layer_truncates_without_under |
| skillref#140 | 上层/9-skillref.md | **direct** |  | max_candidates 同时是下载上限：候选 7 条、max_candidates=3 时下载调用 ≤3 且标 truncated，已断言。 | t<br>e<br>s<br>t<br>/<br>o<br>f<br>f<br>l<br>i<br>n<br>e<br>/<br>u<br>n<br>i<br>t<br>/<br>t<br>e<br>s<br>t<br>_<br>n<br>o<br>r<br>m<br>_<br>g<br>a<br>p<br>_<br>b<br>a<br>t<br>c<br>h<br>2<br>.<br>p<br>y<br>:<br>:<br>T<br> |
| skillref#141 | 上层/9-skillref.md | **direct** |  | 正文层远端候选搜索默认 timeout=120 s，显式 timeout 可覆盖；每次候选下载都显式传 timeout，已断言。 | t<br>e<br>s<br>t<br>/<br>o<br>f<br>f<br>l<br>i<br>n<br>e<br>/<br>u<br>n<br>i<br>t<br>/<br>t<br>e<br>s<br>t<br>_<br>n<br>o<br>r<br>m<br>_<br>g<br>a<br>p<br>_<br>b<br>a<br>t<br>c<br>h<br>2<br>.<br>p<br>y<br>:<br>:<br>T<br> |
| skillref#153 | 上层/9-skillref.md | **direct** |  | info 抽取顺序（不可调换）由包用例钉住 | test/offline/unit/test_skillref_package.py (info 抽取顺序) |
| skillref#166 | 上层/9-skillref.md | **direct** |  | 配置缺失/null = 未配置，不阻断启动、调用时业务失败，有断言 | test/offline/unit/test_skillref_package.py (config 缺失/null 用例) |
| skillref#167 | 上层/9-skillref.md | **direct** |  | 读取顺序（请求参数 → config 快照）有断言 | test/offline/unit/test_skillref_package.py::test_source_from_config_snapshot |
| skillref#173 | 上层/9-skillref.md | **direct** |  | 单一搜索入口、search_in 为唯一深度参数：包用例 + 真机探针 | test/offline/unit/test_skillref_package.py<br>test/semi/probes/skillref_probe.py |
| skillref#180 | 上层/9-skillref.md | **direct** |  | 与 tools/skill_find 共享解析口径（.fnd/.tgf/HTML→MD）：工具探针 + 解析契约 | test/semi/probes/skill_tooling_probe.py<br>test/offline/unit/test_skillref_docs_contracts.py |
| skillref#194 | 上层/9-skillref.md | **na** |  | 决策记录（本版为何不建索引），无独立可测行为 |  |
| skillref#206 | 上层/9-skillref.md | **na** |  | 已知限制（性能数字 ~190s），按限制登记 |  |
| skillref#211 | 上层/9-skillref.md | **na** |  | 已知限制（远端 line 只在本地算），按限制登记 |  |
| skillref#212 | 上层/9-skillref.md | **direct** |  | 不做路径探测：source/doc_root 必须显式给出（缺失即业务失败）有断言 | test/offline/unit/test_skillref_package.py |
| calibre#005 | 上层/12-calibre.md | **indirect** |  | 状态声明（pex 未按官方三阶段验收、禁止交付）+ 其余项已真机验证；pex 两阶段 argv 有契约断言、真机三阶段闭环仍未见证据（按声明口径登记为限制） | test/offline/unit/test_calibre_argv_contracts.py<br>test/live/packages/calibre_e2e_tests.py |
| calibre#011 | 上层/12-calibre.md | **direct** |  | 默认非阻塞 + job_id/status/read_results 三件套与 blocking=true 轮询，均有断言；行为面承接：calibre_e2e_tests.py | test/offline/unit/test_calibre_package.py::test_drc_start_nonblocking<br>test/offline/unit/test_calibre_package.py::test_drc_blocking_completes<br>test/live/packages/calibre_e2e_tests.py |
| calibre#014 | 上层/12-calibre.md | **direct** |  | 失败带 kind/原文片段/run dir；unknown-effect 不自动重试，有断言 | test/offline/unit/test_calibre_package.py (failure_kind 用例)<br>test/offline/unit/test_calibre_job_state.py |
| calibre#031 | 上层/12-calibre.md | **direct** |  | job_id 默认 <kind>_<top>（可显式指定）有断言 | test/offline/unit/test_calibre_package.py::test_lvs_runset_goes_through_official_batch_entry |
| calibre#054 | 上层/12-calibre.md | **direct** |  | calibre_bin 取值顺序（请求显式 > query roles[command].calibre.bin）有断言 + 环境探针 | test/offline/unit/test_calibre_package.py<br>test/semi/probes/calibre_env_probe.py |
| calibre#057 | 上层/12-calibre.md | **direct** |  | launcher 固定先 ulimit -n 65536，有断言；行为面承接：calibre_e2e_tests.py | test/offline/unit/test_calibre_package.py::test_launcher_backgrounds_and_marks_stages<br>test/live/packages/calibre_e2e_tests.py |
| calibre#059 | 上层/12-calibre.md | **direct** |  | license 相关错误单独归类为 license（可重试）有断言（含误报反例） | test/offline/unit/test_calibre_package.py::test_job_state_failed_license |
| calibre#060 | 上层/12-calibre.md | **direct** |  | blocking=false 默认：launcher+后台启动+立即 job_id 有断言；行为面承接：calibre_e2e_tests.py | test/offline/unit/test_calibre_package.py::test_drc_start_nonblocking<br>test/live/packages/calibre_e2e_tests.py |
| calibre#068 | 上层/12-calibre.md | **direct** |  | blocking=true 循环（poll_interval/deadline）有断言；行为面承接：calibre_e2e_tests.py | test/offline/unit/test_calibre_package.py::test_drc_blocking_completes<br>test/live/packages/calibre_e2e_tests.py |
| calibre#069 | 上层/12-calibre.md | **partial** |  | 部分覆盖且已定位偏差：后台作业不被杀 ✓；但 deadline 到点返回最后一次 status（running）而非 spec 的 `timeout` —— 已立 P-098 并加 strict-xfail 红灯钉（--runxfail 实锤 'timeout' != 'running'）。修复后本 ｜ **缺口**: 设计修 P-098（收尾口径：非终态超时 → status=timeout，可保留 last_status 字段）→ 红钉转绿后复评 | test/offline/unit/test_calibre_package.py::test_drc_blocking_timeout_reports_timeout_status |
| calibre#096 | 上层/12-calibre.md | **direct** |  | drc/lvs 参数走官方机制两条互斥路（control file / -gui -lvs -runset -batch）有断言 | test/offline/unit/test_calibre_package.py (runset/官方批处理用例 431-499) |
| calibre#120 | 上层/12-calibre.md | **direct** |  | 三级报告定位回退逐条覆盖（第八轮补）：① 默认名 `DRC.rep`；② 默认名缺失时按 `job.json.report_file` （真实 set 改名场景）；③ 都指不到时在 run dir 按 `*.rep/*.report/*.sum` 模式扫描。三条用例均离线全过。 | test/offline/unit/test_calibre_package.py::test_read_results_drc<br>test/offline/unit/test_calibre_package.py::test_read_results_follows_renamed_report_in_job_json<br>test/offline/unit/test_calibre_package.py::test_read_ |
| calibre#123 | 上层/12-calibre.md | **partial** |  | set 走官方入口有断言；**‘set 只带参数、引用数据必须已存在’的失败边界**无专门用例 ｜ **缺口**: 补：set 引用不存在的 deck/layout → 明确失败（不静默回退） | test/offline/unit/test_calibre_package.py (set/runset 用例) |
| calibre#127 | 上层/12-calibre.md | **direct** |  | pex fmt=none/spice/simple 与非法值拒绝、deck 复制进 run dir，有断言 | test/offline/unit/test_calibre_argv_contracts.py (fmt 枚举与拒绝 56-93) |
| calibre#128 | 上层/12-calibre.md | **direct** |  | pex 固定阶段顺序（phdb→pdb→fmt）逐条断言（P-034 修复后） | test/offline/unit/test_calibre_argv_contracts.py::test_pex_runs_two_stages<br>test/offline/unit/test_calibre_argv_contracts.py::test_pex_adds_a_format_stage_only_for_spice_like_formats |
| calibre#129 | 上层/12-calibre.md | **direct** |  | 每阶段产物/stage 标记校验、阶段失败上报，有断言 | test/offline/unit/test_calibre_package.py::test_launcher_backgrounds_and_marks_stages<br>test/offline/unit/test_calibre_package.py::test_read_results_pex_stage_failure_is_reported |
| calibre#151 | 上层/12-calibre.md | **direct** |  | si.env 带 auCdl 三件套 + checkCAPPERI=nil + 一致 .simrc，有断言；行为面承接：s11_full_flow.py | test/offline/unit/test_calibre_package.py (auCdl 三件套 + checkCAPPERI 用例 509-531)<br>test/live/flows/s11_full_flow.py |
| calibre#160 | 上层/12-calibre.md | **na** |  | 「不做」：并发调度（同 token 建议串行） |  |
| calibre#171 | 上层/12-calibre.md | **na** |  | 已知限制：export 默认只取小文件、目录需点名 |  |
| calibre#172 | 上层/12-calibre.md | **indirect** |  | power/ground 未给沿 deck 默认（可能 ERC 告警）：由 LVS 真机探针结果间接体现，无参数级断言 | test/semi/probes/calibre_package_http_probe.py<br>test/live/flows/s11_full_flow.py |
| calibre#173 | 上层/12-calibre.md | **na** |  | 已知限制：许可不足/并发争用未做全局串行 |  |
