# 业务包说明书（索引）

每个包一个文件；每个业务操作在所属包文件里**有且仅有一个小节**，标题行包含完整操作名。
公共字段（`token`/`timeout`/`step_details`/`log_level`/`log_max_bytes`、响应壳、`kind`、路径约定）见
[../common.md](../common.md) 的「公共约定」，各操作小节不再重复。

| 包 | 操作数 | 做什么 | 文档 |
|---|---|---|---|
| basic | 6 | 直连底层：SKILL / shell / 文件 / GUI 命令 / Spectre 命令 | [basic.md](basic.md) |
| cellview | 22 | 库、cell、view、分类的增删改查 | [cellview.md](cellview.md) |
| schematic | 4 | 原理图读写、检查保存、截屏 | [schematic.md](schematic.md) |
| symbol | 5 | 符号读写、从原理图生成、截屏 | [symbol.md](symbol.md) |
| layout | 5 | 版图读写、GDS 导入导出、显示控制、截屏 | [layout.md](layout.md) |
| maestro | 11 | ADE/Maestro 配置、跑仿真、读结果与历史 | [maestro.md](maestro.md) |
| spectre | 5 | 独立 Spectre 仿真、读 PSF、量指标、导出 | [spectre.md](spectre.md) |
| calibre | 7 | DRC / LVS / PEX 与结果导出（PEX 本版不提供） | [calibre.md](calibre.md) |
| verilog | 4 | Verilog 视图读写、结构导入、导出 | [verilog.md](verilog.md) |
| veriloga | 3 | Verilog-A 读写与检查保存 | [veriloga.md](veriloga.md) |
| gui | 4 | 窗口列表、发按键、自动关弹窗、截屏 | [gui.md](gui.md) |
| skillref | 2 | 查 Cadence SKILL 函数文档 | [skillref.md](skillref.md) |

合计 **12 个包、78 个业务操作**。

## 原子命令（`commands` 参数）

`schematic.write` / `symbol.write` / `layout.write` / `layout.display` / `maestro.write` /
`maestro.write_history` / `verilog.write` / `veriloga.write` 这些操作的 `commands` 是**一组原子命令**：

```json
// 输入
{"operation":"virtuoso.schematic.write","token":"TOKEN","library":"L","cell":"C","view":"schematic",
 "commands":[{"op":"place_instance","...":"..."},{"op":"place_wire","...":"..."}]}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

- 每个原子是一个对象，`op` 决定它做什么，其余字段是该原子的参数；
- 按顺序执行，**遇到第一个失败就停下**（`error` 里会写 `applied: n/m`）；
- 参数写错会在执行前被拒绝，不会产生半个视图。
