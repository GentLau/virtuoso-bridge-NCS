# round9 · "未覆盖行有没有被解释"基线核对（防覆盖率口径被驳回）

> 执行：subagent `/root/opparam_r9`｜2026-09-29 22:18｜只读（数据来自 round8 末次的 coverage-pack，本轮跑完会重新生成，届时对比）
> 数据源：`test/reports/coverage-pack/{summary.json, unclassified.txt, coverage-rules-auto.json}`

## 1. 基线事实（round8 末次）

| 项 | 值 |
|---|---|
| 缺行（missing_lines） | **1465** |
| 分类结果 | **unclassified 1435** / env-blocked 26 / defensive 4 |
| 即"有书面解释"的行 | **30 行（2.0%）** |
| **未解释占比** | **98.0%** |
| 未分类涉及文件 | 45 个 |
| 规则文件 `coverage-rules-auto.json` | 只有 9 个文件的手写规则（平台门控 `os.name` / `main-guard`） |

→ **不能**在报告里写"未覆盖行已逐条解释/已分类"；能写的是"1465 缺行中 30 行有书面分类（26 平台门控 + 4 main-guard），**1435 行未分类**"。

> 补充（复核 round8 报告 §5 第 180 行）：**round8 报告本来就是这么写的** ——
> "未覆盖分类 | 未分类 1435 / 环境阻塞 26 / 防御性 4（missing_line 1465 / missing_branch 997）"。
> 所以 round9 继续沿用这个表格口径即可（换成新数字），不要为了好看把它删掉或改写成"已分类"。
> 另一条 round8 已如实列出的口径 caveat 也要带上：**G7 子进程覆盖率未合并**（`supervisor.py` 等被监督体跑在子进程，
> 当前口径**低估**；见 round8 §5 的 G 表 G7 行）——round9 若仍是同一口径，要照写。

## 2. 未分类缺行的 Top 12（与 `coverage-gap-map-r9.md` 的最弱文件互相印证）

| 缺行数 | 文件 |
|---|---|
| **259** | `src/pyapi/packages/maestro.py` |
| 164 | `src/common/paramiko_backend.py` |
| 118 | `src/transport/middle.py` |
| 105 | `src/register/flow.py` |
| 85 | `src/common/ssh.py` |
| 77 | `src/pyapi/packages/layout.py` |
| 68 | `src/pyapi/packages/calibre.py` |
| 64 | `src/pyapi/packages/skillref.py` |
| 55 | `src/pyapi/packages/symbol.py` |
| 50 | `src/pyapi/packages/spectre.py` |
| 49 | `src/register/probe.py` |
| 39 | `src/transport/tunnel.py` |

## 3. 收口建议（二选一，或多写一节）

1. **补规则**：把明确"刻意不可达/环境门控"的行写进 `coverage-rules-auto.json`（例如 **PEX 本版不提供** 的 `calibre.pex` 分支、
   仅 Windows 或仅 Linux 的 `os.name` 分支、`__main__` guard）。规则每加一类，`unclassified` 就少一批；
2. **如实列缺口**：按上面 Top 12 在报告里开一节"未覆盖热点（1435 行未分类）"，逐文件给出**为什么没测**与**哪类 TB 能补**。

> 两种都可以，但**不要**只写一个总百分数了事——本轮被驳回的点之一就是"覆盖率虚高"，而"98% 的缺行没有解释"正是容易被抓的点。

## 4. 本轮跑完后的对比动作

```bash
python test/shared/runners/classify_uncovered.py \
  --json test/artifacts/evidence/cov-main/coverage-main-strict.json \
  --out test/reports/coverage-pack/coverage-rules-auto.json \
  --unclassified-out test/reports/coverage-pack/unclassified.txt
```

（`run_main_coverage.ps1` 已包含这一步）→ 跑完比较三件事：

1. `summary.json.classification.counts.unclassified` 是否从 **1435** 下降；
2. 上面 Top 12 的缺行数是否下降（尤其 `maestro.py` / `calibre.py` 在 C09/P-106 修复后）；
3. `rules_file` 是否新增了"刻意不可达"类别（如 PEX），避免把设计上不可达的行算作"待补测试"。
