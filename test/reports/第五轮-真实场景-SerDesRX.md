# 第五轮 · 真实业务场景（SerDes RX 全流程）— 现状与产出

> 目的：回答"接口不是只会返回 ok"——用一条**贴近用户实际用法**的差分模拟链路，
> 把库/原理图/symbol/层次/版图/GDS/前仿全走一遍，判据是**测出来的数**。
> 执行者：root ｜ 2026-09-23 20:30–21:00 ｜ 实例：calprobe（PDK tsmcN65，daemon 65122）
> 场景脚本：`test/live/flows/serdes_rx_flow_tb.py` ｜ 证据：`test/artifacts/evidence/round4-scenario/serdes/`

## 1. 场景设计（5 Gb/s 差分 RX 前端）

| 单元 | 内容 | 真实度 |
|---|---|---|
| `inv_buf` | 单级 CMOS 反相器（PDK `pch_25`/`nch_25`），输出缓冲；给 DRC/LVS 留一个语义完整的子块 | PDK 器件 + 真实 pin/net |
| `ctle_core` | 有源 CTLE：差分对 M1/M2（`nch_25`）、尾电流 M3、负载 R1/R2=500Ω、源极退化 RS=50Ω∥CS=1p | 典型 RX 前端的连续时间均衡器 |
| `rx_term` | 50Ω 差分端接 + 共模 `vcm` | 接收端输入端接 |
| `rx_front` | 顶层：`rx_term` + `ctle_core` + `inv_buf` + 20fF 负载电容，**层次化实例** | 真实工程的组织方式 |

命令（可复跑）::

    python test/live/flows/serdes_rx_flow_tb.py --stage all --skip cdl      # 9 阶段（CDL 见 §4）
    python test/live/flows/serdes_rx_flow_tb.py --stage sim                 # 只跑前仿

## 2. 结果（本轮，干净会话）

| 阶段 | 结果 | 关键证据 |
|---|---|---|
| probe | ✅ PDK/analogLib 可见、端子表（`nch_25`: S/G/B/D；`res`,`cap`: PLUS/MINUS） | `serdes-probe.json` |
| lib | ✅ 建库 `SRX65`（绑定 `tsmcN65`），路径在 file role root 下 | `serdes-lib.json` |
| buf / ctle / term | ✅ 原理图写入 + `check_and_save` + symbol 生成 | `serdes-buf.json` / `serdes-ctle.json` / `serdes-term.json` |
| **连通性判据** | ✅ `ctle_core` 10 条网络逐条比对（如 `tail = M3.D + RS1/RS2 + CS1/CS2`、`s1 = M1.S + RS1 + CS1`）**0 处不符** | `serdes-ctle.json: value.net_mismatches = {}` |
| top（层次） | ✅ 实例母单元 `XTERM/XCTLE/XBUF = SRX65/rx_term|ctle_core|inv_buf`；`vinp/vinn/outp/outn/rxout` 等网络连接全部符合预期 | `serdes-top.json` |
| layout | ✅ `ctle_core`/`inv_buf` 版图视图 + 3 个 PDK 器件实例 + M1 走线/标签，读回 3 instances | `serdes-layout.json` |
| **GDS（P-051 口径）** | ✅ A 目标目录已存在：ok；**B 目标父目录不存在（新目录）：ok，远端 `4096 B`** —— P-051 修复在业务场景下复验通过 | `serdes-gds.json` |
| **sim（AC+TRAN）** | ✅ 两个分析都 success；AC 指标：**增益 5.055 dB @1 MHz、5.409 dB @2.5 GHz（峰化 +0.354 dB）、3 dB 带宽 15.8 GHz**；TRAN：outp 1.663→2.059 V（摆幅 396 mV） | `serdes-sim.json` |

> 仿真用真实 PDK 模型（`cor_25.scs` section=tt_25，2.5V 器件，L 取设备允许的 280n），
> 判据写成"数值区间 + 单调/峰化关系"，不是"接口 ok"。

## 3. 本轮由该场景**新发现**的三条缺陷

| ID | 一句话 | 证据（可复跑） |
|---|---|---|
| **P-052** | `schematic.set_instance_params` 改的是**母单元 cell 级 CDF 默认值**（`analogLib/res.r` 1K→777、`nch_25.w` 400n→3u），会话内可见 | `test/semi/probes/shared_cdf_pollution_probe.py` → `round4-probes/round4-shared-cdf-pollution.json` |
| **P-053** | AC 链路两处断：解析器只认分析名 `ac`（`ac1` 直接丢数据）；且解析键带 `ac_` 前缀而 measure 默认 `x="freq"` | `test/semi/probes/spectre_ac_pipeline_probe.py` → `round4-probes/round4-spectre-ac-pipeline.json` |
| **P-054** | 层次化 `symbol.generate` 残留**子单元 symbol view**，同会话二次生成必报 `target symbol is open`（场景连跑第二次即失败） | `test/semi/probes/symbol_generate_hierarchy_handle_probe.py` → `round4-probes/round4-symbol-hierarchy-handle.json` |

细节与影响面见台账 [问题登记.md](问题登记.md) 的"第五轮新增"一节。

## 4. 未打通 / 明确不算覆盖

1. **CDL → LVS**：`si -batch`（auCdl）在本环境对 PDK 器件即失败
   （`hnlCDLParamList`/`hnlCDLFormatInst` 属性缺失），`inv_buf` 这种 PDK-only 单元也一样红；
   既有 `test/live/flows/project_flow_tb.py` 的 cdl 阶段证据（`test/artifacts/env/scenario-project65/evidence-cdl-inv2.json`）
   同样是 `si_rc=255` ⇒ **S11 的 lvs 从未真正跑通，之前只被 P-051 掩盖了一半**。
   需要设计侧给出"网表/CDL 导出"的可用路径（或在 spec 里写明 LVS 前置条件），否则 calibre.lvs 永远缺输入。
2. **DRC**：本场景自身的版图（`serdes-gds.json`）**没有**跑 `calibre.drc`（TB 里是 `--with-calibre` 可选段）。
   真机 `calibre.drc` 链路本轮已由 s11 包**首次打通**（对 `s11_inv/inv.gds`：1737 rulechecks、
   产出 36 条结果、`DRC_RES.db` 落盘，证据 `round5-main/calibre-drc.json`），
   但**结果读取解析不可用**（逐规则计数空、offenders 取到头部告警 → P-059/P-062），
   因此本报告不声称任何设计"DRC 通过"。
3. **ADC 场景**：**本轮已补齐**（原写作"下一轮候选"）——见 `第五轮-真实场景-ADC.md`：
   比较器原理图/版图/GDS + VerilogA SAR 控制，7/7 阶段绿、`round5-adc-sar.json` 判定 22/22
   （0.2/0.61/0.8·Vref → 码字 3/9/12，与理论逐点相等）。
   仍未做的部分：比较器与 SAR 的**混合仿**（CDAC 开关时序）、PVT/蒙特卡洛——边界写在 ADC 报告 §3。
4. **多用户协同共建**：本场景是单用户（calprobe）。两用户共建同一设计库（Gent + vbuser1/vbuser2）
   的协同用例见第五轮其它线。

## 5. 对设计与评审的请求

* P-052/P-053/P-054 三条建议按"先加 TB 红、再修绿"处理，TB 已在仓库内可直接跑；
* CDL/LVS 这条链需要**明确归属**：是产品要提供导出能力，还是环境需要预置 PDK 的 si.env/属性模板；
  在此之前，任何"LVS 通过"的结论都不应写入送审材料。
