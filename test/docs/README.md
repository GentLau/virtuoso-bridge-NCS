# 测试须知（`test/docs/`）

> 一页纸：看完就能开测。细则在文末链接。
> 维护者：测试工程师 ｜ 2026-09-22

**测试分三级**（判据：需不需要真机）——**离线**（不需要）/ **半真机**（需要真机但只跑局部，用于定位）/
**真机**（全真环境、按用户完整动作序列）。各级目录映射与命令清单见 [测试架构.md](测试架构.md) §2 与 §5；
就地入口是三级 README：[offline](../offline/README.md) / [semi](../semi/README.md) / [live](../live/README.md)。

## 1. 怎么测

```powershell
# 提交前必须全绿（与 CI 同口径：unit + integration + scenario）
python -m pytest test/offline/unit test/offline/integration test/offline/scenario

# 真机 pytest（需环境就绪，见 环境说明.md）
python -m pytest test/live/e2e          # 真机 pytest（未满足环境条件会跳过）

# 准出全量（fail-fast，产出覆盖率与证据）
powershell -NoProfile -File test/shared/runners/run_coverage.ps1 -IncludeExtended
```

## 2. 新测试放哪

| 要测什么 | 放哪 | 依赖 |
|---|---|---|
| 函数、契约、参数校验、错误分支 | `test/offline/unit/` | 无网络、无真机 |
| 真实 socket、真实子进程 | `test/offline/integration/` | 本机 | 
| 跨组件流程（如注册六步） | `test/offline/scenario/` | 本机 |
| 必须真 Virtuoso / 真靶机 | `test/live/e2e/`（或 `test/` 下对应子目录） | 远端环境 |
| 手工验收、压测、探针、覆盖率 TB | `test/semi/`、`test/live/` 对应子目录 | 见该目录 README |

一句话判据：**用了 mock 就别放 TB；要真机就别放三层**。

## 3. 文件写到哪

| 谁 | 写哪 |
|---|---|
| 客户端（本机 Python） | 入口 `init_work_dir()` 绑定的 work root，及其 `temp/`、`log/`、`artifact/` |
| 远端（靶机） | 注册表 `roles.<role>.root`（默认 `~/.virtuoso-bridge/<user>/`） |
| Cadence 工程产物 | `~/project/<user>/tb-out/<run-id>/` |
| TB 证据 | `test/artifacts/evidence/<run-id>/`（默认 gitignore；关键证据 `git add -f`） |
| TB 环境 | `test/artifacts/env/<name>/`（可复用 work-dir / registry） |
| 零时产物 | `test/artifacts/tmp/`（可随时删，仓库根不得落任何产物） |

**三条禁止**：共享 `/tmp`、`$HOME` 根、自己拼 `~/...` 字符串。
路径一律走 helper：客户端 `common/paths.py`，远端 `common/remote_paths.py`。

## 4. 提交前

- [ ] 三层全绿；
- [ ] 离线级（`unit`/`integration`/`scenario`）没在仓库里落文件（临时目录用 `tempfile.mkdtemp()`，`test/conftest.py` 负责清）；
- [ ] 证据能回答"输入 → 期望 → 实测"；
- [ ] 修缺陷有红→绿一对证据。

## 5. 细则

[推荐测试环境.md](推荐测试环境.md)（**可选场景 + 跑法，先看这个**）｜[环境说明.md](环境说明.md)（主机/靶机/恢复）｜[文件使用规范.md](文件使用规范.md)（写入规则）｜[用例分层与归口.md](用例分层与归口.md)｜[证据与报告.md](证据与报告.md)｜[测试架构.md](测试架构.md)（分层与覆盖模型）

> 过程资产（问题台账、覆盖度评估、审计报告）在 [`../reports/`](../reports/README.md)：评审前看 [问题登记.md](../reports/问题登记.md) 即可，不是必读守则。
