# schematic 业务包 真机测试计划

> 版本：v1
> 日期：2026-09-18
> 对象：`src/pyapi/packages/schematic.py`（业务包：schematic）
> 依据：`spec/design-concepts/上层/2-schematic.md`（Draft v2）

## 1. 目标与范围

验证 schematic 业务包对外三个操作在真实 Virtuoso 环境下满足 spec：

1. `read`：focus（overview / positions / connectivity / params，含组合）、对象 object_filter（all/none/names/region）、param_filter、connectivity 忽略 object_filter；
2. `write`：通用写，20 个原子命令全部可用，且修改真实落库；
3. `check_and_save`：显式 `schCheck + dbSave`。

## 2. 环境

| 项 | 值 |
|---|---|
| HTTP 服务 | 127.0.0.1:8127（server.api_server） |
| work-dir | `test/tb/artifacts/log-vblog` |
| token | `vb-vblog` |
| Virtuoso | 6.1.8-64b（WSL，DISPLAY=:99） |
| 测试库/cell | `schemtest/t1/schematic`（专用，不碰生产库） |
| 参考读库 | `rfLib/mixer_ip3`（只读，用于多实例/参数用例） |

## 3. 前置条件

- 中层、daemon、8127 服务可用；
- 测试库 `schemtest` 与空 cell `t1/schematic` 已建；
- 所有写用例只作用于 `schemtest/t1`，结束后保留测试库供评审复查。

## 4. 测试设计

### 4.1 read 用例

| 用例 | 输入 | 预期 |
|---|---|---|
| READ-01 | focus=None | 返回 instances/nets/pins/labels/wires/notes 全量 |
| READ-02 | focus=positions | instances 含 xy/orient/bBox，wires、labels、端子中心坐标 |
| READ-03 | focus=connectivity | instances/terms/nets |
| READ-04 | focus=params | 每实例 CDF 参数 |
| READ-05 | focus=positions,connectivity | 组合字段并存 |
| READ-06 | focus=positions,params | 组合字段并存 |
| READ-07 | object_filter.instance={names:[...]} | 只返回指定实例 |
| READ-08 | object_filter.instance={region:[...]} | 只返回区域内实例 |
| READ-09 | object_filter.wire=none / region | 对应 wire 不出/只出区域内 |
| READ-10 | object_filter.label=none / region | 对应 label 不出/只出区域内 |
| READ-11 | object_filter.pin=none / region | 对应 pin 不出/只出区域内 |
| READ-12 | object_filter.note=none / region（focus=None） | 对应 note 不出/只出区域内 |
| READ-13 | param_filter=[...] | 只返回白名单参数 |
| READ-14 | focus=connectivity + object_filter | object_filter 被忽略（全量连接） |

read 返回字段（写入即读回）：
- instance：name/lib/cell/xy/orient/bBox/numInst/master_view/terms/terminals(params 白名单控制)
- wire：points/width/color/line_style
- label：text/xy/orient/justify/font/height
- pin：name/direction/xy
- note：text/xy/orient/justify/font/height

### 4.2 screenshot 用例

| 用例 | 输入 | 预期 |
|---|---|---|
| SHOT-01 | 默认 lib/cell/view，leave_open=False | PNG 下载到客户端 artifact/screenshots |
| SHOT-02 | window_id=1 | 截指定 Virtuoso 窗口成功 |
| SHOT-03 | leave_open=True + toplevel=False + central_widget=False | 参数透传、窗口保留 |

### 4.3 write 用例

| 用例 | 原子 | 验证 |
|---|---|---|
| WRITE-01 | place_instance | read 可见新实例 |
| WRITE-02 | delete_instance | read 实例消失 |
| WRITE-03 | rename_instance | read 新名字 |
| WRITE-04 | set_instance_params | read params 生效（r=20K） |
| WRITE-05 | set_term_nets | 端子生成 stub+label，net 生效 |
| WRITE-06 | place_wire / delete_wire | wires 增删 |
| WRITE-07 | set_wire_properties(width=0.1) | DB line width=0.1 |
| WRITE-08 | place_label / delete_label | labels 增删 |
| WRITE-09 | rename_label | label 文本变化 |
| WRITE-10 | set_label_properties(orient/height) | DB label orient=R90、height=0.2 |
| WRITE-11 | place_pin / delete_pin | pins 增删 |
| WRITE-12 | rename_pin | pin 实例名变化 |
| WRITE-13 | set_pin_properties(direction=output) | pin direction 变化 |
| WRITE-14 | place_note / delete_note | notes 增删 |
| WRITE-15 | rename_note | note 文本变化 |
| WRITE-16 | set_note_properties(orient=R90) | DB note orient=R90 |
| WRITE-17 | 一次 write 多个原子 | 顺序执行、逐步痕迹 |
| WRITE-18 | check_and_save | 返回 saved |

## 5. 风险与假设

- 写用例会修改测试库内容，测试顺序由"先写后读"保证；
- label/note/pin 索引容差 0.001（SKILL 定位实现）；同名 label 以 xy 消歧；
- pin 图形实例名是自动分配的（如 PIN0），业务名是 terminal name；
- 本计划不测并发、权限、异常注入与 GUI 弹窗。

## 6. 退出标准

- READ-01..14 全部通过；
- WRITE-01..18 全部通过；
- 所有通过项有真实 Virtuoso 数据证据；
- 未解决问题清零或记录为"已知限制"并经评审接受。