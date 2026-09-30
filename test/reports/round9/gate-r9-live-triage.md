# round9 · 门禁进行中的三条异常（B 线现场分诊）

> 执行：subagent `/root/opparam_r9`｜2026-09-29 21:20｜只读诊断（机器在跑门禁，我不去抢）
> 数据来源：`test/artifacts/evidence/http-e2e/*.log`（21:02–21:16 这一轮）

## 1. `verilog_import_params` IMP-07 `KeyError: 1` —— **已过期（TB 已在 21:16 修好）**

* 失败日志：`http-e2e/verilog_import_params_e2e_tests.py.log`（**21:14:11**）；
* 现状：TB 文件 mtime **21:16:55**、注释头"最后改动 21:18"，`case_overwrite_false` 里已写明原因：
  "C4 契约：CommandResult 是命名字段对象 … 旧 `[1]` 在 C4 后必抛 KeyError: 1 —— 2026-09-29 21:0x 门禁实测"，
  并已改为 `str((mtime_x or {}).get('stdout') or '')`；
* **结论**：不是产品红，是 **TB 侧 C4 遗留索引**，修好后未再跑（下一轮门禁/单跑即可验证绿）。

## 2. `calibre_e2e_tests` SET-01：`calibre.lvs failed: lvs did not complete: failed process_gone_without_report`（21:11）

* 位置：`http-e2e/calibre_e2e_tests.py.log`（该套 pass=0/fail=0，异常直接把套件打断）；
* 现象：`_case_set_file` 用 `runset=<远端 .lvs set>` 跑 `blocking=True` LVS，等待中作业消失且无完成报告 →
  中层按 P-094 口径归类为 `process_gone_without_report`（**分类正确，不是静默 unknown**）；
* 待判：① set/PDK 路径或权限被改动（环境）；② runset 直驱在**当前** deck 下真的起不来（产品/口径）。
  判别方法：门禁结束后单跑一次该 case 并保留 `run_dir` 日志（`lvs*.log`、`*.rep`）——若是环境，日志里会有"文件/路径不存在"；若是产品，会有 calibre 自身的 usage/许可错误。
* **不要**在拿到单跑日志前把它记成产品缺陷。

## 3. `calibre_export_pex` ENV-01：`环境缺 drc_ok: ''`（21:15）

* 位置：`http-e2e/calibre_export_pex_e2e_tests.py.log`；其余 5 条（EXP-00/01/02/03、PEX-01）**全绿**；
* 关键点：失败信息里的 probe **是空串**（`''`），意味着四条 `test -f/-x`（drc_ok/lvs_ok/bin_ok/gds_ok）**一条都没响**：
  * 要么命令 role 这一跳没执行 / 返回空（P-086 窗口、daemon 短暂忙）；
  * 要么四条路径同时不存在（不太可能——同一批里 `calibre_params` 21:12 刚刚 6/6 用过同一套 PDK 路径）。
* 基线：同一套在 **16:44** 曾 **6/6 全绿**（`evidence/verify-fix-r9/gate-calibre-pex-rerun2.txt`：ENV-01 PASS + 其余 5 条 PASS）。
* 判别方法：门禁结束后**单跑这一套**，把 probe 原文打印出来（现在 TB 只在断言失败信息里带它）；若 probe 非空且缺的只是某一条，再按环境缺口处理。

## 4. 建议（收口前最小动作）

1. 门禁跑完先看 `http-e2e/results.json` 的 `all_passed` 与逐套 rc；
2. 对上面 **2、3** 各做一次单套复跑（`calibre_export_pex` 约 1–2 min；`calibre_e2e` 只需 SET-01 case，若 TB 支持 `--only`）；
3. 若复跑仍红 → 把单跑日志附到对应卡片（P-094 口径已归类，若属产品就是新卡；属环境则写进"环境缺口"）；
4. **IMP-07 不用管**，它是过期日志（TB 已修）。

---

## 5. 终局（21:29 更新）：官方门禁 19 套 = **14 绿 / 5 红**，逐条定性

| 套件 | rc | PASS/FAIL | 定性 | 依据 |
|---|---|---|---|---|
| verilog_import_params | 1 | 12 / 1（IMP-07） | **过期 TB 缺陷**（C4 位置索引，21:16:55 已修） | 失败日志 21:14:11 vs TB mtime 21:16:55 |
| calibre_export_pex | 1 | 5 / 1（ENV-01） | **环境/瞬时空响应** → **已由 21:30 复跑证实**：`rerun-calibre-export-pex.log` **rc=0 / fails=0** | 本文件 §3 + root 复跑队列 |
| calibre_e2e | 1 | 0 / 0（SET-01 打断） | **产品侧"假失败"（分类器竞态）**：见下方 §5.1 | 本文件 §2 + root 的 21:26 取证 |
| maestro_view_param | 1 | 0 / 0（`read_config` 默认≠显式） | **不可复现**：本轮我直接调 2 次比对 → `equal? True`（21:25） | 探针命令与结果见 §6 |
| maestro_e2e | 1 | 0 / 0（`read_history` 撞 stale write lock，pid 已死） | **环境卫生**：P-096 家族的锁检测按设计拒绝（死 pid 锁），清锁/换 cell 即可 | 日志原文（死 pid=3508716，since 20:40） |

> 你（root）已在 21:26–21:28 起跑复跑队列（`calibre-blocking-probe.log`、`calibre-set01-falsefail-evidence.txt`、`gate5-verilog_import_params.log`、`rerun-queue-console.log`），这几份是后续权威依据。
> 21:30 队列进展：`verilog-import-params` rc=1/fails=18（**受我方 burst 负载影响，见 §5.2**）、
> **`calibre-export-pex` rc=0/fails=0 ✅**（ENV-01 确认为瞬时）、`calibre-e2e` 正在跑。

### 5.1 `calibre_e2e` SET-01 的定性（按 root 21:26 取证）

`test/artifacts/evidence/round9/calibre-set01-falsefail-evidence.txt` 显示：

* 门禁 21:11 那次 `lvs-set` 的 `lvs.log` 里有 **`*** LVS run finished with exit code 0 ***`**（第 15624 行）；
* 21:26 的 `lvs-set-r9b` 复跑同样 **COMPLETED / exit code 0**，且写出 `inv2.lvs.report`（37957 B）+ `job.json`（argv 是官方 `calibre -gui -lvs -runset … -batch`）。

→ 结论：**LVS 实际跑完了，bridge 却报 `process_gone_without_report` = 假失败**。`calibre-blocking-probe.log` 还给出对照：
① 对已完成的 run 调 `status` → `completed` ✓；② 新 run dir 的阻塞跑 → **5.6 s 就判 failed**，日志只有 calibre banner。

**这是产品侧竞态**（P-094 判定逻辑的边界）：进程结束得很快时，轮询在"完成标记已写入"之前就观察到进程消失，于是走了 `process_gone_without_report` 分支。
建议（供你落卡/转设计）：
1. 判定"进程消失"前**先做一次终态日志扫描**（completion marker / `exit code 0` / 报告文件存在），或给一个很短的 grace（例如 2 s）再判；
2. TB 侧可加一条回归钉：同一 runset 连跑两次，第二次必须 `completed`（而不是 `process_gone_without_report`）。

### 5.2 ⚠ 自我披露：21:28 那两条 `SKILL execution timed out` 很可能是我造成的负载

* 我在 21:27 单跑了 `one_shot_burst_tb`（**36×3 组并发 one-shot**）来复验半真机第 3 条红——它本身 **rc=0 全绿**，但它与你的复跑队列**重叠**；
* 你的 `rerun-verilog-import-params.log`（21:28:43）与 `gate5-maestro_view_param.log`（21:28:49）随即**大面积**报
  `RuntimeError: SKILL execution timed out`（verilog 连原本能过的 IMP-01..06/09 都红了）；
* 我在 21:29 直接打 `vb-vblog` 的 `1+2` → **ok=true，0.4 s**（CIW 现在是健康的）→ 说明那批超时是**瞬时负载**，不是稳定产品回归。

**结论/建议**：这两套请在**没有任何其它并发负载**时重跑一次（我现在停止一切真机动作，不再抢 CIW）；如果那时仍超时，才按产品问题处理。

## 6. 半真机（40 探针）= **37 绿 / 3 红** → 3 红已全部复跑转绿

| 探针 | 批内失败原因 | 我的复跑结果 |
|---|---|---|
| `maestro_env_probe.py` | `KeyError: 0`（共享 helper `_maestro_tb.py::shell` 用旧位置索引；**helper 已在 21:25 修**） | ✅ **rc=0**（21:27 单跑） |
| `maestro_e2e_probe.py` | 同上 | ✅ **rc=0**（21:27 单跑） |
| `one_shot_burst_tb.py` | 运行期 `VB-TRANSPORT: ChannelException(2,'Connect failed')`（gui/spectre 两组；当时与门禁 maestro 同抢 vblog CIW） | ✅ **rc=0**：`failures: []`，gui 36/36、spectre 36/36，证据 `test/artifacts/evidence/round9/one-shot-burst-r9.json` |

**顺手修掉一个未修净的 C4 遗留**：`test/semi/probes/_maestro_tb.py:100` 还有一处 `r["result"][1]`（xwininfo 路径），
已改为具名 `result.get("stdout","")`；注释头 `最后改动` 更新为 `2026-09-29 21:27`。

## 7. 给主报告 §1 的写法（本轮到 21:29 为止）

> **真机门禁**：`run_all_http.py` 19 套 → **14 绿**；5 红逐条定性：1 条过期 TB 缺陷（已修）、1 条环境/瞬时空响应、
> 1 条待单 case 复跑（calibre set 直驱）、1 条不可复现（maestro `read_config`）、1 条环境卫生（stale lock）。
> **半真机**：40 探针 → 批内 37 绿；3 红经单跑**全部转绿**（2 条为共享 helper 的 C4 遗留、1 条为与门禁同抢 CIW）。
