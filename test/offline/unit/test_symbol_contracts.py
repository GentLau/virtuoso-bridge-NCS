"""L0 contracts for ``pyapi.packages.symbol`` (pure text layers + flow control).

``_parse_read`` 的输入样本取自 S11 真机 symbol 读取输出（tsmcN65 反相器），
保证解析器契约与真实 Cadence 文本一致，而不是自造格式。
"""
from __future__ import annotations

import unittest
from pathlib import Path
from unittest import mock

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import symbol as S


def balanced(text: str) -> bool:
    """引号外的圆括号是否配平（生成 SKILL 的语法底线）。"""
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


class FakeMiddle:
    def __init__(self, *results: VirtuosoResult) -> None:
        self.calls: list[tuple[str, str]] = []
        self.queue = list(results)
        self.default = VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append((token, skill_code))
        return self.queue.pop(0) if self.queue else self.default


def ok(output: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=output)


def fail(*errors: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=list(errors))


#: 真机样本（截取自 test/artifacts/env/scenario-project65/evidence-symbol-inv2.json）
REAL_READ = (
    '(("term" "VIN" "input" 1 ((-0.025 -0.025) (0.025 0.025)) ("none"))'
    ' ("term" "VOUT" "output" 1 ((1.725 -0.025) (1.775 0.025)) ("none"))'
    ' ("shape" "rect" "pin" "drawing" ((-0.025 -0.025) (0.025 0.025)) nil)'
    ' ("shape" "line" "device" "drawing" ((0.0 0.0) (0.25 0.0)) ((0.0 0.0) (0.25 0.0)))'
    ' ("label" "VIN" "normalLabel" (0.2875 0.0) "pin" "label" "centerLeft" "R0"'
    ' "stick" 0.0625 ((0.2875 -0.03125) (0.4375 0.03125)))'
    ' ("selectionBox" ((0.0 -0.25) (1.75 0.5)))'
    ' ("pinOrder" ("VOUT" "VDD" "VSS" "VIN"))'
    ' ("portOrder" nil)'
    ' ("termOrder" nil))'
)


class TestValidators(unittest.TestCase):
    def test_require_text(self):
        self.assertEqual(S._require_text("x", "n"), "x")
        for bad in ("", None, 5):
            with self.assertRaises(ValueError) as ctx:
                S._require_text(bad, "command.name")
            self.assertIn("command.name", str(ctx.exception))

    def test_require_timeout(self):
        S._require_timeout(None)
        S._require_timeout(2)
        for bad in (0, -3, "2"):
            with self.assertRaises(ValueError):
                S._require_timeout(bad)

    def test_require_bool(self):
        self.assertTrue(S._require_bool(True, "flag"))
        self.assertFalse(S._require_bool(False, "flag"))
        for bad in (1, 0, "true", None):
            with self.assertRaises(ValueError) as ctx:
                S._require_bool(bad, "flag")
            self.assertIn("flag", str(ctx.exception))

    def test_number_point_bbox_points(self):
        self.assertEqual(S._number(1.5, "n"), 1.5)
        with self.assertRaises(ValueError):
            S._number("1.5", "n")   # 只接受 int/float，字符串不隐式转换
        with self.assertRaises(ValueError):
            S._number(True, "n")    # bool 被显式排除
        self.assertEqual(S._point([1, 2]), (1.0, 2.0))
        with self.assertRaises(ValueError):
            S._point([1, 2, 3])
        self.assertEqual(S._bbox([0, 0, 1, 1]), (0.0, 0.0, 1.0, 1.0))
        with self.assertRaises(ValueError):
            S._bbox([0, 0, 1])
        with self.assertRaises(ValueError):
            S._bbox([1, 0, 0, 1])
        self.assertEqual(
            S._points([[0, 0], [1, 1]], "command.points"),
            [(0.0, 0.0), (1.0, 1.0)])
        with self.assertRaises(ValueError):
            S._points([[0, 0]], "command.points")


class TestLabelHelpers(unittest.TestCase):
    def test_label_choice_all_kinds_and_error(self):
        self.assertEqual(S._label_choice("pin_name"), ("pin name", "normalLabel"))
        self.assertEqual(S._label_choice("instance"), ("instance label", "NLPLabel"))
        self.assertEqual(S._label_choice("logical"), ("logical label", "NLPLabel"))
        # 注意：报错文案列了 "drawing"，但 drawing 实际不被接受（文案与实现不一致，
        # 已记入 audit 观察项）。这里按真实行为钉住。
        for bad in ("drawing", "nope"):
            with self.assertRaises(ValueError):
                S._label_choice(bad)

    def test_label_defaults_per_kind(self):
        self.assertEqual(S._label_defaults("instance")["justify"], "centerLeft")
        self.assertEqual(S._label_defaults("logical")["justify"], "centerCenter")
        self.assertEqual(S._label_defaults("pin_name")["justify"], "centerLeft")
        self.assertEqual(S._label_defaults("drawing")["justify"], "lowerLeft")

    def test_label_text_autofill_and_required(self):
        self.assertEqual(S._label_text("drawing", {"text": "A"}, required=True), "A")
        self.assertEqual(
            S._label_text("instance", {}, required=False), "[@instanceName]")
        self.assertEqual(S._label_text("logical", {}, required=False), "[@partName]")
        self.assertIsNone(S._label_text("drawing", {}, required=False))
        with self.assertRaises(ValueError):
            S._label_text("drawing", {}, required=True)

    def test_label_lpp(self):
        self.assertEqual(S._label_lpp("pin_name"), ("pin", "label"))
        self.assertEqual(S._label_lpp("instance"), ("instance", "label"))
        self.assertEqual(S._label_lpp("logical"), ("device", "label"))
        self.assertIsNone(S._label_lpp("drawing"))


class TestShapeMatch(unittest.TestCase):
    def test_shape_match_from_bbox_layer_purpose(self):
        expr = S._shape_match_expr("rect", {
            "layer": "M1", "purpose": "drawing", "bbox": [0, 0, 1, 1]})
        self.assertIn('x~>objType == "rect"', expr)
        self.assertIn('x~>layerName == "M1"', expr)
        self.assertIn('x~>purpose == "drawing"', expr)
        self.assertIn("x~>bBox", expr)

    def test_shape_match_from_points(self):
        expr = S._shape_match_expr("line", {"points": [[0, 0], [1, 1]]})
        self.assertIn('x~>objType == "line"', expr)

    def test_shape_match_requires_geometry(self):
        with self.assertRaises(ValueError):
            S._shape_match_expr("rect", {"layer": "M1"})

    def test_match_expressions(self):
        self.assertIn("x~>bBox", S._match_bbox_expr("x", (0, 0, 1, 1)))
        self.assertIn("x~>points", S._points_match_expr("x", [(0, 0), (1, 1)]))


class TestValueHelpers(unittest.TestCase):
    def test_scalar_coercions(self):
        self.assertEqual(S._s(None), "")
        self.assertEqual(S._s(7), "7")
        self.assertEqual(S._i("5", 0), 5)
        self.assertEqual(S._i("bad", 3), 3)
        self.assertEqual(S._f("2.5"), 2.5)
        self.assertEqual(S._f(None), 0.0)

    def test_point_bbox_points_values(self):
        self.assertEqual(S._point_value([1, 2]), [1.0, 2.0])
        self.assertIsNone(S._point_value([1]))
        self.assertEqual(S._bbox_value([[0, 0], [1, 1]]), [[0.0, 0.0], [1.0, 1.0]])
        self.assertIsNone(S._bbox_value([[0, 0], [1]]))
        self.assertIsNone(S._bbox_value("nope"))
        self.assertEqual(S._points_value([[0, 0], [1, 1]]), [[0.0, 0.0], [1.0, 1.0]])
        self.assertIsNone(S._points_value("nope"))
        self.assertEqual(S._points_value([[0, 0], None]), [[0.0, 0.0]])

    def test_safe_name(self):
        self.assertEqual(S._safe_name("a/b c"), "a_b_c")
        self.assertEqual(S._safe_name("///"), "cell")


class TestParseRead(unittest.TestCase):
    def setUp(self):
        self.parsed = S._parse_read(REAL_READ)

    def test_terms(self):
        self.assertEqual(self.parsed["terms"][0]["name"], "VIN")
        self.assertEqual(self.parsed["terms"][0]["direction"], "input")
        self.assertEqual(self.parsed["terms"][0]["num_bits"], 1)
        self.assertEqual(self.parsed["terms"][0]["access_dir"], ["none"])
        self.assertEqual(self.parsed["terms"][1]["bbox"][1], [1.775, 0.025])

    def test_shapes_labels_orders(self):
        self.assertEqual(self.parsed["shapes"][0]["kind"], "rect")
        self.assertEqual(self.parsed["shapes"][1]["points"], [[0.0, 0.0], [0.25, 0.0]])
        self.assertEqual(self.parsed["labels"][0]["text"], "VIN")
        self.assertEqual(self.parsed["labels"][0]["height"], 0.0625)
        self.assertEqual(self.parsed["selection_boxes"], [[[0.0, -0.25], [1.75, 0.5]]])
        self.assertEqual(self.parsed["pin_order"], ["VOUT", "VDD", "VSS", "VIN"])
        self.assertEqual(self.parsed["port_order"], [])

    def test_non_list_and_junk_records_are_tolerated(self):
        empty = S._parse_read("nil")
        self.assertEqual(empty["terms"], [])
        parsed = S._parse_read('(("junk") (42) ("term" "A" "input" 1 ((0 0) (1 1))))')
        self.assertEqual([t["name"] for t in parsed["terms"]], ["A"])


class TestPackageFlows(unittest.TestCase):
    def _pkg(self, *results):
        return S.Package(FakeMiddle(*results))

    def test_read_ok_and_failure(self):
        good = self._pkg(ok(REAL_READ)).read(
            S.ReadRequest(token="t", library="L", cell="C"))
        self.assertTrue(good.ok, good.error)
        self.assertEqual(good.value["terms"][0]["name"], "VIN")

        bad = self._pkg(fail("boom")).read(
            S.ReadRequest(token="t", library="L", cell="C"))
        self.assertFalse(bad.ok)
        self.assertIn("boom", bad.error)

    def test_read_rejects_bad_focus(self):
        pkg = self._pkg(ok("nil"))
        with self.assertRaises(ValueError):
            pkg.read(S.ReadRequest(token="t", library="L", cell="C", focus=[]))
        with self.assertRaises(ValueError):
            pkg.read(S.ReadRequest(token="t", library="L", cell="C", focus=["nope"]))

    def test_write_validates_commands_and_open(self):
        with self.assertRaises(ValueError):
            self._pkg().write(S.WriteRequest(token="t", library="L", cell="C", commands=[]))

        pkg = self._pkg(ok('"ok"'))
        bad_cmd = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C", commands=["not-a-dict"]))
        self.assertFalse(bad_cmd.ok)
        self.assertIn("must be an object with op", bad_cmd.error)

        pkg = self._pkg(fail("cannot open"))
        opened = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "delete_shape", "kind": "rect", "bbox": [0, 0, 1, 1]}]))
        self.assertFalse(opened.ok)
        self.assertIn("cannot open", opened.error)

    def test_write_reports_bad_atom_and_command_failure(self):
        pkg = self._pkg(ok('"ok"'))
        unknown = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C", commands=[{"op": "explode"}]))
        self.assertFalse(unknown.ok)
        self.assertIn("command 0 invalid", unknown.error)

        pkg = self._pkg(ok('"ok"'), ok('"open-ok"'), fail("shape not found"))
        failed = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "delete_shape", "kind": "rect", "bbox": [0, 0, 1, 1]}]))
        self.assertFalse(failed.ok)
        self.assertIn("shape not found", failed.error)
        self.assertIn("not transactional", failed.error)

        pkg = self._pkg(ok('"ok"'), ok('"locked"'))
        locked = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "delete_shape", "kind": "rect", "bbox": [0, 0, 1, 1]}]))
        self.assertFalse(locked.ok)
        self.assertIn("locked by another session", locked.error)

    def test_write_reports_view_probe_results(self):
        missing = self._pkg(ok("missing")).write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "delete_shape", "kind": "rect", "bbox": [0, 0, 1, 1]}]))
        self.assertFalse(missing.ok)
        self.assertIn("not found", missing.error)

        mismatch = self._pkg(ok("mismatch")).write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "delete_shape", "kind": "rect", "bbox": [0, 0, 1, 1]}]))
        self.assertFalse(mismatch.ok)
        self.assertIn("view type", mismatch.error)

        weird = self._pkg(ok("banana")).write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "delete_shape", "kind": "rect", "bbox": [0, 0, 1, 1]}]))
        self.assertFalse(weird.ok)
        self.assertIn("unexpected view probe", weird.error)

    def test_write_happy_path_reports_applied_count(self):
        pkg = self._pkg(ok('"ok"'), ok('"open-ok"'), ok("db:1"), ok('"saved"'))
        result = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "delete_shape", "kind": "rect", "bbox": [0, 0, 1, 1]}]))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value, {"applied": 1})
        names = [step["name"] for step in result.steps]
        self.assertEqual(names, ["view_exists", "open", "command:delete_shape", "check_and_save"])
        codes = [code for _token, code in pkg.middle.calls]
        self.assertNotIn("dbOpenCellViewByType", codes[2])
        self.assertIn("dbClose(vbSymCv)", codes[3])

    def test_check_and_save_probe_and_result(self):
        good = self._pkg(ok('"ok"'), ok('"open-ok"'), ok('"saved"')).check_and_save(
            S.CheckSaveRequest(token="t", library="L", cell="C"))
        self.assertTrue(good.ok, good.error)
        self.assertEqual(good.value, {"saved": True})

        bad = self._pkg(ok('"ok"'), ok('"open-ok"'), fail("pin-list generation failed")).check_and_save(
            S.CheckSaveRequest(token="t", library="L", cell="C"))
        self.assertFalse(bad.ok)
        self.assertIn("pin-list", bad.error)


class ScriptedMiddle:
    """按顺序作答的假 middle（symbol.read / symbol.generate 各一次 skill 调用）。"""

    def __init__(self, *outputs: str, ok: bool = True) -> None:
        self.outputs = list(outputs)
        self.ok = ok
        self.calls: list[str] = []

    def execute_skill(self, code, timeout=None, *, token):
        self.calls.append(code)
        if not self.ok:
            return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=["skill boom"])
        payload = self.outputs.pop(0) if self.outputs else "nil"
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=payload)


class TestSymbolReadOrchestration(unittest.TestCase):
    def test_read_returns_all_sections_and_identity(self):
        middle = ScriptedMiddle(REAL_READ)
        result = S.Package(middle).read(S.ReadRequest(token="t", library="LIB", cell="CELL"))
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["terms"][0]["name"], "VIN")
        self.assertEqual(value["shapes"][0]["kind"], "rect")
        self.assertEqual(value["pin_order"], ["VOUT", "VDD", "VSS", "VIN"])
        self.assertEqual(value["library"], "LIB")
        self.assertEqual(value["cell"], "CELL")
        self.assertEqual(value["view"], "symbol")
        self.assertEqual(value["view_type"], "schematicSymbol")

    def test_focus_limits_sections_but_keeps_identity(self):
        result = S.Package(ScriptedMiddle(REAL_READ)).read(
            S.ReadRequest(token="t", library="LIB", cell="CELL", focus=["terms", "orders"]))
        value = result.value
        self.assertEqual(sorted(k for k in value if k not in
                                ("library", "cell", "view", "view_type")),
                         ["pin_order", "port_order", "term_order", "terms"])
        self.assertEqual(value["port_order"], [])

    def test_malformed_output_is_rejected(self):
        result = S.Package(ScriptedMiddle("(a)(b)")).read(
            S.ReadRequest(token="t", library="LIB", cell="CELL"))
        self.assertFalse(result.ok)
        self.assertIn("not a single complete SKILL list", result.error)

    def test_skill_failure_is_reported(self):
        result = S.Package(ScriptedMiddle(ok=False)).read(
            S.ReadRequest(token="t", library="LIB", cell="CELL"))
        self.assertFalse(result.ok)
        self.assertIn("skill boom", result.error)


class TestSymbolGenerateOrchestration(unittest.TestCase):
    CREATED = ('("generated" "created" (("A" "input" 1) ("Y" "output" 1)) ("A" "Y"))')
    REPLACED = ('("generated" "replaced" (("A" "input" 1)) ("A"))')

    def _generate(self, middle, **fields):
        fields.setdefault("token", "t")
        fields.setdefault("library", "LIB")
        fields.setdefault("cell", "CELL")
        return S.Package(middle).generate(S.GenerateRequest(**fields))

    def test_created_symbol_reports_terms_and_order(self):
        result = self._generate(ScriptedMiddle(self.CREATED))
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["action"], "created")
        self.assertEqual(sorted(value["terminal_names"]), ["A", "Y"])
        self.assertEqual(tuple(value["pin_order"]), ("A", "Y"))
        self.assertEqual(value["schematic_view"], "schematic")
        self.assertEqual(value["symbol_view"], "symbol")

    def test_replaced_symbol(self):
        result = self._generate(ScriptedMiddle(self.REPLACED), overwrite=True)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["action"], "replaced")
        self.assertEqual(result.value["terminal_names"], ["A"])

    def test_pin_order_mismatch_is_rejected(self):
        payload = '("generated" "created" (("A" "input" 1) ("Y" "output" 1)) ("A"))'
        result = self._generate(ScriptedMiddle(payload))
        self.assertFalse(result.ok)
        self.assertIn("pin order mismatch", result.error)

    def test_failure_payloads(self):
        body = self._generate(ScriptedMiddle('("failed" "body boom" nil)'))
        self.assertFalse(body.ok)
        self.assertIn("symbol generation failed: body boom", body.error)

        with_cleanup = self._generate(
            ScriptedMiddle('("failed" "body boom" ("rollback failed"))'))
        self.assertFalse(with_cleanup.ok)
        self.assertIn("cleanup failed: rollback failed", with_cleanup.error)

        cleanup_only = self._generate(
            ScriptedMiddle('("failed" nil ("backup retained"))'))
        self.assertFalse(cleanup_only.ok)
        self.assertIn("symbol generation cleanup failed: backup retained",
                      cleanup_only.error)

        no_detail = self._generate(ScriptedMiddle('("failed" nil nil)'))
        self.assertFalse(no_detail.ok)
        self.assertIn("failed without details", no_detail.error)

    def test_unexpected_outputs_are_rejected(self):
        for payload, needle in (
            ('("nope" "created" nil ("A"))', "unexpected symbol generation output"),
            ('("generated" "sideways" nil ("A"))', "unexpected symbol generation action"),
            ('("generated" "created" "bad" ("A"))', "unexpected final terminal payload"),
            ('("generated" "created" (("A")) ("A"))', "unexpected final terminal record"),
            ('"not-a-list"', "must be a single complete SKILL list"),
        ):
            result = self._generate(ScriptedMiddle(payload))
            self.assertFalse(result.ok, payload)
            self.assertIn(needle, result.error, payload)

    def test_skill_failure_and_argument_validation(self):
        failed = self._generate(ScriptedMiddle(ok=False))
        self.assertFalse(failed.ok)
        self.assertIn("skill boom", failed.error)

        with self.assertRaises(ValueError):
            self._generate(ScriptedMiddle(self.CREATED),
                           schematic_view="same", symbol_view="same")
        with self.assertRaises(ValueError):
            self._generate(ScriptedMiddle(self.CREATED), sort_pins="fancy")
        with self.assertRaises(ValueError):
            self._generate(ScriptedMiddle(self.CREATED), overwrite="yes")
        with self.assertRaises(ValueError):
            self._generate(ScriptedMiddle(self.CREATED), timeout=0)


class ScreenshotMiddle:
    """symbol.screenshot 的假 middle（与 layout.screenshot 同形的四步流程）。"""

    def __init__(self, *, mkdir_rc: int = 0, capture_ok: bool = True,
                 verify_stdout: str = "2048", verify_rc: int = 0,
                 download_rc: int = 0) -> None:
        self.mkdir_rc = mkdir_rc
        self.capture_ok = capture_ok
        self.verify_stdout = verify_stdout
        self.verify_rc = verify_rc
        self.download_rc = download_rc
        self.commands: list[str] = []

    def query(self, *, token, role=None, name=None):
        class _Status:
            value = "success"

        class _Role:
            root = "/role/daemon"

        class _Facts:
            status = _Status()
            roles = {"daemon": _Role()}

        return _Facts()

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        from pyapi.models import CommandResult
        self.commands.append(cmd)
        if cmd.startswith("mkdir -p"):
            return CommandResult(self.mkdir_rc, "", "" if self.mkdir_rc == 0 else "mkdir boom")
        if "wc -c" in cmd:
            return CommandResult(self.verify_rc, f"{self.verify_stdout}\n", "")
        return CommandResult(0, "", "")

    def execute_skill(self, code, timeout=None, *, token):
        if not self.capture_ok:
            return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=["capture boom"])
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        from pyapi.models import CommandResult
        if self.download_rc != 0:
            return CommandResult(self.download_rc, "", "download boom")
        target = Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"PNG")
        return CommandResult(0, str(target), "")


class TestSymbolScreenshot(unittest.TestCase):
    def _shot(self, middle, tmp_root: str, **fields):
        fields.setdefault("token", "t")
        fields.setdefault("library", "LIB")
        fields.setdefault("cell", "CELL")
        with mock.patch.object(S, "artifact_dir", lambda: Path(tmp_root) / "artifact"):
            return S.Package(middle).screenshot(S.ScreenshotRequest(**fields))

    def test_happy_path_and_cleanup(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = ScreenshotMiddle()
            result = self._shot(middle, tmp)
            self.assertTrue(result.ok, result.error)
            local = Path(result.value["local_path"])
            self.assertTrue(local.exists())
            # symbol.screenshot 与 layout 不同：**没有** verify 步（mkdir→capture→download）
            self.assertEqual([step["name"] for step in result.steps],
                             ["mkdir", "capture", "download"])
            self.assertTrue(any(c.startswith("rm -f") for c in middle.commands))

    def test_failure_paths(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            cases = (
                (ScreenshotMiddle(mkdir_rc=1), "mkdir boom"),
                (ScreenshotMiddle(capture_ok=False), "capture boom"),
                (ScreenshotMiddle(download_rc=1), "download boom"),
            )
            for middle, needle in cases:
                result = self._shot(middle, tmp)
                self.assertFalse(result.ok, needle)
                self.assertIn(needle, result.error, needle)

    def test_argument_validation(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            with self.assertRaises(ValueError):
                self._shot(ScreenshotMiddle(), tmp, region=[0, 0])
            with self.assertRaises(ValueError):
                self._shot(ScreenshotMiddle(), tmp, toplevel=1)
            with self.assertRaises(ValueError):
                self._shot(ScreenshotMiddle(), tmp, leave_open="no")


#: op → 最小合法命令（取自带 op_list 抽取 + 人工补字段）
ATOM_COMMANDS: dict[str, dict] = {
    "place_line": {"layer": "device", "purpose": "drawing",
                   "points": [[0, 0], [1, 1]]},
    "place_polygon": {"layer": "device", "purpose": "drawing",
                      "points": [[0, 0], [1, 0], [0, 1]]},
    "place_rect": {"layer": "device", "purpose": "drawing", "bbox": [0, 0, 1, 1]},
    "place_ellipse": {"layer": "device", "purpose": "drawing", "bbox": [0, 0, 1, 1]},
    "delete_shape": {"kind": "rect", "bbox": [0, 0, 1, 1]},
    "set_shape_properties": {"kind": "rect", "bbox": [0, 0, 1, 1],
                             "new_bbox": [0, 0, 2, 2]},
    "place_label": {"label_kind": "drawing", "text": "A", "x": 0, "y": 0,
                    "layer": "text", "purpose": "drawing"},
    "delete_label": {"label_kind": "drawing", "x": 0, "y": 0},
    "rename_label": {"label_kind": "drawing", "x": 0, "y": 0, "new_text": "B"},
    "set_label_properties": {"label_kind": "drawing", "x": 0, "y": 0,
                             "justify": "lowerLeft"},
    "place_pin": {"name": "A", "direction": "input", "x": 0, "y": 0},
    "delete_pin": {"name": "A"},
    "rename_pin": {"name": "A", "new_name": "B"},
    "set_pin_properties": {"name": "A", "direction": "output"},
    "set_selection_box": {"bbox": [0, 0, 1, 1]},
    "set_pin_order": {"term_names": ["A", "B"]},
}


class TestSymbolExpressionHelpers(unittest.TestCase):
    def test_lpp_point_points_bbox_expressions(self):
        self.assertEqual(S._lpp_expr("M1", "drawing"), 'list("M1" "drawing")')
        self.assertEqual(S._point_expr((1.5, 2.0)), "list(1.5 2)")
        self.assertEqual(S._points_expr([(0, 0), (1, 1)]), "list(list(0 0) list(1 1))")
        self.assertEqual(S._bbox_expr((0, 0, 1, 1)), "list(list(0 0) list(1 1))")

    def test_label_xy_from_xy_or_x_y(self):
        self.assertEqual(S._label_xy({"xy": [1, 2]}), (1.0, 2.0))
        self.assertEqual(S._label_xy({"x": 3, "y": 4}), (3.0, 4.0))
        with self.assertRaises(ValueError):
            S._label_xy({"x": 3})

    def test_label_match_expr_per_kind(self):
        pin = S._label_match_expr("pin_name", {"x": 0, "y": 0, "text": "A"})
        self.assertIn('x~>layerName == "pin"', pin)
        self.assertIn('x~>theLabel == "A"', pin)

        inst = S._label_match_expr("instance", {"x": 0, "y": 0})
        self.assertIn('x~>layerName == "instance"', inst)
        self.assertIn('x~>theLabel == "[@instanceName]"', inst)   # 自动补文案

        drawing = S._label_match_expr("drawing", {"x": 0, "y": 0, "layer": "text",
                                                  "purpose": "drawing"})
        self.assertIn('x~>layerName == "text"', drawing)
        self.assertIn('x~>purpose == "drawing"', drawing)
        # labelType 只在**没给 layer** 时兜底（elif 链），这里分开钉
        no_layer = S._label_match_expr("drawing", {"x": 0, "y": 0})
        self.assertIn('x~>labelType == "normalLabel"', no_layer)

    def test_pin_match_and_shape_match_with_points(self):
        self.assertIn('x~>purpose == "label"',
                      S._pin_match_expr("A"))
        with_points = S._shape_match_expr("line", {"points": [[0, 0], [1, 1]]})
        self.assertIn('x~>objType == "line"', with_points)
        self.assertIn("x~>points", with_points)


class TestSymbolAtomicMatrix(unittest.TestCase):
    def _expr(self, op: str, **extra) -> str:
        command = {"op": op, **ATOM_COMMANDS[op], **extra}
        return S.Package(FakeMiddle())._atomic_expr(command)

    def test_every_op_builds_balanced_skill(self):
        for op in ATOM_COMMANDS:
            with self.subTest(op=op):
                expr = self._expr(op)
                self.assertTrue(expr.strip(), op)
                self.assertTrue(balanced(expr), f"{op}: {expr[:120]}")

    def test_expected_cadence_calls(self):
        for op, needle in (
            ("place_line", "dbCreateLine"),
            ("place_polygon", "dbCreatePolygon"),
            ("place_rect", "dbCreateRect"),
            ("place_ellipse", "dbCreateEllipse"),
            ("place_label", "dbCreateLabel"),
            ("delete_shape", "dbDeleteObject"),
            ("place_pin", "dbCreateTerm"),
            ("delete_pin", "dbDeleteObject"),
            ("rename_pin", "dbRenameNet"),
        ):
            with self.subTest(op=op):
                self.assertIn(needle, self._expr(op))

    def test_unknown_op_and_shape_guards(self):
        with self.assertRaises(ValueError) as ctx:
            S.Package(FakeMiddle())._atomic_expr({"op": "explode"})
        self.assertIn("unknown atomic op", str(ctx.exception))
        with self.assertRaises(ValueError):
            S.Package(FakeMiddle())._atomic_expr({"op": ""})
        with self.assertRaises(ValueError):
            self._expr("set_shape_properties", new_bbox=[0, 0, 1, 1], kind="line",
                       points=[[0, 0], [1, 1]])
        with self.assertRaises(ValueError):
            S.Package(FakeMiddle())._atomic_expr(
                {"op": "set_shape_properties", "kind": "rect", "bbox": [0, 0, 1, 1]})

    def test_rename_and_property_guards(self):
        with self.assertRaises(ValueError):
            self._expr("rename_pin", new_name="")
        with self.assertRaises(ValueError):
            self._expr("rename_label", new_text="")


if __name__ == "__main__":
    unittest.main()
