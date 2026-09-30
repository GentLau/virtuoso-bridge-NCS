# round9 · 离线套件稳定性核对：发现 1 个 flaky 用例（1/3 观测）

> 执行：subagent `/root/opparam_r9`｜2026-09-29 21:36｜只读 + 离线复跑（未碰真机）

## 1. 现象

| 轮次 | 命令/证据 | 结果 |
|---|---|---|
| 20:43 | `test/artifacts/evidence/round9/offline-windows-r9.txt`（单会话全量） | ❌ 1 红：`test/offline/unit/test_register_flow.py::TestStepRetryAfterFailure::test_validate_can_retry_same_step`（第 225 行 `assertEqual(retried.stage, "validated")`，进度 46% 处 `F`） |
| 21:14 | `test/artifacts/evidence/round9/offline-windows-r9.xml`（单会话全量） | ✅ **0 红**（该 class 5 条全 PASS） |
| 21:35 | `test/artifacts/evidence/round9/offline-single-session-r9b.txt`（我复跑，`pytest test/offline -q`，rc=0） | ✅ **0 红**（1950 点 / 8 skip / 2 xfail） |
| 22:41 | `test/artifacts/evidence/round9/offline-single-session-r9c.txt`（再复跑，rc=0） | ✅ **0 红** |
| （对照）单文件 | `pytest test/offline/unit/test_register_flow.py -q` | ✅ 68/68 |

## 2. 判定：**测试侧 flaky（顺序/状态依赖），不是产品 bug**

依据：

1. 同一份产品代码（`src/register/flow.py` mtime 19:49，早于 20:43 与 21:14 两次运行）在两次运行中一次红一次绿；
2. 20:53 对 `test_register_flow.py` 的改动只是给 3 处断言**补 `retried.errors` 上下文**（`git diff` 仅 3 行），不改变判据逻辑 → 不是"改测试把红改绿"；
3. 该用例用共享的 `work_root()/registry_path()`（`setUp` 里 `load_registry(registry_path())`），
   而 20:43/21:14 都是**单会话跑全集**（跨文件共享同一 work-root）——**怀疑跨文件状态泄漏**（正是 C0 卡"AAA 与状态还原缺失"那一类）；
4. 项目 runner `run_offline_multi.py` 是**每文件独立进程**（文件间天然隔离），所以它跑不出来；只有单会话全集才会暴露。

**观测统计（截至 22:41）**：单会话全集 **4 次 = 1 红 / 3 绿（25%）**；红的只有 20:43 那一次，
21:14（root）/21:35/22:41（我）三次全绿——典型的**低频 flaky**，不是稳定失败。

## 3. 建议（不需要在本轮改产品）

1. **收口前再跑一次单会话全集**（`python -m pytest test/offline -q`）：若再红，立刻看 `retried.errors`（20:53 加的诊断现在会打印出来）；
2. **加固该用例**（测试侧）：`TestStepRetryAfterFailure` 的 `setUp` 换用**每用例独立 work-root**（例如 `tempfile.TemporaryDirectory()` + 从模板复制注册表），消除跨文件耦合；
3. 在报告里如实体现在线口径：**"离线：0 红（三次单会话中观测到 1 次 flaky，非产品）"**——不要写"10/10 稳定"这类无依据断言。

## 4. 与本轮其它证据的关系

* spec 矩阵审计用的是 21:14 的 XML（0 红），结论不受影响；
* 该 flaky 不在 `src/`，因此**不产生新卡**；若设计侧愿意，可作为"测试稳定性"条目挂到 C0 家族（状态还原）里跟踪。
