# P-076 · 间歇：`spectre.run` 请求永不返回（spectre 已 0 error 跑完；服务端线程不释放，需重启业务面）

| 字段 | 值 |
|---|---|
| 级别 | P2（间歇性挂起；占住 in_flight 线程，客户端只能杀进程） |
| 层 | 上层（spectre 包；第二嫌疑：中层持久 shell） |
| 归属 | 设计侧（上层 spectre 包的 run 路径：等待完成/递归下载） |
| 状态 | **观察（1 次复现，待设计侧定位）** |
| 位置 | `src/pyapi/packages/spectre.py` `run` → `_run_one`（execute → `download_file(recursive=True)` → 解析）；中间层 `run_spectre_command` / 持久 shell 路径 |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

## 现象

2026-09-28 12:59 `design_iterate_tb` 的 `r2_sim` 阶段（calprobe token，2 任务 / `max_workers=2`）卡住 **>25 分钟**：spectre 本身在 12:59:02 就跑完了（两个 run 目录的 `spectre.out` 都是 `spectre completes with 0 errors`，`r2_ac.raw/ac.ac`、`r2_tran.raw/tran1.tran.tran` 都在），但 HTTP 请求不返回、`/health` 显示 **in_flight=1** 一直不降；客户端把 TB 进程杀掉后，服务端线程仍不释放（只能重启 8127 才能清掉）。两侧都没有 ssh/scp/tar 进程 → 阻塞在中间层 Python 路径。
**注意（避免误判）**：同一业务面其它 token 的请求不受影响（卡住期间 vblog/calprobe 的 `1+2` 与新的 `spectre.run` 都正常）。

## 复现

```text
发生样本（保留现场）：`test/artifacts/evidence/round7/design-iterate/`（r1 各段 12:58 完成，r2_edit/r2_sym/r2_layout 12:58:44–53 完成，r2_sim 无产物）；远端 run 目录 `/home/Gent/.virtuoso-bridge/calprobe/spectre/spectre/buf_stage_125804_r2_{ac,tran}`（均已 0 error）。
**未能最小复现**（已试，均正常返回）：① vblog 连续两次单任务 `spectre.run`（6.5s/6.0s）；② vblog 连续两次双击（各 2 任务，6.4s/6.7s）；③ 事后 calprobe 单任务 `spectre.run`（6.1s）。复现脚本：`test/artifacts/tmp/repro_spectre_second_run.py`、`test/artifacts/tmp/repro_spectre_two_tasks_twice.py`。
```

## 证据

卡住时 `/health → in_flight=1`；`spectre.out` 完成时间 12:59:02；客户端 TB 进程被杀后 in_flight 仍为 1；双侧 `ps` 无 ssh/scp/tar。

## 验收判据（修好即转绿）

① 给出该路径的硬超时（等待完成 / 递归下载都必须有 deadline，超时返回结构化错误而不是永久阻塞）；② 复现样本能定位到具体阻塞点（建议设计侧在 `_run_one` 的 execute/download/parse 三段加耗时日志，或用 py-spy 抓卡住线程栈）；③ 修好后连跑 3 次 `design_iterate_tb --stage all` 不再挂。

## 下一步 / 责任人

设计侧定位（样本在 12:59 那次；如需现场可让测试侧重跑并按 py-spy 抓栈）；测试侧暂按'间歇挂起'记录，先跑其余 TB。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
