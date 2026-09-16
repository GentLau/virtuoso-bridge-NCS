"""Real remote coverage TB: Windows client -> WSL real Virtuoso daemon.

Run under coverage:
  coverage run --source=src --parallel-mode test/tb/cov_remote_real.py --work-dir ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from transport.middle import BusinessServer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token", default="vb-vb11")
    args = parser.parse_args()
    wd = Path(args.work_dir).resolve()
    server = BusinessServer(wd)
    temp = Path(tempfile.mkdtemp(prefix="vb-cov-remote-"))
    result = {"steps": []}
    try:
        skill = server.execute_skill("1+2", token=args.token)
        result["steps"].append({"name": "skill", "ok": skill.ok, "output": skill.output})
        if not skill.ok:
            return 2

        cmd = server.run_command("echo cov-ok", token=args.token)
        result["steps"].append({"name": "command", "ok": cmd.returncode == 0, "kind": cmd.kind})
        if cmd.returncode != 0:
            return 2

        src = temp / "in.bin"
        payload = b"coverage-real-remote" * 2048
        src.write_bytes(payload)
        up = server.upload_file(src, "cov/in.bin", token=args.token)
        down = server.download_file("cov/in.bin", temp / "out.bin", token=args.token)
        digest_ok = (
            up.returncode == 0
            and down.returncode == 0
            and hashlib.sha256((temp / "out.bin").read_bytes()).digest()
            == hashlib.sha256(payload).digest()
        )
        result["steps"].append({"name": "file", "ok": digest_ok, "up": up.kind, "down": down.kind})
        if not digest_ok:
            return 2

        gui = server.run_gui_command("echo cov-gui", token=args.token)
        spec = server.run_spectre_command("echo cov-spectre", token=args.token)
        result["steps"].append({"name": "gui", "ok": gui.returncode == 0, "kind": gui.kind})
        result["steps"].append({"name": "spectre", "ok": spec.returncode == 0, "kind": spec.kind})
        if gui.returncode != 0 or spec.returncode != 0:
            return 2
    finally:
        server.close()
    result["ok"] = all(step["ok"] for step in result["steps"])
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
