# 任务 · PVT 多 corner 真机扫描 TB（测试 root 派单）

> 派单：2026-09-29 23:30 ｜ 产出落 `test/reports/round9/pvt-corner-r9.md`（报告）+ 证据 JSON

## 背景

第九轮全面测试的收口清单里，"后仿 / PVT" 是用户点名**要做**的一项：

- 后仿（版图提取网表 vs 原理图网表 DC 对比）本轮已完成：`test/live/flows/s11_postsim_compare.py`
  → verdict=match，max |ΔV| = 8.1e-05（证据 `test/artifacts/evidence/round9/s11-postsim-r9.json`）。
- **PVT（多工艺角扫描）本轮仍无任何 TB 覆盖**：现有 maestro TB 只做 corner 的**配置面**
  （`set_corner`/`setup_corner`/`delete_corner`/变量 scope），从来**没有真正跑过一次多 corner 扫描**；
  `maestro.run` 的返回里有 `corners_done` / `corners_total` 字段（见 `src/pyapi/packages/maestro.py`
  约 2884/2912 行），但没有任何 TB 断言过它们 >1。

## 任务

写一条**真机** TB：`test/live/packages/maestro_pvt_corner_e2e_tests.py`（新文件，作者写 `测试/root`，
最后改动到分钟，依赖如实写；注释头与六步流程按 `test/docs/写TB规范.md`），走 8127 业务面
（`--transport http`，`API=http://127.0.0.1:8127/api/operation`，token 默认 `vb-vblog`），要求：

1. **环境检查**：业务面可达 + `maestro_tb` / `SERDES_TB_LIB` / `tsmcN65` 三库可见（照
   `test/live/packages/maestro_mc_e2e_tests.py` 的 environment 段抄姿势）。
2. **构建**（在 `maestro_tb` 下建**专属** cell，别动共享 setup）：
   - 以 `SERDES_TB_LIB/tb_ctle/schematic` 为源设计建一个 setup；
   - 建 **≥2 个 corner**，每个 corner 绑定**不同的 PDK 模型 section**（TT 与另一个真实存在的 section，
     例如从远端 `/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Models/spectre/toplevel.scs` 里 grep 出
     `section=...` 的真实名字再用；先用 `basic.command.run` 读出来，**不要猜**）；
   - 只挂 1 个便宜的分析（DC 或 AC），避免跑成大仿真。
3. **被测动作**：`virtuoso.maestro.run` 起这次多 corner 扫描（`blocking` 用默认的真机姿势，
   照 MC TB 的等待循环写，超时给足；P-086 窗口命中时最多重试一次并如实记录）。
4. **读回判据（必须值级，不接受"ok 即过"）**：
   - run 状态里 `corners_total >= 2` 且 `corners_done == corners_total`；
   - `maestro.read_results` 每个 corner 都能取到结果（逐 corner 断言非空，列出 corner 名）；
   - 如果两个 section 的数值本来就应该不同，断言两组结果**不全等**（不同 section 名称必须能归因到各自 corner）；
     若实测无法区分，**如实写"不可区分"并说明是环境还是产品语义**，不要硬造判据。
5. **收尾**：只关本 TB 打开的 GUI session；不要删共享库内容（专属 cell 可留）。

## 交付

1. 新 TB 文件（跑绿，`rc=0`）；
2. 证据 JSON：`test/artifacts/evidence/round9/maestro-pvt-corner-r9.json`（含每步期望/实际）；
3. `test/reports/round9/pvt-corner-r9.md`：一段话结论 + 一张"条款/判据/结果/证据"表 + **残留与限制**
   （例如：corner 数上限、是否需要 license、是否受 P-086 窗口影响）；
4. 若发现产品缺陷：**不要改 `src/`**，把现象/复现/期望-实际写进报告，并告诉我（我立卡）。

## 约束

- 真机 TB **必须单流跑**（不要与别的真机 TB 并发，会触发 P-086 `SKILL timeout`）。
- 只写 `test/` 下文件；`src/`、`spec/` 只读。
- 完成后回 3 行内汇报：结论 + 文件 + 遗留问题。
