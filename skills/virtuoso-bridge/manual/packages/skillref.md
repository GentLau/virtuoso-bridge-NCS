# skillref —— SKILL 函数文档查询

不用记 SKILL 函数名：先搜，再看详细说明。写 `basic.skill.execute` 之前用它查语法最省事。

## 1. `virtuoso.skillref.search` — 搜索函数

**功能**：按名字或描述搜索 Cadence 安装的 SKILL 函数文档。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `query` | str | ✅ | — | 关键词或函数名 |
| `mode` | str | — | `fuzzy` | `fuzzy` / `prefix` / `suffix` / `exact` / `regex` |
| `search_in` | str | — | `entry` | `name` / `entry` / `topic` / `body` / `all`；层级累积，越往后越全也越慢 |
| `limit` | int | — | `20` | 最多返回多少条 |
| `under` | list[str] | — | 全部 | 限定搜索目录 |
| `source` | str | — | 自动 | 指定文档源 |
| `doc_root` | str | — | 自动 | 指定本地 Cadence 文档根目录 |
| `max_candidates` | int | — | `50` | 候选上限 |
| `max_files` | int | — | `5000` | 扫描文件上限 |
| `snippet` | bool | — | `true` | 是否返回片段 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `results` | list | 命中列表（函数名、语法、描述、所在文件） |
| `scanned_files` | int | 实际扫描的文件数 |
| `truncated` | bool | 是否因上限被截断 |
| `doc_root` / `source` | str | 实际使用的文档源 |
| `elapsed_ms` | int | 搜索耗时（毫秒） |

**示例**

```json
{"operation":"virtuoso.skillref.search","token":"TOKEN","query":"hiWindowSaveImage"}
{"operation":"virtuoso.skillref.search","token":"TOKEN","query":"dbCreate","mode":"prefix","search_in":"name","limit":50}
// 输出（data 内容）
{"ok":true,"error":null,"query":"hiWindowSaveImage","search_in":"entry",
 "results":[{"name":"hiWindowSaveImage","syntax":"hiWindowSaveImage( w_windowId t_fileName )","description":"Save a window image to a file."}],
 "scanned_files":12,"truncated":false,"doc_root":"/cadre/doc","source":"local","elapsed_ms":37}
```

## 2. `virtuoso.skillref.info` — 看函数详细文档

**功能**：取某个 SKILL 函数的完整说明。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | str | ✅ | — | 函数名（一般来自 `search` 结果） |
| `source` / `doc_root` | str | — | 自动 | 文档源与根目录 |
| `include_raw` | bool | — | `false` | 是否附带原始 HTML |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `found` | bool | 是否找到 |
| `func_name` | str | 函数名 |
| `file_path` | str | 文档文件位置 |
| `topic` | str | 主题名 |
| `plain_text` | str | 正文纯文本 |
| `raw_html` | str | 原始 HTML（`include_raw=true` 时） |

**示例**

```json
// 输入
{"operation":"virtuoso.skillref.info","token":"TOKEN","name":"hiWindowSaveImage"}
// 输出（data 内容）
{"ok":true,"error":null,"found":true,"func_name":"hiWindowSaveImage","topic":"hiWindowSaveImage",
 "file_path":"/cadre/doc/api_more_info/hiWindowSaveImage.html","plain_text":"hiWindowSaveImage( ... )\n\n保存窗口图像……"}
```

## 3. 使用建议

- 只找名字：`mode=prefix` + `search_in=name`（最快）。
- 找"能做什么"：`search_in=topic` 或 `body`。
- 拿到函数名后一定看 `info`：参数顺序与返回类型常和直觉不同。
