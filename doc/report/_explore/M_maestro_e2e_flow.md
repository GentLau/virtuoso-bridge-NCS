# M — Maestro 真实仿真的端到端流程调研

> 对象：`examples/01_virtuoso/maestro/*.py`、`test_bak/test_maestro_*.py`、
> `skills/virtuoso/references/{maestro-python-api,maestro-skill-api,simulation-flow}.md`、
> `examples/01_virtuoso/schematic/01a_create_rc_stepwise.py`；并用
> `src_bak/virtuoso_bridge/virtuoso/maestro/{writer,lifecycle}.py` 与
> `reader/runs.py` 核对实际展开的 SKILL。
> 结论先行：最接近“零 PDK 的最小真实仿真”的是 `06a` + `06b`；它用
> `analogLib` 的 ideal `vdc/res/cap` 跑 AC，没有任何 model file
> (`examples/01_virtuoso/maestro/06a_rc_create.py:71-75,104-115`)。
> 但 06b 在 background session 里 `run_and_wait`/`read_results`
> (`examples/01_virtuoso/maestro/06b_rc_simulate_and_read.py:2-6,65-82`)，
> 与仓库自己的 GUI-mode 规则冲突
> (`skills/virtuoso/references/simulation-flow.md:1-5`,
> `skills/virtuoso/references/maestro-python-api.md:17-28`)；真实 TB 应优先
> 使用 GUI session，把 06b 的后台路径当成待真机复核的旧实验。

## 0. 证据边界

- ✅ 直接证据：示例中实际调用的 Python API，以及 reference 中的 SKILL 展开。
- ✅ 测试只固定包装层、字符串和 CSV 解析；`_RecordingClient` 返回 `"t"`
  (`test_bak/test_maestro_writer.py:18-27`)，`_FakeClient` 用手写 CSV 或空响应
  (`test_bak/test_maestro_read_results.py:99-127`)，waveform viewer 只检查生成文本
  (`test_bak/test_maestro_waveform_viewer.py:165-188`)，没有任何真实仿真测试。
- ⚠️ 06b 的 background 说法与 GUI-mode reference 冲突，见 §5.1。
- 🔶 纯 `analogLib` RC “无需 PDK model”是推断；“06a 没有 model/corner 调用”
  是直接事实 (`06a_rc_create.py:98-116`)。PDK 场景仍必须设置 model/section。
- ⚠️ 当前 `pyproject.toml` 只把 `src` 作为包根 (`pyproject.toml:24-25`)，
  而旧例把 `src` 当 `virtuoso_bridge` 来源
  (`06b_rc_simulate_and_read.py:23-25`)；跑 TB 前必须先解决 legacy
  package/venv 的 import 前提。

## 1. 最小可跑流程

前提：`<lib>/<cell>/schematic` 已存在、已 `schCheck` 并 `dbSave`。
外部要求：Virtuoso 在跑、`spectre` 可启动、license 可用；如果 GUI 打开，
还需要 X display (`AGENTS.md:14-16,251-252,309`)。

| 步骤 | 目的 | 调用/参数 | 注意点 | 旧例 |
|---:|---|---|---|---|
| 0 | 确认 DUT 存在且已保存 | `client.schematic.read(lib, cell)` 或 `ddGetObj(... "schematic")`；schematic 已 `schCheck`+`dbSave` | netlist 前必须 check/save，否则可能弹窗 | `maestro-skill-api.md:442-447`；`06a_rc_create.py:91-92` |
| 1 | 建 ideal RC schematic | `inst("analogLib","vdc/res/cap/gnd",...)`；`wire(...)`；`pin_at("C0","PLUS","OUT")` | master 必须存在；建议 `VDC.acm=1`、`R=1k`、`C=c_val` | `06a_rc_create.py:65-80`；`01a_create_rc_stepwise.py:15-17,70-83` |
| 2 | 设置器件参数 | `cdfFindParamByName(cdfGetInstCDF(...) "vdc/acm/r/c")~>value="..."` | `vdc` 是 DC 值，`acm` 是 AC magnitude；`C0.c=c_val` 才会被 Maestro 变量驱动 | `06a_rc_create.py:82-92` |
| 3 | 建/确保 maestro view | `open_session` → `maeOpenSetup`；`save_setup` → `maeSaveSetup`；`close_session` | 不 save 则磁盘上不存在，后续 GUI 打开可能弹 “Data file does not exist” | `07_ensure_maestro_view.py:14-22,44-70`；`lifecycle.py:217-226` |
| 4 | 选择 session 模式 | 配置用 `open_session`；仿真用 `open_gui_session`（`deOpenCellView`+editable） | policy：GUI required for simulation；background callback 不可靠，close 会取消在途 run | `simulation-flow.md:1-5`；`maestro-python-api.md:17-28`；`04_gui_open_snapshot_close.py:43-60` |
| 5 | 建 test / 绑定 DUT | `create_test("AC", lib=lib, cell=cell, view="schematic", simulator="spectre", session=s)`；改已有 test 用 `set_design(...)` | `create_test` 已含 DUT；`set_design` 只用于换 DUT | `06a_rc_create.py:102`；`writer.py:32-48`；`maestro-skill-api.md:139-148` |
| 6 | 配置 analysis | 先 `set_analysis("AC","tran",enable=False)`；再 `set_analysis("AC","ac",options=AC_OPT)` | Python wrapper 自动补 backtick；options 是 SKILL alist 字符串 | `06a_rc_create.py:103-108`；`writer.py:55-65` |
| 7 | 加 output | `add_output("Vout","AC",output_type="net",signal_name="/OUT")`；`add_output("BW","AC",output_type="point",expr=...)` | 频域用 `VF()` 不要用 `v()`；spec 示例绑定 scalar point | `06a_rc_create.py:109-111`；`maestro-skill-api.md:175-187` |
| 8 | 加 spec | `set_spec("BW","AC",gt="1G")` | spec 必须绑定已存在 output；Python wrapper 只暴露 `lt/gt` | `06a_rc_create.py:112`；`writer.py:91-101` |
| 9 | 设变量/参数 | `set_var("c_val","1p,100f")`；逗号列表建立 sweep | 默认 global；test/corner 变量要 `type_name/type_value` | `06a_rc_create.py:113`；`writer.py:108-130`；`maestro-skill-api.md:194-206` |
| 10 | 建 corner/model（可选） | PDK：`setup_corner(name, model_file=..., model_section=..., variables={...})`；或 `set_env_option(test, '(("modelFiles" (("/path/model.scs" "tt"))))')` | `maeSetCorner` 不能接 model/temperature；必须走 `maeSetVar+axl*`；model path 必须在 Virtuoso/Spectre 主机可见 | `writer.py:200-209,239-290`；`maestro-skill-api.md:208-248` |
| 11 | 设 run mode/job/simulator | `set_current_run_mode("Single Run, Sweeps and Corners")`；小型 TB `set_job_control_mode("Local")` | 06a 完全没设；不要假设已有 view 的默认 run mode；Spectre X 可选 | `writer.py:306-321`；`maestro-python-api.md:320-331`；`08_set_simulator_mode.py:69-98,168-185` |
| 12 | 保存 setup | `save_setup(lib, cell, session=s)` → `maeSaveSetup` | 不 save 会跑旧参数；corner/model/run mode 修改也必须 save | `06a_rc_create.py:115-116`；`troubleshooting.md:191-192`；`writer.py:630-635` |
| 13 | 跑仿真并等待 | `history,status = run_and_wait(session=s, timeout=600)`；实现为 `maeRunSimulation(?callback ...)`+marker 轮询 | marker 只证明 callback，不证明收敛/结果完整；不要用阻塞 `?waitUntilDone t` | `06b_rc_simulate_and_read.py:72-78`；`writer.py:491-575`；`maestro-skill-api.md:353-360` |
| 14 | 读结构化结果 | `read_results(session, lib=lib, cell=cell, history=history)`；内部 `maeExportOutputView ?view "Detail"`→CSV→下载→解析 | reference 写 GUI mode required；不传 history 会自动选最新结果；空 dict 不是异常 | `06b_rc_simulate_and_read.py:80-102`；`runs.py:132-183`；`maestro-python-api.md:162-164` |
| 15 | 导出波形 | `export_waveform(session, 'dB20(mag(v("/OUT")))', path, analysis="ac", history=h)`；phase 同理 | 实现走 `maeOpenResults`→`openResults`→`selectResults`→`ocnPrint`→download | `06b_rc_simulate_and_read.py:104-118`；`runs.py:401-424` |
| 16 | 关闭并验证产物 | background `close_session`；GUI `close_gui_session(save=True)`；检查 PSF、`spectre.out`、`logFile` | GUI unsaved 会走 save/promote/discard；必须验证磁盘结果 | `lifecycle.py:229-242,360-423`；`maestro-python-api.md:94-116` |

推荐 AC options：
`(("start" "1") ("stop" "10G") ("incrType" "Logarithmic") ("stepTypeLog" "Points Per Decade") ("dec" "20"))`
(`06a_rc_create.py:104-108`)。

最小骨架：
```python
AC_OPT = '(("start" "1") ("stop" "10G") ("incrType" "Logarithmic") ("stepTypeLog" "Points Per Decade") ("dec" "20"))'
sess = client.maestro.open_session(lib, cell)                 # 06a:100
client.maestro.create_test("AC", lib=lib, cell=cell, session=sess)  # 06a:102
client.maestro.set_analysis("AC", "tran", enable=False, session=sess)  # 06a:103
client.maestro.set_analysis("AC", "ac", options=AC_OPT, session=sess)  # 06a:104-108
client.maestro.add_output("Vout", "AC", output_type="net",
                          signal_name="/OUT", session=sess)     # 06a:109
client.maestro.add_output("BW", "AC", output_type="point",
                          expr='bandwidth(mag(VF("/OUT")) 3 "low")',
                          session=sess)                         # 06a:110-111
client.maestro.set_spec("BW", "AC", gt="1G", session=sess)   # 06a:112
client.maestro.set_var("c_val", "1p,100f", session=sess)     # 06a:113
client.maestro.save_setup(lib, cell, session=sess)           # 06a:115
client.maestro.close_session(sess)                           # 06a:116

gui = client.maestro.open_gui_session(lib, cell)              # 04:43
client.maestro.save_setup(lib, cell, session=gui)             # flow:36
history, status = client.maestro.run_and_wait(session=gui, timeout=600)  # flow:37
results = client.maestro.read_results(gui, lib=lib, cell=cell, history=history)  # flow:42
client.maestro.export_waveform(gui, 'dB20(mag(v("/OUT")))',
    "rc_ac_mag_db.txt", analysis="ac", history=results["history"])  # 06b:111-112
client.maestro.close_gui_session(gui, save=True)              # 04:60
```

## 2. 真实仿真需要什么，旧例怎么满足

| 条件 | 要求/来源 | 旧例中的满足方式 | 证据 |
|---|---|---|---|
| SSH/本地连接 | Python 到 Virtuoso daemon；远程必须有 SSH alias | `VirtuosoClient.from_env()` | `06a_rc_create.py:60`；`doc/report/复核测试环境.md:31,63` |
| 运行中的 Virtuoso | SKILL、`mae*`、OCEAN 都在 CIW 进程内 | WSL-Gent 已登记 IC6.1.8+`DISPLAY=:10` | `AGENTS.md:14-16,251-252`；`doc/report/复核测试环境.md:12` |
| X11 display | GUI open/focus/dialog/save 需要 | WSL 内 Xvfb `:10`，`DISPLAY=localhost:10.0` | `doc/report/测试执行报告.md:29` |
| Spectre 二进制 | Maestro 的 spectre test 必须能启动 Spectre | WSL-Gent 注册证据记录 `/opt/eda/cadence/SPECTRE241/bin/spectre` | `test/tb/artifacts/reg-six-remote/evidence.json:240`；`AGENTS.md:16,252` |
| Spectre license | 无 license 在启动阶段失败 | `virtuoso-bridge license` 或 `check_license()`；仓库没有 WSL license 通过证据 | `AGENTS.md:309`；`src_bak/virtuoso_bridge/spectre/runner.py:873-976` |
| Cadence shell env | `PATH/LM_LICENSE_FILE/LD_LIBRARY_PATH` 可能只在登录 shell | `VB_CADENCE_CSHRC` 或保证 `spectre` 已在 PATH；每个 SSH command 无状态 | `AGENTS.md:64,265-272` |
| PDK/model file | 只有 PDK 器件需要；model section 必须匹配 | RC 没有；PDK 用 `setup_corner` 或 `set_env_option` | `06a_rc_create.py:98-116`；`writer.py:200-209,239-290` |
| `analogLib` masters | 没有 vdc/res/cap/gnd 就建不了 schematic | RC 例前置条件；env probe 枚举 analogLib | `01a_create_rc_stepwise.py:15-17`；`test/tb/maestro_env_probe.py:105-106` |
| 可写 library/results | `maestro.sdb/active.state/PSF/log` 要落盘 | 结果通常在 `<lib>/<cell>/maestro/results/maestro`，也可能在 scratch root | `runs.py:191-196`；`snapshot.py:207-243` |
| run mode/job control | 决定 test/sweep/corner 语义与 Local/LSF | wrapper 提供 API，但 06a 未调用 | `writer.py:306-321`；`maestro-python-api.md:320-331` |
| 已保存 schematic | 避免 netlister 弹窗/stale view | 06a 显式 `schCheck/dbSave` | `06a_rc_create.py:91-92` |

## 3. RC 例子全量细读

### 3.1 `06a_rc_create.py` 的每一步

| 序 | 位置 | 实际调用/参数 | 作用/注意 |
|---:|---|---|---|
| 1 | `06a_rc_create.py:40-58` | `<LIB>`；cell=`TB_RC_FILTER_<timestamp>` | 时间戳避免覆盖旧结果；TB 也应使用唯一名或明确清理 |
| 2 | `06a_rc_create.py:60-61` | `VirtuosoClient.from_env()` | 连接 daemon；失败在 setup 阶段暴露 |
| 3 | `06a_rc_create.py:65-70` | `client.schematic.create(lib,cell)` | context exit 自动 check/save；`create` 是覆盖语义 |
| 4 | `06a_rc_create.py:71-75` | `analogLib` 的 `vdc/gnd/res/cap` | 纯理想器件，无 PDK |
| 5 | `06a_rc_create.py:76-79` | `V0.PLUS→R0.PLUS`；`R0.MINUS→C0.PLUS`；`C0.MINUS→GND`；`V0.MINUS→GND` | VDC→R→C→GND 低通 |
| 6 | `06a_rc_create.py:80` | `pin_at("C0","PLUS","OUT")` | 后续 `/OUT` 输出节点 |
| 7 | `06a_rc_create.py:82-85` | `dbOpenCellViewByType(lib cell "schematic" nil "a")` | 打开为 edit |
| 8 | `06a_rc_create.py:86-90` | `V0.vdc=0`、`V0.acm=1`、`R0.r=1k`、`C0.c=c_val` | AC 幅度=1；电容由 Maestro 变量驱动 |
| 9 | `06a_rc_create.py:91-92` | `schCheck(cv)`；`dbSave(cv)` | 仿真前必须保存 |
| 10 | `06a_rc_create.py:98-100` | `open_session`=`maeOpenSetup` | background 配置 session |
| 11 | `06a_rc_create.py:102` | `create_test("AC",lib,cell)` | test 名之后复用；默认 spectre/schematic |
| 12 | `06a_rc_create.py:103` | `set_analysis("AC","tran",enable=False)` | 关闭默认 tran |
| 13 | `06a_rc_create.py:104-108` | AC 1–10G，Log，20 pts/dec | 最小 AC sweep |
| 14 | `06a_rc_create.py:109` | `Vout` net=`/OUT` | 波形输出 |
| 15 | `06a_rc_create.py:110-111` | `BW=bandwidth(mag(VF("/OUT")) 3 "low")` | scalar 输出；必须使用 `VF` |
| 16 | `06a_rc_create.py:112` | `set_spec("BW","AC",gt="1G")` | 示例 spec，不保证 pass |
| 17 | `06a_rc_create.py:113` | `set_var("c_val","1p,100f")` | parametric sweep |
| 18 | `06a_rc_create.py:115-116` | save + close | 落盘 `maestro.sdb` 并释放 lock |

06a 明确没有做：run mode、corner、model file、simulator-mode 切换
(`06a_rc_create.py:98-116`)。所以它是“ideal 器件 + 默认 run 条件的 AC smoke”，
不是 PDK corner 模板；PDK 必须补 §1 表格第 10、11 步。

### 3.2 `06b_rc_simulate_and_read.py` 的每一步

| 序 | 位置 | 实际调用/参数 | 作用/注意 |
|---:|---|---|---|
| 1 | `06b_rc_simulate_and_read.py:59-62` | `<LIB> <CELL>`；`from_env()` | cell 名取自 06a 输出 |
| 2 | `06b_rc_simulate_and_read.py:65-70` | `open_session(lib,cell)` | background；与 GUI-only policy 冲突 |
| 3 | `06b_rc_simulate_and_read.py:72-78` | `run_and_wait(session, timeout=600)` | callback marker 轮询；脚本忽略 `_status` |
| 4 | `06b_rc_simulate_and_read.py:80-84` | `read_results(session,lib,cell)` | 未传 `history=`，实现会选“最新有结果” |
| 5 | `06b_rc_simulate_and_read.py:85-102` | 遍历 `points/outputs`，打印 value/spec/pass_fail/overall | 结果结构由 `reader/runs.py` 产生 |
| 6 | `06b_rc_simulate_and_read.py:104-112` | `export_waveform(dB20(mag(v("/OUT"))), analysis="ac", history=...)` | AC magnitude |
| 7 | `06b_rc_simulate_and_read.py:115-118` | `export_waveform(phase(v("/OUT")), analysis="ac", ...)` | AC phase |
| 8 | `06b_rc_simulate_and_read.py:120-135` | 解析两列；1e6/1e8/1e9/1e10 最近点；线性插值 f_3dB | 可在 TB 侧改成断言 |
| 9 | `06b_rc_simulate_and_read.py:136-143` | `close_session` | finally 释放 background session |

### 3.3 RC 样本证明了什么，没证明什么

- 证明：ideal `analogLib` 元件 + AC analysis + variable sweep + spec 可以构成
  Maestro test (`06a_rc_create.py:71-75,104-115`)。
- 证明：Python 可以读 per-point 结果并导出 OCEAN 波形
  (`06b_rc_simulate_and_read.py:80-118`)。
- 未证明：PDK 器件可省略 model；06a 没有 `modelFiles/axlPutModel`
  (`06a_rc_create.py:98-116`)。
- 未证明：background run/read 在当前版本可靠；reference 明确要求 GUI
  (`simulation-flow.md:1-5`；`maestro-python-api.md:162-164`)。
- 未证明：仿真整体成功；06b 没有检查 `status`、PSF、`spectre.out` 或完整产物
  (`06b_rc_simulate_and_read.py:72-102`)。

## 4. `test_bak` 的 maestro 测试固化了什么

| 文件 | 断言/行为 | 位置 |
|---|---|---|
| `test_maestro_ops.py` | client 暴露 `MaestroOps`；public 方法集合完整 | `:8-11,14-29` |
| 同上 | facade 转发 owner+位置参数；`set_analysis` 的 `enable/options/session` 原样转发 | `:32-77` |
| `test_maestro_read_results.py` | 多点 Detail CSV 解析出 history/tests/parameters/outputs/pass_fail，并保留 flat list | `:34-69` |
| 同上 | 空 CSV 返回空 points/outputs/tests | `:71-75` |
| 同上 | 单点无 `Point` 列也能解析 spec/weight/pass_fail | `:78-91` |
| 同上 | 回归 #81：`maeExportOutputView` 只返回 `t` 时，只要 CSV 下载成功就不能返回空 | `:134-161` |
| 同上 | CSV 拉不到返回 `{}` 并 warning `maeExportOutputView did not produce` | `:164-183` |
| 同上 | `maeGetSetup` 无 test 返回 `{}` 并 warning “returned no test” | `:186-201` |
| 同上 | `ocnPrint` 默认 `scientific`，不擅自加 precision/width；显式选项透传 | `:204-272` |
| 同上 | precision 1–16、width≥4、notation 白名单；非法值在 SKILL 前抛错 | `:275-303` |
| `test_maestro_writer.py` | `maeCreateNetlistForCorner` 默认/显式 session 形式，session keyword-only | `:30-43,131-158` |
| 同上 | `add_output` 对全部字符串参数做 SKILL 转义 | `:46-64` |
| 同上 | `run_simulation` 把 timeout 传给 `execute_skill`，生成 `?session ?callback` | `:67-75` |
| 同上 | `run_and_wait` 使用一个端到端预算：start 用 12s，wait 只剩 48s | `:78-102` |
| 同上 | marker 轮询的 command timeout/sleep 不超预算，超时消息含预算 | `:105-128` |
| 同上 | `MaestroOps.create_netlist_for_corner` 显式 session 透传 | `:161-173` |
| `test_maestro_waveform_viewer.py` | open SKILL 含 `awvCreatePlotWindow/maeOpenResults/openResults/awvPlotWaveform` | `:13-30` |
| 同上 | 成功保留 results session；失败关闭 window/session 并报错 | `:33-60` |
| 同上 | lib/cell/history/signal/test/result/results_dir 转义；raw PSF 模式失败必须报错 | `:63-92` |
| 同上 | 无 net signal 时 fallback 到 `maeGetOutputValue`；输入校验和 close 校验 | `:102-162` |
| 同上 | open/close 执行生成 SKILL 并透传 timeout，返回 raw `VirtuosoResult` | `:165-222` |
| `test_maestro_snapshot_filter.py` | snapshot netlist whitelist 必须保留 `exprOutputs.json` | `:9-11` |

## 5. 已知失败模式和矛盾

### 5.1 GUI-only 与 background 冲突

- `simulation-flow.md` 明确 GUI mode required，background callback 不可靠，
  `close_session` 会取消在途 run (`simulation-flow.md:1-5`)；
  `maestro-python-api.md` 也给出同样结论 (`:17-28`)。
- 06b 却说 background 无 modal dialog、automation-safe，并在 background
  调用 run/read (`06b_rc_simulate_and_read.py:2-6,65-82`)。
- `read_results` 实现注释写 “Requires GUI mode”
  (`src_bak/virtuoso_bridge/virtuoso/maestro/reader/runs.py:51-52`)。
- `maestro-skill-api.md:100-104` 说 `maeGetSetup` 必须先 GUI，而 03 与
  lifecycle 实际在 background 读 setup
  (`03_bg_open_read_close_maestro.py:71-80`；`lifecycle.py:217-226`)。
- TB 规则：配置可 background，run/read 用 GUI；不要直接复制 06b。

### 5.2 run mode/corner/model 坑

- 06a 不设 run mode/corner/model (`06a_rc_create.py:98-116`)；复用已有
  view 时默认 run mode 可能是别的值，必须显式设置
  (`writer.py:306-314`)。
- `maeSetCorner` 只支持 `?enabled/?disableTests`；model/temperature 必须走
  `maeSetVar+axl*` 或 XML (`maestro-skill-api.md:210-216,218-248`)。
- `setup_corner` 用 `axlPutModel/axlSetModelFile/axlSetModelSection`
  (`writer.py:276-286`)；文件名/路径/section 任一不存在都会在 netlist 失败。

### 5.3 session/lock/save

- `maeSaveSetup` 前不保存会跑旧参数 (`troubleshooting.md:191-192`)。
- `maeOpenSetup` 创建 `.cdslck`，background 必须 force close；crash 可能留
  stale lock (`maestro-skill-api.md:447`)。
- `open_gui_session` 自动清理 background/其他 cell/Reading window
  (`lifecycle.py:311-357`)；`close_gui_session` 处理 unsaved/promote/discard
  (`lifecycle.py:360-423`)。
- `maeCloseResults` 可能让 Maestro 进入 read-only，下一次 run 失败
  (`simulation-flow.md:152-155`)。

### 5.4 结果读取失败

- `maeExportOutputView` 返回值跨版本不同；以远端 CSV 是否真实存在为准
  (`test_bak/test_maestro_read_results.py:3-18,134-161`)。
- CSV 未生成时 `read_results` 返回 `{}` 而非抛异常
  (`runs.py:149-162`)。
- 不传 `history=` 时会扫描最新有效 history (`runs.py:186-210`)；并发/连续 run
  可能读错，TB 应显式传 history；`run_and_wait` 返回值可能带引号，先 strip
  (`writer.py:539-540`)。
- marker 只代表 callback，不代表收敛/结果完整
  (`writer.py:522-575`)。

### 5.5 sweep/sub-point

- sweep history 可写成 `Interactive.3/4`
  (`09_export_sweep_subpoints.py:4-11`)。
- `maeOpenResults(?history "Interactive.3/4")` 报 ASSEMBLER-2233；
  `read_results` 也拿不到有用结果 (`09_export_sweep_subpoints.py:13-16`)。
- 绕过：直接用 OCEAN `openResults(psf_dir)`→`selectResult(...)`→`ocnPrint(...)`，
  再 `download_file` (`09_export_sweep_subpoints.py:18-25,62-76,108-128`)。
- 09 中 PSF 路径硬编码为 `<pt>/<analysis>-<analysis>.tran.tran`，注释也承认
  版本/analysis 不同路径会变 (`09_export_sweep_subpoints.py:112-116`)；不要照抄。

### 5.6 版本/API/GUI

- 旧版本可能没有 `mae*`，需 `asi*` fallback，检测 `fboundp('maeRunSimulation)`
  (`maestro-skill-api.md:45-68`；`troubleshooting.md:178-179`)。
- IC23.1 不支持 `maeGetSetup(?typeName "globalVar")`，改用
  `asiGetDesignVarList(asiGetCurrentSession())` (`maestro-skill-api.md:137`)。
- `maeGetTestSession` 比旧 `asiGetTest` 更可移植
  (`08_set_simulator_mode.py:19-33`)；`selectResults` 与 09 的 `selectResult`
  拼写不同，需按实际版本确认 (`runs.py:417-421`；`09_...py:71-76`)。
- `snapshot()` 依赖当前 focus，焦点被抢会读错 session
  (`01_read_focused_maestro.py:2-7,20-32`)；04 的 session 比较值得复用
  (`04_gui_open_snapshot_close.py:43-55`)。
- GUI dialog 会阻塞 SKILL channel，可用 `hiFormDone`/X11 dismiss
  (`maestro-skill-api.md:442-447`；`simulation-flow.md:147-156`)。

### 5.7 当前仓库路径坑

- 示例从 `src` import 旧 `virtuoso_bridge`
  (`06b_rc_simulate_and_read.py:23-25`)，但当前 pyproject 只把 `src` 当新四层包根
  (`pyproject.toml:24-25`)；不先处理 legacy package，例子可能在 import 阶段失败。

## 6. 建议的 WSL-Gent 最小真实 TB

### 6.1 circuit/analysis/output

- 第一版用纯 `analogLib` RC 低通：`vdc(acm=1)→res(1k)→OUT→cap(c_val)→gnd`；
  这是 06a 的结构，不需要 PDK model
  (`06a_rc_create.py:71-75,85-90`)。
- 先只开 AC：1 Hz–10 GHz，Logarithmic，20 pts/dec；显式 disable 默认 tran
  (`06a_rc_create.py:103-108`)。
- output：`Vout` net `/OUT`；`BW` point `bandwidth(mag(VF("/OUT")) 3 "low")`
  (`06a_rc_create.py:109-111`)；spec `BW>1G` 可保留，但 TB 同时记录实际 BW
  (`06a_rc_create.py:112`)。
- `c_val` 先单点 `1p` 验证链路，再 `1p,100f` 验证 sweep
  (`06a_rc_create.py:113`)。

### 6.2 corner/model 策略

- 第一版：不调用 `set_env_option/setup_corner`，只验证 Maestro+Spectre 链路。
- 第二版 PDK smoke：`setup_corner("tt_25", model_file=<absolute .scs>,
  model_section="tt", variables={"temperature":"25"})`
  (`writer.py:239-290`)，并设
  `set_current_run_mode("Single Run, Sweeps and Corners")`
  (`writer.py:306-314`)。
- 不要尝试 `maeSetCorner(... ?modelFile ...)`
  (`maestro-skill-api.md:210-216`)。

### 6.3 推荐执行顺序

1. 只读 preflight：SSH、Virtuoso、DISPLAY、`which spectre`、license、lib path、
   `analogLib`；仓库已有 `test/tb/maestro_env_probe.py`
   (`test/tb/maestro_env_probe.py:18-72,98-106`)。
2. 在 scratch lib 建 RC；可参考 `maestro_e2e_probe.py` 的
   `maestro_tb/rc_probe`，注意它会创建/覆盖远端对象
   (`test/tb/maestro_e2e_probe.py:21-35,38-58`)。
3. ensure maestro view：`maeOpenSetup`+`maeSaveSetup`
   (`07_ensure_maestro_view.py:44-70`)。
4. GUI open→配置→save (`04_gui_open_snapshot_close.py:43-60`；
   `simulation-flow.md:15-37`)。
5. `run_and_wait`；若返回 nil，检查 enabled analysis、modal dialog、
   Explorer vs Assembler (`writer.py:424-468,536-571`)。
6. 显式 history 调 `read_results`；确认 points 非空、spec 字段存在
   (`runs.py:132-183`；`test_bak/test_maestro_read_results.py:34-91`)。
7. 导出 AC magnitude/phase；验证文件非空、行数>1
   (`06b_rc_simulate_and_read.py:104-135`)。
8. `close_gui_session(save=True)`；sweep sub-point 另走 09 的 OCEAN 方案
   (`04_gui_open_snapshot_close.py:59-61`；
   `09_export_sweep_subpoints.py:51-76`)。

### 6.4 WSL-Gent 条件矩阵

| 条件 | 现有证据 | 判断/动作 |
|---|---|---|
| Virtuoso | IC6.1.8，Xvfb DISPLAY=:10 | 已有；TB 前仍 `pgrep -f virtuoso` (`doc/report/复核测试环境.md:12,63`) |
| Spectre binary | `/opt/eda/cadence/SPECTRE241/bin/spectre` | 二进制存在；检查版本/PATH (`test/tb/artifacts/reg-six-remote/evidence.json:240`) |
| Spectre license | 仓库只有检测方法，无 WSL 通过证据 | **未知**；跑 `virtuoso-bridge license`/`lmstat -a` (`AGENTS.md:309`；`runner.py:873-976`) |
| GUI/display | Xvfb `:10`，DISPLAY=localhost:10.0 | 若 Xvfb 重启后未起，`open_gui_session` 会失败 (`doc/report/测试执行报告.md:29`) |
| `analogLib` | probe 会枚举，但仓库无固化结果 | **待确认**；运行 env probe (`test/tb/maestro_env_probe.py:105-106`) |
| PDK/model | probe 查 `/home/Gent/models`、`/opt/eda/models`，无结果；RC 不需要 | 第一版不需要；第二版先找绝对 `.scs`+section (`maestro_env_probe.py:65-69`) |
| license env | 支持 `VB_CADENCE_CSHRC`，WSL 是否配置未知 | **未知**；Maestro 内部 Spectre 失败时先查 CIW env (`AGENTS.md:64,265-272`) |
| 磁盘/可写 lib | 有机器容量与项目路径登记，无本 TB 写入证据 | 先查 `df -h`、lib readPath、`/tmp` (`doc/report/复核测试环境.md:12`) |
| legacy Python 包 | 当前 pyproject 只发现新 `src` | **可能缺**；先配置 `src_bak` 或安装旧包 (`pyproject.toml:24-25`；`06b_rc_simulate_and_read.py:23-25`) |

### 6.5 验收标准

- 配置：`maeGetSetup` 有 test；enabled analysis 含 `ac`；PDK 版本
  `modelFiles` 非空；run mode 正确
  (`maestro-skill-api.md:100-137,208-248,310-320`)。
- 运行：history 非空且对应 `results/maestro/<history>`
  (`runs.py:186-210`)。
- 结果：`points` 非空；BW value 可解析；spec/pass_fail 存在
  (`test_bak/test_maestro_read_results.py:34-91,134-161`)。
- 波形：magnitude/phase 文件非空，频率点数量>1
  (`06b_rc_simulate_and_read.py:120-135`)。
- 产物：PSF、`spectre.out`、`logFile` 存在；不要只看 marker/status
  (`maestro-python-api.md:94-116`；`writer.py:522-575`)。
- 环境记录：Spectre path/version、license、model/section（若有）、analogLib、
  Xvfb DISPLAY、lib path (`maestro_env_probe.py:18-72,98-106`；
  `runner.py:873-976`)。

## 7. 最终建议

1. 先做 ideal-RC TB，不先做 PDK TB；用 06a 的电路/AC/output 验证
   “maestro view→test→analysis→output/spec→var→GUI run→CSV→waveform”
   (`06a_rc_create.py:71-75,104-115`；`06b_rc_simulate_and_read.py:80-118`)。
2. 配置可 background，run/read 以 GUI 为准
   (`simulation-flow.md:1-5`；`maestro-python-api.md:17-28`)。
3. corner/model 分阶段：第一版不建，第二版用 `setup_corner`+explicit run mode
   (`writer.py:239-290,306-314`)。
4. 结果双重校验：history+CSV/spec，再查 PSF/log；marker 只是 callback
   (`writer.py:522-575`；`runs.py:132-183`)。
5. sweep 用 09 的 OCEAN absolute PSF path，不用 06b 的自动 history 选择
   (`09_export_sweep_subpoints.py:18-25,51-76`)。
6. WSL blocker 顺序：legacy package → Virtuoso/Xvfb → Spectre/license →
   analogLib → 可写 lib → PDK model/corner
   (`test/tb/maestro_env_probe.py:98-106`；
   `test/tb/artifacts/reg-six-remote/evidence.json:240`；
   `doc/report/测试执行报告.md:29`)。
