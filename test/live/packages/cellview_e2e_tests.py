# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 21:45
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
    data = _c1_wrapper(response)
    return data


def _value(transport, operation: str, **fields: Any) -> Any:
    return _op(transport, operation, **fields).get("value")


def _expect_fail(transport, operation: str, **fields: Any) -> str:
    response = _call(transport, operation, **fields)
    if response.get("ok"):
        raise AssertionError(f"{operation} expected structured failure, got ok")
    return str(response.get("error") or "")


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
    ev.check_true(case, "lib.bind tech set",
                  "cdsDefTechLib" in json.dumps(bound, ensure_ascii=False), bound)

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
    """负控制：删不存在的对象必须**结构化失败**（spec §4 待修订项的口径）。"""
    case = "NEG"
    for label, operation, fields in (
        ("lib", "lib.delete", {"library": "cv_atoms_no_such_lib"}),
        ("cell", "cell.delete", {"library": LIB2, "cell": "no_such_cell"}),
        ("view", "view.delete", {"library": LIB2, "cell": CELL, "view": "no_such_view"}),
        ("cat", "cat.delete", {"library": LIB2, "category": "no_such_cat"}),
    ):
        error = _expect_fail(transport, operation, **fields)
        ev.check_true(case, f"{label}: structured failure", bool(error.strip()), error[:160])


CASES: tuple[tuple[str, Callable[[Any, Evidence], None]], ...] = (
    ("lib", _case_lib),
    ("cell", _case_cell),
    ("view", _case_view),
    ("cat", _case_category),
    ("NEG", _case_negative),
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="direct")
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


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
