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
    entry.route.file.root = f"{scratch}/{token}"
    return ProbeResult(entry=entry, python_major=python_major)


def _probe_remote(request: RegistrationRequest, token: str) -> ProbeResult:
    from transport.ssh import SSHRunner

    host = request.resolved_host
    runner = SSHRunner(
        host,
        user=request.ssh_user,
        jump_host=request.jump_host,
        jump_user=request.jump_user,
    )
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
        daemon_port = probes.allocate_remote_port(runner, python_cmd)
        if daemon_port is None:
            raise RegistrationProbeError(f"no free remote daemon port found on {host}")

    scratch = _resolve_remote_scratch(runner, request.scratch_root)
    if not probes.remote_path_writable(runner, scratch):
        raise RegistrationProbeError(f"deploy root not writable on {host}: {scratch}")

    local_port = request.local_port or daemon_port
    entry = UserEntry(token=token, mode="remote")
    entry.route.skill.daemon_host = request.resolved_daemon_host
    entry.route.skill.daemon_port = daemon_port
    entry.route.skill.local_port = local_port
    entry.route.command.host = host
    entry.route.command.user = login_user
    entry.route.file.host = host
    entry.route.file.root = f"{scratch}/{token}"
    entry.route.jump.host = request.jump_host
    entry.route.jump.user = request.jump_user
    entry.expected.ssh_host_key_fingerprint = fingerprint
    entry.expected.daemon_endpoint_hostname = hostname
    entry.expected.daemon_user = daemon_user
    entry.expected.remote_python = python_cmd
    entry.deploy.scratch_root = scratch
    return ProbeResult(entry=entry, python_major=python_major)


def probe_user(request: RegistrationRequest, *, token: str) -> ProbeResult:
    """Step 3: probe and build a candidate entry.  Never touches the registry."""
    if request.mode == "local":
        return _probe_local(request, token)
    return _probe_remote(request, token)


# -- step 4: deploy ------------------------------------------------------------

def deploy_user(entry: UserEntry, python_major: int) -> str:
    """Deploy daemon/il/setup for a candidate entry; return the setup path."""
    remote = RemoteClient(entry, resolve(entry))
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


def _banner_hostname(entry: UserEntry) -> str | None:
    path = identity_path(entry.token, entry.deploy.scratch_root)
    try:
        if entry.mode == "local":
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        else:
            remote = RemoteClient(entry, resolve(entry))
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


def test_connectivity(entry: UserEntry) -> ConnectivityReport:
    """Step 5: daemon reachable + token match + command/skill smoke."""
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

    if entry.mode == "local":
        cmd = subprocess.run("echo vb-ok", shell=True, capture_output=True, text=True, timeout=15)
        command_ok = cmd.returncode == 0 and cmd.stdout.strip() == "vb-ok"
        if not command_ok:
            detail.append(f"command={cmd.returncode}:{cmd.stderr.strip()}")
        skill = skill_client.execute_skill("1+1")
    else:
        remote = RemoteClient(entry, resolve(entry))
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

    banner = _banner_hostname(entry)
    expected = entry.expected.daemon_endpoint_hostname
    if banner and expected and not _short_host_match(banner, expected):
        warnings.append(f"daemon banner host {banner!r} differs from expected {expected!r}")

    return ConnectivityReport(
        token=token,
        command_ok=command_ok,
        skill_ok=skill_ok,
        token_ok=token_ok,
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

    def apply(self, request: RegistrationRequest) -> RegistrationState:
        state = RegistrationState(user=request.user, request=request)
        state.token = request.token or uuid.uuid4().hex

        errors = validate_local(self.registry, request)
        if errors:
            state.stage = "failed"
            state.errors = errors
            self.state = state
            return state

        try:
            probe = probe_user(request, token=state.token)
        except RegistrationProbeError as exc:
            state.stage = "failed"
            state.errors = [str(exc)]
            self.state = state
            return state

        state.entry = probe.entry
        state.python_major = probe.python_major
        state.stage = "probed"

        try:
            state.setup_path = deploy_user(probe.entry, probe.python_major)
        except Exception as exc:  # noqa: BLE001
            state.stage = "failed"
            state.errors = [f"deploy failed: {exc}"]
            self.state = state
            return state

        state.stage = "deployed"
        self.state = state
        return state

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
        try:
            report = test_connectivity(state.entry)
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
