# 上层业务包：digital_import

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

GDS/Verilog 数字导入与后处理

### 1.1 读操作（不改变业务服务器状态）

（暂无独立读操作；校验读回在写操作内）


### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| import_gds | GDS → cellview（strmin） | 上传 → strmin → 轮询日志 → 校验 | U+S+C+D |
| import_verilog | 结构 Verilog → schematic/symbol | 上传 → ihdl → 轮询日志 → 校验 | U+S+C |
| add_power_labels | PG 网加 label | 定位 pin → 变换 → 建 label | S |
| restyle_labels | 标签样式/方向后处理 | 解析 Tcl → 映射 → SKILL 批 | S+U |


接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 待修订
- import_pipeline 编排暂缓；ihdl 旧代码缺日志轮询，需补。
