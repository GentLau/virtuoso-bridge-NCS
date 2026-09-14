"""F2 live: daemon killed -> structured transport error -> restart -> reconnect.

One fake daemon on vps:127.0.0.1:6790 (token recon-00).  The middle keeps its
SSH tunnel; a daemon kill must surface as a structured Skill error (no hang,
no crash), and a restart on the same port/token must be picked up on the next
call without re-registration.
"""
from __future__ import annotations
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.register.probe import allocate_local_port
from transport.runtime_paths import set_working_dir, registry_path

VPS = "vps"

def main() -> int:
    wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-f2-")))
    reg = load_registry(registry_path())
    lp = allocate_local_port(tries=200)
    e = UserEntry(token="recon-00", mode="remote")
    e.roles.daemon.host = VPS
    e.roles.daemon.daemon_port = 6888
    e.roles.daemon.local_port = lp
    e.roles.command.host = VPS
    e.roles.command.user = "root"
    e.roles.file.host = VPS
    e.roles.daemon.root = "/root/vbtest"
    e.roles.daemon.expected_user = "root"
    reg.register("recon01", e)
    middle = BusinessServer(wd)

    def start_daemon():
        subprocess.Popen(["ssh", VPS, "cd /root && setsid nohup python3 /root/fake_daemon_host.py "
                          "--base-port 6888 --count 1 --token-prefix recon > /tmp/vb_f2.log 2>&1 < /dev/null &"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(3)

    # ensure the daemon is up before the test sequence begins
    for _ in range(10):
        r = middle.execute_skill("RBDToken", token="recon-00", timeout=60)
        if r.ok and (r.output or "").strip().strip('"') == "recon-00":
            break
        start_daemon()
        time.sleep(2)
    else:
        print(json.dumps({"case": "F2", "error": "daemon never came up", "errors": list(r.errors)}))
        return 1

    def call(label):
        t0 = time.time()
        r = middle.execute_skill("RBDToken", token="recon-00", timeout=60)
        return {
            "label": label,
            "status": r.status.name if hasattr(r.status, "name") else str(r.status),
            "ok": bool(r.ok),
            "output": (r.output or "").strip().strip('"'),
            "errors": list(r.errors),
            "elapsed": round(time.time() - t0, 2),
        }

    out = {"case": "F2", "client": "windows", "target": f"{VPS}:6888", "steps": []}
    out["steps"].append(call("before_kill"))
    # kill the daemon (keep the tunnel alive)
    subprocess.run(["ssh", VPS, "pkill -f 'fake_daemon_host.py --base-port 6888'"],
                   capture_output=True, text=True, timeout=20)
    time.sleep(1.5)
    out["steps"].append(call("after_kill"))
    # restart same port/token
    start_daemon()
    time.sleep(4)
    out["steps"].append(call("after_restart"))

    for c in list(middle._clients.values()):
        try:
            c.close()
        except Exception:
            pass
    print(json.dumps(out, ensure_ascii=False))

    first = out["steps"][0]
    mid = out["steps"][1]
    last = out["steps"][2]
    ok = first["ok"] and first["output"] == "recon-00" \
        and (not mid["ok"]) and mid["status"].lower() == "error" \
        and last["ok"] and last["output"] == "recon-00"
    return 0 if ok else 1

if __name__ == "__main__":
    raise SystemExit(main())
