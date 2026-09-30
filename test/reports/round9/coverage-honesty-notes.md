# round9 · 主覆盖率"口径诚实性"备忘（B 线）

> 执行：subagent `/root/opparam_r9`｜2026-09-29 22:12｜只读准备 + 脚本
> 工具：`test/reports/round9/verify_coverage_r9.py`（跑完覆盖率后一键核对）

## 1. 引用规则（第八轮被驳回的教训）

主口径**只能**引用：`test/artifacts/evidence/cov-main/coverage-main-strict.json`（`run_main_coverage.ps1`
的 strict 输出）**并且**同时满足：

1. `coverage-main-r9.log` 尾部是 **`全部步骤通过`**（有 `失败步骤:` 列表的 run，其数字不能当主口径）；
2. `run-meta.json` 的 `head` 与当前 HEAD 一致（否则是旧提交的数字）；
3. **`dirty: true` 时必须一并标注 `worktree_diff_sha`**（本轮就是脏工作区，见 §3）；
4. 只允许 `coverage-main-strict.json` / `coverage-main.json` 两个文件；`*-append-*.json`
   （01:26 / 02:19 那批）是**部分口径产物，不得引用**。

## 2. 跑前基线（我已在覆盖率启动前快照，避免被覆盖）

快照：**`test/artifacts/evidence/round9/coverage-pre-r9-strict.json`**（复制自 `cov-main/coverage-main-strict.json`，mtime 2026-09-28 23:33）

| 指标 | 值 |
|---|---|
| statements | 17325 |
| covered lines | 15860 → **91.54%** |
| branches | 5091 / 6088 → **83.62%** |
| combined（coverage.py `percent_covered`） | **89.48%** |
| 文件数 | 57 |

（即第八轮报告里的 91.54 / 83.62 / 89.48 三数，都能从这份 baseline 复算出来。）

## 3. 本轮（round9）覆盖率 run 的 provenance（跑前实测）

`test/artifacts/evidence/cov-main/run-meta.json`：

```json
{"head": "86cc16945c8ffe7979e5ffc63269cc9256c47fd2",
 "branch": "codex/refactor-tests-docs",
 "worktree_diff_sha": "351f5c037d615a4aa35ac9c318c05b3690113777",
 "dirty": true,
 "started_utc": "2026-09-29T13:56:07Z",   // = 北京 21:56
 "python": "3.12.10", "coverage": ["7.16.0"]}
```

→ 报告里请写：**"覆盖率基于 `86cc169` + 脏工作区 diff `351f5c03…`、Coverage.py 7.16.0"**；
只写一个百分数而不带这三项，会被判"口径不可复现"。

## 4. 跑完后的动作（一条命令）

```bash
python test/reports/round9/verify_coverage_r9.py
```

它会输出（并写 `coverage-verify-r9.json`）：

* `all_steps_passed` / `failed_steps` / 日志里的 `TOTAL` 行；
* `meta.head_matches_now`、`dirty`；
* 与 baseline 的 **逐文件差异**：新增模块 / 消失模块（并特别检查 **`stress_server` 是否回归**——它已被删除，不该再出现在文件清单里）；
* strict totals 的 delta（statements/covered/percent）。

## 5. 已知的"不可引用物"清单（本轮）

| 文件 | 为什么不能引用 |
|---|---|
| `cov-main/*-append-*.json`（01:26 / 02:19） | 增量拼接，不是全量 |
| `cov-main/coverage-main.json`（若 mtime 早于 21:56） | 非本轮 |
| 任何 `coverage-main-r9.log` 里列出 `失败步骤:` 时的 strict JSON | 该 run 有步骤失败，数字不可作主口径 |

## 6. 本轮**预期**会失败的覆盖率步骤（跑完先对照这里）

> 依据：`run_main_coverage.ps1` 用 direct 模式跑 live 套件；本轮有两个**已知未修**的产品缺陷会让对应套件 rc≠0。

| 步骤 | 预期 | 依据 |
|---|---|---|
| `packages/maestro (direct)` | 可能 rc≠0 | **C09**（`write_history` rename 链稳定红，`HISTORY-01`）+ 可能的 P-086 空响应窗口 |
| `packages/calibre_e2e (direct)` | 可能 rc≠0 | **P-106**（`calibre.lvs(runset=…, blocking=true)` 假失败，SET-01 稳定红） |
| `packages/verilog_import_params (direct)` | **应通过** | IMP-07 的 C4 位置索引已在 21:16 修好，而本 run 21:56 才启动（含修复） |
| `packages/layout (direct)` | 应通过 | GDS-02 的 `step_details=True` 已在 20:44 修好 |

→ 若跑完 `失败步骤:` 只有上面前两条，则数字是**下界口径**，报告措辞：
**"本轮覆盖率 X%（语句 Y / 分支 Z）为下界：maestro 因 C09、calibre_e2e 因 P-106 两步 rc≠0；主口径待这两个缺陷修复后复算。"**
（与 round8 处理 01:55 下界的方式一致。）

→ 若出现**其它**失败步骤 → 逐个看日志，不要混进"已知两条"的解释里。

## 7. 本轮实测结果（2026-09-29 22:31 跑完，`verify_coverage_r9.py` 核对）

| 指标 | 基线（round8 23:33） | **本轮 round9** | Δ |
|---|---|---|---|
| statements | 17325 | **18147** | +822 |
| 覆盖行 | 15860 | **16674** | +814 |
| **行覆盖** | 91.54% | **91.88%** | +0.34pp |
| **分支覆盖** | 5091/6088 = 83.62% | **5303/6318 = 83.93%** | +0.31pp |
| **combined** | 89.48% | **89.83%** | +0.35pp |
| 文件数 | 57 | 57 | 0（无新增/删除模块；**`stress_server` 未回归** ✅） |
| 未分类缺行 | 1435 | 1443 | +8 |

**失败步骤 = 预判的两条**：`packages/maestro (direct) rc=1`（**C09** write_history rename 链）、
`packages/calibre (direct) rc=1`（**P-106** 假失败）；`verilog_import_params` 与 `layout` 都通过了（TB 修复生效）。

**provenance**：`head 86cc169` + `dirty: true` + `worktree_diff_sha 351f5c03…` + Coverage.py 7.16.0，
run 起于 `2026-09-29T13:56:07Z`（北京 21:56），strict JSON mtime 22:31:27。

**报告可直接用的句子**：

> **本轮主覆盖率（下界口径）89.83%（语句 91.88% / 分支 83.93%），基于 `86cc169` + 脏工作区 diff `351f5c03…`（Coverage.py 7.16.0）；
> 该 run 有且仅有两条步骤 rc≠0：`packages/maestro`（C09：write_history rename 链）与 `packages/calibre`（P-106：blocking 假失败）——两者均为本轮新立、待设计修的缺陷；修复后需复算主口径。
> 未分类缺行 1443（环境阻塞 26 + 防御性 4 已书面分类）；子进程覆盖率仍未合并（G7），当前口径低估。**
