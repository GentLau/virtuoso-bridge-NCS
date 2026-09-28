# P-079 · local 模式显式 `daemon_port`≠`local_port` 被静默归一化（spec 要求双值相等；`_probe` 守卫不可达）

| 字段 | 值 |
|---|---|
| 级别 | P3（参数被静默丢弃） |
| 层 | 其他（注册流程） |
| 归属 | 设计侧（注册口径二选一，建议显式拒绝） |
| 状态 | **待设计修** |
| 位置 | `src/register/flow.py:1180-1185`（`_prepare_local_port`：`joint = role.local_port or role.daemon_port` 后**同步覆写两值**）与 `:705-715`（`_probe` 的‘双值必须相等’守卫——正常流程经第 2 步后二者已相等，**不可达**）；spec：`中层/add-中层配置文档.md` §6.4 |
| 首报 | 2026-09-28（第八轮条款逐条核账 · g1-core 配置#108 发现） |
| 最近更新 | 2026-09-28 |

## 现象

local 模式显式提交 `daemon_port=65091, local_port=65092`：第 2 步静默把两者都改成 **65092**（local_port 胜出），第 3 步照常 `probed`，无错误无告警 —— 调用方指定的 daemon 端口被丢弃。spec 措辞是「显式双值必须相等」，既未拒绝、也无文档写明优先级。

## 复现

```text
离线最小复现（测试侧实测，2026-09-28）：
  RegistrationRequest(mode="local", user="u", token="tok-local",
      roles={"daemon": {"daemon_port": 65091, "local_port": 65092}})
  → flow.validate() stage=validated、ports=(65092,65092)；flow.probe() stage=probed、errors=[]
脚本：`test/artifacts/tmp/_r8_joint_port.py`
```

## 证据

同上脚本输出；`test/offline/unit/test_register_flow.py::test_validate_preallocates_joint_port_for_local_mode`（只覆盖缺省同步，不含冲突双值）

## 验收判据（修好即转绿）

二选一：① **拒绝**（建议）：第 2 步发现显式双值不等 → failed，错误指向两个端口值（并补离线断言）；② **文档化优先级**：spec 写明 local_port 优先/或 daemon_port 优先，行为按文档固定并补断言。

## 下一步 / 责任人

设计侧定口径 → 测试侧补离线用例（`test_register_flow.py`）并复跑全套。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> **注意**：本目录的文件是**生成物**——任何人在卡片上手写的补充都会被下一次刷新覆盖，
> 请把补充写进 `make_bug_cards.py` 对应条目的 `extra` 字段（见 2026-09-28 教训：P-074 的
> 「讨论决策」一度被刷新吃掉，已回填）。
