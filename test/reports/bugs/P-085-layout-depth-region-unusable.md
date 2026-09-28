# P-085 · `layout.read(depth>0)` 与 `region` 组合**任何写法都失败**（扁平→`_bbox` 拒；两点→`_filter_region` 拒）

| 字段 | 值 |
|---|---|
| 级别 | P2（spec 声明的参数组合确定性不可用） |
| 层 | 上层（layout 包） |
| 归属 | 设计侧（layout 包）；与 P-082 同源但独立 |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/layout.py:1522-1525`（deep 路径 `_bbox(region)` 要求嵌套两点）与 `:1707-1714`（`_filter_region` 要求扁平四元组）；spec `上层/4-layout.md:36,40`（region 定版 `[pos0, pos1]`，depth>0 需 region 或 layers） |
| 首报 | 2026-09-28（第八轮半真机探针 layout_depth_probe.py 发现） |
| 最近更新 | 2026-09-28 |

## 现象

`depth>0` 时两条校验互斥，**没有任何一种 region 写法能通过**：
| 输入 | 结果 |
|---|---|
| `depth=0` + `region=[0,0,60,60]` | ✅ 正常（shapes=3） |
| `depth=1` + `region=[0,0,60,60]`（实现自定的扁平格式） | ❌ `ValueError: bbox must be [ [x, y], [x, y] ]` |
| `depth=1` + `region=[[0,0],[60,60]]`（spec 定版两点） | ❌ `ValueError: shape.region must be [x0, y0, x1, y1]` |
depth>0 因此是**确定性不可用**的参数组合（不是偶发）。

## 复现

```text
python test/semi/probes/layout_depth_probe.py            # 期望 RED（现为确定性失败）
python -m pytest test/offline/unit/test_layout_depth_contract.py -q  # 1 条 strict xfail
```

## 证据

`test/artifacts/evidence/round8/layout-depth.json`（depth0=3 shapes OK / depth1=ValueError）；`test/offline/unit/test_layout_depth_contract.py`（stub middle 证明死在参数形态、未触达传输层）

## 验收判据（修好即转绿）

二选一定口径后实现：① 按 P-074 定版统一 `region` 为对角两点（改 `_filter_region`，deep 分支不动）；② 或 deep 分支把扁平四元组转成两点后再交给 `_bbox()` 并同步 spec。任一方案都要补回归：`depth=1 + region` 返回跨层结果（shapes>0）且 `layout_depth_probe.py` 转 GREEN。

## 下一步 / 责任人

设计侧与 P-082 一起定 region 形态（两处必须同时对齐）→ 测试侧复跑探针 + 离线 xfail + layout live。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
