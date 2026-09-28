"""Instrument dispatch while each e2e suite runs; report operations exercised."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

import server.dispatch as dispatch_module  # noqa: E402
import server.api_server as api_server_module  # noqa: E402

SUITES = [
    "infra_e2e_tests.py",
    "cellview_e2e_tests.py",
    "schematic_e2e_tests.py",
    "symbol_e2e_tests.py",
    "layout_e2e_tests.py",
    "verilog_e2e_tests.py",
    "veriloga_e2e_tests.py",
    "skillref_e2e_tests.py",
    "spectre_e2e_tests.py",
    "maestro_e2e_tests.py",
]

seen: dict[str, set[str]] = {}
errors: list[str] = []
original = dispatch_module.dispatch


def recording_dispatch(middle, payload, *args, **kwargs):
    operation = payload.get("operation")
    if isinstance(operation, str):
        current = sys._getframe(2).f_globals.get("__name__")
        if current not in seen:
            seen[current] = set()
        seen[current].add(operation)
    return original(middle, payload, *args, **kwargs)


dispatch_module.dispatch = recording_dispatch

first_done = False
for suite in SUITES:
    name = suite[:-3]
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "test" / "live" / "packages" / suite
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    transport = module.DirectTransport()
    if not first_done:
        api_server_module.register_packages = lambda: {}
        first_done = True
    # 一个套件抛异常不该让整份覆盖报告消失（2026-09-23：layout 卡 P-044 时
    # 本脚本整体中断，ops_used.json 一直是 9/22 的旧数据）。
    try:
        results = module.run_suite(transport)
        error = ""
    except Exception as exc:  # noqa: BLE001 - 记下来继续跑剩下的套件
        results = None
        error = f"{type(exc).__name__}: {exc}"
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    if results is None:
        errors.append(f"{suite}: {error}")
        print(f"{suite:28} direct=ERROR ops={len(seen.get(name, ()))} {error}")
    else:
        ok = all(status == "PASS" for _, status in results)
        print(f"{suite:28} direct={'PASS' if ok else 'FAIL'} ops={len(seen.get(name, ()))}")

all_ops = set(dispatch_module.operations())
covered = set().union(*seen.values()) if seen else set()
print("\nTOTAL registered:", len(all_ops))
print("TOTAL covered:", len(covered))
print("UNCOVERED:", sorted(all_ops - covered))

out = {
    "registered": sorted(all_ops),
    "covered": sorted(covered),
    "uncovered": sorted(all_ops - covered),
    "by_suite": {key: sorted(value) for key, value in seen.items()},
    "suite_errors": errors,
}
path = ROOT / "test" / "artifacts" / "evidence" / "http-e2e" / "ops_used.json"
path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
print("written:", path)
if errors:
    print("SUITES WITH ERRORS:", "; ".join(errors))
    raise SystemExit(1)
