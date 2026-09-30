# round9 · spec 条款矩阵复核（B 线代跑 A 线，人工结论）

> 执行：subagent `/root/opparam_r9`｜2026-09-29 21:12
> 机器产物：`spec-matrix-r9-b.json`、`spec-matrix-r9-b.md`（脚本 `spec_matrix_r9_audit.py`）
> 输入：`test/reports/round8/round8-spec覆盖矩阵.json`（297 条）+ 本轮 `test/artifacts/evidence/round9/offline-windows-r9.xml`（1960 用例）

## 1. 旧结论重验（297 条）

| 状态 | 条数 | 含义 |
|---|---|---|
| **R9-GREEN** | **226** | 引用的离线证据文件**本轮跑过且无红** → 旧结论在本轮重验成立。其中 221 条来自 pytest JUnit；**5 条来自脚本式 core TB，已在本轮 21:05 复跑**（`core-multi-r9.json`，30/30 绿，含 `semantics_tb.py` 10 例、`fault_injection_tb.py` 8 例） |
| **NA-NO-EVIDENCE-NEEDED** | **53** | 条款本身标 `na`（不要求证据）——**不是缺口**（此前误与"只引 semi/live"混算） |
| NO-OFFLINE-EVIDENCE | **18** | 只引 semi/live/产物类证据。**已逐条对表本轮产物：16 条有本轮证据（注册六步/semi-probes、schematic/symbol/layout/verilog/veriloga 的 `package-e2e-r9-full/*.log`）；2 条仍是旧产物**（见 §4） |
| 引用文件不存在 | **0** | **没有假证据**（round8 矩阵里每条 offline 路径都真实存在于磁盘） |

**对表明细**：`spec-live-evidence-r9.json` / `.md`（脚本 `spec_live_evidence_r9.py`，口径：本轮 = mtime ≥ 2026-09-29 18:00）。

旧结论分布（round8）：direct 222 / indirect 16 / partial 6 / na 53 / **gap 0**。

## 2. 需人工改判的 30 条候选（按本轮变更分组）

> 判定口径：机器只按关键词列候选；下面括号里是我方已有证据给出的**建议改判**。

| 变更 | 候选条数 | 建议 |
|---|---|---|
| **P-102/103 PEX 本版不提供** | 4（含 `calibre#005` "未按官方三阶段验收，禁止用于交付/签核"） | **改为"本版不提供 PEX"**：spec §4.4 已定稿 `pex_unsupported`；TB `calibre_export_pex_e2e_tests.py` **6/6**（本轮门禁） |
| **P-092 删 calibre power/ground** | 1（`calibre#172` "power/ground 未给时沿用 deck 默认"） | **删除/标 na**：字段已从实现删除（op×参数矩阵 8 条"消失"里占 6 条） |
| **C1 响应契约** | 4 | 按新契约改判：成功默认省略 `steps`、失败壳两字段、JSON 出口 `CDSlog`、删 `metadata`、`execution_time` 三位小数；证据：`test/offline/unit/test_result_contract.py` + `test_common_request_fields_contract.py`（84）+ 真机 `step_details_e2e_tests` **6/6** |
| **C2 log_level/log_max_bytes** | 9 | 保持/加强：离线日志合同 + 真机 `skill_log_options_e2e_tests` **7/7**（含 `warn` 过滤、`log_max_bytes` 降级两档）——本轮由 W-1 补强 |
| **C4 CommandResult 命名字段** | 2（含 `总览#179`） | 保持 direct：离线 3 用例 + 真机 `basic.command.run` 实测返回 `{returncode,stdout,stderr,kind}` |
| **P-091 截图远端暂存口径** | 3 | 按新口径改判：三包统一"远端暂存、下载后清理"；真机 screenshot TB symbol/layout 各 6/6 |
| **P-105 screenshot view_type 校验** | 3（含 `symbol#023`） | 保持并补证据：P-105 已关闭（layout/symbol 真机 6/6，SC-06 含坏值负例） |
| **P-104 读路径 `?mode "r"`** | 1 | 保持：真机 `maestro_view_param_e2e_tests` **9/9**（读路径不再建 view） |
| **P-098 blocking 超时** | 4（含 `calibre#011`） | 保持并补口径：spec 已写 `status=timeout`；探针 `calibre_timeout_probe` PASS |

> 其余关键词命中的条目（如 `总览#159` 日志字段、`日志#077` 帧顺序、`注册#011` token 范围）属**上下文命中**，请人工确认是否真的需要改判——机器不替人下结论。

## 3. 我的总体判断

1. **没有"假证据"**：297 条里所有引用的离线文件都真实存在，且 **226 条能在本轮找到全绿证据**
   （221 条 pytest JUnit + 5 条脚本 core TB）——这是"覆盖率不是虚高"的硬支撑，建议主报告直接引用这个数字。
2. **真正需要动笔的只有 30 条候选**，其中 4 + 1 = 5 条是**口径已被推翻**（PEX、power/ground），必须改；其余多为"补提本轮证据"而非改结论。
3. ~~两条脚本 TB 的产物是今日 01:54~~ → **已复跑**：`run_core_multi.py --out test/artifacts/evidence/round9/core-multi-r9.json`，
   **6 条 core TB / 30 用例全绿（ok=true, failed=0）**，5 条脚本证据已是本轮最终口径。

## 4. 18 条"只引 semi/live"的条款怎么收口

**16 条已有本轮证据**（可判"本轮已验"）：注册#007/011/040（`semi-probes.json` + 注册六步）、schematic#025、symbol#026/082、
layout#048/079/179、verilog#060/065/099、veriloga#069/088/094、calibre#172（`package-e2e-r9-full/*.log` 与 `evidence/round9/`）。

**2 条仍是旧产物，收口前需处理**：

| 条款 | verdict | 依赖 TB | 问题 | 建议 |
|---|---|---|---|---|
| ~~`路由#024`~~（P0-01 关闭口径："gui 与 daemon 不必同机"） | indirect | `test/live/flows/role_split_tb.py` | ~~无本轮产物~~ → **已复跑（21:25）** | ✅ 已完成：`--work-dir test/artifacts/env/scenario-role-split --user rolesplit` → **ok=true，5/5 检查通过**（query-roles / query-root-matches-registry / daemon→GLIS-DESKTOP / command→w1-gent / file 上传下载字节一致），证据 `test/artifacts/evidence/round9/role-split-r9.json`。途中修了 S2 注册表：`rolesplit`/`vbrolefc6dbc17` 的 `ssh.backend` paramiko → **openssh**（w1-gent 的 `StrictHostKeyChecking=accept-new` 不被 paramiko 支持，与 vbfake 同类问题） |
| `schematic#018`（`screenshot` 参数：`window_id`/`region`） | direct | `test/live/packages/screenshot_params_e2e_tests.py` + `evidence/round8/screenshot-params/schematic.json` | TB 在门禁里，但本轮只跑了新接线后的 19 套门禁之外的单套，产物仍是 round8 的 | 跑一次 `run_all_http.py`（19 套）即覆盖 |

### 建议写法（替换主报告 §2 的 spec 矩阵行）

> **"297 条 = 226 条本轮离线重验绿（221 pytest + 5 脚本 core TB / 30 用例全绿）+ 53 条 na（不要求证据）+ 18 条只引 semi/live（16 条已有本轮证据、2 条待跑：`路由#024` role_split、`schematic#018` screenshot_params）；另有 30 条因本轮变更需逐条改判（含 PEX×4、power/ground×1 属口径被推翻）；引用文件不存在 0 条。"**
* 若 A 线最终交付了自己的 `spec-matrix-state.md`，以二者**取并集**：本文件提供"新鲜度 + 变更影响"，A 线提供"逐条新结论"。

## 5. 口径声明

本复核是**机器打标 + 人工建议**，不是最终裁决：`R9-GREEN` 只证明"该条款引用的离线证据在本轮跑过且无红"，
不等于"条款本身已被充分覆盖"（覆盖强度仍需按条款逐条看判据，那部分是 A 线的活）。
