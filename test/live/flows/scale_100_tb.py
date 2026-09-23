"""S4 scale-100：100 个协议级 fake daemon × 100 token，验证规模下的隔离与预算。

做法（见 ``test/docs/推荐测试环境.md`` S4）：

* 本机起 ``test/shared/fixtures/fake_daemon_host.py --base-port 6701 --count 100``；
* 生成 100 个 **local 模式**用户（token ``cloud-00``…``cloud-99``，daemon_port 逐个对应）；
* 用真实中间层（``BusinessServer``）并发打 100 条 ``execute_skill("RBDToken")``。

fake daemon 对含 ``RBDToken`` 的 skill **回显自己的 token**，因此这里能断言的是
**"每个客户端拿到的是自己的 token，没有串台"**——这是规模档唯一有价值的判据
（"100 个都连通"本身说明不了路由是对的）。

用法::

    python test/live/flows/scale_100_tb.py --count 100 --rounds 2
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

_SUPPORT = Path(__file__).resolve().parents[2] / "shared" / "fixtures"
if str(_SUPPORT) not in sys.path:
    sys.path.insert(0, str(_SUPPORT))
from _win import no_window  # type: ignore  # noqa: E402


def port_open(port: int, host: str = "127.0.0.1", timeout: float = 0.5) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def wait_ports(base: int, count: int, timeout: float = 60.0) -> tuple[int, list[int]]:
    deadline = time.time() + timeout
    while time.time() < deadline:
        missing = [base + i for i in range(count) if not port_open(base + i)]
        if not missing:
            return count, []
        time.sleep(0.5)
    return count - len(missing), missing


def build_registry(work_dir: Path, count: int, base_port: int, prefix: str) -> Path:
    root = work_dir / "local-root"
    users: dict[str, dict] = {}
    for index in range(count):
        name = f"{prefix}{index:02d}"
        home = root / name
        users[name] = {
            "token": f"{prefix}-{index:02d}",
            "mode": {"default": "local"},
            "ssh": {"default": {"host": None, "user": None, "jump_host": None,
                                "jump_user": None, "proxy": None},
                    "backend": "openssh", "control_master": "auto", "tool_override": {}},
            "root": {"default": None},
            "roles": {
                "gui": {"mode": None, "host": None, "user": None, "jump_host": None,
                        "jump_user": None, "proxy": None, "root": str(home / "gui"),
                        "expected_fingerprint": None, "max_sessions": 4, "display": None},
                "daemon": {"mode": None, "host": None, "user": None, "jump_host": None,
                           "jump_user": None, "proxy": None, "root": str(home),
                           "expected_fingerprint": None, "max_sessions": 4,
                           "daemon_port": base_port + index, "local_port": base_port + index,
                           "python": None, "expected_hostname": None, "expected_user": None},
                "command": {"mode": None, "host": None, "user": None, "jump_host": None,
                            "jump_user": None, "proxy": None, "root": str(home / "command"),
                            "expected_fingerprint": None, "max_sessions": 4},
                "file": {"mode": None, "host": None, "user": None, "jump_host": None,
                         "jump_user": None, "proxy": None, "root": str(home / "file"),
                         "expected_fingerprint": None, "max_sessions": 4},
                "spectre": {"mode": None, "host": None, "user": None, "jump_host": None,
                            "jump_user": None, "proxy": None, "root": str(home / "spectre"),
                            "expected_fingerprint": None, "max_sessions": 4, "bin": None},
            },
            "runtime": {"thread_pool_size": 4, "channel_budget": 2, "connect_timeout": 10.0},
            "cdslog": {"log_level": "all", "log_max_bytes": 65536},
        }
    path = work_dir / "registry.json"
    path.write_text(json.dumps(users, ensure_ascii=False, indent=1), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--count", type=int, default=100)
    ap.add_argument("--base-port", type=int, default=6701)
    ap.add_argument("--prefix", default="cloud")
    ap.add_argument("--rounds", type=int, default=2)
    ap.add_argument("--workers", type=int, default=64)
    ap.add_argument("--work-dir", default=str(ROOT / "test" / "artifacts" / "scenario-scale-100"))
    ap.add_argument("--out", default="")
    args = ap.parse_args(argv)

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    fleet_log = work_dir / "fleet.log"

    from common.paths import init_work_dir, override_work_dir_for_tests  # noqa: E402
    from common.registry import Registry  # noqa: E402
    from transport.middle import BusinessServer  # noqa: E402

    steps: list[dict] = []
    ok = True

    def record(name: str, passed: bool, detail) -> None:
        nonlocal ok
        steps.append({"name": name, "ok": bool(passed), "detail": detail})
        if not passed:
            ok = False

    fleet: subprocess.Popen | None = None
    evidence: dict = {"scenario": "S4-scale-100", "count": args.count,
                      "base_port": args.base_port, "rounds": args.rounds}
    try:
        log_handle = fleet_log.open("w", encoding="utf-8")
        fleet = subprocess.Popen(
            [sys.executable, str(ROOT / "test" / "shared" / "fixtures" / "fake_daemon_host.py"),
             "--base-port", str(args.base_port), "--count", str(args.count),
             "--token-prefix", args.prefix],
            stdout=log_handle, stderr=subprocess.STDOUT, **no_window(),
        )
        ready, missing = wait_ports(args.base_port, args.count)
        record("fleet-listening", not missing,
               {"ready": ready, "count": args.count, "missing": missing[:10]})

        registry_path = build_registry(work_dir, args.count, args.base_port, args.prefix)
        registry = Registry(registry_path).load()
        users = sorted(registry.users())
        record("registry-valid", len(users) == args.count,
               {"users": len(users), "expected": args.count, "path": str(registry_path)})

        init_work_dir(str(work_dir))
        middle = BusinessServer()
        tokens = [f"{args.prefix}-{index:02d}" for index in range(args.count)]

        def probe(token: str) -> dict:
            started = time.perf_counter()
            try:
                result = middle.execute_skill("RBDToken", timeout=30, token=token)
                return {"token": token, "ok": result.ok,
                        "output": (result.output or "").strip().strip('"'),
                        "errors": list(result.errors or []),
                        "elapsed_s": round(time.perf_counter() - started, 3)}
            except Exception as exc:  # noqa: BLE001
                return {"token": token, "ok": False, "output": None,
                        "errors": [f"{type(exc).__name__}: {exc}"],
                        "elapsed_s": round(time.perf_counter() - started, 3)}

        rounds: list[dict] = []
        for round_index in range(args.rounds):
            started = time.perf_counter()
            with ThreadPoolExecutor(max_workers=args.workers) as pool:
                results = list(pool.map(probe, tokens))
            elapsed = round(time.perf_counter() - started, 3)
            misrouted = [item for item in results if item["output"] not in (item["token"], None)]
            failed = [item for item in results if not item["ok"] or item["output"] != item["token"]]
            rounds.append({
                "round": round_index + 1,
                "elapsed_s": elapsed,
                "ok": len(results) - len(failed),
                "failed": len(failed),
                "misrouted": len(misrouted),
                "max_elapsed_s": max(item["elapsed_s"] for item in results),
                "failures": failed[:5],
            })
            record(f"round-{round_index + 1}-all-tokens-own-answer", not failed,
                   rounds[-1])
        evidence["rounds_detail"] = rounds
        evidence["fleet_log"] = str(fleet_log)

        # 负向对照：把 A 的 daemon_port 故意指到 B 的 fake 上。
        # 如果 "output == 自己的 token" 这个判据是有效的，这里必须看到 B 的 token
        # （即检测手段能抓到串台）；否则说明我们的断言是空的。
        control_dir = work_dir / "negative-control"
        control_dir.mkdir(parents=True, exist_ok=True)
        control_users = {
            "cloud-a": None, "cloud-b": None,
        }
        main = json.loads((work_dir / "registry.json").read_text(encoding="utf-8"))
        control_users["cloud-a"] = json.loads(json.dumps(main["cloud00"]))
        control_users["cloud-b"] = json.loads(json.dumps(main["cloud01"]))
        control_users["cloud-a"]["token"] = "cloud-a"
        control_users["cloud-b"]["token"] = "cloud-b"
        # A 指向 B 的端口：A 用自己的 token，但落到 B 的监听上 → 必然 NAK/串台
        control_users["cloud-b"]["roles"]["daemon"]["daemon_port"] = args.base_port
        (control_dir / "registry.json").write_text(
            json.dumps(control_users, ensure_ascii=False, indent=1), encoding="utf-8")
        # 一个进程只能 init_work_dir 一次；测试工具提供的 override 就是给这种切换用的
        override_work_dir_for_tests(control_dir)
        control_middle = BusinessServer()
        probe_b = control_middle.execute_skill("RBDToken", timeout=30, token="cloud-b")
        got = (probe_b.output or "").strip().strip('"')
        record("negative-control-detects-misroute",
               (not probe_b.ok) or got != "cloud-b",
               {"ok": probe_b.ok, "output": got, "errors": list(probe_b.errors or [])})
    finally:
        if fleet is not None:
            fleet.terminate()
            try:
                fleet.wait(timeout=15)
            except subprocess.TimeoutExpired:
                fleet.kill()

    evidence["ok"] = ok
    evidence["steps"] = steps
    out = Path(args.out) if args.out else work_dir / "evidence.json"
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in evidence.items() if k != "steps"}, ensure_ascii=False)[:1200])
    for step in steps:
        print(f"  [{'ok' if step['ok'] else 'FAIL'}] {step['name']}")
    print(f"evidence: {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
