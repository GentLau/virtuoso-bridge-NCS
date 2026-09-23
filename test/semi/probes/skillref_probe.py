"""Real-machine probe for the skillref package (direct dispatch, no HTTP).

Runs the two operations against the real Cadence doc tree in both modes:

* ``--source local  --doc-root C:\\Users\\user\\Desktop\\doc``
* ``--source remote --doc-root /opt/eda/cadence/IC618/doc --doc-token vb-vblog``

The remote case really calls the middle layer (SSH → wsl-gent).
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORK_DIR = ROOT / "test" / "artifacts" / "log-vblog"


def build_transport():
    from common.paths import init_work_dir
    from transport.middle import BusinessServer

    init_work_dir(str(WORK_DIR))
    return BusinessServer()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=("local", "remote"), default=None)
    parser.add_argument("--doc-root", default=None)
    parser.add_argument("--doc-token", default=None)
    parser.add_argument("--from-config", action="store_true",
                        help="用 work-dir/config.json 的 skillref 段（经 common.config 快照）")
    parser.add_argument("--token", default="vb-vblog")
    parser.add_argument("--query", default="ground bounce")
    parser.add_argument("--under", default=None,
                        help="comma separated subdirs for the body layer")
    args = parser.parse_args()

    from pyapi.packages import skillref as skillref_mod
    from pyapi.packages.skillref import InfoRequest, Package, SearchRequest

    if args.from_config:
        from common import config as common_config
        from common.paths import config_path, init_work_dir

        init_work_dir(str(WORK_DIR))
        snapshot = common_config.reload_config(config_path())
        section = dict(snapshot.get("skillref") or {})
        if not section:
            print(f"FAIL no skillref section in {config_path()}")
            return 2
    else:
        if not args.source or not args.doc_root:
            print("FAIL --source and --doc-root are required without --from-config")
            return 2
        section = {"source": args.source, "doc_root": args.doc_root}
        if args.doc_token:
            section["doc_token"] = args.doc_token
        skillref_mod._config_snapshot = lambda: {"skillref": section}

    middle = build_transport()
    package = Package(middle)
    report: dict = {
        "source": section.get("source"),
        "doc_root": section.get("doc_root"),
        "config_driven": bool(args.from_config),
        "cases": [],
    }

    try:
        for search_in in ("name", "entry", "topic", "body"):
            under = args.under.split(",") if (args.under and search_in == "body") else None
            request = SearchRequest(
                token=args.token, query=args.query, search_in=search_in,
                under=under, limit=5,
            )
            started = time.perf_counter()
            result = package.search(request)
            elapsed = round(time.perf_counter() - started, 2)
            report["cases"].append({
                "case": f"search({search_in})",
                "ok": result.ok,
                "error": result.error,
                "elapsed_s": elapsed,
                "elapsed_ms_reported": result.elapsed_ms,
                "hits": len(result.results),
                "layers": sorted({hit["layer"] for hit in result.results}),
                "scanned_files": result.scanned_files,
                "truncated": result.truncated,
                "top": [
                    {key: hit.get(key) for key in
                     ("layer", "score", "name", "title", "relative_path", "why")}
                    for hit in result.results[:3]
                ],
            })

        started = time.perf_counter()
        info = package.info(InfoRequest(token=args.token, name="dbOpenCellViewByType"))
        report["cases"].append({
            "case": "info(dbOpenCellViewByType)",
            "ok": info.ok, "error": info.error, "found": info.found,
            "elapsed_s": round(time.perf_counter() - started, 2),
            "func_name": info.func_name, "file_path": info.file_path,
            "plain_text_len": len(info.plain_text),
            "plain_head": info.plain_text[:200],
        })
        started = time.perf_counter()
        missing = package.info(InfoRequest(token=args.token, name="no_such_fn_xyz"))
        report["cases"].append({
            "case": "info(no_such_fn_xyz)",
            "ok": missing.ok, "found": missing.found, "error": missing.error,
            "elapsed_s": round(time.perf_counter() - started, 2),
        })
    finally:
        close = getattr(middle, "close", None)
        if callable(close):
            close()

    print(json.dumps(report, ensure_ascii=False, indent=2))
    failures = [case for case in report["cases"] if not case["ok"]]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
