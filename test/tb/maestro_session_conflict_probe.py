"""Read-only diagnostic for Maestro GUI/background session conflicts.

This probe intentionally does not force-close any session or open a GUI
window.  A destructive variant was used once and exposed an IC6.1.8 SIGSEGV
when a background session was force-closed immediately before GUI
open/close; the package therefore reports conflicts instead of auto-closing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import init_work_dir  # noqa: E402
from pyapi.packages import maestro  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOKEN = "vb-vblog"


def main() -> int:
    init_work_dir(str(ROOT / "test" / "tb" / "artifacts" / "log-vblog"))
    middle = BusinessServer()
    pkg = maestro.Package(middle)
    try:
        report = {
            "sessions": pkg._session_list(TOKEN, 30),
            "gui_windows": pkg._session_windows(TOKEN, 30),
            "background_sessions": pkg._background_sessions(TOKEN, 30),
        }
        report["conflict"] = bool(report["background_sessions"])
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    finally:
        middle.close()


if __name__ == "__main__":
    raise SystemExit(main())
