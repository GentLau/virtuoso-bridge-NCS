# Spec 对代码评审的裁决（2026-09-18）

> 依据：`doc/report/代码与spec偏差评审.md`
> 角色：spec owner 对 D 系列与 O8/O9 的最终口径裁决；O1–O7 属代码缺陷，不在本文件重复。

## 一、结论

- **D1 / D4 / D8 需要改 spec，已经落地**；
- **D2 / D3 / D5 / D6 / D7 是代码实现缺陷，spec 不改**；
- **O8 / O9 不构成 spec 冲突**：O8 保持“按 OS 语义”，O9 的“零落盘”原本只指 registry/候选，代码可保留。

## 二、逐项裁决

| 项 | 裁决 | 现状 |
|---|---|---|
| D1 `query` 的 token 传参 | **统一 keyword-only**：`middle.query(*, token)`，与五业务接口一致 | spec v34 已定；代码需把位置调用改为 `query(token=…)` |
| D2 `execute_skill` 缺 log 参数 | spec 已有，**代码/上层补** | 未改 spec |
| D3 update 只做结构校验 | spec 已有“整体校验”，**代码补** | 未改 spec |
| D4 update 白名单 | 明确：`token`/`registered_at`/未声明字段一律拒绝；扁平别名不属公共协议 | spec v31 已定 |
| D5 registry 换 token | spec 已写 token 不轮换，**代码补** | 未改 spec |
| D6 并发 update 丢更新 | spec 已写“文件锁 + 读改写原子替换”，**代码补** | 未改 spec |
| D7 公共 API 绕过第六步确认 | spec 已写第六步显式确认，**代码补** | 未改 spec |
| D8 `expected_hostname/user` 运行期比对 | 收窄为“**注册探测时比对，运行期不强制比对**” | spec v32 已定 |
| O8 目录目标原子性 | 保持“按 OS 语义”，不承诺无窗口 | 不改 spec |
| O9 指纹临时文件 | 前五步零落盘仅指 registry/候选；临时文件允许 | 不改 spec |

## 三、相关提交

- `21f1ee9`：D1（初版位置参数）+ D4 + D8；
- `44c9779`：D1 最终统一为 keyword-only。

## 四、留给代码侧的工作

- O1–O7 按代码评审建议修复；
- D2/D3/D5/D6/D7 按 spec 对齐；
- D1 的调用点改为 `query(token=…)`。