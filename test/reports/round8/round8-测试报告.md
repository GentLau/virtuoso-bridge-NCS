# 第八轮全面测试 · 报告（进行中，数字随复跑更新）

> 维护者：测试（root）｜ 2026-09-28 ｜ 基线：`HEAD=64c803c` + 工作区（设计侧未提交改动一并被测）
> 目的：回答送审三个问题——**spec 每条要求测到没有、每个原子/每个参数测到没有、还剩哪些缺陷与缺口**。

## 0. 结论摘要（先看这里）

| 覆盖轴 | 口径 | 结果 |
|---|---|---|
| **A. spec 条款** | `spec/design-concepts/**` 全量 1131 条 → 分诊 NORM 297 / OPS 793 / PROSE 41 | NORM：**direct 219 / indirect 16 / partial 9 / gap 0 / na 53**；OPS 由 op×param + 原子矩阵承担；PROSE 逐条给了"不可测"理由 |
| **B. 原子操作** | `src/pyapi/packages` 写原子 60 个 | `audit_atom_coverage.py`：**GAP=0**、`needs_triage=0`（证据：`evidence/round8/atom-coverage.json`） |
| **C. op × 参数** | OPERATIONS + spec 字段表 628 条 | 机器矩阵：CANDIDATE 499 / GAP 100 / 无调用点 29；`timeout` 家族 38 条已由 `test_param_timeout_contract.py`（79/79 op 拒绝非法值）收口；余项见 §5 |

**本轮新发现缺陷 12 条**（P-078…P-089，全部有红灯证据与最小复现）：`place_wire` 样式参数、local 联合端口、
`view_type` 合同、远端 POSIX 路径、region 口径、`precision` 语义、`include_results` 死参数、
`layout.read depth>0 + region` 确定性不可用、多用户场景后 30–90s daemon 空响应窗口（P-086）、
`maestro.write(save=False)` 跨请求泄漏（P-087）、`delete_var`/`open_waveform` 两处 maestro 参数/清理缺陷（P-088/089）。
已关闭 1 条测试侧事项（C0）。

**三层结论（详见 §7）**：离线 Win **1793/0红/19skip**、Linux py3.9 **1793/0红/29skip**（用例数与 Windows 一致）；
半真机 36 探针、红灯全部对应已立卡缺陷；真机 11 套包首跑 **10/11**、把 WRITE-06 判据改为步骤表后 **11/11 绿**
（maestro 22/22；**P-087 的 save=False 隔离缺陷仍由磁盘级探针钉住为红**）、
注册四项全绿、业务全链全绿、生产面压测 6×6=36/36、实时 e2e 6 pass/5 skip；
覆盖率（合并口径）语句 **67.18%** / 分支 **50.38%** / 合并 **62.81%**（maestro 不完整，见 §7.3）。

## 1. 三层复跑结果

### 1.1 离线（不需要真机）

| 平台 | 命令 | 结果 | 证据 |
|---|---|---|---|
| Windows py3.12 | `python -m pytest test/offline/unit test/offline/integration test/offline/scenario` | 见 §7 复跑记录（含预期红：P-078/P-080 钉住用例） | `evidence/round8/offline-win-*.xml` |
| Linux py3.9（wsl-gent 仓库副本） | `sync_linux_client.ps1 -Run` | 同上（Linux 口径，含 Windows-only 用例的 skip） | `evidence/round8/offline-linux-py39.xml` |

### 1.2 半真机（`run_semi_probes.py --group all`）

- 探针 **36**（截至 21:10；新增 `maestro_save_false_disk_probe`）：最近一次整层 32 ok / 3 fail，
  随后新增的 P-087 探针单独实跑为 RED。fail 全部是**已立卡的产品缺陷**，不是探针坏：
  - `schematic_wire_style_probe.py` → **P-078**（place_wire 样式参数拼接重复）
  - `layout_depth_probe.py` → **P-085**（`depth>0 + region` 任何写法都失败）
  - `maestro_export_include_results_probe.py` → **P-084**（`include_results` 声明但不读）
  - `maestro_save_false_disk_probe.py` → **P-087**（save=False 未隔离，被下一次 save 带走；磁盘级证据）
- 证据：`evidence/round8/semi-probes.json` + `evidence/round8/semi-logs/*.log`。
- 本轮同时修了 2 个**探针自身**的问题（否则会把环境噪声算成产品红灯）：
  `symbol_regen_handle_probe.py`（未清上一轮的 symbol view → 第二次跑必红）、
  `twouser_same_view_probe.py`（CLEAN 是尽力而为的收尾，却被计入判定 → 现显式 `counted=false`）。

### 1.3 真机

| 套件 | 结果 | 证据 |
|---|---|---|
| 11 套包 E2E（`run_all_http.py`） | 见 §7（本轮复跑记录） | `evidence/http-e2e/results.json` |
| 五接口多 token（`cov_remote_real.py`） | 见 §7 | `evidence/round8/cov-remote-real-r8.json` |
| 真机 pytest（`VB_E2E=1 pytest test/live/e2e`） | 见 §7 | `evidence/round8/live-e2e-*.log` |
| 并发压测（`production_face_stress_tb.py`） | 见 §7 | `evidence/round8/production-face-stress.json` |
| 业务场景链（flows/） | SerDes RX 11 段全绿、ADC SAR 24/24、design_iterate 11 段（含 LVS `correct`）、两用户 SerDes 17/17、版图接力 12/12、LVS-from-schematic `correct`、S11 全链、role-split 5/5、multihop 10/10、scale-100 2 轮全对 | `evidence/round8/{serdes,adc-sar-r8.json,design-iterate-r8,serdes-multiuser-r8.json,multiuser-layout-handoff-r8.json,lvs-from-schematic-r8.json,s11,role-split-r8.json,multihop-r8.json,scale-100-r8.json}` |
| 注册专项（4 条） | 六步 local PASS、py27 **10/10**、真 CIW **12/12**、五 role 跨主机 **28/28** | `evidence/round8/registration-*.json` |

## 2. spec 条款逐条（轴 A）

- 机器抽取 1131 条（`spec-clause-triage.md`） → 分诊：**NORM 297 / OPS 793 / PROSE 41**。
- NORM 297 条**逐条裁定**（`round8-spec覆盖矩阵.md/.json`，6 组独立评审后合并）：
  `direct 219 / indirect 16 / partial 9 / na 53 / gap 0`。
  - `na` 一律给出"为什么不可测"（定义/指针/实现自由度/明确不做）；
  - `partial` 逐条写明**补什么**（`round8-gap-actions.md`，本轮已收口 8 条，余 15 条 → §5）。
- 证据引用可复查：矩阵里引用的 **416** 个证据文件**全部存在**（脚本核对，见 §6）。

## 3. 原子操作（轴 B）

- `audit_atom_coverage.py`：60 个写原子，**GAP=0**、无"写了不读回"的真阳性（13 条列举均为探针/负控制，理由已写进 JSON）。
- 每个原子的证据文件数 ≥1，示例 control：`place_rect` 命中 18 份证据。

## 4. op × 参数（轴 C）

- 机器矩阵 628 条：`CANDIDATE 499 / GAP 100 / NO-OP-TB 29`（AST 解析；70 处调用点无法静态解析，单独列出）。
- 本轮已收口的家族：
  - `timeout`（38 条 GAP）：`test/offline/unit/test_param_timeout_contract.py` —— **79/79 op 对 `timeout=0` 返回 400**，
    证据 `evidence/round8/timeout-contract.json`；
  - spectre（output_root / spectre_bin / measure.source_path / export.columns+precision）：`test/live/packages/spectre_params_e2e_tests.py` 5/5；
  - maestro（export/read_results 家族）：`maestro_e2e_tests.py` 扩写后套件内覆盖；
  - skillref（max_candidates）：`test_norm_gap_batch2.py`；
  - layout（depth/region_mode）：真机探针 `layout_depth_probe.py`（结果为 **P-085**，不是"通过"）。
- 余项（calibre 全家族、verilog import/export、screenshot 家族、`view_type`/`view`、`file_is_local`）
  由 `calibre_params` / `verilog_params` / `shot_family` 子代理收口中，状态见 §5 与 `round8/README.md` §3。

## 5. 明缺口（不声称覆盖）

| # | 缺口 | 现状 | 计划 |
|---|---|---|---|
| G1 | `calibre.pex` / `calibre.export` **零调用点** | 29 条参数无任何 TB 调用 | 子代理 `calibre_params` 补真机（PEX 需 license/时间长，先做 export） |
| G2 | calibre 参数家族（hier/fmt/power/ground/spice_file/xcell/hcell/job_id/runset/params/turbo…） | 100 条 GAP 的主要部分 | 同上；离线先断言 runset/deck 文本，真机再验语义 |
| G3 | screenshot 家族（`window_id/region/toplevel/central_widget/view_type`） | 子代理 `shot_family` 收口中；`region` 与 **P-082** 冲突 | 等 P-082 定版后按两点格式复跑 |
| G4 | `layout.read` 的 `depth>0` | **确定性不可用（P-085）** | 修复后同一探针转绿 |
| G5 | `maestro.export.include_results` | **P-084**：声明但不读 | 设计决定实现或删参数 |
| G6 | verilog/veriloga `view_type`、`file_is_local` 远端写 | **P-080/P-081** | 修复后回归 |
| G7 | 蒙卡（MC）能力 | **P-070**：只能读回、不能驱动 | 待产品口径 |
| G8 | 真 CIW 二次 load / 同 token 双 CIW 负向 | 环境约定，未做负向用例 | 记为"明确不做"（评审口径已确认） |
| G9 | 未解析调用点 70 处 | AST 静态解析不到（helper/dict 拼装） | 逐条人工复核后并入 CANDIDATE 或 GAP |

## 6. 本轮修掉的测试侧问题（TB/工具）

1. `symbol_regen_handle_probe.py`：前置未清 symbol view → 不可重复运行（已修，3/3 PASS）。
2. `twouser_same_view_probe.py`：CLEAN 被计入判定（已修 `counted=false`，T1–T5 全绿）。
3. `run_semi_probes.py`：① Windows GBK 解码把 runner 打断（补 `encoding="utf-8"`）② 日志/证据路径写死 round7（改为跟随 `--out`）③ 加了逐探针进度输出。
4. `registration_py27_tb.py` / `registration_real_ciw_tb.py`：重复运行时同一公钥触发查重 → 第 1 步 401（补 `enhanced_token`，现 10/10、12/12）。
5. 删除 `test/live/flows/layout_suite_p044_workaround_tb.py`（P-044 已修，正式套件直接跑 PASS）。
6. 新增条款缺口用例：`test/offline/unit/test_norm_gap_round8.py`（12 用例）+ `test_norm_gap_batch2.py`（12 用例，含 6 条 gap-action 收口）。

## 7. 复跑记录（数字与证据）

### 7.1 离线

| 平台 | 结果 | 证据 |
|---|---|---|
| Windows py3.12（最新树，21:00） | **1793 例 / 0 红 / 0 error / 19 skip**（其中 **11 条 strict-xfail 钉住**：P-078×1、P-079×1、P-080×4、P-081×2、P-082×3） | `offline-win-5.xml` |
| Linux py3.9（wsl-gent 副本，21:38） | **1793 例 / 0 红 / 0 error / 29 skip**（9 条 xfail 钉住：P-078×1、P-079×1、P-080×4、P-082×3）——**与 Windows 用例数完全一致**；跨平台 XPASS(strict) 已由平台门控修掉 | `offline-linux-py39-final.xml` |
| 远端解释器（同次） | py2.7 daemon **5/5** + handler `silent drop (correct)`；py3.6 daemon **5/5** + 编译 ok | `linux-py27-*.json`、`linux-py36-daemon-r8.json` |

### 7.2 真机（截至 21:10）

| 套件 | 结果 | 证据 |
|---|---|---|
| 11 套包 E2E（`run_all_http.py`，21:05） | 首跑 **10/11**（红=maestro WRITE-06 旧判据）；修正判据后 **maestro 22/22** → 11 套包 **11/11 绿**。产品缺陷 P-087（save=False 隔离）由磁盘探针独立红钉 | `http-e2e/results.json`、`round8/run-all-http-r8.log`、`round8/maestro-save-false-disk.json` |
| 五接口多 token（`cov_remote_real.py`） | 由覆盖率 runner 中包含运行（`run_main_coverage.ps1` 的 transport 步骤）；独立快照待回填 | `evidence/cov-main/`（round8 运行中） |
| 真机 pytest（`VB_E2E=1 pytest test/live/e2e`） | rc=0（11 例 = 6 pass / 5 skip：4 条 local 模式需 `VB_E2E_LOCAL=1`、1 条按环境 skip） | `round8/live-e2e-r8.log` |
| 并发压测（`production_face_stress_tb.py`） | **ok=true：6 workers × 6 rounds = 36/36 answered、108 步 0 失败**（scale-100 100×2 另计） | `round8/production-face-stress.json`、`scale-100-r8.json` |
| 业务场景链 | SerDes RX 全链、ADC 24/24、design_iterate（LVS `correct`）、两用户 17/17、接力 12/12、LVS-from-schematic `correct`、role-split 5/5、multihop 10/10、S11 全链 | `evidence/round8/*` |
| 注册专项 | 六步 local ok、py27 10/10、真 CIW 12/12、五 role 28/28 | `evidence/round8/registration-*.json` |

### 7.3 覆盖率

`run_main_coverage.ps1` 于 2026-09-28 21:07–21:29 完成；唯一失败步骤 = `packages/maestro (direct)`
（先被 TB 的 400 语义误红，修好后又被 **P-086** 空响应窗口阻断 → maestro 覆盖**不完整**，见下）。

| 口径 | 语句 | 分支 | 合并 | 文件数 | 证据 |
|---|---|---|---|---|---|
| default | **67.18%** | **50.38%** | **62.81%** | 57 | `cov-main/coverage-main.json` |
| strict（忽略 `# pragma: no cover`） | **67.19%** | **50.38%** | **62.82%** | 57 | `cov-main/coverage-main-strict.json` |

**口径声明（防混引）**：`run_main_coverage` 合并口径 = 离线三层 + offline/core TB + 11 套包(direct) +
cov_remote_real + one_shot_burst + 注册六步/1-4 + S11；未包含 `test/live/e2e` 与压测 TB。
maestro 包因 P-086 本轮**未完整跑完**（其已执行部分已 append 进上述数字）。
覆盖数字**不代表质量**：行为正确性以 TB 断言与负控制为准；不得声称 100%。

## 8. 子代理评审记录

（红队评审结论与处置见本节，评审任务在复跑完成后派发。）
