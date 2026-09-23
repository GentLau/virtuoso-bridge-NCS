"""Throwaway probe: is an empty symbol window captured as a blank image?"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3].parent
sys.path.insert(0, str(ROOT / "src"))

from common.paths import init_work_dir  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "shotprobe", str(ROOT / "test" / "tb" / "symbol_screenshot_probe.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TOKEN = "vb-vblog"
LIB, CELL, VIEW = "schemtest", "probe_empty", "symbol"
HERE = Path(__file__).resolve().parent


def main() -> int:
    init_work_dir(str(ROOT / "test" / "tb" / "artifacts" / "log-vblog"))
    middle = BusinessServer()
    try:
        root = middle.query(token=TOKEN).roles["daemon"].root.rstrip("/")
        middle.execute_skill(
            f'let((o cv) o = ddGetObj("{LIB}" "{CELL}" "{VIEW}") '
            f"when(o ddDeleteObj(o)) "
            f'cv = dbOpenCellViewByType("{LIB}" "{CELL}" "{VIEW}" "schematicSymbol" "w") '
            "unless(cv error(\"create failed\")) unless(dbSave(cv) error(\"save failed\")) "
            "dbClose(cv) t)",
            token=TOKEN,
        )
        remote = f"{root}/screenshots/probe-blank.png"
        middle.execute_skill(
            f'let((vbW vbRc) vbW = geOpen(?lib "{LIB}" ?cell "{CELL}" ?view "{VIEW}" '
            f'?viewType "schematicSymbol" ?mode "r") '
            'unless(vbW error("open failed")) '
            f'vbRc = hiWindowSaveImage(?target vbW ?path "{remote}" ?format "png" '
            '?toplevel nil ?centralWidget t) if(vbRc "saved" "capture-failed"))',
            token=TOKEN,
        )
        local = HERE / "probe-blank.png"
        middle.download_file(remote, local, token=TOKEN)
        print("blank symbol window:", mod.png_stats(local))
        middle.execute_skill(
            "let((vbW) foreach(x hiGetWindowList() "
            f'when(x~>cellView && x~>cellView~>cellName == "{CELL}" vbW = x)) '
            "when(vbW hiCloseWindow(vbW)))",
            token=TOKEN,
        )
        middle.execute_skill(
            f'let((o) o = ddGetObj("{LIB}" "{CELL}" "{VIEW}") '
            "when(o ddDeleteObj(o)))",
            token=TOKEN,
        )
        return 0
    finally:
        middle.close()


if __name__ == "__main__":
    raise SystemExit(main())
