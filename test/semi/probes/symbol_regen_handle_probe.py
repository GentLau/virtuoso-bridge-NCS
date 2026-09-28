# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 22:05
# 依赖: 无
# =======================================================================
"""``symbol.generate`` 句柄/幂等半真机探针（真机 direct dispatch）。

六步流程（test/docs/写TB规范.md §1）：
① `require_environment`（靶机指纹 + schemtest 可见）；
②③ **自己造前置**：`schemtest/sym_regen_probe` 的 schematic（一个 pin）→ 读回确认存在
   （旧版探针用不存在的库 SRX65，三轮全失败还被判"clean"，是假绿——本版修掉）；
④ 连续三次 `symbol.generate`（中间含一次人工关窗）；⑤ 每次读回
   `dbFindOpenCellViewByName(<lib> <cell> "symbol")` 与 generate 的 ok；
⑥ 不清理现场；证据落 `test/artifacts/evidence/symbol-regen-handle/*.json`。

判据（强判据，不再"失败也算 clean"）：
  三次 generate 都必须 ok；每次 generate 之后 symbol view **不得**处于打开态。

用法::

    PYTHONPATH=src python test/semi/probes/symbol_regen_handle_probe.py
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
LIB, CELL = "schemtest", "sym_regen_probe"


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

    # ① 环境检查（不通过直接失败并如实上报）
    env = require_environment(work_dir=args.work_dir, token=args.token,
                              expect_host="GLIS-DESKTOP", require_lib=[LIB])
    init_work_dir(args.work_dir)
    middle = BusinessServer()
    comparisons: list[dict[str, object]] = []
    try:
        def record(name: str, expected: object, actual: object) -> None:
            comparisons.append({"check": name, "expected": expected, "actual": actual,
                                "verdict": "PASS" if expected == actual else "FAIL"})
            if expected != actual:
                raise AssertionError(f"{name}: expected {expected!r}, actual {actual!r}")

        # ②③ 造前置：先删旧图 → 建 schematic → 放一个 pin → 保存 → 读回确认
        try:
            cv.Package(middle).view_delete(cv.ViewDeleteRequest(
                token=args.token, library=LIB, cell=CELL, view="schematic"))
        except Exception:  # noqa: BLE001 - 不存在就继续
            pass
        created = cv.Package(middle).view_create(cv.ViewCreateRequest(
            token=args.token, library=LIB, cell=CELL, view="schematic",
            view_type="schematic"))
        record("baseline view.create", True, bool(created.ok))
        wrote = sch.Package(middle).write(sch.WriteRequest(
            token=args.token, library=LIB, cell=CELL, view="schematic",
            commands=[{"op": "place_pin", "name": "P1", "direction": "input",
                       "pos": [0.0, 0.0]}]))
        record("baseline schematic.write", True, bool(wrote.ok))
        read = sch.Package(middle).read(sch.ReadRequest(
            token=args.token, library=LIB, cell=CELL, view="schematic",
            focus="positions"))
        pins = (read.value or {}).get("pins") or []
        record("baseline pin visible", 1, len(pins))

        def symbol_open() -> str:
            res = middle.execute_skill(
                f'if(dbFindOpenCellViewByName("{LIB}" "{CELL}" "symbol") "OPEN" "CLOSED")',
                timeout=60, token=args.token)
            return (res.output or "").strip().strip('"')

        results: list[dict[str, object]] = []
        for attempt in (1, 2, 3):
            if attempt == 3:
                # ③ 人为关掉可能残留的 symbol view，再试一次
                middle.execute_skill(
                    f'let((cv) cv = dbFindOpenCellViewByName("{LIB}" "{CELL}" "symbol") '
                    "when(cv dbClose(cv)))", timeout=60, token=args.token)
            generated = sym.Package(middle).generate(sym.GenerateRequest(
                token=args.token, library=LIB, cell=CELL,
                schematic_view="schematic", symbol_view="symbol",
                overwrite=(attempt > 1)))
            state = symbol_open()
            results.append({"attempt": attempt, "generate_ok": bool(generated.ok),
                            "error": generated.error, "symbol_open_after": state})
            record(f"generate#{attempt} ok", True, bool(generated.ok))
            record(f"generate#{attempt} leaves symbol closed", "CLOSED", state)
        verdict = "PASS" if all(r["generate_ok"] for r in results) else "FAIL"
    finally:
        middle.close()

    out = Path(args.out) if args.out else (
        ROOT / "test" / "artifacts" / "evidence" / "symbol-regen-handle"
        / f"symbol-regen-{dt.datetime.now():%Y%m%d-%H%M%S}-{verdict.lower()}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({
        "tb": "test/semi/probes/symbol_regen_handle_probe.py",
        "token": args.token, "lib": LIB, "cell": CELL,
        "env": env, "results": results, "comparisons": comparisons, "verdict": verdict,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"verdict": verdict, "results": results}, ensure_ascii=False))
    print(f"evidence: {out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
