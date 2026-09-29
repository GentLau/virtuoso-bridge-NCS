# 业务包说明书

这里按**业务包**逐个说明每个操作的**每个参数**。共 12 个包，对应 79 个业务操作。

## 怎么读

每个操作的参数表列固定为：

| 列 | 含义 |
|---|---|
| 参数 | 请求体里的字段名 |
| 类型 | 期望的 JSON 类型（`str` / `int` / `float` / `bool` / `list` / `dict`） |
| 必填 | ✅ = 必须给；不给就是 400 参数错误 |
| 默认 | 不给时的取值 |
| 说明 | 取值含义、常见取值、注意事项 |

**两个通用参数不再逐表重复**：

- `token`（str，必填）：每次调用都要带，值就是注册时确定的 token。
- `timeout`（数字，可选，默认 `30`）：本次调用的端到端超时（秒）。长任务（跑仿真、结构导入、GDS 导出）建议显式给大一些。

请求体统一形如：

```json
{"operation":"<操作名>","token":"TOKEN", "...参数名":"...参数值"}
```

返回值统一形如（外层壳 `ok/data/error`，`data` 里的字段见各包说明）：

```json
{"ok": true, "data": {"ok": true, "steps": [], "error": null, "value": {}}, "error": null}
```

## 包索引

| 包 | 操作数 | 做什么 | 文档 |
|---|---|---|---|
| basic | 6 | 直连底层：SKILL / shell / 文件 / GUI 命令 / Spectre 命令 | [basic.md](basic.md) |
| cellview | 22 | 库、cell、view、分类的增删改查 | [cellview.md](cellview.md) |
| schematic | 4 | 原理图读写、检查保存、截屏 | [schematic.md](schematic.md) |
| symbol | 5 | 符号读写、从原理图生成、截屏 | [symbol.md](symbol.md) |
| layout | 5 | 版图读写、GDS 导入导出、显示控制、截屏 | [layout.md](layout.md) |
| maestro | 11 | ADE/Maestro 配置、跑仿真、读结果与历史 | [maestro.md](maestro.md) |
| spectre | 5 | 独立 Spectre 仿真、读 PSF、量指标、导出 | [spectre.md](spectre.md) |
| calibre | 8 | DRC / LVS / PEX、CDL 导出与结果导出 | [calibre.md](calibre.md) |
| verilog | 4 | Verilog 视图读写、结构导入、导出 | [verilog.md](verilog.md) |
| veriloga | 3 | Verilog-A 读写与检查保存 | [veriloga.md](veriloga.md) |
| gui | 4 | 窗口列表、发按键、自动关弹窗、截屏 | [gui.md](gui.md) |
| skillref | 2 | 查 Cadence SKILL 函数文档 | [skillref.md](skillref.md) |

## 原子命令（`commands` 参数）约定

`schematic.write` / `symbol.write` / `layout.write` / `layout.display` / `maestro.write` /
`maestro.write_history` / `verilog.write` / `veriloga.write` 这些操作的 `commands` 是**一组原子命令**：

```json
{"operation":"virtuoso.schematic.write","token":"TOKEN","library":"L","cell":"C","view":"schematic",
 "commands":[{"op":"place_instance","...":"..."},{"op":"place_wire","...":"..."}]}
```

- 每个原子是一个对象，`op` 决定它做什么，其余字段是该原子的参数。
- 按顺序执行；**遇到第一个失败就停下**，返回里会说明已经应用了几条（`error` 里的 `applied: n/m`）。
- 一次给一组通常比来回多次调用快；但原则是"一个可验证的动作"一组。
- 参数写错（缺必填、类型不对）会在执行前被拒绝，不会产生半个视图。

## 通用错误速查

| 错误文本 | 含义 |
|---|---|
| `token is required` / `invalid token` | token 没带或不对 |
| `unknown operation: xxx` | 操作名不存在（用 `GET /help` 查） |
| `library not found` / `cell not found` / `view not found` | 目标不存在或名字写错 |
| `... is locked by another session` | 视图正在被别的会话占用 |
| `VB-PATH-NOT-VISIBLE:` | 目标机器上路径不可见 |
| `unknown atomic op: xxx` | 原子命令的 `op` 写错 |
| `command ... requires ...` | 原子命令缺必填字段 |
