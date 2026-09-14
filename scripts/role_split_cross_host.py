"""T2: per-role split across hosts (daemon/gui on wsl, command/file/spectre on vps).

Proves the 5 interfaces route to their own role endpoint, not to one host.
Run from Windows:  python scripts/role_split_cross_host.py
"""
from __future__ import annotations
import json, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.register.probe import allocate_local_port
from transport.runtime_paths import set_working_dir, registry_path

WSL = "wsl-gent"
VPS = "vps"


def main() -> int:
    wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-split-")))
    reg = load_registry(registry_path())
    lp = allocate_local_port(tries=200)
    e = UserEntry(token="vb-vb01", mode="remote")
    # daemon + gui live on wsl
    e.roles.daemon.host, e.roles.daemon.user = WSL, "Gent"
    e.roles.daemon.daemon_port, e.roles.daemon.local_port = 65101, lp
    e.roles.daemon.root = "/home/Gent/.virtuoso-bridge/vb01"
    e.roles.daemon.python = "/usr/bin/python3"
    e.roles.daemon.expected_user = "Gent"
    e.roles.gui.host, e.roles.gui.user = WSL, "Gent"
    e.roles.gui.root = "/home/Gent/vbtest-gui"
    # command + file + spectre live on vps
    for name in ("command", "file", "spectre"):
        role = getattr(e.roles, name)
        role.host, role.user = VPS, "root"
        role.root = "/root/vbtest-cross"
    e.roles.spectre.bin = "/bin/echo"
    reg.register("split01", e)

    m = BusinessServer(wd)
    out = {"case": "T2", "client": "windows", "roles": {
        "daemon": WSL, "gui": WSL, "command": VPS, "file": VPS, "spectre": VPS}}
    errors = []

    import subprocess
    def _host(alias: str) -> str:
        return subprocess.run(
            ["ssh", alias, "hostname -f"], capture_output=True, text=True, timeout=20
        ).stdout.strip().lower()

    wsl_host, vps_host = _host(WSL), _host(VPS)
    out["hostnames"] = {"wsl": wsl_host, "vps": vps_host}

    r = m.execute_skill("RBDToken", token="vb-vb01", timeout=60)
    out["skill"] = {"ok": r.ok, "output": (r.output or "").strip().strip('"')}
    if out["skill"]["output"] != "vb-vb01":
        errors.append(f"skill: {out['skill']}")

    c = m.run_command("hostname -f", token="vb-vb01", timeout=60)
    out["command"] = {"rc": c.returncode, "host": c.stdout.strip()}
    if c.returncode != 0 or vps_host not in c.stdout.strip().lower():
        errors.append(f"command not on vps: {out['command']}")

    g = m.run_gui_command("hostname -f", token="vb-vb01", timeout=60)
    out["gui_command"] = {"rc": g.returncode, "host": g.stdout.strip()}
    if g.returncode != 0 or wsl_host.split(".")[0] not in g.stdout.strip().lower():
        errors.append(f"gui command not on wsl: {out['gui_command']}")

    s = m.run_spectre_command("hostname -f", token="vb-vb01", timeout=60)
    out["spectre_command"] = {"rc": s.returncode, "host": s.stdout.strip()}
    if s.returncode != 0 or vps_host not in s.stdout.strip().lower():
        errors.append(f"spectre command not on vps: {out['spectre_command']}")

    payload = b"cross-host-" + str(time.time()).encode()
    src = Path(tempfile.mkdtemp()) / "p.bin"; src.write_bytes(payload)
    up = m.upload_file(src, "cross.bin", token="vb-vb01", timeout=60)
    dst = Path(tempfile.mkdtemp()) / "back.bin"
    dn = m.download_file("cross.bin", dst, token="vb-vb01", timeout=60) if up.returncode == 0 else None
    out["file"] = {
        "upload_rc": up.returncode,
        "download_rc": dn.returncode if dn else None,
        "sha_ok": bool(dn and dst.exists() and dst.read_bytes() == payload),
        "remote": f"/root/vbtest-cross/cross.bin",
    }
    if not out["file"]["sha_ok"]:
        errors.append(f"file roundtrip failed: {out['file']}")

    out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False))
    for c_ in list(m._clients.values()):
        try: c_.close()
        except Exception: pass
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
