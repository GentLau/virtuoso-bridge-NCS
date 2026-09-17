# 上层业务包：maestro

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

Maestro/ADE 会话、配置、运行与结果

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| read_focused | 读当前焦点会话元数据 | 窗口/会话探测 | S |
| snapshot | 全量快照（XML/点文件包） | 探测 → 导出 → 过滤 → 打包 | S+C+D |
| export_netlist | 按 corner 导网表 | maeCreateNetlistForCorner | S+D |
| read_results | 读全部点/spec/yield | 导出 Detail CSV → 下载 → 解析 | S+D |
| export_waveform | 导出一条 OCEAN 波形 | openResults → ocnPrint → 下载 | S+D |


### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| open | 后台或 GUI 打开会话 | maeOpenSetup/窗口管理 | S+G |
| close | 关闭会话 | maeCloseSession/关窗 | S+G |
| ensure_view | 确保 maestro view 落盘 | open → save → close | S |
| configure | 配置 test/analysis/output/spec/var/option | 按 alist 逐项 mae* 调用 | S |
| setup_corner | 建/载 corner | maeSetCorner/模型绑定 → load | S+U |
| run | 异步启动仿真 | maeRunSimulation → history | S |
| run_and_wait | 启动并等完成 | callback marker → 轮询 → 状态 | S+C+G |
| waveform_viewer | 交互打开/画图/关闭 | AWV 窗口操作 | S+G |
| set_simulator_mode | 设置仿真器模式/预置 | asi* 设置 | S |


接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 待修订
- set_var/set_parameter/set_env_option/set_sim_option/analysis/output/spec 是否全部并入 configure 待定；长任务 start+query 还是 run_and_wait 待定。
