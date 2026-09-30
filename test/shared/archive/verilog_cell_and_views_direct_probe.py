# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 14:05
# 依赖: 真机 vblog token（schemtest 库）
# =======================================================================
"""P-100/P-099 direct 复验。

P-100 判据：源码顶层模块名 ≠ 请求 cell 时，产物必须落在 **请求的 cell** 下。
P-099 判据：import 返回值 `views` 至少含真实生成的视图（functional/symbol 等）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from common.paths import init_work_dir              # noqa: E402
from server import dispatch                         # noqa: E402
from server.api_server import register_packages     # noqa: E402
from transport.middle import BusinessServer         # noqa: E402

TOKEN, LIB = "vb-vblog", "schemtest"
RESULTS: list[dict] = []

init_work_dir(str(ROOT / "test/artifacts/env/log-vblog"))
register_packages()
middle = BusinessServer()


def call(operation: str, **fields):
    _status, body = dispatch.dispatch(
        middle, {"operation": operation, "token": TOKEN, **fields})
    return body


def record(name: str, ok: bool, detail) -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: "
          f"{json.dumps(detail, ensure_ascii=False, default=str)[:180]}")


stamp = time.strftime("%H%M%S")
src = ROOT / "test/artifacts/tmp" / f"vp_{stamp}.v"
src.write_text(f"module vp_{stamp}_m1(input a, output y);\n  assign y = ~a;\nendmodule\n",
               encoding="utf-8", newline="\n")
target_cell = f"vp_{stamp}_m2"

# P-100：cell ≠ 源码模块名 → 写前结构化拒绝（ihdl 没有 dest-cell，实测
# `dest_cell_name` 会被 VERILOGIN-8 拒），且不得留下任何产物。
mismatch = call("virtuoso.verilog.import", library=LIB, cell=target_cell,
                file_path=str(src), file_is_local=True, ref_libs=["basic"],
                overwrite=True, timeout=600)
mismatch_value = (mismatch).get("value") or {}
record("P-100 cell≠模块名 → 写前结构化拒绝",
       mismatch.get("ok") is False
       and mismatch_value.get("reason") == "cell_not_in_source",
       {"error": str(mismatch.get("error"))[:150], "value": mismatch_value})
exists = call("virtuoso.cellview.cell.list", library=LIB)
raw_cells = (exists).get("value")
if isinstance(raw_cells, dict):
    raw_cells = raw_cells.get("cells") or raw_cells.get("names") or []
taken = [c.get("name") if isinstance(c, dict) else str(c)
         for c in (raw_cells or [])]
record("P-100 拒绝后无残留 cell", target_cell not in str(taken),
       {"target": target_cell, "present": target_cell in str(taken)})

# P-099：cell == 源码模块名（正例）→ 返回值 views 必须非空
module_cell = f"vp_{stamp}_m1"
body = call("virtuoso.verilog.import", library=LIB, cell=module_cell,
            file_path=str(src), file_is_local=True, ref_libs=["basic"],
            overwrite=True, timeout=600)
value = (body).get("value") or {}
record("P-100 正例 import ok", body.get("ok") is True,
       {"error": str(body.get("error"))[:160], "cells": value.get("cells")})
views = value.get("views") or []
record("P-099 返回值含真实 views", bool(views),
       {"views": views[:4], "count": len(views)})

passed = sum(1 for item in RESULTS if item["ok"])
print(f"[summary] {passed}/{len(RESULTS)} green")
middle.close()
raise SystemExit(0 if passed == len(RESULTS) else 1)
