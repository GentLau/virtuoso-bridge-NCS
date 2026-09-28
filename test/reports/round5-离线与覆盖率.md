# 第五轮 · 离线层与覆盖率（root 汇总离线线的证据）

> 说明：本轮的离线三件事（Windows 全量、主覆盖率、Linux 客户端矩阵）由离线线执行；
> 收尾时该线尚未落独立报告，root 按它已落盘的证据汇总成本文（数字与证据路径均可复查）。
> 证据根：`test/artifacts/evidence/round5-main/`、`round5-offline/`、`round5-linux-client/`、`cov-main/`。

## 1. Windows 全量（客户端 3.12.10）

| 项 | 值 | 证据 |
|---|---|---|
| 结果 | **1656 passed / 9 skipped / 651 subtests passed，exit 0**（= 1665 项；与 `offline-junit.xml` 的 `<testcase>` 数一致） | `round5-main/offline-pytest2.log`（尾行）、`offline-junit.xml`（failures=0、errors=0、skipped=9；其头部 `tests=2316` 是 pytest 9.1.1 膨胀属性，见独立复核 D5） |
| 口径 | `test/offline/{unit,integration,scenario}` 三层 | 同上 |

## 2. 主覆盖率（合并：离线三层 + 离线 TB + 注册 HTTP + 混合压测 + 真机 TB）

| 指标 | 本轮 | 上轮（第四轮） | 变化 |
|---|---|---|---|
| 语句覆盖 | **91.65%**（15692/17121，缺 1429） | 87.40% | +4.25 pt |
| 分支覆盖 | **83.25%**（4862/5840，缺 978） | 78.37% | +4.88 pt |
| 合并 | **89.52%** | — | — |

* 来源：`cov-main/coverage-main-strict.json`、`coverage-main-strict.txt`（2026-09-23 21:57 终跑；数字含本轮新增 TB）。
* 未覆盖分类：`unclassified 1401 / env-blocked 26 / defensive 5`（`coverage-pack/coverage-rules-auto.json`）。
* 运行器汇总里两条失败步骤的解释：
  * `offline L0-L2 (rc=1)` = **有意钉住的红 TB**（P-055 三条）+ Windows 上的既有 skip；修好后自然转绿；
  * `S11 full flow (LVS) (rc=2)` = 旧 CLI 参数导致的**门禁假动作**（已在本轮修，见 TB 改动清单 L5）。

## 3. Linux 客户端矩阵（3.9.25 / 3.14.6）— 本轮首次跑完整三层

| 解释器 | 首跑 | 终跑（修复测试侧守卫后） | 结论 |
|---|---|---|---|
| Python 3.9.25（`/usr/bin/python3.9`） | 10 failed，**0 collection error** | **6 failed** = P-055(3) + P-056(3) | P-050 **已修好**；剩余红全部是产品缺陷 |
| Python 3.14.6（`~/vb-ncs/.venv`） | 12 failed + 2 subfailed | **8 failed** = P-055(3) + P-056(3) + 深嵌套口径(1) + openssh 下载 mock 时序(1) | 同上；另两条见下 |

原始证据：`round5-linux-client/{py39,py314}.log`、`{py39,py314}-final.log`、`versions.txt`、`json-depth.txt`、`runner.log`；
方法（同步快照 + 两个解释器 + 0 collection error 判定）见 [round5-Linux客户端矩阵.md](round5-Linux客户端矩阵.md)。

### 3.1 Linux 口径暴露的产品缺陷（本轮新增）

| ID | 一句话 | 证据 |
|---|---|---|
| **P-056**（P1） | `supervisor._force_kill_tree` 是 `@staticmethod` 却调 `self._signal_process_group(...)` → POSIX 下 `NameError`，进程组**既收不到 SIGTERM 也收不到 SIGKILL**（3 条既有用例稳定红） | `round5-linux-client/py39-final.log` / `py314-final.log`（`src/server/supervisor.py:301`） |
| **P-057**（口径） | 深嵌套 JSON 的拒绝行为随解释器变化：3.9 在 1000 层即 `RecursionError`→400；3.14 到 20000 层仍被**正常解析**（`json-depth.txt`）→ 旧断言把实现细节当契约 | `round5-linux-client/json-depth.txt`、`round5-Linux客户端矩阵.md` §2 |

### 3.2 测试侧修正（不是产品缺陷，但会挡 CI）

| # | 现象 | 处置 |
|---|---|---|
| 1 | 4 条 **Windows-only** 用例在 POSIX 必红（`test_windows_appdata_default`、`test_ssh_edges.py::test_windows_forward_*`） | 已加 `skipUnless(...)`（TB 改动清单 R4），Windows 行为不变 |
| 2 | `test_json_parser_limits_return_400` 的 `deep` 断言 | 已改跨版本口径（R5）；产品是否加**显式深度上限**另议（P-057） |
| 3 | 3.14 venv 缺 `PySocks` → `test_skill_tunnel_rejects_proxy` 红 | 环境侧补依赖后复跑 |
| 4 | `test_ssh_edges.py::TestOpensshDownloadAttempt::test_failure_reports_combined_stderr_and_discards_stage` 在 py314 终跑仍红（mock 的 Popen 序列与实现调用次数不匹配 → StopIteration） | **未闭环**：判为测试侧时序/序列假设，留给下一轮或离线线收尾（不影响产品结论） |

## 4. 本轮离线侧新增门禁（含负控制）

| TB | 覆盖的 spec 条款 | 负控制 |
|---|---|---|
| `test/offline/unit/test_daemon_log_utf8_budget.py` | 日志返回：UTF-8 截断必须落在字符边界、不得出现 U+FFFD | 换实现为"U+FFFD 兜底" → RED；改"不按字节截断" → RED（`round5-offline/utf8-negative-control.txt`） |
| `test/offline/unit/test_middle_reserved_codes.py` | 真实命令 rc=124/255 必须保持 `kind=command`（桥保留码只在非 command 时解释） | 改实现为"124→timeout、255→transport" → 5 条全红（`reserved-code-negative-control.txt`） |
| `test/offline/unit/test_api_server_method_not_allowed.py` | 已定义路径的错误方法 → 405 + Allow | 3 条红即 P-055 的钉子；另有 2 条绿护栏 |
| `test/offline/unit/test_pyapi_interface_contract.py`（真机线新增） | pyapi 接口与中层协议形状一致（含 `log_level/log_max_bytes`） | 删掉 `log_max_bytes` → RED（`round5-main/pyapi-contract-negative-control.txt`） |

## 5. 给 CI 的建议

1. 把 **Linux + 3.9 / 3.14 离线三层**加进流水线（脚本 `test/artifacts/tmp/r5_linux_client.sh` 可复用）；本轮证明"只在 Windows 上量"会同时放过 P-050（已修）和 P-056（仍在）；
2. 覆盖率门禁沿用 strict 口径（语句 ≥90% / 分支 ≥80%），并把"未覆盖分类"里的 `unclassified` 作为趋势指标；
3. 钉红的 TB（P-055/P-056）在修复前应显式列入"预期红名单"，避免后续执行者误判为环境噪声。
