# P-116 · spec `3-symbol.md:200` 称 `schEditPinOrder` 后 `pin_order` 与 `port_order`/`term_order` 一致；真机实测 `term_order`（`cv~>termOrder` legacy raw）不同步（空/陈旧）

| 字段 | 值 |
|---|---|
| 级别 | P3（文档与真机不一致：按 spec 断言的测试必红；调用方可能把 term_order 当权威顺序） |
| 层 | spec↔真机一致性（上层 symbol 包）· orders 读回口径 |
| 归属 | spec 侧（已裁决：改 spec 文字，不改实现） |
| 状态 | **待测试侧** |
| 位置 | spec `spec/design-concepts/上层/3-symbol.md:35`（orders 字段）与 `:200`（真机结论表）；实现 `src/pyapi/packages/symbol.py:1133`（读 `cv~>termOrder`）/ `:698-711`（写 `schEditPinOrder`） |
| 首报 | 2026-09-30（测试/root：补 symbol orders 三键值级断言时发现） |
| 最近更新 | 2026-09-30 18:45（spec 侧裁决并落地：改文字不改实现，转测试侧） |

## 现象

2026-09-30 真机（vblog）两格对照：`schemtest/symfinal` → pin_order=port_order=`[IN,OUT,BI]`，term_order=`[OUT,IN,BI]`（陈旧不一致）；`schemtest/sym_e2e`（本包 `set_pin_order` 写过）→ pin/port=`[OUT,IN]`，term_order=`[]`（根本没写）。`schGetPinOrder`/`portOrder` 会被 `schEditPinOrder` 更新，`termOrder` 不会。

## 复现

```text
PYTHONPATH=src python test/live/packages/symbol_e2e_tests.py  # 最后一条 ORDERS-TERM（P-116 红钉）
或直接 `virtuoso.symbol.read(library=schemtest, cell=symfinal, view=symbol, focus=[orders])` 比对三键
```

## 证据

`test/artifacts/evidence/round9/symbol-p116.txt`（套件其余 9 条 PASS，仅红钉 FAIL，含两格实测值）

## 验收判据（修好即转绿）

① spec 与真机口径一致（改文字或改实现，二选一）；② TB `ORDERS-TERM` 按裁决转绿（若改 spec，则降级为“term_order 存在且为 list”）；③ 不允许 term_order 静默给出与 pin_order 不同的旧值却对外宣称一致。

## 下一步 / 责任人

**spec owner 已裁决（2026-09-30，用户）：走①改文字，不改实现**——`3-symbol.md:35/:200` 已改为“`term_order` 是 legacy raw、可能为空/陈旧、不得当权威顺序”；实现保持官方 `schEditPinOrder`（写 `pin_order`/`port_order`），不写 `cv~>termOrder`。待测试侧把 TB `ORDERS-TERM` 降级为“`term_order` 存在且为 list（允许与 `pin_order` 不同）”后把本卡移入已关闭。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
