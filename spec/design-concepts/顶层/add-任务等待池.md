# 顶层补充：任务等待池

> 版本：Draft v2
> 日期：2026-09-20
> 状态：Normative（顶层任务等待池职责、契约、端点与配置的唯一口径）
> Supersedes：Draft v1（查询统一端点、token 授权、挂起失败语义）
> 定位：本文是[顶层](1-顶层.md)的附加功能——顶层代为监督长任务的完成情况。挂起区**不负责业务、不负责命令**；它只按上层声明的 `follow_up` 反复询问，直到终态。端点清单见[控制面与业务面](add-控制面与业务面.md)。

## 1. 职责与边界

- 挂起区只做一件事：**监督完成情况**。上层业务包在 `Result` 里声明 `pending`，顶层登记并循环调用 `follow_up.operation` 查询进度，直到终态。
- 挂起区**不对任何业务操作负责**：启动动作是调用方发起该 operation 的一次真实执行；顶层不重放、不撤销、不解释业务结果。重复提交启动请求可能真实执行多次（顶层不承诺幂等去重），以目标侧事实为准。
- 任务表是**内存调度状态**（不是业务状态）：重启即丢，不恢复；终态登记保留到重启供查询，但不占用挂起配额。
- 不做推送：无 SSE / WebSocket / 回调；阻塞模式即长轮询，非阻塞模式即查询。

## 2. 上层声明契约（`pending`）

业务包仍保持同步、无状态，只在 Result 中多一个可选字段：

```python
pending = {
    "follow_up": {"operation": "<已注册 operation>", "payload": {...}},
    "poll_interval": 10.0,   # 可选：本次任务节拍（秒），缺省用 per-token 配置，再缺省 10
    "deadline": 86400.0,     # 可选：本任务总预算（秒），缺省 24h
}
```

- `job_id` 由**顶层生成**，不出现在 `pending` 中；
- `follow_up.operation` 必须是已注册的普通业务操作；`payload` 是它的业务入参（不含 `operation`/`token`）；
- 每次 `follow_up` 都是一次真实的业务操作调用，会占用该 token 的中层线程/通道预算，**不得绕过中层限流**。

## 3. follow_up 三态

顶层只解释 follow_up 返回的固定字段：

| 返回 | 顶层行为 |
|---|---|
| `state="running"`（可选 `progress`） | 按节拍继续轮询 |
| `state="done"`（`result`） | 终态成功，`result` 透传给调用方 |
| `state="failed"`（`error`） | 终态失败，`error` 透传给调用方 |

- `progress` 只透传、不解释；
- follow_up 本身调用异常/超时 → 本次轮询失败，**继续按节拍重试**，不立即判死；直到 `deadline` 到期 → `state="failed"`、`error="deadline"` 终态。

## 4. 调用模式与查询

| 模式 | 选择方式 | 行为 |
|---|---|---|
| 非阻塞（默认） | 不传 `wait` 或 `wait=false` | 立即返回 `job_id` 与查询信息 |
| 阻塞 | `wait=true` | 请求线程循环到终态后返回，结果中同样包含 `job_id` |

- 阻塞/非阻塞**共用同一套 follow_up 逻辑与任务表**；
- 阻塞模式不强制服务端截止；调用方应自行设置 HTTP 超时与 deadline；
- 查询统一端点 `GET /api/job`（业务端口，个人 token）：
  - `GET /api/job/<job_id>`：返回 `{job_id, state, progress?, result?|error?, recent: [...]}`，其中 `recent` 为**最近几次轮询情况**（默认保留最近 10 次）；
  - `GET /api/job`（不带 job_id）：返回 `{jobs: [...]}`，列出**该 token 下全部挂起任务**；
- 授权：查询必须携带该任务所属 `token`，服务端只返回该 token 自己名下的任务；缺失/不匹配 → 4xx `invalid token`，拿不到他人 token 就查不到他人的挂起任务。

## 5. 取消

- `DELETE /api/job/<job_id>`：**只取消挂起区的监督**，不取消、不撤销已经发出的命令/仿真；原命令是否继续以目标侧为准；必须携带该任务所属 `token` 且校验通过；
- 取消后登记项删除，后续查询返回 404；幂等。

## 6. 监督线程与节拍

- 挂起区使用**单个监督线程**统一驱动所有任务，不为每个任务开线程；
- 节拍显式配置（`pending.poll_interval` 或 per-token 配置），默认 10s，最小 1s；
- 终态（done / failed / deadline）与取消都会停止监督并清理配额占用。

## 7. 配置与配额

| 类别 | 存储 | 参数 |
|---|---|---|
| 全局 | `config.json` | `task_global_pending_limit`（挂起区全局在途上限，默认 128） |
| per-token | `task_registry.json`（与中层 `registry.json` 分离，注册时写入） | `task.pending_limit`（该 token 挂起在途上限，默认 8） |

- 提交时超过 per-token 或全局上限 → 明确 4xx `pending limit exceeded` 拒绝，并注明是 per-token 还是 global 上限；任何**挂起失败**都必须在返回中说明失败原因；
- 终态/取消的登记不占上述配额；
- 注册与管理模块产出：`registry.json`（中层消费）、`config.json`、`task_registry.json`（任务等待池消费）。

## 8. 重启与清理

- 内存态：服务重启清空任务表，在途登记**不恢复**，调用方重新发起；
- 终态登记保留到重启，可重复查询。

## 9. 索引

- 顶层职责与响应壳：[顶层 §1–§3](1-顶层.md)；
- 端点清单与端口划分：[控制面与业务面](add-控制面与业务面.md)；
- 业务包契约与注册：[上层](../上层/1-上层.md)；
- 并发与限流：[并发设计](../中层/2-并发设计.md)；
- 本版不做：[本版范围与明确不支持](../总览/add-本版范围与明确不支持.md)。