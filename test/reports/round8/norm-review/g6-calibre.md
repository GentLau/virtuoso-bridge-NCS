# NORM 评审 · g6-calibre（43 条）

> verdict: direct / indirect / partial / gap / na；evidence 为已确认断言的 TB 文件。

| 编号 | 条款（截断） | verdict | 证据 | 说明 |
|---|---|---|---|---|
| skillref#034 | 取值顺序（先到先用，结果原样回带 `source` 与 `doc_root`，便于调用方复用与排错）： | **direct** | test/offline/unit/test_skillref_package.py | source+doc_root 取值顺序（请求→config）与结果回带 source/doc_root 有断言 |
| skillref#051 | **只有这三个字段**——`source` + `doc_root` 是数据源位置，`doc_token` 是远端执行代理账号（必须注册一个 user，用该 user 的远端执行）。 | **direct** | test/offline/unit/test_skillref_package.py (partial-request / remote-without-doc_token) | 只有 source/doc_root/doc_token 三字段；remote 必须 doc_token（注册 user 代理）有断言 |
| skillref#055 | （错误文案带该路径），不退回远端、也不猜别的路径。 | **partial** | test/offline/unit/test_skillref_package.py::test_missing_source_is_business_failure | 缺 source/doc_root 是业务失败有断言；**doc_root 指向不存在路径 → 错误文案带该路径且不退回远端**无专门用例 ｜ 缺口: 补离线：doc_root 不存在 → 业务失败 error 含该路径（断言未发生远端调用） |
| skillref#062 | 路径纪律：远端路径一律按 POSIX 语义拼接，**禁止**对远端路径调用 `Path.exists()`。 | **partial** | test/offline/unit/test_skillref_package.py | 远端路径 POSIX 拼接在实现中；**‘禁止对远端路径调用 Path.exists()’**无静态/行为断言 ｜ 缺口: 补静态断言：remote 分支源码不含远端路径的 Path.exists()/is_dir() 调用（或行为级：Windows 客户端 remote 搜索成功） |
| skillref#064 | 业务失败必须指明"`skillref.doc_token` 无效或已删除"，不得只报 `command failed`。 | **direct** | test/offline/unit/test_skillref_package.py::test_invalid_doc_token_message | doc_token 无效/已删除 → 明确业务失败文案（非泛化 command failed），有断言 |
| skillref#069 | 唯一搜索入口。一次请求 = 一个 `query` + 一组选项，选项只影响"搜到哪一层"与"怎么匹配"。 | **direct** | test/offline/unit/test_skillref_package.py<br>test/semi/probes/skillref_probe.py | search 唯一入口 + 选项矩阵：包用例 + 真机远端探针 |
| skillref#102 | `name` 与 `entry` 的区别只在**是否把语法/描述并入匹配面**，两者共用同一份 `.fnd` 解析。 | **direct** | test/offline/unit/test_skillref_docs_contracts.py<br>test/offline/unit/test_skillref_package.py | name/entry 的匹配面差异（是否并入语法/描述）由解析/打分用例覆盖 |
| skillref#103 | `all` = `body`（最深一档，给"我什么都想搜"的用户一个不用记顺序的取值）。 | **partial** | test/offline/unit/test_skillref_package.py | name/entry/topic/body 四档有断言；**`all` = body 的映射**无用例 ｜ 缺口: 补一条：search_in="all" 行为与 body 等同（或按实现映射断言） |
| skillref#107 | （语法、描述、正文）一律按**大小写不敏感的子串 AND** 匹配，不受 `mode` 影响： | **direct** | test/offline/unit/test_skillref_docs_contracts.py | 大小写不敏感子串 AND 匹配/排序不受 mode 影响：模式矩阵与排序用例 |
| skillref#129 | 未命中返回空 `results` 且 `ok=true`（"查不到"是正常业务结果，不是错误）。 | **direct** | test/offline/unit/test_skillref_package.py (limit/无命中用例) | 未命中 → 空 results 且 ok=true（正常业务结果），有断言 |
| skillref#136 | 因此 `search_in="body"` 在 **local 模式必须给 `under`**（如 `["cpf_ref"]`， | **direct** | test/offline/unit/test_skillref_package.py::test_body_layer_truncates_without_under | body+local 必须给 under（否则截断/拒绝），有断言 |
| skillref#140 | 在本地打分与出摘要；`max_candidates` 同时是下载上限； | **partial** | test/offline/unit/test_skillref_package.py (max_files 用例) | max_files 有断言；**max_candidates 同时作为下载上限**无参数级用例（op×param 矩阵同标 GAP） ｜ 缺口: 补：max_candidates=N → 远端下载调用次数 ≤N（离线 mock 计数） |
| skillref#141 | 4. `timeout` 显式传给每次 C/D 调用；正文层远端候选搜索默认给 120 s，调用方可覆盖。 | **partial** | test/offline/unit/test_skillref_package.py | timeout 透传在 mock 中可见；**正文层远端候选默认 120s**的具体默认值无断言 ｜ 缺口: 补：body 层远端候选搜索默认 timeout=120、可被请求覆盖 |
| skillref#153 | 3. 抽取顺序（不可调换，旧实现 `skill_finder/more_info.py:157`）： | **direct** | test/offline/unit/test_skillref_package.py (info 抽取顺序) | info 抽取顺序（不可调换）由包用例钉住 |
| skillref#166 | * 本段缺失或 `null` = 未配置，不阻断进程启动，只在调用时返回可读的业务失败。 | **direct** | test/offline/unit/test_skillref_package.py (config 缺失/null 用例) | 配置缺失/null = 未配置，不阻断启动、调用时业务失败，有断言 |
| skillref#167 | 实现口径（本包）：读取顺序 = 请求参数 `source`+`doc_root` → `common.config` 快照的 | **direct** | test/offline/unit/test_skillref_package.py::test_source_from_config_snapshot | 读取顺序（请求参数 → config 快照）有断言 |
| skillref#173 | 一个入口，`search_in` 是唯一控制匹配深度的参数。旧 `skill-find` CLI 的语义对应 | **direct** | test/offline/unit/test_skillref_package.py<br>test/semi/probes/skillref_probe.py | 单一搜索入口、search_in 为唯一深度参数：包用例 + 真机探针 |
| skillref#180 | 两者共享同一套解析口径（`.fnd` / `.tgf` / HTML→Markdown），实现以本包为唯一维护点。 | **direct** | test/semi/probes/skill_tooling_probe.py<br>test/offline/unit/test_skillref_docs_contracts.py | 与 tools/skill_find 共享解析口径（.fnd/.tgf/HTML→MD）：工具探针 + 解析契约 |
| skillref#194 | → 文档升级后索引静默过期。若将来要建，必须补"文档树指纹"（文件数 + 最新 mtime）， | **na** | — | 决策记录（本版为何不建索引），无独立可测行为 |
| skillref#206 | 2. 正文层无持久索引：本地模式全树扫描 ~190 s（必须给 `under`）；远端模式靠 `grep` 候选 | **na** | — | 已知限制（性能数字 ~190s），按限制登记 |
| skillref#211 | 6. 正文层远端的 `line` 只在本地算（候选下载后重扫），远端候选本身只保证文件级定位。 | **na** | — | 已知限制（远端 line 只在本地算），按限制登记 |
| skillref#212 | 7. **不做路径探测**：`source` 与 `doc_root` 必须由配置表或请求给出；配错只会得到 | **direct** | test/offline/unit/test_skillref_package.py | 不做路径探测：source/doc_root 必须显式给出（缺失即业务失败）有断言 |
| calibre#005 | > **`calibre.pex` 未按官方三阶段验收，禁止用于交付/签核**；DRC/LVS/`export_cdl`/set 直驱已真机验证。 | **indirect** | test/offline/unit/test_calibre_argv_contracts.py<br>test/live/packages/calibre_e2e_tests.py | 状态声明（pex 未按官方三阶段验收、禁止交付）+ 其余项已真机验证；pex 两阶段 argv 有契约断言、真机三阶段闭环仍未见证据（按声明口径登记为限制） |
| calibre#011 | 2. **默认非阻塞 + 三件套**：run 类操作默认立即返回 `job_id`（Calibre 动辄几十分钟），用 `calibre.status` 看进度、`calibre.read_results` 拿结构化结论 | **direct** | test/offline/unit/test_calibre_package.py::test_drc_start_nonblocking<br>test/offline/unit/test_calibre_package.py::test_drc_blocking_completes | 默认非阻塞 + job_id/status/read_results 三件套与 blocking=true 轮询，均有断言 |
| calibre#014 | 5. **失败可定位**：错误带 `kind`、工具原文片段、run dir 路径；`unknown-effect` 一律不自动重试。 | **direct** | test/offline/unit/test_calibre_package.py (failure_kind 用例)<br>test/offline/unit/test_calibre_job_state.py | 失败带 kind/原文片段/run dir；unknown-effect 不自动重试，有断言 |
| calibre#031 | `job_id` 默认 `<kind>_<top>`（如 `drc_inv2`），请求可显式指定； | **direct** | test/offline/unit/test_calibre_package.py::test_lvs_runset_goes_through_official_batch_entry | job_id 默认 <kind>_<top>（可显式指定）有断言 |
| calibre#054 | 取值顺序：**请求显式 `calibre_bin`** > `query().roles["command"].calibre.bin`； | **direct** | test/offline/unit/test_calibre_package.py<br>test/semi/probes/calibre_env_probe.py | calibre_bin 取值顺序（请求显式 > query roles[command].calibre.bin）有断言 + 环境探针 |
| calibre#057 | - 包内启动器固定先 `ulimit -n 65536`（Calibre 对 fd 上限敏感，实测默认 1024 会告警）； | **direct** | test/offline/unit/test_calibre_package.py::test_launcher_backgrounds_and_marks_stages | launcher 固定先 ulimit -n 65536，有断言 |
| calibre#059 | 许可问题由工具日志暴露，`read_results`/`status` 负责把 `license` 相关错误单独归类为 `license`（可重试）。 | **direct** | test/offline/unit/test_calibre_package.py::test_job_state_failed_license | license 相关错误单独归类为 license（可重试）有断言（含误报反例） |
| calibre#060 | run 类操作默认 `blocking=false`：写 launcher、后台启动、立刻返回 `job_id`。 | **direct** | test/offline/unit/test_calibre_package.py::test_drc_start_nonblocking | blocking=false 默认：launcher+后台启动+立即 job_id 有断言 |
| calibre#068 | `blocking=true` 时包内循环：`deadline = now + timeout`，按 `poll_interval`（默认 5 s）调 `status`， | **direct** | test/offline/unit/test_calibre_package.py::test_drc_blocking_completes | blocking=true 循环（poll_interval/deadline）有断言 |
| calibre#069 | 终态或超时即返回；超时返回 `status=timeout` 且**后台作业继续跑**。 | **partial** | test/offline/unit/test_calibre_job_state.py | 终态判定有断言；**超时 → status=timeout 且后台作业继续跑**无直接用例 ｜ 缺口: 补离线：blocking 超时返回 status=timeout，launcher/作业进程未被杀 |
| calibre#096 | **参数一律用官方机制带**（两条路，互斥）： | **direct** | test/offline/unit/test_calibre_package.py (runset/官方批处理用例 431-499) | drc/lvs 参数走官方机制两条互斥路（control file / -gui -lvs -runset -batch）有断言 |
| calibre#120 | （先默认名，再 `job.json.report_file`，最后在 run dir 内扫描 `*.report/*.rep`），与 set 是否改名无关。 | **partial** | test/offline/unit/test_calibre_package.py (lvsReportFile 解析)<br>test/offline/unit/test_calibre_parsers.py | 报告解析与 lvsReportFile 键有断言；**定位三级回退（默认名→job.json.report_file→扫描 *.rep）**无分支用例 ｜ 缺口: 补：三种报告定位回退各一条（含 set 改名后仍能定位） |
| calibre#123 | > 边界：set 只携带**参数**，不携带数据——它引用的 layout / 源网表 / hcell 文件必须已存在于远端； | **partial** | test/offline/unit/test_calibre_package.py (set/runset 用例) | set 走官方入口有断言；**‘set 只带参数、引用数据必须已存在’的失败边界**无专门用例 ｜ 缺口: 补：set 引用不存在的 deck/layout → 明确失败（不静默回退） |
| calibre#127 | 包会把它复制进 PEX 的 run dir）；`fmt` 可选 `none`/`spice`/`simple`（默认 `none`，即只到 `-pdb`）。 | **direct** | test/offline/unit/test_calibre_argv_contracts.py (fmt 枚举与拒绝 56-93) | pex fmt=none/spice/simple 与非法值拒绝、deck 复制进 run dir，有断言 |
| calibre#128 | 内部固定顺序：`-xrc -phdb` → `-xrc -pdb -rc <deck>` →（可选）`-xrc -fmt -<fmt>`， | **direct** | test/offline/unit/test_calibre_argv_contracts.py::test_pex_runs_two_stages<br>test/offline/unit/test_calibre_argv_contracts.py::test_pex_adds_a_format_stage_only_for_spice_like_formats | pex 固定阶段顺序（phdb→pdb→fmt）逐条断言（P-034 修复后） |
| calibre#129 | **每个阶段校验产物存在**才进入下一阶段（phdb 必须是 xRC 类型，见可行性报告 §2）。 | **direct** | test/offline/unit/test_calibre_package.py::test_launcher_backgrounds_and_marks_stages<br>test/offline/unit/test_calibre_package.py::test_read_results_pex_stage_failure_is_reported | 每阶段产物/stage 标记校验、阶段失败上报，有断言 |
| calibre#151 | **`checkCAPPERI=nil`**——IC618 auCdl batch 的默认值缺口，缺失即 `OSSHNL-411`）与一致的 `.simrc`； | **direct** | test/offline/unit/test_calibre_package.py (auCdl 三件套 + checkCAPPERI 用例 509-531) | si.env 带 auCdl 三件套 + checkCAPPERI=nil + 一致 .simrc，有断言 |
| calibre#160 | 5. 不做并发调度：同一 token 建议串行跑 PDR；许可争用表现为工具报错，由调用方决定重试。 | **na** | — | 「不做」：并发调度（同 token 建议串行） |
| calibre#171 | 2. 大设计的 `svdb`/`*.pdb` 可能很大：`export` 默认只取小文件，目录需显式点名； | **na** | — | 已知限制：export 默认只取小文件、目录需点名 |
| calibre#172 | 3. `power`/`ground` 未给时沿用 deck 默认（可能触发 ERC 告警，见可行性报告 §2 的 LVS 实测）； | **indirect** | test/semi/probes/calibre_package_http_probe.py<br>test/live/flows/s11_full_flow.py | power/ground 未给沿 deck 默认（可能 ERC 告警）：由 LVS 真机探针结果间接体现，无参数级断言 |
| calibre#173 | 4. 许可不足、并发争用未做全局串行（§5.5）。 | **na** | — | 已知限制：许可不足/并发争用未做全局串行 |
