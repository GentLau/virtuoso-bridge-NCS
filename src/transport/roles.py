"""Resolve one verified registry entry into the five runtime role targets.

This module owns *usage-phase* role resolution only.  Registration must not
import it; registration has its own candidate resolution so setup and runtime
remain decoupled (spec: 多用户与注册 §1).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from common.registry import RoleConfig, UserEntry, endpoint_key


@dataclass(frozen=True)
class ResolvedRole:
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
class ResolvedTargets:
    gui: ResolvedRole
    daemon: ResolvedRole
    command: ResolvedRole
    file: ResolvedRole
    spectre: ResolvedRole
    daemon_port: int
    local_port: int
    python: str | None

    def role(self, name: str) -> ResolvedRole:
        return getattr(self, name)


def _resolve_role(entry: UserEntry, name: str, user: str) -> ResolvedRole:
    role: RoleConfig = getattr(entry.roles, name)
    mode = role.mode or entry.mode.default
    root = role.root
    if not root:
        base = entry.root.default or f"~/.virtuoso-bridge/{user}"
        root = f"{base.rstrip('/')}/{name}"
    if mode == "local":
        return ResolvedRole(
            name=name,
            mode=mode,
            host=None,
            user=None,
            jump_host=None,
            jump_user=None,
            proxy=None,
            root=root,
            key=None,
            expected_fingerprint=None,
            max_sessions=role.max_sessions,
        )
    dflt = entry.ssh.default
    host = role.host or dflt.host
    account = role.user or dflt.user
    if not host or not account:
        raise ValueError(f"role {name} is remote but host/user is unresolved")
    jump_host = role.jump_host or dflt.jump_host
    jump_user = role.jump_user or dflt.jump_user
    proxy = role.proxy or dflt.proxy
    return ResolvedRole(
        name=name,
        mode=mode,
        host=host,
        user=account,
        jump_host=jump_host,
        jump_user=jump_user,
        proxy=proxy,
        root=root,
        key=endpoint_key(host, account, jump_host, jump_user, proxy),
        expected_fingerprint=role.expected_fingerprint,
        max_sessions=role.max_sessions,
    )


def fingerprint_conflicts(entry: UserEntry, user: str | None = None) -> list[str]:
    """Compatibility helper for fingerprint consistency across shared endpoints."""
    targets = resolve(entry, user)
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


def resolve(entry: UserEntry, user: str | None = None) -> ResolvedTargets:
    """Resolve all five roles from an already validated registry entry."""
    user = user or entry.token
    gui = _resolve_role(entry, "gui", user)
    daemon = _resolve_role(entry, "daemon", user)
    command = _resolve_role(entry, "command", user)
    file = _resolve_role(entry, "file", user)
    spectre = _resolve_role(entry, "spectre", user)
    daemon_port = entry.roles.daemon.daemon_port or 65432
    local_port = entry.roles.daemon.local_port
    if daemon.mode == "local":
        if local_port not in (None, daemon_port):
            raise ValueError("local daemon requires local_port == daemon_port")
        local_port = daemon_port
    elif local_port is None:
        local_port = daemon_port
    return ResolvedTargets(
        gui=gui,
        daemon=daemon,
        command=command,
        file=file,
        spectre=spectre,
        daemon_port=daemon_port,
        local_port=local_port,
        python=entry.roles.daemon.python,
    )


__all__ = ["ResolvedRole", "ResolvedTargets", "fingerprint_conflicts", "resolve"]
