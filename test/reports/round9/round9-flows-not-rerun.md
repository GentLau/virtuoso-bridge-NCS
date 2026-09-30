# round9 · 业务流程 TB 本轮复跑情况（B 线核对 + root 22:45 复核更新）

> ⚠ **本文件 §1 的原始表格是 21:24 的快照，已被下表取代**（21:24 之后 root 又跑了几条流程）。
> 最新状态以 §1b 为准；§1 原表保留只为留痕。

## 1b. 22:45 复核后的真实状态（以本节为准）

| 业务流程 TB | 本轮（round9）状态 | 证据 |
|---|---|---|
| `serdes_rx_flow_tb.py --stage all` | ✅ 已复跑（22:17） | `evidence/round9/flow-serdes-rx-r9.log` |
| `design_iterate_tb.py --stage all --with-lvs` | ✅ 已复跑（22:19，含 LVS=correct） | `evidence/round9/flow-design-iterate-r9.log` |
| `adc_sar_flow_tb.py` | ✅ 已复跑（22:32，24/24；**此前证据只到 round8**） | `evidence/round9/flow-adc-sar-r9.json` |
| `multiuser_layout_handoff_tb.py` | ✅ 已复跑（22:35，12/12；并修掉旧版文本计数假红） | `evidence/round9/multiuser-layout-handoff-r9.json` |
| `role_split_tb.py` | ✅ 已复跑（21:25，5/5） | `evidence/round9/role-split-r9.json` |
| `s11_full_flow.py` | ✅ 已复跑（含在 22:31 结束的官方 coverage runner 内，非失败步骤） | `evidence/round9/coverage-main-r9.log` |
| `maestro_mc_e2e_tests.py`（MC 验收，非 flow） | ✅ 已复跑（22:43，9/9；**此前无人跑过**） | `evidence/round9/maestro-mc-r9.json` |
| `multiuser_serdes_rx_tb.py` | ❌ 本轮未跑（最近 round8） | `evidence/round8/flow-serdes-multiuser.log` |
| `multihop_jump_tb.py` | ✅ **本轮已跑（23:02，10/10）**（w3 唤醒 + 两处环境修复后，见下） | `evidence/round9/multihop-r9.json` |
| `project_flow_tb.py` | ✅ **本轮已跑（23:00，rc=0，含 spectre `0 errors,0 warnings`）** | `evidence/round9/project-flow-r9/` |
| `lvs_from_schematic_tb.py` | ❌ 本轮未跑（最近 round8） | `evidence/round8/lvs-from-schematic.json` |
| `s11_inprocess_lvs_tb.py` / `s11_postsim_compare.py` | ❌ 本轮未跑（后仿/PVT 口径） | round8 及更早 |
| `scale_100_tb.py` | ✅ **本轮已跑（22:57，100 fake × 2 轮全绿）** | `evidence/round9/scale-100-r9.json` |

环境备注（22:45 实测）：`wsl-gent`（GLIS-DESKTOP）与 `w1-gent` 在线；**w2/w3/w4 三台 lab WSL 不可达**
→ 依赖 w2/w3/w4 的 `multihop_jump_tb`、`registration_hostkey_rotation_tb`（P5 需要 w4 的
`/usr/local/sbin/w4_hostkey_cycle.sh` + sudo）本轮无法执行（后者 20:38 曾跑过一次 ok=true，证据
`evidence/round9/reg-hostkey-rotation.json`）。

> 执行：subagent `/root/opparam_r9`｜2026-09-29 21:24｜只读核对（按证据文件所在轮次判断）
> 口径：**用证据文件所在的轮次目录判断**（`evidence/round5*…round8*` vs `evidence/round9/`），
> 不用 mtime（本 worktree 的 mtime 全被刷新过，不可信）。

## 1. 结论

| 业务流程 TB | 最新证据所在 | 本轮（round9）复跑 |
|---|---|---|
| `adc_sar_flow_tb.py` | `evidence/round8/adc-sar.json` (+round7) | ✅ **本轮已复跑（22:52）**：**多用户**（token-a=`vb-vbuser1`、token-b=`vb-vbuser2`，同一 `adc_sar` 库）→ **24/24 步 ok=true，rc=0**（含 A/B 两侧写读、`check_and_save`、spectre license 检查）；证据 `evidence/round9/adc-sar-r9` |
| `serdes_rx_flow_tb.py`（全流程） | `evidence/round5-serdes-rx.json` | ✅ **本轮已全流程复跑（22:44，`--stage all`，rc=0）**：probe→lib→**buf**（读回 MN/MP + 网络）→**ctle**（9 实例 + 10 网络 + `net_mismatches {}`）→term→**top**（层级 master 全对、`hierarchy_mismatches {}`）→**layout**（3 实例/3 shape）→**gds**（两目录导出各 4096 B）→**cdl**（697 B auCdl）→**sim**（AC 增益 5.055 dB@1MHz / 峰值 5.409 dB / BW>100MHz、tran 摆幅 0.396 V，`ac_checks` 全 true）；证据 `evidence/round9/serdes-r9-full/{serdes-*.json,summary.json}` |
| `s11_full_flow.py` | `evidence/round6b-verify/five-vb-s11.json` 等 | ✅ **本轮已跑**：覆盖率 run 的 `S11 full flow (LVS)` 步骤（22:30–22:31，未在失败步骤里）→ `evidence` 侧 `s11-lvs-verdict.json` **verdict=PASS**；另 root 22:48/22:49 跑了 `s11_inprocess_lvs_tb`（**ok=True**）与 `s11_postsim_compare`（**verdict=match**），证据 `evidence/round9/s11-inprocess-lvs-r9.json`、`s11-postsim-r9.json` |
| `project_flow_tb.py` | `evidence/round8/flow-project-flow.log` | ✅ **本轮已复跑（23:00，rc=0）**：probe→lib→schematic/symbol/cdl/layout/GDS(inv1)→**spectre sim（`0 errors, 0 warnings`）** |
| `design_iterate_tb.py` | `evidence/round8/flow-design-iterate.log`、`round8/design-iterate/` | ✅ **本轮已复跑（22:51，11 stage 全绿 rc=0，`failures=[]`）**：r1 sch→sym（术语 vdd/vin_ext/vout/vss）→layout（MP/MN + 2 shape）→**gds**→**sim**（AC 增益 22.79 dB / BW 2.24 GHz / 摆幅 1.595 V）；r2 **改图**（rename_pin → vout_main、加 CL2/CC/RF、CL.c 20f→200f）→sym→layout（**shape 2→4**）→**sim**（增益 22.82 dB / **BW 0.447 GHz**（CL×10 后带宽下降符合预期）/ 摆幅 1.593 V）；证据 `evidence/round9/design-iterate-r9/{iterate-*.json,iteration-summary.json}` |
| `lvs_from_schematic_tb.py` | `evidence/round8/lvs-from-schematic.json` | ✅ **本轮已复跑（22:56，rc=0 全 ok）**：schematic 读（顶层 6 pin + 子层 depth1/2）→ **auCdl CDL 563 B** → **GDS 36864 B** → upload → `calibre.lvs` → `read_results` **status=correct**（ports 6/6、nets 9/9、inst 6/6、**differences []**）→ **verdict 含 `CORRECT`** → 报告下载 39263 B+sha256；证据 `evidence/round9/lvs-from-schematic-r9.log` + `env/scenario-project65/lvs/evidence-lvs-from-schematic.json` |
| `multiuser_serdes_rx_tb.py` | `evidence/round8/flow-serdes-multiuser.log` | ✅ **本轮已复跑（22:54）**：两用户（`vb-vbuser1`/`vb-vbuser2`）共享 `serdes_rx` → **17/17 ok**（末例 A-final：`rx_fe` 4 器件 MN1/MN2/MP1/MP2）；证据 `evidence/round9/multiuser-serdes-r9` |
| `multiuser_layout_handoff_tb.py` | `evidence/round8/multiuser-layout-handoff-r8.json` | ✅ **本轮已复跑（22:55）**：**12/12**——A 写 2 rect → A 自读 → **B 见到 A 的 shapes** → B 写 → **A 见到 B 的 shapes** → **并发写被结构化拒绝** → A 仍可写 → **无 `*.cdslck` 残留** → final-read-ok；证据 `evidence/round9/multiuser-handoff-r9` |
| `multihop_jump_tb.py` | `evidence/round8/flow-multihop*-.log` | ✅ **本轮已复跑（23:02，10/10）**：直达基线 → 两跳（client IP=`172.20.170.23`、文件 sha256、daemon skill）→ SOCKS5（自拉隧道、出口=`172.20.170.23`）；证据 `evidence/round9/multihop-r9.json` |
| `role_split_tb.py` | `evidence/round8/flow-role-split*.log` | ✅ **本轮已复跑（21:25）**：`--work-dir test/artifacts/env/scenario-role-split --user rolesplit` → ok=true，5/5（daemon→GLIS-DESKTOP、command→w1-gent、file 上传下载字节一致），证据 `evidence/round9/role-split-r9.json`；顺带把 spec `路由#024` 的本轮证据补上 |
| `scale_100_tb.py` | `evidence/round8/flow-scale-100.log` | ✅ **本轮已复跑（22:57）**：100 fake × 2 轮 → 每轮 100 ok / 0 failed / 0 misrouted + 负控检测 misroute |

**本轮真机侧实际覆盖**：**21 套包门禁** + 注册两条 TB + **11 套业务流程/专项 TB 全部复跑**
（role_split / serdes 全流程 / adc_sar 多用户 / design_iterate / multiuser_serdes_rx / multiuser_layout_handoff /
s11 链 / lvs_from_schematic / multihop / scale_100 / project_flow）+ 半真机整批。
**"最近证据在 round8"的说法已不成立——流程 TB 本轮 11/11 全部跑过。**

## 2. 对报告口径的影响（必须如实写）

* **可以**写："本轮真机复跑覆盖 upper-package 全量 19 套 + 注册链路；业务流程 TB 未在本轮整体复跑，其最近证据为 round8。"
* **不要**写："完整工程流（spec→原理图→symbol→版图→LVS→仿真）本轮已复跑/已通过"——那批证据不是本轮的。
* 若必须在本轮拿到流程级结论，建议最小批次（按性价比）：
  1. `serdes_rx_flow_tb.py --stage all`（含 layout/gds/cdl/calibre/sim 全链，最接近"完整工程流"）；
  2. `design_iterate_tb.py`（迭代改图→二次出图）；
3. ~~`role_split_tb.py`~~ ✅ 已完成（见上表）。
  4. 若时间允许：`adc_sar_flow_tb.py`、`multiuser_serdes_rx_tb.py`。

## 3. 需要你决策的一点

`role_split_tb` 是我唯一能顺带把"spec 条款 `路由#024`（P0-01 关闭口径：gui 与 daemon 不必同机）"补上本轮证据的路径，
但它要求：

* 注册表里存在 `roleprobe` 用户（五 role 分主机：daemon→wsl-gent，command→w1-gent，file→w2-gent…）；
* lab WSL 保活（TB 自己会 `wsl.exe -d … sleep infinity`，但需要 w1/w2 在跑）。

要我把这个 S2 环境按"推荐测试环境"的菜谱配起来（注册 `roleprobe` + 起保活 + 跑 role_split），说一声即可；
我也可以只配置不跑，交给你统一安排门禁时间。
