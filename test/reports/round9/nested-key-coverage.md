# round9 · 嵌套键覆盖审计（顶层矩阵的盲区）

> 执行：subagent `/root/opparam_r9`（B 线延伸）｜2026-09-29
> 方法：`test/reports/round9/nested_key_audit.py`（AST，只读）
> 机器结论：`nested-key-audit.json` / `nested-key-audit.md`

## 0. 为什么单独立这一份

op×参数矩阵（`op-param-r9.md`）只看得到 Request **顶层字段**；
`commands: list[dict]`（8 个写操作）、`tasks`/`metrics`（spectre）这类**嵌套映射**才是大量用户可传输入的真正入口。
上一轮"每个可传参数都要覆盖"的口径若只按顶层算，会漏掉这整层——本文件把它补上。

**方法**：从实现里抽 dispatch 分支的 op 字面量 + 常量集合（如 `_PLACE_ATOMS`、`_SHAPE_KINDS`）与每个分支读到的
`command.get("f")` 字段（含 handler→op 归属、守卫上下文继承）；TB 端用 **AST 字符串字面量/关键字名精确匹配**
（不是子串），并对每个结论用独立 grep 复核。

## 1. 数字

- 目标包 7（layout / schematic / symbol / verilog / veriloga / maestro / spectre）、**命令 op 90 个**、
  **(op, 字段) 检查项 365 条**（去重键名 105 个）
- **从未被任何 TB 触碰的嵌套键：28 条 (op,字段) / 去重后 20 个键名**（其中 19 个键在整个 `test/`（除报告/产物）里连一次字面量都没有）
- 二级枚举值 23 个（`*_KINDS`/`*_TYPES`/`*_MODES`/`*_ATOMS`），**未覆盖 5 个**（全在 spectre `_MODES`）
- helper 级键（`bbox`/`points`/`purpose`/`old_text`/`expected_sha256`/`edits`/`include_files`/`spectre_args`/`tasks`/`metrics`/`pos`）逐条查过：**均有 TB 触碰**，不计缺口

| 包 | 命令 op | (op,字段) | 未覆盖 | 说明 |
|---|---|---|---|---|
| layout | 22 | 97 | **0** | 覆盖最完整 |
| schematic | 15 | 51 | 2 | `place_wire` 的 `x_spacing`/`y_spacing` |
| symbol | 16 | 82 | 14 | pin 标签族 7 键（含 `label_type`） |
| verilog | 4 | 9 | 0 | `set_source`/`patch_source`/`ensure_view`/`delete_view` |
| veriloga | 4 | 9 | 0 | 同上 |
| maestro | 28 | 112 | 12 | test/corner 门控、模型绑定、变量类型族 |
| spectre | 1（`tasks[]` 记录） | 5 | 0 | `job`/`netlist`/`include_files`/`mode`/`spectre_args` 全有 TB 触碰 |

## 2. 未覆盖的 20 个嵌套键（逐条）

| 包 | 命令 op | 键 | spec 是否记载 | 说明 |
|---|---|---|---|---|
| symbol | `set_label_properties` | `label_type` | — | 写 `vbLabel~>labelType`（`symbol.py:672-673`），也出现在 `place_label` 的语义标签路径（`:734-739`） |
| symbol | `place_label` | `label_type` | — | 同上 |
| symbol | `place_pin` / `set_pin_properties` | `half_size` | ✅ `3-symbol.md` | pin 标签尺寸 |
| symbol | `place_pin` / `set_pin_properties` | `label_font` | ✅ `3-symbol.md` | pin 标签字体 |
| symbol | 同上 | `label_height` | （随 label_font 一族） | pin 标签字高 |
| symbol | 同上 | `label_justify` | 同上 | pin 标签对齐 |
| symbol | 同上 | `label_orient` | 同上 | pin 标签朝向 |
| symbol | 同上 | `label_pos` | 同上 | pin 标签位置 |
| schematic | `place_wire` | `x_spacing` | ❌ spec 未写 | 直接进 `schCreateWire(...)`（`schematic.py:604`） |
| schematic | `place_wire` | `y_spacing` | ❌ spec 未写 | 同上 |
| maestro | `set_corner` / `set_test` / `delete*` / `lock` … | `enabled` | ✅ `6-maestro.md` | 逐 test/corner 启停 |
| maestro | 同上 | `disable_tests` | ✅ `6-maestro.md` | 批量禁用 |
| maestro | 同上 | `enable_tests` | ✅ `6-maestro.md` | 批量启用 |
| maestro | `setup_corner` | `model_file` | — | corner 模型文件绑定 |
| maestro | `setup_corner` | `model_section` | ✅ `6-maestro.md` | corner 模型 section |
| maestro | `load_corners` | `sections` | — | runset/corner 文件 section 选择 |
| maestro | `set_job_policy` | `job_type` | ✅ `6-maestro.md` | 作业类型 |
| maestro | `set_var` / `set_parameter` | `type_name` | ❌ spec 未写 | 变量类型名 |
| maestro | `set_var` | `type_value` | ❌ spec 未写 | 变量类型取值 |
| maestro | 多条（`set_test`/`set_corner`/`set_spec`…） | `test_name` / `spec_name` | ❌ spec 未写 | 目标 test/spec 名 |

> 复核方式：对每个键在 `test/`（排除 `reports/`、`artifacts/`、`plans/`、`docs/`）做 `\b<key>\b` 全量 grep，
> 19 条 0 命中；`sections` 的 2 处命中在 `test_registration_server.py` / `test_spectre_util_psf_contracts.py`，
> 与 `maestro.load_corners` 无关 → 仍算未覆盖。

## 3. 未覆盖的二级枚举值（5）

`spectre.py::_MODES` 的 **`ax` / `cx` / `lx` / `mx` / `vx`** 从未被任何 TB 用过（TBs 只用了 `_MODES` 里的其余取值）。
→ 建议：`spectre.run` 的模式矩阵至少离线补一轮（真机按成本选测），或在 spec 里写明这 5 个模式本版不支持。

## 4. 建议的 TB 补点（按优先级）

| 优先级 | 补点 | 落点建议 |
|---|---|---|
| P1 | symbol pin 标签族：`half_size`/`label_font`/`label_height`/`label_justify`/`label_orient`/`label_pos`（6 键）+ `label_type`（1 键） | `test/live/packages/symbol_e2e_tests.py` 的 WRITE 档加 2 条命令（`place_pin`、`set_pin_properties`），写后 `read` 回读断言字段生效（symbol 的 `read` 本来就返回 `labels[].label_type` 等） |
| P1 | maestro test/corner 门控族：`enabled`/`disable_tests`/`enable_tests`（3 键，spec ✅） | `test/live/packages/maestro_e2e_tests.py` 或 `maestro_bugfix_batch` 家族：写后 `read_config` 回读断言 |
| P2 | maestro 模型绑定/类型族：`model_file`/`model_section`/`sections`/`job_type`/`type_name`/`type_value`/`test_name`/`spec_name`（8 键） | 同上；先让设计确认 `type_name`/`type_value`/`test_name`/`spec_name` 是否对外（spec 未写） |
| P2 | schematic `place_wire` 的 `x_spacing`/`y_spacing`（2 键） | `schematic_e2e_tests.py` WRITE 档；spec 未记载 → 同步要求 design 补 spec 或删键 |
| P3 | spectre `_MODES` 的 5 个未覆盖取值 | 离线合同优先（`test/offline/unit/test_spectre_contracts.py`），真机按成本选测 |

## 5. 未做 op 归属的 helper（如实列出，均已抽查为"有 TB 触碰"）

`layout._pos_of`/`_shape_match_expr`/`_label_match_expr`、`symbol._shape_match_expr`/`_label_match_expr`/`_label_text`/`_label_xy`、
`schematic._pos_of`、`verilog/_veriloga._set_source`/`_patch_source`、`spectre._run_one`（详见 JSON `helpers_without_op_mapping`）。
这些 helper 按二级键（`kind`/`label_kind`）分支，脚本不做 op 归属；其字段经独立 grep 复核均被 TB 覆盖。

## 6. 口径与残留

- **字面量出现 ≠ 断言语义**：本审计只能证明"该键被某条 TB 写过"，不证明写后断言了效果；断言强度见 `brief-weak-assert.md` 一线。
- 90 个命令 op 里，`layout`（22 op / 0 缺口）、`verilog`、`veriloga`、`spectre` 字段覆盖完整；
  缺口集中在 **symbol pin 标签族（14 条 / 7 键）**、**maestro 写命令族（12 条 / 11 键）**、**schematic `place_wire`（2 条 / 2 键）**。
- 建议下一轮把本脚本并入常规矩阵刷新（脚本已在 round9，保持只读、不改 `src/`），避免这类嵌套键再次成为盲区。

## 7. 补点状态（round9 已落，含口径声明）

新增 `test/offline/unit/test_nested_command_keys_contract.py`（作者：测试/root，21 个用例，**现跑 21/21 绿**），
把上述 20 个键 + 5 个 spectre 模式取值逐条钉住（每条给出"期望 / 实际 / 判定"，含负例：
遗留 `label_x` 拒绝、无写字段拒绝、未知 mode 拒绝、`type_name` 非 test/corner 不发射 `?typeName`）。

补点后重跑本审计：**未被触碰字段 0、未覆盖枚举值 0**。

> ⚠ **口径**（`test/docs/写TB规范.md`）：这是 **L0 离线契约**，只证明"键→SKILL 拼装"正确，
> **不得**算作这些操作/参数已在真机覆盖。真机判据仍需按 §4 的落点补 live 用例
> （symbol pin 标签族、maestro 门控族、schematic `place_wire` 间距）——本报告不声称已完成真机覆盖。

## 8. 真机补点结果（round9 22:50 更新，口径闭合）

root 随后补了真机 TB **`test/live/packages/nested_keys_e2e_tests.py`**，我已把它接进 `run_all_http.py` 门禁并单跑验证：

| 用例 | 内容 | 结果 |
|---|---|---|
| NK-ENV | 环境检查（1+2） | PASS |
| NK-01 | `place_pin` 的 6 个标签键（bbox + label **值级读回**） | **PASS** |
| NK-02 | `set_pin_properties` 的 4 个标签键（值级读回） | **PASS** |
| NK-03 | `place_label(label_type=NLPLabel)` 值级读回 | **PASS** |
| NK-04 | `place_wire` 的 `x_spacing`/`y_spacing` | **PASS（如实记录）**：DB 直读 `("path" (nil) (nil) (0.05))` —— width 落库、两个 spacing 读回 nil → **静默无效参数 = C10**（已立卡，待设计"实现可观察语义 + 补 spec"或"删字段"） |

证据：`test/artifacts/evidence/round9/nested-keys-r9.json`（rc=0，5/5）。

→ 因此本主题的状态是：**L0 契约 21/21 + 真机 5/5；发现并卡住 1 个真实产品问题（C10）**。

## 8. round9 真机补测（symbol / schematic 9 键，**已落**）

> 执行：测试/root（主）｜2026-09-29 22:45｜TB：`test/live/packages/nested_keys_e2e_tests.py`（作者 测试/root）
> 证据：`test/artifacts/evidence/round9/nested-keys-symbol-schematic.json`（**5/5 PASS**）

| 键 | op | 判据（值级读回：`dbOpenCellViewByType ... "r"` 后读属性/bbox） | 结果 |
|---|---|---|---|
| `half_size` | `place_pin` | bbox = pos ± half（0.1 → `(-0.1 -0.1 0.1 0.1)`） | ✅ |
| `label_pos` | `place_pin` | label `~>xy` = `(0.5 0.5)` | ✅ |
| `label_justify` | `place_pin` | label `~>justify` = `"lowerLeft"` | ✅ |
| `label_orient` | `place_pin` | label `~>orient` = `"R90"` | ✅ |
| `label_font` | `place_pin` | label `~>font` = `"fixed"` | ✅ |
| `label_height` | `place_pin` | label `~>height` = `0.2` | ✅ |
| `label_justify/orient/font/height` | `set_pin_properties` | 改后读回 `"upperRight" "R180" "fixed" 0.3` | ✅ |
| `label_type` | `place_label(kind=drawing)` | label `~>labelType` = `"NLPLabel"` | ✅ |
| `x_spacing` / `y_spacing` | `place_wire` | **DB 无可读回属性**：`("path" (nil) (nil) (0.05))`（width 落库、spacing 读回 nil） | ⚠ **惰性参数 → 立卡 C10** |

**真机仍未逐键验证的（12 键，全部属 maestro）**：`enabled`/`disable_tests`/`enable_tests`/
`model_file`/`model_section`/`sections`/`job_type`/`type_name`/`type_value`/`test_name`/`spec_name`
（~~已派 B 线~~ → **由 root 接手，见 §9：已落**）。

## 9. round9 真机补测（maestro 11 键，**已落**）

> 执行：测试/root｜2026-09-30 00:05｜TB：`test/live/packages/maestro_nested_keys_e2e_tests.py`
> 证据：`test/artifacts/evidence/round9/maestro-nested-keys-r9.json`（**9/9 PASS**，rc=0）
> 口径：**能在公开 read 面读到的一律值级断言；读不到的如实标 `readback: none`，不冒充值级**。

| 键 | op | 判据 | 结果 |
|---|---|---|---|
| `enabled` / `enable_tests` / `disable_tests` | `set_corner` | 三档写入被接受 + `read_config.corners` 出现 `nkm_c_off`/`nkm_c_gate_on`/`nkm_c_gate_off`；**enable 状态本身无公开读回字段**（schema：test 条目 = variables/analyses/outputs/env_options/sim_options） | ✅ 接受性 + corner 值级（readback: none） |
| `model_file` / `model_section` | `setup_corner` | corner `nkm_c_model` 建立且 **corner 变量 `NKM_CV=0.9` 值级读回**；model 两字段无公开读回 | ✅ 变量值级（model 字段 readback: none） |
| `type_name` / `type_value` | `set_var` | `?typeName "corner" ?typeValue "nkm_c_model"` → **`corners.nkm_c_model.variables.NKM_TYPEVAR == "2.25"`** | ✅ **值级** |
| `spec_name` | `delete_spec` | `set_spec(lt=1)` → `outputs[].spec = {type: lt, value: 1}`；`delete_spec(spec_name="nkm_test.NKM_OUT")` → **`outputs[].spec == null`** | ✅ **值级（先加后删）** |
| `job_type` / `test_name` | `set_job_policy` | 写入被接受、test 不丢失；job policy 不在公开 schema | ✅ 接受性（readback: none） |
| `sections` | `load_corners` | 仓库无合法 ADE corners CSV 样例 → 本轮只做**负路径**：本地文件缺失必须结构化失败（不静默成功） | ⚠ **负路径**；正例待设计给样例（残留） |
| （附加）`set_parameter` 名称契约 | `set_parameter` | 非 `Library/Cell/View/Instance/Property` 五段路径 → **结构化拒绝**且错误文本含该契约 | ✅ 值级（错误语义） |

**新发现（记入报告，未立卡）**：`set_parameter` 的 `name` 是**层次器件参数路径**（五段），
与 `set_var` 的 `type_name`/`type_value`（scope 语义）**不是同一套参数语义**；op×参数矩阵把两者
混在一行会把语义搞错 —— 已在 `op-param-r9.md` 的口径里按本 TB 实测修正。
其**正例**（真实层次参数名）本轮未构造 → 残留：需设计给一个可用的层次参数样例（或说明不对外）。
