# P-117 · spec `12-calibre.md` §4.5 的 `export.items` 列了 `pdb_dir`，实现未提供（`unknown export item: pdb_dir`）；而 §4.4 又写明既有 PEX 产物可由 `export` 读取

| 字段 | 值 |
|---|---|
| 级别 | P3（文档与实现不一致：按 spec 调用必失败；既有 PEX 产物的导出路径不可达） |
| 层 | spec↔实现一致性（上层 calibre 包）· `export.items` 枚举 |
| 归属 | 设计侧（已裁定：补实现，但本版只做**预留接口**；spec 侧同步一句预留说明） |
| 状态 | **待设计修** |
| 位置 | spec `spec/design-concepts/上层/12-calibre.md:231`（items 枚举）与 `:223`（“既有 PEX 产物仍可由 read_results / export 读取”）；实现 `src/pyapi/packages/calibre.py:56-61`（`_EXPORT_ITEMS` 只有 summary/results_db/netlist/log）与 `:248`（其它 item 一律 ValueError） |
| 首报 | 2026-09-30（测试/root：补 `calibre.export` 枚举覆盖时发现 spec 列了未实现的 item） |
| 最近更新 | 2026-10-08 11:45（用户裁定：补实现但仅预留接口；决策见卡尾） |

## 现象

真机（8127，token vb-vblog）：`calibre.export(run_dir=…, items=["pdb_dir"])` → 400 `invalid request for operation: unknown export item: pdb_dir`；对照 `items=["all_small"]` → 200 且展开为 summary/results_db/log（合法枚举可用，说明只有 pdb_dir 缺）。

## 复现

```text
对任一已有 run_dir 调 `calibre.export(items=['pdb_dir'])`；或 `calibre_e2e_tests.py --only EXPORT` 看 EXPORT-04。
```

## 证据

`test/artifacts/evidence/round9/calibre-c07-r11c.txt`（套件 12/12，含 EXPORT-03/04）；枚举差异见源码锚点

## 验收判据（修好即转绿）

① `calibre.export.items` **接受 `pdb_dir`**（请求层不再 400），与 spec §4.5 枚举一致；② 本版不实现真实 pdb 下载 → 预留语义必须**结构化、点名**（不得静默成功）；③ 预留不影响同请求其它 item：`items=["summary","pdb_dir"]` 仍要下到 summary（值级 sha256）且 `ok=true`；④ spec §4.5 补“`pdb_dir` 本版预留”一句，并同步 §4.4 的既有 PEX 产物口径；⑤ TB `EXPORT-04` 按上面的预留语义更新（PEX 恢复后再升级值级落地断言）。

## 下一步 / 责任人

**决策已定（2026-10-08，用户裁定）：补实现但只做预留接口**，设计侧按卡尾「决策」落地；TB 暂按“现状 + 指向本卡”记录（EXPECT 变红即代表实现已落地 → 测试侧按新语义改断言），不阻塞门禁。

## 决策（2026-10-08，用户裁定）

**补实现，但只做「预留接口」**：

1. `calibre.export.items` 接受 `pdb_dir`（请求层不再报 `unknown export item`），与 spec §4.5 的枚举一致；
2. **本版不实现真实 pdb 下载** —— 依据：PEX 本版不提供，`calibre.pex` 即返回
   `{"ok":false,"error":"calibre.pex is not supported in this version","value":{"reason":"pex_unsupported"}}`
   （spec §4.4 / `calibre.py:45,446-449`），不建 run dir、不调远程；
3. 预留语义必须**结构化且点名**（不得静默成功、不得当成“下到了 0 个文件”糊过去）；
4. 预留**不得影响同一请求里的其它 item**：`items=["summary","pdb_dir"]` 必须照常下到 summary
   （本地文件存在、bytes 一致、sha256 与远端一致），整体 `ok=true`；
5. spec 同步：§4.5 补一句「`pdb_dir` 本版预留（无 PEX 产物可导）」；§4.4 的“既有 PEX 产物可由 export 读取”
   改为“恢复 PEX 前只保证 `read_results(kind="pex")`”。

**测试侧收口计划**：`calibre_e2e_tests.py::EXPORT-04` 由“400 拒绝”改为断言上面的预留语义
（请求接受 / 点名 reason / 混选不破坏 summary+sha256 / 零误删）；PEX 真正恢复时再升级为
pdb 目录的值级落地断言（目录存在且文件非空）。
---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
