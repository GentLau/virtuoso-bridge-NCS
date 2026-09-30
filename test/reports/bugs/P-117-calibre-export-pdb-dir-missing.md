# P-117 · spec `12-calibre.md` §4.5 的 `export.items` 列了 `pdb_dir`，实现未提供（`unknown export item: pdb_dir`）；而 §4.4 又写明既有 PEX 产物可由 `export` 读取

| 字段 | 值 |
|---|---|
| 级别 | P3（文档与实现不一致：按 spec 调用必失败；既有 PEX 产物的导出路径不可达） |
| 层 | spec↔实现一致性（上层 calibre 包）· `export.items` 枚举 |
| 归属 | spec 侧（二选一：删/改 §4.5 的 `pdb_dir`；或由实现补上 pdb 目录导出） |
| 状态 | **待决策** |
| 位置 | spec `spec/design-concepts/上层/12-calibre.md:231`（items 枚举）与 `:223`（“既有 PEX 产物仍可由 read_results / export 读取”）；实现 `src/pyapi/packages/calibre.py:56-61`（`_EXPORT_ITEMS` 只有 summary/results_db/netlist/log）与 `:248`（其它 item 一律 ValueError） |
| 首报 | 2026-09-30（测试/root：补 `calibre.export` 枚举覆盖时发现 spec 列了未实现的 item） |
| 最近更新 | 2026-09-30 23:30（新立） |

## 现象

真机（8127，token vb-vblog）：`calibre.export(run_dir=…, items=["pdb_dir"])` → 400 `invalid request for operation: unknown export item: pdb_dir`；对照 `items=["all_small"]` → 200 且展开为 summary/results_db/log（合法枚举可用，说明只有 pdb_dir 缺）。

## 复现

```text
对任一已有 run_dir 调 `calibre.export(items=['pdb_dir'])`；或 `calibre_e2e_tests.py --only EXPORT` 看 EXPORT-04。
```

## 证据

`test/artifacts/evidence/round9/calibre-c07-r11c.txt`（套件 12/12，含 EXPORT-03/04）；枚举差异见源码锚点

## 验收判据（修好即转绿）

① spec 与实现一致（删/改 pdb_dir，或实现补上）；② TB EXPORT-04 按裁决更新（现状=结构化拒绝并点名 item）；③ 若实现补上：必须值级断言 pdb 目录落地（目录存在且文件非空），并同步 §5 的 PEX 产物口径。

## 下一步 / 责任人

等 spec owner 拍板；TB 已按“现状 + 指向本卡”记录，不阻塞门禁。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
