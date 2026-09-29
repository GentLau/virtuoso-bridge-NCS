# P-105 · `symbol/layout.screenshot` 的 `view_type` 坏值**不被校验**（ok=true 静默接受；P-080 同族的第三个位置）

| 字段 | 值 |
|---|---|
| 级别 | P3（静默无效参数；与 P-080/P-092/P-084 同类） |
| 层 | 上层（symbol / layout 包）· screenshot 参数校验 |
| 归属 | 设计侧（screenshot 入参校验；与 P-080 的 read 侧同口径） |
| 状态 | **待测试侧** |
| 位置 | `src/pyapi/packages/layout.py`（`ScreenshotRequest` → `_screenshot_skill` 链路，view_type 只透传不校验）；`src/pyapi/packages/symbol.py` 同族（待 symbol 档取证）；对照 `verilog/veriloga` 读侧已按 `dda3775` 校验。 |
| 首报 | 2026-09-29（第九轮修复复验，root 直接发现） |
| 最近更新 | 2026-09-29（新立） |

## 现象

真机（vblog，2026-09-29 15:4x，`virtuoso.layout.screenshot(view_type="bogus_type_xyz")`）返回 **ok=true**；同一 TB 里 `schematic` 档 5/5 绿、`layout` 档仅 SC-06 红。
（symbol 档本轮因 vb-vbuser2 的 CIW `SKILL execution timed out` 未取到证据，属环境态，不当作已覆盖。）

## 复现

```text
PYTHONPATH=src python test/live/packages/screenshot_params_e2e_tests.py --transport http
（默认 layout 档；SC-06 断言：坏 view_type 必须 ok=false）
```

## 证据

`test/artifacts/evidence/verify-fix-r9/shot-layout.txt`（SC-01..05 PASS / SC-06 FAIL）；对照 `shot-schematic.txt` 5/5 绿。

## 验收判据（修好即转绿）

① `virtuoso.symbol.screenshot` 与 `virtuoso.layout.screenshot` 的 `view_type` 与 read/write 同口径校验：非字符串/空串 → ValueError；不在该包支持枚举内 → 结构化拒绝（点名取值）；② SC-06 转绿；③ symbol 档在健康 CIW 上取证并判定（本轮环境超时，未覆盖）。

## 下一步 / 责任人

设计侧定 view_type 的合法集合（layout=maskLayout；symbol=schematicSymbol）并加校验；测试侧复跑三档 screenshot TB。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
