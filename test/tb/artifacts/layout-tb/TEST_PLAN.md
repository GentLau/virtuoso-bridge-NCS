# layout 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-21
> 对象：`src/pyapi/packages/layout.py`（业务包：layout）
> 依据：`spec/design-concepts/上层/4-layout.md`（Draft v4）

## 1. 目标与范围

验证 layout 包 5 个对外操作在真实 Virtuoso（IC6.1.8）环境下满足 spec：

| 大类 | 操作 |
|---|---|
| 读 | `read`（focus / detail / object_filter / region_mode / depth） |
| 写 | `write`（几何 / label / instance / mosaic / via 原子 + dbSave） |
| GDS | `gds`（`action=export` XStream Out；`action=import` strmin） |
| 导出 | `screenshot` |
| 展示 | `display`（图层可见性 / 录入层 / 视口） |

重点验证：

1. 几何与 label 原子落库后能按 `read` 结构化读回（含 path 的 width/style）；
2. instance / mosaic 的创建、改名、属性设置与按 name 索引；
3. via 在 techfile 有 viaDef 时可建、可读、可按 `xy+orient` 删除；
4. `read` 的 focus / detail=index / object_filter（none、types、region）真实生效；
5. 只写已存在 view：view 不存在、viewType 不符、strict_lpp 非法层都要失败；
6. `gds` 导出产物可被 `strmin` 重新导入（round trip 校验形状数）；
7. `display` 改的是会话状态且返回值可校验；
8. `screenshot` 产物真实落盘。

## 2. 环境

| 项 | 值 |
|---|---|
| 业务面 | `127.0.0.1:8127` / 直连 `server.dispatch`（`--transport direct`） |
| work-dir | `test/tb/artifacts/log-vblog` |
| token | `vb-vblog` |
| Virtuoso | IC6.1.8-64b（WSL `wsl-gent`，DISPLAY=:99） |
| techfile | `schemtest` 绑定 `cdsDefTechLib`（系统层 y0..y9，**无 PDK**） |
| 执行脚本 | `test/tb/layout_e2e_tests.py`（`--transport direct|http`） |

## 3. 测试台

| cell | 用途 |
|---|---|
| `schemtest/lay_e2e/layout` | 主用例：几何、label、instance、mosaic、via、展示、截图、GDS 导出 |
| `schemtest/lay_master/layout` | 被 instance / mosaic 引用的 master |
| `laygds_lib/lay_e2e/layout` | GDS 导入的落点（用完即删） |

via 用例使用**会话内临时 viaDef**（`techCreateStdViaDef` with y0/y1/y2，用完 `techDeleteViaDef` 删除）。

## 4. 用例

| 用例 | 覆盖 | 预期 |
|---|---|---|
| WRITE-01 | place_rect/polygon/path/line/label | 5 个原子全部 applied；读回 kind 齐全、path width=0.2、style=roundRound、label text 正确 |
| READ-01 | focus/detail/object_filter | focus=summary + filter none 只回摘要；types=[rect] 回 1 条；detail=index 字段收敛为 4 个；region 过滤命中 3 条 |
| WRITE-02 | place_instance/place_mosaic/rename_instance/set_instance_properties | 实例与 mosaic 可读回（mosaic rows/columns）；改名与 xy/orient 设置生效 |
| WRITE-03 | set_shape_properties/rename_label/delete_shape/delete_shapes_on_layer | rect new_bbox、path new_width、label 改名生效；line 与 y1 多边形被删 |
| WRITE-04 | 守卫 | view 不存在失败；viewType 不符失败并报 "view type"；strict_lpp 报 "unknown layer" |
| VIA-01 | place_via/read/delete_via | via 建后 `cv~>vias` 读到 1 个（xy=30,30），删除后为 0 |
| DISPLAY-01 | set_entry_layer/set_layers_visible/show_only_layers | 全部成功；`leGetEntryLayer` 回读含 y0 |
| SHOT-01 | screenshot | 本地 PNG 存在且非空 |
| GDS-01 | gds export + import round trip | 导出 reason=completed、GDS 落盘、日志含 XSTRM-234、translated_structures 含 cell；导入到临时库 reason=completed 且 shape_count>0 |

## 5. 通过准则

- 全部用例 PASS；失败必须保留失败响应与 SKILL/工具日志原文；
- 每个写用例都要有回读证据；
- 已知限制单列，不得用"未测"掩盖失败。
