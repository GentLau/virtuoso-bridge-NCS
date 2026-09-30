# P-118 · `set_job_policy(job_type="netlisting")` 在未设置过该 policy 的 test 上报 **ok=true 但零效果**（`read_config.job_policy.netlisting` 恒 `null`）——静默 no-op

| 字段 | 值 |
|---|---|
| 级别 | P2（静默 no-op：调用方以为 netlisting job policy 已生效；与 P-114/C10 同族） |
| 层 | 上层（maestro 包）· `set_job_policy` 的 `job_type=netlisting` 分支 |
| 归属 | 设计侧（`maestro.set_job_policy` 的 netlisting 分支：`maeGetJobPolicy` 返回 nil 时应创建/或结构化失败，不得静默成功） |
| 状态 | **待设计修** |
| 位置 | `src/pyapi/packages/maestro.py:1402-1429`（`jp = maeGetJobPolicy(...) when(jp …) maeSetJobPolicy(jp …)` —— `jp=nil` 时整段 no-op 且无错误） |
| 首报 | 2026-09-30（测试/root：补 `read_config.job_policy.netlisting` 读回面覆盖时发现） |
| 最近更新 | 2026-09-30 23:55（新立） |

## 现象

真机（vblog，2026-10-01 00:0x，实例重启后复测）：触发条件是**目标 test 没有 netlisting policy 对象**（样本：`maestro_tb/rc_probe` 的 `ac` test，读回 `job_policy.netlisting == null`）：
① 对照组 `job_type="simulation"` + `policy={"maxjobs":2}` → `ok=true` 且读回 `simulation.maxjobs == 2`（写路径本身可用）；
② `job_type="netlisting"` + `policy={"maxjobs":1}` → `ok=true`，读回 `job_policy.netlisting` 仍 `null`；
③ 反复写不同值（1 / 9）都 `ok=true`、读回都 `null`（零效果）。
对照：本 TB 自建的 `nkm_*` setup（ADE 默认已建 netlisting policy）写同参数**能**值级读回 → 缺 policy 才触发静默 no-op。

## 复现

```text
对任一 test 调 `maestro.write(commands=[{op:set_job_policy, test_name:…, job_type:"netlisting", policy:{maxjobs:1}}])`，
再 `read_config` 读 `tests.<test>.job_policy.netlisting`（恒 null）；对照 simulation 分支可正常落盘。
```

## 证据

`test/artifacts/evidence/round9/maestro-netlisting-policy-probe.txt`（逐次实测）+ `test/artifacts/evidence/round9/maestro-nkm-p118.txt`（TB 红钉：10 PASS + NKM-09 FAIL，含 baseline/after 值）+ `maestro-nested-keys-p118-verify2.json`

## 验收判据（修好即转绿）

① `job_type=netlisting` 要么真正把 policy 落盘并能值级读回，要么在“该 test 没有 netlisting policy”时**结构化失败**（点名原因/建议），不得返回 ok；② spec `6-maestro.md:94` 的选择器语义与实现一致；③ TB NKM-09 转绿（或按裁决改成“结构化拒绝”断言）。

## 下一步 / 责任人

等设计定位；测试侧红钉已就位（放最后，不挡 NKM 其它用例）。


---

> 权威事实仍以 [问题登记.md](../问题登记.md)（台账）与 `第五轮-缺陷清单-*.md`（送修视图）为准；
> 本卡片只是「未关闭项」的逐条跟踪视图。状态变化请改
> `test/shared/runners/make_bug_cards.py` 后重新生成本目录。
> 卡片**可以手改**（测试侧维护：补现象、补判据、补证据直接写在卡里即可）。唯一要注意的是
> `make_bug_cards.py` 重新生成同名卡会覆盖手改内容——手改后顺手同步到 `make_bug_cards.py`
> 的对应条目（或先留一份），就不会丢（见 2026-09-28 教训：P-074 的「讨论决策」一度被刷新吃掉，已回填）。
