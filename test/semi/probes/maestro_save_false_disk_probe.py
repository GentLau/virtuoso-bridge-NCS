# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-28 21:10
# 依赖: test/live/packages/maestro_e2e_tests.py（同题 live 用例）
# =======================================================================
"""P-087 红灯钉（磁盘级）：`save=False` 的改动**不被隔离**，会被后续任意一次保存带走。

背景：live 用例 WRITE-06 曾以「新会话读回旧值」为判据，被改判为仅查步骤表
（save=False 不出 `save_setup` 步骤）。但**读回可能命中复用会话的内存**，不能证明磁盘；
而磁盘 sdb 才是用户可见的持久化真相。本探针直接查 `maestro/maestro.sdb`：

  1. save=True 写 1.0  → 步骤含 save_setup；sdb 里值=1.0（对照）
  2. save=False 写 2.0 → 步骤不含 save_setup；**此刻** sdb 仍=1.0（不立即落盘，合规）
  3. 触发一次无关的 save=True 写（写另一个变量）→ **若 sdb 里旧变量变成 2.0 ⇒ RED**
     （未保存值被复用会话里的后续保存静默带走 = 跨请求污染）
  4. 清理：尽力删除两个变量并记录结果（delete_var 在本场景实测报 handle 错误，也要如实记录）

用法::

    PYTHONPATH=src python test/semi/probes/maestro_save_false_disk_probe.py

证据：``test/artifacts/evidence/round8/maestro-save-false-disk.json``
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "test" / "shared" / "runners"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

LIB, CELL, VIEW = "maestro_tb", "rc_probe", "maestro"
OUT = ROOT / "test" / "artifacts" / "evidence" / "round8" / "maestro-save-false-disk.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--token", default="vb-vblog")
    ap.add_argument("--work-dir", default=str(ROOT / "test" / "artifacts" / "env" / "log-vblog"))
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)

    from common.paths import init_work_dir
    from pyapi.packages import maestro
    from transport.middle import BusinessServer
    from env_check import require_environment

    env = require_environment(work_dir=args.work_dir, token=args.token,
                              expect_host="GLIS-DESKTOP")
    init_work_dir(args.work_dir)
    server = BusinessServer()
    checks: list[dict] = []
    try:
        lib_path = server.execute_skill(
            f'ddGetObj("{LIB}")~>readPath', timeout=60, token=args.token).output
        lib_path = (lib_path or "").strip().strip('"')
        sdb = f"{lib_path}/{CELL}/{VIEW}/maestro.sdb"

        def disk_value(name: str) -> str:
            r = server.run_command(
                f'grep -A 2 "<var>{name}" "{sdb}" 2>/dev/null | grep -m1 "<value>"',
                token=args.token)
            return (r.stdout or "").strip()

        def record(label: str, ok: bool, detail: dict) -> None:
            checks.append({"check": label, "ok": ok, **detail})
            print(("PASS " if ok else "FAIL ") + label + " :: "
                  + json.dumps(detail, ensure_ascii=False)[:220])

        name = "e2e_p087_" + time.strftime("%H%M%S")
        other = name + "_other"
        pkg = maestro.Package(server)
        w1 = pkg.write(maestro.WriteRequest(
            token=args.token, library=LIB, cell=CELL, view=VIEW,
            commands=[{"op": "set_var", "name": name, "value": "1.0", "scope": "global"}]))
        steps1 = [s.get("name") for s in (w1.steps or [])]
        record("save=True 有 save_setup 步骤", "save_setup" in steps1, {"steps": steps1})
        v1 = disk_value(name)
        record("save=True 磁盘值=1.0", "1.0" in v1, {"disk": v1, "sdb": sdb})

        w2 = pkg.write(maestro.WriteRequest(
            token=args.token, library=LIB, cell=CELL, view=VIEW, save=False,
            commands=[{"op": "set_var", "name": name, "value": "2.0", "scope": "global"}]))
        steps2 = [s.get("name") for s in (w2.steps or [])]
        record("save=False 无 save_setup 步骤", "save_setup" not in steps2, {"steps": steps2})
        v2 = disk_value(name)
        record("save=False 后立即查磁盘仍为 1.0（未立即落盘）", "1.0" in v2,
               {"disk": v2, "sdb": sdb})

        # 触发一次无关的 save=True 写：若上一步的 2.0 被带走 ⇒ 泄漏（P-087 RED）
        w_trigger = pkg.write(maestro.WriteRequest(
            token=args.token, library=LIB, cell=CELL, view=VIEW,
            commands=[{"op": "set_var", "name": other, "value": "ok", "scope": "global"}]))
        v3 = disk_value(name)
        record("P-087 判据：后续 save=True 后旧变量不得变 2.0", "2.0" not in v3,
               {"disk": v3, "expected": "仍为 1.0", "trigger_steps": [
                   s.get("name") for s in (w_trigger.steps or [])], "sdb": sdb})

        for victim in (name, other):
            w3 = pkg.write(maestro.WriteRequest(
                token=args.token, library=LIB, cell=CELL, view=VIEW,
                commands=[{"op": "delete_var", "name": victim, "scope": "all"}]))
            record(f"清理 {victim}", bool(w3.ok), {"error": (w3.error or "")[:160]})
    finally:
        server.close()

    verdict = "GREEN" if all(c["ok"] for c in checks) else "RED"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(
        {"probe": "maestro_save_false_disk_probe", "env": env, "checks": checks,
         "verdict": verdict}, ensure_ascii=False, indent=1), encoding="utf-8")
    print("verdict:", verdict)
    print("evidence:", args.out)
    return 0 if verdict == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
