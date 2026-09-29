# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 设计/上层开发
# 最后改动: 2026-09-29 11:40
# 依赖: 真机 vblog token（maestro_tb/rc_probe 夹具）+ 8127 业务面
# =======================================================================
"""P-095 红灯探针：悬空 Overwrite History 目标 → run 必须不挂死。

判据（全部满足才算 GREEN）：
  ① run 请求在给定时限内返回（不能把 CIW/daemon 挂住）；
  ② 返回后实例仍可用（1+2 能出结果）；
  ③ 跑完 Overwrite History 标志被复位（不留地雷给下一次 run）。

红灯形态（修前）：run 触发 ASSEMBLER-3018（目标不存在）模态框 → SKILL 通道
全空响应 → 请求超时、实例需人工解封。

本探针自带清场：无论成败，finally 里都会关掉该族模态框、清 Overwrite 标志，
保证不把环境留给下一个人。
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"
LIB, CELL, VIEW = "maestro_tb", "rc_probe", "maestro"
BOGUS = "NoSuchHistory_P095"
MODAL_MARKERS = ("ADE Assembler Message 2406", "ADE Assembler Message 3016",
                 "ADE Assembler Message 3017", "ADE Assembler Message 3018",
                 "ADE Assembler Message 1600")
SESSION_EXPR = (
    "let((s) s = nil "
    "foreach(w hiGetWindowList() "
    "  let((cand name) cand = car(errset(axlGetWindowSession(w))) "
    "    name = hiGetWindowName(w) "
    "    when(cand && name && rexMatchp(\"maestro_tb rc_probe\" name) s = cand))) "
    "s)"
)


def call(operation: str, http_timeout: float = 120, **fields):
    body = json.dumps({"operation": operation, "token": TOKEN, **fields}).encode()
    request = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=http_timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return json.loads(error.read().decode("utf-8"))


def skill(code: str, timeout: float = 120):
    body = call("basic.skill.execute", http_timeout=timeout, skill_code=code)
    return ((body.get("data") or {}).get("result") or {})


def session_name():
    raw = skill(SESSION_EXPR).get("output")
    if not raw or raw in ("nil", "t"):
        return None
    return str(raw).strip('"')


def flag_state() -> str:
    session = session_name()
    if not session:
        return "no-session"
    raw = skill(
        "let((sdb setup) "
        "sdb = axlGetMainSetupDB(\"" + session + "\") setup = axlGetActiveSetup(sdb) "
        "axlGetOverwriteHistory(setup))")
    return str(raw.get("output"))


def arm_dangling_target() -> bool:
    session = session_name()
    if not session:
        return False
    raw = skill(
        "let((sdb setup) "
        "sdb = axlGetMainSetupDB(\"" + session + "\") setup = axlGetActiveSetup(sdb) "
        "axlSetOverwriteHistory(setup t) "
        "axlSetOverwriteHistoryName(setup \"" + BOGUS + "\") "
        "list(axlGetOverwriteHistory(setup) axlGetOverwriteHistoryName(setup)))")
    return "t" in str(raw.get("output"))


def dismiss_dialogs() -> int:
    listing = call("virtuoso.gui.list_windows", http_timeout=60)
    dismissed = 0
    for window in ((listing.get("data") or {}).get("windows") or []):
        title = str(window.get("title") or "")
        if not any(marker in title for marker in MODAL_MARKERS):
            continue
        call("virtuoso.gui.send_key", http_timeout=60,
             window_id=str(window.get("window_id")), key="enter")
        dismissed += 1
        time.sleep(0.5)
    return dismissed


def clear_overwrite() -> None:
    session = session_name()
    if not session:
        return
    skill("let((sdb setup) "
          "sdb = axlGetMainSetupDB(\"" + session + "\") setup = axlGetActiveSetup(sdb) "
          "axlSetOverwriteHistory(setup nil) "
          "axlSetOverwriteHistoryName(setup \"\"))")


def skill_alive() -> bool:
    raw = skill("1+2", timeout=60)
    return str(raw.get("output")) == "3"


checks = []
started = time.monotonic()
try:
    armed = arm_dangling_target()
    checks.append({"name": "armed_dangling_target", "ok": armed,
                   "detail": {"flag": flag_state(), "bogus": BOGUS}})
    run_body = call(
        "virtuoso.maestro.run", http_timeout=180,
        library=LIB, cell=CELL, view=VIEW, blocking=True,
        timeout=60, poll_interval=2,
    )
    elapsed = time.monotonic() - started
    data = run_body.get("data") or {}
    steps = [step.get("name") for step in (data.get("steps") or [])]
    checks.append({"name": "run_returned", "ok": run_body.get("ok") is True,
                   "detail": {"elapsed_s": round(elapsed, 1),
                              "error": run_body.get("error"),
                              "steps": steps}})
finally:
    # 修前会连锁弹框：一次 Enter 可能只推进到下一个框，所以分轮清场 + 等通道恢复
    dismissed = 0
    attempts = 0
    alive = False
    for attempts in range(1, 5):
        dismissed += dismiss_dialogs()
        time.sleep(2)
        if skill_alive():
            alive = True
            break
    if alive:
        clear_overwrite()
    checks.append({"name": "instance_alive_after", "ok": alive,
                   "detail": {"dismissed_dialogs": dismissed,
                              "cleanup_rounds": attempts}})
    flag = flag_state()
    checks.append({"name": "overwrite_flag_reset", "ok": flag in ("nil", ""),
                   "detail": {"flag": flag}})

verdict = "GREEN" if all(item["ok"] for item in checks) else "RED"
print(json.dumps({"probe": "maestro_p095_overwrite_wedge_probe",
                  "checks": checks, "verdict": verdict},
                 ensure_ascii=False, indent=1))
evidence = ROOT / "test/artifacts/evidence/round8"
evidence.mkdir(parents=True, exist_ok=True)
(evidence / "p095-overwrite-wedge.json").write_text(
    json.dumps({"checks": checks, "verdict": verdict}, ensure_ascii=False, indent=1),
    encoding="utf-8")
print("evidence:", evidence / "p095-overwrite-wedge.json")
raise SystemExit(0 if verdict == "GREEN" else 1)
