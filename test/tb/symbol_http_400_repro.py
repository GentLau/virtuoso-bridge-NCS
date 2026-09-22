"""Repro: capture the raw 8127 response for the symbol GEN same-view case.

The E2E suite's HttpTransport does not tolerate 4xx (urllib raises), so the
body of a 400 response never reaches the report.  This probe replays the
exact request the suite sends (symbol_e2e_tests.py, GEN-01/02/03, the
"same source/target view" assertion) and prints status + raw body.

Usage: python test/tb/symbol_http_400_repro.py
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

API = "http://127.0.0.1:8127/api/operation"
TOKEN = "vb-vblog"


def call(payload: dict) -> tuple[int, str]:
    request = urllib.request.Request(
        API,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def main() -> int:
    payload = {
        "operation": "virtuoso.symbol.generate",
        "token": TOKEN,
        "library": "schemtest",
        "cell": "gen_e2e",
        "schematic_view": "schematic",
        "symbol_view": "schematic",   # same as schematic_view -> suite expects ok=False
    }
    status, body = call(payload)
    print(f"request: {json.dumps(payload, ensure_ascii=False)}")
    print(f"status : {status}")
    print(f"body   : {body}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
