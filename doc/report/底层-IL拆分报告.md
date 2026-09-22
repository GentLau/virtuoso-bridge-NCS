# 底层 IL 拆分报告：`ramic_bridge.il` → 核心 + `ramic_bridge_ui.il`

> 日期：2026-09-21
> 报告人：底层 SKILL 语言工程师
> 范围：仅 `src/bridge/resources/*.il`。引擎侧 Python 与测试**不在**本次改动范围内——其所需改动见 §6，本文只报告不实施
> 状态：**IL 侧完成并验证；引擎侧未接线**。接线完成前，新部署不再安装监视器 UI（安全降级，见 §5）

## 1. 结论摘要

- `ramic_bridge.il` 655 → **312** 行：只保留 daemon 生命周期、IPC 帧协议、CDS.log 增量与 identity 落盘；新增 `ramic_bridge_ui.il` **375** 行承载 CIW 监视器、banner 菜单与纯 CIW 辅助过程。
- 搬移是**逐字节**的：被移区块 SHA-256 搬移前后一致（`815d298ebb8e33a632eadad1f29db9bdf4719754ad601d212cd63138d1000768`），351 行中只有 1 行注释被有意改写。
- 依赖**单向**：UI → 核心。核心 → UI 只有 3 处带守卫的重绘钩子（`ramic_bridge.il:158 / 185 / 200`）。
- **未接线**：`virtuoso_setup.il` 仍只 `load` 核心文件 → 新 CIW 会话不会出现 RAMIC 菜单/监视器（§5）。
- 本次越权改动的 3 个引擎文件 + 2 个测试文件 + README 已全部回退，新建的测试文件已删除（§8）。

## 2. 拆分边界

| | 核心 `ramic_bridge.il` | UI 辅助 `ramic_bridge_ui.il` |
|---|---|---|
| 行数 | 312 | 375 |
| 职责 | daemon 生命周期、IPC 帧协议、CDS.log 增量、identity 落盘 | 监视器表单、banner 菜单、状态回显、CIW 清屏 |
| Skill 链路是否必需 | 是 | 否（纯辅助，缺失只影响可观测性） |

### 2.1 核心文件结构

| 行 | 内容 |
|---|---|
| 1–12 | 文件头：图例 + 指向 UI 伴随文件的说明（含单向依赖声明） |
| 16–22 | 注入型配置全局量（`RBDPath` / `RBPython` / `RBPort` / `RBIdentityPath` / `RBDToken` / `RBTempDir` / `RBDLogPath`，全部 `unless(boundp(...))` 保护） |
| 23–29 | 会话内开关：每请求指令 `RBDLogOn` + `RBLocal` / `RBEcho` / `RBDLog` |
| 31–52 | 运行时状态：`RBIpc`（33）、`RBStderrBuf`（36）、`RBLast*`（42–46）、`RBStat*`（50–52） |
| 54–56 | identity 落盘说明（供注册第 5 步读回） |
| 57 | `RBWriteIdentity()` |
| 68 | `RBIpcDataHandler()`：`evalstring("(progn …)")`、STX/NAK 帧、日志开关前缀判定、值帧与 meta 帧合并为单次写入 |
| 123 | `RBIpcErrHandler()`：banner/stat 分词解析、ready 通告、identity 落盘 |
| 189 | `RBIpcFinishHandler()`：退出状态，仅非零退出回吐 stderr |
| 204 | `RBStart()`（`ipcBeginProcess`） |
| 268 | `RBStop()` |
| 279 | `RBStopAll()`（UID 域强杀） |
| 312 | 文件末尾自动 `RBStart()` |

### 2.2 UI 辅助文件结构

| 行 | 内容 |
|---|---|
| 1–17 | 文件头：来源、装载顺序依赖、护栏说明 |
| 18–19 | `if(boundp('RBPort) then progn(` —— 整块护栏 |
| 21–215 | `RBMonitor` 表单：构件与布局（`hiCreateAppForm` 在 166 行） |
| 223–237 | `RBMenuInstalled` 守卫的 banner 菜单 |
| 249 | `RBMRefresh()` |
| 326 | `RBMApply()` |
| 351 | `RBFormatUptime()` |
| 367 | `RBPrintEmptyLines()` |
| 373–375 | `else` + 未装载提示 + 收尾括号 |

## 3. 依赖方向与装载顺序契约

1. **UI → 核心（必需）**：UI 读 `RBPort / RBLocal / RBEcho / RBDLog / RBDLogPath`，回调调用 `RBStart() / RBStop() / RBStopAll()`，全部定义在核心文件。
2. **核心 → UI（唯一钩子，3 处）**：`ramic_bridge.il:158 / 185 / 200`，全部形如 `when(boundp('RBMonInstalled) errset(RBMRefresh()))`。UI 不在场时静默跳过，不影响 daemon。
3. **装载顺序**：核心先、UI 后；`virtuoso_setup.il` 必须按此顺序生成两条 `load()`。
4. **反向保护**：UI 整块被 `if(boundp('RBPort) then progn(…) else printf(…)` 包住。只 load UI（或顺序颠倒）时只打印一行提示、不安装任何构件，不会留下"菜单在、回调全错"的半成品。
5. **重载语义**：老会话（`RBMonInstalled` / `RBMenuInstalled` 已为 `t`）重载时表单与菜单被守卫跳过，`RBMRefresh` / `RBMApply` / `RBFormatUptime` / `RBPrintEmptyLines` 的过程体照常刷新——与拆分前一致。

## 4. 验证证据

| 项 | 方法 | 结果 |
|---|---|---|
| 搬移保真 | 搬移前后对被移区块取 SHA-256 | 一致：`815d298ebb8e33a632eadad1f29db9bdf4719754ad601d212cd63138d1000768` |
| 内容对账 | 新 UI 文件与原文件 302–652 行逐行比对 | 351 行中仅 1 行不同（有意改写的注释：`Reloading ramic_bridge.il` → `Reloading this file`） |
| 核心对账 | 新核心与 `git HEAD` 逐行比对（跳过文件头） | 298 行零差异；尾部为自动启动注释 + `RBStart()` |
| 语法护栏 | 括号平衡状态机（跳过字符串与注释） | 两文件 depth=0、无未闭合字符串（`git HEAD` 原文件同为 0） |
| 现有门禁复跑 | `python -m pytest test/unit/test_log_no_fetch.py test/unit/test_new_middle.py test/unit/test_tunnel.py -q` | 16 passed（三个文件分别校验核心 `.il` 静态内容与部署落盘） |

> 接线状态下（引擎侧改动尚未回退时）另跑过：`test/unit` 全量 exit 0，`test/scenario test/integration` 全绿，本地部署冒烟产出"globals → `load(核心)` → `load(UI)`"的 setup.il。这些结论只对 §6 的接线方案有效，不代表当前仓库状态。

## 5. 当前系统状态（唯一阻塞项）

- 引擎侧未接线：`deploy_files()` 只上传 `ramic_bridge.il`，`generate_setup_il()` 只生成一条 `load()`。
- 后果：**新部署/新 CIW 会话不会安装 RAMIC 监视器**（无菜单、无表单）。daemon 启动、Skill 执行、CDS.log 增量、注册第 5 步 identity 校验均不受影响。
- 不会报错：核心文件已无任何 UI 引用（静态检查覆盖）；UI 文件即便被手工 `load` 也只是打印一行提示。
- 解除条件：完成 §6 接线。

## 6. 引擎侧交接清单（仅报告，未实施）

| # | 文件 | 需要做的事 |
|---|---|---|
| 1 | `src/common/remote_paths.py` | 新增 `ui_il_path(user, root=None)` → `<root>/<user>/ramic/ramic_bridge_ui.il`，并加入 `__all__` |
| 2 | `src/common/setup.py` | `generate_setup_il()` 增加关键字参数 `ui_il: str \| None = None`；在 `load("<核心>")` **之后**追加 `load("<UI>")`；传 `None` 时保持只加载核心 |
| 3 | `src/common/deploy.py` | 把 `ramic_bridge_ui.il` 与核心一起部署（本地 `write_bytes` / 远端 `upload_text`），并把 `ui_il=` 传给 setup 生成器 |
| 4 | 部署顺序 | `virtuoso_setup.il` 必须**最后**写盘：这样 CIW 一旦能看到新 setup，两个 `.il` 必然都已就位，不会 `load` 到缺失文件 |
| 5 | 打包 | 无需改动：`pyproject.toml` 的 package-data 为 `*.il` 通配，新文件自动随包发布（已核对，未修改） |

可选测试断言（本人写过、已随回退删除，需要时可交回原文）：

1. `generate_setup_il(..., ui_il=...)` 产出两条 `load()` 且核心在前；
2. 本地模式 `deploy()` 后 `<root>/ramic/` 同时存在两个 `.il`；
3. 静态护栏：核心无 `hiCreate*` / `RBMonitor`；UI 无 `ipc*` / `evalstring` / `hiFlushLogFile`；核心 3 处钩子必须同时含 `boundp('RBMonInstalled)` 与 `errset(`；两文件括号平衡。

## 7. 已知缺陷（随块搬迁，本次未修）

| 问题 | 新位置 | 影响 |
|---|---|---|
| `Local connect only` 是死开关：`RBStart()` 已固定 `127.0.0.1` | UI 106 / 261 / 331–332；核心 204 起的 `RBStart()` | 勾选只触发一次无意义重启；未收到 banner 时界面显示 `0.0.0.0:<port>`，与真实绑定不符 |
| Apply → `RBStop()` → `RBStart()` 重启竞态：`RBStop()` 不重置 `RBIpc`，紧随的 `RBStart()` 可能判定 "already running" 直接返回 | UI 344–345；核心 268 `RBStop()` | 端口/日志开关的改动静默不生效 |
| `RBMRefresh()` 无条件回写控件，而 `[RB-stat]` 约 1 Hz 触发刷新 | UI 318–321 | 用户正在输入的端口值可能被覆盖 |
| IL→daemon 值帧未转义（`%L` 原样入帧） | 核心 115（`RBIpcDataHandler`） | 返回值含 RS(0x1e) 会截断帧；属协议变更，需与 daemon 同步（见 `spec/design-concepts/底层/6-日志返回设计标准.md` §6.3） |
| 历史包袱：`RBMState` 已不参与布局仍被创建；`RBDLogPath` 为空时按钮显示 `Daemon log ()` | UI 46 / 304；UI 127 | 仅外观与冗余 |

## 8. 变更与回退记录

**保留（本人职责范围内，仅 `.il`）**

- `src/bridge/resources/ramic_bridge.il`：+10 / −353（新增文件头说明；删除 UI 段 351 行；合并一处多余空行）
- `src/bridge/resources/ramic_bridge_ui.il`：新增 375 行

**已回退（越权改动）**

| 文件 | 回退内容 |
|---|---|
| `src/common/setup.py` | `ui_il=` 参数、第二条 `load()`、docstring 补充 |
| `src/common/deploy.py` | `il_assets` 双文件部署、`ui_il=` 传参 |
| `src/common/remote_paths.py` | `ui_il_path()` 与 `__all__` 条目 |
| `test/unit/test_new_middle.py` | import、`ui_il_path` 断言、setup 顺序断言、新用例 |
| `test/unit/test_tunnel.py` | 本地部署两文件断言 |
| `README.md` | 架构树一行 |
| `test/unit/test_bridge_il_split.py` | 整文件删除（本人新建） |

回退方式：先记录每个文件的 `git diff --numstat`，逐个复核"改动行数与本人记录完全一致"后才回退；6 个文件全部命中，未触碰他人正在修改的文件（`ramic_bridge_daemon_3.py` / `ramic_bridge_daemon_27.py` / `src/transport/middle.py` 等在途改动保持原样）。

残留：`test/unit/__pycache__/test_bridge_il_split.cpython-312-pytest-9.1.1.pyc`（删除被沙箱策略拦截；已被 gitignore，不影响仓库状态）。

## 9. 复算命令

```powershell
# 1) 两文件行数与锚点
(Get-Content src/bridge/resources/ramic_bridge.il).Count      # 312
(Get-Content src/bridge/resources/ramic_bridge_ui.il).Count   # 375

# 2) 核心改动面（应只有文件头新增与 UI 段删除）
git diff --stat -- src/bridge/resources/ramic_bridge.il        # +10 / -353

# 3) 现有引擎侧门禁（读 .il 静态内容 / 验证部署落盘）
python -m pytest test/unit/test_log_no_fetch.py test/unit/test_new_middle.py test/unit/test_tunnel.py -q
```

接线完成后建议追加：`generate_setup_il(..., ui_il=…)` 的两条 `load()` 顺序断言、本地 `deploy()` 的两文件落盘断言，以及 §6 列出的静态护栏。
