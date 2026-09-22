"""Minimal end-to-end probe of the Maestro flow, using raw SKILL.

Purpose: prove out (before writing the package) that this environment can
  1. create a maestro view on a cell via maeOpenSetup/maeSaveSetup
  2. create a test + analyses + outputs
  3. run a simulation and see it complete
  4. read the results back

    python test/tb/maestro_e2e_probe.py [step]
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

try:  # keep ® and other SKILL output printable on a GBK console
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:  # noqa: BLE001
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _maestro_tb import DEFAULT_TOKEN, shell, skill, unquote  # noqa: E402

LIB = "maestro_tb"
CELL = "rc_probe"


def step_lib():
    """Create the test library and a simple RC schematic."""
    code = (
        'let((lib) '
        f'  lib = ddGetObj("{LIB}") '
        '  if(lib "exists" '
        f'    progn(lib = ddCreateLib("{LIB}" "/home/Gent/project/vblog/{LIB}") '
        '      if(lib "created" "createFailed"))))'
    )
    ok, out, err = skill(code)
    print("lib:", ok, unquote(out), err)


def step_schematic():
    """vdc -> res -> cap, with a wire and net labels; AC-friendly."""
    code = f'''
let((cv)
  cv = dbOpenCellViewByType("{LIB}" "{CELL}" "schematic" "schematic" "w")
  unless(cv error("open schematic failed"))
  dbCreateInst(cv dbOpenCellViewByType("analogLib" "vdc" "symbol" "schematicSymbol" "r") "V0" list(0.0 0.0) "R0")
  dbCreateInst(cv dbOpenCellViewByType("analogLib" "res" "symbol" "schematicSymbol" "r") "R0" list(2.0 0.0) "R0")
  dbCreateInst(cv dbOpenCellViewByType("analogLib" "cap" "symbol" "schematicSymbol" "r") "C0" list(4.0 0.0) "R0")
  schCreateWire(cv "route" "full" list(0.0:0.0 2.0:0.0) 0 0 0 nil nil)
  schCreateWire(cv "route" "full" list(2.0:0.0 4.0:0.0) 0 0 0 nil nil)
  schCreateWireLabel(cv nil 1.0:0.06 "IN" "lowerCenter" "R0" "stick" 0.0625 nil)
  schCreateWireLabel(cv nil 3.0:0.06 "OUT" "lowerCenter" "R0" "stick" 0.0625 nil)
  schCheck(cv)
  dbSave(cv)
  dbClose(cv)
  "schematic-ok")
'''
    ok, out, err = skill(code)
    print("schematic:", ok, unquote(out), err)
    return ok


def step_maestro_view():
    """Create the maestro view (the M3 'ensure' behaviour)."""
    code = (
        'let((sess rc) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("maeOpenSetup failed")) '
        f'  rc = maeSaveSetup(?session sess) '
        '  maeCloseSession(?session sess ?forceClose t) '
        '  if(rc "maestro-ok" "save-failed"))'
    )
    ok, out, err = skill(code, timeout=300)
    print("maestro view:", ok, unquote(out), err)
    return ok


def step_inspect():
    """What does maeOpenSetup give us; what are the sessions."""
    code = (
        'let((sess out) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("open failed")) '
        '  out = sprintf(nil "session=%L sessions=%L" sess maeGetSessions()) '
        '  maeCloseSession(?session sess ?forceClose t) '
        "out)"
    )
    ok, out, err = skill(code, timeout=300)
    print("inspect:", ok, unquote(out), err)


def step_disk():
    rc, out, err = shell(
        f"echo ---lib---; ls -la /home/Gent/project/vblog/{LIB}/ 2>/dev/null | head; "
        f"echo ---cell---; ls -la /home/Gent/project/vblog/{LIB}/{CELL}/ 2>/dev/null | head -20"
    )
    print("disk:", rc, err.strip())
    print(out)


def step_test():
    """Create a test in the maestro setup and list what we have."""
    code = (
        'let((sess out) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("open failed")) '
        f'  out = errset(maeCreateTest("ac" ?lib "{LIB}" ?cell "{CELL}" '
        '?view "schematic" ?simulator "spectre" ?session sess) nil) '
        '  maeSaveSetup(?session sess) '
        '  maeCloseSession(?session sess ?forceClose t) '
        '  sprintf(nil "create=%L" out))'
    )
    ok, out, err = skill(code, timeout=300)
    print("test:", ok, unquote(out), err)


def step_state():
    """Inspect the setup DB: tests, analyses, outputs, corners."""
    code = (
        'let((sess out tests h) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("open failed")) '
        '  tests = errset(maeGetTestSession("ac" ?session sess) nil) '
        '  h = errset(axlGetMainSetupDB(sess) nil) '
        '  out = sprintf(nil "testSession=%L\\nsetupDB=%L\\n" tests h) '
        '  maeCloseSession(?session sess ?forceClose t) '
        "  out)"
    )
    ok, out, err = skill(code, timeout=300)
    print("state:", ok, unquote(out), err)


def step_analysis():
    code = (
        'let((sess rc) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("open failed")) '
        '  rc = errset(maeSetAnalysis("ac" "ac" ?enable t '
        '?options `(("start" "1") ("stop" "1G") ("dec" "20")) ?session sess) nil) '
        '  maeSaveSetup(?session sess) '
        '  maeCloseSession(?session sess ?forceClose t) '
        '  sprintf(nil "setAnalysis=%L" rc))'
    )
    ok, out, err = skill(code, timeout=300)
    print("analysis:", ok, unquote(out), err)


def step_run():
    code = (
        'let((sess rc) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("open failed")) '
        '  rc = errset(maeRunSimulation(?session sess) nil) '
        '  sprintf(nil "run=%L sessions=%L" rc maeGetSessions()))'
    )
    ok, out, err = skill(code, timeout=600)
    print("run:", ok, unquote(out), err)


def step_status():
    """Run status of a history + what the results tree looks like."""
    code = (
        'let((sess out rc) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("open failed")) '
        '  rc = errset(axlGetRunStatus(sess) nil) '
        '  out = sprintf(nil "runStatus=%L\\n" rc) '
        '  rc = errset(axlGetHistory(axlGetMainSetupDB(sess)) nil) '
        '  out = strcat(out sprintf(nil "history=%L\\n" rc)) '
        '  rc = errset(axlGetCurrentHistory(axlGetMainSetupDB(sess)) nil) '
        '  out = strcat(out sprintf(nil "current=%L\\n" rc)) '
        '  maeCloseSession(?session sess ?forceClose t) '
        "  out)"
    )
    ok, out, err = skill(code, timeout=300)
    print("status:", ok, unquote(out), err)


def step_results_disk():
    rc, out, err = shell(
        f"find /home/Gent/project/vblog/{LIB}/{CELL} -maxdepth 3 -name '*Interactive*' -o -maxdepth 3 -name 'results' "
        f"| head -10; echo ---; ls -R /home/Gent/project/vblog/{LIB}/{CELL}/maestro 2>/dev/null | head -40"
    )
    print("results disk:", rc, err.strip())
    print(out)


def step_run_clean(wait_seconds: int = 45):
    """Start a run and leave everything alone; then look at the log."""
    code = (
        'let((sess rc) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("open failed")) '
        '  rc = errset(maeRunSimulation(?session sess) nil) '
        '  sprintf(nil "run=%L" rc))'
    )
    ok, out, err = skill(code, timeout=600)
    print("start:", ok, unquote(out), err)
    rc, out, err = shell(f"sleep {wait_seconds}; echo waited")
    print("waited:", rc, out.strip(), err.strip())
    rc, out, err = shell(
        f"tail -20 /home/Gent/project/vblog/{LIB}/{CELL}/maestro/results/maestro/*.log | tail -25; "
        f"echo ---dirs---; ls /home/Gent/project/vblog/{LIB}/{CELL}/maestro/results/maestro/ "
    )
    print("after:", rc, err.strip())
    print(out)


def step_watch(run_id: int = 2, polls: int = 12, interval: int = 10):
    """Start a run, then poll ONLY the log via shell — no SKILL calls at all.

    Answers: does the simulation survive when nothing touches the session?
    """
    code = (
        'let((sess rc) '
        f'  sess = maeOpenSetup("{LIB}" "{CELL}" "maestro") '
        '  unless(sess error("open failed")) '
        '  rc = errset(maeRunSimulation(?session sess) nil) '
        '  sprintf(nil "run=%L" rc))'
    )
    ok, out, err = skill(code, timeout=600)
    print(f"[t=0] start:", ok, unquote(out), err)
    import time as _time
    started = _time.time()
    for i in range(polls):
        _time.sleep(interval)
        el = int(_time.time() - started)
        rc, out, err = shell(
            f"tail -3 /home/Gent/project/vblog/{LIB}/{CELL}/maestro/results/maestro/"
            f"Interactive.{run_id}.log 2>/dev/null | tr '\\n' ' '; echo; "
            f"ls -d /home/Gent/project/vblog/{LIB}/{CELL}/maestro/results/maestro/"
            f"Interactive.{run_id} 2>/dev/null || true",
            timeout=60,
        )
        print(f"[t={el}s] {out.strip()}")


SESSION_PROBE = '''
let((out)
  out = ""
  out = strcat(out sprintf(nil "sessions=%L\\n" maeGetSessions()))
  foreach(w hiGetWindowList()
    let((nm sess)
      nm = errset(hiGetWindowName(w) nil)
      sess = errset(axlGetWindowSession(w) nil)
      when(nm && car(nm)
        out = strcat(out sprintf(nil "win num=%L title=%L session=%L\\n"
          w~>windowNum car(nm) sess)))))
  out)
'''


def step_sessions():
    ok, out, err = skill(SESSION_PROBE, timeout=120)
    print("sessions:", ok, err)
    print(unquote(out))


def step_close_all():
    code = (
        'let((n) n = 0 '
        "foreach(s maeGetSessions() "
        "  errset(maeCloseSession(?session s ?forceClose t) nil) n = n + 1) "
        "sprintf(nil \"closed=%d\" n))"
    )
    ok, out, err = skill(code, timeout=180)
    print("close all:", ok, unquote(out), err)


def step_gui_open():
    """Close background sessions, then open the ADE window in editable mode."""
    code = (
        'let((out r nw) '
        "  nw = 0 "
        "  foreach(s maeGetSessions() errset(maeCloseSession(?session s ?forceClose t) nil)) "
        f'  r = errset(deOpenCellView("{LIB}" "{CELL}" "maestro" "maestro" nil "a") nil) '
        '  unless(r error("deOpenCellView failed")) '
        '  out = sprintf(nil "opened=%L" car(r)) '
        "  out)"
    )
    ok, out, err = skill(code, timeout=600)
    print("gui open:", ok, unquote(out), err)


def step_gui_run():
    """Run from the GUI session and report the history name."""
    code = (
        'let((out sess r) '
        "  sess = nil "
        "  foreach(w hiGetWindowList() "
        "    let((nm) nm = errset(hiGetWindowName(w) nil) "
        f'      when(nm && car(nm) && rexMatchp("{CELL}" car(nm)) '
        "        sess = errset(axlGetWindowSession(w) nil)))) "
        '  when(sess sess = if(listp(car(sess)) car(car(sess)) car(sess))) '
        '  unless(sess error("no session for cell")) '
        '  r = errset(maeRunSimulation(?session sess) nil) '
        '  sprintf(nil "session=%L run=%L" sess r))'
    )
    ok, out, err = skill(code, timeout=600)
    print("gui run:", ok, unquote(out), err)


def step_logwatch(run_id: str = "3", polls: int = 10, interval: int = 15):
    """Poll a run's log via shell only."""
    import time as _time
    started = _time.time()
    for _ in range(polls):
        _time.sleep(interval)
        el = int(_time.time() - started)
        rc, out, err = shell(
            f"tail -3 /home/Gent/project/vblog/{LIB}/{CELL}/maestro/results/maestro/"
            f"Interactive.{run_id}.log 2>/dev/null | tr '\\n' '~'; echo; "
            f"ls -d /home/Gent/project/vblog/{LIB}/{CELL}/maestro/results/maestro/"
            f"Interactive.{run_id} 2>/dev/null || echo no-rundir",
            timeout=60,
        )
        print(f"[t={el}s] {out.strip()}")


GUI_SESSION_EXPR = (
    "let((sess) "
    "  sess = nil "
    "  foreach(w hiGetWindowList() "
    "    let((nm s) "
    "      nm = errset(hiGetWindowName(w) nil) "
    "      when(nm && car(nm) && rexMatchp(\"" + CELL + "\" car(nm)) "
    "        s = errset(axlGetWindowSession(w) nil) "
    "        when(s && car(s) && car(s) sess = if(listp(car(s)) car(car(s)) car(s)))))) "
    "  sess)"
)


def step_jobmode():
    """Inspect and switch the job control mode to Local on the open GUI session."""
    code = (
        "let((out sess r m) "
        f"  sess = {GUI_SESSION_EXPR} "
        '  unless(sess error("no GUI session")) '
        '  m = errset(maeGetJobControlMode(?session sess) nil) '
        '  out = sprintf(nil "session=%L modeBefore=%L\\n" sess m) '
        '  r = errset(maeSetJobControlMode("Local" ?session sess) nil) '
        '  out = strcat(out sprintf(nil "setLocal=%L\\n" r)) '
        '  m = errset(maeGetJobControlMode(?session sess) nil) '
        '  out = strcat(out sprintf(nil "modeAfter=%L" m)) '
        "  out)"
    )
    ok, out, err = skill(code, timeout=300)
    print("jobmode:", ok, err)
    print(unquote(out))


def step_gui_run2():
    """Run again from the GUI session (now with Local job control)."""
    code = (
        "let((sess r) "
        f"  sess = {GUI_SESSION_EXPR} "
        '  unless(sess error("no GUI session")) '
        "  r = errset(maeRunSimulation(?session sess) nil) "
        '  sprintf(nil "run=%L" r))'
    )
    ok, out, err = skill(code, timeout=600)
    print("gui run2:", ok, unquote(out), err)


def step_try_modes():
    """Try candidate job control mode names until one sticks."""
    candidates = ["Local", "ICRP", "LSF", "SGE", "NC", "SunGrid", "PBS", "None"]
    code = (
        "let((out sess r m) "
        f"  sess = {GUI_SESSION_EXPR} "
        '  unless(sess error("no GUI session")) '
        "  out = sprintf(nil \"session=%L\\n\" sess) "
        "  foreach(cand list("
        + " ".join(f'"{c}"' for c in candidates)
        + ") "
        "    errset(maeSetJobControlMode(cand ?session sess) nil) "
        "    m = errset(maeGetJobControlMode(?session sess) nil) "
        '    out = strcat(out sprintf(nil "try %s -> now %L\\n" cand m))) '
        "  out)"
    )
    ok, out, err = skill(code, timeout=300)
    print("try modes:", ok, err)
    print(unquote(out))


STEPS = {
    "lib": step_lib,
    "schematic": step_schematic,
    "maestro": step_maestro_view,
    "inspect": step_inspect,
    "disk": step_disk,
    "test": step_test,
    "state": step_state,
    "analysis": step_analysis,
    "run": step_run,
    "status": step_status,
    "results_disk": step_results_disk,
    "run_clean": step_run_clean,
    "watch": step_watch,
    "sessions": step_sessions,
    "close_all": step_close_all,
    "gui_open": step_gui_open,
    "gui_run": step_gui_run,
    "logwatch": step_logwatch,
    "jobmode": step_jobmode,
    "gui_run2": step_gui_run2,
    "try_modes": step_try_modes,
}


def main():
    name = sys.argv[1] if len(sys.argv) > 1 else "all"
    if name == "cmd":
        rc, out, err = shell(" ".join(sys.argv[2:]), timeout=120)
        print(f"rc={rc}")
        print(out)
        if err.strip():
            print("STDERR:", err)
        return
    if name == "gui":
        from _maestro_tb import data
        r = data("basic.gui.run", token=DEFAULT_TOKEN,
                 cmd=" ".join(sys.argv[2:]), timeout=120)
        res = r["result"]
        print(f"rc={res[0]}")
        print(res[1])
        if (res[2] or "").strip():
            print("STDERR:", res[2])
        return
    if name == "il":
        # run raw SKILL from the command line (joined argv)
        ok, out, err = skill(" ".join(sys.argv[2:]), timeout=600)
        print(f"ok={ok}")
        print(unquote(out))
        if err:
            print("ERRORS:", err)
        return
    if name == "all":
        for key in ("lib", "schematic", "maestro", "inspect", "disk"):
            print(f"--- {key} ---")
            STEPS[key]()
            time.sleep(0.3)
    else:
        STEPS[name]()


if __name__ == "__main__":
    main()
