# C0 · 测试规范缺失：无显式 TB 流程约定（环境检查→构建→完备校验→执行→比对），delete/rename/set 类原子在 semi/live 层系统性无覆盖

| 字段 | 值 |
|---|---|
| 级别 | P2（测试规范缺陷；导致覆盖系统性缺口 + 缺陷漏检） |
| 归属 | 测试侧（规范制定 + 覆盖补齐） |
| 状态 | **规范已落地（2026-09-28）；覆盖补齐进行中（B1–B4）** |
| 位置 | `test/docs/写TB规范.md`（六步流程与状态还原，2026-09-28 精简合并后的唯一规范入口） + 三层测试的写原子覆盖；核账脚本 `test/shared/runners/audit_atom_coverage.py` |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

## 现象

独立审计（2026-09-27）发现 delete/rename/set 类写原子在**半真机与真机两层无覆盖**，其离线证据只是「拼出合法 SKILL 文本」的契约断言（FakeMiddle mock），从不执行、无结果比对。测试侧 2026-09-28 核账（60 个原子，schematic/layout/symbol）：**semi/live 两层零引用 12 个**——schematic 的 `delete_instance/delete_note/delete_wire/place_note/place_wire/rename_note/set_note_properties/set_wire_properties`、layout 的 `delete_instance/delete_mosaic/`fit_view/zoom`；另有 20+ 原子 **semi 层**单缺。
根因：`test/reports/internal/测试架构-内部.md §3` 的覆盖度模型是**能力域级**（「某包测没测」），粒度不足以发现包内原子缺口；且此前**没有** TB 执行流程与状态还原约定，delete/rename/set 类原子需要「先造既有对象」，成本高被系统性绕开。

## 复现

```text
`python test/shared/runners/audit_atom_coverage.py --md`（打印 60 原子 × 三层引用面 + GAP 列表）；证据 `test/artifacts/evidence/atom-coverage-2026-09-28.json`；离线文本断言的典型形态见 `test/offline/unit/test_schematic_contracts.py:209-257`
```

## 证据

`test/reports/原子覆盖审查-2026-09-28.md`（逐条复核 C0 的清单与「只发不核」意见）；`test/docs/写TB规范.md`（六步流程 + 状态还原 + 最小判定强度）；`test/artifacts/evidence/atom-coverage-2026-09-28.json` / `.txt`

## 验收判据（修好即转绿）

① 六步 TB 流程与状态还原规则落地为规范（**已满足**，见 `test/docs/写TB规范.md`）；② 12 个两层缺口原子按六步补齐 semi 探针或 live e2e（place→read→delete→read 消失 / rename→read 改名 / set→read 属性变化），`audit_atom_coverage.py` 的 gap 列表逐步清零；③ 2 处弱判据（SerDes 的 calibre lvs/drc 只看 ok）改为读 `calibre.read_results` 结论

## 下一步 / 责任人

测试侧：B1（schematic 8 原子）→ B2（layout 4 原子，display 原子用窗口/截图判据）→ B3（弱判据修正）→ B4（按规范 §7 清单抽查 5 份现役 TB）。每批完成即重跑核账脚本更新本卡状态；关闭判据是 gap=0 且 weak=0

## 独立审计原文（2026-09-27，逐字保留）

> 来源：独立审计卡片 `C0-测试规范-AAA与状态还原缺失.md`。测试侧 2026-09-28 把它并入生成器（`make_bug_cards.py`）以防刷新丢失；上面「现象/根因/验收」是测试侧的**核账后**版本，本节保留审计原文以便对照。

### 现象

独立审计（2026-09-27）发现：**12 个写原子在半真机（semi）和真机（live）两层均无任何测试覆盖**，且**全部集中在 delete/rename/set（删除/改属性）类**：

- schematic（10）：`delete_instance`、`rename_instance`、`place_wire`、`delete_wire`、`set_wire_properties`、`set_label_properties`、`place_note`、`delete_note`、`rename_note`、`set_note_properties`
- layout（6）：`delete_label`、`set_label_properties`、`delete_instance`、`delete_mosaic`、`fit_view`、`zoom`

这些原子在**离线层只有「拼出合法 SKILL 文本」的契约断言**（FakeMiddle mock），从不经真机执行、无结果比对。

### 根因（测试规范缺陷）

测试没有一条显式的 TB 流程规范（环境检查 → 构建 → 完备校验 → 执行 → 比对）与**前置构建干净基线**的约定，导致：

1. place（新建）类 Arrange = 空画布，几乎免费，被充分测试；
2. delete/rename/set 类 Arrange = 需先 seed 一个已知对象（本身依赖 place 或 fixture 注入），成本高，被系统性绕开；
3. cellview 是**持久化**对象（非无状态函数），无「前置构建/还原干净基线」约定 → 跨用例污染风险，进一步劝退写 delete/set 类测试。

### 关联缺陷（由本规范缺陷直接/间接导致）

- **P-073**（rename_pin 静默无效）：rename 类长期无真机闭环，拖到真机探针才暴露；
- **P-074**（spec/实现 pin 索引口径不一致）：定位参数语义无真机验证的同类症状；
- **P-072**（init_work_dir 一次性化）、**P-068**（两用户工艺绑定不一致）：同为「状态管理无规范」的症状。

### TB 规范流程（6 步，已定 —— 已落入 `test/docs/写TB规范.md` §1）

每份 TB 按如下顺序执行，**完成后不清理现场**；现场干净由第 2、3 步（前置构建）负责：

1. **检查环境是否为所需测试环境**：不是所需环境 → TB 直接失败（所需环境通常为日常；写 TB 尽量用日常，非日常需求写好 TB 后移交测试工程师）。
2. **检查当前环境并构建测试环境**：要读原理图就准备一张要读的原理图；要写原理图就准备一张**要被写的原理图**（并还原到未写基线）。
3. **最终检查环境**：确认被测动作所需环境已完备（该有的对象/视图/前置状态都在、且干净）。
4. **执行操作**。
5. **比对结果并记录**（理想 vs 实际）。
6. **重复 4、5**，直到本 TB 完结。

### 审计给出的验收判据

1. 上述 6 步 TB 流程落地为测试规范文档；
2. 上述 12 个双缺失原子按 6 步流程补上 semi 探针或 live e2e（「place→read→delete→read 确认消失 / rename→read 确认改名」闭环）。

---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
