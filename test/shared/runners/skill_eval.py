"""Evaluate one SKILL expression through the business HTTP face (8127).

The CLI equivalent of ``virtuoso-bridge eval`` for the HTTP face, which is what
the TBs exercise.  Handy for environment checks and for turning a manual CIW
poking session into a replayable command:

    python test/shared/runners/skill_eval.py --token vb-vblog "ddGetObj(\"tsmcN65\")~>name"
    python test/shared/runners/skill_eval.py --token vb-vblog --json "1+2"

Exit code is 0 only when the SKILL call reports ``status=success``; the raw
response is printed so a failure is diagnosable without re-running.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

API = "http://127.0.0.1:8127/api/operation"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("expression", help="SKILL expression to evaluate")
    parser.add_argument("--token", default="vb-vblog")
    parser.add_argument("--api", default=API)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--json", action="store_true", help="print the whole response")
    args = parser.parse_args()

    body = json.dumps({
        "operation": "basic.skill.execute",
        "token": args.token,
        "skill_code": args.expression,
        "timeout": args.timeout,
    }).encode("utf-8")
    request = urllib.request.Request(
        args.api, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=args.timeout + 60) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        payload = json.loads(error.read().decode("utf-8"))

    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    result = ((payload.get("data") or {}).get("result") or {})
    print(f"status={result.get('status')} output={result.get('output')!r} "
          f"errors={result.get('errors')} error={payload.get('error')}")
    return 0 if result.get("status") == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
