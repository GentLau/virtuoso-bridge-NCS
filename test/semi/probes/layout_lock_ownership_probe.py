# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（真机靶机指纹/业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时，正文有一行注释说明。
# -*- coding: utf-8 -*-
"""判定 layout 的"被别的会话锁住"是真占用还是误判（半真机级）。

背景（2026-09-23 第二轮）：`layout.write` 在写之前用 `_is_locked()` 探测锁，实现是
`ls -A <view>/*.cdslck` —— **只看文件在不在**。而 OA 的 Edit Lock-Stake 会记录持有者
（`*.cdslck.<host>.<pid>` 后缀），锁完全可能属于**正在执行写入的同一个 CIW**。
实测：锁文件 owner pid = 我们驱动的 CIW，`dbOpenCellViewByType(..., "a")` 照样返回 dbid，
但 `layout.write` 直接判 "locked by another session" → 同一会话的第二次写必失败。

判定：
* 锁文件存在 **且** append 打开成功 → **误判**（缺陷）；
* 锁文件存在 **且** append 打开返回 nil → 真占用（正确行为）；
* 没有锁文件 → 无需判锁（合规）。

用法::

    PYTHONPATH=src python test/semi/probes/layout_lock_ownership_probe.py \
        --work-dir test/artifacts/env/log-vblog --token vb-vblog \
        --lib schemtest --cell lay_e2e --view layout \
        --out test/artifacts/evidence/round2-layout-lock-probe.json
"""
from __future__ import annotations

import argparse
import json
import re
import shlex
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from transport.middle import BusinessServer  # noqa: E402
from common.paths import init_work_dir  # noqa: E402


def _view_dir(server, token: str, lib: str, cell: str, view: str) -> str:
    expr = (f'let((l) l = ddGetObj("{lib}") '
            f'unless(l error("library not found")) '
            f'strcat(ddGetObjReadPath(l) "/" "{cell}" "/" "{view}"))')
    result = server.execute_skill(expr, token=token)
    return (result.output or "").strip().strip('"')


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--lib", default="schemtest")
    parser.add_argument("--cell", default="lay_e2e")
    parser.add_argument("--view", default="layout")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    init_work_dir(Path(args.work_dir).resolve())
    server = BusinessServer()
    view_dir = _view_dir(server, args.token, args.lib, args.cell, args.view)
    listing = server.run_command(
        f"ls -1 {shlex.quote(view_dir)}/*.cdslck* 2>/dev/null; true", token=args.token)
    locks = [line.strip() for line in (listing.stdout or "").splitlines() if line.strip()]
    owners = []
    for lock in locks:
        match = re.search(r"\.cdslck\.([\w.\-]+)\.(\d+)$", lock)
        owners.append({"file": Path(lock).name,
                       "owner_pid": match.group(2) if match else None})

    # 注意：本 CIW 的 eval 上下文里 `dbClose` 会报 "not a function"（已实测），
    # 因此这里只测**能否拿到 edit 模式的 dbid**，不做关闭（视图本来就在该会话里开着）。
    open_expr = (f'dbOpenCellViewByType("{args.lib}" "{args.cell}" '
                 f'"{args.view}" "maskLayout" "a")')
    opened = server.execute_skill(open_expr, token=args.token)
    append_ok = (opened.output or "").strip().startswith("db:")

    # 2026-09-24（第七轮）改判据：P-044 修好后，"有锁文件 + append 能开"**不再**等于缺陷
    # ——判锁不再等于"看文件在不在"。所以这里直接打**产品行为**：发一次真实的
    # `layout.write`，只把 `locked by another session` 当缺陷信号；其它错误（例如
    # 该库的工艺层名不叫 M1）只说明**锁这一关已经过了**，不算缺陷但原样记录。
    write_error = ""
    write_ok = None
    write_attempted = False
    try:
        from server import dispatch as dispatch_mod  # noqa: E402
        from server.api_server import register_packages  # noqa: E402
        register_packages()
        # 注意签名：dispatch(middle, payload) -> (status, body)（见 server/dispatch.py:116）
        _status, response = dispatch_mod.dispatch(server, {
            "operation": "virtuoso.layout.write", "token": args.token,
            "library": args.lib, "cell": args.cell, "view": args.view,
            "commands": [{"op": "place_rect", "layer": "M1", "purpose": "drawing",
                          "bbox": [[50.0, 50.0], [51.0, 51.0]]}],
            "timeout": 300,
        })
        write_attempted = True
        write_ok = bool(response.get("ok"))
        write_error = str(response.get("error") or "")
    except Exception as exc:  # noqa: BLE001 - 探针不能因为导入/调用姿势把结论带偏
        write_error = f"{type(exc).__name__}: {exc}"

    lock_defect = "locked by another session" in write_error
    if not write_attempted:
        # 调用姿势错/导入失败 → **不能**报 clean：这属于"没测到"，必须显式红。
        verdict, ok = (f"INCONCLUSIVE: 无法发起 layout.write（{write_error[:120]}）→ 本轮没测到",
                       False)
    elif lock_defect:
        verdict, ok = ("DEFECT: layout.write 仍按锁文件存在与否判锁（append 能开却被拒）",
                       False)
    elif not locks:
        verdict, ok = "no lock file (nothing to judge)", True
    elif write_ok:
        verdict, ok = "clean: lock file present, layout.write still succeeded", True
    else:
        verdict, ok = ("clean: 锁这一关通过（write 报的是其它命令错误，非锁误判）", True)
    payload = {
        "view_dir": view_dir,
        "lock_files": owners,
        "append_open_ok": append_ok,
        "append_open_output": (opened.output or "").strip(),
        "write_ok": write_ok,
        "write_error": write_error[:400],
        "write_attempted": write_attempted,
        "lock_defect": lock_defect,
        "verdict": verdict,
        "ok": ok,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
