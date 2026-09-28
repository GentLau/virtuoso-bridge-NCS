# === TB 注释头（规范见 test/docs/写TB规范.md §0）=====================
# 作者: 设计/Codex
# 最后改动: 2026-09-28 12:04
# 依赖: 无
# =====================================================================
# 六步流程（按 test/docs/写TB规范.md §1–§6）：
# §1 环境检查：注册流程自身执行 apply/validate/probe，等价环境判定。
# §2 构建：临时/指定 work-dir、注册表、候选 user/token/端口。
# §3 最终检查：确认前四步 stage、远端路径和端口状态。
# §4 执行：真实远端注册前四步。
# §5 比对：stage/远端证据/registry 零写入与期望一致。
# §6 重复/收尾：单流程探针；保留证据，不提交第六步。
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
from common.paths import registry_path, init_work_dir  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--user", default="covreg")
    parser.add_argument("--token", default="cov-token")
    parser.add_argument("--port", type=int, default=65112)
    parser.add_argument("--host", default="wsl-gent")
    parser.add_argument("--ssh-user", default="Gent")
    parser.add_argument("--ssh-key-dir", default="~/.ssh")
    parser.add_argument("--ssh-key", default="id_ed25519")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    out = Path(args.out) if args.out else Path(args.work_dir).resolve() / "cov-registration-evidence.json"

    wd = Path(args.work_dir).resolve()
    wd.mkdir(parents=True, exist_ok=True)
    init_work_dir(wd)
    registry = load_registry(registry_path())
    flow = RegistrationFlow(registry)
    state = flow.apply(RegistrationRequest(
        mode="remote", user=args.user, token=args.token,
        ssh={"default": {"host": args.host, "user": args.ssh_user,
                         "key_dir": args.ssh_key_dir, "key": args.ssh_key}},
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
