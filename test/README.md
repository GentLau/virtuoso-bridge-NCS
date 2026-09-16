# 测试体系（test/）

按等级组织，验收目标是最新四层实现：

```text
test/
  unit/         函数级契约、模型、注册/路由/并发、daemon handler/log
  integration/  真实 socket、daemon 子进程、wire 协议
  scenario/     六步注册、多用户隔离、local 业务链
  e2e/          旧真机脚本（历史资产；本轮真机证据以 tb/ 为准）
  tb/           可执行真机 TB、覆盖率 TB、fake daemon、压测工具
  frontend_tb/  注册页 Mock Testbench
test_bak/       历史测试与调试残留（不参与常规运行）
```

## 常规运行

```powershell
python -m pytest test/unit test/integration test/scenario -q
```

本轮结果：**456 collected / 全部通过（1 个按环境跳过）**。

## 真机 TB

```powershell
# 真机五接口 coverage TB（需要已注册的 daemon；示例为 vb11/65111）
$env:PYTHONPATH='src'
python test/tb/cov_remote_real.py `
  --work-dir test/tb/artifacts/reg-vb11 --token vb-vb11

# 真机注册 1-4 步 coverage TB；只部署，不提交 registry
python test/tb/cov_registration_real.py `
  --work-dir test/tb/artifacts/cov-registration --user covreg --token cov-token --port 65112
```

规模测试（本轮已执行）：

- WSL local：100 用户 × 8 个混合操作 = 800/800 成功；fake daemon 6801–6900。
- Windows→WSL remote：100 用户，每用户五接口链；100/100 成功；压测前后 Windows `ssh.exe` 基线不增长。

## 故障注入 TB

```powershell
$env:PYTHONPATH='src'
python test/tb/fault_injection_tb.py
```

覆盖首次并发 lease、shell permit 释放、Paramiko transport kind、daemon 日志缺省/非法参数、token 缓存失效和 Windows casefold overwrite；红灯/绿灯原始结果保存在 `test/tb/artifacts/`。

## 覆盖率

```powershell
python -m coverage erase
python -m coverage run --source=src -m pytest test/unit test/integration test/scenario -q
$env:PYTHONPATH='src'
python -m coverage run --source=src --append test/tb/cov_remote_real.py `
  --work-dir test/tb/artifacts/reg-vb11 --token vb-vb11
python -m coverage run --source=src --append test/tb/cov_registration_real.py `
  --work-dir test/tb/artifacts/cov-registration --user covreg --token cov-token --port 65112
python -m coverage report -m
```

最新结果：**合并覆盖率 80%**（5749 statements / 1142 missed）；完整解释见 `doc/测试覆盖报告.md`，真机场景与未覆盖项见 `doc/report/五接口三环境真机测试报告.md`。

## 计划与报告

- 测试计划：`test/计划/总览与执行约定.md` 及其分册。
- 真机测试报告：`doc/report/五接口三环境真机测试报告.md`。
- 覆盖率报告：`doc/测试覆盖报告.md`。
- 接口调用指南：`doc/接口调用指南.md`。
