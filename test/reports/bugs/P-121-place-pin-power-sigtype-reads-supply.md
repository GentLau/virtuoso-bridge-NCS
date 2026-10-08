# P-121 · `place_pin(sig_type="power")` 写入成功，但 `read(connectivity).nets[...].sigType` 读回 `"supply"`（其余 9 个取值原样回读）——spec 未写明该 DB 归一化

| 字段 | 值 |
|---|---|
| 级别 | P3（文档缺口：按 spec 值域做「写值==读回」断言会误判；调用方需知道映射） |
| 层 | spec↔真机一致性（上层 schematic 包）· `place_pin.sig_type` 读回 |
| 归属 | spec 侧（在 `2-schematic.md` 的 `sig_type` 值域处补一句：DB 会把 `power` 归一化为 `supply`，读回按 DB 词汇；或由实现/文档给出映射表） |
| 状态 | **待决策** |
| 位置 | spec `spec/design-concepts/上层/2-schematic.md`（`place_pin` 参数表 `sig_type`）；实现 `src/pyapi/packages/schematic.py:85-88`（10 值集合）与 `:727-728`（直接透传给 `schCreatePin`） |
| 首报 | 2026-09-30（round10 补 `sig_type` 10 值全枚举时发现） |
| 最近更新 | 2026-09-30 21:20（新立） |

## 现象

真机（vblog，2026-09-30）：10 值一次性写入同一 schematic（各建一个 pin）后 `read(focus=connectivity)`：analog/clock/ground/reset/scan/signal/tieHi/tieLo/tieOff **原样回读**，`power` → **`supply`**（Virtuoso DB 归一化）。

## 复现

```text
`PYTHONPATH=src python test/live/packages/schematic_e2e_tests.py`（`PIN-OPT` ④ 十值全枚举）；
或直接 `place_pin(sig_type="power")` 后读 `nets[<pin>].sigType`。
```

## 证据

`test/artifacts/evidence/round10/schematic-sigtype-sweep.json`（10 值写/读对照；TB 已按映射断言）

## 验收判据（修好即转绿）

① spec 写明 `power→supply` 归一化（或实现侧给出映射/别名）；② TB 断言与 spec 一致（当前＝按映射断言，并记录写值）；③ 不得出现「值域里有 power、读回永远拿不到 power 却无人知晓」的隐性契约。

## 下一步 / 责任人

等 spec owner 补一句；TB 已钉住映射（不阻塞）。


---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
