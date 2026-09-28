# P-081 · `file_is_local=False` 时 Windows 客户端把 POSIX 远端路径转成反斜杠 → 远端找不到文件

| 字段 | 值 |
|---|---|
| 级别 | P2（该模式在 Windows 客户端完全不可用） |
| 层 | 上层（verilog / veriloga 包）· Windows/Linux 一致性 |
| 归属 | 设计侧（verilog / veriloga 包） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/verilog.py:218-225`（`path = Path(request.file_path)` → `str(path)` 交给 download）、`src/pyapi/packages/veriloga.py:218-225`；Linux 客户端为 `PosixPath` 不受影响 → **同一请求两端行为不同**。 |
| 首报 | 2026-09-28（第八轮 op×param 参数矩阵攻击 file_is_local 分支发现，卡片直报） |
| 最近更新 | 2026-09-28 |

## 现象

Windows 客户端真机实测：`read(file_path="/home/Gent/project/vblog/.../veriloga.va", file_is_local=False)` → `RuntimeError: download requires a regular file: /home/Gent/.virtuoso-bridge/vblog/\home\Gent\... (missing)`；路径被改写成 `\home\Gent\...`（WindowsPath 形态）并按相对路径拼到 role root 下。`source.path` 回显同样是反斜杠形态。

## 复现

```text
python test/artifacts/tmp/r8_p080_p081_evidence.py（真机；看 read_remote_file_is_local_false）
python -m pytest test/offline/unit/test_remote_posix_path_contract.py -q  # 2 条 strict xfail：传给 download 的路径必须逐字节不变
```

## 证据

`test/artifacts/evidence/round8/p080-viewtype-p081-remote-path-2026-09-28.json`；`test/offline/unit/test_remote_posix_path_contract.py`；live 侧已在 `test/live/packages/veriloga_e2e_tests.py` READ-02 留『修复后恢复远端读断言』的注释。

## 验收判据（修好即转绿）

① Windows 客户端 read(file_is_local=False, file_path=<POSIX>) 成功且 sha256 与库路径读取一致；② source.path 原样回显；③ 2 条 xfail 转绿；④ 恢复 live READ-02 的远端读断言。

## 下一步 / 责任人

设计侧不要把远端路径过 `pathlib.Path`（或只在 file_is_local=True 分支使用）；测试侧复跑离线 xfail + veriloga live + 跨平台客户端矩阵。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
