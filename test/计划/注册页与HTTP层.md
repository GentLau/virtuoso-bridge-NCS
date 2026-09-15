# 注册页与 HTTP 层

> 覆盖目标：`src/server/registration_server.py`、`src/server/registration_page.html`、
> `test/frontend_tb/`（Mock Testbench）。判据：页面提交的 payload 与 spec 契约一致，服务端拒绝语义正确。

### 1. 页面 payload 形状

- **测试目标**：页面产出 canonical payload（`mode.default` / `root.default` / `ssh.default.*` / `roles.<name>` / 策略项）
- **测试流程**：静态契约测试 + 起服后 GET / 抓页面检查字段与 `<details>` 平衡
- **预计响应**：字段齐全、`<details>` 平衡、payload 折叠代码在位（`test/unit/test_registration_page.py`）

### 2. per-role 覆盖 UI

- **测试目标**：五个 role 的 `mode/host/user/jump_host/root` 可填并进入 `payload.roles.<name>`
- **测试流程**：逐 role 断言输入存在与 payload 折叠；服务端侧用 HTTP 提交带 per-role 覆盖的请求
- **预计响应**：`entry.roles.<name>` 反映覆盖（root 按 spec 回写绝对路径）

### 3. local role 参数校验

- **测试目标**：`role.<name>.mode=local` 时提交连接字段必须被拒
- **测试流程**：页面侧（自定义校验提示）+ 服务端侧（400 invalid request）
- **预计响应**：前端阻止提交；后端 `400`

### 4. 六步 API

- **测试目标**：`/api/register`（一步）与 `/api/register/apply|validate|probe|deploy|verify`（分步）状态机正确
- **测试流程**：分步推进并检查 `stage/step`；unknown user / 非法 JSON / 非法字段
- **预计响应**：状态与 spec 六步一致；错误为 400/404 且不落盘

### 5. update / delete API

- **测试目标**：update 白名单、嵌套字段、非法值不落盘；delete 解绑
- **测试流程**：`POST /api/user/<user>/update`、`DELETE /api/user/<user>`
- **预计响应**：白名单外字段拒绝；非法值保留旧条目；delete 幂等返回 404/200

### 6. 注册页与 reservation 的联动

- **测试目标**：端口冲突（同 daemon 主机）在页面上得到可读提示
- **测试流程**：先注册占用端口 → 再用同主机同端口提交
- **预计响应**：申请阶段即失败并给出端口冲突原因；不进入探测
