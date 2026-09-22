# Bug 报告：SSH tunnel 启动失败（schematic region 截图验证被阻塞）

> 日期：2026-09-18
> 报告人：上层业务包开发
> 严重程度：阻塞 schematic.screenshot(region=...) 真机验证
> 归属：中层/环境（SSH tunnel）

## 1. 现象

`schematic.screenshot(region=[x1,y1,x2,y2])` 在 `execute_skill` 步骤返回：

```
status=error
errors=["Daemon connection failed: SSH tunnel failed to start on Windows (rc=255) | command-line line 0: invalid time value."]
```

此前相同 work-dir/token 下的 read/write/普通 screenshot 均正常；本次故障出现在 2026-09-18 后续重试中，连续两次复现。

## 2. 环境

- work-dir：`test/tb/artifacts/log-vblog`
- token：`vb-vblog`
- 8127 服务可用（query/mkdir 成功）
- 失败点：`middle.execute_skill` 建 tunnel（`command-line line 0: invalid time value`）

## 3. 复现

```python
from transport.middle import BusinessServer
from pyapi.packages.schematic import Package, ScreenshotRequest
middle = BusinessServer(r"test/tb/artifacts/log-vblog")
Package(middle).screenshot(ScreenshotRequest(
    token="vb-vblog", library="schemtest", cell="t1",
    region=[-1.0, -0.5, 1.0, 0.5], leave_open=False, timeout=180))
```

## 4. 上层侧已确认

- 非 `region` 参数问题：同样的 SKILL 生成逻辑在故障前通过（默认截图 SHOT-01/02/03 PASS）；
- 非 `query` 问题：query 步骤成功；
- 错误出现在中层 SSH tunnel 建立阶段，上层不修改。

## 5. 修复记录（中层，2026-09-18）

- **根因**：中层把 `runtime.connect_timeout` 保留为浮点秒（spec v31 §2.2 要求它是浮点子预算），
  但同一数值被直接渲染进 OpenSSH 命令行 `-o ConnectTimeout=15.0`；OpenSSH 的
  `ConnectTimeout` 只接受整数“时间值”，于是 ssh 立刻以 `command-line line 0: invalid time value`
  退出（rc=255），隧道永远建不起来。默认截断为整数时会掩盖该问题，因此表现为“同一环境下
  先前正常、后续突然失败”。
- **修复**：`src/common/ssh.py::_common_ssh_options` 把 ConnectTimeout 渲染为整数秒
  （`ceil`，最小 1 秒）；内部（Paramiko/预算）仍保留浮点秒子预算，语义不变。
- **TB**：`test/unit/test_ssh.py::test_connect_timeout_rendered_as_integer_for_cli`
  （修复前红：`ConnectTimeout=0.5`）。
- **真机复核**（Windows → `wsl-gent`，token `vb-vblog`）：
  `test/tb/cov_remote_real.py` 5/5 ok；`one_shot_burst_tb.py` 72/72；
  递归上传/下载 + 远端 symlink 解引用 PASS；`registration_http_six_step_tb.py --local-mode` rc=0。
- **提交**：`5e3f848`；代码评审报告见 `doc/report/代码与spec偏差评审.md` §7.3。
