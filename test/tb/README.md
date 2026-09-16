# Testbench（test/tb/）

这里是可执行的真机/压力 Testbench，不会被 pytest 自动收集。测试目标、期望值和结果见 `test/计划/` 与 `doc/report/`。

## 环境约定

- `wsl-gent`：首选真实 Virtuoso 与压力靶机（20 vCPU / 约 16GB）。
- VPS：弱机（2 vCPU / 约 1.6GB），只允许低并发 fake daemon；**禁止用作 100 用户高压靶机**。
- Windows 本机：主客户端与注册 Server；执行大规模测试时必须隐藏 ssh/子进程控制台，并在结束后做进程盘点。

## 本轮使用/新增的 TB

| TB | 覆盖内容 | 环境 |
|---|---|---|
| `cov_remote_real.py` | Windows→WSL 真机五接口 coverage TB | Windows + wsl-gent real daemon |
| `cov_registration_real.py` | 真机注册第 1–4 步；验证前五步本地零落盘 | Windows + wsl-gent |
| `fault_injection_tb.py` | 故障注入：租约竞态、shell permit、错误 kind、日志协议、缓存失效、Windows casefold | 本地/CI，可接真机 |
| `fake_daemon_host.py` | 协议级 fake daemon 群；本轮 6801–6900 共 100 个 | wsl-gent |
| `multi_virtuoso_pilot.py` | 多真实 Virtuoso + 注册的前置脚本（路径需按最新 per-role root 核对） | wsl-gent |
| `smoke_user.py` | 单用户五接口/耗时探针 | wsl-gent |
| `log_file_verify.py` | 返回 log 与 CDS.log 字节区间比对 | WSL/真机 daemon |
| `p1_log_live.py` | CDS.log 增量、分级、限长真机契约 | wsl-gent |
| `composite_stress.py` | 上传→Skill→命令→下载组合服务 | Windows/WSL |
| `stress_client.py` | `server.stress_server` HTTP 压测客户端 | 任意 |
| `f1_connect_burst.py` | 冷启动建连突发（低并发参数） | 强客户端 + WSL |
| `f2_daemon_reconnect.py` | daemon 重启后的结构化错误与恢复 | WSL |

> 历史 TB（如 `p2_extreme_gradient.py`、`multienv_*`、`stress_multiuser*`）保留作历史资产；执行前必须按当前 spec 重新核对 registry schema、reservation 语义和靶机资源上限，不能把旧脚本的默认参数直接视为当前验收结论。

## 运行示例

```powershell
# 真机五接口（需 vb11 registry）
$env:PYTHONPATH='src'
python test/tb/cov_remote_real.py `
  --work-dir test/tb/artifacts/reg-vb11 --token vb-vb11

# 真机注册 1–4 步
python test/tb/cov_registration_real.py `
  --work-dir test/tb/artifacts/cov-registration --user covreg --token cov-token --port 65112
```

## 资源盘点

每轮至少检查：

- Windows：`ssh.exe` 数量不随请求数增长；无 `conhost` 累积；无 `-N -L` 孤儿隧道。
- WSL：目标端口释放；无孤儿 daemon；文件/临时目录符合预期；内存回落。
- 注册：本地无 `registry.reservation`；失败路径无半成品 registry。
