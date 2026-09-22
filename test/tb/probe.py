"""Tiny ad-hoc probe helper: run one operation against the business server."""
import json
import sys
import urllib.request

API = "http://127.0.0.1:8127/api/operation"


def call(operation: str, **fields):
    body = json.dumps({"operation": operation, "token": "vb-vblog", **fields},
                      ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


if __name__ == "__main__":
    op = sys.argv[1]
    payload = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    print(json.dumps(call(op, **payload), ensure_ascii=False, indent=2))
