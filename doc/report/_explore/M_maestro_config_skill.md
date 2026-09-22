# Maestro 配置写 + GUI 会话 SKILL 参考（旧代码提取）

> 范围：`src_bak/virtuoso_bridge/virtuoso/maestro/writer.py`、
> `src_bak/virtuoso_bridge/virtuoso/maestro/lifecycle.py`，以及
> `virtuoso/ops.py`、`virtuoso/response.py`、`virtuoso/skill_output.py`
> 中与 escape/parse 有关的函数。
>
> 总约定：writer 大多数函数先拼 `mae*` SKILL，再经 `_q()` 调
> `execute_skill()`，返回原始 output。只有 `add_output()` 和
> `run_simulation()` 的 session/callback 等少数值显式调用
> `escape_skill_string()`；其他字符串参数直接插入。

## 0. 公共执行契约

- `_q()`：`r.errors` 非空抛 `RuntimeError`，否则 `return r.output or ""`
  (`writer.py:20-25`)。
- `execute_skill` 未传 timeout 时使用 client 的 `_timeout`，构造默认 30 秒
  (`src_bak/virtuoso_bridge/virtuoso/basic/bridge.py:82,316-319`)。
- writer 的 `session=""` 表示省略 `?session`，使用 Cadence current session；
  例外是 `delete_var()`、`setup_corner()` 的 model-file 分支会查询
  `car(maeGetSessions())`。
- `add_output()`、`run_simulation()` 才做显式字符串转义；其他 writer 配置
  函数的 `"..."` 内值基本原样插入 (`writer.py:76-87,349-355`)。
- `_strip_skill_atom(raw)` 仅是 `.strip().strip('"')`，不是完整解码器
  (`writer.py:420-421`)。

---

## 1. writer.py：执行壳

### `_q(client, expr, timeout=None) -> str`

- **签名/出处**：`(client: VirtuosoClient, expr: str, timeout: float | None = None) -> str` (`writer.py:20`)。
- **SKILL 模板**：没有独立 SKILL，只执行调用方 `expr`。
- **参数注入**：`expr` 必填；`timeout is None` 时不传 `timeout`，否则传数值。
- **执行/超时**：`client.execute_skill(expr, **kwargs)`；默认 client 30 秒。
- **返回解析**：`r.errors` 非空抛 `RuntimeError(r.errors[0])`；否则 `r.output or ""`；`nil` 不会变成 `None`。
- **会话**：自身无 `?session`。
- **失败/边界**：SKILL 报错即抛 Python 异常；空 output 静默返回空串。

---

## 2. writer.py：配置写函数

### `create_test(client, test, *, lib, cell, view="schematic", simulator="spectre", session="") -> str`

- **签名/出处**：`writer.py:32-34`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client,
      f'maeCreateTest("{test}" ?lib "{lib}" ?cell "{cell}" '
      f'?view "{view}" ?simulator "{simulator}"{s})')
  ```
- **参数注入**：`test`、`lib`、`cell` 必填；`view`、`simulator` 有默认值；`session` 空才省略，全部原样插入。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output；`"nil"` 不抛错。
- **会话**：可选 `?session`，空值代表 current session。
- **失败/边界**：SKILL 错误由 `_q` 抛出；无存在性/重复 test 检查。

### `set_design(client, test, *, lib, cell, view="schematic", session="") -> str`

- **签名/出处**：`writer.py:42-44`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client,
      f'maeSetDesign("{test}" "{lib}" "{cell}" "{view}"{s})')
  ```
- **参数注入**：`test`/`lib`/`cell` 必填；`view="schematic"`；`session` 空则省略；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output，不把 `t`/`nil` 转 bool。
- **会话**：可选 `?session`。
- **失败/边界**：test/DUT 不存在或非法时由 SKILL 报错决定。

### `set_analysis(client, test, analysis, *, enable=True, options="", session="") -> str`

- **签名/出处**：`writer.py:55-56`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  en = "t" if enable else "nil"
  opts = f" ?options `{options}" if options else ""
  return _q(client,
      f'maeSetAnalysis("{test}" "{analysis}" ?enable {en}{opts}{s})')
  ```
- **参数注入**：`test`/`analysis` 必填；`enable` 默认 `True`→`t`、`False`→`nil`；`options` 空则省略；`session` 空则省略。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：`options` 是原始 SKILL alist 文本，例如 `'(("start" "1") ("stop" "10G"))'`；前带反引号，非双引号字符串，也不做 Python 转义。

### `add_output(client, name, test, *, output_type="", signal_name="", expr="", session="") -> str`

- **签名/出处**：`writer.py:72-74`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{escape_skill_string(session)}"' if session else ""
  parts = (f'maeAddOutput("{escape_skill_string(name)}" '
           f'"{escape_skill_string(test)}"')
  if output_type:
      parts += f' ?outputType "{escape_skill_string(output_type)}"'
  if signal_name:
      parts += f' ?signalName "{escape_skill_string(signal_name)}"'
  if expr:
      parts += f' ?expr "{escape_skill_string(expr)}"'
  parts += f'{s})'
  return _q(client, parts)
  ```
- **参数注入**：`name`/`test` 必填；`output_type`/`signal_name`/`expr`/`session` 有值才拼；所有双引号值均转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`，值经 `escape_skill_string()`。
- **失败/边界**：空字段不生成关键字；含 `"`/`\` 的 expr 等安全进入 SKILL 字符串。

### `set_spec(client, name, test, *, lt="", gt="", session="") -> str`

- **签名/出处**：`writer.py:91-92`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  parts = f'maeSetSpec("{name}" "{test}"'
  if lt: parts += f' ?lt "{lt}"'
  if gt: parts += f' ?gt "{gt}"'
  parts += f'{s})'
  return _q(client, parts)
  ```
- **参数注入**：`name`/`test` 必填；`lt`/`gt`/`session` 有值才拼；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：值中的引号/反斜杠会破坏 SKILL 字符串；空值不生成关键字。

### `set_var(client, name, value, *, type_name="", type_value="", session="") -> str`

- **签名/出处**：`writer.py:108-110`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  parts = f'maeSetVar("{name}" "{value}"'
  if type_name: parts += f' ?typeName "{type_name}"'
  if type_value: parts += f" ?typeValue '{type_value}"
  parts += f'{s})'
  return _q(client, parts)
  ```
- **参数注入**：`name`/`value` 必填；`type_name`/`type_value`/`session` 有值才拼；`type_value` 前是单引号。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：通常传 `type_value='("IB_PSS")'`/`'("myCorner")'`；两个 type 字段可独立出现；无转义。

### `get_var(client, name, *, session="") -> str`

- **签名/出处**：`writer.py:133`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client, f'maeGetVar("{name}"{s})')
  ```
- **参数注入**：`name` 必填；`session` 空则省略；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：直接 output；不调 `_strip_skill_atom()`，调用者自行处理引号/`nil`。
- **会话**：可选 `?session`。
- **失败/边界**：变量不存在通常返回 `nil` 字符串；SKILL error 由 `_q` 抛。

### `delete_var(client, name, *, test="", session="") -> str`

- **签名/出处**：`writer.py:139-140`。
- **SKILL 构造**：
  ```python
  sess = session or _q(client, 'car(maeGetSessions())')
  if test:
      expr = (f'axlRemoveElement(axlGetVar('
              f'axlGetTest(axlGetMainSetupDB("{sess}") "{test}") "{name}"))')
  else:
      expr = (f'axlRemoveElement(axlGetVar('
              f'axlGetMainSetupDB("{sess}") "{name}"))')
  return _q(client, expr)
  ```
- **参数注入**：`name` 必填；`test` 空删 global；`session` 空则先 `car(maeGetSessions())`，原始 output 直接进 `"{sess}"`。
- **执行/超时**：两次 `_q`（取 session、删除）；默认 30 秒。
- **返回解析**：最终原始 output；中间 session 不 strip。
- **会话**：显式 session 优先，否则当前 session 列表第一项。
- **失败/边界**：无 session/第一项为 `nil` 会拼出空或 `nil` session；删 global 前需先删各 test 本地副本 (`writer.py:146-147`)，操作可能 partial。

### `get_parameter(client, name, *, type_name="", type_value="", session="") -> str`

- **签名/出处**：`writer.py:163-165`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  parts = f'maeGetParameter("{name}"'
  if type_name: parts += f' ?typeName "{type_name}"'
  if type_value: parts += f' ?typeValue `{type_value}'
  parts += f'{s})'
  return _q(client, parts)
  ```
- **参数注入**：`name` 必填；`type_name`/`type_value`/`session` 有值才拼；`type_value` 前是反引号。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：`type_value` 是 SKILL list 文本；无匹配通常返回 `nil`；无转义。

### `set_parameter(client, name, value, *, type_name="", type_value="", session="") -> str`

- **签名/出处**：`writer.py:177-179`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  parts = f'maeSetParameter("{name}" "{value}"'
  if type_name: parts += f' ?typeName "{type_name}"'
  if type_value: parts += f' ?typeValue `{type_value}'
  parts += f'{s})'
  return _q(client, parts)
  ```
- **参数注入**：`name`/`value` 必填；其余有值才拼；`type_value` 前是反引号；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：global/corner 语义由 type 字段决定，Python 不校验匹配。

### `set_env_option(client, test, options, *, session="") -> str`

- **签名/出处**：`writer.py:200-201`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client,
      f'maeSetEnvOption("{test}" ?options `{options}{s})')
  ```
- **参数注入**：`test`/`options` 均为必填位置参数；`session` 空则省略；`options` 前是反引号。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：`options` 为空仍会留下孤立反引号；应传合法 SKILL alist，例如 `'(("modelFiles" (("/pdk/model.scs" "tt"))))'`。

### `set_sim_option(client, test, options, *, session="") -> str`

- **签名/出处**：`writer.py:212-213`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client,
      f'maeSetSimOption("{test}" ?options `{options}{s})')
  ```
- **参数注入**：`test`/`options` 必填；`session` 有值才拼；`options` 前是反引号。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：空 options 生成不完整表达式；非法 alist 由 `_q` 抛错。

### `set_corner(client, name, *, disable_tests="", session="") -> str`

- **签名/出处**：`writer.py:228-229`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  dt = f' ?disableTests `{disable_tests}' if disable_tests else ""
  return _q(client, f'maeSetCorner("{name}"{dt}{s})')
  ```
- **参数注入**：`name` 必填；`disable_tests`/`session` 有值才拼；`disable_tests` 前是反引号。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：`disable_tests` 示例为 `'("AC" "TRAN")'`；空值省略关键字。

### `setup_corner(client, name, *, model_file="", model_section="", variables=None, session="") -> str`

- **签名/出处**：`writer.py:239-242`。
- **内部 SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  set_corner(client, name, session=session)
  for var_name, var_value in (variables or {}).items():
      _q(client,
         f'maeSetVar("{var_name}" "{var_value}" '
         f'?typeName "corner" ?typeValue \'("{name}"){s})')
  sess_id = session or _q(client, "car(maeGetSessions())")
  model_name = model_file.rsplit("/", 1)[-1] if "/" in model_file else model_file
  expr = (
      f'let((sdb corn model) '
      f'sdb = axlGetMainSetupDB("{sess_id}") '
      f'corn = axlGetCorner(sdb "{name}") '
      f'model = axlPutModel(corn "{model_name}") '
      f'axlSetModelFile(model "{model_file}") '
      f'{f"""axlSetModelSection(model "{model_section}") """ if model_section else ""}'
      f'model)')
  ```
- **参数注入**：`name` 必填；`model_file`/`model_section`/`variables`/`session` 可选；变量逐项生成；model_name 只按 `/` basename；section 空则省略 `axlSetModelSection`。
- **执行/超时**：`set_corner()` 内部 `_q`，每变量一次 `_q`，model 表达式一次 `_q`；默认各 30 秒。
- **返回解析**：返回 Python `name`，丢弃所有内部 SKILL output；`set_corner()` 结果也被忽略。
- **会话**：显式 session 用于变量和 `axlGetMainSetupDB()`；空 session 时变量省略 `?session`，model 分支查询 `car(maeGetSessions())`。
- **失败/边界**：partial 操作，创建 corner 后变量/model 失败不回滚；`axlGetCorner` 返回 nil 仍继续 `axlPutModel`；路径无转义，不处理 Windows `\` basename。

### `load_corners(client, filepath, *, sections="corners", operation="overwrite") -> str`

- **签名/出处**：`writer.py:293-295`。
- **SKILL 构造**：
  ```python
  return _q(client,
      f'maeLoadCorners("{filepath}" ?sections "{sections}" '
      f'?operation "{operation}")')
  ```
- **参数注入**：`filepath` 必填；`sections="corners"`；`operation="overwrite"`；无 session 参数；无转义。
- **执行/超时**：`_q`；默认 30 秒；本函数不执行 CSV 上传。
- **返回解析**：原始 output；不检查导入结果或远端文件。
- **会话**：无 `?session`，使用 current session。
- **失败/边界**：文件必须在远端路径；含引号/反斜杠会破坏 SKILL。

### `set_current_run_mode(client, run_mode, *, session="") -> str`

- **签名/出处**：`writer.py:306-307`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client, f'maeSetCurrentRunMode(?runMode "{run_mode}"{s})')
  ```
- **参数注入**：`run_mode` 必填；`session` 空则省略；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：示例 `"Single Run, Sweeps and Corners"`；非法 mode 由 SKILL 报错。

### `set_job_control_mode(client, mode, *, session="") -> str`

- **签名/出处**：`writer.py:317-318`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client, f'maeSetJobControlMode("{mode}"{s})')
  ```
- **参数注入**：`mode` 必填；`session` 有值才拼；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：示例 `"Local"`/`"LSCS"`；非法 mode 由 Maestro 报错。

### `set_job_policy(client, policy, *, test_name="", job_type="", session="") -> str`

- **签名/出处**：`writer.py:324-326`；`policy` 无类型标注。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  parts = f"maeSetJobPolicy({policy}"
  if test_name: parts += f' ?testName "{test_name}"'
  if job_type: parts += f' ?jobType "{job_type}"'
  parts += f'{s})'
  return _q(client, parts)
  ```
- **参数注入**：`policy` 必填并原样插入；`test_name`/`job_type`/`session` 有值才拼；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：可选 `?session`。
- **失败/边界**：Python 字符串不会自动补引号；合法性由 SKILL 决定。

### `save_setup(client, lib, cell, *, session="") -> str`

- **签名/出处**：`writer.py:630-631`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client,
      f'maeSaveSetup(?lib "{lib}" ?cell "{cell}" ?view "maestro"{s})')
  ```
- **参数注入**：`lib`/`cell` 必填；`session` 空则省略；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output；不验证磁盘写入。
- **会话**：可选 `?session`。
- **失败/边界**：仿真前旧代码要求先保存 setup；本函数只发起 SKILL。

### `create_netlist_for_corner(client, test, corner, output_dir, *, session="") -> str`

- **签名/出处**：`writer.py:582-584`。
- **SKILL 构造**：
  ```python
  s = f' ?session "{session}"' if session else ""
  return _q(client,
      f'maeCreateNetlistForCorner("{test}" "{corner}" "{output_dir}"{s})')
  ```
- **参数注入**：`test`/`corner`/`output_dir` 必填；`session` 空则省略；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output；不下载产物。
- **会话**：可选 `?session`，省略时 Cadence 用 current session。
- **失败/边界**：产物在远端文件系统，需要 `download_file()`；路径无保护。

### `export_output_view(client, filepath, *, view="Detail") -> str`

- **签名/出处**：`writer.py:594-595`。
- **SKILL 构造**：
  ```python
  return _q(client,
      f'maeExportOutputView(?fileName "{filepath}" ?view "{view}")')
  ```
- **参数注入**：`filepath` 必填；`view="Detail"`；无 session；无转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output；reader 以下载后的 CSV 存在性为准，不信任返回 `t`/`nil`。
- **会话**：无 `?session`，current session。
- **失败/边界**：可能返回 `t`、`nil` 或文件名；本函数不区分。

### `write_script(client, filepath) -> str`

- **签名/出处**：`writer.py:601`。
- **SKILL 构造**：
  ```python
  return _q(client, f'maeWriteScript("{filepath}")')
  ```
- **参数注入**：`filepath` 必填；无 session/转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output；不验证文件。
- **会话**：current session。
- **失败/边界**：文件写在 Cadence/远端主机；路径需自行处理。

---

## 3. writer.py：仿真、诊断与 GUI 辅助

### `run_simulation(client, *, session="", callback="", timeout=None) -> str`

- **签名/出处**：`writer.py:338-339`。
- **SKILL 构造**：
  ```python
  parts = "maeRunSimulation("
  if session: parts += f'?session "{escape_skill_string(session)}" '
  if callback: parts += f'?callback "{escape_skill_string(callback)}" '
  parts = parts.rstrip() + ")"
  return _q(client, parts, timeout=timeout)
  ```
- **参数注入**：session/callback 有值才拼；两者都空时是 `maeRunSimulation()`；两者均转义。
- **执行/超时**：`_q` 并显式传 timeout；`None` 时仍使用 client 默认 30 秒。
- **返回解析**：原始 history output（如 `"Interactive.1"`），不剥引号。
- **会话**：可选 `?session`。
- **失败/边界**：可能返回 `nil` 且 `_q` 不报错，由 `run_and_wait()` 处理。

### `_remove_marker(runner, marker) -> None`

- **签名/出处**：`writer.py:358`。
- **行为**：`runner is None` 时本地 `Path(marker).unlink()`，忽略 `FileNotFoundError`/`OSError`；否则 `runner.run_command(f"rm -f {marker}", timeout=10)`。
- **参数注入**：marker 原样进 shell，不转义；调用方使用生成的 `/tmp/vb_sim_done_*`。
- **执行/超时**：本地文件系统或 SSH；远程 10 秒。
- **返回解析**：无返回；不检查远程结果。
- **会话**：无。
- **失败/边界**：本地删除失败静默；特殊字符 marker 有命令风险。

### `_wait_until_done(client, marker, timeout=600) -> str`

- **签名/出处**：`writer.py:372-373`。
- **行为**：本地 `Path(marker).exists()`+`read_text().strip()`；远端执行 `cat {marker} 2>/dev/null`，单次 timeout `min(10, remaining)`；有内容则 `_remove_marker()` 并返回，否则 `sleep(min(2, remaining))`。
- **参数注入**：`marker` 必填原样插入；`timeout` 是总预算，默认 600 秒。
- **执行/超时**：本地 stdlib 或 SSH `run_command`，不执行 SKILL。
- **返回解析**：本地/远端内容 `.strip()`；空内容不算完成。
- **会话**：无。
- **失败/边界**：到期抛 `TimeoutError("Simulation did not finish within {timeout}s")`。

### `_strip_skill_atom(raw) -> str`

- **签名/出处**：`writer.py:420-421`。
- **行为**：`return (raw or "").strip().strip('"')`。
- **参数注入**：`raw` 可为 None/空串；无转义。
- **执行/超时**：纯 Python，无 I/O。
- **返回解析**：去空白后去两端任意双引号；不是 `_unescape_skill_string()`。
- **会话**：无。
- **失败/边界**：`"nil"` 不变 Python `None`；内部转义不还原。

### `_diagnose_run_not_started(client, session) -> dict[str, str]`

- **签名/出处**：`writer.py:424`。
- **SKILL 探针**：
  ```text
  car(maeGetSetup(?session "{session}"))
  maeGetEnabledAnalysis("{test}" ?session "{session}")
  let((s) s = car(errset(sevSession(hiGetCurrentWindow()))) if(s then "t" else "nil"))
  let((f) f = hiGetCurrentForm() when(f f~>name))
  ```
- **参数注入**：`session` 直接插入前两个表达式，空串也生成 `?session ""`；test 由第一探针经 `_strip_skill_atom()` 后插入第二个。
- **执行/超时**：每个探针各自 `_q`，默认 30 秒；所有块 `except Exception` 后留 partial。
- **返回解析**：固定 keys `session/test/enabled_analyses/is_explorer_window/current_form`；失败字段留空。
- **会话**：强依赖传入 session 文本，不主动查询。
- **失败/边界**：诊断本身不抛错；`maeGetSetup`/`maeGetEnabledAnalysis`/form 探针可能返回 nil 或不存在。

### `_try_recover_blocking_form(client, info) -> bool`

- **签名/出处**：`writer.py:471`。
- **SKILL 构造**：`let((f) f = hiGetCurrentForm() when(f hiFormDone(f)) t)`，随后 `client.dismiss_dialog()` 作 X11 fallback。
- **参数注入**：只读取 `info["current_form"]`；空/`"nil"` 直接返回 `False`。
- **执行/超时**：`_q` 默认 30 秒；X11 `dismiss_dialog()` 为独立兜底；两者都吞异常。
- **返回解析**：有 form 时总是 `True`，即使两侧 dismissal 都失败。
- **会话**：无 `?session`，操作 current form。
- **失败/边界**：不证明恢复成功；`run_and_wait` 最多重试一次。

### `run_and_wait(client, *, session="", timeout=600) -> tuple[str, str]`

- **签名/出处**：`writer.py:491-492`。
- **回调 SKILL**（`writer.py:518-529`）：`nonce=uuid4().hex[:8]`，marker=`/tmp/vb_sim_done_<nonce>`：
  ```skill
  procedure(_vb_sim_done_<nonce>(session runID)
    system(sprintf(nil "echo done > /tmp/vb_sim_done_<nonce>"))
    printf("[%s sim done] run %L\n" nth(2 parseString(getCurrentTime())) runID))
  ```
- **启动流程**（`writer.py:530-575`）：定义 callback → `run_simulation(... callback=..., timeout=remaining)` → `_strip_skill_atom(history)` 查 nil → nil 则诊断+恢复+最多重试一次 → 仍 nil 删除 marker 并抛 `RuntimeError` → 成功则 `_wait_until_done()` 返回 `(history, status)`。
- **参数注入**：`session` 可为空；`timeout=600` 为启动和等待共用的 end-to-end 预算；`remaining_timeout()` 超期抛 `TimeoutError`。
- **执行/超时**：callback 注册用 `client.execute_skill()` 直接执行，不检查 `r.errors`；默认 30 秒。启动/等待受 `timeout` 控制。
- **返回解析**：history 保留原始引号（示例 `'"Interactive.1"'`）；status 是 marker 内容 `"done"`。
- **会话**：非空 session 由 `run_simulation` 拼 `?session`；诊断路径空串也会显式拼 `?session ""`。
- **失败/边界**：`maeRunSimulation` 返回 nil 时 fail fast，避免无限轮询；重试后仍 nil 抛异常；超时抛 `TimeoutError`。

### `migrate_adel_to_maestro(client, lib, cell, state) -> str`

- **签名/出处**：`writer.py:610-611`。
- **SKILL 构造**：`maeMigrateADELStateToMaestro("{lib}" "{cell}" "{state}")`。
- **参数注入**：三者必填；无 session/转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：无。
- **失败/边界**：失败由 SKILL error 或 `nil` 体现。

### `migrate_adexl_to_maestro(client, lib, cell, view="adexl", *, maestro_view="maestro") -> str`

- **签名/出处**：`writer.py:617-619`。
- **SKILL 构造**：`maeMigrateADEXLToMaestro("{lib}" "{cell}" "{view}" ?maestroView "{maestro_view}")`。
- **参数注入**：lib/cell 必填；view 默认 `"adexl"`；maestro_view 关键字默认 `"maestro"`；无 session/转义。
- **执行/超时**：`_q`；默认 30 秒。
- **返回解析**：原始 output。
- **会话**：无。
- **失败/边界**：不验证目标 view。

### `open_maestro_gui_with_history(client, lib, cell, *, history="") -> str`

- **签名/出处**：`writer.py:642-643`。
- **执行顺序**（`writer.py:659-673`）：未给 history 时执行 `asiGetResultsDir(asiGetCurrentSession())`，`.strip('"')` 后用 `/maestro/results/maestro/([^/]+)/` 取 history，找不到抛 `RuntimeError("No simulation history found")`；然后依次 `deOpenCellView("{lib}" "{cell}" "maestro" "maestro" nil "r")`、`maeMakeEditable()`、`maeRestoreHistory("{history}")`、`maeSaveSetup(?lib "{lib}" ?cell "{cell}" ?view "maestro")`。
- **参数注入**：lib/cell 必填；history 空则自动探测；无 session 参数/转义。
- **执行/超时**：探测用 `client.execute_skill()` 直接执行；其余用 `_q`；均未传 timeout，默认 30 秒。
- **返回解析**：返回 Python history 字符串；不返回 SKILL output。
- **会话**：隐式 current GUI session，自动探测依赖 `asiGetCurrentSession()`。
- **失败/边界**：`maeMakeEditable()` 无条件调用，已有编辑锁时可能弹 modal 阻塞；history 不存在则 restore 失败。

---

## 4. lifecycle.py：会话和窗口 SKILL

### `_x11_run(runner, cmd, timeout=5)`

- **签名/出处**：`lifecycle.py:24`。
- **行为**：有 runner 时 `runner.run_command(cmd, timeout=timeout)`；否则 `subprocess.run(["sh","-c",cmd], capture_output=True, text=True, timeout=timeout)`；超时 rc=124，无 sh rc=127。
- **参数注入**：cmd 原样交给 shell；timeout 默认 5 秒；非 SKILL。
- **执行/返回**：SSH/本地 shell；统一返回 `.returncode/.stdout/.stderr`。
- **会话**：无。
- **失败/边界**：Windows 本地 no-op；调用者通常忽略非零 rc。

### `_detect_virtuoso_display(runner) -> str`

- **签名/出处**：`lifecycle.py:52`。
- **探测顺序**：`VB_DISPLAY` → `strings /proc/$(pgrep -u $(whoami) -f "64bit/virtuoso" | head -1)/environ 2>/dev/null | grep ^DISPLAY= | head -1` → 仅本地 `$DISPLAY`。
- **参数注入**：runner 决定 SSH/本地；无 timeout 参数，`_x11_run` 固定 5 秒。
- **执行/返回**：shell；去掉 `DISPLAY=` 并 strip，失败返回空串并 warning。
- **会话**：无。
- **失败/边界**：无 Virtuoso 进程/无 X server 时空串，后续发送 no-op。

### `_send_x11_key(runner, keysym) -> None`

- **签名/出处**：`lifecycle.py:79`。
- **命令模板**：`DISPLAY=<display> python2.7 -c "import ctypes,ctypes.util; xlib=...find_library(chr(88)+chr(49)+chr(49)); xtst=...find_library(chr(88)+chr(116)+chr(115)+chr(116)); dpy=xlib.XOpenDisplay(None); kc=xlib.XKeysymToKeycode(dpy,<keysym>); xtst.XTestFakeKeyEvent(dpy,kc,True,0); xtst.XTestFakeKeyEvent(dpy,kc,False,0); xlib.XFlush(dpy);xlib.XCloseDisplay(dpy)"`。
- **参数注入**：keysym 原样进命令；display 由探测得到；非 SKILL。
- **执行/超时**：`_x11_run(..., timeout=5)`。
- **返回解析**：无；无 display 直接返回。
- **会话**：无。
- **失败/边界**：依赖 python2.7/X11/XTest；不等待窗口响应。

### `_send_x11_alt_n(runner) -> None`

- **签名/出处**：`lifecycle.py:99`。
- **行为**：同 `_send_x11_key` 的 ctypes 模板，按/放 Alt_L(`0xffe9`) 和 `n`(`0x006e`)，发送 Alt+N；timeout 固定 5 秒。
- **参数注入**：runner 决定 SSH/本地；非 SKILL。
- **返回解析**：无。
- **会话/失败**：无 session；用于“不保存”确认，Escape 只能取消对话框。

### `_purge_maestro_cellviews(client, *, timeout=60) -> None`

- **签名/出处**：`lifecycle.py:126`。
- **SKILL 模板**：
  ```skill
  foreach(cv dbGetOpenCellViews()
    when(cv~>viewName == "maestro"
      errset(dbPurge(cv))))
  ```
- **参数注入**：无 SKILL 参数；timeout 默认 60 秒直接传 `execute_skill()`。
- **执行/返回**：直接 `client.execute_skill(..., timeout=timeout)`，忽略 errors/output；无 `?session`。
- **失败/边界**：单个 dbPurge 错误被 errset 吞；是内存逐出，不删磁盘。

### `_get_session_windows(client) -> list[dict]`

- **签名/出处**：`lifecycle.py:144`。
- **SKILL 模板**：
  ```skill
  let((result)
    result = list()
    foreach(w hiGetWindowList()
      let((s name)
        s = car(errset(axlGetWindowSession(w)))
        name = hiGetWindowName(w)
        when(s && name
          result = cons(list(s w~>windowNum name) result))))
    result)
  ```
- **参数注入**：无；直接 `execute_skill()`，未传 timeout，默认 30 秒；不检查 errors。
- **返回解析**：空/`nil`→`[]`；否则正则 `r'\("([^"]+)"\s+(\d+)\s+"([^"]+)"\)'` 解析。标题含 `Assembler`/`Explorer` 才保留；含 `"Editing:"`→`editing`，否则 `reading`；`title.rstrip().endswith("*")`→`modified=True`。
- **会话**：session 来自 `axlGetWindowSession(w)`，标题来自 `hiGetWindowName(w)`。
- **失败/边界**：窗口顺序可能倒序；不支持转义引号标题；非 ADE 窗口丢弃。

### `_close_background_sessions(client) -> list[str]`

- **签名/出处**：`lifecycle.py:189`。
- **SKILL**：先 `maeGetSessions()`；对不在 GUI 窗口 session 集合中的 s 执行 `errset(maeCloseSession(?session "<s>" ?forceClose t))`。
- **参数注入**：无 Python 参数；直接 `execute_skill()`，默认 30 秒。
- **返回解析**：正则找所有双引号 session；对非 GUI session 逐个加入 `closed` 返回；errset 失败不检查。
- **会话**：与 `_get_session_windows()` 的 session 集合联合判断。
- **失败/边界**：GUI-opened zombie 可能无法真正关闭（ASSEMBLER-8051），仍记为 closed；best-effort。

### `open_session(client, lib, cell) -> str`

- **签名/出处**：`lifecycle.py:217`。
- **SKILL 模板**：
  ```skill
  let((session)
    session = maeOpenSetup("<lib>" "<cell>" "maestro")
    printf("[%s maeOpenSetup] <lib>/<cell>  session=%s\n"
           nth(2 parseString(getCurrentTime())) "<lib>" "<cell>" session)
    session)
  ```
- **参数注入**：lib/cell 必填；无 session 参数；无转义。
- **执行/超时**：直接 `client.execute_skill()`；默认 30 秒。
- **返回解析**：`(r.output or "").strip('"')`；空或 `nil`/`t` 抛 `RuntimeError("maeOpenSetup failed for {lib}/{cell}")`。
- **会话**：创建后台 session，后续 writer 应使用返回值。
- **失败/边界**：不先检查 r.errors；后台 session 适合配置读写，仿真用 GUI。

### `close_session(client, session) -> None`

- **签名/出处**：`lifecycle.py:229`。
- **SKILL 模板**：
  ```skill
  progn(
    maeCloseSession(?session "<session>" ?forceClose t)
    printf("[%s maeCloseSession] session=<session> closed\n"
           nth(2 parseString(getCurrentTime())) "<session>"))
  ```
- **参数注入**：session 必填，无转义。
- **执行/超时**：直接 `client.execute_skill()`；默认 30 秒。
- **返回解析**：无返回，不检查 errors。
- **会话**：关闭传入的后台 session。
- **失败/边界**：progn 用于避免尾部 printf 被误解析；错误可能静默导致 session 存活。

### `find_open_session(client) -> str | None`

- **签名/出处**：`lifecycle.py:245`。
- **SKILL 模板**：
  ```skill
  let((result)
    result = nil
    foreach(s maeGetSessions()
      unless(result
        when(maeGetSetup(?session s)
          result = s)))
    result)
  ```
- **参数注入**：无；直接 `execute_skill()`，默认 30 秒，不检查 errors。
- **返回解析**：`.output.strip('"')`；非空且非 `"nil"` 返回，否则 `None`。
- **会话**：只选 `maeGetSetup` 非 nil 的 session（至少一个 test）。
- **失败/边界**：空 maestro view 不可见；需要 fresh view 时用 `_find_session_for_cell()`。

### `_find_session_for_cell(client, lib, cell) -> str | None`

- **签名/出处**：`lifecycle.py:273-274`。
- **行为**：遍历 `_get_session_windows()`；`lib in title and cell in title` 时返回 `w["session"]`，找不到 `None`。
- **参数注入**：substring 匹配，不是精确 cellview 属性匹配。
- **执行/超时**：依赖 `_get_session_windows()`，默认 30 秒。
- **返回解析**：窗口 session 字段。
- **会话**：用于识别 fresh/empty GUI maestro view。
- **失败/边界**：子串或缺少名称会误匹配；多个匹配返回第一个。

### `open_gui_session(client, lib, cell, *, timeout=60) -> str`

- **签名/出处**：`lifecycle.py:294-295`。
- **流程/模板**：关闭后台 session → 取窗口；目标 editing 直接复用；其他窗口 `close_gui_session(save=(mode=="editing"))` → 执行
  ```skill
  deOpenCellView("<lib>" "<cell>" "maestro" "maestro" nil "a")
  ```
  该调用显式 timeout；若 `r.errors` 或 output 空/`nil` 抛 RuntimeError → `_find_session_for_cell()` 找 session，找不到抛 RuntimeError。
- **参数注入**：lib/cell 必填；timeout 关键字默认 60 秒；无字符串转义。
- **执行/超时**：`execute_skill`；打开调用 60 秒，窗口/session 探测默认 30 秒。
- **返回解析**：返回标题匹配得到的 session；不调用 `maeOpenSetup`，也不再调 `maeMakeEditable`。
- **会话**：session 由 GUI 标题匹配；`"a"` 直接 editable 打开。
- **失败/边界**：会关闭其他/reading 窗口，可能丢修改；窗口未出现时抛错；匹配可受子串影响。

### `close_gui_session(client, session, save=True, *, timeout=60) -> None`

- **签名/出处**：`lifecycle.py:360-361`。
- **流程**：找 `session` 窗口；无窗口则直接 `maeCloseSession(?session "<session>" ?forceClose t)` 并 return（不 purge）。有窗口且 modified+save 时：editing 执行 `maeSaveSetup(?session "<session>")`；reading 若无其他 editing 则 `maeMakeEditable()` 成功后保存，否则丢修改。最后 `_close_gui_window()` + `_purge_maestro_cellviews()`。
- **参数注入**：session 必填；save 默认 True 可位置传；timeout 关键字默认 60 秒，用于 maeMakeEditable/hiCloseWindow/purge。
- **执行/超时**：直接 execute 与 _q 混合；save/background close 未显式 timeout（默认 30 秒），关键调用 60 秒。
- **返回解析**：无；不检查 save errors，不验证 session 真关闭。
- **会话**：有窗口走 `hiCloseWindow`，无窗口才退回 `maeCloseSession`。
- **失败/边界**：save=False 时 X11 Alt+N 处理保存框；maeMakeEditable 失败只 warning 并丢弃修改；可能 partial。

### `_close_gui_window(client, window_info, all_windows=None, *, timeout=60) -> None`

- **签名/出处**：`lifecycle.py:426-428`；`all_windows` 未使用。
- **SKILL 模板**：
  ```skill
  let((w)
    foreach(win hiGetWindowList()
      when(win~>windowNum == <window_num> w = win))
    when(w hiCloseWindow(w)))
  ```
- **参数注入**：window_info 需有 window_num/modified；timeout 默认 60 秒；无 session 关键字。
- **执行/返回**：直接 `execute_skill(..., timeout=timeout)`，不检查 errors；无返回。
- **失败/边界**：modified 时先启动 daemon 线程，0.5 秒后 Alt+N，再 hiCloseWindow；join 10 秒，X11 失败不回抛。

---

## 5. ops.py / response.py / skill_output.py：转义与解析

公共函数逐项（签名、行为、返回、边界）：

| 函数 | 签名/出处 | 关键行为与边界 |
|---|---|---|
| `escape_skill_string(value: str) -> str` | `ops.py:7` | `value.replace("\\", "\\\\").replace('"', '\\"')`；先反斜杠后双引号；不处理换行/Tab/NUL/单引号；返回未加外层引号的内容。 |
| `q(value: str) -> str` | `ops.py:11-18` | `f'"{escape_skill_string(value)}"'`；返回完整双引号 SKILL 字面量。writer `add_output` 内联 escape，不调用它。 |
| `response_fields(response: Any) -> tuple[list[str], Any, str]` | `response.py:9` | dict 从 response/result 取 errors/status/output，`ok is False` 且无 errors 时补 `"request failed"`；object 读 `.errors/.status/.output`；返回 `(errors list, status, output str)`。 |
| `_error_messages(errors: Any) -> list[str]` | `response.py:29-36` | `None`/空串→`[]`；str→`[str]`；可迭代→逐项 str；其他→`[str(errors)]`。 |
| `_output_text(output: Any) -> str` | `response.py:39-44` | `None`→`""`；str 原样；其他→`str(output)`；不剥引号、不解析 `nil`。 |
| `parse_skill_str_list` | `skill_output.py:6-19` | 空/nil→`[]`；tokenize 顶层 group/string，`parse_sexpr` 后递归 `_collect_strings()`；只返回字符串叶子。 |
| `tokenize_top_level` | `skill_output.py:22-29` | `(body, *, include_groups=True, include_strings=False, include_atoms=False, max_tokens=None) -> list[str]`；逐字符扫描，字符串用 `_scan_string`、括号用 `_scan_group`，其他聚成 atom。 |
| `scan_top_groups` | `skill_output.py:59-66` | 只 include_groups 的 tokenize；返回顶层括号组。 |
| `parse_sexpr` | `skill_output.py:69` | 空/nil→None、t→True、双引号→`_unescape_skill_string`、括号→递归 list、其他 atom→str。 |
| `is_single_complete_skill_list` | `skill_output.py:98-124` | 要求以 `(` 开头，跟踪 string/escape/depth；中途归零且有尾随字符或负 depth→False；只验证一个完整顶层 list。 |
| `_unescape_skill_string` | `skill_output.py:164-183` | `\n`→换行、`\t`→Tab、`\r`→CR、`\"`→`"`、`\\`→`\`；其他 `\x` 保留 `\x`。 |
| `_scan_string` / `_scan_group` / `_is_escaped` / `_collect_strings` | `skill_output.py:127-193` | 分别扫描字符串、按深度扫描括号、判断前方反斜杠奇偶、递归收集 str 叶子；均纯 Python、无 session/超时。 |

---

## 6. 会话模型

### 后台会话

- **打开**：`open_session(client, lib, cell)` → `maeOpenSetup("<lib>" "<cell>" "maestro")`，输出 strip 引号并校验非空/nil/t；失败抛 RuntimeError (`lifecycle.py:217-226`)。
- **使用**：writer 把非空 session 拼成 `?session "<session>"`；空 session 让 Cadence 用 current session。
- **识别**：`find_open_session()` 遍历 `maeGetSessions()`，取第一个 `maeGetSetup(?session s)` 非 nil 的 session；空 view 不可见 (`lifecycle.py:245-270`)。
- **关闭**：`close_session()` → `maeCloseSession(?session ... ?forceClose t)`，用 `progn` 包裹 close+printf (`lifecycle.py:229-242`)。
- **限制**：后台 session 适合配置读写；仿真用 GUI session。

### GUI 会话

- **打开**：`open_gui_session()` 关闭后台/僵尸 session，复用目标 editing 窗口，关闭其他/reading 窗口，然后 `deOpenCellView(..., nil, "a")`；不额外调用 `maeOpenSetup`/`maeMakeEditable` (`lifecycle.py:294-357`)。
- **识别**：`_find_session_for_cell()` 不用 `maeGetSetup`，而按窗口标题中 lib/cell substring 匹配；fresh/empty view 也能识别 (`lifecycle.py:273-287`)。
- **窗口状态**：`_get_session_windows()` 通过 `hiGetWindowList/axlGetWindowSession/hiGetWindowName`；标题 `"Assembler"`/`"Explorer"` 定类型，`"Editing:"` 定 editing，尾部 `*` 定 modified (`lifecycle.py:144-186`)。
- **关闭**：`close_gui_session()` 根据状态保存/提升/丢弃，`_close_gui_window()` 按 windowNum 执行 `hiCloseWindow(w)`，最后 `_purge_maestro_cellviews()`；无 GUI 窗口才退回 `maeCloseSession` (`lifecycle.py:360-423`)。
- **编辑锁冲突**：reading 有修改且无其他 editing 时调用 `maeMakeEditable()`（无 `?session`）再保存；有其他 editing 时丢修改；该调用可能弹对话框阻塞 SKILL。

### `_purge_maestro_cellviews` 为什么需要

- `hiCloseWindow + maeCloseSession` 后，maestro cellview 可能仍在 Virtuoso 虚拟内存中并持有内部 edit lock。
- `dbPurge(cv)` 强制逐出内存对象，之后另一个 cell 才能 editable 打开；不 purge 可能报 `ASSEMBLER-8127` (`lifecycle.py:126-137,419-422`)。
- 它只逐出内存，不删除磁盘。

### X11 兜底

- 保存确认框会阻塞 `hiCloseWindow`；`_close_gui_window()` 先启动 daemon thread，0.5 秒后 Send Alt+N（No/Don't Save），再 hiCloseWindow (`lifecycle.py:426-468`)。
- DISPLAY 探测：`VB_DISPLAY` → `/proc/<virtuoso>/environ` → 本地 `$DISPLAY`；失败 no-op (`lifecycle.py:52-76`)。
- 发送依赖 python2.7+X11/XTest；Windows 无 `/bin/sh` 时 `_x11_run` rc=127 而非崩溃 (`lifecycle.py:24-49`)。

---

## 7. 通用拼接与转义约定

### 双引号字符串

- `escape_skill_string()` 只把 `\`→`\\`、`"`→`\"`，且先处理反斜杠 (`ops.py:7-9`)。
- 它不转义换行/Tab/控制符；多行文本建议走文件路径。
- 转义分布：`add_output` 全部五类值含 session；`run_simulation` 的 session/callback；其余 writer 配置写函数基本原样插入。

### `?keyword` 与可选值

- 生成形式固定为 ` ?keyword value`；`s = f' ?session "{session}"' if session else ""` 是统一模式。
- 布尔 SKILL 值必须是 `t`/`nil`，如 `set_analysis` 的 `?enable`；Python bool 不会自动映射。
- “有值才拼”是 `[ ?keyword ...]`；`options` 等位置参数没有空值省略保护，可能生成空反引号。

### 反引号 alist / 单引号 list

- `set_analysis`、`set_env_option`、`set_sim_option`、`set_corner`、`get_parameter`、`set_parameter` 用反引号：`?options \`(("temp" "85") ("reltol" "1e-5"))`。反引号让 SKILL 得到 quoted list/alist，而非一个字符串。
- `set_var`、`setup_corner` 的 corner 变量用单引号：`?typeValue '("IB_PSS")`/`'("myCorner")`；同样是 SKILL quote。
- 不要写成 `?options "(...)"`；不要用 `escape_skill_string()` 处理 alist，否则内部 `"` 会被转成 `\"`。
- Python 只原样拼接 alist，不做 JSON/Python repr 转换。

### 返回值与错误

- `_q` 路径：错误抛 `RuntimeError`，成功返回 raw output，`nil` 仍是字符串。
- 直接 `execute_skill` 路径（open/close/lifecycle/window helper）有的不检查 `r.errors`；不要把它们当 `_q`。
- 裸 atom 用 `_strip_skill_atom()`；复杂 `%L` 用 tokenizer/`parse_sexpr()`；不要用 `strip('"')` 处理转义字符串。

---
