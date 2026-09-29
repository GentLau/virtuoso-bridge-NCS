# 业务操作人工体验台

这是一个面向真机业务面的手工体验页面。它不修改生产 server，
只负责：

1. 通过本地 HTTP 服务托管 `index.html`；
2. 把页面同源的 `/health`、`/help`、`/api/operation` 转发到现有业务面；
3. 让浏览器能够读取业务 JSON 返回，而不触发跨域限制。

## 为什么需要一个小代理

生产业务面 `server.api_server` 只暴露：

```text
POST /api/operation
GET  /health
GET  /help
```

它既不托管 HTML，也不发送 CORS 响应头。因此严格意义上“单个 HTML 文件”
可以发出请求，但无法从浏览器读取结构化业务返回。这里不改业务 server，
只在 `test/` 下增加同源人工体验代理。

## 启动

先确认业务面已经运行，例如：

```powershell
python -m server.api_server --host 127.0.0.1 --port 8127 `
  --work-dir test/artifacts/env/log-vblog
```

再启动体验台：

```powershell
python test/live/manual/business_console/serve.py `
  --business-base http://127.0.0.1:8127 `
  --port 8130
```

浏览器打开：

```text
http://127.0.0.1:8130/
```

页面右上角填写实际 token。首版已提供：

- `basic.skill.execute`
- `basic.command.run`
- `basic.gui.run`
- `basic.spectre.run`
- `basic.file.upload`
- `basic.file.download`

左侧“All Operations”会从 `/help` 读取全部已登记操作。未图形化的操作
可以在“原始业务请求”面板中填写 JSON 业务字段。

结果区只展示业务返回的原始 JSON，不替调用方解释 `result`、`steps` 或
`CommandResult` 的字段位置，便于现场核对真实响应协议。

## 使用边界

- 这是真机操作台，不是 mock。执行 SKILL、命令、GUI 命令、Spectre 命令和
  文件传输都会访问真实业务环境。
- 文件路径由业务面所在进程解析，浏览器不会上传文件内容。
- token 只在当前页面内存中使用，不写入 URL、日志或浏览器持久存储。
- `serve.py` 只允许转发 `/health`、`/help`、`/api/operation`，不会变成任意
  HTTP 代理。
