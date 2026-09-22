# skill_tooling 调研与上层包设计方案

> 日期：2026-09-21
> 作者：上层业务包开发助手（与 Euclid 并行的上层助手）
> 状态：**调研完成；待主开发拍板 §6 的 5 个待确认项后开写实现**
> 依据：`spec/design-concepts/上层/9-skillref.md`（Draft v1，取代 9-skill-tooling）、`spec/design-concepts/上层/1-上层.md`（Draft v14，Normative）
> 证据：`doc/report/_explore/D_library_skill_tooling_gui.md`、`src_bak/`、`tools/skill_doc_server.py`、2026-09-21 真机实测（见 §4）
>
> **后续裁定（2026-09-21，主开发指示）**：包名定为 **skillref**，只做查询，
> 且**搜索只有一个入口**：`virtuoso.skillref.search`（一个 `query` + `search_in`
> 控制匹配范围：`name` / `entry` / `topic` / `body`）+ `virtuoso.skillref.info`（详情）；
> `load_il`、`compose_skill` 不做，`find` 不单列。**§5.3 的操作表已被此裁定取代**。
> 正式口径见 `spec/design-concepts/上层/9-skillref.md`（Draft v2，取代 `9-skill-tooling.md`）。

## 0. 结论（TL;DR）

1. 业务操作沿用 spec 表的五个：`compose_skill` / `find_skill` / `skill_info` / `doc_search` / `load_il`。
   其中前四个是「读文档树 + 纯 Python 解析」，只有 `load_il` 是写操作（U+S）。
2. 数据源采用**三态策略**：显式 `doc_root` 优先 → 本地可见就直读（零中层开销）→
   本地不可见才走 `command.run` 探测 + `download_file` 拉取。纯远端部署才付出传输成本。
3. 传输量已被真机实测钉死：`.fnd` 索引 **37 文件 / 2.4 MB**（tar.gz 后约 0.4 MB）、
   `api_more_info.tgf` **924 044 B**。一次递归 `download_file` 就够，
   **不需要**旧版那套「SQLite 索引 + `remote_records.jsonl.gz` 索引流」（那是为 6.5 GB 全站文档设计的）。
4. 解析逻辑不重写：`tools/skill_doc_server.py`（现跑在 8123）已经把 `.fnd` 解析/搜索、
   `.tgf` 索引、HTML→Markdown 全部内联成 **stdlib-only** 实现；
   搬进 `src/pyapi/packages/_skill_docs.py` 即可，连 `markdownify` 依赖都不用引。
5. **不引入任何隐式缓存**。旧版把 `.fnd` 落到 `cache_dir("skill_finder")/<host>`、
   把文档索引落到 `cache_dir("docs_search")`，这与 `1-上层.md` §3.2「不持有跨请求状态：没有缓存」直接冲突；
   新包远端模式每次请求重新拉取（0.4 MB 级），或由调用方显式给 `local_dir`。
6. `doc_search` 是唯一的重活（doc 树 6.5 GB / 71 316 文件），建议 v1 不做，
   或只做「调用方显式给 `doc_roots` + 有界扫描」的简化版；SQLite 索引与远端索引流放 v2（§5.5）。

## 1. 旧代码盘点：五个操作各是什么

| spec 操作 | 旧实现位置 | 形态 |
|---|---|---|
| `compose_skill` | `src_bak/virtuoso_bridge/virtuoso/basic/composition.py:8` `compose_skill_script()` | 纯 Python，12 行 |
| `find_skill` | `src_bak/.../virtuoso/basic/bridge.py:859` `VirtuosoClient.find_skill()` + `virtuoso/skill_finder/` | 探测 + 递归下载 + 本地解析 |
| `skill_info` | `bridge.py:998` `get_skill_more_info()` + `skill_finder/more_info.py` | 按需下载 1 个 tgf + 1 个 HTML |
| `doc_search` | `virtuoso/docs_search.py`（47 KB）+ `bridge.py:1242` | 全站索引 + SQLite + 打分 |
| `load_il` | `bridge.py:1345` `load_il()` | 上传 + `load("path")` |
| CLI 入口 | `src_bak/virtuoso_bridge/cli.py:1774/1811/1827`（子命令），`:1988` 分派 | `skill-find` / `skill-info` / `doc-search` |

注意：新仓库的 console script 已改指 `register.server:main`（`pyproject.toml`），
**这三个 CLI 动词在新 `src/` 里不存在**，属于「旧 CLI 已删除、上层业务未开工」
（`doc/report/代码梳理.md:197`）。也就是说 skill_tooling 是一个真正从零开始的上层包。

## 2. 实现原理（必须保留的部分）

### 2.1 定位文档树：`which virtuoso` + 父目录上溯

`skill_finder/__init__.py:75 discover()` → 本地 `:103` / 远端 `:111`：

1. 远端先 `csh -c 'source <VB_CADENCE_CSHRC>; env'` 取回 `PATH/LM_LICENSE_FILE/CDS*`，
   再 `which virtuoso`；
2. 从 `virtuoso` 可执行文件路径逐级上溯，找第一个含 `doc/finder/SKILL` 的目录
   （`:155 _walk_up_find`，远端是等价的 bash 循环）。

新架构里这段不能再读 `VB_CADENCE_CSHRC`（`1-上层.md` §5.2 禁止读 `VB_*`/`.env`），
但 `which virtuoso` + 上溯的**算法**可以直接搬到 `command.run` 上执行。

### 2.2 `.fnd` 格式与解析

`skill_finder/parser.py:44` 的 3 行记录正则：

```text
\("([^"]+)"\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\n\s*"((?:[^"\\]|\\.)*)"\s*\)
```

即 `("函数名" "语法" "一行描述")`；`;` 开头的行是注释；`:92 parse_fnd_directory`
递归扫描并按**函数名首个出现者胜**去重。`source_file` 保留 `.fnd` 文件名（可追溯）。

### 2.3 五种搜索模式

`__init__.py:191 search()` 分派到 `:239-263`：`exact`（区分大小写全等）、
`prefix`/`suffix`（大小写敏感前缀/后缀）、`regex`（`re.IGNORECASE`，非法正则返回空）、
`fuzzy`（大小写不敏感子串）。`include_desc=True` 时把描述字段并入非 exact 模式的匹配面。
结果**按 name 排序**后 `limit` 截断（不是按相关度——旧实现没有打分，这点保持即可）。

### 2.4 More Info：`.tgf` 索引 + 两种 HTML 代际

`more_info.py:53 parse_tgf_index()` 解析 `api_more_info.tgf` 的两种行
（引号 topic 或 `NULL`），键小写、首个出现者胜；`:79 resolve_doc_path()` 把
`$skdfref/cvio.html` 这类 `$` 前缀路径解析到 `<doc_root>/<rel>`。

HTML 抽取顺序（`:157 extract_doc_section()`，顺序不能改）：

1. 现代 More Info 标记 `<!-- [TOPIC_START_OPEN] ... [TOPIC_START_ATTR]text=<topic> -->`
   … `<!-- [TOPIC_END] -->`（`:84`）；
2. legacy：`<a id|name="<topic>">` 锚点 → 最近的上层标题 → 到下一个同级/更高级标题结束（`:131`）；
3. 标题纯文本等于 topic（处理锚点把函数名劈开的情况）；
4. 可选整文件兜底（只对「一页一函数」的 legacy 页面开）。

`:184 html_to_plain_text()` 先删空/自闭 `<code>` 再转 Markdown（旧版用 `markdownify`）。

### 2.5 `doc_search`：为什么重

`docs_search.py` 是**全站**文档检索：`resolve_doc_roots`（`:117`）解析显式根/env/安装根，
`iter_doc_files` 扫 `{.html,.htm,.txt,.xml,.json,.tgf}`，`scan → score → dedup`（`:556-676`），
落到 schema v3 的 SQLite（`:24`、`:965`），远端则用内嵌 py2/3 脚本产
`remote_records.jsonl.gz`（`:1240 _remote_doc_index_command`，**硬编码 900 s 超时**，`:884`）
再下载建本地索引。工程量大、且与「无状态」冲突（旧版索引落在 cache 目录）。

### 2.6 旧版缓存（新架构必须去掉的部分）

| 旧行为 | 位置 | 新架构处置 |
|---|---|---|
| `.fnd` 下载到 `cache_dir("skill_finder")/<host>`，用 `.source_dir` 标记判断是否重下 | `bridge.py:219/859-960` | **去除**。远端模式每次现拉（0.4 MB），或由调用方给 `local_dir` |
| 文档索引落到 `cache_dir("docs_search")`，用 manifest 判有效 | `bridge.py:1242-1340`、`docs_search.py:779` | **去除**；要落盘必须由调用方显式给路径 |
| cache 以 host/profile 命名 | `bridge.py:219` | 新模型只有 token/role，不做 host 推断 |

## 3. 独立 server：`tools/skill_doc_server.py` 是什么

它是**把上面 2.2–2.4 抽出来的自包含只读查询服务**（stdlib only，不 import
`virtuoso_bridge`、不连 daemon/SSH），直接读本地文档树：

| 位置 | 内容 |
|---|---|
| `:34` | `DEFAULT_DOC = C:\Users\user\Desktop\doc` |
| `:74/100` | `.fnd` 解析（与 `parser.py` 同正则） |
| `:118/128` | `SKILLFinder.search`（五模式，与 `__init__.py:191` 同语义） |
| `:197/229/263` | `.tgf` 索引、现代/legacy 主题抽取（与 `more_info.py` 同语义） |
| `:485` | `html_to_plain_text`：**用 `html.parser.HTMLParser` 重写，去掉了 markdownify 依赖** |
| `:611/664/685/705` | `HELP_DOC` 与 `/api/help`、`/api/find`、`/api/info`、`/api/stats` |
| `:964` | `main()`：`--doc` / `--host` / `--port`（默认 8123） |

意义：**这个文件的解析层就是新上层包的现成私有依赖**。它验证了两件事：
① 解析不依赖 Cadence/网表/virtuoso_bridge；② 用 stdlib 就能替代 markdownify。
它缺的是「数据从哪来」——即远端文档树的取数路径，这正是上层包要补的部分。

## 4. 真机实测事实（2026-09-21）

### 4.1 本地服务（已由本次调研拉起，PID 29688）

```text
GET http://127.0.0.1:8123/api/stats
=> {"doc_root": "C:\\Users\\user\\Desktop\\doc", "total": 9503}
GET /api/find?q=hiGetCurrentWindow&mode=fuzzy&limit=3
=> hiGetCurrentWindow  ::  hiGetCurrentWindow() => w_windowId / nil
GET /api/info?name=dbOpenCellViewByType
=> found=True file=$skdfref/cvio.html plain_text_len=5719
```

本地副本规模：`doc/finder/SKILL` **37 个 `.fnd`、2 286 097 B**；`api_more_info.tgf` **924 044 B**。

### 4.2 远端（`wsl-gent`，token `vb-vblog`，经 `basic.command.run`）

```text
which virtuoso
=> /opt/eda/cadence/IC618/tools/dfII/bin/virtuoso
ls -d /opt/eda/cadence/IC618/doc/finder/SKILL  => 存在
find ... -name '*.fnd' | wc -l                => 37
du -sh .../finder/SKILL                       => 2.4M
ls -l .../api_more_info/api_more_info.tgf     => 924044 B（2023-10-09）
which python3                                 => /usr/local/bin/python3
du -sh /opt/eda/cadence/IC618/doc             => 6.5G
```

结论：本地副本与远端 IC618 文档树**同版本**（文件数、tgf 字节数一致）。
`which virtuoso` + 上溯到 `doc/finder/SKILL` 的旧算法在当前环境**仍然成立**，
可以直接作为新包的远端探测命令。

### 4.3 设计 PoC 已跑通（download → parse → search）

用一次中层调用把远端索引树搬到本机，再用 §3 的解析器复算：

```text
POST /api/operation basic.file.download
  remote_path=/opt/eda/cadence/IC618/doc/finder/SKILL
  local_path=test/tb/artifacts/skill-tooling-tb/probe/finder/SKILL  recursive=true  timeout=120
=> rc=0, kind=command, 耗时 1.16 s

python test/tb/skill_tooling_probe.py --check --compare-8123
=> fnd_files=37, entries=9503, exact_hits=[dbOpenCellViewByType],
   matches_service=true
=> PASS skill-tooling data path (download -> parse -> search)
```

两点结论：① 远端模式的总成本 ≈ 一次 C/D 调用 + 1 s 级传输，方案可行；
② 本地解析结果与 8123 服务逐条一致（9503 条），说明解析层可以直接复用。

## 5. 推荐设计

### 5.1 文件与注册

| 文件 | 作用 |
|---|---|
| `src/pyapi/packages/skill_tooling.py` | 业务包本体：`Package` + 每操作一对 Request/Result + `OPERATIONS` |
| `src/pyapi/packages/_skill_docs.py` | 私有解析库（stdlib only）：`.fnd` 解析/搜索、`.tgf` 索引、HTML 抽取与 Markdown 化；来源 = `tools/skill_doc_server.py` |
| `src/pyapi/packages/__init__.py` | 导出 `SkillToolingPackage` 等 |
| `src/server/api_server.py:305 PACKAGES` | 增一行 `("pyapi.packages.skill_tooling", "Package", "OPERATIONS")` |

操作名建议（点分英文分段，与既有 `virtuoso.cellview.*` / `virtuoso.symbol.*` 一致）：
`virtuoso.skill.compose`、`virtuoso.skill.find`、`virtuoso.skill.info`、
`virtuoso.skill.load_il`、`virtuoso.skill.doc_search`（若做）。

### 5.2 数据源三态（本方案的核心）

每个读操作统一走同一个解析器（内部私有函数 `_resolve_doc_root`）：

1. **显式本地根**：请求给了 `doc_root` 且本进程可见（`Path(doc_root).is_dir()`）→ 直读，
   **零中层调用**。覆盖「客户端已有文档树副本」的场景（本机 `C:\Users\user\Desktop\doc`）。
2. **远端探测**：未给 `doc_root`（或本地不可见）→ `command.run`：
   `which virtuoso` → bash 上溯找 `doc/finder/SKILL` → 返回 `<doc_root>`。探测失败即业务失败。
3. **远端取数**：拿到远端根后 `download_file(<remote>/finder/SKILL, <local_dir>, recursive=True)`，
   落点由调用方显式给 `local_dir`，未给则落 `common.paths.temp_dir()/"skill_tooling"/...`（确定性，可清理）。

Result 里回带 `doc_root` 与 `source`（`local` / `remote`），调用方可把发现结果原样传回下一次请求。

### 5.3 各操作形态

| 操作 | 请求要点 | 步骤 | 主要返回 |
|---|---|---|---|
| `virtuoso.skill.compose` | `commands[]`、`wrap_in_progn=True` | 纯 Python：过滤空白 → 单条且已 `progn(` 则保留 → 换行 join → 可选包 `progn(...)`；空批 `ValueError` | `script` |
| `virtuoso.skill.find` | `query`、`mode`(fuzzy/prefix/suffix/exact/regex)、`limit`、`include_desc`、可选 `doc_root`/`local_dir`、`timeout` | 解析根 → （远端才）拉 `.fnd` → 本地解析去重 → 匹配 → 排序截断 | `entries[]`(name/syntax/description/source_file)、`doc_root`、`source`、`total` |
| `virtuoso.skill.info` | `name`、可选 `doc_root`/`local_dir`/`include_raw` | 解析根 → 取 `api_more_info.tgf`（本地直读或下载）→ 查表（含 `_ocean`/`_viva_skill` 回退）→ 只下载命中的那 1 个 HTML → 抽取 → Markdown | `found`、`func_name`、`file_path`、`topic`、`plain_text`、可选 `raw_html` |
| `virtuoso.skill.load_il` | `local_path`、`remote_path`、`timeout` | `upload_file` → `execute_skill('load("<escaped>")')` | `status/output`、`uploaded`、`skill_command` |
| `virtuoso.skill.doc_search` | 见 §5.5 | — | — |

纪律要点：
- 远端模式下 `.fnd` 只看 `<doc_root>/finder/SKILL`，tgf 只看 `<doc_root>/api_more_info/`；
  路径一律 `posixpath` 语义拼接，**不要**对远端路径调 `Path.exists()`（`D` 报告 §7 已列为红线）。
- 每个中层调用都带请求里的 `token` 原样透传；超时显式给（默认 30 s 不够搬运时给 120 s）。
- 失败保留步骤痕迹（`discover` / `fetch` / `parse` 三步各自 ok/detail），不把「探测不到文档树」伪装成空结果。

### 5.4 为什么**不**让包内直连 8123 那台服务

`1-上层.md` §5.1 明确：包不得接触端口/隧道/传输，只能调五个中层接口；
且 8123 是**手工启动的开发辅助服务**（本次是人工拉起的），把它变成业务依赖等于把
「服务是否在跑」变成业务可用性前提。正确分工是：
**8123 保留为开发辅助（离线速查/网页 UI）**，业务侧由本包经 8127 提供同一份能力。
若日后想让文档查询走独立角色，那属于**中层新增 role** 的范畴（需改中层/顶层 spec），不在上层权限内。

### 5.5 `doc_search` 的取舍（建议 v1 不做）

| 方案 | 代价 | 建议 |
|---|---|---|
| 移植旧版全站索引（SQLite v3 + 远端 JSONL.gz + 900 s 超时） | 47 KB 代码 + 索引落盘与「无状态」冲突 + 6.5 GB 扫描 | **不做**（v2 再议） |
| 简化版：`doc_roots` 必填 + 单次请求内有界扫描（候选上限 + limit + 打分沿用 `_score_match` 规则） | 每次请求 O(根内文件数)；小根可用，全站不可用 | 可作为 v1.5 |
| 只要 `.tgf` 主题检索（不扫正文） | 覆盖「Topic → 目标 HTML」这一半价值，成本极低 | 若主开发只要「文档在哪」，这个够用 |

### 5.6 与 spec 的差异点（已在 `9-skillref.md` §7 落定）

spec 表把 `find_skill`/`skill_info`/`doc_search` 的接口写成 `C+D`；
本方案在「本地可见」时**不调用中层**。这与该文件 §2 待修订的
「纯本地解析不占中层接口」一致，但建议把「本地可见即直读」显式写进 spec，避免后续评审当成偏离。

## 6. 待主开发拍板（5 项）

1. **命名**：`virtuoso.skill.{compose,find,info,load_il,doc_search}`，还是照开发清单用扁平的
   `compose_skill` / `find_skill` / `skill_info` / `doc_search` / `load_il`？
2. **本地直读**：是否接受「`doc_root` 本地可见就直读、不占中层」（§5.2 三态）？
3. **落盘策略**：远端模式的下载落点用 `common.paths.temp_dir()` 下的确定性路径，
   还是强制调用方每次给 `local_dir`？（前者方便，后者更贴「无状态」）
4. **`doc_search` 是否 v1**：不做 / 简化版 / 只做 `.tgf` 主题检索（§5.5）。
5. **`skill.info` 是否默认回 `raw_html`**（体积大，建议默认关，`include_raw=true` 才给）。

## 7. 验收计划（拍板后执行）

- 脚本：`test/tb/skill_tooling_e2e_tests.py --transport direct|http`（沿用 symbol/maestro 的 TB 骨架）。
- 用例草案：
  - compose：空批报错、单条不包、单条已 `progn(` 保留、多条包 `progn`（4 项，可离线跑）；
  - find：五种模式各 1 + `include_desc` + `limit` 截断 + 本地/远端两种 `source` 各 1；
  - info：现代标记命中（`dbOpenCellViewByType`）、legacy 命中、`NULL` topic 兜底、未知函数 `found=false`；
  - load_il：上传一个自建 `.il`（只写自己的工作目录 + 建自己的 cell）→ 真机 `load` → 断言返回与副作用；
  - doc_search：仅在拍板做的情况下加。
- 产物：`test/tb/artifacts/skill-tooling-tb/TEST_PLAN.md` + `TEST_REPORT.md`
  （含 direct/http 双通道结果、真机返回原文、已知限制）。
- 真机回归基线：本文 §4 三条命令的输出就是远端探测与传输量的基线数字。

## 8. 证据索引

| 证据 | 路径:行 |
|---|---|
| 旧 finder 探测/解析/搜索 | `src_bak/virtuoso_bridge/virtuoso/skill_finder/__init__.py:75/103/111/155/191`、`parser.py:44/50/92` |
| 旧 More Info | `src_bak/virtuoso_bridge/virtuoso/skill_finder/more_info.py:53/79/84/131/157/184` |
| 旧 doc_search | `src_bak/virtuoso_bridge/virtuoso/docs_search.py:24/117/191/742/791/965/1240` |
| 旧客户端入口与缓存 | `src_bak/virtuoso_bridge/virtuoso/basic/bridge.py:219/859/998/1242/1345` |
| 旧组合函数 | `src_bak/virtuoso_bridge/virtuoso/basic/composition.py:8` |
| 独立服务 | `tools/skill_doc_server.py:34/74/100/118/197/485/664/685/705/964` |
| 设计 PoC 探针 | `test/tb/skill_tooling_probe.py`（`--check --compare-8123`） |
| 抽取报告（D） | `doc/report/_explore/D_library_skill_tooling_gui.md:133/300-326/523-580/609-654` |
| 新架构约束 | `spec/design-concepts/上层/1-上层.md` §3.2/§4/§5；`spec/design-concepts/上层/9-skillref.md` |
| 新中层接口 | `src/pyapi/models.py:122/140/144/148/163`；`src/transport/middle.py:51/761/846/884/121` |
| 递归下载实现 | `src/common/transfer.py:314 build_tar_download_plan`（远端 `tar -c -h -z` → 本地 `tar xzf`） |
| 注册点 | `src/server/api_server.py:305 PACKAGES`、`src/pyapi/packages/__init__.py` |
