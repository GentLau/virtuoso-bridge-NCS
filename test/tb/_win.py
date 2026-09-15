"""Windows console-hidden subprocess kwargs for the live test benches.

Every TB that shells out to ``ssh``/``scp`` must use these kwargs, otherwise
Windows spawns one console window per process (a 100-user stress run pops
~100 black boxes and slows the whole run down).
"""

from __future__ import annotations

import os
import subprocess


def no_window(**kwargs) -> dict:
    """Return ``kwargs`` plus the Windows no-console flags (no-op elsewhere)."""
    if os.name != "nt":
        return dict(kwargs)
    startupinfo = subprocess.STARTUPINFO()
    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    merged = {
        "creationflags": subprocess.CREATE_NO_WINDOW,
        "startupinfo": startupinfo,
    }
    merged.update(kwargs)
    return merged


__all__ = ["no_window"]
