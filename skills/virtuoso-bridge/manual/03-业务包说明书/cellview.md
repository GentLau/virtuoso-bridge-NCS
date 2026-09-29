# cellview —— 库、cell、view、分类

管的是 Virtuoso 的"文件系统"：库（library）、单元（cell）、视图（view）、以及库内的分类（category）。
其它业务包（原理图、版图、符号……）都建立在这些对象之上，所以**动手画图前先用本包确认目标存在**。

## 0. 公共参数

| 参数 | 类型 | 说明 |
|---|---|---|
| `library` | str | 库名（不是路径） |
| `cell` | str | cell 名 |
| `view` | str | 视图名，如 `schematic` / `symbol` / `layout` |
| `view_type` | str | 视图类型（创建时需要）：`schematic`、`schematicSymbol`、`maskLayout`、`maestro`、`text.v`、`text.veriloga` |

> `view` 是"叫什么名字"，`view_type` 是"是什么类型"。习惯上名字和类型一致（`schematic`/`schematic`），
> 但可以不同——建视图时必须显式给出 `view_type`。

## 1. 库操作

### 1.1 `virtuoso.cellview.lib.list` — 列出所有库

除 `token`/`timeout` 外无参数。

### 1.2 `virtuoso.cellview.lib.get` — 看单个库

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |

### 1.3 `virtuoso.cellview.lib.create` — 建库

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 新库名 |
| `path` | str | ✅ | — | 库目录：**目标机器上的绝对路径**，如 `/home/user/vblog/mylib` |
| `technology_library` | str | — | 无 | 绑定的工艺库，如 `cdsDefTechLib` 或 PDK 库名 |

### 1.4 `virtuoso.cellview.lib.copy` — 复制库

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 源库 |
| `new_library` | str | ✅ | — | 新库名 |
| `new_path` | str | ✅ | — | 新库目录（目标机器绝对路径） |

### 1.5 `virtuoso.cellview.lib.delete` — 删库

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 要删除的库（**不可逆**） |

### 1.6 `virtuoso.cellview.lib.rename` — 库改名

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 原名 |
| `new_name` | str | ✅ | — | 新名 |

### 1.7 `virtuoso.cellview.lib.bind` — 绑定工艺库

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 目标库 |
| `technology_library` | str | ✅ | — | 要绑定的工艺库名 |

> 画版图、用 PDK 器件前，库必须先绑定工艺库；绑错了图层名会解析失败。

## 2. cell 操作

### 2.1 `virtuoso.cellview.cell.list` — 列 cell

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `category` | str | — | 无 | 只列某个分类下的 cell |

### 2.2 `virtuoso.cellview.cell.copy` — 复制 cell

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 源库 |
| `cell` | str | ✅ | — | 源 cell |
| `new_library` | str | ✅ | — | 目标库 |
| `new_cell` | str | ✅ | — | 目标 cell 名 |

### 2.3 `virtuoso.cellview.cell.delete` — 删 cell

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名（**不可逆**） |

### 2.4 `virtuoso.cellview.cell.rename` — cell 改名

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | 原名 |
| `new_name` | str | ✅ | — | 新名 |

## 3. view 操作

### 3.1 `virtuoso.cellview.view.list` — 列视图

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |

> 也是最常用的"视图存在性检查"：列得到 ≠ 能写（可能被锁），但列不到就一定不存在。

### 3.2 `virtuoso.cellview.view.create` — 建视图

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名（不存在时由本操作创建） |
| `view` | str | ✅ | — | 视图名，如 `schematic` |
| `view_type` | str | ✅ | — | 视图类型，如 `schematic` / `schematicSymbol` / `maskLayout` |

### 3.3 `virtuoso.cellview.view.copy` — 复制视图

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 源库 |
| `cell` | str | ✅ | — | 源 cell |
| `view` | str | ✅ | — | 源视图 |
| `new_library` | str | ✅ | — | 目标库 |
| `new_cell` | str | ✅ | — | 目标 cell |
| `new_view` | str | ✅ | — | 目标视图名 |

### 3.4 `virtuoso.cellview.view.delete` — 删视图

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `view` | str | ✅ | — | 视图名（**不可逆**） |

### 3.5 `virtuoso.cellview.view.rename` — 视图改名

| 参数 | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `library` | str | ✅ | — | 库名 |
| `cell` | str | ✅ | — | cell 名 |
| `view` | str | ✅ | — | 原名 |
| `new_name` | str | ✅ | — | 新名 |

## 4. 分类（category）操作

分类是库内给 cell 分组的标签，不影响视图数据本身。

| 操作 | 参数 | 必填 | 说明 |
|---|---|---|---|
| `virtuoso.cellview.cat.list` | `library` | ✅ | 列出该库的所有分类 |
| `virtuoso.cellview.cat.create` | `library`, `category` | ✅ | 新建分类 |
| `virtuoso.cellview.cat.delete` | `library`, `category` | ✅ | 删除分类（cell 本身不受影响） |
| `virtuoso.cellview.cat.rename` | `library`, `category`, `new_name` | ✅ | 分类改名 |
| `virtuoso.cellview.cat.add_cell` | `library`, `category`, `cell` | ✅ | 把 cell 放进分类 |
| `virtuoso.cellview.cat.remove_cell` | `library`, `category`, `cell` | ✅ | 把 cell 移出分类 |

## 5. 返回

所有操作返回 `data.value`：

- `lib.list` / `cell.list` / `view.list` / `cat.list`：列表结果（名字集合）。
- `lib.get`：该库的信息。
- 增删改类：操作的执行痕迹（成功即 `data.ok=true`）。

## 6. 注意事项

- 建库的 `path` 必须是**目标机器上**的绝对路径，且目录可写；库目录建议集中放在注册时配置的根目录下。
- 删除类操作不可逆；删库前先 `lib.list` / `cell.list` 确认。
- 视图正在 Virtuoso 里打开时，删除/改名可能报锁冲突——先让用户关掉窗口。
