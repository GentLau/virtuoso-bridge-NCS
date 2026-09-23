"""L0 contracts for ``pyapi.packages.cellview``.

两层证据：
1. **构造器**：每个 ``_*_skill`` 都是纯字符串函数，这里断言它引用了正确的
   Cadence 函数名、带上了调用方给的实参，并且**括号在引号外配平**（生成的
   SKILL 必须能被解析——这是唯一能离线抓到的语法级缺陷）。
2. **控制流**：用 FakeMiddle 走 ``_run_skill`` 的 ok / 错误码 / 结果畸形 / 执行失败
   四条分支，以及 ``lib_get`` 的值重塑。
"""
from __future__ import annotations

import unittest

from pyapi.models import ExecutionStatus, VirtuosoResult
from pyapi.packages import cellview as C


class FakeMiddle:
    def __init__(self, *results: VirtuosoResult) -> None:
        self.calls: list[tuple[str, str]] = []
        self.queue = list(results)

    def execute_skill(self, skill_code, timeout=None, *, token):
        self.calls.append((token, skill_code))
        return self.queue.pop(0) if self.queue else VirtuosoResult(
            status=ExecutionStatus.SUCCESS, output='list("ok")')


def ok(output: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.SUCCESS, output=output)


def fail(*errors: str) -> VirtuosoResult:
    return VirtuosoResult(status=ExecutionStatus.FAILURE, errors=list(errors))


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


class TestValidators(unittest.TestCase):
    def test_require_text(self):
        self.assertEqual(C._require_text("x", "n"), "x")
        for bad in ("", None, 4):
            with self.assertRaises(ValueError) as ctx:
                C._require_text(bad, "library")
            self.assertIn("library", str(ctx.exception))

    def test_require_timeout(self):
        C._require_timeout(None)
        C._require_timeout(5)
        for bad in (0, -1, "5"):
            with self.assertRaises(ValueError):
                C._require_timeout(bad)

    def test_step_shape(self):
        self.assertEqual(C._step("s", True, 1), {"name": "s", "ok": True, "detail": 1})


class TestSkillBuilders(unittest.TestCase):
    """每个构造器：函数名 + 实参 + 括号配平。"""

    def check(self, expr: str, *needles: str) -> None:
        self.assertTrue(balanced(expr), f"unbalanced SKILL: {expr[:160]}")
        for needle in needles:
            self.assertIn(needle, expr, f"missing {needle!r} in {expr[:160]}")

    def test_library_info_and_list(self):
        self.check(C._library_info_expr("vbLib"), "vbLib~>name", "techGetTechLibName")
        self.check(C._lib_list_skill(), "ddGetLibList")

    def test_lib_get_create_delete_rename_bind(self):
        self.check(C._lib_get_skill("L1"), "ddGetObj", '"L1"', "libraryNotFound")
        self.check(C._lib_create_skill("L2", "/p", None),
                   "ddCreateLib", '"L2"', '"/p"', "libraryExists")
        self.check(C._lib_create_skill("L3", "/p", "techX"),
                   "techBindTechFile", '"techX"', "technologyLibraryNotFound")
        self.check(C._lib_delete_skill("L4"), "ddDeleteObj", '"L4"', "deleteFailed")
        self.check(C._lib_rename_skill("A", "B"), "gdmCreateSpec", '"A"', '"B"')
        self.check(C._lib_bind_skill("L5", "techY"), "techBindTechFile", '"techY"')

    def test_cell_skills(self):
        self.check(C._cell_list_skill("L"), "ddGetObj", '"L"')
        self.check(C._cell_copy_skill("L", "C", "L2", "C2"), '"L2"', '"C2"',
                   "unwindProtect", "dbClose(vbSourceCv)", "dbClose(vbOk)")
        self.check(C._cell_delete_skill("L", "C"), "ddDeleteObj", '"C"')
        self.check(C._cell_rename_skill("L", "C", "C9"), '"C9"')

    def test_view_skills(self):
        self.check(C._view_list_skill("L", "C"), '"L"', '"C"')
        self.check(C._view_create_skill("L", "C", "layout", "maskLayout"),
                   "maskLayout", '"layout"')
        self.check(C._view_copy_skill("L", "C", "v", "L2", "C2", "v2"), '"v2"', '"C2"',
                   "unwindProtect", "dbClose(vbSourceCv)", "dbClose(vbCopied)")
        self.check(C._view_delete_skill("L", "C", "v"), '"v"')
        self.check(C._view_rename_skill("L", "C", "v", "v3"), '"v3"')

    def test_category_skills(self):
        self.check(C._cat_list_skill("L"), '"L"')
        self.check(C._cat_list_cells_skill("L", "cat"),
                   '"cat"', "ddCatGetCatMembers")
        self.check(C._cat_create_skill("L", "cat2"), "ddCatOpenEx", '"cat2"')
        self.check(C._cat_delete_skill("L", "cat3"), "ddCatRemove", '"cat3"',
                   "ddCatClose(vbCat)")
        self.check(C._cat_rename_skill("L", "cat4", "cat5"),
                   "ddCatRemove", '"cat5"',
                   "ddCatClose(vbExisting)", "ddCatClose(vbSource)")

    def test_category_cell_membership_both_directions(self):
        add = C._cat_change_cell_skill("L", "cat", "C", add=True)
        self.check(add, "ddCatAddItem", "cellAlreadyInCategory", '"C"')
        remove = C._cat_change_cell_skill("L", "cat", "C", add=False)
        self.check(remove, "ddCatSubItem", "cellNotInCategory", '"C"')


class TestRunSkillBranches(unittest.TestCase):
    def _pkg(self, *results):
        return C.Package(FakeMiddle(*results))

    def test_ok_record_returns_value(self):
        pkg = self._pkg(ok('("ok" "payload")'))
        result = pkg.lib_list(C.LibListRequest(token="t"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual(result.value, "payload")
        self.assertEqual(result.steps[0]["name"], "list")

    def test_ok_without_value_and_error_code(self):
        plain = self._pkg(ok('("ok")')).lib_list(C.LibListRequest(token="t"))
        self.assertTrue(plain.ok)
        self.assertIsNone(plain.value)

        coded = self._pkg(ok('("error" "libraryNotFound")')).lib_get(
            C.LibGetRequest(token="t", library="L"))
        self.assertFalse(coded.ok)
        self.assertEqual(coded.error, "libraryNotFound")

    def test_partial_record_is_reported_as_failure_code(self):
        partial = self._pkg(ok('("partial" "technologyBindingFailed" "L")')).lib_create(
            C.LibCreateRequest(token="t", library="L", path="/p"))
        self.assertFalse(partial.ok)
        self.assertEqual(partial.error, "technologyBindingFailed")

    def test_malformed_and_failed_results(self):
        for payload in ('"just-a-string"', '("ok") ("ok")', "(", ""):
            result = self._pkg(ok(payload)).lib_list(C.LibListRequest(token="t"))
            self.assertFalse(result.ok, f"{payload!r} should not parse")
            self.assertIn("malformed", result.error)

        exploded = self._pkg(fail("skill blew up")).lib_list(C.LibListRequest(token="t"))
        self.assertFalse(exploded.ok)
        self.assertIn("skill blew up", exploded.error)

    def test_error_record_without_code_defaults(self):
        result = self._pkg(ok('("error")')).lib_list(C.LibListRequest(token="t"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "skillFailed")

    def test_lib_get_reshapes_four_element_value(self):
        shaped = self._pkg(ok('("ok" ("library" "L" "/p" "techX"))')).lib_get(
            C.LibGetRequest(token="t", library="L"))
        self.assertTrue(shaped.ok, shaped.error)
        self.assertEqual(shaped.value,
                         {"name": "L", "path": "/p", "technology_library": "techX"})

    def test_lib_get_leaves_other_shapes_untouched(self):
        odd = self._pkg(ok('("ok" ("library" "L"))')).lib_get(
            C.LibGetRequest(token="t", library="L"))
        self.assertTrue(odd.ok)
        self.assertEqual(odd.value, ["library", "L"])

    def test_request_validation_is_enforced_before_skill(self):
        pkg = self._pkg()
        with self.assertRaises(ValueError):
            pkg.lib_get(C.LibGetRequest(token="t", library=""))
        with self.assertRaises(ValueError):
            pkg.lib_create(C.LibCreateRequest(token="t", library="L", path=""))
        with self.assertRaises(ValueError):
            pkg.lib_create(C.LibCreateRequest(token="t", library="L", path="/p", timeout=0))
        self.assertEqual(pkg.middle.calls, [])


class TestCopyOrchestration(unittest.TestCase):
    """lib_copy 是多步编排（建库 → 列 cell → 逐个复制），每一步都要能独立失败。"""

    def _pkg(self, *results):
        return C.Package(FakeMiddle(*results))

    def test_lib_copy_copies_every_cell_in_order(self):
        middle = FakeMiddle(
            ok('("ok" "NEWLIB")'),          # create
            ok('("ok" ("A" "B"))'),         # list_cells
            ok('("ok" "A")'),               # copy A
            ok('("ok" "B")'),               # copy B
        )
        result = C.Package(middle).lib_copy(C.LibCopyRequest(
            token="t", library="LIB", new_library="NEWLIB", new_path="/p/NEWLIB"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual([step["name"] for step in result.steps],
                         ["create", "list_cells", "copy_cell:A", "copy_cell:B"])
        self.assertEqual(len(middle.calls), 4)

    def test_lib_copy_create_failure_short_circuits(self):
        middle = FakeMiddle(ok('("error" "libraryExists")'))
        result = C.Package(middle).lib_copy(C.LibCopyRequest(
            token="t", library="LIB", new_library="NEWLIB", new_path="/p/NEWLIB"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "libraryExists")
        self.assertEqual([step["name"] for step in result.steps], ["create"])
        self.assertEqual(len(middle.calls), 1)

    def test_lib_copy_list_failure_keeps_create_step(self):
        middle = FakeMiddle(ok('("ok" "NEWLIB")'), ok('("error" "libraryNotFound")'))
        result = C.Package(middle).lib_copy(C.LibCopyRequest(
            token="t", library="LIB", new_library="NEWLIB", new_path="/p/NEWLIB"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "libraryNotFound")
        self.assertEqual([step["name"] for step in result.steps], ["create", "list_cells"])

    def test_lib_copy_cell_failure_stops_after_that_cell(self):
        middle = FakeMiddle(
            ok('("ok" "NEWLIB")'),
            ok('("ok" ("A" "B"))'),
            ok('("error" "copyFailed")'),
        )
        result = C.Package(middle).lib_copy(C.LibCopyRequest(
            token="t", library="LIB", new_library="NEWLIB", new_path="/p/NEWLIB"))
        self.assertFalse(result.ok)
        self.assertEqual(result.error, "copyFailed")
        self.assertEqual([step["name"] for step in result.steps],
                         ["create", "list_cells", "copy_cell:A"])
        self.assertEqual(len(middle.calls), 3)

    def test_lib_copy_empty_source_library(self):
        middle = FakeMiddle(ok('("ok" "NEWLIB")'), ok('("ok")'))
        result = C.Package(middle).lib_copy(C.LibCopyRequest(
            token="t", library="LIB", new_library="NEWLIB", new_path="/p/NEWLIB"))
        self.assertTrue(result.ok, result.error)
        self.assertEqual([step["name"] for step in result.steps], ["create", "list_cells"])

    def test_cell_copy_and_view_copy_are_single_calls(self):
        cell = C.Package(FakeMiddle(ok('("ok" "NEWCELL")'))).cell_copy(
            C.CellCopyRequest(token="t", library="LIB", cell="A",
                              new_library="NEWLIB", new_cell="A2"))
        self.assertTrue(cell.ok, cell.error)
        self.assertEqual(cell.value, "NEWCELL")

        view = C.Package(FakeMiddle(ok('("ok" "NEWVIEW")'))).view_copy(
            C.ViewCopyRequest(token="t", library="LIB", cell="A", view="layout",
                              new_library="NEWLIB", new_cell="A2", new_view="layout2"))
        self.assertTrue(view.ok, view.error)
        self.assertEqual(view.value, "NEWVIEW")

        bad = C.Package(FakeMiddle(ok('("error" "destinationExists")'))).cell_copy(
            C.CellCopyRequest(token="t", library="LIB", cell="A",
                              new_library="NEWLIB", new_cell="A2"))
        self.assertFalse(bad.ok)
        self.assertEqual(bad.error, "destinationExists")

    def test_cell_list_uses_category_skill_when_asked(self):
        with_cat = FakeMiddle(ok('("ok" "A")'))
        C.Package(with_cat).cell_list(C.CellListRequest(token="t", library="LIB", category="cat"))
        self.assertIn("ddCatGetCatMembers", with_cat.calls[0][1])

        without = FakeMiddle(ok('("ok" "A")'))
        C.Package(without).cell_list(C.CellListRequest(token="t", library="LIB"))
        self.assertNotIn("ddCatGetCatMembers", without.calls[0][1])
        self.assertIn("vbLib~>cells", without.calls[0][1])

    def test_lib_copy_validates_arguments(self):
        pkg = C.Package(FakeMiddle())
        with self.assertRaises(ValueError):
            pkg.lib_copy(C.LibCopyRequest(token="t", library="LIB",
                                          new_library="", new_path="/p"))
        with self.assertRaises(ValueError):
            pkg.lib_copy(C.LibCopyRequest(token="t", library="LIB",
                                          new_library="N", new_path="", timeout=0))
        self.assertEqual(pkg.middle.calls, [])


if __name__ == "__main__":
    unittest.main()
