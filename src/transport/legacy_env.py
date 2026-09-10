"""Legacy ``VB_*`` environment migration adapter (temporary).

Import is a one-shot ``load()``; every mapping below is a pure dict lookup.
Do not use this for the new routing path.
"""

from __future__ import annotations

import os
from pathlib import Path

from transport.registry import Registry, UserEntry

_cache: dict[str, str] | None = None


def load_legacy_env(path: str | Path | None = None) -> dict[str, str]:
    """Read the legacy .env once into memory (subsequent calls return cache)."""
    global _cache
    if _cache is not None:
        return _cache
    env: dict[str, str] = {}
    if path:
        p = Path(path)
        if p.is_file():
            for line in p.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                env[key.strip()] = value.strip()
    env.update({k: v for k, v in os.environ.items() if k.startswith("VB_")})
    _cache = env
    return env


def _get(env: dict[str, str], *keys: str) -> str | None:
    for key in keys:
        v = env.get(key)
        if v:
            return v
    return None


def import_user(
    registry: Registry,
    *,
    user: str,
    token: str,
    env_path: str | Path | None = None,
    profile: str | None = None,
) -> UserEntry:
    """Convert one legacy VB_* configuration into a registry entry and register."""
    env = load_legacy_env(env_path)
    suffix = f"_{profile}" if profile else ""
    host = _get(env, f"VB_REMOTE_HOST{suffix}", "VB_REMOTE_HOST")
    if not host:
        raise ValueError("VB_REMOTE_HOST is required")
    user_name = _get(env, f"VB_REMOTE_USER{suffix}", "VB_REMOTE_USER")

    entry = UserEntry(token=token, mode="local" if host in ("localhost", "127.0.0.1") else "remote")
    entry.route.skill.daemon_host = _get(env, f"VB_DAEMON_HOST{suffix}") or host
    entry.route.skill.daemon_port = int(_get(env, f"VB_REMOTE_PORT{suffix}") or 65081)
    entry.route.skill.local_port = int(_get(env, f"VB_LOCAL_PORT{suffix}") or entry.route.skill.daemon_port)
    entry.route.command.host = _get(env, f"VB_DEPLOY_HOST{suffix}") or _get(env, f"VB_GUI_HOST{suffix}") or host
    entry.route.command.user = user_name
    entry.route.file.host = entry.route.command.host
    entry.route.jump.host = _get(env, f"VB_JUMP_HOST{suffix}")
    entry.route.jump.user = _get(env, f"VB_JUMP_USER{suffix}")
    entry.expected.daemon_user = user_name
    entry.expected.remote_python = _get(env, f"VB_REMOTE_PYTHON{suffix}") or "python3"
    entry.deploy.scratch_root = _get(env, f"VB_REMOTE_SCRATCH_ROOT{suffix}") or "~/.virtuoso-bridge"
    entry.ssh.backend = _get(env, f"VB_SSH_BACKEND{suffix}") or "openssh"
    entry.ssh.max_sessions = int(_get(env, f"VB_SSH_MAX_SESSIONS{suffix}") or 10)
    entry.ssh.proxy = _get(env, f"VB_SSH_PROXY{suffix}")
    entry.runtime.channel_budget = int(_get(env, f"VB_SSH_MAX_SESSIONS{suffix}") or 10)
    registry.register(user, entry)
    return entry


__all__ = ["import_user", "load_legacy_env"]
