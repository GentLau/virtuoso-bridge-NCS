# v1 跨层接口契约

> 兼容入口。三条接口的唯一正文见 [protocol-v1.md](protocol-v1.md)。

只看以下三条边界：

1. **高层 ↔ 中层**：`middle.bind(token)` 返回 `BusinessSession`；session 提供 `execute_skill`、`run_command` 和 File（`upload_file`/`download_file`）。
2. **中层 ↔ daemon.py**：TCP，一连接一请求；UTF-8 JSON request/response，以 EOF 结束；request 带 `protocol`、`request_id`、`token`、`op`、`skill`、`timeout_ms`。
3. **daemon.py ↔ SKILL**：`ipcBeginProcess` 管道；`SKILL + LF`；返回 `0x02/0x15 + %L payload + 0x1e`。

daemon.py 只处理 Skill。命令行和文件传输由中层执行；token 在 daemon 层校验，不能进入 SKILL 层。

请不要在本文件追加接口字段，以免与 [protocol-v1.md](protocol-v1.md) 分叉。
