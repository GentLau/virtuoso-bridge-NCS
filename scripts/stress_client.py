"""Stress client for the middle-layer HTTP wrapper."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import sys
import statistics
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor


def post_once(base, path, payload, timeout=120):
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


def is_rejected(body):
    if not isinstance(body, dict):
        return False
    if "stderr" in body and "exceeded" in str(body.get("stderr")):
        return True
    if "errors" in body and any("exceeded" in str(e) for e in body.get("errors", [])):
        return True
    return False


def post_retry(base, path, payload, retries=2000, timeout=120):
    reject_retries = 0
    http_retries = 0
    for _ in range(retries + 1):
        latency, status, body = post_once(base, path, payload, timeout=timeout)
        if status == 200 and not is_rejected(body):
            if path in ("/api/upload", "/api/download") and body.get("returncode") != 0:
                if "exceeded" in str(body.get("stderr", "")):
                    reject_retries += 1
                else:
                    http_retries += 1
                time.sleep(0.05)
                continue
            return latency, status, body, reject_retries, http_retries
        if is_rejected(body):
            reject_retries += 1
            time.sleep(0.02)
            continue
        if status in (-1, 500, 502, 503):
            # transport hiccup: HTTP layer must not be the limiter
            http_retries += 1
            time.sleep(0.05)
            continue
        return latency, status, body, reject_retries, http_retries
    return latency, status, body, reject_retries, http_retries


def make_payload(nbytes=4096):
    return os.urandom(nbytes)


class Stats:
    def __init__(self):
        self.rows = []
        self.bad_value = 0
        self.reject_retries = 0
        self.http_retries = 0
        self.sha_mismatch = 0
        self.samples = []

    def add(self, latency, status, body, reject_retries, http_retries):
        self.rows.append((latency, status, body))
        self.reject_retries += reject_retries
        self.http_retries += http_retries

    def report(self, label):
        lat = [r[0] for r in self.rows]
        statuses = {}
        rejected = 0
        for _, s, b in self.rows:
            statuses[s] = statuses.get(s, 0) + 1
            if is_rejected(b):
                rejected += 1
        http_errors = sum(1 for _, s, _ in self.rows if s == -1)
        if not lat:
            return
        print(f"[{label}] n={len(self.rows)} business_rejected={rejected} http_errors={http_errors} reject_retries={self.reject_retries} http_retries={self.http_retries} bad_value={self.bad_value} sha_mismatch={self.sha_mismatch}")
        for sample in self.samples[:8]:
            print(f"  sample: {sample}")
        print(f"  latency p50={statistics.median(lat):.3f}s p95={statistics.quantiles(lat, n=20)[18]:.3f}s max={max(lat):.3f}s statuses={statuses}")


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="http://127.0.0.1:8126")
    parser.add_argument("--token", default=None)
    parser.add_argument("--tokens", default=None)
    parser.add_argument("--file-roots", default=None)
    parser.add_argument("--concurrency", type=int, default=100)
    parser.add_argument("--commands", type=int, default=100)
    parser.add_argument("--skills", type=int, default=30)
    parser.add_argument("--uploads", type=int, default=20)
    parser.add_argument("--downloads", type=int, default=20)
    parser.add_argument("--file-root", default="/home/Gent/.virtuoso-bridge/stress")
    parser.add_argument("--skill-expr", default="1+1")
    parser.add_argument("--skill-expect", default="token", choices=["token", "two"])
    parser.add_argument("--parallel", action="store_true")
    parser.add_argument("--remote", action="store_true", help="command hosts are remote: use python3, not sys.executable")
    args = parser.parse_args(argv)

    tokens = (args.tokens or (args.token or "")).split(",")
    tokens = [t.strip() for t in tokens if t.strip()]
    roots = (args.file_roots or "").split(",")
    roots = [r.strip() for r in roots if r.strip()]
    if not tokens:
        print("no token provided")
        raise SystemExit(2)

    cmd_stats = Stats()
    skill_stats = Stats()
    up_stats = Stats()
    down_stats = Stats()
    file_contents = {}

    def token_for(i):
        return tokens[i % len(tokens)]

    def root_for(i):
        return roots[i % len(roots)] if roots else "/home/Gent/.virtuoso-bridge/stress"

    def job(kind, i):
        tok = token_for(i)
        if kind == "command":
            py = "python3" if args.remote else sys.executable
            if i % 3 == 0:
                cmd = f'"{py}" -c "print(sum(range(1,101)))"'
                want = "5050"
            elif i % 3 == 1:
                cmd = f"echo vb-{i}"
                want = f"vb-{i}"
            else:
                cmd = f'"{py}" -c "import time; time.sleep(1)"'
                want = ""
            lat, status, body, reject_retries, http_retries = post_retry(
                args.base, "/api/command",
                {"token": tok, "cmd": cmd, "parallel": args.parallel},
            )
            cmd_stats.add(lat, status, body, reject_retries, http_retries)
            if status == 200 and body.get("returncode") == 0 and str(body.get("stdout", "")).strip() != want:
                if len(cmd_stats.samples) < 8:
                    cmd_stats.samples.append({"i": i, "tok": tok, "cmd": cmd, "got": body.get("stdout"), "stderr": body.get("stderr"), "rc": body.get("returncode")})
                cmd_stats.bad_value += 1
        elif kind == "skill":
            lat, status, body, reject_retries, http_retries = post_retry(
                args.base, "/api/skill", {"token": tok, "skill": args.skill_expr},
            )
            skill_stats.add(lat, status, body, reject_retries, http_retries)
            out = str(body.get("output", "")).strip().strip('"')
            want = tok if args.skill_expect == "token" else "2"
            if status != 200:
                if len(skill_stats.samples) < 8:
                    skill_stats.samples.append({"kind": "status", "i": i, "tok": tok, "status": status, "body": body})
            elif out != want:
                # token mode: the value must come from the daemon owning the token
                skill_stats.bad_value += 1
                if len(skill_stats.samples) < 12:
                    skill_stats.samples.append({"kind": "value", "i": i, "tok": tok, "got": body.get("output"), "errors": body.get("errors"), "log": (body.get("log") or "")[:80]})
        elif kind == "upload":
            content = make_payload()
            remote = f"{root_for(i)}/files/stress-{i}.bin"
            lat, status, body, reject_retries, http_retries = post_retry(
                args.base, "/api/upload",
                {"token": tok, "remote_path": remote,
                 "content_b64": base64.b64encode(content).decode()},
                timeout=300,
            )
            up_stats.add(lat, status, body, reject_retries, http_retries)
            if status == 200 and body.get("returncode") == 0:
                file_contents[remote] = hashlib.sha256(content).hexdigest()
        elif kind == "download":
            remote = f"{root_for(i)}/files/stress-{i}.bin"
            wait_deadline = time.time() + 300
            while remote not in file_contents and time.time() < wait_deadline:
                time.sleep(0.05)
            lat, status, body, reject_retries, http_retries = post_retry(
                args.base, "/api/download",
                {"token": tok, "remote_path": remote},
                timeout=300,
            )
            down_stats.add(lat, status, body, reject_retries, http_retries)
            expected = file_contents.get(remote)
            if expected and body.get("sha256") != expected:
                down_stats.sha_mismatch += 1
                if len(down_stats.samples) < 8:
                    down_stats.samples.append({"remote": remote, "tok": tok, "got": body.get("sha256"), "want": expected, "size": body.get("size")})

    tasks = (
        [("command", i) for i in range(args.commands)]
        + [("skill", i) for i in range(args.skills)]
        + [("upload", i) for i in range(args.uploads)]
        + [("download", i) for i in range(args.downloads)]
    )
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(lambda t: job(*t), tasks))

    cmd_stats.report("command")
    skill_stats.report("skill")
    up_stats.report("upload")
    down_stats.report("download")
    print(f"total wall time: {time.time() - t0:.2f}s")


if __name__ == "__main__":
    main()
