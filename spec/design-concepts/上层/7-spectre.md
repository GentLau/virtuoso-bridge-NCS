# 上层业务包：spectre

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

独立 Spectre 仿真与结果解析

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| check_license | 查二进制/版本/license | spectre -V / lmstat -a → 解析 | Sp+C |
| parse_psf | 解析 PSF ASCII | 下载 → 解析 HEADER/VALUE | D |
| aggregate | 聚合结果目录 | 选分析 → 合并信号 | D |
| parse_sweep | 解析参数扫描结果 | 识别 sweep 布局 → 建索引 | D |
| measure | 计算延迟/带宽/噪声等指标 | 纯 Python 数值 | — |
| result_io | 导出 CSV/JSON | 纯 Python 写文件 | — |


### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| run | 跑一个仿真 | 拼命令 → 执行 → 取 .raw/.psf | Sp+D |
| run_batch | 固定批次并行跑 | 逐 netlist 分发 → 收集 | Sp+D |


接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 待修订
- build_command/stage/parameterize 为内部步骤不暴露；run_pool/增量池暂缓；evas_flow 另议。
