# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =====================================================================
"""共享库 CDF 污染探针（第五轮新增，真机）。

``set_instance_params`` 的实现（``src/pyapi/packages/schematic.py:475-495``）写的是
**cell 级** CDF：``vbCcd = cdfGetCellCDF(ddGetObj(vbInst~>libName vbInst~>cellName))``
然后 ``vbP~>value = ...``。于是"给实例设参数"会顺带改掉母单元（analogLib res、
PDK 器件）的默认值。本探针把影响面测清楚：

1. 改前/改后读 cell 级 CDF 默认值（analogLib/res.r、tsmcN65/nch_25.w/l）；
2. 另一个会话（--peer-token，默认 vbuser3，共享同一 /project 库）读同一 cell 的默认值
   → 判断是"同会话内存态"还是"跨会话/跨用户可见"；
3. 结束前还原并复查。

verdict ∈ {clean, same-session-only, cross-session, restore-failed, error}

用法::

    python test/semi/probes/shared_cdf_pollution_probe.py
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
_RUNNERS = Path(__file__).resolve().parents[3] / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
DEFAULT_TOKEN = "d6af595b342647b58ec63ca6"
DEFAULT_PEER = "vb-vbuser3"
LIB, CELL = "SRX65", "cdf_probe"


def call(token: str, operation: str, **fields: Any) -> dict:
    body = json.dumps({"operation": operation, "token": token, **fields},
                      ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def skill(token: str, code: str) -> str:
    response = call(token, "basic.skill.execute", skill_code=code, timeout=300)
    result = ((response).get("result") or {})
    if result.get("status") != "success":
        raise AssertionError(f"SKILL failed: {json.dumps(result, ensure_ascii=False)[:300]}")
    return str(result.get("output") or "").strip()


def cdf_default(token: str, lib: str, cell: str, param: str) -> str:
    return skill(
        token,
        f'let((ccd p) ccd = cdfGetCellCDF(ddGetObj("{lib}" "{cell}")) '
        f'p = get(ccd "{param}") if(p p~>value "NOPARAM"))')


def cdf_set(token: str, lib: str, cell: str, param: str, value: str) -> None:
    skill(
        token,
        f'let((ccd p) ccd = cdfGetCellCDF(ddGetObj("{lib}" "{cell}")) '
        f'p = get(ccd "{param}") if(p progn(p~>value = {value} "SET") "NOPARAM"))')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default=DEFAULT_TOKEN)
    ap.add_argument("--peer-token", default=DEFAULT_PEER)
    ap.add_argument("--out", type=Path,
                    default=ROOT / "test" / "artifacts" / "evidence" / "round4-probes")
    args = ap.parse_args(argv)
    require_environment(base=API, token=args.token, require_lib=["tsmcN65"])

    token, peer = args.token, args.peer_token
    report: dict[str, Any] = {"token": token, "peer_token": peer, "steps": []}

    def step(name: str, value: Any) -> None:
        report["steps"].append({"name": name, "value": value})
        print(f"{name}: {json.dumps(value, ensure_ascii=False)}")

    try:
        before = {
            "alib_res_r": cdf_default(token, "analogLib", "res", "r"),
            "nch25_w": cdf_default(token, "tsmcN65", "nch_25", "w"),
            "nch25_l": cdf_default(token, "tsmcN65", "nch_25", "l"),
        }
        step("before", before)

        call(token, "virtuoso.cellview.lib.create", library=LIB,
             path=f"/home/Gent/.virtuoso-bridge/calprobe/file/serdes_rx/{LIB}",
             technology_library="tsmcN65", timeout=180)
        call(token, "virtuoso.cellview.view.create", library=LIB, cell=CELL,
             view="schematic", view_type="schematic", timeout=180)

        res = call(token, "virtuoso.schematic.write", library=LIB, cell=CELL,
                   view="schematic", timeout=600, commands=[
                       {"op": "place_instance", "master_lib": "analogLib",
                        "master_cell": "res", "master_view": "symbol",
                        "name": "R1", "pos": [0.0, 0.0]},
                       {"op": "place_instance", "master_lib": "tsmcN65",
                        "master_cell": "nch_25", "master_view": "symbol",
                        "name": "M1", "pos": [4.0, 0.0]},
                       {"op": "set_instance_params", "name": "R1", "params": {"r": "777"}},
                       {"op": "set_instance_params", "name": "M1",
                        "params": {"w": "3u", "l": "100n"}},
                   ])
        step("schematic.write", {"ok": res.get("ok"), "error": res.get("error")})

        after = {
            "alib_res_r": cdf_default(token, "analogLib", "res", "r"),
            "nch25_w": cdf_default(token, "tsmcN65", "nch_25", "w"),
            "nch25_l": cdf_default(token, "tsmcN65", "nch_25", "l"),
        }
        step("after", after)
        same_session = any(after[k] != before[k] for k in before)
        report["same_session_mutation"] = same_session
        report["changed_in_session"] = sorted(k for k in before if after[k] != before[k])

        # 下游影响：同一会话里**另一个单元**新放的实例（不给参数）继承到什么
        call(token, "virtuoso.cellview.view.create", library=LIB, cell=CELL + "2",
             view="schematic", view_type="schematic", timeout=180)
        call(token, "virtuoso.schematic.write", library=LIB, cell=CELL + "2",
             view="schematic", timeout=600, commands=[
                 {"op": "place_instance", "master_lib": "analogLib", "master_cell": "res",
                  "master_view": "symbol", "name": "R2", "pos": [0.0, 0.0]},
                 {"op": "place_instance", "master_lib": "tsmcN65", "master_cell": "nch_25",
                  "master_view": "symbol", "name": "M2", "pos": [4.0, 0.0]},
             ])
        read = call(token, "virtuoso.schematic.read", library=LIB, cell=CELL + "2",
                    view="schematic", focus="params", param_filter=["r", "w", "l"],
                    timeout=300)
        read_value = ((read).get("value") or {})
        inherited = {
            inst.get("name"): inst.get("params")
            for inst in (read_value.get("instances") or [])
        }
        step("new-instance-inherits", inherited)
        report["inherited_by_new_instance"] = inherited

        peer_view = {}
        for lib, cell, param in (("analogLib", "res", "r"), ("tsmcN65", "nch_25", "w")):
            key = f"{lib}/{cell}.{param}"
            try:
                peer_view[key] = cdf_default(peer, lib, cell, param)
            except Exception as exc:  # noqa: BLE001
                peer_view[key] = f"ERROR: {type(exc).__name__}: {exc}"
        step("peer-session-defaults", peer_view)
        cross_session = (peer_view.get("analogLib/res.r") not in (None, before["alib_res_r"])
                         or peer_view.get("tsmcN65/nch_25.w") not in (None, before["nch25_w"]))
        report["cross_session_mutation"] = cross_session

        restored: dict[str, str] = {}
        # 无论本次是否观测到变化，都把基线值写回（探针失败中断时不留下污染）
        for lib, cell, param, key in (("analogLib", "res", "r", "alib_res_r"),
                                      ("tsmcN65", "nch_25", "w", "nch25_w"),
                                      ("tsmcN65", "nch_25", "l", "nch25_l")):
            cdf_set(token, lib, cell, param, before[key])
            restored[key] = cdf_default(token, lib, cell, param)
        step("restored", restored)
        restore_ok = all(restored.get(k, before[k]) == before[k] for k in before)

        if not same_session:
            verdict = "clean"
        elif cross_session:
            verdict = "cross-session"
        elif restore_ok:
            verdict = "same-session-only"
        else:
            verdict = "restore-failed"
        report["verdict"] = verdict
    except Exception as exc:  # noqa: BLE001
        report["verdict"] = "error"
        report["error"] = f"{type(exc).__name__}: {exc}"

    args.out.mkdir(parents=True, exist_ok=True)
    path = args.out / "round4-shared-cdf-pollution.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"verdict: {report.get('verdict')}")
    print(f"evidence: {path}")
    return 0 if report.get("verdict") == "clean" else 1


if __name__ == "__main__":
    raise SystemExit(main())
