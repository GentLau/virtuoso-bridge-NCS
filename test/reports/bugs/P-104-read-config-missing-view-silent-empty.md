# P-104 · `maestro.read_config` 对**不存在的 view** 静默返回空配置（ok=true）；调用方无法区分「空 setup」与「view 不存在」

| 字段 | 值 |
|---|---|
| 级别 | P2（静默假数据：空配置会被当成既有 setup 继续消费） |
| 层 | 上层（maestro 包）· 缺失目标的静默成功 |
| 归属 | 设计侧（maestro 包）；口径二选一需 spec owner 拍板 |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/maestro.py:1321`（`read_config` 入口）→ `:3095-3102`（`maeOpenSetup(...)` 读会话），**不校验 cellview 是否存在**；同包 `read_results` 对缺失结果目录会结构化失败（口径不一致）。 |
| 首报 | 2026-09-29（第八轮覆盖率重算时由 maestro view-param TB 红钉暴露，root 复核并最小化） |
| 最近更新 | 2026-09-29（新立） |

## 现象

健康真机（vb-s11，2026-09-29 02:2x）实测：`read_config(library="maestro_tb", cell="rc_probe", view="no_such_view_p104")` → **ok=true**，返回空配置（`tests=[]`、`corners=["Nominal"]`、`variables={}`、`run_mode=""`），steps 为 `open_session/setup/options/...`；调用方无法据此判断 view 不存在。同一断言在 `test/live/packages/maestro_view_param_e2e_tests.py` 的只读族（"不存在的 view 必须结构化失败"）当前为**红钉**（2026-09-29 01:5x 全量覆盖跑 `packages/maestro view-param (direct)` rc=1，报`read_config expected structured failure, got ok`）。

## 复现

```text
python test/artifacts/tmp/r8_p104_readconfig_probe.py        # vb-vblog 当时被 P-086 卡住，已在 vb-s11 确认
python test/live/packages/maestro_view_param_e2e_tests.py --transport http  # read 族负例当前红
```

## 证据

`test/artifacts/evidence/round8/p104-readconfig-missing-view.json`（vb-s11 原始响应）；`test/artifacts/evidence/round8/coverage-main-r8d.log`（vblog 侧同断言原文）。

## 验收判据（修好即转绿）

① `read_config` 对不存在 view 返回结构化失败（点名 library/cell/view）；或 ② spec 明确「不存在即空配置」语义 → TB 按该口径改成断言空配置并加 NOTE，二者取其一并同步报告。

## 下一步 / 责任人

设计侧定口径；测试侧按结论把 `maestro_view_param_e2e_tests.py` 的 read 族负例改成对应用例后复跑。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
