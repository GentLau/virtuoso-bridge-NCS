# 上层业务包：symbol

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

符号创建、自动生成、语义读回

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read | 读回 terms/labels/pinOrder/bbox | 只读打开 → 收集 → 解析 | S |


### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| create | 按几何/label/pin 规格手动建 symbol | 开 symbol → 命令批 → check/save | S |
| generate | 从原理图自动生成 symbol（校验/回滚） | 取 pin 序 → 临时 view → 校验 → 覆盖安装 | S |


接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 待修订
- 原语级 label/pin 创建作为 create 批内命令。
