# 注册页 Mock TB（离线级）

> 级别：**离线**——无 SSH、无 Virtuoso、不落盘。判定见 [`../../docs/测试架构.md`](../../docs/测试架构.md) §2。

- `registration_mock_server.py`：内存态 mock 服务，复用正式注册页资源 `registration_mock_panel.html`；
- 用途：只调前端与 HTTP 交互（成功 / 步骤失败 / 404 会话失效 / 临时 500 等），不接触真实环境。

从仓库根目录运行：

```powershell
python test/offline/frontend/registration_mock_server.py --port 8125
```

浏览器打开 `http://127.0.0.1:8125/`。自动用例在
[`../unit/test_registration_mock_server.py`](../unit/test_registration_mock_server.py)。
