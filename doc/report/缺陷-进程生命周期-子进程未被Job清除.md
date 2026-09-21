# 缺陷：Windows Job Object 关闭后孙进程仍存活

> 日期：2026-09-21
> 发现人：上层开发（symbol 业务包回归时跑全量 unit 发现）
> 归属：**中层/基础设施**（`src/common/process_lifetime.py`、`src/server/supervisor.py`），不属于上层业务包
> 复现环境：本机 Windows + 当前 agent shell；`pytest test/unit` 全量跑时命中

## 1. 现象

```
.\.venv\Scripts\python.exe -m pytest test/unit/test_process_lifetime.py -q
...
> self.assertFalse(_pid_alive(child_pid), "descendant survived job close")
E AssertionError: True is not false : descendant survived job close
```

- 复现率：**2/2**（单跑该文件同样失败，不是全量跑的干扰）。
- `pytest test/unit` 全量：仅此 1 项失败，其余全绿。

## 2. 测试做了什么

`test/unit/test_process_lifetime.py::TestProcessJob::test_close_kills_parent_and_descendant`

1. 用 `subprocess.Popen` 起一个“父进程”（写入 ready 文件后等待 go 文件）；
2. `job = ProcessJob()`；`job.assign(parent)` 断言成功；
3. 写 go 文件，父进程再 `subprocess.Popen` 一个 `python -c "time.sleep(60)"` 孙进程，并把孙 pid 写盘；
4. 断言父子都存活 → `job.close()`；
5. `parent.wait(timeout=5)` 通过（父进程确实被杀）；
6. 再等最多 5s 断言孙进程死亡 → **失败，孙进程仍存活**。

## 3. 初步判断

父进程被 `KILL_ON_JOB_CLOSE` 杀掉，但**孙进程没有随 Job 关闭而被杀**，说明孙进程当时并不在该 Job 内。

可能原因（待中层确认，按可能性排序）：

1. 运行环境（agent / CI 外壳）本身把进程放在某个 Job 里，且带 `JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK`
   之类的 breakaway 语义，导致后续 `CreateProcess` 出来的进程脱离 Job 树；
2. `assign()` 是在父进程已经启动之后才调用（非 `CREATE_SUSPENDED` + assign + resume 的原子做法），
   在嵌套 Job 场景下继承关系不稳定；
3. `ProcessJob.close()` 只关了句柄，实际终止有延迟/被上层 job 抢占。

## 4. 建议

- 加一条诊断：assign 之后对“父进程”调用 `IsProcessInJob(parent, NULL, &inJob)`，把结果写进断言消息，
  先确认是“不在 Job 内”还是“在 Job 内但没被清”；
- 生产路径（`server/supervisor.py` 起业务子进程）建议改成 `CREATE_SUSPENDED` → `assign` → `ResumeThread`，
  保证子进程从第一条指令起就在 Job 内；
- 若确认是外壳环境的 breakaway 行为，请在测试里显式跳过或标注“依赖无 Job 外壳”，
  避免把环境相关失败当成产品回归。

## 5. 影响面

- 对上层业务包（`src/pyapi/packages/*`）无直接影响；
- 若真机也存在“派生进程不随 Job 关闭”的情况，`supervisor` 重启/停机可能留下孤儿进程（如隧道、daemon 后代）。

## 6. 代码侧裁决与修复（2026-09-21）

低层现象确认成立，但触发条件不是“Job Object 本身失效”，而是
`AssignProcessToJobObject` 发生在子进程已经开始执行之后。Windows 在宿主
进程已经处于 Job（尤其是嵌套 Job）内时，不保证这种“后绑定”会让后续
后代继承新 Job；父进程会在 Job 关闭时死亡，孙进程可能留在原 Job/无 Job
状态。

修复采用报告建议的确定性顺序：

1. Windows 下用 `CREATE_SUSPENDED` 创建业务子进程；
2. 在它执行第一条指令前 `AssignProcessToJobObject`；
3. `ResumeThread` 恢复主线程；
4. assign 或 resume 失败时走已有的 `taskkill /T` fallback，并拒绝启动。

对应改动：

- `src/common/process_lifetime.py`：增加 `ProcessJob.resume()`；
- `src/server/supervisor.py`：业务子进程改为挂起创建、绑定后恢复；
- `test/unit/test_process_lifetime.py`：测试改为同样的
  “挂起创建 → assign → resume”顺序，并断言业务进程在恢复前已绑定。

已用真实 supervisor + SSH 隧道做受控验证：隧道建立后强杀 supervisor，
业务进程和隧道进程都被清理；带 `SILENT_BREAKAWAY_OK` 外层 Job 的
复现环境也通过。此报告按真实低层缺陷处理，不能仅靠跳过测试或环境 guard
收口。
