# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =====================================================================
"""两个**真实 OS 用户**在同一 cellview 的 layout 上接力/并发（真机级）。

与 `test/live/stress/layout_multiuser_lock_tb.py` 的区别：

* 那条用的是 `vb-vblog` / `vb-s11`（**同一个 OS 账号**、两个 daemon），考的是锁语义；
* 本条用 `vb-vbuser1` / `vb-vbuser2`（**两个真实 OS 用户**、不同 home/工程/daemon），
  除了锁语义还断言**内容**：A 写 → A 读到的形状数 → B 在 A 结束后读到的形状数 →
  B 写 → A 回读必须看到 B 的新形状（用户 2026-09-23 明确要求"一个用户操作完了，
  另一个用户再操作，理论上应该能操作"）。

判据（不是"接口 ok"）：

1. `layout.read` 返回的 `("shape" ...)` 条目数在 A/B 两侧**逐次一致**；
2. B 增加形状后，**A 回读**能看到增加（跨用户、跨 daemon 的可见性）；
3. 并发写：至少一方成功；失败方必须是**锁类结构化错误**（不能是超时/崩溃）；
4. 收尾：**没有 `*.cdslck` 残留**，且 A 仍能写（系统未卡死）。

用法::

    PYTHONPATH=src python test/live/flows/multiuser_layout_handoff_tb.py \
        --work-dir test/artifacts/env/log-vblog \
        --base http://127.0.0.1:8127/api/operation \
        --lib adc_sar --cell mu2_handoff --lib-path /project/libs/adc_sar \
        --out test/artifacts/evidence/round5-realscen/multiuser-layout-handoff.json
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))
_RUNNERS = Path(__file__).resolve().parents[3] / "test" / "shared" / "runners"
if str(_RUNNERS) not in sys.path:
    sys.path.insert(0, str(_RUNNERS))
from env_check import require_environment  # noqa: E402

from transport.middle import BusinessServer  # noqa: E402
from common.paths import init_work_dir  # noqa: E402


def call(base: str, operation: str, token: str, **fields) -> dict:
    body = json.dumps({"operation": operation, "token": token, **fields}).encode()
    request = urllib.request.Request(
        base, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        try:
            return json.loads(error.read().decode("utf-8"))
        except Exception:  # noqa: BLE001 - 非 JSON 错误体也要能记录
            return {"ok": False, "error": f"HTTP {error.code}"}


def detail_of(response: dict) -> str:
    steps = ((_c1_wrapper(response)).get("steps")) or []
    for step in steps:
        if isinstance(step, dict) and step.get("name") == "read":
            return str(step.get("detail") or "")
    value = (_c1_wrapper(response)).get("value")
    return str(value or "")


def skill_output(response: dict) -> str:
    """取 `basic.skill.execute` 的 output（HTTP 侧可能是 `data.result.output`）。"""
    data = _c1_wrapper(response)
    result = data.get("result")
    if isinstance(result, dict):
        return str(result.get("output") or "")
    for step in data.get("steps") or []:
        if isinstance(step, dict) and step.get("name") == "skill":
            return str(step.get("detail") or "")
    return ""


def tech_binding(base: str, token: str, lib: str) -> str:
    response = call(base, "basic.skill.execute", token,
                    skill_code=f'sprintf(nil "tech=%L" ddGetObj("{lib}")~>techLibName)')
    return skill_output(response)


def shape_count(text: str) -> int:
    return text.count('("shape"')


def read_shapes(base: str, token: str, lib: str, cell: str) -> dict:
    response = call(base, "virtuoso.layout.read", token,
                    library=lib, cell=cell, view="layout")
    text = detail_of(response)
    return {"ok": bool(response.get("ok")), "count": shape_count(text),
            "error": response.get("error"), "detail_head": text[:160]}


def write_rect(base: str, token: str, lib: str, cell: str, x: float,
               layer: str = "M1") -> dict:
    started = time.time()
    response = call(base, "virtuoso.layout.write", token,
                    library=lib, cell=cell, view="layout",
                    commands=[{"op": "place_rect", "layer": layer,
                               "purpose": "drawing",
                               "bbox": [[x, 0.0], [x + 1.0, 1.0]]}])
    return {"token": token, "ok": bool(response.get("ok")),
            "error": response.get("error"),
            "elapsed_s": round(time.time() - started, 3)}


def create_layout(server: BusinessServer, token: str, lib: str, cell: str) -> dict:
    code = (f'let((cv) cv = dbOpenCellViewByType("{lib}" "{cell}" "layout" '
            f'"maskLayout" "w") unless(cv error("create failed")) '
            f'dbSave(cv) dbClose(cv) "created")')
    result = server.execute_skill(code, token=token)
    return {"ok": bool(result.ok), "output": (result.output or "").strip()[:120],
            "error": (getattr(result, "error", "") or "")[:200]}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--base", default="http://127.0.0.1:8127/api/operation")
    parser.add_argument("--token-a", default="vb-vbuser1")
    parser.add_argument("--token-b", default="vb-vbuser2")
    parser.add_argument("--lib", default="adc_sar")
    parser.add_argument("--lib-path", default="/project/libs/adc_sar")
    parser.add_argument("--cell", default="mu2_handoff",
                        help="固定 cell 名（默认复用同一个，避免每次跑都往共享库里堆垃圾）")
    parser.add_argument("--layer", default="M1")
    parser.add_argument("--keep-cell", action="store_true",
                        help="跑完不删除该 cell（默认删除，保持共享库整洁）")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)
    require_environment(base=args.base, token=args.token_a, require_lib=[args.lib])

    work_dir = Path(args.work_dir).resolve()
    cell = args.cell or f"mu2_handoff_{uuid.uuid4().hex[:6]}"
    out = Path(args.out) if args.out else work_dir / "multiuser-layout-handoff.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    init_work_dir(work_dir)
    server = BusinessServer()
    cases: list[dict] = []

    def record(name: str, passed: bool, **detail) -> bool:
        cases.append({"case": name, "ok": bool(passed), **detail})
        print(f"[{'PASS' if passed else 'FAIL'}] {name} {detail if not passed else ''}")
        return bool(passed)

    created = create_layout(server, args.token_a, args.lib, cell)

    # ---- 0. 环境前置：两个用户的 PDK/工艺绑定必须一致（P-068 的教训）----
    # A 绑 tsmcN65（216 层）而 B 绑 cdsDefTechLib（54 层）时，B 写版图会报
    # `dbCreateRect: Invalid layer/purpose`——那是**环境问题**，不是 bridge bug。
    # 落后的一侧执行：techBindTechFile(ddGetObj("<lib>") "<tech>")
    tech_a = tech_binding(args.base, args.token_a, args.lib)
    tech_b = tech_binding(args.base, args.token_b, args.lib)
    same_tech = bool(tech_a) and tech_a == tech_b
    record("env-tech-binding-consistent", same_tech, a=tech_a, b=tech_b,
           hint=f'若不一致：在落后会话执行 techBindTechFile(ddGetObj("{args.lib}") "<tech>")'
                "（环境问题，非 bridge bug；见 P-068 结论）")

    record("create-layout-view", created["ok"], **created)

    a_first = write_rect(args.base, args.token_a, args.lib, cell, 0.0, args.layer)
    a_second = write_rect(args.base, args.token_a, args.lib, cell, 2.0, args.layer)
    record("A-writes-two-rects", a_first["ok"] and a_second["ok"],
           first=a_first, second=a_second)

    a_read1 = read_shapes(args.base, args.token_a, args.lib, cell)
    record("A-reads-own-shapes", a_read1["ok"] and a_read1["count"] >= 2, **a_read1)

    # 一个用户操作完 → 另一个用户再操作（接力）
    b_read1 = read_shapes(args.base, args.token_b, args.lib, cell)
    record("B-sees-A-shapes", b_read1["ok"] and b_read1["count"] == a_read1["count"],
           a_count=a_read1["count"], b_count=b_read1["count"])

    b_write = write_rect(args.base, args.token_b, args.lib, cell, 4.0, args.layer)
    record("B-writes-after-A", b_write["ok"], **b_write)

    b_read2 = read_shapes(args.base, args.token_b, args.lib, cell)
    a_read2 = read_shapes(args.base, args.token_a, args.lib, cell)
    record("A-sees-B-shapes",
           a_read2["ok"] and b_read2["ok"] and a_read2["count"] == b_read2["count"]
           and a_read2["count"] > a_read1["count"],
           a_before=a_read1["count"], a_after=a_read2["count"], b_after=b_read2["count"])

    # 并发写：至少一方成功；失败方必须是锁类结构化错误
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(write_rect, args.base, args.token_a, args.lib, cell, 6.0, args.layer),
                   pool.submit(write_rect, args.base, args.token_b, args.lib, cell, 8.0, args.layer)]
        results = [future.result() for future in futures]
    winners = [item for item in results if item["ok"]]
    structured = all(item["ok"] or "lock" in (item["error"] or "").lower()
                     or "locked" in (item["error"] or "").lower() for item in results)
    record("concurrent-write-structured", bool(winners) and structured, results=results)

    a_after = write_rect(args.base, args.token_a, args.lib, cell, 10.0, args.layer)
    record("A-can-still-write", a_after["ok"], **a_after)

    # 锁残留 + 形状数终检
    listing = server.run_command(f"ls -1 {args.lib_path}/{cell}/layout/", token=args.token_a)
    files = [line.strip() for line in (listing.stdout or "").splitlines() if line.strip()]
    residue = [name for name in files if name.endswith(".cdslck")]
    record("no-cdslck-residue", not residue, files=files[-8:], residue=residue)

    final = read_shapes(args.base, args.token_a, args.lib, cell)
    record("final-read-ok", final["ok"] and final["count"] >= 4, **final)

    # 收尾：把本次用的 cell 删掉（默认固定 cell 名，重复跑不会在共享库里堆垃圾）。
    # 先试 SKILL 对象删除；不行就回退到 `rm -rf`（该 cell 是本 TB 自己建的，用户有权限），
    # 最后用 `ls` 复核"确实没了"再记账。
    if not args.keep_cell:
        cell_dir = f"{args.lib_path}/{cell}"
        server.execute_skill(f'errset(ddDeleteObj(ddGetObj("{args.lib}" "{cell}")))',
                             token=args.token_a)
        probe = server.run_command(f"ls -d {cell_dir} 2>/dev/null || true", token=args.token_a)
        if cell in (probe.stdout or ""):
            server.run_command(f"rm -rf {cell_dir}", token=args.token_a)
            probe = server.run_command(f"ls -d {cell_dir} 2>/dev/null || true", token=args.token_a)
        gone = cell not in (probe.stdout or "")
        record("cleanup-cell", gone, cell_dir=cell_dir,
               note="共享库不留测试 cell（--keep-cell 可保留）")

    payload = {"tb": "multiuser_layout_handoff_tb", "lib": args.lib, "cell": cell,
               "cases": cases,
               "passed": sum(1 for item in cases if item["ok"]), "total": len(cases)}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n{payload['passed']}/{payload['total']} 通过；证据：{out}")
    return 0 if payload["passed"] == payload["total"] else 2


if __name__ == "__main__":
    raise SystemExit(main())


# --- C1 兼容垫片（2026-09-29，C3）------------------------------------------------
# C1（2f88853）起：业务载荷直返顶层（值型 `value`、命令/skill 型 `result`）、
# 成功默认省略 `steps`、失败壳去掉 `data`。历史 TB 按 `response["data"]` 解析，
# 本垫片把新契约响应合成为旧 `data` 壳，让既有解析零改动继续工作。
def _c1_wrapper(body):
    if not isinstance(body, dict):
        return {}
    if isinstance(body.get("data"), dict):
        return body["data"]
    wrapped = {"ok": body.get("ok"), "error": body.get("error")}
    for key in ("value", "result", "steps"):
        if key in body:
            wrapped[key] = body[key]
    return wrapped
