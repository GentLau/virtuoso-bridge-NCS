# round9 任务书 C：log / CDSlog 语义深挖与 TB 补强（可写 TB）

> 执行者：subagent（`/root/log_semantics_r9`）｜下发：测试/root，2026-09-29
> 产出：新增/扩写的 TB + `test/reports/round9/log-semantics-r9.md`

## 背景（用户直接指出的上轮漏洞）
上一轮**没有校验 log 的应有返回值**——C06（`print` 输出不 flush、`CDSlog` 归属错）因此漏掉。
测试/root 已先落一条红钉：`test/live/packages/skill_log_semantics_e2e_tests.py`
（C06-A `print` 不带换行必须落同请求 `CDSlog`；C06-B 不得串到后续请求；C06-C printf 回归；C06-D 边界 NOTE）。
当前实测：**A 空 / B 串场**（证据 `test/artifacts/evidence/verify-fix-r9/c06-skill-log-semantics.json`）。

## 任务
**扩写这条 TB 或新增一条 TB**，把 log/CDSlog 的"应有返回值"系统化钉住（可写测试代码）：
1. **级别语义**：`log_level=off` → `CDSlog` 必须为空；`all` → 含标记；`warn` → 不含 info 级 `printf` 文本
   （若实现如此；否则记录实际并注明判据来源）——与 `test/live/packages/skill_log_options_e2e_tests.py` 不重复但可加强断言强度；
2. **长度上限**：`log_max_bytes` 是否真的截断？上轮观察：**超长单行（≥500B）在 `CDSlog` 里直接消失**——
   复现并判定这是 bug 还是边界（若是 bug → 立卡 C07 + 红钉；若是边界 → 让 spec 写明，TB 改 NOTE）；
3. **增量/轮转**：`test/semi/transport/log_matrix_real_tb.py` 覆盖了 off/分级/增量/轮转——核对它断言的是
   **值**还是只断言长度/ok；把"值"断言补强（同 token 连续两发，第二发只应含新增内容）；
4. **`print` vs `printf` vs `load`**：三类输出的 flush/归属（C06 家族），每类至少一条断言；
5. 发现新 bug：立卡到 `test/shared/runners/make_bug_cards.py`（OPEN 段）并跑
   `python test/shared/runners/make_bug_cards.py` 生成卡片；**不要**动 `src/`。

## 硬约束 / 环境
- 真机入口：`--transport http --token vb-vblog`（业务面 127.0.0.1:8127，标准形态 supervisor 托管）；
- 允许跑真机（这是允许写 TB 的车道）；每次改 TB 要更新注释头 **作者=测试/root** + 最后改动到分钟；
- 一条 TB 只动一个变量；判据强度不得低于期望/实际/判定；
- 若命中 P-086 窗口（`SKILL execution timed out` / `Empty response`）：**如实记录**，重试一次即可，不要"重试到绿"。

## 交付
- 新增/扩写的 TB（`test/live/packages/` 或 `test/semi/` 内）+ 运行证据（JSON/log 落 `test/artifacts/evidence/`
  或 `test/artifacts/evidence/verify-fix-r9/`）；
- `test/reports/round9/log-semantics-r9.md`：① 各用例判据与结果；② 新发现的 bug（卡号）；③ 仍不确定的边界。
