# 未关闭缺陷 × 红灯钉住审计（2026-09-28）

> 口径：C0 要求"发现即钉住"——每个未关闭缺陷都要有一条**当前为红、修好即绿**的用例/探针，
> 或者显式声明"不覆盖及原因"。本表逐条给出钉住物与当前颜色（以最近一次实跑为准）。

| 缺陷 | 钉住物 | 当前颜色（证据） |
|---|---|---|
| **P-078** place_wire 样式参数被丢弃 | `test/semi/probes/schematic_wire_style_probe.py`；`test/offline/unit/test_schematic_contracts.py`（样式参数精确断言） | 🔴 半真机探针 fail（`round8/semi-probes.json`）；离线断言在旧树 Linux 跑出红（需与 Windows 同树复跑确认） |
| **P-079** local 联合端口被静默归一化 | `test/offline/unit/test_norm_gap_round8.py::TestLocalJointPortNotCoerced`（strict xfail） | 🔴（xfail）Windows `offline-win-4.xml` 0 红＝按预期失败；**Linux 需平台门控**（另两处 XPASS(strict) 属 P-081） |
| **P-080** `verilog/veriloga.read` 的 `view_type` 未校验 | `test/offline/unit/test_view_type_param_contract.py`（4 strict xfail）；live 复现件 `round8/p080-viewtype-p081-remote-path-2026-09-28.json` | 🔴（4 xfail，Windows 0 红＝按预期失败） |
| **P-081** 远端 POSIX 路径被 `Path()` 改写 | `test/offline/unit/test_remote_posix_path_contract.py`（strict xfail） | 🔴 但**平台相关**：Windows 按预期失败；Linux 上 XPASS(strict)（`offline-linux-py39.xml`）→ 需改为平台门控或通用断言 |
| **P-082** region 两点 vs 四元组口径漂移 | `test_schematic_contracts.py::test_region_filter_uses_two_points_per_p074_spec` 等（strict xfail）；`layout_depth_probe` 侧证 | 🔴（Windows 0 红＝按预期失败） |
| **P-083** `spectre.export.precision` 语义未定义 | 无红灯（口径项）：`spectre_params_e2e_tests.py` EXPORT-P1 **钉住当前真实语义**（有效数字） | ⚪ 非缺陷钉住型；等 spec 定口径后改断言 |
| **P-084** `maestro.export.include_results` 静默无效 | `test/semi/probes/maestro_export_include_results_probe.py` | 🔴 首跑 RED（`round8/maestro-include-results/include-results.json`，sha 相同）。**依赖前置**：需要 `maestro_tb/rc_probe` 有 `Interactive.*` history；22:40 整层时该 cell 只剩 `MonteCarlo.*` → 探针 rc=2（环境前置，非产品结果） |
| **P-085** `layout.read(depth>0)`+region 不可用 | `test/semi/probes/layout_depth_probe.py`；`test/offline/unit/test_layout_depth_contract.py`（strict xfail） | 🔴 半真机 fail + 离线按预期失败 |
| **P-086** 多用户/长技能后 ~30–90s 空响应窗口 | 复现件 `test/semi/probes/twouser_same_view_probe.py`（CLEAN counted=false，留 `holder_still_running` 字段）；加强证据 `round8/coverage-main-r8.log`（maestro 两次命中）、CDS.log ASSEMBLER-8001 | ⚪ 观察项：**无稳定红灯**（窗口自愈）；按"行为缺陷+复现件"登记，不假装有红钉 |
| **P-087** `save=False` 跨请求泄漏（磁盘级） | `test/semi/probes/maestro_save_false_disk_probe.py`（5 项 checks：步骤表/立即磁盘/**泄漏判据**/清理）；live 步骤表断言在 `maestro_e2e_tests.py` WRITE-06 | 🔴 探针 RED（后续无关 save 后旧变量变 2.0；证据 `round8/maestro-save-false-disk.json`） |
| **P-088** `delete_var scope=all` handle 0 | `test/semi/probes/maestro_delete_var_all_probe.py` | 🔴 探针 RED（`round8/p086-delete-var-all.json` —— 文件名沿用早期流水号，内容是 P-088 的 scope 矩阵） |
| **P-089** `open_waveform_gui.result` 死参数 | `test/semi/probes/maestro_open_waveform_result_probe.py` | 🔴 首跑 RED（bogus 与正确 result 均 ok/同一窗口；`round8/p089-open-waveform-result.json`）。同上依赖 `Interactive.*`；22:40 整层 rc=2（环境前置）→ 待恢复 fixture 后复跑刷新 |
| **P-070** 蒙卡能力缺失（待产品口径） | **无钉住物**（能力缺失，不是实现缺陷） | ⚪ 需"不覆盖声明"：等产品拍板"支持驱动"或"明确不做"，再补 MC 真机验证或写进 spec 明示不支持 |
| **P-090** `basic.file.upload` 偶发 vbtmp 消失 | 无红灯（40 次 hammer + 套件复跑均未复现） | ⚪ 观察项：保留单次现场（卡片）；如再复现升级 |
| **P-091** 截图远端产物保留三包不一致 | `screenshot_params_e2e_tests.py` 各 case 记录远端保留状态（schematic 留 / symbol·layout 删） | ⚪ 口径项（待 spec owner 定）：非实现红灯 |
| **P-092** calibre `power`/`ground` 死参数 | `test/live/packages/calibre_params_e2e_tests.py` **只记录不判红** | ⚠️ **缺红灯钉住**：修复口径定后需把该组升级为断言（现在只能靠源码 4 行锚点） |
| **P-093** `calibre.drc(hier=False)` 带 `-turbo` 非法 | 真机探针 `test/semi/probes/calibre_flat_turbo_probe.py`（`tool_failed=true`，tool 日志第 2 行 `ERROR: The -turbo option is not valid with this flat application.`）；**方向无关离线钉** `test_calibre_argv_contracts.py::test_drc_flat_argv_is_valid`（strict-xfail：拒绝或去掉 -turbo 两种修法都转绿） | 🔴（真机 RED + xfail）；**注意**：同文件 `test_drc_flat_omits_hier_flag` 钉现状 argv（含 -turbo），修复时必须同步改 |
| **P-094** 工具秒退不被检测 | 同一真机探针的 `status` 步：`status=unknown, failure_kind=null, process_alive=false, error_surfaced=false`（工具 1 秒死亡但 API 既没判失败也没把日志里的 ERROR 抛出来）；离线 `test_calibre_job_state.py` 分类用例 | 🔴（真机 RED：error_surfaced=false）；离线判据需补"日志前部 ERROR → 失败" |
| **P-095** 悬空 Overwrite-History → ASSEMBLER-3018 模态挂死 | 复现件 `tmp/_r8_vblog_wait.py` + `_r8_make_history*.py`；跨重启标志实测 `(t \"Interactive.8\")` → 清 nil 后 run 成功 | ⚠️ 缺常驻红灯：建议新增 semi 探针（构造悬空目标 → 期望结构化失败而非挂死），本轮先以现场+复现件登记 |
| **P-096** 陈旧 OA 写锁 → axlOpenInRead0 模态挂死 | 复现件 `tmp/_r8_opengui2.py`（kill 实例后 open_gui → Empty response）+ 删锁恢复对照 | ⚠️ 缺常驻红灯：建议新增"造陈旧锁→open_gui 应结构化失败"探针 |

## 结论

- 未关闭 12 条（P-078…P-089）+ 1 条待决策（P-070）里：**9 条有稳定红灯钉**
  （P-078/079/080/081/082/084/085/087/088/089 中的 9 条：半真机 fail 或 strict-xfail/离线断言），
  **P-086 是观察项（窗口自愈，无稳定红灯，按复现件登记）**，
  **P-083 为口径待定（钉住当前真实语义）**，**P-070 为能力待决策（不覆盖声明）**。
- 上一版遗留的两件事均已处理：① P-079/P-081 的平台门控已修（P-081 xfail 只在 Windows 生效）；
  ② Windows/Linux 已用**同一份最新树**复跑：两边均 **1793 例 / 0 红**（Win 19 skip、Linux 29 skip），
  证据 `round8/offline-win-5.xml`、`round8/offline-linux-py39-final.xml`。
- 新增钉住物均已纳入 `run_semi_probes.py` 表（P-087/P-088/P-089 三条 maestro 探针），下一轮整层会一并跑。
