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
| **P-084** `maestro.export.include_results` 静默无效 | `test/semi/probes/maestro_export_include_results_probe.py` | 🔴 半真机 fail（sha 相同） |
| **P-085** `layout.read(depth>0)`+region 不可用 | `test/semi/probes/layout_depth_probe.py`；`test/offline/unit/test_layout_depth_contract.py`（strict xfail） | 🔴 半真机 fail + 离线按预期失败 |
| **P-070** 蒙卡能力缺失（待产品口径） | **无钉住物**（能力缺失，不是实现缺陷） | ⚪ 需"不覆盖声明"：等产品拍板"支持驱动"或"明确不做"，再补 MC 真机验证或写进 spec 明示不支持 |

## 结论

- 8 条实现/口径缺陷里 **6 条已有真红钉住**（P-078/079/080/081/082/084/085 中的 6 条半真机或离线），
  2 条属"口径待定"（P-083）与"能力待决策"（P-070），按矩阵记"不覆盖声明"而非假装覆盖。
- 需要在最终复跑中处理的两件事：① P-079/P-081 离线 pin 的**平台门控**（Linux XPASS）；
  ② 用**同一份最新树**重跑 Windows + Linux 两份离线 XML（当前两份树版本不一致）。
