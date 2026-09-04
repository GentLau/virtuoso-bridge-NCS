# 调研方法与现场证据记录

> 记录时间：2026-09-04  线程：`virtuoso-bridge-NCS`  
> 本文件只记录只读检查；没有向设计库提交写操作。

## 1. 使用的资料面

| 资料面 | 入口 | 用途 |
|---|---|---|
| Cadence 函数索引 | `http://127.0.0.1:8123/api/find` | 查函数存在性、签名、简短描述 |
| Cadence More Info | `http://127.0.0.1:8123/api/info` | 读取详细 API 语义和示例 |
| Cadence 原始 HTML | `C:\Users\user\Desktop\doc` | 核对章节、版本和上下文 |
| 项目参考 | `skills/`、`README.md`、`AGENTS.md` | 了解既有封装和已知坑 |
| 现场 Virtuoso | `tools/skill_exec.py --port 65082` | 验证版本、数据库类型、库/session/结果路径 |
| 现场文件树 | SSH 到配置的 EDA 主机 | 验证实际 OA/XML/SQLite/log 布局 |

服务统计（`GET /api/stats`）：

```json
{
  "doc_root": "C:\\Users\\user\\Desktop\\doc",
  "total": 9503
}
```

## 2. 关键 API 交叉核对

### DFII / cellview

```text
dbGetDatabaseType
 dbOpenCellViewByType
dbSave
dbClose
dbPurge
ddGetObj
ddGetLibList
dbCreateInst
dbCreateParamInst
dbCreateNet
dbCreateTerm
dbCreatePin
dbReplaceProp
```

### Schematic / CDF / symbol

```text
schCreateWire
schCreateWireLabel
schCreatePin
schCheck
cdfGetInstCDF
schSchemToPinList
schPinListToSymbol
schHiReplace
```

### Maestro / results

```text
maeOpenSetup
maeCreateTest
maeSetAnalysis
maeSetVar
maeAddOutput
maeSaveSetup
maeRunSimulation
maeWaitUntilDone
maeGetSimulationMessages
maeOpenResults
maeGetOutputValue
maeExportOutputView
asiGetAnalogRunDir
axlGetCurrentHistory
axlGetHistoryName
axlGetHistoryResults
```

### IPC / 文件输出

```text
ipcBeginProcess
ipcReadProcess
ipcWait
ipcGetExitStatus
ipcIsAliveProcess
ipcWriteProcess
ipcActivateBatch
ipcActivateMessages
outfile
fprintf
close
```

## 3. 现场运行结果

通过 `tools/skill_exec.py` 只读执行：

```text
getVersion()        → "@(#)$CDS: virtuoso version 6.1.8-64b ...$"
getVersion(t)       → "sub-version  IC6.1.8-64b.500.34"
dbGetDatabaseType() → "OpenAccess"
maeGetSessions()    → ("fnxSession8" "fnxSession10")
```

当前会话的一个结果路径探针返回：

```text
asiGetAnalogRunDir(asiGetSession("fnxSession8"))
→ <simulation-root>/SERDES_TB_LIB/tb_serdes_rx_top/maestro/results/maestro/
   .tmpADEDir_Gent/serdes_top_tran/...
```

`axlGetHistoryName(axlGetCurrentHistory("fnxSession8"))` 和
`axlGetHistoryResults(...)` 的现场结果为：

```text
history → Interactive.0
rdb     → <project>/SERDES_TB_LIB/tb_serdes_rx_top/maestro/results/maestro/Interactive.0.rdb
```

这些结果说明：

1. `history`、RDB、模拟器 run directory 不是同一个路径概念；
2. 当前 GUI/后台 session 的状态可能不同；
3. 结果采集器必须保留运行时返回的路径，不能只拼库目录。

## 4. 现场文件与 SQLite 证据

对一个已有 Maestro history 的只读检查：

```text
<project>/<LIB>/<TB>/maestro/maestro.sdb       XML，约 83 KB
<project>/<LIB>/<TB>/maestro/active.state      XML，约 303 KB
<project>/<LIB>/<TB>/maestro/results/maestro/
    Interactive.N.log                           数百字节
    Interactive.N.msg.db                        SQLite，约 49 KB
    Interactive.N.rdb                           SQLite，约 536 KB

<simulation-root>/<LIB>/<TB>/maestro/results/maestro/Interactive.N/
    1/<TEST>/netlist/input.scs
    1/<TEST>/netlist/runSimulation
    1/<TEST>/psf/spectre.out
```

现场 `*.msg.db` 的核心 schema：

```sql
CREATE TABLE logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  jobid TEXT,
  point TEXT,
  test TEXT,
  level TEXT,
  tool TEXT,
  timestamp TEXT,
  message TEXT,
  attrs TEXT
);
CREATE TABLE location (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  point TEXT,
  test TEXT,
  tool TEXT,
  file TEXT,
  line TEXT,
  UNIQUE(point, test, tool)
);
```

现场同一 history 的 `spectre.out` 命令行包含 `+log ../psf/spectre.out`、`-raw ../psf` 和 `+logstatus`，末尾包含 simulator error/fatal 汇总。`Interactive.N.log` 只包含 history 摘要。这是本研究把 `msg.db + spectre.out + orchestration log` 定为组合证据源的直接依据。

## 5. 当前工作树注意事项

初始检查时发现：

- `src/virtuoso_bridge/` 有大量预先存在的删除变更；
- `src_bak/` 保存了旧实现；
- `spec/`、`tools/skill_doc_server.py` 等为未跟踪内容；
- `.venv` 存在，但当前工作树的 Python 包因已删除模块不能正常 import。

本次调研只新增/写入 `spec/research/` 文档，没有恢复源码、删除文件、修改远端设计库或清理锁文件。

## 6. 复核原则

后续实现若与本文冲突，应按以下优先级复核：

1. 当前安装的 Cadence More Info/函数签名；
2. 对目标 IC/ISR/PDK 的现场最小实验；
3. 项目中带测试和 readback 的实现；
4. 本文中的建议和其他版本经验。

不要因为某个函数在文档索引中存在，就假定它在所有 ADE 类型、session mode 或 PDK 中拥有相同语义；把差异记录到 capability matrix。

## 7. 本轮补充的同步日志捕获证据

2026-09-04 在端口 `65081` 的 IC6.1.8/OpenAccess 会话中，以唯一前缀执行了不涉及设计库写入的表达式探针：

```text
printf("...")                           → RPC 返回 t；消息出现在 CDS.log 的 \o 行
warn("...")                              → RPC 返回 nil；warning 进入 warning channel/CDS.log
outstring + 动态 poport + printf/info      → getOutstring() 返回捕获文本
muffleWarnings(warn(...) warn(...))        → getMuffleWarnings() 返回多个 warning
muffleWarnings(C-level warning)            → getMuffleWarnings() 返回 ADEXL-8067 文本
errset(sqrt(quote(x)))                     → errset.errset 返回函数/位置/错误文本列表
hiPrintToLogFile("...")                   → 写 CDS.log，不进入 outstring
hiStartLog(/tmp/...) ... hiEndLog()        → 生成 ancillary transaction log
```

本轮探针还验证了：

- `getWarn()` 适合拦截尚未打印的单个 warning，但多 warning 场景应使用 `getMuffleWarnings()`；
- `hiGetLogFileName()` 返回当前 session 的实际日志路径 `/home/Gent/CDS.log`；
- `hiFlushLogFile()` 在当前会话返回 `t`；
- 当前 `Interactive.0.msg.db` 的 `logs.id` 可作为增量游标，`meta` 中有 `version=1`；
- 远端 SQLite `sqlite3 .backup` + `pragma integrity_check` 成功建立了一致性副本（仅对研究用副本操作）。

## 8. 本轮形成的设计判断

1. 同步 `printf`/warning/error 应在 SKILL wrapper 中捕获，不能通过事后扫描整个 `CDS.log` 替代。
2. `CDS.log` 只做 session 级补充证据；需要关联时使用 `hiPrintToLogFile` marker + byte cursor，并显式标记 best-effort。
3. Maestro/Spectre 长任务必须采用 callback/status/log-tail/artifact 的异步 observer，不能把所有内容塞进单次 TCP response。
4. 对外返回应是 control result + normalized events + artifact references 三部分，且保留旧 `VirtuosoResult.output` 语义。

本轮详细方案见 [`04-log-return-system-proposal.md`](04-log-return-system-proposal.md)。
