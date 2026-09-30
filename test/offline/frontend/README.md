# 控制台三页 Mock TB（离线级）

> 级别：**离线**——无 SSH、无 Virtuoso、不落盘。判定见 [`../../docs/README.md`](../../docs/README.md) §1。

- `registration_mock_server.py`：内存态 mock 服务，复用正式控制台页面
  `src/register/registration_page.html`；
- 覆盖三页：注册六步、个人查询/更新/删除、管理员 config/process；
- 用途：只调前端与 HTTP 交互（成功 / 步骤失败 / 404 会话失效 / 临时 500 等），
  不接触真实 registry、SSH、Virtuoso 或业务进程。

从仓库根目录运行：

```powershell
python test/offline/frontend/registration_mock_server.py --port 8125
```

浏览器打开 `http://127.0.0.1:8125/`。自动用例在
[`../unit/test_registration_mock_server.py`](../unit/test_registration_mock_server.py)。

个人页安全联调凭据（仅 mock 内存有效）：

```text
user:     demo
personal: demo-token
admin:    mock-admin
```
