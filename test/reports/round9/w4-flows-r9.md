# round9 · W-4 收口：serdes flow 关键 stage 的值级读回

> 执行：subagent `/root/opparam_r9`｜2026-09-29 21:01｜对象 TB：`test/live/flows/serdes_rx_flow_tb.py`
> 来源：`weak-assertions.md` W-4（"stage 只有操作成功语义，值级读回不均"）

## 1. 先把 W-4 的范围说准（复核后的修正）

逐行看完四个 stage 后，真实情况是**不均**，而不是全都缺：

| stage | 复核前的值级判据 | 结论 |
|---|---|---|
| `stage_top` | **已有**：读回 instances + 每个实例的 master（`XCTLE/XTERM/XBUF → LIB/CELL`）并逐条比对，另存 `nets` | 不缺 |
| `stage_layout` | **已有**：读回 instances 数（≥3）与 shape 数 | 偏弱但不缺 |
| `stage_ctle` | **已有**：`nets` 连接表 + `net_mismatches` + symbol 覆盖 | 不缺 |
| `stage_buf` | **完全没有读回**：write → check_and_save → symbol.generate，只记"操作 ok" | **真缺口 → 本轮补上** |

## 2. 改了什么

1. 新增两个纯函数从命令表**推导期望**（改命令表时判据自动跟随）：
   `_placed_names(commands)`（`place_instance` 的 name）、`_term_net_names(commands)`（`set_term_nets` 的值）。
2. 新增 `_readback_schematic(t, cell, st, label, commands)`：`virtuoso.schematic.read` 读回后
   比对**实例名集合**与**网络名集合**，缺失即 `st.bad(...)`（沿用 flow 的判据聚合，任何 `bad` 让整条 TB 失败）。
3. 接入点：`stage_buf`（本轮主缺口）+ `stage_ctle`（补一条显式"实例集合"断言；其 net 级判据已有）。

## 3. 验证（http，8127 标准形态；在 maestro 套件退出后独占运行）

| 命令 | 结果 | 读回实测值 |
|---|---|---|
| `--stage buf` | **rc=0，ok=true（6.75s）** | `buf_instances = ["MN","MP"]`、`buf_nets = ["vdd","vin","vout","vss"]` |
| `--stage ctle` | **rc=0，ok=true（16.95s）** | `ctle_instances = ["CS1","CS2","M1","M2","M3","R1","R2","RS1","RS2"]`、`ctle_nets` 10 条含 vinp/vinn/outp/outn/vbias/vdd/vss；`net_mismatches = {}` |

证据：`test/artifacts/evidence/round9/serdes-r9-buf/{serdes-buf.json,summary.json}`、
`test/artifacts/evidence/round9/serdes-r9-ctle/{serdes-ctle.json,summary.json}`。
TB 注释头（作者/最后改动 21:00）与 `py_compile` 均通过。

## 4. 台账影响

- `weak-assertions.md`：**W-1 / W-2 / W-3 / W-4 全部关闭**；只余 offline 97 例低风险弱断言（按报告 §4 不改写）。
- 无新产品 bug：新断言全部通过，且 `net_mismatches` 为空说明 CTLE 的连接关系与期望一致。
