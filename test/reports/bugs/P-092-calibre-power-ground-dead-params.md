# P-092 · `calibre.drc/lvs/pex` 的 `power` / `ground` 声明并校验，但实现**从不读取**（静默无效）

| 字段 | 值 |
|---|---|
| 级别 | P3（静默无效参数，与 P-084 同类；误导调用方以为能指定电源/地网名） |
| 层 | 上层（calibre 包） |
| 归属 | 设计侧（实现语义或从模型/spec 删除） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/calibre.py:100-101`（字段声明）、`:123-124`（`_opt_text` 校验）——全文件再无 `request.power` / `request.ground` 读取点；deck 改写（`:833-849` 的 `rewrite_deck`/`statements_from_params`）也不注入 POWER/GROUND 语句；argv（`:987-1013`）不带对应选项。 |
| 首报 | 2026-09-28（第八轮 calibre 参数面实测，root 直接发现） |
| 最近更新 | 2026-09-28（新立） |

## 现象

真机（vblog）实测：`calibre.drc(power="VDD", ground="VSS", …)` 与不传这两个参数的同参数运行在 job.json / argv / 报告上**无任何差异**（job.json 里连字段都不出现）；DRC/LVS 结论不变。即参数对行为零影响。

## 复现

```text
`PYTHONPATH=src python test/live/packages/calibre_params_e2e_tests.py --transport http`（CAL-DRC-01 带着 power/ground 跑；CAL-P092-01 记录）
```

## 证据

`test/artifacts/evidence/round8/calibre-params/calibre-params.json`；对照 run_dir `/home/Gent/project/vblog/calibre-e2e/params-drc-*/job.json`（无 power/ground 键）

## 验收判据（修好即转绿）

① 让 power/ground 参与 deck 改写（注入 `LAYOUT POWER`/`LAYOUT GROUND` 或对应 SVRF 语句）并给可观察差异；② 或从模型/spec 删除这两个字段；两者取其一并同步 TB 断言。

## 下一步 / 责任人

设计侧定口径；测试侧按结论把 CAL-P092-01 从 NOTE 改成正向/负向断言。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
