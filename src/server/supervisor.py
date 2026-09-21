"""Management supervisor: parent process owning the business child.

顶层补充 v27 §1/§3:

* 标准形态 = 同机双进程，管理进程为父、业务进程为子（不 detach）；
* `GET /api/process/status`、`POST /api/process/reload`、
  `POST /api/process/restart` 由控制面暴露（管理权限）；
* 子进程意外退出 → `crashed`，不自动拉起；
* 管理退出（子进程 stdin EOF）→ 业务进程自行排空退出；
* `--single-process` 为简化部署：两 face 同进程，`restart` 返回 501。

Run::

    python -m server.supervisor --control-port 8124 --business-port 8127 \\
        --work-dir <work>
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from register.server import RegistrationServer
from common import config as config_base
from common.registry import load_registry
from common.process_lifetime import ProcessJob
from common.ssh import _windows_no_window_kwargs
from common.paths import (
    command_log_file,
    config_path,
    init_work_dir,
    registry_path,
    work_root,
)

#: 与业务子进程约定的控制事件行前缀（子进程 stdout）
EVENT_PREFIX = "VB-EVENT "

#: 重启排空上限（顶层补充 v27 §3：写死 30 秒）
DRAIN_TIMEOUT = 30.0

#: Windows CreateProcess flag: leave the child's primary thread suspended.
_CREATE_SUSPENDED = 0x00000004


def _redact_args(args: list[str]) -> list[str]:
    """Redact any token-looking startup argument (v27 §1.1)."""
    out: list[str] = []
    mask_next = False
    for arg in args:
        if mask_next:
            out.append("***")
            mask_next = False
            continue
        if arg == "--token":
            out.append(arg)
            mask_next = True
        elif arg.startswith("--token="):
            out.append("--token=***")
        else:
            out.append(arg)
    return out


class BusinessProcess:
    """Supervise one `server.api_server --supervised` child."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        work_dir: str | Path,
        python: str | None = None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.work_dir = str(work_dir)
        self.python = python or sys.executable
        self.args = [
            self.python, "-m", "server.api_server",
            "--host", self.host, "--port", str(self.port),
            "--work-dir", self.work_dir,
            "--supervised",
        ]
        self.state = "crashed"  # starting / ready / crashed / stopped
        self.pid: int | None = None
        self.bound_port: int | None = None
        self.last_error: str | None = None
        self._proc: subprocess.Popen[str] | None = None
        self._job: ProcessJob | None = None
        self._job_bound = False
        self._posix_group_pid: int | None = None
        self._events: list[dict] = []
        self._event_cv = threading.Condition()
        self._stderr_tail: list[str] = []
        self._shutting_down = False

    # -- lifecycle -----------------------------------------------------------
    def start(self, timeout: float = DRAIN_TIMEOUT) -> None:
        if self._proc is not None or self._job is not None:
            self._dispose_child(1.0)
        env = dict(os.environ)
        src = str(Path(__file__).resolve().parents[1])
        existing = env.get("PYTHONPATH", "")
        if src not in existing.split(os.pathsep):
            env["PYTHONPATH"] = (src + os.pathsep + existing).rstrip(os.pathsep)
        with self._event_cv:
            self._events.clear()
            self._stderr_tail.clear()
            self.state = "starting"
        self._shutting_down = False
        self._job = ProcessJob()
        popen_kwargs = {
            "env": env,
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "text": True,
            "bufsize": 1,
        }
        popen_kwargs.update(_windows_no_window_kwargs())
        if os.name == "nt":
            # Bind the child to its Job before it executes any instruction.
            # Assigning after it has already started can leave descendants
            # outside the Job when this supervisor itself runs inside one.
            popen_kwargs["creationflags"] |= _CREATE_SUSPENDED
        if os.name != "nt":
            # Make the business child a session/process-group leader so the
            # supervised restart path can signal the whole tree.
            popen_kwargs["start_new_session"] = True
        try:
            self._proc = subprocess.Popen(self.args, **popen_kwargs)
        except Exception:
            self._job.close()
            self._job = None
            raise
        if os.name != "nt":
            self._posix_group_pid = self._proc.pid
        if os.name == "nt":
            self._job_bound = self._job.assign(self._proc)
            self._job_bound = (
                self._job_bound and self._job.resume(self._proc)
            )
            if not self._job_bound:
                self._dispose_child(1.0)
                raise RuntimeError(
                    "could not bind business process to a Windows Job Object; "
                    "refusing to start with process-tree cleanup degraded"
                )
        else:
            self._job_bound = self._job.assign(self._proc)
        self.pid = self._proc.pid
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()
        event = self.wait_event("ready", timeout)
        if event is None:
            self.last_error = (
                "business process did not become ready: "
                + (" | ".join(self._stderr_tail[-3:]) or "no stderr")
            )
            with self._event_cv:
                self.state = "crashed"
            self._dispose_child(5.0)
            raise RuntimeError(self.last_error)
        self.bound_port = int(event.get("port") or self.port)
        with self._event_cv:
            self.state = "ready"

    def _read_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            if not line.startswith(EVENT_PREFIX):
                continue
            try:
                event = json.loads(line[len(EVENT_PREFIX):])
            except ValueError:
                continue
            with self._event_cv:
                self._events.append(event)
                self._event_cv.notify_all()
        # stdout EOF: child exited
        self._mark_exit(proc)

    def _read_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for line in proc.stderr:
            self._stderr_tail.append(line.rstrip())
            if len(self._stderr_tail) > 50:
                del self._stderr_tail[0]

    def _mark_exit(self, proc: subprocess.Popen[str]) -> None:
        with self._event_cv:
            if self._proc is not proc:
                # 已经换成新的子进程（restart 期间旧读取线程收尾）——忽略
                return
            if self._shutting_down:
                self.state = "stopped"
            else:
                self.state = "crashed"
            self._event_cv.notify_all()
        job, self._job = self._job, None
        self._job_bound = False
        if job is not None:
            job.close()
        group, self._posix_group_pid = self._posix_group_pid, None
        if os.name != "nt" and group:
            self._signal_process_group(group, signal.SIGTERM)

    def _send(self, command: str) -> bool:
        proc = self._proc
        if proc is None or proc.stdin is None or proc.poll() is not None:
            return False
        try:
            proc.stdin.write(json.dumps({"cmd": command}) + "\n")
            proc.stdin.flush()
            return True
        except OSError:
            return False

    def wait_event(self, name: str, timeout: float) -> dict | None:
        deadline = time.monotonic() + max(0.0, timeout)
        with self._event_cv:
            while True:
                for event in self._events:
                    if event.get("event") == name:
                        self._events.remove(event)
                        return event
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self._event_cv.wait(left)

    def _wait_exit(self, timeout: float) -> bool:
        proc = self._proc
        if proc is None:
            return True
        try:
            proc.wait(timeout=timeout)
            return True
        except subprocess.TimeoutExpired:
            return False

    def _dispose_child(self, timeout: float) -> None:
        proc = self._proc
        job, self._job = self._job, None
        bound, self._job_bound = self._job_bound, False
        posix_group, self._posix_group_pid = self._posix_group_pid, None
        if proc is None:
            if job is not None:
                job.close()
            return
        if proc.poll() is None:
            if not self._wait_exit(timeout):
                self._force_kill_tree(proc, job_bound=bound)
                self._wait_exit(5.0)
        for stream in (proc.stdin, proc.stdout, proc.stderr):
            try:
                if stream:
                    stream.close()
            except OSError:
                pass
        self._proc = None
        if job is not None:
            job.close()
        if os.name != "nt" and posix_group:
            self._signal_process_group(posix_group, signal.SIGTERM)

    @staticmethod
    def _force_kill_tree(
        proc: subprocess.Popen[str], *, job_bound: bool
    ) -> None:
        """Kill the child tree, using taskkill when no job is available."""
        if os.name == "nt" and proc.pid:
            try:
                result = subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                    timeout=10,
                    creationflags=getattr(
                        subprocess, "CREATE_NO_WINDOW", 0
                    ),
                )
                if result.returncode == 0:
                    return
            except (OSError, subprocess.TimeoutExpired):
                pass
        if os.name != "nt" and proc.pid:
            self._signal_process_group(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=2)
                return
            except subprocess.TimeoutExpired:
                self._signal_process_group(proc.pid, signal.SIGKILL)
                return
        if job_bound:
            return
        try:
            proc.kill()
        except OSError:
            pass

    @staticmethod
    def _signal_process_group(pgid: int, sig: int) -> None:
        try:
            os.killpg(pgid, sig)
        except OSError:
            pass

    # -- management API ------------------------------------------------------
    def status(self) -> dict:
        return {
            "same_process": False,
            "state": self.state,
            "pid": self.pid,
            "port": self.bound_port if self.bound_port is not None else self.port,
            "work_dir": self.work_dir,
            "startup_args": _redact_args(self.args[1:]),
            "last_error": self.last_error,
        }

    def reload(self, timeout: float = DRAIN_TIMEOUT) -> dict:
        if self.state != "ready":
            raise RuntimeError(f"business process is not ready: {self.state}")
        if not self._send("reload"):
            raise RuntimeError("business control channel is closed")
        event = self.wait_event("reload_done", timeout)
        if event is None:
            raise RuntimeError("reload timed out")
        if not event.get("ok"):
            raise RuntimeError(str(event.get("error") or "reload failed"))
        return self.status()

    def restart(self, timeout: float = DRAIN_TIMEOUT) -> dict:
        if self._proc is not None:
            if self._proc.poll() is None:
                self._shutting_down = True
                self._send("drain")
                self.wait_event("drain_done", timeout)
                if not self._wait_exit(5.0):
                    self._proc.kill()
                    self._wait_exit(5.0)
            self._dispose_child(5.0)
        self._shutting_down = False
        self.start(timeout)
        return self.status()

    def shutdown(self, timeout: float = DRAIN_TIMEOUT) -> None:
        if self._proc is None or self._proc.poll() is not None:
            self._dispose_child(5.0)
            return
        self._shutting_down = True
        self._send("drain")
        self.wait_event("drain_done", timeout)
        if not self._wait_exit(5.0):
            self._proc.kill()
            self._wait_exit(5.0)
        self._dispose_child(5.0)


class SameProcessManager:
    """`--single-process` mode: both faces in one process (v27 §3)."""

    same_process = True

    def __init__(self, middle, business_server) -> None:
        self.middle = middle
        self.business_server = business_server

    def status(self) -> dict:
        return {
            "same_process": True,
            "state": "ready" if not self.business_server.draining else "draining",
            "pid": os.getpid(),
            "port": self.business_server.server_address[1],
            "work_dir": str(work_root()),
            "startup_args": [],
            "last_error": None,
        }

    def reload(self) -> dict:
        from server.api_server import (
            load_business_thread_pool_size,
            reload_business_state,
        )

        ok, error = reload_business_state(self.business_server, self.middle)
        if not ok:
            raise RuntimeError(str(error))
        return self.status()

    def restart(self) -> dict:
        # 同进程部署不允许自己重启自己
        raise NotImplementedError

    def shutdown(self) -> None:
        return None


def _build_business(
    host: str, port: int, work_dir: str | None, *, single_process: bool
):
    from transport.middle import BusinessServer
    from server.api_server import (
        build_server,
        pool_size_from_snapshot,
    )

    init_work_dir(work_dir)
    config_base.reload_config(config_path())
    middle = BusinessServer()
    pool_size = pool_size_from_snapshot(config_base.snapshot())
    server = build_server(host, port, middle, max_inflight=pool_size)
    return middle, server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="virtuoso-bridge management supervisor (parent of business)"
    )
    parser.add_argument("--control-host", default="127.0.0.1")
    parser.add_argument("--control-port", type=int, default=8124)
    parser.add_argument("--business-host", default="127.0.0.1")
    parser.add_argument("--business-port", type=int, default=8127)
    parser.add_argument("--work-dir", default=None)
    parser.add_argument(
        "--single-process", action="store_true",
        help="run both faces in this process (restart returns 501)",
    )
    args = parser.parse_args(argv)

    init_work_dir(args.work_dir)
    from common.ssh import configure_command_log

    configure_command_log(command_log_file())
    registry = load_registry(registry_path())

    manager = None
    middle = None
    business_server = None
    threads: list[threading.Thread] = []

    if args.single_process:
        middle, business_server = _build_business(
            args.business_host, args.business_port, args.work_dir,
            single_process=True,
        )
        thread = threading.Thread(
            target=business_server.serve_forever, daemon=True
        )
        thread.start()
        threads.append(thread)
        manager = SameProcessManager(middle, business_server)
    else:
        manager = BusinessProcess(
            host=args.business_host,
            port=args.business_port,
            work_dir=str(work_root()),
        )
        try:
            manager.start()
        except Exception as exc:  # noqa: BLE001
            print(f"[supervisor] business child failed to start: {exc}",
                  file=sys.stderr)

    control = RegistrationServer(
        (args.control_host, args.control_port), registry, manager
    )
    print(
        f"virtuoso-bridge supervisor: control=http://{args.control_host}:"
        f"{args.control_port} business={args.business_host}:{args.business_port}"
        f" same_process={bool(args.single_process)}"
    )
    try:
        control.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        control.server_close()
        if manager is not None:
            try:
                manager.shutdown()
            except Exception:  # noqa: BLE001 - best effort on shutdown
                pass
        if business_server is not None:
            business_server.shutdown()
            business_server.server_close()
        if middle is not None:
            middle.close()


if __name__ == "__main__":
    main()
