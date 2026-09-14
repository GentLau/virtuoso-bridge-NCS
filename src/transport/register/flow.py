"""Six-step registration flow (setup phase).

See ``spec/design-concepts/底层与中层/多用户设计.md`` §3.2:

1. 申请           submit required params (token generated here, no side effect)
2. 本地校验       user-name / port de-dup against the registry (no network)
3. 探测           remote/local environment probes -> candidate ``UserEntry``
4. 部署           upload daemon/il/setup, then hand the load prompt to the user
5. 连通性测试     daemon reachable + token match + dual smoke
6. 写入注册表     only after 1-5 succeed; the single write point

Five roles (gui/daemon/command/file/spectre) each fall back to
``ssh.default.*``; the corresponding probe runs on the corresponding role
(python/port/scratch -> daemon, command smoke -> command, file root -> file,
spectre bin -> spectre).  Spectre is only recorded this version: its SSH and
binary failures are WARNINGs, never registration blockers.
"""

from __future__ import annotations

import getpass
import logging
import shlex
import subprocess
import time
import uuid
from pathlib import Path

from transport.registry import (
    Registry,
    RegistryError,
    UserEntry,
    DaemonConfig,
    EndpointConfig,
    SpectreConfig,
    SshDefaults,
    endpoint_key,
)
from transport.remote_roles import resolve, ResolvedRole, ResolvedTargets
from transport.register import probe as probes
from transport.register.models import (
    ConnectivityReport,
    ProbeResult,
    RegistrationRequest,
    RegistrationState,
    RequestEndpoint,
)
from transport.deploy import deploy_files
from transport.remote_paths import identity_path
from transport.runtime_paths import working_dir
from transport.skill_client import SkillClient
from transport.ssh import SSHRunner

logger = logging.getLogger(__name__)

_LOCAL_DEFAULT_PORT = 65432
_BUSINESS_ROLES = ("gui", "daemon", "command", "file")


class RegistrationProbeError(RuntimeError):
    """A required probe failed; registration aborts without persisting."""


# -- step 2: local validation ------------------------------------------------

def validate_local(registry: Registry, request: RegistrationRequest) -> list[str]:
    """Pure-local checks: user-name and port de-dup inside the registry."""
    errors: list[str] = []
    if registry.get(request.user) is not None:
        errors.append(f"user {request.user!r} is already registered")

    daemon_port = request.role.daemon.daemon_port
    local_port = request.role.daemon.local_port
    for name, entry in registry.entries():
        if entry.route.daemon.daemon_port is not None and daemon_port is not None:
            if entry.route.daemon.daemon_port == daemon_port:
                errors.append(f"daemon port {daemon_port} conflicts with user {name!r}")
        if entry.route.daemon.local_port is not None and local_port is not None:
            if entry.route.daemon.local_port == local_port:
                errors.append(f"local port {local_port} conflicts with user {name!r}")
    return errors


# -- step 3: probe ------------------------------------------------------------

def _resolve_remote_scratch(runner, scratch_root: str) -> str:
    if not scratch_root.startswith("~"):
        return scratch_root
    result = runner.run_command('printf "%s" "$HOME"', timeout=10)
    home = result.stdout.strip()
    if result.returncode == 0 and home:
        return scratch_root.replace("~", home, 1)
    raise RegistrationProbeError("cannot resolve remote $HOME for scratch root")


def _as_endpoint(ep: RequestEndpoint) -> EndpointConfig:
    return EndpointConfig(
        host=ep.host, user=ep.user, jump_host=ep.jump_host,
        jump_user=ep.jump_user, proxy=ep.proxy,
    )


def _build_entry(request: RegistrationRequest, token: str) -> UserEntry:
    entry = UserEntry(token=token, mode=request.mode)
    entry.ssh.default = SshDefaults(
        host=request.ssh.default.host, user=request.ssh.default.user,
        jump_host=request.ssh.default.jump_host,
        jump_user=request.ssh.default.jump_user, proxy=request.ssh.default.proxy,
    )
    entry.route.gui = _as_endpoint(request.role.gui)
    entry.route.daemon = DaemonConfig(
        host=request.role.daemon.host, user=request.role.daemon.user,
        jump_host=request.role.daemon.jump_host,
        jump_user=request.role.daemon.jump_user, proxy=request.role.daemon.proxy,
        daemon_port=request.role.daemon.daemon_port,
        local_port=request.role.daemon.local_port,
    )
    entry.route.command = _as_endpoint(request.role.command)
    entry.route.file = _as_endpoint(request.role.file)
    entry.route.spectre = SpectreConfig(
        host=request.role.spectre.host, user=request.role.spectre.user,
        jump_host=request.role.spectre.jump_host,
        jump_user=request.role.spectre.jump_user, proxy=request.role.spectre.proxy,
        bin=request.role.spectre.bin,
    )
    _apply_policies(request, entry)
    return entry


def _apply_policies(request: RegistrationRequest, entry: UserEntry) -> None:
    """Copy the optional per-user policy fields from the catalog into the entry."""
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


def _resolved_request_role(ep: RequestEndpoint, default: RequestEndpoint) -> ResolvedRole:
    host = ep.host or default.host or ""
    user = ep.user or default.user
    jump_host = ep.jump_host or default.jump_host
    jump_user = ep.jump_user or default.jump_user
    proxy = ep.proxy or default.proxy
    return ResolvedRole(
        host=host, user=user, jump_host=jump_host, jump_user=jump_user,
        proxy=proxy, key=endpoint_key(host, user, jump_host, jump_user, proxy),
    )


def _new_runner(role: ResolvedRole, token: str) -> SSHRunner:
    return SSHRunner(
        host=role.host,
        user=role.user,
        jump_host=role.jump_host,
        jump_user=role.jump_user,
        proxy_url=role.proxy,
        control_identity=token,
    )


def _probe_local(request: RegistrationRequest, token: str) -> ProbeResult:
    hostname = probes.local_hostname()
    python_cmd, python_major = probes.local_python()
    daemon_port = request.role.daemon.daemon_port or _LOCAL_DEFAULT_PORT
    if not probes.local_port_free(daemon_port):
        raise RegistrationProbeError(f"daemon port {daemon_port} already in use locally")
    local_port = request.role.daemon.local_port
    if local_port is not None and local_port != daemon_port:
        raise RegistrationProbeError(
            f"local mode has no tunnel port: local_port must equal daemon_port "
            f"(got local_port={local_port}, daemon_port={daemon_port})"
        )
    local_port = daemon_port
    scratch = request.scratch_root
    if scratch in ("", "~/.virtuoso-bridge"):
        scratch = str(working_dir())
    if not probes.local_path_writable(scratch):
        raise RegistrationProbeError(f"deploy root not writable locally: {scratch}")

    entry = _build_entry(request, token)
    entry.expected.daemon_endpoint_hostname = hostname
    entry.expected.daemon_user = probes.local_user()
    entry.environment.remote_python = python_cmd
    entry.deploy.scratch_root = f"{scratch}/{request.user}"
    entry.route.daemon.daemon_port = daemon_port
    entry.route.daemon.local_port = local_port

    warnings: list[str] = []
    if request.role.spectre.bin:
        if not probes.local_executable_exists(request.role.spectre.bin):
            warnings.append(f"spectre bin not usable locally: {request.role.spectre.bin}")
        else:
            entry.route.spectre.bin = request.role.spectre.bin
    else:
        spectre_bin = probes.detect_local_spectre()
        if spectre_bin:
            entry.route.spectre.bin = spectre_bin
        else:
            warnings.append("no usable spectre found locally (non-blocking)")
    return ProbeResult(entry=entry, python_major=python_major, warnings=warnings)


def _probe_remote(
    request: RegistrationRequest,
    token: str,
    reserved_ports: set[int] | None = None,
    reserved_local_ports: set[int] | None = None,
) -> ProbeResult:
    default = request.ssh.default
    roles = {
        "gui": _resolved_request_role(request.role.gui, default),
        "daemon": _resolved_request_role(request.role.daemon, default),
        "command": _resolved_request_role(request.role.command, default),
        "file": _resolved_request_role(request.role.file, default),
        "spectre": _resolved_request_role(request.role.spectre, default),
    }
    warnings: list[str] = []
    fingerprints: dict[str, str] = {}
    runners: dict[str, SSHRunner] = {}

    def close_all():
        for runner in runners.values():
            try:
                runner.close()
            except Exception:
                pass

    try:
        # host-key + SSH reachability per role; spectre is warning-only
        for name in ("gui", "daemon", "command", "file", "spectre"):
            role = roles[name]
            runner = _new_runner(role, token)
            runners[name] = runner
            reachable = runner.test_connection()
            fp = probes.host_key_fingerprint(role.host)
            if name == "spectre":
                if not reachable:
                    warnings.append(f"spectre role SSH unreachable: {role.host} (non-blocking)")
                elif not fp:
                    warnings.append(
                        f"cannot obtain SSH host key fingerprint for spectre role "
                        f"{role.host} (non-blocking)"
                    )
                else:
                    fingerprints[role.key] = fp
                continue
            if not reachable:
                raise RegistrationProbeError(f"ssh unreachable for {name} role: {role.host}")
            if not fp:
                raise RegistrationProbeError(
                    f"cannot obtain SSH host key fingerprint for {name} role "
                    f"{role.host} (add it to known_hosts out-of-band first)"
                )
            fingerprints[role.key] = fp

        daemon = roles["daemon"]
        daemon_runner = runners["daemon"]

        hostname = probes.remote_hostname(daemon_runner)
        if not hostname:
            raise RegistrationProbeError(f"cannot resolve remote hostname on {daemon.host}")
        daemon_user = probes.remote_user(daemon_runner)
        if not daemon_user:
            raise RegistrationProbeError(f"cannot resolve daemon user on {daemon.host}")

        python = probes.detect_remote_python(daemon_runner)
        if python is None:
            raise RegistrationProbeError(f"no usable remote python found on {daemon.host}")
        python_cmd, python_major = python

        if request.role.daemon.daemon_port is not None:
            if not probes.port_free_on_remote(
                daemon_runner, request.role.daemon.daemon_port, python_cmd
            ):
                raise RegistrationProbeError(
                    f"daemon port {request.role.daemon.daemon_port} already in use "
                    f"on {daemon.host}"
                )
            daemon_port = request.role.daemon.daemon_port
        else:
            daemon_port = probes.allocate_remote_port(
                daemon_runner, python_cmd, reserved=reserved_ports
            )
            if daemon_port is None:
                raise RegistrationProbeError(f"no free remote daemon port found on {daemon.host}")

        scratch = _resolve_remote_scratch(daemon_runner, request.scratch_root)
        if not probes.remote_path_writable(daemon_runner, scratch):
            raise RegistrationProbeError(f"deploy root not writable on {daemon.host}: {scratch}")

        # command smoke on the command role
        command_runner = runners["command"]
        smoke = command_runner.run_command("echo vb-ok", timeout=15)
        if smoke.returncode != 0 or smoke.stdout.strip() != "vb-ok":
            raise RegistrationProbeError(
                f"command role smoke failed on {roles['command'].host}: "
                f"rc={smoke.returncode} err={smoke.stderr.strip()}"
            )

        # spectre binary: explicit -> validate, absent -> detect (both warning-only)
        spectre_runner = runners["spectre"]
        spectre_bin: str | None = None
        if request.role.spectre.bin:
            if probes.remote_executable_exists(spectre_runner, request.role.spectre.bin):
                spectre_bin = request.role.spectre.bin
            else:
                warnings.append(
                    f"spectre executable not usable on {roles['spectre'].host}: "
                    f"{request.role.spectre.bin} (non-blocking)"
                )
        else:
            detected = probes.detect_remote_spectre(spectre_runner)
            if detected:
                spectre_bin = detected
            else:
                warnings.append(
                    f"no usable spectre found on {roles['spectre'].host} (non-blocking)"
                )

        local_port = request.role.daemon.local_port
        if local_port is not None:
            if not probes.local_port_free(local_port):
                raise RegistrationProbeError(f"local port {local_port} is not usable on the caller")
        else:
            local_port = probes.allocate_local_port(reserved=reserved_local_ports)
            if local_port is None:
                raise RegistrationProbeError("no free local tunnel port found")

        entry = _build_entry(request, token)
        entry.route.daemon.daemon_port = daemon_port
        entry.route.daemon.local_port = local_port
        entry.expected.ssh_endpoints = fingerprints
        entry.expected.daemon_endpoint_hostname = hostname
        entry.expected.daemon_user = daemon_user
        entry.environment.remote_python = python_cmd
        entry.deploy.scratch_root = f"{scratch}/{request.user}"
        entry.route.spectre.bin = spectre_bin
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
    if request.mode == "local":
        return _probe_local(request, token)
    return _probe_remote(request, token, reserved_ports, reserved_local_ports)


# -- step 4: deploy ------------------------------------------------------------

def deploy_user(entry: UserEntry, python_major: int, user: str) -> str:
    """Deploy daemon/il/setup for a candidate entry; return the setup path."""
    targets = resolve(entry, user)
    runner = None
    if entry.mode != "local":
        runner = _new_runner(targets.daemon, entry.token)
    try:
        return deploy_files(
            runner=runner,
            token=entry.token,
            user=user,
            scratch_root=targets.scratch_root,
            python_major=python_major,
            python_cmd=entry.environment.remote_python or "python3",
            port=targets.daemon_port,
            local=entry.mode == "local",
        )
    finally:
        if runner is not None:
            runner.close()


# -- step 5: connectivity -------------------------------------------------------

def _short_host_match(a: str | None, b: str | None) -> bool:
    if not a or not b:
        return False
    return a.strip().split(".")[0].lower() == b.strip().split(".")[0].lower()


def _banner_hostname(entry: UserEntry, user: str) -> str | None:
    path = identity_path(user, entry.deploy.scratch_root)
    try:
        if entry.mode == "local":
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        else:
            targets = resolve(entry, user)
            runner = _new_runner(targets.daemon, entry.token)
            try:
                result = runner.run_command(f"cat {shlex.quote(path)}", timeout=10)
            finally:
                runner.close()
            text = result.stdout if result.returncode == 0 else ""
        for line in text.splitlines():
            if line.startswith("host="):
                return line[len("host="):].strip() or None
    except (OSError, RuntimeError):
        return None
    return None


def test_connectivity(entry: UserEntry, user: str) -> ConnectivityReport:
    """Step 5: daemon reachable + token match + host-key + dual smoke."""
    token = entry.token
    warnings: list[str] = []
    detail: list[str] = []
    targets = resolve(entry, user)
    local_port = entry.route.daemon.local_port or entry.route.daemon.daemon_port
    skill_client = SkillClient(
        host="127.0.0.1",
        port=local_port,
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
        expected_endpoints = entry.expected.ssh_endpoints or {}
        for name in _BUSINESS_ROLES:
            role = getattr(targets, name)
            current_fp = probes.host_key_fingerprint(role.host)
            expected_fp = expected_endpoints.get(role.key)
            if expected_fp and current_fp != expected_fp:
                fingerprint_ok = False
                detail.append(
                    f"host key fingerprint mismatch for {name} role {role.host}: "
                    f"current={current_fp} expected={expected_fp}"
                )
        spectre_role = targets.spectre
        current_fp = probes.host_key_fingerprint(spectre_role.host)
        expected_fp = expected_endpoints.get(spectre_role.key)
        if expected_fp and current_fp != expected_fp:
            warnings.append(
                f"spectre role host key mismatch for {spectre_role.host} "
                f"(non-blocking): current={current_fp} expected={expected_fp}"
            )

        command_runner = _new_runner(targets.command, token)
        tunnel_runner = _new_runner(targets.daemon, token)
        try:
            result = command_runner.run_command("echo vb-ok")
            command_ok = result.returncode == 0 and result.stdout.strip() == "vb-ok"
            if not command_ok:
                detail.append(f"command={result.returncode}:{result.stderr.strip()}")
            tunnel_runner.start_port_forward(
                local_port, remote_port=targets.daemon_port
            )
            ready_deadline = time.monotonic() + 60.0
            skill = skill_client.execute_skill("1+1")
            while time.monotonic() < ready_deadline and not skill.ok:
                if not any(
                    "refused/reset" in (err or "") or "did not become ready" in (err or "")
                    for err in skill.errors
                ):
                    break
                time.sleep(0.5)
                skill = skill_client.execute_skill("1+1")
        finally:
            tunnel_runner.stop_port_forward()
            command_runner.close()
            tunnel_runner.close()

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


# -- six-step orchestrator ------------------------------------------------------

class RegistrationFlow:
    """In-memory state machine for one manual six-step registration."""

    def __init__(self, registry: Registry) -> None:
        self.registry = registry
        self.state: RegistrationState | None = None

    def start(self, request: RegistrationRequest) -> RegistrationState:
        token = request.token or uuid.uuid4().hex[:24]
        self.state = RegistrationState(user=request.user, stage="applied", step=1, request=request, token=token)
        return self.state

    def _ensure(self, expected: str, step: int) -> RegistrationState | None:
        if self.state is None or self.state.request is None:
            raise RuntimeError("registration has not started")
        if self.state.stage != expected:
            return None
        self.state.step = step
        return self.state

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
        return state

    def probe(self) -> RegistrationState:
        state = self._ensure("validated", 3)
        if state is None:
            return self.state
        reserved = {
            e.route.daemon.daemon_port
            for _, e in self.registry.entries()
            if e.route.daemon.daemon_port is not None
        }
        reserved_local = {
            e.route.daemon.local_port
            for _, e in self.registry.entries()
            if e.route.daemon.local_port is not None
        }
        try:
            result = probe_user(
                state.request,
                token=state.token,
                reserved_ports=reserved,
                reserved_local_ports=reserved_local,
            )
        except RegistrationProbeError as exc:
            state.stage = "failed"
            state.errors = [str(exc)]
            return state
        state.entry = result.entry
        state.python_major = result.python_major
        state.warnings = list(result.warnings)
        state.stage = "probed"
        return state

    def deploy(self) -> RegistrationState:
        state = self._ensure("probed", 4)
        if state is None:
            return self.state
        try:
            state.setup_path = deploy_user(state.entry, state.python_major, state.user)
        except Exception as exc:  # noqa: BLE001
            state.stage = "failed"
            state.errors = [f"deploy failed: {exc}"]
            return state
        state.stage = "deployed"
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
            self.state = RegistrationState(
                user=self.state.user if self.state else "", stage="failed",
                errors=["no registration in progress"],
            )
            return self.state
        if self.state.stage != "deployed":
            self.state.stage = "failed"
            self.state.errors = [
                f"step order violation: verify requires stage 'deployed', "
                f"got {self.state.stage!r}"
            ]
            return self.state

        state = self.state
        state.step = 5
        try:
            report = test_connectivity(state.entry, state.user)
        except Exception as exc:  # noqa: BLE001
            state.stage = "failed"
            state.errors = [f"connectivity test failed: {exc}"]
            return state

        state.report = report
        state.warnings = list(report.warnings)
        if not report.ok:
            state.stage = "failed"
            state.errors = [report.detail or "connectivity test failed"]
            return state

        state.entry.registered_at = int(time.time())
        try:
            self.registry.register(state.user, state.entry)
        except RegistryError as exc:
            state.stage = "failed"
            state.errors = [str(exc)]
            return state

        state.stage = "committed"
        state.step = 6
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
