"""Restart the vbNN Virtuoso instances so their daemons pick up the new
ramic_bridge_daemon files (listen backlog 128).  One instance per user dir."""
from __future__ import annotations
import subprocess, sys, time

HOST = "wsl-gent"
DISPLAY = os.environ.get("VB_DISPLAY", ":10")
USERS = [f"vb{n:02d}" for n in range(1, 58)]

def ssh(cmd, timeout=120):
    return subprocess.run(["ssh", HOST, cmd], capture_output=True, text=True, timeout=timeout)

def start_one(user):
    cmd = (f"cd /home/Gent/project/{user} && DISPLAY={DISPLAY} nohup bash -lc "
           f"'source ~/.bashrc; virtuoso -log /home/Gent/project/{user}/CDS.log' "
           f"> /home/Gent/project/{user}/start.log 2>&1 < /dev/null &")
    try:
        subprocess.run(["ssh", HOST, cmd], capture_output=True, text=True, timeout=15)
    except subprocess.TimeoutExpired:
        pass

print("killing old virtuoso instances...")
for i, user in enumerate(USERS):
    ssh(f"pkill -f 'project/{user}/CDS.log' 2>/dev/null; pkill -f '.virtuoso-bridge/{user}/ramic' 2>/dev/null; true")
    if i % 10 == 0:
        print(f"  killed {i+1}/{len(USERS)}")
time.sleep(3)

print("relaunching...")
for i, user in enumerate(USERS):
    start_one(user)
    if i % 6 == 0:
        time.sleep(2)
print("waiting for daemons (backlog 128)...")
deadline = time.time() + 420
ready = set()
while time.time() < deadline and len(ready) < len(USERS):
    out = ssh("ss -tln 2>/dev/null | grep -E ':(65[0-9]{3}) '").stdout
    for line in out.splitlines():
        parts = line.split()
        if len(parts) >= 5 and parts[0] == "LISTEN" and parts[3].startswith("127.0.0.1:65"):
            port = int(parts[3].rsplit(":", 1)[1])
            idx = port - 65101
            if 0 <= idx < len(USERS) and parts[4] == "128":
                ready.add(USERS[idx])
    print(f"  ready={len(ready)}/{len(USERS)}", flush=True)
    if len(ready) >= len(USERS):
        break
    time.sleep(5)

print("result:", len(ready), "of", len(USERS))
if len(ready) < len(USERS):
    missing = [u for u in USERS if u not in ready]
    print("missing:", missing)
    raise SystemExit(1)
