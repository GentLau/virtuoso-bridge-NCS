# Virtuoso 数据模型与原理图 / Testbench 编辑调研

> 调研日期：2026-09-04  
> 目标：回答“Virtuoso 如何管理数据，以及编辑原理图、编辑 TB 的较好方式是什么”。  
> 约定：**事实**来自本机 Cadence 文档、项目代码或现场只读验证；**建议**是面向 `virtuoso-bridge-NCS` 重构的设计判断。

## 1. 一句话模型

Virtuoso 的可编程边界可以抽象为：

```text
cds.lib / libList
        │  逻辑库名 → 文件系统库目录
        ▼
Library (ddId)
        ▼
Cell
        ▼
View / CellView
 ┌───────────────┬────────────────┬─────────────────┬─────────────────┐
 │ schematic     │ symbol         │ layout          │ config          │
 │ sch.oa        │ symbol.oa      │ layout.oa       │ expand.cfg      │
 └───────────────┴────────────────┴─────────────────┴─────────────────┘
                                      │
                                      ▼
                         maestro/{maestro.sdb, active.state}
                                      │
                                      ▼
                         results/maestro/{history}/...
```

这不是一个简单的“文件格式树”：

- **DD（Design Data）层**负责库、Cell、View、文件的解析、主文件/派生文件关系、访问权限和设计管理集成。
- **DB/DFII 层**负责对象、属性、拓扑关系、几何和 cellview 的内存表示。
- **应用层**（Composer/Schematic、Layout、Maestro、Spectre/OCEAN 等）在同一数据库上定义更高层语义。
- **运行工件层**保存 netlist、PSF、摘要和结果数据库；它们描述一次运行，不等同于设计源数据。

## 2. 数据所有权表

| 数据对象 | 典型磁盘位置 | 权威内容 | 推荐访问/修改方式 | 不能做什么 |
|---|---|---|---|---|
| 库映射 | `cds.lib`、`DEFINE`/`SOFTINCLUDE` | 逻辑库名、实际路径、参考库 | DD/库管理 API；必要时由受控工具更新 | 只改目录名而不更新映射 |
| Library 元数据 | `<LIB>/cdsinfo.tag`、库级 `data.dm` 等 | 库级属性与 DD 信息 | `ddGetObj`、库管理接口 | 把 `data.dm` 当文本编辑 |
| Schematic | `<CELL>/schematic/sch.oa` | 实例、terminal、net、wire、pin、属性、几何 | `dbOpenCellViewByType` + DFII/SKILL（`dbCreateInst`、`schCreateWire` 等） | `sed`/JSON/XML 工具直接改 `sch.oa` |
| Symbol | `<CELL>/symbol/symbol.oa` | 符号图形、端口语义、pin 顺序等 | `schSchemToPinList` + `schPinListToSymbol`，或 Symbol API | 只改图形、不更新端口语义 |
| Layout | `<CELL>/layout/layout.oa` | 图形、层、purpose、via、PCell 实例、物理连接 | Layout/SKILL API、PCell/ROD 语义 | 直接拼写 OA 二进制 |
| Config view | `<CELL>/config/expand.cfg` | 顶层 design、liblist、viewlist、stoplist、子 Cell binding | 文本编辑可行，但要关闭会话、备份、解析和重开验证；复杂复制优先配置/复制 API | 与 schematic 内容混淆 |
| Maestro setup | `<CELL>/maestro/maestro.sdb` | tests、DUT binding、corner、run mode、history 索引等 XML | `mae*`/`axl*` API；仅在 API 缺口时受控 XML 修改 | 只改 `maestro.sdb` 而不考虑 `active.state` |
| 当前 test 状态 | `<CELL>/maestro/active.state` | 每个 test 的 analyses、outputs、variables、设计信息等 XML | `mae*`/`axl*`；必要时 XML 事务修改 | 不同步 test 名称、输出编号和索引 |
| 运行结果 | `results/maestro/<history>/...`，以及 history 旁的 `.log/.rdb/.msg.db` | 某次 history/point/corner 的输入、模拟器输出、结果 | 只读下载、SQLite 查询、OCEAN/CSV 导出 | 当成新的设计源提交回 OA |
| 锁 | `*.cdslck`、`*.cdslck.<host>.<pid>` | 当前编辑声明和 Lock-Stake 信息 | 通过会话生命周期释放；仅确认无活动 owner 后清理 | 运行中盲删锁 |
| 设计管理状态 | GDM/SOS 或第三方 DM 工具的元数据、`master.tag`/`%` 标记 | checkout/checkin、co-managed files、版本 | GDM/DM 集成；复制时按其规则处理 | 把 source-controlled view 当普通可写目录复制 |

### 2.1 本机现场验证

在 2026-09-04 的只读探针中，当前桥接到的 Virtuoso 返回：

```text
getVersion()       → Virtuoso 6.1.8-64b（build 2023-10-11）
getVersion(t)      → IC6.1.8-64b.500.34
dbGetDatabaseType() → OpenAccess
```

现场库列表同时包含 PDK 库、`analogLib`/`basic` 和用户库；这说明**逻辑库名必须通过当前 Virtuoso 的 `libList` 解析**，不能从本地工作目录猜测。一个实际 Cell 的磁盘形态也验证为：

```text
<CELL>/schematic/sch.oa       # file(1) 为 data，OA magic 开头
<CELL>/schematic/data.dm      # 同样是二进制 data
<CELL>/schematic/master.tag   # 文本，指向 sch.oa
<CELL>/layout/layout.oa       # OA 二进制
<CELL>/maestro/maestro.sdb    # XML
<CELL>/maestro/active.state   # XML
```

## 3. DFII / OpenAccess 的底层语义

### 3.1 对象、属性、关系

本机 `skdfref/chap2.html` 的“Data Stored as Objects”说明：Cadence 工具使用 DFII 统一数据库，以对象保存矩形、terminal、instance、cellview 等概念；数据库同时保存物理信息（几何、layout）和逻辑信息（net、schematic）。当前可通过 `dbGetDatabaseType()` 区分 CDB 与 OpenAccess。

要点：

- `dbObject` 是由数据库例程创建的对象 ID，不是稳定的业务主键。
- 删除对象、关闭最后一个引用或 `dbPurge` 后，相关 ID 可能失效；Python 层不能把 `db:0x...` 当作跨请求长期缓存。
- 属性有数据库预定义的 **attribute**、应用添加的 **property**、以及只读的 **derived attribute**；`~>` 同时访问二者，但 attribute 优先。
- 数据库维护一部分关系，但应用必须正确创建另一部分关系。典型强关系是 terminal 必须连接到 net；任意“只改属性、不调用建模 API”的方案容易留下半合法状态。
- CDF 是应用语义层。对 PDK 器件，实例上看到的普通 property 不一定包含 W/L/nf/m 等有效值；应从 `cdfGetInstCDF(inst)` 读取 effective CDF，并使用相应 CDF callback/替换路径写回。

### 3.2 DD 文件与 master/co-master/derived

`ddGetObj` 文档把 Cell/View 下的文件分成：

- **master**：不可由工具无损重建的源文件；一个 View 通常只有一个 master，`master.tag` 可指出它。
- **co-master**：必须与 master 一起使用的配套源数据，例如多页 schematic 的索引/图形配套文件。
- **derived**：可由 master/co-master 重新生成的派生数据；访问派生文件时可能需要 master context。

DD 还支持 library 的临时目录（`TMP` 属性）：读时可能优先看临时目录，但 master/co-master 仍保存到 library，派生数据才写入临时树。**这解释了为什么“复制一个目录”不一定等于复制一个完整、可编辑、可复现的设计。**

### 3.3 访问模式和锁

`dbOpenCellViewByType` 的核心模式（已通过本机 API 文档核对）如下：

| 模式 | 行为 | 重构层建议 |
|---|---|---|
| `r` | 只读打开；必须已存在 | 所有 readback 默认使用；禁止隐式写入 |
| `a` | append；不存在则创建 | 增量修改的底层语义 |
| `w` | write；不存在则创建，已存在内容从内存中清除 | 只用于显式 replace/create，不要做默认值 |
| `s` | scratch；不能保存到磁盘 | dry-run、探测或临时转换 |
| `wc/wd/ac/ad/sc/sd` | 更细的 master/context 语义 | 第一版公共 API 不暴露，按场景封装 |
`dbSave` 保存 write/append cellview；`dbClose` 释放引用，引用数归零时可从虚拟内存 purge。官方文档明确建议关闭自己打开的 cellview，且 append/write 同时只能有一个用户。

`.cdslck` 的详细 Lock-Stake 文件包含 user、host、PID、创建时间、原因和路径。安全清理原则：

1. 先查 Virtuoso 活动进程、`maeGetSessions()`、`dbGetOpenCellViews()` 和锁 owner；
2. 正常关闭 session/cellview；
3. 只有在确认没有活动 owner 且确实是崩溃遗留后，才清理 stale lock；
4. 复制/打包时默认排除 `*.cdslck` 和 `*.cdslck.*`。

DFII 文档还指出 read mode 为升级、记账、分析等目的可能在内存中发生修改，但必须重新以 editable mode 打开才能保存。**因此“read-only 对象能被赋值”不能作为写入能力判断。**

## 4. 原理图编辑：推荐的分层方式

### 4.1 方法选择矩阵

| 任务 | 首选 | 备选 | 不推荐 |
|---|---|---|---|
| 读取拓扑/实例/CDF | `client.schematic.read(..., include_positions=...)` 或一次性 SKILL probe | 自定义只读 `.il` | 多次逐属性 round-trip |
| 新建 schematic | Python 结构化 request + `create`（底层 `w`） | 批量 `.il`/SKILL | 逐条 GUI 鼠标操作 |
| 增量修改 | `modify`（底层 `a`）+ context manager | 有边界的 SKILL batch | 默认用 `w` 覆盖 |
| 连两个已有 terminal | terminal-aware helper，读 DB 得坐标 | 明确的 `schCreateWire` | 猜 pin 坐标 |
| 连接同一网络但不要求视觉长线 | net label/stub | 真实 wire | 只依赖 instance property |
| PDK 器件参数 | CDF API/callback；封装成 typed operation | `schHiReplace` 对简单字符串/数值 | `inst~>prop` 硬改 |
| 生成 symbol | `schSchemToPinList` → `schPinListToSymbol` → 读回 | 手工 Symbol API | 只复制图形文件 |
| 复制并重排已有设计 | readback → Python planner → 新 Cell → readback verify | `ccpCopyDesign` 后局部修补 | 直接复制含锁/结果的目录 |
| 大量复杂逻辑 | 上传并 `load` 一个版本化 `.il` | 多个 execute_skill | 把复杂循环拆成上百次 RPC |

项目已有的三层抽象值得保留：

1. **Python domain API**：表达“放置 M0、把 D 接 OUT、设置 W=…”。
2. **SKILL operation builders**：把结构化操作编译成经过转义的 SKILL 字符串。
3. **Virtuoso execution**：一次批量提交，在 CIW/DFII 中真正创建对象。

### 4.2 标准写入流程

```text
预检（目标是否存在、是否被占用、PDK master/CDF 是否可用）
   ↓
read-before-write（拿到现状和稳定业务标识）
   ↓
构造纯 Python intent/plan（拓扑显式、位置规则显式）
   ↓
以 r/a/w 明确打开 cellview
   ↓
一次或少量批量 DFII/SKILL 操作
   ↓
schCheck（连接提取 + SRC/VIC，收集 error/warning）
   ↓
dbSave；dbClose；清理临时引用
   ↓
重新 r 打开并 readback，核对实例、master、方向、net、pin、参数
   ↓
生成 artifact manifest（before/after/hash/log）
```

`schCheck` 不只是语法检查：本机文档说明它可以做 connectivity extraction、schematic rules checker 和 cross-view checker，并返回 error/warning 总数；调用它需要对待检查的 cellview 有写权限。故应把 `schCheck` 当作写事务的 postcondition，而不是可选打印。

### 4.3 连接方式：wire、label 与 terminal-aware

`schCreateWire` 支持 `draw`/`route` 入口以及 `flight`/`direct`/`full` 等路由方法；`schCreateWireLabel` 可以把 label glue 到 wire/pin；`schCreatePin` 要求目标 schematic editable。

对 agent 自动化的建议：

- **电气意图优先**：先在内部模型中定义 `instance.term → net`，再决定视觉呈现。
- **跨远距离或不需要美观布线**：在 terminal 位置放短 stub + label，网络名是连接的主键；这比硬编码坐标稳健。
- **需要人读/审图/后续布局**：生成真实 wire，并将 route 作为显式约束或独立阶段，不要在“拓扑创建”阶段偷偷做全局布线。
- 使用 `add_wire_between_instance_terms`、`add_net_label_to_instance_term` 等 terminal-aware helper，从 DB 读取 pin center；不要假设 MOS 的 D/G/S/B 方向永远不变，PMOS、镜像和旋转会改变 stub 方向。
- 总线、继承连接（net expression/netSet）是独立语义，不要把 `BOT<0>`、`BOT\<0\>` 等字符串替换当作一般连接算法。

### 4.4 PDK/CDF 参数

`cdfGetInstCDF(inst)` 返回考虑了实例参数覆盖后的 effective CDF。项目已有经验表明，PDK MOS 的 W/L/nf/m 往往不在普通 `inst~>prop` 中；写入应调用 CDF 相关的 callback 或受控的 `schHiReplace` 路径，并在 readback 时再次读取 effective CDF。

建议为每个 PDK master 建立参数适配器：

```text
MasterAdapter
  ├─ resolve_super_master()
  ├─ list_effective_parameters()
  ├─ validate_value_and_unit()
  ├─ apply_with_cdf_callback()
  └─ readback_effective_value()
```

不同 PDK 的参数名、单位、CDF callback 和隐藏参数差异很大，不能做一个“所有器件通用的 dict→property”实现。

### 4.5 确定性规划与读回验证

项目的 `SchematicPlanRequest`/`SchematicPlanner` 是适合保留的边界：

- 输入显式给出 master、实例名、terminal-to-net、pin direction；
- 1.5 grid、NMOS/PMOS 行、差分对 `R0`/`MY`、pin column、output-stage offset 是规则，不是模型猜测；
- hard constraint 冲突在写入前报错；soft rule 放松要进入 diagnostics；
- 输入排序不应改变输出 plan；
- `verify_readback()` 必须核对 instance presence/master/position/orientation/connectivity/pin。

**非目标**仍应保持：拓扑推断、全局自动布线、从网名猜差分对、静默修复电气意图。重构时不要把 planner 变成第二个不可验证的 SKILL 解释器。

## 5. Symbol 与层次复制

### 5.1 Symbol 生成

本机 `schSchemToPinList` 文档定义了 pin list 的结构（ports、term name、direction、pins 和属性）；`schPinListToSymbol` 根据 pin list 生成 symbol cellview。工程上推荐：

```text
schematic readback
    ↓
schSchemToPinList(lib, cell, schematic)
    ↓
明确 pin 排序/方向策略
    ↓
schPinListToSymbol(lib, cell, symbol, pinList)
    ↓
打开 symbol 读回 terminal names/order/方向
```

生成后必须验证 symbol 端口与 schematic terminal 集合一致。若目标 symbol 已存在，先在关闭状态下做备份/冲突检查；不要触发需要人工点击的 replace dialog。

### 5.2 层次/配置复制

`config/expand.cfg` 的 `design`、`liblist`、`viewlist`、`stoplist` 和每个子 Cell binding 决定层次展开；config-less TB 也可能直接在 `maestro.sdb` 的 `<option>view` 里绑定 `schematic`。

复制策略：

- **同一技术库、同一层次，只改顶层 cell**：复制/重命名 API 后更新 binding，并用 `ccpExpandConfig`/读回验证展开结果。
- **跨库/跨 PDK**：先解析全部 master 和 technology binding，再做映射；不能只改 `design` 字符串。
- **源库受 SOS/GDM 管理**：识别 `master.tag` symlink、`%` 未 checkout 标记和只读权限，优先走 DM 操作；复制出的工作副本须明确其 source-of-truth。

Cadence 的 GDM 抽象了 checkout/checkin，并把 co-managed files 作为同步组处理；这说明版本管理应位于 DFII/DD 之上，而不是对 OA 文件逐个调用通用文件复制。

## 6. Testbench 编辑：拆成四个对象

### 6.1 DUT schematic

这是电气拓扑与 source/device 实例所在的 schematic view。用上一节的 DFII API 编辑；完成后 `schCheck + dbSave`，再交给 netlister。

### 6.2 Config view / hierarchy binding

这是“仿真时每个层次选择哪个 view”的绑定层。`expand.cfg` 是文本，便于 diff 和受控迁移，但修改前必须：关闭相关 session、保留原文件、解析文本语法、重开并确认展开到预期 view。

### 6.3 Maestro setup

`maestro.sdb` 和 `active.state` 的职责不同：

- `maestro.sdb`：active tests、test 的 lib/cell/view/simulator、corners、run mode、history 索引等；
- `active.state`：每个 test 的 designInfo、analysis fields、outputList、变量和更细粒度状态；
- `test_states/`：自动保存或用户保存的 test snapshot；
- `namedStimuli/`：数字 stimulus XML，不应被普通清理逻辑删除；
- `results/maestro`：运行结果和历史，不是 setup 本身。

首选 `mae*`/`axl*`：

```text
open session
  → create/set test
  → set analysis/options
  → add outputs/specs
  → set variables/corners/model files
  → maeSaveSetup
  → run
```

本机文档核对的常用函数包括：

- `maeOpenSetup`、`maeCreateTest`、`maeSetAnalysis`、`maeAddOutput`、`maeSetVar`；
- `maeSetCorner`、`axlGetMainSetupDB`/`axlGetCorner`/`axlPutModel` 等 corner 语义；
- `maeSaveSetup`、`maeRunSimulation`、`maeOpenResults`、`maeExportOutputView`；
- `maeGetSimulationMessages` 用于快速取得 ERROR/WARNING/INFO/ALL 文本；
- 旧版本缺少 `mae*` 时，用能力探测后选择 `asi*` fallback。

**不要把 XML 直接编辑当默认路径**。只有以下情况才考虑：

1. 当前版本没有对应 API；
2. API 已验证无法表达某字段；
3. 修改器实现了备份、临时文件、XML parse/validate、原子替换、重开、readback；
4. 变更范围很窄并且有 golden fixture。

项目已记录的例外是 pnoise jitter event：部分内部表格状态无法仅靠 SKILL API 持久化，必要时才对 `active.state` 做参考副本 + 路径替换，并在重开后验证 GUI/API 读回。

### 6.4 Read-only run、background session 与 edit mode 不是一回事

这是容易混淆的三个概念：

| 层次 | 典型入口 | 是否能运行 | 结果/保存语义 |
|---|---|---|---|
| CellView DB `r` | `dbOpenCellViewByType(... "r")` | 取决于上层应用 | 内存中的兼容性修改不能直接保存回原 view |
| Maestro GUI read-only | `deOpenCellView(... "r")` | ADE Assembler 的某些版本支持 | 可在 project/run 目录产生 `.RO` history；不会直接改 golden setup，之后可由 GUI 促进到 View History（需按版本验证） |
| Maestro background | `maeOpenSetup(...)` | 可以发起部分动作，但本项目观察到 callback/close/结果显示不可靠 | 适合 setup 读写和轻量探针；不作为可靠 simulation observer |
| Maestro GUI editing | GUI open + editable | 推荐的 bridge simulation path | 能保存 setup、加载/查看结果，但 edit lock 是独占的 |

Cadence 公开说明把 ADE 数据分为 setup、waveform/netlist、results database 三类，并指出 waveform/netlist 常落在 project directory，results database 默认在 maestro Lib/Cell/View（也可由 `saveDir` 覆盖）。这与本机现场看到的“project root 与 simulation/saveDir 两棵树”一致，但 `.RO`、`saveDir` 和具体 ISR 的行为必须现场确认。

**因此本文后续说“GUI session required”时，含义是：对本项目 bridge 的稳定运行、callback、结果观察和 GUI 展示，使用 `deOpenCellView`/`open_gui_session`；并不等同于强制把所有操作都改成 edit mode。**

### 6.5 运行工件与结果

Maestro 运行返回的 history 名称必须作为后续操作的显式关联键。不要用“当前窗口显示的 history”或简单字典序猜最新运行。对所有结果操作都带上：

```text
history + test + point + corner + run root
```

- 所有点 × 所有 output：优先 `maeExportOutputView(?view "Detail")` 导出 CSV，再解析；
- 单个已选点 scalar：`maeOpenResults` + `maeGetOutputValue`；
- waveform：OCEAN `openResults`/`selectResults`/`v`/`ocnPrint`，或受控的 PSF parser；
- netlist：`maeCreateNetlistForCorner` 后从远端 download；
- setup 复现：`maeWriteScript` 导出 SKILL script。

## 7. Maestro session 的正确生命周期

项目现有参考把 session 分为两种，调研结论如下：

| 场景 | 推荐 session | 原因 |
|---|---|---|
| 只读 setup / 轻量配置写入 | background `maeOpenSetup` | 不需要 GUI；可读写配置，但要成对关闭 |
| 真实运行、等待完成、在 GUI 显示结果 | GUI `deOpenCellView` / `open_gui_session` | callback 和结果面板行为可靠 |
| 关闭 GUI session | 关对应窗口；必要时先 `maeSaveSetup` | 对 GUI 打开的 session 直接 `maeCloseSession` 会触发 ASSEMBLER-8051 |
| 打开前清 stale internal cellviews | `dbPurgeCellView` 封装的 purge | 避免 ASSEMBLER-8127 |

推荐流程：

```python
client.maestro.purge_maestro_cellviews()
session = client.maestro.open_gui_session(lib, tb_cell)
# 修改 test / variables / analyses
client.maestro.save_setup(lib, tb_cell, session=session)
history, status = client.maestro.run_and_wait(session=session, timeout=600)
results = client.maestro.read_results(
    session, lib=lib, cell=tb_cell, history=history.strip('"')
)
client.maestro.close_gui_session(session, save=True)
```

重要约束：

- `maeSaveSetup` 必须先于 run，否则仿真可能使用旧参数；
- `maeRunSimulation(?waitUntilDone t)` 会阻塞整个 Virtuoso event loop；优先 `?callback`；
- `maeWaitUntilDone('All)` 虽然比 `?waitUntilDone t` 好，但仍占用 SKILL channel，不能作为远程观察器的唯一机制；
- 在调用 `maeMakeEditable()` 前先通过窗口标题识别 Reading/Editing 和尾部 `*`，避免 modal dialog 把 CIW 完全锁死。

## 8. 本项目应该固化的编辑契约

### 8.1 输入

- 所有写操作都用 `CellViewRef(lib, cell, view, view_type)`；
- 所有实例都用稳定业务键（hierarchical path/name），不跨请求保存 dbObject 指针；
- 所有 PDK master 都通过 capability/master adapter 解析；
- 每次写入指定 `intent_id`、用户/agent、目标、预期前置 hash（可选）。

### 8.2 输出

```text
OperationResult
  status: success | partial | conflict | validation_error | transport_error
  changed: bool
  diagnostics: [level, code, message, source]
  before_manifest
  after_manifest
  raw_skill / raw_xml (可选审计)
```

### 8.3 必须验证

- 打开模式与目标是否匹配；
- `schCheck` error/warning 分类；
- save/close 的返回值；
- readback 与 intent 的差异；
- 目标 library path、tech binding、PDK version；
- 是否产生 stale lock、空 `maestro.sdb`、残留临时文件。

## 9. 关键参考

### 项目内

- `../../skills/virtuoso/references/cellview-on-disk-layout.md`
- `../../skills/virtuoso/references/schematic-python-api.md`
- `../../skills/virtuoso/references/schematic-skill-api.md`
- `../../skills/virtuoso/references/schematic-recreation.md`
- `../../skills/virtuoso/references/maestro-python-api.md`
- `../../skills/virtuoso/references/maestro-skill-api.md`
- `../../skills/virtuoso/references/simulation-flow.md`
- `../../skills/virtuoso/references/netlist.md`
- `../../skills/virtuoso/references/library-python-api.md`
- `../../skills/virtuoso/references/symbol-python-api.md`
- `../../skills/virtuoso/references/troubleshooting.md`
- `../../skills/virtuoso/SKILL.md`
- `../../docs/adr/0001-explicit-remote-host-roles.md`
- `../../docs/adr/0002-deterministic-schematic-planner.md`

### Cadence 本地文档（IC6.1.8 安装树）

- `C:\Users\user\Desktop\doc\skdfref\chap2.html`：DFII 对象、属性/关系、CDB/OpenAccess
- `C:\Users\user\Desktop\doc\skdfref\cvio.html`：`dbOpenCellViewByType`、`dbSave`、`dbClose`、`dbPurge`
- `C:\Users\user\Desktop\doc\skdfref\connect.html`、`instance.html`：连接与实例
- `C:\Users\user\Desktop\doc\skcompref\chap2_re_schCreateWire.html`、`chap2_re_schCreatePin.html`：原理图操作
- `C:\Users\user\Desktop\doc\maeSKILLref\maestroSKILL.html`、`runRelated.html`、`jobPolicy.html`：Maestro setup/run/result
- `C:\Users\user\Desktop\doc\caiuser\chap8.html`：GDM

## 10. 证据定位（便于复核）

> 行号以本次调研时工作树和本机 HTML 文件为准；Cadence HTML 章节中的锚点名称比行号更稳定。

| 结论 | 证据 |
|---|---|
| DFII 是对象数据库，同时支持物理/逻辑数据；CDB 与 OpenAccess 可区分 | `C:\Users\user\Desktop\doc\skdfref\chap2.html:156-165`，锚点 `Data Stored as Objects` |
| `dbObject` 生命周期、关闭/purge 后 ID 失效 | `C:\Users\user\Desktop\doc\skdfref\chap2.html:277-285` |
| attribute/property/derived attribute 与关系语义 | `C:\Users\user\Desktop\doc\skdfref\chap2.html:331-368`、`:397-407` |
| `dbOpenCellViewByType` 的 view type 与 r/a/w/s 模式 | `C:\Users\user\Desktop\doc\skdfref\cvio.html:2375-2454`、`:2474-2495` |
| `dbClose` 的引用计数、并发写限制 | `C:\Users\user\Desktop\doc\skdfref\cvio.html:414-432` |
| GDM 处理 co-managed library structure、checkout/checkin | `C:\Users\user\Desktop\doc\caiuser\chap8.html:119-176`；函数索引 `gdmco/gdmci/gdmstatus` |
| Virtuoso 现场为 IC6.1.8/OpenAccess | 只读命令 `getVersion()`、`getVersion(t)`、`dbGetDatabaseType()`；详细记录见 `00-research-method-and-evidence.md` |
| OA/XML/lock 文件的实际布局与可编辑边界 | `../../skills/virtuoso/references/cellview-on-disk-layout.md:8-107`、`:200-282` |
| 原理图 create/modify、batch、schCheck/save、planner/readback | `../../skills/virtuoso/references/schematic-python-api.md:13-114`、`:116-175`；`../../skills/virtuoso/references/schematic-skill-api.md:3-60` |
| Maestro background/GUI session 与 run 约束 | `../../skills/virtuoso/references/maestro-python-api.md:17-45`；`../../skills/virtuoso/references/simulation-flow.md:1-74`、`:100-156` |
| Maestro XML 文件职责、sidecar 与结果树 | `../../skills/virtuoso/references/cellview-on-disk-layout.md:90-155` |
| pnoise jitter 的 XML fallback 限制 | `../../skills/virtuoso/references/maestro-skill-api.md:449-503` |

### 公开交叉参考

- [Cadence Virtuosity：Virtuoso Read Mode Done Right](https://community.cadence.com/cadence_blogs_8/b/cic/posts/virtuosity-read-mode-done-right)：关于 setup、waveform/netlist、results DB 的三类数据以及 ADE Assembler read-only `.RO` history 的公开说明。

### 4.2.1 最小 schematic 代码骨架（示意）

以下代码只展示推荐的调用边界；真正运行前仍要根据目标 PDK 查询 master、terminal 名和 CDF。代码来自项目已有 API 约定，研究阶段没有对现场库执行写入：

```python
from virtuoso_bridge.virtuoso.schematic import (
    schematic_create_inst_by_master_name as inst,
    schematic_create_pin as pin,
    schematic_create_wire_between_instance_terms as wire,
)

# 新建/显式替换：create；增量修改：modify
with client.schematic.create("WORK", "tb_demo") as sch:
    sch.add(inst("analogLib", "vdc", "symbol", "V0", 0, 0, "R0"))
    sch.add(wire("V0", "PLUS", "R0", "PLUS"))
    sch.add(pin("OUT", 3.0, 0.5, "R0", direction="output"))
    # 退出时：批量执行 → schCheck → dbSave

# 重新只读读回，做语义验证
actual = client.schematic.read("WORK", "tb_demo", include_positions=True)
```

实现层需要保证：`create` 使用显式 write 语义，`modify` 使用 append 语义；context manager 不能在 Python 异常时把半成品静默保存；读回失败要返回 before/after 证据。

### 5.3 版本管理边界：GDM/DM 与 Git 如何配合

Cadence 的 GDM 并不是另一种 OA 文件格式，而是让 CAD 应用通过统一接口调用不同设计管理系统的适配层；它知道 workarea、repository、version 和 co-managed set。由此建议：

| 层 | 推荐纳入 Git/制品库的内容 | 说明 |
|---|---|---|
| 意图层 | Python/JSON/SKILL 生成脚本、PDK adapter、planner request | 可审阅、可重放、可做 code review |
| 语义快照层 | schematic/topology/CDF/tech binding 的规范化 JSON、Maestro 过滤 XML、manifest | 用于 diff、回归和 AI 上下文 |
| 设计源层 | OA/DFII cellview 的受控快照或发布包 | 不在多个分支间做二进制三方合并；发布时由 Cadence/DM 流程产生 |
| 运行层 | `.log`、`.msg.db`、`rdb`、netlist、PSF、诊断报告 | 按 retention 保留，默认不污染设计源分支 |
| PDK 层 | 版本/路径/hash/许可信息，不复制受限 PDK | 由部署环境提供，manifest 记录依赖 |

如果现场使用 GDM/SOS 或其他 DM 系统，自动化器应先查询 managed/checkout 状态，再决定是否能写；不能把 `chmod` 或删除 `%` 文件当成通用 checkout。没有 DM 系统的个人实验库也应遵守同样的**单 writer + 新 Cell/备份 + 语义快照**规则。
