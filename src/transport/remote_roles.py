"""Resolve a registry entry into the five concrete role targets.

Each role carries ``host/user/jump_host/jump_user/proxy``; any unset field
falls back to the user's global ``ssh.default.*`` (配置一览 §2.2).  Roles that
resolve to the same endpoint share one SSH connection (keyed by ``endpoint_key``).
"""

from __future__ import annotations

from dataclasses import dataclass

from transport.registry import UserEntry, endpoint_key


@dataclass(frozen=True)
class ResolvedRole:
    host: str
    user: str | None
    jump_host: str | None
    jump_user: str | None
    proxy: str | None
    key: str  # endpoint_key(...): connection identity


@dataclass(frozen=True)
class ResolvedTargets:
    gui: ResolvedRole
    daemon: ResolvedRole
    command: ResolvedRole
    file: ResolvedRole
    spectre: ResolvedRole
    daemon_port: int
    local_port: int
    scratch_root: str
    spectre_bin: str | None


_LOCAL_HOST = "127.0.0.1"


def _resolve_role(role, default, *, local: bool, local_user: str) -> ResolvedRole:
    if local:
        return ResolvedRole(
            host=_LOCAL_HOST, user=local_user, jump_host=None, jump_user=None,
            proxy=None, key=endpoint_key(_LOCAL_HOST, local_user),
        )
    host = role.host or default.host
    user = role.user or default.user
    jump_host = role.jump_host or default.jump_host
    jump_user = role.jump_user or default.jump_user
    proxy = role.proxy or default.proxy
    return ResolvedRole(
        host=host or "", user=user, jump_host=jump_host, jump_user=jump_user,
        proxy=proxy, key=endpoint_key(host, user, jump_host, jump_user, proxy),
    )


def resolve(entry: UserEntry, user: str | None = None) -> ResolvedTargets:
    import getpass

    local = entry.mode == "local"
    local_user = getpass.getuser()
    dflt = entry.ssh.default
    r = entry.route

    gui = _resolve_role(r.gui, dflt, local=local, local_user=local_user)
    daemon = _resolve_role(r.daemon, dflt, local=local, local_user=local_user)
    command = _resolve_role(r.command, dflt, local=local, local_user=local_user)
    file = _resolve_role(r.file, dflt, local=local, local_user=local_user)
    spectre = _resolve_role(r.spectre, dflt, local=local, local_user=local_user)

    daemon_port = r.daemon.daemon_port or 65432
    local_port = r.daemon.local_port or daemon_port
    # scratch_root is already the per-user work directory
    # (~/.virtuoso-bridge/<user>); resolve() never appends a user segment.
    scratch = entry.deploy.scratch_root or "~/.virtuoso-bridge"
    return ResolvedTargets(
        gui=gui, daemon=daemon, command=command, file=file, spectre=spectre,
        daemon_port=daemon_port, local_port=local_port,
        scratch_root=scratch, spectre_bin=r.spectre.bin,
    )


__all__ = ["ResolvedRole", "ResolvedTargets", "resolve"]
