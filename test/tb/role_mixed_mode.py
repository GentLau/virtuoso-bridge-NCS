"""T3: per-role mixed mode on the client host.

Client runs on wsl-gent (local): daemon/command/file roles are local; gui and
spectre roles are remote (vps).  Proves one token can mix local and remote
roles.  Run ON wsl-gent:  PYTHONPATH=src .venv/bin/python test/tb/role_mixed_mode.py
"""
from __future__ import annotations
import json, socket, subprocess, sys, tempfile, threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from _win import no_window  # noqa: E402  (hide Windows consoles for ssh/scp)

from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.runtime_paths import set_working_dir, registry_path

VPS = "vps"
TOKEN = "mix-1"


class FakeDaemon:
    def __init__(self, token):
        self.token = token
        self.sock = socket.socket(); self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0)); self.sock.listen(8)
        self.port = self.sock.getsockname()[1]
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try: conn, _ = self.sock.accept()
            except OSError: return
            try:
                data = b""
                while True:
                    chunk = conn.recv(65536)
                    if not chunk: break
                    data += chunk
                req = json.loads(data.decode())
                if req.get("token") != self.token:
                    conn.sendall(b"\x15" + json.dumps({"error": "invalid token", "log": ""}).encode() + b"\x1e")
                else:
                    val = "2" if "1+1" in req.get("skill", "") else self.token
                    conn.sendall(b"\x02" + json.dumps({"value": val, "log": ""}).encode() + b"\x1e")
            except Exception:
                pass
            finally:
                conn.close()


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="vb-mix-"))
    wd = set_working_dir(tmp / "wd")
    reg = load_registry(registry_path())
    daemon = FakeDaemon(TOKEN)

    e = UserEntry(token=TOKEN, mode="local")  # mode.default = local
    e.root.default = str(tmp / "roots")
    e.roles.daemon.mode = "local"
    e.roles.daemon.daemon_port = daemon.port
    e.roles.daemon.local_port = daemon.port
    e.roles.command.mode = "local"
    e.roles.file.mode = "local"
    # gui / spectre are remote on vps
    for name in ("gui", "spectre"):
        role = getattr(e.roles, name)
        role.mode = "remote"; role.host = VPS; role.user = "root"
        role.root = "/root/vbtest-mix"
    reg.register("mix01", e)

    m = BusinessServer(wd)
    local_host = socket.gethostname().lower()
    vps_host = subprocess.run(["ssh", VPS, "hostname -f"], capture_output=True, text=True, timeout=20, **no_window()).stdout.strip().lower()
    out = {"case": "T3", "client": "wsl-gent", "local_host": local_host, "vps_host": vps_host}
    errors = []

    r = m.execute_skill("RBDToken", token=TOKEN, timeout=60)
    out["skill"] = {"ok": r.ok, "output": (r.output or "").strip().strip('"')}
    if out["skill"]["output"] != TOKEN:
        errors.append(f"skill: {out['skill']}")

    c = m.run_command("hostname -f", token=TOKEN, timeout=60)
    out["command"] = {"rc": c.returncode, "host": c.stdout.strip()}
    if c.returncode != 0 or local_host.split(".")[0] not in c.stdout.strip().lower():
        errors.append(f"command not local: {out['command']}")

    g = m.run_gui_command("hostname -f", token=TOKEN, timeout=60)
    out["gui_command"] = {"rc": g.returncode, "host": g.stdout.strip()}
    if g.returncode != 0 or vps_host not in g.stdout.strip().lower():
        errors.append(f"gui not remote(vps): {out['gui_command']}")

    sp = m.run_spectre_command("hostname -f", token=TOKEN, timeout=60)
    out["spectre_command"] = {"rc": sp.returncode, "host": sp.stdout.strip()}
    if sp.returncode != 0 or vps_host not in sp.stdout.strip().lower():
        errors.append(f"spectre not remote(vps): {out['spectre_command']}")

    payload = b"mixed-mode-payload"
    src = tmp / "p.bin"; src.write_bytes(payload)
    up = m.upload_file(src, "m.bin", token=TOKEN, timeout=60)
    dst = tmp / "back.bin"
    dn = m.download_file("m.bin", dst, token=TOKEN, timeout=60) if up.returncode == 0 else None
    out["file"] = {
        "upload_rc": up.returncode,
        "download_rc": dn.returncode if dn else None,
        "sha_ok": bool(dn and dst.exists() and dst.read_bytes() == payload),
        "local_path": str(tmp / "roots" / "file" / "m.bin"),
    }
    if not out["file"]["sha_ok"]:
        errors.append(f"file: {out['file']}")

    out["errors"] = errors
    print(json.dumps(out, ensure_ascii=False))
    for c_ in list(m._clients.values()):
        try: c_.close()
        except Exception: pass
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
