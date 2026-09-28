# P-080 · `view_type` 在 read 路径不校验（空串/整数/bogus 静默接受）；write 校验后取值又被忽略

| 字段 | 值 |
|---|---|
| 级别 | P2（参数合同不一致 + 死参数） |
| 层 | 上层（verilog / veriloga / layout 包） |
| 归属 | 设计侧（verilog / veriloga 包）；"view_type 是否参与寻址"需 spec owner 定口径 |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/verilog.py:201-230`（read 不碰 view_type）、`:307`（只有 write 校验）、`_view_dir:161`（不使用 view_type）；`src/pyapi/packages/veriloga.py:205-235`、`:476`、`_view_dir:145`。主文件名 `MAIN_FILE` 硬编码，与 spec `8-verilog.md:45`『主文件名由 viewType 决定（`ddMapGetDataTypeFileName` 查）』不一致。截图面同族两处：`src/pyapi/packages/symbol.py:84-96`（ScreenshotRequest.view_type，只透传给 geOpen）、`src/pyapi/packages/layout.py:98-109`（同）；两处对 `view_type="bogus_type_xyz"` 都静默成功。 |
| 首报 | 2026-09-28（第八轮 op×param 参数矩阵攻击发现，卡片直报） |
| 最近更新 | 2026-09-28 |

## 现象

真机（vblog）实测：`read(view_type="")`、`read(view_type=123)`、`read(view_type="bogus_type_xyz")` 全部 `ok=true` 且返回默认视图内容（静默忽略取参）；同一字段 `write(view_type="")` 返回 400 `invalid request: view_type must be a non-empty string`，而 `write(view_type="bogus_type_xyz")` 返回 ok。read/write 校验口径不一致；非默认取值对寻址/主文件名没有任何可观察影响。
**同族第三处（2026-09-28 新增，layout 包）**：`virtuoso.layout.screenshot(view_type="bogus_type_xyz")` 也返回 ok=true 并出图（`view_type="maskLayout"` 与 bogus 之间无可观察差异）；`virtuoso.symbol.screenshot(view_type="bogus_type_xyz")` 同样 ok=true。两条都被新 TB `test/live/packages/screenshot_params_e2e_tests.py`（SC-06）红钉住（跑 `--kind symbol` / `--kind layout` 会在 SC-06 转红——这是**预期红钉**，不是 TB 坏了）。

## 复现

```text
python test/artifacts/tmp/r8_p080_p081_evidence.py（真机；含 read 五态 + write 两态）
python -m pytest test/offline/unit/test_view_type_param_contract.py -q  # 4 条 strict xfail：read 的空串/整数必须 ValueError
```

## 证据

`test/artifacts/evidence/round8/p080-viewtype-p081-remote-path-2026-09-28.json`（live 五态 + write 两态）；`test/offline/unit/test_view_type_param_contract.py`（修复后 xfail→XPASS 转红，强制删标记）

## 验收判据（修好即转绿）

① read 对 view_type 与 write 同口径校验（空/非字符串 → ValueError；4 条 xfail 转绿）；② 产品定口径：若 view_type 按 spec 参与主文件名/视图类型决策 → 实现并对非默认值给可观察差异；若仅为兼容字段 → spec 写明『不参与寻址』并统一 read/write 校验。

## 下一步 / 责任人

设计侧先定 ② 口径、修 read 校验与/或主文件名映射；测试侧按结论删 xfail，复跑 verilog/veriloga 两套 E2E 与离线合同。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
