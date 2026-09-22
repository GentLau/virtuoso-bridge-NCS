# layout 业务包 真机测试报告

> 版本：v1
> 日期：2026-09-21
> 执行环境：direct dispatch / work-dir `test/tb/artifacts/log-vblog` / token `vb-vblog`
> Virtuoso IC6.1.8-64b（WSL `wsl-gent`，techfile=`cdsDefTechLib`，无 PDK）
> 测试库：`schemtest`（`lay_e2e` / `lay_master`）+ 临时 `laygds_lib`
> 执行脚本：`test/tb/layout_e2e_tests.py`（`--transport direct|http`）

## 1. 结论

**direct dispatch 9/9 PASS**（HTTP 8127 待重启加载 layout 包后回归：operations 56 → 61）。

```
PASS    WRITE-01 place geometry/label
PASS    READ-01 focus/object_filter/detail
PASS    WRITE-02 instance + mosaic atoms
PASS    WRITE-03 set/delete/rename atoms
PASS    WRITE-04 guards
PASS    VIA-01 place/read/delete via
PASS    DISPLAY-01 layers/entry layer
PASS    SHOT-01 screenshot
PASS    GDS-01 export + import round trip
```

## 2. 关键证据

### 2.1 几何与 label（WRITE-01 / WRITE-03）

| 项 | 实测 |
|---|---|
| 5 个 place 原子 | rect / polygon / path / line / label 全部落库，`read` 读回 kind 各 1 个 |
| path 属性 | `width=0.2`、`path_style="roundRound"` 读回一致（`set_shape_properties new_width=0.4` 后为 0.4） |
| rect 改形 | `new_bbox=[0,0,2.5,1.5]` 读回 `[[0,0],[2.5,1.5]]` |
| label 改名 | `rename_label` 后读回 `LBL2` |
| 批量删层 | `delete_shapes_on_layer(y1/drawing)` 后 y1 多边形消失 |

### 2.2 读过滤（READ-01）

- `focus=summary` + `object_filter={shape:none, instance:none, via:none}` → 只回摘要字段（无 shapes/instances）；
- `detail=index` → 每条 shape 只剩 `kind/layer/purpose/lpp`（字段集合断言）；
- `object_filter.shape.types=["rect"]` → 1 条；`object_filter.shape.region=[-1,-1,2.5,3.5]` → 3 条（rect+path+line，多边形在区域外、label 在 y=4）。

### 2.3 实例与 mosaic（WRITE-02）

- `place_instance`（master=`lay_master`，xy=10,0）与 `place_mosaic`（2×3，pitch 4/4）均创建成功；
- 读回：`I1`（kind=inst）、`M1`（kind=mosaic，rows=2、columns=3）；
- `rename_instance I1→I1X` + `set_instance_properties(new_xy=[12,3], new_orient="MX")` 读回一致。

### 2.4 via（VIA-01）

- 会话内建临时 viaDef（`techCreateStdViaDef(tf "lay_e2e_via" "y0" "y1" list("y2" 0.2 0.2) list(1 1 list(0.2 0.2)) ...)`）；
- `place_via(xy=30,30)` → `read(focus=vias)` 读到 1 个，`xy=[30,30]`；
- `delete_via(xy=30,30,orient=R0)` → 读回 0 个；随后 `techDeleteViaDef` 清理。

### 2.5 GDS 导出 + 导入（GDS-01）

| 项 | 实测 |
|---|---|
| 导出 | `reason=completed`，`translated_structures=[schemtest/lay_e2e/layout -> lay_e2e]`，GDS 落盘非空 |
| 日志 | `INFO (XSTRM-234): Translation completed. '0' error(s)` |
| 导入 | `strmin -library laygds_lib -strmFile lay_e2e.gds -attachTechFileOfLib cdsDefTechLib -layerMap y_map.map -topCell lay_e2e` → `reason=completed`，`shape_count>0` |
| 产物 | `test/tb/artifacts/layout-tb/lay_e2e.gds` + `lay_e2e.xstream.log`（本机），远端 run 目录按 cleanup_policy 清理 |

### 2.6 截图与展示

- `display`：`set_entry_layer/set_layers_visible/show_only_layers` 全部成功，`leGetEntryLayer` 回读含 `y0`；
- `screenshot`：打开 layout 窗口后截图，本地 `artifact/screenshots/` 得到非空 PNG；远端临时文件已清理。

## 3. 实现过程中踩到并已修掉的坑

1. **`numInst` / `rows` 是数字还是列表不确定**：普通实例 `numInst=1`（数字）、数组实例 `(4)`（列表）；
   mosaic 的列属性名是 **`columns`**（不是 `cols`）。读回必须用 `listp` 分支，否则 `car` 抛错。
2. **path 的 `bBox` 含半宽**：按 points 计算 bbox 去索引 path 永远匹配不上 → 多边形类形状只按
   `points` 逐点匹配（rect/ellipse 才按 `bBox`）。
3. **索引容差 0.001 太松**：DB 网格就是 0.001，相邻两格差值恰为 0.001 → 收敛为 0.0005；
   同时把匹配表达式里的 `>=/<=` 改成 `abs(...) <= tol`。
4. **via 不可按名字索引**：`via~>viaDef` / `~>name` 都是 nil → 改为 `xy + orient` 索引；
   `read(focus=vias)` 返回 `xy/orient/bbox/cut_layer`。
5. **XStream 完成弹框会阻塞整个 SKILL 通道**：IC6.1.8 下 `showCompletionMsgBox="false"` 不可靠，
   导出完成后包内主动关闭 "Stream out translation complete" / "XStream Out" 窗口（走 gui 接口），
   否则后续任何 SKILL 调用都会超时（本次实测被卡住过一次，用 ESC/Enter 解开）。
6. **导出前必须 `dbSave`**：XStream 只翻译磁盘版本；未保存改动不会被导出（真机验证：内存 2 个 rect
   只导出 1 个），且可能触发模态 "Save All" → 包内在导出前显式 save+close。
7. **`strmin` 的 `-topCell` 与 `-layerMap`**：缺 `-layerMap` 直接 `XSTRM-74` 失败；`XSTRM-80009`
   提示的 `-cell` 是厂商笔误（`strmin -help` 里没有该选项）。

## 4. 已知限制

| 限制 | 说明 |
|---|---|
| 无 move 原子 | 位置变更走 `set_*_properties`（rect 用 `new_bbox`、polygon/path 用 `new_points`、instance 用 `new_xy`） |
| `depth>0` 仅覆盖 `dbShapeQuery` 路径 | 需同时给 layers + region；不展开完整层级树（不返回 occurrence 路径） |
| mosaic 属性只读 | rows/columns/pitch 建后不可改；PCell 参数（`dbCreateParamInst`）不在本版 |
| viaDef 依赖 techfile | 无 PDK 时只能建会话内临时 viaDef（只读 techfile 不落盘），跨会话会悬空 |
| `mag` 只读 | 缩放不在本版 |
| 未覆盖 | 并发写、权限、超大版图性能、OASIS、layer map 自动生成 |

## 5. HTTP 8127 回归

- 现状：8127 在加载 layout 之前启动（`/health` = 56 operations）。
- 待重启后执行：`.\.venv\Scripts\python.exe test\tb\layout_e2e_tests.py --transport http`，预期 9/9 PASS 且 `/health` = **61 operations**。
