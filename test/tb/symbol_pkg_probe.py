"""In-process probe for the pyapi.packages.symbol package."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import init_work_dir  # noqa: E402
from pyapi.packages import symbol  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

TOKEN = "vb-vblog"


def main() -> int:
    init_work_dir(str(ROOT / "test" / "tb" / "artifacts" / "log-vblog"))
    middle = BusinessServer()
    pkg = symbol.Package(middle)
    mode = sys.argv[1] if len(sys.argv) > 1 else "read"
    try:
        if mode == "read":
            result = pkg.read(symbol.ReadRequest(
                token=TOKEN, library=sys.argv[2], cell=sys.argv[3],
                view=sys.argv[4] if len(sys.argv) > 4 else "symbol",
            ))
        elif mode == "check":
            result = pkg.check_and_save(symbol.CheckSaveRequest(
                token=TOKEN, library=sys.argv[2], cell=sys.argv[3],
                view=sys.argv[4] if len(sys.argv) > 4 else "symbol",
            ))
        elif mode == "generate":
            result = pkg.generate(symbol.GenerateRequest(
                token=TOKEN, library=sys.argv[2], cell=sys.argv[3],
                schematic_view=sys.argv[4] if len(sys.argv) > 4 else "schematic",
                symbol_view=sys.argv[5] if len(sys.argv) > 5 else "symbol",
                overwrite=(len(sys.argv) > 6 and sys.argv[6] == "overwrite"),
            ))
        else:
            raise SystemExit(f"unknown mode: {mode}")
        print(json.dumps(result.__dict__, ensure_ascii=False, indent=2, default=str))
        return 0 if result.ok else 1
    finally:
        middle.close()


if __name__ == "__main__":
    raise SystemExit(main())
