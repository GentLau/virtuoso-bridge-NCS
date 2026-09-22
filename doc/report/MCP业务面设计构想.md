# MCP 业务面设计构想（研究稿）

> 日期：2026-09-21
> 状态：**研究稿 / 非 Normative**（不得直接用于验收；与 spec 冲突时以 spec 为准）
> 范围：**只覆盖业务面**——业务端口 `/api/operation`、上层业务包、token 的业务语义。
> 不覆盖控制面（注册页、用户管理、`/api/process/*`、`/api/config`、`/api/bug`）。
> 依据：`src/server/api_server.py`、`src/server/dispatch.py`、`src/pyapi/packages/*`、
> `spec/design-concepts/总览/1-四层整体架构与接口.md`、`spec/design-concepts/顶层/add-控制面与业务面.md` §4、
> `spec/research/three-interface-report.md`
> 实测环境：本机业务端口 `8127`（token `vb-vblog`，work-dir `test/tb/artifacts/log-vblog`）

---

## 0. 结论先行

1. **MCP 不该重写业务。** 业务面已经是「显式操作注册表 + 每操作一个 Request/Result + 单一调度壳」，
   这正好是 MCP `tools` 的模型；`dispatch.PACKAGES` 就是一份现成的 tool registry。
   MCP 应作为**第三个投影**（HTTP face / CLI face / MCP face）存在，与
   `spec/research/three-interface-report.md` 的结论一致——核心写一次，界面只花一个适配器。
2. **推荐形态：stdio 薄代理。** `virtuoso-bridge mcp` 作为 MCP 宿主拉起的子进程，
   把每次 tool call 投影成 `POST /api/operation`。不改业务进程，一个 MCP 实例 = 一个 token 身份。
3. **工具不能平铺。** 磁盘上已有 61 个业务操作；平铺成工具会带来上万 token 的常驻开销并让选型退化。
   建议三层：6 个直通 power tools + 约 20 个领域工具 + 目录/逃生舱。
4. **token 属于配置，不属于参数。** 模型永远看不到 token；支持「一个实例一个身份」与多 profile。
5. **MCP 相对 HTTP 的真实增量只有三条**：结果投影（上下文预算）、图片/资源回传（AI 能看版图与波形）、
   任务句柄（长仿真）。协议本身不是目的。

---

## 1. 业务面现状盘点

### 1.1 一个端点 + 一张注册表

业务端口只有三个路由（`spec/design-concepts/顶层/add-控制面与业务面.md` §4）：
`POST /api/operation`、`GET /health`、`GET /help`。

`/help` 与 `dispatch.operations()` 同源，返回已登记操作名清单；`PACKAGE_LOAD_ERRORS` 按包隔离失败。

| 业务包 | 操作数 | 说明 |
|---|---:|---|
| `basic` | 6 | 中层五接口直通：skill / command / upload / download / gui / spectre |
| `demo` | 4 | `demo.pipeline.run`、`demo.parallel.probe`、`virtuoso.netlist.import`、`demo.paths.facts` |
| `gui` | 4 | list_windows / send_key / auto_dismiss / screenshot |
| `cellview` | 22 | lib / cell / view / cat 四组 CRUD |
| `schematic` | 4 | read / write / check_and_save / screenshot |
| `maestro` | 11 | read_config / write / read_results / export / read_history / write_history / open_gui / close_gui / run / open_waveform_gui / close_waveform_gui |
| `symbol` | 5 | read / write / check_and_save / generate / screenshot |
| `layout` | 5 | read / write / gds / screenshot / display |
| **合计** | **61** | 实测 8127 返回 56（该进程启动早于 `layout.py` 落盘，`package_load_errors` 为空）；重启后应为 61 |

调度链路（`src/server/dispatch.py`）：

```text
POST /api/operation
  → 结构校验：body 是对象 / operation 是非空 str / token 是非空 str      （400）
  → 查显式注册表                                                      （404 unknown operation）
  → Request(**业务字段, token=token)                                  （400 结构/领域校验）
  → spec.package(middle).method(request)                              （500 未预期异常）
  → {"ok", "data", "error"}                                          （业务失败也是 200）
```

业务失败用 HTTP 200 + `ok=false` 表达；HTTP 状态码只表达「是否受理」。这是 MCP 投影时必须翻译的一层语义。

### 1.2 请求模型：冻结 dataclass + `__post_init__`，没有 schema

现有 Request 全是 `@dataclass(frozen=True)` + 手写校验（类型、范围、互斥），例如：

```python
@dataclass(frozen=True)
class WriteRequest:
    token: str
    library: str
    cell: str
    commands: list[dict[str, Any]]     # 原子命令批，语义由业务包解释
    view: str = "schematic"
    timeout: int | None = None
```

`OPERATIONS` 四元组只有 `(操作名, 方法名, Request, Result)`——**没有 JSON Schema，也没有 per-operation 描述**。
对 MCP 而言这是第一等工程量：`tools/list` 的 `inputSchema` 与 `description` 目前无处可取。

### 1.3 结果形态（实测，决定上下文预算）

| 调用 | 返回体积 | 形态 |
|---|---:|---|
| `demo.paths.facts` | 0.5 KB | work_root / temp_dir / log_dir / artifact_dir（本机绝对路径） |
| `virtuoso.cellview.lib.list` | 557 B | `steps[].detail.output` 是 SKILL 文本，`value` 是解析后的列表 |
| `virtuoso.schematic.read`（2 器件 RC） | 3.0 KB | `detail.output` 是 `INST\|TERM\|NET\|PIN\|LABEL` 管道文本，`value` 是同一份结构化结果 |
| `log/bug_reports/*.json`（旁证） | 52 KB ~ 8 MB | 单份业务日志的真实上界 |

两个观察：

- **同一份内容出现两次**（`steps[].detail.output` 与 `value`），外加 `meta` 噪声；直接回传模型是纯浪费。
- 读操作体积随电路规模线性增长（管道文本 + 结构化两份），而模型上下文是固定预算。

结论：MCP 层必须做 **投影 + 截断 + 句柄**，不能把业务响应原样塞进 `content`。

### 1.4 token 在业务面的确切语义

- token 是**每次调用的 bearer ticket**，不是会话：`dispatch()` 强制非空，业务包只做透传，不缓存成「当前用户」。
- business 端口的合法性判定与角色路由由中层完成；token 决定五个 role（gui / daemon / command / file / spectre）
  的 `root` 与 `bin`，也就是「连到哪台机的哪个目录」。
- 因此 MCP 层的 token 等价于**身份选择**，而不是普通业务参数。

### 1.5 对 MCP 而言，现状缺什么

| 缺口 | 后果 | 落点 |
|---|---|---|
| 无 `inputSchema` | `tools/list` 无法生成，宿主报错或只能手写 | §3.4 catalog |
| 无 per-operation 描述 | 模型选错工具、猜字段 | §3.4 |
| 结果无投影 | 上下文爆炸、长会话不可用 | §3.5 |
| 无任务句柄 | 长仿真/长导入撞宿主超时 | §3.6 |
| token 无「身份」概念 | 易被写进工具参数与对话历史 | §3.2 |
| 无写操作互斥 | Virtuoso 单会话，并发写未验证 | §3.8 |

---

## 2. 判断：这套业务面天生适合 MCP

- 业务面是「能力注册表 + 参数模型 + 结构化结果」，与 MCP tools 一一对应；HTTP 则要求调用方（AI）
  自己读文档、拼 JSON、猜字段，每次都要重新发现能力。
- 六个 `basic.*` 直通（skill / command / upload / download / gui / spectre）已经覆盖了绝大多数动作——
  **只要 AI 能执行 SKILL、能跑命令、能传文件，它就能完成 90% 的工作**；领域操作只是省 token 的快捷方式。
  这决定了工具分层：直通是底座，领域工具是糖。
- `jsonable()` 已经把 Result 转成 JSON-safe 结构，`Result.ok/error` 已经是现成的 `isError` 判据。

---

## 3. 设计

### 3.1 部署形态

**推荐 A：stdio 薄代理**

```text
AI 宿主 ──stdio(MCP)──> virtuoso-bridge mcp ──HTTP──> 业务端口 ──> 中层 ──> Virtuoso / 命令 / 文件
                            （token 在配置里）      （复用准入、限流、监督、热 reload）
```

优点：不改 `server/api_server.py`；复用项目已经建立的单点准入、线程池上限、`429/503 + Retry-After`、
supervisor reload/restart 语义；MCP 进程无状态、可随时重启；远端场景天然可用（业务端口走 SSH 隧道即可）。

**备选 B：把 MCP face 内嵌进业务进程**（streamable HTTP `/mcp`）。收益是多用户远程共享；
代价是 MCP 规范对 HTTP transport 的要求（`Origin` 校验 MUST、本地绑定 SHOULD、正式认证 SHOULD，
授权走 OAuth 2.1 + Protected Resource Metadata）。**本版不做**，留给 P3。

**不推荐 C：MCP server 直接 import `BusinessServer` 自建 Middle。** 会多出第二份连接池、
第二份 SSH 会话、第二份预算账本，破坏「单一准入点」这个项目花代价换来的不变量。

### 3.2 token 配置模型

```jsonc
// ~/.virtuoso-bridge/mcp/profiles.json   （0600，建议 gitignore）
{
  "default": { "base_url": "http://127.0.0.1:8127", "token": "vb-xxxx" },
  "alice":   { "base_url": "http://127.0.0.1:8127", "token": "..." }
}
```

```jsonc
// 宿主侧（Claude Desktop / Codex / Cursor 等）
{ "mcpServers": { "virtuoso": { "command": "virtuoso-bridge-mcp",
                                "args": ["--profile", "default"] } } }
```

规则：

- **工具参数里没有 token 字段**；凭据只存在于 MCP 进程的配置里，模型不可见、不可改。
  需要切换身份时增加一个 MCP 实例，而不是给模型一个 `token` 参数。
- 优先级：`VB_MCP_TOKEN` 环境变量 > profile 文件 > 启动即报错（缺省不静默降级）。
- **启动自检**：`GET /health` + 一次只读调用（建议 `demo.paths.facts`）；token 无效时 MCP 进程直接
  以清晰错误退出，而不是让模型在第一次业务调用时才发现。
- **审计**：所有 tool call 写 JSONL（剥离 token），落 artifact 目录；AI 驱动的会话需要可复盘。

### 3.3 工具清单与粒度（三层）

**L1 直通（6 个）**——底座，任何版本都保留：

`vb_skill_execute`、`vb_command_run`、`vb_file_upload`、`vb_file_download`、`vb_gui_run`、`vb_spectre_run`

**L2 领域工具（约 20 个）**——按「一个领域一个工具集」聚合，不按操作名平铺：

| 工具 | 覆盖操作数 | 说明 |
|---|---:|---|
| `vb_schematic_read` / `_write` / `_check_and_save` / `_screenshot` | 4 | 语义差异大，保持一操作一工具 |
| `vb_symbol_read` / `_write` / `_check_and_save` / `_generate` / `_screenshot` | 5 | 同上 |
| `vb_layout_read` / `_write` / `_gds` / `_screenshot` / `_display` | 5 | 同上 |
| `vb_maestro_read` / `_write` / `_run` / `_results` / `_gui` / `_export` | 11 | `_gui` 与 `_export` 用 action 枚举收拢（open/close/waveform；history/results/screenshot） |
| `vb_cellview_lib` / `_cell` / `_view` / `_cat` | 22 | 每组一个工具 + `action` 枚举：`list/get/create/copy/delete/rename/bind` |
| `vb_gui_windows` / `_send_key` / `_auto_dismiss` / `_screenshot` | 4 | 与 L1 的 `vb_gui_run` 区分：这里是结构化窗口操作 |
| `vb_netlist_import` | 1 | |

**L3 目录与逃生舱**：`vb_operations_list`（可按包/关键字过滤，返回操作名 + 描述 + schema 摘要）、
`vb_operation_raw(operation, arguments)`（用业务原名调用任意已登记操作）。

理由：61 个工具平铺，按每个工具 100~300 token 估计，是**上万 token 的常驻开销**，
而且工具越多、模型选型越容易退化。L2 的聚合让「一个领域一个入口、动作用枚举」，
同时参数 schema 仍然精确；L3 保证业务包继续增长时 MCP 不被卡住（新增操作立刻可用，只是没有糖）。

命名：`virtuoso.schematic.write` → `vb_schematic_write`。MCP 规范本身不限制工具名字符，
但宿主侧的 function-calling 普遍要求 `[a-zA-Z0-9_-]` 且长度有限（≤64），点号在部分宿主会直接报错；
因此做一次名称映射并保留原名表，`vb_operation_raw` 接受原始点号操作名。

### 3.4 Schema 从哪来：一份 catalog，三处共用

最小改动方案（不动 spec、不动 Request）：

1. 新增 `src/pyapi/catalog.py`：用 `dataclasses.fields` + `typing.get_type_hints` 从 Request 推导基础 JSON Schema
   （`str / int / float / bool / None / list[T] / dict[str, Any]` 已覆盖现有全部 Request），
   再叠加一层**手写元数据覆盖表**（description、单位、取值范围、示例、`read_only`、破坏性标注）。
2. 通过 `GET /api/catalog`（或扩展 `/help`）暴露：`{operation: {package, description, inputSchema, annotations}}`；
   MCP 与 CLI 从同一处取，谁都不手写第二份。
3. 一致性 gate（可自动化）：catalog 的操作集合 **必须等于** `/help` 的操作集合；不等就红灯。
4. P2 可考虑把 Request 逐步换成 pydantic（项目已依赖 pydantic，`Result` 已是 pydantic 模型），
   直接用 `model_json_schema()` 消除手写推导——那是上层动刀，不属于 MCP 首版。

### 3.5 结果投影与上下文预算

| 层 | 内容 |
|---|---|
| `content` | 一句人话摘要 + 关键数字（成功/失败、耗时、条数、关键指标） |
| `structuredContent` | 业务语义主体（`value` / 领域字段）+ `{ok, error}` |
| `resource_link` | 原始完整响应落 artifact 文件后的句柄（`demo.paths.facts.artifact_dir` 是现成落点） |
| 图片 | screenshot 类操作直接作为 MCP `image` content（`local_path` 已是 PNG） |

配套规则：

- 默认 `max_bytes`（建议 32 KB）与 `max_items`；超限返回 `truncated: true` + 句柄 + 收窄建议
  （read 类操作已有 `focus` / `object_filter` / `param_filter`，应在工具描述里主动推荐）。
- 大文本（网表、日志）一律走 resource + 摘要，不进 `content`。
- 业务失败 → `isError: true` + `structuredContent` 保留步骤痕迹；**不要**让模型把 200+`ok=false` 当成功。
- `429`（线程池满）与 `503`（restart 中）不是业务错误：投影成「可重试」，附 `retry_after`。

截图回传是 MCP 相对 HTTP 最高性价比的增量：HTTP 只能给路径，MCP 能让模型真的「看」到原理图、版图、波形。

### 3.6 长任务与进度

业务面其实已经具备任务句柄模型：`virtuoso.maestro.run(blocking=False, poll_interval=...)`
＋ `virtuoso.maestro.read_history`。MCP 直接照搬，不新造异步框架：

- `vb_maestro_run` 默认非阻塞，返回 `history` 句柄与状态；
- `vb_maestro_wait(history, timeout)` 在服务端做有限次数轮询（避免模型自己写循环、发一堆探针）；
- 需要更细粒度时用 MCP `notifications/progress`（宿主支持度不一，作为增强而不是依赖）。

### 3.7 安全 / 权限 / 人在环

- **注解**（MCP 的 `ToolAnnotations`：`readOnlyHint` / `destructiveHint` / `idempotentHint` / `openWorldHint`）：
  read / list / get / screenshot / read_results / read_history → 只读；
  `*.delete`、`*.write`、`gds`、`clear_*`、`write_history` → `destructiveHint=true` 且非幂等。
- **能力档位**（MCP 侧配置项，默认 `standard`）：
  - `read-only`：只注册只读工具（「看波形/看版图/答疑」助手模式）；
  - `standard`：只读 + 领域写操作 + 文件传输；
  - `full`：额外放开 `vb_skill_execute` / `vb_command_run` / `vb_operation_raw`。
- `vb_skill_execute` 与 `vb_command_run` 本质是任意代码执行（等价 shell）。放到 `full`、
  写审计 JSONL、并在描述里明确后果。破坏性工具建议显式 `confirm=true` 参数，
  让「是否真的要删」成为模型必须表态的结构化字段，而不是默认动作。
- **人在环**：MCP 规范建议工具调用始终可被人类拒绝；这套系统还有 GUI 可见性这个天然优势——
  建议默认让操作在 CIW/ADE 中可见，用户可当场监工，而不是全后台黑箱。

### 3.8 并发与串行化：顺手吃掉现有风险

现状风险（见 `doc/report/上层业务包开发状态.md`）：Virtuoso 是单 CIW 会话；maestro 的 GUI/后台会话冲突
曾触发 SIGSEGV；「并发写未覆盖」被明确列为已知限制。而 AI 宿主**天然并行**发 tool call。

MCP 层是天然收口点：

- 写操作按 `(library, cell, view)` 串行（进程内锁 + 队列），读操作允许并发；
- GUI 类操作（open_gui / close_gui / waveform）按会话串行；
- 收到顶层 `429` 时由 MCP 层退避重试，先把抖动挡在模型之外；仍失败才作为可重试错误上报。

这一条是 MCP 相对「裸 HTTP」最实的工程价值：把并发风险集中到一个可测的地方。

### 3.9 resources / prompts（MCP 独有，成本极低）

- `vb://catalog`：操作目录（含 schema 与描述），等价于「AI 版 `/help`」；
- `vb://paths`：本机 work / temp / log / artifact 根（来自 `demo.paths.facts`）；
- `vb://docs/<topic>`：领域参考（SKILL API、netlist 语法、troubleshooting、机制类文档）；
- `vb://artifact/<id>`：最近产物（截图、网表、快照、结果 JSON）。

好处：把「文档/约定/示例」从宿主侧人工粘贴，变成随服务版本一起发布的资源，永不漂移。

prompts 可内置几条高频流程：「建 RC 并跑 AC 看增益」「导入 GDS 并检查版图」「读 Maestro 最近一次结果的关键指标」。

---

## 4. 风险与反直觉点

1. **工具越多 ≠ 越好。** 模型选错工具的成本高于多打一次 `raw`；工具表要按任务聚合，不是按操作名平铺。
2. **token 做成工具参数 = 把凭据写进对话历史**，还可能被日志与审计落盘。必须禁止。
3. **大结果原样回传**是 MCP 最常见的翻车方式：单次调用烧掉几千 token，还挤压后续推理。
4. **官方 SDK 的版本门槛**：`mcp`（PyPI 2.2.0）要求 Python ≥3.10，而本项目 `requires-python >=3.9`。
   要么抬基线，要么首版自研 stdio 适配器（`spec/research/example_calc/adapters/mcp_server.py` 已有可参考的骨架）。
   这是**决策点**，不是实现细节。
5. **并发是最大的隐蔽风险**：AI 并行发调用，Virtuoso 单会话。
6. **HTTP 200 + `ok=false`** 与 MCP `isError` 的语义必须显式对齐，否则模型会静默地把失败当成功。

---

## 5. 落地路线

| 阶段 | 内容 | 验收 |
|---|---|---|
| **P0** | stdio server + 6 个直通 + `vb_operations_list` + `vb_operation_raw` + token 自检；结果先原样回传 | 宿主内跑通 `1+2`、列库、读原理图；无效 token 启动即报错 |
| **P1** | catalog（描述 + schema）+ 领域工具 + 结果投影/截断/artifact link + 图片 content | 大读操作被截断且有句柄；截图在宿主里可见 |
| **P2** | resources / prompts + 能力档位 + 写操作串行锁 + 长任务句柄 + 审计 JSONL | 并发写不再撞车；`vb_maestro_wait` 可完成长仿真 |
| **P3** | 远程内嵌 streamable HTTP + OAuth 2.1 + 多用户 | 远程共享实例可用 |

可自动化的验收门：

- catalog 操作集合 == `/help` 操作集合（防漂移）；
- 每个工具 `inputSchema` 是合法 JSON Schema，且能被对应 Request 成功构造一次；
- MCP e2e：`initialize` → `tools/list` → `tools/call`，加错误路径（未知操作 / 无效 token / 429）；
- 真机回归复用现有 `test/tb` 脚本，不另起一套。

---

## 6. 待拍板问题

1. 部署形态选 A（stdio 薄代理）还是 B（内嵌 streamable HTTP）？——建议 A。
2. 是否把 Python 基线抬到 ≥3.10 以使用官方 `mcp` SDK？——直接决定 P0 用轮子还是自研。
3. 默认能力档位（`read-only` / `standard` / `full`），以及是否默认暴露 `vb_skill_execute`（任意代码执行）。
4. 领域工具粒度：`cellview` 这类 22 操作的包用「一个工具 + action 枚举」，`schematic` / `maestro` 这类语义差异大的
   保持一操作一工具——是否接受这种混合粒度。
5. 多用户：坚持「一个 MCP 实例一个 token」，还是允许同一实例按 profile 切换身份。
