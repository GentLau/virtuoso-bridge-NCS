# 出错了怎么办

## 先做三步

1. **看 `data.steps`**：找最后一条 `ok=false` 的 step，它的 `detail` 里有 SKILL 原文、命令 `stderr`、`returncode`、`kind`——90% 的原因写在这里。
2. **自己复核一次现状**：先 `read`/`list`/`status` 看目标到底存不存在、有没有变化。
3. **用底层命令验事实**：`basic.command.run` 可以 `ls`、`pgrep`、`command -v spectre`，把"猜"换成"看"。

## 按症状查

### 调用根本没进去

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 连不上 / 超时 | 业务服务没起，或端口不是你以为的那个 | `GET /health` 试一下；端口是启动参数，问用户要 |
| HTTP 400 `invalid request for operation: ...` | 字段名写错、类型错、多给了不认识的字段 | 对照 `operations.md` 的必备列；报错里会点名 |
| HTTP 404 `unknown operation: xxx` | 名字不存在或拼错（404 只报未知，不给近邻候选） | `GET /help/operations` 拿准确名字 |
| HTTP 429 `thread pool exceeded ... please retry` | 服务在途请求太多 | 等 1~2 秒重试；批量任务降并发 |
| `token is required` / `invalid token` | 没带 token、抄错、或这个用户没注册 | 找用户核对；注册页能看已注册用户 |

### 操作进去了，但业务失败

| 现象 | 原因 | 怎么办 |
|---|---|---|
| `library not found` / `view not found` | 库/视图不存在或名字写错 | `virtuoso.cellview.lib.list` / `cell.list` / `view.list` 逐级确认 |
| 写视图报 `locked` / `is locked by another session` | 视图在 Virtuoso 里被打开，或上次异常退出留下锁文件 | 让用户关掉该视图窗口后重试；确认没人占用后，再看远端 `<lib>/<cell>/<view>/` 下的 `*.cdslck` |
| `unknown CDF param: xxx` | 器件参数名不是该器件的 CDF 参数 | 查 PDK 手册；或先 `schematic.read` 看现有实例的 `params` |
| `instance not found` / `terminal not found` | 名字拼错，或该实例确实不在这个视图里 | 先 `schematic.read` 拿到实际名字 |
| `VB-PATH-NOT-VISIBLE:` / `no such file` | 路径在远端不存在；或者你把本机路径直接当远端路径用了 | 本机文件先 `basic.file.upload`；远端用 Linux 绝对路径 |
| `sha256 mismatch` | 传输过程中内容对不上（偶尔是磁盘满/网络抖动） | 重传一次；重复失败就查远端磁盘空间 |
| `command -v spectre` 为空 / Spectre 报找不到 | 远端没有 spectre，或没配工具环境 | 先 `spectre.check_license`；仍失败就让用户配好 Spectre 环境 |
| Calibre 报找不到 deck/许可 | deck 路径不对或许可没起 | 先 `calibre.check_env`，再跑 DRC/LVS |
| Maestro `read_results` 没有数据 | 这个 history 还没跑完 / 没有结果 | 用 `read_history` 看状态；跑完再读 |

### 超时与"结果未知"

- 报 `timeout`（`returncode=124`）或 `kind=unknown-effect`：**任务可能已经执行了**。
- 正确做法：先 `read`/`status`/`read_history` 看现状，再决定是补一步还是重来。
- 绝对不要对写操作"原样再发一次"来碰运气——可能变成重复建库、重复放器件、重复起仿真。
- 长任务一开始就该给足 `timeout`（比如 Maestro 跑仿真、Verilog 结构导入）。

### 截图 / 窗口相关

| 现象 | 原因 | 怎么办 |
|---|---|---|
| 截图失败、黑屏、空图 | 远端 GUI 的 `DISPLAY` 没配或不可访问 | 让用户在注册配置里确认 GUI 的 display；用 `basic.gui.run` 跑 `xdpyinfo` 验证 |
| 找不到窗口 / 发按键没反应 | 拿到的 `window_id` 过期或不对 | 重新 `virtuoso.gui.list_windows` 拿最新 id |
| CIW 卡在弹窗，后续操作全失败 | 有模态对话框挡着 | `virtuoso.gui.auto_dismiss`；不行再 `send_key`（`enter`/`escape`） |

### 多个操作互相打架

- 同一个 Virtuoso 会话同一时刻只跑一件事；同一个视图不要一边写一边读。
- Maestro：不要同时开 GUI 会话和后台操作同一个 view；跑仿真前先关掉不需要的窗口。
- 需要并行时用 `basic.command.run` 的 `parallel=true`，或 `spectre.run` 的 `max_workers`。

## 还是解决不了：报障

控制端口（默认 `http://127.0.0.1:8124`）提供 `POST /api/bug`：
请求体里带上个人 token，服务端会**先剥掉凭据**，再把请求体、提交人、时间、近期日志一起存档到工作目录的 `log/bug_reports/`。
报障时把"操作名 + 请求体 + 完整返回（含 `steps`）"一起交上去，最省事。
