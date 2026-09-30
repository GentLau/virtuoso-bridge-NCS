# round9 · log / CDSlog 语义深挖（C 线交付）

> 执行：subagent `/root/log_semantics_r9`｜下发：测试/root，2026-09-29
> 对象：`basic.skill.execute` 的 `CDSlog` 归属 + `log_level`/`log_max_bytes` 语义（spec `底层/6-日志返回设计标准.md`）
> 证据：`test/artifacts/evidence/verify-fix-r9/c06-skill-log-semantics.json`（C06 红钉）；
> `test/artifacts/evidence/round9/skill-log-options-r9.json`（W-1 值级补强，http 7/7）；
> `test/artifacts/evidence/round9/offline-r9-official.log`（离线官方全量）。
> 追加（21:44 干净窗口）：`round9/c06-semantics-r9b.json`（含新 C06-E）、`round9/longline-probe.log`（长行归因）。

## 1. C06 红钉现状（`print` 不 flush / 跨请求串场）

TB：`test/live/packages/skill_log_semantics_e2e_tests.py`（C06-A..D）。最近一次有效跑（stamp 201348）：

| 用例 | 结果 | 实测 |
|---|---|---|
| C06-A `print("MARK")`（不带换行）→ 同一请求 `CDSlog` | **FAIL（红钉）** | `CDSlog == ""`（行缓冲未 flush） |
| C06-B 后续请求不得串场上一条缓冲 | **FAIL（红钉）** | 下一条请求 `CDSlog == '\\o "C06_MARK_C\\n""C06A_201348"\\n'`（串场且带出更早残留） |
| C06-C `printf("MARK\\n")` 回归 | PASS | `CDSlog == '\\o C06C_201348\\n'` |
| C06-D `print("MARK\\n")` 边界 | NOTE（不作判据） | 本轮实测 `in_CDSlog=false`（与 C 的 printf 行为不同，边界待 spec 定） |

**结论**：C06 本体（A）+ 后果（B）稳定复现；C（printf）不回归。修法（卡片已写）：
`ramic_bridge.il` 在 `evalstring` 之后、`lo_end` 抓取之前插 `errset(hiFlushInfo())`；清理 daemon 两版残留 `hiFlush()`。

## 2. W-1（log 选项"只验被接受"）收口情况——由 B 线代跑，证据有效

`skill_log_options_e2e_tests.py` 已被补成值级判据（LOG-04/04b/04d/06），http **7/7 PASS**
（`round9/skill-log-options-r9.json`）。两条**判据构造**教训（供后来者）：

1. `\\w` 前缀**不能**用 `printf("\\w …")` 造——Virtuoso 会给普通输出加 `\\o ` 前缀，落盘成 `\\o \\w …` → 按 §4 归 info；
   正确造法是 SKILL 的 `warn("…")`（落盘 `\\w *WARNING* …`）。
2. `error()` / `errset(error(…))` **不写 CDS.log**（只进 `steps[].detail.errors[]`），
   所以"同一请求 `CDSlog` 非空"这条判据对 error 路径不适用——不要拿它钉 error 行为。

## 3. §5 第三档（error 超限截断）——**函数级已覆盖，仅 E2E 不可达**

W-1 报告曾说"§5 第 3 档无法触发、不得计入覆盖"。经复核，该说法只对 **E2E（经 SKILL 产 `\\e` 行）** 成立；
**daemon `filter_delta()` 的函数级覆盖是完整的**，两份离线文件在 round9 官方跑批中均 PASS：

| 文件 | 覆盖点 |
|---|---|
| `test/offline/unit/test_daemon_log_contract.py::test_truncate_when_even_errors_are_too_long` | 超限 → 降级 → error 仍超限 → `_TRUNCATE_NOTE` + 截断 |
| `test/offline/unit/test_daemon_log_utf8_budget.py`（4 用例 + 预算扫描） | 截断点落多字节字符中间时不产半个字符、不补 U+FFFD、body ≤ max、两说明行、py3/py27 parity |

**申报口径建议**：写"§5 三档在 daemon 函数级有离线判据（列上述用例）；"
"E2E 侧因 SKILL 无法产出 `\\e` 行而不可达——如评审要求 E2E，需 daemon/IL 侧提供测试夹具（例如受控 env 变量注入一行合成 `\\e`）。"
不要把"离线有覆盖"误报成"无覆盖"，也不要把"函数级覆盖"冒充成"E2E 覆盖"。

## 4. 遗留项进展（21:44 干净窗口复跑后更新）

1. **"≥500B 单行在 `CDSlog` 里消失"——已复现并归因（C06 同族，不是独立 bug）**。
   证据 `round9/longline-probe.log`（stamp 214445）：
   - L1 `printf(520×X)` 不带换行 → 同请求 `CDSlog` **空**（`len=0`）；
   - L2 下一条 `printf("\n")` → 长行**串场带出**（`LONGLINE_…` 出现在 L2）；
   - L3 同长行 + 换行 → 同请求 `CDSlog` 542B（正常）。
   ⇒ 与 C06-A/B 同一机制（行缓冲无换行不 flush）；**并入 C06 卡的口径**，不另立卡。
2. **`load` 路径**：已补 **C06-E**（上传 .il → `load` → 断言同请求 `CDSlog` 含标记）并在干净窗口
   **PASS**（`round9/c06-semantics-r9b.json`）；print/printf/load 三类现各有判据。
3. `print+换行` 的 `CDSlog` 归属（C06-D）为 NOTE，**待 spec 定边界**后升级为判据。

## 5. 本轮环境对结论的影响（必须随证据一起引用）

21:3x–21:4x 的 vblog CIW 出现多次退化：`ASSEMBLER-2404 handle 0`、`SKILL execution timed out`、
`ADE Assembler Message 1600` 模态框（`Cannot find an active session named fnxSession25`，出现即死锁需重启）。
期间任何"同一实例连续多套"的结果都可能带 P-086 族污染；C06 红钉证据（201348）取自退化前窗口，可引用；
W-1 的 7/7 为退化前 http 窗口。**两组结论都不依赖退化窗口**。
