# symbol 业务包 真机测试报告

> 版本：v1
> 日期：2026-09-21
> 执行环境：8127 / work-dir `test/tb/artifacts/log-vblog` / token `vb-vblog` / Virtuoso 6.1.8-64b（WSL `wsl-gent`）
> 测试库：`schemtest`（`symfinal` / `sym_e2e` / `gen_e2e`）
> 执行脚本：`test/tb/symbol_e2e_tests.py`（`--transport direct|http`）
> 依据：`spec/design-concepts/上层/3-symbol.md`（Draft v2）

## 1. 结论

**direct dispatch 9/9 PASS**；HTTP 8127 需重启加载 symbol 包（operations 51 → 56）后回归。

```
PASS    READ-01 symfinal structured read
PASS    READ-02 focus filtering
PASS    WRITE-01 create geometry/labels/pins
PASS    WRITE-02 delete/set atoms
PASS    CHECK-01 check_and_save
PASS    WRITE-03 missing view fails
PASS    WRITE-04 wrong view type fails
PASS    GEN-01/02/03 generate + overwrite
PASS    SHOT-01 symbol screenshot
```

## 2. 测试结果与证据

### 2.1 read

| 用例 | 输入 | 实测 |
|---|---|---|
| READ-01 | `read(schemtest/symfinal/symbol)` | terms=`IN(input)/OUT(output)/BI(inputOutput)`，bbox 与真机一致，`access_dir` 字段存在；`pin_order=[IN,OUT,BI]`；shapes 含 line/rect/polygon/ellipse；labels 含 `[@instanceName]`/`[@partName]`/`OUT`/`BI`；selection box `(-3,-3)-(5,3)` |
| READ-02 | `focus=["terms","orders"]` | 只返回 terms + `pin_order/port_order/term_order`，无 labels/shapes |

补充稳定性：连续 12 次 `read(symfinal)` 全部返回 3 个 terminal（无空读、无静默失败）。

### 2.2 write

| 用例 | 覆盖原子 | 实测 |
|---|---|---|
| WRITE-01 | `place_rect / place_polygon / place_ellipse / place_label(drawing,instance,logical) / place_pin ×2 / set_selection_box / set_pin_order` | 10/10 applied；回读 terms=`{IN,OUT}`、`pin_order=[OUT,IN]`、selection box 唯一 |
| WRITE-02 | 批 A：`set_shape_properties(rect,polygon) / rename_label / set_label_properties / rename_pin / set_pin_properties(access_dir) / delete_shape`；批 B：`delete_label / delete_pin` | 改名后 terms=`{IN,OUT2}` 且 pin-name label 同步为 `OUT2`（旧 `OUT` 无残留）；`access_dir` 回读 `["left"]`；`new_bbox=[0,0,2.5,2.5]` 回读一致；删除后 terms=`{IN}`、`[@partName]` 消失、pin 矩形只剩 1 个 |
| WRITE-03 | 目标 view 不存在 | 失败，且不创建 view |
| WRITE-04 | 同名 view 但 viewType 不同（`type_probe` 为 `schematic`） | 失败，错误文案区分“存在但类型不符” |
| CHECK-01 | `check_and_save(sym_e2e/symbol)` | `saved=true`（`schSymbolToPinList` 通过后 `dbSave`） |

### 2.3 generate

| 用例 | 输入 | 实测 |
|---|---|---|
| GEN-01 | `generate(gen_e2e, schematic→symbol_a)` | `action=created`，terminals=`{A,B,C}` |
| GEN-02 | 目标已存在 + `overwrite=false` | 失败（不写坏已有 view） |
| GEN-03 | `overwrite=true` | `action=replaced` |
| GEN-03b | `symbol_view == schematic_view` | 失败 |
| GEN-03c | 目标 symbol 已在窗口打开 + `overwrite=true` | 失败（保护打开中的 view） |

### 2.4 screenshot

| 用例 | 实测 |
|---|---|
| SHOT-01 | `screenshot(sym_e2e/symbol)` 返回本地路径，PNG 落盘且非空：`test/tb/artifacts/log-vblog/artifact/screenshots/sym_e2e-1789973191070-9f3d8ba2.png`（5082 B） |

截图有效性对照实验（`test/tb/symbol_screenshot_probe.py` + `blank_window_probe.py`）：

| 目标 | 产物 | 像素统计 |
|---|---|---|
| 空 symbol view（新建后立即截） | `probe-blank.png` 2475 B | 711×557，**1 色**（全黑） |
| `sym_e2e` symbol（有几何/标签/pin） | `probe-*.png` 5082 B | 711×556，**7 色**（黑底 + 红/黄/橙/白图形） |
| 三种参数变体（offscreen / grabFromScreen / toplevel） | 同一窗口产物逐像素一致 | 说明窗口已绘制时离屏渲染即可，无需 X11 回退 |

结论：`hiWindowSaveImage` 返回值在本机恒为 nil（SKILL 侧文案 `capture-failed`），但文件确实生成；
“全黑”只出现在**窗口无内容**时，属正常表现，不能用“文件存在”单独判定截图有效。

## 3. 关键真机机制（必须遵守）

1. **`a` 模式会凭空创建 cellview**：`dbOpenCellViewByType(..., "a")` 对不存在的 view 返回可编辑内存对象；`"r"` 对“不存在”和“viewType 不符”都返回 nil。因此存在性判定是 `ddGetObj`（区分 missing）+ `"r"` open（区分 mismatch），实测三态 `ok/mismatch/missing` 与预期一致。
2. **pin 删除是分层对象**：`dbDeleteObject(pin)` 只 detach figure，`dbDeleteObject(term)` 级联删 pin 但留下 figure/net。`delete_pin` 必须显式清理 pin → 矩形 figure → pin-name label，并在 net 无其它 terminal 时删 net。
3. **pin 改名不联动**：改 `term~>name` / `pin~>name` 不会改 net 名，也不会改 pin-name label；`rename_pin` 需显式 `dbRenameNet` + 手工同步 label（本轮已加入回归断言）。
4. **pin order 走官方 API**：`cv~>termOrder` 不是权威 pin order；`schEditPinOrder` 才是，写后 `schGetPinOrder`/`portOrder` 一致。
5. **generate 的 `ssgSortPins` 对显式 pin list 无效果**：`schPinListToSymbol` / `schPinListToSymbolGen` 两条路径下 alphanumeric 与 geometric 结果相同（按 schematic 端顺序），`sort_pins` 参数保留但**不承诺排序效果**。
6. **SKILL 多行文本的 `errset(progn` 陷阱**：daemon 对含换行的 SKILL 走“落盘 + `load()`”路径；此时若写成 `errset(progn` 换行再写语句，`errset` 会收到多个参数并报 `too many arguments (at most 2 expected)`。必须写成 `errset(progn(<第一条语句>` 的形式（或单行）。
7. **pin access direction 走官方 API**：`dbSetPinFigAccessDirection(fig list("left"))` 接受**列表**（传标量会报 `argument #2 should be a list`），回读用 `dbGetPinFigAccessDirection`；`read.terms.access_dir` 已用它做往返校验。
8. **pin-name label 需 `schGlueLabel` 才跟随 pin**：`schCreateSymbolLabel` 建的 label 默认 `parent=nil`；`place_pin` / `set_pin_properties(label=true)` 现在会把它 glue 到 pin 矩形上。
9. **`ssh`/底层其余发现（供后续扩展）**：`schCreateSymbolShape`（`style`/`width`，`solid` 落到 `device/drawing1` = 实心）、`dbCreatePath`（可写 `width`）、`dbMoveFig`（移动 pin/label/shape）在 IC6.1.8 均可用；本版未纳入原子集，已记录在 spec §3。
10. **IC6.1.8 渲染由 LPP/DRF packet 决定**：`schSetShapeStyle` 可写可读但不改变显示（`dbSetShapeStyle*` 系列函数在本机不存在）。

## 4. 已知限制

| 限制 | 说明 | 影响 |
|---|---|---|
| 无 width / color / lineStyle / fillStyle | IC618 的 `schSetShapeStyle` 标注为 ICADVM20.1 Only；`dbCreateLine/Rect/Polygon/Ellipse` 不暴露线宽与填充 | 几何样式沿用工艺库默认；`read.shapes` 不返回这些字段 |
| 无 pin / label 移动 | 只有 `place_pin(x,y)` / `place_label(x,y)` 建新对象；未提供 `move_*` 原子 | 移动 = delete + 重新 place（会丢失原对象 id） |
| `read` 的 `focus` 是事后过滤 | SKILL 端一次性收集全部内容，Python 侧裁剪 | 大 symbol 读取体积不受 focus 影响 |
| 索引容差固定 0.001 | shape/label/pin 定位按坐标匹配 | 与 schematic 同口径；同 bbox 同点数的几何现在按逐点比较消歧 |
| `write` 非事务 | 逐命令执行并记录步骤痕迹；中途失败时前面的命令已保存 | 失败响应里带 `commands applied: k/n` 提示 |
| 未覆盖 | 并发写、权限、超大 symbol 性能、`circle/arc/donut/path`、parent-child figure、symbol 内 hierarchy instance | 本版按 spec §3 明确不在范围 |

## 5. HTTP 8127 回归

- 8127 重启加载 symbol 后：`/health` = **56 operations**；
- `symbol_e2e_tests.py --transport http`：**9/9 PASS**（2026-09-21，与 direct 同口径）；
- 期间修掉一处测试脚本缺陷：HTTP 4xx 需要读 body 才能拿到 `ok=false + error` 信封，
  `HttpTransport` 现已捕获 `urllib.error.HTTPError`（此前 400 会直接抛异常）。
