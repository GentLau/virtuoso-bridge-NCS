# C09 · `maestro.write_history` 连续 rename（A→B，再 B→A）第二跳报 `ASSEMBLER-2404 Cannot find a setup database entry for handle`

| 字段 | 值 |
|---|---|
| 级别 | P3（重命名链不可用：`maestro_e2e_tests.HISTORY-01` 因此稳定红） |
| 层 | 上层（maestro 包）· write_history rename 链 |
| 归属 | 设计侧（按**完整套件**复现：maestro 包会话/SDB handle 生命周期；隔离路径已修但整链仍红） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/maestro.py`（`write_history` 的 rename 分支与 SDB handle 复用；`_open_session` 会话内 handle 在重命名后失效） |
| 首报 | 2026-09-29（round9 门禁复跑 + root 隔离复现） |
| 最近更新 | 2026-09-30 22:20（测试侧复跑：隔离路径已绿，完整套件 HISTORY-01 仍红，退回设计复现） |

## 现象

隔离复现（round9，vblog，21:5x）：`rename(Interactive.8 → e2e_renamed)` **ok=True**；紧接着 `rename(e2e_renamed → Interactive.8)` → `("error" 0 t nil ("*Error* error: Cannot find a setup database entry for handle 118109." nil))`。同一形态在门禁 `maestro_e2e_tests.py::HISTORY-01 rename/lock/unlock/delete` 稳定复现（今日 3 次，handle 号不同）。对照：单独 `delete e2e_renamed` **ok=True** 且列表确实少一条 → delete 正常，问题在 rename 链。

## 复现

```text
PYTHONPATH=src python test/live/packages/maestro_e2e_tests.py --transport http  # HISTORY-01
隔离：read_history → pick Interactive.* → write_history(rename H→e2e_renamed) ok → write_history(rename e2e_renamed→H) → ASSEMBLER-2404
```

## 证据

`test/artifacts/evidence/round9/final3-maestro_e2e_tests.py.log`（HISTORY-01 报错原文）；隔离探针 stdout（rename ok / restore fail, handle 118109）

## 验收判据（修好即转绿）

① rename 链（含目标名已存在、重命名回原名）必须成功或给出**点名冲突**的结构化拒绝（对照：重名 rename 已有清晰文案）；② 不得报 SDB handle 错误；③ `maestro_e2e_tests.py` HISTORY-01 转绿。

## 下一步 / 责任人

**设计侧已修 `2610668` + `50e6576`（2026-09-30 12:47）**：`_open_session` 校验 `maeOpenSetup` 返回会话可活跃、失效则关闭重开，rename 链按本次创建路径收尾。真机证据 `test/artifacts/evidence/verify-fix-r10/c09-maestro-history-green.json`（HISTORY-01 隔离路径 HTTP 全链通过）。**测试侧复跑（2026-09-30 22:1x，HEAD=9d24708）**：完整套件仍红 —— `maestro_e2e_tests.py --transport http` 在 `_case_write_history` 报 `Cannot find a setup database entry for handle 52134`（前序用例全部 PASS 后失败），证据 `test/artifacts/evidence/round9/maestro-c09-verify2.txt`。分歧点=**套件内前序用例留下的会话/handle 状态**（隔离 probe 绿、整链红）→ 请设计按完整套件复现定位；修好后 HISTORY-01 转绿即销卡。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
