# REVIEW-C · 第八轮报告数字复核（独立评审）

> 评审方：`/root/verilog_params/red_team`（独立子代理，未参与报告/矩阵撰写）
> 快照：git `HEAD=e3e810d` + 未提交工作区（2026-09-29 00:0x–01:xx 复核）
> 方法：**直接重算证据文件**（脚本 `test/artifacts/tmp/r8_redteam_numbers.py`、`r8_redteam_numbers2.py`、`r8_gap_dump.py`、`r8_grep.py`），不采信报告复述。
> 结论（首轮快照 2026-09-28 23:43–23:52）：**12 项一致 / 8 项不符或口径冲突 / 2 项需注明**。
> **二轮更新（2026-09-29 00:1x–00:3x，工作区被 root 实时修复）见 §4。**

## 1. 逐项核对表

| # | 声称（出处） | 我重算的证据 | 判定 |
|---|---|---|---|
| 1 | 离线 Win：**2456 用例**（`round8/round8-测试报告.md` §1.1/§7、`round8/README.md` §0.0） | `offline-win-final.xml`：`<testcase>`=**1800**、failures=0、skipped=21、xfail=13；`tests=` 属性=2456（虚高，报告 §4.1 自己声明不得引用） | **不符（口径混引）** |
| 2 | 离线 Linux：1800 / 0 红 / 31 skip（11 xfail） | 同 XML 口径 = 1800 / 0 / 31 / 11 ✓ | ok |
| 3 | 半真机：39 探针 / 32 ok / 7 fail | `semi-probes-final.json` 实测 39 行，status: ok=32 / fail=7 ✓ | ok（洪性质见 #4） |
| 4 | "7 条 fail 全部是已立案预期红钉，没有一条环境抖动"（`round8-测试报告.md` §4.3） | 7 条中 2 条是 **`ENV: no Interactive.* history`（rc=2 前置失败）**：`maestro_export_include_results_probe`、`maestro_open_waveform_result_probe`（见 `semi-logs/` 同名日志）；对应红证来自 standalone 复跑（`maestro-include-results/include-results.json` verdict=RED、`p089-open-waveform-result.json` verdict=RED） | **表述过强**：应写"5 条断言红 + 2 条前置失败（另行复跑判红）" |
| 5 | A 轴：297 → direct 219 / indirect 16 / partial 9 / na 53（顶层报告 §0/§1 表） | `round8-spec覆盖矩阵.json` 实测：**direct 222 / indirect 16 / partial 6 / na 53**（=297） | **不符（顶层报告 stale；9070f5e 收口 222/6 后未同步）** |
| 6 | 覆盖率：语句 91.54% / 分支 83.62% / 合并 89.48%（nested §0/§7） | `cov-main/coverage-main-strict.json`：statements 91.544%、branches 83.624%、combined 89.484% ✓；但 `送审自查表.md` 行 6 写 **91.56/83.66/89.50** = `coverage-main.json`（非 strict，+14 statements） | 数字有据 / **双口径在流通，需统一** |
| 7 | 压测 **216 步** / 0 失败（nested §1.3/§7、README §0.0） | `production-face-stress.json`：`steps_total=108`、`steps_failed=0`、planned/answered rounds=36/36（36×3 步） | **不符**：216 无被引证据（顶层写"此前 216 步"较准；nested 把 216 直接挂在该文件上） |
| 8 | 11 套包"逐套 PASS / 11/11"（nested §7、README §0.0） vs "10 稳定绿 + 1 被阻塞"（顶层 §0/§4.4） | `http-e2e/results.json`：`all_passed=false`（maestro rc=1、calibre rc=1，9/11 ok）；`package-e2e-r8-final.log`(21:46)=10/11；`final2`(22:01)=9/11；maestro 23/23 证据在 **`test/artifacts/tmp/maestro_run9.log`（21:28，不在被引证据路径）**；22:06 复跑 `maestro-rerun3.err.log` = `Empty response from daemon` 崩溃 | **两报告结论冲突**：顶层保守口径更符合证据；nested"11/11"需改"批量 9–10/11 + 逐套复跑（含 22:06 崩溃注记、证据入库）" |
| 9 | maestro **22/22**（README §0.0/§6 行 2） | 实测 23 条 PASS（CONFIG-01…HISTORY-01）；顶层 §4.4 写 23/23 | **不符（22 无证据）** |
| 10 | e2e 10 用例 0 红 + local 4/4 | `live-e2e.xml`：10 case / 0 fail / 5 skip ✓；local：`local-live-r8.txt` = "4 passed in 7.67s"（被引的 `local-live-r8b.txt` 只有进度点，80B） | ok / 引用文件偏弱 |
| 11 | 五接口 5/5 | `cov-remote-real-r8.json`：steps 5/5 全 ok=true ✓ | ok |
| 12 | 注册 4 条：py27 10/10、real-ciw 12/12、role-split 28/28、six-local 8/8 | 4 个 json 的 passed/total、checks_passed/total 实测一致 ✓ | ok |
| 13 | timeout 家族 79/79 拒非法值 | `timeout-contract.json`：declared_timeout_ops=79、rejected_400=79、accepted_invalid_200=[]、unresolved=[] ✓ | ok |
| 14 | spec 297 → 222/16/6/0/53 | 矩阵 json 实测一致 ✓（与顶层 219/9 冲突 → 见 #5） | ok |
| 15 | op×参数 628 → CANDIDATE 553 / GAP 46 / NO-OP 29 | `op-param-matrix.json`（23:43 快照）实测一致 ✓；但 `送审自查表.md` 行 3 写 **539 / 38 / 51（24 GAP+27 零调用点）/ 78**（stale）；且 29 条 NO-OP = calibre.export(7)+calibre.pex(22)——同一时刻的 `op-coverage.json` 已关联该 TB（`calibre_pex` 3 个调用点），说明 23:43 快照里两工具的调用关联不一致 | 部分不符（矩阵已 00:06 重建修复，见 §4） |
| 16 | 原子 60 / GAP=0 | `round8/atom-coverage.json`（19:51）gap=0/needs_triage=0 ✓；另有更新的 `evidence/atom-coverage-2026-09-28.json`（23:20）gap=0；两文件 `write_without_readback` 分别 12/11，报告未说明 | ok（双文件 + 未说明指标） |
| 17 | 缺陷：本轮新增 24（P-078…P-101）、未关闭 25 | `test/reports/bugs/P-*.md` = 25 张（P-070 + P-078…P-101）✓ | ok |
| 18 | 自查表 §1："半真机 38/32/6"、"51 条逐 op 缺口" | 与最终 39/32/7、46/29 不符 | **不符（文档 stale）** |

## 2. 不符清单（按影响排序）

1. **N1（严重）两报告结论冲突**：11/11 vs 10+1，必须取一套口径并同步 README/自查表。
2. **N2（严重）压测 216 vs 证据 108**：把数字改为 108（或补 216 那次的证据文件）。
3. **N3（中）顶层报告 A 轴 219/9 过期**（矩阵=222/6）。
4. **N4（中）半真机"7 全红钉"表述**（2 条为 ENV 前置失败；红证在 standalone 复跑里）。
5. **N5（中）Windows 离线 2456 与平台一致口径 1800 混引**（nested §1.1/§7、README §0.0）。
6. **N6（中）maestro 22 vs 23 + 证据未入库 + 22:06 崩溃未记录**。
7. **N7（低-中）覆盖率两套数字在流通**（strict vs 非 strict），需指定唯一口径。
8. **N8（低）自查表多处 stale**（38/6、51/24/27、539/38）。
9. **N9（低）atom-coverage 双文件与 `write_without_readback`（11/12）未说明**。
10. **N10（流程）op×参数矩阵未包含最新 calibre export/pex TB**，29 条 NO-OP 与报告 G12 冲突 → **已于 00:06:48 重建修复（569/59/0），见 §4**。

---

## 4. 二轮复审更新（2026-09-29 00:1x–00:3x，快照漂移后）

> 复核期间工作区被 root 实时修复：`op-param-matrix.json` 等 00:06:48 重建、顶层报告 00:10:21 更新并逐条吸收本复核编号（§10 明确列出"红队发现与处置"）。
> 上文 §1/§2 为首轮快照结论（保留用于审计追溯）；下表为逐条现状。

| 发现 | 现状 | 证据 |
|---|---|---|
| N2 压测 216 | **已修复**：改 **108 步**（36 轮 × 3 步），并注明"红队 REVIEW-C #7 更正" | 顶层报告 §4.4；`production-face-stress.json` steps_total=108 |
| N3 A 轴 219/9 | **已修复**：改 **222/6**（与矩阵一致） | 顶层报告 §0/§1 |
| N4 半真机"7 全断言红" | **已修复**：改为"5 断言红 + 2 前置失败（standalone 复跑判红）"，注明 REVIEW-C #4 | 顶层报告 §4.3 |
| N5 离线 Win 2456 | **顶层已修**（1800 + 口径注）；**nested 报告 §1.1/§7 与 README §0.0 仍是 2456** | 顶层 §4.1；nested/README 未同步 |
| N6 maestro 22/23 + 证据入库 | **已修复**：日志归档 `evidence/round8/maestro-23of23-2128.log`（我实测 23 条 PASS），注明 REVIEW-C #6/#8 | 顶层报告 §4.4 |
| N7 覆盖率双口径 | **已修复（口径唯一化）**：唯一权威 = `coverage-main-strict.json`；非 strict 差异 14 语句已注明 | 顶层报告 §5 |
| N8 自查表 stale | **未修复**：`送审自查表.md`（23:42）仍写 91.56/83.66/89.50、38/32/6、51/24/27、539 | 自查表行 3/6/28/38 |
| N9 原子双文件 | **已修复（注明）**：§2 口径注引用 23:20 版并说明差异来源 | 顶层报告 §2 |
| N10 矩阵 NO-OP 29 | **已修复**：00:06:48 重建 → CANDIDATE 569 / GAP 59 / NO-OP 0；我用同一构建器在 tmp 复算结果一致 | `op-param-matrix.json`（M，0:06:48） |
| N1 两份报告冲突 | **由"冲突"变为"单边陈旧"**：顶层已修，nested `round8/round8-测试报告.md`（23:52）仍写 2456、216、22/22、11/11、219/9（README 同）→ 建议合并/删除 nested 或同步 | nested §1.1/§7、README §0.0 |
| **N11（新）role-split 29/29 无证据** | **新发现**：报告 §1 注/§4.4 声称 29/29；但 `registration-role-split.json`（20:12:53）= checks 28 / passed 28，且其中**没有** `deploy-paths-contain-no-token`；该检查在 TB 20:55:38 才加入（line 380），全 `test/artifacts` 搜不到含该检查的证据 | 需复跑该 TB 后更新证据，或改回 28/28 + 说明 |

## 3. 复核命令（可重放）

```
python test/artifacts/tmp/r8_redteam_numbers.py   # XML/JSON 重算
python test/artifacts/tmp/r8_redteam_numbers2.py  # 半真机/压测/日志补充
python test/artifacts/tmp/r8_gap_dump.py          # GAP/NO-OP 明细
python test/artifacts/tmp/r8_grep.py              # 报告数字行级比对（输出 r8_numbers_grep.txt）
```
