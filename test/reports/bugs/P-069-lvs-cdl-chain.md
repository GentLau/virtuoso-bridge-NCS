# P-069 · Calibre LVS 全链跑不通：auCdl 对 PDK 器件导出 CDL 失败 → 无源网表

| 字段 | 值 |
|---|---|
| 级别 | P2（业务包功能不可用） |
| 归属 | 设计侧 |
| 状态 | **观察（第七轮复验 **correct**，等上层销案）** |
| 位置 | `si -batch`（auCdl）↔ PDK 属性模板（`hnlCDLParamList` / `hnlCDLFormatInst`）↔ `calibre.lvs` 输入 |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

## 现象

含 PDK 器件的 cell 走 CDL 导出时 `si -batch` 失败，报 `hnlCDLParamList` / `hnlCDLFormatInst` 缺失 → **没有可用源网表** → `calibre.lvs` 只能到 `NOT COMPARED`（再叠加 P-062 还会被截成 `not`）。DRC 侧正常（completed，1737 rulechecks / 36 结果）。用户 2026-09-24 判定：这是**业务包本身跑不通**，立案为缺陷（此前误记为「环境/配方口径问题」）。

## 复现

```text
在 wsl-gent 上对含 PDK 器件的 cell 做 CDL 导出（`si -batch`）后跑 `calibre.lvs`；或 `python test/semi/probes/calibre_package_http_probe.py --kind lvs`（专用环境 `test/artifacts/env/s11-calibre` + 业务面 8128）
```

## 证据

**第七轮复验（2026-09-24 晚）**：`test/artifacts/evidence/round7/design-iterate/iterate-lvs.json`——`calibre.export_cdl(CMP_LIB/inv2, 680 B)` → `virtuoso.layout.gds` → `calibre.lvs(deck+cdl)` → `calibre.read_results`：**`status=correct`**、ports 4/4、nets 4/4、inst 1/1、`differences=[]`；S11 全链（`test/artifacts/env/s11/`）也拿到确定结论（`cdl` 693 B）。旧证据（首报时）：`round5-main/s11-flow2.log`（lvs FAIL）、`round5-main/calibre-lvs.json`（`status=NOT COMPARED`）

## 验收判据（修好即转绿）

含 PDK 器件的 cell 能导出可用 CDL，且 `calibre.lvs` 给出 **CORRECT / INCORRECT** 的确定结论（不再是 NOT COMPARED）；S11 `lvs` 阶段 PASS

## 下一步 / 责任人

测试侧已复验通过（deck 入口 + runset 入口两条都好）；等上层/设计确认后把卡片移入 `已关闭-近期.md`。注意：`_calibre.lvs_`（tvf 格式）不是合法 runset，用它当失败证据属『用错文件』


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
