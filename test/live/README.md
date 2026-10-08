# `test/live/` —— 真机级

> **级别：真机测试**（全真环境；所有操作严格按用户实际能产生的操作执行）。
> 判定与目录映射见 [`../docs/README.md`](../docs/README.md) §1 / §3。

## 内容

| 子目录 | 放什么 | 对应"用户动作" |
|---|---|---|
| `registration/` | 六步注册 + 跨主机 / 真 CIW / py2.7 / host-key / 控制面（清单以目录为准） | 注册页六步全流程（apply→validate→probe→deploy→verify→commit）及变体 |
| `transport/` | 五接口全量、CDS.log 主题、超时恢复、disposable CIW（清单以目录为准） | 传输层真实主题 |
| `packages/` | 上层业务包 E2E（按包一份，清单以目录为准） | 业务包的真实操作序列 |
| `e2e/` | 真机 pytest（原 `test/e2e`） | middle+bottom 真链路 |
| `stress/` | 混合并发、饱和、多用户路由、100 用户规模 | 真实客户端压测 |
| `flows/` | S2 role 分主机、S4 规模、S11 工程链（原理图→LVS→前后仿） | 跨包工程流程 |
| `manual/` | 真机手工体验工具（业务操作体验台） | 人直接输入业务操作并查看返回 |

## 怎么跑

```powershell
python test/live/registration/registration_http_six_step_tb.py --work-dir test/artifacts/env/reg-six-local `
    --user vbsixlocal --local-mode --token vb-six-local --out test/artifacts/env/reg-six-local/evidence.json
python test/live/transport/cov_remote_real.py --work-dir test/artifacts/env/log-vblog --token vb-vblog
python test/shared/runners/run_all_http.py                                   # packages 全部套件（便利封装；清单/顺序见脚本 SUITES）
$env:VB_E2E='1'; python -m pytest test/live/e2e -q
python test/live/stress/production_face_stress_tb.py --workers 6 --rounds 6   # 自起生产面压测
# 对接既有真机面：  --base http://127.0.0.1:8127/api/operation --token vb-vblog
python test/live/flows/role_split_tb.py                               # S2
python test/live/flows/scale_100_tb.py --count 100 --rounds 2         # S4
python test/live/flows/s11_full_flow.py                               # S11（需已加载 PDK 的 CIW）

# 真机手工体验：先启动/确认 8127 业务面，再启动同源代理
python test/live/manual/business_console/serve.py `
  --business-base http://127.0.0.1:8127 --port 8130

# 准出（离线+半真机+真机合并集合与覆盖率，fail-fast）
powershell -NoProfile -File test/shared/runners/run_coverage.ps1 -IncludeExtended
```

## 纪律

- 每条结论必须有证据（`test/artifacts/<run-id>/`），且能看出"判据是什么"；
- 环境缺陷（靶机离线、端口被占、display 缺失）与被测缺陷**分开记录**，前者不计失败；
- 注册表按场景隔离（一场景一份 `registry.json`），不跨场景复用。
