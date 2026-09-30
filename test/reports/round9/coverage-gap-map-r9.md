# round9 · 覆盖率"缺口地图"（基于跑前基线，供报告用）

> 执行：subagent `/root/opparam_r9`｜2026-09-29 22:16｜只读分析
> 基线：`test/artifacts/evidence/round9/coverage-pre-r9-strict.json`（round8 末次全量，mtime 2026-09-28 23:33）
> 基线总数：statements **17325** / covered **15860（91.54%）**、branches **5091/6088（83.62%）**、combined **89.48%**、**57 个文件**

## 1. 先说结论（防"覆盖率虚高"指控）

- **0% 覆盖的文件：0 个**；
- **行覆盖 <60% 的文件：0 个**（最弱的也有 69.91%）；
- 也就是说：**没有"整块没测"的模块**，缺口是**局部行/分支**性质的——这正是本轮该用"缺口地图"而不是"一个大百分数"来讲的地方。

## 2. 最弱 15 个文件（基线）

| 行覆盖 | statements | 缺行 | 缺分支 | 文件 |
|---|---|---|---|---|
| 69.91% | 71 | 19 | 15 | `src/common/streams.py` |
| 73.51% | 115 | 23 | 17 | `src/common/process_lifetime.py` |
| 75.00% | 4 | 1 | 0 | `src/bridge/__init__.py` |
| 79.50% | 256 | 50 | 16 | `src/register/probe.py` |
| **80.80%** | **1578** | **259** | **160** | `src/pyapi/packages/maestro.py` ← **绝对缺口最大** |
| 82.14% | 46 | 5 | 5 | `src/common/paths.py` |
| 82.26% | 1064 | 171 | 72 | `src/common/paramiko_backend.py` |
| 83.09% | 777 | 119 | 55 | `src/transport/middle.py` |
| 84.52% | 484 | 64 | 36 | `src/pyapi/packages/skillref.py` |
| 84.57% | 825 | 105 | 80 | `src/register/flow.py` |
| 85.61% | 679 | 68 | 66 | `src/pyapi/packages/calibre.py` |
| 87.47% | 357 | 39 | 21 | `src/transport/tunnel.py` |
| 88.63% | 223 | 16 | 18 | `src/pyapi/packages/gui.py` |
| 89.19% | 56 | 5 | 3 | `src/common/deploy.py` |
| 89.22% | 654 | 55 | 45 | `src/pyapi/packages/symbol.py` |

## 3. 本轮改动与这些缺口的关系（收口时可对照新数字）

| 缺口文件 | 本轮相关动作 | 预期 |
|---|---|---|
| `pyapi/packages/maestro.py`（缺 259 行/160 分支，最大） | C09 修好后 `write_history` rename 链转绿；`maestro_mc_e2e_tests`（9/9）、`maestro_view_param`（待无负载复跑）覆盖读族 | 修复 + 复跑后该文件应见涨 |
| `pyapi/packages/calibre.py` | **P-106**（假失败）修复 + SET-01 转绿；PEX 相关分支本版不提供（会天然不可达，需在报告注明"不可达≠未测"） | 见涨 + 需说明 PEX 不可达段 |
| `transport/middle.py` | W-1 强化的 log 语义（warn 过滤 / 降级两档 / off 空值）走的就是 middle+daemon 日志路径 | 见涨 |
| `pyapi/packages/symbol.py`（89.22%）/ `maestro.py`（80.80%）/ `schematic.py`（91.71%） | 嵌套键 L0 契约（symbol pin 标签族、`place_wire` 间距、maestro 门控）已覆盖**命令构造**分支 | 构造分支见涨；**真机**分支仍未覆盖 |
| `register/probe.py` / `register/flow.py` | 注册两条真机 TB（六步 / host-key 轮换）本轮复跑；离线 flaky 就在 `register/flow` 家族 | 见涨；flaky 需先修 |
| `common/paramiko_backend.py` | 本轮环境修复（S2/vbfake 的 `backend=openssh`）不增加覆盖——**paramiko 路径只在 wsl-gent 等 strict 主机上走到** | 预期平；若要涨需专测 paramiko 分支 |

## 4. 口径提醒

* 报"总覆盖率"时必须同时给 **行 / 分支 / combined** 三个数（coverage.py 的 `percent_covered` 是 combined）；
* 引用时带上 `head + dirty + worktree_diff_sha`（见 `coverage-honesty-notes.md`）；
* **不要**把"PEX 本版不提供"之类的**刻意不可达分支**算成"未覆盖缺陷"，但也**不要**把它们算进"已覆盖"——单独列一节说明。

## 5. 附：`src/pyapi/packages/*` 基线一览（供报告对照）

| 包 | 行覆盖 | 缺行 | 缺分支 |
|---|---|---|---|
| cellview.py | **99.52%** | 1 | 1 |
| basic.py | 96.25% | 6 | 7 |
| veriloga.py | 92.80% | 21 | 18 |
| verilog.py | 92.25% | 24 | 19 |
| schematic.py | 91.71% | 25 | 43 |
| layout.py | 90.91% | 77 | 62 |
| spectre.py | 89.66% | 50 | 31 |
| symbol.py | 89.22% | 55 | 45 |
| gui.py | 88.63% | 16 | 18 |
| calibre.py | 85.61% | 68 | 66 |
| skillref.py | 84.52% | 64 | 36 |
| **maestro.py** | **80.80%** | **259** | **160** |
