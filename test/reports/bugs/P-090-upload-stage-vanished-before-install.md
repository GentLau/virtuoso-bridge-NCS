# P-090 · `basic.file.upload` 偶发 `mv: cannot stat <target>.vbtmp-<hex>`：stage 在 sha256 校验通过后消失，安装步骤报错

| 字段 | 值 |
|---|---|
| 级别 | P3（观察：单次复现、40 次同目标 hammer + 套件复跑均未复现；但错误形态误导为「文件不存在」，掩盖真实性质） |
| 层 | 中层传输（tunnel.upload_file）/ 底层 SSH 常驻 shell |
| 归属 | 待归属（中层 tunnel 安装步骤幂等性 / 底层常驻 shell 重试口径，二选一或联合） |
| 状态 | **观察** |
| 位置 | `src/transport/tunnel.py:487-497`（stage = `<target>.vbtmp-<hex>` → scp → `sha256sum` 比对 → `mv -f -- stage target`）；同一路径被 `src/pyapi/packages/veriloga.py:167-172`（`_write_remote`）与 `src/pyapi/packages/basic.py:173-180`（`basic.file.upload`）共用；`src/common/ssh.py:1941-1981`（`_run_via_persistent_shell_with_retry` 会对同一命令字符串重发一次） |
| 首报 | 2026-09-28（第八轮真机 gate 复跑 veriloga 套件时发现） |
| 最近更新 | 2026-09-28（新立；含复现性判定：单次/未复现） |

## 现象

2026-09-28 21:5x：`veriloga_e2e_tests.py --transport http` 的 WRITE-02 patch_source 报 `patch_source failed: mv: cannot stat '/home/Gent/project/vblog/schemtest/va_e2e/veriloga/veriloga.va.vbtmp-8a7782b8f3884a4aa6e2058e9e8db36f': No such file or directory (commands applied: 0/1)`。
关键点：报错来自 **安装（mv）** 而不是上传或校验——即 upload 已 rc=0、`sha256sum` 已取到并比对通过之后，stage 文件在 mv 前消失。
复现性：同套件随后复跑 **7/7 全绿**；同目录同目标 40 次连续 upload **0 失败**（60.7s）；同目录 `basic.file.upload`（probe_upload.txt）单次也全绿 ⇒ 非路径/权限/磁盘问题。

## 复现

```text
`PYTHONPATH=src python test/live/packages/veriloga_e2e_tests.py --transport http`（本文件原始失败日志见证据 1）；定性探针：`PYTHONPATH=src python test/artifacts/tmp/probe_upload_mv_fail.py`（单次 upload 到同目录，绿）；hammer：`PYTHONPATH=src python test/artifacts/tmp/hammer_upload_same_target.py`（40 次同目标覆盖写，绿）
```

## 证据

① `test/artifacts/tmp/rerun_veriloga.log`（原始 `mv: cannot stat` traceback）；② `test/artifacts/tmp/rerun_veriloga2.log`（复跑 7/7 PASS）；③ `test/artifacts/tmp/hammer_upload_same_target.py` 输出 `done 40 iters ... fails=0`；④ `test/artifacts/env/log-vblog/api-8127-20260928-195332.err.log`（同窗口多次 ConnectionResetError，说明该时段客户端/服务端连接确实在异常抖动）

## 验收判据（修好即转绿）

① 安装步骤幂等化：stage 不存在时若目标文件 digest 与本次 payload 一致，视为已安装并返回成功；② 或把重试严格限定在可证明「未投递」的协议错误，并禁止对已投递命令重发；③ 两者任一 + 失败时日志打印 `stage/target` 与实际重试原因，使该错误形态不再出现或不再误导。

## 下一步 / 责任人

设计侧评估 `ssh.py` 重试口径与 `tunnel.upload_file` 安装幂等性；测试侧保持观察（本轮 40+1 次未复现），若再出现请附 `~/.virtuoso-bridge/vblog/run` 日志定位。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
