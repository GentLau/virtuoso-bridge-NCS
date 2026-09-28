# P-082 · region 口径漂移（P-074 同类）：spec 定版‘对角两点、禁四元组’，实现（读过滤/截图）仍只收四元组

| 字段 | 值 |
|---|---|
| 级别 | P2（spec 合规请求直接失败） |
| 层 | 上层（schematic + layout 包） |
| 归属 | 设计侧（schematic / layout 包对齐 P-074 定版） |
| 状态 | **待设计修** |
| 位置 | schematic：`src/pyapi/packages/schematic.py:79-126`（region 过滤按 4 个 float 解包）、`:932-935`（screenshot region 强制 len==4）；layout：`src/pyapi/packages/layout.py:1707-1714`（`_filter_region` 强制 len==4）。spec：`上层/2-schematic.md` §1.3「region/bbox 一律对角两点 [pos0,pos1]（read 与 write 同形，**不再用四元组**）」；`上层/4-layout.md:36/71/175`（`{"region":[pos0,pos1]}`）。 |
| 首报 | 2026-09-28（第八轮条款逐条核账 · g4-edit schematic#014-018/049-050、layout#023-024/028 发现） |
| 最近更新 | 2026-09-28 |

## 现象

按 spec 传对角两点 `[[x0,y0],[x1,y1]]`：schematic `object_filter.region` → **裸 TypeError**（float(list)）；schematic `screenshot.region` → `ValueError: region must be [x1, y1, x2, y2]`；layout `object_filter.region` → `ValueError: shape.region must be [x0, y0, x1, y1]`。反之 spec 明令弃用的四元组在三个面全被接受 —— 同文件 layout `_bbox`（write 侧）已是两点口径，read 过滤与 schematic 截图没跟上 P-074 定版。
**加强证据（真机探针，2026-09-28）**：layout `read(depth>0)` **在两种形态下都必然失败** —— 扁平四元组过了 `_filter_region` 后被 `_bbox` 拒（`ValueError: bbox must be [ [x, y], [x, y] ]`），嵌套两点又被 `_filter_region` 拒 → **depth 特性 100% 不可用**（`layout-depth.json`：depth0 shapes=3 OK，depth1 直接 BUG）。

## 复现

```text
python test/artifacts/tmp/_r8_region_shapes.py   # 两点/四元组 ×（schematic instance/shape、layout filter）对照
python test/artifacts/tmp/_r8_public_region.py  # 公共 API：read(object_filter=两点 region) → 裸 TypeError；四元组放行到 middle
离线钉住（修复前必红）：test/offline/unit/test_schematic_contracts.py::test_region_filter_uses_two_points_per_p074_spec；test/offline/unit/test_layout_contracts.py::test_object_filter_region_uses_two_points_per_p074_spec
```

## 证据

`test/artifacts/tmp/_r8_region_shapes.py` 六行输出；现有 TB 用四元组的点位：`test_layout_contracts.py:382`、`test_schematic_contracts.py:92/104`（修复后需同步改两点）；真机探针 `test/semi/probes/layout_depth_probe.py` → `test/artifacts/evidence/round8/layout-depth.json`

## 验收判据（修好即转绿）

① 三个请求面只接受对角两点、四元组报显式 ValueError（点明 pos0/pos1）；② 两条钉住用例转绿；③ 旧四元组点位 TB 同步改两点并全绿（layout/schematic 包 E2E 无回归）；④ `layout_depth_probe` 转绿：depth=1 读回 shapes 严格大于 depth=0（层级下钻语义成立）。

## 下一步 / 责任人

设计侧按 P-074 口径统一实现 → 通知测试侧；测试侧改旧点位、复跑离线 + layout/schematic 包 E2E 后销案。

## 关联

- **P-085**：`layout.read(depth>0)` 与 region 的组合任何写法都失败（与本条同源但独立，见该卡片）；修本条时两处（`_filter_region` 与 `_bbox`）必须一起对齐。

---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
