# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 22:15
# 依赖: 无
# =======================================================================
"""层次化 ``symbol.generate`` 句柄/幂等半真机探针（真机 direct dispatch）。

六步流程（test/docs/写TB规范.md §1）：
① `require_environment`；②③ **自己造前置**（leaf/top 两张原理图 + 读回确认）；
④ generate（leaf → top → 再 generate leaf）；⑤ 读回 symbol 的端口/实例与视图开关状态；
⑥ 不清理现场；证据落 `test/artifacts/evidence/symbol-hierarchy-handle/*.json`。

背景（旧版探针的坑）：旧版用不存在的库 SRX65 当基线，三轮 generate 全部报
"source schematic not found" 却仍判 clean，是**假绿**。本版基线建在 `schemtest`
下并读回校验，失败即 FAIL。

判据：leaf/top 两次 generate 都 ok，且生成后 symbol view 处于 CLOSED；
再对 leaf 做一次 overwrite generate 也必须 ok（回归 target symbol is open）。

用法::

    PYTHONPATH=src python test/semi/probes/symbol_generate_hierarchy_handle_probe.py
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "test" / "shared" / "runners"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "artifacts" / "env" / "log-vblog"
LIB = "schemtest"
LEAF, TOP = "sym_hier_leaf", "sym_hier_top"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--token", default=TOKEN)
    parser.add_argument("--work-dir", default=str(WORK_DIR))
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    from common.paths import init_work_dir
    from pyapi.packages import cellview as cv
    from pyapi.packages import schematic as sch
    from pyapi.packages import symbol as sym
    from transport.middle import BusinessServer
    from env_check import require_environment

    env = require_environment(work_dir=args.work_dir, token=args.token,
                              expect_host="GLIS-DESKTOP", require_lib=[LIB])
    init_work_dir(args.work_dir)
    middle = BusinessServer()
    comparisons: list[dict[str, object]] = []
    steps: list[dict[str, object]] = []
    verdict = "FAIL"
    try:
        cvp, schp, symp = cv.Package(middle), sch.Package(middle), sym.Package(middle)

        def record(name: str, expected: object, actual: object) -> None:
            comparisons.append({"check": name, "expected": expected, "actual": actual,
                                "verdict": "PASS" if expected == actual else "FAIL"})
            if expected != actual:
                raise AssertionError(f"{name}: expected {expected!r}, actual {actual!r}")

        def symbol_open(cell: str) -> str:
            res = middle.execute_skill(
                f'if(dbFindOpenCellViewByName("{LIB}" "{cell}" "symbol") "OPEN" "CLOSED")',
                timeout=60, token=args.token)
            return (res.output or "").strip().strip('"')

        def view_exists(cell: str, view: str) -> bool:
            res = middle.execute_skill(
                f'let((views) views = when(ddGetObj("{LIB}" "{cell}") '
                f'ddGetObj("{LIB}" "{cell}")~>views~>name) '
                f'car(setof(x views x == "{view}")))', timeout=60, token=args.token)
            return view in (res.output or "")

        # ② 造前置：leaf/top 的旧视图先删干净
        for cell in (TOP, LEAF):
            for view in ("symbol", "schematic"):
                try:
                    cvp.view_delete(cv.ViewDeleteRequest(token=args.token, library=LIB,
                                                         cell=cell, view=view))
                except Exception:  # noqa: BLE001
                    pass

        # ③ leaf：建 schematic + 一个 pin + 读回
        record("baseline view.create leaf", True,
               bool(cvp.view_create(cv.ViewCreateRequest(
                   token=args.token, library=LIB, cell=LEAF, view="schematic",
                   view_type="schematic")).ok))
        record("baseline write leaf pin", True,
               bool(schp.write(sch.WriteRequest(
                   token=args.token, library=LIB, cell=LEAF, view="schematic",
                   commands=[{"op": "place_pin", "name": "A", "direction": "input",
                              "pos": [0.0, 0.0]}])).ok))
        read_leaf = schp.read(sch.ReadRequest(token=args.token, library=LIB, cell=LEAF,
                                              view="schematic", focus="positions"))
        record("baseline leaf pin visible", 1, len((read_leaf.value or {}).get("pins") or []))

        # ④a generate leaf → ⑤ 读回端口 + 视图关闭
        leaf_gen = symp.generate(sym.GenerateRequest(
            token=args.token, library=LIB, cell=LEAF,
            schematic_view="schematic", symbol_view="symbol"))
        steps.append({"step": "generate leaf", "ok": bool(leaf_gen.ok), "error": leaf_gen.error})
        record("generate leaf ok", True, bool(leaf_gen.ok))
        record("symbol closed after leaf generate", "CLOSED", symbol_open(LEAF))
        leaf_read = symp.read(sym.ReadRequest(token=args.token, library=LIB, cell=LEAF,
                                              view="symbol", focus=["terms"]))
        record("leaf symbol has port A", ["A"],
               [item.get("name") for item in ((leaf_read.value or {}).get("terms") or [])])

        # ④b top：建 schematic + 实例化 leaf symbol → 读回实例
        record("baseline view.create top", True,
               bool(cvp.view_create(cv.ViewCreateRequest(
                   token=args.token, library=LIB, cell=TOP, view="schematic",
                   view_type="schematic")).ok))
        record("baseline write top instance", True,
               bool(schp.write(sch.WriteRequest(
                   token=args.token, library=LIB, cell=TOP, view="schematic",
                   commands=[{"op": "place_instance", "master_lib": LIB, "master_cell": LEAF,
                              "master_view": "symbol", "name": "X1",
                              "pos": [0.0, 0.0]}])).ok))
        top_read = schp.read(sch.ReadRequest(token=args.token, library=LIB, cell=TOP,
                                             view="schematic", focus="positions"))
        record("top instance visible", ["X1"],
               [item.get("name") for item in ((top_read.value or {}).get("instances") or [])])

        top_gen = symp.generate(sym.GenerateRequest(
            token=args.token, library=LIB, cell=TOP,
            schematic_view="schematic", symbol_view="symbol"))
        steps.append({"step": "generate top", "ok": bool(top_gen.ok), "error": top_gen.error})
        record("generate top ok", True, bool(top_gen.ok))
        record("symbol closed after top generate", "CLOSED", symbol_open(TOP))
        record("top symbol view exists", True, view_exists(TOP, "symbol"))

        # ④c 再 generate leaf（overwrite）→ 回归 target symbol is open
        again = symp.generate(sym.GenerateRequest(
            token=args.token, library=LIB, cell=LEAF,
            schematic_view="schematic", symbol_view="symbol", overwrite=True))
        steps.append({"step": "regenerate leaf", "ok": bool(again.ok), "error": again.error})
        record("regenerate leaf ok (no handle leak)", True, bool(again.ok))
        record("symbol closed after regenerate", "CLOSED", symbol_open(LEAF))
        verdict = "PASS"
    except AssertionError as exc:
        steps.append({"step": "assertion", "ok": False, "error": str(exc)})
    finally:
        middle.close()

    out = Path(args.out) if args.out else (
        ROOT / "test" / "artifacts" / "evidence" / "symbol-hierarchy-handle"
        / f"symbol-hierarchy-{dt.datetime.now():%Y%m%d-%H%M%S}-{verdict.lower()}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "tb": "test/semi/probes/symbol_generate_hierarchy_handle_probe.py",
        "token": args.token, "lib": LIB, "leaf": LEAF, "top": TOP,
        "env": env, "steps": steps, "comparisons": comparisons, "verdict": verdict,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": verdict, "steps": steps}, ensure_ascii=False))
    print(f"evidence: {out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

