"""Compare ``hiWindowSaveImage`` capture variants for a symbol window.

Records file size plus a coarse pixel histogram so the report can distinguish
a real capture from an all-black offscreen render.
"""
from __future__ import annotations

import collections
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import init_work_dir  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402

TOKEN = "vb-vblog"
LIB, CELL, VIEW, VTYPE = "schemtest", "sym_e2e", "symbol", "schematicSymbol"


def png_stats(path: Path) -> str:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        return f"{path.name}: not a PNG ({len(data)} B)"
    pos, idat, w, h, ctype = 8, b"", 0, 0, 0
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos + 4])[0]
        typ = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + ln]
        pos += 12 + ln
        if typ == b"IHDR":
            w, h, _bit, ctype, _c, _f, _i = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat += body
        elif typ == b"IEND":
            break
    raw = zlib.decompress(idat)
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    stride = w * ch
    prev = bytearray(stride)
    index = 0
    counter: collections.Counter = collections.Counter()
    for _ in range(h):
        filt = raw[index]
        index += 1
        line = bytearray(raw[index:index + stride])
        index += stride
        if filt == 1:
            for x in range(ch, stride):
                line[x] = (line[x] + line[x - ch]) & 0xFF
        elif filt == 2:
            for x in range(stride):
                line[x] = (line[x] + prev[x]) & 0xFF
        elif filt == 3:
            for x in range(stride):
                left = line[x - ch] if x >= ch else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 0xFF
        elif filt == 4:
            for x in range(stride):
                a = line[x - ch] if x >= ch else 0
                b = prev[x]
                c = prev[x - ch] if x >= ch else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                pred = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[x] = (line[x] + pred) & 0xFF
        for x in range(0, stride, ch):
            key = bytes(line[x:x + 3]) if ch >= 3 else bytes([line[x]] * 3)
            counter[key] += 1
        prev = line
    top = ", ".join(f"{tuple(color)}x{count}" for color, count in counter.most_common(3))
    return (f"{path.name}: {len(data)} B, {w}x{h}, {len(counter)} distinct colours; "
            f"top: {top}")


VARIANTS = {
    "offscreen": 'hiWindowSaveImage(?target vbW ?path "%s" ?format "png" '
                 '?toplevel nil ?centralWidget t)',
    "screen": 'hiWindowSaveImage(?target vbW ?path "%s" ?format "png" '
              '?toplevel nil ?centralWidget t ?grabFromScreen t)',
    "screen_toplevel": 'hiWindowSaveImage(?target vbW ?path "%s" ?format "png" '
                       '?toplevel t ?centralWidget t ?grabFromScreen t)',
}


def main() -> int:
    init_work_dir(str(ROOT / "test" / "tb" / "artifacts" / "log-vblog"))
    middle = BusinessServer()
    try:
        facts = middle.query(token=TOKEN)
        root = facts.roles["daemon"].root.rstrip("/")
        open_rc = middle.execute_skill(
            f'let((vbW) vbW = geOpen(?lib "{LIB}" ?cell "{CELL}" ?view "{VIEW}" '
            f'?viewType "{VTYPE}" ?mode "r") if(vbW "opened" "nil"))',
            token=TOKEN,
        )
        print("open:", open_rc.output if open_rc.ok else open_rc.errors)
        local_dir = ROOT / "test" / "tb" / "artifacts" / "symbol-tb"
        local_dir.mkdir(parents=True, exist_ok=True)
        for name, template in VARIANTS.items():
            remote = f"{root}/screenshots/probe-{name}.png"
            code = (
                "let((vbW vbRc) "
                "vbW = car(setof(x hiGetWindowList() x~>cellView && "
                f'x~>cellView~>cellName == "{CELL}")) '
                'unless(vbW error("window not found")) '
                + template % remote
                + ' if(vbRc "saved" "capture-failed"))'
            )
            run = middle.execute_skill(code, token=TOKEN)
            if not run.ok:
                print(f"{name}: SKILL error: {run.errors}")
                continue
            local = local_dir / f"probe-{name}.png"
            got = middle.download_file(remote, local, token=TOKEN)
            if got.returncode != 0:
                print(f"{name}: download failed: {got.stderr}")
                continue
            print(f"{name}: {run.output.strip()} -> {png_stats(local)}")
        middle.execute_skill(
            "let((vbW) foreach(x hiGetWindowList() "
            f'when(x~>cellView && x~>cellView~>cellName == "{CELL}" vbW = x)) '
            "when(vbW hiCloseWindow(vbW)))",
            token=TOKEN,
        )
        return 0
    finally:
        middle.close()


if __name__ == "__main__":
    raise SystemExit(main())
