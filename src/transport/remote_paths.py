from __future__ import annotations

import posixpath

DEFAULT_SCRATCH_ROOT = "~/.virtuoso-bridge"


def scratch_root(root: str | None = None) -> str:
    value = root or DEFAULT_SCRATCH_ROOT
    if value.startswith("~"):
        from pathlib import Path
        value = str(Path(value).expanduser())
    return value.rstrip("/")


def user_dir(user: str, root: str | None = None) -> str:
    """User-visible remote directory keyed by the (unique) username.

    Tokens are only used for routing/verification, never in user-visible
    paths (see the multi-user design).
    """
    return posixpath.join(scratch_root(root), user)


def ramic_dir(user: str, root: str | None = None) -> str:
    return posixpath.join(user_dir(user, root), "ramic")


def setup_dir(user: str, root: str | None = None) -> str:
    return posixpath.join(user_dir(user, root), "setup")


def status_dir(user: str, root: str | None = None) -> str:
    return posixpath.join(user_dir(user, root), "status")


def daemon_path(user: str, python_major: int, root: str | None = None) -> str:
    name = "ramic_bridge_daemon_27.py" if python_major == 2 else "ramic_bridge_daemon_3.py"
    return posixpath.join(ramic_dir(user, root), name)


def il_path(user: str, root: str | None = None) -> str:
    return posixpath.join(ramic_dir(user, root), "ramic_bridge.il")


def setup_il_path(user: str, root: str | None = None) -> str:
    return posixpath.join(setup_dir(user, root), "virtuoso_setup.il")


def identity_path(user: str, root: str | None = None) -> str:
    return posixpath.join(status_dir(user, root), "daemon_identity.txt")


__all__ = [
    "DEFAULT_SCRATCH_ROOT",
    "daemon_path",
    "identity_path",
    "il_path",
    "ramic_dir",
    "scratch_root",
    "setup_dir",
    "setup_il_path",
    "status_dir",
    "user_dir",
]
