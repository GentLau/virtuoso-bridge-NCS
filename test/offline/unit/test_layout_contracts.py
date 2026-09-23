"""L0 contracts for ``pyapi.packages.layout`` 的坐标/几何校验与原子命令构造。

layout 包的每次真机调用都要先经过这层"把请求翻成 SKILL"的纯函数；
真机 TB 只验证了少数几条 happy path，这里把校验分支与全部原子 op 钉死。
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import layout as L


class FakeMiddle:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append(skill_code)
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='("ok")')


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


#: op → 最小合法命令
COMMANDS: dict[str, dict] = {
    "place_rect": {"layer": "M1", "purpose": "drawing", "bbox": [0, 0, 1, 1]},
    "place_polygon": {"layer": "M1", "purpose": "drawing",
                      "points": [[0, 0], [1, 0], [0, 1]]},
    "place_path": {"layer": "M1", "purpose": "drawing", "points": [[0, 0], [1, 1]],
                   "width": 0.1},
    "place_line": {"layer": "M1", "purpose": "drawing", "points": [[0, 0], [1, 1]]},
    "place_label": {"layer": "text", "purpose": "drawing", "xy": [0, 0], "text": "A"},
    "delete_shape": {"kind": "rect", "bbox": [0, 0, 1, 1]},
    "set_shape_properties": {"kind": "rect", "bbox": [0, 0, 1, 1],
                             "new_bbox": [0, 0, 2, 2]},
    "delete_shapes_on_layer": {"layer": "M1", "purpose": "drawing"},
    "delete_label": {"xy": [0, 0]},
    "rename_label": {"xy": [0, 0], "new_text": "B"},
    "set_label_properties": {"xy": [0, 0], "new_height": 0.2},
    "place_instance": {"master_lib": "L", "master_cell": "C", "name": "I1", "xy": [0, 0]},
    "delete_instance": {"name": "I1"},
    "rename_instance": {"name": "I1", "new_name": "I2"},
    "set_instance_properties": {"name": "I1", "new_xy": [1, 1]},
    "place_mosaic": {"master_lib": "L", "master_cell": "C", "name": "I3", "xy": [0, 0],
                     "rows": 2, "cols": 2, "row_pitch": 1.0, "col_pitch": 1.0},
    "delete_mosaic": {"name": "I3"},
    "place_via": {"via_name": "V1", "xy": [0, 0]},
    "delete_via": {"xy": [0, 0]},
}


class TestCoordinateHelpers(unittest.TestCase):
    def test_require_text_timeout_bool(self):
        self.assertEqual(L._require_text("x", "n"), "x")
        for bad in ("", None, 1):
            with self.assertRaises(ValueError) as ctx:
                L._require_text(bad, "command.layer")
            self.assertIn("command.layer", str(ctx.exception))
        L._require_timeout(None)
        L._require_timeout(1)
        for bad in (0, -1, "1"):
            with self.assertRaises(ValueError):
                L._require_timeout(bad)
        self.assertTrue(L._require_bool(True, "strict_lpp"))
        for bad in (1, "yes", None):
            with self.assertRaises(ValueError) as ctx:
                L._require_bool(bad, "strict_lpp")
            self.assertIn("strict_lpp", str(ctx.exception))

    def test_number_point_bbox(self):
        self.assertEqual(L._number(1.5, "n"), 1.5)
        self.assertEqual(L._number(2, "n"), 2.0)
        for bad in ("1.5", True, None):
            with self.assertRaises(ValueError):
                L._number(bad, "command.width")
        self.assertEqual(L._point([1, 2]), (1.0, 2.0))
        for bad in ([1], [1, 2, 3], "x", None):
            with self.assertRaises(ValueError):
                L._point(bad, "command.xy")
        self.assertEqual(L._bbox([0, 0, 1, 1]), (0.0, 0.0, 1.0, 1.0))
        with self.assertRaises(ValueError):
            L._bbox([0, 0, 1])
        with self.assertRaises(ValueError) as ctx:
            L._bbox([1, 0, 0, 1])
        self.assertIn("x0 < x1", str(ctx.exception))

    def test_points_and_bbox_from_points(self):
        self.assertEqual(L._points([[0, 0], [1, 1]], "p"), [(0.0, 0.0), (1.0, 1.0)])
        with self.assertRaises(ValueError) as ctx:
            L._points([[0, 0]], "command.points", minimum=3)
        self.assertIn("at least 3", str(ctx.exception))
        self.assertEqual(L._bbox_from_points([(1, 2), (3, 0)]), (1.0, 0.0, 3.0, 2.0))

    def test_lpp_and_expressions(self):
        self.assertEqual(L._lpp("M1", "drawing"), ("M1", "drawing"))
        with self.assertRaises(ValueError):
            L._lpp("", "drawing")
        self.assertIn("M1", L._lpp_expr("M1", "drawing"))
        # 点是 SKILL 列表形态 list(x y)，不是 x:y
        self.assertEqual(L._point_expr((1.5, 2.0)), "list(1.5 2)")
        self.assertIn("list(", L._points_expr([(0, 0), (1, 1)]))
        self.assertIn("list(", L._bbox_expr((0, 0, 1, 1)))

    def test_scalar_coercions(self):
        self.assertEqual(L._s(None), "")
        self.assertEqual(L._s(3), "3")
        self.assertEqual(L._f("2.5"), 2.5)
        self.assertEqual(L._f(None), 0.0)
        self.assertEqual(L._i("4", 0), 4)
        self.assertEqual(L._i("bad", 7), 7)
        self.assertEqual(L._safe_name("a/b c"), "a_b_c")
        self.assertEqual(L._safe_name(""), "layout")

    def test_value_extractors(self):
        self.assertEqual(L._point_value([1, 2]), [1.0, 2.0])
        self.assertIsNone(L._point_value([1]))
        self.assertEqual(L._bbox_value([[0, 0], [1, 1]]), [[0.0, 0.0], [1.0, 1.0]])
        self.assertIsNone(L._bbox_value([[0, 0]]))
        self.assertEqual(L._points_value([[0, 0], [1, 1]]), [[0.0, 0.0], [1.0, 1.0]])
        self.assertIsNone(L._points_value("x"))


class TestAtomicMatrix(unittest.TestCase):
    def _raw(self, command: dict) -> str:
        """直接给完整命令（不经 COMMANDS 表），用于精确打到某个校验分支。"""
        return L.Package(FakeMiddle())._atomic_expr(command)

    def _expr(self, op: str, **extra) -> str:
        command = {"op": op, **COMMANDS[op], **extra}
        return L.Package(FakeMiddle())._atomic_expr(command)

    def test_every_atomic_op_builds_balanced_skill(self):
        for op in COMMANDS:
            with self.subTest(op=op):
                expr = self._expr(op)
                self.assertTrue(expr.strip(), f"{op} produced empty expression")
                self.assertTrue(balanced(expr), f"{op}: unbalanced {expr[:120]}")

    def test_expected_cadence_calls(self):
        for op, needle in (
            ("place_rect", "dbCreateRect"),
            ("place_polygon", "dbCreatePolygon"),
            ("place_path", "dbCreatePath"),
            ("place_line", "dbCreateLine"),
            ("place_label", "dbCreateLabel"),
            ("place_instance", "dbCreateInstByMasterName"),
            ("place_mosaic", "dbCreateSimpleMosaic"),
            ("place_via", "dbCreateVia"),
            ("delete_via", "dbDeleteObject"),
            ("delete_shapes_on_layer", "dbDeleteObject"),
        ):
            with self.subTest(op=op):
                self.assertIn(needle, self._expr(op))

    def test_unknown_op_is_rejected(self):
        with self.assertRaises(ValueError) as ctx:
            L.Package(FakeMiddle())._atomic_expr({"op": "explode"})
        self.assertIn("unknown atomic op", str(ctx.exception))
        with self.assertRaises(ValueError):
            L.Package(FakeMiddle())._atomic_expr({})
        with self.assertRaises(ValueError):
            L.Package(FakeMiddle())._atomic_expr({"op": ""})

    def test_place_line_point_count_and_path_width(self):
        with self.assertRaises(ValueError) as ctx:
            self._expr("place_line", points=[[0, 0], [1, 0], [2, 0]])
        self.assertIn("exactly 2 points", str(ctx.exception))
        with self.assertRaises(ValueError):
            self._expr("place_path", width=0)
        with self.assertRaises(ValueError):
            self._expr("place_path", style="nonsense")
        self.assertIn("squareFlush", self._expr("place_path", style="squareFlush"))

    def test_shape_mutation_guards(self):
        with self.assertRaises(ValueError) as ctx:
            self._raw({"op": "set_shape_properties", "kind": "path",
                       "points": [[0, 0], [1, 0]], "new_bbox": [0, 0, 1, 1]})
        self.assertIn("rect/ellipse", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self._raw({"op": "set_shape_properties", "kind": "polygon",
                       "points": [[0, 0], [1, 0], [0, 1]], "new_width": 1})
        self.assertIn("path", str(ctx.exception))
        with self.assertRaises(ValueError) as ctx:
            self._raw({"op": "set_shape_properties", "kind": "rect", "bbox": [0, 0, 1, 1]})
        self.assertIn("at least one new_*", str(ctx.exception))
        with self.assertRaises(ValueError):
            self._expr("delete_shape", kind="nonsense")
        self.assertIn("foreach", self._expr("delete_shape", all=True))

    def test_label_and_instance_property_guards(self):
        with self.assertRaises(ValueError) as ctx:
            self._raw({"op": "set_label_properties", "xy": [0, 0]})
        self.assertIn("at least one new_*", str(ctx.exception))
        with self.assertRaises(ValueError):
            self._expr("rename_label", new_text="")
        with self.assertRaises(ValueError):
            self._raw({"op": "set_instance_properties", "name": "I1"})
        with self.assertRaises(ValueError):
            self._expr("rename_instance", new_name="")
        with self.assertRaises(ValueError):
            self._expr("place_instance", master_lib="")
        with self.assertRaises(ValueError) as ctx:
            self._expr("place_mosaic", rows=0)
        self.assertIn("rows/cols", str(ctx.exception))
        with self.assertRaises(ValueError):
            self._expr("place_via", via_name="")

    def test_delete_shapes_on_layer_types_validation(self):
        with self.assertRaises(ValueError) as ctx:
            self._expr("delete_shapes_on_layer", types=[])
        self.assertIn("non-empty list", str(ctx.exception))
        expr = self._expr("delete_shapes_on_layer", types=["rect", "path"])
        self.assertIn('objType == "rect"', expr)
        self.assertIn('objType == "path"', expr)

    def test_instance_count_and_orientation(self):
        expr = self._expr("place_instance", num_inst=3, orient="R90")
        self.assertIn('"R90"', expr)
        self.assertIn(" 3)", expr)
        with self.assertRaises(ValueError) as ctx:
            self._expr("place_instance", num_inst=0)
        self.assertIn("num_inst", str(ctx.exception))


class TestWriteRequestGuards(unittest.TestCase):
    def _pkg(self):
        return L.Package(FakeMiddle())

    def test_write_rejects_empty_commands(self):
        with self.assertRaises(ValueError) as ctx:
            self._pkg().write(L.WriteRequest(token="t", library="L", cell="C", commands=[]))
        self.assertIn("non-empty list", str(ctx.exception))

    def test_read_validates_filters(self):
        pkg = self._pkg()
        with self.assertRaises(ValueError) as ctx:
            pkg.read(L.ReadRequest(token="t", library="L", cell="C", focus=[]))
        self.assertIn("focus", str(ctx.exception))
        with self.assertRaises(ValueError):
            pkg.read(L.ReadRequest(token="t", library="L", cell="C", focus=["nope"]))
        with self.assertRaises(ValueError):
            pkg.read(L.ReadRequest(token="t", library="L", cell="C", detail="wrong"))
        with self.assertRaises(ValueError):
            pkg.read(L.ReadRequest(token="t", library="L", cell="C", region_mode="wrong"))
        with self.assertRaises(ValueError):
            pkg.read(L.ReadRequest(token="t", library="L", cell="C", depth=-1))
        with self.assertRaises(ValueError) as ctx:
            pkg.read(L.ReadRequest(token="t", library="L", cell="C", depth=1))
        self.assertIn("layers", str(ctx.exception))
        with self.assertRaises(ValueError):
            pkg.read(L.ReadRequest(token="t", library="L", cell="C", object_filter="x"))


class TestXstreamLogHelpers(unittest.TestCase):
    """GDS 导入/导出日志的纯文本判定（无 middle、无真机）。"""

    CLEAN = "\n".join([
        "Calibre XStream 2025.1",
        "Translating cellview PROJ65/inv2/layout as STRUCTURE inv2.",
        "Translating cellview tsmcN65/pch_25/layout as STRUCTURE pch_25_1.",
        "Translation completed with 0 errors",
    ])
    BAD = "\n".join([
        "Translating cellview PROJ65/inv2/layout as STRUCTURE inv2.",
        "XSTRM-273: Translation failed for cell inv2",
    ])

    def test_failure_reason(self):
        self.assertEqual(L._xstream_failure_reason(""), "")
        self.assertEqual(L._xstream_failure_reason(self.CLEAN), "")
        self.assertEqual(L._xstream_failure_reason(self.BAD), "xstream_failure")
        for line in ("Translation failed", "OPEN_FAILED: missing file",
                     "some XSTRM-273 marker"):
            self.assertEqual(L._xstream_failure_reason(line), "xstream_failure")

    def test_translated_structures_pairs_source_and_target(self):
        pairs = L._translated_structures(self.CLEAN)
        self.assertEqual(pairs, ["PROJ65/inv2/layout -> inv2",
                                 "tsmcN65/pch_25/layout -> pch_25_1"])
        self.assertEqual(L._translated_structures("nothing here"), [])

    def test_warnings_collects_known_diagnostics(self):
        log = "\n".join([
            "XSTRM-25: invalid record in layer map",
            "XSTRM-20: layer not found",
            "Dropped Layers: 3",
            "unrelated line",
        ])
        notes = L._xstream_warnings(log)
        self.assertEqual(len(notes), 3)
        self.assertTrue(notes[0].startswith("XSTRM-25"))
        self.assertEqual(L._xstream_warnings(self.CLEAN), [])

    def test_summary_picks_first_diagnostic_line(self):
        self.assertEqual(L._xstream_summary("Info only\nERROR: boom"), "ERROR: boom")
        self.assertEqual(L._xstream_summary("XSTRM-999: hi"), "XSTRM-999: hi")
        self.assertEqual(L._xstream_summary("Info only"), "no diagnostic line in log")


class TestReadFilters(unittest.TestCase):
    """`_parse_read` + `_apply_read_filters` 的纯逻辑（含 summary/shape 记录形态）。"""

    # shape 记录 14 项：kind/layer/purpose/bbox/points/width/text/xy/height/justify/orient/font/path_style
    READ = (
        '(("summary" ((0 0) (10 10)) 2 1 1)'
        ' ("shape" "rect" "M1" "drawing" ((0 0) (1 1))'
        ' ((0 0) (1 0) (1 1) (0 1)) 0 nil (0 0) 0 nil nil "stick" nil)'
        ' ("shape" "path" "M2" "drawing" ((1 1) (2 2)) ((1 1) (2 2))'
        ' 0.5 nil (1 1) 0 nil nil "stick" "extendExtend"))'
    )

    def test_parse_read_accepts_non_list(self):
        empty = L._parse_read("nil")
        self.assertEqual(empty["shape_count"], 0)
        self.assertIsNone(empty["bbox"])
        self.assertEqual(empty["shapes"], [])

    def test_parse_read_summary_and_shapes(self):
        parsed = L._parse_read(self.READ)
        self.assertEqual(parsed["shape_count"], 2)
        self.assertEqual(parsed["instance_count"], 1)
        self.assertEqual(parsed["via_count"], 1)
        self.assertEqual(parsed["bbox"], [[0.0, 0.0], [10.0, 10.0]])
        self.assertEqual([item["kind"] for item in parsed["shapes"]], ["rect", "path"])
        self.assertEqual(parsed["shapes"][0]["lpp"], ["M1", "drawing"])

    def test_apply_read_filters_summary_and_layer_counts(self):
        parsed = L._parse_read(self.READ)
        request = L.ReadRequest(token="t", library="L", cell="C", focus=["summary"])
        value = L._apply_read_filters(parsed, request)
        self.assertEqual(sorted(value), ["bbox", "instance_count", "layer_counts",
                                         "shape_count", "via_count"])
        self.assertEqual(value["layer_counts"], {"M1/drawing": 1, "M2/drawing": 1})

    def test_apply_read_filters_region_and_exclusion(self):
        parsed = L._parse_read(self.READ)
        inside = L.ReadRequest(
            token="t", library="L", cell="C", focus=["shapes"],
            object_filter={"shape": {"region": [0, 0, 1, 1]}})
        self.assertEqual(len(L._apply_read_filters(parsed, inside)["shapes"]), 2)

        outside = L.ReadRequest(
            token="t", library="L", cell="C", focus=["shapes"],
            object_filter={"shape": {"region": [50, 50, 60, 60]}})
        self.assertEqual(L._apply_read_filters(parsed, outside)["shapes"], [])

        excluded = L.ReadRequest(
            token="t", library="L", cell="C", focus=["shapes"],
            object_filter={"shape": "none"})
        self.assertIsNone(L._apply_read_filters(parsed, excluded).get("shapes"))

    def test_filter_helpers(self):
        self.assertIsNone(L._filter_region(None))
        self.assertEqual(L._filter_region({"shape": {"region": [0, 0, 1, 1]}}), [0, 0, 1, 1])
        self.assertEqual(L._filter_entry(None, "shape"), "all")
        self.assertEqual(L._filter_entry({"shape": "none"}, "shape"), "none")
        self.assertEqual(L._filter_layers({"shape": {"layers": [["M1", "drawing"]]}}),
                         [("M1", "drawing")])
        self.assertTrue(L._filter_layers_or_region({"shape": {"layers": [["M1", "drawing"]]}}))
        self.assertFalse(L._filter_layers_or_region({}))
        self.assertTrue(L._bbox_hit([[0, 0], [1, 1]], [0.5, 0.5, 2, 2], "intersect"))
        self.assertFalse(L._bbox_hit([[0, 0], [1, 1]], [2, 2, 3, 3], "intersect"))
        # 注意方向：contain = **bbox 被 region 包含**（不是 region 被 bbox 包含）
        self.assertTrue(L._bbox_hit([[1.5, 1.5], [2, 2]], [1, 1, 2, 2], "contain"))
        self.assertFalse(L._bbox_hit([[0, 0], [3, 3]], [1, 1, 2, 2], "contain"))
        self.assertFalse(L._bbox_hit(None, [0, 0, 1, 1], "intersect"))


class OrchestrationMiddle:
    """layout 编排用假 middle：按 SKILL 文本分派（视图探测 / 命令 / 保存）。"""

    def __init__(self, *, view_state: str = '"ok"', save_output: str = '"saved"',
                 command_ok: bool = True, read_output: str | None = None,
                 lock_files: str = "") -> None:
        self.view_state = view_state
        self.save_output = save_output
        self.command_ok = command_ok
        self.read_output = read_output if read_output is not None else TestReadFilters.READ
        self.lock_files = lock_files
        self.calls: list[str] = []

    def execute_skill(self, code, timeout=None, *, token):
        from pyapi.models import ExecutionStatus, VirtuosoResult
        self.calls.append(code)
        if "vbOut" in code:                        # _read_skill 收集到 vbOut 再 reverse
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.read_output)
        if "vbState" in code:                      # _view_state_expr 探测
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.view_state)
        if "dbSave(" in code:                      # _save_expr
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.save_output)
        if '"open-ok"' in code:                    # _open_for_edit_error 探测
            return VirtuosoResult(
                status=ExecutionStatus.SUCCESS,
                output='"open-failed"' if self.lock_files else '"open-ok"')
        if "ddGetObjReadPath" in code:             # 锁检查前的库 readPath 探测
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"/lib"')
        if not self.command_ok:
            return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=["command boom"])
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="db:1")

    def query(self, *, token, role=None, name=None):
        raise AssertionError("layout read/write/display must not need query")

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        from pyapi.models import CommandResult
        self.calls.append(cmd)
        if "*.cdslck" in cmd:
            return CommandResult(0, self.lock_files, "")
        return CommandResult(0, "", "")


class TestLayoutReadOrchestration(unittest.TestCase):
    READ = TestReadFilters.READ

    def _read(self, middle, **fields):
        return L.Package(middle).read(L.ReadRequest(
            token="t", library="LIB", cell="CELL", view="layout", **fields))

    def test_happy_path_returns_geometry_and_identity(self):
        result = self._read(OrchestrationMiddle())
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["shape_count"], 2)
        self.assertEqual(value["library"], "LIB")
        self.assertEqual(value["cell"], "CELL")
        self.assertEqual(value["view"], "layout")
        self.assertEqual(value["view_type"], "maskLayout")
        self.assertEqual([item["kind"] for item in value["shapes"]], ["rect", "path"])
        self.assertEqual(value["layer_counts"], {"M1/drawing": 1, "M2/drawing": 1})

    def test_focus_limits_sections(self):
        result = self._read(OrchestrationMiddle(), focus=["shapes"])
        value = result.value
        self.assertEqual(sorted(k for k in value if k not in
                                ("library", "cell", "view", "view_type")), ["shapes"])

    def test_malformed_output_is_rejected(self):
        class BadMiddle(OrchestrationMiddle):
            def execute_skill(self, code, timeout=None, *, token):
                from pyapi.models import ExecutionStatus, VirtuosoResult
                self.calls.append(code)
                return VirtuosoResult(status=ExecutionStatus.SUCCESS, output="(a)(b)")

        result = self._read(BadMiddle())
        self.assertFalse(result.ok)
        self.assertIn("not a single complete SKILL list", result.error)

    def test_skill_failure_is_reported(self):
        class FailMiddle(OrchestrationMiddle):
            def execute_skill(self, code, timeout=None, *, token):
                from pyapi.models import ExecutionStatus, VirtuosoResult
                return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=["nope"])

        result = self._read(FailMiddle())
        self.assertFalse(result.ok)
        self.assertIn("nope", result.error)


class TestLayoutWriteOrchestration(unittest.TestCase):
    CMD = {"op": "place_rect", "layer": "M1", "purpose": "drawing", "bbox": [0, 0, 1, 1]}

    def _write(self, middle, **fields):
        return L.Package(middle).write(L.WriteRequest(
            token="t", library="LIB", cell="CELL", view="layout",
            commands=[self.CMD], **fields))

    def test_happy_path_applies_and_saves(self):
        middle = OrchestrationMiddle()
        result = self._write(middle)
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value, {"applied": 1})
        names = [step["name"] for step in result.steps]
        self.assertEqual(names, ["view_exists", "open", "command:place_rect", "dbSave"])

    def test_write_locked_view_reports_lock(self):
        middle = OrchestrationMiddle(lock_files="layout.oa.cdslck\n")
        result = self._write(middle)
        self.assertFalse(result.ok)
        self.assertIn("locked by another session", result.error)

    def test_second_write_is_not_false_locked(self):
        """P-044 回归：本会话自己的锁不能挡第二次写，且每次写后要 dbClose。"""
        middle = OrchestrationMiddle()
        first = self._write(middle)
        second = self._write(middle)
        self.assertTrue(first.ok, first.error)
        self.assertTrue(second.ok, second.error)
        self.assertTrue(any("dbClose(vbLayoutCv)" in code
                            for code in middle.calls))

    def test_save_without_saved_marker_fails(self):
        """layout 的正确对照：保存步必须看到 "saved"，否则判失败。"""
        result = self._write(OrchestrationMiddle(save_output='"check-failed"'))
        self.assertFalse(result.ok)
        self.assertIn("layout save failed", result.error)

        nil_save = self._write(OrchestrationMiddle(save_output="nil"))
        self.assertFalse(nil_save.ok)
        self.assertIn("layout save failed", nil_save.error)

    def test_view_probe_states(self):
        missing = self._write(OrchestrationMiddle(view_state='"missing"'))
        self.assertFalse(missing.ok)
        self.assertIn("not found", missing.error)

        mismatch = self._write(OrchestrationMiddle(view_state='"mismatch"'))
        self.assertFalse(mismatch.ok)
        self.assertIn("is not view type", mismatch.error)

        weird = self._write(OrchestrationMiddle(view_state='"banana"'))
        self.assertFalse(weird.ok)
        self.assertIn("unexpected view probe result", weird.error)

    def test_command_failure_mentions_non_transactional(self):
        result = self._write(OrchestrationMiddle(command_ok=False))
        self.assertFalse(result.ok)
        self.assertIn("command boom", result.error)
        self.assertIn("not transactional", result.error)


    def test_invalid_command_and_empty_list(self):
        bad = L.Package(OrchestrationMiddle()).write(L.WriteRequest(
            token="t", library="LIB", cell="CELL", view="layout",
            commands=[{"op": "explode"}]))
        self.assertFalse(bad.ok)
        self.assertIn("command 0 invalid", bad.error)

        with self.assertRaises(ValueError):
            L.Package(OrchestrationMiddle()).write(L.WriteRequest(
                token="t", library="LIB", cell="CELL", view="layout", commands=[]))


class TestLayoutDisplayOrchestration(unittest.TestCase):
    def _display(self, middle, commands):
        return L.Package(middle).display(L.DisplayRequest(
            token="t", library="LIB", cell="CELL", view="layout", commands=commands))

    def test_happy_path_reports_applied_count(self):
        result = self._display(OrchestrationMiddle(), [
            {"op": "fit_view"}, {"op": "set_layers_visible", "layers": [["M1", "drawing"]],
                                 "visible": True}])
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value, {"applied": 2})
        self.assertEqual([step["name"] for step in result.steps],
                         ["command:fit_view", "command:set_layers_visible"])

    def test_unknown_atom_and_bad_scale(self):
        unknown = self._display(OrchestrationMiddle(), [{"op": "nope"}])
        self.assertFalse(unknown.ok)
        self.assertIn("unknown display atom", unknown.error)

        scale = self._display(OrchestrationMiddle(), [{"op": "zoom", "scale": 0}])
        self.assertFalse(scale.ok)
        self.assertIn("must be > 0", scale.error)

    def test_command_failure_reports_applied_prefix(self):
        result = self._display(OrchestrationMiddle(command_ok=False),
                               [{"op": "fit_view"}])
        self.assertFalse(result.ok)
        self.assertIn("command boom", result.error)
        self.assertIn("(applied: 0/1)", result.error)

    def test_empty_commands_and_non_dict_entry(self):
        with self.assertRaises(ValueError):
            self._display(OrchestrationMiddle(), [])
        bad = self._display(OrchestrationMiddle(), ["not-a-dict"])
        self.assertFalse(bad.ok)
        self.assertIn("must be an object with op", bad.error)


class GdsMiddle:
    """layout.gds 导出编排的假 middle（prepare/flush/launch/poll/publish/cleanup）。

    日志体必须同时含 ``XSTRM-234`` 与 ``Translation completed`` 才会被判定为完成
    （见 `_gds_export` 的轮询退出条件）。
    """

    def __init__(self, *, log_text: str | None = None, gds_size: int = 1234,
                 launch_output: str = '"started"', flush_output: str = '"saved"',
                 poll_rc: int = 0, prepare_rc: int = 0, stage_rc: int = 0,
                 lock_files: str = "") -> None:
        self.log_text = log_text if log_text is not None else (
            "Translating cellview LIB/CELL/layout as STRUCTURE CELL.\n"
            "XSTRM-234: Translation completed.\n")
        self.gds_size = gds_size
        self.launch_output = launch_output
        self.flush_output = flush_output
        self.poll_rc = poll_rc
        self.prepare_rc = prepare_rc
        self.stage_rc = stage_rc
        self.lock_files = lock_files
        self.commands: list[str] = []
        self.skills: list[str] = []
        self.uploads: list[str] = []
        self.downloads: list[str] = []

    def query(self, *, token, role=None, name=None):
        from pyapi.models import ExecutionStatus

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
            return CommandResult(self.prepare_rc, "", "" if self.prepare_rc == 0 else "prepare boom")
        if cmd.startswith("cp "):
            return CommandResult(self.stage_rc, "", "" if self.stage_rc == 0 else "stage boom")
        if "*.cdslck" in cmd:
            return CommandResult(0, self.lock_files, "")
        if "---VBSIZE---" in cmd:
            if self.poll_rc != 0:
                return CommandResult(self.poll_rc, "", "tail failed")
            return CommandResult(0, f"{self.log_text}---VBSIZE---\n{self.gds_size}\n", "")
        return CommandResult(0, "", "")

    def execute_skill(self, code, timeout=None, *, token):
        from pyapi.models import ExecutionStatus, VirtuosoResult
        self.skills.append(code)
        if '"open-ok"' in code:                    # _open_for_edit_error 探测
            return VirtuosoResult(
                status=ExecutionStatus.SUCCESS,
                output='"open-failed"' if self.lock_files else '"open-ok"')
        if "dbSave(" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.flush_output)
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=self.launch_output)

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        from pyapi.models import CommandResult
        self.uploads.append(str(remote_path))
        return CommandResult(0, str(remote_path), "")

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        from pyapi.models import CommandResult
        from pathlib import Path as _Path
        self.downloads.append(str(remote_path))
        target = _Path(local_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"GDS" + b"0" * 64)
        return CommandResult(0, str(target), "")


class TestLayoutGdsOrchestration(unittest.TestCase):
    def _export(self, middle, **fields):
        fields.setdefault("token", "t")
        fields.setdefault("action", "export")
        fields.setdefault("library", "LIB")
        fields.setdefault("cell", "CELL")
        fields.setdefault("file_path", "out.gds")
        return L.Package(middle).gds(L.GdsRequest(**fields))

    def test_action_validation(self):
        with self.assertRaises(ValueError) as ctx:
            self._export(GdsMiddle(), action="sideways")
        self.assertIn("action must be export or import", str(ctx.exception))

    def test_happy_export_publishes_and_cleans_up(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            out = Path(tmp) / "inv2.gds"
            log = Path(tmp) / "inv2.xstream.log"
            middle = GdsMiddle()
            result = self._export(middle, file_path=str(out), log_path=str(log))
            self.assertTrue(result.ok, result.error)
            value = result.value
            self.assertEqual(value["action"], "export")
            self.assertEqual(value["reason"], "completed")
            self.assertEqual(value["gds_size"], 1234)
            self.assertEqual(value["translated_structures"],
                             ["LIB/CELL/layout -> CELL"])
            self.assertTrue(out.exists() and out.stat().st_size > 0)
            self.assertTrue(log.exists())
            self.assertTrue(str(value["remote_run_dir"]).endswith("LIB__CELL__layout"))
            names = [step["name"] for step in result.steps]
            for expected in ("prepare", "flush", "xstream", "log", "publish_gds", "cleanup"):
                self.assertIn(expected, names, names)
            self.assertTrue(any(c.startswith("rm -rf") for c in middle.commands))

    def test_export_remote_destination_copies_without_download(self):
        middle = GdsMiddle()
        result = self._export(
            middle, file_is_local=False,
            file_path="/remote/out.gds", log_path="/remote/out.xstream.log",
        )
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["gds_path"], "/remote/out.gds")
        self.assertEqual(middle.downloads, [])
        self.assertTrue(any(c.startswith("cp /role/daemon/xstream/LIB__CELL__layout/")
                           for c in middle.commands))

    def test_export_remote_destination_rejects_relative_path(self):
        result = self._export(GdsMiddle(), file_is_local=False,
                              file_path="out.gds")
        self.assertFalse(result.ok)
        self.assertIn("absolute remote path", result.error)

    def test_export_locked_view_reports_lock(self):
        middle = GdsMiddle(lock_files="layout.oa.cdslck\n")
        result = self._export(middle)
        self.assertFalse(result.ok)
        self.assertIn("locked by another session", result.error)

    def test_flush_requires_saved_marker(self):
        result = self._export(GdsMiddle(flush_output='"check-failed"'))
        self.assertFalse(result.ok)
        self.assertIn("failed to save the layout before export", result.error)

    def test_launch_must_report_started(self):
        result = self._export(GdsMiddle(launch_output='"error"'))
        self.assertFalse(result.ok)
        self.assertIn("xstream_failure", result.error)

    def test_translation_failure_is_reported_and_keeps_dir_by_default(self):
        log = ("Translating cellview LIB/CELL/layout as STRUCTURE CELL.\n"
               "XSTRM-273: Translation failed for cell CELL\n")
        middle = GdsMiddle(log_text=log)
        result = self._export(middle)
        self.assertFalse(result.ok)
        self.assertIn("xstream_failure", result.error)
        # cleanup_policy 默认 success：失败时**不**清理远端目录（留证据）
        self.assertFalse(any(c.startswith("rm -rf") for c in middle.commands))

    def test_missing_gds_is_reported(self):
        result = self._export(GdsMiddle(gds_size=0))
        self.assertFalse(result.ok)
        self.assertIn("missing_gds", result.error)

    def test_poll_timeout_reports_incomplete_log(self):
        result = self._export(GdsMiddle(poll_rc=1), timeout=0.01, poll_interval=0.001)
        self.assertFalse(result.ok)
        self.assertIn("incomplete_log", result.error)

    def test_layer_map_staging_paths(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            map_file = Path(tmp) / "layer.map"
            map_file.write_text("M1 drawing 31 0\n", encoding="utf-8")
            local = GdsMiddle()
            with tempfile.TemporaryDirectory(prefix="vb-") as out_tmp:
                ok = self._export(local, layer_map=str(map_file),
                                  layer_map_is_local=True,
                                  file_path=str(Path(out_tmp) / "a.gds"))
            self.assertTrue(ok.ok, ok.error)
            self.assertTrue(any(u.endswith("stream.map") for u in local.uploads))

            remote = GdsMiddle()
            with tempfile.TemporaryDirectory(prefix="vb-") as out_tmp:
                ok2 = self._export(remote, layer_map="/remote/layer.map",
                                   layer_map_is_local=False,
                                   file_path=str(Path(out_tmp) / "b.gds"))
            self.assertTrue(ok2.ok, ok2.error)
            self.assertTrue(any(c.startswith("cp /remote/layer.map") for c in remote.commands))

    def test_log_path_must_differ_from_file_path(self):
        # 该检查在 _gds_export 的 try 内 → 以 Result 形式返回，不向调用方抛
        result = self._export(GdsMiddle(), file_path="same.gds", log_path="same.gds")
        self.assertFalse(result.ok)
        self.assertIn("must differ", result.error)

    def test_cleanup_policy_always_cleans_on_failure(self):
        log = "XSTRM-273: Translation failed\n"
        middle = GdsMiddle(log_text=log)
        result = self._export(middle, cleanup_policy="always")
        self.assertFalse(result.ok)
        self.assertTrue(any(c.startswith("rm -rf") for c in middle.commands))

    def test_cleanup_policy_never_keeps_dir_on_success(self):
        import tempfile
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = GdsMiddle()
            result = self._export(middle, cleanup_policy="never",
                                  file_path=str(Path(tmp) / "c.gds"))
            self.assertTrue(result.ok, result.error)
        self.assertFalse(any(c.startswith("rm -rf") for c in middle.commands))


#: 供 mock.patch 替换：模块内的 artifact_dir 决定截图落到哪
def _temp_artifact_dir(tmp_root: str):
    return lambda: Path(tmp_root) / "artifact"


class ScreenshotMiddle:
    """layout.screenshot 的假 middle（mkdir/capture/verify/download/清理）。"""

    def __init__(self, *, mkdir_rc: int = 0, capture_ok: bool = True,
                 verify_stdout: str = "4096", verify_rc: int = 0,
                 download_rc: int = 0, download_bytes: bytes = b"\x89PNG-data") -> None:
        self.mkdir_rc = mkdir_rc
        self.capture_ok = capture_ok
        self.verify_stdout = verify_stdout
        self.verify_rc = verify_rc
        self.download_rc = download_rc
        self.download_bytes = download_bytes
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
        from pyapi.models import ExecutionStatus, VirtuosoResult
        if not self.capture_ok:
            return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=["capture boom"])
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')

    def download_file(self, remote_path, local_path, timeout=None, *, token, recursive=False):
        from pyapi.models import CommandResult
        if self.download_rc == 0:
            target = Path(local_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(self.download_bytes)
            return CommandResult(0, str(target), "")
        return CommandResult(self.download_rc, "", "download boom")


class TestLayoutScreenshot(unittest.TestCase):
    def _shot(self, middle, tmp_root: str, **fields):
        fields.setdefault("token", "t")
        fields.setdefault("library", "LIB")
        fields.setdefault("cell", "CELL")
        fields.setdefault("view", "layout")
        with mock.patch.object(L, "artifact_dir", _temp_artifact_dir(tmp_root)):
            return L.Package(middle).screenshot(L.ScreenshotRequest(**fields))

    def test_happy_path_saves_png_and_cleans_remote(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = ScreenshotMiddle()
            result = self._shot(middle, tmp)
            self.assertTrue(result.ok, result.error)
            local = Path(result.value["local_path"])
            self.assertTrue(local.exists())
            self.assertEqual(local.read_bytes(), b"\x89PNG-data")
            self.assertIn("screenshots", str(local))
            self.assertEqual([step["name"] for step in result.steps],
                             ["mkdir", "capture", "verify", "download"])
            # finally 里必须清掉远端 png
            self.assertTrue(any(c.startswith("rm -f") for c in middle.commands))

    def test_failure_paths(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            mkdir = self._shot(ScreenshotMiddle(mkdir_rc=1), tmp)
            self.assertFalse(mkdir.ok)
            self.assertIn("mkdir boom", mkdir.error)
            self.assertEqual([step["name"] for step in mkdir.steps], ["mkdir"])

            capture = self._shot(ScreenshotMiddle(capture_ok=False), tmp)
            self.assertFalse(capture.ok)
            self.assertIn("capture boom", capture.error)

            empty = self._shot(ScreenshotMiddle(verify_stdout="0"), tmp)
            self.assertFalse(empty.ok)
            self.assertIn("produced no image", empty.error)

            bad_verify = self._shot(ScreenshotMiddle(verify_rc=1), tmp)
            self.assertFalse(bad_verify.ok)
            self.assertIn("produced no image", bad_verify.error)

            dl = self._shot(ScreenshotMiddle(download_rc=1), tmp)
            self.assertFalse(dl.ok)
            self.assertIn("download boom", dl.error)

    def test_region_and_bool_validation(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            with self.assertRaises(ValueError):
                self._shot(ScreenshotMiddle(), tmp, region=[0, 0, 1])
            with self.assertRaises(ValueError):
                self._shot(ScreenshotMiddle(), tmp, toplevel=1)
            with self.assertRaises(ValueError):
                self._shot(ScreenshotMiddle(), tmp, central_widget="yes")
            with self.assertRaises(ValueError):
                self._shot(ScreenshotMiddle(), tmp, leave_open=None)
            with self.assertRaises(ValueError):
                self._shot(ScreenshotMiddle(), tmp, timeout=0)


class GdsImportMiddle(GdsMiddle):
    """layout.gds(import) 的假 middle（库探测 / strmin 可用性 / 暂存 / 启动 / 轮询 / 校验）。"""

    OK_LOG = ("Translating cellview <stream> as STRUCTURE CELL.\n"
              "XSTRM-234: Translation completed.\n")

    def __init__(self, *, lib_exists: bool = True, strmin_rc: int = 0,
                 upload_rc: int = 0, import_log: str | None = None,
                 import_logs: list[str] | None = None,
                 poll_rc: int = 0, verify_shapes: int = 7,
                 verify_instances: int = 2) -> None:
        super().__init__()
        self.lib_exists = lib_exists
        self.strmin_rc = strmin_rc
        self.upload_rc = upload_rc
        self.import_log = import_log if import_log is not None else self.OK_LOG
        self.import_logs = list(import_logs) if import_logs else None
        self.poll_rc = poll_rc
        self.verify_shapes = verify_shapes
        self.verify_instances = verify_instances

    def run_command(self, cmd, timeout=None, *, token, parallel=False):
        from pyapi.models import CommandResult
        self.commands.append(cmd)
        if cmd.startswith("command -v strmin"):
            return CommandResult(self.strmin_rc, "/usr/bin/strmin\n" if self.strmin_rc == 0 else "",
                                 "" if self.strmin_rc == 0 else "not found")
        if "nohup strmin " in cmd:
            return CommandResult(0, "launched\n", "")
        if cmd.startswith("tail -n 400"):
            if self.poll_rc != 0:
                return CommandResult(self.poll_rc, "", "tail failed")
            if self.import_logs:
                payload = self.import_logs.pop(0) if len(self.import_logs) > 1 else self.import_logs[0]
            else:
                payload = self.import_log
            return CommandResult(0, payload, "")
        return super().run_command(cmd, timeout, token=token, parallel=parallel)

    def upload_file(self, local_path, remote_path, timeout=None, *, token, recursive=False):
        from pyapi.models import CommandResult
        self.uploads.append(str(remote_path))
        if self.upload_rc != 0:
            return CommandResult(self.upload_rc, "", "upload boom")
        return CommandResult(0, str(remote_path), "")

    def execute_skill(self, code, timeout=None, *, token):
        from pyapi.models import ExecutionStatus, VirtuosoResult
        self.skills.append(code)
        if "ddGetObj(" in code and "dbOpenCellViewByType" not in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS,
                                  output="t" if self.lib_exists else "nil")
        if "getWorkingDir()" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"/home/u/work"')
        if "dbOpenCellViewByType(" in code:
            return VirtuosoResult(
                status=ExecutionStatus.SUCCESS,
                output=f'({self.verify_shapes} {self.verify_instances} '
                       '((0 0) (10 10)))')
        if "ddUpdateLibList" in code:
            return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')
        return VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')


class TestLayoutGdsImport(unittest.TestCase):
    def _import(self, middle, tmp_root: str, **fields):
        fields.setdefault("token", "t")
        fields.setdefault("action", "import")
        fields.setdefault("library", "LIB")
        fields.setdefault("tech_lib", "TECH")
        fields.setdefault("file_path", str(Path(tmp_root) / "in.gds"))
        fields.setdefault("timeout", 5)
        fields.setdefault("poll_interval", 0.01)
        if fields.get("file_is_local", True):
            Path(fields["file_path"]).write_bytes(b"GDS")
        return L.Package(middle).gds(L.GdsRequest(**fields))

    def test_happy_import_without_top_cell(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = GdsImportMiddle()
            result = self._import(middle, tmp)
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["action"], "import")
        self.assertEqual(value["reason"], "completed")
        self.assertTrue(value["log_path"].endswith("strmIn.log"))
        self.assertTrue(any(u.endswith("in.gds") for u in middle.uploads))
        names = [step["name"] for step in result.steps]
        for expected in ("library:LIB", "library:TECH", "strmin", "stage_gds"):
            self.assertIn(expected, names, names)
        self.assertNotIn("shape_count", value)      # 没给 top_cell 就不做校验

    def test_top_cell_triggers_verification_and_lib_refresh(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            # 第一次轮询还没完成 → 循环里会发 ddUpdateLibList；第二次才出现完成标记
            middle = GdsImportMiddle(import_logs=["starting translation...\n",
                                                  GdsImportMiddle.OK_LOG])
            result = self._import(middle, tmp, top_cell="CELL")
        self.assertTrue(result.ok, result.error)
        value = result.value
        self.assertEqual(value["shape_count"], 7)
        self.assertEqual(value["instance_count"], 2)
        self.assertEqual(value["bbox"], [[0.0, 0.0], [10.0, 10.0]])
        self.assertTrue(any("ddUpdateLibList" in code for code in middle.skills))
        launch = [c for c in middle.commands if "nohup strmin" in c][0]
        self.assertIn("-topCell CELL", launch)

    def test_missing_library_short_circuits(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = GdsImportMiddle(lib_exists=False)
            result = self._import(middle, tmp)
        self.assertFalse(result.ok)
        self.assertIn("target_lib_missing: LIB", result.error)
        self.assertEqual(result.value["reason"], "target_lib_missing")
        self.assertEqual([step["name"] for step in result.steps], ["library:LIB"])

    def test_missing_strmin_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._import(GdsImportMiddle(strmin_rc=1), tmp)
        self.assertFalse(result.ok)
        self.assertIn("tool_missing: strmin not found", result.error)
        self.assertEqual(result.value["reason"], "tool_missing")

    def test_staging_failure_is_reported(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._import(GdsImportMiddle(upload_rc=1), tmp)
        self.assertFalse(result.ok)
        self.assertIn("staging_error: upload boom", result.error)

    def test_translation_failure_carries_reason_and_log_path(self):
        log = "XSTRM-273: Translation failed for CELL\n"
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._import(GdsImportMiddle(import_log=log), tmp)
        self.assertFalse(result.ok)
        self.assertIn("xstream_failure", result.error)
        self.assertEqual(result.value["reason"], "xstream_failure")
        self.assertTrue(result.value["log_path"].endswith("strmIn.log"))

    def test_poll_timeout_reports_incomplete_log(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            result = self._import(GdsImportMiddle(poll_rc=1), tmp, timeout=0.01,
                                  poll_interval=0.001)
        self.assertFalse(result.ok)
        self.assertIn("incomplete_log", result.error)

    def test_remote_paths_use_cp_and_extend_strmin_args(self):
        with tempfile.TemporaryDirectory(prefix="vb-") as tmp:
            middle = GdsImportMiddle()
            result = self._import(middle, tmp, file_is_local=False,
                                  file_path="/remote/in.gds",
                                  ref_lib_file="/remote/refs.layermap",
                                  ref_lib_file_is_local=False,
                                  layer_map="/remote/layer.map",
                                  layer_map_is_local=False)
        self.assertTrue(result.ok, result.error)
        self.assertTrue(any(c.startswith("cp /remote/in.gds") for c in middle.commands))
        # 远端来源也先 cp 到 workdir，strmin 只吃 workdir 下的暂存路径（归一化）
        self.assertTrue(any(c.startswith("cp /remote/layer.map") for c in middle.commands))
        launch = [c for c in middle.commands if "nohup strmin" in c][0]
        self.assertIn("-layerMap /home/u/work/layer.map", launch)
        self.assertIn("-refLibList /home/u/work/refs.layermap", launch)
        self.assertIn("-attachTechFileOfLib TECH", launch)
        self.assertFalse(middle.uploads)


if __name__ == "__main__":
    unittest.main()
