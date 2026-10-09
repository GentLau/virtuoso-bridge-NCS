# cellview —— 库、cell、view、分类

管 Virtuoso 的"文件系统"：库（library）、单元（cell）、视图（view）、库内分类（category）。
其它包（原理图、版图、符号……）都建立在这些对象上，**动手画图前先用本包确认目标存在**。

## 0. 公共概念

| 参数 | 类型 | 说明 |
|---|---|---|
| `library` | str | 库名（不是路径） |
| `cell` | str | cell 名 |
| `view` | str | 视图名，如 `schematic` / `symbol` / `layout` |
| `view_type` | str | 视图类型：`schematic`、`schematicSymbol`、`maskLayout`、`maestro`、`text.v`、`text.veriloga` |

> `view` 是"叫什么"，`view_type` 是"是什么"。习惯上同名同类型，但建视图时必须显式给 `view_type`。

## 1. 库操作

### 1.1 `virtuoso.cellview.lib.list` — 列出所有库

**功能**：列出当前 Virtuoso 能看到的全部库。
**输入参数**：无（公共参数除外）。
**返回**：`value` = 库名列表。

```json
// 输入
{"operation":"virtuoso.cellview.lib.list","token":"TOKEN"}
// 输出（data 内容）
{"ok":true,"error":null,"value":["analogLib","basic","mylib","tsmcN65"]}
```

### 1.2 `virtuoso.cellview.lib.get` — 看单个库

**功能**：查一个库的路径与绑定信息。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |

**返回**

| 字段 | 类型 | 说明 |
|---|---|---|
| `value.name` | str | 库名 |
| `value.path` | str | 库目录（目标机器路径） |
| `value.technology_library` | str | 绑定的工艺库 |

```json
// 输入
{"operation":"virtuoso.cellview.lib.get","token":"TOKEN","library":"mylib"}
// 输出（data 内容）
{"ok":true,"error":null,"value":{"name":"mylib","path":"/home/user/vblog/mylib","technology_library":"tsmcN65"}}
```

### 1.3 `virtuoso.cellview.lib.create` — 建库

**功能**：新建一个库，可选同时绑定工艺库。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 新库名 |
| `path` | str | ✅ | — | 库目录：目标机器绝对路径，如 `/home/user/vblog/mylib` |
| `technology_library` | str | — | 无 | 绑定的工艺库，如 `cdsDefTechLib` |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.lib.create","token":"TOKEN","library":"mylib","path":"/home/user/vblog/mylib","technology_library":"cdsDefTechLib"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 1.4 `virtuoso.cellview.lib.copy` — 复制库

**功能**：整库复制到新名字与新目录。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 源库 |
| `new_library` | str | ✅ | — | 新库名 |
| `new_path` | str | ✅ | — | 新库目录 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.lib.copy","token":"TOKEN","library":"mylib","new_library":"mylib2","new_path":"/home/user/vblog/mylib2"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 1.5 `virtuoso.cellview.lib.delete` — 删库

**功能**：删除整个库（**不可逆**）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 要删除的库 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.lib.delete","token":"TOKEN","library":"mylib2"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 1.6 `virtuoso.cellview.lib.rename` — 库改名

**功能**：改库名。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 原名 |
| `new_name` | str | ✅ | — | 新名 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.lib.rename","token":"TOKEN","library":"mylib","new_name":"mylib_new"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 1.7 `virtuoso.cellview.lib.bind` — 绑定工艺库

**功能**：把库绑定到某个工艺库（画版图、用 PDK 器件前必做）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 目标库 |
| `technology_library` | str | ✅ | — | 工艺库名 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.lib.bind","token":"TOKEN","library":"mylib","technology_library":"tsmcN65"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

## 2. cell 操作

### 2.1 `virtuoso.cellview.cell.list` — 列 cell

**功能**：列出一个库里的 cell。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `category` | str | — | 无 | 只列某个分类下的 cell |

**返回**：`value` = cell 名列表。

```json
// 输入
{"operation":"virtuoso.cellview.cell.list","token":"TOKEN","library":"mylib"}
// 输出（data 内容）
{"ok":true,"error":null,"value":["inv","nand2","rc_probe"]}
```

### 2.2 `virtuoso.cellview.cell.copy` — 复制 cell

**功能**：把 cell（含其视图）复制到目标库/新名字。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 源 |
| `new_library` / `new_cell` | str | ✅ | — | 目标 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.cell.copy","token":"TOKEN","library":"mylib","cell":"inv","new_library":"mylib","new_cell":"inv2"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 2.3 `virtuoso.cellview.cell.delete` — 删 cell

**功能**：删除 cell 及其所有视图（**不可逆**）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.cell.delete","token":"TOKEN","library":"mylib","cell":"inv2"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 2.4 `virtuoso.cellview.cell.rename` — cell 改名

**功能**：改 cell 名。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `new_name` | str | ✅ | — | 新名 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.cell.rename","token":"TOKEN","library":"mylib","cell":"inv","new_name":"inv_old"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

## 3. view 操作

### 3.1 `virtuoso.cellview.view.list` — 列视图

**功能**：列出一个 cell 的所有视图（最常用的存在性检查）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |

**返回**：`value` = 视图名（含类型）列表。

```json
// 输入
{"operation":"virtuoso.cellview.view.list","token":"TOKEN","library":"mylib","cell":"inv"}
// 输出（data 内容）
{"ok":true,"error":null,"value":[["schematic","schematic"],["symbol","schematicSymbol"],["layout","maskLayout"]]}
```

### 3.2 `virtuoso.cellview.view.create` — 建视图

**功能**：新建一个视图（cell 不存在时一并创建）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` | str | ✅ | — | 目标 |
| `view` | str | ✅ | — | 视图名，如 `schematic` |
| `view_type` | str | ✅ | — | 视图类型，如 `schematic` / `schematicSymbol` / `maskLayout` |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.view.create","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic","view_type":"schematic"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 3.3 `virtuoso.cellview.view.copy` — 复制视图

**功能**：把某个视图复制到目标库/cell/视图名。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` / `view` | str | ✅ | — | 源 |
| `new_library` / `new_cell` / `new_view` | str | ✅ | — | 目标 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.view.copy","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic","new_library":"mylib","new_cell":"inv2","new_view":"schematic"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 3.4 `virtuoso.cellview.view.delete` — 删视图

**功能**：删除一个视图（**不可逆**）。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` / `view` | str | ✅ | — | 目标 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.view.delete","token":"TOKEN","library":"mylib","cell":"inv2","view":"schematic"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 3.5 `virtuoso.cellview.view.rename` — 视图改名

**功能**：改视图名。

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` / `cell` / `view` | str | ✅ | — | 目标 |
| `new_name` | str | ✅ | — | 新名 |

**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.view.rename","token":"TOKEN","library":"mylib","cell":"inv","view":"schematic","new_name":"schematic_old"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

## 4. 分类操作

分类是库内给 cell 分组的标签，不影响视图数据。

### 4.1 `virtuoso.cellview.cat.list` — 列出分类

**功能**：列出该库的所有分类。
**输入参数**：`library`。
**返回**：`value` = 分类名列表。

```json
// 输入
{"operation":"virtuoso.cellview.cat.list","token":"TOKEN","library":"mylib"}
// 输出（data 内容）
{"ok":true,"error":null,"value":["analog","digital"]}
```

### 4.2 `virtuoso.cellview.cat.create` — 新建分类

**功能**：在库内新建一个分类。
**输入参数**：`library`, `category`。
**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.cat.create","token":"TOKEN","library":"mylib","category":"digital"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 4.3 `virtuoso.cellview.cat.delete` — 删分类

**功能**：删除分类（cell 本身不受影响）。
**输入参数**：`library`, `category`。
**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.cat.delete","token":"TOKEN","library":"mylib","category":"digital"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 4.4 `virtuoso.cellview.cat.rename` — 分类改名

**功能**：改分类名。
**输入参数**：`library`, `category`, `new_name`。
**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.cat.rename","token":"TOKEN","library":"mylib","category":"digital","new_name":"dig"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 4.5 `virtuoso.cellview.cat.add_cell` — 把 cell 放进分类

**功能**：把一个已有 cell 归入分类。
**输入参数**：`library`, `category`, `cell`。
**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.cat.add_cell","token":"TOKEN","library":"mylib","category":"dig","cell":"inv"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

### 4.6 `virtuoso.cellview.cat.remove_cell` — 把 cell 移出分类

**功能**：把 cell 从分类里移除（cell 本身不删）。
**输入参数**：`library`, `category`, `cell`。
**返回**：`value` = 执行结果。

```json
// 输入
{"operation":"virtuoso.cellview.cat.remove_cell","token":"TOKEN","library":"mylib","category":"dig","cell":"inv"}
// 输出（data 内容）
{"ok":true,"error":null,"value":null}
```

## 5. 注意事项

- 建库的 `path` 必须是目标机器上的绝对路径且目录可写。
- 删除类操作不可逆；删之前先 `lib.list` / `cell.list` 确认。
- 视图正在 Virtuoso 里打开时，删除/改名可能报锁冲突——先让用户关掉窗口。
