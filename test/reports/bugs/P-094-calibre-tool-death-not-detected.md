# P-094 · 工具秒退不被检测：`status` 只报 `unknown`、`blocking=True` 会等满 timeout（日志里的 `ERROR:` 看不见）

| 字段 | 值 |
|---|---|
| 级别 | P2（1 秒失败的作业占满 30 分钟预算，且用户拿不到失败原因） |
| 层 | 上层（calibre 包）· 失败检测 |
| 归属 | 设计侧（calibre 运行器轮询/状态判定） |
| 状态 | **待设计修** |
| 位置 | 等待循环 `src/pyapi/packages/calibre.py:574-594`（只在 `completed`/`failed` 时 break）；`src/pyapi/packages/_calibre_util.py:317-329`（`process_alive=false` + 有 artifacts + 尾部无 marker → `unknown`）；`src/pyapi/packages/calibre.py:929-936`（`_log_tail` 只 `tail -n` 尾部，而 `ERROR:` 在日志第 2 行，`classify_log` 的 `_FAIL_MARKERS`（含 `ERROR:`）永远看不到）。 |
| 首报 | 2026-09-28（第八轮 calibre 参数面实测，root 直接发现） |
| 最近更新 | 2026-09-28（新立） |

## 现象

实测（同一个 flat DRC 作业）：日志已含 `ERROR: The -turbo option is not valid …`，但
`calibre.status` 返回 `{"status": "unknown", "failure_kind": null, "process_alive": false}`；
`calibre.drc(blocking=True, timeout=1800)` 因此蹲满预算（本轮实测 >5 分钟仍停在 poll，被我手工 kill）。
对照 AGENTS.md 的 dual-defense 要求：轮询必须每轮 tail/grep 工具日志里的终态标记——calibre 运行器没做。

## 复现

```text
`PYTHONPATH=src python test/semi/probes/calibre_flat_turbo_probe.py`（探针判据：15s 内 status 必须报失败并带 ERROR 行；今天红）
```

## 证据

`test/artifacts/evidence/round8/p093-flat-turbo-probe.json`（`tool_failed=true` 而 `error_surfaced=false`）

## 验收判据（修好即转绿）

① 轮询每轮对整份日志（或 `grep -m1 -E 'ERROR:|FATAL ERROR'`）做终态判定；② `process_alive=false` 且无完成标记 → 归类 `failed`（failure_kind 如 `process_gone_without_report`）并把 ERROR 行放进 value；③ 探针转绿（不再出现秒退作业等满 timeout）。

## 下一步 / 责任人

设计侧改轮询与 `job_state` 的兜底分类；测试侧复跑探针 + `calibre_e2e_tests.py` 的坏 deck 用例确认无回归。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
