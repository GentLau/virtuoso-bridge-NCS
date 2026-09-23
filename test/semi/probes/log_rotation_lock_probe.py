"""Probe: per-process command logs rotate even if another process holds the old file.

The control face and business face share one work directory.  Logging now
uses ``log/commands.<pid>.log`` per process, so rotation never renames a file
held by another process.  This probe keeps the legacy shared
``log/commands.log`` open in a foreign process, then verifies that this
process's own rotating log still rolls to ``commands.<pid>.log.1``.

Run:  python test/semi/probes/log_rotation_lock_probe.py
Exit 0 = process-local rotation survived the foreign holder; 1 = failed.
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    work_dir = Path(tempfile.mkdtemp(prefix="vb-logrotate-"))
    log_dir = work_dir / "log"
    log_dir.mkdir(parents=True, exist_ok=True)
    shared_legacy = log_dir / "commands.log"
    shared_legacy.write_text("legacy\n", encoding="utf-8")

    holder = subprocess.Popen(
        [sys.executable, "-c",
         "import sys,time;"
         f"fh=open(r'{shared_legacy}','a',encoding='utf-8');"
         "fh.write('holder\\n'); fh.flush(); time.sleep(30)"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.0)  # let the foreign process actually hold commands.log
        process_log = log_dir / f"commands.{os.getpid()}.log"
        process_log.write_bytes(b"x" * (5 * 1024 * 1024 + 100))

        from common.ssh import _setup_command_log

        _setup_command_log(shared_legacy)
        logging.getLogger("probe").info("trigger rotation %s", "y" * 100)
        time.sleep(0.2)
    finally:
        holder.terminate()
        try:
            holder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            holder.kill()

    rotated = sorted(p.name for p in log_dir.glob("commands.*"))
    ok = f"{process_log.name}.1" in rotated
    print(f"work_dir   : {work_dir}")
    print(f"files      : {rotated}")
    print("result:", "PASS (process-local rotation)" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
