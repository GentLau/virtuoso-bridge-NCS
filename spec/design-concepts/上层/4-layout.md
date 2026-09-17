# 上层业务包：layout

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

版图创建、编辑、读回、路由、可见性

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read | 读回几何摘要/结构化几何 | 遍历 shapes/instances → 解析 | S |


### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| create | 新建 layout 并批量执行几何命令 | 开 layout(w) → 命令批 → save | S |
| modify | append 模式批量编辑 | 开 layout(a) → 命令批 → save | S |
| route_multilayer | 多层路径规划与落盘 | Python 算坐标 → 路径批 | S |
| route_bus | 总线多 bit 路径 + label | Python 算坐标 → 路径/label 批 | S |
| set_visibility | 层可见性/激活 LPP/视口 | SKILL 设置 | S+G |
| select_delete | 按范围/层删除形状 | 选择 → 删除 → save | S |
| clear_routing | 清除路由 | 选择 → 删除 → save | S |
| delete_cell | 删除 layout cell | 关窗 → 删对象 | S+G |


接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 待修订
- add_rect/add_polygon/add_path/add_label/add_instance/add_mosaic/create_via 作为 create/modify 批内命令；via 解析依赖 techfile 待确认。
