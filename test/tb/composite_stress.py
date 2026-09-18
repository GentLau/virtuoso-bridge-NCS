"""Composite HTTPServer business simulation for two client topologies.

Topologies
----------
``--mode win-mixed``  Windows client: real users on wsl-gent (Virtuoso + real
                     daemon) mixed with fake users on the vps (fake daemon).
``--mode wsl-mixed``  wsl-gent client: local-mode users running Virtuoso on the
                     same host mixed with remote fake users on the vps.

All requests originate from this process and are sent over HTTP to a
*separate* ``server.stress_server`` process, so the business server and the
clients are isolated exactly like a real deployment.  Each task is dispatched
onto a random user, a random mix of the five interfaces (skill / command /
file upload / file download / composite chain), with a random delay to shuffle
the interleaving.  Retries only happen for "rejected" (capacity) answers and
transport-level failures, are bounded by ``--max-retries``, and are counted.

Output is a single JSON object with per-op counters, latency percentiles,
retry counts and per-user breakdown so the number can be quoted in a report.
"""
from __future__ import annotations
import argparse, base64, hashlib, json, os, random, socket, statistics, subprocess, sys, tempfile, threading, time, urllib.error, urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_src = Path(__file__).resolve().parents[2] / "src"
if _src.is_dir():
    sys.path.insert(0, str(_src))

from common.registry import UserEntry, load_registry
from register.probe import allocate_local_port
from common.paths import override_work_dir_for_tests, registry_path

SPECTRE = "/opt/eda/cadence/SPECTRE241/bin/spectre"
WSL_ROOT = "/home/Gent/.virtuoso-bridge"


def free_port():
    s = socket.socket(); s.bind(("127.0.0.1", 0)); port = s.getsockname()[1]; s.close(); return port


def post(base, path, payload, timeout=90):
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.status, json.loads(resp.read().decode())


def wait_http(base, timeout=20):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.5).close()
            return True
        except OSError:
            time.sleep(0.25)
    return False


def start_local(user, setup, display):
    proj = Path(f"/home/Gent/project/{user}")
    proj.mkdir(parents=True, exist_ok=True)
    # a previous run may have crashed and left the log lock behind
    (proj / "CDS.log.cdslck").unlink(missing_ok=True)
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


def register_fake_vps(reg, user, token, port, local_port, thread_pool=8, channel_budget=2):
    """Hand-written registry entry for a vps fake daemon (no Virtuoso involved)."""
    e = UserEntry(token=token, mode="remote")
    e.roles.daemon.host = "vps"; e.roles.daemon.daemon_port = port; e.roles.daemon.local_port = local_port
    e.roles.command.host = "vps"; e.roles.command.user = "root"; e.roles.file.host = "vps"
    e.roles.daemon.root = "/root/vbtest"
    e.roles.file.root = "~/.virtuoso-bridge/%s/file" % user
    e.roles.daemon.expected_user = "root"
    e.runtime.thread_pool_size = thread_pool   # weak vps: keep load sane
    e.runtime.channel_budget = channel_budget
    reg.register(user, e)


def register_real_wsl(reg, user, token, port, local_port):
    e = UserEntry(token=token, mode="remote")
    e.roles.daemon.host = "wsl-gent"; e.roles.daemon.daemon_port = port; e.roles.daemon.local_port = local_port
    e.roles.command.host = "wsl-gent"; e.roles.command.user = "Gent"; e.roles.file.host = "wsl-gent"
    e.roles.daemon.root = f"{WSL_ROOT}/{user}"
    e.roles.daemon.expected_user = "Gent"
    reg.register(user, e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["win-mixed", "wsl-mixed"], required=True)
    ap.add_argument("--ops", type=int, default=80)
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--max-retries", type=int, default=20,
                    help="retry budget for capacity rejections / 5xx answers")
    ap.add_argument("--max-timeout-retries", type=int, default=2,
                    help="retry budget for client-side request timeouts (st=-1)")
    ap.add_argument("--task-deadline", type=float, default=300.0,
                    help="give up on one task after this many seconds")
    ap.add_argument("--request-timeout", type=float, default=90.0)
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--trace-server-threads", type=float, default=0.0,
                    help="dump every server thread stack every N seconds to the server log")
    ap.add_argument("--server-log", default=None,
                    help="file that receives the stress server's stdout/stderr")
    args = ap.parse_args()

    wd = override_work_dir_for_tests(Path(tempfile.mkdtemp(prefix="vb-comp-")))
    reg = load_registry(registry_path())
    users = []
    reserved = set()
    kinds = {}

    if args.mode == "win-mixed":
        for n in range(1, 7):
            user, token, port = f"vb{n:02d}", f"vb-vb{n:02d}", 65100 + n
            lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
            register_real_wsl(reg, user, token, port, lp)
            users.append((user, token, "real"))
        for n in range(4):
            user, token, port = f"cloud{n:02d}", f"cloud-{n:02d}", 6701 + n
            lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
            register_fake_vps(reg, user, token, port, lp)
            users.append((user, token, "fake"))
    else:
        # wsl client: 4 local real users + 4 vps fake users
        from register import RegistrationFlow, RegistrationRequest
        for n in range(4):
            user, token, port = f"lc{n:02d}", f"l-lc{n:02d}", 65411 + n
            flow = RegistrationFlow(reg)
            state = flow.apply(RegistrationRequest(
                mode="local", user=user, token=token,
                roles={"daemon": {"daemon_port": port},
                      "spectre": {"bin": SPECTRE}},
            ))
            if state.stage != "deployed":
                raise RuntimeError(state.errors)
            start_local(user, state.setup_path, os.environ.get("VB_DISPLAY", "localhost:10.0"))
            if not wait_port(port):
                raise RuntimeError(f"{user} daemon not ready")
            state = flow.verify()
            if state.stage != "verified":
                raise RuntimeError(state.errors)
            state = flow.commit()
            if state.stage != "committed":
                raise RuntimeError(state.errors)
            users.append((user, token, "local"))
        for n in range(4):
            user, token, port = f"cloud{n:02d}", f"cloud-{n:02d}", 6701 + n
            lp = allocate_local_port(reserved=reserved, tries=200); reserved.add(lp)
            register_fake_vps(reg, user, token, port, lp)
            users.append((user, token, "fake"))

    for user, token, kind in users:
        kinds[user] = kind

    server_port = free_port()
    base = f"http://127.0.0.1:{server_port}"
    env = dict(os.environ)
    env["PYTHONPATH"] = str(_src)
    server_log_path = Path(args.server_log) if args.server_log else (wd / "server.log")
    server_log = open(server_log_path, "w", encoding="utf-8")
    if args.trace_server_threads > 0:
        # run the server behind a wrapper that periodically dumps every thread
        # stack: the only way to see where a wedged handler is stuck on Windows
        server_cmd = [
            sys.executable, "-c",
            "import faulthandler, runpy, sys;"
            f"faulthandler.dump_traceback_later({args.trace_server_threads}, repeat=True);"
            "sys.argv = ['server.stress_server', '--port', " + repr(str(server_port)) +
            ", '--work-dir', " + repr(str(wd)) + "];"
            "runpy.run_module('server.stress_server', run_name='__main__')",
        ]
    else:
        server_cmd = [sys.executable, "-m", "server.stress_server",
                      "--port", str(server_port), "--work-dir", str(wd)]
    server_proc = subprocess.Popen(
        server_cmd, stdout=server_log, stderr=subprocess.STDOUT, text=True, env=env,
    )
    if not wait_http(base, timeout=25):
        print(json.dumps({"error": "stress server did not start", "log_path": str(server_log_path)}))
        server_proc.kill()
        return 2

    rng = random.Random(args.seed)
    tasks = []
    for i in range(args.ops):
        user, tok, kind = users[i % len(users)]
        choice = rng.random()
        delay = rng.randint(0, 40)
        if choice < 0.35:
            op = "skill"
        elif choice < 0.55:
            op = "composite"
        elif choice < 0.75:
            op = "command"
        elif choice < 0.90:
            op = "upload"
        else:
            op = "download"
        tasks.append((op, user, tok, kind, i, delay))
    rng.shuffle(tasks)

    counters = {}
    per_user = {u: {"skill": 0, "command": 0, "upload": 0, "download": 0, "composite": 0,
                    "retries": 0, "rejections": 0, "errors": 0, "kind": kinds[u]} for u, _, _ in users}
    latencies = []
    rejections = 0
    retries = 0
    errors = []
    done = 0
    lock = threading.Lock()
    started_at = time.time()

    def trace(msg):
        if args.verbose:
            print(f"[{time.time() - started_at:8.1f}s] {msg}", file=sys.stderr, flush=True)

    def one(task):
        nonlocal retries, done, rejections
        op, user, tok, kind, seq, delay = task
        with lock:
            counters[op] = counters.get(op, 0) + 1
            per_user[user][op] += 1
        started = time.time()
        attempt = 0
        trace(f"start  {op:9s} {user} seq={seq}")
        while True:
            attempt += 1
            attempt_started = time.time()
            try:
                if op == "skill":
                    st, body = post(base, "/api/skill", {"token": tok, "skill": "RBDToken"},
                                    timeout=args.request_timeout)
                elif op == "command":
                    st, body = post(base, "/api/command",
                                    {"token": tok, "cmd": f"echo vb-{seq}; sleep {delay/1000.0:.3f}"},
                                    timeout=args.request_timeout)
                elif op == "composite":
                    # upload + skill + command + download: four stages, each
                    # with its own middle-layer budget, so allow 4x the client
                    # timeout before declaring the chain stuck
                    st, body = post(base, "/api/composite",
                                    {"token": tok, "seq": str(seq), "delay_ms": delay},
                                    timeout=args.request_timeout * 4)
                elif op == "upload":
                    data = (tok + str(seq)).encode() * 512
                    remote = f"comp-{user}-{seq}.bin"
                    st, body = post(base, "/api/upload",
                                    {"token": tok, "remote_path": remote,
                                     "content_b64": base64.b64encode(data).decode()},
                                    timeout=args.request_timeout)
                else:  # download: write a known payload, read it back, compare digest
                    payload = (tok + str(seq)).encode() * 512
                    remote = f"dl-{user}-{seq}.bin"
                    st, body = post(base, "/api/upload",
                                    {"token": tok, "remote_path": remote,
                                     "content_b64": base64.b64encode(payload).decode()},
                                    timeout=args.request_timeout)
                    if st == 200 and body.get("returncode") == 0:
                        st, body = post(base, "/api/download", {"token": tok, "remote_path": remote},
                                        timeout=args.request_timeout)
                        body = dict(body)
                        body["sha_ok"] = body.get("sha256") == hashlib.sha256(payload).hexdigest()
            except urllib.error.HTTPError as exc:
                body = {}
                try:
                    body = json.loads(exc.read().decode())
                except Exception:
                    pass
                st = exc.code
            except Exception as exc:
                st, body = -1, {"error": str(exc)}
            trace(
                f"reply  {op:9s} {user} seq={seq} attempt={attempt} "
                f"status={st} dt={time.time() - attempt_started:.1f}s"
            )

            body_text = json.dumps(body)
            capacity = (
                "exceeded" in body_text
                or "rejected" in body_text
                or body.get("rejected") is True
            )
            if st == 200 and capacity:
                # Capacity rejection is an expected stress outcome: count it
                # and retry (the harness must reach the rejection threshold and
                # still show that every accepted call completed correctly).
                with lock:
                    rejections += 1
                    per_user[user]["rejections"] += 1
                retryable = True
                retry_ok = attempt <= args.max_retries and (time.time() - started) < args.task_deadline
                trace(f"reject {op:9s} {user} seq={seq} attempt={attempt} {body_text[:100]}")
                if retry_ok:
                    with lock:
                        retries += 1
                        per_user[user]["retries"] += 1
                    time.sleep(min(0.05 * attempt, 0.5))
                    continue
                with lock:
                    errors.append(f"{op} {user} {seq}: capacity rejected after {attempt} attempts")
                    per_user[user]["errors"] += 1
                break

            if st == 200:
                problem = None
                if op == "skill" and (not body.get("ok") or (body.get("output") or "").strip().strip('"') != tok):
                    problem = f"skill {user} {seq}: {body}"
                if op == "command" and body.get("returncode") != 0:
                    problem = f"command {user} {seq}: {body}"
                if op == "composite" and not body.get("ok"):
                    problem = f"composite {user} {seq}: {body}"
                if op == "upload" and body.get("returncode") != 0:
                    problem = f"upload {user} {seq}: {body}"
                if op == "download" and (body.get("returncode") != 0 or body.get("sha_ok") is False):
                    problem = f"download {user} {seq}: {body}"
                if problem:
                    with lock:
                        errors.append(problem)
                        per_user[user]["errors"] += 1
                    break
                with lock:
                    latencies.append(time.time() - started)
                    done += 1
                    if args.verbose and done % 10 == 0:
                        trace(f"---- {done}/{len(tasks)} tasks done, in-flight={len(tasks) - done}")
                break

            transport_5xx = st in (500, 503, 504)
            timed_out = st == -1
            retryable = capacity or transport_5xx or timed_out
            if timed_out:
                retry_ok = attempt <= args.max_timeout_retries
            else:
                retry_ok = attempt <= args.max_retries
            retry_ok = retry_ok and (time.time() - started) < args.task_deadline
            if retryable and retry_ok:
                with lock:
                    retries += 1
                    per_user[user]["retries"] += 1
                trace(f"retry  {op:9s} {user} seq={seq} attempt={attempt} status={st} {str(body)[:120]}")
                time.sleep(min(0.05 * attempt, 0.5))
                continue
            with lock:
                errors.append(f"{op} {user} {seq}: status={st} attempt={attempt} {body}")
                per_user[user]["errors"] += 1
            break

    t0 = time.time()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(one, tasks))
    elapsed = time.time() - t0

    def pct(values, q):
        if not values:
            return None
        ordered = sorted(values)
        idx = min(len(ordered) - 1, int(round(q * (len(ordered) - 1))))
        return round(ordered[idx], 2)

    summary = {
        "mode": args.mode,
        "client": "windows" if args.mode == "win-mixed" else "wsl-gent",
        "users": len(users),
        "users_by_kind": {k: sum(1 for _, _, kk in users if kk == k) for k in ("real", "local", "fake")},
        "ops": counters,
        "retries": retries,
        "capacity_rejections": rejections,
        "errors": len(errors),
        "elapsed": round(elapsed, 1),
        "latency_s": {"p50": pct(latencies, 0.50), "p95": pct(latencies, 0.95),
                      "max": round(max(latencies), 2) if latencies else None},
        "per_user": per_user,
        "seed": args.seed,
        "server_log": str(server_log_path),
        "samples": errors[:8],
    }
    print(json.dumps(summary, ensure_ascii=False))
    server_log.close()
    # graceful shutdown first: it releases tunnels/shells (spec 资源盘点)
    try:
        post(base, "/api/shutdown", {}, timeout=10)
    except Exception:  # noqa: BLE001 - best effort
        pass
    server_proc.terminate()
    try:
        server_proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server_proc.kill()
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
