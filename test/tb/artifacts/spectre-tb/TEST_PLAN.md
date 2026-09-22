# spectre 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-21
> 对象：`src/pyapi/packages/spectre.py`（业务包：spectre，Euclid 交付）
> 依据：`spec/design-concepts/上层/7-spectre.md`（Draft v3）

## 1. 目标与范围

验证 5 个对外操作在真实 Spectre 24.1（WSL `wsl-gent`）环境下满足 spec：

| 操作 | 说明 |
|---|---|
| `check_license` | 二进制/版本确认；license 为 best-effort |
| `run` | 单任务 / 多任务批次；`parse=auto` / `parse=none`；`keep_run_dir` |
| `read_results` | 自动识别 raw 目录并解析 |
| `measure` | 在已解析数据上算指标 |
| `export` | CSV/JSON 落盘 |

## 2. 环境

| 项 | 值 |
|---|---|
| 业务面 | direct dispatch（8127 基座修复中，HTTP 回归后补） |
| work-dir | `test/tb/artifacts/log-vblog` |
| token | `vb-vblog` |
| Spectre | 24.1.0.078（`/opt/eda/cadence/SPECTRE241`） |
| 测试网表 | `test/tb/artifacts/log-vblog/artifact/spectre_probe_rc/tb.scs`（5µs RC tran） |

## 3. 用例

| 用例 | 输入 | 预期 |
|---|---|---|
| LICENSE-01 | `check_license` | ok=true、version/bin 非空；不断言能列出 license |
| RUN-01 | 单任务 `parse=auto` | status=success、analyses 含 tran、data 含 OUT/time |
| RUN-02 | `parse=none, download=false, keep_run_dir=true` → `read_results(<run_dir>/tb.raw)` | kind=raw、signals 含 OUT/time；随后清理远端 |
| RESULT-01 | `measure(type=max, signal=OUT)` + `export(csv/json)` | 指标 ok 且为数值；两个产物落盘非空 |
| RUN-03 | 两任务批次 `parse=none, keep_run_dir=true` | runs 2 个且全部 success；清理远端 |
| RUN-04 | 非法网表 | ok=false |

## 4. 通过准则

- 全用例 PASS；失败保留 `steps` 与 Spectre stdout/stderr；
- 不把 license 明细当成功条件（本环境 `lmstat` 不可用）；
- 远端 run_dir 用完即清。
