# P-119 · 每次经桥的请求都会在 CDS.log 多写一条空 `\o ` 行（桥"交互等价换行"的副作用），不计入返回的 `CDSlog` delta

| 字段 | 值 |
|---|---|
| 级别 | P3（观察/口径：用户日志里出现桥产生的空行；半真机 probe 的"文件窗口==delta"契约因此失效） |
| 层 | 中层/底层 · 日志通道（CDS.log 字节窗口） |
| 归属 | spec 侧（**口径已定**：不改实现，改 spec —— 把「桥自身 flush 行不计入 delta、可被过滤」写进日志 spec §8） |
| 状态 | **待设计修** |
| 位置 | daemon 的交互等价换行（C06 修复 `c8bbe8c`）+ `test/semi/transport/log_matrix_real_tb.py::case_increment_bytes`（原判据：窗口必须与 delta 逐字节相同） |
| 首报 | 2026-09-30（round10 半真机全量：`log_matrix_real_tb` 初跑红，逐字节定位到桥自身 flush 空行） |
| 最近更新 | 2026-10-08 12:10（用户裁定：改 spec 口径（文档化该行、不改实现）；见卡尾决策） |

## 现象

真机（vblog，经 8127 与 direct 两种形态一致，2026-09-30）：
请求 `progn(hiPrintToLogFile("VB-LOG-<tag>") hiFlush() hiFlushLogFile() 1+1)` + `log_level=all` → 返回 `CDSlog` = `\o VB-LOG-<tag>\n`（19B），而 CDS.log 生长 **23B** —— 窗口 = 返回行 + `\o \n`（**空行**）；每请求一次稳定出现（连续 4+ 次复现，`contiguous_slice=true`、`bridge_flush_line=true`）。

## 复现

```text
`PYTHONPATH=src python test/semi/transport/log_matrix_real_tb.py --work-dir test/artifacts/env/log-vblog --token vb-vblog`
（或对照：`stat -c %s CDS.log` → 发一条带标记的 `hiPrintToLogFile` 请求 → 再 `stat` + `dd ... | cat -A` 看窗口）
```

## 证据

`test/artifacts/evidence/round10/log-matrix-real-r10.json`（`increment-bytes.bridge_flush_line=true`，窗口/返回字节数入证据）；实测窗口原文（`cat -A`）：`\o VB-LOG-<tag>$` + `\o $`

## 验收判据（修好即转绿）

① **spec 回填**日志 spec §8：`log`/`CDSlog` 只含本次请求增量；桥自身为提交行缓冲而发送的换行产生的空 `\o ` 行**不计入 delta**、可被消费者过滤，且不参与日志分级/长度预算统计（建议原文见卡尾「决策」）；② probe 判据与 spec 一致（只允许 `window == delta + "\\o \n"` 这一种额外形态，其它多余字节仍判红）；③ 除文档外**不做**实现改动（不消除该行，避免动 C06 flush 修复路径）。

## 下一步 / 责任人

**决策已定（2026-10-08，用户裁定）：改 spec 口径** → spec owner 按卡尾建议原文回填 §8 后，测试侧复核 probe 判据与 spec 一致并销卡。探针当前已按该口径精确钉住（不阻塞半真机层）。

## 决策（2026-10-08，用户裁定）

**改 spec 口径，不改实现**：接受「这条空行是桥自身 flush 的副产物」，写进日志 spec；不消除它（避免动 C06 的 flush 修复路径）。

1. 在 `spec/底层/6-日志返回设计标准.md` §8 增补一条（建议原文，spec owner 可直接采用）：

   > `log`（JSON 出口名 `CDSlog`）只包含本次请求期间的 CDS.log 增量；其中**由桥自身为提交行缓冲而发送的换行**
   > 所产生的空输出行（`\o `）**不计入 delta**，消费者可按需过滤；该行不得参与日志分级与长度预算统计。

2. 测试侧判据（保持现状，已实现）：半真机 probe **精确**允许 `窗口 == delta + "\o \n"` 这一种额外形态；
   任何**其它**多出来的字节仍判红（保证真泄漏不会被放过）。
3. 不再做实现改动：不消除该空行（C06 修复 `c8bbe8c` 的换行是行缓冲提交所必需）。
4. 收口流程：spec 回填后由测试侧复核 probe 判据与 spec 一致 → 销卡；若日后要彻底消除该行，另立新卡评估 C06 回归风险。
---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
