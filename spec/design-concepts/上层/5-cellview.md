# 上层业务包：cellview

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

重点在“文件”管理，对象体系分三层：**lib → cell → view**（categories 特殊，另行定义）。每层都有 list/create/copy/delete/rename；get/bind 只在 lib 层。

### 1.1 读操作（不改变业务服务器状态）

| 层级 | 操作名 | 说明 | 接口 |
|---|---|---|---|
| lib | list | 列出所有 lib | S |
| lib | get | 读 lib 元数据（path/tech） | S |
| cell | list | 列出指定 lib 中的所有 cell；给 `category` 时只列该分类下的 cell | S |
| view | list | 列出指定 cell 中的所有 view | S |
| category | list | 列出指定 lib 的所有 categories | S |

### 1.2 写操作（改变业务服务器状态）

| 层级 | 操作名 | 说明 | 接口 |
|---|---|---|---|
| lib | create | 新建 lib | S |
| lib | copy | 复制 lib | S |
| lib | delete | 删除 lib | S |
| lib | rename | lib 改名 | S |
| lib | bind | 绑定技术库（tech） | S |
| cell | copy | 复制 cell | S |
| cell | delete | 删除 cell | S |
| cell | rename | cell 改名 | S |
| view | create | 在指定 cell 中新建 view；cell 尚不存在时，首个 view 的创建即创建 cell | S |
| view | copy | 复制 view | S |
| view | delete | 删除 view | S |
| view | rename | view 改名 | S |
| category | create | 新建 category | S |
| category | delete | 删除 category（不级联删 cell） | S |
| category | rename | category 改名 | S |
| category | add_cell | 把 cell 加入 category | S |
| category | remove_cell | 把 cell 移出 category | S |

接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 操作名规则

建议统一为 `virtuoso.cellview.<层级>.<动作>`，例如：

- `virtuoso.cellview.lib.list`
- `virtuoso.cellview.cell.create`
- `virtuoso.cellview.view.rename`

## 3. 预留（暂不实现）

- **harvest**：输入一个 lib，一次性枚举 lib → cells → views 全貌，对 view 分类，并附带 Maestro setup/analysis 名与结果目录存在性，输出 JSON 报告。可由三层 `list` 拼出，先不实现。

## 4. 待修订

- cell 的归属：cell 要么不属于任何 category（直接挂 lib），要么属于某一个 category；
- cell 层没有 create（随首个 view 创建而存在），cell 的 delete/rename/copy 语义待确认；
- category 只收纳 cell（不收 view）；
- copy 在各层的实现能力（SKILL 支持范围）待验证；
- get/bind 确认只存在于 lib 层；
- 删除/改名的目标不存在时，是否返回结构化失败而非异常。