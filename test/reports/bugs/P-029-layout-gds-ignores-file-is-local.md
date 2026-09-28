# P-029 · `layout.gds` 导出忽略 `file_is_local=False`：产物被下载到客户端假路径树，靶机不留文件仍报 completed

| 字段 | 值 |
|---|---|
| 级别 | P2（调用方意图被静默忽略；客户端被写陌生绝对路径） |
| 归属 | 设计侧（`layout.py` 发布路径） |
| 状态 | **待设计修（已报 `bug-20260922T123712Z-vblog-afac3523`）** |
| 位置 | `src/pyapi/packages/layout.py:1061`（export 分支 `_publish_remote`）、`:1219-1238`（`_publish_remote` 无条件在客户端建目录+下载）、字段定义 `:84` |
| 首报 | 第五轮（2026-09-22；已报 `bug-20260922T123712Z-vblog-afac3523`） |
| 最近更新 | 2026-09-28（补齐卡片） |

## 现象

靶机产物被"下载"到客户端假路径树（`C:\home\Gent\...`），靶机上不留文件，返回值仍报 `reason=completed`；后续依赖靶机产物的步骤（LVS 取 GDS）必然失败。

## 复现

```text
`virtuoso.layout.gds` 带 `file_is_local=False` 导出到不存在目录；现场保留 `C:\home\Gent\.virtuoso-bridge\vbs11\tmp\cmp_top.gds`
```

## 证据

台账 P-029 行；bug id `bug-20260922T123712Z-vblog-afac3523`

## 验收判据（修好即转绿）

按 `file_is_local` 分流，或明确报「该参数在导出方向不支持」+ 客户端路径合法性校验

## 下一步 / 责任人

设计侧修；测试侧复验 S11 gds 阶段 + 路径边界探针


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
