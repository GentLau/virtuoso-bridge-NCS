"""Bring the recommended lab environment up/down (see test/docs/推荐测试环境.md §3-E4).

Only the **lab fake Virtuoso fleet** is automated here; real multi-Virtuoso on
wsl-gent stays manual until the compliant bring-up lands (doc §0.1).

Everything is written under each lab user's bridge root
(``~/.virtuoso-bridge/<user>/{tmp,logs}``) — never ``$HOME`` root, never ``/tmp``.

Usage::

    python test/shared/runners/env_up.py up   --hosts w1-gent,w2-gent --count 2 \
        --out test/artifacts/lab-fake-fleet.json
    python test/shared/runners/env_up.py status --from test/artifacts/lab-fake-fleet.json
    python test/shared/runners/env_up.py down  --from test/artifacts/lab-fake-fleet.json
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "test" / "shared" / "fixtures"))

from _win import no_window  # noqa: E402

FAKE_SRC = ROOT / "test" / "semi" / "fakevirt"
REMOTE_FAKE_DIR = "/opt/fake/virtuoso"

#: 注册表在客户端用的本地隧道端口段（每档一段；必须 ≤65535，且避开远端 daemon 号段）
LOCAL_PORT_BASE = {"e1": 64510, "e2": 64520, "e3": 64530, "e4": 64540}

#: 各档 registry 的默认落点（一个环境一个 work-dir，一份 registry.json）
TIER_WORK_DIR = {
    "e1": "test/artifacts/env/env-e1",
    "e2": "test/artifacts/env/env-e2",
    "e3": "test/artifacts/env/env-e3",
    "e4": "test/artifacts/env/env-e4",
}

#: lab 主机身份 IP（distro 重启后可能变化，用前先按 doc §6 自检）
HOST_IP = {
    "w1-gent": "172.20.170.21",
    "w2-gent": "172.20.170.22",
    "w3-gent": "172.20.170.23",
    "w4-gent": "172.20.170.24",
}

#: 每台一段，避免跨机撞端口（doc §2）
HOST_SEGMENT = {"w1-gent": 65200, "w2-gent": 65300, "w3-gent": 65400, "w4-gent": 65500}


def _ssh(host: str, command: str, timeout: int = 60) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
        capture_output=True, text=True, timeout=timeout, **no_window(),
    )


def _wait_ssh(host: str, timeout: float = 150.0) -> bool:
    """Lab distros stop themselves when idle — wait until ssh really answers."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            if _ssh(host, "hostname", timeout=12).returncode == 0:
                return True
        except subprocess.TimeoutExpired:
            pass
        time.sleep(3.0)
    return False


def _ensure_distro(host: str) -> tuple[bool, int | None]:
    """Start the WSL distro (if stopped) and keep it alive.

    WSL2 stops an idle distro within ~1–2 minutes, which kills the identity IP
    and the ssh endpoint mid-run.  A hidden ``sleep infinity`` inside the distro
    pins it open until ``down`` kills that process.
    """
    keepalive = subprocess.Popen(
        ["wsl.exe", "-d", host, "--", "sleep", "infinity"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **no_window(),
    )
    return _wait_ssh(host), keepalive.pid


def _ensure_deployed(host: str) -> bool:
    check = _ssh(host, f"test -f {REMOTE_FAKE_DIR}/fake_virtuoso.py && echo ok")
    if "ok" in check.stdout:
        return True
    _ssh(host, f"mkdir -p {REMOTE_FAKE_DIR}")
    for local in (FAKE_SRC / "fake_virtuoso.py", FAKE_SRC / "skill_ops.py",
                  ROOT / "src" / "bridge" / "resources" / "ramic_bridge_daemon_3.py"):
        done = subprocess.run(
            ["scp", "-q", str(local), f"{host}:{REMOTE_FAKE_DIR}/"],
            capture_output=True, text=True, timeout=120, **no_window(),
        )
        if done.returncode != 0:
            print(f"  deploy failed on {host}: {done.stderr.strip()[:200]}")
            print(f"  hint: ssh {host} 'sudo mkdir -p {REMOTE_FAKE_DIR} && sudo chown dev:dev {REMOTE_FAKE_DIR}'")
            return False
    return True


def _tcp_ok(ip: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout):
            return True
    except OSError:
        return False


def _start_one(host: str, index: int, prefix: str) -> dict:
    user = f"{prefix}{host[1]}{index}"          # 例: vb-lab112（w1 的第 2 个）
    token = f"{prefix}{host[1]}{index}"
    port = HOST_SEGMENT[host] + index
    bridge_root = f"$HOME/.virtuoso-bridge/{user}"
    cmd = (
        f"mkdir -p {bridge_root}/tmp {bridge_root}/logs && "
        f"sudo ip netns exec labns nohup python3 {REMOTE_FAKE_DIR}/fake_virtuoso.py "
        f"--daemon {REMOTE_FAKE_DIR}/ramic_bridge_daemon_3.py "
        f"--bind 0.0.0.0 --port {port} --token {token} "
        f"--temp-dir {bridge_root}/tmp "
        f"> {bridge_root}/logs/fake.log 2>&1 < /dev/null & echo started"
    )
    try:
        _ssh(host, cmd, timeout=30)
    except subprocess.TimeoutExpired:
        # 远端把 sudo+后台进程挂住 ssh 会话是常见的；就绪与否看端口探测
        pass
    ip = HOST_IP[host]
    # labns 建链 + 首次绑定可能慢到 30–60 s（实测 65201 在 20 s 窗口外才可达）
    deadline = time.time() + 60
    while time.time() < deadline and not _tcp_ok(ip, port):
        time.sleep(0.5)
    return {"host": host, "ip": ip, "port": port, "token": token,
            "user": user, "root": f"/home/dev/.virtuoso-bridge/{user}",
            "reachable": _tcp_ok(ip, port)}


def _stop_one(item: dict) -> bool:
    # `[.]` 防止 pkill 匹配到自己的命令行（否则会杀掉远端 shell，命令无输出）
    # 真实监听方是 fake 拉起的子进程，argv 形如：
    #   python3 .../ramic_bridge_daemon_3.py 0.0.0.0 <port> <token> <tmp>
    # 只 kill 父进程会留下仍占用端口的 daemon；host 段用 [0-9.]+ 以免写死 0.0.0.0/127.0.0.1。
    port = item["port"]
    _ssh(item["host"],
         f"sudo -n pkill -f 'fake_virtuoso[.]py.*--port {port}' 2>/dev/null; "
         f"sudo -n pkill -f 'ramic_bridge_daemon_3[.]py [0-9.]+ {port} ' 2>/dev/null; true")
    time.sleep(0.4)
    return not _tcp_ok(item["ip"], item["port"], timeout=0.6)


def _load(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _route(host: str | None, user: str | None) -> dict:
    return {"host": host, "user": user, "jump_host": None, "jump_user": None, "proxy": None}


def _role(root: str, host: str | None, user: str | None, **extra) -> dict:
    role = {"mode": None, "root": root, "expected_fingerprint": None, "max_sessions": 32}
    role.update(_route(host, user))
    role.update(extra)
    return role


def _entry(token: str, host: str | None, user: str | None, roles: dict) -> dict:
    return {
        "token": token,
        "mode": {"default": "local" if host is None else "remote"},
        "ssh": {"default": _route(host, user), "backend": "paramiko",
                "control_master": "auto", "tool_override": {}},
        "root": {"default": None},
        "roles": roles,
        "registered_at": int(time.time()),
    }


def _build_registry(tier: str, fleet: dict | None) -> dict:
    """One registry per environment.  Layout/log rules: docs/推荐测试环境.md §0."""
    base = LOCAL_PORT_BASE[tier]
    users: dict = {}
    if tier == "e1":
        users["vblog"] = _entry(
            "vb-vblog", "wsl-gent", "Gent",
            {name: _role("/home/Gent/.virtuoso-bridge/vblog", "wsl-gent", "Gent")
             for name in ("command", "file", "spectre")}
            | {"daemon": _role("/home/Gent/.virtuoso-bridge/vblog", "wsl-gent", "Gent",
                               daemon_port=65121, local_port=base + 1, python=None),
               "gui": _role("/home/Gent/.virtuoso-bridge/vblog", "wsl-gent", "Gent",
                            display=":11")},
        )
        users["vbtest"] = _entry(
            "vb-vbtest", "wsl-gent", "Gent",
            {"daemon": _role("/home/Gent/.virtuoso-bridge/vbtest", "wsl-gent", "Gent",
                             daemon_port=65081, local_port=base + 2, python=None)},
        )
    elif tier == "e2":
        users["test5role"] = _entry(
            "vb-test5role", "wsl-gent", "Gent",
            {
                "daemon": _role("/home/Gent/.virtuoso-bridge/test5role", "wsl-gent", "Gent",
                                daemon_port=65141, local_port=base + 1, python=None),
                "gui": _role("/home/Gent/.virtuoso-bridge/test5role", "wsl-gent", "Gent",
                             display=":11"),
                "spectre": _role("/home/Gent/.virtuoso-bridge/test5role", "wsl-gent", "Gent"),
                "command": _role("/home/dev/.virtuoso-bridge/test5role/command", "w1-gent", "dev"),
                "file": _role("/home/dev/.virtuoso-bridge/test5role/file", "w2-gent", "dev"),
            },
        )
    elif tier == "e3":
        for index, port in enumerate(range(65142, 65146), start=1):
            user = f"vbreal{index}"
            users[user] = _entry(
                f"vb-real{index}", "wsl-gent", "Gent",
                {name: _role(f"/home/Gent/.virtuoso-bridge/{user}", "wsl-gent", "Gent")
                 for name in ("command", "file", "spectre")}
                | {"daemon": _role(f"/home/Gent/.virtuoso-bridge/{user}", "wsl-gent", "Gent",
                                   daemon_port=port, local_port=base + index, python=None),
                   "gui": _role(f"/home/Gent/.virtuoso-bridge/{user}", "wsl-gent", "Gent",
                                display=":99")},
            )
        for index, port in enumerate((65201, 65202), start=1):
            user = f"vbfake{index}"
            users[user] = _entry(
                f"vb-lab11" if index == 1 else "vb-lab12", "w1-gent", "dev",
                {"daemon": _role(f"/home/dev/.virtuoso-bridge/vb-lab1{index}", "w1-gent", "dev",
                                 daemon_port=port, local_port=base + 10 + index, python=None)},
            )
    elif tier == "e4":
        instances = (fleet or {}).get("instances") or []
        if not instances:
            instances = [{"host": h, "ip": HOST_IP[h], "port": HOST_SEGMENT[h] + i,
                          "token": f"vb-lab{h[1]}{i}", "user": f"vb-lab{h[1]}{i}"}
                         for h in ("w1-gent", "w2-gent", "w3-gent", "w4-gent") for i in range(1, 5)]
        for index, item in enumerate(instances, start=1):
            user = item.get("user") or f"vbfake{index}"
            users[user] = _entry(
                item["token"], item["host"], "dev",
                {"daemon": _role(f"/home/dev/.virtuoso-bridge/{user}", item["host"], "dev",
                                 daemon_port=item["port"], local_port=base + index, python=None)},
            )
    else:
        raise SystemExit(f"unknown tier: {tier}")
    return users


def _write_registry(tier: str, work_dir: Path, fleet_path: str | None) -> int:
    fleet = _load(fleet_path) if fleet_path else None
    users = _build_registry(tier, fleet)
    work_dir.mkdir(parents=True, exist_ok=True)
    path = work_dir / "registry.json"
    path.write_text(json.dumps(users, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    sys.path.insert(0, str(ROOT / "src"))
    from common.registry import Registry  # noqa: E402  - 用生产代码校验 schema

    registry = Registry(path).load()
    print(f"{tier}: {len(users)} user(s) -> {path}")
    for name in users:
        entry = registry.by_token(users[name]["token"])
        daemon = users[name]["roles"].get("daemon", {})
        roles = ",".join(sorted(users[name]["roles"]))
        print(f"  {name:12s} token={users[name]['token']:14s} daemon={daemon.get('daemon_port') or '-':>6} "
              f"local={daemon.get('local_port') or '-':>6} roles={roles}")
        if entry is None:
            print(f"    WARNING: token {users[name]['token']} not found after reload")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)

    up = sub.add_parser("up", help="start N fake Virtuosos per lab host")
    up.add_argument("--hosts", required=True, help="comma separated, e.g. w1-gent,w2-gent")
    up.add_argument("--count", type=int, default=2)
    up.add_argument("--prefix", default="vb-lab")
    up.add_argument("--out", required=True)

    down = sub.add_parser("down", help="stop the fleet recorded in --from")
    down.add_argument("--from", dest="src", required=True)

    status = sub.add_parser("status", help="probe the fleet recorded in --from")
    status.add_argument("--from", dest="src", required=True)

    reg = sub.add_parser("registry", help="write the per-tier registry.json")
    reg.add_argument("--tier", required=True, choices=["e1", "e2", "e3", "e4"])
    reg.add_argument("--work-dir", default=None,
                     help="默认按档位落在 test/artifacts/env-<tier>/")
    reg.add_argument("--fleet", default=None, help="e4 用：env_up up 产生的 JSON")

    args = parser.parse_args()

    if args.action == "registry":
        work_dir = Path(args.work_dir) if args.work_dir else ROOT / TIER_WORK_DIR[args.tier]
        return _write_registry(args.tier, work_dir, args.fleet)

    if args.action == "up":
        hosts = [h.strip() for h in args.hosts.split(",") if h.strip()]
        unknown = [h for h in hosts if h not in HOST_IP]
        if unknown:
            print(f"unknown hosts: {unknown} (known: {list(HOST_IP)})")
            return 2
        instances = []
        keepalive: dict[str, int] = {}
        for host in hosts:
            reachable, pid = _ensure_distro(host)
            if not reachable:
                print(f"  {host}: not reachable over ssh (distro/netns?) — skipped")
                continue
            keepalive[host] = pid
            if not _ensure_deployed(host):
                continue
            for index in range(1, args.count + 1):
                item = _start_one(host, index, args.prefix)
                instances.append(item)
                print(f"  {item['host']}:{item['port']} token={item['token']} reachable={item['reachable']}")
        payload = {
            "run_id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
            "kind": "lab-fake-fleet",
            "keepalive": keepalive,
            "instances": instances,
        }
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        unreachable = [i for i in instances if not i["reachable"]]
        print(f"fleet: {len(instances) - len(unreachable)}/{len(instances)} reachable -> {out}")
        return 1 if unreachable else 0

    payload = _load(args.src)
    if args.action == "status":
        bad = 0
        for item in payload["instances"]:
            ok = _tcp_ok(item["ip"], item["port"], timeout=1.0)
            bad += 0 if ok else 1
            print(f"  {item['host']}:{item['port']} {'UP' if ok else 'DOWN'}")
        return 1 if bad else 0

    stopped = 0
    for item in payload["instances"]:
        ok = _stop_one(item)
        stopped += 1 if ok else 0
        print(f"  {item['host']}:{item['port']} stopped={ok}")
    for host, pid in (payload.get("keepalive") or {}).items():
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, **no_window())
        print(f"  {host}: keep-alive pid {pid} released")
    print(f"stopped {stopped}/{len(payload['instances'])}")
    return 0 if stopped == len(payload["instances"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
