# 测试体系（`test/`）· 结构地图

> **这份文件只回答三件事**：`test/` 里什么在哪、新东西放哪、手动怎么跑全量。
>
> - 怎么写 TB / 探针 / 用例 → [`docs/写TB规范.md`](docs/写TB规范.md)
> - 环境、实例与 token → [`docs/环境与场景.md`](docs/环境与场景.md)
> - 开发向总入口（三级分类简版） → [`docs/README.md`](docs/README.md)
>
> **维护者**：测试工程师。目录 / TB 增删时必须同步本文件对应条目。
> **本文件面向测试侧内部**；给其他工程师的入口是 [`docs/README.md`](docs/README.md)。
> **本文件不写会过期的数量**（如“N 套包”）：数量只出现在子目录 README 的文件清单里，
> 清单随增删更新；需要即时数字时用 `rg --files` 现场查。

## 0. 30 秒版（测试侧速查）

- **写用例**：不需要真机 → `offline/{unit,integration,scenario}`；要真机但只验证单点 → `semi/`；
  全真环境验收 → `live/`。
- **找环境 / token**：看 [`docs/环境与场景.md`](docs/环境与场景.md) §2。
- **手动跑全量**：离线三层 pytest → 真机前置 `resident_env_check` → packages → registration →
  flows → transport/e2e/stress（第 3 节给了命令与判据）。
- **产物**：`artifacts/{env,evidence,tmp}`；`tmp/` 就是临时区，有临时文件很正常，不进 git 即可。
- **规范底线**：写操作必须读回比对；skip 必须写原因；结论只有 PASS / FAIL / PENDING。
- 详细目录地图见 §1，判定见 §2，手动全量见 §3；对外（其他工程师）入口在 [`docs/README.md`](docs/README.md)。

## 1. 目录地图

```text
test/
├── offline/          离线级：不需要真机；每次提交必须全绿
│   ├── unit/         函数级 / 契约 / 参数校验 / 错误分支（CI 采集）
│   ├── integration/  真实 socket / 真实子进程，不连 Virtuoso（CI 采集）
│   ├── scenario/     跨组件流程：注册、隔离、local 链（CI 采集）
│   ├── core/         确定性协议 / 语义 / 故障 TB（手工，非 pytest）
│   └── frontend/     注册页 mock testbench（手工）
├── semi/             半真机级：要真机，但只跑局部 / 单点，用于定位
│   ├── probes/       单点探针（环境事实、API 语义、疑难复现）
│   ├── transport/    通道 / 日志 / 凭据 / 安装幂等
│   ├── registration/ 注册 1–4 步、失败矩阵
│   └── fakevirt/     CIW 替身 + 真 daemon + 真 middle
├── live/             真机级：全真环境，按用户动作序列验收
│   ├── packages/     上层业务包 E2E（按包一份）
│   ├── flows/        完整工程链路（ADC / SerDes / S11 / 多用户 / 多跳 / 规模）
│   ├── registration/ 六步注册、跨主机、真 CIW、py2.7、host-key、控制面
│   ├── transport/    传输层真机主题（CDS.log、超时恢复、disposable CIW）
│   ├── e2e/          真机 pytest（含 SSH 后端）
│   ├── stress/       并发 / 资源回收 / 多用户锁
│   └── manual/       人工交互场景（业务控制台等）
├── shared/           跨级共享，不属于任何一级
│   ├── fixtures/     夹具：fake daemon、Windows no-window、压测客户端
│   ├── runners/      便利 runner / 编排脚本（可临时失修，不是契约）
│   └── archive/      历史资产（非准出，不作为送审证据）
├── docs/             规范：只有三份（README / 写TB规范 / 环境与场景）
├── reports/          报告与台账
│   ├── bugs/         未关闭缺陷的唯一跟踪视图（逐条卡片）
│   ├── internal/     测试侧内部资料（Runbook / 架构 / 全量准则）
│   ├── coverage-pack/ 覆盖率证据包
│   └── round*/       各轮过程资产（历史轮次）
├── plans/            按主题拆分的测试计划
└── artifacts/        运行数据（默认 gitignore，除非显式入库）
    ├── env/          可复用环境：work-dir / registry / fake 群
    ├── evidence/     一次运行的证据（只增不改）
    └── tmp/          零时产物（可随时整目录删除）
```

## 2. 判定：新用例放哪

| 判据 | 放哪 | 进 CI |
|---|---|---|
| 不需要真机、纯 Python（允许 mock / stub / fake） | `offline/{unit,integration,scenario}` | ✅ |
| 离线 TB：确定性协议 / 语义 / 故障注入 | `offline/core` | ❌（手工） |
| 注册页 mock 面板 | `offline/frontend` | ❌（手工） |
| 要真机，但只验证单点 / 定位问题 | `semi/**` | ❌ |
| 全真环境、按用户动作序列验收 | `live/**` | ❌ |
| 夹具 / runner / 规范 / 报告 / 计划 | `shared/**`、`docs/`、`reports/`、`plans/` | — |

命名：pytest 用例 `test_<主题>.py`；TB `test_<主题>_tb.py` 或 `<包>_e2e_tests.py`；
用例名 `test_<行为>_<期望>`。离线级的额外约束（不得在仓库落文件、unit 不得占固定端口等）
见 [`docs/写TB规范.md`](docs/写TB规范.md) §7。

## 3. 手动跑全量（契约）

> **手动命令是契约**；`shared/runners/**` 是便利封装，可能临时失修。
> 每份 TB 的准确参数以文件头 docstring / `--help` 为准；本节只定义顺序、前置与通过判据。

### 第 0 步 · 前置（真机轮必做）

```powershell
python test/shared/runners/resident_env_check.py     # remote 实例逐个 1+1；有一个不通即非 0
# 控制面就绪：GET http://127.0.0.1:8124/api/process/status（带 admin token）→ state: ready
# 业务面健康：GET http://127.0.0.1:8127/health → status: ok
# 目标实例：
python test/shared/runners/env_check.py --base http://127.0.0.1:8127/api/operation `
    --token <token> --require-lib <lib>
```

实例 / token 清单见 [`docs/环境与场景.md`](docs/环境与场景.md) §2、§6。
真机结论必须跑在“标准形态客户端 + 8127 业务面”，`--transport direct` 只做定位、
不得计入真机通过（[`docs/写TB规范.md`](docs/写TB规范.md) §11）。

### 第 1 步 · 离线（不需要任何环境；每轮先跑）

```powershell
# CI 同口径：三层 pytest
python -m pytest test/offline/unit test/offline/integration test/offline/scenario

# 离线 TB：按 core/README.md 清单逐份跑（各支持 --out）
python test/offline/core/api_server_tb.py --out test/artifacts/evidence/<run-id>/api-server.json
```

判据：pytest 全绿（skip 必须有 reason）；TB 退出码 0，证据里能看到期望 / 实际比对。

### 第 2 步 · 半真机（按需，用于定位）

```powershell
python test/semi/probes/calibre_env_probe.py --facts
# 其余探针 / TB 的用法见文件头；清单见 semi/README.md 与各子目录 README
```

### 第 3 步 · 真机 packages

```powershell
# 单套手动（参数两种写法并存：--base / --api，以 --help 为准）
python test/live/packages/schematic_e2e_tests.py --transport http `
    --base http://127.0.0.1:8127/api/operation `
    --work-dir test/artifacts/env/log-vblog `
    --out test/artifacts/evidence/<run-id>/schematic.json

python test/live/packages/infra_e2e_tests.py --transport http `
    --api http://127.0.0.1:8127/api/operation --token vb-vblog `
    --work-dir test/artifacts/env/log-vblog `
    --out test/artifacts/evidence/<run-id>/infra.json

# 整批（便利封装）：python test/shared/runners/run_all_http.py
```

顺序注意：maestro 相关套件放最后——模态框会卡 CIW，排在前面会连带失败。

### 第 4 步 · 真机 registration

```powershell
python test/live/registration/registration_http_six_step_tb.py `
    --work-dir test/artifacts/env/reg-six-<run-id> --user <user> `
    --out test/artifacts/evidence/<run-id>/reg-six.json
# 跨主机 / 真 CIW / py2.7 / host-key / 控制面读写：见 registration/README.md
```

### 第 5 步 · 真机 flows

```powershell
python test/live/flows/adc_sar_flow_tb.py `
    --work-dir test/artifacts/env/log-vblog `
    --out test/artifacts/evidence/<run-id>/adc-sar.json

python test/live/flows/s11_full_flow.py --token vb-s11 `
    --run-dir test/artifacts/evidence/<run-id>/s11        # 注意是 --run-dir，不是 --out
# 全清单与各 TB 参数：live/flows/README.md
```

### 第 6 步 · 真机 transport / e2e / stress

```powershell
python test/live/transport/cov_remote_real.py `
    --work-dir test/artifacts/env/log-vblog --token vb-vblog

$env:VB_E2E='1'; python -m pytest test/live/e2e -q

python test/live/stress/production_face_stress_tb.py `
    --base http://127.0.0.1:8127/api/operation --token vb-vblog --workers 6 --rounds 6
```

### 第 7 步 · 收尾与记录

- **资源盘点**：远端无隧道 / mux master、无端口残留、无临时文件增长；客户端无进程堆积。
- **落报告**：本轮结果写 `reports/`（索引见 [`reports/README.md`](reports/README.md)）。
- **落缺陷**：新问题按 [`reports/bugs/_模板.md`](reports/bugs/_模板.md) 立卡（未关闭项唯一视图），
  并同步台账与 `shared/runners/make_bug_cards.py`。
- **结论**只有 PASS / FAIL / PENDING；不用历史绿灯冒充当前结论（[`docs/写TB规范.md`](docs/写TB规范.md) §4）。

## 4. 文件放哪（新文件一律按此表）

| 你要放什么 | 位置 | 例 |
|---|---|---|
| 环境（可复用 work-dir、注册表、fake 群） | `artifacts/env/<name>/` | `env/log-vblog/registry.json` |
| 一次运行的产物与证据 | `artifacts/evidence/<run-id>/` | `evidence/s11-postsim/postsim-evidence.json` |
| 零时产物（可随时删） | `artifacts/tmp/` | `tmp/coverage-db/`、调试 dump |
| 报告、台账、覆盖度、审计 | `reports/` | `reports/round10/round10-测试报告.md` |
| 未关闭缺陷卡 | `reports/bugs/` | `bugs/P-121-*.md` |
| 测试计划 | `plans/` | `plans/总览与执行约定.md` |
| 给开发看的规范 | `docs/` | `docs/写TB规范.md` |
| 跨级代码与脚本 | `shared/{fixtures,runners}/` | `shared/runners/run_all_http.py` |
| 历史脚本（不入准出） | `shared/archive/` | — |

`offline/ semi/ live/` 只放**用例与用例自己的进入脚本**；共享夹具、运行脚本、
证据、报告各有固定位置，不放这三层顶层。

## 5. 产物与生命周期

| 区域 | 生命周期 | 规则 |
|---|---|---|
| `artifacts/env/` | 跨轮复用 | 改环境前先确认没有服务在跑；一个场景一份注册表，不跨场景复用 |
| `artifacts/evidence/` | 一轮一份，**只增不改** | 用 `<run-id>/` 分目录；证据含环境指纹、期望 / 实际、后置现场 |
| `artifacts/tmp/` | 零时区：有临时文件、大目录都属正常 | 可随时整目录删除；不进 git 跟踪即可；coverage 数据放 `tmp/coverage-db/` |

- `artifacts/admin-token.txt` 是目录内唯一敏感输入：勿复制、勿写进报告或提交。
- `test/artifacts/*` 默认 gitignore；要入库的关键证据用 `git add -f`，并在提交说明写清支撑哪条结论。
- 证据里不得出现 token / 口令 / 私钥。

## 6. 维护规则

1. **入口唯一**：结构看本文件；写法看 `docs/写TB规范.md`；环境看 `docs/环境与场景.md`；
   轮次索引看 `reports/README.md`。不在这四处之外再复制一份。
2. **新增即登记**：新 TB / 探针 / runner 放进目录后，必须更新所在子目录 README 的文件清单
   （或本文件的索引表）；删除时同步删条目。
3. **不写数量**：清单文件写“谁在、干什么”，不写“目前 N 个”；需要数字现场 `rg --files` 查。
4. **命名**：见 §2；历史命名不强制返工，但改动时优先按规范命名。
5. **缺陷流**：[`reports/bugs/`](reports/bugs/README.md) 是缺陷跟踪唯一视图（未关闭卡片 +
   [已关闭记录](reports/bugs/已关闭-近期.md)）；历史台账 `reports/问题登记.md` 自 2026-10-08 起停更，
   仅存档；条目由 `make_bug_cards.py` 刷新。
6. **报告流**：当前轮报告写 `reports/`，历史轮次保留 `reports/round<N>/`；索引以
   `reports/README.md` 为准。

## 7. 规范与索引

| 入口 | 用途 |
|---|---|
| [`docs/README.md`](docs/README.md) | 开发向三级分类 / 提交前检查（规范简版） |
| [`docs/写TB规范.md`](docs/写TB规范.md) | 六步流程、判据强度、状态还原、证据与路径纪律 |
| [`docs/环境与场景.md`](docs/环境与场景.md) | 常驻实例与 token、场景清单、自检、非日常环境申请 |
| [`offline/README.md`](offline/README.md) | 离线级清单与运行方式 |
| [`semi/README.md`](semi/README.md) | 半真机级清单与运行方式 |
| [`live/README.md`](live/README.md) | 真机级清单与运行方式 |
| [`shared/README.md`](shared/README.md) | 夹具 / runners / 规范的共享资产说明 |
| [`reports/README.md`](reports/README.md) | 报告与台账索引 |
| [`reports/bugs/README.md`](reports/bugs/README.md) | 未关闭缺陷卡片（唯一跟踪视图） |
| [`plans/README.md`](plans/README.md) | 测试计划分册索引 |
| [`artifacts/README.md`](artifacts/README.md) | 运行数据目录说明 |
