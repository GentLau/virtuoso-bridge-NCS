# virtuoso-bridge-NCS

通过 Python 控制 Cadence Virtuoso 的重构版桥接项目。三层架构：

```text
pyapi       上层接口定义（三个接口 + 返回模型）
transport   中层：本地/SSH 投送、注册、路由（业务服务器运行时）
bridge      底层：Virtuoso 常驻 daemon 资源（ramic_bridge.il + daemon）
server      注册 HTTP 页面（六步注册引导）
```

本版**不保留旧项目兼容**：`profile`/`VB_*`/`.env` 已彻底删除，新用户只走六步注册 → `registry.json` → `token`。

## 安装

```bash
uv venv .venv
uv pip install -e ".[dev]"
```

## 快速开始

1. 启动注册页：

```bash
PYTHONPATH=src python -m server.registration_server --port 8124
```

2. 浏览器打开 `http://127.0.0.1:8124/`，按六步注册（申请 → 本地校验 → 探测 → 部署 → CIW load → 连通性测试 → 写注册表）；
3. 上层调用三个接口：

```python
from transport.middle import BusinessServer

server = BusinessServer()   # 工作目录缺省为平台配置目录

r = server.execute_skill("1+2", token="<token>")              # VirtuosoResult(output, log, ...)
c = server.run_command("echo vb-ok", token="<token>")          # CommandResult(rc, stdout, stderr)
server.upload_file("local.scs", "/home/user/run/local.scs", token="<token>")
server.download_file("/home/user/run/out.psf", "out.psf", token="<token>")
```

`token` 每次调用必填（keyword-only）；`run_command(..., parallel=False)`、文件接口 `recursive=False` 是可选参数。

## 设计文档

- 接口基线：`spec/design-concepts/总览/三层整体架构设计.md` 第 4 节
- 配置：`spec/design-concepts/总览/配置一览.md`
- 六步注册：`spec/design-concepts/底层与中层/多用户设计.md`
- CDS.log 返回：`spec/design-concepts/底层与中层/日志返回设计标准.md`

## 测试

```bash
python -m unittest discover -s test/unit -p "test_*.py"
python -m unittest discover -s test/integration -p "test_*.py"
python -m unittest discover -s test/scenario -p "test_*.py"
# 真实 Virtuoso（可选）：
$env:VB_E2E='1'; python -m unittest discover -s test/e2e -p "test_*.py"
```

覆盖报告见 `doc/测试覆盖报告.md`；调用指南见 `doc/接口调用指南.md`。
