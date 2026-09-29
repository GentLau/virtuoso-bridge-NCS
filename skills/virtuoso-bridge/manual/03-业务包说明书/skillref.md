# skillref —— SKILL 函数文档查询

不用记 SKILL 函数名：先搜，再看详细说明。适合在写 `basic.skill.execute` 之前查语法。

## 1. `virtuoso.skillref.search` — 搜索

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `query` | str | ✅ | — | 关键词或函数名 |
| `mode` | str | — | `fuzzy` | 匹配方式：`fuzzy` / `prefix` / `suffix` / `exact` / `regex` |
| `search_in` | str | — | `entry` | 搜索层级：`name` / `entry` / `topic` / `body` / `all`（层级是累积的，越往后越全但越慢） |
| `limit` | int | — | `20` | 最多返回多少条 |
| `under` | list[str] | — | 全部 | 限定目录范围 |
| `source` | str | — | 自动 | 指定文档源 |
| `doc_root` | str | — | 自动 | 指定本地 Cadence 文档根目录 |
| `max_candidates` | int | — | `50` | 候选上限 |
| `max_files` | int | — | `5000` | 扫描文件上限 |
| `snippet` | bool | — | `true` | 是否返回片段 |

返回 `data`：`results`（命中列表：函数名、语法、描述、文件位置）、`scanned_files`、
`truncated`（是否因为上限被截断）、`doc_root`、`elapsed_ms` 等。

## 2. `virtuoso.skillref.info` — 看详细文档

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `name` | str | ✅ | — | 函数名（一般来自 `search` 的结果） |
| `source` | str | — | 自动 | 文档源 |
| `doc_root` | str | — | 自动 | 文档根目录 |
| `include_raw` | bool | — | `false` | 是否附带原始 HTML |

返回 `data`：`found`（是否找到）、`func_name`、`file_path`、`topic`、`plain_text`（正文纯文本）、
`raw_html`（`include_raw=true` 时）。

## 3. 示例

```json
{"operation":"virtuoso.skillref.search","token":"TOKEN","query":"hiWindowSaveImage"}
{"operation":"virtuoso.skillref.search","token":"TOKEN","query":"dbCreate","mode":"prefix","search_in":"name","limit":50}
{"operation":"virtuoso.skillref.info","token":"TOKEN","name":"hiWindowSaveImage"}
```

## 4. 使用建议

- 只想找函数名 → `mode=prefix` + `search_in=name`（最快）。
- 想找"哪个函数能做某件事" → `search_in=topic` 或 `body`（慢一些，但能按描述搜）。
- 拿到函数名后必看 `info`：参数顺序和返回值类型经常和直觉不一致。
