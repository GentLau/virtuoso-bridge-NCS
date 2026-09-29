# verilog —— Verilog 视图与结构导入

管两种事：**文本视图的读写**（把 Verilog 源码当文件改）和**结构导入**（把 Verilog 网表变成
Virtuoso 里的原理图/symbol）。

## 1. `virtuoso.verilog.read` — 读源码

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` + `cell` | str | 与 `file_path` 二选一 | — | 从库里的视图读 |
| `file_path` | str | 与上者二选一 | — | 直接读文件 |
| `file_is_local` | bool | — | `true` | `file_path` 是本机路径还是目标机器路径 |
| `view` | str | — | `verilog` | 视图名 |
| `view_type` | str | — | `text.v` | 视图类型 |
| `focus` | list[str] | — | 全部 | 只要某些片段 |

返回 `data.value`：源码内容（或按 `focus` 裁剪后的内容）。

## 2. `virtuoso.verilog.write` — 写源码

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令，见下 |
| `view` | str | — | `verilog` | 视图名 |
| `view_type` | str | — | `text.v` | 视图类型 |

原子命令：

| 原子 | 参数 | 类型 | 必填 | 说明 |
|---|---|---|---|---|
| `ensure_view` | 无 | — | — | 视图不存在时创建（带一个空 module 模板） |
| `delete_view` | 无 | — | — | 删除视图 |
| `set_source` | `text` | str | ✅ | 整篇覆盖写 |
| | `expected_sha256` | str | — | 先校验当前内容摘要，对不上就拒绝写（防覆盖别人的改动） |
| `patch_source` | `edits` | list[dict] | ✅ | 逐条改；每条用 `old_text`+`new_text`，或用 `start_line`+`end_line`+`new_text` |
| | `all` | bool | — | `old_text` 匹配到多处时是否全部替换（默认 false，多匹配直接报错） |

返回 `data.value` = `{"applied": n}`；末尾还会刷新库列表（`ddUpdateLibList`）。

```json
{"operation":"virtuoso.verilog.write","token":"TOKEN","library":"mylib","cell":"top","view":"verilog",
 "commands":[
  {"op":"ensure_view"},
  {"op":"set_source","text":"module top(a,b); endmodule\n"},
  {"op":"patch_source","edits":[{"old_text":"endmodule","new_text":"// end\nendmodule"}]}]}
```

## 3. `virtuoso.verilog.import` — 结构导入

把 Verilog 结构导入成 Virtuoso 的原理图（并可生成 symbol）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 导入到哪个库/cell |
| `file_path` | str | ✅ | — | Verilog 文件 |
| `file_is_local` | bool | — | `true` | 本机文件会自动搬运 |
| `ref_libs` | list[str] | — | 空 | 参考库（引用到的单元所在的库） |
| `structural_views` | int | — | `4` | 生成哪些视图的位掩码（默认按实现给的组合） |
| `schematic_view` | str | — | `schematic` | 生成的原理图视图名 |
| `functional_view` | str | — | `functional` | 生成的功能视图名 |
| `symbol_view` | str | — | `symbol` | 生成的 symbol 视图名 |
| `power_net` / `ground_net` | str | — | `VDD` / `VSS` | 电源/地网络名 |
| `import_lib_cells` | int | — | `0` | 是否连库单元一起导入 |
| `overwrite` | bool | — | `false` | 已存在时是否覆盖 |
| `timeout` | number | — | `30` | **导入很慢，建议 300 起步** |

```json
{"operation":"virtuoso.verilog.import","token":"TOKEN","library":"mylib","cell":"top",
 "file_path":"C:/work/top.v","overwrite":true,"timeout":300}
```

**前提**：目标库必须能在 CIW 的 `cds.lib` 里解析；否则导入工具会报找不到库
（`VERILOGIN-93` 一类错误）。缺文件、缺库都会被明确报出来，不要靠重试。

## 4. `virtuoso.verilog.export` — 从原理图导出

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `schematic` | 源视图 |
| `output_path` | str | — | 自动 | 导出落点（本机） |
| `recursive` | bool | — | `false` | 是否连下层一起导出 |

## 5. 注意事项

- `set_source` 是整篇覆盖，改之前先用 `read` 拿现状；担心并发改动就带 `expected_sha256`。
- 结构导入依赖环境里的 Verilog 导入工具；工具日志失败时返回里会带日志片段。
- 导入后建议 `schematic.read` 复核顶层连接，再 `symbol.generate` 出符号。
