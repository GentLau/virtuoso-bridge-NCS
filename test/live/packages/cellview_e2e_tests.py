# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 11:20
# 依赖: 无
# =======================================================================
"""``virtuoso.cellview.*`` 真机**逐操作**验收 TB（lib / cell / view / category 四层）。

六步流程（test/docs/写TB规范.md §1）：
① `require_environment`（靶机指纹 + 库可见性）；
②③ 每个操作先造被改对象（专属 scratch lib/cell/view/category），并读回校验基线；
④ 只做被测动作；⑤ **读回比对**（list/get 的期望 vs 实际，逐条入证据）；
⑥ 跑完不清理（下一次运行靠固定 scratch 名 + 先删后建自行还原）。

覆盖 22 个业务操作 + 4 条负控制（删不存在的 lib/cell/view/category 必须结构化失败）。
每个操作在证据里独立成行（case=<层级>.<动作>），便于与 spec 原子清单对账。

用法::

    python test/live/packages/cellview_e2e_tests.py --transport direct
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "test" / "shared" / "runners"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
OP = "virtuoso.cellview."
LIB = "cv_atoms_lib"
LIB2 = "cv_atoms_lib2"
LIB3 = "cv_atoms_lib3"
LIB_PATH = "/home/Gent/.virtuoso-bridge/vblog/cv_atoms_lib"
LIB2_PATH = "/home/Gent/.virtuoso-bridge/vblog/cv_atoms_lib2"
LIB3_PATH = "/home/Gent/.virtuoso-bridge/vblog/cv_atoms_lib3"
CELL = "cv_atoms_cell"
CELL2 = "cv_atoms_cell2"
CELL3 = "cv_atoms_cell3"
VIEW, VIEW2, VIEW3 = "schematic", "schematic_b", "schematic_c"
CAT, CAT2 = "cv_atoms_cat", "cv_atoms_cat2"


class HttpTransport:
    middle = None

    def __init__(self, base: str = API) -> None:
        self.base = base

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=900) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return json.loads(error.read().decode("utf-8"))


class DirectTransport:
    def __init__(self) -> None:
        from common.paths import init_work_dir
        from server import dispatch
        from server.api_server import register_packages
        from transport.middle import BusinessServer

        init_work_dir(str(WORK_DIR))
        register_packages()
        self.dispatch = dispatch
        self.middle = BusinessServer()

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        status, body = self.dispatch.dispatch(self.middle, payload)
        if status not in (200, 400):
            raise AssertionError(f"dispatch status {status}: {body}")
        return body


def _call(transport, operation: str, **fields: Any) -> dict[str, Any]:
    return transport.call({"operation": OP + operation, "token": TOKEN, **fields})


def _op(transport, operation: str, **fields: Any) -> dict[str, Any]:
    response = _call(transport, operation, **fields)
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    data = response
    return data


def _value(transport, operation: str, **fields: Any) -> Any:
    return _op(transport, operation, **fields).get("value")


def _expect_fail(transport, operation: str, **fields: Any) -> str:
    response = _call(transport, operation, **fields)
    if response.get("ok"):
        raise AssertionError(f"{operation} expected structured failure, got ok")
    return str(response.get("error") or "")


def _ensure(transport, operation: str, allowed: tuple[str, ...], **fields: Any) -> None:
    """前置构造：幂等——目标已存在（或已在类目）就算成功。"""
    response = _call(transport, operation, **fields)
    if response.get("ok"):
        return
    error = str(response.get("error") or "")
    if any(code in error for code in allowed):
        return
    raise AssertionError(f"{operation} 前置失败: {error}")


class Evidence:
    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def check(self, case: str, name: str, expected: Any, actual: Any) -> None:
        ok = expected == actual
        self.rows.append({"case": case, "check": name, "expected": expected,
                          "actual": actual, "verdict": "PASS" if ok else "FAIL"})
        if not ok:
            raise AssertionError(f"{case}/{name}: expected {expected!r}, actual {actual!r}")

    def check_true(self, case: str, name: str, condition: bool, actual: Any) -> None:
        self.rows.append({"case": case, "check": name, "expected": True,
                          "actual": actual, "verdict": "PASS" if condition else "FAIL"})
        if not condition:
            raise AssertionError(f"{case}/{name}: expected True, actual {actual!r}")


def _lib_names(transport) -> list[str]:
    return [str(item) for item in (_value(transport, "lib.list") or [])]


def _cell_names(transport, library: str = LIB2, **extra: Any) -> list[str]:
    return [str(item) for item in (_value(transport, "cell.list", library=library, **extra) or [])]


def _view_names(transport, library: str = LIB2, cell: str = CELL) -> list[str]:
    views = _value(transport, "view.list", library=library, cell=cell) or []
    return [str(item[0]) if isinstance(item, (list, tuple)) else str(item) for item in views]


def _reset(transport, ev: Evidence, case: str = "SETUP") -> None:
    """②③ 还原基线：删掉本 TB 的固定 scratch 对象（不存在就跳过），再建干净的一份。"""
    for lib in (LIB, LIB2, LIB3):
        try:
            _op(transport, "lib.delete", library=lib)
        except AssertionError:
            pass
    try:
        _op(transport, "lib.delete", library=LIB2)
    except AssertionError:
        pass
    _op(transport, "lib.create", library=LIB2, path=LIB2_PATH)
    _op(transport, "view.create", library=LIB2, cell=CELL, view=VIEW,
        view_type="schematic")
    _op(transport, "cat.create", library=LIB2, category=CAT)
    ev.check(case, "baseline lib present", True, LIB2 in _lib_names(transport))
    ev.check(case, "baseline cell present", [CELL], _cell_names(transport))
    ev.check(case, "baseline views present", [VIEW], _view_names(transport))
    ev.check(case, "baseline category present", [CAT],
             [str(item) for item in (_value(transport, "cat.list", library=LIB2) or [])])


# ------------------------------------------------------------- lib 层 --
def _case_lib(transport, ev: Evidence) -> None:
    case = "lib"
    ev.check_true(case, "lib.list contains scratch", LIB2 in _lib_names(transport),
                  _lib_names(transport))
    info = _value(transport, "lib.get", library=LIB2) or {}
    ev.check(case, "lib.get path", LIB2_PATH, str(info.get("path") or ""))

    _op(transport, "lib.create", library=LIB, path=LIB_PATH)
    ev.check(case, "lib.create visible", True, LIB in _lib_names(transport))

    _op(transport, "lib.bind", library=LIB, technology_library="cdsDefTechLib")
    bound = _value(transport, "lib.get", library=LIB) or {}
    # 2026-09-30 加强（表 C 真缺口 `virtual.cellview.lib.get.technology_library`）：
    # 原来只在整包 JSON 里找字符串（任何字段含它都算过）→ 改成**点名该字段值级断言**。
    ev.check(case, "lib.get technology_library", "cdsDefTechLib",
             bound.get("technology_library"))

    _op(transport, "lib.rename", library=LIB, new_name=LIB3)
    names = _lib_names(transport)
    ev.check(case, "lib.rename old gone/new present", [False, True],
             [LIB in names, LIB3 in names])

    _op(transport, "lib.copy", library=LIB3, new_library=LIB,
        new_path=LIB_PATH)
    ev.check(case, "lib.copy visible", True, LIB in _lib_names(transport))

    _op(transport, "lib.delete", library=LIB)
    ev.check(case, "lib.delete gone", False, LIB in _lib_names(transport))


# ------------------------------------------------------------ cell 层 --
def _case_cell(transport, ev: Evidence) -> None:
    case = "cell"
    ev.check(case, "cell.list", [CELL], _cell_names(transport))

    _op(transport, "cell.copy", library=LIB2, cell=CELL,
        new_library=LIB2, new_cell=CELL2)
    ev.check(case, "cell.copy visible", sorted([CELL, CELL2]),
             sorted(_cell_names(transport)))
    ev.check(case, "cell.copy carries views", [VIEW], _view_names(transport, cell=CELL2))

    _op(transport, "cell.rename", library=LIB2, cell=CELL2, new_name=CELL3)
    names = _cell_names(transport)
    ev.check(case, "cell.rename old gone/new present", [False, True],
             [CELL2 in names, CELL3 in names])
    ev.check(case, "cell.rename keeps views", [VIEW], _view_names(transport, cell=CELL3))

    _op(transport, "cell.delete", library=LIB2, cell=CELL3)
    ev.check(case, "cell.delete gone", False, CELL3 in _cell_names(transport))


# ------------------------------------------------------------ view 层 --
def _case_view(transport, ev: Evidence) -> None:
    case = "view"
    ev.check(case, "view.list", [VIEW], _view_names(transport))

    _op(transport, "view.create", library=LIB2, cell=CELL, view=VIEW2,
        view_type="schematic")
    ev.check(case, "view.create visible", sorted([VIEW, VIEW2]),
             sorted(_view_names(transport)))

    _op(transport, "view.copy", library=LIB2, cell=CELL, view=VIEW2,
        new_library=LIB2, new_cell=CELL, new_view=VIEW3)
    ev.check(case, "view.copy visible", True, VIEW3 in _view_names(transport))

    _op(transport, "view.rename", library=LIB2, cell=CELL, view=VIEW3,
        new_name="schematic_d")
    names = _view_names(transport)
    ev.check(case, "view.rename old gone/new present", [False, True],
             [VIEW3 in names, "schematic_d" in names])

    _op(transport, "view.delete", library=LIB2, cell=CELL, view="schematic_d")
    ev.check(case, "view.delete gone", False, "schematic_d" in _view_names(transport))


# -------------------------------------------------------- category 层 --
def _case_category(transport, ev: Evidence) -> None:
    case = "cat"
    ev.check(case, "cat.list", [CAT],
             [str(item) for item in (_value(transport, "cat.list", library=LIB2) or [])])

    _op(transport, "cat.add_cell", library=LIB2, category=CAT, cell=CELL)
    ev.check(case, "cat.add_cell visible", [CELL],
             _cell_names(transport, category=CAT))

    _op(transport, "cat.remove_cell", library=LIB2, category=CAT, cell=CELL)
    ev.check(case, "cat.remove_cell", [], _cell_names(transport, category=CAT))

    _op(transport, "cat.rename", library=LIB2, category=CAT, new_name=CAT2)
    cats = [str(item) for item in (_value(transport, "cat.list", library=LIB2) or [])]
    ev.check(case, "cat.rename old gone/new present", [False, True],
             [CAT in cats, CAT2 in cats])

    _op(transport, "cat.create", library=LIB2, category=CAT)
    ev.check(case, "cat.create visible", True,
             CAT in [str(item) for item in (_value(transport, "cat.list", library=LIB2) or [])])
    _op(transport, "cat.delete", library=LIB2, category=CAT)
    cats = [str(item) for item in (_value(transport, "cat.list", library=LIB2) or [])]
    ev.check(case, "cat.delete gone", False, CAT in cats)


def _case_negative(transport, ev: Evidence) -> None:
    """负控制：删不存在的对象必须**结构化失败**，且错误码点名是哪一层不存在。

    2026-09-30 加强：原来只断言"错误非空"，任何失败都能过（包括拼错 op 名、参数校验失败）。
    现在按实现/spec 的分层错误码逐条断言（`libraryNotFound` / `cellNotFound` /
    `viewNotFound` / `categoryNotFound`）——这才是"删不存在的对象"的语义证据。
    """
    case = "NEG"
    for label, operation, fields, expected in (
        ("lib", "lib.delete", {"library": "cv_atoms_no_such_lib"}, "libraryNotFound"),
        ("cell", "cell.delete", {"library": LIB2, "cell": "no_such_cell"}, "cellNotFound"),
        ("view", "view.delete", {"library": LIB2, "cell": CELL, "view": "no_such_view"},
         "viewNotFound"),
        ("cat", "cat.delete", {"library": LIB2, "category": "no_such_cat"},
         "categoryNotFound"),
    ):
        error = _expect_fail(transport, operation, **fields)
        ev.check_true(case, f"{label}: structured failure", bool(error.strip()), error[:160])
        ev.check(case, f"{label}: error code", expected, error.strip())


def _case_negative_copy_rename(transport, ev: Evidence) -> None:
    """copy/rename 与 category 成员操作的**非法档**（2026-09-30 补：这 8 个 op 此前各只有一条正例）。

    每个 op 至少一条"目标已存在"或"源不存在"的非法档，并断言**具体错误码**
    （实现里的枚举：`destinationExists` / `libraryNotFound` / `cellNotFound` / `viewNotFound` /
    `cellAlreadyInCategory` / `cellNotInCategory` / `destinationCategoryExists`）。
    """
    case = "NEG2"
    # ②③ 前置：保证 LIB2/CELL/VIEW 存在，并造出"已存在的目标"（CELL2/VIEW2/cat2）
    _ensure(transport, "cell.copy", ("destinationExists",),
            library=LIB2, cell=CELL, new_library=LIB2, new_cell=CELL2)
    _ensure(transport, "view.copy", ("destinationExists", "copyFailed"),
            library=LIB2, cell=CELL, view=VIEW, new_library=LIB2, new_cell=CELL,
            new_view=VIEW2)
    # 类目是**共享夹具**，可能被别的用例/手工清理掉 → 本用例自带幂等重建
    _ensure(transport, "cat.create", ("categoryExists",), library=LIB2, category=CAT)
    _ensure(transport, "cat.create", ("categoryExists",), library=LIB2, category=CAT2)
    _ensure(transport, "cat.add_cell", ("cellAlreadyInCategory",),
            library=LIB2, category=CAT, cell=CELL)
    _ensure(transport, "lib.copy", ("destinationExists", "libraryExists"),
            library=LIB2, new_library=LIB3, new_path=LIB3_PATH)

    checks = (
        # op、参数、期望错误码
        ("cell.copy 目标已存在", "cell.copy",
         {"library": LIB2, "cell": CELL, "new_library": LIB2, "new_cell": CELL2},
         "destinationExists"),
        ("cell.copy 源 cell 不存在", "cell.copy",
         {"library": LIB2, "cell": "no_such_cell", "new_library": LIB2,
          "new_cell": "dst_x"}, "cellNotFound"),
        ("cell.rename 目标已存在", "cell.rename",
         {"library": LIB2, "cell": CELL, "new_name": CELL2}, "destinationExists"),
        # 注：`view.copy` 目标已存在时实现给的是**通用** `copyFailed`（lib/cell 两条路径给 `destinationExists`）——
        # spec `5-cellview.md` 把"copy 能力/目标不存在时的错误语义"列为**待确认**，故这里按实测断言，
        # 并把"跨层错误码是否统一"并入 P-112（spec 改判）讨论。
        ("view.copy 目标已存在（实测通用码 copyFailed）", "view.copy",
         {"library": LIB2, "cell": CELL, "view": VIEW, "new_library": LIB2,
          "new_cell": CELL, "new_view": VIEW2}, "copyFailed"),
        ("view.copy 源 view 不存在", "view.copy",
         {"library": LIB2, "cell": CELL, "view": "no_such_view", "new_library": LIB2,
          "new_cell": CELL, "new_view": "dst_v"}, "viewNotFound"),
        ("view.rename 目标已存在", "view.rename",
         {"library": LIB2, "cell": CELL, "view": VIEW, "new_name": VIEW2},
         "destinationExists"),
        # `lib.copy` 目标已存在 → 实测 `libraryExists`（与 cell 层的 `destinationExists` **不一致**，并入 P-112）
        ("lib.copy 目标已存在（实测 libraryExists）", "lib.copy",
         {"library": LIB2, "new_library": LIB3, "new_path": LIB3_PATH},
         "libraryExists"),
        ("lib.rename 目标已存在", "lib.rename",
         {"library": LIB2, "new_name": LIB3}, "destinationExists"),
        ("cat.add_cell 已在类目", "cat.add_cell",
         {"library": LIB2, "category": CAT, "cell": CELL}, "cellAlreadyInCategory"),
        ("cat.add_cell cell 不存在", "cat.add_cell",
         {"library": LIB2, "category": CAT, "cell": "no_such_cell"}, "cellNotFound"),
        ("cat.remove_cell 不在类目", "cat.remove_cell",
         {"library": LIB2, "category": CAT, "cell": CELL2}, "cellNotInCategory"),
        ("cat.rename 目标已存在", "cat.rename",
         {"library": LIB2, "category": CAT, "new_name": CAT2},
         "destinationCategoryExists"),
        # create 族的非法档（2026-09-30 补：`lib.create`/`view.create` 此前只有一条正例）
        ("lib.create 已存在", "lib.create",
         {"library": LIB2, "path": LIB2_PATH}, "libraryExists"),
        ("lib.create 技术库不存在", "lib.create",
         {"library": "cv_atoms_tmp_x", "path": LIB2_PATH,
          "technology_library": "no_such_tech"}, "technologyLibraryNotFound"),
        ("view.create 非法 view_type", "view.create",
         {"library": LIB2, "cell": CELL, "view": "schematic_badtype",
          "view_type": "bogus_type"}, "createFailed"),
    )
    for label, operation, fields, expected in checks:
        error = _expect_fail(transport, operation, **fields)
        ev.check(case, f"{label}: error code", expected, error.strip())

    # ⑤ 反证：上面这些"非法档"都没有产生副作用（目标对象不重复、源对象仍在）
    ev.check(case, "cell2 未重复", 1, _cell_names(transport).count(CELL2))
    ev.check(case, "view2 未重复", 1, _view_names(transport, cell=CELL).count(VIEW2))
    ev.check_true(case, "源 cell 仍在", CELL in _cell_names(transport),
                  _cell_names(transport))


CASES: tuple[tuple[str, Callable[[Any, Evidence], None]], ...] = (
    ("lib", _case_lib),
    ("cell", _case_cell),
    ("view", _case_view),
    ("cat", _case_category),
    ("NEG", _case_negative),
    ("NEG2", _case_negative_copy_rename),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="http",
                        help="direct=故障定位/覆盖率；真机判据必须 http")
    parser.add_argument("--base", default=API)
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    transport = HttpTransport(args.base) if args.transport == "http" else DirectTransport()
    ev = Evidence()
    results: list[tuple[str, str]] = []
    env_report: dict[str, Any] = {}
    try:
        from env_check import require_environment

        options: dict[str, Any] = {"token": TOKEN, "expect_host": "GLIS-DESKTOP",
                                   "require_lib": ["schemtest"]}
        env_report = (require_environment(base=args.base, **options) if args.transport == "http"
                      else require_environment(work_dir=str(WORK_DIR), **options))

        _reset(transport, ev)
        for name, func in CASES:
            try:
                func(transport, ev)
                results.append((name, "PASS"))
            except Exception as exc:  # noqa: BLE001
                results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
                raise
    finally:
        out = Path(args.out) if args.out else (
            ROOT / "test" / "artifacts" / "evidence"
            / f"cellview-atoms-{dt.datetime.now():%Y%m%d-%H%M}" / "cellview-atoms-green.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "tb": "test/live/packages/cellview_e2e_tests.py",
            "transport": args.transport, "token": TOKEN,
            "libs": {"main": LIB, "scratch": LIB2, "third": LIB3},
            "env": env_report,
            "results": [{"case": name, "verdict": status} for name, status in results],
            "comparisons": ev.rows,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"evidence: {out}")
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
