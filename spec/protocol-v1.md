# 跨层接口协议 v1

只定义三条接口格式，不定义高层业务 API。

```text
高层 ──Python──> 中层 ──TCP/JSON──> daemon.py ──ipcBeginProcess──> SKILL
```

| 边界 | 格式 | 负责内容 |
|---|---|---|
| 高层 ↔ 中层 | Python 接口 | Skill / RunCommand / File |
| 中层 ↔ daemon.py | TCP；JSON + EOF | 只传 Skill |
| daemon.py ↔ SKILL | IPC；文本行 + `STX/NAK/RS` | CIW 求值 |

**daemon.py 不执行命令行，也不处理文件。**

## 1. 高层 ↔ 中层

### 建立会话

```python
session = middle.bind(token)
```

`token` 只在 `bind()` 传一次；session 固定用户和路由。高层不传 host、port、SSH、
tunnel、profile 或 daemon 地址。

### 三个能力

```python
class BusinessSession(Protocol):
    # Skill：发送到 Virtuoso CIW
    def execute_skill(
        self, skill: str, *, timeout_ms: int = 30_000
    ) -> Result[SkillData]: ...

    # RunCommand：发送到中层选定的业务命令主机
    def run_command(
        self, command: str, *, cwd: str | None = None,
        env: dict[str, str] | None = None,
        timeout_ms: int = 600_000,
    ) -> Result[CommandData]: ...

    # File：upload/download 是同一个能力的两个方向
    def upload_file(self, local_path: str, server_path: str, *,
                    timeout_ms: int = 600_000) -> Result[FileData]: ...
    def download_file(self, server_path: str, local_path: str, *,
                      timeout_ms: int = 600_000) -> Result[FileData]: ...
```

统一返回：

```json
{
  "request_id": "uuid",
  "status": "success | failed | timeout | unknown",
  "data": {},
  "error": null
}
```

`data`：

```json
{"output": "3"}
```

```json
{"returncode": 0, "stdout": "...", "stderr": "..."}
```

```json
{"bytes": 1024, "sha256": "..."}
```

`server_path`/`cwd` 是当前 session 的业务服务器路径；物理位置由中层决定。

## 2. 中层 ↔ daemon.py

### 传输

```text
TCP byte stream
一条连接 = 一个 request + 一个 response
request：UTF-8 JSON；中层写完后 shutdown(SHUT_WR)，EOF 结束
response：UTF-8 JSON；daemon 写完后关闭连接，EOF 结束
```

不使用裸换行分帧，不在一条连接上发送多个 request。

### request

```json
{
  "protocol": "vb.daemon.v1",
  "request_id": "uuid",
  "token": "opaque-session-token",
  "op": "skill",
  "skill": "getVersion()",
  "timeout_ms": 30000
}
```

- `protocol` 固定为 `vb.daemon.v1`。
- `op` v1 只能为 `skill`；`skill` 是 SKILL 源码，不是 shell。
- `token` 由中层从 session 注入，daemon 校验。
- `request_id` 必须在 response 原样返回。

### response

```json
{
  "protocol": "vb.daemon.v1",
  "request_id": "uuid",
  "status": "ok",
  "output": "3",
  "error": null
}
```

```json
{
  "protocol": "vb.daemon.v1",
  "request_id": "uuid",
  "status": "invalid_token",
  "output": "",
  "error": {"code": "INVALID_TOKEN", "message": "token mismatch"}
}
```

`status`：`ok`、`invalid_token`、`bad_request`、`skill_error`、`timeout`、`daemon_error`。

处理顺序固定为：

```text
收完整 JSON → 校验字段 → 校验 token → 投送 Skill → 读取下层 frame → 返回 JSON
```

token 错误时不得写 Virtuoso stdin；token 不进入下一层，也不回显到 response。

## 3. daemon.py ↔ SKILL（`ramic_bridge.il`）

### 传输方向

```text
daemon.py stdout  ──>  RBIpcDataHandler
ramic_bridge.il   ──>  ipcWriteProcess  ──>  daemon.py stdin
```

这是 `ipcBeginProcess` 管道，不是 TCP/SSH；不携带 token 和 `request_id`。
一个 daemon 同时只允许一个 in-flight Skill。

### request frame：daemon.py → SKILL

```text
<一条物理行的 canonical SKILL> + LF (0x0a)
```

```text
getVersion()\n
```

多行 Skill 由 daemon.py 内部包装为单行，或写临时 `.il` 后发送单行 `load("...")`。
`ramic_bridge.il` 收齐一条消息后再 `evalstring`，按 `progn` 语义取最后表达式的值。

### response frame：SKILL → daemon.py

```text
<status-byte> + <payload> + RS (0x1e)
```

| 字节 | 含义 |
|---:|---|
| `0x02`（STX） | 求值成功 |
| `0x15`（NAK） | 求值失败或内部超时 |
| `0x1e`（RS） | frame 结束 |

`payload` 是 SKILL `%L` 文本；成功为结果值，失败为错误文本；不得包含未转义的 `0x1e`。
CIW `printf` 和 daemon stderr 只是诊断输出，不是 response payload。

## 4. 定稿

```text
高层↔中层：bind(token) → BusinessSession → Skill / RunCommand / File
中层↔daemon.py：TCP；一连接一请求；UTF-8 JSON request/response；EOF 分帧
daemon.py↔SKILL：ipcBeginProcess；SKILL + LF；STX/NAK + %L payload + RS
```

现有旧 daemon 的 `{"skill": ..., "timeout": ...}` 和原始 `STX/NAK/RS` 仅由兼容适配器处理，
不作为新的 v1 契约。
