# -*- coding: utf-8 -*-
"""两用户同一 cellview 读写语义探针（真机，两个 CIW 共享同一库）。

目的
----
上层业务包的 write 是"打开 edit → 原子操作 → 保存"的组合；本探针用两个用户
（各自独立 CIW、共享同一 OA 库）观察同一 cellview 的读写/读写交叉行为，
逐条与期望对比：

    T1  A 写完后 B 读       期望：可见 A 的数据
    T2  A 写完后 B 写       期望：成功（A 不残留 edit 锁）
    T3  A 写完后 A 再写     期望：成功（同会话连续写）
    T4  A 持有 edit 时 B 读 期望：成功（只读不被编辑锁挡）
    T5  A 持有 edit 时 B 写 期望：干净、可定位的锁失败（不挂起、不误报）

本探针不改任何产品代码，只记录"期望 vs 实测"；结论写入
``test/artifacts/evidence/<run-id>/twouser-same-view-{red|green}.json``。
任一场景不满足期望即整体 RED（退出码 1），供后续修复后复跑转绿。

用法（本地，走 business 层 dispatch，不经 HTTP）::

    python test/semi/probes/twouser_same_view_probe.py \
        --work-dir test/artifacts/env/scenario-multi-user-s3 \
        --token-a vb-mu2 --token-b vb-mu3 \
        --lib TEST_LIB --cell twouser_probe --view schematic
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shlex
import sys
import threading
import time
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from common.paths import init_work_dir  # noqa: E402
from server import dispatch  # noqa: E402
from server.api_server import register_packages  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402


def _skill(server, token: str, code: str) -> str:
    result = server.execute_skill(code, token=token)
    if not result.ok:
        raise RuntimeError("; ".join(result.errors) or "SKILL failed")
    return result.output or ""


def _op(server, token: str, operation: str, **fields):
    _status, body = dispatch.dispatch(
        server, {"operation": operation, "token": token, **fields})
    return body


def _view_dir(server, token: str, lib: str, cell: str, view: str) -> str:
    expr = (f'let((l) l = ddGetObj("{lib}") '
            f'unless(l error("library not found")) '
            f'strcat(ddGetObjReadPath(l) "/" "{cell}" "/" "{view}"))')
    return _skill(server, token, expr).strip().strip('"')


def _lock_entries(server, token: str, view_dir: str) -> list[dict]:
    listing = server.run_command(
        f"ls -1 {shlex.quote(view_dir)}/*.cdslck* 2>/dev/null; true", token=token)
    entries = []
    for line in (listing.stdout or "").splitlines():
        name = Path(line.strip()).name
        if not name:
            continue
        match = re.search(r"\.cdslck\.([\w.\-]+)\.(\d+)$", name)
        entries.append({"file": name,
                        "owner_pid": match.group(2) if match else None})
    return entries


def _wait_lock(server, token: str, view_dir: str, deadline: float) -> bool:
    while time.time() < deadline:
        if _lock_entries(server, token, view_dir):
            return True
        time.sleep(0.5)
    return False


def _labels_of(body: dict) -> list[dict]:
    value = body.get("data", {}).get("value") or body.get("value") or {}
    labels = value.get("labels") or []
    return [item for item in labels if isinstance(item, dict)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token-a", required=True, help="用户 A 的 token")
    parser.add_argument("--token-b", required=True, help="用户 B 的 token")
    parser.add_argument("--lib", default="TEST_LIB")
    parser.add_argument("--cell", default="twouser_probe")
    parser.add_argument("--view", default="schematic")
    parser.add_argument("--out", default="", help="证据 JSON 路径（默认自动生成）")
    args = parser.parse_args(argv)

    init_work_dir(str(Path(args.work_dir).resolve()))
    register_packages()
    server = BusinessServer()

    scenarios: list[dict] = []
    t0 = _dt.datetime.now()

    def record(sid: str, desc: str, expected: str, observed, ok: bool, extra=None):
        scenarios.append({
            "id": sid, "description": desc, "expected": expected,
            "observed": observed, "ok": ok, "extra": extra or {},
        })

    # 环境自检：两个用户各自能执行 SKILL 且看到同一库。
    for name, token in (("A", args.token_a), ("B", args.token_b)):
        out = _skill(server, token, f'list(getWorkingDir() ddGetObj("{args.lib}"))')
        record(f"SELF-{name}", f"{name} 环境自检", "SKILL 可用且库可见", out,
               bool(out) and "dd:" in out)

    def write_label(token: str, text: str) -> dict:
        return _op(server, token, "virtuoso.schematic.write",
                   library=args.lib, cell=args.cell, view=args.view,
                   commands=[{"op": "place_label", "text": text, "x": 0, "y": 0}])

    def read_labels(token: str) -> dict:
        return _op(server, token, "virtuoso.schematic.read",
                   library=args.lib, cell=args.cell, view=args.view,
                   focus="positions")

    # 干净起点：两个会话都 purge 掉任何残留 edit 句柄（防上一轮泄漏污染），
    # 再由 A 删除、重建；最后校验视图确实是空的，否则视为环境污染而非产品缺陷。
    def fresh_start() -> bool:
        for token in (args.token_a, args.token_b):
            _skill(server, token,
                   f'let((cv) cv = dbOpenCellViewByType("{args.lib}" "{args.cell}" '
                   f'"{args.view}" "schematic" "a") when(cv dbPurge(cv)) t)')
        _skill(server, args.token_a,
               f'let((o) o = ddGetObj("{args.lib}" "{args.cell}" "{args.view}") '
               'when(o unless(ddDeleteObj(o) error("delete failed"))))')
        _skill(server, args.token_a,
               f'let((cv) cv = dbOpenCellViewByType("{args.lib}" "{args.cell}" '
               f'"{args.view}" "schematic" "w") '
               'unless(cv error("create failed")) '
               'unless(dbSave(cv) error("save failed")) dbClose(cv) t)')
        empty = read_labels(args.token_a)
        return empty.get("ok") and not _labels_of(empty)

    if not fresh_start() and not fresh_start():
        raise RuntimeError(
            f"environment contaminated: {args.lib}/{args.cell}/{args.view} "
            "still carries stale objects after two purge+delete cycles")
    view_dir = _view_dir(server, args.token_a, args.lib, args.cell, args.view)

    # T1：A 写完，B 读。
    write_label(args.token_a, "A1")
    b_read = read_labels(args.token_b)
    texts = [item.get("text") for item in _labels_of(b_read)]
    record("T1", "A 写完后 B 读", "B 读到 A 的 label",
           {"ok": b_read.get("ok"), "error": b_read.get("error"), "texts": texts},
           b_read.get("ok") and "A1" in texts)

    # T2：A 写完后 B 写。
    b_write = write_label(args.token_b, "B1")
    record("T2", "A 写完后 B 写同一视图", "成功（A 不残留锁）",
           {"ok": b_write.get("ok"),
            "error": (b_write.get("error") or "")[:300],
            "steps": [(s.get("name"), s.get("ok")) for s in
                      (b_write.get("data", {}).get("steps") or [])]},
           bool(b_write.get("ok")))

    # T3：A 连续再写（同会话）。
    a_write2 = write_label(args.token_a, "A2")
    record("T3", "A 写完后 A 再写", "成功（同会话连续写）",
           {"ok": a_write2.get("ok"),
            "error": (a_write2.get("error") or "")[:300]},
           bool(a_write2.get("ok")))

    # 锁残留盘点：三次写都已"完成"，视图目录里不应再有 A 持有的 edit 锁。
    locks_after = _lock_entries(server, args.token_a, view_dir)
    record("LOCK", "写流程结束后的锁残留", "无本会话残留 edit 锁",
           {"locks": locks_after, "view_dir": view_dir}, not locks_after)

    # T4/T5：A 持锁期间 B 读/写。A 在一个独立请求里 open edit + hiSleep(20) + close，
    # 两个 CIW 独立执行，B 的请求与之并发。
    holder = threading.Thread(
        target=lambda: _skill(
            server, args.token_a,
            f'let((cv) cv = dbOpenCellViewByType("{args.lib}" "{args.cell}" '
            f'"{args.view}" "schematic" "a") '
            'unless(cv error("cannot open edit")) '
            'hiSleep(20) dbClose(cv) t)'),
        daemon=True)
    holder.start()
    held = _wait_lock(server, args.token_a, view_dir, time.time() + 15)

    b_read2 = read_labels(args.token_b)
    record("T4", "A 持有 edit 时 B 读", "成功（只读不受编辑锁影响）",
           {"ok": b_read2.get("ok"), "error": b_read2.get("error"),
            "texts": [item.get("text") for item in _labels_of(b_read2)]},
           bool(held) and bool(b_read2.get("ok")))

    b_write2 = write_label(args.token_b, "B2")
    lock_clean = "locked" in (b_write2.get("error") or "").lower()
    record("T5", "A 持有 edit 时 B 写", "干净、可定位的锁失败（不挂起）",
           {"ok": b_write2.get("ok"),
            "error": (b_write2.get("error") or "")[:300],
            "steps": [(s.get("name"), s.get("ok")) for s in
                      (b_write2.get("data", {}).get("steps") or [])],
            "held_observed": held},
           bool(held) and not b_write2.get("ok") and lock_clean)

    holder.join(timeout=30)

    # 清理：purge 释放 A 的编辑句柄后删视图（尽力而为，不参与判定）。
    try:
        _skill(server, args.token_a,
               f'let((cv) cv = dbOpenCellViewByType("{args.lib}" "{args.cell}" '
               f'"{args.view}" "schematic" "a") when(cv dbPurge(cv))) '
               f'let((o) o = ddGetObj("{args.lib}" "{args.cell}" "{args.view}") '
               'when(o unless(ddDeleteObj(o) error("delete failed"))))')
    except Exception as exc:  # noqa: BLE001
        record("CLEAN", "清理视图", "成功释放锁并删除", f"{type(exc).__name__}: {exc}",
               False)

    server.close()

    all_ok = all(item["ok"] for item in scenarios)
    run_id = f'twouser-{_dt.datetime.now().strftime("%Y%m%dT%H%M%S")}'
    evidence_root = SRC.parent / "test" / "artifacts" / "evidence"
    out_path = Path(args.out) if args.out else (
        evidence_root / run_id / f'twouser-same-view-{"green" if all_ok else "red"}.json')
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_meta": {
            "started": t0.isoformat(timespec="seconds"),
            "work_dir": str(Path(args.work_dir).resolve()),
            "lib": args.lib, "cell": args.cell, "view": args.view,
            "view_dir_remote": view_dir,
            "verdict": "GREEN" if all_ok else "RED",
        },
        "scenarios": scenarios,
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"evidence: {out_path}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
