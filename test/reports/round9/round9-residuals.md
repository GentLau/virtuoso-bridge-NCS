# round9 · 残留与待办汇总（B 线，供主报告 §6 直接采用）

> 执行：subagent `/root/opparam_r9`｜2026-09-29 22:15｜只读汇总（每条都带证据路径与下一步）
>
> **当前未关闭卡 = 6 张**：`C06`、`C07`、`C09`、`C10`、`P-086`、`P-106`（22:48 复核 `make_bug_cards.py --check`：计划 9 文件 / 缺失 0 / 过期 0；
> 主报告 §5 目前仍写"未关闭 2"，需按此行更新）。

## A. 设计侧（需要动手）

| # | 事项 | 现状与证据 | 建议 |
|---|---|---|---|
| A1 | **`calibre_e2e` SET-01「假失败」竞态**（本轮新发现，**2/2 复现**）→ **已立卡 `P-106`（待设计修）** | 根因已定位：`_status_snapshot` 用 **`pgrep -f <run_dir>`** 判活，而 official-batch 的 calibre 命令行**只含 runset 路径、不含 run_dir** → 恒无匹配 → 首个 poll 即 `process_gone_without_report`。两次复现的远端 `lvs.log` 都写有 `exit code 0` + `inv2.lvs.report`(37957 B) | 设计修 `_status_snapshot` 判活口径（或按"命令行/ cwd / 报告文件"多路判活）+ 回归钉"同 runset 连跑两次第二次必须 completed"。证据：`evidence/round9/calibre-set01-falsefail-evidence.txt`、`calibre-blocking-probe.log`、`rerun-calibre-e2e.log`、卡片 `bugs/P-106-calibre-blocking-false-fail.md` |
| A1b | **`maestro.write_history` rename 链 handle 错**（本轮新立卡 **`C09`**，待设计修） | 隔离复现：`rename(Interactive.8→e2e_renamed)` ok，紧接 `rename(e2e_renamed→Interactive.8)` 报 `ASSEMBLER-2404 Cannot find a setup database entry for handle 118109`；门禁 `HISTORY-01` 今日 **3 次稳定红**；对照 `delete e2e_renamed` ok → 问题在 rename 链的 SDB handle 生命周期 | 设计修 `write_history` rename 分支的 handle 复用；证据 `evidence/round9/final3-maestro_e2e_tests.py.log` + 卡片 |
| A2 | **C07**（spec 把 `export_cdl` 折进 `lvs(source=…)`，实现未跟） | 待决策；红钉 `test/offline/unit/test_calibre_lvs_source_contract.py` **2×strict xfail，现跑 `xx`** ✅ | 设计拍板：①实现 fold（同步迁 5 处 TB）或 ②回退 spec；任一路径走完即 XPASS 转红提醒删钉 |
| A3 | **C06**（桥执行 `print` 不刷 CIW/不落同请求 CDSlog，且串到后续请求） | 红钉 TB 存在（`skill_log_semantics_e2e_tests.py`），但**此前没有任何 runner 引用它** | 红钉 runner 已补：`test/shared/runners/run_redpins.py`（判 HOLD/UNEXPECTED-GREEN/BROKEN，后两者 rc=1）；设计修 `ramic_bridge.il` 的 `errset(hiFlushInfo())` + 清 daemon 两版 `hiFlush()` |
| A4 | **spec 矩阵 30 条改判候选** | 其中 **5 条口径已被推翻**：PEX×4（`calibre#005`"未按三阶段验收"→应改"本版不提供"）、`power/ground`×1（`calibre#172`，字段已删） | 逐条落笔/让设计改 spec；清单见 `spec-matrix-r9-b-review.md §2` |

## B. 测试侧（我方能动）

| # | 事项 | 现状 | 下一步 |
|---|---|---|---|
| B1 | ~~**`maestro_view_param` / `verilog_import_params` 缺"无负载"有效结果**~~ | **✅ 已闭环（22:35–22:39 安静窗口）**：`maestro_view_param` **9/9 PASS**（`evidence/round9/maestro-view-param-r9b.json`）、`verilog_import_params` **13/13 PASS**（含 IMP-07/08/10/11，`evidence/round9/verilog-import-params-r9b.json`）→ 确认此前红都是环境/并发，非产品 | 无；结果可直接进报告 |
| B2 | ~~业务流程 TB 本轮复跑情况~~ | **✅ 11/11 全部复跑**：`role_split` 5/5、`serdes_rx_flow` 全流程 rc=0、`design_iterate` 11 stage rc=0、`adc_sar` 24/24、`multiuser_serdes_rx` 17/17、`multiuser_layout_handoff` 12/12、`s11` 链（PASS/match）、`lvs_from_schematic`（**LVS CORRECT**）、**`multihop` 10/10**（两跳+SOCKS5）、**`scale_100`**（100 fake ×2 轮全绿）、**`project_flow`** rc=0（含 spectre 0 err/0 warn） | 无（详见 `round9-flows-not-rerun.md`；multihop 途中修的两处环境见 Runbook） |
| B3 | ~~嵌套键真机验证~~ | **✅ 已闭环（20/21 键真机落位）**：L0 契约 **21/21**；真机 TB `nested_keys_e2e_tests.py`（我接进门禁）**5/5** 覆盖 symbol/schematic 9 键（DB 直读值级）；**root 另补 `maestro_nested_keys_e2e_tests.py` → 9/9**（maestro 11 键：type_name/type_value/spec_name 值级；enabled/enable_tests/disable_tests/model_file/model_section/job_type/test_name **如实标注"readback: none"**；`sections` 仅有负路径）；`place_wire` spacing 两键 → **C10** 待设计裁决。执行矩阵刷新：**53 live TB / 门禁 23 / 无人引用 0 / 今日无证据 0** | 无（仅 C10 待设计） |
| B4 | **§5 第 3 档（error 截断）不可达** | SKILL 产不出 `\e` 前缀行（printf 被加 `\o `；`error()/errset` 不进 CDS.log） | daemon/IL 侧给合成行夹具，或降为离线单测；详见 `log-options-w1-r9.md §3` |
| B5 | **离线 flaky 用例** | `test_register_flow.py::TestStepRetryAfterFailure::test_validate_can_retry_same_step`：3 次单会话中 1 次红（20:43），21:14/21:35 两次全绿 | 收口前再跑一次单会话全集；建议该 class 的 `setUp` 用**每用例独立 work-root**；详见 `offline-flaky-r9.md` |
| B6 | 证据命名不统一 | 3 条 TB 今晚确实跑过，但证据文件名用连字符（如 `c06-skill-log-semantics.json`）→ 自动核对显示"今日无证据" | 后续证据文件名带 TB 名；详见 `live-execution-gaps.md §3` |
| B7 | **门禁组成修正（23:15）** | `run_all_http.py` 里 `nested_keys_e2e_tests.py` **重复登记两次**（同一套跑两遍）；同时 `skill_log_options_e2e_tests.py`（C2/CDSlog 真机面）**只在门禁外人工跑**——正是"log 返回值没人拦"的同类隐患 | 已修：删重复项、把 `skill_log_options_e2e_tests.py` 接进门禁（放在 `infra` 之后、任何 maestro 套件之前，因其 LOG-06 读 `maestro_tb/rc_probe`）；门禁由 23 套 → **24 套**（唯一项）。矩阵/报告里的"23 套"需按 24 重算 |
| B8 | **LOG-07 并发归属（23:12 新增）** | `skill_log_options_e2e_tests.py` 增第 7 例：同一 token 并发 4 条 `log_level=all`，断言每条 `CDSlog` 只含自己的标记（spec §3 投递闸门/增量归属） | 待安静窗口跑一次取证据；若红即报新 bug |

## C. 环境

| # | 事项 | 现状 | 下一步 |
|---|---|---|---|
| C1 | `maestro_e2e` 撞 **stale write lock**（死 pid 3508716，since 20:40） | 产品按 P-096 口径**正确拒绝**（不是产品 bug）；但会让任何后续 maestro 用例红 | 跑前清锁（`rm -f <cellview>/maestro/*.cdslck`，仅限属主已死）**或**给该套件独立 fixture cell；已建议进跑前 checklist |
| C2 | vblog 实例 | 21:39 由 root 硬重启，重启后 `1+2` **ok / 0.5 s** | 后续所有 maestro/verilog 复跑都应在"刚重启 + 无并发"窗口做 |
| C3 | S2 多 role 环境 | 注册表 `rolesplit`/`vbrolec…` 的 `ssh.backend` 已由 paramiko 改 **openssh**（w1-gent 的 `accept-new` 不被 paramiko 支持）→ `role_split_tb` 5/5 | 已记入 Runbook；新建 S2/S15 类场景先按此配 |

## D. 口径（报告必须遵守）

1. **覆盖率**：只引 `cov-main/coverage-main-strict.json`，且必须同时满足"日志尾部 `全部步骤通过` + `meta.head` 与当前 HEAD 一致"；本轮 `run-meta.json` 是
   `head=86cc169` + **`dirty: true`** + `worktree_diff_sha=351f5c03…` + Coverage.py 7.16.0 → **报告要带这三项**；
   `*-append-*.json`（01:26/02:19 那批）与早于 21:56 的 `coverage-main.json` **不可引用**。跑完用 `verify_coverage_r9.py` 出一致性核对。
   **本轮已跑完**：下界 **89.83%（语句 91.88 / 分支 83.93）**，失败步骤正是 C09 与 P-106 两条；基线快照 `test/artifacts/evidence/round9/coverage-pre-r9-strict.json`（91.54/83.62/89.48）。
2. **门禁 5 红的表述**（不要再写成"5 套产品缺陷"）：1 套已复跑绿（环境瞬时）/ 1 套产品假失败竞态（A1）/ 1 套过期 TB 缺陷已修未复跑（B1）/ 1 套环境卫生（C1）/ 1 套待无负载复跑（B1）。
3. **P-086 保持观察**：半真机 `twouser_same_view_probe` 本轮 **rc=0**（其 tail 仍含 `SKILL execution timed out`，窗口仍被观察到但探针判据通过）；措辞用"观察项，探针本轮通过、窗口仍偶发"。
4. **离线**：写"0 红，但 3 次单会话中观测 1 次 flaky（非产品）"，不要写"稳定全绿"。
5. **嵌套键**：写"L0 契约 **21/21**；真机 **20/21 键已落位**（`nested_keys_e2e_tests` 5/5 + `maestro_nested_keys_e2e_tests` 9/9），仅 `place_wire` spacing 两键 → **C10**"。
   （原措辞"真机未逐键验证"是 20:xx 的旧状态，已被 B3 的实测取代——两处**不得**再自相矛盾。）
6. **注册表缺省 vs spec §6.1 防御性回退（口径待澄清，非缺陷）**：spec §6.1 写"请求不携带 `log_level` 且注册表无值时按 `off` 处理（防御性回退）"，
   但实现里 `UserEntry.cdslog` 恒有值（`CdsLog.log_level` 默认 `all`，`src/common/registry.py:282`），标准注册表 `log-vblog/registry.json` 里 `cdslg` 键缺失 →
   实测 LOG-01 缺省请求 `CDSlog` 非空（= all）。两种读法都可自洽：(a) 该句只约束 daemon 协议缺省（`req.get("log_level","off")`，已实现）；
   (b) 未配置用户应默认 off（则实现偏离）。**报告写"待裁决"，不要写成缺陷**；若裁定 (b)，再立卡改默认值。
