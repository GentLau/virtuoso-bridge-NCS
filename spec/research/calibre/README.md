# Calibre 业务包：调研与开发记录

> **状态：暂缓开发（2026-09-28）**｜口径（规范性）见 [`spec/design-concepts/上层/12-calibre.md`](../../design-concepts/上层/12-calibre.md)
> 本目录只放**依据与记录**，不构成规范；与 spec 冲突时以 spec 为准。
> 下一步怎么走：见 [00-下一步开发方向.md](00-下一步开发方向.md)。

## 为什么暂缓

方向在 2026-09-24 被纠正并达成一致：**Calibre 侧不自己理解参数**——
参数合并交给官方入口（`calibre -gui -<app> -runset <set> -batch`），
本包只做**发起/轮询 + 结果分析**。手写"runset 键 → SVRF 语句"映射的做法已被删除
（真机代价见 [03 §11.1](03-网表导出机制调查报告.md)）。

暂缓的具体原因：

1. **PEX 必须先重做**：官方 PEX 是三条命令且修饰符属于"内容"
   （`-pdb -rcc` / `-fmt -all -xcell hcells`，用错会得到 702/0 vs 912/540 的电容差异），
   本包现有手写三阶段 argv 与官方不一致 → **PEX 未验收，禁止用于交付/签核**；
2. **等外部资产**：真机侧需要一份**可用的 PEX set + 输入数据**（layout GDS / 源网表 / hcell）
   才能做"与 GUI 逐字节一致"的验收；
3. 其余能力（DRC/LVS/export_cdl/set 直驱）已可用，先冻结在现状态，不再加功能。

## 现状一览（截至 2026-09-28）

| 能力 | 状态 | 证据 |
|---|---|---|
| `check_env`（工具事实来自注册表 per-role 用户组） | ✅ 真机验证 | 常驻套件 `ENV-01` |
| `drc`（deck + 白名单占位符改写；官方 CLI） | ✅ 真机验证 | `DRC-01/02` |
| `lvs`（同 DRC，另收 `cdl`） | ✅ 真机验证 | `LVS-01` |
| `export_cdl`（官方 auCdl：`si -batch -command netlist` + `checkCAPPERI=nil`） | ✅ 真机验证 | `EXPORT-01`、`LVS-02`（→ LVS `correct`） |
| `runset` 直驱（官方批处理 `-gui -<app> -runset … -batch`） | ✅ LVS 真机验证；DRC/PEX 未单独验证 | `SET-01`（产物含 Calibre 生成的 `_calibre.lvs_`） |
| `read_results` / `export`（报告解析、产物下载） | ✅ DRC/LVS 验证；报告改名也能解析 | `test/offline/unit/test_calibre_*.py` |
| `pex` | ⚠️ **未验收（argv 与官方不一致）** | 见 [00](00-下一步开发方向.md) P0-1 |

真机套件：`python test/live/packages/calibre_e2e_tests.py --transport direct`（2026-09-24 实测 **8/8**，
`VB_CALIBRE_REQUIRE_LVS_VERDICT=1`）。
离线：`test/offline/unit/test_calibre_*.py`（**68** 用例）。
环境：wsl-gent / token `vb-vblog` / 65nm PDK（`CRN65GPNEW`）/ Calibre v2025.1_16.10。

## 资料索引

| # | 文档 | 内容 |
|---|---|---|
| 00 | [00-下一步开发方向.md](00-下一步开发方向.md) | **恢复开发时的第一份读物**：P0/P1/P2、验收判据、开放问题 |
| 01 | [01-调研与方案.md](01-调研与方案.md) | 2026-09-22 首轮调研：环境、三段流程实跑、6 个硬缺口、实现路线 |
| 02 | [02-可行性报告.md](02-可行性报告.md) | 真机可行性：DRC 1737 规则 / LVS 报告解析 / xRC 三段、job 形态与判据 |
| 03 | [03-网表导出机制调查报告.md](03-网表导出机制调查报告.md) | 源网表从哪来：Calibre 不产源网表 → 官方 auCdl 链路、`checkCAPPERI` 根因、runset/control-file 实测（§9/§11） |
| 04 | [04-官方运行机制-外部报告-2026-09-24.md](04-官方运行机制-外部报告-2026-09-24.md) | **业务环境（212/189，Calibre 2023.2 + SMIC40）穷尽版报告**：CI=runset→控制文件翻译器、三条引擎命令原文、修饰符对照实验、batch 复现逐字节一致、runset 两种格式、产物清单与踩坑 |
| 05 | [05-需求-对顶层中层的支持.md](05-需求-对顶层中层的支持.md) | 曾向顶层/中层提的支持项（R1–R3 已作废，R4–R6 为文档性建议） |

代码：`src/pyapi/packages/calibre.py`、`src/pyapi/packages/_calibre_util.py`
测试：`test/live/packages/calibre_e2e_tests.py`、`test/offline/unit/test_calibre_*.py`、`test/semi/probes/calibre_*.py`

## 三条不可动摇的结论（恢复开发前先记住）

1. **引擎只认控制文件**：runset 只在 CI 层有意义；CI 把它现译成 `_<rules>_` 控制文件
   （`#!tvf` + `tvf::VERBATIM{…}` + 末尾 `source "<PDK deck>"`）再 spawn 引擎。
   → 我们要么用官方入口翻译（首选），要么直接拿现成控制文件，**不要自己翻译**。
2. **batch 不做 Virtuoso 导出**：布局/网表必须是现成文件（我们的 `layout.gds` 产的是 GDSII，
   可以直接填 `xrc.layout.layoutFile.value`；源网表用 `export_cdl` 的产物填 `xrc.source.sourceFile.value`）。
3. **命令行修饰符是内容的一部分**：PEX 三段必须整条照抄
   （`-lvs -hier -spice svdb/<cell>.sp -turbo` → `-xrc -pdb -rcc -turbo -xcell hcells` →
   `-xrc -fmt -all -xcell hcells`），并且 batch 与 GUI 产物**逐字节一致**（仅 DATE 行不同）。
