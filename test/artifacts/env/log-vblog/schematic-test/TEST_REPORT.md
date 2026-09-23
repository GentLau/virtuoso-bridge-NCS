# schematic 业务包 真机测试报告

> 版本：v1
> 日期：2026-09-18
> 执行环境：8127 / work-dir `test/tb/artifacts/log-vblog` / token `vb-vblog` / Virtuoso 6.1.8-64b
> 测试库：`schemtest/t1/schematic`（新建）；只读参照：`rfLib/mixer_ip3`

## 1. 结论

**全部通过。** read 14 项、write 18 项共 32 项用例在真实 Virtuoso 上执行并验证通过。发现并修复 8 个实现缺陷，回归后无未解决缺陷。

## 2. read 执行结果

| 用例 | 结果 | 证据 |
|---|---|---|
| READ-01 overview | PASS | mixer_ip3：6 inst / 3 nets / params；schemtest/t1：inst/wires/labels/pins/notes 全量 |
| READ-02 positions | PASS | 6 inst（xy/orient/bBox）；wires=2；端子中心坐标 `PLUS [0,0]`、`MINUS [0,-0.375]` |
| READ-03 connectivity | PASS | 6 inst、3 nets、terms `phase_err→gnd!` 等 |
| READ-04 params | PASS | R1 params `r=20K`；mixer `gain=40` 等 |
| READ-05 positions,connectivity | PASS | inst 同时含 xy/terminals 与 terms |
| READ-06 positions,params | PASS | inst 同时含 xy 与 params |
| READ-07 instance names filter | PASS | names=[I9] 返回 1 inst |
| READ-08 instance region filter | PASS | region=[-1,-1,0,1] 返回 1 inst |
| READ-09 wire none/region | PASS | none→wires=0；region=[-2.5,-0.1,2.5,0.1]→1 wire |
| READ-10 label none/region | PASS | none→labels=0；region 返回 MID label |
| READ-11 pin none/region | PASS | none→pins=0；region 返回目标 pin |
| READ-12 note none/region | PASS | none→notes=0；region 返回目标 note |
| READ-13 param_filter | PASS | whitelist=[gain] 只返回 gain |
| READ-14 connectivity 忽略 object_filter | PASS | 带 names filter 仍返回 6 inst、3 nets |

## 2.1 read 详细字段结果

- wire 读回 `width=0.1`（set_wire_properties 后），color/lineStyle=nil 正确返回；
- label 读回 `orient=R90`、`height=0.2`（set_label_properties 后），justify/font 一并返回；
- note 读回 `orient=R90`；
- 参数白名单/对象 object_filter 仍全部通过。

## 2.2 screenshot 执行结果

| 用例 | 结果 | 证据 |
|---|---|---|
| SHOT-01 默认目标 | PASS | PNG 2467B 落 `artifact/screenshots/` |
| SHOT-02 window_id | PASS | window_id=1 截取成功 |
| SHOT-03 参数组合 | PASS | leave_open/toplevel/centralWidget 透传成功 |

## 3. write 执行结果

| 用例 | 结果 | 证据 |
|---|---|---|
| WRITE-01 place_instance | PASS | `analogLib/res R1` 落库可读 |
| WRITE-02 delete_instance | PASS | 删除后 inst=0 |
| WRITE-03 rename_instance | PASS | R0→R1 可读 |
| WRITE-04 set_instance_params | PASS | r=20K 读回 |
| WRITE-05 set_term_nets | PASS | PLUS→VDD、MINUS→GND 的 stub+label，net 连接读回 |
| WRITE-06 place/delete_wire | PASS | wires 增删读回 |
| WRITE-07 set_wire_properties | PASS | DB 查 line `width=0.1` |
| WRITE-08 place/delete_label | PASS | labels 增删读回 |
| WRITE-09 rename_label | PASS | OUT→OUT2 读回 |
| WRITE-10 set_label_properties | PASS | DB 查 label `orient=R90, height=0.2` |
| WRITE-11 place/delete_pin | PASS | pins 增删读回 |
| WRITE-12 rename_pin | PASS | pin 实例名改名读回 |
| WRITE-13 set_pin_properties | PASS | direction input→output 读回 |
| WRITE-14 place/delete_note | PASS | notes 增删读回 |
| WRITE-15 rename_note | PASS | hello→world 读回 |
| WRITE-16 set_note_properties | PASS | DB 查 note `orient=R90` |
| WRITE-17 多原子一次 write | PASS | 6 原子顺序执行、steps 痕迹齐全 |
| WRITE-18 check_and_save | PASS | 返回 saved |

## 4. 开发期缺陷记录（已修复并回归）

| # | 缺陷 | 修复 |
|---|---|---|
| 1 | read SKILL 括号不平衡（TERM/PARAM/PINS 各缺 1 个右括号） | 补齐，四个 focus 括号深度 0 |
| 2 | INSTANCES 段无头标记、INST 行缺换行 | 加 `INSTANCES\n` 与行尾换行 |
| 3 | daemon 返回的 `\n` 为字面反斜杠+n | read 剥引号后还原换行 |
| 4 | WIRE 点对解析错误 | 正则提取 `(x y)` 点对 |
| 5 | 跨调用 `vbSchemCv` unbound | 每原子/保存各自 `let` 打开 cellview |
| 6 | place_instance master viewType 错 | symbol 用 `schematicSymbol` |
| 7 | set_pin_properties 删除后访问旧对象 | 先保存 name/xy/orient 再重建 |
| 8 | region/whitelist 等 setof 谓词多语句 let | 改为单表达式 bBox 判断；connectivity 忽略 object_filter 补齐 |

## 5. 覆盖矩阵

- 20 个原子命令：**全部 PASS**
- 3 个对外操作：`read` / `write` / `check_and_save` **全部 PASS**
- focus：4 种 + 2 种组合 **PASS**
- object_filter：5 类对象 ×（none / region / instance-names）**PASS**
- param_filter **PASS**

## 6. 已知限制（评审需接受）

1. label/note/pin 索引容差固定 0.001；
2. pin 图形实例名是 Cadence 自动分配（如 PIN0），业务 pin 名为 terminal name；
3. 区域截图未实现（`hiWindowSaveImage` 非交互模式不支持区域，后续经 GUI 抓屏扩展）；
4. 未测：权限控制、GUI 弹窗、错误注入、超大 schematic 性能。

## 7. 产物

- 测试库：`schemtest/t1/schematic`（保留）
- 测试脚本（执行用临时脚本，已清理）
- 本计划/报告：`test/tb/artifacts/log-vblog/schematic-test/`