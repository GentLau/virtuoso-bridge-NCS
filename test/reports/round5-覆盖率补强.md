# 第五轮 · 覆盖率补强（离线层，2026-09-23 23:2x）

> 目的：把"语句/分支覆盖最低的几个模块"补上**真实行为**用例——不是凑行数，
> 每条都对应 spec/契约并且能做负控制。补测过程本身也产出 2 条新观察项（P-066/P-067）。
> 数据：`test/artifacts/evidence/round5-cov-uplift/`（离线层独立 `COVERAGE_FILE`，不污染 `cov-main`）。

## 1. 新增用例（3 个文件 / 22 条）

| 文件 | 条数 | 补的是哪个契约 | 关键断言（节选） |
|---|---|---|---|
| `test/offline/unit/test_config_snapshot_edges.py` | 6 | `common/config` 的**进程级快照身份语义**（`init_config` 同路径幂等 / 换路径 `RuntimeError`；`replace_snapshot` 无 path 时的默认绑定；`_freeze`/`_thaw` 对序列的处理） | 同路径二次 `init` 必须**同一对象**；换路径必须报错且不改绑；`snapshot()["xs"]` 是 `tuple`、嵌套映射是 `MappingProxyType`、写它抛 `TypeError`；`snapshot_dict()` 返回可写副本且不反向污染快照 |
| `test/offline/unit/test_workdir_contract.py` | 6（1 条按平台 skip） | `common/paths` 的**工作根契约**（同路径幂等 / 换路径报错 / `force` 才切换；未初始化时所有派生路径必须明确报错；子目录惰性创建；`default_work_dir()` 平台规则） | `work_root/temp_dir/log_dir/artifact_dir/registry_path/config_path/command_log_file` 未初始化时**逐个**抛 `work dir not initialized`；Windows=`APPDATA/virtuoso_bridge`、POSIX=`XDG_CONFIG_HOME/virtuoso_bridge`（按平台守卫） |
| `test/offline/unit/test_maestro_util_edges.py` | 10 | `_maestro_util` 的**读回边界**：多点 Detail CSV（`Parameters:` 行 + 数字 Point 行）、`Parameters:` 未加引号的退化形态、OCEAN 文本非数字列、`skill_alist` 字符串/非法类型、`history_name_for_file` 空名与后缀族、`parse_overall_yield` 数值强转 | 两个 `Parameters:` 行 → 2 个 point 且参数全在；`Parameters:` 未加引号 → 只留第一个参数（**P-067 现状**）；`"x abc 2"` 行被跳过而 `"2 3.5"` 保留；`skill_alist(5)`/`[["a"]]` 抛带名字的 `ValueError` |

## 2. 逐模块前后对比（同一代码状态：合并口径 before vs 离线 after）

> 口径说明：**before** 取本轮较早的**合并**覆盖率数据 `cov-main/coverage-main-before-uplift.json`
> （21:58 生成，含真机包；补测前）；**after** 取本次离线层独立复算
> `round5-cov-uplift/coverage-uplift.json`。这三个模块是纯逻辑/纯文本，真机套件并不额外覆盖它们，
> 因此这个对比是可比的；**总覆盖率**的最终口径以 §3 的合并复算为准。

| 模块 | before 语句 | after 语句 | before 完整分支 | after 完整分支 |
|---|---|---|---|---|
| `common/config.py` | 53/60 = **88%** | **60/60 = 100%** | 8/16 = **50%** | 15/16 = **94%** |
| `common/paths.py` | 45/51 = **88%** | **48/51 = 94%** | 6/10 = **60%** | 7/10 = **70%** |
| `pyapi/packages/_maestro_util.py` | 168/205 = **82%** | **198/205 = 97%** | 86/112 = **77%** | 100/112 = **89%** |

## 3. 总覆盖率（合并口径，已被 `run_main_coverage.ps1` 重算）

| 口径 | 值 | 证据 |
|---|---|---|
| 复算前（基准） | 语句 **15681/17107 = 91.66%**；完整分支 **4859/5834 = 83.29%**（partial 821） | `cov-main/coverage-main-before-uplift.json` |
| **复算后（定版）** | 语句 **15724/17107 = 91.92%**；完整分支 **4886/5834 = 83.75%**（partial 810）；合并指标 89.82% | `cov-main/coverage-main.{json,txt}`（strict：15735/17121 = 91.90%，分支 4889/5840） |

> 复算命令：`powershell -NoProfile -File test/shared/runners/run_main_coverage.ps1`（离线三层 + 真机包 E2E + 注册 + S11 一起 append）。
> 该次运行的两个"失败步骤"是**预期内**的：`offline L0-L2`（11 条有意红）与 `S11 full flow (LVS)`（drc/lvs 受 X 系列口径约束）。

## 4. 负控制与"不是凑数"的证据

* `config`/`paths` 用例：**正向**断言对象身份与异常文案；**反向**做法——把 `init_config` 的"同路径返回同一对象"改成每次重建、
  或把 `work_root()` 的空值改成 `Path.cwd()`，对应用例立刻红（改法见文件内 docstring）。
* `_maestro_util` 用例：正常形态（带引号 `Parameters:` → 两个参数）与退化形态（未加引号 → 丢参数）**成对**存在，
  只用"断言现状"那条不能说明问题——两条一起才能证明"是引号形态决定了解析结果"。
* 三条边界都**不依赖真机**、不依赖顺序（各自的临时目录/快照都在用例内恢复；见 P-064/P-065 的教训）。

## 5. 补测带出的新发现

| ID | 级别 | 一句话 | 已钉的用例 |
|---|---|---|---|
| **P-066** | P3 | `skill_value()` 兜底分支对非 JSON 类型冒 `AttributeError`（`basic.q` 期待 str），错误类型不明确 | `test_skill_value_never_silently_emits_a_wrong_literal` |
| **P-067** | P3 | `parse_detail_csv` 的 `Parameters:` 行只读第一个 CSV 单元格：导出未加引号时逗号后的参数被**静默丢弃** | `test_unquoted_parameters_row_drops_everything_after_the_first_comma`（+ 引号形态的正常用例） |
