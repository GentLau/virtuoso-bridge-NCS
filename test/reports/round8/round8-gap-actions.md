# 第八轮条款缺口动作（partial → 待补测试）

> 共 12 条：**待补测试 6 条（verdict=partial）** + 6 条已声明由其它 TB/环境限制承担（verdict=indirect）。
> 待补项完成后把对应行的 verdict 提升并回填证据。


## A. 待补测试（partial）

### 配置#108（中层/add-中层配置文档.md）

- 条款：**联合端口**：`mode=local` 时 `daemon_port` 与 `local_port` 是同一个候选端口——任一缺省由同一值生成并同步写入，显式双值必须相等。
- 现状：缺省→同值生成并同步写入有断言；**显式双值不等**时实测被静默归一化（local_port 胜出、daemon_port 请求被丢弃，见 P-079），flow.py:705-715 的拒绝守卫在正常流程不可达
- 待补：P-079 定口径后补测：钉住用例 TestLocalJointPortNotCoerced 修复前红；若选‘local_port 优先’需把用例改成断言归一化行为

### schematic#050（上层/2-schematic.md）

- 条款：- 多点：`points: [pos, …]`；区域/矩形：`region` / `bbox` 一律**对角两点** `[pos0, pos1]`（read 与 write 同形，**不再用四元组**）；
- 现状：points=[pos,…] 两点/多点有断言；**region 的对角两点在 read 过滤与 screenshot 仍失败（P-082）**，实现只收四元组，与该条‘不再用四元组’冲突
- 待补：P-082 修复后补两点正例（read 过滤 + screenshot）并复跑

### verilog#101（上层/8-verilog.md）

- 条款：3. `ihdl` **返回码不可信**：语法错误、参考库缺失、降级导入都是 rc=0；成功看 `357/372/345`，
- 现状：‘rc 不可信、只看日志+产物’有断言；**成功标记 357/372/345 的识别分支**无用例
- 待补：补离线：三种成功标记日志 → 判成功；缺失标记 → incomplete_log

### verilog#103（上层/8-verilog.md）

- 条款：4. `ihdl` 会向 `-cdslib` 指定的文件**追加 DEFINE**（目标库未注册时还在 cwd 建同名库目录）→ 必须用按次副本；
- 现状：按次副本在建命令里有体现；**ihdl 向 -cdslib 追加 DEFINE 的防污染效果**（共享文件保持不变）无断言
- 待补：真机补：import 后共享 cds.lib 未被追加（sha 对比）+ 无 cwd 同名库目录残留

### calibre#069（上层/12-calibre.md）

- 条款：终态或超时即返回；超时返回 `status=timeout` 且**后台作业继续跑**。
- 现状：部分覆盖且已定位偏差：后台作业不被杀 ✓；但 deadline 到点返回最后一次 status（running）而非 spec 的 `timeout` —— 已立 P-098 并加 strict-xfail 红灯钉（--runxfail 实锤 'timeout' != 'running'）。修复后本行可升 direct。
- 待补：设计修 P-098（收尾口径：非终态超时 → status=timeout，可保留 last_status 字段）→ 红钉转绿后复评

### calibre#123（上层/12-calibre.md）

- 条款：> 边界：set 只携带**参数**，不携带数据——它引用的 layout / 源网表 / hcell 文件必须已存在于远端；
- 现状：set 走官方入口有断言；**‘set 只带参数、引用数据必须已存在’的失败边界**无专门用例
- 待补：补：set 引用不存在的 deck/layout → 明确失败（不静默回退）


## B. 已声明承担方式（indirect / 环境限制，不单独立项）

### 总览#094（总览/1-四层整体架构与接口.md）

- 条款：1. 业务参数校验、操作顺序和领域对象；
- 现状：参数校验有包级离线契约、操作顺序由包 E2E 间接体现；无独立条款级用例（该行是职责列表片段）
- 承担方式：—（由包契约+E2E 共同承担，不单独立项）

### 总览#211（总览/1-四层整体架构与接口.md）

- 条款：底层只连接一个 Virtuoso 会话并执行 Skill，不扩展成通用远程命令代理。**一个 token = 一个活动 daemon = 一个 CIW**；不同 token 不得共享同一个底层 Skill 通道；需要第二个 CIW 必须注册第二个 user/token。
- 现状：一 token→一 daemon 的映射与多 token 隔离有断言（离线多用户 + 真机四 token）；‘第二 CIW=配置错误’属环境约定，无负向用例
- 承担方式：—（环境约定项，不做负向）

### 路由#024（中层/3-路由设计.md）

- 条款：这条准则同时是评审 P0-01 的关闭口径：规范不再承诺"gui 与 daemon 必须同机"，也不再假设；bridge 按配置投送。
- 现状：role 跨主机不被拒绝已有真机证据（daemon/gui 在 wsl-gent、command/file 在 w1）；**gui 与 daemon 异机**无环境（第二台真 GUI 主机）——桥层按配置投送，不假设同机
- 承担方式：环境限制项：如需闭合，需第二台带 X/Virtuoso 的主机；当前以‘跨主机投送不被拒绝’的同等证据承担

### 注册#011（其他/1-多用户与注册.md）

- 条款：- **token 使用范围**：只用于路由与校验（注册表路由、daemon 比对、Skill 请求）；用户可读路径一律用唯一用户名，不用 token。
- 现状：部署/根路径按 userid 组织（注册表实际条目可见）；‘token 不得出现在用户可读路径’无单独负向断言
- 承担方式：可选：断言注册部署产物路径不含 token 值（六步 TB 内一行）

### verilog#060（上层/8-verilog.md）

- 条款：（ihdl 会往里追加 `DEFINE`，不能给共享/全局那份）；
- 现状：实现在 run_dir 生成 cds.lib 副本（不给共享份）；真机导入成功隐含该路径，但**无断言共享 cds.lib 未被追加 DEFINE**
- 承担方式：真机补：import 前后对比共享 cds.lib sha256 不变 + run_dir 副本存在

### verilog#065（上层/8-verilog.md）

- 条款：3. 执行（**必须带 LD_LIBRARY_PATH 前缀**，否则缺 `libsasl2.so.2`、rc=127）：
- 现状：真机 import 成功即证明前缀生效（否则 libsasl2 缺失 rc=127）；**无直接断言命令前缀**
- 承担方式：可选加固：离线断言生成命令以 LD_LIBRARY_PATH=… 开头


<!-- 处置记录（人工维护，重跑本脚本不会覆盖） -->







## 处置记录

> 2026-09-28 23:15（测试 root）。上面 A/B 两节由 `merge_round8_spec_matrix.py` 生成；本节的处置结论手工维护。

### A. 待补 6 条的活动状态

| 条款 | 依赖 | 当前状态 | 收口判据 |
|---|---|---|---|
| 配置#108 (P-079) | 设计定口径（拒绝 or 归一化） | 红钉用例 `TestLocalJointPortNotCoerced` 已在离线树（strict-xfail，P-079 修复前红） | 设计修 P-079 → 红钉转 XPASS；若选"local_port 优先"则把用例改判归一化 |
| schematic#050 (P-082) | 设计修 `region` 两点 | 探针 `schematic_region_two_point_probe.py` 已红（P-082） | 两点正例在 read 过滤 + screenshot 双通过 |
| verilog#101 | 测试侧（本车道） | 车道 `verilog_params` 在补：三种成功标记（357/372/345）识别 + 缺失标记 → `incomplete_log` | 离线用例合并后回填证据 |
| verilog#103 | 测试侧（本车道） | 同上：真机 sha256 对比共享 `cds.lib` 未被追加 + 无 cwd 同名库目录残留 | 真机 import 用例回填 |
| calibre#069 (P-098) | 设计修超时口径 | 红钉 `test_calibre_timeout_status.py`（`--runxfail` 实锤 `running` ≠ `timeout`） | 设计修 P-098 → 红钉转绿 |
| calibre#123 | 测试侧（本车道） | 车道 `calibre_params` 在补：set 引用不存在的 deck/layout → 明确失败 | 真机用例回填 |

### B. 处置顺序约定

- A 组任一条收口后：把对应 `norm-review/g*.json` 的 verdict 从 `partial` 提升为 `direct`/`indirect` 并补 `evidence`，
  重跑本脚本；**不得**只改生成的 md 不改 JSON。
- B 组（6 条 indirect）为已声明承担方式，本轮不再立项；如需关闭需给出同等或更强的证据。

