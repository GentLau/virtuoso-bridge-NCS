# 第五轮 · 真实业务场景 #2（ADC：比较器 + SAR 逻辑）

> 延续 SerDes RX 场景（同目录 [第五轮-真实场景-SerDesRX.md](第五轮-真实场景-SerDesRX.md)），
> 这条场景盯的是 ADC 项目里最常见的两段：**模拟比较器**（PDK 器件、真实前仿）
> 与 **数字 SAR 控制**（VerilogA、码字正确性）。
> 执行者：root ｜ 2026-09-23 20:5x ｜ 实例：**vbuser1**（非 Gent 的另一个 OS 用户，daemon 65401）
> 场景脚本：`test/live/flows/adc_sar_flow_tb.py` ｜ 证据：`test/artifacts/evidence/round4-scenario/adc/`

## 1. 结果总览（7/7 阶段绿）

| 阶段 | 结果 | 关键数字 / 证据 |
|---|---|---|
| probe | ✅ PDK + analogLib 可见，cwd=`/home/vbuser1/.virtuoso-bridge/vbuser1/run` | `adc-probe.json` |
| lib | ✅ 建库 `SADC65`（绑定 tsmcN65），产物落在 **vbuser1** 的 file role root 下 | `adc-lib.json` |
| cmp（原理图） | ✅ 7 器件强臂式比较器原理图；**8 条网络逐条比对 0 处不符**；symbol 7 个端子 | `adc-cmp.json` |
| layout + GDS | ✅ 版图 + PDK 器件实例；GDS 导出到**新目录**（`gds-new/<ts>`）成功，4096 B | `adc-layout.json` |
| ctrl（VerilogA） | ✅ `virtuoso.veriloga.write` + `check_and_save`：module=`sar4_loop`，ports=`clk/rst/vin/code`，源码 920 B 往返一致 | `adc-ctrl.json` |
| **sim-cmp（真实 PDK 前仿）** | ✅ 5T OTA 比较器，±150 mV 差模：`n2 = 2.277 V`（正）vs `0.527 V`（负），**极性分离 1.75 V** | `adc-sim-cmp.json` |
| **sim-sar（VerilogA 闭环）** | ✅ 4-bit SAR 对 3 个输入逐一定量：0.2·Vref→**3**、0.61·Vref→**9**、0.8·Vref→**12**，与理论值**逐点相等** | `adc-sim-sar.json` |

## 2. 这条场景额外验证到的 spec 条款

| spec | 条款 | 本次证据 |
|---|---|---|
| `7-spectre` §run | `tasks[].include_files`：include 文件上传到 run_dir，netlist 里用 **basename** 引用 | 反证 + 正证：先用**本地绝对路径**写 `ahdl_include` → `ERROR (SFE-868) Cannot open the input file 'C:UsersuserDesktop...'`；改为 `ahdl_include "sar4_ctrl.va"` + `include_files=[本地 .va]` → 三个 run 全 success。**实现与 spec 一致**，且这条"本地路径会原样进远端"是用户最容易踩的坑，值得写进 skill/文档 |
| `12-veriloga` | 写源码 → `check_and_save` 解析 module/ports/pin order | `adc-ctrl.json`（module_name/ports 与设计一致） |
| `5-cellview`/`1-四层整体架构` §5.6 | 产物必须落在 role root 下（不是 `/tmp`、不是家目录） | `adc-lib.json` / `adc-layout.json`：库在 `/home/vbuser1/.virtuoso-bridge/vbuser1/file/adc_sar/SADC65`，GDS 在 `…/file/adc_sar/gds-new/…` |

## 3. 覆盖边界（不声称的部分）

1. **比较器不是 ADC 全链**：sim-cmp 用 5T OTA 表征"极性 + 差模响应"，
   强臂式版图/原理图（`cmp_latch`）本轮只做了设计入库与 GDS 导出，没有做后仿/DRC/LVS；
2. **SAR 是算法级闭环**：`sar4_loop` 内部用理想比较器/DAC，验证的是**码字算法**；
   与真实比较器的联合仿（含 CDAC 开关时序）本轮未做；
3. **没有做 PVT/蒙特卡洛**：单点 tt_25、单温度；
4. 与 SerDes 场景相同：**LVS 不可达**（auCdl 在本环境报 `hnlCDLParamList`，见 SerDes 报告 §4）。

## 4. 建议下一轮补的场景

* 把 `cmp_latch` 的强臂比较器与 `sar4_loop` 的码字逻辑接起来（CDAC + 开关时序），做一次真正的
  "模拟比较器 + 数字 SAR" 混合仿真，判据用**码字误差 < 0.5 LSB + 单调性**；
* 给 `cmp_latch` 补输入失调扫描（Vos）与噪声（`noise_integral` 指标），把 spec 的
  `noise_integral` 从"离线单测"推进到"真机数据"。
