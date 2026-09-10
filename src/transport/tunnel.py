"""Per-token remote side: deploy bottom files, tunnel, command and file ports.

Uses the full SSHRunner (OpenSSH + Paramiko, persistent shell, ControlMaster,
staging/atomic install) restored from the legacy implementation.  The registry
supplies every transport knob.

Role runners follow the legacy pattern: one ``SSHRunner`` per distinct target
host, shared across roles that resolve to the same host.  This keeps the
daemon/deploy, command and file roles independent when the registry pins them
to different hosts, while avoiding duplicate persistent shells on one host.
"""

from __future__ import annotations

import hashlib
import logging
import shlex
import threading
from pathlib import Path

from pyapi.models import CommandResult
from transport.deploy import deploy_files
from transport.registry import UserEntry
from transport.remote_roles import ResolvedTargets
from transport.setup import generate_setup_il
from transport.ssh import SSHRunner

logger = logging.getLogger(__name__)


def _norm_host(host: str | None) -> str:
    return (host or "").strip().rstrip(".").lower()


class RemoteClient:
    """One instance per token; owns that token's SSH connections and locks."""

    def __init__(self, entry: UserEntry, targets: ResolvedTargets, user: str) -> None:
        self.entry = entry
        self.targets = targets
        self.user = user  # user-visible path identity (username is unique)
        self._is_local = entry.mode == "local"

        self._runner_kwargs: dict = {
            "jump_user": targets.jump_user,
            "timeout": 600,
            "connect_timeout": int(entry.runtime.connect_timeout),
            "persistent_shell": True,
            "backend": entry.ssh.backend or "openssh",
            "max_sessions": entry.ssh.max_sessions or 10,
            "proxy_url": entry.ssh.proxy,
            "control_master": entry.ssh.control_master or "auto",
            "tool_override": entry.ssh.tool_override or None,
            "control_identity": entry.token,  # per-token ControlMaster namespace
        }
        self._runners: dict[str, SSHRunner] = {}
        self._parallel_runner: SSHRunner | None = None
        self._serial_lock = threading.Lock()
        self._channel_sem = threading.BoundedSemaphore(entry.runtime.channel_budget)

    # -- role runners --------------------------------------------------------

    def _runner(self, host: str, user: str | None) -> SSHRunner:
        """One SSHRunner per distinct (host, account); reused across roles."""
        key = (_norm_host(host), user or "")
        runner = self._runners.get(key)
        if runner is not None:
            return runner
        jump_host = self.targets.jump_host
        if jump_host and _norm_host(jump_host) == _norm_host(host):
            # The role target itself is the login/jump host; suppress the jump.
            jump_host = None
        kwargs = self._runner_kwargs.copy()
        kwargs.update(host=host, user=user, jump_host=jump_host)
        runner = SSHRunner(**kwargs)
        self._runners[key] = runner
        return runner

    @property
    def skill_runner(self) -> SSHRunner:
        """Runner that reaches the bottom daemon host (deploy + tunnel)."""
        return self._runner(self.targets.skill_host, self.entry.expected.daemon_user)

    @property
    def command_runner(self) -> SSHRunner:
        return self._runner(self.targets.command_host, self.targets.command_user)

    @property
    def file_runner(self) -> SSHRunner:
        return self._runner(self.targets.file_host, self.targets.command_user)

    def _parallel_command_runner(self) -> SSHRunner:
        if self._parallel_runner is None:
            backend = (self.entry.ssh.backend or "openssh").strip().lower()
            if backend == "paramiko":
                # ParamikoSessionBackend multiplexes a session per call; the
                # regular runner is already parallel, no second connection.
                self._parallel_runner = self.command_runner
            else:
                jump_host = self.targets.jump_host
                if jump_host and _norm_host(jump_host) == _norm_host(self.targets.command_host):
                    jump_host = None
                kwargs = self._runner_kwargs.copy()
                kwargs.update(
                    host=self.targets.command_host,
                    user=self.targets.command_user,
                    jump_host=jump_host,
                    persistent_shell=False,  # parallel bypasses the serial shell
                )
                self._parallel_runner = SSHRunner(**kwargs)
        return self._parallel_runner

    # -- deployment ---------------------------------------------------------

    def deploy(self, python_major: int = 3) -> str:
        return deploy_files(
            runner=None if self._is_local else self.skill_runner,
            token=self.entry.token,
            user=self.user,
            scratch_root=self.targets.scratch_root,
            python_major=python_major,
            python_cmd=self.entry.expected.remote_python or "python3",
            port=self.targets.skill_port,
            local=self._is_local,
        )

    # -- tunnel -------------------------------------------------------------

    def ensure_tunnel(self) -> None:
        if self._is_local:
            return
        runner = self.skill_runner
        if runner.is_tunnel_alive:
            return
        runner.start_port_forward(
            self.targets.local_port,
            remote_port=self.targets.skill_port,
        )

    def close(self) -> None:
        runners = list(self._runners.values())
        if self._parallel_runner is not None:
            runners.append(self._parallel_runner)
        seen: set[int] = set()
        for runner in runners:
            if id(runner) in seen:
                continue
            seen.add(id(runner))
            runner.stop_port_forward()
            runner.close()

    # -- command -------------------------------------------------------------

    def run_command(
        self,
        cmd: str,
        timeout: int | None = None,
        parallel: bool = False,
    ) -> CommandResult:
        if parallel:
            if not self._channel_sem.acquire(blocking=False):
                return CommandResult(returncode=1, stdout="", stderr="channel budget exceeded")
            try:
                return self._parallel_command_runner().run_command(cmd, timeout=timeout)
            finally:
                self._channel_sem.release()
        with self._serial_lock:
            return self.command_runner.run_command(cmd, timeout=timeout)

    # -- file (runner already stages + atomically installs; we add digest) -----

    def upload_file(
        self,
        local_path: Path,
        remote_path: str,
        timeout: int | None = None,
        recursive: bool = False,
    ) -> CommandResult:
        if not self._channel_sem.acquire(blocking=False):
            return CommandResult(returncode=1, stdout="", stderr="channel budget exceeded")
        try:
            local_path = Path(local_path)
            if recursive:
                if not local_path.is_dir():
                    return CommandResult(1, "", f"recursive upload requires a directory: {local_path}")
                # directory tar upload; a single sha256 digest is not meaningful
                return self.file_runner.upload(local_path, remote_path, recursive=True, timeout=timeout)
            if local_path.is_dir():
                return CommandResult(1, "", f"directory upload requires recursive=True: {local_path}")
            up = self.file_runner.upload(local_path, remote_path, timeout=timeout)
            if up.returncode != 0:
                return up
            return self._verify(remote_path, local_path.read_bytes())
        finally:
            self._channel_sem.release()

    def download_file(
        self,
        remote_path: str,
        local_path: Path,
        timeout: int | None = None,
        recursive: bool = False,
    ) -> CommandResult:
        if not self._channel_sem.acquire(blocking=False):
            return CommandResult(returncode=1, stdout="", stderr="channel budget exceeded")
        try:
            local_path = Path(local_path)
            if recursive:
                return self.file_runner.download(
                    remote_path, local_path, recursive=True, timeout=timeout
                )
            dl = self.file_runner.download(
                remote_path, local_path, recursive=False, timeout=timeout
            )
            if dl.returncode != 0:
                return dl
            return self._verify(remote_path, local_path.read_bytes())
        finally:
            self._channel_sem.release()

    def _verify(self, remote_path: str, local_bytes: bytes) -> CommandResult:
        local_sha = hashlib.sha256(local_bytes).hexdigest()
        check = self.file_runner.run_command(
            f"sha256sum {shlex.quote(remote_path)}", timeout=60
        )
        if check.returncode != 0:
            return check
        remote_sha = check.stdout.strip().split()[0] if check.stdout.strip() else ""
        if remote_sha != local_sha:
            return CommandResult(
                returncode=1,
                stdout="",
                stderr=f"sha256 mismatch: local={local_sha} remote={remote_sha}",
            )
        return CommandResult(0, remote_path, "")


__all__ = ["RemoteClient"]
