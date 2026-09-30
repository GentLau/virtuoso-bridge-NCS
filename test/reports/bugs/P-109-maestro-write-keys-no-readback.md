# P-109 · maestro 7 个写键的公开读回面已补齐（corner `enabled`/`enabled_tests`/`disabled_tests`/`models`、test `job_policy`）：真机值级读回 10/10，待测试侧复核销卡

| 字段 | 值 |
|---|---|
| 级别 | P3（覆盖阻塞：参数有、判据没有；按《全量测试准则》§2 表 C 属“readback:none”，不得算作已比对） |
| 层 | 上层（maestro 包）· 写命令族缺公开读回面 |
| 归属 | 设计侧（已选①：在 `read_config` 暴露对应字段） |
| 状态 | **待测试侧** |
| 位置 | 写入侧：`src/pyapi/packages/maestro.py::_command_exprs` 的 `set_corner`（`?enabled`/`?enableTests`/`?disableTests`）、`setup_corner`（`axlSetModelFile`/`axlSetModelSection`）、`set_job_policy`（`?jobType`/`?testName`）；读取侧：`read_config` 的公开 schema（顶层 `library/cell/view/tests/variables/parameters/corners/run_options/run_mode/job_control_mode/current_history`，test 条目 `variables/analyses/outputs/env_options/sim_options`）**没有上述字段**。 |
| 首报 | 2026-09-30（round9 嵌套键真机补测；按用户要求把“需协调项”立卡） |
| 最近更新 | 2026-09-30 17:50（设计侧实现 + 真机值级读回证据，转测试侧收口） |

## 现象

真机（2026-09-30，TB `test/live/packages/maestro_nested_keys_e2e_tests.py`，9/9 PASS）：
① `set_corner(enabled=False)` / `enable_tests` / `disable_tests` → 写入成功、`read_config.corners` 能看到 corner **名字**，但**看不到启用状态**；
② `setup_corner(model_file=…, model_section=…)` → corner 变量可读回，**model 文件/section 读不回**；
③ `set_job_policy(test_name=…, job_type=…)` → 写入成功，**无任何读回点**；
证书侧只能写成“接受性覆盖 + readback:none”，按准则不得写“已覆盖”。

## 复现

```text
PYTHONPATH=src python test/live/packages/maestro_nested_keys_e2e_tests.py --transport http --out test/artifacts/evidence/round9/maestro-nested-keys-r9.json  # 看 NKM-02/03/05 的 readback 注记
```

## 证据

`test/artifacts/evidence/round9/maestro-nested-keys-r9.json`（`readback: none` 的三条用例与 schema 证据）；对照：`type_name/type_value`（set_var）与 `spec_name`（delete_spec）**有**读回面并已值级断言（同 TB NKM-04/06）

## 验收判据（修好即转绿）

二选一：① `read_config` 增加对应字段（corner.enabled、corner.model.{file,section}、job policy 的 jobType/testName），TB 升为值级断言；② spec 逐键写明“本版只写不读”并说明为什么（例如底层 API 无查询接口），同时把 `readback:none` 记入正式口径（不再作为缺口）。

## 下一步 / 责任人

**设计侧已落地 `d3b0845`（2026-09-30 17:04）**：`read_config` 新增 corner `enabled/enabled_tests/disabled_tests/models[].{name,file,section,test}` 与 test `job_policy.{simulation,netlisting}`；spec `6-maestro.md` 同步。真机：`maestro_nested_keys_e2e_tests.py` 值级断言 **10/10 PASS**，证据 `test/artifacts/evidence/verify-fix-r10/maestro-nested-keys-p109-final2.json`（NKM-02/03/05 均按值读回；simulation policy 可见 maxJobs=2）。待测试侧复核后把本卡移入已关闭。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
