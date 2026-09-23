"""L0 contracts for ``pyapi.packages.maestro`` 的 SKILL 构造层。

`Package._command_exprs(command, session)` 是**纯字符串构造器**（把一条
write/write_history 原子翻译成 SKILL 表达式列表），不碰真机，因此
"每个 op 至少能构造出合法 SKILL" 这件事可以完全离线钉死——这正是真机
TB 覆盖不到的那一大片。

矩阵数据（op → 最小合法命令）由 `test/shared/runners/skill_op_table.py`
从源码抽取后人工补全，新增 op 时该表会因 "unknown atomic op" 而红。
"""
from __future__ import annotations

import unittest

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import maestro as M


class FakeMiddle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append(skill_code)
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='("ok")')

    def query(self, *, token, role=None, name=None):
        # maestro 用 query 取 role root（load_corners 之类的路径推导）；
        # 这里给一个最小可用对象即可。
        class _Role:
            root = "/role/root"

        class _Query:
            roles = {"command": _Role(), "daemon": _Role(), "file": _Role()}

        return _Query()


def balanced(text: str) -> bool:
    depth = 0
    in_string = False
    escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not in_string


#: op → 最小合法命令（值取最朴素形态；类型不对会被构造器拒绝并在此暴露）
COMMANDS: dict[str, dict] = {
    "set_test": {"test": "t1", "lib": "L", "cell": "C"},
    "set_design": {"test": "t1", "lib": "L", "cell": "C"},
    "delete_test": {"test": "t1"},
    "set_analysis": {"test": "t1", "analysis": "tran"},
    "set_var": {"name": "v1", "value": "1"},
    "delete_var": {"name": "v1"},
    # name 必须是 Library/Cell/View/Instance/Property 五段式（源码 :974 校验）
    "set_parameter": {"name": "L/C/view/inst/param", "value": "2"},
    "delete_parameter": {"name": "p1"},
    "set_env_option": {"test": "t1", "options": {"a": "b"}},
    "set_sim_option": {"test": "t1", "options": {"a": "b"}},
    "set_corner": {"name": "c1"},
    "delete_corner": {"name": "c1"},
    "setup_corner": {"name": "c1"},
    "set_run_mode": {"run_mode": "single"},
    "set_job_control_mode": {"mode": "local"},
    # policy 字符串必须是"原始 SKILL 表达式"（以 ( 或 ' 开头），否则被拒（源码 :1140-1145）
    "set_job_policy": {"policy": "(t)", "test": "t1"},
    "set_simulator_mode": {"mode": "spectre"},
    "add_output": {"name": "o1", "test": "t1"},
    # 必须带一个 spec bound（gt/lt/min/max/tol/range 之一）或 info/weight/corner（源码 :1205-1209）
    # bound 目前只接受字符串（数值会抛原始 AttributeError，见下方用例与 bug 报告）
    "set_spec": {"name": "s1", "test": "t1", "min": "0"},
    "delete_output": {"name": "o1", "test": "t1"},
    "delete_spec": {"name": "s1", "test": "t1"},
    "delete": {"history": "h1"},
    "delete_results": {"history": "h1"},
    "rename": {"history": "h1", "new_name": "h2"},
    "lock": {"history": "h1"},
    "unlock": {"history": "h1"},
}


class TestModuleHelpers(unittest.TestCase):
    def test_require_text_history_output(self):
        self.assertEqual(M._require_text("x", "n"), "x")
        with self.assertRaises(ValueError):
            M._require_text("", "n")
        self.assertEqual(M._require_history_name("h1"), "h1")
        for bad in ("a/b", "a\\b", ".", "..", "x..y", ""):
            with self.assertRaises(ValueError):
                M._require_history_name(bad)
        self.assertEqual(M._require_output_name("o1"), "o1")
        for bad in ("a\nb", "a\rb", "a\tb", ""):
            with self.assertRaises(ValueError):
                M._require_output_name(bad)

    def test_require_timeout(self):
        M._require_timeout(None)
        M._require_timeout(3)
        for bad in (0, -1, "3"):
            with self.assertRaises(ValueError):
                M._require_timeout(bad)

    def test_session_kw(self):
        self.assertEqual(M._session_kw(""), "")
        self.assertIn("?session", M._session_kw("s1"))

    def test_small_coercions(self):
        self.assertEqual(M._unwrap_errset([1]), 1)
        self.assertEqual(M._unwrap_errset([1, 2]), [1, 2])
        self.assertEqual(M._to_int(" 42 "), 42)
        self.assertIsNone(M._to_int("x"))
        self.assertEqual(M._as_list(None), [])
        self.assertEqual(M._as_list([1]), [1])
        self.assertEqual(M._as_list(1), [1])
        self.assertEqual(M._as_dict({"a": 1}), {"a": 1})
        self.assertEqual(M._as_dict(None), {})
        self.assertEqual(M._safe_token("a b/c"), "a_b_c")
        self.assertEqual(M._safe_token(None, "fb"), "fb")

    def test_skill_atom_value(self):
        self.assertIsNone(M._skill_atom_value("nil"))
        self.assertTrue(M._skill_atom_value("t"))
        self.assertEqual(M._skill_atom_value('"text"'), "text")
        # parse_sexpr 产出的是字符串原子，不做数值转换
        self.assertEqual(M._skill_atom_value("(1 2)"), ["1", "2"])
        self.assertEqual(M._skill_atom_value("42"), 42)
        self.assertEqual(M._skill_atom_value("4.5"), 4.5)
        self.assertEqual(M._skill_atom_value("bare"), "bare")

    def test_skill_value_expr(self):
        self.assertEqual(M._skill_value_expr("s"), '"s"')
        self.assertEqual(M._skill_value_expr(3), "3")

    def test_skill_name_list(self):
        self.assertEqual(M._skill_name_list("a", "n"), "'(\"a\")")
        self.assertEqual(M._skill_name_list("'(\"a\")", "n"), "'(\"a\")")
        self.assertEqual(M._skill_name_list("(\"a\")", "n"), "'(\"a\")")
        self.assertEqual(M._skill_name_list(["a", "b"], "n"), "'(\"a\" \"b\")")
        self.assertEqual(M._skill_name_list_body(["a"], "n"), "(\"a\")")
        for bad in (None, "", "   ", [], 5):
            with self.assertRaises(ValueError):
                M._skill_name_list(bad, "typeValue")


class TestCommandExprMatrix(unittest.TestCase):
    def _exprs(self, op: str, **extra):
        command = {"op": op, **COMMANDS[op], **extra}
        return M.Package(FakeMiddle())._command_exprs(command, "s1")

    def test_every_op_builds_balanced_skill(self):
        self.assertTrue(COMMANDS, "matrix must not be empty")
        for op in COMMANDS:
            with self.subTest(op=op):
                exprs = self._exprs(op)
                self.assertIsInstance(exprs, list)
                self.assertTrue(exprs, f"{op} produced no expressions")
                self.assertTrue(all(isinstance(item, str) and item.strip()
                                    for item in exprs), f"{op} produced empty item")
                for item in exprs:
                    self.assertTrue(balanced(item), f"{op}: unbalanced {item[:120]}")

    def test_session_argument_is_threaded(self):
        with_session = self._exprs("delete", history="h1")[0]
        without = M.Package(FakeMiddle())._command_exprs(
            {"op": "delete", "history": "h1"}, "")[0]
        self.assertIn("s1", with_session)
        self.assertNotIn("s1", without)

    def test_unknown_op_and_non_dict_are_rejected(self):
        pkg = M.Package(FakeMiddle())
        with self.assertRaises(ValueError) as ctx:
            pkg._command_exprs({"op": "explode"}, "")
        self.assertIn("explode", str(ctx.exception))
        with self.assertRaises(ValueError):
            pkg._command_exprs(["not-a-dict"], "")
        with self.assertRaises(ValueError):
            pkg._command_exprs({"op": ""}, "")
        with self.assertRaises(ValueError):
            pkg._command_exprs({}, "")

    def test_missing_required_fields_are_rejected(self):
        pkg = M.Package(FakeMiddle())
        with self.assertRaises(ValueError):
            pkg._command_exprs({"op": "set_test", "test": "t1"}, "")
        with self.assertRaises(ValueError):
            pkg._command_exprs({"op": "delete_test"}, "")
        with self.assertRaises(ValueError):
            pkg._command_exprs({"op": "set_var", "name": ""}, "")
        with self.assertRaises(ValueError):
            pkg._command_exprs({"op": "delete", "history": "../x"}, "")

    def test_set_spec_rejects_multiple_bound_kinds(self):
        with self.assertRaises(ValueError) as ctx:
            M.Package(FakeMiddle())._command_exprs(
                {"op": "set_spec", "name": "s1", "test": "t1", "min": "0", "max": "1"}, "")
        self.assertIn("one spec bound", str(ctx.exception))

    def test_set_spec_should_accept_numeric_bound(self):
        """缺陷：数值 bound 走到 `basic.q(0)` → `AttributeError: 'int' object has no
        attribute 'replace'`（调用方看到 `command 0 invalid: 'int' object has no
        attribute 'replace'`）。spec 只写了 `lt / gt`，没说必须字符串。
        报告：bug-20260922T1315xx。修好后转绿。"""
        exprs = M.Package(FakeMiddle())._command_exprs(
            {"op": "set_spec", "name": "s1", "test": "t1", "min": 0}, "")
        self.assertTrue(exprs and all(balanced(item) for item in exprs))

class _Status:
    value = "success"


class _Role:
    root = "/role/daemon"


class _Facts:
    status = _Status()
    roles = {"daemon": _Role()}


class WriteMiddle:
    """按 SKILL 文本作答的假 middle，用来驱动 ``maestro.write`` 的会话编排。

    ``session_windows`` 控制走哪条路径：

    * ``"background"`` —— 没有窗口（后台会话，直接可写）；
    * ``"reading"``    —— 窗口标题是 ``Reading:``，需要 ``maeMakeEditable`` 提升；
    * ``"stuck"``      —— 提升失败（``nil``），write 应报 ``session is not editable``。
    """

    def __init__(self, path: str = "background", sessions: str = "nil",
                 save_output: str = '"saved"') -> None:
        self.path = path
        self.sessions_answer = sessions
        self.save_output = save_output
        self.promoted = False
        self.calls: list[str] = []
        self.uploads: list[str] = []
        self.fail_on: str = ""
        self.fail_silently_on: str = ""

    def query(self, *, token, role=None, name=None):
        return _Facts()

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        self.uploads.append(str(remote_path))
        from pyapi.models import CommandResult
        return CommandResult(0, str(remote_path), "", "command")

    def execute_skill(self, code, timeout=None, *, token):
        self.calls.append(code)
        if self.fail_on and self.fail_on in code:
            return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=["boom"])
        if self.fail_silently_on and self.fail_silently_on in code:
            # 无 errors 的失败：调用方只有 op 名可用，正是 `command {op} failed` 分支
            return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=[])
        if code.startswith("maeGetSessions"):
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.sessions_answer)
        if code.startswith("maeOpenSetup"):
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"sess1"')
        if "hiGetWindowList" in code:
            if self.path == "background":
                return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="nil")
            mode = "Editing:" if (self.promoted or self.path == "editing") else "Reading:"
            title = f"Assembler - LIB/CELL/maestro - {mode} x"
            return VirtuosoResult(
                status=ExecutionStatus.SUCCESS, output=f'(("sess1" 12 "{title}"))')
        if code.startswith("maeMakeEditable"):
            if self.path == "stuck":
                return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="nil")
            self.promoted = True
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")
        if code.startswith("maeSaveSetup"):
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.save_output)
        if code.startswith("maeCloseSession"):
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="t")


class TestWriteOrchestration(unittest.TestCase):
    REQUEST = dict(token="t", library="LIB", cell="CELL", view="maestro",
                   commands=[{"op": "delete", "history": "h1"}])

    def test_background_session_runs_command_saves_and_closes(self):
        middle = WriteMiddle(path="background")
        result = M.Package(middle).write(M.WriteRequest(**self.REQUEST))
        self.assertTrue(result.ok, result.error)
        names = [step["name"] for step in result.steps]
        self.assertEqual(
            names,
            ["open_session", "session_editable", "command:delete", "save_setup", "close_session"],
        )
        self.assertEqual(result.value, {"applied": 1, "session": "sess1"})
        self.assertTrue(any(call.startswith("maeCloseSession") for call in middle.calls))

    def test_gui_reading_session_is_promoted_to_editing(self):
        middle = WriteMiddle(path="reading")
        result = M.Package(middle).write(M.WriteRequest(**self.REQUEST))
        self.assertTrue(result.ok, result.error)
        names = [step["name"] for step in result.steps]
        self.assertIn("make_editable", names)
        self.assertTrue(any(call.startswith("maeMakeEditable") for call in middle.calls))

    def test_editing_session_needs_no_promotion(self):
        middle = WriteMiddle(path="editing")
        result = M.Package(middle).write(M.WriteRequest(**self.REQUEST))
        self.assertTrue(result.ok, result.error)
        self.assertFalse(any(call.startswith("maeMakeEditable") for call in middle.calls))

    def test_promotion_failure_stops_before_commands(self):
        middle = WriteMiddle(path="stuck")
        result = M.Package(middle).write(M.WriteRequest(**self.REQUEST))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "session is not editable")
        self.assertFalse(any("maeSetHistoryLock" in call for call in middle.calls))

    def test_existing_session_is_not_closed(self):
        middle = WriteMiddle(sessions='("sess1")')
        result = M.Package(middle).write(M.WriteRequest(**self.REQUEST))
        self.assertTrue(result.ok, result.error)
        self.assertFalse(any(call.startswith("maeCloseSession") for call in middle.calls))
        self.assertNotIn("close_session", [step["name"] for step in result.steps])

    def test_save_can_be_skipped(self):
        middle = WriteMiddle()
        result = M.Package(middle).write(M.WriteRequest(save=False, **self.REQUEST))
        self.assertTrue(result.ok, result.error)
        self.assertNotIn("save_setup", [step["name"] for step in result.steps])

    def test_command_failure_is_reported_with_op_name(self):
        middle = WriteMiddle()
        middle.fail_on = "maeSetHistoryLock"
        result = M.Package(middle).write(M.WriteRequest(
            token="t", library="LIB", cell="CELL", view="maestro",
            commands=[{"op": "lock", "history": "h1"}]))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "boom")

        silent = WriteMiddle()
        silent.fail_silently_on = "maeSetHistoryLock"
        silent_result = M.Package(silent).write(M.WriteRequest(
            token="t", library="LIB", cell="CELL", view="maestro",
            commands=[{"op": "lock", "history": "h1"}]))
        self.assertFalse(silent_result.ok)
        self.assertIn("command lock failed", silent_result.error)

    def test_invalid_command_stops_with_index(self):
        middle = WriteMiddle()
        result = M.Package(middle).write(M.WriteRequest(
            token="t", library="LIB", cell="CELL", view="maestro",
            commands=[{"op": "explode"}]))
        self.assertFalse(result.ok)
        self.assertIn("command 0 invalid", result.error)

    def test_load_corners_uploads_local_csv_first(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            csv = Path(tmp) / "corners.csv"
            csv.write_text("name,vdd\nnom,1.0\n", encoding="utf-8")
            middle = WriteMiddle()
            result = M.Package(middle).write(M.WriteRequest(
                token="t", library="LIB", cell="CELL", view="maestro",
                commands=[{"op": "load_corners", "local_path": str(csv),
                           "filepath": "ignored-by-design"}]))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(len(middle.uploads), 1)
        self.assertTrue(middle.uploads[0].endswith(".maestro-corners-" ) or
                        ".maestro-corners-" in middle.uploads[0])
        self.assertIn("upload_corners", [step["name"] for step in result.steps])


class ReadConfigMiddle(WriteMiddle):
    """按 SKILL 文本作答的假 middle，用来驱动 ``maestro.read_config`` 的全部读回分支。

    每条回答都是**真实 mae*/axl* 调用的返回形态**（list / alist / 文本块），
    这样 read_config 里的 `parse_sexpr` / `parse_skill_str_leaves` /
    `pairs_to_dict` / `decode_skill_text` 都走真实路径。
    """

    def __init__(self, *, setup: str | None = None, sessions: str = "nil") -> None:
        super().__init__(sessions=sessions)
        self.setup = setup or (
            '(("t1") ("c1") "vars" "params" "single" "local")'
        )

    def execute_skill(self, code, timeout=None, *, token):
        self.calls.append(code)
        if code.startswith("maeGetSessions"):
            return _ok(self.sessions_answer)
        if code.startswith("maeOpenSetup"):
            return _ok('"sess1"')
        if "list(maeGetSetup(" in code:
            return _ok(self.setup)
        if code.startswith("cadr(axlGetVars(axlGetTest("):
            return _ok('("tv1")')
        if code.startswith("cadr(axlGetVars(axlGetCorner("):
            return _ok('("cv1")')
        if code.startswith("cadr(axlGetVars("):
            return _ok('("v1" "v2")')
        if code.startswith("axlGetParameters(axlGetCorner("):
            return _ok('("LIB/CELL/maestro/c1/p2")')
        if code.startswith("axlGetParameters("):
            return _ok('("p1")')
        if "maeGetEnabledAnalysis(" in code:
            return _ok('(("t1" (("tran" (("stop" "10n"))))))')
        if code.startswith("maeGetEnvOption("):
            if "boom" in code:
                raise AssertionError("not used")
            return _ok('(("temp" "27"))')
        if code.startswith("maeGetSimOption("):
            return _ok('(("errpreset" "moderate"))')
        if "buildString(mapcar(lambda((o) sprintf" in code:
            # 字段序（见源码 sprintf）：name, type, signal, expression, plot,
            # save, evalType, yaxisUnit, spec
            return _ok('"TEST\\\\tt1\\\\n'
                       'OUT\\\\tVOUT\\\\toutput\\\\tVOUT\\\\tnil\\\\t1\\\\tnil'
                       '\\\\ttran\\\\tV\\\\tnil\\\\n"')
        # 注意：这些读回表达式外层常被 `let((s) s = ...)` 包住，只能用子串匹配
        if "maeGetVar(n ?typeName \"test\"" in code:
            return _ok('(("tv1" 5))')
        if "maeGetVar(n ?typeName \"corner\"" in code:
            return _ok('(("cv1" 7))')
        if "maeGetVar(n ?session" in code:
            return _ok('(("v1" 1) ("v2" 2))')
        if "maeGetParameter(" in code and '?typeName "corner"' in code:
            # 角参数值读的是**标量**（read_config 用 _skill_atom_value(unquote(...))）
            return _ok('"3"')
        if "maeGetParameter(n ?session" in code:
            return _ok('(("p1" "9"))')
        if "axlGetSpecData(" in code:
            return _ok('("min" 1)')
        if "axlGetCurrentHistory(" in code:
            return _ok('"h1"')
        if code.startswith("maeCloseSession"):
            return _ok("t")
        return _ok("nil")


def _ok(payload: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=payload)


class TestReadConfigOrchestration(unittest.TestCase):
    REQUEST = dict(token="t", library="LIB", cell="CELL", view="maestro")

    def _read(self, middle, **fields):
        return M.Package(middle).read_config(
            M.ReadConfigRequest(**{**self.REQUEST, **fields}))

    def test_all_sections_present(self):
        middle = ReadConfigMiddle()
        result = self._read(middle)
        self.assertTrue(result.ok, result.error)
        config = result.value
        self.assertEqual(config["tests"], ["t1"])
        self.assertEqual(config["corners"], ["c1"])
        # parse_sexpr 产出字符串原子：数值不会被隐式转换
        self.assertEqual(config["variables"], {"v1": "1", "v2": "2"})
        self.assertEqual(config["parameters"], {"p1": "9"})
        self.assertEqual(config["test_variables"], {"t1": {"tv1": "5"}})
        self.assertEqual(config["corner_variables"], {"c1": {"cv1": "7"}})
        self.assertEqual(config["corner_parameters"],
                         {"c1": {"LIB/CELL/maestro/c1/p2": 3}})   # 标量经 _skill_atom_value 转成 int
        self.assertEqual(config["analyses"], {"t1": {"tran": {"stop": "10n"}}})
        self.assertEqual(config["env_options"], {"t1": {"temp": "27"}})
        self.assertEqual(config["sim_options"], {"t1": {"errpreset": "moderate"}})
        self.assertEqual(config["outputs"]["t1"][0]["name"], "VOUT")
        self.assertEqual(config["outputs"]["t1"][0]["eval_type"], "tran")
        self.assertEqual(config["outputs"]["t1"][0]["yaxis_unit"], "V")
        self.assertEqual(config["specs"][0]["name"], "t1.VOUT")
        self.assertEqual(config["specs"][0]["type"], "min")
        self.assertEqual(config["specs"][0]["value"], "1")
        self.assertEqual(config["outputs"]["t1"][0]["spec"],
                         {"type": "min", "value": "1"})
        self.assertEqual(config["run_mode"], "single")
        self.assertEqual(config["job_control_mode"], "local")
        self.assertEqual(config["current_history"], "h1")
        self.assertNotIn("raw", config)

    def test_include_raw_adds_raw_section(self):
        middle = ReadConfigMiddle()
        result = self._read(middle, include_raw=True)
        self.assertTrue(result.ok, result.error)
        raw = result.value["raw"]
        # raw 存的是**读回内容**（不是表达式本身）
        self.assertEqual(raw["setup"],
                         '(("t1") ("c1") "vars" "params" "single" "local")')
        self.assertTrue(raw["outputs"].startswith('"TEST'))

    def test_include_parameters_false_skips_parameter_reads(self):
        middle = ReadConfigMiddle()
        result = self._read(middle, include_parameters=False)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["parameters"], {})
        # 现状（spec 未定义该开关语义）：include_parameters=False **只关掉全局那一支**，
        # 角参数值仍会读——按真实行为钉住，已记入报告 §3.1 观察项。
        params = [call for call in middle.calls if "maeGetParameter" in call]
        self.assertEqual(len(params), 1, params)
        self.assertIn('?typeName "corner"', params[0])

    def test_unparseable_setup_is_a_structured_failure(self):
        middle = ReadConfigMiddle(setup='("only-one")')
        result = self._read(middle)
        self.assertFalse(result.ok)
        self.assertIn("could not parse maeGetSetup readback", result.error)

    def test_existing_session_is_reused_and_not_closed(self):
        middle = ReadConfigMiddle(sessions='("sess1")')
        result = self._read(middle)
        self.assertTrue(result.ok, result.error)
        self.assertFalse(any(call.startswith("maeCloseSession")
                             for call in middle.calls))
        self.assertNotIn("close_session", [step["name"] for step in result.steps])

    def test_created_session_is_closed(self):
        middle = ReadConfigMiddle(sessions="nil")
        result = self._read(middle)
        self.assertTrue(result.ok, result.error)
        self.assertIn("close_session", [step["name"] for step in result.steps])

    def test_empty_tests_skip_analysis_output_and_spec_reads(self):
        middle = ReadConfigMiddle(setup='(nil ("c1") "vars" "params" "single" "local")')
        result = self._read(middle)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["tests"], [])
        self.assertEqual(result.value["analyses"], {})
        self.assertEqual(result.value["outputs"], {})
        self.assertEqual(result.value["specs"], [])
        self.assertFalse(any("maeGetEnabledAnalysis" in call for call in middle.calls))

    def test_step_names_are_stable(self):
        middle = ReadConfigMiddle()
        result = self._read(middle)
        names = [step["name"] for step in result.steps]
        for expected in ("open_session", "setup", "analyses", "options", "outputs",
                         "variables", "test_variables", "corner_variables",
                         "parameters", "corner_parameters", "specs"):
            self.assertIn(expected, names, names)


class HistoryMiddle(WriteMiddle):
    """驱动 ``maestro.write_history`` 的假 middle。

    * ``lock_flags`` —— ``maeGetHistoryLockFlag`` 的依次返回值（用完后重复最后一个）；
    * ``sdb_histories`` —— ``cadr(axlGetHistory(...))`` 的依次返回值（``None`` 表示 ``nil``）。

    这两个序列就是 write_history "改完必须验证" 逻辑的输入。
    """

    def __init__(self, *, lock_flags=(0,), sdb_histories=(None,),
                 sessions: str = "nil") -> None:
        super().__init__(sessions=sessions)
        self.lock_flags = list(lock_flags)
        self.sdb_histories = list(sdb_histories)

    def _next(self, seq: list, default):
        if not seq:
            return default
        return seq.pop(0) if len(seq) > 1 else seq[0]

    def execute_skill(self, code, timeout=None, *, token):
        self.calls.append(code)
        if "maeGetHistoryLockFlag(" in code:
            return _ok(f'"{self._next(self.lock_flags, 0)}"')
        if "cadr(axlGetHistory(" in code:
            names = self._next(self.sdb_histories, None)
            return _ok("nil" if names is None else "(" + " ".join(
                f'"{name}"' for name in names) + ")")
        if "maeDeleteExplorerHistory(" in code:
            return _ok("t")
        return super().execute_skill(code, timeout, token=token)


class TestWriteHistoryOrchestration(unittest.TestCase):
    REQUEST = dict(token="t", library="LIB", cell="CELL", view="maestro")

    def _write(self, middle, **cmd):
        return M.Package(middle).write_history(M.WriteHistoryRequest(
            **self.REQUEST, commands=[cmd]))

    def test_delete_happy_path_saves_and_verifies(self):
        middle = HistoryMiddle(sdb_histories=(None,))
        result = self._write(middle, op="delete", history="h1")
        self.assertTrue(result.ok, result.error)
        names = [step["name"] for step in result.steps]
        self.assertIn("history:delete", names)
        self.assertIn("save_setup", names)
        self.assertNotIn("delete_explorer", names)

    def test_delete_falls_back_to_explorer_when_still_in_sdb(self):
        # 第一次查还在 → 触发 maeDeleteExplorerHistory → 再查已删除
        middle = HistoryMiddle(sdb_histories=(["h1"], None))
        result = self._write(middle, op="delete", history="h1")
        self.assertTrue(result.ok, result.error)
        names = [step["name"] for step in result.steps]
        self.assertIn("delete_explorer", names)
        self.assertIn("save_setup_retry", names)
        self.assertTrue(any("maeDeleteExplorerHistory" in call for call in middle.calls))

    def test_delete_verification_failure_is_reported(self):
        middle = HistoryMiddle(sdb_histories=(["h1"],))
        result = self._write(middle, op="delete", history="h1")
        self.assertFalse(result.ok)
        self.assertIn("history delete verification failed", result.error)
        self.assertIn("still exists", result.error)

    def test_locked_history_refuses_delete_without_running_it(self):
        middle = HistoryMiddle(lock_flags=(1,))
        result = self._write(middle, op="delete", history="h1")
        self.assertFalse(result.ok)
        self.assertIn("is locked (flag=1)", result.error)
        self.assertFalse(any("axlGetHistoryEntry" in call for call in middle.calls))

    def test_rename_requires_new_name_visible(self):
        # rename 分支只查一次 sdb（查新名字是否可见），所以序列只给一项
        ok_middle = HistoryMiddle(sdb_histories=(["h2"],))
        good = self._write(ok_middle, op="rename", history="h1", new_name="h2")
        self.assertTrue(good.ok, good.error)
        self.assertIn("save_setup", [step["name"] for step in good.steps])

        bad_middle = HistoryMiddle(sdb_histories=(None,))
        bad = self._write(bad_middle, op="rename", history="h1", new_name="h2")
        self.assertFalse(bad.ok)
        self.assertIn("renamed history 'h2' is not visible", bad.error)

    def test_lock_and_unlock_verification(self):
        locked = self._write(HistoryMiddle(lock_flags=(1,)), op="lock", history="h1")
        self.assertTrue(locked.ok, locked.error)

        wrong_lock = self._write(HistoryMiddle(lock_flags=(0,)), op="lock", history="h1")
        self.assertFalse(wrong_lock.ok)
        self.assertIn("lock verification returned flag=0", wrong_lock.error)

        unlocked = self._write(HistoryMiddle(lock_flags=(0,)), op="unlock", history="h1")
        self.assertTrue(unlocked.ok, unlocked.error)

        stuck = self._write(HistoryMiddle(lock_flags=(1,)), op="unlock", history="h1")
        self.assertFalse(stuck.ok)
        self.assertIn("unlock verification still reports user lock", stuck.error)

    def test_invalid_command_and_empty_list(self):
        with self.assertRaises(ValueError):
            M.Package(HistoryMiddle()).write_history(M.WriteHistoryRequest(
                **self.REQUEST, commands=[]))
        bad = self._write(HistoryMiddle(), op="explode", history="h1")
        self.assertFalse(bad.ok)
        self.assertIn("command 0 invalid", bad.error)

    def test_command_failure_stops_before_verification(self):
        middle = HistoryMiddle()
        middle.fail_silently_on = "maeSetHistoryLock"
        result = self._write(middle, op="lock", history="h1")
        self.assertFalse(result.ok)
        self.assertIn("history lock failed", result.error)
        self.assertFalse(any("maeSaveSetup(" in call for call in middle.calls))


if __name__ == "__main__":
    unittest.main()
