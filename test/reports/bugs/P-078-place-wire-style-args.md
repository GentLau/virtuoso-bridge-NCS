# P-078 · `place_wire` 样式参数拼接重复：width 静默建出 path、color/line_style 直接报错

| 字段 | 值 |
|---|---|
| 级别 | P2（静默错误结果 + 硬报错） |
| 层 | 上层（schematic 包） |
| 归属 | 设计侧（schematic 包） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/schematic.py:575-583`（两段追加逻辑都保留：575-578 与 579-583 重复拼 width/color/line_style；按官方签名应只保留 `width [color [lineStyle]]` 一次 → 删除第二段） |
| 首报 | 2026-09-28（测试侧第八轮参数矩阵发现，卡片直报） |
| 最近更新 | 2026-09-28 |

## 现象

`place_wire` 只传 `points` 正常；**一旦传样式参数**：
1. `width=0.1` → 生成 `schCreateWire(... 0 0 0.1 0.1 nil)`，**静默建出 `path` 而不是 `line`(wire)**，`schematic.read` 看不到该线（wire_count=0），下游连通性/网表会当它不存在；write 仍报 ok。
2. `width+color` → `too many arguments (at most 9 expected, 10 given)` 硬报错。
3. `width+color+line_style` → `12 given` 硬报错。
真机 DB 复核：ctrl 用例 shape=`(("line" nil nil nil))`，width 用例 shape=`(("path" 0.1 nil nil))`。

## 复现

```text
python test/semi/probes/schematic_wire_style_probe.py            # 真机，5 例：ctrl/route OK，width/color/style BUG
python -m pytest test/offline/unit/test_schematic_contracts.py -q  # 离线钉住用例 test_wire_style_arguments_exact 必红
```

## 证据

`test/artifacts/evidence/round8/schematic-wire-style.json`（逐例 write/read/DB 三层 + 离线 SKILL 文本）；离线失败输出见 round8/offline-win-1.log（本条为**有意红钉住**）

## 验收判据（修好即转绿）

① 半真机探针 `schematic_wire_style_probe.py` **5/5 OK**（width 读回 width≈0.1 且 read 可见；color/line_style 不再报 too-many-arguments 且读回正确）；② 离线 `test_wire_style_arguments_exact` 转绿；③ 复跑 `schematic_e2e_tests.py`（含 ATOM-wire）不回归。

## 下一步 / 责任人

设计侧按官方签名收敛为单次拼接（删 579-583 段或 575-578 段，二者只留一）→ 通知测试侧；测试侧复跑上述三件套后销案。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
