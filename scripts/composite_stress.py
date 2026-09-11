"""Composite HTTPServer business simulation for two client topologies."""
from __future__ import annotations
import argparse, hashlib, json, os, random, socket, sys, tempfile, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_here = Path(__file__).resolve().parent
for _cand in (_here / "src", _here.parent / "src"):
    if _cand.is_dir():
        sys.path.insert(0, str(_cand))
        break

from transport.registry import UserEntry, load_registry
from transport.register.probe import allocate_local_port
from transport.runtime_paths import set_working_dir, registry_path
from transport.middle import BusinessServer
from server.stress_server import StressServer

SPECTRE = "/opt/eda/cadence/SPECTRE241/bin/spectre"

def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port

def post(base, path, payload, timeout=180):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())

def start_local(user, setup, display):
    proj = Path(f"/home/Gent/project/{user}")
    proj.mkdir(parents=True, exist_ok=True)
    (proj / ".cdsinit").write_text(f'load("{setup}")\n', encoding="utf-8")
    cmd = (f"cd {proj} && DISPLAY={display} nohup bash -lc "
           f"'source ~/.bashrc; virtuoso -log {proj}/CDS.log' > {proj}/start.log 2>&1 < /dev/null &")
    os.system(f'bash -lc "{cmd}"')

def wait_port(port, timeout=240):
    deadline = time.time() + timeout
    while time.time() < deadline:
        s = socket.socket(); s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", port)) == 0:
            s.close(); return True
        s.close(); time.sleep(2)
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["win-mixed", "wsl-mixed"], required=True)
    ap.add_argument("--ops", type=int, default=80)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()

    wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-comp-")))
    reg = load_registry(registry_path())
    users = []
    reserved = set()
    if args.mode == "win-mixed":
        for n in range(1, 7):
            user, token, port = f"vb{n:02d}", f"vb-vb{n:02d}", 65100 + n
            lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
            e = UserEntry(token=token, mode="remote")
            e.route.skill.daemon_host = "wsl-gent"; e.route.skill.daemon_port = port; e.route.skill.local_port = lp
            e.route.command.host = "wsl-gent"; e.route.command.user = "Gent"; e.route.file.host = "wsl-gent"
            e.deploy.scratch_root = f"/home/Gent/.virtuoso-bridge/{user}"
            e.expected.daemon_user = "Gent"
            reg.register(user, e); users.append((user, token, "real"))
        for n in range(10):
            user, token, port = f"cloud{n:02d}", f"cloud-{n:02d}", 6701 + n
            lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
            e = UserEntry(token=token, mode="remote")
            e.route.skill.daemon_host = "vps"; e.route.skill.daemon_port = port; e.route.skill.local_port = lp
            e.route.command.host = "vps"; e.route.command.user = "root"; e.route.file.host = "vps"
            e.deploy.scratch_root = "/root/vbtest"
            e.expected.daemon_user = "root"
            reg.register(user, e); users.append((user, token, "fake"))
    else:
        # wsl client: 4 local real users + 4 vps fake users
        from transport.register import RegistrationFlow, RegistrationRequest
        for n in range(4):
            user, token, port = f"lc{n:02d}", f"l-{user}", 65411 + n
            flow = RegistrationFlow(reg)
            state = flow.apply(RegistrationRequest(mode="local", user=user, token=token, daemon_port=port, spectre_bin=SPECTRE))
            if state.stage != "deployed":
                raise RuntimeError(state.errors)
            start_local(user, state.setup_path, os.environ.get("VB_DISPLAY", "localhost:10.0"))
            if not wait_port(port):
                raise RuntimeError(f"{user} daemon not ready")
            state = flow.verify()
            if state.stage != "committed":
                raise RuntimeError(state.errors)
            users.append((user, token, "local"))
        for n in range(4):
            user, token, port = f"cloud{n:02d}", f"cloud-{n:02d}", 6701 + n
            lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
            e = UserEntry(token=token, mode="remote")
            e.route.skill.daemon_host = "vps"; e.route.skill.daemon_port = port; e.route.skill.local_port = lp
            e.route.command.host = "vps"; e.route.command.user = "root"; e.route.file.host = "vps"
            e.deploy.scratch_root = "/root/vbtest"
            e.expected.daemon_user = "root"
            reg.register(user, e); users.append((user, token, "fake"))

    middle = BusinessServer(wd)
    port = free_port()
    server = StressServer(("127.0.0.1", port), middle)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{port}"

    rng = random.Random(args.seed)
    tasks = []
    for i in range(args.ops):
        user, tok, kind = users[i % len(users)]
        choice = rng.random()
        delay = rng.randint(0, 40)
        if choice < 0.4:
            tasks.append(("skill", user, tok, i, delay))
        elif choice < 0.6:
            tasks.append(("composite", user, tok, i, delay))
        elif choice < 0.8:
            tasks.append(("command", user, tok, i, delay))
        else:
            tasks.append(("upload", user, tok, i, delay))
    rng.shuffle(tasks)

    counters = {}
    retries = 0
    errors = []
    lock = threading.Lock()

    def one(task):
        nonlocal retries
        op, user, tok, seq, delay = task
        with lock: counters[op] = counters.get(op, 0) + 1
        attempt = 0
        while True:
            attempt += 1
            try:
                if op == "skill":
                    st, body = post(base, "/api/skill", {"token": tok, "skill": "RBDToken"})
                elif op == "composite":
                    st, body = post(base, "/api/composite", {"token": tok, "seq": str(seq), "delay_ms": delay})
                elif op == "command":
                    st, body = post(base, "/api/command", {"token": tok, "cmd": f"echo vb-{seq}; sleep {delay/1000.0:.3f}"})
                else:
                    data = (tok + str(seq)).encode() * 512
                    src = Path(tempfile.mkdtemp()) / "f.bin"; src.write_bytes(data)
                    remote = f"{middle.registry.by_token(tok).deploy.scratch_root}/comp-{user}-{seq}.bin"
                    st, body = post(base, "/api/upload", {"token": tok, "remote_path": remote,
                                                           "content_b64": __import__('base64').b64encode(data).decode()})
                    body = {"ok": body.get("returncode") == 0, "body": body}
                    if not body["ok"]:
                        with lock: errors.append(f"upload {user} {seq}: {body['body']}")
                        break
                    continue
            except urllib.error.HTTPError as exc:
                body = {}
                try: body = json.loads(exc.read().decode())
                except Exception: pass
                st = exc.code
            except Exception as exc:
                st, body = -1, {"error": str(exc)}
            if st == 200:
                if op == "skill" and (not body.get("ok") or (body.get("output") or "").strip().strip('"') != tok):
                    with lock: errors.append(f"skill {user} {seq}: {body}")
                    break
                if op == "composite" and not body.get("ok"):
                    with lock: errors.append(f"composite {user} {seq}: {body}")
                    break
                if op == "command" and body.get("returncode") != 0:
                    with lock: errors.append(f"command {user} {seq}: {body}")
                    break
                break
            if ("exceeded" in str(body) or st in (-1, 500)) and attempt < 100:
                with lock: retries += 1
                time.sleep(0.05)
                continue
            with lock: errors.append(f"{op} {user} {seq}: status={st} attempt={attempt} {body}")
            break

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(one, tasks))
    print(json.dumps({"mode": args.mode, "client": "windows" if args.mode=="win-mixed" else "wsl-gent",
                      "users": len(users), "ops": counters, "retries": retries,
                      "errors": len(errors), "elapsed": round(time.time()-t0,1), "seed": args.seed,
                      "samples": errors[:5]}, ensure_ascii=False))
    server.shutdown(); server.server_close()
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
