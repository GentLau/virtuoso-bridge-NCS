# C1 · `basic.skill.execute` 响应 JSON 冗余：同一个 `VirtuosoResult` 在 `data.result` 与 `data.steps[0].detail` 各序列化一次，空可选字段全展开

| 字段 | 值 |
|---|---|
| 级别 | P2（全局响应形态缺陷：所有 basic.skill.execute 命中；两层重复携带完整结果，日志开启时体积翻倍） |
| 层 | 上层（basic 包 + pyapi.models 序列化）· 响应契约 |
| 归属 | 设计侧（上层 basic.py 的结果构造 + pyapi.models 的序列化口径；若涉及顶层 jsonable 归顶层） |
| 状态 | **待决策** |
| 位置 | `src/pyapi/packages/basic.py:146-155`（`Result(steps=[... detail=skill], result=skill)` 同一对象放两处）；`src/pyapi/models.py:24-37`（`VirtuosoResult` 7 个字段；空 errors/warnings/metadata/log 也参与 model_dump）；`src/server/dispatch.py:58-77,151`（`jsonable` → `model_dump(mode="json")`，外层再包 `ok/data/error`）。 |
| 首报 | 2026-09-29（用户直报：`basic.skill.execute` 的 `1+1` 响应过长） |
| 最近更新 | 2026-09-29（新立，记录现状；未修） |

## 现象

实测 `basic.skill.execute(skill_code="1+1")` 的响应：外层 `ok`、`data.ok`、`steps[0].ok`、`detail.status` 四处表达成功；**同一个 `VirtuosoResult` 在 `data.steps[0].detail` 和 `data.result` 各出现一次**；两份都带
- `errors: []`、`warnings: []`、`metadata: {}`、`log: ""`；
- `execution_time: 0.32900000002700835`（完整浮点 repr）。
真正结果只有 `output: "2"`，响应仍约 700 字节。

## 复现

```text
POST http://127.0.0.1:8127/api/operation
{"operation":"basic.skill.execute","token":"<token>","skill_code":"1+1"}
对照：同一响应里 `data.result` 与 `data.steps[0].detail` 的 `output/status/errors/warnings/metadata/log` 完全相同。
```

## 证据

用户 2026-09-29 实测响应（见卡片原文）；代码锚点三处；上游测试现状：`test/live/flows/*` 大量直接读 `data.result`，`adc_sar_flow_tb.py` 等又 fallback 到 `steps[0].detail`，说明重复形态已成事实接口。

## 验收判据（修好即转绿）

① 先定 canonical 位置（建议只保留 `data.result`，`steps` 只留步骤元信息/失败时留原始结果）；② 同一 `VirtuosoResult` 不得在同一响应中出现两次；③ 空 `errors/warnings/metadata/log` 按选定口径省略，`execution_time` 限定精度；④ 新增离线契约 TB 钉住最小响应形态；⑤ 更新所有消费 `data.result`/`steps[0].detail` 的调用方。

## 下一步 / 责任人

设计侧先裁决响应 canonical 形态与空字段口径（需同步 `1-上层.md`/顶层响应壳）；测试侧按裁决补响应形态 TB，再改 basic.py/models.py。

## 讨论决策（2026-09-29）

**决策 1（统一壳）**：顶层不再把业务结果套进 `ok/data/error` 壳——业务包可达且返回结果时，**直接返回业务包结果本体**；只有走不到业务包（非法 JSON / 缺 `operation`/`token` / 未知 operation / Request 构造失败 / 未预期异常）才返回壳形错误。

配套前提（三条，缺一即不可行）：
- 业务 Result 必须保证含 `ok`/`error`——建议在 `pyapi.models` 收口 Result 基类（当前 10 个包各自定义 Result，口径已漂移）；
- `ok`/`error`/`steps` 定为**保留字段**，业务字段不得占用（合并后与业务字段同一命名空间）；
- 属**破坏性变更**：需同步消费方（`test/live/flows/*` 大量读 `data.result`，`adc_sar_flow_tb.py` 等 fallback 到 `steps[0].detail`）。

**决策 2（steps 改造）**：任何业务操作支持公共可选参数 `step_details`；**不传时 `steps` 整字段省略**；开启时每步记 `{"name": 名, "ok": 布尔, "detail": 中层结果}`，键名统一 `name`，失败步骤必须保留 `detail`/`error`。

**决策 3（删字段）**：删除 `VirtuosoResult.metadata`（`src/pyapi/models.py:36`）与 `SimulationResult.metadata`（`:111`）——新链路无任何写入点、恒为 `{}`；日志已有 `log` 字段，其余扩展信息应由上层 Result 的业务字段承载，不由公共模型提供万能字典（`spec/research/04-log-return-system-proposal.md:159` 同向）。

影响面（已核对）：`src/` 无写入亦无读取；`examples/` 中 7 处 `result.metadata` 读取的是**旧包** `virtuoso_bridge`（旧实现里 metadata 承载 `command`/`spectre_command`/`delivery`/`queue_wait_s` 等），与新模型无关；`SimulationResult` 除定义与导出外无其他使用点。

**决策 4（`execution_time` 精度）**：**保留三位小数**（毫秒级，`round(x, 3)`）。建议在 `VirtuosoResult` 模型层用字段序列化器统一处理——现写入点集中在 `src/common/skill_client.py`（共 10 处），逐点 round 既易漏、新路径也会再漏；模型层处理可让 HTTP 响应与 `save_json` 等所有出口口径一致。

---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
