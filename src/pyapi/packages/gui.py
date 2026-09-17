"""``gui`` business package: window listing, dialog recovery, key injection, screenshot.

业务包名：gui。只调中层接口（GUI 一次性命令、文件下载、query），
不接触 transport/socket/subprocess，token 每次调用原样透传。

实现口径（spec/design-concepts/上层/10-gui.md）：
- 唯一清单入口是 X11 顶层窗口；
- 动作必须带显式 window_id，按键白名单 enter/escape；
- 动作后校验 still_mapped；
- auto_dismiss 只处理分类为 dialog 的窗口，设次数上限并保留逐窗口证据。
"""
from __future__ import annotations

import posixpath
import re
import shlex
import time
from pathlib import Path
from dataclasses import dataclass, field
from typing import Any

from pyapi.models import Middle

OPERATIONS = (
    ("virtuoso.gui.list_windows", "list_windows", "ListWindowsRequest", "ListWindowsResult"),
    ("virtuoso.gui.send_key", "send_key", "SendKeyRequest", "SendKeyResult"),
    ("virtuoso.gui.auto_dismiss", "auto_dismiss", "AutoDismissRequest", "AutoDismissResult"),
    ("virtuoso.gui.screenshot", "screenshot", "ScreenshotRequest", "ScreenshotResult"),
)

# 从 Virtuoso 进程环境里取 DISPLAY；取不到退 :0。
_DISPLAY_PREFIX = (
    "disp=$(for p in $(pgrep -f 'virtuoso' 2>/dev/null); do "
    "d=$(tr '\\0' '\\n' </proc/$p/environ 2>/dev/null | "
    "sed -n 's/^DISPLAY=\\(.*\\)/\\1/p' | head -1); "
    "[ -n \"$d\" ] && { echo \"$d\"; break; }; done); export DISPLAY=${disp:-:0}"
)

# 通过 ctypes 调 libX11/libXtst 注入一次按键（enter/escape）。
_SEND_KEY_SCRIPT = r'''
import ctypes, os, sys
wid = int(sys.argv[1], 0)
key = sys.argv[2]
x11 = ctypes.CDLL("libX11.so.6")
xtst = ctypes.CDLL("libXtst.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
x11.XSetInputFocus.restype = ctypes.c_int
x11.XSetInputFocus.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
x11.XKeysymToKeycode.restype = ctypes.c_uint
x11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
xtst.XTestFakeKeyEvent.restype = ctypes.c_int
xtst.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
x11.XFlush.restype = ctypes.c_int
x11.XFlush.argtypes = [ctypes.c_void_p]
x11.XCloseDisplay.restype = ctypes.c_int
x11.XCloseDisplay.argtypes = [ctypes.c_void_p]
d = x11.XOpenDisplay(os.environ.get("DISPLAY", ":0").encode())
if not d:
    raise SystemExit("cannot open X display")
ks = 0xFF0D if key == "enter" else 0xFF1B
x11.XSetInputFocus(d, wid, 2, 0)  # RevertToNone, CurrentTime
kc = x11.XKeysymToKeycode(d, ks)
xtst.XTestFakeKeyEvent(d, kc, 1, 0)
xtst.XTestFakeKeyEvent(d, kc, 0, 0)
x11.XFlush(d)
x11.XCloseDisplay(d)
'''

# 抓取一个 X 窗口（或 root）像素并写二进制 PPM。
_CAPTURE_SCRIPT = r'''
import ctypes, os, sys
wid_arg, out = sys.argv[1], sys.argv[2]

class XWA(ctypes.Structure):
    _fields_ = [("x", ctypes.c_int), ("y", ctypes.c_int),
                ("width", ctypes.c_int), ("height", ctypes.c_int),
                ("border_width", ctypes.c_int), ("depth", ctypes.c_int),
                ("visual", ctypes.c_void_p), ("root", ctypes.c_ulong),
                ("class_", ctypes.c_int), ("bit_gravity", ctypes.c_int),
                ("win_gravity", ctypes.c_int), ("backing_store", ctypes.c_int),
                ("backing_planes", ctypes.c_ulong), ("backing_pixel", ctypes.c_ulong),
                ("save_under", ctypes.c_int), ("colormap", ctypes.c_ulong),
                ("map_installed", ctypes.c_int), ("map_state", ctypes.c_int),
                ("all_event_masks", ctypes.c_long), ("your_event_mask", ctypes.c_long),
                ("do_not_propagate_mask", ctypes.c_long),
                ("override_redirect", ctypes.c_int), ("screen", ctypes.c_void_p)]

class XImage(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int),
                ("xoffset", ctypes.c_int), ("format", ctypes.c_int),
                ("data", ctypes.c_void_p), ("byte_order", ctypes.c_int),
                ("bitmap_unit", ctypes.c_int), ("bitmap_bit_order", ctypes.c_int),
                ("bitmap_pad", ctypes.c_int), ("depth", ctypes.c_int),
                ("bytes_per_line", ctypes.c_int), ("bits_per_pixel", ctypes.c_int),
                ("red_mask", ctypes.c_ulong), ("green_mask", ctypes.c_ulong),
                ("blue_mask", ctypes.c_ulong)]

x11 = ctypes.CDLL("libX11.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XOpenDisplay.argtypes = [ctypes.c_char_p]
x11.XDefaultRootWindow.restype = ctypes.c_ulong
x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
x11.XGetWindowAttributes.restype = ctypes.c_int
x11.XGetWindowAttributes.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p]
x11.XGetImage.restype = ctypes.c_void_p
x11.XGetImage.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.c_int,
                          ctypes.c_uint, ctypes.c_uint, ctypes.c_ulong, ctypes.c_int]
x11.XGetPixel.restype = ctypes.c_ulong
x11.XGetPixel.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
x11.XDestroyImage.restype = ctypes.c_int
x11.XDestroyImage.argtypes = [ctypes.c_void_p]
x11.XCloseDisplay.restype = ctypes.c_int
x11.XCloseDisplay.argtypes = [ctypes.c_void_p]

d = x11.XOpenDisplay(os.environ.get("DISPLAY", ":0").encode())
if not d:
    raise SystemExit("cannot open X display")
wid = x11.XDefaultRootWindow(d) if wid_arg == "root" else int(wid_arg, 0)
wa = XWA()
if not x11.XGetWindowAttributes(d, wid, ctypes.byref(wa)):
    raise SystemExit("cannot read window attributes")
w, h = wa.width, wa.height
ptr = x11.XGetImage(d, wid, 0, 0, w, h, 0xFFFFFFFF, 2)
if not ptr:
    raise SystemExit("cannot capture window")
img = XImage.from_address(ptr)

def shift(mask):
    s = 0
    while mask and not (mask & 1):
        mask >>= 1
        s += 1
    return s

rs, gs, bs = shift(img.red_mask), shift(img.green_mask), shift(img.blue_mask)
buf = bytearray(w * h * 3)
i = 0
for y in range(h):
    for x in range(w):
        p = x11.XGetPixel(ptr, x, y)
        buf[i] = (p >> rs) & 0xFF
        buf[i + 1] = (p >> gs) & 0xFF
        buf[i + 2] = (p >> bs) & 0xFF
        i += 3
x11.XDestroyImage(ptr)
x11.XCloseDisplay(d)
with open(out, "wb") as fh:
    fh.write(("P6\n%d %d\n255\n" % (w, h)).encode())
    fh.write(bytes(buf))
'''


def _require_text(value: Any, name: str) -> None:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{name} must be a non-empty string")


def _require_timeout(timeout: Any) -> None:
    if timeout is not None and (not isinstance(timeout, (int, float)) or timeout <= 0):
        raise ValueError("timeout must be a positive number or None")


def _step(name: str, ok: bool, detail: Any) -> dict[str, Any]:
    return {"name": name, "ok": ok, "detail": detail}


_WIN_LINE = re.compile(
    r'^\s*(0x[0-9a-fA-F]+)\s+(?:"([^"]*)"|\(has no name\)):\s*\(([^)]*)\)\s+'
    r'(\d+)x(\d+)\+(-?\d+)\+(-?\d+)\s+\+(-?\d+)\+(-?\d+)'
)
_DIALOG_WORDS = re.compile(r"(?i)error|warning|question|confirm|notice|dialog")


def parse_xwininfo_tree(text: str) -> list[dict[str, Any]]:
    """Parse ``xwininfo -root -tree`` into top-level window records.

    每条：window_id / title / wm_class / width / height / kind / suggested_action。
    """
    windows: list[dict[str, Any]] = []
    for line in text.splitlines():
        m = _WIN_LINE.match(line)
        if not m:
            continue
        window_id, title, cls, width, height = m.group(1), m.group(2) or "", m.group(3), m.group(4), m.group(5)
        wm_class = [item for item in re.findall(r'"([^"]*)"', cls)]
        record = {
            "window_id": window_id,
            "title": title,
            "wm_class": wm_class,
            "width": int(width),
            "height": int(height),
            "kind": "window",
            "suggested_action": None,
        }
        if not title:
            record.update(kind="anon", suggested_action="ignore")
        elif "Virtuoso" in title and "CDS.log" in title:
            record["kind"] = "ciw"
        elif "perfUtilExtCtrl" in title:
            record.update(kind="aux", suggested_action="ignore")
        elif _DIALOG_WORDS.search(title):
            record.update(kind="dialog", suggested_action="dismiss")
        else:
            record["kind"] = "window"
        windows.append(record)
    return windows


def _find_ciw(windows: list[dict[str, Any]]) -> str | None:
    for win in windows:
        if win["kind"] == "ciw":
            return win["window_id"]
    return None


# ---- requests / results ------------------------------------------------------

@dataclass(frozen=True)
class ListWindowsRequest:
    token: str
    timeout: int | None = None


@dataclass
class ListWindowsResult:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    windows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class SendKeyRequest:
    token: str
    window_id: str
    key: str = "enter"
    timeout: int | None = None


@dataclass
class SendKeyResult:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    still_mapped: bool | None = None


@dataclass(frozen=True)
class AutoDismissRequest:
    token: str
    timeout: int | None = None
    max_attempts: int = 2


@dataclass
class AutoDismissResult:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    dismissed: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class ScreenshotRequest:
    token: str
    output_path: str
    target: str = "ciw"
    timeout: int | None = None


@dataclass
class ScreenshotResult:
    ok: bool
    steps: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    local_path: str | None = None


# ---- package ----------------------------------------------------------------

class Package:
    def __init__(self, middle: Middle) -> None:
        self.middle = middle

    def list_windows(self, request: ListWindowsRequest) -> ListWindowsResult:
        _require_text(request.token, "token")
        _require_timeout(request.timeout)
        cmd = _DISPLAY_PREFIX + "\nxwininfo -root -tree"
        run = self.middle.run_gui_command(cmd, timeout=request.timeout, token=request.token)
        steps = [_step("list", run.returncode == 0, run)]
        if run.returncode != 0:
            return ListWindowsResult(False, steps, run.stderr or "xwininfo failed")
        return ListWindowsResult(True, steps, None, parse_xwininfo_tree(run.stdout))

    def send_key(self, request: SendKeyRequest) -> SendKeyResult:
        _require_text(request.token, "token")
        _require_text(request.window_id, "window_id")
        if request.key not in ("enter", "escape"):
            raise ValueError("key must be 'enter' or 'escape'")
        _require_timeout(request.timeout)
        cmd = (
            _DISPLAY_PREFIX
            + f'\npython3 - "{request.window_id}" "{request.key}" <<\'PY\'\n'
            + _SEND_KEY_SCRIPT
            + "\nPY"
        )
        sent = self.middle.run_gui_command(cmd, timeout=request.timeout, token=request.token)
        steps = [_step("send", sent.returncode == 0, sent)]
        if sent.returncode != 0:
            return SendKeyResult(False, steps, sent.stderr or "key injection failed", None)
        verify_cmd = _DISPLAY_PREFIX + f"\nxwininfo -id {request.window_id}"
        verified = self.middle.run_gui_command(
            verify_cmd, timeout=request.timeout, token=request.token,
        )
        still_mapped = verified.returncode == 0
        steps.append(_step("verify", still_mapped, verified))
        return SendKeyResult(True, steps, None, still_mapped)

    def auto_dismiss(self, request: AutoDismissRequest) -> AutoDismissResult:
        _require_text(request.token, "token")
        _require_timeout(request.timeout)
        if not isinstance(request.max_attempts, int) or request.max_attempts <= 0:
            raise ValueError("max_attempts must be a positive integer")
        listed = self.list_windows(ListWindowsRequest(request.token, request.timeout))
        steps = [_step("list", listed.ok, listed)]
        if not listed.ok:
            return AutoDismissResult(False, steps, listed.error)
        candidates = [win for win in listed.windows if win["kind"] == "dialog"]
        dismissed: list[dict[str, Any]] = []
        for win in candidates:
            record = {"window_id": win["window_id"], "title": win["title"], "attempts": []}
            still = True
            for attempt in range(request.max_attempts):
                key = "escape" if attempt == 0 else "enter"
                sent = self.send_key(
                    SendKeyRequest(request.token, win["window_id"], key, request.timeout),
                )
                record["attempts"].append({"key": key, "still_mapped": sent.still_mapped})
                still = bool(sent.still_mapped)
                if not sent.ok or not still:
                    break
            record["still_mapped"] = still
            dismissed.append(record)
        steps.append(_step("dismiss", True, dismissed))
        return AutoDismissResult(True, steps, None, dismissed)

    def screenshot(self, request: ScreenshotRequest) -> ScreenshotResult:
        _require_text(request.token, "token")
        _require_timeout(request.timeout)
        if request.target not in ("ciw", "display") and not re.fullmatch(
            r"0x[0-9a-fA-F]+", request.target
        ):
            raise ValueError("target must be 'ciw', 'display' or a 0x window id")
        facts = self.middle.query(request.token)
        steps = [_step("query", facts.status.value == "success", facts)]
        if facts.status.value != "success":
            return ScreenshotResult(False, steps, "; ".join(facts.errors) or "query failed")
        gui_role = facts.roles.get("gui")
        gui_root = gui_role.root if gui_role else None
        if not gui_root:
            return ScreenshotResult(False, steps, "gui role root is not available")

        windows = self.list_windows(ListWindowsRequest(request.token, request.timeout))
        steps.append(_step("list", windows.ok, windows))
        if not windows.ok:
            return ScreenshotResult(False, steps, windows.error)
        if request.target == "ciw":
            target = _find_ciw(windows.windows)
            if target is None:
                return ScreenshotResult(False, steps, "no CIW window found")
        elif request.target == "display":
            target = "root"
        else:
            target = request.target

        name = f"shot-{int(time.time() * 1000)}.ppm"
        remote_abs = posixpath.join(gui_root.rstrip("/"), "screenshots", name)
        cmd = (
            f"mkdir -p $(dirname {shlex.quote(remote_abs)}); "
            + _DISPLAY_PREFIX
            + f'\npython3 - "{target}" "{remote_abs}" <<\'PY\'\n'
            + _CAPTURE_SCRIPT
            + "\nPY"
        )
        captured = self.middle.run_gui_command(cmd, timeout=request.timeout, token=request.token)
        steps.append(_step("capture", captured.returncode == 0, captured))
        if captured.returncode != 0:
            return ScreenshotResult(False, steps, captured.stderr or "capture failed")

        local_path = Path(request.output_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        downloaded = self.middle.download_file(
            remote_abs, local_path, timeout=request.timeout, token=request.token,
        )
        steps.append(_step("download", downloaded.returncode == 0, downloaded))
        if downloaded.returncode != 0:
            return ScreenshotResult(False, steps, downloaded.stderr or "download failed")
        return ScreenshotResult(True, steps, None, str(local_path))


__all__ = [
    "AutoDismissRequest",
    "AutoDismissResult",
    "ListWindowsRequest",
    "ListWindowsResult",
    "OPERATIONS",
    "Package",
    "ScreenshotRequest",
    "ScreenshotResult",
    "SendKeyRequest",
    "SendKeyResult",
    "parse_xwininfo_tree",
]