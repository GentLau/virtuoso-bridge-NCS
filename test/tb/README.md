# Testbench（test/tb/）

这里是可执行的真机/压力 Testbench，不会被 pytest 自动收集。测试目标、期望值和结果见 `test/计划/` 与 `doc/report/`。
本轮（2026-09-16）的缺陷清单与红→绿证据见 [`doc/report/TB增强轮-缺陷与证据.md`](../../doc/report/TB增强轮-缺陷与证据.md)。

## 环境约定

- `wsl-gent`：首选真实 Virtuoso 与压力靶机（20 vCPU / 约 16GB）。真机 TB 使用
  `vb01–vb06`、`vb11` 以及新注册的 `vblog`（daemon 端口 65121，token `vb-vblog`）。
- VPS：弱机（2 vCPU / 约 1.6GB），只允许低并发 fake daemon；**禁止用作 100 用户高压靶机**。
- Windows 本机：主客户端与注册 Server；执行大规模测试时必须隐藏 ssh/子进程控制台，并在结束后做进程盘点。
- WSL 客户端等价性测试需要 `wsl-gent` 自身可被 ssh 到（已建立 `~/.ssh/authorized_keys` 回环）；
  客户端一律用 `--remote-host localhost`。

## 本轮使用/新增的 TB

| TB | 覆盖内容 | 环境 |
|---|---|---|
| `run_coverage.ps1` | 合并覆盖率一键复算（离线 + 离线 TB + HTTP TB + 真机 TB） | Windows |
| `semantics_tb.py` | 本地文件接口 deadline、registry 跨进程读改写、安装崩溃安全 | 任意平台 |
| `daemon_log_protocol_tb.py` | daemon 日志协议矩阵（off/分级/轮转/读不到/降级/截断/第二帧超时/错误帧/监听循环），py3+py27 双跑 | 任意平台 |
| `_daemon_harness.py` | 脚本化 CIW 夹具（兼容 py3 `.buffer` 与 py2.7 文本流） | 任意平台 |
| `log_matrix_real_tb.py` | 真机 CDS.log：字节一致增量、off 源头、桥零注入、IL 前缀护栏 | Windows→wsl-gent |
| `registration_http_six_step_tb.py` | 真实 HTTP 六步注册（本地全流程 / 远端 1–4 步），含 update/delete/乱序拒绝 | Windows(+wsl-gent) |
| `http_mixed_stress_tb.py` | 五接口 + 组合服务的 HTTP 并发（随机顺序、随机延时、重试计数、可选饱和） | Windows / WSL |
| `one_shot_burst_tb.py` | 一次性通道突发（超过服务端 MaxSessions）不得暴露 transport 错误 | Windows→wsl-gent |
| `fault_injection_tb.py` | 故障注入：租约竞态、shell permit、错误 kind、日志参数校验、缓存失效、Windows casefold | 本地/CI |
| `cov_remote_real.py` | Windows→WSL 真机五接口 coverage TB | Windows + wsl-gent |
| `cov_registration_real.py` | 真机注册第 1–4 步；验证前五步本地零落盘 | Windows + wsl-gent |
| `fake_daemon_host.py` | 协议级 fake daemon 群（单实例/多实例） | wsl-gent / VPS |
| `composite_stress.py` | 上传→Skill→命令→下载组合服务 | Windows/WSL |
| `stress_client.py` | `server.stress_server` HTTP 压测客户端 | 任意 |
| `log_file_verify.py`、`p1_log_live.py` | 返回 log 与 CDS.log 字节区间比对 | WSL/真机 daemon |

> 历史 TB（如 `p2_extreme_gradient.py`、`multienv_*`、`stress_multiuser*`）保留作历史资产；执行前必须按当前 spec 重新核对 registry schema、reservation 语义和靶机资源上限，不能把旧脚本的默认参数直接视为当前验收结论。

## 运行示例

```powershell
$env:PYTHONPATH='src'

# 离线 TB
python test/tb/semantics_tb.py --out test/tb/artifacts/semantics-green.json
python test/tb/daemon_log_protocol_tb.py --out test/tb/artifacts/log-protocol.json
python test/tb/fault_injection_tb.py --out test/tb/artifacts/fault-injection-green.json

# 真机五接口（需 vb11 registry）
python test/tb/cov_remote_real.py --work-dir test/tb/artifacts/reg-vb11 --token vb-vb11

# 真机注册 1–4 步
python test/tb/cov_registration_real.py --work-dir test/tb/artifacts/cov-registration --user covreg --token cov-token --port 65112

# 真机 CDS.log 矩阵 / 一次性通道突发
python test/tb/log_matrix_real_tb.py --work-dir test/tb/artifacts/log-vblog --token vb-vblog
python test/tb/one_shot_burst_tb.py --work-dir test/tb/artifacts/one-shot-burst --token vb-vblog

# HTTP 混合压力（Windows；WSL 客户端加 --remote-host localhost 并在 WSL 内运行）
python test/tb/http_mixed_stress_tb.py --work-dir test/tb/artifacts/http-stress2 `
  --remote-token vb-vblog --remote-daemon-port 65121 `
  --remote-root /home/Gent/.virtuoso-bridge/vblog --workers 6 --rounds 6
```

## 资源盘点

每轮至少检查：

- Windows：`ssh.exe` 数量不随请求数增长；无 `conhost` 累积；无 `-N -L` 孤儿隧道。
- WSL：目标端口释放；无孤儿 daemon；`/tmp/vb-six-*` 等临时目录回收；内存回落。
- 注册：本地无 `registry.reservation`；失败路径无半成品 registry；`registry.json.lock` 为常驻空文件（设计如此，不再删除）。
