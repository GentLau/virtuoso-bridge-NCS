"""Start N real Virtuoso instances on wsl-gent, one registered user each.

Each instance runs in its own folder with a local .cdsinit that loads that
user's generated setup (unique token/port).  Starts one by one, checks memory,
then waits for the daemon banner and runs the step-5 verification.

Usage: python test/tb/multi_virtuoso_pilot.py --users 3
"""

from __future__ import annotations

import argparse
import base64
import subprocess
import sys
import tempfile
import time
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from _win import no_window  # noqa: E402  (hide Windows consoles for ssh/scp)

from register import RegistrationFlow, RegistrationRequest
from common.registry import load_registry
from common.paths import registry_path, override_work_dir_for_tests

HOST = "wsl-gent"
SSH_USER = "Gent"
DISPLAY = os.environ.get("VB_DISPLAY", ":10")
MEM_MIN_FREE_GB = 2.0


def ssh(cmd: str, timeout=120):
    return subprocess.run(["ssh", HOST, cmd], capture_output=True, text=True, timeout=timeout, **no_window())


def free_gb() -> float:
    out = ssh("free -b").stdout
    for line in out.splitlines():
        if line.startswith("Mem:"):
            parts = line.split()
            return float(parts[6]) / (1024 ** 3)  # available column
    return 0.0


def write_cdsinit(user: str, setup: str):
    script = f'load("{setup}")\n'
    b64 = base64.b64encode(script.encode("utf-8")).decode("ascii")
    remote = (
        f"mkdir -p /home/Gent/project/{user} && "
        f"echo {b64} | base64 -d > /home/Gent/project/{user}/.cdsinit"
    )
    ssh(remote)


def start_virtuoso(user: str):
    cmd = (
        f"cd /home/Gent/project/{user} && "
        f"DISPLAY={DISPLAY} nohup bash -lc 'source ~/.bashrc; virtuoso -log /home/Gent/project/{user}/CDS.log' "
        f"> /home/Gent/project/{user}/start.log 2>&1 < /dev/null &"
    )
    try:
        subprocess.run(["ssh", HOST, cmd], capture_output=True, text=True, timeout=15, **no_window())
    except subprocess.TimeoutExpired:
        pass  # Windows ssh may linger even after the remote command returns


def daemon_ready(user: str, port: int, timeout=240):
    deadline = time.time() + timeout
    marker = f"virtuoso-bridge/{user}/ramic/ramic_bridge_daemon_"
    while time.time() < deadline:
        out = ssh(
            f"pgrep -fa 'virtuoso-bridge/{user}/ramic/ramic_bridge_daemon_'"
        ).stdout
        if marker in out:
            # the process wrapper appears before the socket binds; require
            # the actual listener so verify talks to a live daemon
            chk = ssh(f"ss -tlnp 2>/dev/null | grep -q ':{port} '")
            if chk.returncode == 0:
                return True
        time.sleep(2)
    return False


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=3)
    parser.add_argument("--start-at", type=int, default=1)
    parser.add_argument("--work-dir", default=None)
    parser.add_argument("--clean", action="store_true")
    args = parser.parse_args(argv)

    wd = Path(args.work_dir) if args.work_dir else Path(tempfile.mkdtemp())
    override_work_dir_for_tests(wd)
    if args.clean:
        ssh("pkill -f 'project/vb0[0-9]' 2>/dev/null; pkill -f 'virtuoso-bridge/vb0[0-9]' 2>/dev/null; sleep 2; echo cleaned")
    registry = load_registry(registry_path())

    flows = {}
    for n in range(args.start_at, args.start_at + args.users):
        user = f"vb{n:02d}"
        token = f"vb-{user}"
        flow = RegistrationFlow(registry)
        state = flow.apply(RegistrationRequest(
            mode="remote", user=user, token=token,
            ssh={"default": {"host": HOST, "user": SSH_USER}},
            roles={"daemon": {"daemon_port": 65100 + n}},
        ))
        if state.stage != "deployed":
            print(f"{user} deploy failed: {state.errors}")
            continue
        flows[user] = (flow, state)
        print(f"{user} deployed: {state.setup_path} port={state.entry.roles.daemon.daemon_port}")

    print("starting Virtuoso instances one by one...")
    for user, (flow, state) in flows.items():
        if free_gb() < MEM_MIN_FREE_GB:
            print(f"memory low ({free_gb():.1f}G available), stopping at {user}")
            break
        write_cdsinit(user, state.setup_path)
        start_virtuoso(user)
        print(f"{user} starting; available={free_gb():.1f}G")
        time.sleep(8)

    print("waiting for daemons...")
    ok = []
    for user, (flow, state) in flows.items():
        ready = daemon_ready(user, state.entry.roles.daemon.daemon_port)
        print(f"{user} daemon_ready={ready} available={free_gb():.1f}G")
        if not ready:
            continue
        v = flow.verify()
        print(f"{user} verify={v.stage} errors={v.errors}")
        if v.stage == "committed":
            ok.append(user)
    print(f"committed={len(ok)}/{len(flows)} users; workdir={wd}; available={free_gb():.1f}G")


if __name__ == "__main__":
    main()
