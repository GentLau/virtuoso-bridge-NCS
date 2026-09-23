"""S11 - end-to-end engineering flow on a real PDK: spec -> schematic -> symbol
-> layout -> GDS -> DRC -> LVS -> (pre / post) simulation.

Why this scenario exists
------------------------
Every per-package TB proves one operation in isolation.  This scenario drives
the *chain* a real designer walks, on the real machine, with the TSMC 65nm
PDK:  the failure modes that matter in production (state left behind by an
earlier step, a view that exists but is empty, a GDS that DRC accepts but LVS
cannot compare) only appear when the steps run back to back.

    python test/live/flows/s11_full_flow.py                       # all stages
    python test/live/flows/s11_full_flow.py --only lib,schematic  # prefix run
    python test/live/flows/s11_full_flow.py --run-dir <dir>       # evidence dir

Evidence: <run-dir>/s11-<stage>.json per stage + <run-dir>/summary.json.
Each stage records the exact request payload, the raw response and the verdict,
so a failure can be replayed without guessing which call produced it.

Environment: business API on 127.0.0.1:8127 with a token whose registry entry
points at a real Virtuoso (default ``vb-vblog`` = wsl-gent CIW pid 369800),
PDK at /opt/eda/PDK/CRN65GPNEW/CRN65GPNEW.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
PDK = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW"
PDK_LIB = "tsmcN65"
LIB = "s11_inv"
CELL = "inv"
TECH_LIB = "tsmcN65"
REMOTE_LIB_DIR = f"/home/Gent/project/vblog/{LIB}"
REMOTE_WORK = f"/home/Gent/project/vblog/{LIB}/s11"


def call(operation: str, token: str, **fields):
    body = json.dumps({"operation": operation, "token": token, **fields}).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=1800) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


class Runner:
    def __init__(self, token: str, run_dir: Path, only: list[str] | None) -> None:
        self.token = token
        self.run_dir = run_dir
        self.only = set(only) if only else None
        self.results: list[dict] = []
        self.state: dict = {}
        run_dir.mkdir(parents=True, exist_ok=True)

    def want(self, stage: str) -> bool:
        return self.only is None or stage in self.only

    def record(self, stage: str, payload: dict, response: dict, verdict: str, note: str = ""):
        entry = {
            "stage": stage,
            "verdict": verdict,
            "note": note,
            "request": payload,
            "response": response,
        }
        (self.run_dir / f"s11-{stage}.json").write_text(
            json.dumps(entry, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        self.results.append({"stage": stage, "verdict": verdict, "note": note})
        print(f"{verdict:<6} {stage:<10} {note}")


def skill(runner: Runner, code: str, timeout: float = 900) -> dict:
    return call("basic.skill.execute", runner.token, skill_code=code, timeout=timeout)


def skill_ok(response: dict) -> tuple[bool, str]:
    data = (response or {}).get("data") or {}
    result = data.get("result") or {}
    status = result.get("status")
    output = (result.get("output") or "").strip()
    errors = result.get("errors") or []
    return status == "success", output or "; ".join(errors)


# --------------------------------------------------------------------- stages
def stage_lib(runner: Runner) -> None:
    payload = {
        "operation": "virtuoso.cellview.lib.create",
        "library": LIB,
        "path": REMOTE_LIB_DIR,
        "technology_library": TECH_LIB,
    }
    response = call("virtuoso.cellview.lib.create", runner.token,
                    library=LIB, path=REMOTE_LIB_DIR, technology_library=TECH_LIB)
    if not response.get("ok") and "technology" in str(response.get("error", "")).lower():
        # The PDK's tech attachment name is not always the library name; a
        # library without a tech database is enough for schematic/symbol work
        # and layout can be attached later with lib.bind.
        response = call("virtuoso.cellview.lib.create", runner.token,
                        library=LIB, path=REMOTE_LIB_DIR)
        payload["technology_library"] = "<dropped: technologyLibraryNotFound>"
    if not response.get("ok"):
        response2 = call("virtuoso.cellview.lib.get", runner.token, library=LIB)
        if response2.get("ok"):
            runner.record("lib", payload, response2, "PASS", "library already present")
            return
        runner.record("lib", payload, response, "FAIL", response.get("error") or "lib.create failed")
        return
    runner.record("lib", payload, response, "PASS", "library created")


def stage_schematic(runner: Runner) -> None:
    build = (
        "let((cv mn mp p1 p2 p3 p4)"
        f' cv = dbOpenCellViewByType("{LIB}" "{CELL}" "schematic" "schematic" "w")'
        ' unless(cv error("cannot open schematic cellview"))'
        ' mn = dbCreateInstByMasterName(cv "' + PDK_LIB + '" "nch_25" "symbol" "MN" 1.0:1.0 "R0")'
        ' mp = dbCreateInstByMasterName(cv "' + PDK_LIB + '" "pch_25" "symbol" "MP" 1.0:3.0 "R0")'
        ' p1 = dbCreateInstByMasterName(cv "basic" "ipin" "symbol" "IN" -2.0:1.0 "R0")'
        ' p2 = dbCreateInstByMasterName(cv "basic" "opin" "symbol" "OUT" 4.0:3.0 "R0")'
        ' p3 = dbCreateInstByMasterName(cv "basic" "ipin" "symbol" "VDD" 1.0:5.0 "R0")'
        ' p4 = dbCreateInstByMasterName(cv "basic" "ipin" "symbol" "VSS" 1.0:-1.0 "R0")'
        ' unless(mn error("NMOS instance not created"))'
        ' unless(mp error("PMOS instance not created"))'
        ' dbSave(cv) dbClose(cv)'
        ' sprintf(nil "devices=MN,MP pins=%s,%s,%s,%s" '
        ' (if(p1 "IN" "missing") (if(p2 "OUT" "missing")'
        ' (if(p3 "VDD" "missing") (if(p4 "VSS" "missing")))))'
        ' )'
    )
    response = skill(runner, build)
    ok, detail = skill_ok(response)
    payload = {"operation": "basic.skill.execute", "stage": "schematic.build"}
    if not ok:
        runner.record("schematic", payload, response, "FAIL", f"build failed: {detail}")
        return
    check = call("virtuoso.schematic.check_and_save", runner.token,
                 library=LIB, cell=CELL, view="schematic")
    read = call("virtuoso.schematic.read", runner.token,
                library=LIB, cell=CELL, view="schematic")
    value = ((read.get("data") or {}).get("value") or {})
    instances = value.get("instances") or []
    runner.state["schematic_instances"] = len(instances)
    verdict = "PASS" if check.get("ok") and read.get("ok") and len(instances) >= 2 else "FAIL"
    note = f"{detail}; check_and_save={check.get('ok')}; read_instances={len(instances)}"
    runner.record("schematic", {"build": payload, "check": check}, read, verdict, note)


def stage_symbol(runner: Runner) -> None:
    payload = {"operation": "virtuoso.symbol.generate", "library": LIB, "cell": CELL}
    response = call("virtuoso.symbol.generate", runner.token,
                    library=LIB, cell=CELL, schematic_view="schematic",
                    symbol_view="symbol", overwrite=True)
    if not response.get("ok"):
        runner.record("symbol", payload, response, "FAIL", response.get("error") or "generate failed")
        return
    read = call("virtuoso.symbol.read", runner.token, library=LIB, cell=CELL, view="symbol")
    value = ((read.get("data") or {}).get("value") or {})
    pins = value.get("pins") or value.get("terminals") or []
    runner.record("symbol", payload, read,
                  "PASS" if read.get("ok") else "FAIL",
                  f"symbol read ok={read.get('ok')} pins={len(pins)}")


def stage_layout(runner: Runner) -> None:
    view = call("virtuoso.cellview.view.create", runner.token, library=LIB, cell=CELL,
                view="layout", view_type="maskLayout")
    runner.state["layout_view_create"] = view.get("ok")
    commands = [
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": "nch_mac",
         "master_view": "layout", "name": "MN", "xy": [0, 0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": "pch_mac",
         "master_view": "layout", "name": "MP", "xy": [0, 6], "orient": "R0"},
        {"op": "place_rect", "layer": "M1", "purpose": "drawing",
         "bbox": [-1.0, -1.0, 1.0, 7.0]},
        {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "OUT",
         "xy": [0.0, 3.0]},
        {"op": "place_label", "layer": "M1", "purpose": "drawing", "text": "OUT",
         "xy": [0.0, 3.0]},
    ]
    payload = {"operation": "virtuoso.layout.write", "library": LIB, "cell": CELL,
               "commands": commands}
    response = call("virtuoso.layout.write", runner.token, library=LIB, cell=CELL,
                    view="layout", view_type="maskLayout", commands=commands)
    if not response.get("ok"):
        runner.record("layout", payload, response, "FAIL", response.get("error") or "layout.write failed")
        return
    read = call("virtuoso.layout.read", runner.token, library=LIB, cell=CELL,
                view="layout", detail="summary")
    value = ((read.get("data") or {}).get("value") or {})
    instances = value.get("instances") or []
    runner.record("layout", payload, read, "PASS" if read.get("ok") else "FAIL",
                  f"instances={len(instances)} keys={sorted(value)[:8]}")


def stage_gds(runner: Runner) -> None:
    gds = f"{REMOTE_WORK}/{CELL}.gds"
    layer_map = f"/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/{TECH_LIB}/{TECH_LIB}.layermap"
    payload = {"operation": "virtuoso.layout.gds", "action": "export", "gds": gds,
               "layer_map": layer_map, "layer_map_is_local": False}
    response = call("virtuoso.layout.gds", runner.token, action="export", library=LIB,
                    cell=CELL, view="layout", file_path=gds, file_is_local=False,
                    top_cell=CELL, layer_map=layer_map, layer_map_is_local=False,
                    tech_lib=TECH_LIB)
    if not response.get("ok"):
        runner.record("gds", payload, response, "FAIL", response.get("error") or "gds export failed")
        return
    runner.state["gds"] = gds
    runner.record("gds", payload, response, "PASS", f"gds -> {gds}")


def stage_drc(runner: Runner) -> None:
    gds = runner.state.get("gds") or f"{REMOTE_WORK}/{CELL}.gds"
    deck = f"{PDK}/Calibre/drc/calibre.drc"
    payload = {"operation": "calibre.drc", "gds": gds, "top": CELL, "deck": deck}
    response = call("calibre.drc", runner.token, gds=gds, top=CELL, deck=deck,
                    blocking=True, timeout=1800)
    ok = bool(response.get("ok"))
    value = ((response.get("data") or {}).get("value") or {})
    runner.record("drc", payload, response, "PASS" if ok else "FAIL",
                  f"value_keys={sorted(value)[:8] if isinstance(value, dict) else value}")


def stage_lvs(runner: Runner) -> None:
    gds = runner.state.get("gds") or f"{REMOTE_WORK}/{CELL}.gds"
    deck = f"{PDK}/Calibre/lvs/calibre.lvs"
    cdl = runner.state.get("cdl") or str(ROOT / "test/artifacts/evidence/s11-probe/inv.scs")
    payload = {"operation": "calibre.lvs", "gds": gds, "top": CELL, "deck": deck, "cdl": cdl}
    response = call("calibre.lvs", runner.token, gds=gds, top=CELL, deck=deck,
                    cdl=cdl, blocking=True, timeout=1800)
    ok = bool(response.get("ok"))
    value = ((response.get("data") or {}).get("value") or {})
    runner.record("lvs", payload, response, "PASS" if ok else "FAIL",
                  f"value_keys={sorted(value)[:10] if isinstance(value, dict) else value}")


def stage_sim(runner: Runner) -> None:
    netlist = runner.state.get("sim_netlist")
    if not netlist:
        runner.record("sim", {"operation": "spectre.run"}, {}, "SKIP",
                      "no simulation netlist staged yet")
        return
    payload = {"operation": "spectre.run", "tasks": [netlist]}
    response = call("spectre.run", runner.token, tasks=[netlist],
                    spectre_args=["+escchars", "+log", "status", "-format", "psfascii"],
                    max_workers=2, parse="auto", download=False, timeout=1800)
    runner.record("sim", payload, response, "PASS" if response.get("ok") else "FAIL",
                  str(response.get("error") or "spectre run")[:120])


STAGES = [
    ("lib", stage_lib),
    ("schematic", stage_schematic),
    ("symbol", stage_symbol),
    ("layout", stage_layout),
    ("gds", stage_gds),
    ("drc", stage_drc),
    ("lvs", stage_lvs),
    ("sim", stage_sim),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", default="vb-vblog")
    parser.add_argument("--only", default="",
                        help="comma separated stage list (default: all)")
    parser.add_argument("--run-dir", type=Path,
                        default=ROOT / "test/artifacts/env/scenario-s11")
    args = parser.parse_args()

    runner = Runner(args.token, args.run_dir, [s for s in args.only.split(",") if s])
    started = time.time()
    for name, function in STAGES:
        if not runner.want(name):
            continue
        try:
            function(runner)
        except Exception as exc:  # noqa: BLE001 - a stage crash is evidence
            runner.record(name, {"stage": name}, {}, "ERROR", f"{type(exc).__name__}: {exc}")

    summary = {
        "scenario": "s11-full-flow",
        "token": args.token,
        "seconds": round(time.time() - started, 1),
        "passes": sum(1 for r in runner.results if r["verdict"] == "PASS"),
        "fails": sum(1 for r in runner.results if r["verdict"] in ("FAIL", "ERROR")),
        "stages": runner.results,
    }
    (runner.run_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if summary["fails"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
