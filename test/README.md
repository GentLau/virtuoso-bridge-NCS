# 测试体系（test/）

按等级组织：函数级 → 集成级 → 场景级 → 真实场景级，验收中层（transport）、底层（bridge）、注册流程（transport/register）与注册页面（server）。

```text
test/
  frontend_tb/  前端 Mock Testbench：模拟注册接口和 UI 场景
  unit/         函数级：纯函数、数据模型、解析、带 mock 的传输/注册分支
  integration/  集成级：真实 socket 的假 daemon、daemon 子进程、wire 协议
  scenario/     场景级：六步注册全流程、多用户隔离、完整业务模拟（skill/command/file/并发）
  e2e/          真实场景级：远端单用户全流程 + 57 用户远端业务并发 + 6 用户本地业务并发
test_bak/       旧 tests/ 内容 + 调试期临时文件（不参与常规运行）
```

## 前端 Mock Testbench

Mock 注册页面位于 `test/frontend_tb/`，复用 `src/server/registration_page.html`，
但 Mock Server、场景控制面板和模拟状态全部属于测试代码，不进入 `src/`。

```powershell
.\.venv\Scripts\python.exe test\frontend_tb\registration_mock_server.py --port 8125
```

浏览器打开 `http://127.0.0.1:8125/`，可在右下角切换成功、失败、会话失效和临时错误场景。

## 运行

```bash
# 函数级
python -m unittest discover -s test/unit -p "test_*.py" -v

# 集成级
python -m unittest discover -s test/integration -p "test_*.py" -v

# 场景级
python -m unittest discover -s test/scenario -p "test_*.py" -v

# 真实场景级·远端（需要 wsl-gent + 运行中的 bridge daemon）
$env:VB_E2E='1'; python -m unittest discover -s test/e2e -p "test_*.py" -v

# 真实场景级·本地（在 wsl-gent 上运行；先把 src/test 部署过去）
# scp -r src test wsl-gent:/home/Gent/vb-ncs/
# ssh wsl-gent 'cd /home/Gent/vb-ncs && python3 -m venv .venv && .venv/bin/pip install pydantic paramiko pytest'
ssh wsl-gent 'cd /home/Gent/vb-ncs && VB_E2E_LOCAL=1 VB_LOCAL_USERS=6 .venv/bin/python -m unittest discover -s test/e2e -p "test_business_local_live.py" -v'
```

## 覆盖率

```bash
coverage erase
coverage run --source=src -m unittest discover -s test/unit -p "test_*.py"
coverage run -a --source=src -m unittest discover -s test/integration -p "test_*.py"
coverage run -a --source=src -m unittest discover -s test/scenario -p "test_*.py"
$env:VB_E2E='1'; coverage run -a --source=src -m unittest discover -s test/e2e -p "test_*.py"
coverage report --skip-empty --show-missing
```

最新数字与未覆盖原因见 `doc/测试覆盖报告.md`。

## e2e 场景覆盖

```text
远端单用户（test_e2e_live.py）
  六步注册 apply → CIW RBStop+load → verify → commit(唯一落盘)
  → execute_skill(value+CDS.log增量) → run_command → upload/download(sha256)
  → parallel=True 时间区间重叠 → Paramiko run_command + upload_text + cat

远端多用户并发（test_business_remote_live.py，VB_E2E=1）
  57 个真实 daemon：RBDToken 逐用户路由校验 + 三接口混合并发 + 拒绝即重试

本地多用户并发（test_business_local_live.py，VB_E2E_LOCAL=1，wsl-gent）
  6 个本地账号六步注册 → 每账号一个真实 Virtuoso → 三接口业务 + 并发（全程无 SSH）
```
