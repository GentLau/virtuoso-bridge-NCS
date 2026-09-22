"""End-to-end acceptance tests for ``virtuoso.cellview.*`` (lib/cell/view/cat CRUD)."""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
WORK_DIR = ROOT / "test" / "tb" / "artifacts" / "log-vblog"


class HttpTransport:
    middle = None

    def call(self, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            API, data=body, headers={"Content-Type": "application/json"}, method="POST",
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


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _value(transport, operation: str, **fields: Any) -> Any:
    return _op(transport, operation, **fields).get("value")


def run_suite(transport) -> list[tuple[str, str]]:
    results: list[tuple[str, str]] = []
    prefix = "virtuoso.cellview."

    def run(name: str, func: Callable[[], Any]) -> None:
        try:
            func()
            results.append((name, "PASS"))
        except Exception as exc:  # noqa: BLE001
            results.append((name, f"FAIL: {type(exc).__name__}: {exc}"))
            raise

    def case() -> None:
        # existing-library read ops
        libs = _value(transport, prefix + "lib.list")
        _check(isinstance(libs, list) and "schemtest" in libs, f"lib.list: {libs}")
        info = _value(transport, prefix + "lib.get", library="schemtest")
        _check(isinstance(info, dict) and info.get("path"), f"lib.get: {info}")
        cats = _value(transport, prefix + "cat.list", library="schemtest")
        _check(cats is None or isinstance(cats, list), f"cat.list: {cats}")

        # scratch library lifecycle
        lib = "cv_e2e_lib"
        lib2 = "cv_e2e_lib2"
        lib_copy = "cv_e2e_copy"
        path = f"/home/Gent/.virtuoso-bridge/vblog/{lib}"
        for name in (lib, lib2, lib_copy):
            try:
                _op(transport, prefix + "lib.delete", library=name)
            except AssertionError:
                pass
        _op(transport, prefix + "lib.create", library=lib, path=path)
        _op(transport, prefix + "lib.bind", library=lib,
            technology_library="cdsDefTechLib")
        _op(transport, prefix + "lib.rename", library=lib, new_name=lib2)
        listed = _value(transport, prefix + "lib.list")
        _check(lib2 in listed, f"lib rename not visible: {listed}")

        # view + cell lifecycle
        cell = "cv_e2e_cell"
        _op(transport, prefix + "view.create", library=lib2, cell=cell,
            view="schematic", view_type="schematic")
        views = _value(transport, prefix + "view.list", library=lib2, cell=cell)
        _check(isinstance(views, list) and "schematic" in [str(item[0]) for item in views],
               f"view.list: {views}")
        cells = _value(transport, prefix + "cell.list", library=lib2)
        _check(cell in [str(item) for item in cells], f"cell.list: {cells}")
        _op(transport, prefix + "view.copy", library=lib2, cell=cell,
            view="schematic", new_library=lib2, new_cell=cell, new_view="schematic_copy")
        _op(transport, prefix + "view.rename", library=lib2, cell=cell,
            view="schematic_copy", new_name="schematic_copy2")
        _op(transport, prefix + "view.delete", library=lib2, cell=cell,
            view="schematic_copy2")
        _op(transport, prefix + "cell.copy", library=lib2, cell=cell,
            new_library=lib2, new_cell="cv_e2e_cell_copy")
        _op(transport, prefix + "cell.rename", library=lib2,
            cell="cv_e2e_cell_copy", new_name="cv_e2e_cell_copy2")
        _op(transport, prefix + "cell.delete", library=lib2,
            cell="cv_e2e_cell_copy2")

        # category lifecycle
        cat = "cv_e2e_cat"
        _op(transport, prefix + "cat.create", library=lib2, category=cat)
        cats = _value(transport, prefix + "cat.list", library=lib2) or []
        _check(cat in cats, f"cat.list after create: {cats}")
        _op(transport, prefix + "cat.add_cell", library=lib2, category=cat, cell=cell)
        cat_cells = _value(transport, prefix + "cell.list", library=lib2, category=cat)
        _check(cell in [str(item) for item in cat_cells], f"cat cells: {cat_cells}")
        _op(transport, prefix + "cat.remove_cell", library=lib2, category=cat, cell=cell)
        _op(transport, prefix + "cat.rename", library=lib2, category=cat,
            new_name="cv_e2e_cat2")
        _op(transport, prefix + "cat.delete", library=lib2, category="cv_e2e_cat2")

        # library copy + cleanup
        _op(transport, prefix + "lib.copy", library=lib2, new_library=lib_copy,
            new_path=f"/home/Gent/.virtuoso-bridge/vblog/{lib_copy}")
        _op(transport, prefix + "lib.delete", library=lib_copy)
        _op(transport, prefix + "lib.delete", library=lib2)
        remaining = _value(transport, prefix + "lib.list")
        _check(lib2 not in remaining and lib_copy not in remaining,
               f"lib cleanup failed: {remaining}")

    run("CELLVIEW-01 full CRUD", case)
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=("direct", "http"), default="direct")
    args = parser.parse_args()
    transport = HttpTransport() if args.transport == "http" else DirectTransport()
    try:
        results = run_suite(transport)
    finally:
        middle = getattr(transport, "middle", None)
        if middle is not None:
            middle.close()
    for name, status in results:
        print(f"{status:6}  {name}")
    return 0 if results and all(status == "PASS" for _, status in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
