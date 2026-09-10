"""BusinessServer — the middle layer facade.

Upper layer talks only to this object; token is a per-call parameter.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import threading
from pathlib import Path

from pyapi.models import CommandResult, ExecutionStatus, Middle, VirtuosoResult
from transport.registry import Registry, load_registry
from transport.remote_roles import ResolvedTargets, resolve
from transport.runtime_paths import registry_path, set_working_dir
from transport.skill_client import SkillClient
from transport.tunnel import RemoteClient

logger = logging.getLogger(__name__)


class BusinessServer(Middle):
    def __init__(self, work_dir: str | Path | None = None) -> None:
        set_working_dir(work_dir)
        self.registry: Registry = load_registry(registry_path())
        self._clients: dict[str, RemoteClient] = {}
        self._skill_clients: dict[str, SkillClient] = {}
        self._capacity: dict[str, threading.BoundedSemaphore] = {}
        self._lock = threading.Lock()

    # -- per-token state -----------------------------------------------------

    def _entry(self, token: str):
        entry = self.registry.by_token(token)
        if entry is None:
            raise LookupError(f"unknown token")
        return entry

    def _targets(self, entry) -> ResolvedTargets:
        return resolve(entry)

    def _remote(self, token: str) -> RemoteClient:
        with self._lock:
            client = self._clients.get(token)
            if client is None:
                entry = self._entry(token)
                user = self.registry.user_of(token) or token
                client = RemoteClient(entry, self._targets(entry), user)
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

    # -- three interfaces -----------------------------------------------------

    def execute_skill(self, skill_code: str, timeout: float | None = None, *, token: str) -> VirtuosoResult:
        acquired = False
        try:
            entry = self._entry(token)
            if not self._acquire(token, entry):
                return VirtuosoResult(status=ExecutionStatus.ERROR, errors=["thread pool exceeded"])
            acquired = True
            if entry.mode != "local":
                self._remote(token).ensure_tunnel()
            return self._skill(token).execute_skill(skill_code, timeout=timeout)
        except LookupError as exc:
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
                return self._local_command(cmd, timeout)
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
