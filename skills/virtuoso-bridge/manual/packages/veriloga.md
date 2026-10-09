# veriloga —— Verilog-A

Verilog-A 视图就是"库里的一个文本视图"，操作方式与 Verilog 相仿，视图类型是 `text.veriloga`。

## 1. `virtuoso.veriloga.read` — 读源码

**功能**：从库里的视图或直接从一个文件读取 Verilog-A 源码。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` + `cell` | str | 与 `file_path` 二选一 | — | 从库里的视图读 |
| `file_path` | str | 与上者二选一 | — | 直接读文件 |
| `file_is_local` | bool | — | `true` | `file_path` 是本机路径还是目标机器路径 |
| `view` | str | — | `veriloga` | 视图名 |
| `view_type` | str | — | `text.veriloga` | 视图类型 |
| `focus` | list[str] | — | 全部 | 只要某些片段 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value` | dict | 源码内容（含 `text` 等字段；按 `focus` 裁剪） |

**示例**

```json
{"operation":"virtuoso.veriloga.read","token":"TOKEN","library":"mylib","cell":"va","view":"veriloga"}
{"operation":"virtuoso.veriloga.read","token":"TOKEN","file_path":"C:/work/model.va","file_is_local":true}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"library":"mylib","cell":"va","view":"veriloga","view_type":"text.veriloga",
 "text":"`include \"constants.vams\"\nmodule va(a,b);\nendmodule\n","modules":["va"],"ports":["a","b"]}}
```

## 2. `virtuoso.veriloga.write` — 写源码

**功能**：创建/覆盖/局部修改 Verilog-A 源码。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令，见下 |
| `view` | str | — | `veriloga` | 视图名 |
| `view_type` | str | — | `text.veriloga` | 视图类型 |

原子命令：

| 原子 | 参数 | 必填 | 说明 |
|---|---|---|---|
| `ensure_view` | 无 | — | 视图不存在时创建，并写入带 `` `include "constants.vams" `` / `` `include "disciplines.vams" `` 的空 module 模板 |
| `delete_view` | 无 | — | 删除视图 |
| `set_source` | `text`；可选 `expected_sha256` | ✅ | 整篇覆盖写；给了摘要就先校验，防覆盖别人的改动 |
| `patch_source` | `edits`（`old_text`+`new_text`，或 `start_line`+`end_line`+`new_text`）；可选 `all` | ✅ | 局部修改；`old_text` 多处匹配且 `all≠true` 时报错 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.applied` | int | 成功应用的命令条数 |

**示例**

```json
{"operation":"virtuoso.veriloga.write","token":"TOKEN","library":"mylib","cell":"va","view":"veriloga",
 "commands":[
  {"op":"ensure_view"},
  {"op":"set_source","text":"`include \"constants.vams\"\n`include \"disciplines.vams\"\nmodule va(a,b);\n  electrical a,b;\nendmodule\n"}]}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"applied":2}}
```

> 视图不存在时**必须先** `ensure_view`：直接 `set_source` 或 `patch_source` 会被拒绝（不允许产生半个视图）。

## 3. `virtuoso.veriloga.check_and_save` — 检查并保存

**功能**：让 Virtuoso 对 Verilog-A 源码做语法检查并保存。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `veriloga` | 视图名 |
| `view_type` | str | — | `text.veriloga` | 视图类型 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.module_name` | str | 解析出的模块名 |
| `value.ports` | list | 端口列表 |
| `value.pin_order` | list | 端口顺序 |
| `value.param_list` | list | 参数列表 |
| `value.errors` | list | 编译错误（有错时） |
| `value.err_log` | str | 错误日志路径 |

**示例**

```json
// 输入
{"operation":"virtuoso.veriloga.check_and_save","token":"TOKEN","library":"mylib","cell":"va","view":"veriloga"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"module_name":"va","ports":["a","b"],"pin_order":["a","b"],
 "param_list":[],"err_log":"/home/user/.virtuoso-bridge/<user>/veriloga/va/ahdlcmi.err","errors":[]}}
```

## 4. 注意事项

- 改完源码要重新 `check_and_save`，仿真器才会用新代码。
- `ensure_view` 只在视图不存在时创建，不会覆盖已有内容。
- **symbol 生成本版不提供**（`ahdlSymbolGen` 会弹模态窗阻塞 CIW，已禁用）。需要 symbol 时先用
  `virtuoso.symbol.generate` 从 schematic 生成，再在 symbol 里补 Verilog-A 相关标注。
