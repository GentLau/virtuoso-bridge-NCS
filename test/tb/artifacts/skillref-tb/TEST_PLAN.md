# skillref 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-21
> 对象：`src/pyapi/packages/skillref.py`（业务包：skillref，Kepler 交付）
> 依据：`spec/design-concepts/上层/9-skillref.md`（Draft v11）

## 1. 目标与范围

验证 `search` 与 `info` 两个操作在 local / remote 两种数据源下的行为：

- `search_in` 四层（name/entry/topic/body）与 mode、未知查询；
- `info` 命中 / 未命中 / 内容；
- 配置链路（`config.json` 的 `skillref` 段）与错误口径。

## 2. 环境

| 项 | 值 |
|---|---|
| 业务面 | direct dispatch（8127 基座修复中） |
| token | `vb-vblog`（身份校验） |
| local doc root | `C:\Users\user\Desktop\doc` |
| remote doc root | `/opt/eda/cadence/IC618/doc`（执行账号由 `skillref.doc_token` 配置） |

## 3. 用例

| 用例 | 输入 | 预期 |
|---|---|---|
| SEARCH-01 | local：name/entry/topic 各 1（`dbOpenCellView`）+ body（`ground bounce`，`under=["cpf_ref"]`） | 四层均非空命中 |
| SEARCH-02 | local：exact 精确名 + 未知查询 | exact 命中精确名；未知返回空且 ok=true |
| INFO-01 | local：`dbOpenCellViewByType` 与不存在函数 | 前者 found=true 且正文含函数名；后者 found=false 且 ok=true |
| SEARCH/INFO-02 | remote 同名查询 | 与 local 同口径命中 |
| ERR-01 | 不存在的 doc_root、非法 source | ok=false，错误文案明确 |

## 4. 通过准则

- 全用例 PASS；失败保留响应 error；
- 不断言耗时上限（只记录）；不断言 8123 服务状态（本包与 8123 解耦）。
