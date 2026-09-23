# 上层业务包：layout

> 版本：Draft v4
> 日期：2026-09-21
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：Draft v3（GDS 导入/导出收拢为本包一个 `gds` 操作；截图口径对齐 schematic/maestro；组织方式对齐 schematic）
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

核心是读和写。写是**按对象对称**的原子操作：shape（rect/polygon/path/line）、label、instance、mosaic、via
各有 place / delete，label 与 instance 另有 rename，shape / label / instance 有 set。
另有三个**非几何**操作：`gds`（GDS 导入/导出收拢）、`screenshot`（截图）、`display`（展示，不落数据）。

边界：

- 只编辑**已存在**的 layout cellview，固定 append 模式 `a`；新建/替换/删除 view 与删除 cell 归 cellview 包；
- viewType 固定 `maskLayout`，view 默认 `"layout"`；
- GDS 的导入与导出都在本包（一个 `gds` 操作，`action=export|import`）；结构 Verilog 导入（`ihdl`）、
  PG label、标签后处理归 digital-import 包；
- 不做路由抽象：多层/总线路由是调用方用 `place_path` / `place_label` 组合出来的规划；
- 不提供"按当前选择集"的写操作（selection 是全局 GUI 状态，不能作业务索引）。

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read | `focus` 可选、可组合；不填=全部；可带区域/对象过滤 | 开只读 → 按 focus 执行对应 SKILL 段 → 解析 | S |
| screenshot | 版图截图：默认 `lib/cell/view`，可选 `window_id`；格式 PNG | 找/开窗口 → hiWindowSaveImage → 下载 | S+D |

- focus 取值：`summary`（bbox、各类计数、按 LPP 的 shape 计数）、`shapes`（几何 + label 属性）、
  `instances`（name/master/xy/orient/num_inst/bbox）、`vias`；不填=全部；
- focus 支持组合，例如 `shapes,instances`；
- 可选 `detail`：`geometry`（默认，含坐标与属性）/ `index`（只回 type + LPP，供大版图廉价索引）；
- 可选 `object_filter`：每个对象一个条目，**不写默认 `all`**；条目可以是 `none`（该类一个都不读）；
  - `shape`：`all` / `none` / `{"layers":[["M1","drawing"],...]}` / `{"types":["rect","polygon","path","line","label"]}` / `{"region":[x0,y0,x1,y1]}`（可组合）；
  - `instance`：`all` / `none` / `{"names":["I1","M0<0:3>"]}` / `{"region":[...]}`；
  - `via`：`all` / `none` / `{"region":[...]}`；
- 可选 `region_mode`：`intersect`（默认）/ `contain`，作用于 object_filter 里的 region；
- 可选 `depth`：`0`（默认，只读本层）/ `>0`（跨层，需同时给 `region` 或 `layers`）；
- `vias` 与 `depth>0` 的真机边界见 §5；
- `screenshot` 的参数与产物口径见 §1.4。

`read` 返回字段：

| focus | 字段 |
|---|---|
| `summary` | `bbox`、`shape_count`、`instance_count`、`via_count`、按 LPP 的 shape 计数 |
| `shapes` | `obj_type / layer / purpose / lpp / bbox / points / width / path_style`；label 额外 `text / xy / height / justify / orient / font` |
| `instances` | `name / master(lib,cell,view) / xy / orient / num_inst / bbox` |
| `vias` | `via_name / xy / orient / bbox` |

### 1.2 写操作（改变业务服务器状态）

对外只有一个**通用写操作** `write`：调用方一次给一组原子命令，业务包内部组织 SKILL 逐个改写，最后统一 `dbSave`。
调用方不会按单个原子调用多次。

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| write | 通用写：`lib/cell/view + commands[]` | 探测 view 存在 → 开 cellview(a) → 逐命令 → dbSave | S |
| gds | GDS 导入/导出，`action=export\|import` | 见 §1.3 | S+C+U+D |

`write.commands` 每项 = `{"op": 原子名, ...该原子参数}`；按顺序执行并保留每步痕迹。
`write` 只接受已存在的 view：先探测（`ddGetObj` 判存在 + `dbOpenCellViewByType(..., "r")` 判类型），
**不得靠 `a` 模式凭空创建**；非事务——中途失败时前面的命令已生效，失败响应带 `commands applied: k/n`。

**write 支持的原子命令**：每个原子 = `op` + **索引**（要动哪个对象）+ 附加参数。

| 对象 | 原子名 | 索引（动哪个） | 附加参数 |
|---|---|---|---|
| rect | `place_rect` | —（新建） | `layer, purpose, bbox=[x0,y0,x1,y1]` |
| polygon | `place_polygon` | —（新建） | `layer, purpose, points[[x,y],...]`（≥3 点，去重后非退化） |
| path | `place_path` | —（新建） | `layer, purpose, points[[x,y],...]`（≥2 点）, `width>0`；可选 `style`（7 个合法值，不传用 `truncateExtend`） |
| line | `place_line` | —（新建） | `layer, purpose, points[[x,y],...]`（=2 点） |
| shape（通用） | `delete_shape` | `kind + layer/purpose + (bbox\|points)`；`all=false` 默认唯一命中 | — |
| shape（通用） | `set_shape_properties` | 同 `delete_shape` | `new_bbox?, new_points?, new_width?` |
| shape（按层批量） | `delete_shapes_on_layer` | `layer, purpose` | `types?`（缺省=该 LPP 全部类型） |
| label | `place_label` | —（新建） | `layer, purpose, xy, text`；可选 `justify/orient/font/height`（不传用底层默认） |
| label | `delete_label` | `xy`（可选加 `text`/`layer` 消歧义） | — |
| label | `rename_label` | `xy`（可选加 `old_text`） | `new_text` |
| label | `set_label_properties` | `xy`（可选加 `text`） | `xy?, height?, justify?, orient?, font?` |
| instance | `place_instance` | —（新建） | `master_lib, master_cell, master_view="layout", name, xy, orient="R0"`；可选 `num_inst`（数组实例，name 变 `A<0:n>`） |
| instance | `delete_instance` | `name` | — |
| instance | `rename_instance` | `name` | `new_name` |
| instance | `set_instance_properties` | `name` | `xy?, orient?`（`xy` 必须写 point；`mag`/`master` 只读，不在本版） |
| mosaic | `place_mosaic` | —（新建） | `master_lib, master_cell, master_view="layout", name, xy, orient` , `rows, cols, row_pitch, col_pitch` |
| mosaic | `delete_mosaic` | `name` | — |
| via | `place_via` | —（新建） | `via_name, xy, orient="R0"`；techfile-gated（§1.2.2） |
| via | `delete_via` | `via_name + xy + orient` | — |

索引约定：`rect`/`ellipse` 按 `bbox`；`polygon`/`path`/`line` 按 `points`（逐点比对，容差 0.001）；
`label` 按 `xy`（可加 `text`/`layer` 消歧义）；`instance`/`mosaic` 按 `name`；`via` 按 `via_name + xy + orient`。
命中多于一个且未给 `all=true` → 失败（fail closed）。

#### 1.2.1 LPP 与失败语义

- LPP 统一用 `["LAYER","PURPOSE"]`；数字层号可作底层 fallback，不作为业务接口；
- 底层 `dbCreateXxx` 失败**返回 nil 而不抛错** → 每个原子必须判返回值，失败即业务失败；
- 默认**不做** techfile 预检；`write` 可选 `strict_lpp=true` 时校验：`techGetLayerNum(tf, layer)` 非 nil +
  `purpose` 在 `tf~>purposes` 中（**不要用 `techGetPurposeNum`**，`drawing` 都返回 -1）；
- 删除统一 `dbDeleteObject`（重复删除安全）；不用 `leHiDelete`，不用不存在的 `dbDeleteObj` / `leDeleteFig`；
  批量删层用 `dbShapeQuery(cv lpp bbox 0 <stopLevel>)`，**stopLevel 必须覆盖层次**；
- 无 layout "check" 语义：`write` 末尾只 `dbSave`，返回 nil 即业务失败；不设独立 `check_and_save`。

#### 1.2.2 via（techfile-gated）

`place_via` 依赖 techfile 内的 via 定义：先探测 `tf~>viaDefs` 非空且 `techFindViaDefByName(tf, via_name)` 命中，
再用 `dbCreateVia(cv viaDef point orient)`；不命中直接给"techfile 内无该 viaDef"的明确失败，
不走到 `dbCreateVia(nil)`。via 定义的创建（`techCreateStdViaDef` 等）不在本版。

### 1.3 gds（导入 / 导出收拢为一个操作）

一个操作、两个方向：`action="export"`（layout → GDS）与 `action="import"`（GDS → layout）。
两者共享"显式路径域 + map 文件 + 轮询日志 + 产物校验"的口径。

| 参数 | 说明 |
|---|---|
| `action` | `export` / `import`，必填 |
| `lib / cell` | 必填；`view` 默认 `"layout"` |
| `file_path` | export：本机 GDS 目标路径；import：GDS 源文件（本机→上传，远端→直接用） |
| `layer_map` | layer map 文件（export 映射 OA LPP→stream 层号；import 用 `-layerMap` 把 stream 层号映射回 OA）。缺省时导出会走自动 mapping（层号不确定），导入在本环境会直接失败（`XSTRM-74`） |
| `ref_lib_file` | 仅 import：参考库清单（`-refLibList`），可选 |
| `tech_lib` | import 必填：目标库绑定/对齐的技术库（`-attachTechFileOfLib`） |
| `log_path` | export 默认 `<output stem>.xstream.log`；import 默认远端工作目录 `strmIn.log` |
| `timeout` / `poll_interval` | export 默认 300s / 0.5s；import 默认 600s / 3s |
| `cleanup_policy` | 仅 export：`success`（默认）/ `always` / `never` |

**export 行为**：

1. 校验：`file_path` / `log_path` / `layer_map` 互不相同、`layer_map` 是常规文件、数值为正有限；
   layer map 为 LF 行尾、每条记录 4 个必填字段（`layer purpose streamLayer datatype`）；
2. 远端 run 目录取本 token 的 role root（`query`）下的固定子目录（不生成事后不可重建的随机路径）；
3. **先 `dbSave` 目标 cellview**：XStream 只翻译磁盘上的已保存版本；会话里有未保存改动时
   导出内容不完整，且可能弹 "Save All" 模态框阻塞整个 SKILL 通道；
4. SKILL 侧：设置 XStream 字段（`library/topCell/view/strmFile/layerMap/logFile/runDir` +
   `virtualMemory="false"` 非阻塞读盘 + `showCompletionMsgBox="false"`），
   **先 capture 旧值再改**，用 `unwindProtect` 恢复，然后 `xstOutDoTranslate()`；
5. 轮询 XStream log：完成 = `XSTRM-234` + `Translation completed`；
   终态失败 = `XSTRM-273` / `Translation failed` / `OPEN_FAILED`（bounded 匹配，避免误伤 `XSTRM-2730` 等）；
   `XSTRM-25`（map 记录非法）/ `XSTRM-20`（覆盖已有文件）/ `Dropped Layers` 作为诊断返回；
6. **导出后收尾自己开的窗口**：IC6.1.8 的完成提示框可能无视 `showCompletionMsgBox`，
   模态框会阻塞后续 SKILL 调用 → 关闭 "Stream out translation complete" / "XStream Out"；
7. **log 先发布、GDS 后发布**；GDS 未通过（缺失/空/未稳定）不覆盖本机既有 GDS；
8. 返回 `gds_path / log_path / translated_structures / warnings`。

**import 行为**：

1. 前置校验：目标库在 `cds.lib` 可见（`ddGetObj` 非 nil）、`tech_lib` 可见、`strmin` 在命令角色可执行；
2. staging：本机 GDS / map 文件上传到远端工作目录并改写为 basename；
3. 命令（走 C 接口，不用 SKILL `system()`）：
   `strmin -library <lib> -strmFile <gds> -attachTechFileOfLib <tech_lib> -logFile strmIn.log [-layerMap <file>] [-refLibList <file>] [-topCell <cell>] -replaceBusBitChar`；
   `-topCell` 才是"只翻译输入流里的某个 cell"的合法选项（`XSTRM-80009` 里提示的 `-cell` 是厂商笔误）；
4. 轮询：每轮 `ddUpdateLibList()` + 读 `strmIn.log`；`XSTRM-273` + `Translation failed` 立即失败；
   `XSTRM-234` + `Translation completed` 才算完成；**完成前不得读目标 cellview**（会读到旧版 stale bbox）；
5. 完成后校验并返回 `instance_count / shape_count / bbox`；
6. `strmin` 的 `system()` 返回码不可信（可能"假失败但仍在跑"）→ 只用日志 + 产物判成败。

**共用返回**：`ok / action / reason / timed_out / log_path / errors / warnings`；
`reason` 取值：`completed` / `xstream_failure` / `xstream_errors` / `incomplete_log` / `missing_gds` /
`empty_gds` / `staging_error` / `publication_error` / `cleanup_error` / `tool_missing` / `target_lib_missing`。

范围：只承诺 GDS；**不做 OASIS**。export 走 SKILL XStream Out（不是命令行 `strmout`），import 走 `strmin` 命令。

### 1.4 screenshot

口径与 schematic / maestro 完全一致（同一套窗口定位 + `hiWindowSaveImage` + 下载约定）：

| 参数 | 说明 |
|---|---|
| `lib / cell / view` | 默认目标；用于在窗口列表里按 `w~>cellView` 的 lib/cell/view 匹配已开窗口 |
| `window_id` | 可选显式目标；**显式给了坏 id 直接业务失败，不做 X11/display 回退** |
| `region` | `[x0,y0,x1,y1]`（user units）；截前 `hiZoomIn(window bbox)` 把区域填满窗口 |
| `toplevel` / `central_widget` | 透传给 `hiWindowSaveImage` |
| `leave_open` | 默认 `false`；只关闭本操作自己打开的窗口，不动别人已开的窗口 |

规则：

- 格式固定 PNG；窗口按 cellView 匹配不到时才 `geOpen` 打开（`?mode "r"`）；
- **禁止不带 bbox 的 `hiZoomIn`/`hiZoomOut`**（会进交互橡皮筋并卡死 SKILL 通道）；
- 远端存该 token 的 role root 的 `screenshots/`，本地存客户端工作目录 `artifact/screenshots/`；
- `hiWindowSaveImage` 失败即业务失败；无内容窗口会截出单色黑图（属正常，不是失败）。

### 1.5 display（展示，不落数据）

只改编辑器/会话状态，需要显式 `lib/cell`（或 `window_id`）：

| 原子 | 底层 | 说明 |
|---|---|---|
| `set_layers_visible` | `leSetLayerVisible(lpp t/nil tf)` | 指定 LPP 显示/隐藏 |
| `show_only_layers` | `leSetAllLayerVisible(nil tf)` + 逐个显示 | 只显示指定 LPP |
| `set_entry_layer` | `leSetEntryLayer(lpp tf)` | 录入层（LSW 当前层） |
| `fit_view` / `zoom` | `hiZoomAbsoluteScale(w n)` / `hiZoomIn(w bbox)` | 需窗口；显式 `window_id` |

不做：`highlight_net` 与"选中"（IC6.1.8 无 `hiHighlightSet`；`geSelectFig`/`geGetSelSet`
在无真实输入焦点的会话里不可靠），LSW 交互函数（`leHiLayerGen` 等）也不封装。

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 归属（不在本包）

| 能力 | 归属 |
|---|---|
| view create/replace/delete/rename、cell delete | cellview |
| 结构 Verilog 导入 `ihdl`、PG label、标签后处理流水线 | digital-import |
| 截图机制（窗口解析、抓屏、下载） | gui 机制 + layout 领域封装 |
| selection / highlight / LSW 交互 | 不进业务 API |

## 3. 不在本版

- 路由抽象（多层/总线）与 `clear_routing`：调用方用几何原子组合；
- instance 层级树展开、parent/child 与 figure group；
- mosaic / instance 的 PCell 参数写入（`dbCreateParamInst` 只对 pcell super master 有效）、`mag` 缩放；
- via 定义创建、OASIS、layer map 管理；
- 按选择集删除（`leHiDelete`）、`clear_current_layout`；
- 并发写。

## 4. 决策记录（2026-09-21）

| # | 决策 |
|---|---|
| 1 | `display` 作为 layout 的展示子操作（底层 `le*` SKILL，不需要 GUI 也能改可见性） |
| 2 | `export_gds` 放 layout 包（旧公开面即 `client.layout.export_gds`） |
| 3 | GDS 导出的 `reason` 收敛为 §1.3 的 9 个值，不沿用旧 13 值枚举 |
| 4 | via 本版实现，但标注 techfile-gated；真机验收需带 PDK 的环境 |
| 5 | region 查询本版做；`depth>0` 只走 `dbShapeQuery` 路径，不展开完整层级树 |
| 6 | `strict_lpp` 默认 `false`（轻校验），严格模式可选 |
| 7 | 旧 `route_multilayer`/`route_bus`/`clear_routing` 降级为调用方组合；`set_visibility` 进 `display`；`select_delete`/`delete_cell` 不进 API（cell 删除归 cellview） |
| 8 | **GDS 导入与导出都归本包**，收拢为一个 `gds` 操作（`action=export\|import`）；digital-import 只保留 `ihdl` / PG label / 标签后处理 |
| 9 | 截图口径**参考 schematic + maestro**：cellView 匹配窗口 → `geOpen` 兜底、`window_id` 显式则坏 id 直接失败、`region` 用 `hiZoomIn(bbox)`、`toplevel/central_widget` 透传、PNG 落 role root `screenshots/` 与本地 `artifact/screenshots/`、无 X11 回退 |
| 10 | `gds` 的参数按 vendor 选项拆开：`layer_map`（导出/导入的层映射）与 `ref_lib_file`（仅导入 `-refLibList`）；导入选 cell 用 `-topCell` |
| 11 | 索引容差由 0.001 收敛为 **0.0005**（半个 dbu）；via 索引改为 `xy + orient`（viaDef/name 不可回读） |

## 5. 真机事实（IC6.1.8，2026-09-21 实测）

1. `a` 模式对不存在的 view 会**创建**；`w` 会**清空**已存在内容 → write 固定 `a` 且先探测；
2. `cv~>cellViewType` 才是 viewType（`~>viewType` / `~>viewTypeName` 都是 nil）；
3. `dbCreateXxx` 失败分两类：**非法 LPP → 抛 SKILL 硬错误**；**几何非法 → nil + WARNING** →
   上层既要判返回值也要能收错误；`xy` 写 **point**（`7:8`），`bBox`/`points` 写 list；
4. **`dbClose` 不落盘**：必须显式 `dbSave` 后再 `dbClose`；未保存的 cellview 留在会话里会污染导出
   （只导出磁盘旧版本）并可能弹模态框；
5. `cv~>shapes` 只含**顶层图形**；via / instance / mosaic 分别在 `cv~>vias` / `~>instances` / `~>mosaics`；
6. 区域/层级查询显式给 level（`dbShapeQuery(cv lpp bbox 0 32)`）；3 参数默认形式会下探一层 instance
   但**不含 via 生成图形**，不要依赖默认；
7. 坐标按 **0.001 网格**吸附 ⇒ 索引容差取 **0.0005（半格）**；用 0.001 会把相邻两格误判为相等；
8. rect **没有 `points`**（用 `bBox`）；path 的 `points` 是中心线、宽度走 `~>width`，`bBox` 含半宽；
   label 文本在 `~>theLabel`，其 `bBox` 由字体度量推导；
9. via 的 `~>viaDef` / `~>name` **不可读**（都是 nil）⇒ 只能按 `xy + orient` 索引；
10. via 不属于 `cv~>shapes`，但 `dbShapeQuery` 会以 `(via shape)` 形式返回其生成图形；
11. `hiGetCurrentWindow()` 返回的是 CIW（可能未实例化），开窗口用 `geOpen`；
12. IC6.1.8 **不存在**：`dbDeleteObj`、`leDeleteFig`、`dbGetLayer*`、`dbCreateMosaic`、`dbCreateViaByName`、
    `viaGetViaDef`、`techGetViaDef`、`leSetActiveLayer`、`leGetVisibleLayers`、`hiHighlightSet`、
    `hiLayerControl`、`leHiLayerControl`、`hiOpenCellView`；`techGetPurposeNum` 存在但不可靠（`drawing` 返回 -1）；
13. 依赖 techfile/PDK：via 定义、真实金属层作图；`leGetValidLayerList` 只反映 LSW 可录入层，
    **不能**用来判断 `dbCreate*` 是否接受某 LPP（真机已验证 `("y0" "pin")` 不在列表里但可建）；
14. XStream Out 走 Virtuoso Framework License，**不需要 PDK、不需要版图窗口**，只需要活着的 CIW 会话；
    但导出后可能弹 "Stream out translation complete" 模态框（`showCompletionMsgBox` 不可靠），需自行关闭。
