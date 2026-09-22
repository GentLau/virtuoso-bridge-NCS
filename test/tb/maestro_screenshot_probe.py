"""Real-machine probe for the Maestro screenshot parity path."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "test" / "tb"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

DIRECT = "--direct" in sys.argv
if DIRECT:
    sys.path.insert(0, str(ROOT / "src"))
    from common.paths import init_work_dir  # noqa: E402
    from server import dispatch as dispatch_module  # noqa: E402
    from server.api_server import register_packages  # noqa: E402
    from transport.middle import BusinessServer  # noqa: E402

    init_work_dir(str(ROOT / "test" / "tb" / "artifacts" / "log-vblog"))
    register_packages()
    _middle = BusinessServer()

    def api_call(operation: str, **fields):
        _, body = dispatch_module.dispatch(
            _middle, {"operation": operation, "token": "vb-vblog", **fields},
        )
        return body

    def api_data(operation: str, **fields):
        env = api_call(operation, **fields)
        if not env.get("ok"):
            raise RuntimeError(f"{operation} failed: {env.get('error')}")
        return env["data"]
else:
    from _maestro_tb import call as api_call, data as api_data  # noqa: E402


def one(label: str, **extra) -> dict:
    response = api_call(
        "virtuoso.maestro.export",
        library="maestro_tb",
        cell="rc_probe",
        kind="screenshot",
        **extra,
    )
    print(f"--- {label} ok={response.get('ok')}")
    data_obj = response.get("data") or {}
    value = data_obj.get("value") or {}
    if value:
        print(json.dumps(value, ensure_ascii=False, indent=2))
    else:
        print("error:", response.get("error"))
    return response


def main() -> int:
    gui = api_data(
        "virtuoso.maestro.open_gui",
        library="maestro_tb",
        cell="rc_probe",
    )
    window = gui["value"]["window"]
    print("maestro window:", window)

    default = one("default")
    by_window = one("window_id", window_id=window)
    region = one("region", window_id=window, region=[-1, -1, 1, 1])
    not_top = one("toplevel false", window_id=window, toplevel=False)
    bad = one("bad window id (expected failure)", window_id=999999)

    ok = (
        default.get("ok")
        and by_window.get("ok")
        and region.get("ok")
        and not_top.get("ok")
        and not bad.get("ok")
    )
    for label, response in (
        ("default", default), ("window_id", by_window),
        ("region", region), ("toplevel_false", not_top),
    ):
        value = (response.get("data") or {}).get("value") or {}
        path = value.get("local_path")
        if path:
            p = Path(path)
            print(f"{label}: file={p.is_file()} size={p.stat().st_size if p.is_file() else 0}")
    print("screenshot parity:", "PASS" if ok else "FAIL")
    if DIRECT:
        _middle.close()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
