# P-101 · `import(overwrite=False)` 对已存在 cell 返回成功但**不写任何内容**，且无 skipped/已存在 标记（用户无法区分「导入成功」与「没做事」）

| 字段 | 值 |
|---|---|
| 级别 | P3（静默 no-op：调用方会误以为设计已导入） |
| 层 | 上层（verilog 包） |
| 归属 | 待决策（spec 口径：overwrite=False 语义是 skip 还是拒绝） |
| 状态 | **待决策** |
| 位置 | `src/pyapi/packages/verilog.py:490`（`import_if_exists := 1 if request.overwrite else 0`）→ ihdl 跳过已存在 cell 并正常结束；`import_verilog:562-571` 仍按 `reason=completed` 返回 `cells/views`，未标注「未覆盖/跳过」。 |
| 首报 | 2026-09-28（第八轮 verilog.import 参数面实测，root 直接发现） |
| 最近更新 | 2026-09-28（新立） |

## 现象

真机（vblog）实测：同一 cell（`schemtest/vimp_top`）第二次 `import(overwrite=False)`：
- 返回值 `ok=true, reason=completed`；
- `schemtest/vimp_top/functional` 的 mtime **不变**（1790609122 → 1790609122）⇒ 内容没被改写；
- 结果里没有 `skipped` / `existing` / `warnings` 之类的标记 ⇒ 与真正导入成功无法区分。
（同一用例另一次运行返回 `RuntimeError: sha256 mismatch`，属 P-090 家族的上传校验抖动，已在 P-090 记录。）

## 复现

```text
`PYTHONPATH=src python test/live/packages/verilog_import_params_e2e_tests.py --transport http`（IMP-07 + mtime 对照）
```

## 证据

`test/artifacts/evidence/round8/verilog-import-params/verilog-import-params.json`；mtime 对照见该次运行 stdout（`overwrite=False 返回成功；… mtime … → …（变化=否）`）

## 验收判据（修好即转绿）

① spec 明确 `overwrite=False` 对已存在 cell 的语义，并在返回里体现（如 `skipped=true` / 结构化错误 `cell_exists`）；② TB IMP-07 按结论改成强断言（现在是 NOTE + mtime 检查）。

## 下一步 / 责任人

spec owner 定口径；测试侧把 IMP-07 改成对应断言。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
