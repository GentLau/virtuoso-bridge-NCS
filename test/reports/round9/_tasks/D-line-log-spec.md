# D 线任务 · 日志 spec 验收矩阵（测试 root 派单）

> 派单时间：2026-09-29 23:10 ｜ 执行者：subagent ｜ 产出目录：`test/reports/round9/`

## 背景（一句话）

上一轮全面测试漏掉了 C06（桥执行 `print` 的输出不落同一请求 `CDSlog`），根因之一是
**TB 只验 `ok`、没有校验 log 的应有返回值**。本轮要把日志 spec 的每一条验收标准都对到 TB 上，
把"只在函数级离线覆盖 / 根本没覆盖 / 断言过弱"的地方全部指出来。

## 判据源（唯一）

`spec/design-concepts/底层/6-日志返回设计标准.md`：
§1 目标与硬性边界、§3 增量机制（offset 定界、无 marker、无 cursor）、§4 分级（`\e`/`\w`/其它）、
§5 限长与自动降级（三档：全回 / 降级 error-only + 说明行 / 字节截断 + 说明行，UTF-8 半个字符要丢）、
§6 协议（6.1 请求字段与优先级、6.2 回包 STX/NAK + JSON + RS、6.3 内部 metadata frame 的
`STX + path + US(0x1f) + start + US + end + RS` 两帧合并语义）、§7 边界与错误语义、
**§8 八条验收标准（本节是矩阵主干）**。

## 要产出什么

1. `test/reports/round9/log-spec-acceptance-r9.md`：一张表，每行 = 条款编号（如 `§8.1`、`§5-第2档`、
   `§6.3-第二帧`）+ 覆盖 TB 的相对路径 + 层级（**offline 函数级 / semi 真环境 / live 生产面 E2E**）
   + 断言是否**值级**（vs 只判 ok/非空）+ 结论（已覆盖 / 仅函数级 / 缺口）+ 证据文件路径。
2. `test/reports/round9/log-spec-acceptance-r9.json`：机器可读版（同字段 + 复现命令）。
3. **缺口清单**：spec 要求但没有任何 TB 断言的条目，每条给具体补点方案（落哪个 TB、断言什么值、用什么 SKILL 表达式或哪个 daemon 函数触发）。
   真机/semi 的补点只写方案，**不要动 `test/live/**`**（那是我的地盘）。
4. 允许你新增**离线单测**（只在 `test/offline/unit/` 下新文件；注释头按 `test/docs/写TB规范.md` §0，
   作者写 `作者: 测试/root`，最后改动写到分钟，依赖如实写），把离线可测的缺口补上并跑绿。

## 必须逐条给结论的已知薄弱点

- `§8.5` 文件轮转/清空 → `start` 归零：真有 TB 吗？（`hiFlushLogFile`/`fileLength` 之后 size < start 的分支）
- `§6.3` 第二帧（`US` 定界、`start`/`end` 十进制字节偏移、两帧合并为一次 `ipcWriteProcess`、off 不产生第二帧）
- `§8.1`「`off` 在 IL 侧零 flush / 零 fileLength / 零读文件」是否有**静态断言 + 行为**双层证据（找 `test/offline/unit/test_log_no_fetch.py`、`test_log_off.py`）
- `§8.7` 截断尾部不留半个 UTF-8 字符（`test_daemon_log_utf8_budget.py` 覆盖到什么程度）
- `§7` token 不匹配 → NAK `invalid token`、`log=""`、**SKILL 零接触**
- `§7` `CDS.log` 不可读 → `log=""` + `warnings` 固定文本 `CDS.log unavailable: <reason>`；且 `off` **不追加**该 warning
- `§8.4` 降级/截断两行说明**不受 `log_max_bytes` 限制**

## 约束

- 只读 `src/` 与 `spec/`，**不得修改**；只在 `test/` 下写文件。
- 离线跑批：`python test\shared\runners\run_offline_multi.py`，或单独 `python -m pytest test/offline/unit/<file> -q`。
- **不要**并发跑真机 TB（会触发 P-086 `SKILL timeout` 窗口）；你不需要跑真机。
- 完成后回一条 **3 行以内**汇报：结论 + 新增文件 + 关键缺口。
