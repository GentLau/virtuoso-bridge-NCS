# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =====================================================================
"""多用户 layout 协同 TB（真机级）：同一 cellview 的**交接 / 并发 / 陈旧锁**。

为什么要有它（用户 2026-09-23 要求）：
"一个用户操作完了，另一个用户理论上应该能继续操作" —— 之前 layout 写路径不关闭
编辑句柄、且判锁只看文件是否存在，导致第二个用户永远进不来（P-044）。设计侧已修
（open→save→close），本 TB 负责**击穿**：把交接、并发、死锁残留三种情况都跑一遍。

用例：
  H1  A 写 → B 写            期望：两次都 ok（交接可用）
  H2  B 写 → A 写            期望：两次都 ok
  C1  A、B 同时写            期望：至少一方 ok；失败方必须是**结构化锁错误**（不挂死、不误报）
  C2  C1 之后 A 再写         期望：ok（并发后系统仍可用）
  S1  预置"死进程"陈旧锁 → A 写   期望：ok（陈旧锁不得挡写）

用法::

    PYTHONPATH=src python test/live/stress/layout_multiuser_lock_tb.py \
        --work-dir test/artifacts/env/log-vblog \
        --token-a vb-vblog --token-b vb-s11 \
        --lib schemtest --out test/artifacts/evidence/round3-layout-multiuser.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
_RUNNERS = Path(__file__).resolve().parents[3] / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

from common.paths import init_work_dir  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402


def call(base: str, operation: str, token: str, **fields):
    body = json.dumps({"operation": operation, "token": token, **fields}).encode()
    request = urllib.request.Request(
        base, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def create_view(server: BusinessServer, token: str, lib: str, cell: str) -> str:
    code = (f'let((cv) cv = dbOpenCellViewByType("{lib}" "{cell}" "layout" '
            f'"maskLayout" "w") unless(cv error("create failed")) '
            f'dbSave(cv) dbClose(cv) "created")')
    result = server.execute_skill(code, token=token)
    return (result.output or "").strip()


LAYER = "y0"  #: schemtest 里真实存在的层（M1 在该库里不存在，会被 dbCreateRect 拒绝）


def write_rect(base: str, token: str, lib: str, cell: str, x: int) -> dict:
    started = time.time()
    response = call(base, "virtuoso.layout.write", token,
                    library=lib, cell=cell, view="layout",
                    commands=[{"op": "place_rect", "layer": LAYER, "purpose": "drawing",
                               "bbox": [[x, 0], [x + 1, 1]]}])
    return {"token": token, "cell": cell, "ok": bool(response.get("ok")),
            "error": response.get("error"),
            "elapsed_s": round(time.time() - started, 3)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8127/api/operation")
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token-a", required=True)
    parser.add_argument("--token-b", required=True)
    parser.add_argument("--lib", default="schemtest")
    parser.add_argument("--lib-path", default="/home/Gent/project/vblog/schemtest",
                        help="共享库物理路径（预置陈旧锁用；两个实例必须都 DEFINE 到它）")
    parser.add_argument("--layer", default="y0", help="该库里真实存在的层（schemtest：y0/y1/y2/y3/text）")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    require_environment(base=args.base, token=args.token_a, require_lib=[args.lib])

    global LAYER
    LAYER = args.layer if hasattr(args, "layer") else LAYER
    work_dir = Path(args.work_dir).resolve()
    init_work_dir(str(work_dir))
    init_work_dir(work_dir)
    server = BusinessServer()
    report: dict = {"cases": [], "verdict": {}}

    def record(name: str, ok: bool, detail) -> None:
        report["cases"].append({"case": name, "ok": bool(ok), "detail": detail})

    # ---- H1：A 写 → B 写 ----------------------------------------------------
    cell = "mu_handoff"
    created = create_view(server, args.token_a, args.lib, cell)
    first = write_rect(args.base, args.token_a, args.lib, cell, 0)
    second = write_rect(args.base, args.token_b, args.lib, cell, 2)
    record("H1-a-then-b", first["ok"] and second["ok"],
           {"create": created, "a": first, "b": second})

    # ---- H2：B 写 → A 写 ----------------------------------------------------
    cell = "mu_handoff_rev"
    created = create_view(server, args.token_a, args.lib, cell)
    first = write_rect(args.base, args.token_b, args.lib, cell, 10)
    second = write_rect(args.base, args.token_a, args.lib, cell, 12)
    record("H2-b-then-a", first["ok"] and second["ok"],
           {"create": created, "b": first, "a": second})

    # ---- C1：同时写 ---------------------------------------------------------
    cell = "mu_concurrent"
    created = create_view(server, args.token_a, args.lib, cell)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write_rect, args.base, args.token_a, args.lib, cell, 20),
                   pool.submit(write_rect, args.base, args.token_b, args.lib, cell, 22)]
        results = [future.result() for future in futures]
    winners = [item for item in results if item["ok"]]
    structured = all(("lock" in (item["error"] or "").lower())
                     or ("locked" in (item["error"] or "").lower())
                     or item["ok"] for item in results)
    record("C1-concurrent", bool(winners) and structured,
           {"create": created, "results": results,
            "note": "至少一方成功，且失败方必须是锁类结构化错误"})

    # ---- C2：并发之后仍可写 --------------------------------------------------
    after = write_rect(args.base, args.token_a, args.lib, cell, 24)
    record("C2-writable-after-concurrent", after["ok"], after)

    # ---- S1：死进程陈旧锁不得挡写 --------------------------------------------
    cell = "mu_stale_lock"
    created = create_view(server, args.token_a, args.lib, cell)
    view_dir = f"{args.lib_path.rstrip('/')}/{cell}/layout"
    stale = server.run_command(
        f"cd {view_dir} && touch {cell}.oa.cdslck {cell}.oa.cdslck.deadhost.999999 "
        f"&& ls -1 *.cdslck*", token=args.token_b, timeout=60)
    write = write_rect(args.base, args.token_a, args.lib, cell, 30)
    record("S1-stale-lock-not-blocking", write["ok"],
           {"stale_files": (stale.stdout or "").split(), "write": write})

    # ---- 收尾：两个用户都还能干活 --------------------------------------------
    health = {token: server.execute_skill("1+1", token=token).ok
              for token in (args.token_a, args.token_b)}
    record("Z-final-health", all(health.values()), health)

    report["verdict"] = {
        "passed": sum(1 for case in report["cases"] if case["ok"]),
        "total": len(report["cases"]),
        "ok": all(case["ok"] for case in report["cases"]),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return 0 if report["verdict"]["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
