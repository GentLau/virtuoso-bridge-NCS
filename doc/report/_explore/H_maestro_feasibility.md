# Maestro 初版 spec 可行性调查（H）

> 日期：2026-09-18
> 对象：`spec/design-concepts/上层/6-maestro.md`（Draft v3 初版）
> 结论：全部能力均有 SKILL 路径。
> **2026-09-20 修订**：history 的 delete/rename 已由 [G_maestro_history_ops.md](G_maestro_history_ops.md) 查到公开 API，本文件原"不可行"结论作废。

## 1. 配置类

| 子项 | 可行性 | 依据 |
|---|---|---|
| get_var / get_parameter | ✅ | 旧 `writer.py:108/177`（maeGetVar / maeGetParameter） |
| 枚举 tests | ✅ | `axlGetTests`（SKILL 文档） |
| 枚举 corners | ✅ | `axlGetCorners`、`axlGetCornersForATest` |
| 枚举 specs | ✅ | `axlGetSpecs` |
| 枚举 vars | ✅ | `axlGetVars` |
| 枚举 analyses / outputs | ⚠️ | 未找到现成枚举函数，需用 `maeGetTestSession`/对象属性或暂缓 |
| 15 个配置写原子 | ✅ | 旧 `writer.py` 全部有对应实现 |

## 2. 结果类

| 子项 | 可行性 | 依据 |
|---|---|---|
| add_output / set_spec | ✅ | 旧 `writer.py:72/91` |
| read_results | ✅ | 旧 `reader/runs.py`（Detail CSV → points/spec/yield） |
| 单条波形 | ✅ | 旧 `reader/bundle.py` export_waveform |

## 3. 导出类

| kind | 可行性 | 依据 |
|---|---|---|
| netlist | ✅ | `maeCreateNetlistForCorner`（旧 writer.py:582） |
| script | ✅ | `maeWriteScript`（旧 writer.py:601） |
| outputs_csv | ✅ | `maeExportOutputView`（旧 writer.py:594） |
| snapshot | ✅ | 旧 `reader/snapshot.py`（sdb/state/filter/按点文件） |
| screenshot | ✅ | `hiWindowSaveImage` 对 Maestro 窗口；窗口按 `cellView~>viewName=="maestro"` 定位（与 schematic 同机制）；可先经展示类打开再截 |

## 4. 历史类

| 子项 | 可行性 | 依据 |
|---|---|---|
| 列出/当前/最新 history | ✅ | `axlGetHistory`、`axlGetCurrentHistory`、`axlGetRunStatus`；旧 session.py 的 mtime/自然排序 |
| 锁定 / 解锁 | ✅ | `axlSetHistoryLock`、`axlGetHistoryLock` |
| 复制 / 另存为 | ✅ | `axlLoadHistory`、`axlCommitSetupDBAndHistoryAs` |
| 覆盖式运行设置 | ✅ | `axlSetOverwriteHistory`、`axlSetOverwriteHistoryName` |
| 删除整条 history | ✅ | `axlRemoveElement(axlGetHistoryEntry(sdb, name))`（官方示例）；Explorer 另有 `maeDeleteExplorerHistory` |
| 删除部分数据 | ✅ | `maeDeleteSimulationData(hist, ?keepNetlist, ?keepQuickPlot)`，对应 GUI 三档；备选 `axlRemoveSimulationResults` |
| 重命名 | ✅ | `axlSetHistoryName(handle, newName)`（官方示例）；OCEAN XL 用 `ocnxlRenameCurrentHistory` |
| 复制（原地） | ⚠️→暂定 | 无"原地复制单条 history"API；只有 `axlLoadHistory` / `axlCommitSetupDBAndHistoryAs` / `maeImportHistory` |

## 5. 仿真类

| 子项 | 可行性 | 依据 |
|---|---|---|
| open_gui / close_gui | ✅ | 旧 lifecycle.py（窗口复用、Editing/Reading、save/promote） |
| run | ✅ | `maeRunSimulation`（旧 writer.py:338） |
| run_and_wait | ✅ | 旧 writer.py:491（callback marker 轮询） |

## 6. 展示类

| 子项 | 可行性 | 依据 |
|---|---|---|
| open/close waveform GUI | ✅ | 旧 `waveform_viewer.py`（maeOpenSetup→maeOpenResults→awvCreatePlotWindow→awvPlotWaveform；close 含校验） |

## 7. 内部中间节点

- 后台 open/save/ensure：✅（maeOpenSetup/maeSaveSetup）
- 窗口状态探测（mode/modified）：✅（旧 session.py `_fetch_window_state`）
- Detail CSV 中间导出：✅（maeExportOutputView）

## 8. 下一步

历史机制全部明确（含 delete/rename），无阻塞点；进入参数定稿前需闭环 `G_maestro_history_ops.md` §7 的真机验证清单。
