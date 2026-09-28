# P-103 · `calibre.pex` 报 `status=completed` 但 stage3 失败：完成判定读到**前一阶段**的 COMPLETED 标记就提前收工（P-102 的真故障被掩盖成绿）

| 字段 | 值 |
|---|---|
| 级别 | P2（假绿：调用方按 ok/status 判定会以为 PEX 成功，实际没有网表产物） |
| 层 | 上层（calibre 包）· 完成判定 |
| 归属 | 设计侧（calibre 运行器的 job_state/等待循环按 log 尾部判完成的口径） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/_calibre_util.py:317-329`（`job_state` 只按 `log_tail` 里出现 `_DONE_MARKERS` 就判 completed）+ `src/pyapi/packages/calibre.py:574-594`（blocking 循环一见 completed 就 break）；pex 的三阶段日志同名 glob `*.log` 被 `tail -n 40` 合并 → **stage1 的 `CALIBRE xRC::PHDB GENERATOR COMPLETED` 落进 tail**。 |
| 首报 | 2026-09-29（第八轮 calibre PEX 参数面实测，root 直接发现） |
| 最近更新 | 2026-09-29（新立） |

## 现象

真机（vblog，2026-09-29 01:05，`pex(fmt="spice")`）run_dir `/home/Gent/project/vblog/calibre-e2e/pex-fmt-1790615068023/`：
- `pex.stage1.log` 尾部 `--- CALIBRE xRC::PHDB GENERATOR COMPLETED ---`（stage1 成功）；
- `pex.stage2.log` 正常结束；
- **`pex.stage3.log` 为空**、**`pex.log` 末行 `stage3_failed`**、run_dir 里 **没有任何 netlist 产物**；
- 但 `calibre.pex` 运行期返回 **`ok=true, status=completed`** ⇒ 假绿。
（同一 run_dir 用 `read_results(kind=pex)` 会因 `stage\d_failed` 判失败 —— 即**两个入口口径相反**。）

## 复现

```text
`PYTHONPATH=src python test/live/packages/calibre_export_pex_e2e_tests.py --transport http`（PEX-FMT-01 红钉：断言先查 `stage3_failed`/netlist，再查 status，因此今天判红）
```

## 证据

run_dir 三份 stage 日志 + `pex.log`（上列实测）；TB 红钉 `PEX-FMT-01`；对照 P-102（stage3 argv 非法的根因）与 `_calibre_util.py:322-324` 的 `classify_log`（只认 `ERROR:` 等标记）。

## 验收判据（修好即转绿）

① 完成判定必须**按阶段**取日志（stage3 的完成标记才算 pex completed），或要求产物（netlist/pdb）齐；② `stage\d_failed` 一旦出现立即判 failed（与 `read_results` 同口径）；③ PEX-FMT-01 转绿。

## 下一步 / 责任人

设计侧与 P-102 一起改（argv + 完成判定）；测试侧复跑 PEX-01/PEX-FMT-01 确认不再假绿。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
