"""Resolve a registry entry into the five concrete role targets.

Each role carries ``mode / host / user / jump_host / jump_user / proxy / root``
(spec: 配置一览 §2.3).  ``mode=local`` means the client runs on that role's
target host: no SSH, direct local execution.  ``mode=remote`` means the middle
layer SSHes to the role's host/account.  Unset fields fall back to the global
defaults (``mode.default`` / ``ssh.default.*`` / ``root.default``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from transport.registry import RoleConfig, UserEntry, endpoint_key

_LOCAL_HOST = "127.0.0.1"
_DEFAULT_ROOT = "~/.virtuoso-bridge"
_DEFAULT_DAEMON_PORT = 65432


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
    key: str | None  # endpoint_key for remote roles; None for local roles
    expected_fingerprint: str | None


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


def _role_mode(role: RoleConfig, entry: UserEntry) -> Literal["local", "remote"]:
    return role.mode or entry.mode.default


def _role_root(role: RoleConfig, entry: UserEntry, user: str, name: str) -> str:
    base = entry.root.default or f"{_DEFAULT_ROOT}/{user}"
    base = base.rstrip("/")
    return (role.root or f"{base}/{name}").rstrip("/") or base


def _resolve_role(entry: UserEntry, name: str, user: str) -> ResolvedRole:
    role: RoleConfig = getattr(entry.roles, name)
    mode = _role_mode(role, entry)
    root = _role_root(role, entry, user, name)
    if mode == "local":
        return ResolvedRole(
            name=name, mode=mode, host=None, user=None, jump_host=None,
            jump_user=None, proxy=None, root=root, key=None,
            expected_fingerprint=None,
        )
    dflt = entry.ssh.default
    host = role.host or dflt.host
    ruser = role.user or dflt.user
    jump_host = role.jump_host or dflt.jump_host
    jump_user = role.jump_user or dflt.jump_user
    proxy = role.proxy or dflt.proxy
    return ResolvedRole(
        name=name, mode=mode, host=host, user=ruser, jump_host=jump_host,
        jump_user=jump_user, proxy=proxy, root=root,
        key=endpoint_key(host, ruser, jump_host, jump_user, proxy),
        expected_fingerprint=role.expected_fingerprint,
    )


def resolve(entry: UserEntry, user: str | None = None) -> ResolvedTargets:
    """Resolve all five roles.  ``user`` is the registry key (path identity)."""
    user = user or entry.token
    gui = _resolve_role(entry, "gui", user)
    daemon = _resolve_role(entry, "daemon", user)
    command = _resolve_role(entry, "command", user)
    file = _resolve_role(entry, "file", user)
    spectre = _resolve_role(entry, "spectre", user)
    daemon_port = entry.roles.daemon.daemon_port or _DEFAULT_DAEMON_PORT
    local_port = entry.roles.daemon.local_port or daemon_port
    return ResolvedTargets(
        gui=gui, daemon=daemon, command=command, file=file, spectre=spectre,
        daemon_port=daemon_port, local_port=local_port,
        python=entry.roles.daemon.python,
    )


def fingerprint_conflicts(entry: UserEntry, user: str | None = None) -> list[str]:
    """Check that roles sharing one endpoint carry the same fingerprint.

    Spec: 配置一览 §4.3 — 同 endpoint 被多个 remote role 共享时，各 role 的
    ``expected_fingerprint`` 必须一致。
    """
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


__all__ = ["ResolvedRole", "ResolvedTargets", "fingerprint_conflicts", "resolve"]
