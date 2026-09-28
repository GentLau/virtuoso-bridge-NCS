# P-097 · 覆盖式再导入后紧跟的视图查询偶发 `*Error* cell not found`（同 cell 连导时出现 1 次，之后 2/2 复跑皆成功）

| 字段 | 值 |
|---|---|
| 级别 | P3（观察：未稳定复现，但用户串行导入同一 cell 时会撞到，表现为整体失败） |
| 层 | 上层（verilog 包）/ 库视图刷新时序 |
| 归属 | 待归属（verilog 包 `_read_views` 与 ihdl 覆盖写后的库视图刷新时序） |
| 状态 | **观察** |
| 位置 | `src/pyapi/packages/verilog.py:251-256`（`_read_views` 里 `unless(cell error("cell not found"))`）+ `import_verilog:558`（`ddUpdateLibList()` 在 `_verify_import` 之前只刷一次）。 |
| 首报 | 2026-09-28（第八轮 verilog.import 参数面实测，root 直接发现） |
| 最近更新 | 2026-09-28（新立，含 2/2 未复现说明） |

## 现象

2026-09-28 23:03 实测：IMP-01（`file_is_local=True`，overwrite=True）成功后，IMP-02（同一 cell、`file_is_local=False`、overwrite=True）在 `_read_views` 处抛 `RuntimeError: ("error" 0 t nil ("*Error* cell not found"))` → 整个 import 返回失败；
随后手工复跑同参数 2 次（远端就地 + overwrite）**2/2 全成功**（`views` 仍为空见 P-096），且 `ddGetObj("schemtest" "vimp_top")` 一直存在 ⇒ 判定为**时序/刷新**类瞬时现象，非稳定缺陷。

## 复现

```text
同参数连跑两次：见 `test/live/packages/verilog_import_params_e2e_tests.py` IMP-01→IMP-02 顺序；复现尝试记录见本卡片证据。
```

## 证据

`test/artifacts/evidence/round8/verilog-import-params/verilog-import-params.json`（`failure` 字段原文）

## 验收判据（修好即转绿）

① 覆盖式再导入后 `_read_views` 不再出现 cell not found（或在覆盖写后补一次 `ddUpdateLibList()` 再查）；② 若确认是瞬时，给 `_read_views` 有界重试并在结果里标注。

## 下一步 / 责任人

设计侧评估覆盖写后的视图刷新时序；测试侧在 IMP-02 前插一次 `ddUpdateLibList` 观察是否消失（不改判据，只做定位）。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
