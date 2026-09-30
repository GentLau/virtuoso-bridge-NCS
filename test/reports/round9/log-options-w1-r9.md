# round9 · W-1 收口：log `warn` 过滤 / `log_max_bytes` 降级 / 领域操作 off 空日志

> 执行：subagent `/root/opparam_r9`｜2026-09-29 20:52｜对象 TB：`test/live/packages/skill_log_options_e2e_tests.py`
> 依据：`weak-assertions.md` W-1（该 TB 的 LOG-04/05/06 只断言 ok）；spec `底层/6-日志返回设计标准.md` §4/§5
> 证据：`test/artifacts/evidence/round9/skill-log-options-r9.json`（**http 传输，7/7 PASS**）

## 1. 改了什么

| 用例 | 改前 | 改后（判据强度） |
|---|---|---|
| LOG-04 | `log_level=warn` → 只 `assert ok` | **按 §4 分级断言**：`warn("MARKER")` 产出的 warning 行必须保留、`printf` 的 info 行必须剔除。实测 `CDSlog == '\\w *WARNING* VB_W1_WARN'`（info 标记不在其中） |
| LOG-04b（新） | — | **§5 降级档**：info 洪泛（40×~45B）配 `log_max_bytes=200` → 断言 `CDSlog` 含 `auto-degraded` 且不含任何 info 标记。实测 `'\n[log auto-degraded: error-only due to log_max_bytes]'` |
| LOG-04d（新） | — | **§5 降级档（warn 入口）**：`log_level=warn` + 40 条 `warn()` 洪泛配 `log_max_bytes=300` → 同样断言降级说明出现、warn 行不再返回 |
| LOG-06 | 领域操作 off → `assert ok` + `assert steps` | 补 **`CDSlog == ""`** 断言；并修掉一处 **过期 C1 消费方**：成功响应默认省略 `steps`，故请求显式加 `step_details=True`（原断言在当前契约下必然失败） |

## 2. 反复确认过的实现事实（可复现）

1. **`\w` 行不能用 `printf` 造**：`printf("\\w …")` 在 CDS.log 里落成 `\o \w …`（Virtuoso 给普通输出加 `\o ` 前缀）→ 会被 §4 归为 **info**。正确造法是 SKILL 的 **`warn("…")`**，落盘为 `\w *WARNING* …`。
2. **`error()` / `errset(error(...))` 不进 CDS.log**：单发与滞后一发都为 `CDSlog=""`，错误只出现在 `steps[…].detail.errors[]`（实测 `*Error* VB_HARD_ERR_…`）。

## 3. 残留（如实列出，不声称覆盖）

**§5 第 3 档无法触发**：`[log truncated: increment not fully returned due to log_max_bytes]` 要求"降级后 error 增量仍超限"，
而按第 2 条事实，SKILL 侧**产不出 `\e` 前缀的 CDS.log 行** → 本 TB 无法构造该场景。
建议（二选一，供上层/设计定）：

* 在 **daemon/IL 侧**提供一个可控夹具（例如测试专用环境变量让 IL 写一行 `\e` 合成行），TB 再断言截断说明；或
* 把"截断分支"降为**离线/单元级**判据：直接对日志过滤/截断函数注入含 `\e` 的文本，断言两行说明与字节截断规则（§5 已给精确字符串）。

在补上之前，**不得**把"§5 第 3 档"计入已覆盖。

## 4. 对台账的影响

- `weak-assertions.md` 的 **W-1 视为关闭**（LOG-04/04b/04d/06 已具值级判据；见 §1）。
- 未产生新的产品 bug 卡：本次三条断言全部**通过**，说明 `warn` 过滤与 `log_max_bytes` 降级在真机上**行为正确**；
  唯一新发现是 §3 的**测试侧可达性限制**（不是产品缺陷）。
