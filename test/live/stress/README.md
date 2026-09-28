# stress TB

- `production_face_stress_tb.py`：**生产面**混合并发（`POST /api/operation` → dispatch → basic 包 → 中层）。
  两种模式：① 缺省**自起**一个 `server.api_server`（临时 work-dir + local 模式注册表，零依赖）；
  ② `--base http://127.0.0.1:8127/api/operation --token vb-vblog` 对接既有真机面（额外混 skill/gui/spectre）。
  判据：计划轮数=应答轮数、`steps_failed==0`、上传/下载 sha256 一致、失败必须是结构化 `kind`。
  **不再使用**已删除的测试专用 `server.stress_server` 压测壳。
- `layout_multiuser_lock_tb.py` / `multi_user_routing_tb.py` / `scale_local_fake_tb.py`：其余并发/多用户 TB（真机侧）。

工作目录与暂存区都在 `--work-dir` 内；远端路径由 `--remote-root` 显式提供。
弱机 VPS 只允许低并发 fake daemon，不得作为 100 用户高压靶机。
