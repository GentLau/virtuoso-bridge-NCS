"""Bring a whole test *scenario* to the required state (see docs/推荐测试环境.md 菜谱章).

一个场景 = 客户端 + 注册表 + 服务端组合（真机/fake、几个、带不带工艺库）。
`up` 会把场景需要的东西起齐（不用的不动/停掉），`down` 收摊，`status` 体检。

    python test/shared/runners/scenario.py list
    python test/shared/runners/scenario.py up   role-split
    python test/shared/runners/scenario.py status role-split
    python test/shared/runners/scenario.py down role-split

真实例按 docs/推荐测试环境.md §0.1 启动：cwd 用 ``~/.virtuoso-bridge/<user>/run/``，
运行态文件（CDS.log/锁/ahdlSimDB）留在该目录，工程目录只放 cds.lib 等设计产物。
"""
from __future__ import annotations

import argparse
import base64
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from common.registry import Registry  # noqa: E402

LAB_IP = {"w1-gent": "172.20.170.21", "w2-gent": "172.20.170.22",
          "w3-gent": "172.20.170.23", "w4-gent": "172.20.170.24"}
PDK_CDS = "/opt/eda/PDK/CRN65GPNEW/CRN65GPNEW/cds.lib"
CADENCE_SOFTINCLUDE = "/opt/eda/cadence/IC618/share/cdssetup/cds.lib"
REAL_HOST = "wsl-gent"
FAKE_DIR = "/opt/fake/virtuoso"
RAMIC_FILES = ("ramic_bridge.il", "ramic_bridge_daemon_3.py", "ramic_bridge_daemon_27.py")

#: 场景预设（菜谱）。hosts 里的 user 就是 wsl-gent 上的 bridge 用户（不是 OS 账号）。
SCENARIOS: dict[str, dict] = {
    "calibre": {
        "title": "Calibre 功能验证：单用户、全 role→wsl-gent、2 个带 PDK 的真实 Virtuoso",
        "client": "windows（本机）",
        "real": [
            {"user": "vbcal1", "token": "vb-cal1", "port": 65171, "local_port": 64571, "pdk": True},
            {"user": "vbcal2", "token": "vb-cal2", "port": 65172, "local_port": 64572, "pdk": True},
        ],
        "fake": [],
        "tbs": [
            "python test/semi/probes/calibre_env_probe.py --facts",
            "python test/semi/probes/calibre_cdl_probe.py --lib <lib> --cell <cell> --view schematic",
        ],
    },
    "role-split": {
        "title": "多 role 验证：2 用户，真 daemon 在 wsl-gent + fake 在 w1",
        "client": "windows（本机）",
        "real": [
            {"user": "vbrole1", "token": "vb-role1", "port": 65161, "local_port": 64561, "pdk": False},
        ],
        "fake": [
            {"host": "w1-gent", "port": 65201, "token": "vb-role2", "user": "vbrole2"},
        ],
        "tbs": [
            "python test/live/transport/cov_remote_real.py --work-dir test/artifacts/env/scenario-role-split --token vb-role1",
        ],
    },
    "multi-user": {
        "title": "多用户/token 隔离：3 真（wsl-gent）+ 2 fake（w1/w2）",
        "client": "windows（本机）",
        "real": [
            {"user": f"vbmu{i}", "token": f"vb-mu{i}", "port": 65180 + i, "local_port": 64580 + i, "pdk": False}
            for i in range(1, 4)
        ],
        "fake": [
            {"host": "w1-gent", "port": 65201, "token": "vb-lab11", "user": "vbmu4"},
            {"host": "w2-gent", "port": 65301, "token": "vb-lab21", "user": "vbmu5"},
        ],
        "tbs": ["python test/live/stress/http_mixed_stress_tb.py --work-dir test/artifacts/env/scenario-multi-user --workers 4 --rounds 4"],
    },
    "concurrency": {
        "title": "高并发：真机 4 + lab fake 16（20 真机不可行，见文档 §5 内存账）",
        "client": "windows（本机）+ w1（Linux 客户端，一致性用）",
        "real": [
            {"user": f"vbcc{i}", "token": f"vb-cc{i}", "port": 65190 + i, "local_port": 64590 + i, "pdk": False}
            for i in range(1, 5)
        ],
        "fake": [
            {"host": h, "port": base + i, "token": f"vb-lab{h[1]}{i}", "user": f"vbfake{h[1]}{i}"}
            for h, base in (("w1-gent", 65200), ("w2-gent", 65300), ("w3-gent", 65400), ("w4-gent", 65500))
            for i in range(1, 5)
        ],
        "tbs": [
            "python test/live/stress/http_mixed_stress_tb.py --work-dir test/artifacts/env/scenario-concurrency --workers 24 --rounds 3",
            "python test/shared/runners/ops_used.py",
        ],
    },
}


def _ssh(host: str, command: str, timeout: int = 60, check: bool = False):
    done = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", host, command],
                          capture_output=True, text=True, encoding="utf-8", errors="replace",
                          timeout=timeout)
    if check and done.returncode != 0:
        raise RuntimeError(f"ssh {host} failed: {done.stderr.strip()[:200]}")
    return done


def _ssh_script(host: str, script: str, timeout: int = 180):
    payload = base64.b64encode(script.encode("utf-8")).decode("ascii")
    return _ssh(host, f"echo {payload} | base64 -d | bash", timeout=timeout)


def _tcp_ok(ip: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((ip, port), timeout):
            return True
    except OSError:
        return False


def _wait_port(ip: str, port: int, timeout: float = 150.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _tcp_ok(ip, port):
            return True
        time.sleep(2.0)
    return False


def _route(host, user):
    return {"host": host, "user": user, "jump_host": None, "jump_user": None, "proxy": None}


def _role(root, host, user, **extra):
    role = {"mode": None, "root": root, "expected_fingerprint": None, "max_sessions": 32}
    role.update(_route(host, user))
    role.update(extra)
    return role


def _real_entry(user: str, token: str, port: int, local_port: int) -> dict:
    root = f"/home/Gent/.virtuoso-bridge/{user}"
    roles = {name: _role(root, REAL_HOST, "Gent") for name in ("command", "file", "spectre")}
    roles["daemon"] = _role(root, REAL_HOST, "Gent", daemon_port=port, local_port=local_port, python=None)
    roles["gui"] = _role(root, REAL_HOST, "Gent", display=":99")
    return {"token": token, "mode": {"default": "remote"},
            "ssh": {"default": _route(REAL_HOST, "Gent"), "backend": "paramiko",
                    "control_master": "auto", "tool_override": {}},
            "root": {"default": None}, "roles": roles, "registered_at": int(time.time())}


def _fake_entry(user: str, token: str, host: str, port: int, local_port: int) -> dict:
    root = f"/home/dev/.virtuoso-bridge/{user}"
    return {"token": token, "mode": {"default": "remote"},
            "ssh": {"default": _route(host, "dev"), "backend": "paramiko",
                    "control_master": "auto", "tool_override": {}},
            "root": {"default": None},
            "roles": {"daemon": _role(root, host, "dev", daemon_port=port,
                                      local_port=local_port, python=None)},
            "registered_at": int(time.time())}


def _registry_for(scenario: dict) -> dict:
    users: dict[str, dict] = {}
    for index, item in enumerate(scenario.get("real", []), start=1):
        users[item["user"]] = _real_entry(item["user"], item["token"], item["port"], item["local_port"])
    for index, item in enumerate(scenario.get("fake", []), start=1):
        users[item["user"]] = _fake_entry(item["user"], item["token"], item["host"], item["port"],
                                          64560 + index)
    return users


def _deploy_real(user: str, token: str, port: int, pdk: bool) -> str:
    """Deploy ramic + setup + cds.lib + .cdsinit on wsl-gent, then start Virtuoso."""
    root = f"/home/Gent/.virtuoso-bridge/{user}"
    proj = f"/home/Gent/project/{user}"

    from common.setup import generate_setup_il

    setup_il = generate_setup_il(
        daemon=f"{root}/ramic/ramic_bridge_daemon_3.py",
        il=f"{root}/ramic/ramic_bridge.il",
        python_cmd="python3",
        port=port,
        token=token,
        identity=f"{root}/status/identity.json",
        temp_dir=f"{root}/tmp",
        log_path=f"{root}/logs/daemon.log",
    )
    resources = {name: (ROOT / "src" / "bridge" / "resources" / name).read_bytes()
                 for name in RAMIC_FILES}
    payload = {
        "setup_il": setup_il,
        "resources": {k: base64.b64encode(v).decode() for k, v in resources.items()},
        "pdk": pdk,
    }
    script = [
        f"mkdir -p {root}/ramic {root}/setup {root}/logs {root}/tmp {root}/status {root}/run {proj}",
        "python3 - <<'PY'",
        "import base64, json, pathlib, sys",
        f"root = pathlib.Path('{root}')",
        f"proj = pathlib.Path('{proj}')",
        "data = json.loads(sys.stdin.read())",
        "for name, blob in data['resources'].items():",
        "    (root / 'ramic' / name).write_bytes(base64.b64decode(blob))",
        "(root / 'setup' / 'virtuoso_setup.il').write_text(data['setup_il'], encoding='utf-8')",
        "(root / 'run' / '.cdsinit').write_text(f'load(\"{root}/setup/virtuoso_setup.il\")\\n', encoding='utf-8')",
        "include = 'INCLUDE " + PDK_CDS + "' if data['pdk'] else ''",
        "proj_cds = proj / 'cds.lib'",
        "if not proj_cds.exists():",
        "    proj_cds.write_text(f'SOFTINCLUDE " + CADENCE_SOFTINCLUDE + "\\n{include}\\n', encoding='utf-8')",
        "elif data['pdk'] and 'PDK' not in proj_cds.read_text(encoding='utf-8', errors='replace'):",
        "    proj_cds.write_text(proj_cds.read_text(encoding='utf-8', errors='replace') + include + '\\n', encoding='utf-8')",
        "PY",
        f"cd {root}/run && DISPLAY=:99 nohup virtuoso -cdslib {proj}/cds.lib -log {root}/run/CDS.log "
        f"> {root}/logs/start.log 2>&1 < /dev/null & echo launched",
    ]
    body = "\n".join(script)
    _ssh_script(REAL_HOST, f"cat > /tmp/.scenario_payload.json <<'JSON'\n{json.dumps(payload)}\nJSON\n{body}",
                timeout=180)
    return root


def _stop_real(user: str) -> None:
    _ssh(REAL_HOST, f"pkill -f 'project/{user}' 2>/dev/null; "
                    f"pkill -f '.virtuoso-bridge/{user}/ramic' 2>/dev/null; true", timeout=30)


def _start_fake(item: dict) -> None:
    host, port = item["host"], item["port"]
    user, token = item["user"], item["token"]
    bridge_root = f"/home/dev/.virtuoso-bridge/{user}"
    cmd = (f"mkdir -p {bridge_root}/tmp {bridge_root}/logs && "
           f"sudo -n ip netns exec labns nohup python3 {FAKE_DIR}/fake_virtuoso.py "
           f"--daemon {FAKE_DIR}/ramic_bridge_daemon_3.py --bind 0.0.0.0 --port {port} "
           f"--token {token} --temp-dir {bridge_root}/tmp "
           f"> {bridge_root}/logs/fake.log 2>&1 < /dev/null & echo started")
    try:
        _ssh(host, cmd, timeout=30)
    except subprocess.TimeoutExpired:
        pass
    _wait_port(LAB_IP[host], port, timeout=90)


def _stop_fake(item: dict) -> None:
    host, port = item["host"], item["port"]
    _ssh(host, f"sudo -n pkill -f 'ramic_bridge_daemon_3[.]py [0-9.]+ {port} ' 2>/dev/null; "
               f"sudo -n pkill -f 'fake_virtuoso[.]py.*--port {port}' 2>/dev/null; true", timeout=30)


def _state_path(name: str) -> Path:
    return ROOT / "test" / "artifacts" / f"scenario-{name}" / "state.json"


def _up(name: str) -> int:
    scenario = SCENARIOS[name]
    work_dir = ROOT / "test" / "artifacts" / f"scenario-{name}"
    work_dir.mkdir(parents=True, exist_ok=True)
    registry_path = work_dir / "registry.json"
    users = _registry_for(scenario)
    registry_path.write_text(json.dumps(users, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    Registry(registry_path).load()          # 生产校验

    print(f"[{name}] {scenario['title']}")
    print(f"  client : {scenario['client']}")
    print(f"  registry: {registry_path.relative_to(ROOT)}  ({len(users)} users)")
    for item in scenario.get("fake", []):
        _stop_fake(item)                     # 先归零，保证状态确定
        _start_fake(item)
        print(f"  fake   : {item['host']}:{item['port']} token={item['token']} "
              f"reachable={_tcp_ok(LAB_IP[item['host']], item['port'])}")
    for item in scenario.get("real", []):
        _stop_real(item["user"])
        _deploy_real(item["user"], item["token"], item["port"], item.get("pdk", False))
        ready = _wait_port("127.0.0.1", item["port"], timeout=150)
        print(f"  real   : {REAL_HOST}:{item['port']} user={item['user']} token={item['token']} "
              f"pdk={item.get('pdk', False)} daemon_ready={ready}")
    state = {"scenario": name, "started_at": datetime.now(timezone.utc).isoformat(),
             "work_dir": str(work_dir), "real": scenario.get("real", []), "fake": scenario.get("fake", [])}
    _state_path(name).write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  TB:")
    for command in scenario.get("tbs", []):
        print(f"    {command}")
    return 0


def _status(name: str) -> int:
    state = json.loads(_state_path(name).read_text(encoding="utf-8"))
    bad = 0
    for item in state.get("real", []):
        ok = _tcp_ok("127.0.0.1", item["port"], timeout=2.0)   # 经 ssh 隧道前先看本机？
        # 真实例监听在远端 127.0.0.1，这里用远端 ss 判断
        remote = _ssh(REAL_HOST, f"ss -ltn | grep -c ':{item['port']} ' || true").stdout.strip()
        up = remote not in ("", "0")
        bad += 0 if up else 1
        print(f"  real {item['user']:10s} port={item['port']} {'UP' if up else 'DOWN'}")
    for item in state.get("fake", []):
        up = _tcp_ok(LAB_IP[item["host"]], item["port"], timeout=2.0)
        bad += 0 if up else 1
        print(f"  fake {item['user']:10s} {item['host']}:{item['port']} {'UP' if up else 'DOWN'}")
    return 1 if bad else 0


def _down(name: str) -> int:
    state = json.loads(_state_path(name).read_text(encoding="utf-8"))
    for item in state.get("real", []):
        _stop_real(item["user"])
        print(f"  real {item['user']} stopped")
    for item in state.get("fake", []):
        _stop_fake(item)
        print(f"  fake {item['host']}:{item['port']} stopped")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list", help="list scenarios")
    for action in ("up", "status", "down"):
        p = sub.add_parser(action)
        p.add_argument("name", choices=sorted(SCENARIOS))
    args = parser.parse_args()

    if args.action == "list":
        for name, scenario in sorted(SCENARIOS.items()):
            print(f"{name:12s} {scenario['title']}")
            print(f"{'':12s} client={scenario['client']} "
                  f"real={len(scenario.get('real', []))} fake={len(scenario.get('fake', []))}")
        return 0
    return {"up": _up, "status": _status, "down": _down}[args.action](args.name)


if __name__ == "__main__":
    raise SystemExit(main())
