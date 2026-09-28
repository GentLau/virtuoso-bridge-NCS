# 环境 Runbook（内部）— 测试侧维护，开发不必读

> **读者**：测试工程师（本目录主人）。 ｜ 2026-09-28 从 `test/docs/环境说明.md` 迁入内部。
> 开发要用的环境信息（用哪个实例、token、怎么自检）看 **[`../../docs/环境与场景.md`](../../docs/环境与场景.md)**；
> 本文件保留：节点全表、密钥组织与回滚、端口/账号、选靶机规则、故障恢复、py2.7 真解释器路径。

> 维护者：测试工程师 ｜ 版本：v1.0 ｜ 最后实测：2026-09-22 17:28
> 环境事实的权威来源：[`doc/report/环境支持.md`](../../../doc/report/环境支持.md)（IT 维护）。
> 本文只写**测试视角**：哪台机器能干什么、怎么连、边界在哪、坏了怎么恢复。

## 1. 拓扑

```text
                                    ┌── 直连 ──────────► vps（114.215.183.227，可选）
本机（Windows / DESKTOP-F143LSD）───┤
   Tailscale 100.123.188.27        └── 直连 lab 网 ──► w1~w4-gent（172.20.170.21~24，本机 WSL）

                                    ┌── glis-desktop（100.123.135.71，用户 ljt03）＝ 中转机
本机 ──经 glis-desktop（ProxyJump）──┴──► wsl-gent（172.18.80.17，用户 Gent）＝ 真实 Virtuoso 靶机
```

`172.18.80.17` 是 glis 上 WSL2 的内部地址，本机不能直连，必须经 `ProxyJump`。

## 2. 节点清单

| 节点 | 系统 | 账号 / 密钥 | 角色 | 测试用途 |
|---|---|---|---|---|
| 本机 | Windows | 本仓库 `.venv`（Python 3.12.10） | 客户端 / 控制端 | 跑离线/半真机/真机各级、HTTP 服务端、注册服务、发压 |
| glis-desktop | Windows（Tailscale） | `ljt03`，默认密钥 | 中转机 | 仅作跳板；不作为测试靶机 |
| wsl-gent | AlmaLinux-8（WSL2，内核 6.6.114.1） | `Gent`，`id_ed25519` | **真实 Virtuoso 靶机** | 真机五接口、注册 1–4 步、CDS.log 增量、业务包 E2E |
| w1-gent | AlmaLinux 8.10（Python 3.9） | `dev`，`lab_ed25519` | lab 靶机 | fake Virtuoso 宿主（`/opt/fake/virtuoso`） |
| vbuser1 / vbuser2 | wsl-gent 上的**普通用户**（uid 1001/1002，cadshare 组） | 本机密钥，`ssh -o User=vbuser1 wsl-gent` | 真多用户靶机 | S13：各自 headless Virtuoso（Xvfb :100/:101）+ 各自 daemon 65401/65402；与 Gent 共享 `/project/libs`（umask 0002 + setgid，组内可互改） |
| w2-gent | Ubuntu 22.04（Python 3.10） | `dev`，`lab_ed25519` | lab 靶机 | 备用客户端 / 通用 Linux 资源 |
| w3-gent | Ubuntu 22.04 | `dev`，`lab_ed25519` | lab 靶机 + 跳板 | 备选客户端；另有 `w3-socks`（DynamicForward 1080） |
| w4-gent | Ubuntu 22.04 | `dev`，`lab_ed25519` | lab 靶机 | python2 兼容垫片宿主 |
| vps | Debian（内核 6.1.0-51） | `root`，`id_ed25519_vps` | 弱机 | **仅**低并发 fake daemon 靶机 |

lab 四台各有一个 `labns` 网络命名空间（独立 IP/端口/进程/文件系统），但共享同一 WSL 内核与内存池：
**CPU/内存预算按"一台 VM"计算**，不要同时在多台上压测。

## 3. 本轮实测（2026-09-22 17:28）

### 3.1 SSH 密钥组织（2026-09-23 整理）

| 私钥 | 指纹（comment） | 授权到 | 用途 |
|---|---|---|---|
| `~/.ssh/id_ed25519` | `XRx7iNdW…`（openclaw-workspace） | wsl-gent 的 `Gent` / `vbuser1` / `vbuser2` | 本机对所有 wsl-gent 账号的默认钥 |
| `C:\wsl\shared\keys\lab_w1_ed25519` … `lab_w4_ed25519` | 各自独立（comment `lab-w1`…`lab-w4`） | **各自那台** lab 主机的 `dev` | **测试默认**：`ssh wN-gent` 走本机自己的钥（一台失守不波及其它台） |
| `C:\wsl\shared\keys\lab_ed25519` | `bsUefobn…`（wsl-lab） | w1–w4 全部 | **管理钥**：批量/运维；别名 `wN-gent-mgmt` |
| `~/.ssh/id_ed25519_vps` | `ZJEqeJoz…`（desktop-f143lsd-vps） | vps | vps 专用 |
| `C:\wsl\shared\keys\vbuser2_ed25519` | `swxVxa+V…`（comment `vbuser2`） | wsl-gent 的 `vbuser2` | **vbuser2 的独立钥**（与 Gent/vbuser1 不共享 → 用来测"独立凭据"路径） |

> 用户侧的设计（2026-09-23 定）：**vbuser1 与 Gent 同款**（同库映射 `/project` + 共用同一把凭据，用于测"复用他人已登记凭据"）；
> **vbuser2 独立**（自有密钥 + 自有的库/工程目录，用于测隔离与"每用户一钥"的正路径）。

- 每台 lab 的 `~/.ssh/authorized_keys` 现在**两行**：管理钥 + 本机钥；改动前备份为 `authorized_keys.bak-20260923`；
- 本机 ssh config 改动前备份为 `~/.ssh/config.bak-r3-keys`；
- 回滚：恢复 config 备份 + 在各 lab 执行 `mv ~/.ssh/authorized_keys.bak-20260923 ~/.ssh/authorized_keys`；
- 私钥权限：WSL 生成在 `/mnt/c` 的钥默认 777，Windows OpenSSH 会拒收 → 需
  `icacls <key> /inheritance:r /grant:r "$env:USERNAME:R"`（已对四把执行）。

> 与"密钥冲突"测试的关系（spec r43 §4/§26/§38）：凭据按**公钥指纹**查重；同一 entry 内不同 role 可用不同 `key`（同用户多把钥）；
> 跨 entry 复用同一指纹需 `enhanced_token`（管理员 token 或任一已登记持有者 token）。四台各持独立钥正好提供"同指纹/异指纹"两种素材。

| 目标 | 结果 | 备注 |
|---|---|---|
| `vps` | ✅ 0.9s | `iZz1iwzbaf5hy6Z`，Debian |
| `100.123.135.71`（glis） | ✅ 2.3s | `GLIS-DESKTOP` |
| `wsl-gent` | ✅ 2.2s | WSL2 内核；`hostname` 返回 `GLIS-DESKTOP`（WSL 默认沿用宿主名），属正常 |
| `w1-gent` ~ `w4-gent` | ❌ 各 8s 超时 | 本机 `wsl -l -v` 显示四台均为 `Stopped`；**不是故障**，用前先启动（见 §7.3） |

本机侧观察（2026-09-22 17:29）：`8124`（`register.server`）与 `8127`（`api_server`）当时**已被残留进程监听**——
这两个是固定端口，跑测前必须按 §8 确认，否则会出现用例失败或“假绿”。

wsl-gent 上的当前事实（`pgrep` / `ss` 实测）：

- 真实 Virtuoso：`/opt/eda/cadence/IC618/tools/dfII/bin/64bit/virtuoso`（pid 369800，日志 `~/virtuoso_11.log`）；
- `vblog` daemon：`127.0.0.1:65121`，token `vb-vblog`，root `/home/Gent/.virtuoso-bridge/vblog`；
- 另有 `65122` 监听（历史注册账号的 daemon，用前先查注册表确认归属）；
- 协议级 fake daemon：`~/.virtuoso-bridge/vbtest/fakevirt`，`127.0.0.1:65081`，token `vb-vbtest`；
- Cadence 安装：`IC618`、`IC231`、`SPECTRE241`、`QUANTUS231`、`SSV231`、`XCELUMMAIN2309`；`python3` = 3.14.6；
- **Python 2.7（真解释器）**：`/opt/eda/cadence/XCELUMMAIN2309/tools.lnx86/python2.7/bin/python2.7`（2.7.6，XCELIUM 自带，**无需 sudo、无需另装**；`hashlib` 因 OpenSSL 不匹配不可用，但 daemon 只用 stdlib 基础模块）。详见 §9。
- **参考 Cadence 环境（完整）**：`/home/Gent/project/test/`（`.cdsinit` + `cds.lib` + TEST_BRIDGE/TEST_LIB 等库）。
- **多用户共享区**：`/project/`（`root:cadshare 2775`）——`libs/` 放共享库、`cds.lib.shared` 是组可写清单（已含 `DEFINE tsmcN65`）；三用户（Gent/vbuser1/vbuser2）共用 `/etc/profile.d/zz-cadence.sh` 的 Cadence 环境。新用户**无 sudo**、读不到 `/home/Gent`（700）。
  真机实例的 run 目录按 [环境与场景.md §2](../../docs/环境与场景.md) 合并该环境生成**真实** `cds.lib`；
  生成脚本 `test/shared/runners/make_run_env_complete.py`（在 wsl-gent 上执行）。
  自检：`ddGetObj("schemtest")`、`ddGetObj("tsmcN65")`、`ddGetObj("TEST_BRIDGE")` 全部回 `dd:0x…`。
- `~/.virtuoso-bridge/` 下存在大量 `<user>` 目录（`vb01`…`vb57`、`e2e-*`、`lc00`…）——
  多用户并存是**设计上的正常现象**，不是垃圾，禁止批量清理。

### 3.2 多跳 / 代理链路（2026-09-23 建成，S15）

| 段 | 事实 | 说明 |
|---|---|---|
| 跳板机 | `w3-gent` = 172.20.170.23，账号 `dev` | 本机 ssh config 里 `w3-gent` 带 `IdentityFile C:\wsl\shared\keys\lab_w3_ed25519` |
| 目标机 | `w1-gent` = 172.20.170.21，账号 `dev` | 用 `lab_w1_ed25519`；两跳链路 Windows→w3-gent→w1-gent |
| 直连对照 | 同一目标机直连时 `SSH_CONNECTION` 客户端 IP = `172.20.160.1`；经跳板 = `172.20.170.23` | **这就是 S15 的判据**（能区分真跳板 vs 直连） |
| SOCKS5 | `ssh -N -D 127.0.0.1:11080 w3-gent`（S15 的 TB 自己拉起/收尾） | 产品侧 role `proxy=socks5://127.0.0.1:11080`，走 `PySocks`（Windows 客户端需 `pip install PySocks`） |
| 多跳专用 fake | w1-gent `labns` 内 **65203**，token `vb-hopfake`，拉起脚本 `test/shared/runners/start_hop_fake.sh` | 常驻 65201/65202 的 token 是 `vb-lab11/vb-lab12`，**daemon 令牌必须与注册表 token 一致**，否则 skill 返回 `invalid token`（踩过） |

### 3.3 注册表热重载 / standalone 业务面的口径（P-048 结论，2026-09-24）

spec《其他/多用户与注册》§1 与《顶层/控制面与业务面》§1.1 明确：注册表**启动导入一次、运行期不自动读文件**，
由 `POST /api/process/reload`（管理权限，控制面）**显式触发**重导。所以"热重载要手动发命令"是设计语义，不是缺陷。

| 部署形态 | 改 `registry.json` 后怎么生效 |
|---|---|
| **标准形态**（`server.supervisor` 控制面 spawn 业务面） | 发 `POST /api/process/reload`（`Authorization: Bearer <admin>`）；**立即生效**，无需重启 |
| **我们测试台的 standalone 形态**（`python -m server.api_server --port ...`） | **没有控制通道 → 必须重启该业务面**（常驻环境 8127/8128/8131 都是这一形态） |

> 端到端语义 TB：`test/offline/integration/test_supervisor_process.py::test_http_reload_picks_up_registry_file`
> （不 reload → 新 token 无效；reload 后立即可用）。
> **跑测提醒**：改了 `src/` 或注册表之后，**先重启 standalone 业务面再验**，否则测到的是旧进程里的实现
> （2026-09-24 实测：不重启会让"已修好的功能"看起来完全没生效）。

## 4. 服务端口与账号约定

| 端口 | 用途 | 备注 |
|---|---|---|
| `8127` | 顶层业务 HTTP（`server.api_server`） | 业务包 E2E / 压测默认入口 |
| `8124` | 注册服务（`register.server`） | 注册页与六步注册 |
| `651xx` | 远端 daemon（每账号一段） | 例：`vblog`=65121、`vbtest`=65081、lab fake=65131 |

- 账号名 `[a-z0-9_-]+`（`vb01`、`vblog`、`lc00`…），禁止空格、`/`、`~`；
- token 与账号一一对应，写在注册表里；**token 不得出现在测试报告正文**，引用时只写账号；
- 本版代码不再读 `profile` / `VB_*` / `.env`：注册与路由统一消费 `registry.json`，
  TB 必须显式传 `--work-dir` 与 `--token`。

## 5. 选靶机规则

1. 默认靶机 = `wsl-gent`（真实 Virtuoso / Spectre 能力）。真机 TB 必须在这里跑。
2. 需要"假目标"时用 lab `w1-gent` 的 fake Virtuoso（协议真、CIW 假），或 wsl-gent 上的 `vbtest` fake daemon。
3. `vps` 只在 lab 不可用、且并发 ≤ 低档时使用；**禁止**作为 100 用户高压靶机。
4. 本机 Windows 可执行 100 用户级远端压测，但必须隐藏子进程控制台、限制建连并发，
   并在前后做 `ssh.exe`/`conhost` 进程盘点。
5. 压测前确认没有别人正在跑同一靶机（见 §8 检查清单）。

## 6. 健康检查

```powershell
ssh -o BatchMode=yes -o ConnectTimeout=15 vps "hostname"
ssh -o BatchMode=yes -o ConnectTimeout=15 100.123.135.71 "hostname"
ssh -o BatchMode=yes -o ConnectTimeout=20 wsl-gent "hostname; pgrep -c virtuoso"
foreach ($h in 'w1-gent','w2-gent','w3-gent','w4-gent') { ssh -o BatchMode=yes -o ConnectTimeout=8 $h "hostname" }
wsl.exe -l -v
```

通过标准：全部返回主机名（lab 需先启动发行版）。检查完记得更新本文档首部的"最后实测"。

## 7. 故障与恢复

**lab 主机整机停机（w1–w4 空闲自动 suspend）** —— 2026-09-23 第三轮实测恢复路径：

1. 本机 `wsl -d w1-gent -u dev -- bash -lc 'echo boot-ok; sudo -n true'` 唤醒发行版；
2. 把 [`../../shared/runners/start_lab_fakes.sh`](../../shared/runners/start_lab_fakes.sh) 拷进发行版执行
   （脚本内含 `sed -i 's/\r$//'` 需要时先做，避免 CRLF 破坏 bash），它会在 `labns` 里重建
   `vb-lab11/65201` 与 `vb-lab12/65202` 两个 fake；
3. **必须在 `labns` 里查监听**：`sudo -n ip netns exec labns ss -ltn | grep 6520`（默认 netns 看不到）；
4. fake 常驻即保持发行版不休眠；随后 S3/S6 等场景可直接跑。

**多跳（S15）环境恢复**：`w3-gent`/`w1-gent` 任一停机后按上面的方式唤醒，然后
① 多跳专用 fake：`Get-Content test/shared/runners/start_hop_fake.sh -Raw | ssh w1-gent-mgmt "bash -s"`
（**注意把 CRLF 去掉**，否则 bash 报 `$'\r'`；脚本落到 65203/`vb-hopfake`）；
② 业务面：`python -m server.api_server --port 8131 --work-dir test/artifacts/env/multihop`（改过注册表必须重启）；
③ 自检：`PYTHONPATH=src python test/live/flows/multihop_jump_tb.py --work-dir test/artifacts/env/multihop --base http://127.0.0.1:8131/api/operation`，期望 11/11。

**多用户实例（vbuser1/vbuser2）重启**：

```bash
scp test/shared/runners/bringup_user.sh vbuser1@wsl-gent:~/
ssh -o User=vbuser1 wsl-gent 'bash ~/bringup_user.sh vbuser1 65401'   # vbuser2 同理 -> 65402
```

脚本会重写 `setup/virtuoso_setup.il` 与 `run/{cds.lib,.cdsinit}`，然后用 `xvfb-run` 起 headless Virtuoso；
自检：`ss -ltn | grep 6540`、以及用注册表 `test/artifacts/env/multi-user-real/`（业务面 8129）跑 `1+1`。

另：注册表里的 `local_port` 必须**逐用户唯一**（本轮实测 vblog/vbs11 都写 65201 → 第二个用户恒返回
`invalid token`，因为它命中的是别人的隧道）。修法：`local_port` 取与该用户 daemon 端口不同的空闲值。

**排查顺序**（远程链路）：先 `ssh 100.123.135.71`，再 `ssh wsl-gent`。
都超时 → 7.2；只有 wsl-gent 超时 → 7.1。

- **7.1 WSL 发行版停止**（中转机在线）：`ssh 100.123.135.71 "wsl.exe -l -v"` 确认 `Stopped`，
  再 `ssh 100.123.135.71 "wsl.exe -d AlmaLinux-8"` 启动，最后重跑 §6。
- **7.2 glis-desktop 整机离线**：需现场开机（局域网不同网段，无远程路径）；开机后 WSL 不会自启，按 7.1 处理。
- **7.3 本机 lab 身份 IP 丢失**：`wsl -d w1-gent -- true` 触发启动，
  `wsl-lab-netns.service` / `wsl-lab-boot.service` 会重建 `labns`；不要手改 `labns`/`br-lab`/veth。

## 8. 跑测前检查清单

1. `Get-NetTCPConnection -State Listen -LocalPort 8124,8127` —— 必须为空（残留服务会让用例失败或假绿）；
2. 目标 daemon 端口（如 65121）已被监听，且注册表里对应账号存在；
3. 靶机上没有并发跑测（`pgrep -af pytest|stress`）；
4. 磁盘/内存余量足够本次规模（压测大小 ≤ 一台 VM 的预算）；
5. 跑完按 [写TB规范.md §5](../../docs/写TB规范.md) 落盘，并做资源盘点（隧道、端口、临时目录、`ssh.exe` 数）。

## 9. Python 2.7 真解释器（2026-09-23 建成）

**结论：不用装**——wsl-gent 上 Cadence XCELIUM 自带 py2.7，免 sudo 直接用。

| 项 | 值 |
|---|---|
| 解释器 | `/opt/eda/cadence/XCELUMMAIN2309/tools.lnx86/python2.7/bin/python2.7` |
| 版本 | `Python 2.7.6` |
| 被测脚本落点 | `~/project/vblog/tb-sandbox/py27/`（daemon 脚本副本 + 探针 + `tmp/`） |
| 探针 | `python3 test/semi/probes/py27_daemon_probe.py --py27 <上面的解释器> --daemon <daemon 副本> --port 6603 --token py27-probe --out <证据 json>` |
| 已验证 | 2026-09-23 **5/5 PASS**：启动监听 / token 拒绝 / log_level 拒绝 / log_max_bytes 拒绝 / 看门狗超时；证据 `test/artifacts/evidence/py27-daemon-probe.json` |
| 已知阻断 | `ramic_bridge_daemon_27.py` 缺 `# -*- coding: utf-8 -*-` → 真 py2.7 下 SyntaxError 起不来（问题登记 P-043）；探针是在远程副本补该行后跑通的 |
| 不覆盖 | 需要 CIW 的 SKILL 执行链路（daemon 的 stdin 帧通道）；那部分属真机 CIW 场景 |

---

## 10. 恢复记录：2026-09-28「恢复日常环境」

**触发**：用户问"现在是日常环境吗" → 自检 `remote 实例 4/8 通`（calprobe/vbs11/vbuser1/vbuser2 全 `SKILL execution timed out`，
daemon 端口在监听、CIW 进程也在，属"CIW 侧 bridge 失联"）；同时客户端还挂着 3 个非日常业务面（8128/8129/8131），
wsl-gent 上还有 vbe2e / vbmu2 / vbmu3 三台非日常 CIW + 一个 65082 孤儿 daemon，w1 上还有 S15 专用的 hopfake(65203)。

**动作与结果**（脚本留在 `test/artifacts/tmp/`，可复用）：

| 步骤 | 命令/脚本 | 结果 |
|---|---|---|
| 1 | `restore_vbs11_calprobe.sh`（Gent 身份，用 vblog 的 1016092 继承 Cadence 环境，`:11` display） | 65200 / 65122 重新 LISTEN；`env_check` 对 `vb-s11` 与 PDK token 均通过（`lib-tsmcN65` 可见） |
| 2 | `restore_user_instance.sh vbuser1 65401` / `vbuser2 65402`（各自身份；先杀旧 `-cdslib ./cds.lib` 的 virtuoso，再 `bringup_user.sh`） | 65401 / 65402 重新 LISTEN；两个 token 的 `env_check` 通过且都能看到共享库 `serdes_rx` |
| 3 | 客户端停 8128 / 8129 / 8131（按 PID 精确停） | 只剩日常业务面 **8127** |
| 4 | `cleanup_gent_extras.sh`（精确 pkill：65082 孤儿、vbmu2/3、(65210/65211)、vbe2e） | wsl-gent 只剩日常 5 个真实实例的 virtuoso；6xxxx 监听 = 65081/65121/65122/65200/65401/65402 |
| 5 | w1 上 `kill 7152 7151 7148`（hopfake） | 65203 消失，65201/65202（vbfake1/2）保留 |

**最终自检**：`resident_env_check.py` → `remote 实例 8/8 通；skip 1`，`/health OK`，**rc=0**；
`cov_remote_real.py --token vb-vblog` → 五接口 5/5 通过（该 TB 已在 2026-09-28 自行接入 `require_environment`，
输出里能看到 environment 段全绿）。

**经验**：

1. "daemon 在监听但 SKILL 超时" = CIW 侧 bridge 丢了 → **重启该实例的 Virtuoso**（不要只重启 daemon）；
2. 用户实例用 `bringup_user.sh` 恢复（它会重建 run 目录 + `.cdsinit`，自动 load setup IL）；
3. Gent 侧实例用 `start_real_virtuoso.sh <run-dir> <cds.lib> <display> [ref-pid]`，`ref-pid` 传一个**正在跑的**
   Virtuoso（继承 `PATH/LD_LIBRARY_PATH/CDS_LIC_FILE/…`），display 可复用 `:11`；
4. 恢复后必须跑一次 `resident_env_check.py` + 一个真机 TB（本次用五接口）才算确认，不要只看端口。

### 10.1 追加经验（2026-09-28 晚：改造 TB 时又踩到的）

1. **重启用户实例必须"按 PID 杀干净"**：只 `pkill -f '<virtuoso 的某段命令行>'` 可能漏（例如老的
   calprobe 实例是用 `-log /home/Gent/virtuoso_calprobe.log` 起的，没有 `-cdslib` 段）。
   漏杀的后果：旧 **daemon 仍占着端口**（65401），新实例看起来"起来了"（端口在听）但 SKILL 永远超时。
   正确姿势：先 `pgrep -au <user> -f 'ramic_bridge_daemon_3.py 127.0.0.1 <port>|dfII/bin/64bit/virtuoso'`
   列出，再按 PID `kill -TERM`（不退出就 `kill -9`），确认端口释放后再跑 `bringup_user.sh`。
   脚本：`test/artifacts/tmp/hard_restart_user_instance.sh`。
2. **旧实例留下的编辑锁会挡住新会话的写**：症状 `schematic view <lib>/<cell>/schematic is locked by another session`。
   处置：确认锁的 owner pid 已死（或就是那个孤儿实例）→ 杀掉孤儿实例 → 删掉 `<cellview>/sch.oa.cdslck*`。
   预防：TB 用**带 run-id 的 cell 名**（本仓库示例：`design_iterate_tb --tag`、ADC/多用户 TB 的 `--tag`）。
3. **`layout.gds` 可能把导出会话挂死**（P-075）：XStream 在导出者会话里弹出**模态**
   `"Stream out translation complete"`，之后该会话的 SKILL 全部 30s 超时；`gui.auto_dismiss` 关不掉，
   只能重启实例。取证：`xwininfo -display <该实例 DISPLAY> -root -tree | grep -E 'Stream|XStream'`。
   回归探针：`test/semi/probes/gds_then_skill_probe.py`（导出后同会话 `1+2` 必须还能通）。
4. **`spectre.run` 可能永不返回**（P-076）：spectre 已 0 error 跑完，但 HTTP 请求 >25min 不返回、
   `/health` 的 `in_flight` 一直不降；客户端杀进程也救不回那个线程 → **重启业务面**才能清（本次已做）。
   排查顺序：① `in_flight` ② 远端 run 目录里 `spectre.out` 是否已 `completes with 0 errors`
   ③ 双侧有没有 ssh/scp/tar 进程（本次没有 → 阻塞在中间层 Python 路径）。
5. **改了 `src/` 就要重启业务面**：standalone `api_server` 只在启动时导入代码。今天 8127 还是
   4 天前（09-24）的进程，导致 TB 按**新** `pos` 口径发请求、服务端按**旧** `x/y` 校验，报
   `command 0 invalid: 'x'` —— 看着像 TB 坏，其实是业务面过期。
