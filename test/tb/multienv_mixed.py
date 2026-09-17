"""M1 single-client mixed multi-user: 6 real wsl Virtuoso + 10 vps fake daemons."""
from __future__ import annotations
import hashlib, os, subprocess, sys, tempfile, threading, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from transport.middle import BusinessServer
from common.registry import UserEntry, load_registry
from register.probe import allocate_local_port
from common.paths import override_work_dir_for_tests, registry_path

VPS = "vps"
WSL = "wsl-gent"

def main() -> int:
    wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-mixed-")))
    reg = load_registry(registry_path())
    users = []
    reserved = set()
    # 6 real wsl users
    for n in range(1, 7):
        user, token, port = f"vb{n:02d}", f"vb-vb{n:02d}", 65100 + n
        lp = allocate_local_port(reserved=reserved, tries=200)
        reserved.add(lp)
        e = UserEntry(token=token, mode="remote")
        e.roles.daemon.host = WSL; e.roles.daemon.daemon_port = port; e.roles.daemon.local_port = lp
        e.roles.command.host = WSL; e.roles.command.user = "Gent"
        e.roles.file.host = WSL
        e.roles.daemon.root = f"/home/Gent/.virtuoso-bridge/{user}"
        e.roles.daemon.expected_user = "Gent"
        e.ssh.backend = "openssh"
        reg.register(user, e)
        users.append((user, token))
    # 10 vps fake users
    for n in range(10):
        user, token, port = f"cloud{n:02d}", f"cloud-{n:02d}", 6701 + n
        lp = allocate_local_port(reserved=reserved, tries=200)
        reserved.add(lp)
        e = UserEntry(token=token, mode="remote")
        e.roles.daemon.host = VPS; e.roles.daemon.daemon_port = port; e.roles.daemon.local_port = lp
        e.roles.command.host = VPS; e.roles.command.user = "root"
        e.roles.file.host = VPS
        e.roles.daemon.root = "/root/vbtest"
        e.roles.daemon.expected_user = "root"
        e.ssh.backend = "openssh"
        reg.register(user, e)
        users.append((user, token))

    m = BusinessServer(wd)
    errors = []
    lock = threading.Lock()

    def skill(i):
        user, tok = users[i % len(users)]
        r = m.execute_skill("RBDToken", token=tok, timeout=90)
        got = (r.output or "").strip().strip('"')
        while not r.ok and "exceeded" in str(r.errors):
            time.sleep(0.02); r = m.execute_skill("RBDToken", token=tok, timeout=90)
            got = (r.output or "").strip().strip('"')
        if not r.ok or got != tok:
            with lock: errors.append(f"skill {user}: {r.status} {got} {r.errors}")

    def command(i):
        user, tok = users[i % len(users)]
        c = m.run_command(f"echo vb-{i}", token=tok)
        while c.returncode == 1 and "exceeded" in c.stderr:
            time.sleep(0.02); c = m.run_command(f"echo vb-{i}", token=tok)
        if c.returncode != 0 or c.stdout.strip() != f"vb-{i}":
            with lock: errors.append(f"command {user}: rc={c.returncode} out={c.stdout!r} err={c.stderr!r}")

    def upload(i):
        user, tok = users[i % len(users)]
        src = Path(tempfile.mkdtemp()) / "f.bin"; src.write_bytes(tok.encode())
        remote = f"/root/vbtest/{user}/f-{i}.bin" if user.startswith("cloud") else f"/home/Gent/.virtuoso-bridge/{user}/f-{i}.bin"
        u = m.upload_file(src, remote, token=tok)
        while u.returncode == 1 and "exceeded" in u.stderr:
            time.sleep(0.02); u = m.upload_file(src, remote, token=tok)
        if u.returncode != 0:
            with lock: errors.append(f"upload {user}: {u.stderr}")

    def download(i):
        user, tok = users[i % len(users)]
        remote = f"/root/vbtest/{user}/f-{i}.bin" if user.startswith("cloud") else f"/home/Gent/.virtuoso-bridge/{user}/f-{i}.bin"
        dst = Path(tempfile.mkdtemp()) / "g.bin"
        d = m.download_file(remote, dst, token=tok)
        while d.returncode == 1 and "exceeded" in d.stderr:
            time.sleep(0.02); d = m.download_file(remote, dst, token=tok)
        if d.returncode != 0 or dst.read_bytes() != tok.encode():
            with lock: errors.append(f"download {user}: rc={d.returncode} {d.stderr}")

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=64) as pool:
        list(pool.map(skill, range(len(users) * 2)))
    with ThreadPoolExecutor(max_workers=64) as pool:
        list(pool.map(command, range(len(users) * 2)))
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(upload, range(len(users))))
    with ThreadPoolExecutor(max_workers=32) as pool:
        list(pool.map(download, range(len(users))))
    print(f"users={len(users)} elapsed={time.time()-t0:.1f}s errors={len(errors)}")
    for err in errors[:20]:
        print("  ", err)
    for c in list(m._clients.values()):
        try: c.close()
        except Exception: pass
    return 0 if not errors else 1

if __name__ == "__main__":
    raise SystemExit(main())
