"""Real remote registration coverage TB (steps 1-4 only, no commit)."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from transport.register import RegistrationFlow, RegistrationRequest
from transport.registry import load_registry
from transport.runtime_paths import set_working_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--user", default="covreg")
    parser.add_argument("--token", default="cov-token")
    parser.add_argument("--port", type=int, default=65112)
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    args = parser.parse_args()

    wd = Path(args.work_dir).resolve()
    wd.mkdir(parents=True, exist_ok=True)
    set_working_dir(wd)
    registry = load_registry()
    flow = RegistrationFlow(registry)
    state = flow.apply(RegistrationRequest(
        mode="remote", user=args.user, token=args.token,
        ssh={"default": {"host": args.host, "user": args.ssh_user}},
        roles={"daemon": {"daemon_port": args.port}},
    ))
    print(json.dumps({
        "stage": state.stage,
        "step": state.step,
        "errors": state.errors,
        "warnings": state.warnings,
        "setup_path": state.setup_path,
        "registry_written": (wd / "registry.json").exists(),
        "reservation_file": (wd / "registry.reservation").exists(),
    }, ensure_ascii=False))
    return 0 if state.stage == "deployed" and not (wd / "registry.json").exists() else 2


if __name__ == "__main__":
    raise SystemExit(main())
