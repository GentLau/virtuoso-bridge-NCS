# 第八轮全面测试 · 报告

> 维护者：测试（root）｜ 2026-09-28 ｜ 基线：`HEAD=d47dabe` + 工作区（设计侧未提交改动一并被测）
> 目的：回答送审三问——**spec 每条要求测到没有？每个原子/每个参数测到没有？还剩哪些缺陷与缺口？**
> 证据根：`test/artifacts/evidence/round8/`（本轮全部复跑证据），机器矩阵见 `test/reports/round8/`。

## 0. 结论摘要

| 覆盖轴 | 口径 | 结果 |
|---|---|---|
| **A. spec 条款** | `spec/design-concepts/**` 全量抽 1131 条 → 分诊 NORM 297 / OPS 793 / PROSE 41 | NORM **direct 222 / indirect 16 / partial 6 / gap 0 / na 53**；OPS 由 op×param + 原子矩阵承担；PROSE 逐条给"不可测"理由 |
| **B. 原子操作** | `src/pyapi/packages` 写原子 60 个 | `audit_atom_coverage.py`：**GAP=0**、`needs_triage=0`（`evidence/round8/atom-coverage.json`） |
| **C. op × 参数** | OPERATIONS + spec 字段表 628 条 | 机器矩阵：CANDIDATE 553 / **GAP 46** / 无调用点 29（本轮起点 116）；`timeout` 家族 36 条由统一合同用例覆盖（79/79 op 拒非法值），余项见 §4/§5 |
| **覆盖率（组合口径）** | `run_main_coverage.ps1`（离线三层 + 离线 TB + 11 套包 direct + transport + 注册 + S11） | **语句 90.33% / 分支 82.26% / 合并 88.23%**（2026-09-29 01:55；**下界**——maestro 两步 rc=1）；未分类未覆盖行 1646（AST 证明体系见 `coverage-pack/`）；全绿快照 91.54/83.62/89.48 见 `coverage-main-strict-2333.json` |

**缺陷**：本轮**新发现 24 条**（P-078…P-101，逐条有最小复现/证据），未关闭合计 **25 条**（含待产品决策的 P-070）。
最重的一类不是单点功能错，而是**静默/误导**：`place_wire` 静默建出 path（P-078）、`layout.read depth>0` 组合确定性不可用（P-085）、
`save=False` 改动被后续保存静默带走（P-087）、daemon 空响应窗口被报成"cwd 不可用"（P-086/观察项）。

## 1. 三层复跑结果

### 1.1 离线（不需要真机）

| 平台 | 命令 | 结果 | 证据 |
|---|---|---|---|
| Windows py3.12 | `python -m pytest test/offline/unit test/offline/integration test/offline/scenario` | **1805 用例 / 0 失败 / 0 错误 / 21 skip（含 13 xfail）** | `evidence/round8/offline-win-final3.xml` |
| Linux py3.9（wsl-gent 仓库副本） | `test/shared/runners/sync_linux_client.ps1 -Run` | **1805 用例 / 0 失败 / 0 错误 / 31 skip（含 11 xfail）/ 123.1 s** | `evidence/round8/offline-linux-py39-final3.xml` |

> `xfail` = 已立卡未修缺陷的钉住用例（P-078/P-079/P-080/P-081/P-082 家族），带 `reason="P-08x: …"`；
> 修复后自动 XPASS，**不改判据**。离线层不得落盘/起服务的纪律由 `test/conftest.py` 强制。

### 1.2 半真机（`run_semi_probes.py --group all`）

- 最近一次整层：**39 探针 / 32 ok / 7 fail**（`evidence/round8/semi-probes-final.json`），
  7 条红灯**全部**对应已立卡缺陷，没有"无主红灯"：

| 探针 | 缺陷 |
|---|---|
| `schematic_wire_style_probe.py` | P-078 `place_wire` 样式参数拼接重复 |
| `layout_depth_probe.py` | P-085 `layout.read depth>0 + region` 任何写法都失败 |
| `maestro_export_include_results_probe.py` | P-084 `include_results` 死参数 |
| `maestro_save_false_disk_probe.py` | P-087 `save=False` 跨请求泄漏 |
| `maestro_delete_var_all_probe.py` | P-088 `delete_var(scope=all)` 句柄错误 |
| `maestro_open_waveform_result_probe.py` | P-089 `open_waveform_gui(result=)` 被忽略 |
| `calibre_flat_turbo_probe.py` | P-093 `calibre flat/turbo` 拼出非法 argv |

- 本轮同时修掉 **2 个探针自身缺陷**（否则会把噪声算成产品红灯）：
  `symbol_regen_handle_probe.py`（未清上一轮 symbol view → 二次跑必红）、
  `twouser_same_view_probe.py`（CLEAN 是尽力而为，却被计入判定 → 现 `counted=false`）。

### 1.3 真机

| 套件 | 结果 | 证据 |
|---|---|---|
| 11 套包 E2E | **逐套单独复跑：9 套绿（infra/cellview/schematic/symbol/layout/verilog/veriloga/skillref/spectre）+ calibre 8/8**；**maestro 23/23**（21:28 入档）之后被 P-086/P-095/P-096 阻塞 | `evidence/http-e2e/*.log`、`evidence/round8/package-e2e-r8*.log` |
| 五接口多 token | skill/command/file/gui/spectre 五接口全 OK（`vb-vblog`，含 query 只读面） | `evidence/round8/cov-remote-real-r8.json` |
| 真机 pytest | 10 用例 / 0 失败 / 5 skip（skip 均带明确原因）；**local 模式 4 用例在 Linux 侧另跑 4/4 且 teardown 后端口归零** | `evidence/round8/live-e2e.xml`、`local-live-r8b.txt` |
| 并发压测 | **36/36 轮应答、108 步 0 失败**（6 worker × 6 轮，31.2 s） | `evidence/round8/production-face-stress.json` |
| 业务场景（flows/） | SerDes RX **11 段全绿**（含 DRC 读回 1737 规则/28 结果、AC 增益 5.06 dB、BW 15.8 GHz）；ADC SAR **24/24**；design_iterate 11 段 + LVS `correct`；两用户共建 **17/17**；版图接力 **12/12**；LVS-from-schematic `correct`；S11 全链；role-split；multihop **10/10**；scale-100 2 轮全对 | `evidence/round8/{serdes/,adc-sar-r8.json,design-iterate-r8/,serdes-multiuser-r8.json,multiuser-layout-handoff-r8.json,lvs-from-schematic-r8.json,s11/,role-split-r8.json,multihop-r8.json,scale-100-r8.json}` |
| 注册专项（4 条） | 六步 local PASS；py27 **10/10**；真 CIW **12/12**；五 role 跨主机 **28/28** | `evidence/round8/registration-*.json` |

> **批量 vs 单跑的差异（必须写清楚）**：`run_all_http.py` 批量跑 3 次里分别有 1/3/2 套被 **P-086**
>（多用户/长任务后 30–90 s 的 daemon 空响应窗口）打断；自愈后逐套单跑即绿。结论按"逐套单跑"给，
> 批量失败与单跑证据都留在 `evidence/round8/package-e2e-r8*.log`，不混用。

## 2. spec 条款逐条（轴 A）

- 机器抽取 1131 条（`spec-clause-triage.md`）→ 分诊 **NORM 297 / OPS 793 / PROSE 41**；
- NORM 297 条**逐条裁定**（6 组独立评审后合并）：**direct 222 / indirect 16 / partial 6 / na 53 / gap 0**
  —— 见 `round8-spec覆盖矩阵.md/.json`（含逐条证据路径）与 `round8-gap-actions.md`（partial 的待补动作）；
- 矩阵引用的 **416 个证据文件全部存在**（脚本核对）；
- `partial` 剩余 6 条：注册#108（等 P-079 定口径）、schematic#050（等 P-082）、verilog#101（成功标记口径：实现用 `End of Logfile.`+产物校验，spec 写 357/372/345 —— 需 spec owner 定稿）、verilog#103（共享 cds.lib 防污染的真机 sha 对比）、calibre#069（blocking 超时语义）、calibre#120（报告三级定位回退）。

## 3. 原子操作（轴 B）

- 60 个写原子：**GAP=0**、`needs_triage=0`；13 条"写了不读回"的列举全部是探针/负控制（理由写在 JSON 里）。
- 判据口径：写原子必须有读回/几何/字节级断言才算覆盖；纯文本契约（只断言 SKILL 文本含某函数名）**不计**覆盖。

## 4. op × 参数（轴 C）

- 机器矩阵 628 条：**CANDIDATE 553 / GAP 46 / 无调用点 29**（本轮起点：GAP 116）。
- 残余 GAP 的构成与处置：

| 家族 | 条数 | 处置 |
|---|---:|---|
| `timeout` | 36 | 统一合同用例 `test/offline/unit/test_param_timeout_contract.py`：79 个 op 逐个断言 `timeout=0/-5/nan/"30"` 被拒（400），证据 `evidence/round8/timeout-contract.json` |
| `calibre.*` 家族 | 42 | 子代理 `calibre_params` 收口中（本轮已产出 P-092/P-093/P-094/P-098 四条缺陷）；`calibre.pex`/`calibre.export` 仍是**零调用点**（见 §5 G1） |
| `layout.read :: depth` | 1 | 已被 `layout_depth_probe.py` 覆盖，但结果是 **P-085（红）**，不计"通过" |

## 5. 明缺口（**不声称覆盖**）

| # | 缺口 | 现状 | 计划 |
|---|---|---|---|
| G1 | `calibre.pex` / `calibre.export` 零调用点（29 条参数） | 无任何 TB 调用 | 子代理补真机（PEX 需 license/时间长，先做 export） |
| G2 | calibre 参数语义（hier/fmt/power/ground/…） | 离线已断言 runset 文本，真机语义未逐项验 | 随 P-092/P-093 修复后补齐 |
| G3 | screenshot 家族（`window_id/region/toplevel/central_widget/view_type`） | 已补，`region` 与 P-082 冲突未定版 | P-082 修复后按两点格式复跑 |
| G4 | `layout.read depth>0` | **P-085 确定性不可用** | 修复后同一探针转绿 |
| G5 | `maestro.export.include_results` | **P-084** 声明但不读 | 设计决定实现或删参数 |
| G6 | verilog/veriloga `view_type`、`file_is_local` 远端写 | **P-080/P-081** | 修复后回归 |
| G7 | 蒙卡（MC）能力 | **P-070**：只能读回、不能驱动 | 待产品口径 |
| G8 | 同 token 双 CIW / 二次 load 负向 | 环境约定，未做负向用例 | 记为"明确不做"（评审口径已确认） |
| G9 | AST 无法静态解析的调用点 | 70 处（helper/dict 拼装） | 逐条人工复核后并入 CANDIDATE 或 GAP |
| G10 | 真机 100 实例规模 | 现为协议级 100 fake + 真机 6~8 实例 | 用户已定口径：不需要真机 100，按现状通过 |

## 6. 本轮修掉的测试侧问题（TB/工具，含我直接改的设计 TB）

1. `run_offline_multi.py`：离线三层（2400+ 用例）此前**完全不计入 coverage** → 子进程改走 `coverage run --append`（本轮覆盖率因此从 64% 升到 89% 口径，属**修正测量**而非改判据）。
2. `run_semi_probes.py`：Windows GBK 解码打断 runner（补 `encoding="utf-8"`）；日志/证据路径写死 round7（改为跟随 `--out`）；新增逐探针进度输出。
3. `symbol_regen_handle_probe.py`：前置未清 symbol view → 不可重复运行（已修，3/3 PASS）。
4. `twouser_same_view_probe.py`：CLEAN 计入判定 → 显式 `counted=false`，T1–T5 全绿。
5. `registration_py27_tb.py` / `registration_real_ciw_tb.py`：重复运行时同一公钥触发查重 → 第 1 步 401（补 `enhanced_token`，现 10/10、12/12）。
6. `test/live/e2e/test_business_local_live.py`：teardown 的 pkill 模式在 `VB_LOCAL_PROJECT_ROOT` 覆盖后匹配不到 → 实例残留、二次跑必撞端口（改成完整路径匹配，复跑 4/4 且端口归零）。
7. `maestro_e2e_tests.py` WRITE-06：原判据假设"新会话读回旧值"不成立（session 被复用）→ 改为**步骤表判据**（save=False 不得出现 `save_setup`），磁盘级泄漏由 P-087 探针承担。
8. 删除 `test/live/flows/layout_suite_p044_workaround_tb.py`（P-044 已修，正式套件直接跑 PASS）。
9. 新增条款缺口用例：`test_norm_gap_round8.py`（12 用例）、`test_norm_gap_batch2.py`（12 用例）、`test_param_timeout_contract.py`（79 op）。

## 6bis. 观察项（不单独立卡，但评审要看）

| 观察 | 证据 | 说明 |
|---|---|---|
| P-086 窗口期的错误文案误导 | 22:00 `calibre.export_cdl` 报 `cds.lib not resolved (CIW cwd unavailable)`；22:04 `getWorkingDir()` 正常；22:06 calibre 8/8 PASS | 空响应与"cwd 不可用"必须分开报 |
| 顶层未知字段处理不统一 | dataclass 模型 → 400 `unexpected keyword argument`；pydantic 模型 → 静默忽略 | 建议统一口径（见 `test_norm_gap_batch2.py::TestRequestIdNotIntroduced` 注释） |
| 离线层 skip 的构成 | 19–31 条 skip，逐条带 reason（平台守卫/条件跳过） | 非"沉默跳过"；`test/offline/README.md` 有纪律 |

## 7. 数字与证据一览（送审判据）

| 项 | 数字 | 证据文件 |
|---|---|---|
| 离线 Win py3.12 | 1805 / 0 红 / 21 skip（13 xfail） | `evidence/round8/offline-win-final3.xml` |
| 离线 Linux py3.9 | 1805 / 0 红 / 31 skip（11 xfail） | `evidence/round8/offline-linux-py39-final3.xml` |
| 半真机 | 39 探针 / 32 ok / 7 红（全部已立卡） | `evidence/round8/semi-probes-final.json` |
| 真机包 E2E | 10 套稳定绿 + 1 被阻塞（maestro P-086/P-095/P-096） | `evidence/http-e2e/*.log` |
| 真机五接口 | 5/5 | `evidence/round8/cov-remote-real-r8.json` |
| 真机 e2e + local | 10 用例 0 红（5 skip）+ local 4/4 | `evidence/round8/live-e2e.xml`、`local-live-r8b.txt` |
| 压测 | 108 步 / 0 失败 | `evidence/round8/production-face-stress.json` |
| 业务场景 | 10 条链全绿（见 §1.3） | `evidence/round8/*` |
| 注册专项 | 4 条 TB 全绿（28/28、12/12、10/10、六步） | `evidence/round8/registration-*.json` |
| 覆盖率 | 语句 90.33% / 分支 82.26% / 合并 88.23%（下界，maestro 2 步 rc=1；全绿快照 91.54/83.62/89.48） | `evidence/cov-main/coverage-main-strict.json` + `coverage-main-strict-2333.json` + `test/reports/coverage-pack/summary.json` |
| spec 条款 | 297 NORM 逐条：222/16/6/0/53 | `round8-spec覆盖矩阵.json` |
| 原子 | 60 原子 GAP=0 | `evidence/round8/atom-coverage.json` |
| op×参数 | 628 条：553/46/29 | `round8/op-param-matrix.json` |
| 缺陷 | 本轮新增 24、未关闭 25 | `test/reports/bugs/README.md` |

## 8. 子代理评审记录

（评审任务派发后回填；底稿见 `test/artifacts/tmp/r8_review_prompts.md`。）
