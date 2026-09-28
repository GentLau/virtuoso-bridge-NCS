# 第八轮全面测试报告（2026-09-28）

> 状态：**收尾中**（本文件随最后两件收尾更新：Linux 离线重跑、覆盖率汇总、红队评审结论）
> 口径：**三轴覆盖**（A spec 条款 / B 原子 / C op×参数）× **三层回归**（离线 / 半真机 / 真机）+ 缺陷与"不覆盖声明"。
> 原则：只用可复查证据说话；**弱判据（只看 ok/rc）不作为覆盖结论**；未跑到的显式列缺口，不声称 100%。

## 0. 一句话结论

- 三轴里 **B（原子，60 个）gap=0/weak=0**；**A（条款）297 条已逐条裁定，direct 211 / indirect 16 / partial 17 / na 53，gap=0**；
  **C（op×参数 628 条）** root 车道已清零、calibre/screenshot/verilog 三车道收尾中。
- 三层回归：Windows 离线 **1793 例 / 0 红 / 19 skip**（最新树）；半真机 **35 探针（32 绿 + 3 个预期红钉）**；
  真机 **11 套包 11/11** + 注册/流程/压测场景全绿（明细见 §4）。
- 本轮新发现并立案 **12 条缺陷**（P-078…P-089），全部有红灯钉住或显式口径声明；**不声称已排干净**。

## 1. 覆盖轴 A：spec 条款

- 抽取：`extract_spec_clauses.py` 从 13 份 Normative 文档抽 **1131 条候选**（标题/表行/规范句式）；
- 裁定：`norm-review/g1..g6` 逐条给出 verdict 与证据（**必须打开证据文件确认断言**），合并稿 `round8-spec覆盖矩阵.md`；
- 当前分布（297 条可测条款）：

| verdict | 条数（最新矩阵快照） | 含义 |
|---|---:|---|
| direct | 219 | 有直接断言（读回/数值/字节/结构化错误） |
| indirect | 16 | 产物被下游消费且有断言（已在矩阵注明） |
| partial | 9 | 部分覆盖，剩余动作见 `round8-gap-actions.md`（原 15 条，已闭环含 root 2 条） |
| na | 53 | 术语表/引用/状态行等不可测，逐条给"为什么不可测" |
| gap | 0 | —— |

> root 已完成其中 2 条缺口动作：**注册#011**（部署路径不得含 token，P3 TB 29/29）、**layout#179**（失败分类 TB 4/4）。
> 机器抽查：全 436 处证据引用，**文件 0 缺失**、函数名不匹配 2 处（1 处过时、1 处暴露 veriloga#068/#096 缺"生成式缺席断言"，已转车道补）。

## 2. 覆盖轴 B：原子操作（60 个）

- 工具：`audit_atom_coverage.py`；证据 `test/artifacts/evidence/atom-coverage-2026-09-28.json`
- 结果：**gap=0 / weak=0 / 待分诊=0 / 间接=0**（semi+live 均有引用；"证据树第二来源"同样 0 遗漏）；
- 本轮补强：serdes calibre 补 `read_results`、ADC/多用户 SerDes 补 `symbol.read` 端口比对、S11 gds 补 stat+sha256。

## 3. 覆盖轴 C：op × 参数（79 个操作 / 628 条）

- 工具：`build_op_param_matrix.py`（AST v2，能解析 `OP + "suffix"` 拼接与跨函数转发）；
- 最新快照：**CANDIDATE 501 / GAP 98 / NO-OP-TB 29**；`NO-OP-TB` 的业务 op 只剩 `calibre.export`、`calibre.pex`（calibre 车道收尾中）；
- root 车道（spectre/maestro/layout 失败分类/注册 token-path）已清零：
  - `spectre_params_e2e_tests.py` **5/5**；`maestro_e2e_tests.py` **23/23**；`layout_geometry_classification_e2e_tests.py` **4/4**；
  - 期间抓出 4 条同源缺陷：P-083（precision 语义未定义）、P-084（include_results 死参数）、**P-088**（delete_var scope=all）、**P-089**（open_waveform_gui.result 死参数）。
- 剩余 GAP 全在三条子代理车道（calibre 24 / screenshot 14 / verilog 12）+ `layout.read.depth`（P-085 已红钉）。

## 4. 三层回归

### 4.1 离线（Windows，最新树）

- `pytest test/offline -q` → **1793 例 / 0 红 / 19 skip**（`evidence/round8/offline-win-r8.xml`、`offline-win-5.xml` 同口径复核一致）。

### 4.2 离线（Linux py3.9）

- 同一份树在 wsl-gent 仓库副本上跑 → **1793 例 / 0 红 / 29 skip**（`evidence/round8/offline-linux-py39-r8.xml`）；
- **两平台用例数完全一致（1793）**，且都 0 红 → Linux/Windows 客户端离线一致性本轮成立；
- 上一份旧树里的 3 红（P-079 两条 XPASS(strict) 平台门控 + P-078 断言）已由对应子代理处理。

### 4.3 半真机（35 探针）

- `run_semi_probes.py --group all` → **32 绿 / 3 红**；3 红均为已立案预期红钉：
  `schematic_wire_style_probe`（P-078）、`maestro_export_include_results_probe`（P-084）、`layout_depth_probe`（P-085）；
- 证据：`evidence/round8/semi-probes.json`、`semi-probes-r8.log`。

### 4.4 真机

- **11 套包**：gate 10/11（唯一红为 root 的 WRITE-06 旧判据）→ 修正后 `maestro_e2e_tests.py` **23/23**，
  合计 **11/11**（`evidence/round8/package-e2e-r8.log`、`http-e2e/*.log`）；
- **注册**：six-local ok、py27 **10/10**、role-split **29/29**、real-ciw **12/12**；
- **流程/规模/并发**：multihop 10/10、scale-100（100 fake）ok、多用户版图接力 12/12、多用户 SerDes **17/17**、ADC **24/24**、role-credential-isolation 8/8、生产面混合压测（此前 216 步 0 失败）。
- **LVS**：`lvs_from_schematic_tb`（源网表由 `schematic.read` 产品数据生成 → 桥导出 GDS → `calibre.lvs` + `read_results`）
  实测 **CORRECT**（`CMP_LIB/cmp_top`，ports 6，`lvs.rep` 行含 `CORRECT`；证据 `evidence/round8/lvs-from-schematic-r8.json`）；
  对照 `s11_full_flow` 的自建版图（只有 M1 矩形无布线）为 `incorrect`（预期）。

## 5. 覆盖率（机器）

**本轮口径**：`coverage run --branch --source=src` 逐层/逐套件采集后合并（含离线三层 + standalone TB + 11 包 direct +
真机五接口 + 注册 + S11 等步骤；与历史"再并入 ssh/paramiko/supervisor 定向运行"的合并口径**不同，禁止混引**）。

| 指标 | 数值 | 证据 |
|---|---|---|
| 语句 | **67.19%**（covered 11641 / 17325，miss 5684） | `evidence/cov-main/coverage-main-strict.json`（2026-09-28 21:36 重跑） |
| 分支 | **50.38%**（covered 3067 / 6088，miss 3021） | 同上 |
| combined | **62.82%**（display 63%） | 同上 |
| 模块数 | 57 | 同上 |
| 未覆盖分类 | 未分类 5638 / 防御性 8 / 环境阻塞 50 | `coverage-pack/coverage-rules-auto.json` |

> 口径说明：① 初轮（`coverage-main-r8.log`）有一处 step rc=1（`packages/maestro (direct)`，root 的 WRITE-06 旧判据）；
> 修正后重跑得本表数字（与初轮 67.12%/50.30%/62.75% 差异仅来自该 step 恢复）。
> ② 与历史 79.31%/69.88%（离线三层，合并 ssh/paramiko/supervisor/register 定向运行）与 86.60%/77.39%
> （再合并真机）**口径不可比**；③ **不声称 100%**，明缺口见 §7。

## 6. 本轮缺陷（全部有红灯钉住或口径声明）

| ID | 层 | 状态 | 一句话 | 钉住物/证据 |
|---|---|---|---|---|
| P-078 | 上层 schematic | 待设计修 | `place_wire` 样式参数（width/color/line_style）与 spec 不符 | 半真机探针红 |
| P-079 | 中层 配置 | 待设计修 | local 联合端口显式双值不等被静默归一化 | 离线 strict xfail（需平台门控） |
| P-080 | 上层 verilog/veriloga | 待设计修 | read 的 `view_type` 未校验 | 离线 4 strict xfail |
| P-081 | 中层 SSH | 待设计修 | 远端 POSIX 路径被 `Path()` 改写 | 离线 strict xfail（Linux 侧 XPASS，需门控） |
| P-082 | 上层 + 口径 | 待设计修 | region 两点 vs 四元组口径漂移（三处请求面） | 离线 strict xfail + 探针 |
| P-083 | 上层 spectre | 待归属 | `export.precision` 语义未定义（实现=有效数字） | TB 按实效钉住 |
| P-084 | 上层 maestro | 待设计修 | `export.include_results` 死参数 | 半真机探针红 |
| P-085 | 上层 layout | 待设计修 | `layout.read(depth>0)` + region 任何写法都失败 | 探针红 + 离线 xfail |
| P-086 | 底层/中层 | 观察 | 多用户同视图后 30–90s `Empty response`（自愈） | 探针 4/4 复现 |
| P-087 | 上层 maestro | 待设计修 | `save=False` 改动被后续 save 静默带走 | 磁盘级探针红 |
| P-088 | 上层 maestro | 待设计修 | `delete_var(scope=all)` 确定性 handle 0 | 红灯探针 + scope 矩阵 |
| P-089 | 上层 maestro | 待设计修 | `open_waveform_gui.result` 死参数 | 红灯探针 |

## 7. 明缺口 / 不覆盖声明（防"虚高"）

| # | 未覆盖项 | 现状 | 说明 |
|---|---|---|---|
| G1 | **蒙特卡洛驱动** | 无实现（P-070 待产品口径） | 只有"读回 MC 结果"的解析用例；MC 实验还留下过共享库 run_mode 污染（已恢复） |
| G2 | **后仿 / PVT** | 后仿（PEX）仅在 calibre 车道收尾 | 本轮只做前仿（AC/TRAN）+ DRC/LVS；PVT 未测 |
| G3 | **真实 100 台机器** | 用 100 个协议级 fake 替代 | scale-100 是 fake fleet；真机侧只有 8 实例 |
| G4 | **>2 跳拓扑** | 2 跳 + SOCKS5 叠加已测（multihop 10/10） | 3 跳以上未测 |
| G5 | **自建版图的 LVS `correct`** | 仅在复用既有真实版图时成立 | 本轮新增：源网表由产品数据生成（`lvs_from_schematic_tb`，CMP_LIB/cmp_top）→ **CORRECT**；但**版图本身不是桥自建布线**（自建版图仍 `incorrect`）。要闭合需"桥 write 出带布线/端口的版图 → LVS correct" |
| G6 | **Linux 客户端只跑离线层** | 真机/半真机仍以 Windows 客户端为主 | 与"Linux/Windows 一致性"要求仍有距离（Linux 离线含 py3.9 py2.7.6 探针） |
| G7 | **子进程覆盖率** | 未合并 | `supervisor.py` 等被监督体跑在子进程，当前口径低估（R7-O-11） |
| G8 | **GUI"点击级"交互** | 仅探针级（窗口定位 + 截图 parity） | 无真实鼠标点击/对话框流程用例（模态框类问题靠探针与 X11 工具兜） |
| G9 | **host-key 轮换 TB（P5）** | **TB 未落地** | 测试侧接口已就绪（`w4_hostkey_cycle.sh` status/use-a/use-b/restore + 常驻说明）；设计侧未写 TB |
| G10 | **maestro 多 corner 扫描整链** | 仅有包级 e2e 与历史探针 | 本轮未做"多 corner 扫描 + 结果比对"整链 |
| G11 | **`layout.read(depth>0)`** | **确定性不可用**（P-085） | 已红钉；在修复前该参数组合记"未覆盖（被缺陷阻塞）" |
| G12 | **calibre.export / calibre.pex** | 收尾中（calibre 车道） | 当前 `NO-OP-TB` 两个业务 op；若本轮来不及，按"下轮首项"记录而非假装覆盖 |

## 8. 环境与过程（本轮踩坑记录）

- 8127 是 standalone：**改 `src/` 后必须重启**，否则探针读旧代码（本轮两次踩到）；
- 共享库 `maestro_tb/rc_probe` 被 MC 实验改成 `Monte Carlo Sampling` → 常规 run 产出 MC 布局、waveform 读回失败（已恢复）；
- 并发纪律：三个子代理各自起过重叠 runner（两名并发 `run_all_http`、semi 探针与 live 套件互相打断 maestro 会话）→ 已收敛为单 runner 并记录在案。

## 9. 复现入口（节选）

```powershell
python -m pytest test/offline -q -p no:cacheprovider
PYTHONPATH=src python test/shared/runners/run_semi_probes.py --group all
PYTHONPATH=src python test/live/packages/maestro_e2e_tests.py --transport http
PYTHONPATH=src python test/live/packages/spectre_params_e2e_tests.py --transport http
PYTHONPATH=src python test/live/packages/layout_geometry_classification_e2e_tests.py
python test/shared/runners/audit_atom_coverage.py
python test/shared/runners/build_op_param_matrix.py
```
