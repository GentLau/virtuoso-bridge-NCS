# stress TB

- `http_mixed_stress_tb.py`：HTTP 入口的 Skill/命令/文件/GUI/Spectre 随机混合并发，
  支持 capacity-reject 重试、marker/sha256 回读、ssh 进程风暴与暂存目录残留检查。

工作目录与暂存区都在 `--work-dir` 内；远端路径由 `--remote-root` 显式提供。
弱机 VPS 只允许低并发 fake daemon，不得作为 100 用户高压靶机。
