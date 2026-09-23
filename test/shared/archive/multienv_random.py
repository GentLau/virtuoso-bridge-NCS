"""Randomized mixed-concurrency business simulation (single client, 3 envs).

6 real wsl Virtuoso users + 10 vps fake users, one Windows client.  Ops are
chosen at random (skill/command/upload/download), shuffled, and business
rejections are retried.  Emits per-op counters + routing/log/hash evidence.
"""
from __future__ import annotations
import argparse, hashlib, json, random, sys, tempfile, threading, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "src"))
from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from register.probe import allocate_local_port
from common.paths import override_work_dir_for_tests, registry_path

WSL, VPS = "wsl-gent", "vps"

def build_users(reg):
    users = []
    reserved = set()
    for n in range(1, 7):
        user, token, port = f"vb{n:02d}", f"vb-vb{n:02d}", 65100 + n
        lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
        e = UserEntry(token=token, mode="remote")
        e.roles.daemon.host = WSL; e.roles.daemon.daemon_port = port; e.roles.daemon.local_port = lp
        e.roles.command.host = WSL; e.roles.command.user = "Gent"; e.roles.file.host = WSL
        e.roles.daemon.root = f"/home/Gent/.virtuoso-bridge/{user}"
        e.roles.daemon.expected_user = "Gent"
        reg.register(user, e); users.append((user, token, "real", port))
    for n in range(10):
        user, token, port = f"cloud{n:02d}", f"cloud-{n:02d}", 6701 + n
        lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
        e = UserEntry(token=token, mode="remote")
        e.roles.daemon.host = VPS; e.roles.daemon.daemon_port = port; e.roles.daemon.local_port = lp
        e.roles.command.host = VPS; e.roles.command.user = "root"; e.roles.file.host = VPS
        e.roles.daemon.root = f"/root/.virtuoso-bridge/{user}"
        e.roles.daemon.expected_user = "root"
        reg.register(user, e); users.append((user, token, "fake", port))
    return users

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ops-per-user", type=int, default=12)
    ap.add_argument("--seed", type=int, default=20260911)
    ap.add_argument("--concurrency", type=int, default=64)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-rand-")))
    reg = load_registry(registry_path())
    users = build_users(reg)
    m = BusinessServer(wd)

    rng = random.Random(args.seed)
    hashes = {}
    counters = {"skill":0,"command":0,"upload":0,"download":0}
    retries = {"skill":0,"command":0,"upload":0,"download":0}
    errors = []
    lock = threading.Lock()
    tasks = []
    base_seq = {}
    for ui,(user,tok,kind,port) in enumerate(users):
        # every user gets one guaranteed upload that downloads can reference
        size0 = rng.randint(1, 32768)
        base_seq[user] = f"{ui}-0"
        tasks.append(("upload", user, tok, kind, base_seq[user], size0))
        for opi in range(1, args.ops_per_user):
            choice = rng.random()
            seq = f"{ui}-{opi}"
            if choice < 0.40:
                tasks.append(("skill", user, tok, kind, seq, None))
            elif choice < 0.70:
                tasks.append(("command", user, tok, kind, seq, rng.randint(0,2)))
            elif choice < 0.85:
                tasks.append(("upload", user, tok, kind, seq, rng.randint(1, 32768)))
            else:
                tasks.append(("download", user, tok, kind, base_seq[user], None))
    rng.shuffle(tasks)
    downloads = [t for t in tasks if t[0] == "download"]
    tasks = [t for t in tasks if t[0] != "download"] + downloads

    def one(task):
        op, user, tok, kind, seq, arg = task
        with lock:
            counters[op] += 1
        attempt = 0
        if op == "skill":
            while True:
                attempt += 1
                if attempt % 4 == 0 and kind == "real":
                    marker = f"RAND-{seq}-{uuid.uuid4().hex[:6]}"
                    skill = f'progn(hiPrintToLogFile("{marker}") RBDToken)'
                    r = m.execute_skill(skill, token=tok, timeout=90)
                    ok = r.ok and (r.output or "").strip().strip('"') == tok and marker in r.log
                    if not ok:
                        with lock: errors.append(f"skill-log {user} {seq}: {r.status} {r.output!r} log={r.log!r} {r.errors}")
                    break
                r = m.execute_skill("RBDToken", token=tok, timeout=90)
                if not r.ok and "exceeded" in str(r.errors):
                    with lock: retries[op] += 1
                    time.sleep(0.01); continue
                if not r.ok or (r.output or "").strip().strip('"') != tok:
                    with lock: errors.append(f"skill {user} {seq}: {r.status} {r.output!r} {r.errors}")
                break
        elif op == "command":
            cmds = [f"echo vb-{seq}", "python3 -c 'print(sum(range(1,101)))'", "sleep 0.2"]
            wants = [f"vb-{seq}", "5050", ""]
            cmd, want = cmds[arg], wants[arg]
            while True:
                attempt += 1
                c = m.run_command(cmd, token=tok)
                if c.returncode == 1 and "exceeded" in c.stderr:
                    with lock: retries[op] += 1
                    time.sleep(0.01); continue
                if c.returncode != 0 or c.stdout.strip() != want:
                    with lock: errors.append(f"command {user} {seq}: rc={c.returncode} out={c.stdout!r} err={c.stderr!r}")
                break
        elif op == "upload":
            data = bytes((arg + 1) % 251 for _ in range(arg))
            src = Path(tempfile.mkdtemp()) / "f.bin"; src.write_bytes(data)
            remote = f"/root/.virtuoso-bridge/{user}/r-{seq}.bin" if kind == "fake" else f"/home/Gent/.virtuoso-bridge/{user}/r-{seq}.bin"
            hashes[remote] = hashlib.sha256(data).hexdigest()
            while True:
                attempt += 1
                u = m.upload_file(src, remote, token=tok)
                if u.returncode == 1 and "exceeded" in u.stderr:
                    with lock: retries[op] += 1
                    time.sleep(0.01); continue
                if u.returncode != 0:
                    with lock: errors.append(f"upload {user} {seq}: {u.stderr}")
                break
        else:
            remote = f"/root/.virtuoso-bridge/{user}/r-{seq}.bin" if kind == "fake" else f"/home/Gent/.virtuoso-bridge/{user}/r-{seq}.bin"
            dst = Path(tempfile.mkdtemp()) / "g.bin"
            while True:
                attempt += 1
                d = m.download_file(remote, dst, token=tok)
                if d.returncode == 1 and "exceeded" in d.stderr:
                    with lock: retries[op] += 1
                    time.sleep(0.01); continue
                if d.returncode != 0:
                    with lock: errors.append(f"download {user} {seq}: rc={d.returncode} {d.stderr}")
                    break
                want = hashes.get(remote)
                if want and hashlib.sha256(dst.read_bytes()).hexdigest() != want:
                    with lock: errors.append(f"download-hash {user} {seq}")
                break

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(one, tasks))
    out = {
        "client": "Windows 本机",
        "users": {"real_wsl": 6, "fake_vps": 10},
        "ops": counters,
        "retries": retries,
        "errors": len(errors),
        "elapsed": round(time.time()-t0, 1),
        "seed": args.seed,
        "error_samples": errors[:10],
    }
    if args.json:
        print(json.dumps(out, ensure_ascii=False))
    else:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    for c in list(m._clients.values()):
        try: c.close()
        except Exception: pass
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
