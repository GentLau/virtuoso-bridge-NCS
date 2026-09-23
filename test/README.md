# 测试体系（`test/`）

> **规范唯一入口**：[`docs/README.md`](docs/README.md)。新建用例、跑测和交证据前先读该目录。

## 三级测试架构

**判据只有一个问题：这条用例需不需要真实环境？**

| 级别 | 定义 | 谁跑 / 何时 | 怎么跑（示例） |
|---|---|---|---|
| **离线测试** | 不需要真实环境，纯 Python（允许 mock/stub/fake 夹具） | 每次提交、CI | `python -m pytest test/offline/unit test/offline/integration test/offline/scenario` + `test/offline/core/*` |
| **半真机测试** | 需要真机，但**不一定完整运行**：探针、单点、局部链路；用于过程调试与确认 | 定位问题、确认环境时 | 例：`python test/semi/probes/calibre_env_probe.py --facts`、`cov_registration_real.py`（1–4 步）、`log_matrix_real_tb.py` |
| **真机测试** | **全真环境**，操作严格按用户实际动作序列（六步注册、五接口、包 E2E、工程链、压测） | 验收轮 | 例：`registration_http_six_step_tb.py`、`cov_remote_real.py`、`runners/run_all_http.py`、`flows/*` |

> 三级不是"高低之分"：离线级保每次提交，半真机级保定位效率，真机级保验收结论。
> 详细判定细则与"目录 → 级别"全量映射见 [`docs/测试架构.md`](docs/测试架构.md) §2；
> 各级的完整命令清单见三级 README：[`offline/`](offline/README.md)、[`semi/`](semi/README.md)、[`live/`](live/README.md)
> （不设一键脚本，由测试工程师按场景执行）。

目录就是按三级物理组织的：

```text
test/
  offline/                [离线级] 不需要真机
     unit/   integration/ scenario/      # pytest 默认采集（CI 同口径）
     core/                               # 确定性协议/语义/故障 TB
     frontend/                           # 注册页 mock testbench
  semi/                   [半真机级] 需真机，只跑局部/单点，用于定位
     probes/  fakevirt/  registration/   # 探针 / fake CIW / 注册 1–4 步
     transport/                          # CDS.log 矩阵、一次性通道 burst
  live/                   [真机级] 全真环境、按用户动作序列（验收）
     registration/  transport/  packages/  e2e/  stress/  flows/
  shared/                 [跨级共享] 不属于任何一级
     fixtures/             夹具代码（fake daemon、Windows no-window、压测客户端、脚本化 daemon）
     runners/              运行脚本（覆盖率/套件编排/环境准备，手工执行）
     standards/            规范指针（真源在 docs/）
     archive/              历史资产（非准出，不作为送审证据）
  docs/                   [规范] 其他工程师唯一入口：环境/文件/分层/证据/推荐环境
  reports/                [报告] 过程资产：问题台账、覆盖度、审计、首轮报告、覆盖率证据包
  plans/                  [计划] 按主题拆分的测试计划
  artifacts/              [数据] 运行数据，整目录 gitignore
     env/                  环境：可复用 work-dir / registry（TB 的 --work-dir 指这里）
     evidence/             产物：一次运行的证据（json/txt/log、报告快照）
     tmp/                  零时产物：可随时删（coverage 数据、调试 dump）
     admin-token.txt       唯一敏感输入（gitignored，勿复制到别处）
  conftest.py  README.md
```

## 文件放哪（新文件一律按此表）

| 你要放什么 | 位置 | 例 |
|---|---|---|
| 环境（可复用工作目录、注册表、fake 群） | `test/artifacts/env/<name>/` | `env/log-vblog/registry.json` |
| 一次运行的产物与证据 | `test/artifacts/evidence/<run-id>/` | `evidence/s11-postsim/postsim-evidence.json` |
| 零时产物（可随时删） | `test/artifacts/tmp/` | `tmp/coverage-db/`、`tmp/dbg-*.txt` |
| 报告、台账、覆盖度、审计 | `test/reports/` | `reports/首轮测试报告.md` |
| 测试计划 | `test/plans/` | `plans/总览与执行约定.md` |
| 给其他工程师的规范 | `test/docs/` | `docs/文件使用规范.md` |
| 跨级代码与脚本 | `test/shared/{fixtures,runners,standards}/` | `shared/runners/run_all_http.py` |
| 历史脚本（不入准出） | `test/shared/archive/` | — |

三级（`offline/ semi/ live/`）只放**用例与用例自己的进入脚本**；共享夹具、运行脚本、证据、报告各有固定位置，不放顶层。

## 常规运行

```powershell
# 离线级：pytest 三个离线目录 + offline/core 的四个离线 TB
python -m pytest test/offline/unit test/offline/integration test/offline/scenario -q
python test/offline/core/semantics_tb.py --out test/artifacts/evidence/semantics-green.json
```

`pyproject.toml` 的 `testpaths` 固定为离线三级目录，CI 不会误收集手工 TB；
半真机/真机级一律显式运行（见上表入口）。

## 真机/覆盖率

```powershell
powershell -NoProfile -File test/shared/runners/run_coverage.ps1 -IncludeExtended
```

详细目录说明、单 TB 命令和环境要求见三级 README（[offline](offline/README.md) /
[semi](semi/README.md) / [live](live/README.md)）与 [`docs/测试架构.md`](docs/测试架构.md) §5。

## 文件纪律

所有测试、TB 和探针必须遵守 [`docs/文件使用规范.md`](docs/文件使用规范.md)；
`shared/standards/TB文件使用规范.md` 只是旧路径兼容指针。

## 计划与报告

- 测试计划：`test/plans/总览与执行约定.md` 及分册。
- 覆盖率报告：`doc/测试覆盖报告.md`。
- 真机测试报告：`doc/report/五接口三环境真机测试报告.md`。
- 接口调用指南：`doc/接口调用指南.md`。
