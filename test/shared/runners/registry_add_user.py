"""Copy one user entry from a registry that already validates into another work-dir.

Used when a scenario needs an extra token in its own work-dir but you do not want
to hand-write registry JSON (the proven entry is reused verbatim, then the target
is re-validated through the real ``Registry.load`` so a bad copy cannot slip in).

Usage:
    python test/shared/runners/registry_add_user.py \
        --from test/artifacts/env/log-vblog/registry.json --user calprobe \
        --to test/artifacts/env/http-stress-sat/registry.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--from", dest="source", type=Path, required=True)
    ap.add_argument("--user", required=True)
    ap.add_argument("--to", dest="target", type=Path, required=True)
    args = ap.parse_args(argv)

    source = json.loads(args.source.read_text(encoding="utf-8"))
    if args.user not in source:
        raise SystemExit(f"user {args.user!r} not in {args.source}")
    entry = source[args.user]

    target = json.loads(args.target.read_text(encoding="utf-8")) if args.target.exists() else {}
    target[args.user] = entry
    args.target.write_text(
        json.dumps(target, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"added {args.user!r} to {args.target} ({len(target)} users)")

    # Re-validate through the production loader so a malformed copy fails here, not at run time.
    from common.registry import Registry  # noqa: E402

    registry = Registry(args.target).load()
    users = sorted(registry.users())
    print(f"validated: {len(users)} users accepted: {users}")
    if args.user not in users:
        raise SystemExit(f"copy failed: {args.user!r} not visible after reload")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
