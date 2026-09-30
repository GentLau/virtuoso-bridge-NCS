# round9 · 缺陷台账完整性核对（B 线复核）

> 执行：subagent `/root/opparam_r9`｜2026-09-29 21:12｜只读核对（未改台账）
> 对象：`test/shared/runners/make_bug_cards.py`（生成器）、`test/reports/bugs/`（卡片）、`test/reports/问题登记.md`（台账）

## 0. 复审时间：2026-09-29 22:48（root 已修掉 L3/L4/L5；新增 C10 与 L7）

**当前未关闭卡 = 6 张**：`C06`、`C07`、`C09`、**`C10`**、`P-086`、`P-106`（`make_bug_cards.py --check`：计划 9 / 缺失 0 / 过期 0）。
本轮新立四张：`P-106`（calibre blocking 假失败，§1.1）、`C09`（maestro write_history rename 链，§1.2）、
**`C10`（`place_wire` 的 `x_spacing`/`y_spacing` 静默无效——由 B 线嵌套键审计发现、root 真机证实：DB 读回 `("path" (nil) (nil) (0.05))`，width 落库而两个 spacing 读回 nil）**、以及 `C07`（见下）。

## 1. 生成器 ↔ 卡片：一致 ✅

- `make_bug_cards.py` 的 OPEN 列表 = **5 条**：`C06`、`C07`、`C09`、`P-086`、`P-106`；
- 磁盘上 `test/reports/bugs/` 恰有对应的 5 张开放卡（+`_模板.md`/`README.md`/`已关闭-近期.md`）；
- `make_bug_cards.py --check`：**计划文件 6 / 缺失 0 / 过期 0 / 应清理 0** ✅。

### 1.1 `P-106`（本轮新卡，根因已定位）

标题即根因：`_status_snapshot` 用 **`pgrep -f <run_dir>`** 判活，而 official-batch 的 calibre 命令行**只含 runset 路径、不含 run_dir** → 恒无匹配 → 首个 poll 即 `process_gone_without_report`（P-094 分类被"输入"带偏）。两次复现（门禁 21:11 + 探针 21:26）且远端日志都写有 `exit code 0`。**状态：待设计修**。
我这边的独立分诊与它一致：`test/reports/round9/gate-r9-live-triage.md §5.1`。

### 1.2 `C09`（本轮新卡）

`maestro.write_history` 连续 rename（A→B 再 B→A）第二跳报 `ASSEMBLER-2404 Cannot find a setup database entry for handle N`；隔离复现 + 门禁 `HISTORY-01` 3 次稳定红；`delete` 对照正常 → 问题在 rename 链的 SDB handle 生命周期。**状态：待设计修**。

## 2. C07 的红钉状态：正确 ✅（可直接用于收口）

- `test/offline/unit/test_calibre_lvs_source_contract.py` 存在（2135 B），内含 **2 条 `strict=True` 的 xfail**；
- 现跑 `pytest -q` → `xx`（2 条预期失败，锁住"实现未 fold"的事实）；
- 满足"红钉挂卡"要求：设计侧一旦拍板（fold 实现 / 回退 spec），XPASS 会转红提醒删标记。

## 3. 台账不一致（建议一次性修）

| # | 位置 | 问题 | 状态 |
|---|---|---|---|
| L1 | `round9-测试报告.md` §5 | 写"**未关闭 2**：P-086、C06" | ⏳ 待改：应为 **5**（C06、C07、C09、P-086、P-106） |
| L2 | `round9-测试报告.md` §3 | 新发现只列了 C06 | ⏳ 待改：补 **C07 / C09 / P-106** |
| L3 | `问题登记.md` C07 缺行 | 已补 | ✅ root 已修（全文有 C07 行） |
| L4 | `问题登记.md` P-086 链接错 slug | 已改为 `bugs/P-086-empty-response-window-after-long-skill.md` | ✅ root 已修（22:20 复核：目标文件存在） |
| L5 | 25 条断链 | 已清理：22:20 复核 **bug 链接 6 条 / 断链 0** | ✅ root 已修 |
| L6 | `问题登记.md` **没有 C09 行** | ✅ root 已补（22:48 复核 C09=1） |
| L7 | `问题登记.md` **没有 C10 行** | ✅ **已补（23:07，B 线直接写入）**：按既有 6 列表格格式新增最新一行（ID/类别/问题/证据/影响/状态），链接指向 `bugs/C10-place-wire-spacing-lazy-params.md`；复核：六张未关闭卡 **C06/C07/C09/C10/P-106/P-086 全部有登记行**、bug 链接 **8 条 / 断链 0**、`make_bug_cards.py --check` **9/0/0** |

> 断链清单（25 条）：C1、C2、C4、P-078、P-079、P-080、P-081、P-082、P-083、P-084、P-085、P-086、P-087、P-088、P-089、
> P-090、P-091、P-092、P-093、P-094、P-095、P-096、P-097、P-098、P-099。
> 复现命令见本目录 `spec-matrix-r9-b-review.md` 同级的这段脚本思路，或直接用：
> `python - <<'PY'` 解析 `问题登记.md` 中 `(bugs/*.md)` 链接并核对存在性 `PY`。

## 4. 结论

- **只有 3 张开放卡，且有 2 张（C06/C07）各自挂着可复跑的红钉**——台账与红钉的机械状态是健康的；
- 需要人动笔的是 **L1–L5 五处**（都在主报告与 `问题登记.md`，属"文档一致性"，不影响代码/测试结论）；
- 建议收口时以 `make_bug_cards.py --check` + 本文件当作"台账已核"的证据。
