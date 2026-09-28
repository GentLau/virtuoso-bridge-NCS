# 审计 · 第五轮 TB 改动复核 —— 独立复核（第二双眼睛）

> 复核人：`r5_semi/audit_r5_independent`（独立线执行，非本轮 TB 改动作者）
> 时间：2026-09-23 22:29 – 23:10 ｜ 工作树：**含 P-064 修复**（`test/conftest.py` 改为每会话私有 temp 根）
> 复核对象：`test/reports/审计-第五轮TB改动复核.md`（root 自查稿）、`test/reports/round5-TB改动清单.md`
> 方法：按自查稿 §6「10 分钟可复算清单」逐条复算 + 独立解析全部关键证据 + 抽检新钉 TB 鉴别力 + **一次真 Linux 全量复跑**
>
> **结论先行**：自查稿核心判定 **成立**——本轮 TB 改动**没有"为绿而改"**，`src/` 零改动，11 条红全部是有意钉住的产品缺陷。
> 但独立复核发现 **5 处需要修正的记述/口径（D1–D5）**，其中 **D5 影响所有对外数字**（"2335 用例"是 pytest 9.1.1 写出的膨胀属性，真值 1686）。

## 1. §6 清单逐条复算

| # | 清单项 | 我跑的命令 | 实测结果 | 与自查稿一致？ |
|---|---|---|---|---|
| 1 | `src/` 零改动 | `git status --short -- src` | **空**（另：`git diff --stat -- src` 也为空） | ✅ |
| 2 | 被删除的断言行 | `git diff -U0 -- test` + 过滤删除的 `assert` | **5 行 / 3 处** = P-057 两处（4 行）+ `test/live/e2e/test_e2e_live.py` 1 行 | ⚠️ **自查稿只记了 4 行** → D1 |
| 3 | 11 红钉复跑 | `python -m pytest test/offline/unit/test_api_server_method_not_allowed.py test/offline/unit/test_calibre_parsers.py test/offline/unit/test_calibre_job_state.py -q` | **11 failed / 0 error**，逐条与 junit 11 条**完全相同**（P-055×3 + P-059/P-062×6 + P-061×2） | ✅ |
| 4 | 两个新契约全绿 | `python -m pytest test/offline/unit/test_daemon_log_utf8_budget.py test/offline/unit/test_middle_reserved_codes.py -q` | **10 passed**（5 + 5） | ✅ |
| 5 | 负控制三件套 | 见 §2 | pyapi 契约**文件内自带**、可直接复跑 ✅；UTF-8 / 保留码**只有产物文件、仓库里没有可复跑入口** | ⚠️ D3 |
| 6 | Linux 全量复跑 | 重建 tar → `wsl-gent` → `bash r5_linux_client.sh`（py3.9.25 + py3.14.6） | **tests=1686 / 14 failed / 0 error / 18 skipped**，两解释器**逐条同红**；0 collection error | ❌ **自查稿写"6 红"** → D2 |

## 2. 负控制鉴别力（逐件复核）

| TB | 负控制设计 | 我能否复跑 | 我的判定 |
|---|---|---|---|
| `test_pyapi_interface_contract.py`（L3） | **文件内自带**：`test_near_miss_signature_is_rejected_by_the_shape_check`（少 `log_max_bytes` / 默认值漂移）+ ABC 不可实例化 | ✅ 直接 `pytest` 即跑（本轮 5 passed） | **有鉴别力**（正例 + 反例都在用例里，不依赖外部脚本） |
| `test_daemon_log_utf8_budget.py`（R1） | 变体实验（U+FFFD 兜底 / 不按字节截断 → RED） | ❌ 只留下 `round5-offline/utf8-negative-control.txt`，**harness 未入库** | 证据记录了结论，**复现性不足** → D3 |
| `test_middle_reserved_codes.py`（R2） | 把 rc=124/255 改判 timeout/transport → 5 条 RED | ❌ 同上（`round5-offline/reserved-code-negative-control.txt`） | 同上 → D3 |

> 说明：R1/R2 的**正向**用例我复跑全绿（§1-第 4 项），且断言写法本身可读出鉴别力（逐字节前缀 + 字符边界 + `kind` 原样）；
> 但"换个实现就会红"这件事目前**只能读旧产物**，送审方若要求现场复算会缺脚本。

## 3. Linux 独立复跑（我新增的证据）

| 项 | 值 |
|---|---|
| 方法 | 本地打 `src/ + test/`（去掉 `test/artifacts`）tar → 上传 `wsl-gent` → `bash r5_linux_client.sh` |
| 客户端 | AlmaLinux / kernel 6.6.114.1-microsoft-standard-WSL2 |
| 解释器 | `/usr/bin/python3.9` = 3.9.25（pytest 8.4.2）；`~/vb-ncs/.venv/bin/python` = 3.14.6（pytest 9.1.1） |
| 结果（py3.9） | **1686 tests / 14 failed / 0 error / 18 skipped**（junit 属性与 `<testcase>` 数一致，pytest 8.4.2 无膨胀问题） |
| 结果（py3.14） | **同 14 条红**，逐条一致 |
| 红的是哪些 | P-055×3 + **calibre×8（P-059/P-062×6 + P-061×2）** + P-056×3（POSIX 强杀 `NameError`） |
| 证据 | `test/artifacts/evidence/round5-audit/linux-py39-audit.xml`、`linux-py39-audit.log`、`linux-py314-audit.log` |

**与报告口径的差异（D2）**：`round5-Linux客户端矩阵.md` 写"**6 红**（P-055×3 + P-056×3）"——那是 **calibre 三条 TB 加入之前**的快照。
按当前工作树复跑应为 **14 红**（= Windows 侧 11 条同源红 + Linux 专有 P-056×3）。这不是产品回归，是**文档停更**：报告需要改口径或注明快照时点。

## 4. 独立发现 D1–D6

| # | 严重度 | 事实 | 证据 | 建议 |
|---|---|---|---|---|
| **D1** | 低（文档） | 自查稿 §2 声称"本轮只删了 2 行 ×2 处（P-057）"；实际还有第 3 处：`test/live/e2e/test_e2e_live.py` 把 `assertIsNotNone(current, "no running bridge daemon to bootstrap from")` 换成 `skipTest("需要专用引导 CIW … P-046")` | 删除行清单（§1-2）；替换后行为 `6 passed / 4 skipped`（`e2e-live-green2.log`） | 评估：**可接受**（P-046 明令禁止自动挑 CIW，避免 `RBStop()` 打挂他人实例；有 pin 时用例照跑且绿）。但**必须把这一处写进"删除断言"清单**，否则"只删了 4 行"的口径不成立 |
| **D2** | 中（文档/数字） | `round5-Linux客户端矩阵.md` 的"6 红"已过期；当前工作树 Linux = **14 红** | §3 的两份日志/XML | 把矩阵改成"14 红（= 11 同源 + P-056×3）"，或明确标注"6 红为 21:35 快照，不含其后新增的 calibre 钉" |
| **D3** | 低（可复现性） | R1/R2 的负控制 harness 未入库，仓库只剩输出文本 | `round5-offline/*-negative-control.txt` | 把变体实现固化成 runner（如 `test/shared/runners/negative_controls.py`），让"换个实现就红"可现场复算 |
| **D4** | 中（测试侧·新发现） | **端口压力下仍有一条残余假红**：`test/offline/unit/test_register_flow.py::TestFlowApply::test_deploy_failure_stops_flow` 报 `'deploy boom' not found in 'no free local tunnel port found'`（P-063 残余的**点名责任人**） | `round5-main/p063-pressure-after-p064.xml`（80 tests / 1 failed） | 该用例只打桩了 `_recheck_ports_before_deploy`，**没打桩前置的端口分配**；照 `test_reservation.py` 的做法补 `mock.patch("register.probe.allocate_local_port"/"local_port_free")` 即可闭环。全量 1641 项在同压力下已是 11 红（`p063-fullunit-pressure-after-p064.xml`），说明**只差这一处** |
| **D5** | **高（数字口径）** | **pytest 9.1.1 写出的 junit `tests` 属性是膨胀值**，不能当作用例数。实例：同一次运行 `tests="2316"` 而 pytest 自己的汇总行是 `1656 passed, 9 skipped`（=1665）；离线三层真值 **1686** | 见下方对照表 | **已就地修订**：`第五轮测试报告.md` §1/§11、`round5-spec覆盖矩阵.md` 口径行、`审计-第五轮TB改动复核.md` §2、`round5-离线与覆盖率.md` §1（保留膨胀值仅作注释） |
| **D6** | 低（归属核对） | 自查稿 §2 称"本轮全部改动都在 `test/` 与 `test/reports/`"，但 `skills/virtuoso-bridge/SKILL.md` 与 `skills/virtuoso-bridge/references/operations.md` 的 mtime = **09-23 19:48**（落本轮窗口内；其余非 test 文件都停在 ≤11:08） | `Get-Item` mtime 清单 | 若是本轮为配合场景做的 skill 文档更新，请在报告里补一句；否则注明"跨轮次未提交改动" |

### D5 对照表（同一文件内部自洽性检查）

| 证据文件 | junit `tests` 属性 | 实际 `<testcase>` 数 | pytest 汇总行/独立口径 | pytest 版本 |
|---|---|---|---|---|
| `round5-main/offline-junit.xml` | 2316 | **1665** | `1656 passed, 9 skipped`（`offline-pytest2.log`）→ 1656+9=1665 ✅ | 9.1.1 |
| `round5-main/offline-final6.xml` | 2335 | **1686** | 进度字符 1686（`[100%]`）；`--collect-only` 逐文件求和 **1686** | 9.1.1 |
| `round5-main/conc-A.xml` | 2287 | **1641** | 与 unit-only 选择一致 | 9.1.1 |
| `round5-main/p063-pressure-after-p064.xml` | 80 | **80** | 小幅选择未触发膨胀 | 9.1.1 |
| 探针：单文件 5 用例 | **223** | 5 | — | 9.1.1（Windows 与 Linux 同值） |
| 探针：同一文件 5 用例（Linux） | **5** | 5 | — | **8.4.2**（同机对照，正常） |

> 结论：真值口径 = **`<testcase>` 元素数** 或 **pytest 汇总行**；`tests` 属性在 9.1.1 下不可用（8.4.2 正常）。
> 因此第五轮口径应为：**Windows 离线三层 1686 项 → 11 failed / 6 skipped / 1669 passed**；Linux 1686 项 → 14 failed / 18 skipped / 1654 passed。

## 5. 我在清单之外复算的关键数字（抽查）

| 项 | 来源 | 我的复核 |
|---|---|---|
| 十套包 E2E | `round5-main/run-all-http-results.json` | `all_passed=true`；**10 个 suite 逐条 ok=true / rc=0** ✅ |
| 多跳（S15） | `round5-multihop/multihop-jump.json` | `passed=11 / total=11` ✅ |
| 规模档 S4 | `round5-main/scale-100.json` | `ok=true` ✅ |
| e2e live | `round5-main/e2e-live-green2.log` | `6 passed, 4 skipped`（skip 原因=未设 `VB_E2E_LOCAL=1`）✅ |
| 两次离线整跑一致性 | `offline-final.xml` / `offline-final6.xml` | 11 条红逐条相同 ✅ |
| SerDes / ADC 场景 | `round5-serdes-rx.json` / `round5-adc-sar.json` | `ok=true`，判定 15/15（9 阶段）与 22/22 ✅ |
| P-063 修复前后 | `conc-A/B.xml` vs `conc-new-A/B`、`conc-C/D` | 并发 29 failed → **11 failed**（修复有效）✅ |

## 6. 我顺手修掉/标注的 stale（供收尾核对）

1. 已改 `第五轮-真实场景-SerDesRX.md` §4.2/§4.3：原写"DRC 本轮未跑""ADC 本轮未做"——
   实际真机 `calibre.drc` 已对 `s11_inv/inv.gds` 实跑（1737 rulechecks / 36 结果 / `DRC_RES.db`），ADC 场景已补齐（22/22）。
2. 已改 `第五轮测试报告.md` §11 一行：两次整跑口径写成"**逐字段一致**"。
3. 已在 `第五轮测试报告.md` 追加 **§12 收尾追加核对**（含 `offline-final7.log` 作废说明）。
4. **膨胀数字已就地修订**（D5）：`第五轮测试报告.md` §1/§11、`round5-spec覆盖矩阵.md` 第 225 行、
   `审计-第五轮TB改动复核.md` §2、`round5-离线与覆盖率.md` 第 11 行——四处都改成"真值口径 + 膨胀值注释"，
   不再把 `tests=2335/2287/2316` 当用例数引用。

## 7. 仍未闭环（本复核不推翻，只登记）

* **P-057**：深嵌套 JSON 的 deep 用例仍是弱断言（跨解释器行为差异），需产品决定是否加显式深度上限；
* **LVS/CDL 归属**：`si -batch`/auCdl 在本环境对 PDK 器件即失败，LVS 无输入 → 归属待定；
* **X2**：真实 100 台规模用 100 fake 替代，口径需验收方确认；
* **半真机 py2.7 真 SKILL 往返**：目前只到协议/校验层；
* **P-056 在 Windows 侧不暴露**（POSIX 分支专属），修复后需在 Linux 侧复验；
* **P-063 残余**：见 D4（已点名单条用例）。

## 8. 判定

1. **"是否为了变绿而改 TB"**：**否**。逐条判定与自查稿一致（纯新增 / 有依据的口径修正 / 消除脆弱），唯一"删断言"处替换后整体更强（P-057），另有 1 处"断言 → skipTest"（D1）属 P-046 安全策略且有绿证据。
2. **数字可信度**：11 条有意红、E2E 10/10、多跳 11/11、场景数字全部**独立复算通过**；**唯一需要修的是用例总数的口径（D5）**。
3. **第二双眼睛**：**已补**——本文件即独立复核产物（复核人非本轮 TB 改动作者，且复跑了清单 6 项、纠正 5 处记述、点名 1 条残余假红）。
4. 结论：**判定通过**；建议 parent 按 D2/D5 修订数字口径、按 D4 补一处打桩后即可送审。
