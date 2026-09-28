# P-102 · `calibre.pex` 第三阶段 argv 非法（`-fmt spice`）：stage1/stage2 成功后 stage3 必被 Calibre 拒绝 → PEX 整体不可用

| 字段 | 值 |
|---|---|
| 级别 | P2（PEX 作为交付能力不可用；spec 已把它标成「禁止交付」，本条把「为什么」钉到具体 argv 与日志） |
| 层 | 上层（calibre 包）· xRC 第三阶段 |
| 归属 | 设计侧（calibre 包 `_argv_for` 的 pex 分支；roadmap P0-1 要求改官方 batch） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/calibre.py:1007-1013`（pex 三阶段 argv：stage3 = `[binary, "-xrc", "-fmt", request.fmt, deck_path]`）；Calibre 用法块（`pex.stage3.log:188-215`）只接受 `-fmt { -c | -r | -rc | … | -simple | -netmodel }`，`spice`/`simple` **不带前导 `-`** 都不匹配。 |
| 首报 | 2026-09-29（第八轮 calibre 零调用 op 补测，root 直接定位） |
| 最近更新 | 2026-09-29（新立） |

## 现象

真机（vblog）实测 2026-09-29 00:05（**用 PDK 的 rcx deck** + LVS 产出的 svdb，其余参数按 spec 12-calibre.md:187）：
- stage1 `calibre -xrc -phdb …` → `--- CALIBRE xRC::PHDB GENERATOR COMPLETED`（成功）；
- stage2 `calibre -xrc -pdb -rc …` → 正常结束；
- stage3 `calibre -xrc -fmt spice …` → 打 usage（`pex.stage3.log:93` 是命令回显，`:188+` 是用法），`pex.log` 末尾 `stage3_failed`，桥返回 `pex did not complete: failed input`。
⇒ 三阶段里前两阶段产物（phdb/pdb）都正常，**只有 fmt 阶段的命令形态错**。

## 复现

```text
`PYTHONPATH=src python test/artifacts/tmp/pex_rcx_experiment.py`（一次性实验，参数：deck=`/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/Calibre/rcx/calibre.rcx`、`lvs_run_dir=<含 svdb 的 LVS run>`、`fmt=spice`）
```

## 证据

run_dir `/home/Gent/project/vblog/calibre-e2e/pex-rcx-1790611157804/`：`pex.stage1.log` 尾部 COMPLETED、`pex.stage2.log`、`pex.stage3.log`（命令回显 + usage）、`pex.log` 的 `stage3_failed`；TB 侧红钉：`test/live/packages/calibre_export_pex_e2e_tests.py` 的 PEX-01。

## 验收判据（修好即转绿）

① 按 `spec/research/calibre/00-下一步开发方向.md` P0-1 改成官方链路（有 set 走 `-gui -pex -runset … -batch`，与 GUI 基线 `.pex.netlist` 逐字节比对）；或 ② 保留 deck 模式但 stage3 用 Calibre 接受的 flag 形态并断言 `.pex.netlist` 存在；③ PEX-01 转绿（或 spec 明确把 deck 模式从接口里删掉）。

## 下一步 / 责任人

设计侧选 ①/②；测试侧按结论改 `calibre_export_pex_e2e_tests.py` 的 PEX 断言（现在是精确红钉）。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
