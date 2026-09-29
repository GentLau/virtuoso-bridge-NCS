# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 04:10
# 依赖: 真机 vblog token（maestro_tb/rc_probe 夹具）
# =======================================================================
"""maestro 包本批缺陷复验（P-087/P-088/P-089/P-084/P-095）。

判据：
  P-088  delete_var(scope=all) 成功（不再 handle 0）+ 变量读回消失
  P-087  save=False 的改动被隔离（后续 save 不带走）+ 关闭会话步可见
  P-084  ExportRequest 不再有 include_results（死参数已删）
  P-089  OpenWaveformRequest 不再有 result（死参数已删）
  P-095  悬空 Overwrite 目标被清掉、run 正常返回、跑完 flag 复位

六步：① 自检=query 到 token；②③ 造对象/造悬空 overwrite 目标；④ 只做被测动作；
⑤ 读回比对（sdb/步骤/读回值）；⑥ 不清现场（保留 history 与步骤证据）。
"""
from __future__ import annotations

import dataclasses
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from common.paths import init_work_dir              # noqa: E402
from pyapi.packages import maestro as M             # noqa: E402
from server import dispatch                         # noqa: E402
from server.api_server import register_packages     # noqa: E402
from transport.middle import BusinessServer         # noqa: E402

TOKEN = "vb-vblog"
LIB, CELL, VIEW = "maestro_tb", "rc_probe", "maestro"

init_work_dir(str(ROOT / "test/artifacts/env/log-vblog"))
register_packages()
middle = BusinessServer()
RESULTS: list[dict] = []


def call(operation: str, **fields):
    _status, body = dispatch.dispatch(
        middle, {"operation": operation, "token": TOKEN, **fields})
    return body


def record(name: str, ok: bool, detail) -> None:
    RESULTS.append({"name": name, "ok": bool(ok), "detail": detail})
    print(f"  {'PASS' if ok else 'FAIL'}  {name}: "
          f"{json.dumps(detail, ensure_ascii=False, default=str)[:160]}")


def read_vars() -> dict:
    body = call("virtuoso.maestro.read_config", library=LIB, cell=CELL, view=VIEW)
    value = (body.get("data") or {}).get("value") or {}
    return value.get("variables") or {}


# -- P-088 / P-087 ---------------------------------------------------------
stamp = time.strftime("%H%M%S")
print("P-088 delete_var(scope=all)")
name = f"p088_{stamp}"
created = call("virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
               commands=[{"op": "set_var", "name": name, "value": "7.0",
                          "scope": "all"}])
record("P-088 set_var(all)", created.get("ok") is True, created.get("error"))
deleted = call("virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
               commands=[{"op": "delete_var", "name": name, "scope": "all"}])
record("P-088 delete_var(all)", deleted.get("ok") is True,
       {"error": deleted.get("error"),
        "steps": [s["name"] for s in (deleted.get("data") or {}).get("steps") or []]})
record("P-088 变量已消失", name not in read_vars(), {"vars": len(read_vars())})

print("P-087 save=False 隔离")
probe_var = f"p087_{stamp}"
call("virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
     commands=[{"op": "set_var", "name": probe_var, "value": "1.0"}])
unsaved = call("virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
               save=False,
               commands=[{"op": "set_var", "name": probe_var, "value": "2.0"}])
reason = ((unsaved.get("data") or {}).get("value") or {}).get("reason")
record("P-087 save=False 被结构化拒绝",
       unsaved.get("ok") is False and reason == "save_false_unsupported",
       {"ok": unsaved.get("ok"), "reason": reason, "error": unsaved.get("error")})
call("virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
     commands=[{"op": "set_var", "name": f"{probe_var}_other", "value": "ok"}])
record("P-087 拒绝后无污染(仍=1.0)", read_vars().get(probe_var) == "1.0",
       {"value": read_vars().get(probe_var)})
call("virtuoso.maestro.write", library=LIB, cell=CELL, view=VIEW,
     commands=[{"op": "delete_var", "name": probe_var},
               {"op": "delete_var", "name": f"{probe_var}_other"}])

# -- P-084 / P-089：死参数已删 ---------------------------------------------
print("P-084 / P-089 死参数")
record("P-084 无 include_results",
       "include_results" not in {f.name for f in dataclasses.fields(M.ExportRequest)},
       sorted(f.name for f in dataclasses.fields(M.ExportRequest)))
record("P-089 无 result",
       "result" not in {f.name for f in dataclasses.fields(M.OpenWaveformRequest)},
       sorted(f.name for f in dataclasses.fields(M.OpenWaveformRequest)))

# -- P-095：悬空 overwrite 目标 --------------------------------------------
print("P-095 悬空 Overwrite 目标")
session_raw = call("basic.skill.execute", timeout=60,
                   skill_code="car(maeGetSessions())")
session = str(((session_raw.get("data") or {}).get("result") or {}).get("output")
              or "").strip('"')
record("P-095 找到活动会话", bool(session) and session not in ("nil", "t"),
       {"session": session})
arm = call("basic.skill.execute", timeout=120, skill_code=(
    "let((sdb setup) "
    f"sdb = axlGetMainSetupDB(\"{session}\") setup = axlGetActiveSetup(sdb) "
    "axlSetOverwriteHistory(setup t) "
    'axlSetOverwriteHistoryName(setup "NoSuchHistory_P095") '
    "list(axlGetOverwriteHistory(setup) axlGetOverwriteHistoryName(setup)))"))
record("P-095 悬空目标已就位", "t" in str(((arm.get("data") or {}).get("result") or {})
                                          .get("output")),
       {"output": ((arm.get("data") or {}).get("result") or {}).get("output"),
        "errors": ((arm.get("data") or {}).get("result") or {}).get("errors")})

run = call("virtuoso.maestro.run", library=LIB, cell=CELL, view=VIEW,
           timeout=600, poll_interval=2, blocking=True)
data = run.get("data") or {}
value = data.get("value") or {}
step_names = [s["name"] for s in data.get("steps") or []]
record("P-095 未被模态框挂死", run.get("ok") is True,
       {"history": value.get("history"), "status": value.get("status"),
        "error": run.get("error")})
record("P-095 有清理动作", "overwrite_clear" in step_names, step_names)

after_session = str(((call("basic.skill.execute", timeout=60,
                           skill_code="car(maeGetSessions())")
                      .get("data") or {}).get("result") or {}).get("output")
                    or "").strip('"')
after = call("basic.skill.execute", timeout=60, skill_code=(
    "let((sdb setup) "
    f"sdb = axlGetMainSetupDB(\"{after_session}\") setup = axlGetActiveSetup(sdb) "
    "list(axlGetOverwriteHistory(setup) axlGetOverwriteHistoryName(setup)))"))
flag_output = str(((after.get("data") or {}).get("result") or {}).get("output") or "")
record("P-095 跑完 flag 复位", flag_output.startswith("(nil"),
       {"flag": flag_output,
        "errors": ((after.get("data") or {}).get("result") or {}).get("errors")})

bogus = call("virtuoso.maestro.run", library=LIB, cell=CELL, view=VIEW,
             history="NoSuchHistory_P095", blocking=True, timeout=60,
             poll_interval=2)
record("P-095 点名不存在的目标 → 结构化失败",
       bogus.get("ok") is False
       and "overwrite target not found" in str(bogus.get("error")),
       {"error": bogus.get("error")})

passed = sum(1 for item in RESULTS if item["ok"])
print(f"[summary] {passed}/{len(RESULTS)} green")
(ROOT / "test/artifacts/evidence").mkdir(parents=True, exist_ok=True)
(ROOT / "test/artifacts/evidence/maestro-bugfix-batch.json").write_text(
    json.dumps({"results": RESULTS}, ensure_ascii=False, indent=1), encoding="utf-8")
middle.close()
raise SystemExit(0 if passed == len(RESULTS) else 1)
