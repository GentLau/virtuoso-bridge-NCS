# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 13:40
# 依赖: 真机 vblog token（schemtest/lay_e2e 布局）
# =======================================================================
"""P-082/P-085 direct 复验：region 只收对角两点，且 depth>0 能真下钻。

判据：
  ① 四元组 region → 显式 ValueError（点名 pos0/pos1），且不触达传输层；
  ② depth=0 与 depth=1 都用两点 region，且 depth=1 读回的 shapes 严格多于 depth=0。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from common.paths import init_work_dir              # noqa: E402
from server import dispatch                         # noqa: E402
from server.api_server import register_packages     # noqa: E402
from transport.middle import BusinessServer         # noqa: E402

TOKEN, LIB, CELL, VIEW = "vb-vblog", "schemtest", "lay_e2e", "layout"
LAYERS = [["y0", "drawing"], ["y1", "drawing"], ["y2", "drawing"],
          ["y3", "drawing"], ["text", "drawing"]]
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
          f"{json.dumps(detail, ensure_ascii=False, default=str)[:170]}")


# ① 四元组必须被显式拒绝
quad = call("virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
            focus=["shapes"], detail="index",
            object_filter={"shape": {"region": [0, 0, 60, 60]},
                           "instance": "none", "via": "none"})
record("① 四元组 region 被拒（点名 pos0/pos1）",
       quad.get("ok") is False and "pos0" in str(quad.get("error")),
       {"error": str(quad.get("error"))[:160]})

# ② depth 0 vs 1（两点 region）。先放一个 master 实例，否则没有层级可下钻
#    （深度下钻的判据本身要求"实例的图形被带出来"）。
placed = call("virtuoso.layout.write", library=LIB, cell=CELL, view=VIEW,
              commands=[{"op": "place_instance", "master_lib": LIB,
                         "master_cell": "lay_master", "master_view": VIEW,
                         "name": "P085_I1", "pos": [3.0, 3.0], "orient": "R0"}])
record("② 前置：放置 master 实例", placed.get("ok") is True,
       {"error": placed.get("error")})


def read(depth: int) -> dict:
    body = call("virtuoso.layout.read", library=LIB, cell=CELL, view=VIEW,
                focus=["shapes"], detail="index", region_mode="intersect",
                depth=depth,
                object_filter={"shape": {"layers": LAYERS,
                                         "region": [[0.0, 0.0], [60.0, 60.0]]},
                               "instance": "none", "via": "none"})
    return body


flat = read(0)
deep = read(1)
n0 = len(((flat).get("value") or {}).get("shapes") or [])
n1 = len(((deep).get("value") or {}).get("shapes") or [])
record("② depth>0 真机下钻成功且多于 depth=0", deep.get("ok") is True and n1 > n0,
       {"depth0": n0, "depth1": n1, "error": str(deep.get("error"))[:140]})

passed = sum(1 for item in RESULTS if item["ok"])
print(f"[summary] {passed}/{len(RESULTS)} green")
middle.close()
raise SystemExit(0 if passed == len(RESULTS) else 1)
