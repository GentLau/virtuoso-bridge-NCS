# P-070 · 蒙特卡洛能力缺失：只能读回 MC 结果，不能驱动 MC 仿真

| 字段 | 值 |
|---|---|
| 级别 | P2（能力缺失） |
| 层 | 上层（maestro/spectre 包） |
| 归属 | 待决策（产品口径：支持驱动 MC or 明确不做）→ 设计侧实现/写 spec |
| 状态 | **待决策** |
| 位置 | `src/pyapi/packages/_maestro_util.py:141`（唯一 MC 相关代码）、`:291-313`（`parse_overall_yield`）；spec：`6-maestro.md:130`（唯一 MC 提及，锁语义）、`7-spectre.md`（分析枚举无 montecarlo） |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

## 现象

全 `src/` 搜 `monte|carlo`（忽略大小写）**只命中 1 行**（历史目录正则）；**没有任何配置/启动 MC 分析的代码**，spectre 分析枚举也只有 `tran/dc/ac/info/noise`。现状 = 只能读回别人跑完的结果（yield/mean/sigma + `MonteCarlo.N` 目录识别），**不能驱动蒙特卡洛仿真**。用户 2026-09-24 判定：能力缺失要提 bug。

## 复现

```text
`rg -n -i "monte|carlo" src/`（只 1 行）；`rg -n -i monte spec/`（只 1 处，锁语义）；离线只有解析用例：`pytest test/offline/unit/test_maestro_util.py -q`
```

## 证据

代码锚点见上；测试证据：`test_maestro_util.py::test_overall_yield`、`test_natural_sort_histories`（离线）；真机 MC **从未跑过**（无证据）

## 验收判据（修好即转绿）

二选一：① 支持驱动 —— 能配置 montecarlo 分析并启动，跑完读回 yield/mean/sigma 且与 ADE GUI 对数一致（真机一次）；② 不支持 —— spec 明确写「只读 MC 结果、不驱动」并标为明确不做

## 下一步 / 责任人

设计侧先定口径；定了之后测试侧补真机 MC 验证（或补不覆盖声明），并把「两项目全链」里的 MC/PVT 一栏按口径收口

## 设计侧进展（2026-09-28，提交 `64c803c`）
- 真机调查 v2：`set_run_mode('Monte Carlo Sampling')` + **裸** `maeRunSimulation` 可跑出真 history `MonteCarlo.0`（24.8s）；文档写的 `?runMode` 默认 Single Run 与实测不符。
- 选项矩阵：`maeSetRunOption` 只认 `mcmethod`/`mcnumpoints`；其余 15 项走 `axlPutRunOption`+`axlSetRunOptionValue` 可写可回读（`dutsummary` 读回空串）。
- 副作用提醒：MC 实验会把共享库 `maestro_tb/rc_probe` 的 run_mode 改成 Monte Carlo Sampling，**跑完务必还原**（本轮已由测试侧恢复过一次）。
- 待办：产品拍板「支持驱动」后，在 maestro 包补正式入口 + spec；测试侧据此补真机 MC 验证与 yield/sigma 对数。

---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
