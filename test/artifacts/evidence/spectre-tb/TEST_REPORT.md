# spectre 业务包 真机测试报告

> 版本：v1
> 日期：2026-09-21
> 执行：direct dispatch / work-dir `test/tb/artifacts/log-vblog` / token `vb-vblog`
> Spectre 24.1.0.078（WSL `wsl-gent`）；脚本 `test/tb/spectre_e2e_tests.py --transport direct`

## 1. 结论

**direct 真机 6/6 PASS**（HTTP 8127 待基座修复后回归，预期 `/health` 含 5 个 `spectre.*`）。

```
PASS    LICENSE-01 check_license
PASS    RUN-01 run + auto parse
PASS    RUN-02 raw + read_results
PASS    RESULT-01 measure + export
PASS    RUN-03 multi task
PASS    RUN-04 bad netlist fails
```

## 2. 关键证据

| 项 | 实测 |
|---|---|
| check_license | ok=true，Spectre 24.1.0.078 版本串与 bin 路径齐全 |
| run 单任务 | RC tran 5µs 成功，rc=0，`analyses=['tran']`，`data.time`/`data.OUT` 各 252 点，V(OUT) 峰值 1V |
| raw 读回 | `parse=none, keep_run_dir=true` 后 `read_results(<run_dir>/tb.raw)` → `kind=raw`，signals 含 `time/OUT` |
| measure | `{type:"max", signal:"OUT"}` → ok，value≈1.0 |
| export | CSV/JSON 均落盘非空 |
| 多任务 | 同一网表两个 job 并行成功，`runs` 长度 2 且全部 success |
| 失败注入 | 非法网表 → `ok=false`（Spectre 解析错误透传） |

## 3. 测试中修正的问题

1. `parse` / `download` / `keep_run_dir` 是**批次级**参数：放在 task 字典里会被 `_normalize_tasks`
   静默忽略，导致 `keep_run_dir=true` 不生效、run_dir 被清掉（首次 raw 读回因此失败）。
   测试与用法已统一按批次级传参（与 spec §5.1 一致）。

## 4. 已知限制

- `lmstat` 在本环境不可用（IC618 loader 问题），license 明细为 best-effort，不影响 `check_license` 成功判定；
- PSF 参数扫描形态（`kind=sweep`）只有离线解析验证，未真机跑 sweep 网表；
- file/spectre role 分离与可见性失败路径未测；
- HTTP 8127 回归待基座修复后补。
