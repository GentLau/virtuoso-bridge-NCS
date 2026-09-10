"""Six-step registration flow (setup phase).

See ``spec/design-concepts/底层与中层/多用户设计.md`` §3.2:

1. 申请           submit required params (token generated here, no side effect)
2. 本地校验       user-name / port de-dup against the registry (no network)
3. 探测           remote/local environment probes -> candidate ``UserEntry``
4. 部署           upload daemon/il/setup, then hand the load prompt to the user
5. 连通性测试     daemon reachable + token match + dual smoke
6. 写入注册表     only after 1-5 succeed; the single write point

The runtime never imports this module; it only consumes ``registry.json``.
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from transport.registry import Registry, RegistryError, UserEntry
from transport.register import probe as probes
from transport.register.models import (
    ConnectivityReport,
    ProbeResult,
    RegistrationRequest,
    RegistrationState,
)
from transport.remote_paths import identity_path
from transport.remote_roles import resolve
from transport.runtime_paths import working_dir
from transport.skill_client import SkillClient
from transport.tunnel import RemoteClient

logger = logging.getLogger(__name__)

_LOCAL_DEFAULT_PORT = 65432


class RegistrationProbeError(RuntimeError):
    """A required probe failed; registration aborts without persisting."""


# -- step 2: local validation ------------------------------------------------

def validate_local(registry: Registry, request: RegistrationRequest) -> list[str]:
    """Pure-local checks: user-name and port de-dup inside the registry."""
    errors: list[str] = []
    if registry.get(request.user) is not None:
        errors.append(f"user {request.user!r} is already registered")

    for name, entry in registry.entries():
        if entry.route.skill.daemon_port is not None and request.daemon_port is not None:
            if entry.route.skill.daemon_port == request.daemon_port:
                errors.append(
                    f"daemon port {request.daemon_port} conflicts with user {name!r}"
                )
        if entry.route.skill.local_port is not None and request.local_port is not None:
            if entry.route.skill.local_port == request.local_port:
                errors.append(
                    f"local port {request.local_port} conflicts with user {name!r}"
                )
    return errors


# -- step 3: probe ------------------------------------------------------------

def _resolve_remote_scratch(runner, scratch_root: str) -> str:
    if not scratch_root.startswith("~"):
        return scratch_root
    result = runner.run_command('printf \'%s\' "$HOME"', timeout=10)
    home = result.stdout.strip()
    if result.returncode == 0 and home:
        return scratch_root.replace("~", home, 1)
    raise RegistrationProbeError("cannot resolve remote $HOME for scratch root")


def _apply_policies(request: RegistrationRequest, entry: UserEntry) -> None:
    """Copy the optional per-user policy fields from the catalog into the entry."""
    if request.ssh_backend:
        entry.ssh.backend = request.ssh_backend
    if request.ssh_max_sessions is not None:
        entry.ssh.max_sessions = request.ssh_max_sessions
    if request.ssh_proxy is not None:
        entry.ssh.proxy = request.ssh_proxy
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
    if request.spectre_host:
        entry.route.spectre.host = request.spectre_host
    if request.spectre_bin:
        entry.route.spectre.bin = request.spectre_bin


def _probe_local(request: RegistrationRequest, token: str) -> ProbeResult:
    hostname = probes.local_hostname()
    python_cmd, python_major = probes.local_python()
    daemon_port = request.daemon_port or _LOCAL_DEFAULT_PORT
    if not probes.local_port_free(daemon_port):
        raise RegistrationProbeError(f"daemon port {daemon_port} already in use locally")
    local_port = request.local_port or daemon_port
    scratch = request.scratch_root
    if scratch in ("", "~/.virtuoso-bridge"):
        scratch = str(working_dir())
    if not probes.local_path_writable(scratch):
        raise RegistrationProbeError(f"deploy root not writable locally: {scratch}")

    entry = UserEntry(token=token, mode="local")
    entry.route.skill.daemon_host = "127.0.0.1"
    entry.route.skill.daemon_port = daemon_port
    entry.route.skill.local_port = local_port
    entry.expected.daemon_endpoint_hostname = hostname
    entry.expected.daemon_user = probes.local_user()
    entry.expected.remote_python = python_cmd
    entry.deploy.scratch_root = scratch
    entry.route.file.root = f"{scratch}/{request.user}"
    _apply_policies(request, entry)
    return ProbeResult(entry=entry, python_major=python_major)


def _probe_remote(
    request: RegistrationRequest, token: str, reserved_ports: set[int] | None = None
) -> ProbeResult:
    from transport.ssh import SSHRunner

    host = request.resolved_host
    runner = SSHRunner(
        host,
        user=request.ssh_user,
        jump_host=request.jump_host,
        jump_user=request.jump_user,
    )
    try:
        return _probe_remote_with_runner(request, token, reserved_ports, runner, host)
    finally:
        runner.close()  # registration must leave no SSH master/socket behind


def _probe_remote_with_runner(
    request: RegistrationRequest,
    token: str,
    reserved_ports: set[int] | None,
    runner,
    host: str,
) -> ProbeResult:
    if not runner.test_connection():
        raise RegistrationProbeError(f"ssh unreachable: {host}")

    fingerprint = probes.host_key_fingerprint(host)
    if not fingerprint:
        raise RegistrationProbeError(f"cannot obtain SSH host key fingerprint for {host}")

    hostname = probes.remote_hostname(runner)
    if not hostname:
        raise RegistrationProbeError(f"cannot resolve remote hostname on {host}")

    login_user = request.ssh_user or probes.remote_user(runner)
    daemon_user = request.daemon_user or login_user
    if not login_user or not daemon_user:
        raise RegistrationProbeError(f"cannot resolve remote daemon user on {host}")
    if request.daemon_user and not probes.remote_user_exists(runner, daemon_user):
        raise RegistrationProbeError(f"daemon user does not exist on {host}: {daemon_user}")

    python = probes.detect_remote_python(runner)
    if python is None:
        raise RegistrationProbeError(f"no usable remote python found on {host}")
    python_cmd, python_major = python

    if request.daemon_port is not None:
        if not probes.port_free_on_remote(runner, request.daemon_port, python_cmd):
            raise RegistrationProbeError(f"daemon port {request.daemon_port} already in use on {host}")
        daemon_port = request.daemon_port
    else:
        daemon_port = probes.allocate_remote_port(
            runner, python_cmd, reserved=reserved_ports
        )
        if daemon_port is None:
            raise RegistrationProbeError(f"no free remote daemon port found on {host}")

    scratch = _resolve_remote_scratch(runner, request.scratch_root)
    if not probes.remote_path_writable(runner, scratch):
        raise RegistrationProbeError(f"deploy root not writable on {host}: {scratch}")

    # explicit tool paths are validated here while the daemon is still down
    if request.spectre_bin and not probes.remote_executable_exists(runner, request.spectre_bin):
        raise RegistrationProbeError(f"spectre executable not usable on {host}: {request.spectre_bin}")

    local_port = request.local_port
    if local_port is not None:
        if not probes.local_port_free(local_port):
            raise RegistrationProbeError(
                f"local port {local_port} is not usable on the caller"
            )
    else:
        local_port = probes.allocate_local_port()
        if local_port is None:
            raise RegistrationProbeError("no free local tunnel port found")
    entry = UserEntry(token=token, mode="remote")
    entry.route.skill.daemon_host = request.resolved_daemon_host
    entry.route.skill.daemon_port = daemon_port
    entry.route.skill.local_port = local_port
    entry.route.command.host = host
    entry.route.command.user = login_user
    entry.route.file.host = host
    entry.route.file.root = f"{scratch}/{request.user}"
    entry.route.jump.host = request.jump_host
    entry.route.jump.user = request.jump_user
    entry.expected.ssh_host_key_fingerprint = fingerprint
    entry.expected.daemon_endpoint_hostname = hostname
    entry.expected.daemon_user = daemon_user
    entry.expected.remote_python = python_cmd
    entry.deploy.scratch_root = scratch
    _apply_policies(request, entry)
    return ProbeResult(entry=entry, python_major=python_major)


def probe_user(
    request: RegistrationRequest,
    *,
    token: str,
    reserved_ports: set[int] | None = None,
) -> ProbeResult:
    """Step 3: probe and build a candidate entry.  Never touches the registry."""
    if request.mode == "local":
        return _probe_local(request, token)
    return _probe_remote(request, token, reserved_ports)


# -- step 4: deploy ------------------------------------------------------------

def deploy_user(entry: UserEntry, python_major: int, user: str) -> str:
    """Deploy daemon/il/setup for a candidate entry; return the setup path."""
    remote = RemoteClient(entry, resolve(entry), user)
    try:
        return remote.deploy(python_major=python_major)
    finally:
        remote.close()


# -- step 5: connectivity -------------------------------------------------------

def _short_host_match(a: str | None, b: str | None) -> bool:
    """Compare hostnames, tolerating short vs fully-qualified forms."""
    if not a or not b:
        return False
    return a.strip().split(".")[0].lower() == b.strip().split(".")[0].lower()


def _banner_hostname(entry: UserEntry, user: str) -> str | None:
    path = identity_path(user, entry.deploy.scratch_root)
    try:
        if entry.mode == "local":
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        else:
            remote = RemoteClient(entry, resolve(entry), user)
            try:
                # the identity file is written by the il on the daemon host
                result = remote.skill_runner.run_command(f"cat {shlex.quote(path)}", timeout=10)
            finally:
                remote.close()
            text = result.stdout if result.returncode == 0 else ""
        for line in text.splitlines():
            if line.startswith("host="):
                return line[len("host="):].strip() or None
    except (OSError, RuntimeError):
        return None
    return None


def test_connectivity(entry: UserEntry, user: str) -> ConnectivityReport:
    """Step 5: daemon reachable + token match + host-key + dual smoke.

    Everything that required a live daemon in step 3 is completed here.
    """
    token = entry.token
    warnings: list[str] = []
    detail: list[str] = []

    skill_client = SkillClient(
        host="127.0.0.1",
        port=resolve(entry).local_port,
        timeout=30.0,
        token=token,
        log_level=entry.cdslog.log_level,
        log_max_bytes=entry.cdslog.log_max_bytes,
    )

    fingerprint_ok = True
    if entry.mode == "local":
        cmd = subprocess.run("echo vb-ok", shell=True, capture_output=True, text=True, timeout=15)
        command_ok = cmd.returncode == 0 and cmd.stdout.strip() == "vb-ok"
        if not command_ok:
            detail.append(f"command={cmd.returncode}:{cmd.stderr.strip()}")
        skill = skill_client.execute_skill("1+1")
    else:
        expected_fp = entry.expected.ssh_host_key_fingerprint
        current_fp = probes.host_key_fingerprint(entry.route.skill.daemon_host)
        fingerprint_ok = (not expected_fp) or (current_fp == expected_fp)
        if expected_fp and not fingerprint_ok:
            detail.append(
                f"host key fingerprint mismatch: current={current_fp} expected={expected_fp}"
            )
        remote = RemoteClient(entry, resolve(entry), user)
        try:
            remote.ensure_tunnel()
            result = remote.run_command("echo vb-ok")
            command_ok = result.returncode == 0 and result.stdout.strip() == "vb-ok"
            if not command_ok:
                detail.append(f"command={result.returncode}:{result.stderr.strip()}")
            skill = skill_client.execute_skill("1+1")
        finally:
            remote.close()

    skill_ok = skill.ok and (skill.output or "").strip().strip('"') == "2"
    token_ok = "invalid token" not in " ".join(skill.errors).lower()
    if not skill_ok:
        detail.append(f"skill={skill.status}:{skill.errors}")

    banner = _banner_hostname(entry, user)
    expected = entry.expected.daemon_endpoint_hostname
    if banner and expected and not _short_host_match(banner, expected):
        warnings.append(f"daemon banner host {banner!r} differs from expected {expected!r}")

    return ConnectivityReport(
        token=token,
        command_ok=command_ok,
        skill_ok=skill_ok,
        token_ok=token_ok,
        fingerprint_ok=fingerprint_ok,
        banner_hostname=banner,
        expected_hostname=expected,
        detail="; ".join(detail),
        warnings=warnings,
    )


# -- orchestration -----------------------------------------------------------

class RegistrationFlow:
    """One in-progress registration: apply (steps 1-4) then verify (steps 5-6)."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.state: RegistrationState | None = None

    # step 1: submit the application (no side effects beyond the in-memory state)
    def start(self, request: RegistrationRequest) -> RegistrationState:
        state = RegistrationState(user=request.user, request=request, step=1)
        state.token = request.token or uuid.uuid4().hex
        state.stage = "applied"
        self.state = state
        return state

    def _ensure(self, expected_stage: str, step: int):
        if self.state is None or self.state.request is None:
            state = RegistrationState(
                user=self.state.user if self.state else "",
                stage="failed",
                errors=["no registration in progress"],
            )
            self.state = state
            return None
        if self.state.stage == "failed":
            return None
        state = self.state
        state.step = step
        return state

    # step 2: local registry checks (pure local, no network)
    def validate(self) -> RegistrationState:
        state = self._ensure("applied", 2)
        if state is None:
            return self.state
        errors = validate_local(self.registry, state.request)
        if errors:
            state.stage = "failed"
            state.errors = errors
        else:
            state.stage = "validated"
        self.state = state
        return state

    # step 3: remote/local environment probes
    def probe(self) -> RegistrationState:
        state = self._ensure("validated", 3)
        if state is None:
            return self.state
        reserved = {
            e.route.skill.daemon_port
            for _, e in self.registry.entries()
            if e.route.skill.daemon_port is not None
        }
        try:
            result = probe_user(state.request, token=state.token, reserved_ports=reserved)
        except RegistrationProbeError as exc:
            state.stage = "failed"
            state.errors = [str(exc)]
            self.state = state
            return state
        state.entry = result.entry
        state.python_major = result.python_major
        state.stage = "probed"
        self.state = state
        return state

    # step 4: upload daemon/il/setup; returns load instructions
    def deploy(self) -> RegistrationState:
        state = self._ensure("probed", 4)
        if state is None:
            return self.state
        try:
            state.setup_path = deploy_user(state.entry, state.python_major, state.user)
        except Exception as exc:  # noqa: BLE001
            state.stage = "failed"
            state.errors = [f"deploy failed: {exc}"]
            self.state = state
            return state
        state.stage = "deployed"
        self.state = state
        return state

    # steps 1-4 in one shot (used by the CLI and API compatibility endpoint)
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
            return self.state  # idempotent: step 6 is the terminal state
        if self.state is None or self.state.entry is None:
            state = RegistrationState(
                user=self.state.user if self.state else "",
                stage="failed",
                errors=["no registration in progress"],
            )
            self.state = state
            return state

        state = self.state
        state.step = 5
        try:
            report = test_connectivity(state.entry, state.user)
        except Exception as exc:  # noqa: BLE001
            state.stage = "failed"
            state.errors = [f"connectivity test failed: {exc}"]
            self.state = state
            return state

        state.report = report
        state.warnings = list(report.warnings)
        if not report.ok:
            state.stage = "failed"
            state.errors = [report.detail or "connectivity test failed"]
            self.state = state
            return state

        # step 6: the single registry write point.
        state.entry.registered_at = int(time.time())
        try:
            self.registry.register(state.user, state.entry)
        except RegistryError as exc:
            state.stage = "failed"
            state.errors = [str(exc)]
            self.state = state
            return state

        state.stage = "committed"
        state.step = 6
        self.state = state
        return state


def register_user(registry: Registry, **fields) -> RegistrationState:
    """One-shot convenience (apply + verify) for scripted local registration."""
    flow = RegistrationFlow(registry)
    state = flow.apply(RegistrationRequest(**fields))
    if state.stage == "deployed":
        state = flow.verify()
    return state


__all__ = [
    "RegistrationFlow",
    "RegistrationProbeError",
    "deploy_user",
    "probe_user",
    "register_user",
    "test_connectivity",
    "validate_local",
]
