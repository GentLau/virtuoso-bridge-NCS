"""Shared helpers for the maestro test benches.

Talks to the business face (default http://127.0.0.1:8127) so the TBs exercise
exactly the path a real caller uses.
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
API = "http://127.0.0.1:8127/api/operation"
DEFAULT_TOKEN = "vb-vblog"


def call(operation: str, token: str = DEFAULT_TOKEN, timeout: float = 300.0, **payload):
    """POST one operation; returns the full response envelope."""
    body = json.dumps({"operation": operation, "token": token, **payload}).encode("utf-8")
    req = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:  # keep the body for debugging
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from None


def data(operation: str, token: str = DEFAULT_TOKEN, timeout: float = 300.0, **payload):
    """Like call() but returns the inner data dict, raising on ok=false."""
    env = call(operation, token=token, timeout=timeout, **payload)
    if not env.get("ok"):
        raise RuntimeError(f"{operation} failed: {env.get('error')}")
    return env["data"]


def skill(code: str, token: str = DEFAULT_TOKEN, timeout: float = 300.0):
    """Run SKILL text; returns (ok, output, errors)."""
    inner = data("basic.skill.execute", token=token, timeout=timeout, skill_code=code)
    result = inner["result"]
    return result["status"] == "success", result.get("output", ""), result.get("errors", [])


def shell(cmd: str, token: str = DEFAULT_TOKEN, timeout: float = 300.0):
    """Run a shell command on the command role."""
    inner = data("basic.command.run", token=token, timeout=timeout, cmd=cmd)
    rc, out, err = inner["result"][0], inner["result"][1], inner["result"][2]
    return rc, out, err


def unquote(value: str) -> str:
    """Strip the SKILL string quoting a daemon result may carry."""
    text = (value or "").strip()
    if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    return text.replace('\\"', '"').replace("\\n", "\n")


def send_key(window_id: str, key: str = "escape", token: str = DEFAULT_TOKEN):
    """Send one X11 key to a window, reusing the gui package's own script.

    Goes through basic.gui.run so it works even while the SKILL channel is
    blocked by a modal dialog.
    """
    if str(ROOT / "src") not in sys.path:
        sys.path.insert(0, str(ROOT / "src"))
    from pyapi.packages import gui as gui_pkg

    cmd = (
        gui_pkg._DISPLAY_PREFIX
        + f'\npython3 - "{window_id}" "{key}" <<\'PY\'\n'
        + gui_pkg._SEND_KEY_SCRIPT
        + "\nPY"
    )
    return data("basic.gui.run", token=token, cmd=cmd, timeout=120)


def xwininfo(pattern: str, display: str = ":99", token: str = DEFAULT_TOKEN):
    """List X11 windows whose title matches a grep pattern."""
    r = data(
        "basic.gui.run", token=token, timeout=120,
        cmd=f"DISPLAY={display} xwininfo -root -tree | grep -i -E '{pattern}'",
    )
    return r["result"][1]


def artifacts_dir() -> Path:
    """Client-side artifact directory for this TB."""
    path = ROOT / "test" / "tb" / "artifacts" / "maestro-tb"
    path.mkdir(parents=True, exist_ok=True)
    return path


def main():
    """Quick smoke check: python test/tb/_maestro_tb.py"""
    ok, out, errors = skill("1+1")
    print("skill 1+1 ->", ok, out, errors)
    rc, out, err = shell("echo tb-ok; uname -n")
    print("command ->", rc, out.strip(), err.strip())
    print(json.dumps(data("demo.paths.facts"), ensure_ascii=False)[:400])


if __name__ == "__main__":
    sys.exit(main())
