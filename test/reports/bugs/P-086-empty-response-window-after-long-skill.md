# P-086 · 多用户同视图场景后 ~30–90s 窗口内同 token 请求得到 `Empty response from daemon`（随后自愈）

| 字段 | 值 |
|---|---|
| 级别 | P3（观察：可恢复，但窗口期错误不可读、无结构化语义） |
| 层 | 底层 daemon / 中层连接（多用户场景） |
| 归属 | 待归属（底层 daemon 请求生命周期 / 中层连接复用，二选一或联合） |
| 状态 | **观察** |
| 位置 | 底层：`src/bridge/resources/ramic_bridge_daemon_3.py:187`（`_read_frame` 对空 stdin 只 1ms 轮询、无 EOF/停滞判定）；中层：`src/common/skill_client.py:185`（读空 → `errors=["Empty response from daemon"]`，非 spec 枚举文案）；触发 TB：`test/semi/probes/twouser_same_view_probe.py`（holder 单请求内 `dbOpenCellViewByType a` + `hiSleep(20)` 持锁） |
| 首报 | 2026-09-28（第八轮半真机整层，twouser_same_view_probe 复跑 4 次稳定复现） |
| 最近更新 | 2026-09-28 |

## 现象

复现 4/4（2026-09-28）：跑完 twouser 多用户同视图场景后，**同 token 新请求立即得到 `Empty response from daemon`**；raw socket 新建连接 6s 内未被 accept（daemon 忙，wchan=hrtimer_nanosleep）。CLEAN 步记录 `holder_still_running=false`（holder 已结束）。**约 30–90s 后自愈**（python daemon 回到 `inet_csk_accept`，`1+2` 恢复 SUCCESS='3'），无需重启实例。
**加强证据（21:30–21:38，无并发）**：`maestro_e2e_tests.py --transport direct` 单独跑两次，均在套件中途 `virtuoso.maestro.read_config/write` 报 `RuntimeError: Empty response from daemon`；同窗口 CDS.log 出现 `ERROR (ASSEMBLER-8001): Cannot determine a valid ADE Assembler session from the supplied argument "0"` —— 有调用把**会话句柄 0** 传给了 ADE API（与 `delete_var` 报的 `Cannot find a setup database entry for handle 0` 同源嫌疑）。
**第三次/第四次复现（22:06–22:12，HTTP 面，无并发）**：`maestro_e2e_tests.py --transport http` 复跑两次，分别在 `virtuoso.maestro.run` 与 `virtuoso.maestro.read_config` 报同一句 `RuntimeError: Empty response from daemon`（证据 `../artifacts/evidence/round8/maestro-rerun3.out.log`）；失败后 3 连发 `1+2` 全部 ~0.3s 成功（自愈成立）。同分钟 CDS.log 出现 `ERROR (ASSEMBLER-2404): Cannot find a setup database entry for handle 0` + `ASSEMBLER-8001 … supplied argument "0"`（22:09:06 起同一 session 生命周期）。⇒ **同一实例上只有 maestro 套件稳定触发**，其它 9 套包与 base 五接口全绿，支持「maestro 调用序列把句柄 0 传给 ADE API → daemon 侧空响应」这一解释（待设计侧确认）。
**同族第四形态（2026-09-29 02:30 gate，skillref 套件）**：本地 staging 安装阶段 `[WinError 5] 拒绝访问: …\temp\skillref\<hash>\finder\.vbtmp-<hex>\SKILL -> …\finder\SKILL`；最小复现（同名目录递归下载两次）**2/2 绿** ⇒ 判为 Windows 本地 `install_staged` 的瞬时时失败（可能被实时扫描/句柄占用打断），归入本卡观察族；重跑套件即绿，不作为功能红。
**同层第二形态（2026-09-28 23:19 verilog 导入 TB）**：`virtuoso.verilog.import` 在
**同层第三形态（2026-09-29 02:0x maestro 覆盖补跑）**：`virtuoso.maestro.read_config` 报 `("asiGet" 0 t nil ("*Error* asiGet: no applicable method for the classes" list(symbol)))`；同一调用 standalone 复跑立刻 ok=true（同一 sdb、同一 cell）⇒ 归入本卡的瞬时族，不单独立卡。排查中确认共享 `maestro_tb/rc_probe` 的全局变量已累积 ~30 条 `e2e_save_*`/`p086_*` 残留（P-088 `delete_var scope=all` 失效导致清不掉）——**不是**本次 read_config 失败的直接原因，但属同一共享库卫生问题。`overwrite=False` 场景返回 `RuntimeError: sha256 mismatch`（上传 stage 的摘要与本地文件不符，同一调用前一次却返回 ok=true）—— 与 P-090 同属「上传 staging/校验」路径，一并观察。
**持久形态根因（22:48 定位，见 P-095）**：`maestro.run` 的悬空 Overwrite-History 目标触发 `ASSEMBLER-3018` 模态框（CDS.log：`# Displaying modal dbox "adexlMessageDialog"`）→ CIW 阻塞；该形态 **8×15s 轮询不自愈**，需按 Runbook §10.3 重启实例。

## 复现

```text
python test/semi/probes/twouser_same_view_probe.py --work-dir test/artifacts/env/log-vblog \
  --token-a vb-vbuser1 --token-b vb-vbuser2 --lib serdes_rx --cell twouser_probe_r8 \
  --out test/artifacts/evidence/round8/twouser-same-view-r8d.json
# 随后立即 python test/artifacts/tmp/_r8_user1_recover.py → Empty response；隔 ~60s 再跑 → SUCCESS
```

## 证据

`test/artifacts/evidence/round8/twouser-same-view-r8d.json`（CLEAN counted=false + holder_still_running=false）；`p085-vbuser1-daemon-hang-2026-09-28.json`、`p085-dd-modal-wedge-2026-09-28.json`（现场快照，文件名沿用当天流水号）；CDS.log 出现过 `a '(' at line 1 was still unclosed on EOF` 读入警告；maestro 侧：`evidence/round8/coverage-main-r8.log`（两次 Empty response + 失败步骤）、`~/.virtuoso-bridge/vblog/run/CDS.log` 21:36:04 的 ASSEMBLER-8001(argument "0") 行

## 验收判据（修好即转绿）

① 触发场景结束后 0 窗口期：同 token 下一条请求直接成功；② 若窗口不可避免，错误必须是 spec 枚举语义（`unknown-effect`/`timeout`/具名 busy）且文案可读；③ daemon 对 stdin EOF/请求停滞有可观测处置（日志 + 退出/复位），不再静默轮询。

## 下一步 / 责任人

设计侧定位窗口期 daemon 在等什么（建议给请求生命周期加日志：recv→ipc 写→ipc 读→回包，各步带耗时）；中层评估 stale 连接自动重连与空响应结构化。测试侧：探针 CLEAN 已改 best-effort（不计判定），Runbook 记『跑完 twouser 等 90s 再跑同实例用例』。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
