# P-038 · 声明支持 Python 3.9，但裸装 3.9 无法导入（pydantic 求值 PEP 604 注解；pyproject 未声明 `eval_type_backport`）

| 字段 | 值 |
|---|---|
| 级别 | P2（任何 3.9 客户端/CI 作业不可用；跨客户端一致性在 3.9 上不成立） |
| 层 | 其他（公共 / 打包） |
| 归属 | 设计侧（打包/依赖或 requires-python 口径） |
| 状态 | **待设计修（已报 `bug-20260922T141119Z-vblog-5e939e33`）** |
| 位置 | `src/common/registry.py:155`（`mode: Literal["local","remote"] | None`）；`pyproject.toml:9`（`requires-python = ">=3.9"`）；dev extra 未含 `eval_type_backport` |
| 首报 | 第五轮（2026-09-22；已报 `bug-20260922T141119Z-vblog-5e939e33`） |
| 最近更新 | 2026-09-28（复测：lab py3.9 因已装 backport 能跑，裸装仍会挂） |

## 现象

3.9 上 pydantic 求值 PEP 604 注解直接抛 `TypeError: Unable to evaluate type annotation ... install the eval_type_backport package`；全仓 48 文件 785 处 PEP 604 注解。**2026-09-28 复测**：wsl-gent `/usr/bin/python3.9`（pydantic 2.13.5）因已装 `eval_type_backport` 可正常 import；裸装 3.9 仍会挂。

## 复现

```text
`/usr/bin/python3.9 -c "from common.registry import UserEntry"`（未装 backport 时失败）；见 `round7-测试报告.md` §2 Linux 客户端口径
```

## 证据

台账 P-038 行；bug id `bug-20260922T141119Z-vblog-5e939e33`；wsl-gent py3.9 复测（`backport: True`、`registry import OK`）

## 验收判据（修好即转绿）

二选一：`requires-python>=3.10` 并删 CI 3.9，或把 `eval_type_backport; python_version<"3.10"` 写进依赖并让 3.9 作业真跑绿

## 下一步 / 责任人

设计侧定口径；测试侧按口径复跑 py3.9 离线三层


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
