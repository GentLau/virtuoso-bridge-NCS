# 第五轮 · 顶层 API 面真机复核（业务面端点契约）

> 执行者：root ｜ 2026-09-23 21:0x ｜ 方式：**对常驻业务面 8127 发真实 HTTP**（只读探测，不改状态）+ 离线回环 TB 复现
> 关联 spec：《顶层》§3（响应壳与错误分界）、《控制面与业务面》§4（业务端口端点清单）

## 1. 真机实测（`test/artifacts/evidence/round5-live-api/business-port-surface.json`）

| 请求 | 实测 | spec 要求 | 判定 |
|---|---|---|---|
| `GET /health` | 200（`face=business`、`operations=82`、`in_flight/max_inflight`） | 200 | ✅ |
| `GET /help` | 200（端点数与 operation 清单） | 200 | ✅ |
| `GET /api/register/<user>` | **404 not found** | 业务面不含注册端点 | ✅ |
| `GET /api/users` | **404 not found** | 业务面不含管理端点 | ✅ |
| `GET /api/operation` | **404 not found**，无 `Allow` | **405 + `Allow`**（已定义路径） | ❌ **P-055** |
| `POST /health` | 404 not found | **405 + `Allow`** | ❌ **P-055** |
| `POST /help` | 404 not found | **405 + `Allow`** | ❌ **P-055** |
| `POST /api/operation`（空体） | 400 `operation is required` | 4xx 结构错误 | ✅ |
| `POST /api/operation`（合法 operation、缺字段） | 400 结构化（缺 `library/cell/view`） | 4xx 结构错误，领域/授权由中层判定 | ✅ |
| `POST /api/operation`（未知/非法 token、字段齐全） | 200 `ok=false`（业务失败，不下传 token） | 2xx 业务失败 | ✅（见 §3） |
| `GET /nope` | 404 not found | 404 | ✅ |

## 2. 离线复现（`test/offline/unit/test_api_server_method_not_allowed.py`）

- **3 红 2 绿**：`GET /api/operation`、`POST /health`、`POST /help` 三条按 spec 断言 405 → **红**；
  `PUT /api/operation` → 405、未知方法 `FOO /api/operation` → 405、未定义路径 → 404 三条**绿**（作为回归护栏）。
- 根因锚点：`src/server/api_server.py:127-161`（`do_GET` 兜底 404）、`:163-166`（`do_POST` 兜底 404）；
  已实现 405 的入口只有 `do_PUT/do_DELETE/do_OPTIONS/do_TRACE/do_PATCH/do_CONNECT/do_HEAD` 与 `__getattr__`→`_unknown_method()`。
- **对照组（说明这不是"设计口径"）**：控制面同一规则已实现且有用例 ——
  `test/offline/unit/test_registration_server.py:737-764`：`PATCH /api/register` → 405 且 `Allow: GET, POST, PUT, DELETE`；
  未知方法与已定义/未定义路径的组合也有断言。业务面缺的是同一套判定。

## 3. 本轮同时确认（无需修复，记录口径）

1. 业务面 `/health` 暴露 `operations`/`in_flight`/`max_inflight`/`draining`，与《控制面与业务面》§5 的"业务面能力上限"口径一致；
2. 业务面**不暴露**注册/管理端点（`/api/register/*`、`/api/users` 均 404）——与"两面不混用"一致；
3. 结构化错误体形状符合《顶层》§3：`{"ok":false,"data":null,"error":...}`，失败行 `data=null`。

## 4. 处置

- 缺陷登记：**P-055**（待并入 `test/reports/问题登记.md` 第五轮表；本轮多名执行者并写台账，root 在收尾时统一合并，避免同段落并发改写）；
- TB：`test/offline/unit/test_api_server_method_not_allowed.py`（修好即自动转绿，**不需要**改断言）；
- 建议修法：`do_GET`/`do_POST` 的兜底分支改成"路径在 `_DEFINED_PATHS` → `_method_not_allowed()`，否则 404"，
  `Allow` 按路径真实方法集输出（`/api/operation`→`POST`，`/health`、`/help`→`GET`）。
