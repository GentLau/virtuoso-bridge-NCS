"""Windows process-lifetime contract for supervised children."""

from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.process_lifetime import ProcessJob


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(0x00100000, False, pid)
    if not handle:
        return False
    code = ctypes.c_ulong()
    ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
    kernel32.CloseHandle(handle)
    return bool(ok) and code.value == 259  # STILL_ACTIVE


@unittest.skipUnless(os.name == "nt", "Windows Job Object contract")
class TestProcessJob(unittest.TestCase):
    def test_close_kills_parent_and_descendant(self):
        with tempfile.TemporaryDirectory() as td:
            pidfile = Path(td) / "child.pid"
            parent_code = (
                "import subprocess, sys, time;"
                "p=subprocess.Popen([sys.executable, '-c', sys.argv[2]]);"
                "open(sys.argv[1], 'w').write(str(p.pid));"
                "time.sleep(60)"
            )
            child_code = "import time; time.sleep(60)"
            parent = subprocess.Popen(
                [sys.executable, "-c", parent_code, str(pidfile), child_code],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            child_pid = None
            try:
                deadline = time.time() + 10
                while not pidfile.exists() and time.time() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pidfile.exists(), "child pid was not written")
                child_pid = int(pidfile.read_text(encoding="ascii"))

                job = ProcessJob()
                if not job.assign(parent):
                    self.skipTest("process could not be assigned to a Job Object")
                job.close()

                parent.wait(timeout=5)
                deadline = time.time() + 5
                while _pid_alive(child_pid) and time.time() < deadline:
                    time.sleep(0.05)
                self.assertFalse(_pid_alive(child_pid), "descendant survived job close")
            finally:
                if parent.poll() is None:
                    parent.kill()
                if child_pid is not None and _pid_alive(child_pid):
                    subprocess.run(
                        ["taskkill", "/PID", str(child_pid), "/T", "/F"],
                        capture_output=True, check=False,
                    )


if __name__ == "__main__":
    unittest.main()
