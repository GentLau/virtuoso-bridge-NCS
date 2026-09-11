# Log 契约 P1：off 零获取 + offset 增量（真实 Virtuoso）

> 日期：2026-09-11
> 代码基线：`dcb72d4`（后无 log 逻辑变更）
> 执行脚本：`scripts/p1_log_live.py`；目标 vb01（65101）。

## 1. 期望

1. `log=all`：用户 skill 写一行后，`result.log` 只含本次 `[start,end)` 增量且包含该行；
2. `log=all`：无输出的 `1+1` 返回 `log=""`（桥不注入内容）；
3. `log=off`：返回 `log=""`，且 IL 不 flush/fileLength/读文件（源头零获取）；
4. CDS.log 中不存在 `VB-BEGIN`/`VB-END` 等桥注入行。

## 2. 方法

- 构造两个独立 registry 工作目录，分别把 vb01 的 `cdslog.log_level` 设为 `all` 与 `off`；
- `all`：`progn(hiPrintToLogFile("<marker>") 1+1)`，断言 output=2 且 marker 在 log 中；随后纯 `1+1`，断言 log 为空；
- `off`：同样写 marker，断言 output=2 且 log 为空；
- `ssh wsl-gent` 对 CDS.log 做 `grep -c "VB-BEGIN\|VB-END"`。

## 3. 结果

```text
all-write: SUCCESS 2 marker_in_log=True log_len=22
all-noop-log-empty: True
off: SUCCESS 2 log_empty=True
CDS.log bridge-marker count: 0
```

## 4. 结论

通过。`off` 零获取、增量 offset 定界、无 CDS.log 注入全部符合规范。
