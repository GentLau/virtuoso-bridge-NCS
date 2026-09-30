# verilog —— Verilog 视图与结构导入

两种事：**文本视图的读写**（把 Verilog 源码当文件改）和**结构导入**（把 Verilog 网表变成 Virtuoso 里的原理图/symbol）。

## 1. `virtuoso.verilog.read` — 读源码

**功能**：从库里的视图或直接从一个文件读取 Verilog 源码。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` + `cell` | str | 与 `file_path` 二选一 | — | 从库里的视图读 |
| `file_path` | str | 与上者二选一 | — | 直接读文件 |
| `file_is_local` | bool | — | `true` | `file_path` 是本机路径还是目标机器路径 |
| `view` | str | — | `verilog` | 视图名 |
| `view_type` | str | — | `text.v` | 视图类型 |
| `focus` | list[str] | — | 全部 | 只要某些片段 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value` | dict | 源码内容与解析结果（按 `focus` 裁剪） |

**示例**

```json
{"operation":"virtuoso.verilog.read","token":"TOKEN","library":"mylib","cell":"top","view":"verilog"}
{"operation":"virtuoso.verilog.read","token":"TOKEN","file_path":"C:/work/top.v","file_is_local":true}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"library":"mylib","cell":"top","view":"verilog","view_type":"text.v",
 "text":"module top(a,b);\nendmodule\n","modules":["top"],"ports":["a","b"]}}
```

## 2. `virtuoso.verilog.write` — 写源码

**功能**：创建/覆盖/局部修改 Verilog 源码视图。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令，见下 |
| `view` | str | — | `verilog` | 视图名 |
| `view_type` | str | — | `text.v` | 视图类型 |

原子命令：

| 原子 | 参数 | 必填 | 说明 |
|---|---|---|---|
| `ensure_view` | 无 | — | 视图不存在时创建，并写入一个空 module 模板 |
| `delete_view` | 无 | — | 删除视图 |
| `set_source` | `text`；可选 `expected_sha256` | ✅ | 整篇覆盖写；给摘要时先校验 |
| `patch_source` | `edits`（`old_text`+`new_text`，或 `start_line`+`end_line`+`new_text`）；可选 `all` | ✅ | 局部修改 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.applied` | int | 成功应用的命令条数 |

**示例**

```json
{"operation":"virtuoso.verilog.write","token":"TOKEN","library":"mylib","cell":"top","view":"verilog",
 "commands":[
  {"op":"ensure_view"},
  {"op":"set_source","text":"module top(a,b); endmodule\n"},
  {"op":"patch_source","edits":[{"old_text":"endmodule","new_text":"// end\nendmodule"}]}]}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"applied":3}}
```

> 视图不存在时必须先 `ensure_view`：直接 `set_source`/`patch_source` 会被拒绝。

## 3. `virtuoso.verilog.import` — 结构导入

**功能**：把 Verilog 结构导入成 Virtuoso 的原理图（并可生成 symbol）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 导入到哪个库/cell |
| `file_path` | str | ✅ | — | Verilog 文件 |
| `file_is_local` | bool | — | `true` | 本机文件会自动搬运 |
| `ref_libs` | list[str] | — | 空 | 参考库（引用到的单元所在库） |
| `structural_views` | int | — | `4` | 生成哪些视图的位掩码 |
| `schematic_view` / `functional_view` / `symbol_view` | str | — | `schematic`/`functional`/`symbol` | 生成的视图名 |
| `power_net` / `ground_net` | str | — | `VDD` / `VSS` | 电源/地网络名 |
| `import_lib_cells` | int | — | `0` | 是否连库单元一起导入 |
| `overwrite` | bool | — | `false` | 已存在时是否覆盖 |
| `timeout` | number | — | `30` | **导入慢，建议 300 起步** |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.cells` / `value.views` | list | 导入产生的 cell 与视图 |
| `value.warnings` | list | 警告 |
| `value.log_path` | str | 导入工具日志 |
| `value.reason` / `value.diagnostics` | str/dict | 失败原因与诊断（失败时） |

**示例**

```json
{"operation":"virtuoso.verilog.import","token":"TOKEN","library":"mylib","cell":"top",
 "file_path":"C:/work/top.v","overwrite":true,"timeout":300}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"cells":["top"],"views":["schematic","symbol"],
 "warnings":[],"log_path":"/home/user/.virtuoso-bridge/<user>/calibre/.."}}
```

**前提**：目标库必须能在 CIW 的 `cds.lib` 里解析，否则导入工具直接报找不到库（`VERILOGIN-93` 一类）。

## 4. `virtuoso.verilog.export` — 从原理图导出

**功能**：把原理图导出成 Verilog。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `schematic` | 源视图 |
| `output_path` | str | — | 自动 | 导出落点（本机） |
| `recursive` | bool | — | `false` | 是否连下层一起导出 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.verilog_path` | str | 导出的 Verilog 文件 |
| `value.log_path` | str | 导出日志 |
| `value.module_count` | int | 导出模块数 |

**示例**

```json
{"operation":"virtuoso.verilog.export","token":"TOKEN","library":"mylib","cell":"top","view":"schematic","output_path":"C:/work/top.v"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"verilog_path":"C:/work/top.v","log_path":"/home/user/work/top.export.log","module_count":3}}
```
