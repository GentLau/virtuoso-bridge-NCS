# 公共约定

本节是**所有业务操作共用**的字段与形态说明；各操作小节只写自己特有的参数，不再重复这里的内容。

## 公共约定

### 请求形态

所有业务操作都是同一个 HTTP 调用：

```json
{"operation":"<业务操作名>","token":"TOKEN", "...参数名":"...参数值"}
```

发往业务面的 `POST /api/operation`；`Content-Type: application/json`。
不知道有哪些操作：`GET /help/operations`（清单）或 `GET /help/operations?name=<操作名>`（详情）。

### 公共参数（每个操作都可带）

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `token` | str | ✅ | — | 每次调用都要带，值就是注册时确定的 token |
| `timeout` | 数字 | — | `30` | 端到端超时（秒）。长任务（跑仿真、结构导入、GDS 导出）建议显式给大 |
| `step_details` | bool | — | `false` | `true` 时成功响应里也带上 `steps`（默认只有失败才带） |
| `log_level` | str | — | 注册表默认 | 本次调用采集 CDS.log 的级别（`off`/`all`/`warn`/`error`）。只对会执行 SKILL 的操作有效 |
| `log_max_bytes` | int | — | 注册表默认 | 本次调用 CDS.log 的长度上限（字节）。同上，只对执行 SKILL 的操作有效 |

支持 `log_level`/`log_max_bytes` 的操作：所有 `virtuoso.*` 包的操作，以及 `basic.skill.execute`。

### 响应壳

```json
{"ok": true, "data": {"ok": true, "error": null, "value": {}}, "error": null}
```

| 字段 | 说明 |
|---|---|
| 外层 `ok` | 请求是否被受理；`false` 时看外层 `error`（400 参数错 / 404 未知操作 / 429 太忙…） |
| `data.ok` | 业务是否成功 |
| `data.error` | 失败摘要（成功为 `null`） |
| `data.steps` | 过程痕迹，**默认只在失败时出现**；`step_details=true` 时成功也带。每项 `{"name","ok","detail"}`，`detail` 里有命令 `stdout/stderr`、`returncode`、`kind`、SKILL 返回等原始证据 |

### 业务数据放在哪

| 情况 | 位置 |
|---|---|
| 多数包（cellview / schematic / symbol / layout / maestro / verilog / veriloga / spectre / calibre） | `data.value` |
| `basic.*` | `data.result`（SKILL 结果的日志键是 `CDSlog`） |
| 截屏：schematic / gui | `data.local_path` |
| 截屏：symbol / layout | `data.value.local_path` |
| `virtuoso.skillref.*` | `data.results` / `data.plain_text` 等专用字段 |

### 命令类结果的 `kind`

命令类结果（`basic.command.run` 等）里 `kind` 比 `returncode` 更可靠——只有 `kind=command` 时 `returncode`
才是命令自己的退出码：

| kind | 含义 | 保留码 |
|---|---|---|
| `command` | 真实命令执行完毕 | 命令自身退出码 |
| `timeout` | 超时 | 124 |
| `transport` | 建连/断连等传输失败 | 255 |
| `path` | 路径不可见/类型不符（`stderr` 含 `VB-PATH-NOT-VISIBLE:`） | ≠0 |
| `unknown-effect` | 结果未知，**可能已产生副作用** | 255 |
| `rejected` | 容量拒绝（线程/通道/角色会话数超限） | 1 |
| `checksum` | 文件校验和不一致（`sha256 mismatch`） | 1 |
| `invalid-token` | token 不认识 | 1 |

### 路径

- `local_path`：**调用方（你本机）**的路径；
- 其它路径（`remote_path`、网表、GDS、日志…）：**目标机器**上的路径，Linux 风格；
- 相对路径按对应角色的根目录解析，绝对路径原样使用；
- 本机文件要先传过去（`basic.file.upload`），远端产物要取回来用 `basic.file.download`。

### 示例的写法

各操作小节里的示例给两段：`// 输入` 是可直接发送的请求体，`// 输出` 是成功响应的 `data` 内容
（完整响应外面还有一层壳 `{"ok": true, "data": <输出>, "error": null}`）。
示例里以 `//` 开头的行只是标注，**复制时删掉**。
