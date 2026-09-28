# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-28 21:10
# 依赖: 无
# =======================================================================
# 六步流程（test/docs/写TB规范.md §1）：
# ① 环境检查（真机靶机指纹/业务面）；②③ 造并校验基线；④ 只做被测动作；
# ⑤ 读回比对（期望/实际入证据）；⑥ 跑完不清理现场。某步不适用时，正文有一行注释说明。
# -*- coding: utf-8 -*-
"""P-044 一句话复现：同一 CIW 的第二次 `layout.write` 必失败（锁误判）。

判定口径
--------
* 建视图（原始 SKILL，正常 dbClose）→ 干净起点；
* 写 #1 成功 → 本会话把视图以 edit 模式打开并保存，OA 落下
  `<view>.oa.cdslck.<host>.<pid>`；
* 取锁文件 owner pid 与**真实 CIW 进程 pid** 对比：相同即"自己锁自己"；
* 写 #2 返回 "is locked by another session" → 误判确认（缺陷）；
* 写 #2 成功 → 判锁已修正（回归通过）。

用法（本地，走 business 层 dispatch，不经 HTTP）::

    python test/semi/probes/layout_p044_second_write_probe.py \
        --work-dir test/artifacts/env/log-vblog --token vb-vblog \
        --out test/artifacts/evidence/round3-layout-p044.json
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

from common.paths import init_work_dir  # noqa: E402
from server import dispatch  # noqa: E402
from server.api_server import register_packages  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402


def _view_dir(server, token: str, lib: str, cell: str, view: str) -> str:
    expr = (f'let((l) l = ddGetObj("{lib}") '
            f'unless(l error("library not found")) '
            f'strcat(ddGetObjReadPath(l) "/" "{cell}" "/" "{view}"))')
    result = server.execute_skill(expr, token=token)
    return (result.output or "").strip().strip('"')


def _lock_owner_pids(server, token: str, view_dir: str) -> list[dict]:
    listing = server.run_command(
        f"ls -1 {shlex.quote(view_dir)}/*.cdslck* 2>/dev/null; true", token=token)
    owners = []
    for line in (listing.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.search(r"\.cdslck\.([\w.\-]+)\.(\d+)$", line)
        owners.append({"file": Path(line).name,
                       "owner_pid": match.group(2) if match else None})
    return owners


def _ciw_pid(server, token: str, cdslib: str) -> str:
    probe = server.run_command(
        f"pgrep -f {shlex.quote('virtuoso .*' + cdslib)} | head -1", token=token)
    return (probe.stdout or "").strip()


def _skill(server, token: str, code: str) -> str:
    result = server.execute_skill(code, token=token)
    if not result.ok:
        raise RuntimeError("; ".join(result.errors) or "SKILL failed")
    return result.output or ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--lib", default="schemtest")
    parser.add_argument("--cell", default="p044_probe")
    parser.add_argument("--view", default="layout")
    parser.add_argument("--cdslib", default="project/vblog/cds.lib",
                        help="CIW 启动用的 cds.lib（用于从 pgrep 里认出该实例）")
    parser.add_argument("--out", default="")
    args = parser.parse_args(argv)

    init_work_dir(str(Path(args.work_dir).resolve()))
    register_packages()
    server = BusinessServer()

    def op(operation: str, **fields):
        _status, body = dispatch.dispatch(
            server, {"operation": operation, "token": args.token, **fields})
        return body

    # 干净起点：删掉旧视图，用原始 SKILL 建一个（模拟"上一步刚保存并关闭"）。
    _skill(server, args.token,
           f'let((o) o = ddGetObj("{args.lib}" "{args.cell}" "{args.view}") '
           'when(o unless(ddDeleteObj(o) error("delete failed"))))')
    _skill(server, args.token,
           f'let((cv) cv = dbOpenCellViewByType("{args.lib}" "{args.cell}" '
           f'"{args.view}" "maskLayout" "w") '
           'unless(cv error("create failed")) '
           'unless(dbSave(cv) error("save failed")) dbClose(cv) t)')

    base = {"library": args.lib, "cell": args.cell, "view": args.view}
    first = op("virtuoso.layout.write", **base,
               commands=[{"op": "place_rect", "layer": "y0", "purpose": "drawing",
                          "bbox": [0, 0, 2, 1]}])
    view_dir = _view_dir(server, args.token, args.lib, args.cell, args.view)
    owners = _lock_owner_pids(server, args.token, view_dir)
    ciw = _ciw_pid(server, args.token, args.cdslib)

    second = op("virtuoso.layout.write", **base,
                commands=[{"op": "place_rect", "layer": "y1", "purpose": "drawing",
                           "bbox": [3, 0, 4, 1]}])

    owner_pids = [item["owner_pid"] for item in owners]
    same_session = bool(ciw) and ciw in owner_pids
    second_error = second.get("error") or ""
    false_positive = bool(same_session and not second.get("ok")
                          and "locked by another session" in second_error)
    payload = {
        "view_dir": view_dir,
        "ciw_pid": ciw,
        "lock_files": owners,
        "lock_owned_by_ciw": same_session,
        "write_1_ok": bool(first.get("ok")),
        "write_1_error": first.get("error"),
        "write_2_ok": bool(second.get("ok")),
        "write_2_error": second.get("error"),
        "write_2_steps": (second.get("data") or {}).get("steps"),
        "verdict": (
            "FALSE POSITIVE: same-session lock blocks the second write"
            if false_positive else
            "no defect observed" if second.get("ok") else
            "inconclusive: second write failed for another reason"
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
    return 1 if false_positive else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
