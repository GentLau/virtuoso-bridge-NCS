"""Extract the (op -> required command fields) table from a package dispatcher.

Many upper-layer packages translate ``{"op": ...}`` commands into SKILL via one
``if op == "..."`` chain.  When writing contract tests you need to know which
fields each op requires; reading that off by eye is error-prone, so this tool
prints the table straight from the source.

Usage:
    python test/shared/runners/skill_op_table.py src/pyapi/packages/maestro.py -o out.md
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

IF_EQ = re.compile(r'^\s*if op == "([a-z_]+)"')
IF_IN = re.compile(r"^\s*if op in \(([^)]+)\)")
GET = re.compile(r'command\.get\("([a-z_]+)"')
IDX = re.compile(r'command\["([a-z_]+)"\]')


def extract(path: Path) -> list[tuple[str, list[str]]]:
    rows: list[tuple[str, list[str]]] = []
    current: str | None = None
    fields: list[str] = []

    def flush() -> None:
        if current:
            rows.append((current, fields.copy()))

    for line in path.read_text(encoding="utf-8").splitlines():
        eq = IF_EQ.match(line)
        inn = IF_IN.match(line)
        if eq:
            flush()
            current, fields = eq.group(1), []
        elif inn:
            flush()
            current = "IN " + inn.group(1)
            fields = []
        elif current:
            fields.extend(GET.findall(line))
            fields.extend(name + "*" for name in IDX.findall(line))
    flush()
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("source", type=Path)
    ap.add_argument("-o", "--out", type=Path)
    args = ap.parse_args(argv)

    rows = extract(args.source)
    lines = [f"# op table extracted from {args.source}", "",
             f"ops: {len(rows)}", "",
             "| op | required fields (get / [index]*, optional) |", "|---|---|"]
    for op, fields in rows:
        seen: list[str] = []
        for name in fields:
            if name not in seen:
                seen.append(name)
        lines.append(f"| `{op}` | {', '.join('`' + n + '`' for n in seen)} |")
    text = "\n".join(lines) + "\n"
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} ({len(rows)} ops)")
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
