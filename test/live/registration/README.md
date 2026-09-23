# registration TB

- `registration_http_six_step_tb.py`：真实 HTTP 六步（apply→validate→probe→deploy→verify→commit），
  覆盖乱序拒绝、update/delete、前五步零落盘。
- `cov_registration_real.py`：注册 1–4 步 coverage TB。

远端一次性文件只允许放注册表 root 下的 `tmp/`；本地一次性 root 放在
`--work-dir/local-root-*`，运行结束清理。
