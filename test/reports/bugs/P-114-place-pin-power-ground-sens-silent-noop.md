# P-114 · `place_pin` 的 `power_sens`/`ground_sens`/四属性组合**报 ok 但零对象**（静默 no-op）；`off_sheet` 单用报 `nth: argument #1 should be an integer`

| 字段 | 值 |
|---|---|
| 级别 | P2（静默 no-op：调用方以为建好了 pin，实际库里什么都没有；与 C10/P-092 同族但更隐蔽） |
| 层 | 上层（schematic 包）· `place_pin` 可选属性参数（P-113 残留） |
| 归属 | 设计侧（已修：`place_pin` 可选实参对齐；P-113 修完后暴露的残留） |
| 状态 | **待测试侧** |
| 位置 | `src/pyapi/packages/schematic.py` 的 `place_pin` 分支（可选实参 `off_sheet`/`power_sens`/`ground_sens`/`sig_type` 的拼装与位置对齐）。 |
| 首报 | 2026-09-30（P-113 修复后复跑 `place_pin` 四档时发现：三档静默 no-op + 一档硬报错） |
| 最近更新 | 2026-09-30 18:20（设计侧已修 + PIN-OPT 真机 51 行绿证据，转测试侧收口） |

## 现象

真机（vblog，2026-09-30，P-113 修复 commit `0e14c8b` 之后；每个档都在**新建空 cell**上单独跑）：
① `power_sens="powerSensitive"` → `write ok=True`，但 `read(positions).pins=[]`、`read(connectivity).pins=[]`、`nets={}` —— **静默 no-op**；
② `ground_sens="groundSensitive"` → 同上（ok 但零对象）；
③ 四属性组合（`sig_type+off_sheet+power_sens+ground_sens`）→ 同上（ok 但零对象）；
④ `off_sheet=True` 单独 → 硬报错 `("nth" 0 t nil ("*Error* nth: argument #1 should be an integer" nil))`；
⑤ 对照：不带可选属性的普通 pin → 正常建出（positions 有图形、connectivity 有同名 net）；`sig_type="signal"` 单独 → 正常建出且 `numBits/sigType` 可值级读回（P-113 已验收）。

## 复现

```text
`python test/artifacts/tmp/probe_power_pin.py`（逐档新建空 cell 后各跑一次，打印两路读回）；TB 侧：`test/live/packages/schematic_e2e_tests.py::PIN-OPT`（已按红钉写法固定）。
```

## 证据

`test/artifacts/evidence/round9/schematic-place-pin-residual-p114.txt`（五档实测：baseline / 普通 pin / power_sens / ground_sens / off_sheet / 四属性 / off_sheet+power）；TB 证据 `test/artifacts/evidence/round9/schematic-r9l.txt`（11/11 PASS，含 P-114 红钉用例）。

## 验收判据（修好即转绿）

① 四个可选属性**单独**与**任意组合**都能真正建出 pin（positions 有图形 + connectivity 有 net/term）；② 不得出现"报 ok 但零对象"；③ `off_sheet` 单用不再 `nth`；④ TB `PIN-OPT` 从红钉升级为值级断言后跑绿。

## 下一步 / 责任人

**设计侧已修 `09af55c`（2026-09-30 16:04）**：power/ground sens 先校验目标 terminal 存在（缺失结构化失败）、`schCreatePin` 后校验 pin 真创建（nil/0 不得报 ok）、`off_sheet=true` 无可用 master 时结构化拒绝。真机单点复验：`test/artifacts/evidence/verify-fix-r10/p114-pin-opt-green.json`（PIN-OPT 51 行判据全 PASS：power/ground 正例建出 PSENS、缺 terminal 负例、off_sheet/四属性结构化拒绝、sig_type 值级读回）。待测试侧复跑 schematic 全量后把本卡移入已关闭。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
