# 审计 · 第五轮 TB 改动复核（是否"为绿而改"）

> 审计对象：本轮（第五轮）对 `test/` 的全部改动 + 本轮新钉的"有意红"用例。
> 审计口径沿用第三轮：**真缺陷修复 / 收紧（断言变强）/ 口径修正（有依据）/ 可疑**。
> **执行者说明（诚实标注）**：本审计初稿由 root（本轮编排者）执行。原计划派**独立审计员**（不同上下文）复核，
> 收尾时并发位被占满（`spawn_agent` 返回 *agent thread limit reached*）一度无法派出；**后由 r5_live 线派出独立审计员 `r5_auditor`**，
> 其阶段汇报独立复现了 §5-5 的"注册类用例并发假红"（见 P-063），但该审计员在收尾时被中断、**没有留下完整审计报告**。
> 因此本文件的判定仍是"root 自查 + 一名独立审计员的部分复核"，**不构成完整第二双眼睛**；§6 给出 10 分钟可复算清单。
>
> **补充（22:58）**：为补上这一步，本轮又派了一名独立审计员 `audit_r5_independent`（独立上下文、独立任务书）；
> 它在 35 分钟内未产出报告（机器空闲、无 pytest 进程，属其自身停滞），**本条独立复核最终未取得**。
> 因此：**"TB 改动无假绿"这一结论目前仍只有 root 一方证据 + 可复算清单**，送审前请按 §6 让另一位工程师跑一遍（10 分钟）。

## 1. 方法与可复算命令

```powershell
git status --short -- src                      # 必须为空：本轮不改产品代码
git diff -U0 -- test | Select-String '^\+' | Select-String 'skip|xfail|except|pass$|assert True|== True'
git diff -U0 -- test | Select-String '^-'  | Select-String 'assert|_check\('
python -m pytest test/offline/unit test/offline/integration test/offline/scenario -q `
    --junit-xml=test/artifacts/evidence/round5-main/offline-final.xml
```

## 2. 机械扫描结果

| 检查 | 结果 |
|---|---|
| `src/` 是否被改 | **0 个文件**（`git status --short -- src` 为空）——本轮全部改动都在 `test/` 与 `test/reports/` |
| 新增行里的假绿手法（skip/xfail/except/pass/恒真断言） | 命中 3 类，逐条解释后**无一是为绿而加**：① 既有 `daemon_internal_error_path_probe.py` 的 py27 SKIP（第三轮遗留，非本轮）；② `run_all_http.py` 的 `except` 已核实**不吞失败**（`ok = proc.returncode == 0`、`overall_ok &= ok`、rc≠0 即 return 1）；③ 本轮新增的 4 处 `skipUnless`（P-058）——**Windows 上照常执行**，只在 Linux 上 skip 并给出理由 |
| **被删除的断言** | 本轮只删了 2 行 ×2 处，全部来自 P-057 的深嵌套 JSON 口径修正：`assertEqual(status, 400)` + `assertIn("invalid JSON body")`（对 deep 用例）。**替换后断言更强**：新增"5000 层 → 400 或 200 且必须是可解析 JSON 响应壳（含 `error`/`data`）"+"**200000 层 → 必须 400 invalid JSON body**"（两解释器一致） |
| 报告引用证据是否在盘 | 对全部第五轮/round5 报告做路径抽取（正则扫 `round[0-9]`/`evidence` 路径，复算于 22:30）：**引用 66 条，命中 66 条，缺失 0**（逐条清单 `test/artifacts/evidence/round5-audit/evidence-paths.txt`） |
| 离线 junit（最终口径） | **1686 项 / failures=11 / errors=0 / skipped=6**；11 条红**全部是有意钉住的缺陷**：P-055×3 + calibre（P-059/P-061/P-062）×8（`round5-main/offline-final.xml`）。junit 头 `tests=2335` 为 pytest 9.1.1 膨胀属性（独立复核 D5） |

## 3. 逐条判定

| 对象 | 改动性质 | 判定 | 依据 |
|---|---|---|---|
| R1 `test_daemon_log_utf8_budget.py`（新增） | 纯新增契约 | **真缺陷预防（收紧）** | 5 用例 + 0..len 逐点扫描 + py3/py27 parity；负控制：换成 U+FFFD 兜底 → 红、换成不按字节截断 → 红（`round5-offline/utf8-negative-control.txt`） |
| R2 `test_middle_reserved_codes.py`（新增） | 纯新增契约 | **真缺陷预防（收紧）** | 不打桩跑真实 subprocess；负控制：把 rc 124/255 改判 kind → **5 条全红**；正确实现 0 红 |
| R3 `test_api_server_method_not_allowed.py`（新增，3 红） | 新增"按 spec 期望"的红用例 | **真缺陷修复（钉住 P-055）** | 真机实测（8127）与离线复现一致；同规则在控制面已实现 → 不是"设计口径"；红项在缺陷修好后自动转绿（无需改断言） |
| R4 4 条 Windows-only 用例加 `skipUnless` | 平台守卫 | **口径修正（有依据）** | `test_windows_appdata_default` 在 Linux 必然 `NotImplementedError`（pathlib 限制）；另 3 条测的是产品 `if _IS_WINDOWS:` 分支。**Windows 行为不变**（仍执行），Linux 上 skip 有理由 |
| R5 两处 `test_json_parser_limits_return_400` | 断言重组 | **口径修正（且整体更强）** | 见 §2 删除断言行：deep 用例由"必须 400 invalid JSON"改为"结构化不变量 + 200000 层必须 400"；long-int 断言原样保留 |
| L1 `test_e2e_live.py` 补 `key_dir/key` | 测试请求补必填字段 | **口径修正（跟 spec r22）** | 红证据：`e2e-live-red.log`（`ValidationError: role gui is remote: SSH credential ... required`，守卫 `src/register/models.py:213`）；修后 6 passed / 4 skipped，跑两轮均绿 |
| L2 `cov_registration_real.py` 同上 | 测试请求补必填字段 | **口径修正（跟 spec r22）** | 修后 `stage=deployed`、registry 零写入（`round5-main/cov-registration-real.log`） |
| L3 `test_pyapi_interface_contract.py`（新增） | 纯新增契约 | **真缺陷预防（收紧）** | 负控制：源码副本删掉 `log_max_bytes` → 形状检查 **RED（defect detected）**（`round5-main/pyapi-contract-negative-control.txt`） |
| L4 `test_empty_queue_times_out_and_closes_shell` 改为确定性桩预算 | 消除时序脆弱 | **口径修正（不是放松）** | 原用例在负载下会走"写出前预算耗尽"分支（合法但不同路径）；改后仍断言"空队列超时 → 关闭 shell"，且整类 8 passed；红证据保留在 `main-coverage.log` |
| L5 `run_main_coverage.ps1` 的 S11 步骤改 CLI | 修"从未真正执行"的门禁 | **真缺陷修复（门禁）** | 旧参数导致 argparse `rc=2`、flow JSON 从未产出（`main-coverage.log` 汇总行）；修后独立实跑有逐阶段 verdict（`round5-main/s11-flow.log`） |
| 新增 `test_calibre_parsers.py` / `test_calibre_job_state.py`（8 红） | 新增"按真报告/真行为"的红用例 | **真缺陷修复（钉住 P-059/P-061/P-062）** | 样本取自真机 `DRC.rep` / `LVS.rep` 裁剪（`test/shared/fixtures/calibre_*_sample.txt`）；逐条与真机证据 `round5-main/calibre-*.json` 对齐 |

## 4. 关键鉴别力（负控制）复核

| TB | 负控制 | 结果 |
|---|---|---|
| UTF-8 截断（R1） | 换实现为"U+FFFD 兜底" / "不按字节截断" | **RED / RED**（`round5-offline/utf8-negative-control.txt`） |
| 保留码语义（R2） | 把真实 rc=124/255 改判成 timeout/transport | **5/5 RED**，正确实现 0 红（`round5-offline/reserved-code-negative-control.txt`） |
| pyapi 接口形状（L3） | 源码副本删 `log_max_bytes` | **RED（defect detected）**（`round5-main/pyapi-contract-negative-control.txt`） |
| 业务面 405（R3） | 无（红本身即证据；修好后自动绿） | 现状 3 红 / 2 绿（`offline-final.xml`） |
| 前几轮：infra `netlist.import`"假成功" | 产品若退回假成功 → 红 | 已有（第三轮审计 §2），本轮未变 |

## 5. 可疑或未证明项（不放过）

| # | 项 | 现状 | 建议 |
|---|---|---|---|
| 1 | **没有独立第二双眼睛** | 本轮并发位耗尽，独立审计员未能派出（本轮唯一执行者亲审） | 送审前请另一位工程师按 §6 清单复算一次，重点看 R4/R5/L1/L2 这四处"改过既有用例"的地方 |
| 2 | P-057 的 deep 用例仍是**弱断言**（只钉"结构化 400/200 + 无断连"） | 有依据（跨版本差异实测），但产品若想统一行为需加显式深度上限 | 若设计接受"加深度上限"，把 deep 5000 层改回强断言 `400 invalid JSON body`（并写进 spec） |
| 3 | `test_ssh_edges.py` 负载 flake 的稳定性 | **已补 100× 循环：`runs=100 fails=0`（在并发离线全量的负载下）** → `round5-main/l4-stability-100x.log` | 已闭环 |
| 4 | 半真机的 py2.7 **真 SKILL 往返**（不只是协议层）仍未覆盖 | 本轮只到协议/校验/看门狗 5/5 | 需要 CIW 的 stdin 帧通道；列为下一轮候选 |
| 5 | **注册类离线用例并发跑会假红**（P-063） | 2 路并发 `test/offline/unit`：各 **29 failed**（其中 register_flow 15 + reservation 3 是假红）；独占时 11 failed（全是有意红）→ `round5-main/conc-A.xml`/`conc-B.xml` vs `offline-final6.xml`。`test_reservation.py` 的单点打桩**不足** | 统一在注册类用例里把 `local_port_free`/`allocate_local_port` 打桩或指向测试私有区间；**在此之前，离线全量必须"独占端口区间"跑**（报告已注明） |
| 6 | 证据目录里有一个**中止残片** `round5-main/offline-final7.log` | 该跑在启动时检测到机器已有 3 个 pytest（并发），被主动终止；文件是部分输出，**不得作为任何结论依据**（本轮所有引用都用 `offline-final6.xml` / `conc-A/B.xml`） | 建议下一轮清理或改名为 `.aborted` |

## 6. 独立复核清单（10 分钟可完成）

1. `git status --short -- src`（应为空）；
2. `git diff -U0 -- test | Select-String '^\-' | Select-String 'assert'`（应只看到 P-057 的那 4 行，且替换行在文件里更强）；
3. `python -m pytest test/offline/unit/test_api_server_method_not_allowed.py test/offline/unit/test_calibre_parsers.py test/offline/unit/test_calibre_job_state.py -q`（应 **11 红**，与 junit 一致；若有人偷偷改绿 → 立即可疑）；
4. `python -m pytest test/offline/unit/test_daemon_log_utf8_budget.py test/offline/unit/test_middle_reserved_codes.py -q`（应全绿）；
5. 负控制三件套复跑（§4 三条命令见文件头）；
6. Linux：`bash test/artifacts/tmp/r5_linux_client.sh` 的产物应复现"6 红（P-055×3 + P-056×3）、其余全绿"。

## 7. 结论

- 本轮 TB 改动**没有被判定为"为绿而改"**：全部改动要么是纯新增、要么是跟 spec 的口径修正、要么是消除平台/时序脆弱；
  唯一"删除断言"处（P-057）在替换后**整体更强**（新增 200000 层强断言）。
- **已知缺口**：缺少独立审计（§5-1）、P-057 的 deep 弱断言是产品选择项（§5-2）。
- 与第三轮同样的纪律：**破坏性动作的目标必须显式化**——本轮 e2e 引导只允许 pin 专用 `vbe2e`，未再出现自动发现 CIW 的行为（P-046 已闭环）。

## 8. 闭环更新（22:10，r5_live 线补）

* §5-3（`test_ssh_edges` 那个 flake 只加固、未做循环稳定性验证）→ **已闭环**：
  在**并发跑整套离线三层**的负载下，对该用例循环 **100 次：0 失败**（总耗时 259.6s）。
  证据：`test/artifacts/evidence/round5-main/l4-stability-100x.log`。
* §5-1（缺独立第二双眼睛）→ **仍未闭环**：已另起独立审计 subagent（无本轮改动历史）按 §6 复算，
  但它在交付前被中断、**未产出**独立复核文件；送审前仍需另一位工程师按 §6 复算一次。详见 §9。

## 9. 附记（22:15，独立审计实际状态 + 新发现）

* 独立审计 subagent（`r5_auditor`，无本轮改动历史）按 §6 开始复算，但在**交付前被用户中断**，
  因此 `审计-第五轮TB改动复核-独立复核.md` **未产出**——§5-1 的缺口**仍然存在**（送审前仍需他人复算一次）。
  它中断前留下的阶段汇报里有一条**真实发现**，已由 r5_live 复核并登记为 **P-063**：
  注册类离线用例（`test_reservation.py` / `test_register_flow.py`）在**并发跑测**时会因
  65081–65130 端口区间被占而假红；对照实验见 §10。
* §10 对照实验（同一命令、同一工作树，只差机器负载）：
  * 并发负载（同机还有其它整跑）：**14 failed** = 11 条有意红 + `test_reservation.py` 3 条假红 → `test/artifacts/evidence/round5-main/unit-order-check.log`；
  * 机器空闲：**11 failed** = 只有有意红 → `test/artifacts/evidence/round5-main/unit-order-check2.log`。
  结论：本轮"11 红基线"**必须在独占端口区间时复算**，否则会被 P-063 污染。
* P-063 处置（22:2x）：① 端口占满条件下**单跑** `test_reservation.py` 修复前 1 failed → 加固 `setUp`（固定 `local_port_free=True`）后 **13/13 passed**（`p063-portpressure-repro.log` / `p063-fix-green.log`）；
  ② **残余**：同样占满端口时"整目录整跑"仍见过一次 3 条 reservation 红（`p063-fix-fullunit-under-pressure.log`，14 failed），随后同命令复跑回到 11 failed —— **间歇、未根因化**，下一轮用 `pytest -l --tb=long` 抓 `state.errors` 继续定位。登记为 P-063"部分闭环"。

## 10. 独立复核落地（23:10，audit_r5_independent 线）

* **§5-1 闭环**：独立复核已产出 `test/reports/审计-第五轮TB改动复核-独立复核.md`（复核人非本轮 TB 改动作者）：
  自查稿 §6 清单 6 项逐条复算 + 关键数字独立解析 + **一次真 Linux（3.9.25 / 3.14.6）全量复跑**。
* **判定：通过** —— 无"为绿而改"；11 条红逐条为有意钉；`src/` 零改动复算为空。
* 独立复核另提 **D1–D6**，其中两条已就地落修：
  * **D5（数字口径，重要）**：pytest 9.1.1 的 junit `tests` 属性膨胀（`5 → 223`、`1665 → 2316`、`1686 → 2335`），
    离线三层真值 = **1686 项**；已修订本文件 §2、`第五轮测试报告.md` §1/§11、`round5-spec覆盖矩阵.md` 口径行、`round5-离线与覆盖率.md` §1。
  * **D2**：Linux 矩阵"6 红"是 calibre TB 加入前的快照 —— 当前工作树复跑为 **14 红**（= 11 同源 + P-056×3），
    证据 `test/artifacts/evidence/round5-audit/linux-py39-audit.{xml,log}` / `linux-py314-audit.log`。
* **D4（P-063 残余点名）**：端口压力下 `test/offline/unit/test_register_flow.py::TestFlowApply::test_deploy_failure_stops_flow`
  报 `'deploy boom' not found in 'no free local tunnel port found'`（缺少 `allocate_local_port` 打桩）；
  同压力下整目录（1641 项）已是 11 红（`round5-main/p063-fullunit-pressure-after-p064.xml`），**只差这一处**。
