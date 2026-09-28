# P-098 · `blocking=true` 超时返回最后一次 `status`（running/unknown），未按 spec 返回 `status=timeout`

| 字段 | 值 |
|---|---|
| 级别 | P3（口径偏差：调用方按 spec 判 `status=="timeout"` 会永远不成立；作业本身不杀、行为其余正确） |
| 层 | 上层（calibre 包）· 阻塞轮询口径 |
| 归属 | 设计侧（calibre 包轮询收尾） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/calibre.py:575-594`（deadline 到点后 `value.update({"status": last.get("status", "timeout")})`——`last` 在跑过至少一次 poll 后必非空，于是永远是最后一次观测值 `running`/`unknown`）；spec：`上层/12-calibre.md:117-121`（§3.4「终态或超时即返回；**超时返回 `status=timeout`** 且后台作业继续跑」） |
| 首报 | 2026-09-28（第八轮 calibre#069 缺口核账时按 spec 对表发现并复现） |
| 最近更新 | 2026-09-28 |

## 现象

离线可复现（假 middle 让作业永远 running）：`drc(blocking=True, timeout=0.2, poll_interval=0.01)` → 返回 `value.status='running'`、`elapsed_ms≈202`、`error='drc did not complete: running'`；spec 要求的 `status='timeout'` 只会在**从未 poll 过**时意外落到默认值。后台作业继续跑（无 kill 命令）这一半符合 spec。

## 复现

```text
python -m pytest test/offline/unit/test_calibre_package.py -q -k timeout_reports --runxfail   # 当前红（'timeout' != 'running'）
```

## 证据

红灯钉 `test/offline/unit/test_calibre_package.py::PackageTests::test_drc_blocking_timeout_reports_timeout_status`（strict-xfail；value 全量打印见 --runxfail 输出）

## 验收判据（修好即转绿）

① deadline 到点且最后状态非终态时，对外 `status` 必须是 `"timeout"`（可加 `last_status` 字段保留观测值）；② 不得杀后台作业；③ 红钉转绿（XPASS 后删 strict 标记）。

## 下一步 / 责任人

设计侧改收尾口径 → 测试侧复跑该钉与 calibre 套件。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
