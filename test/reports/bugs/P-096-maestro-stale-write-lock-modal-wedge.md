# P-096 · 陈旧 OA 写锁（属主进程已死）触发 `axlOpenInRead0` 模态框 → CIW/daemon 再次挂死；应结构化失败或自动强制

| 字段 | 值 |
|---|---|
| 级别 | P2（崩溃后该 cell 的 maestro 打不开且会挂死实例，需人工删锁） |
| 层 | 上层（maestro 包）· 崩溃恢复 / OA 写锁 |
| 归属 | 设计侧（maestro 打开/写路径的锁判定；可参考 schematic 的“locked by another session”结构化失败） |
| 状态 | **待设计修** |
| 位置 | 现场：`/home/Gent/project/vblog/maestro_tb/rc_probe/maestro/maestro.sdb.cdslck`（属主为被 kill 的旧实例）；`src/pyapi/packages/maestro.py` 的 open/ensure-editable 路径（未先把死属主锁转成结构化失败）；CDS.log 弹框：`# Displaying modal dbox "axlOpenInRead0", title "ADE Assembler Open View"` |
| 首报 | 2026-09-28（第八轮：vblog 崩溃恢复时实测） |
| 最近更新 | 2026-09-28 |

## 现象

实例被 kill 后留下 `maestro.sdb.cdslck`（写锁，属主进程已不存在）。新实例上 `maestro.open_gui` → `deOpenCellView failed ...: Empty response from daemon`，随后**所有 skill 请求空响应**（实例再次挂死）；CDS.log 显示 `Couldn't get a write lock ... currently "write" locked by user Gent on machine GLIS-DESKTOP (since …)` + 模态框。手动删除陈旧 `cdslck` 并重启实例后 open_gui 立即恢复成功（session fnxSession0, editing）。

## 复现

```text
1) 手工复现：杀掉带未释放锁的 maestro 实例 → 新实例 `python test/artifacts/tmp/_r8_opengui2.py` → 观察 Empty response + CDS.log 模态行
2) 恢复：清 `<cellview>/*.cdslck` + 重启实例（见 `round8/../internal/环境Runbook-内部.md` §10.2/§10.3）
```

## 证据

CDS.log `Couldn't get a write lock … since Mon Sep 28 22:43:53` + `axlOpenInRead0` 两行；`_r8_opengui2.py` 输出；恢复后 open_gui ok 对照

## 验收判据（修好即转绿）

① 打开/编辑前检测写锁属主：属主进程已死（或期望指纹不符）→ 返回结构化失败（或按产品口径自动强制/只读打开），**不得**弹模态；② 回归：`kill -9` 实例 → 新实例 open_gui 要么成功（死锁被正确处理）要么明确失败，CIW/daemon 不挂死；③ 与 P-095 的 watchdog 修复联动（ASSEMBLER/ADE 模态兜底）。

## 下一步 / 责任人

设计侧定“死属主锁”处置口径并实现；测试侧在 `maestro_pkg_probe`/新探针里补“陈旧锁恢复”回归（先手工造锁再验证行为）。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
