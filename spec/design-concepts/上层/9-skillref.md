# 上层业务包：skillref

> 版本：Draft v8
> 日期：2026-09-21
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：Draft v7（skillref 段加入 `doc_token` 代理账号，读取改为 `common.config` 快照）；Draft v6（**记录"本版不建索引"的决策与实测依据**，见 §6.5）；Draft v5（更正正文层成本口径：可搜索文本只有 223.8 MB；远端 `grep` 0.10–0.15 s、本地纯 Python 189 s，本地模式必须给 `under`）；Draft v4（去掉 `local_dir`）；Draft v3（显式 `source` + `doc_root`，去掉路径探测）；Draft v2（config 方案 A + R1–R7；`search_in` 增 `all`；返回补 `elapsed_ms`）；Draft v1（单一搜索入口）；本文取代设计概念 `9-skill-tooling.md`
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 总述

skillref 是 **SKILL 参考查询包**：一个搜索框 + 一个详情查询，共 **2 个只读业务操作**。

| 操作 | 对应交互 |
|---|---|
| `virtuoso.skillref.search` | 搜索框：一个 `query` 输入 + 一组选项（搜到哪一层、怎么匹配、搜多大范围） |
| `virtuoso.skillref.info` | 结果行点进去：按函数名取该函数的详细文档 |

搜索**不拆成多个操作**：`search_in` 一个参数决定匹配范围（名称 → 词条 → 主题 → 正文，
逐级加深），调用方永远只面对同一个入口与同一种返回结构。

三条不变式：

1. **只读**：不写 Virtuoso、不建 cell、不改库，全部操作只读文档树；
2. **无状态**：包内不建持久索引、不做隐式缓存；远端模式的中间落点固定在
   `temp_dir()/skillref/` 下（§3.4），每请求重新取数，随时可清；
3. **本地/远端同义**：同一操作在两种模式下语义一致，差别只在取数方式（见 §3）；
4. **数据源显式**：本地还是远端、路径是什么，由配置表或请求写明，**包不探测、不猜测**（见 §3.1）。

## 2. 业务操作

### 2.1 读操作总表

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| `virtuoso.skillref.search` | 统一搜索：按 `search_in` 在名称/词条/主题/正文中查 | 定位 doc root → 按范围取数 → 匹配 → 打分排序 | C+D（远端模式） |
| `virtuoso.skillref.info` | 单函数详细文档 | 取 `.tgf` → 查表 → 取 1 个 HTML → 抽取 → Markdown | C+D（远端模式） |

两个操作都是**纯读操作**。本地模式下不调用任何中层接口；远端模式下只用
`run_command`（C）与 `download_file`（D），不使用 Skill / Upload / GUI。

### 2.2 接口简写

S=`execute_skill`、C=`run_command`、U=`upload_file`、D=`download_file`、
G=`run_gui_command`、Sp=`run_spectre_command`。

## 3. 数据源与运行模式

文档树（一个 doc root）里的三类文件，对应三个匹配层次：

| 层 | 文件 | 内容 | 实测规模（IC618） |
|---|---|---|---|
| 词条层 | `<doc_root>/finder/SKILL/**.fnd` | 函数名 + 语法 + 一行描述 | 37 文件 / 2 286 097 B → 9503 条 |
| 主题层 | `<doc_root>/api_more_info/api_more_info.tgf` | 函数名 → HTML 文件 + topic | 9730 行 / 3987 个目标文件 / 924 044 B |
| 正文层 | `<doc_root>/**.html/.htm/.txt/.xml/.json` | 参考手册正文与辅助文本 | **可搜索子集 223.8 MB / 9 426 文件**（`.html` 8 597 / 209.6 MB 为主；整树 6.5 GB 的其余部分是 mp4/gif/pdf/png 与 Cadence 自带 `.cfs` 索引，不参与检索） |

### 3.1 数据源：显式配置，不探测

数据源由**三个字段**完全确定：`source`（`local` / `remote`）× `doc_root`（绝对路径）× `doc_token`（远端执行所用代理账号）。
取值顺序（先到先用，结果原样回带 `source` 与 `doc_root`，便于调用方复用与排错）：

1. **请求参数** `source` + `doc_root`（最高优先级，用于一次性换树/调试）；
2. **配置表**：`common.config` 快照的 `skillref` 段
   （`{"skillref": {"source": "remote", "doc_root": "/opt/eda/cadence/IC618/doc", "doc_token": "<已注册 user 的 token>"}}`，见 §6.1 R2）；`doc_token` 只来自配置，请求参数不可覆盖；
3. 两级都不完整 → **业务失败**（`ok=false`），文案写明
   "skillref 数据源未配置：请在 config.json 的 skillref 段给出 source + doc_root（remote 模式另需 doc_token），或由请求参数给出 source + doc_root"。

两个操作都先经只读查询 `query` 校验调用者 token；remote 模式后续的 C/D 调用以配置的 `doc_token` 作为中层 token 执行。

**不做路径探测**：不执行 `which virtuoso`、不做父目录上溯、不按"本地看得见就本地"猜测
（旧 `skill_finder.discover()` 那套 discovery 本版不实现）。理由：探测依赖远端 shell 环境，
失败时无法区分"没装 Virtuoso"与"装了但文档树在别处"；用户视角下不如把"哪台机、哪个路径"
一次配清，行为可预期。包同样不读 `VB_*`/`.env`（上层 §5.2）。

字段校验（请求与配置同口径，违反即业务失败）：

| 字段 | 规则 |
|---|---|
| `source` | 必须是 `local` 或 `remote`（大小写不敏感） |
| `doc_root` | 非空绝对路径字符串、不含 NUL；`local` 模式要求在本进程可见，`remote` 模式是业务服务器上的绝对路径 |
| `doc_token` | 只来自配置、请求参数不可覆盖；`remote` 模式必填，必须对应一个已注册 user（控制面 PUT 时校验），`local` 模式忽略 |

**只有这三个字段**——`source` + `doc_root` 是数据源位置，`doc_token` 是远端执行代理账号（必须注册一个 user，用该 user 的远端执行）。
远端模式下"下到本机哪里"是包的内部实现（§3.4），不占用户参数。

### 3.2 local 模式（`source="local"`）

直接读本机文件、不调用任何中层业务接口；`doc_root` 不可见时业务失败
（错误文案带该路径），不退回远端、也不猜别的路径。

### 3.3 remote 模式（`source="remote"`）

`doc_root` 是 doc 代理账号所注册 user 的业务服务器上的绝对路径（如 `/opt/eda/cadence/IC618/doc`）→ 以 `doc_token` 用 C+D 取数：

| 层 | 取数方式 | 体积（实测） |
|---|---|---|
| 词条层 | 一次 `download_file(<doc_root>/finder/SKILL, <temp_dir()/skillref/…>, recursive=True)`（落点由包内部决定，§3.4） | 2.4 MB（tar.gz 压缩后更小） |
| 主题层 | 一次 `download_file(<doc_root>/api_more_info/api_more_info.tgf, ...)`；命中后只再取 1 个 HTML | 924 KB + 单文件 |
| 正文层 | 一次 `command.run` 跑远端候选搜索（`grep -r -l -m1`，形状见 `src_bak/virtuoso_bridge/virtuoso/docs_search.py:417-459`）→ `download_file` 取候选（≤ `max_candidates`）→ 本地打分与摘要 | 搜索本身 0 传输（整树 0.10–0.15 s）；候选 ≈190–240 KB/个、≈1.9 s/个 |

路径纪律：远端路径一律按 POSIX 语义拼接，**禁止**对远端路径调用 `Path.exists()`。

### 3.4 远端取数的落点（包内部，不是用户参数）

- 远端模式要把 `.fnd` / `.tgf` / 候选正文落到本机才能解析：落点固定为
  `common.paths.temp_dir()/skillref/<doc_root 摘要>/`，由包自己管理，**不对外暴露参数**；
- 每次请求重新取数，不做隐式新鲜度判断、不承诺复用；同一次请求内的多个层次共享同一份落点；
- 落点内容随时可被清理，不影响正确性（包不把它当缓存）。

## 4. `virtuoso.skillref.search`

唯一搜索入口。一次请求 = 一个 `query` + 一组选项，选项只影响"搜到哪一层"与"怎么匹配"。

### 4.1 输入

```json
{
  "query": "ground bounce",
  "search_in": "entry",
  "mode": "fuzzy",
  "under": ["cpf_ref"],
  "limit": 20,
  "snippet": true,
  "source": "remote",
  "doc_root": "/opt/eda/cadence/IC618/doc"
}
```

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `query` | 是 | — | 唯一输入框；多词按 AND 处理（沿用旧 `_query_terms` 口径） |
| `source` | 否 | 配置表值 | `local` / `remote`；与 `doc_root` 一起确定数据源（见 §3.1） |
| `search_in` | 否 | `entry` | 匹配范围，逐级加深：`name` / `entry` / `topic` / `body`；`all` 是 `body` 的别名（见 §4.2） |
| `mode` | 否 | `fuzzy` | 名称/标题列的匹配方式：`fuzzy` / `prefix` / `suffix` / `exact` / `regex`（见 §4.3） |
| `under` | 否 | — | doc root 下的相对子目录列表（如 `["cpf_ref"]`），限定正文层扫描范围 |
| `limit` | 否 | 20 | 结果条数上限（1–200） |
| `max_candidates` | 否 | 50 | 正文层候选上限（远端模式下同时限制下载文件数） |
| `max_files` | 否 | 5000 | 正文层未给 `under` 时的扫描文件上限，超出回 `truncated=true` |
| `snippet` | 否 | `true` | 是否回带命中片段 |
| `doc_root` | 否 | 配置表值 | 绝对路径；校验规则见 §3.1 |
| `timeout` | 否 | — | 单次 C/D 调用的超时（正文层远端候选搜索默认 120 s） |

### 4.2 匹配范围 `search_in`（逐级加深）

| 取值 | 搜什么 | 命中形态 | 成本（IC618 实测） |
|---|---|---|---|
| `name` | `.fnd` 函数名 | `{name, syntax}` | 与 `entry` 同（同一份索引解析） |
| `entry` | 函数名 + 语法 + 一行描述 | `{name, syntax, description}` | 词条层取数 2.4 MB / 1.16 s（远端） |
| `topic` | `entry` + `.tgf` 主题名与目标文件名 | `{topic, target_path, anchor}` | 追加 tgf 924 KB |
| `body` | `topic` + 正文文件标题/相对路径/内容 | `{title, relative_path, line, snippet}` | 远端 `grep` 整树 0.10–0.15 s + 逐候选下载 ≈1.9 s/文件；本地纯 Python 全扫 189 s（须给 `under`） |

`name` 与 `entry` 的区别只在**是否把语法/描述并入匹配面**，两者共用同一份 `.fnd` 解析。
`all` = `body`（最深一档，给"我什么都想搜"的用户一个不用记顺序的取值）。

**不做隐式扩层**：某一档没命中就返回空，**不会**自动往更深的层再搜一遍
（用户要更深就改 `search_in`）；这样同一 query 的结果可预期、成本可预算。

### 4.3 `mode` 语义

`mode` 只作用于**名称/标题列**（函数名、topic 名、正文标题）；更深层字段
（语法、描述、正文）一律按**大小写不敏感的子串 AND** 匹配，不受 `mode` 影响：

| mode | 名称列语义 |
|---|---|
| `fuzzy`（默认） | 大小写不敏感子串 |
| `prefix` | 前缀（大小写敏感） |
| `suffix` | 后缀（大小写敏感） |
| `exact` | 全等（大小写敏感） |
| `regex` | Python 正则（`re.IGNORECASE`；非法正则回空结果） |

### 4.4 打分与排序

同一层内按分数降序、同分按名字/路径升序；跨层排序按层序（名称 → 词条 → 主题 → 正文）。

| 层 | 加分项 |
|---|---|
| 名称 | 全等 100 / 前缀 80 / 子串 60 |
| 词条 | 语法命中 +20 / 描述命中 +10 |
| 主题 | topic 全等 90 / 子串 70；目标文件名命中 +10 |
| 正文 | 标题命中 40 / 相对路径命中 30 / 正文命中 20；每个额外查询词 +5 |

同一逻辑位置（同文件 + 同 topic）在多层命中时合并为一条，保留最高层并保留
所有命中原因，与旧实现 `docs_search.py:1204-1223` 的去重口径一致。

### 4.5 返回

`results[]`：`layer`（`name`/`entry`/`topic`/`body`）、`score`、
`name` 或 `title`、`syntax` / `description` / `target_path` / `relative_path` / `line`
（按层给）、`snippet`、`why`（命中字段列表）；
外加 `query`、`search_in`、`layers_run`、`scanned_files`、`truncated`、
`doc_root`、`source`（`local`/`remote`）、`elapsed_ms`。

未命中返回空 `results` 且 `ok=true`（"查不到"是正常业务结果，不是错误）。
命中 `entry` 层时结果里一定带 `name`，可直接喂给 `info`；命中 `body` 层时带
`relative_path`（`doc_root` 下可点开的文件），便于人复查原文。

### 4.6 上限与边界

1. **正文层按模式分派，两边差约 1000 倍**（2026-09-21 真机实测）：
   - **远端**：一次 `command.run` 跑 `grep -r -l -m1`，扫整树文本子集（223.8 MB / 9 426 文件）
     耗时 **0.10–0.15 s**，再按候选逐个下载（每文件 ≈1.9 s，受 `max_candidates` 限制）；
   - **本地**：纯 Python 扫描整棵树 **189 s**（旧实现口径；`rg` 对照 36.8 s 冷 / ≈2 s 热）。
     因此 `search_in="body"` 在 **local 模式必须给 `under`**（如 `["cpf_ref"]`，
     40 文件 / 2.8 MB / 0.7 s）；未给时按 `max_files` 截断并回 `truncated=true`；
2. 本版**不建持久索引**（旧 `docs_search.py` 的 SQLite v3 不移植）；决策依据见 §6.5；
3. 远端正文层的候选搜索在业务服务器上执行（一次 `command.run`），下载候选后
   在本地打分与出摘要；`max_candidates` 同时是下载上限；
4. `timeout` 显式传给每次 C/D 调用；正文层远端候选搜索默认给 120 s，调用方可覆盖。

## 5. `virtuoso.skillref.info`

按函数名取详细文档（搜索结果行的"详情页"），等价于旧 `skill-info` CLI
（`src_bak/virtuoso_bridge/cli.py:1811`）。

| 参数 | 必填 | 默认 | 说明 |
|---|---|---|---|
| `name` | 是 | — | 函数名；自动尝试 `_ocean` / `_viva_skill` 后缀回退 |
| `include_raw` | 否 | `false` | 是否回带 `raw_html`（默认只回 Markdown） |
| `source` / `doc_root` / `timeout` | 否 | — | 见 §3 |

语义：

1. 取 `<doc_root>/api_more_info/api_more_info.tgf`，按**小写键**查表
   （首个重复项胜、`NULL` topic 归一为 `None`）；
2. 目标 HTML = `<doc_root>/<去掉 $ 前缀的 file_path>`，只取命中的那 1 个文件；
3. 抽取顺序（不可调换，旧实现 `skill_finder/more_info.py:157`）：
   现代 `<!-- [TOPIC_START_OPEN] ... -->`…`<!-- [TOPIC_END] -->` →
   legacy 锚点/标题定位（到下一个同级或更高级标题结束）→
   该文件只索引一个函数时整页兜底；
4. HTML → Markdown 用 stdlib 转换（`tools/skill_doc_server.py:485` 的口径），不引入第三方依赖。

返回：`found`、`func_name`、`file_path`、`topic`、`plain_text`、
`raw_html`（仅 `include_raw=true`）、`doc_root`、`source`。
未命中返回 `found=false` 且 `ok=true`。

## 6. 与既有 spec 的关系（差异与待确认）

### 6.1 配置表扩展：已定方案 A（`config.json` 增加 `skillref` 段，已由[顶层补充 §5](../顶层/add-控制面与业务面.md)落地）

`skillref` 段含 `source`/`doc_root`/`doc_token` 三个字段；PUT 只覆盖请求里出现的键、
`GET` 回带时 `doc_token` 脱敏等结构口径以[顶层补充 §5](../顶层/add-控制面与业务面.md)为唯一口径，本文不复制。

实现口径（本包）：读取顺序 = 请求参数 `source`+`doc_root` → `common.config` 快照的
`skillref.source`+`skillref.doc_root`+`skillref.doc_token` → 业务失败（不探测）。
`doc_token` 只来自配置；remote 模式以它作为中层 token 执行 C/D。
`skillref` 段缺失不影响进程启动，只让 skillref 操作返回可读的失败文案。

### 6.2 单一搜索入口

v1 曾把"词条检索"与"多层检索"拆成 `find` / `search` 两个操作；本版合并为 `search`
一个入口，`search_in` 是唯一控制匹配深度的参数。旧 `skill-find` CLI 的语义对应
`search_in="name"`（只匹配函数名）。

### 6.3 本地直读不占中层接口

旧文件 §2 待修订已写"纯本地解析不占中层接口"；本版把它写成正式口径（§3.2），
两个操作在本地模式下接口列均为空。

### 6.4 与 `tools/skill_doc_server.py`（8123）的关系

8123 是**开发辅助服务**（本地单文档根、无 token、手工启动），不属于四层链路；
本包是**业务面能力**（经 8127 + token，本地/远端双模式，四层匹配）。
两者共享同一套解析口径（`.fnd` / `.tgf` / HTML→Markdown），实现以本包为唯一维护点。

### 6.5 决策记录：本版为什么不建索引

2026-09-21 用旧实现（schema v3）在真实文档树上实测：

| 项 | 实测 |
|---|---:|
| 首次建索引 + 查一次（223.8 MB 文本 / 71 319 文件） | 187.66 s |
| 索引体积 `index.sqlite` | 159.5 MB |
| 第二次查询（复用索引） | 0.21 s |
| 对照：不建索引（本地直扫 / 远端 `grep`） | 189 s / **0.10–0.15 s** |

1. **远端模式建索引是负收益**：远端 `grep -r` 整树 0.1 s，建索引反而要先把 224 MB 文本
   拉回来、花 ≥190 s 建库、占 160 MB 磁盘；
2. **本地模式才值**（190 s → 0.21 s），但那只是"本机有文档树副本"的便利路径，
   不是本版的主线场景；
3. **旧索引有陈旧性缺陷**：有效性判据只比 `schema_version` 与 `doc_root`
   （`src_bak/virtuoso_bridge/virtuoso/docs_search.py:779-788`），不检测文档树变化
   → 文档升级后索引静默过期。若将来要建，必须补"文档树指纹"（文件数 + 最新 mtime），
   并让索引路径由调用方显式给出（满足上层 §3.2"确定性定位"）。

本版结论：**不建索引**；正文层按 §4.6 的"远端 `grep` 候选 / 本地限 `under`"实现。

## 7. 已知限制

1. 只覆盖 Cadence 自带的 SKILL 索引；第三方/客户自定义 API 不在 `.fnd` 中；
2. 正文层无持久索引：本地模式全树扫描 ~190 s（必须给 `under`）；远端模式靠 `grep` 候选
   （0.10–0.15 s）+ 逐候选下载（≈1.9 s/文件）；
3. 正文层只读文本类后缀（`.html/.htm/.txt/.xml`），不含 PDF、图片与二进制；
4. `info` 对未知代际的 HTML 可能退化为整页兜底（仅当该文件只索引一个函数）；
5. 远端正文层依赖远端 `find`/`grep`（`LC_ALL=C grep -F -I`），依赖远端 shell 环境；
6. 正文层远端的 `line` 只在本地算（候选下载后重扫），远端候选本身只保证文件级定位。
7. **不做路径探测**：`source` 与 `doc_root` 必须由配置表或请求给出；配错只会得到
   "路径不存在/不可见"的明确失败，不会自动换树、也不会回头去猜；
8. **不做拼写纠错、同义词与自然语言理解**：`mode` 只有 §4.3 的五种；某一档没命中
   也不会自动往更深的层再搜一遍（§4.2）。

## 8. 验收

脚本 `test/tb/skillref_e2e_tests.py --transport direct|http`，产物落
`test/tb/artifacts/skillref-tb/TEST_PLAN.md` + `TEST_REPORT.md`。

| 组 | 用例 |
|---|---|
| search 范围 | `search_in` 四档各 1（`name` / `entry` / `topic` / `body`），断言层次与命中面一致 |
| search 模式 | 五种 `mode` 各 1 + `limit` 截断 + 未知查询回空 |
| search 正文层 | `under=["cpf_ref"]` 命中 `ground bounce`（0.7 s 级）；缺 `under` 时 `truncated` 边界 |
| info | 现代标记命中（`dbOpenCellViewByType`）、legacy 命中、`NULL` topic 兜底、`_ocean` 回退（`ocnPrint`）、未知函数 `found=false` |
| 数据源 | 请求参数给定（`local` / `remote` 各 1）、配置表给定（1）、未配置 → 明确失败（1） |
| 失败 | local 路径不存在、remote 路径不可见、`source` 非法值、正文层超 `max_files` |

真机基线（2026-09-21 实测，作为断言下限）：

| 项 | 值 |
|---|---|
| `.fnd` | 37 文件 / 2 286 097 B → **9503 条** |
| `.tgf` | 924 044 B / 9730 行 / 3987 个目标文件 |
| 远端 doc root（实测路径） | `/opt/eda/cadence/IC618/doc`（同版本 `virtuoso` 在 `/opt/eda/cadence/IC618/tools/dfII/bin/`；本版只作为配置示例，不做探测） |
| 远端词条层取数 | 一次递归下载 1.16 s（rc=0） |
| 正文层限定 `cpf_ref`（本地扫描） | 0.59–0.71 s，命中 `reference.html` 的 `ground bounce` |
| 正文层整树（远端 `grep` 候选） | 0.10–0.15 s（文本子集 223.8 MB / 9 426 文件） |
| 正文层整树（本地纯 Python，对照） | 189.17 s |
| 远端单文件下载 | `.tgf` 924 KB → 2.58 s；HTML 188 KB → 1.86 s；243 KB → 1.96 s |

## 9. 证据索引

| 证据 | 位置 |
|---|---|
| 旧 finder 探测/解析/搜索 | `src_bak/virtuoso_bridge/virtuoso/skill_finder/__init__.py:75/103/111/155/191`、`parser.py:44/50/92` |
| 旧 More Info | `src_bak/virtuoso_bridge/virtuoso/skill_finder/more_info.py:53/79/84/131/157/184` |
| 旧文档检索 | `src_bak/virtuoso_bridge/virtuoso/docs_search.py:24/117/191/272/417/742/965` |
| 旧 CLI 入口 | `src_bak/virtuoso_bridge/cli.py:1774/1811/1827` |
| 8123 参考实现 | `tools/skill_doc_server.py:34/74/100/118/197/485/523/664` |
| 调研与方案 | `doc/report/skilltooling-调研与上层包设计方案.md` |
| 远端取数成本评估（实测） | `doc/report/skillref-远端取数成本评估.md` |
| 探针 | `test/tb/skill_tooling_probe.py`、`test/tb/docs_search_probe.py` |
| 实测记录 | `test/tb/artifacts/skill-tooling-tb/docs-search-probe-20260921.log` |
