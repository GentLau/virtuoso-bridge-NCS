"""C1: same business sequence on Windows and Linux clients against vps fake daemons."""
from __future__ import annotations
import argparse, hashlib, json, random, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
_here = Path(__file__).resolve().parent
for _cand in (_here / "src", _here.parent / "src"):
    if _cand.is_dir():
        sys.path.insert(0, str(_cand))
        break
from transport.middle import BusinessServer
from transport.registry import UserEntry, load_registry
from transport.register.probe import allocate_local_port
from transport.runtime_paths import set_working_dir, registry_path

VPS = "vps"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="client")
    ap.add_argument("--users", type=int, default=10)
    ap.add_argument("--ops-per-user", type=int, default=6)
    ap.add_argument("--seed", type=int, default=777)
    ap.add_argument("--concurrency", type=int, default=32)
    args = ap.parse_args()

    wd = set_working_dir(Path(tempfile.mkdtemp(prefix="vb-equiv-")))
    reg = load_registry(registry_path())
    users = []
    reserved = set()
    for n in range(args.users):
        user, token, port = f"cloud{n:02d}", f"cloud-{n:02d}", 6701 + n
        lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
        e = UserEntry(token=token, mode="remote")
        e.route.daemon.host = VPS; e.route.daemon.daemon_port = port; e.route.daemon.local_port = lp
        e.route.command.host = VPS; e.route.command.user = "root"; e.route.file.host = VPS
        e.deploy.scratch_root = "/root/vbtest"
        e.expected.daemon_user = "root"
        reg.register(user, e)
        users.append((user, token))

    m = BusinessServer(wd)
    rng = random.Random(args.seed)
    tasks = []
    for ui, (user, tok) in enumerate(users):
        tasks.append(("upload", user, tok, f"{ui}-0", 2048))
        for opi in range(1, args.ops_per_user):
            choice = rng.random()
            seq = f"{ui}-{opi}"
            if choice < 0.45:
                tasks.append(("skill", user, tok, seq, None))
            elif choice < 0.75:
                tasks.append(("command", user, tok, seq, rng.randint(0,1)))
            else:
                tasks.append(("download", user, tok, f"{ui}-0", None))
    rng.shuffle(tasks)
    downloads = [t for t in tasks if t[0] == "download"]
    tasks = [t for t in tasks if t[0] != "download"] + downloads

    counters = {"skill":0,"command":0,"upload":0,"download":0}
    retries = {"skill":0,"command":0,"upload":0,"download":0}
    errors = []
    lock = threading.Lock()

    def one(task):
        op, user, tok, seq, arg = task
        with lock: counters[op] += 1
        if op == "skill":
            while True:
                r = m.execute_skill("RBDToken", token=tok, timeout=90)
                transient = "exceeded" in str(r.errors) or any(
                    k in str(r.errors).lower() for k in ("refused", "reset", "closed", "banner", "timed out")
                )
                if not r.ok and transient:
                    with lock: retries[op] += 1
                    time.sleep(0.01); continue
                if not r.ok or (r.output or "").strip().strip('"') != tok:
                    with lock: errors.append(f"skill {user} {seq}: {r.status} {r.output!r} {r.errors}")
                break
        elif op == "command":
            cmd = f"echo vb-{seq}"
            while True:
                c = m.run_command(cmd, token=tok)
                if c.returncode in (1, 255) and ("exceeded" in c.stderr or any(
                        k in c.stderr.lower() for k in ("kex", "closed", "banner", "VB-TRANSPORT"))
                ):
                    with lock: retries[op] += 1
                    time.sleep(0.01); continue
                if c.returncode != 0 or c.stdout.strip() != f"vb-{seq}":
                    with lock: errors.append(f"command {user} {seq}: rc={c.returncode} out={c.stdout!r} err={c.stderr!r}")
                break
        elif op == "upload":
            data = (seq.encode() * 512)[:arg]
            src = Path(tempfile.mkdtemp()) / "f.bin"; src.write_bytes(data)
            remote = f"/root/vbtest/{user}/eq-{seq}.bin"
            while True:
                u = m.upload_file(src, remote, token=tok)
                if u.returncode != 0 and (not u.stderr.strip() or "exceeded" in u.stderr or any(
                        k in u.stderr.lower() for k in ("kex", "closed", "banner", "VB-TRANSPORT"))
                ):
                    with lock: retries[op] += 1
                    time.sleep(0.05); continue
                if u.returncode != 0:
                    with lock: errors.append(f"upload {user} {seq}: {u.stderr}")
                break
        else:
            remote = f"/root/vbtest/{user}/eq-{seq}.bin"
            dst = Path(tempfile.mkdtemp()) / "g.bin"
            while True:
                d = m.download_file(remote, dst, token=tok)
                if d.returncode != 0 and (not d.stderr.strip() or "exceeded" in d.stderr or any(
                        k in d.stderr.lower() for k in ("kex", "closed", "banner", "VB-TRANSPORT"))
                ):
                    with lock: retries[op] += 1
                    time.sleep(0.05); continue
                if d.returncode != 0:
                    with lock: errors.append(f"download {user} {seq}: rc={d.returncode} {d.stderr}")
                break

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(one, tasks))
    out = {"label": args.label, "users": len(users), "ops": counters, "retries": retries,
           "errors": len(errors), "elapsed": round(time.time()-t0,1), "seed": args.seed}
    print(json.dumps(out, ensure_ascii=False))
    for c in list(m._clients.values()):
        try: c.close()
        except Exception: pass
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
