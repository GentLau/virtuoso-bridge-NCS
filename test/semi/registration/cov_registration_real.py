"""Real remote registration coverage TB (steps 1-4 only, no commit)."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from register import RegistrationFlow, RegistrationRequest
from common.registry import load_registry
from common.paths import registry_path, override_work_dir_for_tests  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--user", default="covreg")
    parser.add_argument("--token", default="cov-token")
    parser.add_argument("--port", type=int, default=65112)
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    out = Path(args.out) if args.out else Path(args.work_dir).resolve() / "cov-registration-evidence.json"

    wd = Path(args.work_dir).resolve()
    wd.mkdir(parents=True, exist_ok=True)
    override_work_dir_for_tests(wd)
    registry = load_registry(registry_path())
    flow = RegistrationFlow(registry)
    state = flow.apply(RegistrationRequest(
        mode="remote", user=args.user, token=args.token,
        ssh={"default": {"host": args.host, "user": args.ssh_user}},
        roles={"daemon": {"daemon_port": args.port}},
    ))
    evidence = {
        "ok": state.stage == "deployed" and not (wd / "registry.json").exists(),
        "token": args.token,
        "user": args.user,
        "work_dir": str(wd),
        "stage": state.stage,
        "step": state.step,
        "errors": state.errors,
        "warnings": state.warnings,
        "setup_path": state.setup_path,
        "registry_written": (wd / "registry.json").exists(),
        "reservation_file": (wd / "registry.reservation").exists(),
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False))
    return 0 if state.stage == "deployed" and not (wd / "registry.json").exists() else 2


if __name__ == "__main__":
    raise SystemExit(main())
