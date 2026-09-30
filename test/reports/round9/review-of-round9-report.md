# round9 报告交叉复核（B 线 → 主报告）

> 复核人：subagent `/root/opparam_r9`｜2026-09-29 21:03｜对象：`test/reports/round9/round9-测试报告.md`（20:59 版，"进行中"）
> 方法：逐条把主报告的数字与我方产物的**现跑证据**对表；下列每条都给了可直接替换的措辞。

## A. 三处已过期（我方工作已闭环，主报告仍写"进行中/待补"）

| # | 主报告位置 | 现文 | 应改为 | 现跑证据 |
|---|---|---|---|---|
| A1 | §2.3 嵌套键 | "未覆盖 28 条（20 键名）… 已派 B 线补测（进行中）" | "**L0 契约已补**：新增 `test/offline/unit/test_nested_command_keys_contract.py`（**21 用例 21/21 绿**，含负例），补点后审计 **未触碰字段 0 / 未覆盖枚举值 0**；**真机补点未做**（残留，见 C1）" | 本轮重跑 `test/reports/round9/nested_key_audit.py` → `未被触碰字段 0；未覆盖枚举值 0`；`pytest --collect-only` → 21 |
| A2 | §2.4 W-4 | "`serdes_rx_flow_tb`/`design_iterate_tb` 关键 stage 无值级读回 → **待补**" | "**已补并验证**：真缺口只有 `stage_buf`（已补实例名+网络名读回），`stage_ctle` 补显式实例集合断言；**http 实测 `--stage buf` rc=0（6.75s）、`--stage ctle` rc=0（16.95s）**。`stage_top`/`stage_layout` 复核后本就有值级判据" | `test/artifacts/evidence/round9/serdes-r9-buf/serdes-buf.json`（`buf_instances=["MN","MP"]`、`buf_nets=["vdd","vin","vout","vss"]`）、`serdes-r9-ctle/serdes-ctle.json`（9 实例 + 10 网络 + `net_mismatches={}`） |
| A3 | §6 待办 1、2 | "嵌套键 28 条补测（进行中）"、"W-4 关键 stage 值级读回" | 删掉这两条，替换为 C 区列出的**新残留** | 同上 |

## B. 一处口径风险（会被评审判"自相矛盾"）

**B1 §1 真机行写"10 套包 E2E 门禁"，但 `run_all_http.py` 现在是 19 套。**
两个 runner 不是一回事，建议写清楚：

* `test/shared/runners/run_package_e2e.ps1`：**10 套**（`test/artifacts/package-e2e-r9-full/` 那张表）；
* `test/shared/runners/run_all_http.py`：**19 套**（round9 又接入 `step_details` / `layout_geometry_classification` / `gui`，
  原 16 → 19；清单见 `test/reports/round9/live-execution-matrix.md`）。

另外：`layout` 那次 `rc=1` 的日志（`package-e2e-r9-full/layout.log`）是 **20:30 的旧产物**，
当时 TB 还没传 `step_details=True`（C1 契约下成功响应默认省略 steps）；TB 于 20:41/20:44 修好，**不要拿旧日志当现红**。

## C. 建议补进 §6 的四条残留（当前版本缺）

1. **嵌套键只有 L0 契约**：20 个键 + 5 个 spectre mode 的**离线拼装**已钉住，但**真机行为未逐键验证**（离线契约不计真机覆盖）；落点建议见 `nested-key-coverage.md §4`。
2. **§5 第 3 档（error 截断）不可达**：`[log truncated: …]` 需要"降级后 error 增量仍超限"，
   而 SKILL 侧产不出 `\e` 行（`printf` 会被加上 `\o ` 前缀；`error()`/`errset` 不进 CDS.log）。
   建议 daemon/IL 侧给可控夹具，或降为离线单测。详见 `log-options-w1-r9.md §3`。
3. **`calibre.drc`/`calibre.lvs` 的 `fmt`/`lvs_run_dir` 是惰性字段**（只校验+回填 meta，读取点在不可达的 PEX 分支）——
   与 P-092 同族，需设计二选一（spec 声明保留位 / 删字段）。详见 `op-param-r9.md §4`。
4. **证据命名不统一**：3 条 TB 今晚确实跑过，但证据文件名用连字符（如 `c06-skill-log-semantics.json`）导致
   自动核对显示"今日无证据（4）"。建议证据文件名带 TB 名。详见 `live-execution-gaps.md §3`。

## D. 已核对为**准确**的部分（无需改动）

* §2.1 原子级（60 / 零引用 0 / 误报 13 有理由 / 弱判据 0）——与本轮复跑一致；
* §2.2 的 `test_common_request_fields_contract.py` **84 项**（现跑 `--collect-only` = 84）✓；
* §2.5 三条接线 TB 的成绩（step_details 6/6、gui 4/4、geometry 4/4）✓；
* §3 C06 的两条红钉描述（A 空 / B 串场 / C 绿 / D NOTE）与我方 `skill_log_semantics` 证据一致；
* §5 台账"未关闭 2（P-086、C06）"与 `test/reports/bugs/` 当前状态一致。

> ⚠ 21:12 更新：**D 的最后一条已过期**——`make_bug_cards.py` 的 OPEN 列表现为 **3 条（C06/C07/P-086）**，
> 磁盘也有 3 张开放卡；主报告 §5 的"未关闭 2"与 §3 未列 C07 均需改。详见 `ledger-integrity-r9.md`（L1–L5）。

## E. 建议的最终收口清单（供主报告直接采用）

1. 三层结果：离线 0 红；半真机整组结果；真机 **19 套** http 门禁结果（含本轮新接入 3 套）；
2. 五张核账：原子 0 缺口 / op×参数 **真缺口 0**（215 合同 + 25 N-A，含 2 条惰性字段待裁）/ 嵌套键 **L0 0 缺口但真机未补** / 断言强度 W-1..W-4 **全部关闭** / 真机执行矩阵 **无人引用 0**；
3. 残留：C 区四条 + 半真机与 maestro 复审结论。

---

## F. 23:05 终版复核（对 23:00 版报告）

**已并入本版（我上轮提的 L1/L2 已处置）**：§1 分清两个 runner（10 套 vs 19 套）并写明"复跑后 17/19 绿，剩 2 红 = P-106/C09"；
§2.6 覆盖率按 strict + provenance + "含 2 个失败步骤的条件覆盖率"写；§5 未关闭 **6**（含 C10）；§7 收录全部交叉评审件。

**仍需改的两处（都是"报告内部数字对不上"，很小）**：

| # | 位置 | 现文 | 应改为 |
|---|---|---|---|
| G1 | §2.5 | "live TB 共 **50** 个" | **53**（我 23:05 重跑执行矩阵：53 live TB / **门禁 23** / 无人引用 **0** / 今日无证据 **0**）；并把"3 条接线"改为"**5 条接线**"（我接的 step_details / layout_geometry / gui / **nested_keys** + root 接的 maestro_mc、maestro_nested_keys） |
| G2 | §6.1 | "**maestro 12 键待补（B 线补测中）**" | 与本报告 §2.3 自相矛盾：§2.3 已写 `maestro_nested_keys_e2e_tests.py` **9/9 PASS**（maestro 11 键已落、sections 仅负路径、其余如实标 readback:none）。应改为"**嵌套键真机 20/21 键已落**；仅 `place_wire` spacing 两键属 **C10** 待设计裁决" |

**台账 L7（已闭合）**：`问题登记.md` 的 C10 行由 B 线于 23:07 直接补上（既有 6 列格式、最新一行）；
复核：六张未关闭卡 C06/C07/C09/C10/P-106/P-086 **全部有行**、bug 链接 **8/0 断链**、`make_bug_cards.py --check` **9/0/0**。
至此 §F 的 G1/G2/L7 三项全部处置完毕，**报告与台账无已知未闭合项**。
