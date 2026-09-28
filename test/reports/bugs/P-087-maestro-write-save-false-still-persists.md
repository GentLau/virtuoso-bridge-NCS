# P-087 · `save=False` 的改动不被隔离：后续任意一次 save 会把它静默带走（跨请求污染）；同场景 `delete_var` 清理报 handle 错误

| 字段 | 值 |
|---|---|
| 级别 | P2（静默跨请求污染用户 setup + 清理失败） |
| 层 | 上层（maestro 包）· 会话复用 |
| 归属 | 设计侧（maestro 包）；`save` 的对外语义需 spec owner 定稿 |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/maestro.py:1760-1765`（save=False 只跳过显式 `maeSaveSetup`，不丢弃/隔离会话内改动）；`:1303-1317` `_close_if_created`/`_close_session`；`delete_var` 清理路径（本场景报 handle 错误）。spec `6-maestro.md` 未定义 `save` 语义（仅 :173 提到 open/save/close） |
| 首报 | 2026-09-28（第八轮：live WRITE-06 首红 → 磁盘级探针确认隔离缺失） |
| 最近更新 | 2026-09-28 |

## 现象

磁盘级因果链（真机 maestro_tb/rc_probe，2026-09-28 实测）：
1. `write(set_var v=1.0)`（save=True）→ 步骤含 save_setup，sdb 中 v=1.0 ✓
2. `write(save=False, set_var v=2.0)` → 步骤**不含** save_setup，**立即**查 sdb 仍 v=1.0 ✓（未立即落盘）
3. 随后一次**无关**的 `write(set_var other=ok)`（save=True）→ sdb 中 v 被写成 **2.0** ✗ —— 未保存改动留在复用会话里，被下一次保存静默带走（跨请求污染）。
4. 同场景 `delete_var` 清理两个变量均失败：`*Error* error: Cannot find a setup database entry for handle 0`。

## 复现

```text
PYTHONPATH=src python test/semi/probes/maestro_save_false_disk_probe.py   # 期望 RED（第 5 项 FAIL=2.0）
# 证据：test/artifacts/evidence/round8/maestro-save-false-disk.json
```

## 证据

`test/artifacts/evidence/round8/maestro-save-false-disk.json`（5 项 checks：步骤表/立即磁盘/泄漏判据/清理）；live 侧 `maestro_e2e_tests.py` WRITE-06 现按步骤表判定（可过），**不足以防住本条泄漏**，以磁盘探针为准

## 验收判据（修好即转绿）

① spec 明确 `save` 语义（推荐：save=False 的改动必须被隔离 —— 关闭/丢弃或快照-回滚，后续 save 不得带走）；② 实测第 3 步泄漏消失（旧变量仍 1.0），删参数则改为负向「传 save 被拒」；③ `delete_var` 在复用会话/失败恢复路径可正常清理（或明确报可读错误）；④ 探针转 GREEN。

## 下一步 / 责任人

设计侧定 `save` 隔离口径 + 修 delete_var handle 路径；测试侧把磁堢探针纳入半真机层并复跑 live WRITE-06。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
