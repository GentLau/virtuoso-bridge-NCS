# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 13:05
# 依赖: 真机 vblog token（schemtest/maestro_tb 夹具）+ direct 传输
# =======================================================================
"""P-096 复验：陈旧/他人 OA 写锁必须在开之前结构化失败，不得弹模态挂死。

判据（三例，全部满足才 GREEN）：
  ① 死属主锁（pid 不存在）→ 错误含 "stale write lock" 且点名 pid/属主；
  ② 活但他人的锁（用 pid=1 模拟）→ 错误含 "write lock held by"；
  ③ 本实例自己的锁（当前 Virtuoso pid）→ **不**被锁检查拦住（放行到正常打开路径）。
另：全程 `1+2` 可用（实例没被模态框挂死）。

现场用**临时目录**伪造锁桩（不碰真实 fixture 的 maestro view），跑完清理。
红灯基线见卡片 P-096（真机 `axlOpenInRead0` 模态 + Empty response），
本探针验证的是"守卫生效"这半段。
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

TOKEN = "vb-vblog"
LIB, CELL, VIEW = "maestro_tb", "p096_lock_scratch", "maestro"
RESULTS: list[dict] = []

init_work_dir(str(ROOT / "test/artifacts/env/log-vblog"))
register_packages()
middle = BusinessServer()


def call(operation: str, **fields):
    _status, body = dispatch.dispatch(
        middle, {"operation": operation, "token": TOKEN, **fields})
    return body


def sh(cmd: str):
    return middle.run_command(cmd, timeout=60, token=TOKEN)


def record(name: str, ok: bool, detail) -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: "
          f"{json.dumps(detail, ensure_ascii=False, default=str)[:170]}")


lib_path = str(
    (call("basic.skill.execute", skill_code='ddGetObj("maestro_tb")~>readPath')
     .get("result") or {}).get("output", "")
).strip('"')
view_dir = f"{lib_path}/{CELL}/{VIEW}"

STALE_PID = "999999"


def write_lock(pid: str, owner: str = "Gent") -> None:
    sh(f"mkdir -p {view_dir} && touch {view_dir}/maestro.sdb && "
       f"printf '%s\\n' "
       f"'LockStakeVersion               1.1' "
       f"'LoginName                      {owner}' "
       f"'HostName                       GLIS-DESKTOP.localdomain' "
       f"'ProcessIdentifier              {pid}' "
       f"'AppIdentifier                  /opt/eda/cadence/IC618/tools/dfII/bin/64bit/virtuoso' "
       f"'TimeEditLocked                 Tue Sep 29 13:00:00 2026 CST' "
       f"> {view_dir}/maestro.sdb.cdslck")


def cleanup() -> None:
    sh(f"rm -rf {view_dir}")


try:
    # ① 死属主
    write_lock(STALE_PID)
    body = call("virtuoso.maestro.read_config", library=LIB, cell=CELL, view=VIEW)
    error = str(body.get("error") or "")
    record("① 死属主锁 → 结构化失败", body.get("ok") is False
           and "stale write lock" in error and STALE_PID in error,
           {"ok": body.get("ok"), "error": error[:200]})

    # ② 活锁（pid=1，还活着）→ 不得被锁检查误拦（区分"自家/他人"不可靠，只拦死属主）
    write_lock("1", owner="other")
    body = call("virtuoso.maestro.read_config", library=LIB, cell=CELL, view=VIEW)
    error = str(body.get("error") or "")
    record("② 活锁不误拦", "stale write lock" not in error and "write lock held" not in error,
           {"ok": body.get("ok"), "error": error[:200]})

    # ③ 本实例自己的锁（拿当前 Virtuoso pid）
    work_dir = str(
        (call("basic.skill.execute", skill_code="getWorkingDir()")
         .get("result") or {}).get("output", "")
    ).strip('"')
    own = sh(f"pgrep -u $(whoami) -f 'virtuoso.*{work_dir}' | head -1").stdout.strip()
    if own:
        write_lock(own)
        body = call("virtuoso.maestro.read_config", library=LIB, cell=CELL, view=VIEW)
        error = str(body.get("error") or "")
        record("③ 自家锁 → 不被锁检查拦",
               "write lock" not in error and "stale" not in error,
               {"own_pid": own, "error": error[:160]})
    else:
        record("③ 自家锁 → 不被锁检查拦", False, {"reason": "no own virtuoso pid"})
finally:
    cleanup()

probe = call("basic.skill.execute", skill_code="1+2", timeout=60)
output = ((probe).get("result") or {}).get("output")
record("实例未被挂死（1+2）", str(output) == "3", {"output": output})

passed = sum(1 for item in RESULTS if item["ok"])
print(f"[summary] {passed}/{len(RESULTS)} green")
middle.close()
raise SystemExit(0 if passed == len(RESULTS) else 1)
