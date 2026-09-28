# P-077 · 显式 `role.daemon.python` 传裸命令名（如 `python3`）时注册第 3 步失败；运行时可解析 PATH

| 字段 | 值 |
|---|---|
| 级别 | P3（口径不一致：注册探测 vs 运行时；会绊住手写配置的用户） |
| 归属 | 设计侧（定口径：探测接受 PATH 名 or spec 写明必须绝对路径） |
| 状态 | **待归属** |
| 位置 | `src/register/flow.py:747`（`remote_executable_exists` → `test -x <显式值>`；`src/register/probe.py:194-199`）vs `src/bridge/resources/ramic_bridge.il:259`（daemon 启动走 `/usr/bin/env … <RBPython>`，PATH 可解析） |
| 首报 | 第五轮（2026-09-23）／见台账 |
| 最近更新 | 2026-09-24（测试侧整理 bug 卡） |

## 现象

注册 apply 给 daemon role 显式 `python: "python3"` → 第 3 步 probe 失败：`explicit daemon python is not executable on wsl-gent: python3`；而同一取值在 daemon 启动路径（IL 里经 env 执行）可用。spec《中层配置文档》只写「显式→校验，缺省→探测」，未写明显式值必须是绝对路径。

## 复现

```text
`PYTHONPATH=src python test/live/registration/registration_role_split_tb.py --work-dir test/artifacts/env/reg-role-split`（改回 `"python": "python3"` 即复现；改绝对路径后 **28/28 通过**）
```

## 证据

`test/artifacts/evidence/tb-sixstep-20260928/registration-role-split.json`（修正后 28/28）、`src/register/flow.py:747`、`src/register/probe.py:194`、`src/bridge/resources/ramic_bridge.il:259`

## 验收判据（修好即转绿）

二选一并落到 spec：① 探测用 `command -v <值>` 解析 PATH 名（与运行时一致）；② spec 明确「显式值必须为绝对路径」，注册页/错误信息同步提示

## 下一步 / 责任人

设计侧定口径；测试侧两个注册 TB 已改绝对路径绕行（`/usr/local/bin/python3`）


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
