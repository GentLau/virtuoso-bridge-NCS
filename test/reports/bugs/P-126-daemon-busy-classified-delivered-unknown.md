# P-126 · daemon `busy`（确定未执行）被归类为 `delivered_unknown`：token 被误标 dirty，后续请求被迫先走 probe 轮询

| 字段 | 值 |
|---|---|
| 级别 | P3（语义错位+多余等待；busy 本属可安全重试的 not_delivered） |
| 层 | 中层 `skill_client` ↔ 底层 daemon 协议语义（busy/dirty） |
| 归属 | 设计侧（`busy`→`not_delivered`；如需可在 spec 侧明确 busy/dirty 语义） |
| 状态 | **待设计修** |
| 位置 | `src/common/skill_client.py:119-121`（busy/timeout 同归 delivered_unknown）；`src/bridge/resources/ramic_bridge_daemon_3.py:438-448`（busy=读请求后直接 NAK，未碰 Virtuoso）；消费方 `src/transport/middle.py:777-793`（dirty 门 probe 等待）与 `:807-813`（置 dirty） |
| 首报 | 2026-10-08（外部静态审查 A4） |
| 最近更新 | 2026-10-08（测试侧建卡） |

## 现象

一次 busy 会把 token 打进 `_skill_dirty`，下一请求先循环 probe 到 idle 才发送；而 busy 语义是「daemon 仍脏、本请求未执行」，可安全重试，语义上不该报「结果未知」。

## 复现

```text
半真机（vblog）：先构造 daemon dirty（发长 SKILL 触发超时）→ 再发一条 → 收 busy → 观察客户端置 dirty 及下一请求的 probe 等待；TB 待补（transport 协议组）。
```

## 证据

静态核实（2026-10-08）：daemon busy 分支未执行即拒绝；客户端映射 delivered_unknown；middle 据此置 dirty 并让后续请求探测等待。

## 验收判据（修好即转绿）

① busy 单列 not_delivered（不置 dirty、不误报结果未知）；② timeout 等真 unknown 路径行为不变；③ 协议 TB 断言：busy 后下一请求直接发送/快速返回。

## 下一步 / 责任人

等设计修；测试侧补 busy 协议 TB（可复用现有 dirty/probe TB 骨架）。


---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
