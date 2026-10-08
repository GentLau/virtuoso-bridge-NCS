# P-130 · 【改进汇总】重复实现收敛 / 死代码清理 / 排障日志与小项清理（非缺陷，不阻塞功能）

| 字段 | 值 |
|---|---|
| 级别 | 改进（非缺陷；由外部静态审查提出，测试侧抽查复核） |
| 层 | 全仓（架构治理 · 非缺陷改进汇总） |
| 归属 | 设计侧（排期执行；重构以行为不变为约束） |
| 状态 | **观察** |
| 位置 | 重复实现：`_step`×9 包、`_require_*` 8–12 份、截图流水线×4、传输暂存/安装×4（`middle.py`/`tunnel.py`/`ssh.py`）、分块 sha256×3、kind 映射×3（`ssh.py:944`/`paramiko_backend.py:1733`/`middle.py:153`）、`register/candidate.py` vs `transport/roles.py`、`register/models.py` vs `common/registry.py`、py2/py3 daemon 双份（有意为之，长期同步风险）；死代码：`src/transport/budgets.py:71-90`（try_acquire_thread 等，全仓无调用）、`src/transport/tunnel.py:660`（`_verify` 无调用）、`src/pyapi/packages/basic.py:451`（`_collect_strings` 无调用）、`src/pyapi/packages/calibre.py:442-452`（pex 半残链，建议与 P-117 预留口径一起收）；排障：`src/transport/middle.py:605` 等 `except LookupError` 会把内部 KeyError 报成 invalid token；`src/server/dispatch.py:110-113`（TypeError/ValueError→400 是 spec §3.3 规定，建议补服务端 traceback 日志以区分代码 bug）；小项：`src/common/registry.py:287-291` 重复 `model_config`、`src/common/ssh.py:327-332` control_master force≡auto、`src/register/flow.py:1248` `_token_ok` 冗余、`flow.py:1475` 冗余 except、`src/pyapi/packages/skillref.py:427-428` no-op 分支、`src/common/paths.py:102` 注释与实现不一致 |
| 首报 | 2026-10-08（外部静态审查） |
| 最近更新 | 2026-10-08（测试侧建卡） |

## 现象

重复实现已产生真实漂移（verilog/veriloga=P-129、gui 截图第 4 份实现漏清理=P-125、candidate/roles 解析差异=P-120 相关）；死代码与宽异常捕获增加维护成本与排障误导。

## 复现

```text
—（治理项，无单一复现；重构项验收＝行为不变+回归全绿）
```

## 证据

外部静态审查（2026-10-08，AST 统计同名相似函数 207 对）+ 测试侧抽查复核（死代码 3 条确认无调用；小项 3 条确认属实；spec §3.3 4xx 归因核实）

## 验收判据（修好即转绿）

① 各项独立完成即可勾掉；② 重构类以「行为不变 + 现有 TB 回归全绿」为验收；③ 排障类以「内部异常不再伪装成协议/参数错误」为验收；④ 建议在 P-122~P-129 修复后再动重构，避免与修复打架。

## 下一步 / 责任人

排期执行；测试侧在每项重构后跑对应层回归并在本卡尾部记录进度。

## 我层复核与拒绝项（2026-10-08，中+底层）

**已清理（随 `5a80392` 入库）**：`tunnel._verify`（含 2 条专用单测）、`budgets.py` 的 thread 预算家族（`try_acquire_thread`/`release_thread`/`threads_in_use`/`thread_pool_size`）、`basic._collect_strings`、`common/registry.UserEntry` 重复 `model_config`。全量离线回归绿；8135 重启后 env_check + 五接口冒烟绿。

以下条目经复核**拒绝/无需修改**（本轮不改）：

1. **传输暂存/安装×4 → 已收敛，无重复可删**：单一实现在 `common/transfer.py`，`paramiko_backend`/`middle`/`ssh` 均走它；`tunnel._install_stage_command` 是 OpenSSH 后端「远端 shell mv」机制，与本地安装不是同一实现，不合并。
2. **分块 sha256×3 → 实为 2 份本地 + 1 份远端查询**：`middle._sha256_file` 与 `tunnel._sha256_local` 仅「到期异常类型」不同（`_DeadlineExceeded` vs `subprocess.TimeoutExpired`），合并需引入异常转换参数，为合并而加抽象、净收益低；`_remote_sha256` 是远端 `sha256sum` 查询，不同类。保留现状。
3. **kind 映射×3 → 条目不成立**：`paramiko_backend.py` 无 kind 映射（它返回 rc/stdout/stderr，由 `ssh.py::_result_from_rc` 统一映射）；实际只有两处且输入不同（远端文本→kind vs 异常→kind）。卡内行号/条数过期，划掉。
4. **`register/models.py` vs `common/registry.py` → 有意分层**：请求模型允许缺省/扩展（未定稿输入），注册表模型 required/forbid（已校验产物）；合并会破坏边界。不合并。
5. **`register/candidate.py` vs `transport/roles.py` → 本版不做**：注册期（未定稿、相对 root、凭据可未解析）与运行期（已校验注册表）契约不同；P-120 的漂移教训已由该轮修复吸收（该接的线接全）。合并属设计级重构、风险大于收益；若未来再出现同源漂移，再单独立项。
6. **`middle.py` except LookupError → 复核不成立**：`_entry()` 只做 `registry.by_token()`（内部全 `.get`），`LookupError` 只可能是「unknown token」本意；except 只包 `_entry()`，不吞内部异常。
7. **`server/dispatch.py` traceback 日志 → 不加**：spec §3.3 的 `(TypeError, ValueError)→400` 行为正确，未观察到排障盲区；属可选增强、非缺陷，保持现状。
8. **`flow._token_ok` / `flow.py:1475` 冗余 except / `paths.py:102` 注释 → 非问题或已不存在**：`_token_ok` 是仅用一次的命名 helper（风格非 bug）；1475 冗余 except 与 paths 注释在当前代码已不存在。划掉。

**决策与落地（2026-10-08，用户裁定 A）**：删掉 `ssh.control_master="force"`，只保留 `auto/disable`。代码与前端已完成：`registry.py`/`register/models.py` 枚举、`ssh.py` 分支（未知值显式报错）、`registration_page.html` 下拉项；TB：runner/两模型/页面三条新断言，旧 `force` 用法改 `auto`。**spec 侧需求（待 spec owner 落地）**：`add-中层配置文档.md:35` 的 `auto/force/disable` 需改为 `auto/disable`。

非我层或有意为之（不列为本层残留）：py2/py3 daemon 双份（有意为之）。

## 上层结论（2026-10-08）：截图流水线×4 → 收敛 + gui 豁免

已落地（commit `360dba1`）：新增 `src/pyapi/packages/_screenshot.py`，`ensure_window_skill` / `close_window_skill` / `screenshot_skill` 三份共享 SKILL 模板；schematic / symbol / layout 的既有差异（viewType 取值、not-found 文案、window_id 解析、zoom 坐标语法）参数化保留，三包改薄包装（函数名/签名不变），生成文本与收敛前逐字比对 **15/15 一致**。流程骨架保留：命名规则、返回形状（schematic 顶层 `local_path` vs value dict）、capture 校验步（symbol 查 `saved`、layout 加文件大小 verify）均为已验收的对外差异。`gui.py::screenshot` 是 X11 `XGetImage` 直抓（不经过 SKILL），机制不同——明确豁免，不在模板收敛范围。验证：三包契约测试全绿；8133（vbuser1b）真机三包 screenshot 全绿（4542B / 5367B / 3758B）。

---

> 本卡片是当前跟踪视图；已关闭记录见 [已关闭-近期.md](已关闭-近期.md)。
> 历史台账 [问题登记.md](../问题登记.md) 自 2026-10-08 起停更（仅存档）。
> 状态变化请改 `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
