# `test/offline/` —— 离线级

> **级别：离线测试**（不需要真实环境，纯 Python；允许 mock/stub/fake 夹具）。
> 判定与目录映射见 [`../docs/测试架构.md`](../docs/测试架构.md) §2。

## 内容

| 子目录 | 放什么 | 进 CI |
|---|---|---|
| `unit/` | 函数/类/模块契约、参数校验、错误分支；允许密闭本地资源（`127.0.0.1:0`、本机子进程、`tempfile`） | ✅ |
| `integration/` | 真实 socket / 真实子进程边界（本机），不需要 Virtuoso | ✅ |
| `scenario/` | 跨组件流程（六步注册、多用户隔离、local 业务链） | ✅ |
| `core/` | 确定性离线 TB：协议/语义/故障注入/顶层 HTTP（原 `test/tb/core`） | ❌ 显式 |
| `frontend/` | 注册页 mock testbench（无 SSH / 无 Virtuoso / 无落盘） | ❌ 显式 |

## 怎么跑

```powershell
# CI 同口径（pyproject.toml::testpaths 已固定为 unit/integration/scenario）
python -m pytest test/offline/unit test/offline/integration test/offline/scenario

# 离线 TB（各自落 evidence）
python test/offline/core/api_server_tb.py          --out test/artifacts/evidence/api-server.json
python test/offline/core/semantics_tb.py           --out test/artifacts/evidence/semantics-green.json
python test/offline/core/fault_injection_tb.py     --out test/artifacts/evidence/fault-injection-green.json
python test/offline/core/daemon_log_protocol_tb.py --out test/artifacts/evidence/log-protocol.json
```

## 纪律

- 不得写仓库内文件（临时目录用 `tempfile.mkdtemp(prefix="vb-")`，由 `test/conftest.py` 清理）；
- `unit/` 不得起服务、不占固定端口；需要固定端口时放 `integration/` 或 `scenario/` 并在 `finally` 释放；
- 结论必须能被本机复现，不需要任何远端前提。
