# C09 · `maestro.write_history` rename 链撞只读/陈旧的 Maestro session → `Cannot find a setup database entry for handle`（已修：复用 editable session + 只读冲突结构化拒绝）

| 字段 | 值 |
|---|---|
| 级别 | P3（重命名链不可用：`maestro_e2e_tests.HISTORY-01` 因此稳定红） |
| 层 | 上层（maestro 包）· write_history rename 链 |
| 归属 | 设计侧（已修：maestro 包 session 选择 + 只读冲突处理） |
| 状态 | **待测试侧** |
| 位置 | `src/pyapi/packages/maestro.py`（`write_history` 的 rename 分支与 SDB handle 复用；`_open_session` 会话内 handle 在重命名后失效） |
| 首报 | 2026-09-29（round9 门禁复跑 + root 隔离复现） |
| 最近更新 | 2026-09-30 19:21（设计侧定位只读 session 根因并修复，vbs11 真机链验证通过，转测试侧） |

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

**设计侧二修（2026-09-30 19:2x，本轮）**：根因是 `maeOpenSetup` 在 view 已被其他 session 以 edit 模式打开时会返回 **read-only** session（或直接弹 `ASSEMBLER-8127` 模态）；旧代码把无窗口的后台 session 一律当可写，于是 rename 在只读 session 上以 stale SDB handle 报错。修法：① `_open_session` 先用 `axlGetSessionLibName/CellName/ViewName` + `axlIsSessionReadOnly` 扫描，优先复用同 cellview 的 **editable** session；② 只有只读匹配 session 时**不再调 maeOpenSetup**（避免弹模态/拿到只读会话），写路径直接给出点名的结构化拒绝，读路径复用只读会话；③ `_ensure_session_editable` 对后台 session 也查 `axlIsSessionReadOnly`，不再盲信可写。真机证据（新代码、vbs11 + 临时业务面 8138，fresh CIW）：happy path `Interactive.1→c09_tmp→Interactive.1` 全绿；预置 editable session 后 `Interactive.0→c09_tmp2→Interactive.0` 仍全绿、复用同一 session（未多开）、链后 `1+2=3` 存活；证据 `test/artifacts/evidence/verify-fix-r10/c09-vbs11-fix-green.json`。离线回归：`test/maestro_package_flow.py` 新增 3 条（复用 editable / 只读后台拒写 / 只读冲突不调 maeOpenSetup），`test_maestro_command_exprs.py` fake 适配；maestro 离线 **104 全绿**。待测试侧在 vblog fresh CIW 复跑 `maestro_e2e_tests.py`，HISTORY-01 转绿后销卡。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
