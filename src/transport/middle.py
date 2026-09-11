"""BusinessServer — the middle layer facade.

Upper layer talks only to this object; token is a per-call parameter.
"""

from __future__ import annotations

import logging
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from pyapi.models import CommandResult, ExecutionStatus, Middle, VirtuosoResult
from transport.registry import Registry, load_registry
from transport.remote_roles import ResolvedTargets, resolve
from transport.runtime_paths import registry_path, set_working_dir
from transport.skill_client import SkillClient
from transport.tunnel import RemoteClient

logger = logging.getLogger(__name__)


class _LocalCommandSession:
    """One persistent local command interpreter per token.

    ``parallel=False`` commands share this session: submission order and
    session state (cwd, shell variables) are preserved, exactly like the
    remote persistent shell.  ``parallel=True`` still launches an independent
    process per call.  stdout/stderr are kept separate via a per-call
    stderr temp file; the bridge never injects output into the command
    stream.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._seq = 0
        self._proc = None
        self._reader = None
        self._dead = False
        self._eof = False
        self._current = None
        self._err_dir = Path(tempfile.mkdtemp(prefix="vb_local_err_"))
        self._spawn()

    # -- platform shell ---------------------------------------------------

    @staticmethod
    def _shell_command() -> list[str]:
        if os.name == "nt":
            return ["cmd.exe", "/Q", "/D"]
        return ["sh"]

    @staticmethod
    def _env() -> dict:
        env = dict(os.environ)
        if os.name == "nt":
            env["PROMPT"] = "__VBPS__"  # fixed prompt marker, filtered out
        return env

    @staticmethod
    def _rc_echo() -> str:
        return "echo __VB_RC_%errorlevel%__" if os.name == "nt" else "echo __VB_RC_$?__"

    @staticmethod
    def _eol() -> str:
        return "\r\n" if os.name == "nt" else "\n"

    def _quote_path(self, path: str) -> str:
        return f'"{path}"' if os.name == "nt" else shlex.quote(path)

    # -- process management ------------------------------------------------

    def _spawn(self) -> None:
        proc = subprocess.Popen(
            self._shell_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=self._env(),
        )
        self._proc = proc
        self._dead = False
        self._eof = False
        self._seq = 0
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        time.sleep(0.1)  # let cmd/sh finish startup before the first write
        self._drain_banner()

    def _drain_banner(self) -> None:
        marker = "__VB_DRAIN_0__"
        with self._lock:
            self._current = {
                "out_marker": marker, "err_marker": "__VB_ERREND_0__",
                "phase": "out", "out": [], "err": [], "rc": 0,
                "done": False, "eof": False,
            }
        self._write_line(f"echo {marker}")
        self._write_line("echo __VB_ERREND_0__")
        self._wait_current(None)
        with self._lock:
            self._current = None

    def _read_loop(self) -> None:
        try:
            for line in self._proc.stdout:  # type: ignore[union-attr]
                stripped = line.strip()
                if os.name == "nt":
                    # cmd.exe prints the prompt on the same line as the next
                    # command's output; strip every prompt prefix
                    while stripped.startswith("__VBPS__"):
                        stripped = stripped[len("__VBPS__"):].lstrip()
                    if not stripped:
                        continue
                with self._lock:
                    cur = self._current
                    if cur is None:
                        continue
                    if cur["phase"] == "out":
                        if stripped == cur["out_marker"]:
                            cur["phase"] = "err"
                        elif stripped.startswith("__VB_RC_") and stripped.endswith("__"):
                            try:
                                cur["rc"] = int(stripped[len("__VB_RC_"):-2])
                            except ValueError:
                                pass
                        else:
                            cur["out"].append(stripped + "\n")
                    else:
                        if stripped == cur["err_marker"]:
                            cur["done"] = True
                        else:
                            cur["err"].append(stripped + "\n")
        except (OSError, ValueError):
            pass
        finally:
            with self._lock:
                self._eof = True
                if self._current is not None:
                    self._current["eof"] = True
                self._dead = True

    def _write_line(self, text: str) -> None:
        assert self._proc and self._proc.stdin
        self._proc.stdin.write(text + self._eol())
        self._proc.stdin.flush()

    def _wait_current(self, deadline: float | None) -> None:
        while True:
            with self._lock:
                cur = self._current
                done = cur["done"] if cur else True
                eof = cur["eof"] if cur else True
            if done or eof:
                return
            if deadline is not None and time.monotonic() >= deadline:
                return
            time.sleep(0.01)

    def _close_locked(self) -> None:
        self._dead = True
        proc = self._proc
        if proc is not None:
            already_exited = proc.poll() is not None
            if not already_exited:
                for stream in (proc.stdin, proc.stdout):
                    try:
                        if stream:
                            stream.close()
                    except OSError:
                        pass
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except OSError:
                    pass
        self._proc = None
        if self._reader is not None:
            self._reader.join(timeout=1)
            self._reader = None

    def execute(self, cmd: str, timeout: float | None = None) -> CommandResult:
        need_spawn = False
        with self._lock:
            if self._dead or self._proc is None or self._proc.poll() is not None:
                need_spawn = True
            else:
                self._seq += 1
                n = self._seq
                err_path = self._err_dir / f"err_{n}.txt"
                out_marker = f"__VB_EOM_{n}__"
                err_marker = f"__VB_ERREND_{n}__"
                self._current = {
                    "out_marker": out_marker, "err_marker": err_marker,
                    "phase": "out", "out": [], "err": [], "rc": 0,
                    "done": False, "eof": False,
                }
        if need_spawn:
            # spawn WITHOUT holding the session lock: the reader thread must
            # be able to take it while we drain the new shell banner
            try:
                self._close_locked()
                self._spawn()
            except OSError as exc:
                self._dead = True
                return CommandResult(255, "", f"VB-TRANSPORT: local shell unavailable: {exc}")
            with self._lock:
                self._seq += 1
                n = self._seq
                err_path = self._err_dir / f"err_{n}.txt"
                out_marker = f"__VB_EOM_{n}__"
                err_marker = f"__VB_ERREND_{n}__"
                self._current = {
                    "out_marker": out_marker, "err_marker": err_marker,
                    "phase": "out", "out": [], "err": [], "rc": 0,
                    "done": False, "eof": False,
                }

        quoted_err = self._quote_path(str(err_path))
        # group the command so its stderr redirects to the per-call file;
        # braces/parens run in the current session so cwd/env state persists
        if os.name == "nt":
            grouped = f"( {cmd} ) 2> {quoted_err}"
        else:
            grouped = f"{{ {cmd}; }} 2> {quoted_err}"
        try:
            self._write_line(grouped)
            self._write_line(self._rc_echo())
            self._write_line(f"echo {out_marker}")
            self._write_line(f"type {quoted_err}" if os.name == "nt" else f"cat {quoted_err}")
            self._write_line(f"echo {err_marker}")
            self._write_line(f"del {quoted_err}" if os.name == "nt" else f"rm -f {quoted_err}")
        except (OSError, ValueError):
            self._close_locked()
            return CommandResult(255, "", "VB-TRANSPORT: local shell write failed")

        deadline = None if timeout is None else time.monotonic() + timeout
        self._wait_current(deadline)
        with self._lock:
            cur = self._current
            out = "".join(cur["out"]).rstrip("\n")
            err = "".join(cur["err"]).rstrip("\n")
            rc = cur["rc"]
            done = cur["done"]
            eof = cur["eof"]
            if self._current is cur:
                self._current = None
        try:
            err_path.unlink(missing_ok=True)
        except OSError:
            pass
        if not done and not eof:
            self._close_locked()
            return CommandResult(124, out, f"command timed out after {timeout}s")
        if eof:
            proc_rc = self._proc.poll() if self._proc is not None else None
            self._close_locked()
            return CommandResult(proc_rc if proc_rc is not None else 255, out, err or "local shell exited")
        return CommandResult(rc, out, err)

    def close(self) -> None:
        with self._lock:
            self._close_locked()


class BusinessServer(Middle):
    def __init__(self, work_dir: str | Path | None = None) -> None:
        set_working_dir(work_dir)
        self.registry: Registry = load_registry(registry_path())
        self._clients: dict[str, RemoteClient] = {}
        self._skill_clients: dict[str, SkillClient] = {}
        self._capacity: dict[str, threading.BoundedSemaphore] = {}
        self._local_locks: dict[str, threading.Lock] = {}
        self._local_sessions: dict[str, _LocalCommandSession] = {}
        self._lock = threading.Lock()

    # -- per-token state -----------------------------------------------------

    def _entry(self, token: str):
        entry = self.registry.by_token(token)
        if entry is None:
            raise LookupError(f"unknown token")
        return entry

    def _targets(self, entry, user: str | None = None) -> ResolvedTargets:
        return resolve(entry, user=user)

    def _remote(self, token: str) -> RemoteClient:
        with self._lock:
            client = self._clients.get(token)
            if client is None:
                entry = self._entry(token)
                user = self.registry.user_of(token) or token
                client = RemoteClient(entry, self._targets(entry, user=user), user)
                self._clients[token] = client
                # Never replace a semaphore that _acquire() may already hold.
                self._capacity.setdefault(
                    token,
                    threading.BoundedSemaphore(entry.runtime.thread_pool_size),
                )
            return client

    def _skill(self, token: str) -> SkillClient:
        with self._lock:
            client = self._skill_clients.get(token)
            if client is None:
                entry = self._entry(token)
                targets = self._targets(entry)
                client = SkillClient(
                    host="127.0.0.1",
                    port=targets.local_port,
                    timeout=30.0,
                    token=token,
                    log_level=entry.cdslog.log_level,
                    log_max_bytes=entry.cdslog.log_max_bytes,
                )
                self._skill_clients[token] = client
            return client

    def _acquire(self, token: str, entry=None) -> bool:
        if entry is None:
            entry = self._entry(token)
        with self._lock:
            sem = self._capacity.get(token)
            if sem is None:
                sem = threading.BoundedSemaphore(entry.runtime.thread_pool_size)
                self._capacity[token] = sem
        return sem.acquire(blocking=False)

    def _release(self, token: str) -> None:
        sem = self._capacity.get(token)
        if sem is not None:
            sem.release()

    def _local_lock(self, token: str) -> threading.Lock:
        """Per-token serial lock for the persistent local command session."""
        with self._lock:
            lock = self._local_locks.get(token)
            if lock is None:
                lock = threading.Lock()
                self._local_locks[token] = lock
            return lock

    def _local_session(self, token: str) -> _LocalCommandSession:
        with self._lock:
            session = self._local_sessions.get(token)
            if session is None:
                session = _LocalCommandSession()
                self._local_sessions[token] = session
            return session

    # -- three interfaces -----------------------------------------------------

    def execute_skill(self, skill_code: str, timeout: float | None = None, *, token: str) -> VirtuosoResult:
        acquired = False
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return VirtuosoResult(status=ExecutionStatus.ERROR, errors=["thread pool exceeded"])
            acquired = True
            if entry.mode != "local":
                self._remote(token).ensure_tunnel(deadline=deadline)
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            return self._skill(token).execute_skill(skill_code, timeout=remaining)
        except LookupError as exc:
            return VirtuosoResult(status=ExecutionStatus.ERROR, errors=[str(exc)])
        except RuntimeError as exc:
            # transient transport setup failure (e.g. a cold sshd handshake
            # drop); surface as an error result so callers can retry
            return VirtuosoResult(status=ExecutionStatus.ERROR, errors=[str(exc)])
        finally:
            if acquired:
                self._release(token)

    def run_command(self, cmd: str, timeout: int | None = None, *, token: str, parallel: bool = False) -> CommandResult:
        acquired = False
        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded")
            acquired = True
            if entry.mode == "local":
                if parallel:
                    return self._local_command(cmd, timeout)
                with self._local_lock(token):
                    return self._local_session(token).execute(cmd, timeout)
            return self._remote(token).run_command(cmd, timeout=timeout, parallel=parallel)
        except LookupError as exc:
            return CommandResult(returncode=1, stdout="", stderr=str(exc))
        finally:
            if acquired:
                self._release(token)

    def upload_file(self, local_path: Path, remote_path: str, timeout: int | None = None, *, token: str, recursive: bool = False) -> CommandResult:
        acquired = False
        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded")
            acquired = True
            if entry.mode == "local":
                return self._local_upload(local_path, remote_path, recursive)
            return self._remote(token).upload_file(Path(local_path), remote_path, timeout=timeout, recursive=recursive)
        except LookupError as exc:
            return CommandResult(returncode=1, stdout="", stderr=str(exc))
        finally:
            if acquired:
                self._release(token)

    def download_file(self, remote_path: str, local_path: Path, timeout: int | None = None, *, token: str, recursive: bool = False) -> CommandResult:
        acquired = False
        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded")
            acquired = True
            if entry.mode == "local":
                return self._local_download(remote_path, local_path, recursive)
            return self._remote(token).download_file(remote_path, Path(local_path), timeout=timeout, recursive=recursive)
        except LookupError as exc:
            return CommandResult(returncode=1, stdout="", stderr=str(exc))
        finally:
            if acquired:
                self._release(token)

    # -- local-mode helpers ---------------------------------------------------

    @staticmethod
    def _local_command(cmd: str, timeout: int | None) -> CommandResult:
        try:
            proc = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout)
            return CommandResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(returncode=124, stdout="", stderr=f"command timed out after {timeout}s")

    @staticmethod
    def _local_upload(local_path: Path, remote_path: str, recursive: bool) -> CommandResult:
        try:
            src = Path(local_path)
            dst = Path(remote_path)
            if recursive:
                if not src.is_dir():
                    return CommandResult(1, "", f"recursive upload requires a directory: {src}")
                shutil.copytree(src, dst, dirs_exist_ok=True)
            else:
                if src.is_dir():
                    return CommandResult(1, "", f"directory upload requires recursive=True: {src}")
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
            return CommandResult(0, str(dst), "")
        except OSError as exc:
            return CommandResult(1, "", str(exc))

    @staticmethod
    def _local_download(remote_path: str, local_path: Path, recursive: bool) -> CommandResult:
        try:
            src = Path(remote_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            if recursive:
                shutil.copytree(src, local_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src, local_path)
            return CommandResult(0, str(local_path), "")
        except OSError as exc:
            return CommandResult(1, "", str(exc))


__all__ = ["BusinessServer"]
