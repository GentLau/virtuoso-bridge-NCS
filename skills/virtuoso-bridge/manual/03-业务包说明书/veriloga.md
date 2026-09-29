# veriloga —— Verilog-A

Verilog-A 视图就是"库里的一个文本视图"，操作方式和 Verilog 一样，只是视图类型是 `text.veriloga`。

## 1. `virtuoso.veriloga.read` — 读源码

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` + `cell` | str | 与 `file_path` 二选一 | — | 从库里的视图读 |
| `file_path` | str | 与上者二选一 | — | 直接读文件 |
| `file_is_local` | bool | — | `true` | 路径是本机还是目标机器 |
| `view` | str | — | `veriloga` | 视图名 |
| `view_type` | str | — | `text.veriloga` | 视图类型 |
| `focus` | list[str] | — | 全部 | 只要某些片段 |

## 2. `virtuoso.veriloga.write` — 写源码

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `commands` | list[dict] | ✅ | — | 原子命令（与 verilog 相同） |
| `view` | str | — | `veriloga` | 视图名 |
| `view_type` | str | — | `text.veriloga` | 视图类型 |

原子命令：

| 原子 | 参数 | 必填 | 说明 |
|---|---|---|---|
| `ensure_view` | 无 | — | 创建视图并写入一个带 `` `include "constants.vams" `` / `` `include "disciplines.vams" `` 的空 module 模板 |
| `delete_view` | 无 | — | 删除视图 |
| `set_source` | `text`；可选 `expected_sha256` | ✅ | 整篇覆盖写 |
| `patch_source` | `edits`（`old_text`+`new_text` 或 `start_line`+`end_line`+`new_text`）；可选 `all` | ✅ | 局部修改 |

```json
{"operation":"virtuoso.veriloga.write","token":"TOKEN","library":"mylib","cell":"va","view":"veriloga",
 "commands":[
  {"op":"ensure_view"},
  {"op":"set_source","text":"`include \"constants.vams\"\n`include \"disciplines.vams\"\nmodule va(a,b);\n  electrical a,b;\nendmodule\n"}]}
```

## 3. `virtuoso.veriloga.check_and_save` — 检查并保存

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | — | `veriloga` | 视图名 |
| `view_type` | str | — | `text.veriloga` | 视图类型 |

写完源码后调用它，让 Virtuoso 做一次语法检查并落盘（编译报错会体现在返回里）。

## 4. 注意事项

- `ensure_view` 只在视图不存在时创建；已存在时不会覆盖你的内容。
- 改 Verilog-A 后要重新 `check_and_save`，仿真器才会用新代码。
