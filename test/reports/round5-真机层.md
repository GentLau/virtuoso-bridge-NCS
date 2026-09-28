# 第五轮 · 真机主线回归（r5_live 线）

> 范围：离线三级复跑 + 真机主线（十套包 E2E / 五接口 / 注册 / 多机 role / 规模档 / 真机 pytest）+ 本轮 live 线 TB 修正。
> 执行：r5_live 线 ｜ 2026-09-23 20:4x–21:1x ｜ 环境：文档 §0.3 常驻 8 实例 + 业务面 8127（`resident_env_check`：remote 8/8 通、`/health` 200）。
> 全部证据在 `test/artifacts/evidence/round5-main/`（本轮前缀 `round5-main`）与既有共享路径（复制留档）。

## 1. 结果总览

| # | 项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 离线三层（Windows 客户端 3.12） | **1656 passed / 9 skipped / 651 subtests passed, exit 0** | `round5-main/offline-pytest2.log`、`offline-junit.xml` |
| 2 | 十套上层包 E2E（HTTP 真机） | **10/10 PASS，`all_passed=true`** | `round5-main/run-all-http-results.json`、`test/artifacts/evidence/http-e2e/*.log` |
| 3 | 五接口 × 4 实例 | vblog / vbs11 / vbuser1 / vbuser2 **各 5/5 ok**（skill/command/file/gui/spectre） | `round5-main/cov-remote-real-*.json` |
| 4 | 注册 1–4（半真机，remote） | **deployed（step=4），registry 零写入、无 reservation 残留** | `round5-main/cov-registration-real.log` |
| 5 | S10 真机 pytest（e2e/live） | **6 passed / 4 skipped**（4 skip = `VB_E2E_LOCAL` 未开的 local 例）；`test_full_flow`、`test_paramiko_backend_live` 均 PASS，连跑两轮均绿 | `round5-main/e2e-live-green.log`、`e2e-live-green2.log`（`-v` 具名） |
| 6 | S2 多 role 分主机 | **5/5 ok**（daemon→wsl-gent；command/file→w1-gent；file 往返内容一致） | `round5-main/role-split.json` |
| 7 | S4 规模档（100 fake） | **两轮 100/100，0 串号**，负控制能检出 misroute | `round5-main/scale-100.json` |
| 8 | 压测：混合 6 worker × 6 轮 | **72/72，0 失败 0 重试 0 拒绝**；SSH 进程 8→8、staging 0 残留 | `round5-main/http-stress-6x6.json` |
| 9 | 压测：饱和 24 worker × 3 轮 | **144/144 最终应答，0 失败**；拒绝全部以结构化 `rejected` 计（重试后 100% 完成）；SSH 8→8、0 残留 | `test/artifacts/env/http-stress-sat/evidence.json`、`round5-main/http-stress-saturation.log` |
| 10 | 主覆盖率（cov-main 口径，严格） | **语句 91.65% / 分支 83.25%**（combined 89.52%，62 文件）；默认口径 TOTAL 90% | `test/artifacts/evidence/cov-main/coverage-main-strict.json`、`round5-main/main-coverage2.log` |

## 2. 本轮 live 线 TB 修正（红 → 绿）

spec r22 落地后，**remote role 注册必须带 SSH 凭据**（`src/register/models.py:213` 守卫）。两个"直接调 `RegistrationFlow.apply` 注册远端用户"的 TB 没带 → 注册第一步 `ValidationError`，其中 S10 真机 e2e 整条红。修正与证据：

| # | 文件 | 前（红） | 后（绿） |
|---|---|---|---|
| L1 | `test/live/e2e/test_e2e_live.py` | `ValidationError: role gui is remote: SSH credential (key_dir/key) is required`（`e2e-live-red.log`） | 补 `key_dir`（默认 `~/.ssh`）/`key`（默认 `id_ed25519`，`VB_E2E_KEY_DIR/VB_E2E_KEY` 可覆盖）→ 六步注册到 `committed`；**6 passed / 4 skipped**（`e2e-live-green.log` exit 0；`e2e-live-green2.log` 具名 PASS；第二次跑 bootstrap 已轮换到 65083/e2e-a9306a46 仍绿） |
| L2 | `test/semi/registration/cov_registration_real.py` | 同一根因（同 `ValidationError`，守卫 `src/register/models.py:213`） | 新增 `--ssh-key-dir/--ssh-key`（默认 `~/.ssh`/`id_ed25519`）→ `stage=deployed, step=4`、零 registry 写入（`cov-registration-real.log` exit 0） |
| L3 | `test/offline/unit/test_pyapi_interface_contract.py`（新增） | D2 修复（`91e3e6d`：`VirtuosoInterface.execute_skill` 补 `log_level/log_max_bytes`）此前在 `test/` 下**零引用零覆盖** | 5 个契约用例：`execute_skill` 在 pyapi 接口与中层 `Middle` 协议间同名/同序/同默认值；五个业务接口 `token` 必填 keyword-only；ABC 不可实例化、最小实现可过。负控制（源码副本删 `log_max_bytes`）→ **RED，defect detected**（`pyapi-contract-negative-control.txt`） |
| L4 | `test/offline/unit/test_ssh_edges.py`（时序脆弱用例加固） | 主覆盖率整跑里唯一非预期红：`_close_persistent_shell_locked` 断言被调用 0 次——50ms 真实预算在高负载下让"写出前预算耗尽"分支先命中（合法但不同路径） | 改用确定性桩预算把用例钉在"等待回包超时 → 关 shell"分支；修复前单跑 12/12 绿、修复后 5/5 绿 + 整类 8 passed；**并发整套离线三层负载下循环 100 次 = 0 失败**（`round5-main/l4-stability-100x.log`） |

> L1/L2 是**测试侧跟 spec**（补齐必填字段），不是放松断言；L3 附突变负控制、L4 附 12 次/5 次复跑对照。
> 本线其余改动（L5 覆盖率 runner 的 S11 假动作、L6 S11 layout.read 旧参数、L7/L9 calibre 解析与状态判据、L8 calibre 专用环境+探针）
> 见 [`round5-TB改动清单.md`](round5-TB改动清单.md) §2。

## 3. 本轮 live 线发现（除上述 TB 失配）

1. **`role_split_tb.py` 默认参数与 `scenario-role-split` registry 不符**：TB 默认 `--user roleprobe --token d6af595b…`，registry 里实际只有 `rolesplit`（token `vb-s11`）。裸跑必然 `KeyError: 'roleprobe'`（或换 user 后因错 token 得到 `invalid token` 的假红）。按实际值（`--user rolesplit --token vb-s11`）复跑 → **5/5 ok**。
   建议（测试侧，很轻）：默认值对齐 registry，或启动时从 `--work-dir/registry.json` 读唯一用户。
2. **`test_business_remote_live.py`（S10 第二组用例）不受 r22 影响**：它直接构造 `UserEntry`（不走注册校验），实测 4/4 PASS——说明"注册面要求凭据"与"运行面连接"的边界行为符合预期。

## 4. 结论与未覆盖

* 本线口径下，**除有意钉红的缺陷 TB 外，真机主线全绿**；S10 的 4 个 skip 是 `VB_E2E_LOCAL` 门槛（需要本机/WSL local 模式 + X display），与上一轮同口径，不声称覆盖。
* 多跳 jump/proxy 高压组合、真实 100 台 Virtuoso 属环境缺口（与 spec 覆盖矩阵 §11 X1/X2 一致）。
* 主覆盖率两次实跑的对比、失败步骤归因与 `cov-main` 证据包见 §6（本步不中止，失败清单以脚本末尾"汇总"为准）。

## 5. 首通：calibre 包真机链路（本轮新开，钉住 4 条）

常驻注册表原先**没有任何 `role.command.calibre` 工具事实**、`test/live/packages/` 也没有 calibre 套件 →
新注册的 calibre 包此前**没有真机入口**（P-060）。本轮用独立 work-dir
`test/artifacts/env/s11-calibre`（token `vb-s11cal`，calibre bin 指向
`/opt/eda/mentor/CALIBRE2025/aok_cal_2025.1_16.10/bin/calibre`）+ 独立业务面 **8128** +
新探针 `test/semi/probes/calibre_package_http_probe.py` 把产品路径走通：

| 操作 | 结果 | 证据 |
|---|---|---|
| `calibre.check_env` | ✅ ok：Calibre **v2025.1_16.10**、deck `deck_file_ok` | `round5-main/calibre-check-env.json` |
| `calibre.drc`（s11_inv/inv 的 GDS，1737 rulechecks） | ✅ completed，**36 results**，`DRC_RES.db` 落盘 | `round5-main/calibre-drc.json` |
| `calibre.read_results`（drc） | ❌ 解析垃圾 → **P-059**（逐规则计数空、总数 null、offenders 取头部告警） | `round5-main/calibre-drc.json`、`test/offline/unit/test_calibre_parsers.py`（红） |
| `calibre.lvs`（GDS vs 手写 CDL） | ✅ 跑到 completed（`LVS completed. NOT COMPARED.`，端口/电源网不符 —— 玩具版图 + 手写源网表，符合预期） | `round5-main/calibre-lvs.json` |
| `read_results`（lvs）/ 阻塞轮询 | ❌ verdict 截成 `not`、counts 空 → **P-062**；输入错误时进程已死仍轮询 9+ 分钟 → **P-061** | `round5-main/calibre-lvs.json`、`round5-main/calibre-lvs-fastfail.json`、`test/offline/unit/test_calibre_job_state.py`（红） |

> 结论：**calibre 包能跑（工具/许可/deck/作业都通），但"结果读取"和"失败快退"两处不可用**。
> 4 条已登记（P-059/060/061/062），其中 060 已在本轮临时补齐（专用环境 + 探针），
> 建议固化成常驻条目并补 `test/live/packages/calibre_e2e_tests.py`（入 `run_all_http.py` SUITES）。

## 6. 主覆盖率（cov-main 口径，回填）

命令：`powershell -NoProfile -File test/shared/runners/run_main_coverage.ps1`（隔离 `COVERAGE_FILE`，
不中止；末尾"汇总"给失败步骤）。两次实跑对比：

| 次 | 结果 | 失败步骤 | 说明 |
|---|---|---|---|
| 第 1 次（21:28） | 严格 91.64% / 83.20% | `offline L0-L2`、`S11 full flow (LVS)` | 离线 4 红（3×P-055 + 1 个时序脆弱用例 L4）；S11 步骤用旧 CLI 直接 `rc=2`（L5，等于没跑） |
| 第 2 次（21:54，修正后） | 严格 **91.65% / 83.25%** | `offline L0-L2`、`S11 full flow (LVS)` | 离线 **11 红 = 3×P-055 + 6×P-059/P-062 + 2×P-061**（全部是有意钉的缺陷）；S11 步骤**真正跑了**：lib/schematic/symbol/**layout**/gds 5 项 PASS，drc/lvs 失败的原因是该 token 的注册表没有 `role.command.calibre` 事实（P-060），sim 无网表输入（SKIP） |

> 口径说明：数字来自**当前工作树**（`HEAD=91e3e6d` + 本轮 TB 改动）。离线步骤 rc=1 是**预期红**
> （先红后绿的缺陷钉），不代表测试基础设施故障；第 2 次已无"假动作"步骤。
