# P-095 · `maestro.run` 的 Overwrite History 目标悬空：`ASSEMBLER-3018` 模态框阻塞 CIW → daemon 空响应（watchdog 不处理）

| 字段 | 值 |
|---|---|
| 级别 | P1（可把实例 CIW 挂死；P-086 持久形态的直接根因） |
| 层 | 上层（maestro 包）· GUI 模态 |
| 归属 | 设计侧（maestro 包 run 流程 + 对话框 watchdog） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/maestro.py:2960-2973`（`request.history` 时 `axlSetOverwriteHistory(setup t)` + `axlSetOverwriteHistoryName(...)`，**运行后/无 history 时不清理或复位**）；`_start_simulation_with_watchdog`（未识别/未关闭 `ASSEMBLER-3018` 的 `adexlMessageDialog`） |
| 首报 | 2026-09-28（第八轮：P-084/P-089 fixture 恢复时定位到根因） |
| 最近更新 | 2026-09-28 |

## 现象

真机（vblog/maestro_tb rc_probe）实测链：先前 run 把 Overwrite History 设为 `Interactive.8`；该 history 之后不存在（cell 只剩 MonteCarlo.*）；再跑一次**不带 history** 的 `virtuoso.maestro.run` → ADE 弹模态 `ERROR (ASSEMBLER-3018): The history item 'Interactive.8' selected to be overwritten does not exist` + `# Displaying modal dbox "adexlMessageDialog", title "ADE Assembler Message 3018"` → CIW 阻塞，daemon 进入 **Empty response 窗口且 2 分钟不自愈**（8×15s 轮询全空响应；query 正常）。run 返回 `maeRunSimulation returned nil; diagnosis: {'current_form': None, 'sessions': []}`。

## 复现

```text
1) 复现窗口：`python test/artifacts/tmp/_r8_vblog_wait.py`（8×15s 全 Empty response）
2) 现场：` ssh wsl-gent 'tail -n 8 ~/.virtuoso-bridge/vblog/run/CDS.log'` → ASSEMBLER-3018 模态行
3) 恢复：`test/artifacts/tmp/hard_restart_user_instance.sh`（Gent 身份，端口 65121）
```

## 证据

CDS.log 22:48:02 现场（ASSEMBLER-3018 + adexlMessageDialog 两行）；`round8/coverage-main-r8.log` 中同族 Empty response 历史；P-086 卡片（本条是其持久形态的根因）

## 验收判据（修好即转绿）

① run 结束（成功/失败/超时）后 Overwrite History 状态被复位（或每次 run 前校验目标存在、不存在即清 flag）；② watchdog 能识别并关闭 `adexlMessageDialog`/ASSEMBLER-3018（或在弹框前避免）；③ 复现件：不带 history 的 run 在悬空 overwrite 目标下**不得**挂死 CIW，且返回结构化失败；④ 无窗口期残留（P-086 复跑转绿）。

## 下一步 / 责任人

设计侧修 run 的 overwrite 生命周期 + watchdog 覆盖 ASSEMBLER 模态；测试侧补红灯探针（悬空目标 → 期望结构化失败而非挂死）。

## 补充（2026-09-28 22:55，跨重启持久化实证）

- 实例硬重启后，用 `open_gui` 拿到 session 后读 setup 标志：`(t "Interactive.8")` —— **悬空目标跨重启持久化在 .sdb 里**；
- 手动 `axlSetOverwriteHistory(setup nil)` 后复核 `(nil "Interactive.8")`，再跑裸 `run` → `status=done, history=Interactive.0`（新 history 正常创建，不再弹框）。
- 结论：run 流程必须在设置/使用后复位 Overwrite 标志，或运行前校验目标存在。

---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
