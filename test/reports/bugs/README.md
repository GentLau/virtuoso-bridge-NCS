# `test/reports/bugs/` —— 缺陷跟踪唯一视图

> 维护者：测试工程师（我）｜最近刷新：2026-10-08
> **这个目录回答两个问题：现在还有哪些 bug 没关（§1 + 逐条卡片）；关掉的是什么理由（[已关闭-近期.md](已关闭-近期.md)）。**

## 0. 三条规矩（动这里之前先看）

1. **当前事实源就是本目录**：未关闭项在 §1（逐条卡片），已关闭记录在
   [已关闭-近期.md](已关闭-近期.md)。历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更，
   仅作存档；两份口径冲突时以本目录为准。
2. **状态只能从这五个里选**：`待设计修` / `待测试侧` / `待归属` / `待决策` / `观察`。
   关闭时**不删卡片**：移到 [已关闭-近期.md](已关闭-近期.md) 并写一句「凭什么关的」（证据路径）。
3. **刷新方式**：改 `test/shared/runners/make_bug_cards.py` 的 `OPEN` / `CLOSED_RECENT` 段，
   然后 `python test/shared/runners/make_bug_cards.py`（幂等；`--check` 只校验不写盘）。

## 1. 未关闭（5 条）

| ID | 层 | 级别 | 归属 | 状态 | 一句话 | 卡片 |
|---|---|---|---|---|---|---|
| **P-121** | spec↔真机一致性（上层 schematic 包）· `place_pin.sig_type` 读回 | P3（文档缺口：按 spec 值域做「写值==读回」断言会误判；调用方需知道映射） | spec 侧（**口径已定**：不改实现，在 `2-schematic.md` 的 `sig_type` 值域处补一句 DB 归一化说明——`power` 读回为 `supply`，读回按 DB 词汇） | 待设计修 | `place_pin(sig_type="power")` 写入成功，但 `read(connectivity).nets[...].sigType` 读回 `"supply"`（其余 9 个取值原样回读）——spec 未写明该 DB 归一化 | [P-121-place-pin-power-sigtype-reads-supply.md](P-121-place-pin-power-sigtype-reads-supply.md) |
| **P-120** | 注册流程（register/flow）· SSH 后端选择与 ssh-config 兼容性 | P3（一致性缺陷：apply 收 `ssh_backend` 但 probe 不用 → 用户按文档选 openssh 也无法绕过 paramiko 的限制；`accept-new` 的 env 要求本身已在 `test/docs/环境与场景.md:110` 写明） | 设计侧（`register/flow.py::_new_runner` 透传 `ssh_backend`/`tool_override`；accept-new 的错误文案可加一句「改 ssh config 为 yes/ask 或换 openssh 后端」） | 待设计修 | 注册 probe **忽略** apply 里的 `ssh_backend`（永远 paramiko）；而 paramiko 又拒绝 `StrictHostKeyChecking=accept-new` → 用户即使选了 openssh 后端，只要 ssh config 是 accept-new 就注册不了 | [P-120-register-probe-ignores-ssh-backend-accept-new.md](P-120-register-probe-ignores-ssh-backend-accept-new.md) |
| **P-119** | 中层/底层 · 日志通道（CDS.log 字节窗口） | P3（观察/口径：用户日志里出现桥产生的空行；半真机 probe 的"文件窗口==delta"契约因此失效） | spec 侧（**口径已定**：不改实现，改 spec —— 把「桥自身 flush 行不计入 delta、可被过滤」写进日志 spec §8） | 待设计修 | 每次经桥的请求都会在 CDS.log 多写一条空 `\o ` 行（桥"交互等价换行"的副作用），不计入返回的 `CDSlog` delta | [P-119-cdslog-bridge-flush-blank-line.md](P-119-cdslog-bridge-flush-blank-line.md) |
| **P-118** | 上层（maestro 包）· `set_job_policy` 的 `job_type=netlisting` 分支 | P2（静默 no-op：调用方以为 netlisting job policy 已生效；与 P-114/C10 同族） | 设计侧（`maestro.set_job_policy` 的 netlisting 分支：`maeGetJobPolicy` 返回 nil 时应创建/或结构化失败，不得静默成功） | 待设计修 | `set_job_policy(job_type="netlisting")` 在未设置过该 policy 的 test 上报 **ok=true 但零效果**（`read_config.job_policy.netlisting` 恒 `null`）——静默 no-op | [P-118-maestro-netlisting-job-policy-silent-noop.md](P-118-maestro-netlisting-job-policy-silent-noop.md) |
| **P-117** | spec↔实现一致性（上层 calibre 包）· `export.items` 枚举 | P3（文档与实现不一致：按 spec 调用必失败；既有 PEX 产物的导出路径不可达） | 设计侧（已裁定：补实现，但本版只做**预留接口**；spec 侧同步一句预留说明） | 待设计修 | spec `12-calibre.md` §4.5 的 `export.items` 列了 `pdb_dir`，实现未提供（`unknown export item: pdb_dir`）；而 §4.4 又写明既有 PEX 产物可由 `export` 读取 | [P-117-calibre-export-pdb-dir-missing.md](P-117-calibre-export-pdb-dir-missing.md) |

> 优先级口径：**P1** = Linux 侧资源/安全或核心指标链路断（P-056、P-053）；
> **P2** = 真实设计流会给出错的/空的结果，且多数**静默**；**P3/观察** = 非阻塞但建议顺手修。

## 2. 本轮/近期已关闭（101 条）

完整列表与关闭依据见 [已关闭-近期.md](已关闭-近期.md)（唯一出口，本 README 不重复）。

## 3. 非缺陷跟踪项（16 项，不建卡）

文档 / 环境 / 审计 / 覆盖度类条目：**不是产品缺陷**，只在 §3 索引（避免与缺陷卡片混淆）。
所有**缺陷**（含早期轮次已上报的 `bug-2026…`）都在上面 §1 的卡片里，或已移入 §2 已关闭记录。

| ID | 事项 | 当前状态 |
|---|---|---|
| P-001 | 覆盖度报告 `doc/测试覆盖报告.md` 与当前 `src/` 布局脱节（缺负责人） | 待定负责人 |
| P-003 | 环境占用（跑测前检查清单已写） | 待固化到脚本 |
| P-004 | `.pytest_cache` 里 14 条 lastfailed 指向已不存在的旧路径（缓存噪声） | 已记录（建议定期清缓存） |
| P-005 | 瞬态红灯（观察中） | 观察 |
| P-006 | 文件纪律审计（Q1 全链路 / Q2 逐 role / Q3 逐 TB 三项未覆盖） | 待补（审计项，非缺陷） |
| P-010 | 文档一致性（§7 需改「已确认发生、待清理」） | 待改文档 |
| P-011 | `/tmp` 口径待定稿（设计内例外 vs 泄露） | 待定稿 |
| P-014 | 现场观察（找不到创建者） | 待代码定位 |
| P-016 | 完成度评估 / 补测归口（非缺陷） | 待处理 |
| P-017 | 归属未定（先定创建者） | 待确认 |
| P-021 | 历史实例启动位置不规范（`$HOME`/工程目录污染；规范已落地，现场清理与 legacy 重写待办） | 环境账，非缺陷 |
| P-023 | wsl-gent 起 20 个真 Virtuoso 超出内存（真机上限 10–12；口径已写环境文档） | 待用户确认替代口径 |
| P-028 | 运行中的 vblog CIW 没有 PDK（已按 S1 专用实例口径处置） | 环境账，已给口径 |
| P-033 | `test/artifacts` 入库口径已定：env / tmp 退索引（179 个运行状态文件，2026-10-08），当前跟踪 70 个（69 evidence + README）；剩 3 个 evidence 文件含明文 token，待脱敏 | 仓库卫生，主要问题已处置 |
| P-036 | lab fake 与 bridge 隧道兼容性（已复测可达，症状未复现） | 观察（降级，不再阻塞） |
| P-040 | 仓库内 `.ps1` 一律 UTF-8 with BOM（约定，已写入首轮报告 §6.1） | 约定，非缺陷 |

## 4. 关联文件

- 历史台账（2026-10-08 停更，仅供考古）：[问题登记.md](../问题登记.md)
- 已关闭记录的修复验证：[round6-修复验证报告.md](../round6-修复验证报告.md)
- 覆盖率证据包：[coverage-pack/](../coverage-pack/)
- 最新一轮过程资产：[round10/](../round10/)
- 两个完整项目的验收清单：[两项目全链-验收清单.md](../两项目全链-验收清单.md)
- 新增卡片模板：[_模板.md](_模板.md)
