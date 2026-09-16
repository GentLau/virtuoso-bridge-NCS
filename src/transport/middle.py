"""BusinessServer — the middle layer facade.

Upper layer talks only to this object; token is a per-call parameter.
"""

from __future__ import annotations

import atexit
import hashlib
import logging
import os
import shlex
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from pathlib import Path

from pyapi.models import (
    CommandResult,
    ExecutionStatus,
    Middle,
    QueryResult,
    RoleQuery,
    VirtuosoResult,
)
from transport.budgets import CapacityExceeded
from transport.remote_paths import RemotePathError
from transport.registry import Registry, load_registry
from transport.roles import ResolvedTargets, resolve
from transport.runtime_paths import registry_path, set_working_dir
from transport.skill_client import SkillClient
from transport.ssh import UnknownEffectError
from transport.transfer import install_staged_item
from transport.tunnel import RemoteClient

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0  # spec: timeout=None -> 30s for all five interfaces

# Local transfers stream in bounded chunks so the call deadline is observed
# even when the disk is slow; a single shutil.copy2 cannot be interrupted.
_TRANSFER_CHUNK = 1024 * 1024


class _DeadlineExceeded(Exception):
    """A local transfer ran past the budget of its interface call."""


def _copy_file_with_deadline(src: Path, dst: Path, deadline: float | None) -> None:
    """Stream-copy one file, checking the budget between chunks."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    with src.open("rb") as source, dst.open("wb") as target:
        while True:
            if deadline is not None and time.monotonic() >= deadline:
                raise _DeadlineExceeded
            chunk = source.read(_TRANSFER_CHUNK)
            if not chunk:
                break
            target.write(chunk)
    try:
        shutil.copystat(src, dst)
    except OSError:  # best effort; content is already correct
        pass


def _copy_tree_with_deadline(src: Path, dst: Path, deadline: float | None) -> None:
    """Recursive copy that checks the budget for every directory entry."""
    stack: list[tuple[Path, Path]] = [(src, dst)]
    while stack:
        if deadline is not None and time.monotonic() >= deadline:
            raise _DeadlineExceeded
        current_src, current_dst = stack.pop()
        current_dst.mkdir(parents=True, exist_ok=True)
        try:
            current_dst.chmod(current_src.stat().st_mode & 0o777)
        except OSError:
            pass
        with os.scandir(current_src) as entries:
            for entry in entries:
                if deadline is not None and time.monotonic() >= deadline:
                    raise _DeadlineExceeded
                entry_src = Path(entry.path)
                entry_dst = current_dst / entry.name
                if entry.is_dir(follow_symlinks=True):
                    stack.append((entry_src, entry_dst))
                else:
                    _copy_file_with_deadline(entry_src, entry_dst, deadline)


def _copy_into_with_deadline(src: Path, dst: Path, deadline: float | None) -> None:
    """Copy a file or a whole tree, honouring ``deadline``."""
    if src.is_dir():
        _copy_tree_with_deadline(src, dst, deadline)
    else:
        _copy_file_with_deadline(src, dst, deadline)

# Reserved diagnostic prefixes (spec: 三层架构 §4.4).  Upper layers may match
# on them; the text after the prefix is diagnostic detail only.
_VB_TRANSPORT = "VB-TRANSPORT: "
_VB_PATH = "VB-PATH-NOT-VISIBLE: "
_VB_UNKNOWN_EFFECT = "VB-UNKNOWN-EFFECT: "


def _effective_timeout(timeout: float | int | None) -> float:
    return _DEFAULT_TIMEOUT if timeout is None else float(timeout)


def _error_result(exc: BaseException, budget: float | None = None) -> CommandResult:
    """Map a transported exception onto the ``CommandResult.kind`` contract.

    Timeouts keep the bridge reserved code 124, transport failures 255; the
    only place a real command's exit code is exposed is ``kind="command"``.
    """
    if isinstance(exc, CapacityExceeded):
        return CommandResult(1, "", exc.message, kind="rejected")
    if isinstance(exc, (subprocess.TimeoutExpired, TimeoutError)):
        detail = (
            f"command timed out after {float(budget):g}s"
            if budget is not None
            else "command timed out"
        )
        return CommandResult(returncode=124, stdout="", stderr=detail, kind="timeout")
    if isinstance(exc, RemotePathError):
        return CommandResult(1, "", f"{_VB_PATH}{exc}", kind="path")
    if isinstance(exc, UnknownEffectError):
        return CommandResult(255, "", f"{_VB_UNKNOWN_EFFECT}{exc}", kind="unknown-effect")
    if isinstance(exc, (FileNotFoundError, IsADirectoryError, NotADirectoryError)):
        return CommandResult(1, "", f"{_VB_PATH}{exc}", kind="path")
    return CommandResult(255, "", f"{_VB_TRANSPORT}{exc}", kind="transport")


class _LocalCommandSession:
    """One persistent local command interpreter per token.

    ``parallel=False`` commands share this session (order + cwd/env state
    preserved); ``parallel=True`` launches an independent process per call.
    stdout/stderr are kept separate via a per-call stderr file that Python
    reads back after the shell finishes the command.
    """

    def __init__(self, cwd: str | None = None) -> None:
        self._lock = threading.RLock()
        self._seq = 0
        self._proc = None
        self._reader = None
        self._dead = False
        self._eof = False
        self._current = None
        self._err_dir = Path(tempfile.mkdtemp(prefix="vb_local_err_"))
        self._cwd = None
        if cwd:
            workdir = Path(cwd).expanduser()
            workdir.mkdir(parents=True, exist_ok=True)
            self._cwd = str(workdir)
        self._spawn()

    @staticmethod
    def _shell_command() -> list[str]:
        return ["cmd.exe", "/Q", "/D"] if os.name == "nt" else ["sh"]

    @staticmethod
    def _env() -> dict:
        env = dict(os.environ)
        if os.name == "nt":
            env["PROMPT"] = "__VBPS__"
        return env

    @staticmethod
    def _rc_echo() -> str:
        return "echo __VB_RC_%errorlevel%__" if os.name == "nt" else "echo __VB_RC_$?__"

    @staticmethod
    def _eol() -> str:
        return "\r\n" if os.name == "nt" else "\n"

    def _quote_path(self, path: str) -> str:
        return f'"{path}"' if os.name == "nt" else shlex.quote(path)

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
            cwd=self._cwd or None,
        )
        self._proc = proc
        self._dead = False
        self._eof = False
        self._seq = 0
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        time.sleep(0.1)
        self._drain_banner()

    def _drain_banner(self) -> None:
        marker = "__VB_DRAIN_0__"
        with self._lock:
            self._current = {"marker": marker, "out": [], "rc": 0, "done": False, "eof": False}
        self._write_line(f"echo {marker}")
        self._wait_current(None)
        with self._lock:
            self._current = None

    def _read_loop(self) -> None:
        try:
            for line in self._proc.stdout:  # type: ignore[union-attr]
                stripped = line.strip()
                if os.name == "nt":
                    while stripped.startswith("__VBPS__"):
                        stripped = stripped[len("__VBPS__"):].lstrip()
                    if not stripped:
                        continue
                with self._lock:
                    cur = self._current
                    if cur is None:
                        continue
                    if stripped == cur["marker"]:
                        cur["done"] = True
                    elif stripped.startswith("__VB_RC_") and stripped.endswith("__"):
                        try:
                            cur["rc"] = int(stripped[len("__VB_RC_"):-2])
                        except ValueError:
                            pass
                    else:
                        cur["out"].append(stripped + "\n")
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
                marker = f"__VB_EOM_{n}__"
                self._current = {"marker": marker, "out": [], "rc": 0, "done": False, "eof": False}
        if need_spawn:
            try:
                self._close_locked()
                self._spawn()
            except OSError as exc:
                self._dead = True
                return CommandResult(255, "", f"VB-TRANSPORT: local shell unavailable: {exc}", kind="transport")
            with self._lock:
                self._seq += 1
                n = self._seq
                err_path = self._err_dir / f"err_{n}.txt"
                marker = f"__VB_EOM_{n}__"
                self._current = {"marker": marker, "out": [], "rc": 0, "done": False, "eof": False}

        quoted_err = self._quote_path(str(err_path))
        if os.name == "nt":
            grouped = f"( {cmd} ) 2> {quoted_err}"
        else:
            grouped = f"{{ {cmd}; }} 2> {quoted_err}"
        try:
            self._write_line(grouped)
            self._write_line(self._rc_echo())
            self._write_line(f"echo {marker}")
        except (OSError, ValueError):
            self._close_locked()
            return CommandResult(255, "", "VB-TRANSPORT: local shell write failed", kind="transport")

        deadline = None if timeout is None else time.monotonic() + timeout
        self._wait_current(deadline)
        with self._lock:
            cur = self._current
            out = "".join(cur["out"]).rstrip("\n")
            rc = cur["rc"]
            done = cur["done"]
            eof = cur["eof"]
            if self._current is cur:
                self._current = None
        err = ""
        try:
            if err_path.exists():
                err = err_path.read_text(encoding="utf-8", errors="replace").rstrip("\n")
            err_path.unlink(missing_ok=True)
        except OSError:
            pass
        if not done and not eof:
            self._close_locked()
            return CommandResult(124, out, f"command timed out after {timeout}s", kind="timeout")
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
        self._skill_entries: dict[str, UserEntry] = {}
        self._capacity: dict[str, threading.BoundedSemaphore] = {}
        self._local_locks: dict[str, threading.Lock] = {}
        self._skill_gates: dict[str, threading.Lock] = {}
        self._local_sessions: dict[str, _LocalCommandSession] = {}
        self._lock = threading.RLock()
        # spec 资源盘点：进程退出不得留下隧道/常驻 shell（TB 与业务进程同样适用）
        atexit.register(self.close)

    def invalidate_token(self, token: str) -> None:
        """Close and forget cached runtime resources for one token."""
        with self._lock:
            client = self._clients.pop(token, None)
            self._skill_clients.pop(token, None)
            self._skill_entries.pop(token, None)
            session = self._local_sessions.pop(token, None)
            self._capacity.pop(token, None)
        for resource in (client, session):
            if resource is not None:
                try:
                    resource.close()
                except Exception:  # noqa: BLE001
                    logger.debug("invalidating token %s failed", token, exc_info=True)

    def close(self) -> None:
        """Release every per-token client (tunnels + shells) exactly once."""
        with self._lock:
            clients = list(self._clients.values())
            self._clients.clear()
            sessions = list(self._local_sessions.values())
            self._local_sessions.clear()
            self._skill_clients.clear()
            self._skill_entries.clear()
            self._capacity.clear()
        for client in clients:
            try:
                client.close()
            except Exception:  # noqa: BLE001 - best effort on shutdown
                logger.debug("closing client failed", exc_info=True)
        for session in sessions:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                logger.debug("closing local session failed", exc_info=True)

    # -- per-token state -----------------------------------------------------

    def _entry(self, token: str):
        entry = self.registry.by_token(token)
        if entry is None:
            raise LookupError(f"unknown token")
        return entry

    def _targets(self, entry, user: str | None = None) -> ResolvedTargets:
        return resolve(entry, user=user)

    def _remote(self, token: str) -> RemoteClient:
        try:
            entry = self._entry(token)
        except LookupError:
            self.invalidate_token(token)
            raise
        stale = None
        with self._lock:
            client = self._clients.get(token)
            if client is not None and client.entry is not entry:
                stale = client
                client = None
                self._clients.pop(token, None)
            if client is None:
                user = self.registry.user_of(token) or token
                client = RemoteClient(entry, self._targets(entry, user=user), user)
                self._clients[token] = client
                self._capacity.setdefault(
                    token,
                    threading.BoundedSemaphore(entry.runtime.thread_pool_size),
                )
        if stale is not None:
            try:
                stale.close()
            except Exception:  # noqa: BLE001
                logger.debug("closing stale client for %s failed", token, exc_info=True)
        return client

    def _skill(self, token: str) -> SkillClient:
        try:
            entry = self._entry(token)
        except LookupError:
            self.invalidate_token(token)
            raise
        with self._lock:
            client = self._skill_clients.get(token)
            if client is not None and self._skill_entries.get(token) is not entry:
                self._skill_clients.pop(token, None)
                self._skill_entries.pop(token, None)
                client = None
            if client is None:
                user = self.registry.user_of(token) or token
                targets = self._targets(entry, user=user)
                port = (
                    targets.daemon_port
                    if targets.daemon.mode == "local"
                    else targets.local_port
                )
                client = SkillClient(
                    host="127.0.0.1",
                    port=port,
                    timeout=30.0,
                    token=token,
                    log_level=entry.cdslog.log_level,
                    log_max_bytes=entry.cdslog.log_max_bytes,
                )
                self._skill_clients[token] = client
                self._skill_entries[token] = entry
            return client

    def _acquire(self, token: str, entry=None) -> threading.BoundedSemaphore | None:
        """Take one thread-pool slot; returns the semaphore to release later.

        Returning the object (instead of re-looking it up on release) removes
        the "release reads a dict that may be swapped/removed" race and keeps
        acquire/release paired per call.
        """
        if entry is None:
            entry = self._entry(token)
        with self._lock:
            sem = self._capacity.get(token)
            if sem is None:
                sem = threading.BoundedSemaphore(entry.runtime.thread_pool_size)
                self._capacity[token] = sem
        return sem if sem.acquire(blocking=False) else None

    @staticmethod
    def _release(sem: threading.BoundedSemaphore | None) -> None:
        if sem is not None:
            sem.release()

    def _skill_gate(self, token: str) -> threading.Lock:
        """Per-token **delivery** gate for the Skill channel.

        One CIW evaluates one SKILL at a time.  The gate is acquired *before*
        the request leaves the client so that a request still waiting for its
        turn can be withdrawn when the caller's deadline expires; without it
        the request would already sit inside the daemon's kernel backlog and
        would run later even though the client already reported a timeout.
        """
        with self._lock:
            gate = self._skill_gates.get(token)
            if gate is None:
                gate = threading.Lock()
                self._skill_gates[token] = gate
            return gate

    def _local_lock(self, token: str) -> threading.Lock:
        """Per-token serial lock for the persistent local command session."""
        with self._lock:
            lock = self._local_locks.get(token)
            if lock is None:
                lock = threading.Lock()
                self._local_locks[token] = lock
            return lock

    def _local_session(self, token: str, cwd: str | None = None) -> _LocalCommandSession:
        with self._lock:
            session = self._local_sessions.get(token)
            if session is None:
                session = _LocalCommandSession(cwd=cwd)
                self._local_sessions[token] = session
            return session

    # -- three interfaces -----------------------------------------------------

    def execute_skill(self, skill_code: str, timeout: float | None = None, *, token: str) -> VirtuosoResult:
        budget = _effective_timeout(timeout)
        deadline = time.monotonic() + budget
        sem = None
        gate: threading.Lock | None = None
        gate_held = False
        try:
            entry = self._entry(token)
            sem = self._acquire(token, entry)
            if sem is None:
                return VirtuosoResult(status=ExecutionStatus.ERROR, errors=["thread pool exceeded"])
            user = self.registry.user_of(token) or token
            targets = self._targets(entry, user=user)

            # client-side delivery queue: while waiting here nothing has been
            # sent to the daemon, so a timeout can still be withdrawn
            gate = self._skill_gate(token)
            remaining = max(0.0, deadline - time.monotonic())
            if not gate.acquire(timeout=remaining):
                # The delivery state is deliberately not observable: spec v17
                # makes every external Skill timeout look like "result unknown".
                return VirtuosoResult(
                    status=ExecutionStatus.ERROR,
                    errors=["SKILL execution timed out"],
                )
            gate_held = True

            if targets.daemon.mode == "remote":
                self._remote(token).ensure_tunnel(deadline=deadline)
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                return VirtuosoResult(
                    status=ExecutionStatus.ERROR,
                    errors=["SKILL execution timed out"],
                )
            return self._skill(token).execute_skill(skill_code, timeout=remaining)
        except LookupError:
            return VirtuosoResult(status=ExecutionStatus.ERROR, errors=["invalid token"])
        except CapacityExceeded as exc:
            return VirtuosoResult(status=ExecutionStatus.ERROR, errors=[exc.message])
        except RemotePathError as exc:
            return VirtuosoResult(
                status=ExecutionStatus.ERROR, errors=[f"{_VB_PATH}{exc}"]
            )
        except (subprocess.TimeoutExpired, TimeoutError):
            return VirtuosoResult(
                status=ExecutionStatus.ERROR,
                errors=["SKILL execution timed out"],
            )
        except Exception as exc:  # noqa: BLE001
            # transport/tunnel setup failure (e.g. a cold sshd handshake drop);
            # surface as an error result so callers can retry
            return VirtuosoResult(
                status=ExecutionStatus.ERROR,
                errors=[f"Daemon connection failed: {exc}"],
            )
        finally:
            if gate_held and gate is not None:
                gate.release()
            self._release(sem)

    def run_command(self, cmd: str, timeout: int | None = None, *, token: str, parallel: bool = False) -> CommandResult:
        sem = None
        budget: float | None = None
        try:
            entry = self._entry(token)
            sem = self._acquire(token, entry)
            if sem is None:
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded", kind="rejected")
            user = self.registry.user_of(token) or token
            targets = self._targets(entry, user=user)
            budget = _effective_timeout(timeout)
            deadline = time.monotonic() + budget
            if targets.command.mode == "local":
                if parallel:
                    return self._local_command(cmd, budget, cwd=targets.command.root)
                lock = self._local_lock(token)
                if not lock.acquire(timeout=budget):
                    return CommandResult(
                        returncode=124, stdout="",
                        stderr=f"command timed out waiting for the serial command slot after {budget}s",
                        kind="timeout",
                    )
                try:
                    remaining = max(0.0, deadline - time.monotonic())
                    if remaining <= 0:
                        return CommandResult(
                            returncode=124, stdout="",
                            stderr=f"command timed out waiting for the serial command slot after {budget}s",
                            kind="timeout",
                        )
                    return self._local_session(token, cwd=targets.command.root).execute(cmd, remaining)
                finally:
                    lock.release()
            remaining = max(0.0, deadline - time.monotonic())
            if remaining <= 0:
                return CommandResult(
                    returncode=124, stdout="",
                    stderr=f"command timed out before execution after {budget}s",
                    kind="timeout",
                )
            return self._remote(token).run_command(
                cmd, timeout=remaining, parallel=parallel
            )
        except LookupError:
            return CommandResult(returncode=1, stdout="", stderr="invalid token", kind="invalid-token")
        except Exception as exc:  # noqa: BLE001 - mapped onto the kind contract
            return _error_result(exc, budget)
        finally:
            self._release(sem)

    def upload_file(self, local_path: Path, remote_path: str, timeout: int | None = None, *, token: str, recursive: bool = False) -> CommandResult:
        sem = None
        budget = _effective_timeout(timeout)
        try:
            entry = self._entry(token)
            sem = self._acquire(token, entry)
            if sem is None:
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded", kind="rejected")
            user = self.registry.user_of(token) or token
            targets = self._targets(entry, user=user)
            if targets.file.mode == "local":
                return self._local_upload(
                    local_path, remote_path, recursive,
                    root=targets.file.root, budget=budget,
                )
            return self._remote(token).upload_file(
                Path(local_path), remote_path,
                timeout=budget, recursive=recursive,
            )
        except LookupError:
            return CommandResult(returncode=1, stdout="", stderr="invalid token", kind="invalid-token")
        except Exception as exc:  # noqa: BLE001 - mapped onto the kind contract
            return _error_result(exc, budget)
        finally:
            self._release(sem)

    def download_file(self, remote_path: str, local_path: Path, timeout: int | None = None, *, token: str, recursive: bool = False) -> CommandResult:
        sem = None
        budget = _effective_timeout(timeout)
        try:
            entry = self._entry(token)
            sem = self._acquire(token, entry)
            if sem is None:
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded", kind="rejected")
            user = self.registry.user_of(token) or token
            targets = self._targets(entry, user=user)
            if targets.file.mode == "local":
                return self._local_download(
                    remote_path, local_path, recursive,
                    root=targets.file.root, budget=budget,
                )
            return self._remote(token).download_file(
                remote_path, Path(local_path),
                timeout=budget, recursive=recursive,
            )
        except LookupError:
            return CommandResult(returncode=1, stdout="", stderr="invalid token", kind="invalid-token")
        except Exception as exc:  # noqa: BLE001 - mapped onto the kind contract
            return _error_result(exc, budget)
        finally:
            self._release(sem)

    # -- read-only companion query (spec §4.2) ---------------------------------

    def query(self, token: str) -> QueryResult:
        """Return the per-role ``root``/``bin`` facts for one token.

        Read-only: it answers from the in-memory registry snapshot, never
        connects, never caches, never writes, and does not touch the three
        budgets or the delivery queues.  Topology fields are deliberately not
        exposed.  An unknown token is a structured failure:
        ``{"status": "error", "errors": ["invalid token"]}``.
        """
        entry = self.registry.by_token(token)
        if entry is None:
            return QueryResult(
                status=ExecutionStatus.ERROR, errors=["invalid token"]
            )
        user = self.registry.user_of(token) or token
        targets = self._targets(entry, user=user)
        roles: dict[str, RoleQuery] = {}
        for name in ("gui", "daemon", "command", "file", "spectre"):
            configured = getattr(entry.roles, name)
            roles[name] = RoleQuery(
                root=targets.role(name).root,
                bin=getattr(configured, "bin", None) if name == "spectre" else None,
            )
        return QueryResult(status=ExecutionStatus.SUCCESS, roles=roles)

    # -- one-shot role interfaces (gui / spectre) ------------------------------

    def run_gui_command(self, cmd: str, timeout: int | None = None, *, token: str) -> CommandResult:
        """GUI 命令执行：在 gui role 上执行一条一次性命令（无常驻 shell）。"""
        return self._one_shot_role("gui", cmd, timeout, token)

    def run_spectre_command(self, cmd: str, timeout: int | None = None, *, token: str) -> CommandResult:
        """Spectre 命令执行：在 spectre role 上执行一条一次性命令。"""
        return self._one_shot_role("spectre", cmd, timeout, token)

    def _one_shot_role(self, role_name: str, cmd: str, timeout: int | None, token: str) -> CommandResult:
        sem = None
        budget = _effective_timeout(timeout)
        try:
            entry = self._entry(token)
            sem = self._acquire(token, entry)
            if sem is None:
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded", kind="rejected")
            user = self.registry.user_of(token) or token
            targets = self._targets(entry, user=user)
            role = targets.role(role_name)
            if role.mode == "local":
                return self._local_command(cmd, budget, cwd=role.root)
            return self._remote(token).run_one_shot(
                role_name, cmd, timeout=budget
            )
        except LookupError:
            return CommandResult(returncode=1, stdout="", stderr="invalid token", kind="invalid-token")
        except Exception as exc:  # noqa: BLE001 - mapped onto the kind contract
            return _error_result(exc, budget)
        finally:
            self._release(sem)

    # -- local-mode helpers ---------------------------------------------------

    @staticmethod
    def _local_command(cmd: str, timeout: int | None, cwd: str | None = None) -> CommandResult:
        workdir = None
        if cwd:
            workdir = Path(cwd).expanduser()
            workdir.mkdir(parents=True, exist_ok=True)
        try:
            proc = subprocess.run(
                cmd, shell=True, capture_output=True, text=True,
                timeout=timeout, cwd=workdir,
            )
            return CommandResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(returncode=124, stdout="", stderr=f"command timed out after {timeout}s", kind="timeout")
        except OSError as exc:
            return CommandResult(returncode=1, stdout="", stderr=str(exc), kind="path")

    @staticmethod
    def _sha256_file(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _remove_path(path: Path) -> None:
        if not path.exists() and not path.is_symlink():
            return
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path, ignore_errors=True)
        else:
            try:
                path.unlink()
            except OSError:
                pass

    @staticmethod
    def _install_staged(stage: Path, target: Path) -> None:
        """Install a staged item with the shared crash-safe replace.

        Regular files are installed with a single atomic ``os.replace`` (no
        window in which the previous target is missing); directory targets keep
        the backup dance and are cleaned up here.
        """
        install_staged_item(None, stage, target)

    @staticmethod
    def _local_upload(
        local_path: Path,
        remote_path: str,
        recursive: bool,
        root: str | None = None,
        budget: float | None = None,
    ) -> CommandResult:
        src = Path(local_path)
        dst = Path(remote_path).expanduser()
        if not dst.is_absolute() and root:
            dst = Path(root).expanduser() / dst
        if not src.exists() and not src.is_symlink():
            return CommandResult(1, "", f"VB-PATH-NOT-VISIBLE: {src}", kind="path")
        deadline = None if budget is None else time.monotonic() + budget
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if recursive:
                if not src.is_dir():
                    return CommandResult(
                        1, "", f"recursive upload requires a directory: {src}", kind="path"
                    )
                stage = dst.parent / f".vbtmp-{uuid.uuid4().hex}"
                try:
                    _copy_tree_with_deadline(src, stage, deadline)
                    BusinessServer._install_staged(stage, dst)
                finally:
                    BusinessServer._remove_path(stage)
                return CommandResult(0, str(dst), "", kind="command")
            if src.is_dir():
                return CommandResult(
                    1, "", f"directory upload requires recursive=True: {src}", kind="path"
                )
            stage = dst.parent / f".vbtmp-{uuid.uuid4().hex}"
            try:
                _copy_file_with_deadline(src, stage, deadline)
                if BusinessServer._sha256_file(src) != BusinessServer._sha256_file(stage):
                    return CommandResult(
                        1, "", "sha256 mismatch", kind="checksum"
                    )
                BusinessServer._install_staged(stage, dst)
            finally:
                BusinessServer._remove_path(stage)
            return CommandResult(0, str(dst), "", kind="command")
        except _DeadlineExceeded:
            return CommandResult(
                124, "", BusinessServer._timeout_detail(budget), kind="timeout"
            )
        except OSError as exc:
            return CommandResult(1, "", f"VB-PATH-NOT-VISIBLE: {exc}", kind="path")

    @staticmethod
    def _local_download(
        remote_path: str,
        local_path: Path,
        recursive: bool,
        root: str | None = None,
        budget: float | None = None,
    ) -> CommandResult:
        src = Path(remote_path).expanduser()
        if not src.is_absolute() and root:
            src = Path(root).expanduser() / src
        dst = Path(local_path)
        if not src.exists() and not src.is_symlink():
            return CommandResult(1, "", f"VB-PATH-NOT-VISIBLE: {src}", kind="path")
        deadline = None if budget is None else time.monotonic() + budget
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if recursive:
                if not src.is_dir():
                    return CommandResult(
                        1, "", f"recursive download requires a directory: {src}", kind="path"
                    )
                stage = dst.parent / f".vbtmp-{uuid.uuid4().hex}"
                try:
                    _copy_tree_with_deadline(src, stage, deadline)
                    BusinessServer._install_staged(stage, dst)
                finally:
                    BusinessServer._remove_path(stage)
                return CommandResult(0, str(dst), "", kind="command")
            if src.is_dir():
                return CommandResult(
                    1, "", f"directory download requires recursive=True: {src}", kind="path"
                )
            stage = dst.parent / f".vbtmp-{uuid.uuid4().hex}"
            try:
                _copy_file_with_deadline(src, stage, deadline)
                if BusinessServer._sha256_file(src) != BusinessServer._sha256_file(stage):
                    return CommandResult(
                        1, "", "sha256 mismatch", kind="checksum"
                    )
                BusinessServer._install_staged(stage, dst)
            finally:
                BusinessServer._remove_path(stage)
            return CommandResult(0, str(dst), "", kind="command")
        except _DeadlineExceeded:
            return CommandResult(
                124, "", BusinessServer._timeout_detail(budget), kind="timeout"
            )
        except OSError as exc:
            return CommandResult(1, "", f"VB-PATH-NOT-VISIBLE: {exc}", kind="path")

    @staticmethod
    def _timeout_detail(budget: float | None) -> str:
        if budget is None:
            return "transfer timed out"
        return f"command timed out after {budget:g}s"


__all__ = ["BusinessServer"]
