# 条款证据强度分布（事实列，不改变 verdict）

> 维护：测试（root）｜ 2026-09-28 ｜ 强度列由 `merge_round8_spec_matrix.py` 生成
> 数据：`round8-spec覆盖矩阵.json` 的 `evidence_level` 字段

## 0. 结论摘要

| 口径 | 数字 |
|---|---|
| direct + indirect 条款 | 238 |
| 其中**至少一条 live 证据** | **78** |
| 其中**至少一条 semi 证据**（无 live） | **20** |
| 其余为**仅离线证据** | **140** |
| 113 个 op（79 业务 + 34 原子）里**有 live/semi 实跑调用点**的 | **111** |
| 仅有零调用点的 op | 2（`calibre.pex` / `calibre.export`，见 G1 车道） |

> op 级统计来自 `op-coverage.json`（AST 调用点 + 文件归属），复算命令见 §4。

## 1. 判定原则（本轮口径，供评审核对）

条款的**主语**决定它的设计验证层，不搞"一刀切都要 live"：

1. **Python 侧逻辑**（参数校验、默认值补全、命令/SKILL 文本拼装、错误映射、
   PSF/报告/日志解析、预算与截断、注册与路由、端口与路径规则）→ 离线契约/桩件
   用例就是该条款的设计验证层，**不因"没有 live"而降级**。
2. **不可控或有副作用的路径**（故障注入、回滚、资源拒绝、模态弹窗规避、
   传输中断清理）→ 离线桩件是**唯一可控**的判据；live 环境不允许为了取证去
   制造这类破坏。此类条款的 live 面只体现在"正常路径仍然工作"。
3. **工具侧真实行为**（真实写入/读回/生成/导出/仿真/窗口/license/launcher）
   → 必须有 `live` 或 `semi` 证据；若只有离线证据，必须在 §3 逐条点名并承接。

## 2. 按文档分布

| 文档大类 | live/semi | 仅离线 | 小计 |
|---|---:|---:|---:|
| 上层/* | 75 | 66 | 141 |
| 总览/* | 9 | 18 | 27 |
| 顶层/* | 2 | 16 | 18 |
| 中层/* | 5 | 28 | 33 |
| 底层/* | 0 | 8 | 8 |
| 其他/* | 7 | 4 | 11 |
| **合计** | **98** | **140** | **238** |

> 上层 141 条里仍有 66 条只引用离线判据；其**行为级**子集已逐条承接（§3），
> 其余为 §1 原则 1/2 覆盖的 Python 侧与故障注入类条款。

## 3. 仅离线证据的**行为级**条款：承接证据逐条点名

下表列出"主语是工具侧真实行为、但当前只引用了离线证据"的条款，
按 §1 原则 3 给出该条款**行为面的同步承接证据**（op 级 live/semi 调用点，可复算）。

| 编号 | 条款摘要 | 行为面承接（live/semi） |
|---|---|---|
| symbol#023 | `read` 默认 `view="symbol"`/`view_type="schematicSymbol"`，必须返回通用 shapes | `virtuoso.symbol.read` 24 个 live 调用点（`symbol_e2e_tests.py`、`design_iterate_tb.py`） |
| symbol#117 | `schPinListToSymbolGen` 按传入顺序生成（`sort_pins` 不承诺排序） | `virtuoso.symbol.generate` 22 个 live 调用点（`symbol_e2e_tests.py`、`project_flow_tb.py`） |
| layout#139 | 禁止无 bbox 的 `hiZoomIn/Out`（会卡死 SKILL 通道） | 判据是"生成文本里不出现无 bbox 的 zoom"（离线）；live 侧 `virtuoso.layout.display/read` 每轮套件都在跑 |
| layout#185 | via 图形不在 read 结果里，不要依赖默认 | `layout_geometry_classification_e2e_tests.py`（真机几何分类） |
| layout#189 | via 只能按 `pos + orient` 索引 | 同上 |
| verilog#071 | `ihdl` 返回码不可信，只看日志 + 产物 | `virtuoso.verilog.import` 20 个 live 调用点（`verilog_e2e_tests.py`、`verilog_import_params_e2e_tests.py`） |
| verilog#108 | `VERILOGIN-127` 拒绝并降级 functional | 同上（真机降级路径已实测） |
| veriloga#053 | 写临时文件 → 校验读回 → 原子替换 `veriloga.va` | `virtuoso.veriloga.check_and_save` 9 个 live 调用点（`veriloga_e2e_tests.py`） |
| veriloga#055 | `master.tag` 内容与模块名约束 | 同上（真机 `check_and_save` 后读回） |
| veriloga#085 | `dbOpenCellViewByType(..., "w")` 恒 nil → 必须走文件路径 | `virtuoso.veriloga.write/read` 16/13 个 live 调用点 |
| veriloga#089 | AHDL 上下文默认未加载 → 冷启动需 `loadContext` | 同上（真机保存成功即证明上下文处理正确） |
| skillref#102 | `name` 与 `entry` 的区别只在是否并入语法/描述 | `virtuoso.skillref.search` 21 个 live 调用点（`skillref_e2e_tests.py`） |
| calibre#011 | 默认非阻塞 + `status`/`read_results` 三件套 | `calibre.drc` 8 + `calibre.status` 7 + `calibre.read_results` 28 个 live 调用点 |
| calibre#057 | 启动器固定 `ulimit -n 65536` | 真机 launcher 文本落盘可查（`calibre.drc/lvs` live 调用点） |
| calibre#060 | run 默认非阻塞：写 launcher、后台启动、立刻返回 `job_id` | `calibre.drc/lvs` live 非阻塞用例（`calibre_e2e_tests.py`） |
| calibre#068 | `blocking=true` 时按 `poll_interval` 循环到 deadline | 真机 blocking 用例 + **P-098** 钉住超时口径 |
| calibre#151 | `checkCAPPERI=nil` / `.simrc` 一致性 | 真机 CDL 导出 + LVS 全链（`calibre.export_cdl` 11 个 live 调用点） |

**结论**：上表 17 条没有一条是"行为面无人验证"；**live 调用点已回填**进
`norm-review/g4-edit.json`、`g5-sim.json`、`g6-calibre.json` 的 `evidence`，
重跑 merge 后这些行的 `evidence_level` 已从 `offline` 升为 `live`（§0 数字随之更新）。

### 3.1 行为级且**无 live 承接** → 待补

当前为空（0 条）。若复算发现新增，直接追加到本节并同步 `round8-gap-actions.md`。

## 4. 复算命令

```powershell
python test/shared/runners/merge_round8_spec_matrix.py    # 重算 evidence_level 列
```

```python
# op 级：哪些 op 完全没有 live/semi 调用点
import json
cov = json.load(open('test/reports/round8/op-coverage.json', encoding='utf-8'))
print([k for k, v in cov.items()
       if not any(f.startswith(('test/live/', 'test/semi/')) for f in v['files'])])
# => ['calibre.export', 'calibre.pex']
```
