"""Real remote coverage TB: Windows client -> WSL real Virtuoso daemon.

Run under coverage:
  coverage run --source=src --parallel-mode test/live/transport/cov_remote_real.py --work-dir ...
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import uuid
from pathlib import Path

SRC = Path(__file__).resolve().parents[3] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from transport.middle import BusinessServer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--token", default="vb-vb11")
    parser.add_argument("--out", default="")
    args = parser.parse_args()
    wd = Path(args.work_dir).resolve()
    out = Path(args.out) if args.out else wd / "cov-remote-real-evidence.json"
    server = BusinessServer(wd)
    temp = tempfile.TemporaryDirectory(prefix="vb-cov-remote-")
    result = {"steps": []}
    exit_code = 0
    try:
        skill_marker = f"cov-skill-{uuid.uuid4().hex[:10]}"
        skill = server.execute_skill(f'strcat("{skill_marker}")', token=args.token)
        result["steps"].append({"name": "skill",
                                "ok": skill.ok and skill_marker in (skill.output or ""),
                                "output": skill.output})
        if not (skill.ok and skill_marker in (skill.output or "")):
            exit_code = 2
            return 2

        cmd_marker = f"cov-cmd-{uuid.uuid4().hex[:10]}"
        cmd = server.run_command(f"echo {cmd_marker}", token=args.token)
        cmd_ok = cmd.returncode == 0 and cmd_marker in (cmd.stdout or "")
        result["steps"].append({"name": "command", "ok": cmd_ok, "kind": cmd.kind,
                                "stdout": (cmd.stdout or "")[:80]})
        if not cmd_ok:
            exit_code = 2
            return 2

        temp_path = Path(temp.name)
        src = temp_path / "in.bin"
        payload = b"coverage-real-remote" * 2048
        src.write_bytes(payload)
        up = server.upload_file(src, "cov/in.bin", token=args.token)
        down = server.download_file("cov/in.bin", temp_path / "out.bin", token=args.token)
        digest_ok = (
            up.returncode == 0
            and down.returncode == 0
            and hashlib.sha256((temp_path / "out.bin").read_bytes()).digest()
            == hashlib.sha256(payload).digest()
        )
        result["steps"].append({"name": "file", "ok": digest_ok, "up": up.kind, "down": down.kind})
        if not digest_ok:
            exit_code = 2
            return 2

        gui_marker = f"cov-gui-{uuid.uuid4().hex[:10]}"
        spec_marker = f"cov-spectre-{uuid.uuid4().hex[:10]}"
        gui = server.run_gui_command(f"echo {gui_marker}", token=args.token)
        spec = server.run_spectre_command(f"echo {spec_marker}", token=args.token)
        gui_ok = gui.returncode == 0 and gui_marker in (gui.stdout or "")
        spec_ok = spec.returncode == 0 and spec_marker in (spec.stdout or "")
        result["steps"].append({"name": "gui", "ok": gui_ok, "kind": gui.kind,
                                "stdout": (gui.stdout or "")[:80]})
        result["steps"].append({"name": "spectre", "ok": spec_ok, "kind": spec.kind,
                                "stdout": (spec.stdout or "")[:80]})
        if not (gui_ok and spec_ok):
            exit_code = 2
            return 2
    finally:
        server.close()
        temp.cleanup()
        result["ok"] = all(step["ok"] for step in result["steps"]) and not exit_code
        result["token"] = args.token
        result["work_dir"] = str(wd)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                       encoding="utf-8")
        # Print from the finally block: the early ``return 2`` paths used to skip
        # the print entirely, so a red run produced no stdout at all and the only
        # record was the evidence file.  A failing acceptance step must say why
        # on the console.
        print(json.dumps(result, ensure_ascii=False), flush=True)
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
