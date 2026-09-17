# 上层业务包：skill_tooling

> 版本：Draft v1
> 日期：2026-09-17
> 状态：Draft（待共同修订，暂未纳入 README 治理）
> Supersedes：无
> 定位：业务包/业务操作一般契约见[1-上层.md](1-上层.md)；五业务接口见[四层整体架构与接口 §4](../总览/1-四层整体架构与接口.md)。

## 1. 业务操作

SKILL 工具：组合、查找、文档检索

### 1.1 读操作（不改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| compose_skill | 有序 SKILL 串组合（纯本地） | 过滤空 → progn | — |
| find_skill | SKILL Finder 搜索 | 定位 .fnd → 解析 → 匹配 | C+D |
| skill_info | 函数 More Info | 取 .tgf/HTML → 解析 | C+D |
| doc_search | Cadence 文档检索 | 发现 → 索引 → 排序 | C+D |


### 1.2 写操作（改变业务服务器状态）

| 操作名 | 说明 | 步骤摘要 | 接口 |
|---|---|---|---|
| load_il | 上传并 load IL | 上传 → load(path) | U+S |


接口简写：S=execute_skill、C=run_command、U=upload_file、D=download_file、G=run_gui_command、Sp=run_spectre_command。

## 2. 待修订
- 纯本地解析不占中层接口。
