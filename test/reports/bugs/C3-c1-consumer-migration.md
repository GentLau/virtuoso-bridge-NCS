# C3 · C1 落地后测试侧消费方未适配：仍按旧 `data` 壳解析响应（约 50 个文件）

| 字段 | 值 |
|---|---|
| 级别 | P2（测试资产失效：不修则 live/semi 门禁假红/读不到 steps） |
| 层 | 测试侧（消费方适配）· C1 破坏性契约变更 |
| 归属 | 测试侧（root） |
| 状态 | **待测试侧** |
| 位置 | 命中面：`rg -l 'get("data")' test/ --glob '!test/artifacts/**'`；已适配 4 个（`calibre_export_pex_e2e_tests.py`、`maestro_e2e_tests.py`、`skill_log_options_e2e_tests.py`、`maestro_p095_overwrite_wedge_probe.py`）。 |
| 首报 | 2026-09-29（C1 落地后首轮复跑暴露） |
| 最近更新 | 2026-09-29（新立） |

## 现象

C1 契约（`2f88853`）把业务载荷移到顶层（值型 `value`、命令/skill 型 `result`）、成功默认省略 `steps`、失败壳去掉 `data`；旧解析 `response.get("data")` 拿到空 dict ⇒ 假红（calibre 门禁 ENV-01「环境缺 drc_ok」、maestro TB WRITE-05「SKILL failed: {}」）或读不到响应级 `steps`（WRITE-06「save_setup 步骤 []」）。

## 复现

```text
PYTHONPATH=src python test/live/packages/calibre_export_pex_e2e_tests.py --transport http
```

## 证据

C1 契约 TB `test/offline/unit/test_top_layer_dispatch.py::test_success_returns_result_body`（`{"ok":True,"value":7}`）；本轮实测：`basic.command.run` → 顶层 `result`；`maestro.read_config` → 顶层 `value` + **响应级** `steps`。

## 验收判据（修好即转绿）

① 命中文件全部改为形状无关解包（顶层 `value`/`result` 优先，兼容旧 `data`）；② 需要步骤名的用例改读响应级 `steps`；③ 逐套复跑 live/semi 门禁并如实记账；④ 完成后关 C3，C1 随之可关。

## 下一步 / 责任人

按清单分批适配（优先级 live/packages → semi/probes → live/flows），每批复跑对应门禁。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
