# 第五轮 · Linux 客户端矩阵（3.9.25 / 3.14.6）

> 目的：复验 **P-050**（daemon 模块在伪 stdin 下不可导入 → Linux 采集期 6 errors）是否真的修好，
> 并回答 spec《中层配置文档》§1 的"客户端 Python ≥ 3.9"（上界不封顶）在**真 Linux 解释器**上的表现。
> 上一轮（第四轮）这条只拿到"采集失败"的红证据，本轮是**第一次在 Linux 上跑完整离线三层**。

## 1. 方法（可复现）

| 项 | 值 |
|---|---|
| 客户端主机 | `wsl-gent`（AlmaLinux, kernel 6.6.114.1-microsoft-standard-WSL2, x86_64） |
| 解释器 A | `/usr/bin/python3.9` → **3.9.25**（系统，pytest 8.4.2 / pydantic 2.13.5） |
| 解释器 B | `~/vb-ncs/.venv/bin/python` → **3.14.6**（pytest 9.1.1 / pydantic 2.13.5 / paramiko / PySocks） |
| 代码快照 | 当前工作区（**含未提交改动**）打成 tar 后解到 `~/project/vblog/tb-sandbox/r5repo`（**不用远端旧副本**） |
| 命令 | `PYTHONPATH=src <py> -m pytest test/offline/unit test/offline/integration test/offline/scenario -q -p no:cacheprovider` |
| 脚本 | `test/artifacts/tmp/r5_linux_client.sh`（同步 + 建 venv + 跑两个解释器） |
| 证据 | `test/artifacts/evidence/round5-linux-client/`（`py39.log` / `py314.log` / `*-final.log` / `versions.txt` / `json-depth.txt`） |

## 2. 结果

### 2.1 首跑（暴露问题的那一次，`py39.log` / `py314.log`）

| 解释器 | 结果 | 失败明细 |
|---|---|---|
| 3.9.25 | **10 failed**（其余全绿，**0 collection error** ⇒ P-050 已修好） | P-055 三条（新钉住）+ 4 条 Windows-only 用例 + `test_process_lifetime` POSIX 1 条 + `test_supervisor_internals` POSIX 2 条 |
| 3.14.6 | **12 failed + 2 SUBFAILED** | 同上 + `test_json_parser_limits_return_400`（deep 嵌套，2 处）+ `test_skill_tunnel_rejects_proxy`（**环境缺 PySocks**） |

> **P-050 结论：修复有效**。两个解释器都**跑完了整个离线三层**（1656 项），采集期 0 error，
> 与第四轮的"6 errors / 一个都跑不了"形成对照。`test/offline/unit/test_daemon_import_contract.py`
> 在 Linux 上转绿（该用例在 Windows 侧按设计 skip）。

### 2.2 失败分类与处置（逐条）

| # | 现象 | 归因 | 处置 |
|---|---|---|---|
| 1 | `test_api_server_method_not_allowed.py` 3 条（`GET /api/operation`、`POST /health`、`POST /help` 该 405 却 404） | **产品（顶层）P-055** | 保留红 TB（本轮新钉住）；见 `round5-顶层API面复核.md` |
| 2 | `test_process_lifetime.py::TestPosixBusinessProcessLifetime::test_dispose_kills_process_group_descendant`：`supervisor.py:266 → _force_kill_tree → NameError: name 'self' is not defined` | **产品（控制面）P-056** | 保留红用例；根因 `src/server/supervisor.py:280-307`（`@staticmethod` 里调 `self._signal_process_group`） |
| 3 | `test_supervisor_internals.py::TestForceKillTree::test_posix_group_sigterm_success_returns` / `..._sigkills_after_sigterm_timeout` 同 `NameError` | **产品（控制面）P-056**（同一根因，两个用例） | 同上 |
| 4 | `test_models_paths.py::test_windows_appdata_default`：`NotImplementedError: cannot instantiate 'WindowsPath'` | **测试侧**（mock 全局 `os.name='nt'` 会让 pathlib 在非 Windows 上直接抛错，宿主平台限制） | **已修**：加 `skipUnless(sys.platform == "win32")`（见 TB 改动清单 R4） |
| 5 | `test_ssh_edges.py::test_windows_forward_*` 3 条：`'_TunnelProc' object has no attribute 'stderr'` 等 | **测试侧**（产品侧 `if _IS_WINDOWS:` 分支在 POSIX 上根本不走，用例却无守卫） | **已修**：三条加 `skipUnless(ssh_mod._IS_WINDOWS)`（R4） |
| 6 | `test_registration_server.py` / `test_top_layer_pool.py::test_json_parser_limits_return_400`（仅 3.14，deep 嵌套） | **测试侧口径 + 产品建议**：3.14 的 C 扫描器不再按层递归 → 5000 层被**正常解析**，随后业务层拒绝（仍是 400 + JSON）；旧断言把"某解释器的实现细节"当产品契约 | **已修**：long-int 仍钉 `invalid JSON body`（跨版本稳定）；deep 只钉"400 + JSON 错误体 + 无断连"（R5）。**产品建议**：若要统一跨版本行为，加显式嵌套深度上限 |
| 7 | `test_ssh.py::test_skill_tunnel_rejects_proxy`（仅 3.14） | **环境侧**：3.14 venv 缺 `PySocks`（`import socks` 失败） | 已 `pip install PySocks` 后复跑（见 §3） |
| 8 | 一次 `test_ssh_edges.py::TestOpensshDownloadAttempt::...` 在**并发重负载**下偶发（StopIteration），同文件单独跑 3/3 绿、组合跑 2/2 绿 | 可疑 flake（非稳定复现） | 记录为观察项，不立案；建议后续加 `-p no:randomly` 之外的稳定性观察 |

## 3. 修复后复跑（最终口径）

| 解释器 | 结果 | 红项 |
|---|---|---|
| 3.9.25 | **6 failed**（其余全绿；4 条 Windows-only 用例按平台 skip） | P-055×3（`test_api_server_method_not_allowed.py`）+ P-056×3（`test_process_lifetime.py::…process_group_descendant`、`test_supervisor_internals.py::TestForceKillTree::test_posix_group_*`） |
| 3.14.6 | **6 failed**（同上） | 与 3.9 **逐条相同** |

> 结论：修正测试侧守卫/口径（R4/R5）后，Linux 上剩下的红**全部是有意钉住的产品缺陷**，
> 两个解释器结果完全一致 —— 说明红项不是"版本抖动"。（日志 `py39-final2.log` / `py314-final2.log`；
> 该两次日志未捕获 pytest 结尾的计数行，红项清单见各日志末尾 `short test summary info`。）

### 3.1 最新口径（2026-09-23 23:0x，独立复核线复跑，**以这一行为准**）

| 解释器 | 用例数（`<testcase>` 真实口径） | 结果 | 红项 |
|---|---|---|---|
| 3.9.25（pytest 8.4.2） | **1686** | **14 failed / 0 error / 18 skipped** | P-055×3 + **calibre×8**（P-059/P-062×6 + P-061×2）+ P-056×3 |
| 3.14.6（pytest 9.1.1） | 1686 | **同样 14 条，逐条一致** | 同上 |

> 上面 §3 表的"6 failed"是 **21:35 的快照**——那时 `test_calibre_parsers.py` / `test_calibre_job_state.py`
> （8 条有意红）还没加入 TB。**当前工作树请按 14 红看**（= Windows 侧同源的 11 条 + Linux 专属 P-056×3）。
> 证据：`test/artifacts/evidence/round5-audit/linux-py39-audit.xml`、`linux-py39-audit.log`、`linux-py314-audit.log`（独立复核 D2）。

## 4. 给 CI 的建议（本轮教训）

P-050 的代价是"Linux 客户端**整条链路**此前不可用而没人发现"——因为 Windows 上恰好走不到那条分支。
建议把 **Linux + 3.9/3.14** 两个离线三层作业加进流水线（`.github/workflows/tests.yml` 已有 3.9/3.13 矩阵，
但 Linux 侧历史上从未真正采起来）；本报告的 `r5_linux_client.sh` 可直接复用。
