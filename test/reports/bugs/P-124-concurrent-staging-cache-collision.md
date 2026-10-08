# P-124 · 并发共享本地暂存路径互相覆盖：verilog/veriloga 固定主文件名同目录缓存（可能把 A 的内容上传给 B）；skillref 每请求 rmtree 同一 doc_root 暂存目录（删掉他人正在读的文件）

| 字段 | 值 |
|---|---|
| 级别 | P2（并发静默错误：内容错位/读失败） |
| 层 | 上层包并发 · 本地暂存/缓存（verilog/veriloga/skillref） |
| 归属 | 设计侧（缓存/暂存路径按 token/cell/请求唯一化，或只读共享+进程内锁） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/verilog.py:159-163`（`_cache_dir`=`artifact_dir()/verilog`）+`:199-216`（本地名只用 `Path(remote).name`，主文件固定 `verilog.v`）；`src/pyapi/packages/veriloga.py:154-157,174-190`（同型 `veriloga.va`）；`src/pyapi/packages/skillref.py:446-450`（`_stage_reset` 每请求 rmtree）+`:710-712`（stage 仅按 doc_root 哈希） |
| 首报 | 2026-10-08（外部静态审查 A7） |
| 最近更新 | 2026-10-08（测试侧建卡） |

## 现象

同进程任意两个并发请求：a) verilog/veriloga 读写同一本地文件 → 后写覆盖先写，可能把 A cell 的内容上传到 B 的 view；b) skillref 同一 doc_root 并发搜索：一方 reset 删掉另一方正在读取的暂存文件 → 随机失败。

## 复现

```text
半真机/离线：并发两条 `verilog.write(set_source)`（不同 cell、同名 view）→ 校验交叉污染；skillref 两路并发搜索同 doc_root。TB 待补（并发组）。
```

## 证据

静态核实（2026-10-08）：路径构造共享 + 固定主文件名；skillref stage 命名与每请求清理。

## 验收判据（修好即转绿）

① 暂存/缓存路径唯一化（或锁/只读共享）；② 新增并发 TB 证明互不干扰；③ 串行行为不变。

## 下一步 / 责任人

等设计修；测试侧补并发 TB（两路并发×2 场景）。


---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
