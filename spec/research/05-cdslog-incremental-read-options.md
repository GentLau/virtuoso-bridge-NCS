# CDS.log 增量获取：API 调研结论与实时跟随方案

> 2026-09-09 · 只回答一个问题：Cadence 有没有“读取 CDS.log 增量”的接口，以及如何让日志跟随 daemon 执行链条实时返回。

## 1. 结论：没有读取接口，只有“路径 + flush + 追加”钩子

对本地 IC6.1.8 文档索引（9503 个函数）全量检索后确认：**Cadence 没有公开 SKILL 接口能读取 CDS.log 的内容或增量。**

官方“Log File Functions”公开列表只有：

| 函数 | 作用 | 是否读取日志内容 |
|---|---|---|
| `hiGetLogFileName()` | 返回当前 session log 的绝对路径 | 否 |
| `hiFlushLogFile()` | 刷新主 log 和 secondary log | 否 |
| `hiPrintToLogFile()` | 追加一行到 log（不显示到 CIW） | 否（只写） |
| `hiStartLog()` / `hiEndLog()` | 建立/停止一个 secondary transaction log | 否（只写） |
| `hiIsInReplay()` / `hiReplayFile()` | replay 状态/回放 | 否 |
| `hiSetFilter()` / `hiSetFilterOptions()` | CIW 显示过滤 | 否 |

证据：`C:\Users\user\Desktop\doc\skuiref\chap2.html:3057-3072`；finder 中所有 `hi*log*`、`asi*log*` 函数名均无读取类 API。

所以：**增量内容本身只能靠文件读取。** Cadence 真正提供的是三个关键钩子：

```text
hiGetLogFileName()    → 让 daemon 知道该 tail 哪个文件
hiFlushLogFile()      → 让缓冲内容及时落盘
hiPrintToLogFile()    → 让 daemon 往 CDS.log 写可识别的边界标记
```

## 2. 实测：文件跟随在 SKILL 执行期间就能拿到增量

现场验证：在**同一条长时间执行的 SKILL** 中写入标记并 flush：

```skill
progn(
  hiPrintToLogFile("VB_REALTIME_xxx_A") hiFlushLogFile()
  ipcSleep(3)
  hiPrintToLogFile("VB_REALTIME_xxx_B") hiFlushLogFile()
  ipcSleep(3)
  hiPrintToLogFile("VB_REALTIME_xxx_C") hiFlushLogFile()
  1
)
```

执行期间由客户端每 0.5s `ssh grep` 观察 CDS.log，结果：

```text
t=0.5s  A 已出现
t=1.5s  A、B 已出现
t=2.5s  A、B、C 已出现
```

结论：**只要执行链条中的 SKILL 在进度点调用 `hiFlushLogFile()`，文件侧 tail 就能实时看到。** 不需要新协议，不需要把日志塞进 TCP。

## 3. 三个简单方案

### 方案 A：请求边界增量（最推荐，先做）

每次 execute 由 SKILL wrapper 完成：

```skill
hiGetLogFileName()
hiFlushLogFile()
before = fileLength(path)

hiPrintToLogFile("VB-BEGIN <request_id>")
执行用户 SKILL
hiPrintToLogFile("VB-END <request_id>")
hiFlushLogFile()
after = fileLength(path)
```

响应把 `path / before / after` 一并返回；Python 侧用 SSH/SFTP 读取 `[before, after)`。

```text
特点：一条请求一条增量，实现最简单，失败也返回 partial delta
```

### 方案 B：side tail 实时跟随

客户端记录起始 offset，请求发出后单独线程按 0.2–0.5s 轮询：

```text
读取 [cursor, 当前文件长度)
```

为了让日志在执行期间出现，daemon 在它编排的**每个操作步骤之间**插入一次 `hiFlushLogFile()`：

```text
step1 → flush → step2 → flush → step3 → flush
```

```text
特点：真正“执行到哪就看到哪”；不侵入用户 SKILL 正文，只改 wrapper
```

### 方案 C：专用 daemon 事件文件

如果不想和 `CDS.log`（人工操作、ADE 后台线程会混入）耦合：

```skill
outfile(operation_log) ; fprintf(...) ; drain()
```

SKILL 每个步骤把进度写到专属文件，客户端 tail 这个文件。

```text
特点：关联 100% 干净，但要自己管理文件生命周期
```

## 4. 推荐落地顺序

```text
第一步：A —— 每次 execute 自动带回 CDS.log 增量（改动集中在 wrapper + 一个 reader）
第二步：B —— wrapper 在步骤间加 flush，让增量在执行过程中实时可见
第三步：C —— 需要严格隔离时，为每个 operation 建专用 event 文件
```

一句话：**Cadence 没有读日志的 API，但给了“路径、flush、写标记”三个钩子；实时跟随 = 执行链条负责 flush 落盘，客户端负责按字节 tail 文件。**
