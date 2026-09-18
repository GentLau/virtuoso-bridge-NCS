# virtuoso-bridge-NCS

通过 Python 控制 Cadence Virtuoso 的重构版桥接项目。四层架构：

```text
server      顶层：HTTP 入口与业务调度
pyapi       上层：业务包与操作封装
transport   中层：本地/SSH 投送与 token 路由
register    独立注册模块：六步注册引导与控制面
bridge      底层：Virtuoso 常驻 daemon 资源（ramic_bridge.il + daemon）
common      四层共享的本机路径与工具基座
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
PYTHONPATH=src python -m register.server --port 8124
```

2. 浏览器打开 `http://127.0.0.1:8124/`，按六步注册（申请 → 本地校验 → 探测 → 部署 → CIW load → 连通性测试 → 写注册表）；
3. 上层调用五个接口：

```python
from common.paths import init_work_dir
from transport.middle import BusinessServer

init_work_dir()             # 入口初始化进程级工作目录（默认平台配置目录）
server = BusinessServer()

r = server.execute_skill("1+2", token="<token>")              # VirtuosoResult(output, log, ...)
c = server.run_command("echo vb-ok", token="<token>")          # CommandResult(rc, stdout, stderr)
server.upload_file("local.scs", "/home/user/run/local.scs", token="<token>")
server.run_gui_command("echo vb-ok", token="<token>")        # GUI 一次性命令
server.run_spectre_command("spectre -v", token="<token>")    # Spectre 一次性命令
server.download_file("/home/user/run/out.psf", "out.psf", token="<token>")
```

`token` 每次调用必填（keyword-only）；`run_command(..., parallel=False)`、文件接口 `recursive=False` 是可选参数。

接口共 5 个：Skill 执行 / 命令执行 / 文件执行 / GUI 命令执行 / Spectre 命令执行；role 与目标位置见 [spec/design-concepts/底层与中层/多节点设计.md](spec/design-concepts/底层与中层/多节点设计.md)。

## 只看前端：Mock Testbench

Mock TB 复用正式注册页面，但所有 API 状态都保存在内存中，**不会连接
SSH / Virtuoso、不会部署文件，也不会读写 `registry.json`**：

```bash
# 从仓库根目录运行（Mock 实现和控制面板位于 test/）
.\.venv\Scripts\python.exe test\frontend_tb\registration_mock_server.py --port 8125
```

浏览器打开 `http://127.0.0.1:8125/`。右下角 **Front-end Mock TB**
可以切换成功、步骤失败、404 会话失效、临时 500 等接口场景，也可以直接
跳到任意一步的 UI 状态，无需完整执行前置步骤。

## 设计文档

- 接口基线：`spec/design-concepts/总览/1-四层整体架构与接口.md` 第 4 节
- 配置：`spec/design-concepts/中层/add-中层配置文档.md`
- 六步注册：`spec/design-concepts/其他/1-多用户与注册.md`
- CDS.log 返回：`spec/design-concepts/底层/6-日志返回设计标准.md`

## 测试

```bash
python -m unittest discover -s test/unit -p "test_*.py"
python -m unittest discover -s test/integration -p "test_*.py"
python -m unittest discover -s test/scenario -p "test_*.py"
# 真实 Virtuoso（可选）：
$env:VB_E2E='1'; python -m unittest discover -s test/e2e -p "test_*.py"
```

覆盖报告见 `doc/测试覆盖报告.md`；调用指南见 `doc/接口调用指南.md`。
