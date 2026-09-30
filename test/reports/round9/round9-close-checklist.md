# round9 · 收口检查单（按顺序执行，带前置条件与期望）

> 整理：subagent `/root/opparam_r9`｜2026-09-29 22:15
> 用法：从上往下做；每步都写"前置 / 命令 / 期望 / 证据 / 失败怎么办"。

## 0. 前置（30 秒）

```bash
python test/shared/runners/resident_env_check.py          # 期望 remote 实例 8/8
curl -s http://127.0.0.1:8127/health                     # 期望 ok
python -c "import json,urllib.request as u;print(json.load(u.urlopen(urllib.request.Request('http://127.0.0.1:8127/api/operation',data=json.dumps({'operation':'basic.skill.execute','token':'vb-vblog','skill_code':'1+2'}).encode(),headers={'Content-Type':'application/json'},method='POST'))))"
```

* vblog `1+2` 期望 `ok=True` 且 <2 s；**>10 s 或超时** → 先按 Runbook §10.6 重启 vblog（kill 按 cwd 匹配 + 清 `*.cdslck`），不要带着坏实例跑后面几步。
* 全程**不要并发**：一次只跑一套（今晚 21:28 那次大面积 `SKILL execution timed out` 就是并发造成的）。

## 1. 覆盖率核对（离线，随时可跑）

```bash
python test/reports/round9/verify_coverage_r9.py
```

* 期望：`all_steps_passed=true`、`meta.head_matches_now=true`。
* 把 `strict_totals`（行/分支/combined 三个数）+ `head 86cc169` + `dirty:true` + `worktree_diff_sha 351f5c03…` + `coverage 7.16.0` 一起写进报告；
* 与基线 `coverage-pre-r9-strict.json`（91.54 / 83.62 / 89.48）对比 `delta`；
* 检查 `baseline.removed/added`，特别确认 **`stress_server` 没有回归**；
* `all_steps_passed=false` → 该 run 的数字**不得**当主口径（先修失败步骤或说明）。

## 2. 红钉 runner（真机，轻量）

```bash
python test/shared/runners/run_redpins.py          # 或 --only c06
```

* 期望：`[RED-PIN-HOLDS] c06`（C06 未修 → 红钉钉住）。
* 若 `RED-PIN-UNEXPECTED-GREEN` → 缺陷可能已修：去 `make_bug_cards.py` 删 C06 红钉/改判；
* 若 `RED-PIN-BROKEN` → 那是环境/超时，不算红钉成立（看 `test/artifacts/evidence/redpins/c06.log`）。

> **✅ 已完成（22:34）**：`[RED-PIN-HOLDS] c06 rc=1`，退出码 0；证据 `test/artifacts/evidence/redpins/{c06.log,redpins.json}`。
> C06 现在的红钉是 **11 例**（A/B/F/H/I/J/K 共 8 红 = print 无换行不落本请求 CDSlog；C/D/E/G/ENV 5 绿 = printf/换行路径）。
> 途中修了 runner 自身一个 Windows 编码 bug（`text=True` 按 GBK 解码 → stdout=None），已改为显式 UTF-8。

## 3. 两套"缺无负载结果"的门禁（真机，安静窗口，串行）

```bash
python test/live/packages/maestro_view_param_e2e_tests.py --transport http
python test/live/packages/verilog_import_params_e2e_tests.py --transport http
```

* 前置：第 0 步通过、且**没有别的 TB/覆盖率在跑**。
* `verilog` 期望 **13/13**（IMP-07 的 C4 位置索引已于 21:16 修好）；
* `maestro_view_param` 期望 9/9；若仍红且错误是 `SKILL execution timed out` → 记"环境/负载"，**不要**判产品红；
* 证据落 `test/artifacts/evidence/round9/`（建议命名带套件名）。

> **✅ 已完成（22:35–22:39，安静窗口）**：`maestro_view_param` → **9/9 PASS**（`evidence/round9/maestro-view-param-r9b.json`）；
> `verilog_import_params` → **13/13 PASS**（`evidence/round9/verilog-import-params-r9b.json`，含 IMP-07/08/10/11）。
> 结论：这两套此前的红都是**环境/并发**（我的 burst、实例重启），不是产品回归。

## 4. 离线 flaky 复跑（离线，安全）

```bash
python -m pytest test/offline -q | tee test/artifacts/evidence/round9/offline-single-session-r9c.txt
```

* 观察 `test_register_flow.py::TestStepRetryAfterFailure::test_validate_can_retry_same_step` 是否复现（历史 3 次里 1 次红）；
* 若复现：证据里现在会带 `retried.errors`（20:53 加的诊断）→ 照 `offline-flaky-r9.md §3` 处理（建议该 class 用独立 work-root）。

## 5. 业务流程最小批（真机，较长；按需）

```bash
python test/live/flows/serdes_rx_flow_tb.py --stage all --out test/artifacts/evidence/round9/serdes-r9-full
python test/live/flows/design_iterate_tb.py
```

* 这两套是"完整工程流/迭代流"的代表；跑完把 stage JSON 收进 `evidence/round9/`；
* 其余流程（adc_sar / multiuser_* / multihop / scale_100 / s11 / project_flow / lvs_from_schematic）若本轮不跑，
  按 `round9-flows-not-rerun.md` 如实写"最近证据为 round8"。

> **✅ 第 1 条已完成（22:44）**：`serdes_rx_flow_tb --stage all` → **rc=0 全绿**（probe/lib/buf/ctle/term/top/layout/gds/cdl/sim），
> 证据 `test/artifacts/evidence/round9/serdes-r9-full/{serdes-*.json,summary.json}`；
> 关键数值：GDS 4096 B×2、CDL 697 B、AC 增益 5.055 dB@1MHz / 峰值 5.409 dB / BW>100 MHz、tran 摆幅 0.396 V。
> **✅ 第 2 条也已完成（22:51）**：`design_iterate_tb` → **11 stage 全绿 rc=0（`failures=[]`）**：
> r1 sch/sym/layout/gds/sim（增益 22.79 dB、BW 2.24 GHz、摆幅 1.595 V）→ r2 改图（rename_pin、CL 20f→200f、加 CL2/CC/RF）→ sym/layout（**shape 2→4**）→ sim（增益 22.82 dB、**BW 0.447 GHz**、摆幅 1.593 V）；
> 证据 `test/artifacts/evidence/round9/design-iterate-r9/{iterate-*.json,iteration-summary.json}`。
> 其余流程（adc_sar / multiuser_* / multihop / scale_100 / s11 / project_flow / lvs_from_schematic）仍待跑或如实标注"最近证据 round8"。
>
> **✅ 追加（22:52）**：`adc_sar_flow_tb`（**多用户**：`vb-vbuser1` + `vb-vbuser2` 同一库协同）→ **24/24 步 ok=true，rc=0**，
> 证据 `test/artifacts/evidence/round9/adc-sar-r9`。至此"两个完整项目"达成（serdes_rx 全流程 + adc_sar 多用户）。
> 仍待：multiuser_serdes_rx / multiuser_layout_handoff / multihop / scale_100 / s11 / project_flow / lvs_from_schematic。
>
> **✅ 追加（22:54–22:55）**：`multiuser_serdes_rx` → **17/17 ok**；`multiuser_layout_handoff` → **12/12**
> （A 写→B 见→B 写→A 见、并发写结构化拒绝、**无 `*.cdslck` 残留**）；证据 `evidence/round9/multiuser-serdes-r9`、`evidence/round9/multiuser-handoff-r9`。
> ~~仍待：multihop / scale_100 / s11 / project_flow / lvs_from_schematic~~ → **全部完成**：
> s11（PASS/match）、lvs_from_schematic（CORRECT）、**scale_100**（100 fake ×2 轮全绿）、
> **project_flow**（rc=0，spectre 0 err/0 warn）、**multihop**（**10/10**，两跳+SOCKS5）。
>
> **✅ 追加（22:56）**：`s11` 链已由覆盖率 run + root 的两条 s11 TB 覆盖（verdict **PASS** / inprocess **ok** / postsim **match**）；
> `lvs_from_schematic_tb` → **rc=0 全 ok，LVS verdict `CORRECT`**（ports 6/6、nets 9/9、inst 6/6、differences []），
> 证据 `evidence/round9/lvs-from-schematic-r9.log`。至此**已复跑 8 套流程**；仍待：multihop（需 S15 环境）/ scale_100 / project_flow。

## 6. 文案收口（三处）

1. 主报告 §5："未关闭 **2**" → **5**（C06 / C07 / C09 / P-086 / P-106）；
2. 主报告 §3：新发现补 **C07 / C09 / P-106**；
3. `问题登记.md`：补 **C09** 一行（其余 4 张已有；22:20 复核断链 0）。

## 7. 机械核账（离线，30 秒）

```bash
python test/shared/runners/make_bug_cards.py --check          # 期望 计划 8 / 缺失 0 / 过期 0
python test/shared/runners/check_tb_headers.py                # 期望 114/114 合格（22:15 实测）
python test/shared/runners/check_skip_reasons.py              # 期望 静态 0 违规 / 动态无原因 0
```

## 8. 环境恢复日常

* 停掉非日常面（如果开了 8128/8130/8131 等）；
* `resident_env_check.py` 回到 8/8；保留 8124+8127 标准形态；
* 若本轮重启过 vblog/vbuser2，把处置记进 Runbook §10。
