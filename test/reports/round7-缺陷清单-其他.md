# 第七轮 · 缺陷清单（其他 —— 给测试/环境/文档侧，非源码 bug）

> 口径：**源码类**缺陷在 `round7-缺陷清单-上层.md`；这里只放"不是产品源码错，但会绊人"的项：
> 测试工具/探针自身、环境配置、文档与 spec 表格、口径提示。每条都给了复现与验收。
> 本轮这类项**都已由测试侧当场处理**（TB 可改就改），未关闭的只剩 P-074（需要设计侧定口径）。

| 编号 | 类别 | 标题 | 现状 | 处理 | 证据 |
|---|---|---|---|---|---|
| R7-O-01 | 探针 | `py27_handler_probe.py` 用包导入 py2.7 daemon → 真 py2.7 下必然 SyntaxError | **已修**（按文件路径载入，与真实部署一致） | 见 `round7-TB修正.md` R7-TB-06 | wsl-gent `~/project/vblog/tb-sandbox/r7out/py27-handler.json`（`silent drop (correct)`，Python 2.7.6） |
| R7-O-02 | TB | `scale_100_tb.py` 同进程二次 `init_work_dir` → P-072 新口径下起不来 | **已修**（负向对照改子进程） | 见 `round7-TB修正.md` R7-TB-07 | `test/artifacts/env/scenario-scale-100/evidence.json`（5/5） |
| R7-O-03 | TB | `serdes_rx_flow_tb.py` 的 `cdl` 阶段仍走被淘汰的 `si -batch` 手写 env 路径 | **已修**（改走 `calibre.export_cdl`） | 见 `round7-TB修正.md` R7-TB-08 | `test/artifacts/evidence/round7/serdes/serdes-cdl.json` |
| R7-O-04 | TB（新增） | 迭代链 TB 自身的四处假红（缺 VSS 地、耦合电容测量频点、读回值带引号、append 语义重放实例） | **已修** | 见 `round7-TB修正.md` R7-TB-01/02/04/05 | `test/artifacts/evidence/round7/design-iterate/`（11 段证据 JSON） |
| R7-O-05 | 口径提示 | **GDS 的 sha256 不能当"内容变了"的判据**（文件内嵌时间戳，同一版图两次导出 sha 必不同） | 已写进 TB 注释与证据字段 | 内容差异改用 `virtuoso.layout.read` 的 shape 计数；GDS 只验"能发布到新目录" | `iterate-r1_gds.json`（sha_a）、`iterate-r2_layout.json`（sha_b ≠ sha_a）、`iterate-r2_layout.json:gds_sha_note` |
| R7-O-06 | 口径提示 | `calibre.read_results` 必须带 `job_id` 或 `run_dir`，否则返回空 `value`（看着像"LVS 没结论"） | 已写进 TB（并断言 `read_results.ok`） | TB 里从 `calibre.lvs` 的 `value.job_id` 透传 | `iterate-lvs.json:read_results_request` / `results_inv2` |
| R7-O-07 | 环境 | pytest 跑完**不打印汇总行**（"N passed, M skipped in Xs"），`-q` 下日志停在 `[100%]` | 观察项（不影响 rc 与 JUnit 计数） | 报告口径改为：**以 JUnit `<testcase>` 计数 + rc 为准**（本轮 Windows/Linux 都是 1725 例、逐文件收集数完全一致） | `offline2.log`、`offline2.xml`（`cases=1725`）、`test/artifacts/tmp/collect-win.txt` vs `collect-linux.txt`（逐文件一致） |
| R7-O-08 | 文档 | spec 表格把 pin 的索引写成 `xy`，实现要 `x`/`y` | **未关闭** → 已立案 **P-074**（给设计侧定口径） | TB 已按实现写 | `test/reports/bugs/P-074-pin-index-xy-doc-mismatch.md` |
| R7-O-09 | TB（standalone） | `offline/core/{semantics_tb,fault_injection_tb}.py` 同进程多次 `init_work_dir` → P-072 新口径下 9 条检查假红（`run_main_coverage.ps1` 因此报 2 个 rc=1） | **已修**（改每 case 子进程） | 见 `round7-TB修正.md` R7-TB-11/12 | `round7/semantics.json`（10/10）、`round7/fault-injection.json`（8/8） |
| R7-O-10 | TB（真因定位） | S11 的 lvs 长期 FAIL 的真因是**原理图 pin 姿势错**（`dbCreateInstByMasterName(… "basic" "ipin" …)` 摆假 pin → auCdl 无法下钻），不是 P-069 | **已修**（改 `schCreatePin` + 官方 `calibre.export_cdl`） | 见 `round7-TB修正.md` R7-TB-09 | `test/artifacts/env/s11/`（cdl 693 B、lvs `status=incorrect` 确定结论、summary rc=0） |
| R7-O-11 | 覆盖率测量 | `src/server/supervisor.py` 单跑覆盖率 **0.0%**，但它的离线用例（`test_supervisor_process.py`/`test_supervisor_internals.py`）本轮全绿 —— 代码跑在**子进程**里，runner 未开子进程覆盖率（`COVERAGE_PROCESS_START`）→ 数字**低估**执行事实 | **未关闭（测量口径）**：下一轮给 cov runner 加 `concurrency=multiprocessing` + `.pth` 钩子，把子进程覆盖率并进来 | 本轮报告里明确标注，禁止拿 0% 当"未测"证据 | `test/artifacts/evidence/cov-main/coverage-main-strict.json`（supervisor 335 条语句 0 覆盖） |
| R7-O-12 | 半真机入口 | 半真机探针此前**没有固化入口**：参数/依赖散在 docstring，本轮首跑就因参数姿势错红了 4 个探针（`skill_tooling/skillref/docs_search/role_credential_isolation`），另有 1 个探针判据过时（`layout_lock_ownership`） | **已修**：新增 `test/shared/runners/run_semi_probes.py`（表驱动）+ 3 处探针/参数纠正；本轮整层 **32/32 green（456s）** | 见 `round7-TB修正.md` R7-TB-14/15/16 | `test/artifacts/evidence/round7/semi-probes.json`、`round7/semi-logs/` |
| R7-O-13 | 环境观察 | 常驻 vblog 实例上 `ControlMaster` 在 wsl-gent 侧会报 `getsockname failed: Not a socket` → 自动降级为"每会话新建连接"（不影响结论，但会增加建连开销）；`ssh_backend_semi_tb` 另观察到"持久 shell 中途退出 → 回退一次性 SSH"这一条路径被真实触发 | **观察项（不是缺陷）**：注册表可显式 `ssh.control_master='disable'`；回退路径本身是设计内的 | 记录以备排查"为什么慢/为什么连接数高" | `round7/semi-logs/role_credential_isolation_tb.py.log`、`.../ssh_backend_semi_tb.py.log` |
| R7-O-14 | 探针红→定位 | `twouser_same_view_probe` 用 `TEST_LIB` 时红（`*Error* create failed`）——`TEST_LIB` 只在 calprobe 的 `cds.lib` 里，两个真实用户的会话看不到 | **已修（参数）**：改用 `/project/libs/serdes_rx` 共享库 → **7 场景全绿**（含"A 持有 edit 时 B 读成功 / B 写得到干净锁失败"） | 见 `round7-TB修正.md` R7-TB-15（同批参数纠正） | `test/artifacts/evidence/round7/twouser-same-view.json`（verdict GREEN） |
| R7-O-15 | 矩阵证据 | **spec 矩阵有 4 行引用了"已不存在"的证据文件**（A17/E8 引用已删除的 `http_mixed_stress_tb`、C1 引用不存在的 `test_registry.py`、G7 引用随 `demo` 包删除的旧用例）——这正是审核最容易一击命中的"写了证据其实没有" | **已修**：A17/E8 改指 `production_face_stress_tb.py`（+ 本轮证据）、C1 改指现存 registry 用例、G7 **用新离线用例补回覆盖**；并新增逐行核账工具防复发 | 见 `round7-测试报告.md` §10、矩阵 §15 | 核账结果：`rows=195, missing_evidence_rows=0, offline_verified=84, not_rerun=110`（`audit_spec_matrix_evidence.py`） |
| R7-O-16 | 覆盖丢失 | G7 那条覆盖原本挂在 `test/upper_layer_paths.py`，随 `src/pyapi/packages/demo.py` 一起删除后**没有任何用例在管**"上层不得 import transport/socket/subprocess/paramiko、不读 VB_*/\.env"这条 spec 约束 | **已补**：新增离线用例 `test/offline/unit/test_upper_layer_import_contract.py`（AST 静态扫描 pyapi/\*\* + `server/dispatch.py`，含**负控制**与**正控制**） | 断言可鉴别：负控制造 `import paramiko` 必被抓到；正控制确认扫描面覆盖真实文件 | 该文件 5 项全绿（含在离线 1731 例里：`round7/offline3.xml`） |

## 环境侧（本轮记录，非缺陷）

- **wsl-gent 解释器**：`/usr/bin/python3.9`（客户端口径）、`/usr/bin/python3.6.8`、Cadence XCELIUM 自带
  `/opt/eda/cadence/XCELUMMAIN2309/tools.lnx86/python2.7/bin/python2.7`（2.7.6）。
  **没有** py2.7 的 `python2.7` 命令别名 —— 用探针时请显式给全路径（本轮脚本 `test/artifacts/tmp/r7_linux_client.sh` 就是这么做的）。
- **常驻 fake** 仍在跑：w1 上 `vbfake1/2`（65201/65202）；wsl-gent 侧 5 个真实会话（65121/65200/65122/65401/65402）。
- **两个新用户**（`vbuser1`/`vbuser2`）本轮跑通了五接口 + 两用户共建/接力（见真机报告），说明运维给的账号可用。
