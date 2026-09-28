# 第八轮条款缺口动作（partial → 待补测试）

> 共 15 条；完成后把对应行的 verdict 提升并回填证据。

> **root 处置记录（2026-09-28 21:0x）**：
> * `注册#011` → **已完成**：`registration_role_split_tb.py` 新增 `deploy-paths-contain-no-token` 断言（6 条部署路径均不得含 token 值）。
> * `layout#179` → **已完成**：新增 `test/live/packages/layout_geometry_classification_e2e_tests.py` **4/4**——
>   正常 rect 成功且读回、零面积 rect 被包层预校验拦下（错误点名 `bbox requires pos0 < pos1`）、
>   非法 LPP 给出 SKILL 硬错误 + 非事务提示；证据 `evidence/round8/layout-geometry-classification.json`。
>   **口径差异记录**：spec 写“几何非法 → nil+WARNING”，实测包层提前预校验（更可归因）；
>   报告里按“实现更严格、建议同步 spec 措辞”记，不判缺陷。

## 总览#094（总览/1-四层整体架构与接口.md）

- 条款：1. 业务参数校验、操作顺序和领域对象；
- 现状：参数校验有包级离线契约、操作顺序由包 E2E 间接体现；无独立条款级用例（该行是职责列表片段）
- 待补：—（由包契约+E2E 共同承担，不单独立项）

## 总览#211（总览/1-四层整体架构与接口.md）

- 条款：底层只连接一个 Virtuoso 会话并执行 Skill，不扩展成通用远程命令代理。**一个 token = 一个活动 daemon = 一个 CIW**；不同 token 不得共享同一个底层 Skill 通道；需要第二个 CIW 必须注册第二个 user/token。
- 现状：一 token→一 daemon 的映射与多 token 隔离有断言（离线多用户 + 真机四 token）；‘第二 CIW=配置错误’属环境约定，无负向用例
- 待补：—（环境约定项，不做负向）

## 配置#108（中层/add-中层配置文档.md）

- 条款：**联合端口**：`mode=local` 时 `daemon_port` 与 `local_port` 是同一个候选端口——任一缺省由同一值生成并同步写入，显式双值必须相等。
- 现状：缺省→同值生成并同步写入有断言；**显式双值不等**时实测被静默归一化（local_port 胜出、daemon_port 请求被丢弃，见 P-079），flow.py:705-715 的拒绝守卫在正常流程不可达
- 待补：P-079 定口径后补测：钉住用例 TestLocalJointPortNotCoerced 修复前红；若选‘local_port 优先’需把用例改成断言归一化行为

## 路由#024（中层/3-路由设计.md）

- 条款：这条准则同时是评审 P0-01 的关闭口径：规范不再承诺"gui 与 daemon 必须同机"，也不再假设；bridge 按配置投送。
- 现状：role 跨主机不被拒绝已有真机证据（daemon/gui 在 wsl-gent、command/file 在 w1）；**gui 与 daemon 异机**无环境（第二台真 GUI 主机）——桥层按配置投送，不假设同机
- 待补：环境限制项：如需闭合，需第二台带 X/Virtuoso 的主机；当前以‘跨主机投送不被拒绝’的同等证据承担

## 注册#011（其他/1-多用户与注册.md）

- 条款：- **token 使用范围**：只用于路由与校验（注册表路由、daemon 比对、Skill 请求）；用户可读路径一律用唯一用户名，不用 token。
- 现状：部署/根路径按 userid 组织（注册表实际条目可见）；‘token 不得出现在用户可读路径’无单独负向断言
- 待补：可选：断言注册部署产物路径不含 token 值（六步 TB 内一行）

## schematic#018（上层/2-schematic.md）

- 条款：- `screenshot`：目标默认 `lib/cell/view`，可选 `window_id`；可选 `region=[pos0, pos1]`（user units，截前 `hiZoomIn(window, bBox)` 把区域填满窗口）；`toplevel` / `centralWidget` 暴露；`lea
- 现状：screenshot 基本路径（lib/cell/view + PNG）有真机用例；`window_id/region/toplevel/central_widget` 参数属第八轮 op×param GAP（shot_family 子代理补测中）；region 形状同时受 P-082（两点 vs 四元组）影响
- 待补：shot_family 交付后回填；P-082 修复后 region 用例需改两点

## schematic#050（上层/2-schematic.md）

- 条款：- 多点：`points: [pos, …]`；区域/矩形：`region` / `bbox` 一律**对角两点** `[pos0, pos1]`（read 与 write 同形，**不再用四元组**）；
- 现状：points=[pos,…] 两点/多点有断言；**region 的对角两点在 read 过滤与 screenshot 仍失败（P-082）**，实现只收四元组，与该条‘不再用四元组’冲突
- 待补：P-082 修复后补两点正例（read 过滤 + screenshot）并复跑

## layout#179（上层/4-layout.md）

- 条款：3. `dbCreateXxx` 失败分两类：**非法 LPP → 抛 SKILL 硬错误**；**几何非法 → nil + WARNING** →
- 现状：非法 LPP 硬错误有真机用例；**几何非法 → nil+WARNING 的分支**靠探针间接覆盖，无分类断言
- 待补：补：几何非法（如零面积 rect）→ 业务失败且错误文本含 WARNING 语义

## verilog#060（上层/8-verilog.md）

- 条款：（ihdl 会往里追加 `DEFINE`，不能给共享/全局那份）；
- 现状：实现在 run_dir 生成 cds.lib 副本（不给共享份）；真机导入成功隐含该路径，但**无断言共享 cds.lib 未被追加 DEFINE**
- 待补：真机补：import 前后对比共享 cds.lib sha256 不变 + run_dir 副本存在

## verilog#065（上层/8-verilog.md）

- 条款：3. 执行（**必须带 LD_LIBRARY_PATH 前缀**，否则缺 `libsasl2.so.2`、rc=127）：
- 现状：真机 import 成功即证明前缀生效（否则 libsasl2 缺失 rc=127）；**无直接断言命令前缀**
- 待补：可选加固：离线断言生成命令以 LD_LIBRARY_PATH=… 开头

## verilog#101（上层/8-verilog.md）

- 条款：3. `ihdl` **返回码不可信**：语法错误、参考库缺失、降级导入都是 rc=0；成功看 `357/372/345`，
- 现状：‘rc 不可信、只看日志+产物’有断言；**成功标记 357/372/345 的识别分支**无用例
- 待补：补离线：三种成功标记日志 → 判成功；缺失标记 → incomplete_log

## verilog#103（上层/8-verilog.md）

- 条款：4. `ihdl` 会向 `-cdslib` 指定的文件**追加 DEFINE**（目标库未注册时还在 cwd 建同名库目录）→ 必须用按次副本；
- 现状：按次副本在建命令里有体现；**ihdl 向 -cdslib 追加 DEFINE 的防污染效果**（共享文件保持不变）无断言
- 待补：真机补：import 后共享 cds.lib 未被追加（sha 对比）+ 无 cwd 同名库目录残留

## calibre#069（上层/12-calibre.md）

- 条款：终态或超时即返回；超时返回 `status=timeout` 且**后台作业继续跑**。
- 现状：终态判定有断言；**超时 → status=timeout 且后台作业继续跑**无直接用例
- 待补：补离线：blocking 超时返回 status=timeout，launcher/作业进程未被杀

## calibre#120（上层/12-calibre.md）

- 条款：（先默认名，再 `job.json.report_file`，最后在 run dir 内扫描 `*.report/*.rep`），与 set 是否改名无关。
- 现状：报告解析与 lvsReportFile 键有断言；**定位三级回退（默认名→job.json.report_file→扫描 *.rep）**无分支用例
- 待补：补：三种报告定位回退各一条（含 set 改名后仍能定位）

## calibre#123（上层/12-calibre.md）

- 条款：> 边界：set 只携带**参数**，不携带数据——它引用的 layout / 源网表 / hcell 文件必须已存在于远端；
- 现状：set 走官方入口有断言；**‘set 只带参数、引用数据必须已存在’的失败边界**无专门用例
- 待补：补：set 引用不存在的 deck/layout → 明确失败（不静默回退）

