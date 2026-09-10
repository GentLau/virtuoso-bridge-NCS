# 跨层接口协议 v1

只定义**两条跨层接口**：高层↔中层、中层↔daemon.py。daemon.py 与 Virtuoso 之间只是底层内部实现（收到什么 SKILL 就写进去、再读回结果），不构成独立跨层契约。基线是**现有代码**，改动只有两处：

- 所有接口新增 **`token`** 参数（多用户路由/鉴权）；
- `run_command` 新增 **`parallel`** 参数（本项目新建的显式并行机制）。

```text
高层 ──Python──> 中层 ──TCP/JSON──> daemon.py ──ipcBeginProcess──> SKILL
```

| 边界 | 格式 | 负责内容 |
|---|---|---|
| 高层 ↔ 中层 | Python 接口 | Skill / RunCommand / File |
| 中层 ↔ daemon.py | TCP；JSON 请求 + `STX/NAK/RS` 响应 | 只传 Skill |

**daemon.py 不执行命令行，也不处理文件。**

## 1. 高层 ↔ 中层：三接口

### 1.1 与现有代码的对应关系

| 接口 | 现实现 | 本次改动 |
|---|---|---|
| Skill | `VirtuosoClient.execute_skill()` | 新增 `token` |
| RunCommand | `SSHClient.run_command()` | 新增 `token`、`parallel` |
| File | `SSHClient.upload_file()` / `download_file()` | 新增 `token` |

现有代码里高层还有其他调用口（cellview、截图、X11、skill finder 等），v1 中层只向上承诺上述三个端口，其余入口不进入本协议。

### 1.2 接口签名

```python
# 1. Skill —— 原 VirtuosoClient.execute_skill
def execute_skill(
    skill_code: str,
    timeout: float | None = None,
    *, token: str,                    # 必填：多用户路由参数（keyword-only）
) -> VirtuosoResult: ...

# 2. RunCommand —— 原 SSHClient.run_command
def run_command(
    cmd: str,
    timeout: int | None = None,
    *, token: str,                    # 必填：多用户路由参数（keyword-only）
    parallel: bool = False,            # 新增：显式并行机制
) -> CommandResult: ...

# 3. File —— 原 SSHClient.upload_file / download_file
def upload_file(
    local_path: Path,
    remote_path: str,
    timeout: int | None = None,
    *, token: str,                    # 必填：多用户路由参数（keyword-only）
    recursive: bool = False,           # 可选：False=单文件，True=目录递归
) -> CommandResult: ...

def download_file(
    remote_path: str,
    local_path: Path,
    timeout: int | None = None,
    *, token: str,                    # 必填：多用户路由参数（keyword-only）
    recursive: bool = False,           # 可选：False=单文件，True=目录递归
) -> CommandResult: ...
```

### 1.3 调用示例

```python
# Skill：执行 1+2，结果原样返回
r = middle.execute_skill("1+2", token="a3f9c2…")
# r.status == "success"；r.output == "3"

# RunCommand：默认串行
r = middle.run_command("spectre netlist.scs", token="a3f9c2…")
# CommandResult(returncode=0, stdout="...", stderr="")

# RunCommand：显式并行（两条互相独立的命令）
r1 = middle.run_command("spectre corner1.scs", token="a3f9c2…", parallel=True)
r2 = middle.run_command("spectre corner2.scs", token="a3f9c2…", parallel=True)
# parallel=True：中层为每次调用开独立 exec channel，两条命令并行跑，完成顺序不保证

# File：上传 / 下载
middle.upload_file("local.scs", "/home/user/run/local.scs", token="a3f9c2…")
middle.download_file("/home/user/run/out.psf", "out.psf", token="a3f9c2…")
middle.download_file("/home/user/run/psf_dir", "psf_dir", recursive=True, token="a3f9c2…")
```

### 1.4 返回类型（保持现状，不改）

```python
class ExecutionStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    ERROR = "error"

class VirtuosoResult(BaseModel):
    status: ExecutionStatus
    output: str = ""
    errors: list[str] = []
    warnings: list[str] = []
    execution_time: float | None = None
    metadata: dict[str, Any] = {}
    # SkillResult = VirtuosoResult

class CommandResult(NamedTuple):
    returncode: int
    stdout: str
    stderr: str
```

### 1.5 token / parallel 约定

- `token`：每次调用**必填**的关键字路由/鉴权参数；中层按 token 路由，并把 token 放入发给 daemon 的请求。
- `parallel`：`False`（默认）沿用现代码 persistent shell，同一 token 内命令串行、保证先后顺序；`True` 中层为本次调用开独立 exec channel，与其他命令并行，**不保证完成顺序**，只用于互相独立的命令。它是 RunCommand 的参数，不是第四个接口。
- 上层不传 host、port、SSH、tunnel、profile 或 daemon 地址。

## 2. 中层 ↔ daemon.py

### 2.1 传输（与现代码一致）

```text
TCP byte stream
一条连接 = 一个 request + 一个 response
request：UTF-8 JSON；中层写完后 shutdown(SHUT_WR)，EOF 表示结束
response：raw bytes；daemon 写完后关闭连接，EOF 表示结束
```

不在一条连接上发送多个 request，也不用裸换行分帧。

### 2.2 request（现代码字段 + 新增 token）

```json
{
  "skill": "getVersion()",
  "timeout": 30.0,
  "token": "a3f9c2…"
}
```

- `skill`：SKILL 源码，不是 shell 命令；
- `timeout`：秒，现代码语义不变；
- `token`：必填字段；缺失、`null` 或不匹配一律拒绝，SKILL 零接触；
- 不加 `protocol`、`request_id`、`op`、`timeout_ms`——现代码没有这些字段。

### 2.3 response（现代码 framing，不改）

daemon 不回 JSON，直接回原始字节：

```text
成功：0x02 + 输出文本 + 0x1e
失败：0x15 + 错误文本 + 0x1e
```

| 字节 | 十六进制 | 名称 | 含义 |
|---|---|---|---|
| `0x02` | `02` | STX | SKILL 求值成功 |
| `0x15` | `15` | NAK | SKILL 求值失败 / 内部超时 |
| `0x1e` | `1E` | RS | 帧结束 |

完整示例（`getVersion()` 返回 `"3"`）：

```text
请求（中层发给 daemon 的 JSON 字节）：
7b 22 73 6b 69 6c 6c 22 3a 20 22 67 65 74 56 65 72 73 69 6f 6e 28 29 22 2c 20 22 74 69 6d 65 6f 75 74 22 3a 20 33 30 2e 30 2c 20 22 74 6f 6b 65 6e 22 3a 20 22 61 33 66 39 63 32 e2 80 a6 22 7d
（即 {"skill": "getVersion()", "timeout": 30.0, "token": "a3f9c2…"}）

成功响应（daemon 回给中层的原始字节）：
02 33 1e
│  │  └─ 1e = RS，帧结束
│  └─ 33 = 字符 '3'，即 SKILL 返回值
└─ 02 = STX，成功

失败响应（语法错误）：
15 2a 45 72 72 6f 72 2a 20 2e 2e 2e 1e
│  └──────────────────────┘ └─ 1e = RS
│       错误文本 "*Error* ..."
└─ 15 = NAK，失败
```

中层把响应映射为上层结果：

```text
STX 开头 → VirtuosoResult(status=SUCCESS, output=payload)
NAK 开头 → VirtuosoResult(status=ERROR, errors=[payload])
payload 含 "TimeoutError" → 超时错误
空响应 / JSON 解析失败 → 错误
```

### 2.4 token 校验顺序

```text
收完整 JSON
  → 解析 skill / timeout / token
  → token 缺失、为 null 或不匹配：回 0x15 + "invalid token"，不写 Virtuoso stdin（SKILL 零接触）
  → token 不匹配：回 0x15 + "invalid token"，不写 Virtuoso stdin（SKILL 零接触）
  → token 匹配：把 skill 投送到第 3 节管道
```

token 不进入下一层，也不回显到 response。

## 3. 底层内部实现：daemon.py ↔ Virtuoso（非跨层接口）

### 3.1 方向

```text
daemon.py stdout  ──>  RBIpcDataHandler(ipcId, data)
ramic_bridge.il   ──>  ipcWriteProcess(ipcId, data)  ──>  daemon.py stdin
```

这是 Virtuoso 的 `ipcBeginProcess` 管道，不是 TCP/SSH；**不携带 token**。它不是跨层接口，只是 daemon 的内部机制：收到什么 SKILL 就写进 Virtuoso，再读回结果。一个 daemon 同时只允许一个 in-flight Skill。

### 3.2 request frame：daemon.py → SKILL（现代码，不改）

daemon 把一条 Skill 包装成单行文本写入 stdout，末尾必须带 LF（`0x0a`）：

```text
单行 Skill（不含 \n）：
  let(((__vb_r getVersion())) hiFlush() __vb_r)\n

多行 Skill（含 \n）——daemon 把它打包成临时 .il 文件再 load：
  1) 写临时文件 vb_eval_<随机>.il，内容为：
       _vb_eval_result = progn(
       <skill_code 原文，多行原样保留>
       )
  2) 再发送单行：
       load("/tmp/vb_eval_<随机>.il") hiFlush() _vb_eval_result\n
  3) 执行完 daemon 删除临时文件
```

说明：

- 单行路径 `let(((__vb_r …)) hiFlush() __vb_r)` 直接求值并返回最后表达式的值；
- 多行路径写成文件是因为 `load()` 只返回 `t`，所以代码里用全局变量 `_vb_eval_result = progn(...)` 把最后表达式的值取回来；同时保留注释 `;` 和多行结构；
- `\n`（LF = `0x0a`）是消息边界；
- `ramic_bridge.il` 收到 `data` 后执行 `evalstring(strcat("(progn " data ")"))`，取最后表达式的值。

### 3.3 response frame：SKILL → daemon.py（现代码，不改）

```text
<状态字节> + <payload> + RS(0x1e)
```

| 字节 | 十六进制 | 名称 | 含义 |
|---|---|---|---|
| `0x02` | `02` | STX | 求值成功 |
| `0x15` | `15` | NAK | 求值失败或内部超时 |
| `0x1e` | `1E` | RS | frame 结束 |

完整示例：

```text
成功（getVersion() 返回 "3"）：
02 33 1e
│  │  └─ 1e = RS，帧结束
│  └─ 33 = 字符 '3'，payload = result
└─ 02 = STX，成功

失败（SKILL 报错）：
15 2a 45 72 72 6f 72 2a 20 2e 2e 2e 1e
│  └──────────────────────┘ └─ 1e = RS
│       payload = errset.errset 的错误文本
└─ 15 = NAK，失败
```

`payload` 是 SKILL `%L` 文本：成功为 `result`，失败为 `errset.errset`。
CIW `printf` 和 daemon stderr 只是诊断输出，不是 response payload。

## 4. 定稿

```text
高层↔中层：
  execute_skill(skill_code, timeout=None, *, token)
  run_command(cmd, timeout=None, *, token, parallel=False)
  upload_file(local_path, remote_path, timeout=None, *, token, recursive=False)
  download_file(remote_path, local_path, timeout=None, *, token, recursive=False)

中层↔daemon.py：
  请求 {"skill": ..., "timeout": ..., "token": ...}，EOF 结束
  响应 02/15 + payload + 1e，EOF 结束

底层内部（非跨层接口）：
  收到什么 SKILL 就写进 Virtuoso，读回 02/15 + %L payload + 1e
```

## 5. 与现代码的差异清单

| 位置 | 现代码 | v1 |
|---|---|---|
| `execute_skill` | `(skill_code, timeout=None)` | 新增必填 keyword-only `token` |
| `run_command` | `(cmd, timeout=None)` | 新增必填 keyword-only `token`、`parallel=False` |
| `upload_file` | `(local_path, remote_path, timeout=None)` | 新增必填 keyword-only `token`、可选 `recursive=False` |
| `download_file` | `(remote_path, local_path, timeout=None, recursive=False)` | 新增必填 keyword-only `token`（上传/下载对称） |
| 中层↔daemon 请求 | `{"skill", "timeout"}` | 新增 `"token"` |
| 中层↔daemon 响应 | `STX/NAK/RS` 原始字节 | 不变 |
| 底层↔Virtuoso | 内部实现：写 SKILL、读 `STX/NAK/RS` | 不变，不加 token（非跨层接口） |
