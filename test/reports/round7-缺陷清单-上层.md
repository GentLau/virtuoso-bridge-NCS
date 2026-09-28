# 第七轮 · 缺陷清单（上层 / 源码类）

> 送修视图。**权威事实**仍在 `test/reports/问题登记.md`（台账）与 `test/reports/bugs/`（未关闭卡片）。
> 本轮新增 **2 条**（P-073、P-074），复验 **1 条**（P-069 → LVS 拿到 `correct`），其余未关闭项 1 条（P-070 待口径）。

## 0. 本轮结论一句话

产品在 **calibre 官方 auCdl + LVS** 这条链上已经从"跑不通"变成"**拿到 CORRECT**"；
但**原理图 pin 原子操作**在真机上暴露出新的语义缺陷（改名的可见效果、改方向会破坏 pin 名），
另有 1 条 spec/实现口径不一致会持续绊住写 TB 的人。

## 1. P-073（新立，P2）· pin 原子操作与"pin 有效名"不一致

**一句话**：`rename_pin` 返回成功但**改不动用户看得见的名字**；`set_pin_properties` 改方向时把
**pin 名换成自动名**（`y` → `PIN1`），下游 symbol/网表端口名跟着变。

| 项 | 内容 |
|---|---|
| 位置 | `src/pyapi/packages/schematic.py:615-637`（`delete_pin`/`rename_pin`/`set_pin_properties`），`:601-614`（`place_pin`） |
| 根因（测试侧判断） | 这三个原子按 **pin 实例** 匹配/改名，把**实例名**当成了 pin 名；而 pin 的**有效名**在 pin 标签/端口对象上（实例名多为自动名 `PIN0/PIN1/...`） |
| 症状 ① | `rename_pin`：write `status=success, output="a2"`、`check_and_save=saved`；随后 `schematic.read` 的 pins 仍是 `["a","y"]`，`symbol.generate` 出的端口仍是 `a`；DB 里只有实例名从 `PIN0` 变成 `a2` ⇒ **对用户是静默无操作** |
| 症状 ② | `set_pin_properties(y→input)`：write 成功，但 read 的 pin 变成 `["a","PIN1"]`，symbol 端口变 `["PIN1","a"]` ⇒ **用户只改方向，端口名被改坏** |
| 对照（正常） | `delete_pin` 行为正确：pin 从 read 列表消失 |
| 复现 | `python test/semi/probes/schematic_pin_ops_probe.py --token <PDK_TOKEN>`（四角度：write 自报 / read / symbol / DB 实例名）；迭代链：`python test/live/flows/design_iterate_tb.py --stage all`（`r2_edit.pin-renamed`、`r2_sym.symbol-terms-round2` 两条红） |
| 证据 | `test/artifacts/evidence/round7/pin-ops.json`、`test/artifacts/evidence/round7/design-iterate/iterate-r2_edit.json`、`.../iterate-r2_sym.json` |
| 验收判据 | ① `rename_pin` 后 read 与 symbol 端口名都变；② `set_pin_properties` 只改方向、pin 名不变；③ `delete_pin` 后端口消失；④ 补离线用例（断言落在"下游可见的 pin 名"） |
| 备注 | 这两条红是**测试侧故意保留**的钉住项（见 `round7-TB修正.md` 末节），修好即自动转绿 |

## 2. P-074（新立，P3）· spec 表格与实现的 pin 索引口径不一致

**一句话**：spec `2-schematic.md:59` 表格写 pin 的索引是 `xy`，实现要 `x`/`y`；
照表格写必然 `command N invalid: 'x'`。

| 项 | 内容 |
|---|---|
| 位置 | `spec/design-concepts/上层/2-schematic.md:59`（`delete_pin/rename_pin/set_pin_properties` 标 `xy`） vs `src/pyapi/packages/schematic.py:615-616`（`cmd["x"]`/`cmd["y"]`） |
| 影响 | 所有写 TB 的人（含本轮的我）都会先踩一次；错误信息是裸露的 `KeyError('x')`，不提示"要用 x/y" |
| 复现 | 把 `design_iterate_tb.py:R2_RENAME` 改回 `{"op":"rename_pin","xy":[6.0,0.0],...}` 即复现 |
| 验收判据 | 口径一致（建议实现同时接受 `xy` 与 `x`/`y`，或 spec 改写成 `x`,`y`），且校验失败信息指名缺哪个字段 |

## 3. P-069（复验 → 本轮的结论是「已修好」，等上层确认销案）

**本轮拿到了 LVS 的确定结论 `correct`**，两条入口都通：

| 入口 | 调用 | 结果 |
|---|---|---|
| deck 入口（P-069 验收判据） | `calibre.export_cdl(CMP_LIB/inv2, 680 B)` → `virtuoso.layout.gds(inv2)` → `calibre.lvs(deck+cdl)` → `calibre.read_results(job_id)` | `status=correct`，counts：ports 4/4、nets 4/4、inst 1/1、`differences=[]` |
| runset 入口（上一轮已验，本轮沿用结论） | `calibre.lvs(runset=…jy_ctle.lvs)` | `completed / correct`（mode=official-batch） |

证据：`test/artifacts/evidence/round7/design-iterate/iterate-lvs.json`（含 `results_inv2` 全量摘要）。
**注意**：`_calibre.lvs_`（tvf 格式）不是合法 runset，用它当失败证据是**用错文件**（见 TB 注释）。

## 4. P-070（未关闭，等口径）

蒙特卡洛：`src/` 全库只有 1 行 MC 相关代码（读回结果），**没有驱动 MC 分析的实现**；
spec 的分析枚举里也没有 `montecarlo`。等产品定"支持驱动 or 明确不做"，测试侧再补真机验证或不覆盖声明。
本轮**没有**为它新增断言（避免在口径未定时制造假红）。

## 5. 给设计的优先级建议

1. **P-073**（P2）：pin 名语义错误会静默改坏用户原理图数据，建议优先；
2. **P-074**（P3）：一行文档/一次校验信息的成本，能省掉后来者每次踩坑；
3. **P-070**：需要一句产品口径（支持 or 不做），测试侧才能收口覆盖矩阵里的 MC/PVT 一栏。
