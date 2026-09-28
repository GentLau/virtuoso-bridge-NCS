# 审计 · 本轮 TB 改动是"真缺陷修复"还是"为了绿而改"（2026-09-23）

> 被审对象：本轮我改过的测试侧文件（`git diff -- test` 里的路径类 + 断言类 + 探针类改动）。
> 审计方式：**独立 subagent 审计 + 我自己的可复现复算**，每一条都要求给出"原始代码是否真错 / 改后断言是否变弱 / 负控制能否变红"三答。
> 结论口径：**真缺陷修复** = 原始 TB 代码本身写错或写了修复前的旧契约；**弱化/伪造** = 为了让红灯变绿而删断言、放宽断言、吞异常或改成 skip。

## 0. 审计分工与完成度（诚实标注）

| 线路 | 范围 | 执行者 | 状态 |
|---|---|---|---|
| A | `s11_full_flow.py`（SKILL 嵌套 if）、`infra_e2e_tests.py`（netlist.import 断言） | 独立审计员 `audit_tb_flows` | ⚠️ **未按任务书交付**：该审计员转去做"第三轮环境恢复与复验"，产出了自己的两份清单与 P-044 第二层根因、P-047、P-048，但**没有给出"A 线"的审计结论**。它留下的负控制脚本由我复算（见 §2）——**因此 §1/§2 的定性目前只有我这一方证据，缺第二双眼睛** |
| B | 30 个文件的证据/环境路径批量改动 | 独立审计员 `audit_tb_paths` | **仍在跑**；我已自证其中"漏改=0"这一关键项（见 §3） |
| C | 假绿手法专项（skip/降级/吞异常） | 我（第三个 slot 被线程上限挡住，未能派出独立审计员，**这是本次审计的已知缺口**） | 见 §4 |

## 1. `s11_full_flow.py`：**真缺陷修复**（证据：修前真机报错 + 修后真机断言通过）

- 原始代码把 SKILL 的嵌套 `if` 写成 `sprintf(nil "…" (if(p1 …) (if(p2 …)))` —— SKILL 的 `if` 是特殊形式，这种写法会被解释成"拿上一个 if 的结果去调用"。**真机 CIW 日志留痕**：`/home/Gent/virtuoso_11.log:11467` → `\e *Error* eval: not a function - dbClose(cv)`（就发生在本轮 s11 首次尝试时）。
- 改后真机复跑（证据 `test/artifacts/evidence/s11-round3/summary.json`，token `vb-vblog`）：`PASS`，note = `"devices=MN,MP pins=IN,OUT,VDD,VSS"; check_and_save=True; read_instances=6; pins_ok=True`。
- **断言强度**：改动只动 SKILL 表达式、没碰断言；TB 仍逐实例读回并校验 pin（`read_instances=6` / `pins_ok=True`）。
- **未完成**：s11 的"负控制"（故意少建一个器件、确认 TB 变红）**我没有单独复算**，只有正例证据。

## 2. `infra_e2e_tests.py`：**真缺陷修复（且是加强断言，不是弱化）**

- 原断言 `_check(imported.get("ok"), …)` 是在给一条**已删除的假成功路径**背书；修复后产品侧 `netlist.import` 是诚实参考桩（`ok=False` + `reference stub`）。TB 改成断言"必须结构化失败 + 明说 stub"——**方向是收紧**。
- **负控制（本次审计独立复算，命令可重放）**：
  ```powershell
  $env:PYTHONPATH="src"; .\.venv\Scripts\python.exe test\artifacts\tmp\mutation_infra_netlist_import.py
  ```
  实测输出：
  ```
  A) product fakes success -> RED: netlist.import must not fake success: {'ok': True, ...}
  B) product honest stub   -> GREEN
  VERDICT: assertion is discriminating
  ```
  即：产品若退回"假成功"，TB **会红**；产品保持诚实桩，TB 绿。断言有鉴别力。

## 3. 路径批量改动（30 文件）：**未发现使测试空转**

- 已核：`test/artifacts/{env,evidence,tmp}` 三个层级均存在，且在 [README](../artifacts/README.md) §1 有职责说明（`env/`=可复用环境、`evidence/`=一轮一份只增不改、`tmp/`=可随时删）。
- **漏改=0（本次复算）**：`rg -n "artifacts[/\\](log-vblog|http-e2e|skill-tooling-tb|layout-tb|symbol-tb|scenario-)" test src` → 无命中，说明旧平铺路径在代码侧已清除（报告/文档里的历史记录不计）。
- 待独立审计员回传的仍是两项：① 是否存在"断言读的目录 ≠ 写入的目录"（空转）；② 报告引用的证据文件是否齐全。

## 4. 假绿手法专项：**发现 1 处结构性假绿路径（当前不可达，仍应收紧）**

`test/semi/probes/daemon_internal_error_path_probe.py` 我把 py27 腿改成"没有 `VB_PY27` 就 skip"。风险点：

```python
ran = [item for item in verdicts if not item.get("skipped")]
silent = all(not item["bytes_sent"] for item in ran)   # ran 为空时 all([]) == True
return 0 if silent else 1                              # → 全跳过 = 绿
```

- **实测**（`VB_PY27` 未设）：输出 `[daemon_27] SKIP: 需要真 py2.7…` + `VERDICT: contract holds (test is wrong)`，**exit=0**。
- **可达性**：`test/offline/unit/test_daemon_runtime_contracts.py` 的 `VARIANTS = ("py3", "py27")`，py3 腿总会执行（实测 `[py3] handler saw ['ValueError'] -> sent b''`），所以"`ran` 为空"当前**不可达**。
- **判定**：不是本次改动造成的假绿，但`all([])`是个陷阱——**建议加一行守卫**：`if not ran: print("SKIP: 无可用解释器"); return 2`（用非 0 退出码区分"跳过"与"契约成立"）。
- 该 skip 是否"掩盖缺陷"：**不掩盖**。py2.7 的真实信号由另一条链路承载（`test/semi/probes/py27_daemon_probe.py`，当前因 P-043 **0/5 红**），没有丢覆盖。

### 其余扫描结果（本轮 diff 新增行）

`git diff -U0 -- test | Select-String '^\+' | Select-String 'skip|xfail|except:|except Exception|pass$|lenient|warn_only'` 命中的新增行只有：
`daemon_internal_error_path_probe.py` 的 4 行 SKIP 逻辑（上面已判）+ `run_package_e2e.ps1` 的 `$Skip` 解析（**非我本轮改动**）。
即：本轮我的改动**没有**新增 `except: pass`、没有把断言改成 print、没有新增 xfail。

## 5. 一处**不属于 TB 改动**但必须记录的测试侧缺陷（本轮审计的副产品）

| ID | 事实 | 后果 |
|---|---|---|
| P-046 | `test/live/e2e/test_e2e_live.py::_discover_current_daemon()` 未固定引导源时会挑任意真 daemon 的 CIW，并对其执行 `RBStop()+load(<新 setup>)` | 实测覆盖掉用户 ADE 实例（CIW 369800）→ 65121 通道消失 → **P-045 被误判成"并发打挂通道"**。详见 [问题登记.md](问题登记.md) P-045′/P-046 |
| — | 同一测试用 `tempfile.mkdtemp(prefix="vb-")` 作 work-dir（`:126`），跑完即失 | 本轮报告里"e2e pytest ✓"**没有可复查的证据文件**——这正是 P-045 能长期挂着错的土壤。建议改为固定 work-dir（`test/artifacts/env/vbe2e-*`）并落 run 日志 |

## 6. 结论

1. 已复算的两处**核心改动都是真缺陷修复**，且 `infra` 那条是**加强**断言（有可重放的变异检查）。
2. 路径批次**未发现空转或漏改**（旧路径零残留、三层目录有定义）。
3. **一项审计缺口**：假绿专项我一人做完，没有第二双眼睛；且 s11 的负控制、路径批次的"写-读一致性"仍等两个独立审计员回传，**回传后本文件会被更新**。
4. 本轮最值得记住的教训不是"哪条 TB 写错了"，而是 **P-045**：一条测试用 `RBStop()` 覆盖了别人的 CIW，把产品侧告成了"并发打挂通道"。**破坏性操作的目标选择必须显式化**。
