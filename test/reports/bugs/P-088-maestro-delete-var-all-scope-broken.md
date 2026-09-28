# P-088 · `maestro.write(delete_var, scope=..all..)` 确定性失败：Cannot find a setup database entry for handle 0

| 字段 | 值 |
|---|---|
| 级别 | P2（用户清理/teardown 常用路径不可用；现有套件用 try/except 掩盖） |
| 层 | 上层（maestro 包） |
| 归属 | 设计侧（maestro 包 delete_var 的 all 分支 SKILL） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/maestro.py:930-941`（all 分支 `foreach(tn cadr(axlGetTests(sdb)) … axlGetTest(sdb tn) …)` / `foreach(cn cadr(axlGetCorners(sdb)) … axlGetCorner(sdb cn) …)` → `axlGetVar(0 …)` 报 handle 0） |
| 首报 | 2026-09-28（第八轮 op×param 补测；红灯探针已留证） |
| 最近更新 | 2026-09-28（新立） |

## 现象

scope 矩阵实测：`global` set/delete 均 ✓；`test`（test=ac）✓；**`all` set ✓ / delete ✗** `*Error* error: Cannot find a setup database entry for handle 0`。副产物：`maestro_e2e_tests.py` 的 scope=all 清理在 try/except 里，失败被吞 → rc_probe 的 sdb 里残留 `e2e_save_*` 变量（本轮实测 3 个）。

## 复现

```text
`PYTHONPATH=src python test/semi/probes/maestro_delete_var_all_probe.py`（预期红）
```

## 证据

`test/artifacts/evidence/round8/p086-delete-var-all.json`；`test/artifacts/tmp/probe_delete_var_scopes.py`

## 验收判据（修好即转绿）

delete_var scope=all 成功删除 global/test/corner 三处同名变量（探针转绿）；现有套件的 try/except 清理改为显式断言

## 下一步 / 责任人

设计侧修 all 分支的迭代写法；测试侧复跑探针 + 清理 rc_probe 残留变量


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
