# P-099 · `virtuoso.verilog.import` 返回值里的 `views` 恒为空，与真机实际视图不符（functional/symbol 明明已生成）

| 字段 | 值 |
|---|---|
| 级别 | P2（结构化返回值与事实不符：调用方按 `views` 判断产物会得出「什么都没导入」的结论） |
| 层 | 上层（verilog 包） |
| 归属 | 设计侧（verilog 包 `_read_views`） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/verilog.py:251-281`（`_read_views`：SKILL `sprintf(nil "%L" out)` → `basic.parse_sexpr` → 遍历取 view/type/data/file）；调用点 `_verify_import:594` / `import_verilog:566`（结果 `views` 直接取它）。 |
| 首报 | 2026-09-28（第八轮 verilog.import 参数面实测，root 直接发现） |
| 最近更新 | 2026-09-28（新立） |

## 现象

真机（vblog，`schemtest/vimp_top`）实测：
① `virtuoso.verilog.import(file_is_local=True, ref_libs=["basic"], overwrite=True)` 返回 `{"reason": "completed", "cells": ["vimp_top_child","vimp_top"], "views": [], "instance_count": 1, "net_count": 2, "term_count": 2, "bbox": [...]}`；
② 同一 cell 用 SKILL 直接查（`mapcar(lambda((v) v~>name) c~>views)`）得到 `("functional" "symbol")`；
③ 把 `_read_views` 的**同一条 SKILL 文本**离线跑一遍（`basic.parse_sexpr` + 同一遍历），能正常解析出 6 条 view/file 记录 ⇒ 解析逻辑离线可用，问题在真机链路里的实际返回值形态（需设计侧在进程内复现）。

## 复现

```text
`PYTHONPATH=src python test/live/packages/verilog_import_params_e2e_tests.py --transport http`（IMP-08 是红钉；IMP-01/03 打印 `NOTE P-096` 对照真机实际 views）
```

## 证据

`test/artifacts/evidence/round8/verilog-import-params/verilog-import-params.json`；cell `schemtest/vimp_top` + `schemtest/vimp_top_views`（现场保留，不清理）

## 验收判据（修好即转绿）

① import 返回值 `views` 至少包含真实生成的视图（与 `mapcar ~>views` 一致）；② IMP-08 红钉转绿。

## 下一步 / 责任人

设计侧在 `_read_views` 里加一行原始返回（`raw`）日志定位真机形态差异；测试侧复跑 IMP-08。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
