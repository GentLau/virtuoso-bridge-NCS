# Testbench（test/tb/）

**这里是可执行的真实环境 Testbench（TB），不是 pytest 用例。** 它们需要真机环境（本机 / wsl-gent / vps）才能运行，
pytest 用 `test_*.py` 命名收集，这些文件不以下划线测试名开头，因此**不会被 `pytest` 自动收集**（设计如此）。

约定：

- TB 只做"跑真环境 + 收集证据"，判定标准与期望值写在 `doc/report/` 的对应报告里；
- TB 的公共前置（注册表、fake daemon、多 Virtuoso）由 fixtures 脚本准备，不重复实现；
- 需要 host 别名 `wsl-gent`（真实 Virtuoso）与 `vps`（无 Virtuoso，跑 fake daemon）；
- 运行前先同步代码：`tar -czf /tmp/src.tgz -C . src test && scp /tmp/src.tgz wsl-gent:/tmp/`（TB 在 `test/tb/`，路径按 `test/tb/xxx.py` 调用）。

| TB | 覆盖内容 | 需要环境 |
|---|---|---|
| `unit` 之外的**场景级/并发级** TB ↓ | | |
| `smoke_user.py` | 单用户五个接口逐阶段计时（skill/command/upload/download） | wsl-gent |
| `role_split_cross_host.py` | T2：五 role 跨主机投送（daemon/gui 在 wsl，command/file/spectre 在 vps） | wsl-gent + vps |
| `role_mixed_mode.py` | T3：同一 token 内 local/remote 混合（客户端在 wsl-gent） | wsl-gent + vps |
| `composite_stress.py` | 组合服务压测（上传→skill→命令→下载），Windows/wsl 两种客户端拓扑 | 本机或 wsl-gent + vps |
| `multienv_mixed.py` | 单客户端混合多用户（6 真实 wsl + 10 vps fake） | 本机 + wsl-gent + vps |
| `multienv_random.py` | 三环境随机混合并发（请求乱序、拒绝即重试） | 本机 + wsl-gent + vps |
| `client_equiv.py` | C1：同一业务序列在 Windows 与 Linux 客户端上等价 | 本机 + wsl-gent + vps |
| `stress_live.py` | 单用户真实 daemon 压力（100 命令 / 30 skill / 上传下载） | wsl-gent |
| `stress_multiuser.py` | 100 用户路由压测（fake daemon 群） | vps |
| `stress_multiuser_real.py` | 多真实 daemon 并发路由（用 `multi_virtuoso_pilot.py` 建的表） | wsl-gent |
| `p1_log_live.py` | CDS.log 增量契约（offset/分级/限长）真机验证 | wsl-gent |
| `log_file_verify.py` | 逐请求把返回的 `log` 与真实 CDS.log 字节区间比对 | wsl-gent |
| `p2_extreme_gradient.py` | 弱 vps 极端梯度（100 fake 用户、并发 400/500/600） | vps |
| `f1_connect_burst.py` | 冷启动建连突发（MaxStartups 场景，30 个新 token 同时建隧道） | vps |
| `f2_daemon_reconnect.py` | daemon 被杀 → 结构化 transport 错误 → 重启重连 | vps |
| fixtures ↓ | | |
| `fake_daemon_host.py` | 协议级 fake daemon 群（无 Virtuoso 的远端模拟） | vps |
| `stress_client.py` | `server.stress_server` 的 HTTP 压测客户端（并发/重试/统计） | 任意 |
| `multi_virtuoso_pilot.py` | 在 wsl-gent 拉起 N 个真实 Virtuoso + 注册用户（批量前置） | wsl-gent |
| `restart_vb_virtuosos.py` | 重启 vbNN 实例以加载新 daemon 文件 | wsl-gent |

> 历史说明：这些 TB 原先散落在 `scripts/`；按项目约定（TB 属于 `test/`）统一收拢到本目录。
