"""S3 多用户路由/隔离 TB（真机 + fake 混合注册表）。

注册表由 ``--work-dir`` 提供（每个用户已配好 token / daemon 端口 / root），
本 TB 只做两件事：

1. **逐用户串行**：``execute_skill("RBDToken")`` 的返回值必须等于该用户自己的
   token —— 任何"串号"（拿到别人的 daemon/响应）立即失败；
2. **混合并发**：N 轮并发请求轮转打在所有用户上，统计 ok / failed / misrouted。

    python test/live/stress/multi_user_routing_tb.py \
        --work-dir test/artifacts/env/scenario-multi-user \
        --out test/artifacts/env/scenario-multi-user/evidence.json \
        --rounds 4

退出码：有 failed 或 misrouted → 1。
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from common.paths import override_work_dir_for_tests  # noqa: E402
from common.registry import load_registry  # noqa: E402
from common.paths import registry_path  # noqa: E402
from transport.middle import BusinessServer  # noqa: E402


def _clean(value: str | None) -> str:
    return (value or "").strip().strip('"')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--out", default="")
    parser.add_argument("--rounds", type=int, default=4, help="并发轮数（每轮打所有用户）")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    work_dir = Path(args.work_dir).resolve()
    work_dir.mkdir(parents=True, exist_ok=True)
    override_work_dir_for_tests(work_dir)
    registry = load_registry(registry_path())
    users = sorted(registry.users())
    tokens = {name: registry.get(name).token for name in users}
    server = BusinessServer(work_dir)

    evidence: dict = {"work_dir": str(work_dir), "users": tokens, "serial": [], "concurrent": {}}
    failed = 0
    misrouted = 0

    for name, token in tokens.items():
        result = server.execute_skill("RBDToken", timeout=args.timeout, token=token)
        got = _clean(result.output)
        ok = bool(result.ok) and got == token
        if not ok:
            failed += 1
            if result.ok and got != token:
                misrouted += 1
        evidence["serial"].append({
            "user": name, "token": token, "ok": ok, "returned": got,
            "status": str(result.status), "errors": list(result.errors or []),
        })

    lock = threading.Lock()
    stats = {"ok": 0, "failed": 0, "misrouted": 0}
    details: list[dict] = []

    def one(index: int) -> None:
        name = users[index % len(users)]
        token = tokens[name]
        try:
            result = server.execute_skill("RBDToken", timeout=args.timeout, token=token)
            got = _clean(result.output)
            if not result.ok:
                key = "failed"
            elif got != token:
                key = "misrouted"
            else:
                key = "ok"
        except Exception as exc:  # noqa: BLE001 - 任何异常都算失败并留证
            key, got = "failed", f"{type(exc).__name__}: {exc}"
        with lock:
            stats[key] += 1
            if key != "ok":
                details.append({"user": name, "token": token, "kind": key, "returned": got})

    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=len(users)) as pool:
        for _round in range(args.rounds):
            list(pool.map(one, range(len(users))))
    elapsed = time.monotonic() - started

    evidence["concurrent"] = {
        "rounds": args.rounds, "users_per_round": len(users),
        "elapsed_s": round(elapsed, 3), **stats, "failures": details[:20],
    }
    evidence["ok"] = failed == 0 and misrouted == 0 and stats["failed"] == 0 and stats["misrouted"] == 0
    evidence["failed"] = failed + stats["failed"]
    evidence["misrouted"] = misrouted + stats["misrouted"]

    text = json.dumps(evidence, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0 if evidence["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
