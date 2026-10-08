# P-130 · 【改进汇总】重复实现收敛 / 死代码清理 / 排障日志与小项清理（非缺陷，不阻塞功能）

| 字段 | 值 |
|---|---|
| 级别 | 改进（非缺陷；由外部静态审查提出，测试侧抽查复核） |
| 层 | 全仓（架构治理 · 非缺陷改进汇总） |
| 归属 | 设计侧（排期执行；重构以行为不变为约束） |
| 状态 | **观察** |
| 位置 | 重复实现：`_step`×9 包、`_require_*` 8–12 份、截图流水线×4、传输暂存/安装×4（`middle.py`/`tunnel.py`/`ssh.py`）、分块 sha256×3、kind 映射×3（`ssh.py:944`/`paramiko_backend.py:1733`/`middle.py:153`）、`register/candidate.py` vs `transport/roles.py`、`register/models.py` vs `common/registry.py`、py2/py3 daemon 双份（有意为之，长期同步风险）；死代码：`src/transport/budgets.py:71-90`（try_acquire_thread 等，全仓无调用）、`src/transport/tunnel.py:660`（`_verify` 无调用）、`src/pyapi/packages/basic.py:451`（`_collect_strings` 无调用）、`src/pyapi/packages/calibre.py:442-452`（pex 半残链，建议与 P-117 预留口径一起收）；排障：`src/transport/middle.py:605` 等 `except LookupError` 会把内部 KeyError 报成 invalid token；`src/server/dispatch.py:110-113`（TypeError/ValueError→400 是 spec §3.3 规定，建议补服务端 traceback 日志以区分代码 bug）；小项：`src/common/registry.py:287-291` 重复 `model_config`、`src/common/ssh.py:327-332` control_master force≡auto、`src/register/flow.py:1248` `_token_ok` 冗余、`flow.py:1475` 冗余 except、`src/pyapi/packages/skillref.py:427-428` no-op 分支、`src/common/paths.py:102` 注释与实现不一致 |
| 首报 | 2026-10-08（外部静态审查） |
| 最近更新 | 2026-10-08（测试侧建卡） |

## 现象

重复实现已产生真实漂移（verilog/veriloga=P-129、gui 截图第 4 份实现漏清理=P-125、candidate/roles 解析差异=P-120 相关）；死代码与宽异常捕获增加维护成本与排障误导。

## 复现

```text
—（治理项，无单一复现；重构项验收＝行为不变+回归全绿）
```

## 证据

外部静态审查（2026-10-08，AST 统计同名相似函数 207 对）+ 测试侧抽查复核（死代码 3 条确认无调用；小项 3 条确认属实；spec §3.3 4xx 归因核实）

## 验收判据（修好即转绿）

① 各项独立完成即可勾掉；② 重构类以「行为不变 + 现有 TB 回归全绿」为验收；③ 排障类以「内部异常不再伪装成协议/参数错误」为验收；④ 建议在 P-122~P-129 修复后再动重构，避免与修复打架。

## 下一步 / 责任人

排期执行；测试侧在每项重构后跑对应层回归并在本卡尾部记录进度。


---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
