# 需求：`config.json` 增加 `skillref` 段（供 skillref 业务包读取文档树位置）

> 提出方：上层业务包开发（skillref）｜日期：2026-09-21｜状态：**待 spec owner 裁决**
> 关联：`spec/design-concepts/上层/9-skillref.md` §3.1 / §6.1（本需求的服务方口径）
> 落法：已选**方案 A**（扩展 `config.json`），不新增独立文件

## 1. 一句话需求

让部署方在 `config.json` 里配一次"SKILL 文档树在哪台机、哪个路径"，skillref 业务包读它做事，
不必每次请求都传路径，也不必让包去猜路径。

```json
{
  "business_thread_pool_size": 1024,
  "skillref": {
    "source": "remote",
    "doc_root": "/opt/eda/cadence/IC618/doc"
  }
}
```

## 2. 为什么现在不行（现状证据）

| 现状 | 位置 |
|---|---|
| 规范写明 `config.json` **当前只有一个参数** `business_thread_pool_size` | `spec/design-concepts/顶层/add-控制面与业务面.md:113` |
| 控制面 `load_config()` 只保留这一个键，读文件时其余键直接丢弃 | `src/register/server.py:822-828` |
| `PUT /api/config` 按内存快照整体写回 → **手工加进文件的 `skillref` 段会被下一次 PUT 抹掉** | `src/register/server.py:830-843` |
| 业务进程也只在启动时读这一个键 | `src/server/api_server.py:38-45` |

## 3. 需求（R1–R7）

| 编号 | 要求 | 落点 |
|---|---|---|
| R1 | 参数清单从"只有一个 `business_thread_pool_size`"改为多参数，登记 `skillref` 段 | 顶层补充 §5 |
| R2 | **schema 只有两个字段**：`{"skillref": {"source": "local\|remote", "doc_root": "<绝对路径字符串，可为 null>"}}`；未列出的子键原样保留（前向兼容）；远端取数的中间落点由 skillref 包自己管理，**不进配置** | 顶层补充 §5 + 控制面 |
| R3 | `GET /api/config` 原样回带 `skillref` 段；`PUT /api/config` **只覆盖请求里出现的键，不得丢弃已有键** | 控制面 |
| R4 | 生效时机与 `business_thread_pool_size` 一致：业务进程启动导入一次快照，`POST /api/process/reload` 后对新请求生效；写明"改 `source`/`doc_root` 需 reload" | 顶层补充 §5 |
| R5 | 校验：`source ∈ {local, remote}`；`doc_root` 非空绝对路径、不含 NUL；`PUT` 非法值 → 4xx 且不落盘 | 控制面 |
| R6 | 缺失/`null` **不是错误**：业务进程照常启动；skillref 被调用时返回明确的业务失败（"数据源未配置"），不探测路径 | 控制面 + skillref §3.1 |
| R7 | 语义归属：字段的**业务含义**（SKILL 文档树根、`source` 的两种取数方式）归 `9-skillref.md`；顶层只登记字段名、类型、默认值与生效时机 | 两边 |

## 4. 明确不做（本需求边界）

1. **不做路径探测**：不执行 `which virtuoso`、不做父目录上溯、不按"本地看得见就本地"猜测；
   `source` 与 `doc_root` 永远由配置或请求显式给出；
2. 不新增 role、不碰中层五接口、不改注册表 schema；
3. 不引入"文档树缓存/索引"配置项（skillref 本版无持久索引）。

## 5. 验收建议（改完后怎么测）

1. `PUT /api/config` 只传 `{"business_thread_pool_size": 512}`，重启前先手工在 `config.json`
   写入 `skillref` 段 → PUT 后 `GET /api/config` 仍能看到 `skillref`（验 R3）；
2. `PUT /api/config` 传 `{"skillref": {"source": "bogus", "doc_root": "relative/path"}}`
   → 4xx，且 `config.json` 不被改写（验 R5）；
3. 配好 `skillref` 后 `POST /api/process/reload`，调用 `virtuoso.skillref.search`
   → 返回里带 `source`/`doc_root`（验 R4）；
4. 删掉 `skillref` 段后重启业务进程 → 进程正常起来（验 R6），调用该操作得到
   "数据源未配置"的业务失败而不是 5xx。
