# round9 · 原子级覆盖独立复核（60 原子）

> 执行：subagent `/root/opparam_r9`｜2026-09-29｜工具：`test/shared/runners/audit_atom_coverage.py`（复跑，非重写）
> 证据：`test/artifacts/evidence/atom-coverage-2026-09-29.json`

## 1. 结果

| 指标 | 结果 |
|---|---|
| 原子总数（schematic / layout / symbol） | **60** |
| semi/live **零引用**（"从未在真机跑过"强信号） | **0** |
| 其中证据树里也查不到的 | 0 |
| 阳性对照 `place_rect`（出现在多少证据文件里） | **23**（对照有效，不是"检索器失灵") |
| 写了不读回：需人工分类 | **0** |
| 已知误报（带书面理由） | **13** |
| 已知弱判据 | **0** |

## 2. 本轮的唯一增量：2 条 needs-triage 的分类

复跑时新增 2 条待分诊（round8 后新写的两个 calibre 探针），逐条核实后归入"已知误报（间接判据）"，
与既有的 `s11_inprocess_lvs_tb` / `calibre_e2e_tests` 同类：

| 位置 | 写操作 | 为何不是缺口 |
|---|---|---|
| `test/semi/probes/calibre_flat_turbo_probe.py` | `basic.file.upload` | 上传的 deck 由下游 `calibre.drc` 消费；判据是 flat 模式不带 `-turbo`（argv/日志）且 `DRC.rep` 产出（P-093）。上传本身另有 `ok is True` 断言（`_upload_text:103-109`） |
| `test/semi/probes/calibre_timeout_probe.py` | `basic.file.upload` | 上传的坏 deck 由下游 `calibre.drc` 消费；判据是 `status=timeout`（P-098）。上传本身另有 `ok is True` 断言（`_upload_text:90-96`） |

两条例外已写进 `test/shared/runners/audit_atom_coverage.py::KNOWN_FALSE_POSITIVES`（含理由），
复跑后 **needs-triage 归零**。

## 3. 口径（防止过度声称）

- 本审计是**引用面**审计：原子名在 semi/live 测试文件里出现 + 有下游读回/比对动作，
  **不等于**该原子已在真机执行过——真机证据只认 `run_all_http.py`（HTTP 8127）的套件结果。
- `gap=0 / 待分诊=0` 只说明"没有哪个原子在 semi/live 完全没被引用"，不构成覆盖率结论。
