"""Candidate resolver used only during registration.

Registration must remain independent from the runtime routing module: it works
on a not-yet-registered configuration whose roots may still be relative and
whose ports may still be unassigned.
"""
from __future__ import annotations

import os
import posixpath
from dataclasses import dataclass
from typing import Literal

from transport.registry import RoleConfig, UserEntry, endpoint_key

_DEFAULT_ROOT = "~/.virtuoso-bridge"
_DEFAULT_DAEMON_PORT = 65432


@dataclass(frozen=True)
class CandidateRole:
    name: str
    mode: Literal["local", "remote"]
    host: str | None
    user: str | None
    jump_host: str | None
    jump_user: str | None
    proxy: str | None
    root: str
    key: str | None
    expected_fingerprint: str | None
    max_sessions: int


@dataclass(frozen=True)
class CandidateTargets:
    gui: CandidateRole
    daemon: CandidateRole
    command: CandidateRole
    file: CandidateRole
    spectre: CandidateRole
    daemon_port: int
    local_port: int
    python: str | None

    def role(self, name: str) -> CandidateRole:
        return getattr(self, name)


def _role_root(role: RoleConfig, entry: UserEntry, user: str, name: str) -> str:
    base = entry.root.default or f"{_DEFAULT_ROOT}/{user}"
    base = base.rstrip("/")
    return (role.root or f"{base}/{name}").rstrip("/") or base


def _resolve_role(entry: UserEntry, name: str, user: str) -> CandidateRole:
    role: RoleConfig = getattr(entry.roles, name)
    mode = role.mode or entry.mode.default
    root = _role_root(role, entry, user, name)
    if mode == "local":
        return CandidateRole(
            name=name, mode=mode, host=None, user=None, jump_host=None,
            jump_user=None, proxy=None, root=root, key=None,
            expected_fingerprint=None, max_sessions=role.max_sessions,
        )
    dflt = entry.ssh.default
    host = role.host or dflt.host
    account = role.user or dflt.user
    jump_host = role.jump_host or dflt.jump_host
    jump_user = role.jump_user or dflt.jump_user
    proxy = role.proxy or dflt.proxy
    return CandidateRole(
        name=name, mode=mode, host=host, user=account,
        jump_host=jump_host, jump_user=jump_user, proxy=proxy, root=root,
        key=endpoint_key(host, account, jump_host, jump_user, proxy),
        expected_fingerprint=role.expected_fingerprint,
        max_sessions=role.max_sessions,
    )


def resolve_candidate(entry: UserEntry, user: str) -> CandidateTargets:
    gui = _resolve_role(entry, "gui", user)
    daemon = _resolve_role(entry, "daemon", user)
    command = _resolve_role(entry, "command", user)
    file = _resolve_role(entry, "file", user)
    spectre = _resolve_role(entry, "spectre", user)
    daemon_port = entry.roles.daemon.daemon_port or _DEFAULT_DAEMON_PORT
    local_port = entry.roles.daemon.local_port or daemon_port
    return CandidateTargets(
        gui=gui, daemon=daemon, command=command, file=file, spectre=spectre,
        daemon_port=daemon_port, local_port=local_port,
        python=entry.roles.daemon.python,
    )


def validate_commit_shape(entry: UserEntry, user: str) -> list[str]:
    """Validate the final registry shape immediately before the step-6 write."""
    errors: list[str] = []
    if entry.root.default is not None:
        errors.append("root.default must be null after probe")
    targets = resolve_candidate(entry, user)
    for name in ("gui", "daemon", "command", "file", "spectre"):
        role = targets.role(name)
        configured = getattr(entry.roles, name)
        if configured.root is None:
            if name != "spectre":
                errors.append(f"role {name}.root is required")
            continue
        if not (configured.root.startswith("/") or os.path.isabs(configured.root)):
            errors.append(f"role {name}.root must be absolute")
        if role.mode == "local":
            if any((configured.host, configured.user, configured.jump_host,
                    configured.jump_user, configured.proxy)):
                errors.append(f"role {name} is local but has connection fields")
        else:
            if not role.host or not role.user:
                errors.append(f"role {name} is remote but host/user is unresolved")
            if name != "spectre" and not configured.expected_fingerprint:
                errors.append(f"role {name}.expected_fingerprint is required")
    daemon_port = entry.roles.daemon.daemon_port
    local_port = entry.roles.daemon.local_port
    if daemon_port is None:
        errors.append("role.daemon.daemon_port is required")
    if local_port is None:
        errors.append("role.daemon.local_port is required")
    if targets.daemon.mode == "local" and daemon_port != local_port:
        errors.append("local daemon requires local_port == daemon_port")
    if not entry.roles.daemon.python:
        errors.append("role.daemon.python is required")
    return errors


def fingerprint_conflicts_candidate(entry: UserEntry, user: str) -> list[str]:
    targets = resolve_candidate(entry, user)
    by_key: dict[str, list[tuple[str, str]]] = {}
    for name in ("gui", "daemon", "command", "file", "spectre"):
        role = targets.role(name)
        if role.key and role.expected_fingerprint:
            by_key.setdefault(role.key, []).append((name, role.expected_fingerprint))
    errors: list[str] = []
    for key, items in by_key.items():
        values = {fp for _, fp in items}
        if len(values) > 1:
            roles = ", ".join(name for name, _ in items)
            errors.append(
                f"endpoint {key} has conflicting expected_fingerprint across roles: {roles}"
            )
    return errors


__all__ = [
    "CandidateRole",
    "CandidateTargets",
    "fingerprint_conflicts_candidate",
    "resolve_candidate",
    "validate_commit_shape",
]
