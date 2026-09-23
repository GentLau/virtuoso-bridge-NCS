"""S4 规模档：100 个协议级 fake daemon + 100 用户并发，验证规模与 token 隔离。

每个 fake daemon（`support/fake_daemon_host.py`）对含 ``RBDToken`` 的请求会**回自己的
token** —— 因此"每个用户拿回自己的 token"就是串号检测；`1+1` 期望 "2" 作为数据面校验。

    python test/live/stress/scale_local_fake_tb.py \
        --work-dir test/artifacts/env/scenario-scale-100 --users 100 --ops 8 --workers 24 \
        --out test/artifacts/env/scenario-scale-100/evidence.json

退出码：出现失败/串号 → 1。
"""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "test" / "shared" / "fixtures"))

from _win import no_window  # noqa: E402
from common.paths import init_work_dir  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402


def _listening(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), 0.3):
            return True
    except OSError:
        return False


def _ensure_fleet(base_port: int, users: int, prefix: str) -> subprocess.Popen | None:
    if all(_listening(base_port + i) for i in range(users)):
        return None
    proc = subprocess.Popen(
        [sys.executable, str(ROOT / "test" / "shared" / "fixtures" / "fake_daemon_host.py"),
         "--base-port", str(base_port), "--count", str(users), "--token-prefix", prefix],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **no_window(),
    )
    deadline = time.time() + 60
    while time.time() < deadline:
        if all(_listening(base_port + i) for i in range(users)):
            return proc
        time.sleep(0.5)
    raise SystemExit(f"fake fleet did not come up on {base_port}..{base_port + users - 1}")


def _registry(work_dir: Path, users: int, base_port: int, prefix: str) -> dict:
    entries = {}
    for index in range(users):
        # 与 fake_daemon_host.py 的 token 规则保持一致：f"{prefix}-{i:02d}"
        user = f"{prefix}-{index:02d}"
        root = str(work_dir / "local-root" / user)
        Path(root).mkdir(parents=True, exist_ok=True)
        roles = {
            name: {"mode": None, "host": None, "user": None, "jump_host": None, "jump_user": None,
                   "proxy": None, "root": f"{root}/{name}", "expected_fingerprint": None,
                   "max_sessions": 10}
            for name in ("gui", "command", "file", "spectre")
        }
        roles["daemon"] = dict(roles["gui"], daemon_port=base_port + index,
                               local_port=base_port + index, python=None)
        entries[user] = {
            "token": user, "mode": {"default": "local"},
            "ssh": {"default": {"host": None, "user": None, "jump_host": None,
                                "jump_user": None, "proxy": None},
                    "backend": "paramiko", "control_master": "auto", "tool_override": {}},
            "root": {"default": None}, "roles": roles,
            "registered_at": int(time.time()),
        }
    return entries


def _one(server: BusinessServer, user: str, token: str, ops: int) -> list[str]:
    problems = []
    for _ in range(ops):
        got = server.execute_skill("RBDToken", timeout=30, token=token)
        value = (got.output or "").strip().strip('"')
        if not got.ok or value != token:
            problems.append(f"{user}: token probe got {value!r} (want {token!r})")
            continue
        two = server.execute_skill("1+1", timeout=30, token=token)
        if not two.ok or (two.output or "").strip() != "2":
            problems.append(f"{user}: 1+1 got {(two.output or '').strip()!r} ok={two.ok}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--users", type=int, default=100)
    parser.add_argument("--ops", type=int, default=8, help="每用户轮数（每轮 2 次调用）")
    parser.add_argument("--workers", type=int, default=24)
    parser.add_argument("--base-port", type=int, default=6801)
    parser.add_argument("--token-prefix", default="cloud")
    parser.add_argument("--out", default="")
    args = parser.parse_args()

    work_dir = Path(args.work_dir)
    work_dir.mkdir(parents=True, exist_ok=True)
    fleet = _ensure_fleet(args.base_port, args.users, args.token_prefix)
    entries = _registry(work_dir, args.users, args.base_port, args.token_prefix)
    (work_dir / "registry.json").write_text(
        json.dumps(entries, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    init_work_dir(str(work_dir))
    from common.registry import Registry

    Registry(work_dir / "registry.json").load()      # 生产校验
    server = BusinessServer()

    started = time.time()
    failures: list[str] = []
    users = list(entries)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(_one, server, user, entries[user]["token"], args.ops)
                   for user in users]
        for future in futures:
            failures.extend(future.result())
    elapsed = round(time.time() - started, 2)

    total_calls = len(users) * args.ops * 2
    payload = {
        "ok": not failures,
        "users": len(users), "ops_per_user": args.ops, "workers": args.workers,
        "total_calls": total_calls, "failed": len(failures),
        "elapsed_s": elapsed, "calls_per_s": round(total_calls / elapsed, 1) if elapsed else None,
        "base_port": args.base_port,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "failures": failures[:20],
    }
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    if fleet is not None:
        fleet.terminate()
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
