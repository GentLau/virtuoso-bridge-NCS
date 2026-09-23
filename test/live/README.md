# `test/live/` —— 真机级

> **级别：真机测试**（全真环境；所有操作严格按用户实际能产生的操作执行）。
> 判定与目录映射见 [`../docs/测试架构.md`](../docs/测试架构.md) §2。

## 内容

| 子目录 | 放什么 | 对应"用户动作" |
|---|---|---|
| `registration/` | `registration_http_six_step_tb.py` | 注册页六步全流程（apply→validate→probe→deploy→verify→commit） |
| `transport/` | `cov_remote_real.py` | 五接口全量（skill/command/file/gui/spectre） |
| `packages/` | 10 套上层包 E2E（infra/cellview/schematic/symbol/layout/verilog/veriloga/skillref/spectre/maestro） | 业务包的真实操作序列 |
| `e2e/` | 真机 pytest（原 `test/e2e`） | middle+bottom 真链路 |
| `stress/` | 混合并发、饱和、多用户路由、100 用户规模 | 真实客户端压测 |
| `flows/` | S2 role 分主机、S4 规模、S11 工程链（原理图→LVS→前后仿） | 跨包工程流程 |

## 怎么跑

```powershell
python test/live/registration/registration_http_six_step_tb.py --work-dir test/artifacts/env/reg-six-local `
    --user vbsixlocal --local-mode --token vb-six-local --out test/artifacts/env/reg-six-local/evidence.json
python test/live/transport/cov_remote_real.py --work-dir test/artifacts/env/log-vblog --token vb-vblog
python test/shared/runners/run_all_http.py                                   # 10 套包 E2E
$env:VB_E2E='1'; python -m pytest test/live/e2e -q
python test/live/stress/http_mixed_stress_tb.py --work-dir test/artifacts/env/http-stress2 `
    --remote-token vb-vblog --remote-daemon-port 65121 `
    --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 6
python test/live/flows/role_split_tb.py                               # S2
python test/live/flows/scale_100_tb.py --count 100 --rounds 2         # S4
python test/live/flows/s11_full_flow.py                               # S11（需已加载 PDK 的 CIW）

# 准出（离线+半真机+真机合并集合与覆盖率，fail-fast）
powershell -NoProfile -File test/shared/runners/run_coverage.ps1 -IncludeExtended
```

## 纪律

- 每条结论必须有证据（`test/artifacts/<run-id>/`），且能看出"判据是什么"；
- 环境缺陷（靶机离线、端口被占、display 缺失）与被测缺陷**分开记录**，前者不计失败；
- 注册表按场景隔离（一场景一份 `registry.json`），不跨场景复用。
