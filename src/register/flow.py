"""Six-step registration flow (setup phase).

Spec: ``多用户与注册`` §3.2 and ``路由设计``.

1. 申请       submit canonical params (token generated here, no side effect)
2. 本地校验   user-name / port de-dup against the registry (no network)
3. 探测       per-role probes: mode=local runs locally, mode=remote via SSH
4. 部署       upload daemon/il/setup to the daemon role root, prompt CIW load
5. 连通性     daemon reachable + token match + dual smoke + fingerprint
6. 写注册表   the only durable write point

Roles are probed on their own role (python/port/root -> daemon; command smoke
-> command; file root -> file; bin -> spectre).  Spectre probe failures are
WARNING-only.  Registration never persists partial state.
"""

from __future__ import annotations

import getpass
import logging
import shlex
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path

from common.registry import (
    CdsLog,
    canonical_host,
    DaemonRoleConfig,
    ModeConfig,
    Registry,
    RegistryError,
    RoleConfig,
    Roles,
    RootConfig,
    Runtime,
    SpectreRoleConfig,
    Ssh,
    SshDefaults,
    UserEntry,
    endpoint_key,
)
from register.candidate import (
    CandidateRole,
    fingerprint_conflicts_candidate,
    resolve_candidate,
    validate_commit_shape,
)
from register.reservation import Reservation, ReservationTable
from register import probe as probes
from register.models import (
    ConnectivityReport,
    ProbeResult,
    RegistrationRequest,
    RegistrationState,
)
from common.deploy import deploy_files
from common.remote_paths import identity_path
from common.skill_client import SkillClient
from common.ssh import SSHRunner

logger = logging.getLogger(__name__)

_LOCAL_DEFAULT_PORT = 65432
_BUSINESS_ROLES = ("gui", "daemon", "command", "file")
_ALL_ROLES = ("gui", "daemon", "command", "file", "spectre")


class RegistrationProbeError(RuntimeError):
    """A required probe failed; registration aborts without persisting."""


STEP_BUDGET_SECONDS = 30.0  # one independent budget per registration step (spec v17)


class StepBudget:
    """One end-to-end deadline per registration step (配置一览 §6.4 / 架构 §5.8).

    Every network phase of a step spends from the same budget; a phase never
    restarts the window, and retries inside a phase share what is left.
    """

    def __init__(self, label: str, seconds: float = STEP_BUDGET_SECONDS) -> None:
        self.label = label
        self.seconds = float(seconds)
        self.deadline = time.monotonic() + self.seconds

    def remaining(self, per_call: float | None = None) -> float:
        # never hand out more than the step budget itself (float safety)
        left = min(self.deadline - time.monotonic(), self.seconds)
        if left <= 0:
            raise RegistrationProbeError(
                f"{self.label} deadline ({self.seconds:g}s) exhausted"
            )
        return left if per_call is None else min(left, float(per_call))

    def expired(self) -> bool:
        return time.monotonic() >= self.deadline


class _BudgetedRunner:
    """Wrap an ``SSHRunner`` so every call spends from one step budget."""

    def __init__(self, runner: SSHRunner, budget: StepBudget) -> None:
        self._runner = runner
        self._budget = budget

    def run_command(self, cmd: str, timeout: float | None = None):
        return self._runner.run_command(cmd, timeout=self._budget.remaining(timeout))

    def upload_text(self, text: str, remote_path: str, timeout: float | None = None):
        return self._runner.upload_text(
            text, remote_path, timeout=self._budget.remaining(timeout)
        )

    def upload(self, *args, timeout: float | None = None, **kwargs):
        return self._runner.upload(
            *args, timeout=self._budget.remaining(timeout), **kwargs
        )

    def download(self, *args, timeout: float | None = None, **kwargs):
        return self._runner.download(
            *args, timeout=self._budget.remaining(timeout), **kwargs
        )

    def __getattr__(self, name):  # upload/download/close/... pass through
        return getattr(self._runner, name)


# -- step 2: local validation ------------------------------------------------

def daemon_scope_of_request(request: RegistrationRequest) -> str:
    """Uniqueness scope of the candidate daemon port: canonical host, or "local"."""
    role = request.roles.daemon
    mode = role.mode or request.mode.default
    if mode == "local":
        return "local"
    host = role.host or request.ssh.default.host
    return canonical_host(host) or "local"


def daemon_scope_of_entry(entry: UserEntry, user: str) -> str:
    """Same scope computed for an already-registered entry."""
    targets = resolve_candidate(entry, user)
    if targets.daemon.mode == "local":
        return "local"
    return canonical_host(targets.daemon.host) or "local"


def validate_local(registry: Registry, request: RegistrationRequest, token: str | None = None) -> list[str]:
    """Pure-local checks: user/token de-dup + port de-dup with correct scope.

    ``daemon_port`` is unique **per daemon target host** (two hosts may use the
    same number); ``local_port`` is unique on this machine (配置一览 §6.4).
    """
    errors: list[str] = []
    if registry.get(request.user) is not None:
        errors.append(f"user {request.user!r} is already registered")
    candidate_token = token or request.token
    holder = registry.user_of(candidate_token) if candidate_token else None
    if holder is not None and holder != request.user:
        errors.append(f"token {candidate_token!r} already belongs to user {holder!r}")

    scope = daemon_scope_of_request(request)
    daemon_port = request.roles.daemon.daemon_port
    local_port = request.roles.daemon.local_port
    for name, entry in registry.entries():
        if entry.roles.daemon.daemon_port is not None and daemon_port is not None:
            if entry.roles.daemon.daemon_port == daemon_port and \
                    daemon_scope_of_entry(entry, name) == scope:
                errors.append(
                    f"daemon port {daemon_port} conflicts with user {name!r} "
                    f"on {scope}"
                )
        if entry.roles.daemon.local_port is not None and local_port is not None:
            if entry.roles.daemon.local_port == local_port:
                errors.append(f"local port {local_port} conflicts with user {name!r}")
    return errors


# -- helpers -------------------------------------------------------------------

def validate_final(registry: Registry, entry: UserEntry, user: str) -> list[str]:
    """Step 6 re-check with the *final* ports (配置一览 §6.4 commit 冲突)."""
    errors: list[str] = []
    if registry.get(user) is not None:
        errors.append(f"user {user!r} is already registered")
    holder = registry.user_of(entry.token)
    if holder is not None and holder != user:
        errors.append(f"token {entry.token!r} already belongs to user {holder!r}")
    scope = daemon_scope_of_entry(entry, user)
    daemon_port = entry.roles.daemon.daemon_port
    local_port = entry.roles.daemon.local_port
    for name, existing in registry.entries():
        if (existing.roles.daemon.daemon_port is not None and daemon_port is not None
                and existing.roles.daemon.daemon_port == daemon_port
                and daemon_scope_of_entry(existing, name) == scope):
            errors.append(f"daemon port {daemon_port} conflicts with user {name!r} on {scope}")
        if (existing.roles.daemon.local_port is not None and local_port is not None
                and existing.roles.daemon.local_port == local_port):
            errors.append(f"local port {local_port} conflicts with user {name!r}")
    return errors


def _resolve_remote_scratch(runner, scratch_root: str) -> str:
    if not scratch_root.startswith("~"):
        return scratch_root
    result = runner.run_command('printf "%s" "$HOME"', timeout=10)
    home = result.stdout.strip()
    if result.returncode == 0 and home:
        return scratch_root.replace("~", home, 1)
    raise RegistrationProbeError("cannot resolve remote $HOME for role root")


def _build_entry(request: RegistrationRequest, token: str) -> UserEntry:
    entry = UserEntry(
        token=token,
        mode=ModeConfig(default=request.mode.default),
        ssh=Ssh(
            default=SshDefaults(
                host=request.ssh.default.host, user=request.ssh.default.user,
                jump_host=request.ssh.default.jump_host,
                jump_user=request.ssh.default.jump_user,
                proxy=request.ssh.default.proxy,
            )
        ),
        root=RootConfig(default=request.root.default),
        roles=Roles(
            gui=RoleConfig(**{k: v for k, v in request.roles.gui.model_dump().items() if v is not None}),
            daemon=DaemonRoleConfig(**{k: v for k, v in request.roles.daemon.model_dump().items() if v is not None}),
            command=RoleConfig(**{k: v for k, v in request.roles.command.model_dump().items() if v is not None}),
            file=RoleConfig(**{k: v for k, v in request.roles.file.model_dump().items() if v is not None}),
            spectre=SpectreRoleConfig(**{k: v for k, v in request.roles.spectre.model_dump().items() if v is not None}),
        ),
    )
    _apply_policies(request, entry)
    return entry


def _apply_policies(request: RegistrationRequest, entry: UserEntry) -> None:
    if request.ssh_backend:
        entry.ssh.backend = request.ssh_backend
    if request.ssh_control_master:
        entry.ssh.control_master = request.ssh_control_master
    if request.ssh_tool_override:
        entry.ssh.tool_override = dict(request.ssh_tool_override)
    if request.thread_pool_size is not None:
        entry.runtime.thread_pool_size = request.thread_pool_size
    if request.channel_budget is not None:
        entry.runtime.channel_budget = request.channel_budget
    if request.connect_timeout is not None:
        entry.runtime.connect_timeout = request.connect_timeout
    if request.log_level:
        entry.cdslog.log_level = request.log_level
    if request.log_max_bytes is not None:
        entry.cdslog.log_max_bytes = request.log_max_bytes


def _new_runner(role: CandidateRole, token: str) -> SSHRunner:
    """One SSH session per target for the whole registration.

    Registration runs 20+ small probes; paying a fresh SSH handshake for each
    of them is what made a real (Windows → jump → wsl) registration take
    minutes.  The runner therefore keeps one login shell per endpoint and
    multiplexes nothing: ``control_master="disable"`` (OpenSSH multiplexing is
    unavailable on Windows and useless here) + ``persistent_shell=True``.
    """
    return SSHRunner(
        host=role.host,
        user=role.user,
        jump_host=role.jump_host,
        jump_user=role.jump_user,
        proxy_url=role.proxy,
        control_identity=token,
        control_master="disable",
        persistent_shell=True,
    )


def _local_role_checks(role: CandidateRole) -> str:
    """Command availability + root writability for a local role.

    Returns the expanded local root (stored back into the registry entry).
    """
    proc = subprocess.run(
        "echo vb-ok", shell=True, capture_output=True, text=True, timeout=15
    )
    if proc.returncode != 0 or proc.stdout.strip() != "vb-ok":
        raise RegistrationProbeError(
            f"local role {role.name} command probe failed: rc={proc.returncode}"
        )
    root = Path(role.root).expanduser()
    if not probes.local_path_writable(root):
        raise RegistrationProbeError(
            f"role {role.name} root not writable locally: {root}"
        )
    return str(root.resolve())


def _remote_role_checks(runner: SSHRunner, role: CandidateRole) -> str:
    """Command availability + root writability for a remote role.

    Returns the resolved absolute root (stored back into the registry entry).
    """
    smoke = runner.run_command("echo vb-ok", timeout=15)
    if smoke.returncode != 0 or smoke.stdout.strip() != "vb-ok":
        raise RegistrationProbeError(
            f"role {role.name} command probe failed on {role.host}: "
            f"rc={smoke.returncode} err={smoke.stderr.strip()}"
        )
    root = _resolve_remote_scratch(runner, role.root)
    if not root.startswith("/"):
        raise RegistrationProbeError(
            f"role {role.name} root must resolve to an absolute path: {root}"
        )
    if not probes.remote_path_writable(runner, root):
        raise RegistrationProbeError(
            f"role {role.name} root not writable on {role.host}: {root}"
        )
    return root


def _probe(
    request: RegistrationRequest,
    token: str,
    reserved_ports: set[int] | None = None,
    reserved_local_ports: set[int] | None = None,
) -> ProbeResult:
    entry = _build_entry(request, token)
    user = request.user
    targets = resolve_candidate(entry, user)
    warnings: list[str] = []
    runners: dict[str, SSHRunner] = {}
    role_runners: dict[str, SSHRunner] = {}
    budget = StepBudget("step 3 (probe)")   # same mechanism as step 5
    reserved_ports = set(reserved_ports or ())
    reserved_local_ports = set(reserved_local_ports or ())

    def close_all():
        seen_ids: set[int] = set()
        for runner in list(runners.values()):
            if id(runner) in seen_ids:
                continue
            seen_ids.add(id(runner))
            try:
                runner.close()
            except Exception:
                pass

    try:
        for name in _ALL_ROLES:
            role = targets.role(name)
            entry_role = getattr(entry.roles, name)
            try:
                if role.mode == "local":
                    entry_role.root = _local_role_checks(role)
                    # §2.3: local role 无 endpoint，expected_fingerprint 必须为 null
                    entry_role.expected_fingerprint = None
                    continue
                if not probes.ssh_port_is_22(role.host):
                    raise RegistrationProbeError(
                        f"role {name} SSH target must resolve to port 22: {role.host}"
                    )
                if role.jump_host and not probes.ssh_port_is_22(role.jump_host):
                    raise RegistrationProbeError(
                        f"role {name} jump host must resolve to port 22: {role.jump_host}"
                    )
                endpoint = endpoint_key(role.host, role.user, role.jump_host,
                                        role.jump_user, role.proxy)
                runner = runners.get(endpoint)
                if runner is None:
                    # first role on this endpoint: pay the handshake once
                    runner = _new_runner(role, token)
                    runners[endpoint] = runner
                    if not runner.test_connection(budget.remaining(15.0)):
                        raise RegistrationProbeError(
                            f"ssh unreachable for {name} role: {role.host}"
                        )
                role_runners[name] = runner
                fp = probes.host_key_fingerprint(role.host)
                explicit_fp = getattr(request.roles, name).expected_fingerprint
                if fp is None and explicit_fp:
                    fp = probes.scan_host_key_fingerprint(role.host)
                if not fp:
                    raise RegistrationProbeError(
                        f"cannot obtain SSH host key fingerprint for {name} role "
                        f"{role.host} (add it to known_hosts out-of-band first)"
                    )
                if explicit_fp and fp != explicit_fp:
                    raise RegistrationProbeError(
                        f"{name} role host-key fingerprint mismatch on "
                        f"{role.host}: expected {explicit_fp}, got {fp}"
                    )
                entry_role.expected_fingerprint = fp
                entry_role.root = _remote_role_checks(_BudgetedRunner(runner, budget), role)
            except RegistrationProbeError as exc:
                if name == "spectre":
                    entry_role.root = None
                    entry_role.expected_fingerprint = None
                    entry_role.bin = None
                    warnings.append(f"{exc} (non-blocking)")
                    continue
                raise
        # daemon-specific environment probes spend the same step budget
        daemon = targets.daemon
        python_major: int | None = None
        if daemon.mode == "local":
            explicit_python = request.roles.daemon.python
            if explicit_python:
                if not probes.local_executable_exists(explicit_python):
                    raise RegistrationProbeError(
                        f"explicit daemon python is not executable: {explicit_python}"
                    )
                python_major = probes.local_python_major(explicit_python)
                if python_major is None:
                    raise RegistrationProbeError(
                        f"cannot determine explicit daemon python major: {explicit_python}"
                    )
                python_cmd = explicit_python
            else:
                python_cmd = sys.executable
                python_major = sys.version_info.major
            entry.roles.daemon.python = python_cmd
            entry.roles.daemon.expected_hostname = socket.gethostname()
            entry.roles.daemon.expected_user = getpass.getuser()
            # 配置一览 §6.4: local 模式下 daemon_port 与 local_port 是同一个
            # 候选端口——任一缺省用同一个值生成并同步写入，双值必须相等。
            requested_daemon_port = request.roles.daemon.daemon_port
            requested_local_port = request.roles.daemon.local_port
            if (
                requested_daemon_port is not None
                and requested_local_port is not None
                and requested_daemon_port != requested_local_port
            ):
                raise RegistrationProbeError(
                    "daemon role is local: daemon_port and local_port are the same "
                    f"candidate port (got daemon_port={requested_daemon_port}, "
                    f"local_port={requested_local_port})"
                )
            explicit_port = (
                requested_daemon_port is not None or requested_local_port is not None
            )
            joint_port = (
                requested_daemon_port or requested_local_port or _LOCAL_DEFAULT_PORT
            )
            if (
                joint_port in reserved_local_ports
                or not probes.local_port_free(joint_port)
            ):
                if explicit_port:
                    raise RegistrationProbeError(
                        f"daemon port {joint_port} is not usable locally"
                    )
                replacement = probes.allocate_local_port(
                    reserved=reserved_local_ports
                )
                if replacement is None:
                    raise RegistrationProbeError(
                        "no free local daemon port found"
                    )
                joint_port = replacement
            entry.roles.daemon.daemon_port = joint_port
            entry.roles.daemon.local_port = joint_port
        else:
            runner = _BudgetedRunner(role_runners["daemon"], budget)
            explicit_python = request.roles.daemon.python
            if explicit_python:
                if not probes.remote_executable_exists(runner, explicit_python):
                    raise RegistrationProbeError(
                        f"explicit daemon python is not executable on "
                        f"{daemon.host}: {explicit_python}"
                    )
                python_major = probes.remote_python_major(runner, explicit_python)
                if python_major is None:
                    raise RegistrationProbeError(
                        f"cannot determine explicit daemon python major on "
                        f"{daemon.host}: {explicit_python}"
                    )
                python_cmd = explicit_python
            else:
                python = probes.detect_remote_python(runner)
                if python is None:
                    raise RegistrationProbeError(
                        f"no usable python found on daemon role {daemon.host}"
                    )
                python_cmd, python_major = python
            entry.roles.daemon.python = python_cmd
            hostname = probes.remote_hostname(runner)
            if not hostname:
                raise RegistrationProbeError(f"cannot resolve daemon hostname on {daemon.host}")
            entry.roles.daemon.expected_hostname = hostname
            daemon_user = probes.remote_user(runner)
            if not daemon_user:
                raise RegistrationProbeError(
                    f"cannot resolve daemon user on {daemon.host}"
                )
            entry.roles.daemon.expected_user = daemon_user
            if request.roles.daemon.daemon_port is not None:
                if request.roles.daemon.daemon_port in reserved_ports:
                    raise RegistrationProbeError(
                        f"daemon port {request.roles.daemon.daemon_port} is reserved "
                        f"by another registration in progress"
                    )
                if not probes.port_free_on_remote(
                    runner, request.roles.daemon.daemon_port, python_cmd
                ):
                    raise RegistrationProbeError(
                        f"daemon port {request.roles.daemon.daemon_port} already in use "
                        f"on {daemon.host}"
                    )
                entry.roles.daemon.daemon_port = request.roles.daemon.daemon_port
            else:
                allocated = probes.allocate_remote_port(
                    runner, python_cmd, reserved=reserved_ports
                )
                if allocated is None:
                    raise RegistrationProbeError(
                        f"no free remote daemon port found on {daemon.host}"
                    )
                entry.roles.daemon.daemon_port = allocated
            local_port = request.roles.daemon.local_port
            if local_port is not None:
                if local_port in reserved_local_ports:
                    raise RegistrationProbeError(
                        f"local port {local_port} is reserved by another "
                        f"registration in progress"
                    )
                if not probes.local_port_free(local_port):
                    raise RegistrationProbeError(f"local port {local_port} is not usable")
            else:
                local_port = probes.allocate_local_port(reserved=reserved_local_ports)
                if local_port is None:
                    raise RegistrationProbeError("no free local tunnel port found")
            entry.roles.daemon.local_port = local_port

        # spectre bin (warning-only)
        spectre_role = targets.spectre
        def nullify_spectre(reason: str | None = None) -> None:
            """§6.2: spectre 探测失败时 root/fingerprint/bin 一并提交为 null。"""
            entry.roles.spectre.root = None
            entry.roles.spectre.expected_fingerprint = None
            entry.roles.spectre.bin = None
            if reason:
                warnings.append(reason)

        if entry.roles.spectre.root is None:
            pass  # prior spectre probe failure is warning-only; keep binomial null
        elif spectre_role.mode == "local":
            if request.roles.spectre.bin:
                if probes.local_executable_exists(request.roles.spectre.bin):
                    entry.roles.spectre.bin = request.roles.spectre.bin
                else:
                    nullify_spectre(
                        f"spectre bin not usable locally: {request.roles.spectre.bin} "
                        f"(non-blocking)"
                    )
            else:
                detected = probes.detect_local_spectre()
                if detected:
                    entry.roles.spectre.bin = detected
                else:
                    nullify_spectre("no usable spectre found locally (non-blocking)")
        else:
            raw_runner = role_runners.get("spectre")
            runner = _BudgetedRunner(raw_runner, budget) if raw_runner is not None else None
            if runner is not None:
                if request.roles.spectre.bin:
                    if probes.remote_executable_exists(runner, request.roles.spectre.bin):
                        entry.roles.spectre.bin = request.roles.spectre.bin
                    else:
                        nullify_spectre(
                            f"spectre bin not usable on {spectre_role.host}: "
                            f"{request.roles.spectre.bin} (non-blocking)"
                        )
                else:
                    detected = probes.detect_remote_spectre(runner)
                    if detected:
                        entry.roles.spectre.bin = detected
                    else:
                        nullify_spectre(
                            f"no usable spectre found on {spectre_role.host} (non-blocking)"
                        )

        # endpoint-fingerprint consistency across roles sharing an endpoint
        conflicts = fingerprint_conflicts_candidate(entry, user)
        if conflicts:
            raise RegistrationProbeError("; ".join(conflicts))

        # the final registry is runtime-ready: every root is an absolute path;
        # the application-time fallback is not persisted.
        entry.root.default = None
        assert python_major in (2, 3)
        return ProbeResult(entry=entry, python_major=python_major, warnings=warnings)
    finally:
        close_all()


def probe_user(
    request: RegistrationRequest,
    *,
    token: str,
    reserved_ports: set[int] | None = None,
    reserved_local_ports: set[int] | None = None,
) -> ProbeResult:
    """Step 3: probe and build a candidate entry.  Never touches the registry."""
    return _probe(
        request, token,
        reserved_ports=reserved_ports,
        reserved_local_ports=reserved_local_ports,
    )


# -- step 4: deploy ------------------------------------------------------------

def deploy_user(entry: UserEntry, python_major: int, user: str, budget: StepBudget | None = None) -> str:
    """Deploy daemon/il/setup to the daemon role root; return the setup path."""
    targets = resolve_candidate(entry, user)
    daemon = targets.daemon
    runner = None
    if daemon.mode == "remote":
        runner = _new_runner(daemon, entry.token)
        if budget is not None:
            runner = _BudgetedRunner(runner, budget)
    try:
        if budget is not None:
            budget.remaining()
        result = deploy_files(
            runner=runner,
            token=entry.token,
            user=user,
            scratch_root=daemon.root,
            python_major=python_major,
            python_cmd=entry.roles.daemon.python or "python3",
            port=targets.daemon_port,
            local=daemon.mode == "local",
        )
        if budget is not None:
            budget.remaining()
        return result
    finally:
        if runner is not None:
            runner.close()


# -- step 5: connectivity -------------------------------------------------------

def _short_host_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().split(".")[0].lower() == b.strip().split(".")[0].lower()


def identity_warnings(
    identity_text: str, expected_hostname: str | None, expected_user: str | None
) -> list[str]:
    """Compare the daemon identity file with the expected baselines.

    spec 多用户与注册 §3.1 步 5：banner hostname / daemon user 与 ``expected_*``
    不一致只记 WARNING，不阻断注册。
    """
    values: dict[str, str] = {}
    for line in identity_text.splitlines():
        if "=" in line:
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    warnings: list[str] = []
    host = values.get("host") or None
    if host and expected_hostname and not _short_host_match(host, expected_hostname):
        warnings.append(
            f"daemon banner host {host!r} differs from expected {expected_hostname!r}"
        )
    actual_user = values.get("user") or None
    if actual_user and expected_user and actual_user != expected_user:
        warnings.append(
            f"daemon user {actual_user!r} differs from expected {expected_user!r}"
        )
    return warnings


def identity_user(identity_text: str) -> str | None:
    """Daemon user recorded in the identity file (``user=`` line)."""
    for line in identity_text.splitlines():
        if line.startswith("user="):
            return line[len("user="):].strip() or None
    return None


def _identity_text(entry: UserEntry, user: str, budget: StepBudget | None = None) -> str | None:
    targets = resolve_candidate(entry, user)
    path = identity_path(user, targets.daemon.root)
    try:
        if targets.daemon.mode == "local":
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        else:
            runner = _new_runner(targets.daemon, entry.token)
            if budget is not None:
                runner = _BudgetedRunner(runner, budget)
            try:
                result = runner.run_command(f"cat {shlex.quote(path)}", timeout=10)
            finally:
                runner.close()
            text = result.stdout if result.returncode == 0 else ""
        return text or None
    except (OSError, RuntimeError):
        return None


def _banner_hostname(
    entry: UserEntry,
    user: str,
    budget: StepBudget | None = None,
    identity_text: str | None = None,
) -> str | None:
    text = identity_text if identity_text is not None else _identity_text(entry, user, budget=budget) or ""
    for line in text.splitlines():
        if line.startswith("host="):
            return line[len("host="):].strip() or None
    return None


def test_connectivity(entry: UserEntry, user: str) -> ConnectivityReport:
    """Step 5: daemon reachable + token match + fingerprints + dual smoke."""
    token = entry.token
    warnings: list[str] = []
    detail: list[str] = []
    targets = resolve_candidate(entry, user)
    daemon = targets.daemon
    budget = StepBudget("step 5 (connectivity)")

    skill_port = targets.daemon_port if daemon.mode == "local" else targets.local_port
    skill_client = SkillClient(
        host="127.0.0.1",
        port=skill_port,
        timeout=budget.remaining(30.0),
        token=token,
        log_level=entry.cdslog.log_level,
        log_max_bytes=entry.cdslog.log_max_bytes,
    )

    fingerprint_ok = True
    tunnel_runner = None
    command_runner = None
    try:
        # command smoke on the command role
        command_role = targets.command
        if command_role.mode == "local":
            proc = subprocess.run(
                "echo vb-ok", shell=True, capture_output=True, text=True, timeout=15
            )
            command_ok = proc.returncode == 0 and proc.stdout.strip() == "vb-ok"
            if not command_ok:
                detail.append(f"command={proc.returncode}:{proc.stderr.strip()}")
        else:
            command_runner = _new_runner(command_role, token)
            result = _BudgetedRunner(command_runner, budget).run_command("echo vb-ok")
            command_ok = result.returncode == 0 and result.stdout.strip() == "vb-ok"
            if not command_ok:
                detail.append(f"command={result.returncode}:{result.stderr.strip()}")

        # per-role fingerprint comparison (remote roles only)
        for name in _ALL_ROLES:
            role = targets.role(name)
            expected = getattr(entry.roles, name).expected_fingerprint
            if role.mode != "remote" or not expected:
                continue
            current = probes.host_key_fingerprint(role.host)
            if current != expected:
                message = (
                    f"{name} role host key mismatch for {role.host}: "
                    f"current={current} expected={expected}"
                )
                if name == "spectre":
                    warnings.append(message + " (non-blocking)")
                else:
                    fingerprint_ok = False
                    detail.append(message)

        # skill smoke through the daemon role
        if daemon.mode == "remote":
            tunnel_runner = _new_runner(daemon, token)
            tunnel_runner.start_port_forward(
                targets.local_port,
                remote_port=targets.daemon_port,
                deadline=budget.deadline,
            )
        skill = skill_client.execute_skill("1+1", timeout=budget.remaining())
        if daemon.mode == "remote":
            # right after the tunnel comes up the daemon may still be binding;
            # the retry loop spends the *same* step budget (no fresh window)
            while not skill.ok and not budget.expired():
                if not any(
                    "refused/reset" in (err or "") or "did not become ready" in (err or "")
                    for err in skill.errors
                ):
                    break
                time.sleep(0.5)
                try:
                    skill = skill_client.execute_skill("1+1", timeout=budget.remaining())
                except RegistrationProbeError:
                    break
    finally:
        if tunnel_runner is not None:
            tunnel_runner.stop_port_forward()
            tunnel_runner.close()
        if command_runner is not None:
            command_runner.close()

    skill_ok = skill.ok and (skill.output or "").strip().strip('"') == "2"
    token_ok = "invalid token" not in " ".join(skill.errors).lower()
    if not skill_ok:
        detail.append(f"skill={skill.status}:{skill.errors}")

    # 一次读取 identity 文件，同时用于 banner 记录与 host/user 比对——
    # 旧实现为 user 比对再读一次（remote 模式多花一条 SSH 命令）。
    identity_text = _identity_text(entry, user, budget=budget) or ""
    banner = _banner_hostname(entry, user, budget=budget, identity_text=identity_text)
    expected_hostname = entry.roles.daemon.expected_hostname
    warnings.extend(
        identity_warnings(
            identity_text,
            expected_hostname,
            entry.roles.daemon.expected_user,
        )
    )

    return ConnectivityReport(
        token=token,
        command_ok=command_ok,
        skill_ok=skill_ok,
        token_ok=token_ok,
        fingerprint_ok=fingerprint_ok,
        banner_hostname=banner,
        expected_hostname=expected_hostname,
        detail="; ".join(detail),
        warnings=warnings,
    )


# -- six-step orchestrator ------------------------------------------------------

class RegistrationFlow:
    """In-memory state machine for one manual six-step registration."""

    def __init__(
        self,
        registry: Registry,
        reservations: ReservationTable | None = None,
    ) -> None:
        self.registry = registry
        self.reservations = reservations or ReservationTable()
        self.state: RegistrationState | None = None

    # -- reservation plumbing (配置一览 §6.4) --------------------------------
    def _candidate_reservation(self, state: RegistrationState) -> Reservation:
        entry = state.entry
        daemon_port = None
        local_port = None
        if entry is not None:
            daemon_port = entry.roles.daemon.daemon_port
            local_port = entry.roles.daemon.local_port
        else:
            daemon_port = state.request.roles.daemon.daemon_port
            local_port = state.request.roles.daemon.local_port
        return Reservation.create(
            user=state.user,
            token=state.token,
            daemon_scope=daemon_scope_of_request(state.request),
            daemon_port=daemon_port,
            local_port=local_port,
        )

    def _reserve(self, state: RegistrationState) -> list[str]:
        return self.reservations.reserve(self._candidate_reservation(state))

    def _update_reservation(self, state: RegistrationState) -> list[str]:
        return self.reservations.update(self._candidate_reservation(state))

    def _prepare_local_port(self, state: RegistrationState) -> list[str]:
        """Step 2: pre-allocate / validate the local tunnel port.

        配置一览 §6.4: 第二步在内存分配候选（缺省 local_port 本机预分配；
        缺省远端 daemon_port 第三步分配并回写）。local 模式下 daemon_port 与
        local_port 是同一个候选端口，必须同步写入。
        """
        request = state.request
        role = request.roles.daemon
        mode = role.mode or request.mode.default
        reserved = self._reserved_local_ports_all()

        def unusable(port: int) -> bool:
            return port in reserved or not probes.local_port_free(port)

        if mode == "local":
            joint = role.local_port or role.daemon_port
            if joint is None:
                joint = probes.allocate_local_port(reserved=reserved)
                if joint is None:
                    return ["no free local tunnel port found"]
            elif unusable(joint):
                # local 模式下两者是同一个候选端口，按 daemon_port 的冲突
                # 语义报告（配置一览 §6.4 / 多用户与注册 §3 第二步）。
                return [
                    f"daemon port {joint} conflicts with another registration "
                    f"in progress or is already in use locally"
                ]
            role.daemon_port = joint
            role.local_port = joint
            return []

        if role.local_port is not None:
            if unusable(role.local_port):
                return [f"local port {role.local_port} is not usable"]
            return []
        allocated = probes.allocate_local_port(reserved=reserved)
        if allocated is None:
            return ["no free local tunnel port found"]
        role.local_port = allocated
        return []

    def _release_reservation(self, state: RegistrationState | None) -> None:
        if state is not None and state.user:
            try:
                self.reservations.release(state.user)
            except Exception:  # noqa: BLE001 - release is best effort
                logger.warning("failed to release reservation for %s", state.user)

    def _fail(self, state: RegistrationState, errors: list[str]) -> RegistrationState:
        state.stage = "failed"
        state.errors = list(errors)
        return state

    def cancel(self) -> RegistrationState | None:
        """Explicit cancellation: drop the reservation, keep the registry clean.

        多用户与注册 §3.3: cancel 只合法于任意非 committed 进行中会话；
        committed 会话不可被取消（幂等 no-op）。
        """
        if self.state is not None and self.state.stage != "committed":
            self._release_reservation(self.state)
            self.state.stage = "cancelled"
        return self.state

    def reserved_daemon_ports(self, daemon_scope: str | None = None) -> set[int]:
        """daemon ports held by *other* in-progress registrations.

        配置一览 §6.4: daemon_port 的唯一性作用域是 daemon 目标主机——同一
        端口号在不同 daemon host 上互不冲突。``daemon_scope=None`` 返回全部。
        """
        others = [
            r for r in self.reservations.records()
            if self.state is None or r.user != self.state.user
        ]
        return {
            r.daemon_port
            for r in others
            if r.daemon_port is not None
            and (
                daemon_scope is None
                or (r.daemon_scope or "local") == daemon_scope
            )
        }

    def reserved_local_ports(self) -> set[int]:
        """local tunnel ports held by *other* in-progress registrations."""
        others = [
            r for r in self.reservations.records()
            if self.state is None or r.user != self.state.user
        ]
        return {r.local_port for r in others if r.local_port is not None}

    def _registry_daemon_ports(self, daemon_scope: str | None) -> set[int]:
        """Committed users' daemon ports on one daemon target host (§6.4)."""
        ports: set[int] = set()
        for name, entry in self.registry.entries():
            port = entry.roles.daemon.daemon_port
            if port is None:
                continue
            if daemon_scope is None or daemon_scope_of_entry(entry, name) == daemon_scope:
                ports.add(port)
        return ports

    def _registry_local_ports(self) -> set[int]:
        """Committed users' local tunnel ports on this machine (§6.4)."""
        return {
            entry.roles.daemon.local_port
            for _, entry in self.registry.entries()
            if entry.roles.daemon.local_port is not None
        }

    def _reserved_local_ports_all(self) -> set[int]:
        return self.reserved_local_ports() | self._registry_local_ports()

    def start(self, request: RegistrationRequest) -> RegistrationState:
        self._release_reservation(self.state)
        token = request.token
        if token is None:
            token = uuid.uuid4().hex[:24]
            if self.registry.user_of(token) is not None:
                token = uuid.uuid4().hex[:24]
        self.state = RegistrationState(
            user=request.user, stage="applied", step=1, request=request, token=token
        )
        return self.state

    def _ensure(self, expected: str, step: int) -> RegistrationState | None:
        if self.state is None or self.state.request is None:
            raise RuntimeError("registration has not started")
        retry_same_step = (
            self.state.stage == "failed" and self.state.step == step
        )
        if self.state.stage != expected and not retry_same_step:
            return None
        self.state.step = step
        self.state.errors = []
        self.state.warnings = []
        self.state.report = None
        return self.state

    def validate(self) -> RegistrationState:
        state = self._ensure("applied", 2)
        if state is None:
            return self.state
        errors = validate_local(self.registry, state.request, state.token)
        if not errors:
            errors = self._prepare_local_port(state)
        if not errors:
            # reserve before touching the network so concurrent registrations
            # cannot pick the same user/token/ports
            errors = self._reserve(state)
        if errors:
            return self._fail(state, errors)
        state.stage = "validated"
        return state

    def probe(self) -> RegistrationState:
        state = self._ensure("validated", 3)
        if state is None:
            return self.state
        try:
            result = probe_user(
                state.request,
                token=state.token,
                reserved_ports=(
                    self.reserved_daemon_ports(
                        daemon_scope_of_request(state.request)
                    )
                    | self._registry_daemon_ports(
                        daemon_scope_of_request(state.request)
                    )
                ),
                reserved_local_ports=self._reserved_local_ports_all(),
            )
        except (RegistrationProbeError, Exception) as exc:  # noqa: BLE001
            if not isinstance(exc, RegistrationProbeError):
                logger.warning("probe failed with %s: %s", type(exc).__name__, exc)
            return self._fail(state, [str(exc)])
        state.entry = result.entry
        state.python_major = result.python_major
        state.warnings = list(result.warnings)
        # step 3 may have allocated the real ports: refresh the reservation so
        # other registrations see the final numbers
        conflicts = self._update_reservation(state)
        if conflicts:
            return self._fail(state, conflicts)
        state.stage = "probed"
        return state

    def _recheck_ports_before_deploy(self, state: RegistrationState, budget: StepBudget) -> None:
        """Step-4 TOCTOU check; one transparent re-allocation is allowed."""
        entry = state.entry
        daemon = resolve_candidate(entry, state.user).daemon
        if daemon.mode == "local":
            budget.remaining()
            port = entry.roles.daemon.daemon_port
            if port is None or not probes.local_port_free(port):
                replacement = probes.allocate_local_port(
                    reserved=self._reserved_local_ports_all()
                )
                if replacement is None:
                    raise RegistrationProbeError(
                        "daemon port changed before deploy and no replacement is free"
                    )
                entry.roles.daemon.daemon_port = replacement
                entry.roles.daemon.local_port = replacement
        else:
            if not daemon.host or not daemon.user:
                # Candidate entries produced by unit fakes may not be fully
                # populated; the real probe path always fills both fields.
                return
            runner = _BudgetedRunner(_new_runner(daemon, entry.token), budget)
            try:
                python_cmd = entry.roles.daemon.python or "python3"
                port = entry.roles.daemon.daemon_port
                if port is None or not probes.port_free_on_remote(
                    runner, port, python_cmd
                ):
                    replacement = probes.allocate_remote_port(
                        runner,
                        python_cmd,
                        reserved=(
                            self.reserved_daemon_ports(
                                daemon_scope_of_entry(entry, state.user)
                            )
                            | self._registry_daemon_ports(
                                daemon_scope_of_entry(entry, state.user)
                            )
                        ),
                    )
                    if replacement is None:
                        raise RegistrationProbeError(
                            "daemon port changed before deploy and no replacement is free"
                        )
                    entry.roles.daemon.daemon_port = replacement
                local_port = entry.roles.daemon.local_port
                if local_port is None or not probes.local_port_free(local_port):
                    replacement = probes.allocate_local_port(
                        reserved=self._reserved_local_ports_all()
                    )
                    if replacement is None:
                        raise RegistrationProbeError(
                            "local tunnel port changed before deploy and no replacement is free"
                        )
                    entry.roles.daemon.local_port = replacement
            finally:
                runner.close()
        conflicts = self._update_reservation(state)
        if conflicts:
            raise RegistrationProbeError("; ".join(conflicts))

    def deploy(self) -> RegistrationState:
        state = self._ensure("probed", 4)
        if state is None:
            return self.state
        try:
            budget = StepBudget("step 4 (deploy)")
            self._recheck_ports_before_deploy(state, budget)
            state.setup_path = deploy_user(
                state.entry, state.python_major, state.user, budget=budget
            )
        except Exception as exc:  # noqa: BLE001
            return self._fail(state, [f"deploy failed: {exc}"])
        state.stage = "deployed"
        # the user may take a long time to load the setup in the CIW: keep the
        # reservation fresh so a long wait is not mistaken for a crash
        try:
            self.reservations.touch(state.user)
        except Exception:  # noqa: BLE001
            pass
        return state

    def apply(self, request: RegistrationRequest) -> RegistrationState:
        self.start(request)
        self.validate()
        if self.state.stage == "validated":
            self.probe()
        if self.state.stage == "probed":
            self.deploy()
        return self.state

    def verify(self) -> RegistrationState:
        if self.state is not None and self.state.stage == "committed":
            return self.state
        if self.state is None or self.state.entry is None:
            stage = self.state.stage if self.state else None
            if stage in ("applied", "validated", "probed"):
                # a known, pre-deploy stage: this is an order violation, and the
                # caller needs to know what is missing (not a generic "nothing
                # in progress", which hides lost state)
                self.state.stage = "failed"
                self.state.errors = [
                    f"step order violation: verify requires stage 'deployed', "
                    f"got {stage!r}"
                ]
                return self.state
            self.state = RegistrationState(
                user=self.state.user if self.state else "", stage="failed",
                errors=["no registration in progress"],
            )
            return self.state
        retry_after_failure = (
            self.state.stage == "failed" and self.state.step == 5
        )
        if self.state.stage not in ("deployed", "failed") or (
            self.state.stage == "failed" and not retry_after_failure
        ):
            stage = self.state.stage
            self.state.stage = "failed"
            self.state.errors = [
                f"step order violation: verify requires stage 'deployed', got {stage!r}"
            ]
            return self.state
        if self.state.stage == "failed" and self.state.entry is None:
            self.state.errors = ["no registration in progress"]
            return self.state
        # spec 多用户与注册 §3.1: the connectivity test is retryable — a failed
        # step 5 keeps the candidate entry, so a fixed environment can simply
        # POST /verify again.

        state = self.state
        state.step = 5
        # §3.3: 同一步原样重试；上一次失败的错误/报告不得残留到成功结果里
        state.errors = []
        state.warnings = []
        state.report = None
        try:
            report = test_connectivity(state.entry, state.user)
        except Exception as exc:  # noqa: BLE001
            return self._fail(state, [f"connectivity test failed: {exc}"])

        state.report = report
        state.warnings = list(report.warnings)
        if not report.ok:
            return self._fail(state, [report.detail or "connectivity test failed"])

        # 第五步通过只报告连通性 OK，不落盘；第六步由用户显式确认触发
        state.stage = "verified"
        state.step = 5
        return state

    def commit(self) -> RegistrationState:
        """Step 6: the only durable write, after explicit user confirmation."""
        if self.state is not None and self.state.stage == "committed":
            return self.state
        if self.state is None or self.state.entry is None:
            self.state = RegistrationState(
                user=self.state.user if self.state else "", stage="failed",
                errors=["no registration in progress"],
            )
            return self.state
        retry_after_failed_commit = (
            self.state.stage == "failed" and self.state.step == 6
        )
        if self.state.stage != "verified" and not retry_after_failed_commit:
            stage = self.state.stage
            self.state.stage = "failed"
            self.state.errors = [
                f"step order violation: commit requires stage 'verified', got {stage!r}"
            ]
            return self.state

        state = self.state
        # BUG-2: commit 失败也必须停留在第 6 步，否则同一步原样重试会被
        # 服务端当作 step order violation（spec §3.3：各步失败均可原地重试）。
        state.step = 6
        state.errors = []
        errors = validate_commit_shape(state.entry, state.user)
        errors += validate_final(self.registry, state.entry, state.user)
        if errors:
            return self._fail(state, errors)
        state.entry.registered_at = int(time.time())
        try:
            self.registry.register(state.user, state.entry)
        except RegistryError as exc:
            return self._fail(state, [str(exc)])

        self._release_reservation(state)
        state.stage = "committed"
        state.step = 6
        return state


def register_user(
    registry: Registry, *, confirm_commit: bool = False, **fields
) -> RegistrationState:
    """One-shot convenience (apply + verify + commit) for scripted registration.

    多用户与注册 §3.1/§3.3: 第五步通过不自动保存，第六步必须由用户显式确认。
    因此本辅助函数要求 ``confirm_commit=True``；缺省直接拒绝，不落盘。
    """
    if not confirm_commit:
        raise ValueError(
            "register_user requires explicit confirm_commit=True: step 6 "
            "(registry write) is a user confirmation, never automatic"
        )
    flow = RegistrationFlow(registry)
    state = flow.apply(RegistrationRequest(**fields))
    if state.stage == "deployed":
        state = flow.verify()
    if state.stage == "verified":
        state = flow.commit()
    return state


__all__ = [
    "RegistrationFlow",
    "identity_user",
    "identity_warnings",
    "RegistrationProbeError",
    "deploy_user",
    "probe_user",
    "register_user",
    "test_connectivity",
    "validate_local",
]
