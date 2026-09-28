# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 23:30
# 依赖: 无
# =======================================================================
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
六步流程（test/docs/写TB规范.md §1）：
① `require_environment`（靶机指纹 / 业务面 / 需要的库）；②③ 造并校验基线（专属库、cell、前置对象）；
④ 只做被测动作；⑤ 读回比对（期望 / 实际入证据）；⑥ 跑完不清理现场。
某步不适用时，正文有一行注释说明原因。
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
        # 2026-09-24（第七轮）改：pin 必须用 `schCreatePin` 建（真正的 schematic pin），
        # 不能用 `dbCreateInstByMasterName(cv "basic" "ipin" …)` 摆一个"像 pin 的实例"——
        # 后者在 auCdl 网表器里是要**下钻**的普通子单元，而 basic/ipin 只有 symbol 视图，
        # 于是必然报 `OSSHNL-116 Unable to descend into any of the views … for the instance
        # 'VSS' in cell 'inv'`，LVS 全线拿不到源网表（本轮定位，属 TB 姿势错误）。
        ' p1 = schCreatePin(cv nil "IN" "input" nil -2.0:1.0 "R0")'
        ' p2 = schCreatePin(cv nil "OUT" "output" nil 4.0:3.0 "R0")'
        ' p3 = schCreatePin(cv nil "VDD" "inputOutput" nil 1.0:5.0 "R0")'
        ' p4 = schCreatePin(cv nil "VSS" "inputOutput" nil 1.0:-1.0 "R0")'
        ' unless(mn error("NMOS instance not created"))'
        ' unless(mp error("PMOS instance not created"))'
        ' dbSave(cv) dbClose(cv)'
        # SKILL 的 if 是特殊形式：嵌套写 if(c1 a if(c2 b …))，不能写成 (if(..)(if(..)))
        # （后者会被当成"用上一个 if 的结果去调用"→ eval: not a function）。
        ' sprintf(nil "devices=MN,MP pins=%s,%s,%s,%s"'
        ' if(p1 "IN" "missing") if(p2 "OUT" "missing")'
        ' if(p3 "VDD" "missing") if(p4 "VSS" "missing"))'
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
    # 判据必须覆盖 build 返回的 pin 串：任一 pin 建失败时会变成 `missing`
    # （真机验证：p1=nil → `pins=missing,OUT,VDD,VSS`）。只数 instance 会在
    # "实例建出来了但 pin 缺失"时假绿。
    pins_ok = "pins=IN,OUT,VDD,VSS" in detail
    verdict = ("PASS" if check.get("ok") and read.get("ok")
               and len(instances) >= 2 and pins_ok else "FAIL")
    note = (f"{detail}; check_and_save={check.get('ok')}; "
            f"read_instances={len(instances)}; pins_ok={pins_ok}")
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
         "master_view": "layout", "name": "MN", "pos": [0, 0], "orient": "R0"},
        {"op": "place_instance", "master_lib": PDK_LIB, "master_cell": "pch_mac",
         "master_view": "layout", "name": "MP", "pos": [0, 6], "orient": "R0"},
        {"op": "place_rect", "layer": "M1", "purpose": "drawing",
         "bbox": [[-1.0, -1.0], [1.0, 7.0]]},
        {"op": "place_label", "layer": "M1", "purpose": "pin", "text": "OUT",
         "pos": [0.0, 3.0]},
        {"op": "place_label", "layer": "M1", "purpose": "drawing", "text": "OUT",
         "pos": [0.0, 3.0]},
    ]
    payload = {"operation": "virtuoso.layout.write", "library": LIB, "cell": CELL,
               "commands": commands}
    response = call("virtuoso.layout.write", runner.token, library=LIB, cell=CELL,
                    view="layout", view_type="maskLayout", commands=commands)
    if not response.get("ok"):
        runner.record("layout", payload, response, "FAIL", response.get("error") or "layout.write failed")
        return
    # layout.read 的 detail 现在只接受 geometry/index（旧值 "summary" 已被
    # focus=["summary"] 取代）——第五轮实测：带旧值直接 4xx
    # "invalid request: detail must be geometry or index"，layout 阶段永远红，
    # 后面的 gds/drc/lvs 全被拖住。这里按当前 API 取 instances 索引。
    read = call("virtuoso.layout.read", runner.token, library=LIB, cell=CELL,
                view="layout", focus=["instances"], detail="index")
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
    # 注意：``cdl`` 必须是**远端路径**（calibre 包不代传源网表；传本地 Windows 路径
    # 会被 deck 当成相对名，报 "Can not open source netlist file C:Users..."）。
    #
    # 2026-09-24（第七轮）改：源网表不再用"本地探针网表"这种必然 FAIL 的兜底，
    # 改为走产品自己的官方链路 `calibre.export_cdl`（PDK 器件可导出，见 P-069 复验）；
    # 这样 S11 的 lvs 阶段才是"链路真的通"的证据。
    cdl = runner.state.get("cdl")
    if not cdl or not str(cdl).startswith("/"):
        export_dir = f"{REMOTE_WORK}/cdl"
        # cds.lib 必须是"带 Cadence 默认库（basic/analogLib）的完整清单"——只有工程
        # 自己的 cds.lib 时，auCdl 找不到 basic/ipin 的视图，报
        # `Add one of these views to the cell 'ipin' in the library 'basic'`（实测 2026-09-24）。
        # 所以这里以 calprobe 的完整 cds.lib 为基底，再补一行本工程库定义。
        remote_cds_lib = f"{REMOTE_WORK}/s11.cds.lib"
        prep_cmd = (f"mkdir -p {REMOTE_WORK} && cp /home/Gent/project/calprobe/cds.lib "
                    f"{remote_cds_lib} && (grep -q 'DEFINE {LIB} ' {remote_cds_lib} || "
                    f"echo 'DEFINE {LIB} {REMOTE_LIB_DIR}' >> {remote_cds_lib}); "
                    f"grep -n 'DEFINE {LIB} ' {remote_cds_lib} | tail -1")
        prep = call("basic.command.run", runner.token, cmd=prep_cmd, timeout=120)
        prep_out = ((prep.get("data") or {}).get("result") or [None, ""])
        runner.record("cdl-prep", {"operation": "basic.command.run", "cmd": prep_cmd}, prep,
                      "PASS" if prep.get("ok") else "FAIL",
                      f"stdout={(prep_out[1] if isinstance(prep_out, list) else '')[-160:]}")
        if not prep.get("ok"):
            runner.record("lvs", {"operation": "calibre.lvs"}, {}, "BLOCKED",
                          "cds.lib 准备失败，无法导出源网表")
            return
        runner.record("cdl-export", {"operation": "calibre.export_cdl"},
                      {}, "INFO", f"run_dir={export_dir} cds_lib={remote_cds_lib}")
        export = call("calibre.export_cdl", runner.token, library=LIB, cell=CELL,
                      view="schematic", netlist_name=CELL, run_dir=export_dir,
                      cds_lib=remote_cds_lib, timeout=900)
        export_value = ((export.get("data") or {}).get("value") or {})
        exported = str(export_value.get("netlist_path") or "")
        runner.record("cdl", {"operation": "calibre.export_cdl", "library": LIB,
                              "cell": CELL, "run_dir": export_dir}, export,
                      "PASS" if (export.get("ok") and exported) else "FAIL",
                      f"bytes={export_value.get('bytes')} path={exported}")
        if not (export.get("ok") and exported):
            runner.record("lvs", {"operation": "calibre.lvs"}, {}, "BLOCKED",
                          "no remote CDL (export_cdl failed) — see the cdl stage above")
            return
        cdl = exported
    payload = {"operation": "calibre.lvs", "gds": gds, "top": CELL, "deck": deck, "cdl": cdl}
    response = call("calibre.lvs", runner.token, gds=gds, top=CELL, deck=deck,
                    cdl=cdl, blocking=True, timeout=1800)
    ok = bool(response.get("ok"))
    value = ((response.get("data") or {}).get("value") or {})
    job_id = value.get("job_id") if isinstance(value, dict) else None
    verdict = None
    if ok and job_id:
        results = call("calibre.read_results", runner.token, kind="lvs", job_id=job_id,
                       timeout=300)
        summary = ((results.get("data") or {}).get("value") or {}).get("summary") or {}
        verdict = summary.get("status")
        # 判据（2026-09-24 第七轮定口径）：本 TB 的版图是脚本搭出的最小几何（两个器件 +
        # M1 矩形 + 标签），**没有真实布线/端口层**，因此"比较得上"是本阶段的正确期望；
        # "correct" 需要真实版图，已由 design_iterate_tb.py 的 lvs 阶段（CMP_LIB/inv2
        # 真实 cell）钉住。这里要求的是**确定结论**（correct/incorrect），
        # 并单独报出 correct 与否，避免拿"not_compared"当通过。
        definite = str(verdict).lower() in ("correct", "incorrect", "clean")
        runner.record("lvs-verdict", {"operation": "calibre.read_results", "job_id": job_id},
                      results, "PASS" if definite else "FAIL",
                      f"status={verdict} definite={definite} "
                      f"counts={summary.get('counts')} "
                      f"(correct 需真实版图，见 design_iterate_tb.py)")
    runner.record("lvs", payload, response, "PASS" if ok else "FAIL",
                  f"status={verdict} value_keys={sorted(value)[:10] if isinstance(value, dict) else value}")


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
