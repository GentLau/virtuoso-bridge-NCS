# C07 · spec 把 `calibre.export_cdl` 折进 `calibre.lvs` 的 `source` 参数（`source/emit_cdl/cds_lib`）：实现已落地、独立 op 已删除，待测试侧复跑销卡

| 字段 | 值 |
|---|---|
| 级别 | P3（一致性：spec §8 验收两行在现行实现上不可达；TB 仍跑在 spec 已删除的旧入口上） |
| 层 | spec↔实现一致性（上层 calibre / LVS 源网表入口） |
| 归属 | 设计侧（已选①：实现 fold；测试侧收口红钉） |
| 状态 | **待测试侧** |
| 位置 | spec：`spec/design-concepts/上层/12-calibre.md` §4.3 参数表（`:157-168`）、§4.3.2 auCdl 内产（`:194-208`）、§6.3（`:246-249`）、§8 验收（`:258-273`），源自 commit `6b1b855`（2026-09-29 14:29，**只改 spec**）；实现：`src/pyapi/packages/calibre.py:82-145`（`RunRequest` 无这 3 个字段）、`:1115-1124`（OPERATIONS 仍注册 `calibre.export_cdl`，实体在 `:341-423`）。 |
| 首报 | 2026-09-29（第九轮 B 线发现 + 测试/root 复核 commit `6b1b855` 与实现后定案） |
| 最近更新 | 2026-09-30 17:50（设计侧实现 + 真机闭环证据，转测试侧收口） |

## 现象

按 spec §8 调 `calibre.lvs(source=…)` 会在请求解析即 400：`server/dispatch.py::build_request` → `RunRequest(**fields)` → `TypeError: got an unexpected keyword argument 'source'` → `invalid request for operation: …`。反向：spec 已删的 `calibre.export_cdl` 仍可调用，且真机套件与 4 条 flow TB 都在用它 —— 审计口径下「spec 验收行无实现无 TB」与「TB 覆盖的是 spec 不认的入口」同时成立。

## 复现

```text
离线（不碰真机）：
```python
from pyapi.packages.calibre import RunRequest
RunRequest(token='t', deck='/r/deck', source={'kind':'cdl','path':'/r/x.cdl'})
# TypeError: … unexpected keyword argument 'source'
```
红钉：`test/offline/unit/test_calibre_lvs_source_contract.py`（strict xfail ×2，挂本卡）。
```

## 证据

`git show 6b1b855`（spec-only：删 §4.6 `export_cdl`、§4.3 增 `source/emit_cdl/cds_lib`、§8 验收改 source 口径）；`test/reports/round9/op-param-r9.md` §6.3（B 线独立发现）；旧 API TB：`test/live/packages/calibre_e2e_tests.py:186-193,339,343`、`test/live/flows/design_iterate_tb.py:763,841`、`test/live/flows/project_flow_tb.py:371`、`test/live/flows/serdes_rx_flow_tb.py:618`、`test/live/flows/s11_full_flow.py:286`；研究文档仍写 export_cdl 独立可用：`spec/research/calibre/README.md:21,30`。

## 验收判据（修好即转绿）

二选一：① **实现**——`calibre.lvs` 接受 `source.kind=cdl|schematic`（schematic 按 §4.3.2 在 run dir 内走 auCdl 现产并作为 LVS 源）+ `emit_cdl` + `cds_lib`，同时明确 `calibre.export_cdl` 去留（删除，或标注兼容保留并在 spec 写明）→ 红钉 XPASS 转绿流程走完；② **回退 spec**——写回独立 `export_cdl` 与 §4.6、删除 source 口径 → 测试侧把红钉改为非缺陷断言并销卡。

## 下一步 / 责任人

**设计侧已落地（2026-09-30）**：`RunRequest` 收 `source/emit_cdl/cds_lib`，`calibre.lvs` 在 run dir 内折 `source`；独立 `calibre.export_cdl` 已删除；4 条 flow TB（design_iterate/project_flow/s11_full_flow/serdes_rx）与包 E2E 已迁到 `source=` 口径。真机证据：`test/artifacts/evidence/verify-fix-r10/c07-lvs-source-fold-green.json`（LVS-02/03 均 `correct`）与 `c07-design-iterate-lvs3.txt`（`design_iterate --stage lvs` ok=true、source.schematic→`correct`、cdl 680 B）。离线：`test/offline/unit/test_calibre_lvs_source_contract.py` 红钉转绿 + `test_calibre_package.py` 新增 cds_lib 回归（`test_lvs_source_schematic_with_cds_lib_completes`）。待测试侧复跑包 E2E（含 flow 抽跑）后把本卡移入已关闭；LVS-01（旧 `cdl=` 参数）不在 spec 口径内、强判据预期红，属 TB 侧残留，建议一并清理。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
