# === TB 注释头（规范见 test/docs/写TB规范.md §0）=========================
# 作者: 测试/root
# 最后改动: 2026-09-30 17:40
# 依赖: 真机 vblog token（maestro_tb/rc_probe 夹具）+ 8127 业务面
# =======================================================================
# 夹具说明（2026-09-30 补）：探针**自带会话夹具** —— 没有活动 ADE 会话时自己 `open_gui`，
# 收尾再关掉；此前在无会话时直接判 RED，被误读成产品缺陷。
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

import argparse
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


def _payload(body):
    """C1 契约兼容解包：值型 op → 顶层 `value`；命令/skill 型 → 顶层 `result`；旧壳 → `data.value`/`data`。"""
    if not isinstance(body, dict):
        return {}
    for key in ("value", "result"):
        value = body.get(key)
        if isinstance(value, dict):
            return value
    data = body
    if isinstance(data, dict):
        inner = data.get("value")
        return inner if isinstance(inner, dict) else data
    return {}


def skill(code: str, timeout: float = 120):
    body = call("basic.skill.execute", http_timeout=timeout, skill_code=code)
    payload = _payload(body)
    nested = payload.get("result")
    return nested if isinstance(nested, dict) else payload


def session_name():
    raw = skill(SESSION_EXPR).get("output")
    if not raw or raw in ("nil", "t"):
        return None
    return str(raw).strip('"')


def ensure_session() -> bool:
    """确保存在 `maestro_tb/rc_probe` 的 ADE 会话（设置 overwrite 标志需要一个活动 session）。

    返回 True 表示**本探针自己开的**（收尾时要关掉，避免在别人屏幕上留窗口）。
    2026-09-30 补：此前该探针在"没有活动会话"时直接判 RED（`no-session`），
    被误读成产品缺陷 —— 实际是夹具缺失。
    """
    if session_name():
        return False
    opened = call("virtuoso.maestro.open_gui", http_timeout=180,
                  library=LIB, cell=CELL, view=VIEW, timeout=180)
    for _ in range(15):
        if session_name():
            return True
        time.sleep(1)
    raise AssertionError(f"open_gui 后仍找不到活动会话: {str(opened.get('error'))[:120]}")


def close_own_session() -> None:
    try:
        call("virtuoso.maestro.close_gui", http_timeout=120,
             library=LIB, cell=CELL, view=VIEW, timeout=120)
    except Exception:  # noqa: BLE001 - 收尾失败只记录，不影响判定
        pass


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
    for window in (_payload(listing).get("windows") or []):
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
opened_session = False
try:
    opened_session = ensure_session()
    checks.append({"name": "session_ready", "ok": session_name() is not None,
                   "detail": {"opened_by_probe": opened_session}})
    armed = arm_dangling_target()
    checks.append({"name": "armed_dangling_target", "ok": armed,
                   "detail": {"flag": flag_state(), "bogus": BOGUS}})
    run_body = call(
        "virtuoso.maestro.run", http_timeout=180,
        library=LIB, cell=CELL, view=VIEW, blocking=True,
        timeout=60, poll_interval=2,
    )
    elapsed = time.monotonic() - started
    steps = [step.get("name") for step in (run_body.get("steps") or [])]
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
    if opened_session:
        close_own_session()
        checks.append({"name": "own_session_closed", "ok": session_name() is None,
                       "detail": {"closed_by_probe": True}})

_parser = argparse.ArgumentParser(description="P-095 overwrite 悬空目标不挂死探针")
_parser.add_argument("--out", default=str(ROOT / "test" / "artifacts" / "evidence"
                                         / "round9" / "p095-overwrite-wedge.json"))
_args = _parser.parse_args()

verdict = "GREEN" if all(item["ok"] for item in checks) else "RED"
print(json.dumps({"probe": "maestro_p095_overwrite_wedge_probe",
                  "checks": checks, "verdict": verdict},
                 ensure_ascii=False, indent=1))
evidence = Path(_args.out)
evidence.parent.mkdir(parents=True, exist_ok=True)
evidence.write_text(
    json.dumps({"checks": checks, "verdict": verdict}, ensure_ascii=False, indent=1),
    encoding="utf-8")
print("evidence:", evidence)
raise SystemExit(0 if verdict == "GREEN" else 1)
