# P-073 · 原理图 pin 原子操作与「pin 有效名」不一致：rename_pin 静默无效、set_pin_properties 把 pin 名改成自动名

| 字段 | 值 |
|---|---|
| 级别 | P2（写操作语义错误；set_pin_properties 静默改坏用户数据） |
| 层 | 上层（schematic 包） |
| 归属 | 设计侧（上层 schematic 包 `_atomic_skill`） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/schematic.py:615-637`（`delete_pin`/`rename_pin`/`set_pin_properties` 按 **pin 实例** 匹配并把实例名当 pin 名）、`:601-614`（`place_pin`）；spec `2-schematic.md:59` 表格 |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

## 现象

真机实测（`DI65` 与 `PINOP` 两个 cell，两种环境）：
① `rename_pin` 返回 `status=success, output="新名"`、`check_and_save` 返回 `saved`，但 `virtuoso.schematic.read` 的 pin 列表**仍是旧名**、`symbol.generate` 二次出图的端口名**也仍是旧名**（下游网表看到的端口没变）；直接读 DB 才看到只有 **pin 实例名**被改了（`("PIN0" "ipin")` → `("a2" "ipin")`）——即对用户是**静默无操作**。
② `set_pin_properties`（改 direction）写成功，但 pin **名字被换成自动名**：`y` → `PIN1`，symbol 端口也跟着变成 `PIN1` —— 用户只改方向，端口名被改坏。
③ `delete_pin` 行为正确（pin 从 read 列表消失）。

## 复现

```text
`python test/semi/probes/schematic_pin_ops_probe.py --token <PDK_TOKEN>`（token 从 `test/artifacts/env/log-vblog/registry.json` 的 calprobe 条目取；报告里不写明文）（四个角度：write 自报 / schematic.read / symbol 端口 / DB 里 pin 实例名）；迭代链侧复现：`python test/live/flows/design_iterate_tb.py --stage all`（`r2_edit` 的 `pin-renamed`、`r2_sym` 的 `symbol-terms-round2` 两条断言）
```

## 证据

`test/artifacts/evidence/round7/pin-ops.json`（三轮步骤逐条留证）、`test/artifacts/evidence/round7/design-iterate/iterate-r2_edit.json`、`.../iterate-r2_sym.json`、`test/artifacts/evidence/round7/design_iterate_run.log`

## 验收判据（修好即转绿）

三个原子在真实 cell 上语义正确：`rename_pin` 后 read 与 symbol 端口名都变；`set_pin_properties` 只改方向、pin 名保持不变；`delete_pin` 后端口消失；并补离线用例钉住（断言必须落在「下游可见的 pin 名」，不是实例名）

## 下一步 / 责任人

设计侧：pin 的**有效名**在标签/端口对象上，`rename_pin` 要改的是它（或同步改实例名+标签），`set_pin_properties` 不能用实例名去重建 pin。测试侧：修好后重跑 `design_iterate_tb` 与`schematic_pin_ops_probe`（本轮这两处是**已登记的预期红**）


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
