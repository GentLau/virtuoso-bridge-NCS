"""L0 contracts for ``pyapi.packages.schematic`` (no Virtuoso, no sockets).

These cover the pure text layers the real-machine TBs never reach:
the SKILL-answer parser, the read filters, every atomic command builder and the
read/write/check_and_save control flow with a fake middle.
"""
from __future__ import annotations

import unittest

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import schematic as S


class FakeMiddle:
    """Minimal middle: records calls, answers with queued results."""

    def __init__(self, *results: VirtuosoResult) -> None:
        self.calls: list[tuple[str, str]] = []
        self.queue = list(results)
        self.default = VirtuosoResult(status=ExecutionStatus.SUCCESS, output='"ok"')

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append((token, skill_code))
        if self.queue:
            return self.queue.pop(0)
        return self.default

    def query(self, *, token, role=None, name=None):
        raise AssertionError("query is not used by schematic")


def ok(output: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=output)


def fail(*errors: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=list(errors))


class TestValidators(unittest.TestCase):
    def test_require_text_accepts_non_empty(self):
        self.assertEqual(S._require_text("x", "f"), "x")

    def test_require_text_rejects_empty_and_non_string(self):
        # 契约是 "non-empty"：空白串按实现是**接受**的，这里把边界钉死，
        # 避免以后有人误以为它做 strip 校验。
        self.assertEqual(S._require_text("   ", "f"), "   ")
        for bad in ("", None, 3):
            with self.assertRaises(ValueError) as ctx:
                S._require_text(bad, "command.master_lib")
            self.assertIn("command.master_lib", str(ctx.exception))

    def test_require_timeout_accepts_none_and_positive(self):
        S._require_timeout(None)
        S._require_timeout(1)
        S._require_timeout(0.5)

    def test_require_timeout_rejects_bad_values(self):
        # bool 是 int 子类，True 会被接受；只钉住真正非法的取值。
        for bad in (0, -1, "5"):
            with self.assertRaises(ValueError):
                S._require_timeout(bad)

    def test_q_quotes_and_escapes(self):
        self.assertEqual(S._q("a"), '"a"')
        self.assertEqual(S._q('a"b'), '"a\\"b"')

    def test_unquote_strips_quotes(self):
        self.assertEqual(S._unquote('"abc"'), "abc")

    def test_region_exprs_scalar_and_shape(self):
        self.assertIn("0", S._region_in_expr([0, 0, 1, 1]))
        self.assertIn("0", S._region_shape_expr([0, 0, 1, 1]))

    def test_region_exprs_reject_wrong_length(self):
        for fn in (S._region_in_expr, S._region_shape_expr):
            with self.assertRaises(ValueError):
                fn([0, 0, 1])

    def test_instance_filter_all_none_names_region(self):
        self.assertEqual(S._instance_filter_expr("all"), "t")
        self.assertEqual(S._instance_filter_expr("none"), "nil")
        names = S._instance_filter_expr({"names": ["A", "B"]})
        self.assertIn("member(__inst~>name", names)
        region = S._instance_filter_expr({"region": [0, 0, 1, 1]})
        self.assertIn("xCoord(__inst~>xy) >= 0", region)
        self.assertIn("yCoord(__inst~>xy) <= 1", region)

    def test_instance_filter_rejects_bad_input(self):
        with self.assertRaises(ValueError):
            S._instance_filter_expr(["A"])
        with self.assertRaises(ValueError):
            S._instance_filter_expr("sometimes")

    def test_shape_filter_none_dict_and_invalid(self):
        self.assertEqual(S._shape_filter_expr("none"), "nil")
        self.assertIn("x~>bBox", S._shape_filter_expr({"region": [0, 0, 1, 1]}))
        with self.assertRaises(ValueError):
            S._shape_filter_expr({"names": ["A"]})

    def test_point_str_formats_pairs(self):
        self.assertEqual(S._point_str([[0, 1], [2, 3]]), "list(0:1 2:3)")


class TestParseSchematic(unittest.TestCase):
    PAYLOAD = "\n".join([
        "INSTANCES",
        "INST|MP|tsmcN65|pch_25|(0.0 1.0)|R0|((-0.425 0.5125) (0.81875 1.275))|1|symbol",
        "TERM|D|VOUT",
        "TERM|G|VIN",
        "TERMXY|D|0.25|0.8125",
        'PARAM|model|\\"pch_25\\"',
        "NLACTION|stop",
        "INST|MN|tsmcN65|nch_25|(0.0 -1.0)|R0|((-0.425 -1.48125) (0.825 -0.71875))|1",
        "TERM|D|VOUT",
        "NETS",
        "NET|VOUT|1|signal|nil|MN.D|MP.D",
        "NET|VSS|1|signal|t",
        "PINS",
        "PIN|VIN|input|1",
        "PIN|VOUT|output|1|2.0|0.0",
        "LABELS",
        'LABEL|VIN|(0.25 1.0)|"R0"|"lowerCenter"|"stick"|0.0625',
        "LABEL|BROKEN|(0.1 0.2)|nil|nil|nil|not-a-number",
        "WIRES",
        'WIRE|((0.0 1.0) (0.0 1.25))|0|"red"|"dashed"',
        "WIRE|((0.0 0.0) (1.0 0.0))|bad",
        "NOTES",
        'NOTE|hello|(1.0 2.0)|"R0"|"lowerLeft"|"fixed"|0.125',
        "NOTE|bare",
        "END",
    ])

    def setUp(self):
        self.parsed = S._parse_schematic(self.PAYLOAD)

    def test_instances_terms_params_nlaction(self):
        first = self.parsed["instances"][0]
        self.assertEqual(first["name"], "MP")
        self.assertEqual(first["lib"], "tsmcN65")
        self.assertEqual(first["xy"], [0.0, 1.0])
        self.assertEqual(first["orient"], "R0")
        self.assertEqual(first["numInst"], "1")
        self.assertEqual(first["master_view"], "symbol")
        self.assertEqual(first["terms"], {"D": "VOUT", "G": "VIN"})
        self.assertEqual(first["terminals"], {"D": [0.25, 0.8125]})
        self.assertEqual(first["params"]["model"], "pch_25")
        self.assertEqual(first["nlAction"], "stop")

    def test_second_instance_defaults_master_view(self):
        second = self.parsed["instances"][1]
        self.assertEqual(second["name"], "MN")
        self.assertEqual(second["master_view"], "symbol")

    def test_nets_pins_labels_wires_notes(self):
        self.assertEqual(self.parsed["nets"]["VOUT"]["connections"], ["MN.D", "MP.D"])
        self.assertFalse(self.parsed["nets"]["VOUT"]["isGlobal"])
        self.assertTrue(self.parsed["nets"]["VSS"]["isGlobal"])
        self.assertEqual(self.parsed["pins"][0], {"name": "VIN", "direction": "input"})
        self.assertEqual(self.parsed["pins"][1]["xy"], [2.0, 0.0])
        self.assertEqual(self.parsed["labels"][0]["height"], 0.0625)
        self.assertIsNone(self.parsed["labels"][1]["height"])
        self.assertEqual(self.parsed["wires"][0]["color"], "red")
        self.assertEqual(self.parsed["wires"][0]["line_style"], "dashed")
        self.assertIsNone(self.parsed["wires"][1]["width"])
        self.assertEqual(self.parsed["notes"][0]["height"], 0.125)
        self.assertEqual(self.parsed["notes"][1], {"text": "bare"})

    def test_blank_and_unknown_lines_are_skipped(self):
        parsed = S._parse_schematic("\n\nJUNK\nNETS\nNET|X|1|signal|nil|A.B\n")
        self.assertEqual(parsed["instances"], [])
        self.assertEqual(parsed["nets"]["X"]["connections"], ["A.B"])


class TestAtomicSkill(unittest.TestCase):
    def test_place_instance_builds_master_and_name(self):
        expr = S._atomic_skill("place_instance", {
            "master_lib": "tsmcN65", "master_cell": "nch_25", "name": "MN",
            "x": 0, "y": 1})
        self.assertIn("dbCreateInst", expr)
        self.assertIn('"tsmcN65"', expr)
        self.assertIn('"MN"', expr)

    def test_delete_rename_instance(self):
        self.assertIn("dbDeleteObject", S._atomic_skill("delete_instance", {"name": "A"}))
        renamed = S._atomic_skill("rename_instance", {"name": "A", "new_name": "B"})
        self.assertIn('"B"', renamed)

    def test_set_instance_params_requires_params_mapping(self):
        expr = S._atomic_skill("set_instance_params", {"name": "MP", "params": {"w": "1u"}})
        self.assertIn("cdfGetInstCDF", expr)
        self.assertIn('"w"', expr)

    def test_set_term_nets_stub_and_label(self):
        expr = S._atomic_skill("set_term_nets", {
            "name": "MP", "term_nets": {"G": "VIN"}, "stub_length": 0.05})
        self.assertIn("schCreateWire", expr)
        self.assertIn("schCreateWireLabel", expr)
        self.assertIn("0.05", expr)

    def test_wire_ops(self):
        placed = S._atomic_skill("place_wire", {"points": [[0, 0], [1, 0]]})
        self.assertIn("schCreateWire", placed)
        styled = S._atomic_skill("place_wire", {
            "points": [[0, 0], [1, 0]], "width": 0.1, "color": "red",
            "line_style": "dashed"})
        self.assertIn('"red"', styled)
        deleted = S._atomic_skill("delete_wire", {"points": [[0, 0], [1, 0]]})
        self.assertIn("dbDeleteObject", deleted)
        props = S._atomic_skill("set_wire_properties", {
            "points": [[0, 0], [1, 0]], "width": 0.2})
        self.assertIn("__obj~>width", props)

    def test_label_ops(self):
        placed = S._atomic_skill("place_label", {"text": "VIN", "x": 0, "y": 0})
        self.assertIn("schCreateWireLabel", placed)
        alias = S._atomic_skill("place_label", {"text": "VIN", "x": 0, "y": 0, "alias": True})
        self.assertTrue(alias.rstrip(")").endswith("t"))
        self.assertIn("dbDeleteObject",
                      S._atomic_skill("delete_label", {"x": 0, "y": 0}))
        self.assertIn('"NEW"',
                      S._atomic_skill("rename_label", {"x": 0, "y": 0, "new_text": "NEW"}))
        styled = S._atomic_skill("set_label_properties", {
            "x": 0, "y": 0, "justify": "lowerLeft", "height": 0.2})
        self.assertIn("vbObj~>justify", styled)
        self.assertIn("vbObj~>height", styled)

    def test_pin_ops(self):
        placed = S._atomic_skill("place_pin", {
            "name": "VIN", "direction": "input", "x": 0, "y": 0})
        self.assertIn("schCreatePin", placed)
        self.assertIn('"input"', placed)
        extended = S._atomic_skill("place_pin", {
            "name": "VIN", "direction": "input", "x": 0, "y": 0,
            "off_sheet": True, "power_sens": "VDD", "ground_sens": "VSS",
            "sig_type": "signal"})
        self.assertIn('"VDD"', extended)
        self.assertIn("dbDeleteObject",
                      S._atomic_skill("delete_pin", {"x": 0, "y": 0}))
        self.assertIn('"NEW"',
                      S._atomic_skill("rename_pin", {"x": 0, "y": 0, "new_name": "NEW"}))
        changed = S._atomic_skill("set_pin_properties", {
            "x": 0, "y": 0, "direction": "output"})
        self.assertIn("schCreatePin", changed)
        # 实现把 direction 原样传给 schCreatePin（Virtuoso 自行选 ipin/opin 母版）；
        # 源码里预先算好的 master_cell 表达式是死代码（见 audit 记录）。
        self.assertIn('"output"', changed)

    def test_note_ops(self):
        placed = S._atomic_skill("place_note", {"text": "hello", "x": 0, "y": 0})
        self.assertIn("schCreateNote", placed)
        self.assertIn("dbDeleteObject", S._atomic_skill("delete_note", {"x": 0, "y": 0}))
        self.assertIn('"NEW"',
                      S._atomic_skill("rename_note", {"x": 0, "y": 0, "new_text": "NEW"}))
        styled = S._atomic_skill("set_note_properties", {
            "x": 0, "y": 0, "font": "fixed", "height": 0.1})
        self.assertIn("vbObj~>font", styled)

    def test_unknown_op_and_bad_atoms_raise(self):
        with self.assertRaises(ValueError) as ctx:
            S._atomic_skill("nope", {})
        self.assertIn("nope", str(ctx.exception))
        # place_instance 对 master_lib/master_cell 不做本地校验（空串照样拼 SKILL，
        # 交给运行时报错）——钉住现状，改动时会在此暴露。
        loose = S._atomic_skill("place_instance", {
            "master_lib": "", "master_cell": "", "name": "n", "x": 0, "y": 0})
        self.assertIn("dbCreateInst", loose)
        # 本地点数校验只存在于 place_line/place_path（place_wire 直接透传）：
        with self.assertRaises(ValueError):
            S._atomic_skill("place_line", {"points": [[0, 0], [1, 0], [2, 0]]})
        with self.assertRaises(ValueError):
            S._atomic_skill("place_path", {
                "points": [[0, 0]], "layer": "M1", "purpose": "drawing", "width": 0.1})
        with self.assertRaises(ValueError):
            S._atomic_skill("place_path", {
                "points": [[0, 0], [1, 0]], "layer": "M1", "purpose": "drawing",
                "width": 0})


class TestPackageFlow(unittest.TestCase):
    def _pkg(self, *results):
        return S.Package(FakeMiddle(*results))

    def test_read_parses_answer_and_records_step(self):
        pkg = self._pkg(ok('"INSTANCES\\nINST|MP|L|C|(0.0 0.0)|R0|b|1|symbol\\nEND\\n"'))
        result = pkg.read(S.ReadRequest(token="t", library="L", cell="C", view="schematic"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value["instances"][0]["name"], "MP")
        self.assertEqual(result.steps[0]["name"], "read")

    def test_read_reports_failure_and_error_sentinel(self):
        bad = self._pkg(fail("boom")).read(
            S.ReadRequest(token="t", library="L", cell="C"))
        self.assertFalse(bad.ok)
        self.assertIn("boom", bad.error)

        sentinel = self._pkg(ok('"ERROR"')).read(
            S.ReadRequest(token="t", library="L", cell="C"))
        self.assertFalse(sentinel.ok)
        self.assertIn("could not be opened", sentinel.error)

    def test_read_validates_request_fields(self):
        pkg = self._pkg()
        with self.assertRaises(ValueError):
            pkg.read(S.ReadRequest(token="", library="L", cell="C"))
        with self.assertRaises(ValueError):
            pkg.read(S.ReadRequest(token="t", library="L", cell="C", timeout=0))

    def test_write_runs_each_command_then_saves(self):
        middle = FakeMiddle(ok("open-ok"), ok("db:1"), ok("saved"))
        pkg = S.Package(middle)
        result = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "place_label", "text": "A", "x": 0, "y": 0}]))
        self.assertTrue(result.ok, result.error)
        names = [step["name"] for step in result.steps]
        self.assertEqual(names, ["open", "command:place_label", "check_and_save"])
        self.assertEqual(len(middle.calls), 3)
        codes = [code for _token, code in middle.calls]
        self.assertNotIn("dbOpenCellViewByType", codes[1])
        self.assertIn("dbClose(vbSchemCv)", codes[2])

    def test_write_reports_open_state_failures(self):
        for state, marker in (('"missing"', "not found"),
                              ('"type-mismatch"', "view type"),
                              ('"locked"', "locked by another session")):
            pkg = self._pkg(ok(state))
            result = pkg.write(S.WriteRequest(
                token="t", library="L", cell="C",
                commands=[{"op": "place_label", "text": "A", "x": 0, "y": 0}]))
            self.assertFalse(result.ok, state)
            self.assertIn(marker, result.error)

    def test_write_rejects_bad_commands_and_open_failure(self):
        with self.assertRaises(ValueError):
            self._pkg().write(S.WriteRequest(token="t", library="L", cell="C", commands=[]))

        pkg = self._pkg(ok("open-ok"), ok("x"))
        bad_cmd = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C", commands=[{"noop": 1}]))
        self.assertFalse(bad_cmd.ok)
        self.assertIn("must be an object with op", bad_cmd.error)

        pkg = self._pkg(ok("open-ok"), ok("x"))
        unknown = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C", commands=[{"op": "explode"}]))
        self.assertFalse(unknown.ok)
        self.assertIn("command 0 invalid", unknown.error)

        pkg = self._pkg(fail("no such cell"))
        opened = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "place_label", "text": "A", "x": 0, "y": 0}]))
        self.assertFalse(opened.ok)
        self.assertIn("no such cell", opened.error)

    def test_write_reports_command_and_save_failures(self):
        pkg = self._pkg(ok("open-ok"), fail("command blew up"))
        failed = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "place_label", "text": "A", "x": 0, "y": 0}]))
        self.assertFalse(failed.ok)
        self.assertIn("command blew up", failed.error)

        pkg = self._pkg(ok("open-ok"), ok("db:1"), fail("check failed"))
        save = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "place_label", "text": "A", "x": 0, "y": 0}]))
        self.assertFalse(save.ok)
        self.assertIn("check failed", save.error)

    def test_check_and_save_success_and_failure(self):
        good = self._pkg(ok('"open-ok"'), ok('"saved"')).check_and_save(
            S.CheckSaveRequest(token="t", library="L", cell="C"))
        self.assertTrue(good.ok, good.error)

    def test_check_and_save_must_report_check_failure(self):
        """红灯：schCheck 失败（SKILL 返回 "check-failed"）当前仍报 ok=True。

        缺陷编号 bug-20260922T124018Z-vblog-0584e46b；修好后本用例会变成
        unexpected success，提示把它改回普通断言。
        """
        bad = self._pkg(ok('"open-ok"'), ok('"check-failed"')).check_and_save(
            S.CheckSaveRequest(token="t", library="L", cell="C"))
        self.assertFalse(bad.ok)
        self.assertIn("check", bad.error or "")

    def test_write_must_report_check_failure(self):
        """同一缺陷的 write 路径（open-ok → 命令 → 保存返回 check-failed）。"""
        pkg = self._pkg(ok("open-ok"), ok("db:1"), ok('"check-failed"'))
        result = pkg.write(S.WriteRequest(
            token="t", library="L", cell="C",
            commands=[{"op": "place_label", "text": "A", "x": 0, "y": 0}]))
        self.assertFalse(result.ok)
        self.assertIn("check", result.error or "")


if __name__ == "__main__":
    unittest.main()
