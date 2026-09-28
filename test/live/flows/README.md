# flows/ —— 跨包工程场景（**真机级**）

> **测试级别：真机测试**（全真环境；操作严格按真实用户流程产生）。
> 与 `packages/` 的分工：`packages/` 证明"某个包单独能不能用"；本目录证明"连起来能不能干活"——
> 上一步留下的状态、空视图、DRC 过但 LVS 对不上……只有串起来才暴露。
> （原 `test/offline/scenarios/` 已并入本目录，避免同义目录分裂。）

| TB | 场景 | 需要什么 | 证据 |
|---|---|---|---|
| `s11_full_flow.py` | **S11** spec→schematic→symbol→layout→GDS→DRC→LVS→前仿→后仿（分阶段、逐阶段落证） | 业务面 8127 + **启动时已加载 PDK 的 CIW** | `test/artifacts/evidence/round8/s11/s11-<stage>.json` + `summary.json` |
| `project_flow_tb.py` | **S11（仿真支线）** probe/lib/schematic/symbol/layout/gds/sim 分阶段可增量跑 | calprobe 真实例（含 tsmcN65 的 cds.lib）+ PDK 路径 | `test/artifacts/env/scenario-project65/evidence-*.json` |
| `lvs_from_schematic_tb.py` | 原理图 → CDL → Calibre LVS 的专项链路 | PDK deck + 真实例 | 见其 `--out` |
| `s11_postsim_compare.py` | 前仿/后仿网表同测试台对照（Δ 判据） | 两份 netlist + spectre | `test/artifacts/evidence/s11-postsim/postsim-evidence.json` |
| `s11_inprocess_lvs_tb.py` | S11 的 in-process 变体（export→upload→LVS 一条命令）；产出 `artifacts/s11/flow.json` | vbs11 真实例（token `vb-s11`） | `test/artifacts/env/s11/flow.json` |
| `role_split_tb.py` | **S2** 多 role 分主机（daemon/command/file 落点各不相同） | 注册表 `test/artifacts/env/scenario-role-split/registry.json`（用户 `rolesplit`，token `vb-s11`）+ wsl-gent/w1 可达；**该 profile 用 openssh 后端**（原因见 `test/reports/环境建设说明.md` §2.4） | `test/artifacts/evidence/round8/role-split-r8.json` |
| `scale_100_tb.py` | **S4** 协议级 100 daemon 规模 + 隔离 | 无外部依赖（本机自己起 100 个 fake 并生成 100 用户注册表） | `test/artifacts/env/scenario-scale-100/evidence.json` |
| `serdes_rx_flow_tb.py` | **真实业务场景 A**：差分 SerDes RX（端接+CTLE+缓冲）→ 层次化原理图 → symbol → 版图 → GDS → CDL → DRC/LVS → AC/TRAN 仿真（带数值判据） | calprobe 真实例（tsmcN65 + Calibre），token `d6af595b…`；`--with-calibre` 追加 DRC/LVS | `test/artifacts/evidence/round8/serdes/`（11 段 + `summary.json`） |
| `adc_sar_flow_tb.py` | **真实业务场景 B**：SAR ADC（cmp/latch/top）全链 + 版图 + 仿真，**两个真实用户**交叉参与 | 两个真实例 token（`vb-vbuser1`/`vb-vbuser2`） | `test/artifacts/evidence/round8/adc-sar-r8.json`（24/24） |
| `multiuser_serdes_rx_tb.py` | **S13 两真实用户共建**同一库/cell（交叉读写，判"谁写谁读得到"） | 同上两个 token + 共享库映射 | `test/artifacts/evidence/round8/serdes-multiuser-r8.json`（17/17） |
| `multiuser_layout_handoff_tb.py` | **S16 版图接力**：A 不关闭会话，B 接着读/写；断言无残留锁（`no-cdslck-residue`） | `--work-dir test/artifacts/env/log-vblog` + 两个 token | `test/artifacts/evidence/round8/multiuser-layout-handoff-r8.json`（12/12） |
| `design_iterate_tb.py` | **真实业务场景 C（迭代链）**：改图 → 二次出 symbol → 版图二次发布 → 仿真复测；网表由 `schematic.read` 回读的**连接+参数**现场拼装；断言带宽/增益的**方向变化** | calprobe 真实例 `d6af595b…`；`--with-lvs` 追加 P-069 验收链（真实 cell `CMP_LIB/inv2` → `correct`） | `test/artifacts/evidence/round8/design-iterate-r8/`（11 段 + `iteration-summary.json`） |
| `multihop_jump_tb.py` | **拓扑**：jump 主机与 SOCKS5 代理叠加（含经 jump 的 daemon SKILL 与文件往返 sha256；直连/经跳来源 IP 对照） | `--work-dir test/artifacts/env/multihop`（含 token `vb-hopjump`/`vb-hopsocks`/`vb-hopfake` + 负控制 `vb-lab11`）；w3-gent 需在线（jump 主机） | `test/artifacts/evidence/round8/multihop-r8.json`（10/10） |
| `layout_suite_p044_workaround_tb.py` | ~~P-044 临时绕行 runner~~ **已删除**：P-044 已修复，正式套件 `packages/layout_e2e_tests.py` 直接跑（本轮 PASS） | — | — |

## 约定

- 每个 TB 单独跑、单独落证据，**不放进 `testpaths`**（它们要真机或大量端口，不进 CI）；
- 场景需要的注册表写在各自的 `artifacts/scenario-*/registry.json` 里，**一场景一份**，互不复用；
- 证据里必须能看出"判据是什么、为什么这算通过"——例如 S4 用 fake daemon 回显自身 token 来证明
  **没有串台**，而不是只证明"连得上"；
- 破坏性动作（起/停 WSL、占端口、写远端目录）由 TB 自己负责收尾，跑完要能立刻复跑。

## 常用命令

```powershell
python test/live/flows/project_flow_tb.py --stage sim --cell inv2
python test/live/flows/role_split_tb.py
python test/live/flows/scale_100_tb.py --count 100 --rounds 2
```

## 写新场景的约定

1. 一个场景一个脚本，文件名 `s<n>_<名字>.py`，并登记到上面的表；
2. 复用 `test/shared/runners/` 的 runner 与 `test/shared/fixtures/` 的 helper，不要再造一套；
3. 场景**必须**逐阶段落证据：没有证据的场景不算跑过；
4. 需要真机/PDK 的场景在脚本 docstring 写清前置环境，缺环境时**明确失败**而不是静默跳过。
