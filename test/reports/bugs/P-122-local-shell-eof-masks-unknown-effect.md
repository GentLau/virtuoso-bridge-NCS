# P-122 · 本地 shell 中途退出（EOF）被当作命令正常完成：`kind` 缺省为 `command`、`returncode` 用 `proc_rc`（可能为 0），违反「结果未知」合同（远端同类路径已走 UnknownEffectError）

| 字段 | 值 |
|---|---|
| 级别 | P2（静默错误语义：把结果未知读成真实退出码/成功） |
| 层 | 中层 · 本地命令会话（`_LocalCommandSession`） |
| 归属 | 设计侧（eof 且未收到 rc/marker 时返回 `kind="unknown-effect"`，至少 `transport`，与远端对齐） |
| 状态 | **待设计修** |
| 位置 | `src/transport/middle.py:473-483`（eof 分支不设 kind）；合同与默认值 `src/pyapi/models.py:133-141`（kind 默认 `command`；§4.4 保留码语义）；远端对照 `UnknownEffectError` 路径 |
| 首报 | 2026-10-08（外部静态审查 A3） |
| 最近更新 | 2026-10-08（测试侧建卡） |

## 现象

本地命令执行中 shell 异常退出时，返回 `CommandResult(kind="command", returncode=proc_rc or 255)`——若真实进程恰已退出（rc=0），上层会读成「命令成功」；若为 255，也被当作真实退出码而非「未知」。

## 复现

```text
离线/半真机：本地模式执行长命令（如 `sleep 5`）中途 kill 本地 shell → 检查返回 kind/rc；TB 待补（transport 本地组）。
```

## 证据

静态核实（2026-10-08）：eof 分支无 kind；CommandResult 默认 `command`；远端同类场景结构化 unknown-effect。

## 验收判据（修好即转绿）

① eof 且无 rc/marker ⇒ kind != `command`；② 本地 shell 死亡路径 TB 覆盖；③ 正常完成路径行为不变。

## 下一步 / 责任人

等设计修；测试侧补本地 shell 死亡 TB（1 条即可，配正常路径回归）。


---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
