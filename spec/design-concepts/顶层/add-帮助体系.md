# 顶层补充：帮助体系（`/help` 端点族）

> 版本：Draft v2
> 日期：2026-10-09
> 状态：Normative（帮助端点族唯一口径）
> Supersedes：Draft v1（未知操作 404 只报未知，不做近邻候选）
> 定位：本文是[顶层](1-顶层.md)的补充，定义 `/help` 端点族的形态、契约与数据来源；端点清单主表见[控制面与业务面](add-控制面与业务面.md)，本文只讲帮助子族细则。帮助不解释任何业务操作语义。

## 1. 原则

1. 帮助三档：quickstart（人）、操作清单（人+机）、操作详情（人+机）；
2. 帮助端点一律无鉴权，且不回显绝对路径、主机名、注册表内容；
3. 数据三分不复制：操作清单来自注册表（运行态事实），机械字段来自 `Request` 模型，散文来自手册原文；端点不另写说明；
4. 人看文本、机器看 JSON。

## 2. 端点

### 2.1 `GET /help` —— quickstart（人）

- 返回 `text/plain` 固定文本（手写维护）；无鉴权。

### 2.2 `GET /help/operations` —— 清单 / 详情（人+机）

| 形态 | 请求 | 返回 |
|---|---|---|
| 清单 | 无 `name` | `{count, groups}`：组=包，每操作 `{name, summary}`；`summary` = 手册小节标题 `—` 后的后缀，取不到省略 |
| 详情 | `?name=<操作名>` | `{name, package, method, required_fields, request_schema, doc, content_format, common_ref, common, content}` |

- 可选参数：`group`（清单收窄到某包）、`common=0`（详情省略公共约定段）；
- `required_fields` 由 `request_schema.required` 派生；`request_schema` = `Request.model_json_schema()`；
- `content` 与 `common` 是手册小节/公共段的 **markdown 原文**，端点不加工、不改写；
- 未知操作 → `404`；手册不可用 → 降级：仍返回 schema 与 `doc` 定位，`content` 省略并附 `content_unavailable` 原因，不报错。

## 3. 数据来源

| 输出 | 来源 |
|---|---|
| `name` / `method` / Request | 各包 `OPERATIONS` 四元组 |
| 操作清单 | 注册表（包加载失败则该包操作不出现） |
| `request_schema` | `Request.model_json_schema()` |
| `doc.file` / `section_title` | 操作名前缀 → 包文件；标题行含完整操作名的小节 |
| `summary` / `content` / `common` | 手册小节 / 公共约定段的 markdown 原文 |
| 控制面 `/help` 的 endpoints | 路由表派生，不手写 |

## 4. 响应契约

- `/help` 根为 `text/plain`、无壳；JSON 端点统一 `{ok, data, error}` 壳；
- 状态码：`200` 正常、`404` 未知操作、`405` 方法不支持（含 `Allow`）；
- 可选 `ETag`：按资源计算（操作详情 = schema + 该节 content 的哈希；`common` 单独一个）；
- 兼容：既有 `/help` 的 `operations` 数组保留，新增字段为增量。

## 5. 手册数据源的结构约定（文档格式）

1. 每个业务操作在所属包文件里**有且仅有一个小节**，标题行包含完整操作名（反引号包裹）；
2. 标题格式 `… \`<操作名>\` — <短标题>`，`—` 后即 `summary`；层级不限、同文件内一致；
3. 允许一个标题覆盖多个操作（返回同一节内容）；
4. 公共字段只放 `manual/common.md` 的「公共约定」节，操作小节不得重复；
5. 文件路径是契约的一部分：`manual/packages/<包>.md`、`manual/common.md` **永不改名**；`--manual-root` 可覆盖根目录；
6. 手册目录随服务分发、只读；缺失时按 §2.2 降级，不影响业务端点。

## 6. 明确不做

- 不提供 `result_schema`；不把 help 做成业务操作；不做文档生成脚本；不做文档 ↔ 代码双向断言；不把散文搬进模型。
