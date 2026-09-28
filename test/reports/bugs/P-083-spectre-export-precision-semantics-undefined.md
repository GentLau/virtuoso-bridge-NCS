# P-083 · `spectre.export.precision` 语义未定义：实现按**有效数字**（`%.Ng`），用户直觉是小数位

| 字段 | 值 |
|---|---|
| 级别 | P3（口径/文档；会造成「导入的 CSV 精度与预期不符」） |
| 层 | 上层（spectre 包） |
| 归属 | 设计侧（spec 写明语义，或实现改小数位） |
| 状态 | **待归属** |
| 位置 | `src/pyapi/packages/spectre.py:1050`（`formatter = f"{value:.{precision}g}"`）vs `spec/design-concepts/上层/7-spectre.md:287`（只列字段，未定义语义） |
| 首报 | 2026-09-28（第八轮 op×param 补测；未走外部 bug 系统） |
| 最近更新 | 2026-09-28（新立） |

## 现象

`export(format=csv, precision=3)` 对 1.23456 输出 `1.23`（3 位有效数字），而按「小数位」直觉应为 `1.235`。

## 复现

```text
`PYTHONPATH=src python test/live/packages/spectre_params_e2e_tests.py --transport http --token vb-vblog`（EXPORT-P1 按实效口径钉住）
```

## 证据

`test/artifacts/evidence/round8/spectre-params/spectre-params.json`、`.../spectre_params_export.csv`（1.23/2.35/3.46）

## 验收判据（修好即转绿）

spec 明确写「有效数字」，或实现改为小数位；两者取其一并同步 TB 断言

## 下一步 / 责任人

设计侧定口径；测试侧按拍板结果更新 EXPORT-P1 断言


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
