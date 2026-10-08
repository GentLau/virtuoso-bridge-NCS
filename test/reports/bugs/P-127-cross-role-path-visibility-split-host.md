# P-127 · 跨 role 可见性缺口：文本视图/截图在 split-host（file/command 与 daemon/gui 不同机）合法配置下静默错位——上传成功但 daemon 读不到、清理在错误主机执行不报错

| 字段 | 值 |
|---|---|
| 级别 | P2（合法配置下的静默错误；需口径裁决） |
| 层 | 上层包 ↔ 中层 role 拓扑 · spec §5.6 口径边界（split-host） |
| 归属 | 设计侧+spec 侧（二选一裁决：包内把同路径读/写/清理收敛到同一 role；或在注册/文档固定可见性要求并在注册期校验） |
| 状态 | **待决策** |
| 位置 | `src/pyapi/packages/verilog.py:186-216` / `veriloga.py:159-190`（SKILL 在 daemon 侧解析 `ddGetObjReadPath`，文件却走 file 角色上传/下载）；截图四包（`schematic.py:940-944`、`symbol.py:978-985`、`layout.py:1477-1487`、`gui.py:421-425`）写 gui/daemon root、用 command 角色 mkdir/rm；spec `spec/design-concepts/总览/1-四层整体架构与接口.md` §5.6（「bridge 不要求 role 共享目录；跨 role 传文件由调用方保证」） |
| 首报 | 2026-10-08（外部静态审查 A8） |
| 最近更新 | 2026-10-08（测试侧建卡） |

## 现象

file/command 与 daemon/gui 不同机时：文本视图上传「成功」但 daemon 侧路径不可见/是旧内容；截图 `rm` 落在 command 主机、删不到 gui 主机文件且 `rm -f` 不报错 → 残留；若 file 角色看不到 gui 产物，下载失败但错误指向不明。

## 复现

```text
常驻环境 fork：daemon→wsl-gent、file→本地 wsl、command→另一台 → 跑 text-view `set_source` 与截图各一发，观察落点与返回；TB 待补（multi-role 组已有 role-split 骨架可扩展）。
```

## 证据

静态核实 + spec §5.6 原文（2026-10-08）。

## 验收判据（修好即转绿）

① 裁决落地（包内同 role 闭环 or 注册期校验）；② split-host 至少覆盖文本视图与截图各一条 TB；③ 不可见时结构化错误（VB-PATH-NOT-VISIBLE 或明确提示），不静默错位。

## 下一步 / 责任人

请用户/spec owner 裁决路线（测试侧建议：包内同 role 闭环优先，注册期校验兜底）；裁决后测试侧补 split-host TB。


---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
