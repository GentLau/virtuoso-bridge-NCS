"""P2 live: extreme gradient on the weak vps (100 fake users, 400/500/600).

Per-user capacity is deliberately tight (thread pool 4, channel budget 2) so
the middle starts returning structured "exceeded" rejections; the stress
client retries until every instruction succeeds.  Final hard bar: completion
100%, route mismatch 0, sha mismatch 0.
"""
from __future__ import annotations
import argparse
import json
import re
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _win import no_window  # noqa: E402  (hide Windows consoles for ssh/scp)

from transport.registry import UserEntry, load_registry
from transport.register.probe import allocate_local_port
from transport.runtime_paths import set_working_dir, registry_path

VPS = "vps"

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--levels", nargs="+", type=int, default=[400, 500, 600])
    args = ap.parse_args()

    # Split endpoints: the 1.6G vps OOM-kills a single 100-daemon process plus
    # 100 first-connect tunnels; 40 users stay on vps and 60 move to wsl-gent.
    subprocess.run(["ssh", VPS, "pkill -f 'base-port 6900' || true"], capture_output=True, timeout=20, **no_window())
    subprocess.run(["ssh", "wsl-gent", "pkill -f 'base-port 6601' || true"], capture_output=True, timeout=20, **no_window())
    time.sleep(1)
    subprocess.Popen(["ssh", VPS, "cd /root && setsid nohup python3 /root/fake_daemon_host.py "
                      "--base-port 6900 --count 40 --token-prefix p2a > /tmp/vb_p2.log 2>&1 < /dev/null &"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **no_window())
    subprocess.Popen(["ssh", "wsl-gent", "cd /home/Gent/vb-ncs && setsid nohup "
                      ".venv/bin/python test/tb/fake_daemon_host.py --base-port 6601 --count 60 "
                      "--token-prefix p2b > /tmp/vb_p2_wsl.log 2>&1 < /dev/null &"],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **no_window())
    time.sleep(5)

    wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-p2-")))
    reg = load_registry(registry_path())
    tokens, roots, reserved = [], [], set()
    for n in range(args.users):
        user = f"p2-{n:02d}"
        if n < 40:
            host, token, port = VPS, f"p2a-{n:02d}", 6900 + n
        else:
            host, token, port = "wsl-gent", f"p2b-{n-40:02d}", 6601 + (n - 40)
        lp = allocate_local_port(reserved=reserved, tries=2000)
        assert lp is not None
        reserved.add(lp)
        e = UserEntry(token=token, mode="remote")
        e.roles.daemon.host = host
        e.roles.daemon.daemon_port = port
        e.roles.daemon.local_port = lp
        e.roles.command.host = host
        e.roles.command.user = "root" if host == VPS else "Gent"
        e.roles.file.host = host
        e.roles.daemon.root = "/root/vbtest" if host == VPS else "/home/Gent/vbtest"
        e.roles.daemon.expected_user = "root" if host == VPS else "Gent"
        e.runtime.thread_pool_size = 4
        e.runtime.channel_budget = 2
        reg.register(user, e)
        tokens.append(token)
    roots = [("/root/vbtest" if tok.startswith("p2a") else "/home/Gent/vbtest")
             for tok in tokens]

    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
    server = subprocess.Popen(
        [sys.executable, "-m", "server.stress_server", "--port", "8127", "--work-dir", str(wd)],
        stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT, env=env,
    )
    try:
        for _ in range(60):
            if server.poll() is not None:
                print(json.dumps({"case": "P2", "error": "server exited early"}))
                return 1
            try:
                socket.create_connection(("127.0.0.1", 8127), timeout=0.5).close()
                break
            except OSError:
                time.sleep(0.25)
        results = []
        for level in args.levels:
            t0 = time.time()
            client = subprocess.run(
                [sys.executable, str(Path(__file__).resolve().parent / "stress_client.py"),
                 "--base", "http://127.0.0.1:8127",
                 "--tokens", ",".join(tokens),
                 "--file-roots", ",".join(roots),
                 "--concurrency", str(level),
                 "--commands", "600", "--skills", "400",
                 "--uploads", "200", "--downloads", "200",
                 "--remote", "--skill-expr", "RBDToken"],
                capture_output=True, text=True, timeout=1800,
            )
            lines = re.findall(r"\[[a-z]+\] .*", client.stdout)
            def _metric(prefix, key):
                for ln in lines:
                    if ln.startswith("[" + prefix + "]") and key in ln:
                        m = re.search(key + r"=(\d+)", ln)
                        return int(m.group(1)) if m else -1
                return -1
            def _http_errors(prefix):
                for ln in lines:
                    if ln.startswith("[" + prefix + "]"):
                        m = re.search(r"http_errors=(\d+)", ln)
                        return int(m.group(1)) if m else -1
                return -1
            ok = True
            reasons = []
            for prefix in ("command", "skill", "upload", "download"):
                bad = _metric(prefix, "bad_value") if prefix in ("command", "skill") else 0
                sha = _metric(prefix, "sha_mismatch")
                http_err = _http_errors(prefix)
                if bad != 0 or sha != 0 or http_err != 0:
                    ok = False
                    reasons.append(f"{prefix}: bad={bad} sha={sha} http_errors={http_err}")
            results.append({
                "level": level, "rc": client.returncode, "ok": ok,
                "elapsed": round(time.time() - t0, 1),
                "stdout": client.stdout, "stderr": client.stderr[-2000:],
                "reasons": reasons,
            })
        print(json.dumps({"case": "P2", "client": "windows", "users": args.users,
                          "results": results}, ensure_ascii=False))
        return 0 if all(r["ok"] for r in results) else 1
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

if __name__ == "__main__":
    raise SystemExit(main())
