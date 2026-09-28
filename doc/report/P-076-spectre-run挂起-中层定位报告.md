# P-076 定位报告：`spectre.run` 请求不返回，卡在中层的递归 tar 下载

| 项 | 值 |
|---|---|
| 现象卡片 | `test/reports/bugs/P-076-spectre-run-request-never-returns.md` |
| 结论 | **中层的递归 tar 下载判定不了“传完了”**：数据已落盘，但下载调用不返回 |
| 责任层 | **中层**（`src/common/paramiko_backend.py` 的 `download_tar` / `_wait_tar_transfer` / `_copy_stream`；`src/common/transfer.py` 的暂存清理） |
| 上层是否要改 | **不要**。上层每次都显式传 `timeout`（本例 1200s），`spectre.run` 只是等中层返回；用上层看门狗去补中层的洞属于替别人擦屁股（已撤回 `cd818e7`） |
| 现场时间 | 2026-09-28 12:59:01–12:59:06（卡住）／13:22:31（该 server 进程被杀） |

## 一、先回答“为什么不返回、成功了还是失败了”

**成功的是数据，没完成的是判定。**

同一个 `spectre.run`（`max_workers=2`，任务 `buf_stage_125804_r2_ac` / `_r2_tran`）：

| 任务 | 远端 spectre | 递归下载 raw | 安装到最终路径 | `spectre.out` |
|---|---|---|---|---|
| `_r2_ac` | 12:59:02 完成（0 error） | 12:59:02 写完 | 装好 `r2_ac.raw/` | 已下载 12:59:05 |
| `_r2_tran` | 12:59:02 完成（0 error） | 12:59:02 写完 | **没装**，只留在 `.vbtmp-*/r2_tran.raw/` | **缺失** |

`_r2_tran` 的数据**已经在本地磁盘上**（`tran1.tran.tran` 40074B、`logFile`、`logStatus`，时间戳 12:59:02），
但没有被“安装”到最终路径 `r2_tran.raw/`，后续的 `spectre.out` 下载根本没开始。
也就是说：**不是仿真失败、不是传输失败，而是“传输已完成，中层判断不出已完成”**，请求停在这次
`download_file` 里。

## 二、证据

**E1 没装上的暂存目录（最硬）**

```
test/artifacts/env/log-vblog/artifact/spectre/buf_stage_125804_r2_tran/
  .vbtmp-b617f6085d8f4b8b9c3729006fddf895/r2_tran.raw/logFile        651B  12:59:02
                                              /logStatus             83B  12:59:02
                                              /tran1.tran.tran    40339B  12:59:02
```

同请求的 `_r2_ac` 任务同一秒已装好（`r2_ac.raw/…` + `spectre.out` 12:59:05）⇒ 不是负载/PDK/环境问题，
是**单次传输**的完成判定卡住。

**E2 服务端命令日志（旧 8127 进程 PID 4492）**

`test/artifacts/env/log-vblog/log/commands.4492.log`：

- 12:59:01 ×2 `Upload completed successfully`（两个 netlist 上传，`_run_one` 已过 prepare/upload）；
- 12:59:01–12:59:03 打开的 channel 908–915 **全部 EOF sent + EOF received**（字节都到齐了）；
- 之后到进程被杀（13:22:31）**没有任何 channel 活动、没有错误/回溯**，只剩 SSH keepalive；
- 13:21:27 通道编号从 0 重新开始 = 期间 SSH 传输层被重建（旧连接已被放弃）。

**E3 卡住期间别的 token 正常** ⇒ 不是顶层 in_flight/锁的问题（`api_server.py` 的 slot 是
acquire/release 配对的普通计数；handler 卡在 dispatch 里，它就一直是 1）。

**E4 暂存目录泄漏是成批的，不是孤例**

```
artifact/spectre/buf_stage_125804_r2_tran/.vbtmp-b617f608…
artifact/maestro/screenshots/.vbtmp-…        ← 另一处同类残留
```

## 三、代码定位：为什么会出现“数据到了却不返回”

`src/common/paramiko_backend.py::ParamikoSessionBackend.download_tar`：

```python
remote_rc, local_rc = self._wait_tar_transfer(channel, tar_process, workers, failures, deadline, ...)
...
install_staged_path(plan)          # ← 本次从未执行到
```

`_wait_tar_transfer` 的完成条件是

```python
if (channel.exit_status_ready() and process.poll() is not None
        and all(not worker.is_alive() for worker in workers)):
    break
```

即必须**三个 pump 线程全部退出**：`_copy_stream(remote_stdout_file → tar stdin)`、
`_read_stream(remote_stderr_file)`、`_read_stream(tar_stderr)`。其中 `_copy_stream` 是对 paramiko
`ChannelFile` 的**阻塞读**：一旦 EOF 语义没被观察到（对端已关 channel，但本地 file 对象没返回 EOF），
该线程就永久存活，这个循环只剩一条出路 —— `deadline.remaining(command)`（本例 `timeout=1200s`）。

于是形态就是：**数据/远端命令都已完成，完成判定却要等满整个 per-call deadline**（最长 20 分钟），
对使用方看起来就是“请求不返回”；而这条路上唯一的兜底是 deadline，deadline 之后的 `discard_stage`
又是 best-effort ⇒ 暂存目录残留（E4）。

> 注：本例现场在 13:22:31 被杀，13:19:06 附近是否真的抛了 deadline 无法从日志百分百确认
> （channel 那时早已关闭，超时路径不留日志）。这正是下面第 4 条要求补计时日志的原因。

## 四、请中层修这四点（可按此验收）

1. **完成判定不要依赖 pump 线程**：以“远端 channel 结束（`exit_status_ready`/EOF）＋ 本地 tar 退出
   ＋ 暂存产物存在”为完成条件；线程只负责搬运，不能成为“是否返回”的前提。
2. **线程要有界**：`_copy_stream`/`_read_stream` 必须能被打断（先关流再 join，join 带超时；
   残留 reader 只记 warning）。`_stop_tar_transfer` 现在虽是 `join(timeout=1)`，但**join 不掉的线程
   仍挡住了主流程的完成判定**，两处要一起改。
3. **超时/失败路径清理要可靠**：kill tar → 关流 → 删暂存目录（Windows 句柄释放后重试），
   删不掉要把残留路径写进错误里（现在是静默留垃圾）。
4. **加阶段计时日志**（channel open/close、tar exit、install 起止与耗时）：本卡是间歇复现，
   没有这些日志只能事后猜。

## 五、复现与取证工具（已写好，可直接用）

```text
# 同口径 2 任务 spectre.run ×N 轮，实时跟 /health，卡住自动 py-spy dump 8127 进程栈
python test/semi/probes/p076_spectre_run_hang_probe.py --rounds 6 --hang-after 90

# 把“中层调用 ↔ paramiko channel”一一对上（判断某 channel 属于哪个调用）
python test/semi/probes/spectre_channel_map_probe.py
```

已跑结果：4 轮全部 6.5–7.2s 正常返回（间歇问题，未复现）；探针给出的同口径调用序列是
`prepare → upload_netlist → execute → download_raw → download_spectre.out → .fc → .ic`。
另：`run_spectre_command("sleep 20", timeout=5)` → vblog 6.06s、calprobe 5.22s 返回
`rc=124 kind=timeout`（命令执行段守约，不是本次挂点）。

## 六、与上层的关系（给评审的结论）

- 上层 `spectre.run` 对每一次中层调用都显式传 `timeout`（TB 传 1200s），并且只做“等结果 → 记 steps”；
  中层契约成立时它是有界等待，不需要、也不应该在上层再叠一层看门狗去补中层的洞（该改动已撤回）。
- 建议把 `test/reports/bugs/P-076-*.md` 的「层/归属」改为 **中层**（“上层为主/第二嫌疑中层”不再成立）。
