# P-129 · `veriloga.write` 缺 view 存在性门（`verilog.write` 有）：缺失/脏残留 view 下 `set_source` 的返回语义与磁盘结果未对齐——脏残留目录时可能静默写出无 `master.tag` 的孤儿文件

| 字段 | 值 |
|---|---|
| 级别 | P2（同族包行为漂移；「静默 ok」成立范围待半真机复现定性） |
| 层 | 上层（veriloga 包）· `write`/`set_source` 前置门 · 与 verilog 同族漂移 |
| 归属 | 设计侧（对齐 `verilog._view_exists` 前置门与错误提示；建议抽共享 text-view 前置） |
| 状态 | **待测试侧** |
| 位置 | `src/pyapi/packages/veriloga.py:358-397`（`write` 无 `_view_exists`，直接 `_set_source`）；对照 `src/pyapi/packages/verilog.py:374-394`（`view_ready` 前置报错）与 `:441`（`_view_exists` 定义） |
| 首报 | 2026-10-08（外部静态审查 A1） |
| 最近更新 | 2026-10-08（测试侧建卡） |

## 现象

对不存在/脏残留的 Verilog-A view 调 `set_source`：verilog 明确提示先 `ensure_view`；veriloga 无此门——新鲜缺失多数以 scp/mv 错误收场（文案不友好），而「目录存在但无 master.tag」的脏残留会写出孤儿 `veriloga.va` 且可能 ok=true。

## 复现

```text
半真机（vblog）：① 对完全不存在 view 的 cell 执行 `set_source`；② 手工制造残留（建 view 目录、不放 master.tag）再执行 → 对比返回语义与磁盘文件。
```

## 证据

静态核实（2026-10-08，测试/root）：veriloga 全文无 `_view_exists`；verilog 有门+友好文案；上传链路为 `scp 旁路 stage + mv 安装`（`tunnel.py:40-58`、`:509-540`），目录缺失时 mv 失败、目录存在时静默落盘。

## 验收判据（修好即转绿）

① veriloga 与 verilog 同门同文案；② 两种前置场景（缺失目录/脏残留）均不得静默成功，返回与磁盘一致；③ TB 覆盖两条路径后转设计修。

## 下一步 / 责任人

测试侧先跑半真机复现定性（两条路径），据实回填本卡后转设计侧对齐门。


---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
