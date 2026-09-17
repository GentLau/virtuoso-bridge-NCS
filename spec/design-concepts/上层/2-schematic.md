# 上层业务包：schematic

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

原理图创建、编辑、读回、参数、网表导入导出

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read | 结构化读回实例/线网/pin/参数 | SKILL 分段收集 → 解析记录 | S |
| verify_plan | 读回并与计划比对 | 读回 → 比对诊断 | S |
| export_netlist | 导出 .scs 并下载 | 远端导出 → 下载 | S+D |
| plan | 按约束生成布局计划（纯本地） | 纯 Python 规划/冲突诊断 | — |


### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| create | 新建 cellview 并批量执行编辑命令 | 开 cellview(w) → 命令批 → schCheck/dbSave | S |
| modify | append 模式批量编辑已有 cellview | 开 cellview(a) → 命令批 → schCheck/dbSave | S |
| set_instance_params | 按过滤规则设置实例 CDF 参数 | 解析实例/过滤 → cdfUpdate → check/save | S |
| apply_plan | 把计划落成编辑命令批 | 计划 → 命令批 → 执行 | S |
| import_netlist | 上传网表 → spiceIn → 生成 symbol | 上传 → spiceIn → symbol | U+S+C |
| rename_instance | 重命名实例 | 定位 → 改名 → check/save | S |
| delete_instance | 删除实例 | 定位 → 删除 → check/save | S |
| delete_cell | 删除 cell | 关窗 → 删 DB 对象 | S+G |


接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 待修订
- 原语 add_instance/add_wire/add_label/add_pin/connect_inherited 作为 create/modify 批内命令；是否保留批结构待定。
