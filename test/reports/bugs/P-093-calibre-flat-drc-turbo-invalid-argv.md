# P-093 · `calibre.drc(hier=False)` 命令行非法：`-turbo` 与 flat 模式冲突 → Calibre 打 usage、作业秒退

| 字段 | 值 |
|---|---|
| 级别 | P2（该参数组合下 DRC 完全跑不了，且呈现为工具 usage dump 而非可读错误） |
| 层 | 上层（calibre 包） |
| 归属 | 设计侧（calibre 包 `_argv_for`） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/calibre.py:987-997`（`_argv_for`：`-hier` 按 `request.hier` 决定，但 `flags += ["-turbo", str(request.turbo)]` 无条件追加） |
| 首报 | 2026-09-28（第八轮 calibre 参数面实测，root 直接发现） |
| 最近更新 | 2026-09-28（新立） |

## 现象

真机（vblog）实测 `calibre.drc(gds=inv.gds, top=inv, deck=PDK/drc/calibre.drc, hier=False, turbo=2)`：
`drc.log` 第 2 行 = `ERROR: The -turbo option is not valid with this flat application.`，随后整段 Calibre usage；
calibre 进程 1s 内退出（`process_alive=false`），run_dir 里只有 usage dump，没有 DRC.rep。
原因：flat（非 `-hier`）DRC 不接受 `-turbo`；桥只按 hier 切换 `-hier`，却始终追加 `-turbo`。

## 复现

```text
`PYTHONPATH=src python test/semi/probes/calibre_flat_turbo_probe.py`（预期红）
run_dir 现场：`/home/Gent/project/vblog/calibre-e2e/p093-flat-<ms>/drc.log`
```

## 证据

`test/artifacts/evidence/round8/p093-flat-turbo-probe.json`（含 drc.log 的 `ERROR:` 原文与 status 快照）

## 验收判据（修好即转绿）

① `hier=False` 时不追加 `-turbo`（或仅 hier/pex 路径追加）；或 ② 提交前对 `hier=False + turbo` 给结构化拒绝；两条任一 + 探针在 flat 模式下能真跑出 DRC.rep（或在非 hier 时明确拒绝）。

## 下一步 / 责任人

设计侧改 `_argv_for` 的 turbo 条件；测试侧复跑探针与 `calibre_params_e2e_tests.py` 的 flat 分支。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
