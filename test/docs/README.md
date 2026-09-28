# 测试须知（开发向 · 唯一规范入口）

> **读者**：上层 / 中层 / 底层开发工程师（写 TB、跑测试、交证据的人）。
> **读完能做什么**：知道三级测试是什么、常用命令怎么跑、新用例/TB 放哪、提交前要过哪几关。
> **不覆盖**：测试侧内部运维（靶机 / 密钥 / 故障恢复）与历次测试过程 —— 那些在 `test/reports/`
> （内部资料集中在 `test/reports/internal/`）。

## 1. 三级测试（判据只有一个：需不需要真机）

| 级别 | 定义 | 目录 / 资产 | 谁跑、何时 | 入口 |
|---|---|---|---|---|
| **离线** | 不需要真机，纯 Python（允许 mock / fake 夹具） | `test/offline/{unit,integration,scenario}`；`core/`、`frontend/` 是同级的 TB 习惯（显式跑，不进 CI） | 每次提交 / CI | `python test/shared/runners/run_offline_multi.py`、`run_core_multi.py` |
| **半真机** | 需要真机，但只跑局部 / 单点，用于过程调试与确认 | `test/semi/{probes,transport,registration,fakevirt}` | 定位问题、确认环境时 | 例：`python test/semi/probes/calibre_env_probe.py --facts` |
| **真机** | 全真环境，操作严格按用户实际动作序列（验收用） | `test/live/{packages,flows,stress,transport,registration,e2e}` | 验收轮 | 例：`python test/shared/runners/run_all_http.py` |

> 同一行为可以跨级覆盖，但**结论只认与场景匹配的级别**：用了 mock / 纯夹具的不算半真机或真机证据。

## 2. 常用命令

```powershell
# 提交前必须全绿（与 CI 同口径）
python test/shared/runners/run_offline_multi.py
python test/shared/runners/run_core_multi.py

# 真机：11 套包 E2E（含 calibre）+ 五接口
python test/shared/runners/run_all_http.py
python test/live/transport/cov_remote_real.py --work-dir test/artifacts/env/log-vblog --token vb-vblog

# 真机 pytest（环境不满足会按条件跳过）
python -m pytest test/live/e2e
```

参数与全部 runner 清单见 [`../shared/runners/README.md`](../shared/runners/README.md)。

## 3. 新用例 / TB 放哪

| 要测什么 | 放哪 | 进 CI |
|---|---|---|
| 函数、契约、参数校验、错误分支 | `test/offline/unit/` | ✅ |
| 真实 socket / 真实子进程（不要 Virtuoso） | `test/offline/integration/` | ✅ |
| 跨组件流程（注册、隔离、local 链） | `test/offline/scenario/` | ✅ |
| 需要真机，但只验证单点 | `test/semi/`（probes / transport / registration / fakevirt） | ❌ |
| 按用户完整动作序列验收 | `test/live/`（packages / flows / stress / transport / registration / e2e） | ❌ |

命名：用例文件 `test_<被测主题>.py`；TB `test_<主题>_tb.py` 或 `<包>_e2e_tests.py`；用例名 `test_<行为>_<期望>`。

## 4. 提交前检查

- [ ] 三层全绿（离线三层 + 你新增 / 改动对应的半真机或真机 TB）；
- [ ] 离线级（`unit`/`integration`/`scenario`）没有在仓库里落文件（临时目录用 `tempfile.mkdtemp(prefix="vb-")`）；
- [ ] 证据能回答「输入 → 期望 → 实测」，修缺陷有红 → 绿一对证据；
- [ ] 文件**尽可能只使用三处**：客户端 work root / 远端 role root / `~/project/<user>/`（详见 [写TB规范.md](写TB规范.md) §6）；
- [ ] 写完 TB 先跑一次环境检查脚本：`python test/shared/runners/env_check.py --base … --token … --require-lib …`（[写TB规范.md](写TB规范.md) §1 第 1 步）。
- [ ] TB 顶部按 [写TB规范.md](写TB规范.md) §0 补好**注释头（3 栏：作者 / 最后改动到分钟 / 依赖）**。

## 5. 文档地图（开发只要看这三份）

| 你要做什么 | 看哪 |
|---|---|
| 写 TB / 探针 / 压测（六步流程、环境检查脚本、状态还原、判据强度、证据、路径纪律） | [写TB规范.md](写TB规范.md) |
| 挑场景、拿 token、自检、申请非日常环境 | [环境与场景.md](环境与场景.md) |
| 三级分类、运行入口、提交前检查 | 本页 |
| 内部资料（环境 Runbook、测试架构与覆盖度、报告规范） | [`../reports/internal/`](../reports/internal/) —— 开发不必读 |

## 6. 旧文档名对照（历史文档里的链接落到这里查）

| 旧名（已并入其中一份） | 现在看 |
|---|---|
| `测试架构.md` | 本页（三级 / 入口）+ [`../reports/internal/测试架构-内部.md`](../reports/internal/测试架构-内部.md)（边界 / 覆盖度 / 责任） |
| `用例分层与归口.md` | 本页 §3 + [写TB规范.md](写TB规范.md) §7 |
| `文件使用规范.md` | [写TB规范.md](写TB规范.md) §6 |
| `证据与报告.md` | [写TB规范.md](写TB规范.md) §5 + [`../reports/internal/报告与证据-内部.md`](../reports/internal/报告与证据-内部.md) |
| `工作根与测试姿势.md` | [写TB规范.md](写TB规范.md) §3 |
| `TB流程与状态还原规范.md` | [写TB规范.md](写TB规范.md) §1–§4 |
| `推荐测试环境.md` | [环境与场景.md](环境与场景.md) |
| `环境说明.md` | [环境与场景.md](环境与场景.md)（开发部分）+ [`../reports/internal/环境Runbook-内部.md`](../reports/internal/环境Runbook-内部.md)（运维部分） |
