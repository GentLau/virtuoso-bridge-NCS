# 第五轮 · 真实业务场景补充（2026-09-23 23:5x–00:2x）

> 本轮在原有 S13（两用户共建 SerDes RX，15/15）与 S14（ADC SAR 22/22）之外，
> 又补了 **S15 多跳/代理**（11/11，见 `第五轮测试报告.md` §11.1）与
> **S16 两真实 OS 用户的 layout 接力/并发**（本文件）。另外两个计划中的场景
> （设计迭代二次出图、真实多实例规模）**未完成**，在 §3 如实声明。

## S16 `multiuser_layout_handoff_tb.py` —— 两个真实 OS 用户改同一张版图

**怎么跑**

```bash
PYTHONPATH=src python test/live/flows/multiuser_layout_handoff_tb.py \
    --work-dir test/artifacts/env/log-vblog \
    --base http://127.0.0.1:8127/api/operation \
    --lib adc_sar --lib-path /project/libs/adc_sar \
    --out test/artifacts/evidence/round5-realscen/multiuser-layout-handoff.json
```

**判据（不是"接口 ok"）**：A（`vb-vbuser1`）写 2 个矩形 → A 自读形状数 ≥2 →
B（`vb-vbuser2`）在 A 结束后读到的形状数**与 A 相同** → B 再写 1 个 →
**A 回读必须看到 B 的新形状**（跨用户、跨 daemon 可见）→ 并发写至少一方成功且
失败方必须是锁类结构化错误 → 收尾无 `*.cdslck` 残留。

**结果：8/11**（证据 `round5-realscen/multiuser-layout-handoff.json`；
含一条 `cleanup-cell` —— 跑完把共享库里的测试 cell 删掉并复核，避免"测试自己造垃圾"）

| 用例 | 结果 | 说明 |
|---|---|---|
| create-layout-view | ✅ | A 建 `adc_sar/mu2_handoff_*` 的 layout view |
| A-writes-two-rects | ✅ | 产品路径 `virtuoso.layout.write`（`place_rect` M1/drawing） |
| A-reads-own-shapes | ✅ | `layout.read` 解析出 2 个 `("shape" "rect" "M1" ...)` |
| **B-sees-A-shapes** | ✅ | **跨用户读可见**（B 读到的形状数与 A 逐字一致） |
| **B-writes-after-A** | ❌ | `dbCreateRect: Invalid layer/purpose ("M1" "drawing")` —— **B 的会话解析不了 PDK 层名**（见 P-068） |
| A-sees-B-shapes | ❌ | 因 B 写失败，形状数没变（连带失败，不是独立缺陷） |
| concurrent-write-structured | ❌ | A 被锁挡住（`layout view ... is locked by another session`，结构化、符合契约）；B 仍是层名错误 → "至少一方成功"不成立 |
| A-can-still-write | ✅ | 并发/失败之后 A 仍能写（系统未卡死） |
| no-cdslck-residue | ✅ | 收尾目录无 `*.cdslck`（P-044 修复后的锁清理有效） |
| final-read-ok | ❌ | 终检形状数 3 < 4（因 B 的写入始终没成功） |
| cleanup-cell | ✅ | 跑完 `ddDeleteObj`（失败则 `rm -rf` 回退）+ `ls` 复核：共享库不留测试 cell（`--keep-cell` 可保留） |

**结论**：**跨用户读、锁交接、失败后可用性、锁清理**这四件事在真实双 OS 用户下成立；
但"第二个用户能不能在**共享 PDK 库**里画形状"不成立 —— 已登记 **P-068**（归属待定：
产品层名解析 or 会话级 PDK 环境）。

## 我做的排查（都记录在案，避免下轮重复）

| 动作 | 结果 |
|---|---|
| 两个用户查 `ddGetObj("adc_sar")~>techLibName` | 都是 `"tsmcN65"`（库绑定一致） |
| 两个用户查 `techGetTechFile(ddGetObj("adc_sar"))` | 都返回有效 tech id（不同 db id） |
| B 打开已有 layout（`sar_top_205836`）后再写 | 仍失败（不是"没打开过 tech"这么简单） |
| B 跑 `techBindTechFile(adc_sar, tsmcN65)` 后再写 | `errset` 返回 nil（调用本身报错），写仍失败 |
| B 在自己的新 cell 里写（排除"跨用户创建"因素） | 同样失败 → **不是**跨用户问题，是 B 这个会话的层名解析问题 |
| B 读同一个 cell | 正常（读路径不需要层名解析） |

## 3. 未完成 / 声明缺口（不声称覆盖）

| 计划场景 | 状态 | 原因 |
|---|---|---|
| `design_iteration_tb.py`（改图→二次出 symbol→版图→GDS→AC 前仿→`measure` 默认 `x="freq"`） | **未做** | 本轮时间用在了 P-064/P-065/P-068 排查与覆盖率补强；P-053/P-054 已有探针级证据钉住（`round4-probes/`），但**"整条迭代链一次跑通"仍缺** |
| `scale_real_instances_tb.py`（真实多实例规模，spec 缺口 X2） | **未做** | 同上；X2 仍是明缺口（现有替代：S4 = 100 个协议级 fake） |
| LVS 全链 | 仍缺 | `si -batch`/auCdl 对 PDK 器件失败 → 无源网表（见台账"明确不立案"段与 X 系列） |
