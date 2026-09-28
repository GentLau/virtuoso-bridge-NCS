# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 19:45
# 依赖: 无
# =======================================================================
"""``virtuoso.schematic.*`` 真机原子级验收 TB（含 P-074 `pos` 口径）。

六步流程（test/docs/写TB规范.md §1）：
① `require_environment` 检查环境；② 造基线（专属 cell；每个原子先造被改对象）；
③ 校验基线；④ 只做被测动作；⑤ **读回比对**（期望 / 实际都写进证据）；⑥ 跑完不清理现场。

原子覆盖（对齐 spec 上层/2-schematic.md §1.2；机器核账 `audit_atom_coverage.py`）：
instance place/delete/rename/set_instance_params/set_term_nets、wire place/delete/set、
label place/delete/rename/set、pin place/delete/rename/set、note place/delete/rename/set；
另有负控制（`xy` / 拆字段必须被拒且点名 `pos`）+ read 过滤 + check_and_save + screenshot。

用法::

    python test/live/packages/schematic_e2e_tests.py --transport direct
    python test/live/packages/schematic_e2e_tests.py --transport http
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
LIB, CELL, VIEW = "schemtest", "sch_atoms", "schematic"
PDK_LIB, PDK_NCH = "tsmcN65", "nch"
TOL = 0.0011


class HttpTransport:
    middle = None

    def __init__(self, base: str = API) -> None:
        self.base = base

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base, data=body, headers={"Content-Type": "application/json"}, method="POST",
        )
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


def _op(transport, operation: str, **fields: Any) -> Any:
    response = transport.call({"operation": operation, "token": TOKEN, **fields})
    if not response.get("ok"):
        raise AssertionError(f"{operation} failed: {response.get('error')}")
    return response["data"]


def _value(transport, operation: str, **fields: Any) -> dict[str, Any]:
    value = _op(transport, operation, **fields).get("value")
    if not isinstance(value, dict):
        raise AssertionError(f"{operation} returned no value dict")
    return value


def _skill(transport, code: str) -> str:
    data = _op(transport, "basic.skill.execute", skill_code=code)
    result = data.get("result", {})
    if result.get("status") != "success":
        raise AssertionError(f"SKILL failed: {result}")
    return result.get("output", "")


def _read(transport, focus: Any = None) -> dict[str, Any]:
    fields: dict[str, Any] = {"library": LIB, "cell": CELL, "view": VIEW}
    if focus:
        fields["focus"] = focus
    return _value(transport, "virtuoso.schematic.read", **fields)


def _write(transport, commands: list[dict[str, Any]]) -> dict[str, Any]:
    """`write` 成功时 value 为 null（判据是 steps 里每条命令 ok）→ 用 _op。"""
    return _op(transport, "virtuoso.schematic.write",
               library=LIB, cell=CELL, view=VIEW, commands=commands)


def _write_fails(transport, commands: list[dict[str, Any]]) -> str:
    response = transport.call({"operation": "virtuoso.schematic.write", "token": TOKEN,
                               "library": LIB, "cell": CELL, "view": VIEW,
                               "commands": commands})
    if response.get("ok"):
        raise AssertionError(f"expected failure, got ok: {commands}")
    return str(response.get("error") or "")


class Evidence:
    """比对表：期望 / 实际 / 判定（写TB规范 §5）。"""

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


def _ensure_cell(transport) -> None:
    """② 造基线：专属 cell 从零重建（幂等：下一次运行自己还原）。"""
    _skill(
        transport,
        f'let((o) o=ddGetObj("{LIB}" "{CELL}") when(o ddDeleteObj(o))) '
        f'let((cv) cv=dbOpenCellViewByType("{LIB}" "{CELL}" "{VIEW}" '
        '"schematic" "w") unless(cv error("create failed")) '
        'unless(dbSave(cv) error("save failed")) dbClose(cv) t)',
    )


def _baseline(transport, case: str, ev: Evidence) -> None:
    """②③ 还原并校验基线：专属 cell 重建后各对象集合必须为空（每例自带前置）。"""
    _ensure_cell(transport)
    _skill(transport, f'ddGetObj("{LIB}" "{CELL}")')
    value = _read(transport)
    for key in ("instances", "labels", "wires", "pins", "notes"):
        ev.check(case, f"baseline empty ({key})", [], value.get(key))


def _near(point: Any, expected: list[float]) -> bool:
    if not isinstance(point, list) or len(point) < 2:
        return False
    try:
        return (abs(float(point[0]) - expected[0]) <= TOL
                and abs(float(point[1]) - expected[1]) <= TOL)
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------- 原子用例 --
def _case_instance_atoms(transport, ev: Evidence) -> None:
    """instance：place → rename → set_instance_params → delete（每步读回）。"""
    case = "ATOM-instance"
    _baseline(transport, "ATOM-instance", ev)
    _write(transport, [{"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PDK_NCH,
                        "master_view": "symbol", "name": "MN1", "pos": [0.0, 0.0],
                        "orient": "R0"}])
    value = _read(transport, focus="positions")
    inst = next((item for item in value.get("instances", []) if item.get("name") == "MN1"), None)
    ev.check_true(case, "place_instance visible", inst is not None, value.get("instances"))
    ev.check(case, "place_instance pos", True, _near((inst or {}).get("pos"), [0.0, 0.0]))

    _write(transport, [{"op": "rename_instance", "name": "MN1", "new_name": "MN2"}])
    names = sorted(item.get("name") for item in
                   _read(transport, focus="positions").get("instances", []))
    ev.check(case, "rename_instance", ["MN2"], names)

    _write(transport, [{"op": "set_instance_params", "name": "MN2",
                        "params": {"l": "180n", "w": "1u"}}])
    params = next((item.get("params") for item in
                   _read(transport, focus="params").get("instances", [])
                   if item.get("name") == "MN2"), None) or {}
    ev.check(case, "set_instance_params l", "180n", str(params.get("l", "")).lower())
    ev.check(case, "set_instance_params w", "1u", str(params.get("w", "")).lower())

    _write(transport, [{"op": "delete_instance", "name": "MN2"}])
    names = [item.get("name") for item in _read(transport, focus="positions").get("instances", [])]
    ev.check(case, "delete_instance", [], names)


def _case_term_nets(transport, ev: Evidence) -> None:
    """set_term_nets：四个端子挂网 → connectivity 读回 nets + stub labels。"""
    case = "ATOM-set_term_nets"
    _baseline(transport, "ATOM-set_term_nets", ev)
    _write(transport, [{"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PDK_NCH,
                        "master_view": "symbol", "name": "MN1", "pos": [0.0, 0.0]}])
    _write(transport, [{"op": "set_term_nets", "name": "MN1",
                        # 显式 stub_length：回归 `(0.5)` 被 SKILL 当函数调用的老 bug。
                        # 取 0.1（小于引脚间距），0.5 会跨过相邻引脚（默认值之所以是 rbHw+0.05）。
                        "stub_length": 0.1,
                        "term_nets": {"G": "vin", "D": "vout", "S": "vss", "B": "vss"}}])
    conn = _read(transport, focus="connectivity")     # nets 在 connectivity
    nets = sorted(conn.get("nets") or {})
    ev.check_true(case, "nets carry terminal nets", {"vin", "vout", "vss"} <= set(nets), nets)
    labels = sorted(item.get("text") for item in                    # stub label 在 positions
                    _read(transport, focus="positions").get("labels", []))
    ev.check_true(case, "stub labels created", {"vin", "vout", "vss"} <= set(labels), labels)
    _write(transport, [{"op": "delete_instance", "name": "MN1"}])


def _case_wire_atoms(transport, ev: Evidence) -> None:
    """wire：place → set_wire_properties → delete（按 points 索引）。"""
    case = "ATOM-wire"
    _baseline(transport, "ATOM-wire", ev)
    points = [[0.0, 0.0], [2.0, 0.0]]
    _write(transport, [{"op": "place_wire", "points": points}])
    wires = _read(transport, focus="positions").get("wires", [])
    ev.check(case, "place_wire count", 1, len(wires))
    first = (wires[0].get("points") if wires else None) or [None, None]
    ev.check_true(case, "place_wire points", _near(first[0], points[0]) and _near(first[1], points[1]),
                  wires)

    _write(transport, [{"op": "set_wire_properties", "points": points,
                        "width": 0.1, "color": "yellow"}])
    wire = (_read(transport, focus="positions").get("wires") or [{}])[0]
    ev.check(case, "set_wire_properties width", 0.1, round(float(wire.get("width") or 0.0), 3))
    ev.check(case, "set_wire_properties color", "yellow", wire.get("color"))

    _write(transport, [{"op": "delete_wire", "points": points}])
    ev.check(case, "delete_wire", [], _read(transport, focus="positions").get("wires", []))


def _case_label_atoms(transport, ev: Evidence) -> None:
    """label：place → rename → set → delete（pos 索引）。"""
    case = "ATOM-label"
    _baseline(transport, "ATOM-label", ev)
    pos = [1.0, 1.0]
    _write(transport, [{"op": "place_label", "text": "n1", "pos": pos}])
    labels = _read(transport, focus="positions").get("labels", [])
    ev.check_true(case, "place_label visible",
                  any(item.get("text") == "n1" and _near(item.get("pos"), pos)
                      for item in labels), labels)

    _write(transport, [{"op": "rename_label", "pos": pos, "new_text": "n2"}])
    ev.check(case, "rename_label", ["n2"],
             sorted(item.get("text") for item in
                    _read(transport, focus="positions").get("labels", [])))

    _write(transport, [{"op": "set_label_properties", "pos": pos, "height": 0.2}])
    label = next((item for item in _read(transport, focus="positions").get("labels", [])
                  if item.get("text") == "n2"), {})
    ev.check(case, "set_label_properties height", 0.2, round(float(label.get("height") or 0), 4))

    _write(transport, [{"op": "delete_label", "pos": pos, "text": "n2"}])
    ev.check(case, "delete_label", [], _read(transport, focus="positions").get("labels", []))


def _case_pin_atoms(transport, ev: Evidence) -> None:
    """pin：place → rename → set_pin_properties → delete（pos 索引）。

    P-073 验收口径：判据必须落在**下游可见的 pin 名（terminal 名）**上，
    不是自动生成的 pin 实例名（PIN0）。所以改名/改方向后同时查
    `read(connectivity)` 与 `symbol.generate` 出来的端口名。
    """
    case = "ATOM-pin"
    _baseline(transport, "ATOM-pin", ev)
    pos = [-3.0, 0.0]
    _write(transport, [{"op": "place_pin", "name": "P1", "direction": "input", "pos": pos}])
    pins = _read(transport, focus="positions").get("pins", [])
    # 位置模式读回的是 pin 图形实例名（自动 PINn）+ 方向 + pos；业务名（terminal）见 connectivity。
    ev.check(case, "place_pin count", 1, len(pins))
    ev.check_true(case, "place_pin pos", _near((pins[0] if pins else {}).get("pos"), pos), pins)
    ev.check(case, "place_pin direction", "input",
             (pins[0] if pins else {}).get("direction"))
    conn = _read(transport, focus="connectivity").get("pins", [])
    ev.check(case, "place_pin business name", ["P1"], sorted(item.get("name") for item in conn))

    _write(transport, [{"op": "rename_pin", "pos": pos, "new_name": "P2"}])
    conn = _read(transport, focus="connectivity").get("pins", [])
    ev.check(case, "rename_pin (read 的业务名)", ["P2"],
             sorted(item.get("name") for item in conn))
    _op(transport, "virtuoso.symbol.generate", library=LIB, cell=CELL,
        schematic_view=VIEW, symbol_view="symbol", overwrite=True)
    terms = _value(transport, "virtuoso.symbol.read", library=LIB, cell=CELL,
                   view="symbol", focus=["terms"]).get("terms", [])
    ev.check(case, "rename_pin（symbol 端口名）", ["P2"],
             sorted(item.get("name") for item in terms))

    _write(transport, [{"op": "set_pin_properties", "pos": pos, "direction": "output"}])
    conn = _read(transport, focus="connectivity").get("pins", [])
    ev.check(case, "set_pin_properties direction", ["output"],
             sorted(item.get("direction") for item in conn))
    ev.check(case, "set_pin_properties 不改名（P-073）", ["P2"],
             sorted(item.get("name") for item in conn))

    _write(transport, [{"op": "delete_pin", "pos": pos}])
    ev.check(case, "delete_pin", [],
             _read(transport, focus="connectivity").get("pins", []))


def _case_note_atoms(transport, ev: Evidence) -> None:
    """note：place → rename → set → delete（pos 索引）。

    注意：`read` 的 NOTES 段只在**不填 focus（all）**时输出（spec §1.1），
    所以本用例读回用 all-mode。
    """
    case = "ATOM-note"
    _baseline(transport, "ATOM-note", ev)
    pos = [3.0, 3.0]
    _write(transport, [{"op": "place_note", "text": "note1", "pos": pos}])
    notes = _read(transport).get("notes", [])
    ev.check_true(case, "place_note visible",
                  any(item.get("text") == "note1" and _near(item.get("pos"), pos)
                      for item in notes), notes)

    _write(transport, [{"op": "rename_note", "pos": pos, "new_text": "note2"}])
    ev.check(case, "rename_note", ["note2"],
             sorted(item.get("text") for item in _read(transport).get("notes", [])))

    _write(transport, [{"op": "set_note_properties", "pos": pos, "height": 0.1}])
    note = next((item for item in _read(transport).get("notes", [])
                 if item.get("text") == "note2"), {})
    ev.check(case, "set_note_properties height", 0.1, round(float(note.get("height") or 0), 4))

    _write(transport, [{"op": "delete_note", "pos": pos, "text": "note2"}])
    ev.check(case, "delete_note", [], _read(transport).get("notes", []))


def _case_negative(transport, ev: Evidence) -> None:
    """负控制：`xy` / 拆字段必须被拒，且错误里点名 `pos`（P-074 验收判据）。"""
    case = "NEG-pos"
    _baseline(transport, case, ev)
    for bad in ({"op": "delete_pin", "xy": [0.0, 0.0]},
                {"op": "place_label", "text": "x", "x": 0.0, "y": 0.0},
                {"op": "place_pin", "name": "PX", "direction": "input"}):
        error = _write_fails(transport, [bad])
        ev.check_true(case, f"reject {bad.get('op')}:{sorted(set(bad) - {'op'})}",
                      "pos" in error, error[:160])
    ev.check(case, "nothing created", [], _read(transport, focus="positions").get("pins", []))


def _case_read_filters(transport, ev: Evidence) -> None:
    """read：focus=positions 与 object_filter=none（读侧契约）。"""
    case = "READ-filters"
    _baseline(transport, "READ-filters", ev)
    _write(transport, [{"op": "place_instance", "master_lib": PDK_LIB, "master_cell": PDK_NCH,
                        "master_view": "symbol", "name": "MN1", "pos": [0.0, 0.0]}])
    value = _read(transport, focus="positions")
    ev.check_true(case, "positions returns instances", bool(value.get("instances")),
                  value.get("instances"))
    filtered = _value(transport, "virtuoso.schematic.read", library=LIB, cell=CELL, view=VIEW,
                      focus="positions",
                      object_filter={"instance": "none", "label": "none", "pin": "none",
                                     "note": "none", "wire": "none"})
    ev.check(case, "object_filter none", [], filtered.get("instances"))
    _write(transport, [{"op": "delete_instance", "name": "MN1"}])


def _case_check_and_save(transport, ev: Evidence) -> None:
    case = "CHECK-01"
    data = _op(transport, "virtuoso.schematic.check_and_save",
               library=LIB, cell=CELL, view=VIEW)
    ev.check_true(case, "check_and_save ok", bool(data.get("ok")), data)


def _case_screenshot(transport, ev: Evidence) -> None:
    case = "SHOT-01"
    _skill(transport, f'deOpenCellView("{LIB}" "{CELL}" "{VIEW}" "schematic" nil "r")')
    try:
        value = _op(transport, "virtuoso.schematic.screenshot",
                    library=LIB, cell=CELL, view=VIEW, leave_open=True)
        path = Path(str(value.get("local_path") or ""))
        ev.check_true(case, "screenshot file non-empty",
                      path.is_file() and path.stat().st_size > 0, str(path))
    finally:
        _skill(transport,
               'let((w) foreach(x hiGetWindowList() '
               f'when(x~>cellView && x~>cellView~>cellName == "{CELL}" w = x)) '
               "when(w hiCloseWindow(w)))")


CASES: tuple[tuple[str, Callable[[Any, Evidence], None]], ...] = (
    ("ATOM-instance", _case_instance_atoms),
    ("ATOM-set_term_nets", _case_term_nets),
    ("ATOM-wire", _case_wire_atoms),
    ("ATOM-label", _case_label_atoms),
    ("ATOM-pin", _case_pin_atoms),
    ("ATOM-note", _case_note_atoms),
    ("NEG-pos", _case_negative),
    ("READ-filters", _case_read_filters),
    ("CHECK-01", _case_check_and_save),
    ("SHOT-01", _case_screenshot),
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
        # ① 环境检查（不满足直接失败，不 skip、不换环境）
        from env_check import require_environment

        options: dict[str, Any] = {"token": TOKEN, "expect_host": "GLIS-DESKTOP",
                                   "require_lib": [LIB, PDK_LIB]}
        env_report = (require_environment(base=args.base, **options) if args.transport == "http"
                      else require_environment(work_dir=str(WORK_DIR), **options))

        # ②③ 造基线 + 校验基线（每个用例内部还会各自还原一次）
        _baseline(transport, "BASELINE", ev)

        # ④⑤⑥ 逐个原子：执行 + 读回比对
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
            / f"schematic-atoms-{dt.datetime.now():%Y%m%d-%H%M}"
            / "schematic-atoms-green.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({
            "tb": "test/live/packages/schematic_e2e_tests.py",
            "transport": args.transport,
            "token": TOKEN, "lib": LIB, "cell": CELL, "view": VIEW,
            "pdk": f"{PDK_LIB}/{PDK_NCH}",
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

