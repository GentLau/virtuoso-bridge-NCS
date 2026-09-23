# 增强凭据 `enhanced_token` 落地说明（2026-09-23）

> spec：`SPEC-2026-09-23-r22`《多用户与注册》v40、《控制面与业务面》v40：
> `apply` 请求体新增可选 `enhanced_token`；值为**管理员 token 或任一已登记持有者的
> token**；只校验、不落盘、不回显、不进日志。
> 用户口径：**声明里加一个可选参数；不提供走老路子；提供了该用就用。最小改动。**

## 1. 改动（最小面）

| 文件 | 改动 |
|---|---|
| `src/register/models.py` | `RegistrationRequest` 增加可选字段 `enhanced_token: str \| None`（同一套 `validate_token` 字符集/长度校验） |
| `src/register/server.py` | ①`_require_admin` 抽出 `_is_admin_token()`；②新增 `_enhanced_token_ok()`（管理员 token 或任一已登记 holder token）；③`apply` 构建 `RegistrationRequest` 后，**提供了 enhanced_token 就校验**，不通过 → `401 {"error": "invalid enhanced_token"}`，不改变状态；④凭据清洗正则加入 `enhanced_token` 键名（`/api/bug` 落盘前同样掩码） |

不做（本轮）：

* **未提供时保持老路子**——不新增强制门（若现在强制"local 模式必须加强凭据"，
  现有注册页/测试都不带该字段，会立刻不可用）；本地模式/凭据复用的强制门
  待前端与使用方就绪后再收紧；
* 不动前端注册页（尚无 enhanced_token 输入框）；
* 不实现 r18–r21 的 `key_dir`/`key`、凭据复用与 endpoint 复用（代码尚未落地，
  那些是另一批功能）。

## 2. 契约细节

* 位置：`POST /api/register` 的 `action=apply` 请求体（其余 action 仍只允许
  `{user, action, token}`）；
* 取值：管理员 token（SHA-256 比对，同 `Authorization` 口径）或
  `registry.user_of(token)` 命中的任一已登记持有者 token；
* 失败：4xx 且**不改变注册会话状态**；成功也不回显（响应只含候选状态）；
* 不落盘：`_build_entry()` 只拷贝显式字段，`enhanced_token` 永远不会进入注册表。

## 3. 证据

```text
test/artifacts/evidence/enhanced-token-red.txt    # 实现前：字段被 extra_forbid 拒绝（400）
test/artifacts/evidence/enhanced-token-green.txt  # 实现后：5 个新用例全绿
```

用例（`test/offline/unit/test_registration_server_edges.py::TestRegisterCommandEdges`）：

1. holder token / 管理员 token 都能通过 apply；
2. 未知 enhanced_token → 401 且不创建会话；
3. 不带该字段 → 老路径照常 200；
4. 状态查询不回显该值；
5. bug 报告落盘前掩码 `enhanced_token`。
