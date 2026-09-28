# P-100 · `virtuoso.verilog.import` 的 `cell` 参数不参与落地：ihdl 只按**源码顶层模块名**建 cell，取值不同即整体报 `*Error* cell not found`（且写已发生）

| 字段 | 值 |
|---|---|
| 级别 | P2（spec 说 cell 是显式目标；实际非同名就失败，还会留下已写入的副作用 = 报错但库已改） |
| 层 | 上层（verilog 包）· 与 spec 口径 |
| 归属 | 设计侧（verilog 包 `import_verilog` 的 ihdl 调用/参数拼装） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/verilog.py:487-522`（`ihdl_param` 只有 `dest_sch_lib`，**没有任何 dest cell 项**，`ihdl` 因此按源码模块名落地）；随后 `_verify_import:575-604` 却用 `request.cell` 去 `ddGetObj` → 不同名必然 `*Error* cell not found`。spec：`spec/design-concepts/上层/8-verilog.md:80`「`library` / `cell`：目标库与顶层 cell（**显式给**，不用文件名推导）」。 |
| 首报 | 2026-09-28（第八轮 verilog.import 参数面实测，root 直接发现） |
| 最近更新 | 2026-09-28（新立） |

## 现象

真机（vblog，源文件顶层模块 `vimp_m1`）：
- `import(cell="vimp_m1", …)` → `ok=true, reason=completed`，`schemtest/vimp_m1` 目录存在；
- `import(cell="vimp_m2", 同一个源文件)` → `ok=false, error=RuntimeError: ("error" 0 t nil ("*Error* cell not found"))`，`schemtest/vimp_m2` **不存在**，但 `schemtest/vimp_m1/functional` 的 mtime 已被刷新（另一轮实测：23:12:45 → 23:13:22）⇒ **写已发生而调用方收到失败**。
- 结论：`cell` 只在「校验」里被用，落地时被忽略；非同名场景既拿不到产物也拿不到真实原因。

## 复现

```text
`PYTHONPATH=src python test/live/packages/verilog_import_params_e2e_tests.py --transport http`（IMP-10 是红钉；IMP-01/02/03/09 都按「模块名=请求 cell」跑，故仍能验证其它参数）
```

## 证据

`test/artifacts/evidence/round8/verilog-import-params/verilog-import-params.json`；现场 cell `schemtest/vimp_m1`、`schemtest/vimp_top`（保留不清理）

## 验收判据（修好即转绿）

① 让 ihdl 按 `request.cell` 落地（在 `ihdl_param`/命令行里给 dest cell，或对源码顶层模块名做显式映射并报错清晰）；② 若产品坚持「cell 必须等于顶层模块名」，spec 改口径 + 前置校验（读到模块名不一致时**在写之前**结构化拒绝）；③ 两条任一，IMP-10 转绿。

## 下一步 / 责任人

设计侧先定口径（ihdl 能否指定 dest cell 名）；测试侧复跑 IMP-10 与 IMP-01/02 确认无回归。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
