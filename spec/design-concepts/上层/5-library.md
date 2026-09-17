# 上层业务包：library

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

库与分类管理、单元清单

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| list | 列出所有库 | ddGetLibList → 解析 | S |
| get | 读库元数据(path/tech) | ddGetObj → 读属性 | S |
| harvest | 库/单元/视图清单与报告 | 遍历 cells/views → JSON | S |


### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| create | 建库 | ddCreateLib → 读回校验 | S |
| delete | 删库 | ddDeleteObj | S |
| rename | 库改名 | ccpRename | S |
| bind_tech | 绑定技术库 | techBind/techSet → 读回 | S |
| categories | 分类的增删改查 | ddCat 操作 → 重开校验 | S |


接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 待修订
- open/save/close 是否单列操作待定；diagnose_locks 暂缓。
