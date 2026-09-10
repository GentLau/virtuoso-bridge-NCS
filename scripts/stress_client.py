"""Stress client for the middle-layer HTTP wrapper.

Usage:
  python scripts/stress_client.py --base http://127.0.0.1:8125 --token TOKEN \
      --concurrency 20 --commands 60 --skills 20
"""

from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def post(base, path, payload, timeout=120):
    req = urllib.request.Request(
        base + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            return time.perf_counter() - start, resp.status, body
    except urllib.error.HTTPError as exc:
        return time.perf_counter() - start, exc.code, {}
    except Exception as exc:  # noqa: BLE001
        return time.perf_counter() - start, -1, {"error": str(exc)}


def run(base, token, concurrency, commands, skills):
    results = {"command": [], "skill": []}

    def one(kind, i):
        if kind == "command":
            payload = {"token": token, "cmd": f"echo vb-{i}"}
            latency, status, body = post(base, "/api/command", payload)
            results["command"].append((latency, status, body))
        else:
            payload = {"token": token, "skill": "1+1"}
            latency, status, body = post(base, "/api/skill", payload)
            results["skill"].append((latency, status, body))

    tasks = [("command", i) for i in range(commands)] + [("skill", i) for i in range(skills)]
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(lambda t: one(*t), tasks))

    return results


def summarize(label, rows):
    lat = [r[0] for r in rows]
    statuses = {}
    for _, s, _ in rows:
        statuses[s] = statuses.get(s, 0) + 1
    err = sum(1 for _, s, b in rows if s != 200 or (isinstance(b, dict) and "error" in b))
    if not lat:
        return
    print(f"[{label}] n={len(rows)} errors={err} statuses={statuses}")
    print(f"  latency p50={statistics.median(lat):.3f}s p95={statistics.quantiles(lat, n=20)[18]:.3f}s max={max(lat):.3f}s")


def check_parallel_overlap(base, token):
    def one():
        cmd = "s=$(date +%s.%N); sleep 1; e=$(date +%s.%N); printf '%s %s' \"$s\" \"$e\""
        _, status, body = post(base, "/api/command", {"token": token, "cmd": cmd, "parallel": True})
        if status != 200:
            return None
        parts = str(body.get("stdout", "")).split()
        if len(parts) != 2:
            return None
        return float(parts[0]), float(parts[1])

    with ThreadPoolExecutor(max_workers=2) as pool:
        a, b = list(pool.map(lambda _: one(), range(2)))
    if not a or not b:
        print("[parallel] overlap check failed (missing intervals)")
        return
    overlap = min(a[1], b[1]) - max(a[0], b[0])
    print(f"[parallel] interval overlap={overlap:.3f}s (serial would be ~0)")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8125")
    parser.add_argument("--token", required=True)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--commands", type=int, default=60)
    parser.add_argument("--skills", type=int, default=20)
    args = parser.parse_args(argv)

    t0 = time.time()
    results = run(args.base, args.token, args.concurrency, args.commands, args.skills)
    summarize("command", results["command"])
    summarize("skill", results["skill"])
    check_parallel_overlap(args.base, args.token)
    print(f"total wall time: {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
