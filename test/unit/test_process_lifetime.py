"""Windows process-lifetime contract for supervised children."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from common.process_lifetime import ProcessJob


def _pid_alive(pid: int) -> bool:
    if os.name != "nt":
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [
        wintypes.DWORD, wintypes.BOOL, wintypes.DWORD
    ]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        ok = kernel32.GetExitCodeProcess(handle, ctypes.byref(code))
        return bool(ok) and code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _taskkill(pid: int) -> None:
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass


@unittest.skipUnless(os.name == "nt", "Windows Job Object contract")
class TestProcessJob(unittest.TestCase):
    def test_close_kills_parent_and_descendant(self):
        with tempfile.TemporaryDirectory() as td:
            pidfile = Path(td) / "child.pid"
            ready = Path(td) / "ready"
            go = Path(td) / "go"
            parent_code = (
                "import pathlib, subprocess, sys, time\n"
                "ready = pathlib.Path(sys.argv[1])\n"
                "go = pathlib.Path(sys.argv[2])\n"
                "pidfile = pathlib.Path(sys.argv[3])\n"
                "ready.write_text('ready')\n"
                "while not go.exists():\n"
                "    time.sleep(0.05)\n"
                "p = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(60)'])\n"
                "pidfile.write_text(str(p.pid))\n"
                "time.sleep(60)"
            )
            parent = subprocess.Popen(
                [
                    sys.executable, "-c", parent_code,
                    str(ready), str(go), str(pidfile),
                ],
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            child_pid = None
            job = ProcessJob()
            try:
                deadline = time.time() + 10
                while not ready.exists() and time.time() < deadline:
                    time.sleep(0.05)
                self.assertTrue(ready.exists(), "parent did not become ready")
                self.assertTrue(
                    job.assign(parent),
                    "test process could not be assigned to a Job Object",
                )
                go.write_text("go", encoding="ascii")
                deadline = time.time() + 10
                while not pidfile.exists() and time.time() < deadline:
                    time.sleep(0.05)
                self.assertTrue(pidfile.exists(), "child pid was not written")
                child_pid = int(pidfile.read_text(encoding="ascii"))
                self.assertTrue(_pid_alive(parent.pid))
                self.assertTrue(_pid_alive(child_pid))

                job.close()

                parent.wait(timeout=5)
                deadline = time.time() + 5
                while _pid_alive(child_pid) and time.time() < deadline:
                    time.sleep(0.05)
                self.assertFalse(_pid_alive(child_pid), "descendant survived job close")
            finally:
                job.close()
                if parent.poll() is None:
                    _taskkill(parent.pid)
                if child_pid is not None:
                    _taskkill(child_pid)


@unittest.skipUnless(os.name == "nt", "Windows Job Object contract")
class TestBusinessProcessLifetime(unittest.TestCase):
    def test_unbound_fallback_uses_taskkill_tree(self):
        from server.supervisor import BusinessProcess

        class FakeProc:
            pid = 4242
            killed = False

            def kill(self):
                self.killed = True

        proc = FakeProc()
        with mock.patch("server.supervisor.subprocess.run") as run:
            run.return_value.returncode = 0
            BusinessProcess._force_kill_tree(proc, job_bound=False)
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ["taskkill", "/PID", "4242"])
        self.assertIn("/T", command)
        self.assertIn("/F", command)
        self.assertFalse(proc.killed)

    def test_shutdown_kills_supervised_descendant(self):
        from server.supervisor import BusinessProcess

        with tempfile.TemporaryDirectory() as td:
            pidfile = Path(td) / "descendant.pid"
            script = (
                "import json, pathlib, subprocess, sys, time\n"
                "p = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(60)'])\n"
                "pathlib.Path(sys.argv[1]).write_text(str(p.pid))\n"
                "print('VB-EVENT ' + json.dumps("
                "{'event': 'ready', 'port': 1}), flush=True)\n"
                "for line in sys.stdin:\n"
                "    if 'drain' in line:\n"
                "        print('VB-EVENT ' + json.dumps("
                "{'event': 'drain_done', 'ok': True}), flush=True)\n"
                "        break\n"
                "time.sleep(1)\n"
            )
            bp = BusinessProcess(host="127.0.0.1", port=1, work_dir=td)
            bp.args = [sys.executable, "-c", script, str(pidfile)]
            child_pid = None
            try:
                bp.start(timeout=15)
                child_pid = int(pidfile.read_text(encoding="ascii"))
                self.assertTrue(_pid_alive(child_pid))
                bp._dispose_child(1.0)
                deadline = time.time() + 5
                while _pid_alive(child_pid) and time.time() < deadline:
                    time.sleep(0.05)
                self.assertFalse(_pid_alive(child_pid))
            finally:
                bp._dispose_child(0.5)
                if child_pid is not None:
                    _taskkill(child_pid)
                if bp.pid:
                    _taskkill(bp.pid)


@unittest.skipIf(os.name == "nt", "POSIX process-group contract")
class TestPosixBusinessProcessLifetime(unittest.TestCase):
    def test_dispose_kills_process_group_descendant(self):
        from server.supervisor import BusinessProcess

        with tempfile.TemporaryDirectory() as td:
            pidfile = Path(td) / "descendant.pid"
            script = (
                "import pathlib, subprocess, sys, time\n"
                "p = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(60)'])\n"
                "pathlib.Path(sys.argv[1]).write_text(str(p.pid))\n"
                "print('VB-EVENT ' + __import__('json').dumps("
                "{'event': 'ready', 'port': 1}), flush=True)\n"
                "time.sleep(60)\n"
            )
            bp = BusinessProcess(host="127.0.0.1", port=1, work_dir=td)
            bp.args = [sys.executable, "-c", script, str(pidfile)]
            child_pid = None
            try:
                bp.start(timeout=15)
                child_pid = int(pidfile.read_text(encoding="ascii"))
                self.assertTrue(_pid_alive(child_pid))
                bp._dispose_child(1.0)
                deadline = time.time() + 5
                while _pid_alive(child_pid) and time.time() < deadline:
                    time.sleep(0.05)
                self.assertFalse(_pid_alive(child_pid))
            finally:
                bp._dispose_child(0.5)
                if child_pid is not None:
                    try:
                        os.kill(child_pid, 9)
                    except OSError:
                        pass
                if bp.pid:
                    try:
                        os.kill(bp.pid, 9)
                    except OSError:
                        pass


if __name__ == "__main__":
    unittest.main()
