# REVIEW-B · 第八轮遗漏审计（独立评审）

> 评审方：`/root/verilog_params/red_team`（独立子代理）｜ 快照：`HEAD=e3e810d` + 未提交工作区
> 方法：重算 op×param/原子矩阵 → 追查 46 GAP / 29 NO-OP 的落地状态（TB+证据）；AST 扫全树吞异常；对照 spec 范围文档与 `test/live/flows/README.md` 场景表。
> 分级：**必须补 3 / 建议补 4 / 可接受（已声明）7**

## A. 必须补（阻断"覆盖完成"结论）

1. **calibre.pex 当前未覆盖、且未立卡**：`evidence/round8/calibre-export-pex.json`（2026-09-29 00:00:21 最近一次）EXP-00/01/02 = PASS，**PEX-01 = FAIL（"pex did not complete: failed input"）**。报告 §G12 写"结果以实际 rc 为准"——当前事实就是未绿，必须二选一：(a) 修 TB 前置（svdb/输入三件套）后复跑转绿；(b) 立卡"PEX 不可用/未覆盖（阻塞）"并在报告显式记。另：23:43 矩阵快照把 calibre.pex 的 22 条参数全记 NO-OP-TB（同一时刻 `op-coverage.json` 已关联该 TB）→ 需重建矩阵。**（二轮更新：已立 P-102 并重建矩阵，见 §E。）**
2. **maestro 证据链不完整**：23/23 的日志只在 `test/artifacts/tmp/maestro_run9.log`（tmp 会被清理，且不在报告引用的证据路径）；22:06 的最近一次复跑是 `Empty response from daemon` 崩溃（`maestro-rerun3.err.log`）。要么把 21:28 的 23/23 归档进 `evidence/round8/`，要么按"被 P-086 阻塞"如实记（顶层报告口径）。
3. **P-101 无红灯（防误读）**：`test/live/packages/verilog_import_params_e2e_tests.py` 的 IMP-07 在"`overwrite=False` 返回成功且 mtime 不变"时 **PASS**（只 NOTE + mtime 断言）→ 该缺陷不会被 TB 抓住。卡片已注"待 spec 定口径"，但报告不能把它算作"P-101 已被 TB 覆盖"；定口径后必须改强断言（成功须带 skipped/existing 标记，或结构化拒绝）。

## B. 建议补

4. **46 条 GAP 构成未拆**：实测 46 = **34×`timeout`**（仅统一合同"非法值被拒"79/79 覆盖，不含逐 op 成功路径）+ calibre.drc 7（cdl/fmt/hcell_file/lvs_run_dir/runset/spice_file/xcell_file）+ calibre.lvs 4（fmt/ground/lvs_run_dir/power；power/ground=P-092 死参数）+ `layout.read.depth` 1（P-085 红钉）。报告 §0 说"calibre 参数面只剩 drc.runset 一条真缺口"，与矩阵 7 条 drc 不一致 → 需要逐行口径（kind 不适用 / 死参数 / 真缺口 / 被缺陷阻塞）。
5. **自查表 stale 数字**（见 REVIEW-C N8）会造成审阅误读 → 同步。
6. **"明确不做"清单核对**（`spec/design-concepts/总览/add-本版范围与明确不支持.md`，13 项）：抽验已有覆盖：无 token → `invalid token`（多离线+live ✓）；路径非沙箱语义（路径专项 ✓）；`request_id`（矩阵 总览#238 有离线用例 ✓）；**未找到 TB 的**：#4（`profile`/`VB_*`/`.env` 迁移入口不存在）、#13（顶层任务等待池）、#5（非对称签名/HMAC 拒绝）。建议补低成本离线契约（旧入口 import 失败 / 请求模型不含相关字段），或在矩阵逐条登记"明确不做 → na+理由"。
7. **后仿/PVT 口径**：`evidence/round8/postsim-evidence.json`（15:05）显示"提取版图网表（**无寄生**）前/后对照 verdict=match（max ΔV=8.1e-5），带寄生 PEX 被 P-034/P-098 家族阻塞"。报告 §G2 写"本轮只做前仿"，与该证据不一致 → 应写"无寄生后仿对照已做；带寄生未通；PVT 未做"。

## C. 吞异常扫描（P-086 假绿风险）

- AST 全扫 `test/live` + `test/semi`：**42 个** `except: pass / continue / 裸 except 不 raise` 处理器，全清单见 `test/artifacts/tmp/r8_swallow_scan.txt`。
- 抽验：`cellview_e2e_tests.py:151/155`（`_reset` 的 lib.delete 幂等保护，断言在 try 外）、`maestro_e2e_tests.py:296/309/380/393/447/897`（清理/幂等保护，断言在 try 外）→ **未发现已证实的假绿**。
- 其余 30+ 处建议红队按 brief 抽样，重点：`maestro_e2e_tests.py:653/697`、`registration_*.py`（探测轮询）、`test_business_remote_live.py:142`、`ssh_backend_semi_tb.py:280-296`。
- 结论：P-086 空响应窗口**暂无已证实的假绿**；该疑虑需按上述清单抽查后才能关闭。

## D. 已声明/可接受的缺口（与报告一致）

蒙卡 P-070（待产品口径）、PVT、>2 跳（≥2 跳为用户既定"代理通过"口径）、100 台真实机（fake fleet 替代）、GUI 点击级、Linux 客户端跑 11 套包、`layout.read depth>0`（P-085 红钉）、host-key 轮换 TB（G9，设计侧未落地）。

> 注：G6 表述要区分两层——"Linux 客户端 base 五接口 + 文件族 6/6 已跑"（本轮新增）与"11 套包/复杂 flows 未在 Linux 客户端跑"。

## E. 二轮复审更新（2026-09-29 00:1x–00:3x）

- **B-#1 calibre.pex → 已处置**：立卡 **P-102**（stage3 `-fmt spice` argv 非法，含 stage1/2/3 日志与 `pex.log` 的 `stage3_failed`），矩阵 00:06 重建后 **NO-OP-TB=0**，报告 G12 按"spec 已标禁止交付 + 已钉死"记录，不再冒充覆盖。**残留**：`PEX-01` 仍红（预期红钉），设计修好后转绿。
- **B-#3 P-101 → TB 已改强断言**（TB 0:09:14，证据 0:09:48 复跑）：ok 分支要求 `skipped/existing/warnings` 标记。**留意点**：若 op 返回非 ok（例如 P-090 的 `sha256 mismatch`），走 else 分支也 PASS——属"待 spec 口径"的过渡形态，审阅别把它当"P-101 已验证通过"。
- **B-#4 GAP 构成 → 已拆解**：报告 §3 现写 59 = 25 真缺口（pex 12 / kind 不适用 11 / export.job_id 1 / layout.depth 1）+ 超时等伪参数；与我的重算（34 timeout + 25 其他）一致。
- **B-#6 "明确不做" → 已登记**：§7 G16 按 na 登记 3 项（旧入口/pending 等待池/HMAC）；建议的低成本离线契约仍未写（报告已声明为流程残留）。
- **B-#7 后仿 → 已更正**：§7 G2 = 无寄生后仿对照 match（max ΔV=8.1e-5）/ 带寄生未通 / PVT 未做。
- **仍未做（与报告 §10 自述一致）**：brief #1 的 ≥40 条全量抽查（本评审只完成 15 项语义 + 55 项机器核验）；`add-本版范围` 13 项缺硬证据契约。
