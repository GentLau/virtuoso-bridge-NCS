"""Per-token remote side: daemon tunnel, command, file and one-shot role runners.

Only ``mode=remote`` roles are handled here; ``mode=local`` roles are executed
directly by ``BusinessServer`` (no SSH).  One ``SSHRunner`` is created per
resolved endpoint (``ResolvedRole.key``); roles sharing an endpoint share it.
Budgets (thread pool, channel budget) are per-token.
"""

from __future__ import annotations

import hashlib
import logging
import posixpath
import shlex
import threading
import time
from pathlib import Path

from pyapi.models import CommandResult
from transport.deploy import deploy_files
from transport.registry import UserEntry
from transport.remote_paths import RemotePathError
from transport.budgets import CapacityExceeded, TokenBudgets
from transport.roles import ResolvedRole, ResolvedTargets
from transport.ssh import SSHRunner

logger = logging.getLogger(__name__)


def _norm_host(host: str | None) -> str:
    return (host or "").strip().rstrip(".").lower()


def remote_root_path(remote_path: str, root: str) -> str:
    """Resolve a role-relative remote path against that role's root."""
    if remote_path.startswith(("/", "~")):
        return remote_path
    return posixpath.join(root.rstrip("/"), remote_path)


class RemoteClient:
    """One instance per token; owns that token's SSH connections and locks."""

    def __init__(self, entry: UserEntry, targets: ResolvedTargets, user: str) -> None:
        self.entry = entry
        self.targets = targets
        self.user = user  # user-visible path identity (username is unique)

        self._runner_kwargs: dict = {
            "timeout": 600,
            "connect_timeout": int(entry.runtime.connect_timeout),
            "persistent_shell": True,
            "backend": entry.ssh.backend or "paramiko",
            "max_sessions": entry.runtime.channel_budget or 10,
            "control_master": entry.ssh.control_master or "auto",
            "tool_override": entry.ssh.tool_override or None,
            "control_identity": entry.token,  # per-token ControlMaster namespace
        }
        self._runners: dict[str, SSHRunner] = {}
        self._one_shot_runners: dict[str, SSHRunner] = {}
        # runner creation is a check-then-act: without this lock the first
        # burst of concurrent calls creates one SSHRunner per thread.
        self._runner_lock = threading.Lock()
        self._homes: dict[str | None, str] = {}
        self._home_lock = threading.Lock()
        self._serial_lock = threading.Lock()
        self.budgets = TokenBudgets(
            thread_pool_size=entry.runtime.thread_pool_size,
            channel_budget=entry.runtime.channel_budget,
        )
        for role_name in ("gui", "daemon", "command", "file", "spectre"):
            role = targets.role(role_name)
            if role.mode == "remote" and role.key:
                self.budgets.set_endpoint_limit(role.key, role.max_sessions)
        self._tunnel_lease = None
        self._persistent_leases: dict[str, object] = {}
        self._persistent_lease_lock = threading.Lock()
        self._tunnel_lock = threading.Lock()

    # -- role runners --------------------------------------------------------

    def _runner(self, role: ResolvedRole) -> SSHRunner:
        """One SSHRunner per resolved remote endpoint (single-flight)."""
        assert role.mode == "remote", f"role {role.name} is local; no SSH runner"
        assert role.key is not None
        runner = self._runners.get(role.key)
        if runner is not None:
            return runner
        with self._runner_lock:
            runner = self._runners.get(role.key)
            if runner is not None:
                return runner
            jump_host = role.jump_host
            if jump_host and _norm_host(jump_host) == _norm_host(role.host):
                jump_host = None  # the target itself is the jump host
            kwargs = self._runner_kwargs.copy()
            kwargs.update(
                host=role.host, user=role.user, jump_host=jump_host,
                jump_user=role.jump_user, proxy_url=role.proxy,
                max_sessions=self.budgets.endpoint_limit(role.key),
            )
            runner = SSHRunner(**kwargs)
            self._runners[role.key] = runner
            return runner

    def _one_shot_runner(self, role: ResolvedRole) -> SSHRunner:
        """Dedicated one-shot (non-persistent) runner for gui/spectre/parallel."""
        assert role.mode == "remote", f"role {role.name} is local; no SSH runner"
        if (self.entry.ssh.backend or "paramiko").lower() == "paramiko":
            # Paramiko multiplexes a session per call; the regular runner is
            # already parallel, so no second connection/runner is needed.
            return self._runner(role)
        runner = self._one_shot_runners.get(role.name)
        if runner is not None:
            return runner
        with self._runner_lock:
            runner = self._one_shot_runners.get(role.name)
            if runner is not None:
                return runner
            jump_host = role.jump_host
            if jump_host and _norm_host(jump_host) == _norm_host(role.host):
                jump_host = None
            kwargs = self._runner_kwargs.copy()
            kwargs.update(
                host=role.host, user=role.user, jump_host=jump_host,
                jump_user=role.jump_user, proxy_url=role.proxy,
                max_sessions=self.budgets.endpoint_limit(role.key),
                persistent_shell=False,  # 一次性命令，无常驻 shell
            )
            runner = SSHRunner(**kwargs)
            self._one_shot_runners[role.name] = runner
            return runner

    def _channel_denial(self, role: ResolvedRole) -> str:
        return self.budgets.denial_reason(role.key or role.name)

    def _acquire_channel(self, role: ResolvedRole):
        lease = self.budgets.try_acquire_channel(
            endpoint_key=role.key or role.name,
            role_name=role.name,
            role_max_sessions=role.max_sessions,
        )
        if lease is None:
            raise CapacityExceeded(role.name, self._channel_denial(role))
        return lease

    def _acquire_command_channel(self, role: ResolvedRole):
        """Return (lease, persistent).

        The OpenSSH backend may keep one long-lived shell per command endpoint;
        that shell owns a channel for its whole life.  Paramiko opens a fresh
        session per call and therefore needs a per-call lease.
        """
        runner = self.command_runner
        if not getattr(runner, "persistent_shell_enabled", False):
            return self._acquire_channel(role), False
        key = f"command:{role.key or role.name}"
        with self._persistent_lease_lock:
            lease = self._persistent_leases.get(key)
            if lease is None:
                lease = self._acquire_channel(role)
                self._persistent_leases[key] = lease
            return lease, True

    def _run_internal_one_shot(self, role: ResolvedRole, cmd: str, timeout: float):
        lease = self._acquire_channel(role)
        try:
            return self._one_shot_runner(role).run_one_shot(cmd, timeout=timeout)
        finally:
            lease.release()

    def remote_home(self, role: ResolvedRole) -> str:
        """Remote ``$HOME`` for the role's connection (single-flight, cached).

        scp uses the SFTP protocol by default, so ``~`` is NOT shell-expanded
        on the remote side; the middle layer expands it explicitly.  The lookup
        uses a one-shot runner so it can never wedge the persistent command
        shell; failures are cached as "" (callers fall back to the raw root).
        """
        key = role.key
        cached = self._homes.get(key)
        if cached:
            return cached
        with self._home_lock:
            cached = self._homes.get(key)
            if cached:
                return cached
            detail = ""
            try:
                result = self._run_internal_one_shot(
                    role, 'printf "%s" "$HOME"', 15
                )
                cached = result.stdout.strip() if result.returncode == 0 else ""
                if not cached:
                    detail = (
                        result.stderr.strip()
                        or f"rc={result.returncode}"
                    )
            except Exception as exc:  # noqa: BLE001 - reported as a path error
                detail = str(exc)
            if not cached:
                # Never cache a failure: the next call retries.  Returning the
                # raw ``~`` root instead would silently create a literal
                # ``~/.virtuoso-bridge`` directory on the target.
                raise RemotePathError(
                    f"cannot resolve remote $HOME for role {role.name} on "
                    f"{role.host}: {detail or 'empty response'}"
                )
            self._homes[key] = cached
            return cached

    def expanded_root(self, role: ResolvedRole) -> str:
        if role.mode != "remote" or not role.root.startswith("~"):
            return role.root
        return role.root.replace("~", self.remote_home(role), 1)

    def resolve_remote_path(self, role: ResolvedRole, path: str) -> str:
        """Expand ``~`` and resolve a relative path against the role root."""
        if path.startswith("~"):
            path = self.remote_home(role) + path[1:]
        if path.startswith("/"):
            return path  # absolute paths never depend on the role root
        return remote_root_path(path, self.expanded_root(role))

    @property
    def skill_runner(self) -> SSHRunner:
        return self._runner(self.targets.daemon)

    @property
    def command_runner(self) -> SSHRunner:
        return self._runner(self.targets.command)

    @property
    def file_runner(self) -> SSHRunner:
        return self._runner(self.targets.file)

    # -- deployment ---------------------------------------------------------

    def deploy(self, python_major: int = 3) -> str:
        """Deploy bridge files to the daemon role root (local or remote)."""
        role = self.targets.daemon
        runner = self._runner(role) if role.mode == "remote" else None
        return deploy_files(
            runner=runner,
            token=self.entry.token,
            user=self.user,
            scratch_root=self.expanded_root(role),
            python_major=python_major,
            python_cmd=self.entry.roles.daemon.python or "python3",
            port=self.targets.daemon_port,
            local=role.mode == "local",
        )

    # -- tunnel -------------------------------------------------------------

    def ensure_tunnel(self, deadline: float | None = None) -> None:
        if self.targets.daemon.mode == "local":
            return  # local daemon: direct 127.0.0.1 connection, no tunnel
        runner = self.skill_runner
        if runner.is_tunnel_alive:
            return
        with self._tunnel_lock:
            if runner.is_tunnel_alive:
                return
            if self._tunnel_lease is not None:
                self._tunnel_lease.release()
                self._tunnel_lease = None
            lease = self._acquire_channel(self.targets.daemon)
            try:
                runner.start_port_forward(
                    self.targets.local_port,
                    remote_port=self.targets.daemon_port,
                    deadline=deadline,
                )
            except Exception:
                lease.release()
                raise
            self._tunnel_lease = lease

    def close(self) -> None:
        runners = list(self._runners.values()) + list(self._one_shot_runners.values())
        seen: set[int] = set()
        for runner in runners:
            if id(runner) in seen:
                continue
            seen.add(id(runner))
            runner.stop_port_forward()
            runner.close()
        if self._tunnel_lease is not None:
            self._tunnel_lease.release()
            self._tunnel_lease = None
        for lease in list(self._persistent_leases.values()):
            lease.release()
        self._persistent_leases.clear()

    # -- command -------------------------------------------------------------

    def run_command(
        self,
        cmd: str,
        timeout: int | None = None,
        parallel: bool = False,
    ) -> CommandResult:
        role = self.targets.command
        try:
            if parallel:
                lease = self._acquire_channel(role)
                persistent = False
            else:
                lease, persistent = self._acquire_command_channel(role)
        except CapacityExceeded as exc:
            return CommandResult(1, "", exc.message, kind="rejected")
        try:
            if parallel:
                return self._one_shot_runner(role).run_one_shot(
                    cmd, timeout=timeout
                )
            if timeout is None:
                with self._serial_lock:
                    return self.command_runner.run_command(cmd, timeout=None)
            started = time.monotonic()
            if not self._serial_lock.acquire(timeout=max(0.0, float(timeout))):
                return CommandResult(
                    returncode=124, stdout="",
                    stderr=f"command timed out waiting for the serial command slot after {timeout}s",
                    kind="timeout",
                )
            try:
                remaining = float(timeout) - (time.monotonic() - started)
                if remaining <= 0:
                    return CommandResult(
                        returncode=124, stdout="",
                        stderr=f"command timed out waiting for the serial command slot after {timeout}s",
                        kind="timeout",
                    )
                return self.command_runner.run_command(cmd, timeout=remaining)
            finally:
                self._serial_lock.release()
        finally:
            if not persistent:
                lease.release()

    def run_one_shot(self, role_name: str, cmd: str, timeout: int | None = None) -> CommandResult:
        """One-shot command on gui/spectre; occupies the token channel budget."""
        role = self.targets.role(role_name)
        try:
            lease = self._acquire_channel(role)
        except CapacityExceeded as exc:
            return CommandResult(1, "", exc.message, kind="rejected")
        try:
            return self._one_shot_runner(role).run_one_shot(cmd, timeout=timeout)
        finally:
            lease.release()

    # -- file (runner already stages + atomically installs; we add digest) -----

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        timeout: int | None = None,
        recursive: bool = False,
    ) -> CommandResult:
        role = self.targets.file
        try:
            lease = self._acquire_channel(role)
        except CapacityExceeded as exc:
            return CommandResult(1, "", exc.message, kind="rejected")
        deadline = time.monotonic() + float(timeout) if timeout else None
        try:
            local_path = Path(local_path)
            remote_path = self.resolve_remote_path(role, remote_path)
            if recursive:
                if not local_path.is_dir():
                    return CommandResult(
                        1, "", f"recursive upload requires a directory: {local_path}",
                        kind="path",
                    )
                return self.file_runner.upload(
                    local_path, remote_path, recursive=True, timeout=timeout
                )
            if local_path.is_dir():
                return CommandResult(
                    1, "", f"directory upload requires recursive=True: {local_path}",
                    kind="path",
                )
            up = self.file_runner.upload(local_path, remote_path, timeout=timeout)
            if up.returncode != 0:
                return up
            return self._verify(remote_path, local_path.read_bytes(), deadline=deadline)
        finally:
            lease.release()

    def download_file(
        self,
        remote_path: str,
        local_path: Path,
        timeout: int | None = None,
        recursive: bool = False,
    ) -> CommandResult:
        role = self.targets.file
        try:
            lease = self._acquire_channel(role)
        except CapacityExceeded as exc:
            return CommandResult(1, "", exc.message, kind="rejected")
        deadline = time.monotonic() + float(timeout) if timeout else None
        try:
            local_path = Path(local_path)
            remote_path = self.resolve_remote_path(role, remote_path)
            if recursive:
                return self.file_runner.download(
                    remote_path, local_path, recursive=True, timeout=timeout
                )
            dl = self.file_runner.download(
                remote_path, local_path, recursive=False, timeout=timeout
            )
            if dl.returncode != 0:
                return dl
            return self._verify(remote_path, local_path.read_bytes(), deadline=deadline)
        finally:
            lease.release()

    def _verify(
        self, remote_path: str, local_bytes: bytes, deadline: float | None = None
    ) -> CommandResult:
        """Verify the remote digest on a one-shot channel.

        The digest check must not sit behind the token's persistent command
        shell: a long-running command there would turn every file transfer
        into a timeout (observed as ``channel budget``/timeout noise under
        load).  A one-shot call is never multiplexed through that shell.
        """
        local_sha = hashlib.sha256(local_bytes).hexdigest()
        budget = 60.0
        if deadline is not None:
            budget = max(0.0, min(budget, deadline - time.monotonic()))
            if budget <= 0.0:
                return CommandResult(
                    returncode=124, stdout="",
                    stderr="digest verification skipped: request deadline exhausted",
                    kind="timeout",
                )
        check = self._one_shot_runner(self.targets.file).run_one_shot(
            f"sha256sum {shlex.quote(remote_path)}", timeout=budget
        )
        if check.returncode != 0:
            return check
        remote_sha = check.stdout.strip().split()[0] if check.stdout.strip() else ""
        if remote_sha != local_sha:
            return CommandResult(
                returncode=1, stdout="",
                stderr=f"sha256 mismatch: local={local_sha} remote={remote_sha}",
                kind="checksum",
            )
        return CommandResult(0, remote_path, "")


__all__ = ["RemoteClient", "remote_root_path"]
