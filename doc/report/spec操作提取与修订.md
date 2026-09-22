# spec 操作提取与修订底稿

> 日期：2026-09-17
> 目的：把各 Normative 文档里的"操作"集中提取成一张总表，标注哪些是固定的、哪些是待定的，供共同修订。
> 状态：工作底稿，非 Normative。取代 `doc/report/上层业务包开发清单.md`（那份按旧代码原语罗列，待本稿修订后重写）。

## 1. 操作在哪些层

| 层 | 操作 | 性质 |
|---|---|---|
| 中层 | 5 个业务接口 + 1 个只读查询 | **固定**，唯一底座，不增不减 |
| 顶层 | 接收 `operation` → 选包 → 调方法 → 响应壳 | **固定**，调度机制 |
| 控制面 | 六步注册 | **固定**，不属于业务操作 |
| 上层 | 业务包内的业务操作 | **待定**，本文重点修订 |

## 2. 中层固定操作（提取）

| 操作 | 签名 | 目标 role | 返回 |
|---|---|---|---|
| Skill 执行 | `execute_skill(skill_code, timeout=None, *, token)` | daemon（串行） | VirtuosoResult |
| 命令执行 | `run_command(cmd, timeout=None, *, token, parallel=False)` | command | CommandResult |
| 文件上传 | `upload_file(local, remote, timeout=None, *, token, recursive=False)` | file | CommandResult |
| 文件下载 | `download_file(remote, local, timeout=None, *, token, recursive=False)` | file | CommandResult |
| GUI 命令 | `run_gui_command(cmd, timeout=None, *, token)` | gui（一次性） | CommandResult |
| Spectre 命令 | `run_spectre_command(cmd, timeout=None, *, token)` | spectre（一次性） | CommandResult |
| 只读查询 | `query(token)` | 注册表内存快照 | root/bin，不计入业务接口 |

来源：四层架构 §4.1/§4.2，路由 §3。

## 3. 顶层固定调度

一次 HTTP 请求 = `{operation, token, 业务参数}`，按显式注册表 `{operation: (包类, 方法名, Request)}` 找到业务包与方法，构造 Request、调用方法、结果装进 `{ok, data, error}`。

- 结构校验（类型/必填/范围）失败 → 4xx；
- 业务失败 → 2xx + `ok=false`；
- 未预期异常 → 5xx。

来源：顶层 §2/§3。

## 4. 控制面固定操作（不是业务操作）

①申请 → ②本地校验 → ③探测 → ④部署 → ⑤连通性 → ⑥写注册表。

来源：多用户与注册 §3。

## 5. 上层业务操作（待共同修订）

spec 目前**不枚举**上层具体操作，只规定操作形态（`method(request) -> Result`）。以下从旧代码提取，按"是否有意义"分为三档，请逐项修订。

### 5.1 建议保留（有明确业务语义，调用方会直接使用）

| 业务操作 | 理由 |
|---|---|
| schematic.read / symbol.read / layout.read | 结构化读回，是其它操作与检查的前提 |
| schematic.create / layout.create（含批量编辑命令） | 一个请求创建一个完整 cellview |
| schematic.export_netlist / import_netlist | 文件往返 + Skill，典型编排 |
| symbol.generate | 从原理图自动生成 symbol |
| library.list / get / create / delete / rename | 库管理基础 |
| maestro.open / ensure_view / snapshot / run / read_results / export_waveform | 仿真生命周期粗粒度动作 |
| spectre.run / run_batch / parse_psf / measure | 独立仿真与结果解析 |
| digital_import.import_gds / import_verilog | 外部工具编排 |
| desktop_gui.list_windows / dismiss_dialog / screenshot | GUI 一次性命令的封装 |
| skill_tooling.find_skill / doc_search | 工具查询 |

### 5.2 存疑（是否单列成操作，还是并入批量编辑命令）

| 业务操作 | 疑问 |
|---|---|
| add_wire / add_label / add_pin / add_instance 等各原语 | 单独成 HTTP 操作太碎；是否只作为 create/modify 的批内命令，不单独暴露 |
| layout.add_rect / add_path / create_via 等各原语 | 同上 |
| set_instance_params / get_instance_params | 是否并入 read/write |
| rename_instance / delete_instance / delete_cell | 是否并入通用编辑批 |
| maestro.set_var / set_parameter / set_env_option 等各配置项 | 十几项全暴露太多；是否合并成 configure(alist) |
| library.open / save / close | 是否值得单独暴露，还是编辑批的一部分 |
| spectre.build_command / stage / parameterize | 纯内部步骤，是否暴露 |

### 5.3 建议丢弃或暂缓

| 业务操作 | 理由 |
|---|---|
| spectre.evas_flow | 旧实现不兼容五接口，另议 |
| visio_export | Windows COM 直跑，缺适配层；先定方案再排期 |
| digital_import.import_pipeline | 编排脚本，先等子操作定稿 |
| spectre.run_pool / 增量池 | 并发形态未定，先只做 run_batch |
| desktop_gui.bootstrap | 一次性安装动作，按需再议 |
| library.diagnose_locks | 运维脚本，非业务 |

## 6. 明确不存在的操作（不可新增）

| 不做 | 口径 |
|---|---|
| Spectre 高层封装、仿真编排 | 中层只给一次性命令；编排属上层（可做，但中层不提供） |
| GUI 图形化封装 | 只给 GUI 一次性命令 |
| 异步 command handle / request_id | 长任务由上层 marker/轮询 |
| 文件沙箱 | root 只是目录约定 |
| 跨机启动 daemon | 本版不做 |

来源：本版范围与明确不支持 §2。

## 7. 待修订问题

1. 业务操作的最小粒度：按"业务用例"还是按"SKILL 原语"？倾向前者，§5.2 并入批。
2. 一个业务包内"批"怎么表达：`create(request.commands=[...])`，还是每个原语仍是方法、由调用方多次调用？
3. 配置类操作（Maestro set_var 等）合并成 `configure(options)` 是否够用？
4. 长任务（仿真/导入）的操作对：`start` + `query` 两个操作，还是单同步操作 + 调用方给 job 参数？
5. §5.1/5.2/5.3 逐项确认保留、合并、丢弃。