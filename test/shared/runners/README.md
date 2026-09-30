# `test/shared/runners/` —— 运行与复算脚本

- `run_coverage.ps1`：当前准出集合的覆盖率 + fail-fast 门禁。
- `run_main_coverage.ps1`：主覆盖率复算（隔离 `COVERAGE_FILE`，产出 text/json/分支报告与证据包）。
- `run_offline_multi.py`：离线 pytest 多进程 runner；每遇到 work-root 边界就重开 pytest 进程。
- `run_core_multi.py`：`offline/core` 四个 TB 的多进程 runner；每个 case 一个进程。
- `run_package_e2e.ps1`：上层包 E2E 编排（逐套件日志 + `summary.json`）。
- `run_all_http.py`：上层包 HTTP E2E 全量套件。
- `coverage_evidence.py` / `classify_uncovered.py`：覆盖率证据包与未覆盖行自动分类。
- `env_up.py` / `registry_add_user.py`：环境与注册表准备。
- `resident_env_check.py`：**常驻环境自检**（逐个 token 打通 `1+1` + `/health`，失败时打印该实例怎么起）。
- `env_check.py`：**TB 第 1 步专用**——"当前环境是不是我需要的环境"一键检测（宿主/用户/token/SKILL 通道/库与工艺可见性/calibre/spectre/解释器版本；`--base` 走 HTTP、`--work-dir` 走进程内并附 `query`；`--json` 落环境证据，退出码非 0 即环境不对）。用法见 [`../../docs/写TB规范.md`](../../docs/写TB规范.md) §1。
- `check_tb_headers.py`：**TB 注释头核账**（规范 §0）——扫描 `test/{semi,live,offline/core}` 的 TB/探针，校验 3 栏（作者 / 最后改动到分钟 / 依赖），`--emit` 生成补全草案（作者名留空由本人填），`--fail` 预留门禁。
- `bringup_user.sh` / `start_lab_fakes.sh` / `make_run_env_complete.py`：真机实例与 lab fake 的起法（详见 [`../../docs/环境与场景.md`](../../docs/环境与场景.md) §2 与 [`../../reports/internal/环境Runbook-内部.md`](../../reports/internal/环境Runbook-内部.md)）。
- `make_multihop_env.py` / `start_hop_fake.sh`：**多跳（jump/SOCKS5）专项环境**（S15）——生成 `test/artifacts/env/multihop/registry.json`、在 w1-gent 起 65203/`vb-hopfake`；配套 TB `test/live/flows/multihop_jump_tb.py`。
- `start_disposable_ciw.sh` / `stop_disposable_ciw.sh` / `ciw_load_setup.py`：**可丢弃 CIW（注册专项 P4）**——在 wsl-gent 起一个 headless 真 Virtuoso + 注入用最小 daemon（bootstrap `vb-<name>`）；TB 用 `ciw_load_setup.py` 执行 `RBStop() + load(<注册第 4 步生成的 setup>)`，把 CIW 换成注册生成的真实 daemon（`--verify-port/--verify-token` 轮询 `1+2` 确认后才返回 0）。用法见 [`../../docs/环境与场景.md`](../../docs/环境与场景.md) §7。
- `w4_hostkey_cycle.sh`：**w4-gent host-key 轮换（注册专项 P5）**——`status/use-a/use-b/restore` 四个动作，每次输出 `SET=` + `FINGERPRINT=SHA256:…`；首次调用会备份原始 key，`restore` 恢复。部署到 w4 的 `/usr/local/sbin/`（需 sudo），接口见 [`../../docs/环境与场景.md`](../../docs/环境与场景.md) §7。
- `hold_ports.py`：占住一段本机端口，用来复现/回归"机器级端口被占"造成的假红（P-063）。
- `verify_spec_matrix_evidence.py`：拿最新 JUnit 核对 spec 覆盖矩阵每一行的证据文件**这轮到底跑没跑**（产出矩阵 §14）。
- `run_redpins.py`：**红钉 runner**——跑 `REDPINS` 清单里的真机红钉 TB（当前 C06），判定 `RED-PIN-HOLDS / UNEXPECTED-GREEN / BROKEN`；绿了即提醒删红钉/改判（离线红钉由 xfail 天然覆盖，不需要它）。
- `make_bug_cards.py`：生成/刷新 `test/reports/bugs/`（**未关闭缺陷的唯一跟踪视图**：逐条卡片 + README 索引 + 已关闭记录）；`--check` 只校验不写盘。
- `ops_matrix.py`：列出上层包已注册 operation。
- `ops_used.py`：运行上层套件并统计 operation 覆盖。
- `scenario.py`：按场景名驱动的入口。

上述脚本都从**仓库根目录**运行（`parents[3]` / `$PSScriptRoot\..\..\..`），
命令见 [`../../README.md`](../../README.md) 与三级 README。
运行产物一律落 `test/artifacts/{env,evidence,tmp}/`，脚本自身不写仓库根。
