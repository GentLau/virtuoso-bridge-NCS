# symbol 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-21
> 对象：`src/pyapi/packages/symbol.py`（业务包：symbol）
> 依据：`spec/design-concepts/上层/3-symbol.md`（Draft v2）

## 1. 目标与范围

验证 symbol 业务包 5 个对外操作在真实 Virtuoso 环境下满足 spec：

| 大类 | 操作 |
|---|---|
| 读 | `read`（`focus` 可组合） |
| 写 | `write`（原子批写 + 末尾 check/save）、`check_and_save` |
| 生成 | `generate`（schematic → symbol，临时 view + 校验 + 备份回滚） |
| 导出 | `screenshot`（含可选 `region` 缩放） |

重点验证：

1. `read` 能读回 terms / labels / shapes / orders / selection box，且 `focus` 过滤真实生效；
2. `write` 的几何、标签、引脚、结构原子在真机上可执行、可回读；
3. `write` 只 append、不 replace：目标 view 不存在时必须失败，不得静默创建；
4. `generate` 的 created / overwrite / 同源同目标 / 目标已打开四类分支行为正确；
5. `screenshot` 产物真实落到本地工作目录。

## 2. 环境

| 项 | 值 |
|---|---|
| 业务面 | `127.0.0.1:8127`（`server.api_server`）/ 直连 `server.dispatch` |
| work-dir | `test/tb/artifacts/log-vblog` |
| token | `vb-vblog` |
| Virtuoso | 6.1.8-64b（WSL `wsl-gent`，DISPLAY=:99） |
| 测试库 | `schemtest` |
| 执行脚本 | `test/tb/symbol_e2e_tests.py`（`--transport direct|http`） |
| 单操作探针 | `test/tb/symbol_pkg_probe.py` |

## 3. 测试台

| cell | view | 来源 | 用途 |
|---|---|---|---|
| `symfinal` | `symbol` | 预置夹具（真机手工构造） | 四类几何 + 三类 label + 三个 terminal 的读回样本 |
| `sym_e2e` | `symbol` | 用例自动创建/清理 | write / check_and_save / screenshot |
| `gen_e2e` | `schematic` + `symbol_a` | 用例自动创建/清理 | generate 全部分支 |

## 4. 测试用例

### 4.1 读

| 用例 | 输入 | 预期 |
|---|---|---|
| READ-01 | `read(schemtest/symfinal/symbol)` | terms 含 `IN/OUT/BI`；`pin_order=[IN,OUT,BI]`；shapes 含 line/rect/polygon/ellipse；labels 含 pin 名；selection box 存在 |
| READ-02 | 同上 `focus=["terms","orders"]` | 只返回 terms 与 `pin_order/port_order/term_order`，无 labels/shapes |

### 4.2 写

| 用例 | 输入 | 预期 |
|---|---|---|
| WRITE-01 | 10 条原子：place_rect / place_polygon / place_ellipse / place_label(drawing,instance,logical) / place_pin×2 / set_selection_box / set_pin_order | 全部 applied；回读 terms=`{IN,OUT}`、`pin_order=[OUT,IN]`、selection box 唯一 |
| WRITE-02 | 9 条原子：set_shape_properties(rect/polygon) / rename_label / set_label_properties / rename_pin / set_pin_properties / delete_shape / delete_label / delete_pin | 回读后 terms=`{IN}`、ellipse 消失、logical label 消失 |
| WRITE-03 | `write` 到不存在的 view | 失败（ok=false），不创建 view |
| CHECK-01 | `check_and_save(sym_e2e/symbol)` | 返回 `saved=true` |

### 4.3 生成

| 用例 | 输入 | 预期 |
|---|---|---|
| GEN-01 | `generate(gen_e2e, schematic→symbol_a, overwrite=false)` | `action=created`；terminal_names=`{A,B,C}` |
| GEN-02 | 目标已存在且 `overwrite=false` | 失败 |
| GEN-03 | `overwrite=true` | `action=replaced` |
| GEN-03b | `symbol_view == schematic_view` | 失败 |
| GEN-03c | 目标 symbol 已在窗口打开 + `overwrite=true` | 失败（不破坏打开中的 view） |

### 4.4 截图

| 用例 | 输入 | 预期 |
|---|---|---|
| SHOT-01 | `screenshot(schemtest/sym_e2e/symbol)` | 返回远端路径 + 本地路径；本地 PNG 存在且非空 |

## 5. 通过准则

- 全部用例 PASS；任一失败必须给出失败响应原文与 SKILL 输出；
- 每个写用例都要有回读证据（不能只看写返回）；
- 已知限制单独列出，不得用"未测"掩盖失败。
