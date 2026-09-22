# Maestro 改动梳理报告

> 日期：2026-09-18
> 目的：把旧 Maestro 能力到新业务包的每处改动拆成可逐个讨论的决策节点。
> 对象：`spec/design-concepts/上层/6-maestro.md`（Draft v4，参数待逐项定稿）

## 0. 旧功能 → 新提案总览

| 旧编号 | 旧功能 | 去向 | 说明 |
|---|---|---|---|
| M1 | 后台会话 open/close | **write 内部中间节点** | 不对外，open/close 作为 write 的公共步骤 |
| M2 | GUI 会话 open/reuse/close | **open_gui / close_gui** | close 固定保存，Reading 先 promote |
| M3 | 确保 maestro view 存在 | **对外删除，内部包含** | `maeOpenSetup + maeSaveSetup` 由 write/open_gui 自动执行 |
| M4 | 读焦点会话 | **对外删除，内部包含** | close_gui 固定保存，内部探测 mode 后 promote+save |
| M5 | 全量快照 | **export** | kind=snapshot |
| M6 | test/analysis 配置 | **write** | 配置原子；其中 output/spec 归结果写 |
| M7 | 变量/参数 | **write** | 配置原子 |
| M8 | 环境/仿真选项 | **write** | 配置原子 |
| M9 | corner | **write** | 配置原子 |
| M10 | run mode/job policy | **write** | 配置原子 |
| M11 | 异步启动仿真 | **run** | maeRunSimulation |
| M12 | 启动并等待 | **run_and_wait** | 回调 marker + 轮询 |
| M13 | 导出网表/setup/结果 | **export**（部分进 read_results 内部） | kind=netlist/script/outputs_csv |
| M14 | 读结果点/spec/yield | **read_results** | |
| M15 | 导出 OCEAN 波形 | **read_results** | 单条波形 |
| M16 | 交互波形查看器 | **open_waveform_gui / close_waveform_gui** | 展示类，给人看 |
| M17 | 仿真器模式 | **write** | 配置原子 |
| — | history 管理（旧包未实现） | **read_history / write_history** | 删/改/锁均有 SKILL；复制不做 |

## 新章节分类（大类 → 子类）

| 大类 | 子类 | 对外操作 | 包含旧功能 |
|---|---|---|---|
| 配置类 | 配置读 | `read_config` | get_var / get_parameter（+配置枚举，新聚合，暂定） |
| 配置类 | 配置写 | `write(commands[])` 配置原子 | M6 test/design/analysis、M7 var/param、M8 env/sim option、M9 corner、M10 run mode/job policy、M17 simulator mode |
| 结果类 | 结果写 | `write(commands[])` 结果原子 | M6 add_output / set_spec |
| 结果类 | 结果读 | `read_results` | M14、M15 |
| 导出类 | 导出 | `export(kind=netlist/script/outputs_csv/snapshot/screenshot)` | M5、M13；screenshot 给 agent，可先经展示类打开再截 |
| 历史类 | 历史读 | `read_history` | `axlGetHistory` / `axlGetCurrentHistory` / `axlGetRunStatus` / `axlGetHistoryLock` |
| 历史类 | 历史写 | `write_history(commands[])` | delete `axlRemoveElement(axlGetHistoryEntry)`；delete_results `maeDeleteSimulationData`；rename `axlSetHistoryName`；lock `maeSetHistoryLock`。复制按需求**不做** |
| 仿真类 | GUI 开关 | `open_gui` / `close_gui` | M2（M4 为 close_gui 内部） |
| 仿真类 | 仿真启动 | `run` / `run_and_wait` | M11、M12 |
| 展示类 | 给人类看 | `open_waveform_gui / close_waveform_gui` | M16；展示类不做截图，截图属导出类 |

## write 去向展开（配置类，M6–M10、M17）

`write(commands[])` 的配置原子，每个原子 = op + 索引 + 附加参数。

内部公共步骤（不对外）：

- open：`maeOpenSetup(lib cell "maestro")` 打开后台会话；
- close：`maeCloseSession` 关闭并保存；
- 每个 `write` 调用 = open → 逐原子执行 → close，调用方无会话概念。



| 原子 | 旧函数 | 索引（动哪个） | 附加参数 | 备注 |
|---|---|---|---|---|
| set_test | `maeCreateTest` | `test` | lib, cell, view="schematic", simulator="spectre" | |
| set_design | `maeSetDesign` | `test` | lib, cell, view="schematic" | 改 DUT |
| set_analysis | `maeSetAnalysis` | `test` | analysis, enable?, options? | options 暂定字符串 |
| add_output | `maeAddOutput` | `test` | name, output_type?, signal_name?, expr? | |
| set_spec | `maeSetSpec` | `test` | name, lt?, gt? | |
| set_var | `maeSetVar` | `name` | value, scope?(test/corner) | |
| get_var | `maeGetVar` | `name` | — | 读配置，归属待议 |
| delete_var | `axlRemoveElement` | `name` | test? | |
| set_parameter | `maeSetParameter` | `name` | value, scope? | |
| get_parameter | `maeGetParameter` | `name` | — | 读配置，归属待议 |
| set_env_option | `maeSetEnvOption` | `test` | options | |
| set_sim_option | `maeSetSimOption` | `test` | options | |
| set_corner | `maeSetCorner` | `name` | disable_tests? | 只建空 corner |
| setup_corner | `maeSetCorner + maeSetVar + axl*` | `name` | model_file?, model_section?, variables? | 完整 corner |
| load_corners | `maeLoadCorners` | —（文件导入） | filepath, sections?, operation? | CSV 上传 |
| set_run_mode | `maeSetCurrentRunMode` | —（会话级） | run_mode | 索引待议 |
| set_job_control_mode | `maeSetJobControlMode` | —（会话级） | mode | 索引待议 |
| set_job_policy | `maeSetJobPolicy` | test? | policy, job_type? | |
| set_simulator_mode | `asiSetHighPerformanceOptionVal` | `test` | mode（内部映射 uniMode/preset） | |

待议：

1. get_var/get_parameter 归 read 操作还是允许 write 内读；
2. options 保持 SKILL alist 字符串还是结构化；
3. 会话级原子（run_mode/job_control）的索引；
4. load_corners 的 CSV role/路径；
5. set_corner 与 setup_corner 是否合并。

## 决策节点

### 节点 1：GUI 会话是否保留 open/close

- 提案：保留 `open_gui` / `close_gui` 两个操作。
- 问题：`close_gui` 的保存/丢弃语义是否要参数（save=True/False）；GUI 窗口复用还是强制新开。

### 节点 2：后台会话不对外暴露

- 提案：删除 M1 的 open/close；所有读写操作内部 `maeOpenSetup` + 完成后 `maeCloseSession`。
- 问题：内部打开/关闭的会话名/冲突怎么处理；读写频繁时反复开/关的开销是否接受。

### 节点 3：ensure view 归 cellview

- 提案：`cellview.view.create(lib, cell, "maestro", view_type="maestro")` 通用承担；maestro 不特化。
- 问题：cellview 包当前 view.create 是否支持非 schematic 的 view_type（需要确认 `dbOpenCellViewByType` 用法），若需要"存在则跳过"是否加 ensure 语义。

### 节点 4：read_focused

- 提案：读当前焦点窗口会话元数据。
- 问题：是否保留"当前焦点"这种隐式目标，还是改为显式 lib/cell。

### 节点 5：snapshot

- 提案：保留全量快照。
- 问题：`snapshot_filter.yaml` 过滤资产怎么随包分发；快照输出的粒度（raw XML / SKILL 段 / 按点文件）是否照旧。

### 节点 6–10、17：配置原子命令

- 提案：`write(commands[])` 收拢 12 个原子。
- 问题：每个原子参数怎么设计（SKILL alist 直接透传还是结构化字段）；是否支持一次 write 里同一原子重复出现。

### 节点 11：run 异步启动

- 提案：`run` 返回 history 名。
- 问题：是否要可选 callback；history 名缺省自动。

### 节点 12：run_and_wait 长任务

- 提案：保留同步等待。
- 问题：marker 轮询形态（旧代码 shell cat /tmp marker）怎么在新五接口下实现；deadline 与轮询间隔；是否需要拆 start + poll。

### 节点 13：export_netlist / 结果导出

- 提案：`export_netlist` 保留；结果导出并入 `read_results`。
- 问题：远端文件写哪个 role；下载粒度（单文件/目录）。

### 节点 14：read_results

- 提案：Detail CSV → 结构化 points/spec/yield。
- 问题：CSV 解析规则是否照旧；spec/yield 查询放这里还是独立。

### 节点 15：export_waveform

- 提案：单条 OCEAN 文本波形导出。
- 问题：表达式、analysis/history/format 参数集。

### 节点 16：waveform_viewer

- 提案：GUI 打开/画图/关闭保留为一个操作。
- 问题：GUI 交互操作是否拆 open/plot/close；是否与 `open_gui` 合并。

## 建议讨论顺序

节点 3（归属）→ 节点 2（会话）→ 节点 6–10/17（配置收拢）→ 节点 11/12（运行）→ 节点 4/5/13/14/15（读取）→ 节点 16（GUI）。

每个节点确认后，我同步改 `6-maestro.md` 一处，不大面积重写。
