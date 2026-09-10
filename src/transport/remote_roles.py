"""Resolve a registry entry into concrete host/user targets.

Defaults follow the documented chain:

    daemon_host ──> command.host ──> file.host ──> spectre.host
    daemon_user ──> command.user
    scratch_root ──> file.root
"""

from __future__ import annotations

from dataclasses import dataclass

from transport.registry import UserEntry


@dataclass(frozen=True)
class ResolvedTargets:
    skill_host: str
    skill_port: int
    local_port: int
    command_host: str
    command_user: str | None
    file_host: str
    file_root: str
    spectre_host: str | None
    spectre_bin: str | None
    jump_host: str | None
    jump_user: str | None
    scratch_root: str


def resolve(entry: UserEntry) -> ResolvedTargets:
    r = entry.route
    scratch = entry.deploy.scratch_root or "~/.virtuoso-bridge"
    daemon_host = r.skill.daemon_host or "127.0.0.1"
    daemon_port = r.skill.daemon_port or 65432
    local_port = r.skill.local_port or daemon_port
    daemon_user = entry.expected.daemon_user

    command_host = r.command.host or daemon_host
    command_user = r.command.user or daemon_user
    file_host = r.file.host or command_host
    file_root = r.file.root or f"{scratch}/{entry.token}"
    spectre_host = r.spectre.host or command_host

    return ResolvedTargets(
        skill_host=daemon_host,
        skill_port=daemon_port,
        local_port=local_port,
        command_host=command_host,
        command_user=command_user,
        file_host=file_host,
        file_root=file_root,
        spectre_host=spectre_host,
        spectre_bin=r.spectre.bin,
        jump_host=r.jump.host,
        jump_user=r.jump.user,
        scratch_root=scratch,
    )


__all__ = ["ResolvedTargets", "resolve"]
