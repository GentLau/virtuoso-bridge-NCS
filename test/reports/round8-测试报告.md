# 第八轮全面测试报告（2026-09-28）

> 状态：**定稿**（已并入：Linux 离线/真机客户端两条线、覆盖率终值、缺陷台账、四份独立红队评审与逐条处置；见 §10）
> 口径：**三轴覆盖**（A spec 条款 / B 原子 / C op×参数）× **三层回归**（离线 / 半真机 / 真机）+ 缺陷与"不覆盖声明"。
> 原则：只用可复查证据说话；**弱判据（只看 ok/rc）不作为覆盖结论**；未跑到的显式列缺口，不声称 100%。

## 0. 一句话结论

- 三轴里 **B（原子，60 个）gap=0/weak=0**；**A（条款）297 条已逐条裁定，direct 222 / indirect 16 / partial 6 / na 53，gap=0**；
  **C（op×参数 628 条）最新快照 CANDIDATE 569 / GAP 59 / NO-OP-TB 0**：root / screenshot / verilog.import 三条车道清零，
  **calibre.export / calibre.pex 两个零调用 op 也首次有了 TB 调用（NO-OP-TB 归零）**；
  GAP 从 46 回升到 59 是**口径解释**：新扫到的 pex 调用点把该 op 的 12 个参数行首次纳入矩阵（此前无任何调用点）。
  PEX 本体被 P-102 阻塞（spec 也标「禁止交付」），这些行**如实计为未覆盖**，不并入 direct。
- 三层回归：离线 **1807 例 / 0 红**（Windows 21 skip / Linux py3.9 31 skip，**两平台计数一致**）；
  半真机 **39 探针（32 绿 + 7 个预期红钉）**；真机 base 五接口 + 文件族 + Linux 客户侧全栈全绿，
  **11 套包 = 10 稳定绿 + 1 被缺陷阻塞**（maestro 卡 P-086/P-095；calibre 初跑红已定性为同一根因的连带，
  恢复实例后复跑 **8/8**，见 §4.4）；
  注册/流程/压测场景全绿（明细见 §4）。
- 本轮新发现并立案 **25 条缺陷**（P-078…P-102 区间：root 侧 P-092/093/094/099/100/101/102，子代理侧 P-095/096/098，
  其余为前序根/其它车道），其中 **P-095 + P-096 是 P-086 的两类 P1 根因**（悬空 Overwrite History / 陈旧 OA 写锁 → 模态框卡死 CIW），
  全部有红灯钉住或显式口径声明；**不声称已排干净**。

## 1. 覆盖轴 A：spec 条款

- 抽取：`extract_spec_clauses.py` 从 13 份 Normative 文档抽 **1131 条候选**（标题/表行/规范句式）；
- 裁定：`norm-review/g1..g6` 逐条给出 verdict 与证据（**必须打开证据文件确认断言**），合并稿 `round8-spec覆盖矩阵.md`；
- 当前分布（297 条可测条款）：

| verdict | 条数（最新矩阵快照） | 含义 |
|---|---:|---|
| direct | 222 | 有直接断言（读回/数值/字节/结构化错误） |
| indirect | 16 | 产物被下游消费且有断言（已在矩阵注明） |
| partial | 6 | 部分覆盖，剩余动作见 `round8-gap-actions.md` |
| na | 53 | 术语表/引用/状态行等不可测，逐条给"为什么不可测" |
| gap | 0 | —— |

> root 已完成其中 2 条缺口动作：**注册#011**（部署路径不得含 token，P3 TB 29/29）、**layout#179**（失败分类 TB 4/4）。
> 机器抽查：全 436 处证据引用，**文件 0 缺失**、函数名不匹配 2 处（1 处过时、1 处暴露 veriloga#068/#096 缺"生成式缺席断言"，已转车道补）。

## 2. 覆盖轴 B：原子操作（60 个）

- 工具：`audit_atom_coverage.py`；证据 `test/artifacts/evidence/atom-coverage-2026-09-28.json`
- 结果：**gap=0 / weak=0 / 待分诊=0 / 间接=0**（semi+live 均有引用；"证据树第二来源"同样 0 遗漏）；
- 本轮补强：serdes calibre 补 `read_results`、ADC/多用户 SerDes 补 `symbol.read` 端口比对、S11 gds 补 stat+sha256。
- **口径注（红队 REVIEW-C #9 提出）**：同一指标有两份产物 —— `test/reports/round8/atom-coverage.json`（19:51，写原子 `write_without_readback=12`）
  与 `test/artifacts/evidence/atom-coverage-2026-09-28.json`（23:20，`write_without_readback=11`）。本报告引用后者；
  差 1 条来自本轮新增的写原子回读用例，**评判结论（gap=0/weak=0）两者一致**，但引用时必须带文件名与时间。

## 3. 覆盖轴 C：op × 参数（79 个操作 / 628 条）

- 工具：`build_op_param_matrix.py`（AST v2，能解析 `OP + "suffix"` 拼接与跨函数转发）；
- 最新快照：**CANDIDATE 569 / GAP 59 / NO-OP-TB 0**（本轮起点 GAP 98、NO-OP-TB 29）；
  `NO-OP-TB` 归零 = 79 个 op **每个都至少有一条 TB 调用**（calibre.export / calibre.pex 由本轮新 TB 补上）；
  GAP 59 里 25 条是"真正没覆盖的参数行"（其中 pex 12 条因 P-102 阻塞、calibre kind 不适用 11 条、export.job_id 1 条、layout.read.depth 1 条），其余为超时/视图类伪参数（脚本过滤后不计）；
- root 车道（spectre/maestro/layout 失败分类/注册 token-path）已清零：
  - `spectre_params_e2e_tests.py` **5/5**；`maestro_e2e_tests.py` **23/23**；`layout_geometry_classification_e2e_tests.py` **4/4**；
  - 期间抓出 4 条同源缺陷：P-083（precision 语义未定义）、P-084（include_results 死参数）、**P-088**（delete_var scope=all）、**P-089**（open_waveform_gui.result 死参数）。
- **screenshot 车道本轮清零**（root 自己补的 TB）：`screenshot_params_e2e_tests.py` 三级 kind 各覆盖
  `window_id`/`region`/`toplevel`/`central_widget`/`leave_open`/`view_type`，实测
  schematic **5/5**、symbol **5/5**（均绿）、layout **5 绿 + SC-06 红钉**（bogus `view_type` 不校验 → P-080 同族）；
  期间抓出 **P-091**（symbol/layout 下载后删远端暂存，与 spec「远端存 screenshots/」口径不一致）与
  **P-082 的完整形态**（layout/symbol 要两点、schematic 要四元组，spec 只写了两点）。
- **verilog 车道本轮清零**（root 新增 TB）：`verilog_import_params_e2e_tests.py` 在**健康实例上干净复跑 = 9 绿 + 3 红钉**
  （`file_is_local` True/False、`ref_libs` 正/负、`structural_views` 4 与 5 的**产物差异**、三个视图名参数、
  `import_lib_cells`、`overwrite`、语法错负向、`export(recursive=False/True)` 模块数对照；
  红钉 = IMP-08（P-099 `views` 恒空）、IMP-10（P-100 `cell` 参数不落地）、IMP-07（P-101 `overwrite=False` 未写入却 completed 且无跳过标记，返回 `cells=[]`）。
  注：00:09 那次复跑整段是 P-086 空响应（实例被 P-095 模态框卡死），已作废；00:15 实例硬重启后的这次才是本报告引用的结果。）
- 剩余 GAP（最新矩阵 **CANDIDATE 553 / GAP 46**，generic GAP 只剩 12 条）：`calibre.drc` 7 + `calibre.lvs` 4 + `layout.read.depth` 1；
  其中 **9 条属「kind 不适用」**（spice_file/hcell_file/xcell_file/fmt/lvs_run_dir 只在 lvs/pex 分支消费，见 `calibre.py:987-1013`）、
  **2 条是死参数**（power/ground，P-092）、**1 条真缺口 = `drc.runset`（set 模式真跑）**；
  `layout.read.depth`（P-085）与 `verilog.read/write.view_type`（P-080）仍是红钉。**未覆盖项如实列出，不并入 direct**。
- **calibre 参数面本轮大补齐**（root 新增 TB）：`calibre_params_e2e_tests.py` **5/5 绿**，
  覆盖 `check_env(calibre_bin/deck 正负)`、`drc(calibre_bin/hier/turbo/poll_interval/job_id/params/run_dir)`、
  `read_results(log_lines=0/5 双向)`、`lvs(spice_file/hcell_file/xcell_file/hier/turbo/poll_interval)`；
  剩余 GAP 里 **`drc.spice_file/hcell_file/xcell_file/fmt/lvs_run_dir` 与 `lvs.fmt/lvs_run_dir` 属"kind 不适用"**
  （argv 只在 lvs/pex 分支消费，见 `src/pyapi/packages/calibre.py:987-1013`）、**`power`/`ground` 是死参数（P-092）**、
  `drc.runset`（set 模式）仍缺一条真跑——这三类在矩阵里保持 GAP/红钉，不粉饰。
- 期间又抓出 **3 条缺陷**：P-092（power/ground 死参数）、**P-093**（`hier=False` 仍带 `-turbo` → Calibre 判非法、打 usage）、
  **P-094**（工具秒退不被检测：`status` 只报 `unknown`、`blocking=True` 等满 timeout）；红钉探针
  `test/semi/probes/calibre_flat_turbo_probe.py` 已注册进 `run_semi_probes.py --group calibre`。

## 4. 三层回归

### 4.1 离线（Windows，最新树）

- `pytest test/offline -q` → **1807 例 / 0 红 / 21 skip**（`evidence/round8/offline-win-final2.xml`，2026-09-29 00:26 复跑；
  用 `--collect-only` 逐文件核对：**108 个文件、每文件计数与 Linux 完全一致**）。
  口径提醒：该 XML 的 `tests` 属性由 pytest 写成了 2456，但其中 `<testcase>` 元素实测 **1800 条、无重复**
  （`collection` 与 `testcase` 双口径以 1800 为准）。

### 4.2 离线（Linux py3.9）

- 同一份树（tar 同步后）在 wsl-gent 仓库副本上跑 → **1807 例 / 0 红 / 31 skip**（`evidence/round8/offline-linux-py39-final2.xml`）；
- **两平台计数完全一致（1807 / 0 红）**；skip 差 10 条均为平台门控（Windows 侧多跑 10 条路径类用例），
  ⇒ Linux/Windows 客户端离线一致性本轮成立；
- 上一份旧树里的 3 红（P-079 两条 XPASS(strict) 平台门控 + P-078 断言）已由对应子代理处理。

### 4.3 半真机（39 探针）

- `run_semi_probes.py --group all`（23:51 快照）→ **39 探针 / 32 ok / 7 fail**（`evidence/round8/semi-probes-final.json`）；
- 7 条 fail **都是已立案红钉，但性质分两档**（红队 REVIEW-C #4 指出原先"全部断言红"的表述过强，已按实测改写）：
  * **断言红 5 条**：`layout_depth_probe`（P-085）、`schematic_wire_style_probe`（P-078）、`maestro_save_false_disk_probe`（P-087）、
    `maestro_delete_var_all_probe`（P-088）、`calibre_flat_turbo_probe`（P-093+P-094，`tool_failed=true` 而 `error_surfaced=false`）；
  * **前置失败 2 条（rc=2，`ENV: no Interactive.* history`）**：`maestro_export_include_results_probe`（P-084）、
    `maestro_open_waveform_result_probe`（P-089）—— 这两条的**红灯证据来自各自 standalone 复跑**：
    `evidence/round8/maestro-include-results/include-results.json`（verdict=RED）与 `evidence/round8/p089-open-waveform-result.json`（verdict=RED）；
    探针本身的环境前置（依赖 `Interactive.*` history）记为已知限制，不当作"功能已测"。
- 单条探针日志：`evidence/round8/semi-logs/<probe>.log`；calibre 红钉的原始证据：`evidence/round8/p093-flat-turbo-probe.json`。

### 4.4 真机

- **11 套包（三次 gate 分开记，不合并口径）**：
  1. 初版 gate（`package-e2e-r8.log`）**10/11**：唯一红是 root 自己的 WRITE-06 旧判据 → 修判据后 `maestro_e2e_tests.py`
     **23/23**（原始日志已从 `tmp/` 归档到 `evidence/round8/maestro-23of23-2128.log`，23 条 PASS，红队 REVIEW-C #8/#6 要求证据入库已完成）；
  2. 中间版 gate（`package-e2e-r8-final.log`）**8/11**：三红 layout/verilog/veriloga 全是 `Empty response from daemon`（P-086 族），
     按"红项单独复跑定性"逐套复跑 → `layout` **rc=0**、`verilog` **rc=0**、`veriloga` **7/7**（复跑前出现一次 P-090 形态的
     `mv: cannot stat <stage>`，重跑即绿，已单独立案为观察项）；
  3. **终版 gate（21:51 起，树=当前）`package-e2e-r8-final2.log` = 9 PASS / 2 FAIL**：
     - `maestro_e2e_tests.py` FAIL：`virtuoso.maestro.run` → `RuntimeError: Empty response from daemon`（P-086，同一实例上第 3 次独立复现；
       复跑仍在 `read_config` 处再报同错，**不是** TB 判据问题）；
     - `calibre_e2e_tests.py` FAIL：EXPORT-01 `calibre.export_cdl failed: cds.lib not resolved (CIW cwd unavailable; pass cds_lib explicitly)`
       —— **已定性为 P-086/P-095 的连带**：当时 maestro 刚把 CIW 卡进 ASSEMBLER-3018 模态框，
       `getWorkingDir()` 拿不到 cwd。22:56 在恢复后的实例上**单独复跑 calibre 套件 = 8/8 全绿**
       （`evidence/round8/calibre-rerun.out.log`；LVS 结论 `not_compared` 属 P-069 的既定口径，套件已显式 WARN 不假装跑通）。
  ⇒ **本轮可复现结论 = 10 套稳定绿**（含 calibre 复跑 8/8）；**只有 maestro 被 P-086/P-095 阻塞**，
    但"空响应窗口"本身仍是缺陷，**不声称 11/11**。

### 4.5 真机 · Linux 客户端（客户侧全栈）

- 口径：**客户端侧代码全部跑在 Linux**，不是"Windows 客户端连 Linux 目标"——业务面 `api_server` + 中层 `transport`
  + 包层都在 wsl-gent 上，用 `/usr/bin/python3.9`（满足"客户端 ≥3.9"），指向 wsl-gent 上的真实实例 `vbuser2`（daemon 65402，GUI `:103`）。
- 环境：仓库副本 `~/project/vblog/tb-sandbox/linux-client/repo` + 独立注册表 `env-live`（token `vb-vbuser2`）+ Linux 侧业务面 `127.0.0.1:8127`；
  与 Windows 侧常驻 8127 / Gent 实例完全隔离（不同注册表、不同实例）。
- 结果：`infra_e2e_tests.py --transport http` **6/6 PASS**（五接口 skill/command/gui/spectre + 文件上传下载 + 递归目录 + 串并行 + 超时语义 + GUI 枚举/截图），
  证据 `evidence/round8/linux-client-infra.json`（含 `python: 3.9.25`、`platform: Linux-…-WSL2`）。
- 过程中修掉一个**环境漂移**（不是产品 bug）：vbuser1/vbuser2 的 Virtuoso 实际跑在 `:110`/`:103`（`xvfb-run -a` 随机显示号），
  注册表却写 `:100`/`:101`，导致 `virtuoso.gui.*` 报 `no CIW window found`；已把两个注册表改成实际值并写入 `docs/环境与场景.md` 的 DISPLAY 纪律。
- 复现入口见 `docs/环境与场景.md` §7「Linux 客户端真机链路」。**仍不覆盖**：Linux 客户端下跑 *全部* 包套件与 flows（本轮只跑 base 五接口 + 文件族；包/流程层仍以 Windows 客户端为主，见 §7 G6）。
- **注册**：six-local ok、py27 **10/10**、role-split **29/29**（含 `deploy-paths-contain-no-token`；
  证据 `evidence/round8/registration-role-split.json`，2026-09-29 00:42 干净 work-dir 复跑）、real-ciw **12/12**；
- **流程/规模/并发**：multihop 10/10、scale-100（100 fake）ok、多用户版图接力 12/12、多用户 SerDes **17/17**、ADC **24/24**、role-credential-isolation 8/8、
  生产面混合压测 **108 步 / 0 失败**（`evidence/production-face-stress.json`：`steps_total=108, steps_failed=0`；36 轮 × 3 步）。
  （红队 REVIEW-C #7 更正：原报告"216 步"在该证据文件里**没有依据**——216 若指历史某次，需另附证据；本报告统一引用 108。）
- **LVS**：`lvs_from_schematic_tb`（源网表由 `schematic.read` 产品数据生成 → 桥导出 GDS → `calibre.lvs` + `read_results`）
  实测 **CORRECT**（`CMP_LIB/cmp_top`，ports 6，`lvs.rep` 行含 `CORRECT`；证据 `evidence/round8/lvs-from-schematic-r8.json`）；
  对照 `s11_full_flow` 的自建版图（只有 M1 矩形无布线）为 `incorrect`（预期）。

## 5. 覆盖率（机器）

**本轮口径**：`coverage run --branch --source=src` 逐层/逐套件采集后合并（含离线三层 + standalone TB + 11 包 direct +
真机五接口 + 注册 + S11 等步骤；与历史"再并入 ssh/paramiko/supervisor 定向运行"的合并口径**不同，禁止混引**）。

| 指标 | 数值 | 证据 |
|---|---|---|
| 语句 | **91.54%**（covered 15860 / 17325，miss 1465） | `evidence/cov-main/coverage-main-strict.json`（2026-09-28 23:33:35 重跑） |
| 分支 | **83.62%**（covered 5091 / 6088，miss 997） | 同上 |
| combined | **89.48%**（(15860+5091)/(17325+6088)） | 同上（`totals.percent_covered`） |
| 模块数 | 57 | 同上 |
| 运行元数据 | `head=a572607…`、`dirty=true`、`worktree_diff_sha=806874d…`、Coverage 7.16.0 | `evidence/cov-main/run-meta.json` |
| 未覆盖分类 | 见 `coverage-pack/`（本轮分类脚本产物，未在本表内冒充"已解释"） | `coverage-pack/coverage-rules-auto.json` |

> 口径说明：① **唯一权威口径 = `coverage-main-strict.json`**（`--branch --source=src` 逐层/逐套件合并后 `coverage json --strict`）；
> 同目录 `coverage-main.json`（非 strict）比 strict 多 14 条语句，**不得混引**（红队 REVIEW-C #7 已把"双口径流通"标为问题）；
> ② 与历史 67.19%/50.38%（本轮早前更窄的口径）、79.31%/69.88%（第七轮，合并 ssh/paramiko/supervisor/register 定向运行）、
> 86.60%/77.39%（再合并真机）**都不可比**——引用时必须带文件与时间；③ **不声称 100%**：本数字只说明"这批用例覆盖到的语句比例"，
> 未覆盖的 1465 行里包含被缺陷阻塞/环境阻塞的模块，明缺口见 §7 与 `coverage-pack/`。

## 6. 本轮缺陷（全部有红灯钉住或口径声明）

| ID | 层 | 状态 | 一句话 | 钉住物/证据 |
|---|---|---|---|---|
| P-078 | 上层 schematic | 待设计修 | `place_wire` 样式参数（width/color/line_style）与 spec 不符 | 半真机探针红 |
| P-079 | 中层 配置 | 待设计修 | local 联合端口显式双值不等被静默归一化 | 离线 strict xfail（需平台门控） |
| P-080 | 上层 verilog/veriloga/**symbol/layout 截图** | 待设计修 | `view_type` 不校验（read 静默接受；symbol/layout 截图对 bogus 也成功） | 离线 4 strict xfail + `screenshot_params_e2e_tests.py` SC-06 红钉（symbol/layout） |
| P-081 | 中层 SSH | 待设计修 | 远端 POSIX 路径被 `Path()` 改写 | 离线 strict xfail（Linux 侧 XPASS，需门控） |
| P-082 | 上层 + 口径 | 待设计修 | region 两点 vs 四元组口径漂移（三处请求面） | 离线 strict xfail + 探针 |
| P-083 | 上层 spectre | 待归属 | `export.precision` 语义未定义（实现=有效数字） | TB 按实效钉住 |
| P-084 | 上层 maestro | 待设计修 | `export.include_results` 死参数 | 半真机探针红 |
| P-085 | 上层 layout | 待设计修 | `layout.read(depth>0)` + region 任何写法都失败 | 探针红 + 离线 xfail |
| P-086 | 底层/中层 | 观察（根因见 P-095） | 多用户同视图后 / maestro run 后 `Empty response`（30–90s 自愈，模态框形态可 >2 分钟不自愈） | 探针 4/4 + 终版 gate 第 3 次复现 |
| P-087 | 上层 maestro | 待设计修 | `save=False` 改动被后续 save 静默带走 | 磁盘级探针红 |
| P-088 | 上层 maestro | 待设计修 | `delete_var(scope=all)` 确定性 handle 0 | 红灯探针 + scope 矩阵 |
| P-089 | 上层 maestro | 待设计修 | `open_waveform_gui.result` 死参数 | 红灯探针 |
| P-090 | 中层传输 | 观察 | upload 安装步骤偶发 `mv: cannot stat <stage>`（校验通过后 stage 消失；复跑与 40 次 hammer 均绿） | 原始日志 + 复跑对照 + hammer 不入册脚本 |
| P-091 | 上层 symbol/layout | 待决策 | 截图远端产物策略三包不一致（schematic 保留 / symbol+layout `rm -f`），spec 写「远端存 role root screenshots/」 | 新 TB SC-01 的 `remote_present` NOTE + `find` 0 命中 |
| P-092 | 上层 calibre | 待设计修 | `power`/`ground` 声明并校验但实现从不读取（静默无效，与 P-084 同类） | 真机 job.json/argv/报告三者无差异 |
| P-093 | 上层 calibre | 待设计修 | `hier=False` 仍追加 `-turbo` → Calibre 判非法、打 usage、作业秒退 | 半真机探针红 + drc.log 原文 |
| P-094 | 上层 calibre | 待设计修 | 工具秒退不被检测：`status=unknown`/`failure_kind=null`，`blocking=True` 等满 timeout | 同上探针（`tool_failed=true` vs `error_surfaced=false`） |
| P-095 | 上层 maestro | 待设计修 | **P-086 的 P1 根因**：悬空 Overwrite History → `ASSEMBLER-3018` 模态框阻塞 CIW，watchdog 不处理 | 子代理现场（CDS.log 22:48 + 8×15s 空响应） |
| P-096 | 上层 maestro | 待设计修 | 陈旧 OA 写锁（属主进程已死）触发 `axlOpenInRead0` 模态框 → CIW/daemon 再挂死；应结构化失败或自动强制 | 子代理探针（P-086 第二类根因） |
| P-097 | 上层 verilog | 观察 | 覆盖式再导入后紧跟的 `_read_views` 偶发 `*Error* cell not found`（1 次；随后 2/2 复跑成功） | verilog 导入 TB 的 `failure` 字段原文 |
| P-098 | 上层 calibre | 待设计修 | `blocking=true` 超时未按 spec 返回 `status=timeout`，而是回最后一次 `running/unknown` | 子代理卡片（与 P-094 互补：一个错在检测、一个错在枚举口径） |
| P-099 | 上层 verilog | 待设计修 | `virtuoso.verilog.import` 返回值 `views` 恒为空（真机已有 functional/symbol/netlist）| IMP-08 红钉 + 同 SKILL 离线解析可用的对照 |
| P-100 | 上层 verilog | 待设计修 | `import` 的 `cell` 参数不参与落地（ihdl 按源码顶层模块名建 cell）；不同名即整体报 `cell not found` 且**写已发生** | IMP-10 红钉 + mtime 23:12:45→23:13:22 实测 |
| P-101 | 上层 verilog | 待决策 | `overwrite=False` 对已存在 cell 返回成功但**什么都没写**，且无 skipped/existing 标记（静默 no-op） | **IMP-07 红钉**（mtime 证明未写入 + 断言"必须带跳过标记"→ 当前红）；红队 REVIEW-B #3 指出的"无红灯"已修 |
| P-102 | 上层 calibre | 待设计修 | `pex` 第三阶段 argv 非法（`-fmt spice`，Calibre 只认 `-fmt -<flag>`）：stage1/2 成功、stage3 打 usage → PEX 整体不可用（spec 已标「禁止交付」，roadmap P0-1 要求改官方 batch） | 实验 run_dir 三份 stage 日志 + `pex.log` 的 `stage3_failed`；TB 的 PEX-01 红钉 |

## 7. 明缺口 / 不覆盖声明（防"虚高"）

| # | 未覆盖项 | 现状 | 说明 |
|---|---|---|---|
| G1 | **蒙特卡洛驱动** | 无实现（P-070 待产品口径） | 只有"读回 MC 结果"的解析用例；MC 实验还留下过共享库 run_mode 污染（已恢复） |
| G2 | **后仿 / PVT** | 口径更正（红队 REVIEW-B #7） | **无寄生后仿对照已做**：`evidence/round8/postsim-evidence.json`（15:05）显示"提取版图网表（无寄生）前/后对照 verdict=match，max ΔV=8.1e-5"；**带寄生的 PEX 未通**（P-034/P-098/P-102 家族）；**PVT 未做**。三者不得混写成"本轮只做前仿" |
| G3 | **真实 100 台机器** | 用 100 个协议级 fake 替代 | scale-100 是 fake fleet；真机侧只有 8 实例 |
| G4 | **>2 跳拓扑** | 2 跳 + SOCKS5 叠加已测（multihop 10/10） | 3 跳以上未测 |
| G5 | **自建版图的 LVS `correct`** | 仅在复用既有真实版图时成立 | 本轮新增：源网表由产品数据生成（`lvs_from_schematic_tb`，CMP_LIB/cmp_top）→ **CORRECT**；但**版图本身不是桥自建布线**（自建版图仍 `incorrect`）。要闭合需"桥 write 出带布线/端口的版图 → LVS correct" |
| G6 | **Linux 客户端包/流程层未跑** | 本轮新增：Linux 客户侧全栈跑 base 五接口 + 文件族 **6/6**（§4.5）；离线层 py3.9 与 py2.7/3.6 探针已绿 | 仍差：Linux 客户端下跑 11 套包 E2E / flows（多用户、ADC、SerDes）——这些 TB 硬编码 `127.0.0.1:8127 + vb-vblog`，需逐个加 `--api/--token` 覆盖（`infra_e2e_tests.py` 已加，可作样板） |
| G7 | **子进程覆盖率** | 未合并 | `supervisor.py` 等被监督体跑在子进程，当前口径低估（R7-O-11） |
| G8 | **GUI"点击级"交互** | 仅探针级（窗口定位 + 截图 parity） | 无真实鼠标点击/对话框流程用例（模态框类问题靠探针与 X11 工具兜） |
| G9 | **host-key 轮换 TB（P5）** | **TB 未落地** | 测试侧接口已就绪（`w4_hostkey_cycle.sh` status/use-a/use-b/restore + 常驻说明）；设计侧未写 TB |
| G10 | **maestro 多 corner 扫描整链** | 仅有包级 e2e 与历史探针 | 本轮未做"多 corner 扫描 + 结果比对"整链 |
| G11 | **`layout.read(depth>0)`** | **确定性不可用**（P-085） | 已红钉；在修复前该参数组合记"未覆盖（被缺陷阻塞）" |
| G12 | **calibre.export / calibre.pex** | export 已覆盖；pex 被缺陷阻塞（P-102） | `calibre_export_pex_e2e_tests.py`：ENV-01 / EXP-00 / **EXP-01（all_small 三类产物齐）** / **EXP-02（summary 对 LVS run_dir）** 绿；**PEX-01 红** = P-102（stage1/2 成功、stage3 argv 非法）。口径补充：`spec/…/12-calibre.md:7` 已写「`calibre.pex` 未按官方三阶段验收，禁止用于交付/签核」，`spec/research/calibre/00-下一步开发方向.md` P0-1 要求改官方 batch —— 即 **PEX 的 deck 模式本轮按"禁止交付 + 已钉死"处理，不冒充已覆盖** |
| G13 | **calibre 参数面剩余 11 条** | 部分覆盖（见 §3） | 已覆盖：calibre_bin/hier/turbo/poll_interval/job_id/params/run_dir/cdl? 与 lvs 的 spice/hcell/xcell、read_results.log_lines（`calibre_params_e2e_tests.py` 5/5）。**仍未覆盖**：`drc.runset`（set 模式真跑）；**kind 不适用（不构成缺口）**：`drc.spice_file/hcell_file/xcell_file/fmt/lvs_run_dir`、`lvs.fmt/lvs_run_dir`（argv 只在 lvs/pex 分支消费）；**死参数红钉**：`drc/lvs.power/ground`（P-092） |
| G14 | **verilog.import 参数面** | **已清零**（本轮补） | `verilog_import_params_e2e_tests.py` 10 绿 + 2 红钉（P-099/P-100）；`import_lib_cells` 只做到"被接受"——「库内 cell 导入」需另写引用 basic 库的源文件才可观察，**该语义仍未覆盖，如实声明** |
| G15 | **screenshot 远端产物留证** | P-091 待决策 | 实测只有 schematic 留远端；symbol/layout 清理 → 审计无法从远端复核三包截图（本地 PNG 均有） |
| G16 | **`add-本版范围与明确不支持.md` 的 13 项"明确不做"** | **红队点名的 3 项已补离线契约** | 该文档不在 `extract_spec_clauses.py` 的 13 份 NORMATIVE 输入里，故矩阵没有它的行。红队 REVIEW-B #6 点名的 3 项已有机器判据：`test/offline/unit/test_scope_exclusions.py`（4 例，全绿）——①CLI 无 `--profile/--env/--migrate` 旧迁移入口、②`pyapi/server/register/common.profile` 模块不存在、③`server.dispatch/api_server` 无 `task_pool/wait_pool/job_pool` 等公共入口、④`pyapi.models`/`register.models` 无 `signature/hmac/signed` 字段 |

## 8. 环境与过程（本轮踩坑记录）

- 8127 是 standalone：**改 `src/` 后必须重启**，否则探针读旧代码（本轮两次踩到）；
- 共享库 `maestro_tb/rc_probe` 被 MC 实验改成 `Monte Carlo Sampling` → 常规 run 产出 MC 布局、waveform 读回失败（已恢复）；
- 并发纪律：三个子代理各自起过重叠 runner（两名并发 `run_all_http`、semi 探针与 live 套件互相打断 maestro 会话）→ 已收敛为单 runner 并记录在案。
- **calibre 参数面的教训（P-093/P-094 的发现路径）**：`hier=False + turbo` 组合让 Calibre 秒退，
  而桥的轮询只看"报告是否出现" → 一次 TD 实测挂满 5 分钟才被人工 kill。
  结论写进 §7/G13：**凡是"工具可能秒退"的参数组合，TB 必须自带宽限轮询或走非阻塞 + `status`**（本 TB 的 LVS 用例已改成这种形态）。
- **vblog 实例硬重启 SOP（本次实战补全，供 Runbook 收录）**：
  ① 现象：`basic.skill.execute 1+2` 连续 `Empty response`，`run/CDS.log` 末尾有 `# Displaying modal dbox "adexlMessageDialog"`（P-095 形态，不自愈）；
  ② 按 PID `kill -TERM`（必要时 `-KILL`）旧 `virtuoso -cdslib ./cds.lib` 与 `ramic_bridge_daemon_3.py … 65121`，确认端口释放；
  ③ 在 `~/.virtuoso-bridge/vblog/run` 下：`DISPLAY=:11 nohup virtuoso -cdslib ./cds.lib -log ./CDS.log &`——**必须**先
     `source /etc/profile.d/zz-cadence.sh` 并显式补 `LD_LIBRARY_PATH`（含 `IC618/tools/dfII/lib/64bit` 等），否则报
     `libap_sh.so: cannot open shared object file`；
  ④ `run/.cdsinit` 会自动 `load(setup/virtuoso_setup.il)`，daemon 随 CIW 起来（本次 45s 内 65121 恢复 LISTEN）；
  ⑤ 冒烟：`basic.skill.execute 1+2 == 3`（本次已通过）。**注意**：这次事故是 P-095 的真实复现，不是环境噪声。
- **注册 TB 禁止并发**（2026-09-29 00:28–00:40 实测教训）：root 与子代理同时对 `wsl-gent`+`w1-gent` 跑 role-split 时，
  两边的短连接风暴互相挤压 → 一边报 `ssh … ss/hostname timed out after 20–30s`、另一边撞上
  `credential reuse requires enhanced_token`（复用了对方刚建的 work-dir 凭据）。**单跑结果 29/29**（`registration-role-split-r8b.json`），
  被并发污染的三份产物已移入 `evidence/round8/superseded/`，不得引用。→ 纪律：同一时刻只允许一条注册 TB 占用这两台靶机；
  复用 work-dir 前必须清空 `registered_users`。

## 9. 复现入口（节选）

```powershell
python -m pytest test/offline -q -p no:cacheprovider
PYTHONPATH=src python test/shared/runners/run_semi_probes.py --group all
PYTHONPATH=src python test/live/packages/maestro_e2e_tests.py --transport http
PYTHONPATH=src python test/live/packages/spectre_params_e2e_tests.py --transport http
PYTHONPATH=src python test/live/packages/layout_geometry_classification_e2e_tests.py
PYTHONPATH=src python test/live/packages/screenshot_params_e2e_tests.py --transport http \
  --token vb-vbuser2 --lib serdes_rx --cell rx_top --view schematic --kind schematic   # 另有 --kind symbol / layout
PYTHONPATH=src python test/live/packages/infra_e2e_tests.py --transport http \
  --api http://127.0.0.1:8127/api/operation --token vb-vbuser2 --work-dir <linux 侧 env-live>  # Linux 客户端车道
python test/shared/runners/audit_atom_coverage.py
python test/shared/runners/build_op_param_matrix.py
```

## 10. 红队评审（独立子代理）

- 任务书：`test/reports/round8/red-team-brief.md`（8 条必查清单）。执行方：独立子代理 `/root/verilog_params/red_team`。
- 产出四份：
  `review-A-lite-抽查.md`（15 项分层抽样：ok 12 / overclaim 1 / 无法确认 2）、
  `review-B-遗漏审计.md`（必须补 3 / 建议补 4 / 可接受声明 7 + 42 处吞异常扫描）、
  `review-C-数字复核.md`（12 项一致 / 8 项不符或口径冲突）、
  `review-D-direct全量抽样.md`（brief #1 全量补做：42 条 direct 语义核验，g1–g6 每簇 7 条，seed=4092；**36 ok / 6 需处置**）。
- **brief #1 已补齐**：A(15) + D(42，去重) = **57 条 direct 人工语义核验**，覆盖 6 簇。
- **红队发现与处置（本报告已同步）**：
  1. **A-上层#043 overclaim（高置信）**：原引用 `test_middle_contracts.py`+`test_pyapi_packages.py` 里根本没有 checksum/重试断言。
     → 已改为 `test_tunnel_transfer.py::test_upload_checksum_mismatch_does_not_move_stage` / `::test_verify_mismatch` +
     `test_ssh_edges.py::test_retryable_predicate_matrix`（矩阵 md+json 同步）。
  2. **C-N1/N5/N6/N7/N8**：11/11 vs 10+1、离线 2456 vs 1800、压测 216 vs 108、A 轴 219/9 vs 222/6、覆盖率双口径 —— 本报告逐条更正（§0/§1/§4.3/§4.4/§5），
     maestro 的 23/23 原始日志已从 `tmp/` 归档到 `evidence/round8/maestro-23of23-2128.log`。
  3. **C-N4**：半真机"7 条全是断言红"表述过强 → 已按实测改为"5 条断言红 + 2 条前置失败（红证在 standalone 复跑）"（§4.3）。
  4. **C-N9**：原子覆盖双文件 + `write_without_readback` 12/11 → 已在 §2 注明引用文件与差异原因。
  5. **B-#3 P-101 无红灯** → IMP-07 已改为**强断言**（未写入却返回 completed 必须带 skipped/existing 标记；当前红）。
  6. **B-#1 calibre.pex 未立卡/矩阵未重建** → 已立 **P-102**（stage3 argv 非法，含三阶段日志证据）并重建矩阵（NO-OP-TB 归零）。
  7. **B-#7 后仿/PVT 口径** → §7 G2 已改为"无寄生后仿对照 match；带寄生未通；PVT 未做"。
  8. **B-#6 "明确不做"清单未登记** → §7 G16 已按 na（范围声明）登记 3 项，不假装覆盖。
- **原两处残留（已补齐，2026-09-29 00:5x）**：① brief #1 的 ≥40 条全量抽查（review-D 完成 42 条，§上）；② B#6 的低成本离线契约 —— `test/offline/unit/test_scope_exclusions.py` 4 例覆盖旧入口/pending/HMAC 缺失（§7 G16）。
- **review-D 六项处置**（逐条落地，均已复跑）：
  1. `总览#175`（RS 终止字节无显式断言）→ 在 `test_daemon_handler.py` 成功/NAK/日志三条路径补 `raw.endswith(RS)` 显式断言（19/19 绿）。
  2. `总览#206`（跨 token 不共用未断言）→ 矩阵证据补 `test_multi_user_isolation.py::test_two_users_route_to_their_own_daemons`（`assertIsNot(_skill(tok-a), _skill(tok-b))`）。
  3. `并发#022`（Skill 专用隧道未计入通道数）→ `test_endpoint_budgets.py` 新增 2 例：隧道存活时占用 1 条 daemon 通道；建隧道失败必须归还租约（7/7 绿）。
  4. `日志#045`（reason 声称的 64KB 默认值测试不存在）→ `test_registry_more.py::test_cdslog_defaults_and_bounds` 断言 `log_level="all"`、`log_max_bytes=65536`、非法值拒绝。
  5. `控制面#011`（`src/...:991` 引用形式）→ 行为已由 `TestRegistrationBindsLoopback` AST 断言覆盖；`src/` 锚点本就不在仓库证据检查器范围内，按形式项记录，不改判据。
  6. `layout#180`（`pos` 写 point vs `list(x y)`）→ spec 的 `point（7:8）` 是类型记号，实现 `list(x y)` 即 SKILL point 值；真机写入/读回全绿，**口径措辞级**，登记不改实现。
- 红队结论：**未再发现"整行假覆盖"**；剩余为设计侧待修的已立卡缺陷与显式声明的环境/能力缺口（§7）。
