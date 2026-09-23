"""BusinessServer — the middle layer facade.

Upper layer talks only to this object; token is a per-call parameter.
"""

from __future__ import annotations

import atexit
import hashlib
import logging
import math
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
from common.remote_paths import RemotePathError
from common.registry import Registry, load_registry
from common.validation import ROLE_FIXED_FIELDS, ROLE_GROUP_NAME_RE
from transport.roles import ResolvedTargets, resolve
from common.paths import (
    command_log_file,
    override_work_dir_for_tests,
    registry_path,
    temp_dir,
)
from common.skill_client import SkillClient
from common.ssh import (
    UnknownEffectError,
    _windows_no_window_kwargs,
    configure_command_log,
)
from common.transfer import install_staged_item
from transport.tunnel import RemoteClient

logger = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 30.0  # spec: timeout=None -> 30s for all five interfaces
#: Spec 四层整体架构与接口 §5.8 (Draft v36): platform timeout upper bound.
#: Current Windows socket timers are milliseconds; larger values cannot be
#: represented and previously leaked an OverflowError from the transport.
_MAX_TIMEOUT_SECONDS = 2_147_483.0

# Local transfers stream in bounded chunks so the call deadline is observed
# even when the disk is slow; a single shutil.copy2 cannot be interrupted.
_TRANSFER_CHUNK = 1024 * 1024

# Query may only name execution facts or user groups; connection and
# registration-verification fields are deliberately not addressable.
_QUERY_RESERVED_NAMES = ROLE_FIXED_FIELDS - {"root", "display", "bin"}


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

# Reserved diagnostic prefixes (spec: 四层整体架构与接口 §4.4).  Upper layers may match
# on them; the text after the prefix is diagnostic detail only.
_VB_TRANSPORT = "VB-TRANSPORT: "
_VB_PATH = "VB-PATH-NOT-VISIBLE: "
_VB_UNKNOWN_EFFECT = "VB-UNKNOWN-EFFECT: "


def _effective_timeout(timeout: float | int | None) -> float:
    if timeout is None:
        return _DEFAULT_TIMEOUT
    if isinstance(timeout, bool):
        raise ValueError("timeout must be a positive finite number")
    try:
        value = float(timeout)
    except (TypeError, ValueError) as exc:
        raise ValueError("timeout must be a positive finite number") from exc
    if (
        not math.isfinite(value)
        or value <= 0
        or value > _MAX_TIMEOUT_SECONDS
    ):
        raise ValueError(
            "timeout must be a positive finite number no larger than "
            f"{_MAX_TIMEOUT_SECONDS:g} seconds"
        )
    return value


def _reject_nul_path(value: object, label: str) -> None:
    """Reject NUL before the OS/shell silently truncates the path."""
    if "\x00" in str(value):
        raise RemotePathError(f"{label} contains NUL byte")


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

    #: Upper bound for the shell's startup echo.  Without it a local shell
    #: that never answers makes every call hang forever, which violates the
    #: end-to-end deadline contract (四层整体架构 §5.8).
    _BANNER_TIMEOUT = 15.0

    def __init__(self, cwd: str | None = None, *, err_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._seq = 0
        self._proc = None
        self._reader = None
        self._dead = False
        self._eof = False
        self._current = None
        # 错误临时文件也放在顶层注入的工作目录下（不再直接用系统 temp）
        # 没有显式注入时必须回退到进程级 work root；缺少 work root 是装配
        # 错误，不应该静默污染系统 temp。
        base_dir = Path(err_dir) if err_dir is not None else temp_dir()
        base_dir.mkdir(parents=True, exist_ok=True)
        self._err_dir = Path(
            tempfile.mkdtemp(prefix="local_err_", dir=base_dir)
        )
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
            # Set the working directory with an explicit ``cd`` in the banner
            # probe below.  Passing a transient/invalid path to cmd.exe's
            # ``cwd`` can make it emit a localized startup error while still
            # returning rc=0, which hid the real failure from callers.
            cwd=None,
            **_windows_no_window_kwargs(),
        )
        self._proc = proc
        self._dead = False
        self._eof = False
        self._seq = 0
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()
        try:
            time.sleep(0.1)
            self._drain_banner()
        except Exception:
            self._close_locked()
            raise

    def _drain_banner(self) -> None:
        marker = "__VB_DRAIN_0__"
        if self._cwd and not os.path.isdir(self._cwd):
            raise RuntimeError(
                f"local command cwd does not exist: {self._cwd!r}"
            )
        with self._lock:
            self._current = {"marker": marker, "out": [], "rc": 0, "done": False, "eof": False}
        prefix = ""
        if self._cwd:
            quoted = self._quote_path(self._cwd)
            prefix = f"cd /d {quoted} && " if os.name == "nt" else f"cd {quoted} && "
        self._write_line(prefix + f"echo {marker}")
        self._wait_current(time.monotonic() + self._BANNER_TIMEOUT)
        with self._lock:
            cur = self._current
            ready = bool(cur and (cur["done"] or cur["eof"]))
            output = "".join(cur["out"]) if cur else ""
            self._current = None
        if not ready:
            raise RuntimeError(
                "local command shell did not become ready "
                f"(cwd={self._cwd!r}, output={output[-500:]!r})"
            )

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
        reader = self._reader
        self._proc = None
        self._reader = None
        # 先终止子进程（其 stdout 随进程退出 EOF，读取线程随之结束），再
        # 关闭流。若反过来在阻塞读取期间 close()，Windows 上会等待读锁，
        # 使关闭路径永久挂起。
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:  # noqa: BLE001
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except Exception:  # noqa: BLE001
                    pass
        if reader is not None:
            reader.join(timeout=1)
        if proc is not None and (reader is None or not reader.is_alive()):
            for stream in (proc.stdin, proc.stdout):
                try:
                    if stream:
                        stream.close()
                except OSError:
                    pass

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
            spawn_error = None
            for attempt in range(2):
                try:
                    self._close_locked()
                    self._spawn()
                    spawn_error = None
                    break
                except (OSError, RuntimeError) as exc:
                    spawn_error = exc
                    if attempt == 0:
                        time.sleep(0.1)
            if spawn_error is not None:
                self._dead = True
                return CommandResult(
                    255, "",
                    f"VB-TRANSPORT: local shell unavailable: {spawn_error}",
                    kind="transport",
                )
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
        # 会话被丢弃时才清理自己的错误目录；超时/重建路径只走 _close_locked，
        # 目录要留给下一次调用继续使用。
        shutil.rmtree(self._err_dir, ignore_errors=True)


class BusinessServer(Middle):
    def __init__(self, work_dir: str | Path | None = None) -> None:
        """Work root comes from the ``common.paths`` base (entry initializes it).

        ``work_dir`` is the test/tool convenience that switches the base to an
        explicit directory; production callers pass nothing.
        """
        if work_dir is not None:
            override_work_dir_for_tests(work_dir)
        configure_command_log(command_log_file())
        self.registry: Registry = load_registry(registry_path())
        self._clients: dict[str, RemoteClient] = {}
        self._skill_clients: dict[str, SkillClient] = {}
        self._skill_entries: dict[str, UserEntry] = {}
        self._capacity: dict[str, threading.BoundedSemaphore] = {}
        self._in_flight: dict[str, int] = {}
        self._retire_pending: set[str] = set()
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
            self._in_flight.pop(token, None)
            self._retire_pending.discard(token)
            self._local_locks.pop(token, None)
            self._skill_gates.pop(token, None)
        for resource in (client, session):
            if resource is not None:
                try:
                    resource.close()
                except Exception:  # noqa: BLE001
                    logger.debug("invalidating token %s failed", token, exc_info=True)

    def reload_registry(self) -> None:
        """Explicitly refresh the runtime snapshot and retire stale caches.

        Runtime never rereads ``registry.json`` implicitly.  A control-plane
        deployment on the same filesystem may call this method (or restart the
        business process) after a management update.

        顶层补充 v27: ``/api/process/reload`` 不打断在途请求 —— 快照立即切换
        （新请求按新注册表路由），旧 token 的连接缓存等其 in-flight 归零后
        再关闭。
        """
        fresh = load_registry(registry_path())
        to_close: list[str] = []
        with self._lock:
            self.registry = fresh
            tokens = (
                set(self._clients)
                | set(self._skill_clients)
                | set(self._skill_entries)
                | set(self._local_sessions)
                | set(self._capacity)
            )
            for token in tokens:
                if self._in_flight.get(token, 0) > 0:
                    self._retire_pending.add(token)
                else:
                    to_close.append(token)
        for token in to_close:
            self.invalidate_token(token)

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
            self._local_locks.clear()
            self._skill_gates.clear()
            self._in_flight.clear()
            self._retire_pending.clear()
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
                    connect_timeout=entry.runtime.connect_timeout,
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
            if not sem.acquire(blocking=False):
                return None
            self._in_flight[token] = self._in_flight.get(token, 0) + 1
            return sem

    def _release(
        self,
        sem: threading.BoundedSemaphore | None,
        token: str | None = None,
    ) -> None:
        """Release one in-flight slot; retire a token whose cache is pending."""
        retire = False
        if sem is not None:
            sem.release()
        if token is not None:
            with self._lock:
                left = self._in_flight.get(token, 0) - 1
                if left > 0:
                    self._in_flight[token] = left
                else:
                    self._in_flight.pop(token, None)
                    if token in self._retire_pending:
                        self._retire_pending.discard(token)
                        retire = True
        if retire:
            self.invalidate_token(token)

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
                session = _LocalCommandSession(cwd=cwd, err_dir=temp_dir())
                self._local_sessions[token] = session
            return session

    # -- five business interfaces + read-only query ---------------------------

    def execute_skill(
        self,
        skill_code: str,
        timeout: float | None = None,
        *,
        token: str,
        log_level: str | None = None,
        log_max_bytes: int | None = None,
    ) -> VirtuosoResult:
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
                # The delivery state is deliberately not observable: the
                # frozen contract makes every external Skill timeout look like
                # "result unknown" (四层整体架构与接口 §4.5/§5.8).
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
            return self._skill(token).execute_skill(
                skill_code,
                timeout=remaining,
                log_level=log_level,
                log_max_bytes=log_max_bytes,
            )
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
            self._release(sem, token)

    def run_command(self, cmd: str, timeout: int | None = None, *, token: str, parallel: bool = False) -> CommandResult:
        sem = None
        budget = _effective_timeout(timeout)
        try:
            entry = self._entry(token)
            sem = self._acquire(token, entry)
            if sem is None:
                return CommandResult(returncode=1, stdout="", stderr="thread pool exceeded", kind="rejected")
            user = self.registry.user_of(token) or token
            targets = self._targets(entry, user=user)
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
            self._release(sem, token)

    def upload_file(self, local_path: Path, remote_path: str, timeout: int | None = None, *, token: str, recursive: bool = False) -> CommandResult:
        sem = None
        budget = _effective_timeout(timeout)
        started = time.monotonic()
        try:
            _reject_nul_path(local_path, "local_path")
            _reject_nul_path(remote_path, "remote_path")
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
            remaining = max(0.0, budget - (time.monotonic() - started))
            if remaining <= 0:
                return CommandResult(
                    returncode=124, stdout="",
                    stderr=f"command timed out after {budget:g}s",
                    kind="timeout",
                )
            return self._remote(token).upload_file(
                Path(local_path), remote_path,
                timeout=remaining, recursive=recursive,
            )
        except LookupError:
            return CommandResult(returncode=1, stdout="", stderr="invalid token", kind="invalid-token")
        except Exception as exc:  # noqa: BLE001 - mapped onto the kind contract
            return _error_result(exc, budget)
        finally:
            self._release(sem, token)

    def download_file(self, remote_path: str, local_path: Path, timeout: int | None = None, *, token: str, recursive: bool = False) -> CommandResult:
        sem = None
        budget = _effective_timeout(timeout)
        started = time.monotonic()
        try:
            _reject_nul_path(remote_path, "remote_path")
            _reject_nul_path(local_path, "local_path")
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
            remaining = max(0.0, budget - (time.monotonic() - started))
            if remaining <= 0:
                return CommandResult(
                    returncode=124, stdout="",
                    stderr=f"command timed out after {budget:g}s",
                    kind="timeout",
                )
            return self._remote(token).download_file(
                remote_path, Path(local_path),
                timeout=remaining, recursive=recursive,
            )
        except LookupError:
            return CommandResult(returncode=1, stdout="", stderr="invalid token", kind="invalid-token")
        except Exception as exc:  # noqa: BLE001 - mapped onto the kind contract
            return _error_result(exc, budget)
        finally:
            self._release(sem, token)

    # -- read-only companion query (spec §4.2) ---------------------------------

    def query(
        self,
        *,
        token: str,
        role: str | None = None,
        name: str | None = None,
    ) -> QueryResult:
        """Return the per-role facts for one token.

        Read-only: it answers from the in-memory registry snapshot, never
        connects, never caches, never writes, and does not touch the three
        budgets or the delivery queues.  Topology fields are deliberately not
        exposed.  Optional ``role``/``name`` filters select one role or one
        fact/group.  An unknown token is a structured failure:
        ``{"status": "error", "errors": ["invalid token"]}``.
        """
        role_names = ("gui", "daemon", "command", "file", "spectre")
        if role is not None and role not in role_names:
            raise ValueError(f"unknown role: {role!r}")
        if name is not None:
            if role is None:
                raise ValueError("name requires role")
            if name in _QUERY_RESERVED_NAMES:
                raise ValueError(f"query name is not exposed: {name!r}")
            if name not in {"root", "display", "bin"} and not ROLE_GROUP_NAME_RE.fullmatch(name):
                raise ValueError(f"invalid query name: {name!r}")

        entry = self.registry.by_token(token)
        if entry is None:
            return QueryResult(
                status=ExecutionStatus.ERROR, errors=["invalid token"]
            )
        user = self.registry.user_of(token) or token
        targets = self._targets(entry, user=user)
        roles: dict[str, RoleQuery] = {}
        selected_roles = (role,) if role is not None else role_names
        for role_name in selected_roles:
            configured = getattr(entry.roles, role_name)
            facts: dict[str, object] = {}

            def add_fact(key: str, value: object) -> None:
                if value is not None:
                    facts[key] = value

            if name is None:
                add_fact("root", targets.role(role_name).root)
                if role_name == "gui":
                    add_fact("display", getattr(configured, "display", None))
                if role_name == "spectre":
                    add_fact("bin", getattr(configured, "bin", None))
                for group_name, group_value in (configured.model_extra or {}).items():
                    add_fact(group_name, group_value)
            elif name == "root":
                add_fact("root", targets.role(role_name).root)
            elif name == "display" and role_name == "gui":
                add_fact("display", getattr(configured, "display", None))
            elif name == "bin" and role_name == "spectre":
                add_fact("bin", getattr(configured, "bin", None))
            else:
                add_fact(name, (configured.model_extra or {}).get(name))

            roles[role_name] = RoleQuery(**facts)
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
        started = time.monotonic()
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
            remaining = max(0.0, budget - (time.monotonic() - started))
            if remaining <= 0:
                return CommandResult(
                    returncode=124, stdout="",
                    stderr=f"command timed out after {budget:g}s",
                    kind="timeout",
                )
            return self._remote(token).run_one_shot(
                role_name, cmd, timeout=remaining
            )
        except LookupError:
            return CommandResult(returncode=1, stdout="", stderr="invalid token", kind="invalid-token")
        except Exception as exc:  # noqa: BLE001 - mapped onto the kind contract
            return _error_result(exc, budget)
        finally:
            self._release(sem, token)

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
                **_windows_no_window_kwargs(),
            )
            return CommandResult(proc.returncode, proc.stdout, proc.stderr)
        except subprocess.TimeoutExpired:
            return CommandResult(returncode=124, stdout="", stderr=f"command timed out after {timeout}s", kind="timeout")
        except OSError as exc:
            return CommandResult(returncode=1, stdout="", stderr=str(exc), kind="path")

    @staticmethod
    def _sha256_file(path: Path, *, deadline: float | None = None) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                if deadline is not None and time.monotonic() >= deadline:
                    raise _DeadlineExceeded
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
                if BusinessServer._sha256_file(src, deadline=deadline) != \
                        BusinessServer._sha256_file(stage, deadline=deadline):
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
                if BusinessServer._sha256_file(src, deadline=deadline) != \
                        BusinessServer._sha256_file(stage, deadline=deadline):
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
