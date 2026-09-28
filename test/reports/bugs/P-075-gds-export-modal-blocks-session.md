# P-075 · `virtuoso.layout.gds` 导出后会话残留模态对话框（"Stream out translation complete"）→ 同会话 SKILL 通道挂死，必须重启实例

| 字段 | 值 |
|---|---|
| 级别 | P1（会话被挂死；多用户/GDS 后继续操作的流程直接卡住） |
| 层 | 上层（layout/gui 包） |
| 归属 | 设计侧（上层 layout.gds / strmout 调用路径） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/layout.py` 的 `virtuoso.layout.gds`（strmout/XStream 调用）＋ `src/pyapi/packages/gui.py` 的 `auto_dismiss`（现有规避手段对它无效） |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

## 现象

在**同一会话**里执行 `virtuoso.layout.gds`（导出 GDS 到新目录，XStream/strmout）之后，**该会话若出现模态** `"Stream out translation complete"` 窗口（XStream 完成框），该会话的 SKILL 通道被一个**模态对话框**阻塞：窗口列表可见 `"Stream out translation complete"`（class `virtuoso`）＋ `"XStream Out"`；此后该 token 的任何 `basic.skill.execute` / 依赖 SKILL 的操作都 30s 超时（`SKILL execution timed out`）。实测：`virtuoso.gui.auto_dismiss` 返回 ok 但 `dismissed=null`（关不掉这个窗口），**只能重启该实例**才能恢复。
受害场景（已复现 3 次）：多用户协同里 A 出完 GDS、B 改同一 cell 的 schematic 后，A 的回读超时；单会话流程里"出 GDS 后继续写原理图"同样中招。
**观察到的差异（待设计侧定位触发条件）**：同一台机器上 `vblog` / `calprobe` 会话导出 GDS 后只有**非模态**的 `"XStream Out"` 主窗体、SKILL 仍可用；`vbuser1`（Xvfb `:105`，headless）稳定留下**模态完成框**并挂死 —— 可能与 XStream 表单/焦点/headless 显示或 strmout 参数有关。

## 复现

```text
① **最小复现（单会话，无第二用户）**：
`PYTHONPATH=src python test/semi/probes/gds_then_skill_probe.py --token vb-vbuser1 --file-root /home/vbuser1/.virtuoso-bridge/vbuser1/file --skill-timeout 45`
→ lib/view/write/read-back/gds-export 全 OK，最后一步 `skill-after-gds` FAIL：`elapsed_s=30.0, SKILL execution timed out`（证据 JSON 见下）。
② 二分复现脚本（含多用户版本，定位到 --gds 是触发项）：
`PYTHONPATH=src python test/artifacts/tmp/bisect_cross_user_block.py --cell blk_gds_x --symbol --layout --gds`
→ 观察最后一步：`A: read after B write (30.0s) ok=False err=SKILL execution timed out`；去掉 `--gds` 的对照组（`--symbol --layout`）通过（0.3s）。
③ 端到端：`PYTHONPATH=src python test/live/flows/adc_sar_flow_tb.py --work-dir test/artifacts/env/log-vblog --token-a vb-vbuser1 --token-b vb-vbuser2` → 21/22，失败步 `A-see:B's instance`（read_error=SKILL execution timed out）。
④ 窗口取证：`xwininfo -display <A 的 DISPLAY> -root -tree | grep -E 'Stream|XStream'`。
```

## 证据

`test/artifacts/evidence/round7/gds-then-skill.json`（单会话最小复现：RED）；`test/artifacts/evidence/round7/adc-sar-pos2.json`（21/22，失败步带原始 read_error）；窗口列表（A 会话）：`0x4001e9 "Stream out translation complete"`、`0x4001e6 "XStream Out"`（test/artifacts/tmp/check_wedge_after_gds.sh 的输出）；对照组 E1/E2（symbol / symbol+layout）全绿、E3（+gds）复现。

## 验收判据（修好即转绿）

① `virtuoso.layout.gds` 返回后，**同会话**的下一次 SKILL 调用在正常时限内成功（无需重启）——最小复现即 `gds_then_skill_probe` 转绿；② 或由产品在导出结束时关闭自己的 XStream 模态窗口，并让 `gui.auto_dismiss` 能识别/关闭它；③ 回归门：新增探针 `test/semi/probes/gds_then_skill_probe.py` 转绿 + ADC TB 回到 22/22。

## 下一步 / 责任人

设计侧定位 strmout 调用（是否用了会弹完成框的 XStream UI 路径；建议改批处理/导出后显式关窗）。测试侧：新探针先钉住红灯（已加），修好后跑「探针 + ADC TB + 一次多用户 GDS→改单」三轮复验。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
