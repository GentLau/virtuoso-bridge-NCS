# round9 · 真机传输形态合规核对（§11 口径）

> 执行：subagent `/root/opparam_r9`｜2026-09-29｜只读核查（未改任何 TB）
> 口径来源：`test/docs/写TB规范.md` §11「真机 = 全真环境 = 模拟生产环境」：
> 真机 TB 必须走标准形态（8124 控制面 + 8127 业务面 HTTP）；`--transport direct` 只允许故障定位，**不得计入真机判据**。

## 1. 结论

| 面 | 现状 | 判定 |
|---|---|---|
| 门禁 runner `test/shared/runners/run_all_http.py` | 每个套件都**显式**追加 `--transport http`（:61-63） | ✅ 合规（真机证据来源） |
| 覆盖率 runner `run_coverage.ps1` / `run_main_coverage.ps1` | 显式 `--transport direct`，且注释写明"覆盖率要在本进程内执行才能被 measure；HTTP 测的是已在跑的常驻服务进程"（`run_coverage.ps1:159-168`、`run_main_coverage.ps1:71-79`） | ✅ 有意为之，但**必须**在报告里标注"direct 覆盖率 ≠ 真机覆盖证据" |
| **12** 个 live TB 的 **argparse 默认值** | 默认 `direct`（见 §2 表） | ⚠ **风险点**：手工单跑（或将来新写的 runner）会静默产出非真机结果，却看起来像真机证据 |
| **11** 个 live TB | `choices=("http",)` 或默认 `http` | ✅ |

## 2. 默认 `direct` 的 12 个 TB（建议一次性翻默认）

| TB | 现默认 | 建议 |
|---|---|---|
| `test/live/packages/infra_e2e_tests.py` | direct | 改 `http`；`direct` 保留为显式选项 |
| `test/live/packages/cellview_e2e_tests.py` | direct | 同上 |
| `test/live/packages/schematic_e2e_tests.py` | direct | 同上 |
| `test/live/packages/symbol_e2e_tests.py` | direct | 同上 |
| `test/live/packages/layout_e2e_tests.py` | direct | 同上 |
| `test/live/packages/gui_e2e_tests.py` | direct | 同上 |
| `test/live/packages/verilog_e2e_tests.py` | direct | 同上 |
| `test/live/packages/veriloga_e2e_tests.py` | direct | 同上 |
| `test/live/packages/spectre_e2e_tests.py` | direct | 同上 |
| `test/live/packages/skillref_e2e_tests.py` | direct | 同上 |
| `test/live/packages/calibre_e2e_tests.py` | direct | 同上 |
| `test/live/flows/project_flow_tb.py` | direct | 同上 |

> 另有少量 live TB 不接 `--transport`（自行内嵌 dispatch 或纯编排），需要逐个标注"是否真机判据"——本轮未逐条核，列为残留（§3.4）。

## 3. 建议（按优先级）

1. **P1**：把上表 12 个 TB 的 `default="direct"` 改为 `default="http"`，并在 `help` 写明
   `direct = 故障定位/覆盖率，不计入真机判据`。改动是单行的、不影响 `run_all_http.py`（它本来就显式传 http）。
2. **P1**：报告口径固定一句话——**真机证据只取自 `run_all_http.py`（http）**；覆盖率数字（direct）单独标注来源。
   本 round9 的主结论表已按此执行（见 `round9-测试报告.md` 的"传输形态"列）。
3. **P2**：给 `run_all_http.py` 加一条"若某套件未接受 `--transport` 参数即判配置错误"的护栏，
   避免将来新增 TB 时静默跑成进程内形态。
4. **P2**：`scenario.py`（按注释调 live/transport 脚本）里出现的调用点逐条复核传输形态（:64 等）。

## 4. 附：`run_all_http.py` 的调用行（证据）

```
61:            proc = subprocess.run(
63:                 "--transport", "http", *SUITE_ARGS.get(suite, [])],
```
