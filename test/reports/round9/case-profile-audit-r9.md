# round9 · op「用例档位」覆盖审计（铁律②：最简/日常/边界/非法）

> 工具（临时）：`test/artifacts/tmp/case_profile_audit.py`｜数据：`test/reports/round9/op-param-matrix.json`（2026-09-30 13:53 生成）
> 口径：**静态近似**——按"该 op 在 semi/live 的调用点数量"判"是否只有一条用例"，按关键词
> （`expect_fail` / `_write_fails` / `must fail`）判"是否有非法输入档"。**不等于**语义分档（最简/日常/边界）已齐。

## 1. 结果

| 指标 | 数值 |
|---|---|
| 业务 op（矩阵口径） | **79** |
| semi/live 调用点 <2（疑"只有一条用例"） | **12 → 2**（余 2 个复核为误报） |
| semi/live 无"非法输入档"线索 | **20**（逐条复核见 §3b；其中 calibre 5 个按"环境限制 → skip"） |

## 2. 只有一条用例的 op（12）

`virtuoso.cellview.cat.add_cell`、`virtuoso.cellview.cat.rename`、`virtuoso.cellview.cell.copy`、
`virtuoso.cellview.cell.rename`、`virtuoso.cellview.lib.copy`、`virtuoso.cellview.lib.rename`、
`virtuoso.cellview.view.copy`、`virtuoso.cellview.view.rename`、`virtuoso.gui.list_windows`、
`virtuoso.skillref.info`、`virtuoso.symbol.check_and_save`、`virtuoso.verilog.write`

> 说明：cellview 的 copy/rename 族在 `cellview_e2e_tests` 里各只有一次真实调用（正例），
> 而且**没有"目标已存在 / 源不存在"这类非法档**（见下）。

### 2b. 处置结果（2026-09-30 续补）

| op | 处置 |
|---|---|
| `cellview.{lib,c ell,view}.{copy,rename}`、`cat.{add_cell,rename}`（8 个） | ✅ **已补**：`cellview_e2e_tests.NEG2` 新增 **15 条非法档**（目标已存在 / 源不存在 / 已在类目 / 不在类目 / 非法 view_type / 非法技术库），逐个断言**具体错误码**，并断言目标对象不重复、源对象仍在 → TB **6/6 PASS**（`evidence/round9/cellview-r9j.txt`） |
| `symbol.check_and_save` | ✅ **已补**：`CHECK-01` 增加"缺失 view 必须结构化失败且点名 view" → `symbol_e2e_tests` **9/9** |
| `verilog.write` | ✅ **已补（红钉）**：非法档发现 **P-115**（缺 `ensure_view` 时静默创建半成品 view；非法 `view_type` 不校验），按红钉固定 → `verilog_e2e_tests` **4/4** |
| `gui.list_windows` | ✅ 复核为**误报**：该 op 无参数，`gui_e2e_tests.GUI-01` 用"窗口集合前后差集"做值级判据，已足够 |
| `skillref.info` | ✅ 复核为**误报**：`INFO` 用例已含"命中内容断言 + 缺失函数负例" |

## 3. 没有非法输入档线索的 op（20）

`basic.command.run`、`basic.skill.execute`、`calibre.export`、`calibre.lvs`、`calibre.pex`、
`calibre.read_results`、`calibre.status`、`spectre.run`、`virtuoso.cellview.lib.create`、
`virtuoso.cellview.view.create`、`virtuoso.gui.list_windows`、`virtuoso.layout.gds`、
`virtuoso.layout.read`、`virtuoso.layout.write`、`virtuoso.schematic.check_and_save`、
（及清单里其余 5 个）

> 说明：像 `layout.read` 的非法 `view_type`（P-080）、`layout.gds` 的坏路径等**其实已有负例**
> （分布在参数面 TB 里），关键词没命中 → 本表**必须人工复核**后再定缺口；这里只作为"优先排查清单"。

### 3b. 逐条复核结果（2026-09-30）

| op | 复核结论 |
|---|---|
| `basic.command.run` | ✅ 已有：超时档（rc=124/kind=timeout）。**本轮新增**非零退出（`exit 7`→`ok=false`+`rc=7`）与不存在命令（rc=127）→ `infra.BASIC-06` |
| `basic.skill.execute` | ✅ **本轮新增**：语法错 `1+` → 结构化失败 + 错误文本非空 |
| `basic.gui.run` / `basic.spectre.run` | ✅ **本轮新增**：不存在命令 → 业务失败且 rc 非 0 |
| `calibre.{export,lvs,pex,read_results,status}` | ⏭ **环境限制 → skip**（用户 2026-09-30 裁定）：按"环境限制：<具体>"记录，不算缺陷、不算覆盖 |
| `spectre.run` | ✅ 已有：RUN-04 坏网表（且本轮把假绿修成真断言） |
| `virtuoso.cellview.lib.create` / `view.create` | ✅ **本轮新增**：`lib.create` 已存在→`libraryExists`、技术库不存在→`technologyLibraryNotFound`、`view.create` 非法 view_type→`createFailed` |
| `virtuoso.gui.list_windows` | ✅ 无参数，不适用负例 |
| `virtuoso.layout.gds` | ✅ 已有：`cleanup_policy="bogus"` → 结构化失败 |
| `virtuoso.layout.read` / `layout.write` | ✅ 已有：坏 `view_type`（P-080）、非法几何/LPP 分类（`layout_geometry_classification_e2e_tests`） |
| `virtuoso.schematic.check_and_save` | ✅ **本轮新增**：缺失 view → 结构化失败且点名 |
| `virtuoso.schematic.read` / `write` | ✅ 已有：NEG-pos（`xy`/拆字段被拒且点名 `pos`）；read 侧非法 `view_type` 由 P-080 同族覆盖 |
| `virtuoso.symbol.generate` | ✅ 已有：不 overwrite / 同源同目标 → 结构化失败 |
| `virtuoso.symbol.read` / `symbol.screenshot` | ✅ 已有：缺失 view 负例（WRITE-03 同族）+ 坏 `view_type`（P-105） |

## 4. 下一步（本轮未做，留下一步）

1. 把"用例档位"做成**语义口径**而不是关键词：每个 op 标注 4 档（最简/日常/边界/非法）分别由哪条用例承担，
   与表 B（参数）、表 C（输出字段）同源维护；
2. 先处理 §2 的 12 个"单例 op"：补"目标已存在/源不存在/名字非法"等非法档与一个"日常"档；
3. §3 的 20 个人工逐条复核（多数可能已有负例，只是不在同一文件里）。
