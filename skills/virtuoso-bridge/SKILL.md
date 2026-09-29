---
name: virtuoso-bridge
description: "在 Virtuoso 上干活：建库/建 cell、画原理图/符号/版图、导入 Verilog/Verilog-A、跑 Maestro/Spectre/Calibre、导 GDS、截屏、查 SKILL 文档。用户提出任何 Virtuoso/EDA 操作需求时触发——所有操作都是同一个 HTTP 调用：POST http://127.0.0.1:8127/api/operation（端口以实际为准）。"
---

# 怎么用 virtuoso-bridge

一句话：**先确认服务在哪 → 带上 token 发一个 POST → 看返回里的 `ok`**。

## 0. 开工前先问清三件事

| 要什么 | 默认 / 常见值 | 说明 |
|---|---|---|
| 业务服务地址 | `http://127.0.0.1:8127` | 端口是启动参数，可能不是 8127；`GET /health` 有响应就说明服务在跑 |
| token | 用户给的字符串（如 `vb-xxxx`） | 每次请求都要带；**照抄，不要自造** |
| 远端路径 | Linux 绝对路径（`/home/<user>/...`） | 所有操作发生在远端；本机文件要先 upload 上去 |

服务没起、或还没有 token：请用户打开注册页（默认 `http://127.0.0.1:8124/`）走完注册——
页面第 4 步会打印一行 `load("/.../virtuoso_setup.il")`，让用户粘进 Virtuoso 的 CIW；
第 5 步自动做连通性测试；第 6 步保存。**token 在注册过程中确定**，注册页可以查看已注册用户。

### 一次调用长什么样

```bash
curl -s http://127.0.0.1:8127/api/operation \
  -H "Content-Type: application/json" \
  -d '{"operation":"basic.skill.execute","token":"<token>","skill_code":"1+2"}'
```

不知道有哪些 operation：`curl -s http://127.0.0.1:8127/help` 会列出这个进程的全部可用操作名。
带字段的完整清单（按任务分组）在 `references/operations.md`。**不要猜名字。**

> 给人看的配套说明书在 `manual/`：`01-快速开始.md`（最短路径用起来）、`02-参考手册.md`（接口与运维）、
> `03-业务包说明书/`（每个操作的每个参数）。

## 1. 返回怎么读

```json
{"ok": true, "error": null, "value": {}, "steps": [{"name": "...", "ok": true, "detail": {}}]}
```

`steps` 默认只在失败时出现；成功要看步骤就显式传 `step_details=true`。

| 看哪里 | 含义 | 你要做什么 |
|---|---|---|
| 非 2xx + `{"ok":false,"error":…}` | 请求没走到业务包（JSON/operation/token/Request 错误，或服务拒绝） | 先修请求/服务，不要看业务字段 |
| HTTP 200 + `ok=false` | 业务失败 | 看 `error`，再看 `steps` 里最后一条 `ok=false` 的 `detail` |
| HTTP 200 + `ok=true` | 成功 | 取 `value` / `result` 等业务字段 |

结果主体放在哪，各包略有不同：

- 多数操作：`value`（read 类的内容、write 类的统计都在这里）
- `basic.*`：`result`（原样的 SKILL/命令结果：`status`/`output`/`errors`/`CDSlog` 或 `returncode`/`stdout`/`stderr`/`kind`）
- 截图（文件已落回本机）：`virtuoso.schematic.screenshot` / `virtuoso.gui.screenshot` → `local_path`；
  `virtuoso.symbol.screenshot` / `virtuoso.layout.screenshot` → `value.local_path`
- `virtuoso.skillref.*`：`results` / `plain_text`

`steps[]` 是过程证据：每一步 `{"name", "ok", "detail"}`；
`detail` 里能看到 SKILL 原文、命令 `stderr`、`returncode`、`kind`——**排查失败先看这里**。

命令类结果里的 `kind` 值得记住：

| kind | 含义 | 处置 |
|---|---|---|
| `command` | 真实命令退出码，`returncode` 就是命令自己的 | 看 `returncode`/`stderr` |
| `timeout` | 超时（保留码 124） | 见下面"超时"一条 |
| `transport` | 连不上/断连（保留码 255） | 先查服务与网络 |
| `path` | 远端路径不存在/类型不符（`stderr` 含 `VB-PATH-NOT-VISIBLE:`） | 核对远端路径 |
| `unknown-effect` | 结果未知，**可能已经执行** | 先 read 查现状，别盲目重发 |
| `rejected` | 服务容量拒绝（线程池/通道/单角色上限） | 可稍后重试 |
| `checksum` | 文件校验和不对（`sha256 mismatch`） | 重新传一次 |
| `invalid-token` | token 不认识 | 核对 token |

## 2. 出错先看这几条

| 症状 | 多半是 | 怎么办 |
|---|---|---|
| `invalid token` | token 抄错，或这个用户没注册 | 找用户核对 token |
| `unknown operation: xxx` | 操作名不对 | `GET /help` 查 |
| 写视图失败 / 报 `locked` | 视图在 Virtuoso 里被别的会话打开，或残留锁文件 | 让用户关掉该视图；详见 `references/troubleshooting.md` |
| 路径类报错 | 给的是本机路径，或远端目录不存在 | 本机文件先 `basic.file.upload`；远端用 Linux 绝对路径 |
| 超时 | 任务没在预算内跑完 | **超时不等于没执行**：先 `read`/`status` 看现状，再决定要不要重发 |
| 截图失败 / 黑屏 | 远端 GUI display 没配好 | 见 `references/troubleshooting.md` |

完整的症状 → 原因 → 处置清单：`references/troubleshooting.md`。

## 3. 干活的套路

1. **读优先**：动手前先 `read` / `list` 看现状；写完再 `read` 一次验证，不要只信 `ok=true`。
2. **一个动作一组命令**：`*.write` 支持一次给一串原子命令，比来回多次快。
3. **文件两头分清**：本机 `C:/...` ↔ 远端 `/home/...`；上传用 `basic.file.upload`，下载用 `basic.file.download`。
4. **长任务先拿凭据再轮询**：Maestro 默认非阻塞，先拿到 `history`；Calibre 先拿 `job_id`，再 `status` / `read_results`。
5. **CIW 里看不到返回值**：`basic.skill.execute` 的结果只回到你这里；要让用户也在 CIW 里看到，SKILL 自己 `printf`。
6. **没有现成操作就直连底层**：`basic.skill.execute`（跑 SKILL）和 `basic.command.run`（跑 shell）是万能逃生口。

## 4. 任务索引（字段清单见 `references/operations.md` 对应章节）

| 想干什么 | 看哪节 |
|---|---|
| 建库、建 cell / view、分类管理 | 库与 cellview |
| 画原理图：放器件、连线、引脚、标注、改名、改参数 | 原理图 |
| 生成或手改 symbol（含 pin 顺序、选择框） | 符号 |
| 画版图、放 via/mosaic、控制显示、导 GDS | 版图 |
| Maestro/ADE：改配置、跑仿真、读结果、看 history | Maestro |
| 独立 Spectre 仿真、读 PSF、量指标、导出 CSV | Spectre |
| Calibre DRC / LVS / PEX 与结果导出 | Calibre |
| 导入 Verilog / Verilog-A，或写文本视图 | Verilog / Verilog-A |
| 截屏、列窗口、发按键、自动关弹窗 | GUI |
| 查 Cadence SKILL 函数文档 | SKILL 文档查询 |
| 端到端照抄流程（建反相器、跑仿真、出 GDS…） | `references/recipes.md` |

## 5. 三条铁律

1. **不要猜**：operation 名用 `GET /help` 查，字段用 `references/operations.md` 查。
2. **写操作先确认目标存在**（库/cell/view），写完再读一次验证。
3. **超时不等于没发生**：写操作超时后先查现状，再决定是否重发。
