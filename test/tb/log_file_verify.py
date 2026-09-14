"""HTTP-based log byte verification against the real CDS.log interval."""
import argparse, base64, json, socket, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request, uuid
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from transport.registry import UserEntry, load_registry
from transport.register.probe import allocate_local_port
from transport.runtime_paths import set_working_dir, registry_path
from server.stress_server import StressServer
from transport.middle import BusinessServer

LOG = "/home/Gent/project/vb01/CDS.log"

def ssh(cmd):
    return subprocess.run(["ssh", "wsl-gent", cmd], capture_output=True, text=True, timeout=60)

def fsize():
    return int(ssh(f"stat -c %s {LOG}").stdout.strip())

def read_range(start, length):
    if length <= 0:
        return b""
    out = ssh(f"dd if={LOG} bs=1 skip={start} count={length} 2>/dev/null | base64 -w0")
    return base64.b64decode(out.stdout.strip() or "")

def post(base, path, payload, timeout=90):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--requests", type=int, default=12)
    args = ap.parse_args()

    wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-logver-")))
    reg = load_registry(registry_path())
    e = UserEntry(token="vb-vb01", mode="remote")
    e.roles.daemon.host = "wsl-gent"; e.roles.daemon.daemon_port = 65101
    e.roles.daemon.local_port = allocate_local_port()
    e.roles.command.host = "wsl-gent"; e.roles.command.user = "Gent"
    e.roles.daemon.root = "/home/Gent/.virtuoso-bridge/vb01"
    e.roles.daemon.expected_user = "Gent"
    reg.register("vb01", e)

    middle = BusinessServer(wd)
    sock = socket.socket(); sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]; sock.close()
    server = StressServer(("127.0.0.1", port), middle)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    rows = []
    for i in range(args.requests):
        marker = f"LOGVER-{uuid.uuid4().hex[:10]}"
        lines = [marker]
        if i % 3 == 0:
            lines.append("\\o info-line-" + marker)
        before = fsize()
        skill = "progn(" + " ".join(f'hiPrintToLogFile("{ln}")' for ln in lines) + " 1+1)"
        body = post(base, "/api/skill", {"token": "vb-vb01", "skill": skill})
        after = fsize()
        file_bytes = read_range(before, after - before)
        returned = (body.get("log") or "").encode("utf-8")
        rows.append({"i": i, "before": before, "after": after,
                     "file_len": len(file_bytes), "returned_len": len(returned),
                     "equal": file_bytes == returned, "output": body.get("output"), "ok": body.get("ok")})
        time.sleep(0.1)
    ok = sum(1 for r in rows if r["equal"])
    print(json.dumps({"requests": len(rows), "equal": ok, "rows": rows}, ensure_ascii=False))
    server.shutdown(); server.server_close()
    return 0 if ok == len(rows) else 1

if __name__ == "__main__":
    raise SystemExit(main())
