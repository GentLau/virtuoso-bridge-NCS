# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 12:35
# 依赖: 真机 vblog token（schemtest 夹具）
# =======================================================================
"""口径批（P-091 / P-101）direct 自检：截图远端不留 + overwrite=false 显式跳过。

判据：
  P-091  schematic.screenshot → 本地 PNG 存在，且远端 role root screenshots/ 新增数为 0
  P-101  verilog.import(overwrite=False) 命中已存在 cell → reason=skipped_existing
         + skipped=true + cells=[]，且不跑 ihdl（无 stage 步骤）
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

TOKEN = "vb-vblog"
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
          f"{json.dumps(detail, ensure_ascii=False, default=str)[:160]}")


def remote_shot_count() -> int:
    root = middle.query(token=TOKEN).roles["daemon"].root.rstrip("/")
    listing = middle.run_command(
        f"ls -1 {root}/screenshots 2>/dev/null | wc -l", timeout=30, token=TOKEN)
    return int((listing.stdout or "0").strip() or 0)


# -- P-091 ------------------------------------------------------------------
print("P-091 截图远端暂存")
before = remote_shot_count()
shot = call("virtuoso.schematic.screenshot", library="schemtest",
            cell="sch_e2e", view="schematic", timeout=300)
raw_value = (shot.get("data") or {}).get("value")
if isinstance(raw_value, str):
    local_path = raw_value
elif isinstance(raw_value, dict):
    local_path = raw_value.get("local_path") or raw_value.get("path") or ""
else:
    local_path = ""
step_names = [s.get("name") for s in ((shot.get("data") or {}).get("steps") or [])]
record("P-091 截图成功", shot.get("ok") is True,
       {"error": shot.get("error"), "steps": step_names,
        "value": str(raw_value)[:100]})
time.sleep(1)
after = remote_shot_count()
record("P-091 远端不留存", after <= before, {"before": before, "after": after})
record("P-091 本地 PNG 存在",
       bool(local_path) and Path(str(local_path)).is_file(),
       {"local_path": str(local_path)[:100]})

# -- P-101 ------------------------------------------------------------------
print("P-101 overwrite=false 跳过标记")
src = ROOT / "test/artifacts/tmp/vimp_skip_probe.v"
src.write_text(
    "module vimp_skip_probe(input a, output y);\n  assign y = ~a;\nendmodule\n",
    encoding="utf-8", newline="\n")
first = call("virtuoso.verilog.import", library="schemtest", cell="vimp_skip_probe",
             file_path=str(src), file_is_local=True, ref_libs=["basic"],
             overwrite=True, timeout=600)
record("P-101 首次导入成功", first.get("ok") is True,
       {"error": first.get("error")})
second = call("virtuoso.verilog.import", library="schemtest", cell="vimp_skip_probe",
              file_path=str(src), file_is_local=True, ref_libs=["basic"],
              overwrite=False, timeout=600)
value2 = (second.get("data") or {}).get("value") or {}
steps2 = [s.get("name") for s in ((second.get("data") or {}).get("steps") or [])]
record("P-101 二次导入显式跳过",
       second.get("ok") is True
       and value2.get("reason") == "skipped_existing"
       and value2.get("skipped") is True
       and value2.get("cells") == []
       and not any(str(name).startswith("stage") for name in steps2),
       {"value": {k: value2.get(k) for k in ("reason", "skipped", "cells", "views")},
        "steps": steps2, "error": second.get("error")})

passed = sum(1 for item in RESULTS if item["ok"])
print(f"[summary] {passed}/{len(RESULTS)} green")
middle.close()
raise SystemExit(0 if passed == len(RESULTS) else 1)
