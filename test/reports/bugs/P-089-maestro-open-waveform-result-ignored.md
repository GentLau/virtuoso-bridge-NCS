# P-089 · `maestro.open_waveform_gui.result` 声明但**从不被实现读取**（静默无效）

| 字段 | 值 |
|---|---|
| 级别 | P3（静默无效参数，与 P-084 同类） |
| 层 | 上层（maestro 包） |
| 归属 | 设计侧（实现语义或从模型/spec 删除） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/maestro.py:187`（`OpenWaveformRequest.result`）；全文件 `request.result` 只出现在 read_results 的波形表达式（`:1909/:1912`），open_waveform_gui 的 SKILL（`:3139-3158`）只做 `v(signal)`，无 `?result` 分支 |
| 首报 | 2026-09-28（第八轮 op×param 补测；红灯探针已留证） |
| 最近更新 | 2026-09-28（新立） |

## 现象

`open_waveform_gui(result="ac")` 与 `result="no_such_result_name"` **都成功**、都返回正常窗口（window:243 / window:245）⇒ 参数对行为零影响。

## 复现

```text
`PYTHONPATH=src python test/semi/probes/maestro_open_waveform_result_probe.py`（预期红）
```

## 证据

`test/artifacts/evidence/round8/p089-open-waveform-result.json`

## 验收判据（修好即转绿）

二选一：① 让 result 参与波形表达式（`?result`）并给出错误名失败语义；② 从模型/spec 删除该字段；探针转绿或删除

## 下一步 / 责任人

设计侧定口径；测试侧复跑探针确认


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
