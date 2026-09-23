"""S11 端到端工程流程 TB：spec → schematic → symbol → layout → LVS → 前仿 → 后仿。

针对真实设计（默认 ``CMP_LIB/cmp_top``：schematic+symbol+layout 齐全），逐段跑通并留证：

    python test/live/flows/s11_full_flow.py --work-dir test/artifacts/env/s11 --token vb-s11 \
        --lib CMP_LIB --cell cmp_top --out test/artifacts/env/s11/flow.json

每段输出 ``{stage, status, detail}``；``status`` ∈ pass / fail / pending（pending 必须写原因）。
退出码：有 fail → 1；只有 pass/pending → 0。
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import init_work_dir  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402


def _op(server: BusinessServer, token: str, operation: str, **fields):
    """走顶层 dispatch（与 HTTP 面同语义）；调用前必须先 register_packages()。"""
    from server import dispatch

    payload = {"operation": operation, "token": token, **fields}
    status, body = dispatch.dispatch(server, payload)
    if status not in (200, 400):
        raise RuntimeError(f"dispatch status {status}: {body}")
    if not body.get("ok"):
        raise RuntimeError(f"{operation} failed: {body.get('error')}")
    return body.get("data")


def stage_schematic(server, token, lib, cell, out: list) -> None:
    data = _op(server, token, "virtuoso.schematic.read", library=lib, cell=cell, view="schematic")
    summary = data.get("summary") if isinstance(data, dict) else data
    out.append({"stage": "schematic-read", "status": "pass",
                "detail": {"library": lib, "cell": cell, "view": "schematic",
                           "summary": summary if not isinstance(summary, (list, dict)) else "ok",
                           "keys": sorted(data)[:12] if isinstance(data, dict) else None}})


def stage_symbol(server, token, lib, cell, out: list) -> None:
    data = _op(server, token, "virtuoso.symbol.read", library=lib, cell=cell, view="symbol")
    pins = data.get("pins") if isinstance(data, dict) else None
    out.append({"stage": "symbol-read", "status": "pass",
                "detail": {"pins": pins if not isinstance(pins, list) else f"{len(pins)} pins",
                           "keys": sorted(data)[:12] if isinstance(data, dict) else None}})


def stage_layout(server, token, lib, cell, out: list) -> None:
    data = _op(server, token, "virtuoso.layout.read", library=lib, cell=cell, view="layout")
    out.append({"stage": "layout-read", "status": "pass",
                "detail": {"keys": sorted(data)[:12] if isinstance(data, dict) else None}})


def stage_gds(server, token, lib, cell, local_gds: str, out: list, layer_map: str = "") -> None:
    """导出 GDS 到**客户端**（当前实现里 export 只支持下载方向，见 P-027）。"""
    kwargs = {}
    if layer_map:
        kwargs = {"layer_map": layer_map, "layer_map_is_local": False}
    data = _op(server, token, "virtuoso.layout.gds", action="export", library=lib, cell=cell,
               view="layout", file_path=local_gds, timeout=300, **kwargs)
    detail = {"local_gds": local_gds, "exists": Path(local_gds).is_file(),
              "size": Path(local_gds).stat().st_size if Path(local_gds).is_file() else 0}
    out.append({"stage": "layout-gds-export", "status": "pass" if detail["exists"] else "fail",
                "detail": detail})


def stage_upload_gds(server, token, local_gds: str, remote_gds: str, out: list) -> None:
    """把本地 GDS 传回靶机，供 LVS 使用（绕开 P-027：导出只支持下载）。"""
    data = _op(server, token, "basic.file.upload", local_path=local_gds, remote_path=remote_gds,
               timeout=300)
    out.append({"stage": "upload-gds", "status": "pass", "detail": {"remote_gds": remote_gds}})


def stage_lvs(remote_gds: str, remote_cdl: str, top: str, work_dir: str, token: str,
              out: list) -> None:
    """Calibre LVS：用分层 CDL（已合并）+ 导出的 GDS，读 lvs.rep 的 CORRECT/INCORRECT。"""
    import subprocess

    probe = ROOT / "test" / "semi" / "probes" / "calibre_env_probe.py"
    run = subprocess.run(
        [sys.executable, str(probe), "--work-dir", work_dir, "--token", token,
         "--stage", "lvs", "--gds", remote_gds, "--top", top, "--cdl", remote_cdl],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=1800,
    )
    if run.returncode != 0:
        out.append({"stage": "lvs", "status": "fail",
                    "detail": f"probe rc={run.returncode}: {(run.stderr or run.stdout)[-300:]}"})
        return
    verdict = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "wsl-gent",
         "grep -m1 -E 'CORRECT|INCORRECT' /home/Gent/project/vblog/calibre_probe/lvs_run/lvs.rep"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
    ).stdout.strip()
    ok = "CORRECT" in verdict and "INCORRECT" not in verdict
    out.append({"stage": "lvs", "status": "pass" if ok else "fail",
                "detail": {"gds": remote_gds, "cdl": remote_cdl, "verdict": verdict[:120]}})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--lib", default="CMP_LIB")
    parser.add_argument("--cell", default="cmp_top")
    parser.add_argument("--run-dir", default="")
    # strmout 的 map 格式：`<layer> <purpose> <streamNum> <dataType>`；PDK 的 CCI/dfii map 不是这个格式
    parser.add_argument("--layer-map", default="/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/tsmcN65/tsmcN65.layermap")
    parser.add_argument("--cdl", default="/home/Gent/.virtuoso-bridge/vbs11/tmp/cmp_top_full.cdl",
                        help="LVS 用参考网表（分层设计需把子电路 CDL 合并成一份）")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    init_work_dir(args.work_dir)
    from server.api_server import register_packages

    register_packages()          # 与 HTTP 面一致：先把上层包注册进 dispatch
    server = BusinessServer()
    run_dir = args.run_dir or "/home/Gent/.virtuoso-bridge/vbs11/tmp"
    local_gds = str(ROOT / "test" / "artifacts" / "s11" / f"{args.cell}.gds")
    results: list[dict] = []
    started = time.time()

    stages = [
        ("schematic-read", lambda: stage_schematic(server, args.token, args.lib, args.cell, results)),
        ("symbol-read", lambda: stage_symbol(server, args.token, args.lib, args.cell, results)),
        ("layout-read", lambda: stage_layout(server, args.token, args.lib, args.cell, results)),
        ("layout-gds-export", lambda: stage_gds(server, args.token, args.lib, args.cell,
                                                local_gds, results, args.layer_map)),
        ("upload-gds", lambda: stage_upload_gds(server, args.token, local_gds,
                                                f"{run_dir}/{args.cell}.gds", results)),
        ("lvs", lambda: stage_lvs(f"{run_dir}/{args.cell}.gds", args.cdl, args.cell,
                                  args.work_dir, args.token, results)),
        ("pre-sim", None),
        ("post-sim", None),
    ]
    for name, runner in stages:
        if runner is None:
            results.append({"stage": name, "status": "pending",
                            "detail": "本轮 S11 首版只跑通 read/export 四段；LVS/前仿/后仿见 calibre 探针与 maestro/spectre 套件"})
            continue
        try:
            runner()
        except Exception as exc:  # noqa: BLE001
            results.append({"stage": name, "status": "fail",
                            "detail": f"{type(exc).__name__}: {exc}"})

    payload = {"ok": all(r["status"] != "fail" for r in results),
               "elapsed_s": round(time.time() - started, 2),
               "library": args.lib, "cell": args.cell, "results": results}
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
