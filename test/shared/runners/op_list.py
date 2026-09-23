"""Print the ops a package's ``_atomic_expr`` / ``_command_exprs`` dispatches on.

Usage:
    python test/shared/runners/op_list.py src/pyapi/packages/symbol.py
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

EQ = re.compile(r'op\s*==\s*"([a-z_]+)"')
IN = re.compile(r'op\s+in\s+\(([^)]+)\)')


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    args = ap.parse_args(argv)
    text = args.source.read_text(encoding="utf-8")
    ops: list[str] = []
    for match in EQ.finditer(text):
        ops.append(match.group(1))
    for match in IN.finditer(text):
        for item in re.findall(r'"([a-z_]+)"', match.group(1)):
            ops.append(item)
    seen: list[str] = []
    for op in ops:
        if op not in seen:
            seen.append(op)
    print(len(seen))
    print("\n".join(seen))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
